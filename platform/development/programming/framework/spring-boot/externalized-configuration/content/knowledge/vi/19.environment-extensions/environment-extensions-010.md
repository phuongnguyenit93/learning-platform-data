# Ranh giới giữa Spring Boot thuần, Spring Cloud Config, Consul và Vault

## 1. Mục tiêu và câu hỏi thiết kế

Một ứng dụng Spring Boot có thể chạy tốt chỉ với `application.yaml`, biến môi trường, command-line arguments và các file được mount vào container. Tuy nhiên, khi số lượng ứng dụng, môi trường, nhóm phát triển và dữ liệu nhạy cảm tăng lên, thường xuất hiện những yêu cầu như:

- Nhiều service cùng đọc một tập cấu hình trung tâm, có kiểm soát thay đổi và phiên bản.
- Một service cần lấy cấu hình theo **tên ứng dụng, profile và phiên bản** mà không chứa tất cả file trong JAR.
- Cần đọc những key/value từ một hạ tầng có khả năng service discovery và watch thay đổi.
- Secret không được đóng gói trong source hoặc image; thông tin đăng nhập phải có ACL, audit, vòng đời và khả năng cấp phát động.
- Người vận hành muốn biết khi cấu hình đổi thì instance nào đã nhận, khi nào cần restart, và trường hợp mất kết nối với nguồn cấu hình sẽ ra sao.

Ba sản phẩm thường được nhắc đến là **Spring Cloud Config**, **HashiCorp Consul** và **HashiCorp Vault**. Chúng có thể đưa dữ liệu về cùng một abstraction của Spring là `Environment`, nhưng **không có cùng mục đích, mô hình quản trị hoặc khả năng bảo mật**.

Bài học thuộc nhóm **Mở rộng Environment** trong chủ đề **Spring Boot Externalized Configuration**. Nhiệm vụ của bạn là nhận diện **ranh giới trách nhiệm**, không chỉ thuộc cú pháp `spring.config.import`.

Sau bài này, bạn có thể:

1. Nêu được Spring Boot **thuần** đã hỗ trợ những gì về externalized configuration.
2. Giải thích vai trò của `Environment`, `PropertySource`, Config Data API, placeholder và `@ConfigurationProperties`.
3. Chỉ ra điều Spring Boot thuần **không tự cung cấp**: một Config Server tập trung, Consul agent/KV hoặc Vault secret store.
4. Phân biệt Spring Cloud Config Server/Client với Spring Cloud Consul Config và Spring Cloud Vault Config.
5. Cấu hình import cho ba integration theo cách Config Data hiện đại.
6. Phân biệt việc **nạp cấu hình lúc startup** với **refresh runtime**, watch, bus và rotation secrets.
7. Lựa chọn chính sách fail-fast, fallback, retry và readiness có chủ đích.
8. Hiểu ranh giới bảo mật giữa cấu hình thường, thông tin nhạy cảm và dynamic credentials.
9. Chạy một ví dụ Spring Boot thuần; biết cách mở rộng thành từng biến thể Cloud độc lập.
10. Thiết kế kiểm thử và runbook cho local, Docker/Kubernetes và production.

**Môi trường minh họa:** Java 21, Spring Boot 3.3.13 và khi có Spring Cloud thì release train **2023.0.6** tương thích với bản Boot này theo tài liệu phiên bản chính thức. Những ví dụ dùng host, key và token giả; không cung cấp mật khẩu hoặc thông tin đăng nhập production.

## 2. Bản đồ tổng quan: cùng đích `Environment`, khác nguồn và trách nhiệm

Một biểu đồ tư duy:

```text
                         SPRING BOOT APPLICATION
                       +--------------------------+
                       |       Environment        |
                       |       PropertySources    |
                       |       ConfigData API     |
                       +------------+-------------+
                                    |
                           Resolution / Binding
                                    |
                 +------------------+------------------+
                 |                                     |
            @Value, ${...}                  @ConfigurationProperties
                 |                                     |
                 +------------------+------------------+
                                    |
                         Beans / Services

              Property sources đưa vào Environment:
    +-----------------+----------------+--------------------+
    | Spring Boot core| Cloud Config   | Consul Config      |
    | file/YAML/env    | remote Config  | Consul KV          |
    | CLI/configtree   | Server         |                    |
    +-----------------+----------------+--------------------+
                \             |                 /
                 \            |                /
                  \      các import/plugin     /
                   \          |               /
                    +---------+--------------+
                              |
                       Spring Cloud Vault
                         secret backends
```

Tất cả nguồn cuối cùng có thể cung cấp những key kiểu:

```text
demo.display-label
demo.retry-delay
spring.datasource.username
spring.datasource.password
```

Nhưng nơi dữ liệu được lưu, ai được phép đọc, ai kiểm duyệt thay đổi và có cần mạng để startup hay không **không được giải quyết chỉ bằng `Environment`**.

Một tóm tắt rất ngắn:

- **Boot thuần:** tiêu thụ, ưu tiên, chuyển đổi và bind cấu hình.
- **Cloud Config:** phân phối cấu hình tập trung tới nhiều ứng dụng, thường từ Git hoặc backend khác.
- **Consul Config:** đọc cấu hình từ KV store của Consul; Consul còn có discovery/health như một mảng chức năng riêng.
- **Vault:** quản lý bí mật, identity/authentication, policy và secret lifecycle; Spring Cloud Vault giúp ứng dụng dùng secret như property source.

Không sản phẩm nào mặc định giải quyết tất cả yêu cầu về rollout, quyền truy cập, refresh an toàn và vận hành. Những yêu cầu này cần thiết kế end-to-end.

## 3. Spring Boot thuần đã có những khả năng nào?

Spring Boot có hệ thống **Externalized Configuration** đủ mạnh để nhiều ứng dụng không cần bất kỳ Spring Cloud component nào.

### 3.1. `Environment` và các `PropertySource`

`Environment` cung cấp interface để lấy property theo tên:

```java
String mode = environment.getProperty("demo.mode");
```

Bên dưới, Spring tập hợp các `PropertySource` từ nhiều nguồn. Khi cùng khóa xuất hiện ở nhiều nơi, **thứ tự ưu tiên** quyết định giá trị hiệu lực. Boot bổ sung nhiều nguồn thông dụng và quy tắc xử lý profile.

Một project Spring Boot thuần có thể nhận dữ liệu từ:

- `application.properties` hoặc `application.yaml` trong classpath.
- File nằm ngoài JAR ở các vị trí mặc định hoặc do ứng dụng chỉ định.
- File profile-specific như `application-dev.yaml`.
- Biến môi trường, Java system property.
- Command-line args như `--demo.mode=from-cli`.
- `SPRING_APPLICATION_JSON` trong những ngữ cảnh hỗ trợ.
- Imported Config Data: file, thư mục `configtree:` và các location khác được Boot tích hợp.
- Custom `PropertySource`, `EnvironmentPostProcessor` hoặc Config Data SPI do chính ứng dụng/thư viện cung cấp.

Ví dụ:

```yaml
# application.yaml
demo:
  display-label: "Boot-only"
  retry-delay: 500ms
```

Ghi đè qua CLI:

```bash
java -jar app.jar --demo.display-label=from-cli
```

Không cần Config Server, Consul hoặc Vault để có hành vi này.

### 3.2. Placeholder và type-safe binding

Cấu hình có thể tham chiếu bằng placeholder:

```yaml
demo:
  service-name: billing
  display-label: "${demo.service-name:unknown}-worker"
```

Trong Java:

```java
@Value("${demo.display-label}")
String label;
```

Hoặc bind cả nhóm:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoSettings(
        String displayLabel,
        Duration retryDelay
) {}
```

`@ConfigurationProperties` hỗ trợ relaxed binding, conversion cho `Duration`, `DataSize`, `URI`, nested records, collections và validation phù hợp.

Các khả năng này **không yêu cầu** Spring Cloud. Khi bạn thêm Config Server/Consul/Vault, phần quan trọng thường là **thêm nguồn dữ liệu cho Binder đã tồn tại**, không phải thay một bộ Binder hoàn toàn mới.

### 3.3. Config Data và `spring.config.import`

Spring Boot cho phép import thêm dữ liệu:

```yaml
spring:
  config:
    import: "optional:file:./local-overrides.yaml"
```

Hoặc import một thư mục chứa các file, mỗi file đóng góp một property:

```yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
```

Ví dụ mount:

```text
/run/config/
  demo.display-label
  demo.retry-delay
```

Giá trị trong từng file trở thành property tương ứng. Một Kubernetes Secret hoặc ConfigMap được mount thành file có thể được đọc theo kiểu config tree này.

Điều cần nhớ:

> **Config Data API là cơ chế import và xử lý các location. Nó không tự tạo một máy chủ cấu hình tập trung, ACL của Vault hay watch cho Consul.**

Những prefix do integration cung cấp như `configserver:`, `consul:` và `vault://` cần thư viện tích hợp tương ứng trên classpath.

### 3.4. Mở rộng Boot thuần bằng SPI

Với yêu cầu đặc thù, có thể tạo:

- `EnvironmentPostProcessor`: thêm/chỉnh các nguồn trước giai đoạn tạo phần lớn bean.
- `PropertySource`: mô tả một nguồn cung cấp key/value.
- `ConfigDataLocationResolver`: nhận diện và phân giải một loại import location.
- `ConfigDataLoader`: tải dữ liệu từ location đã được phân giải.
- `ApplicationContextInitializer`: tùy biến context trong giai đoạn khởi tạo.

Đây là các **điểm mở rộng** của Boot/Framework. Tuy nhiên, tự viết một provider remote có thể đồng nghĩa bạn phải tự giải quyết TLS, auth, retry, caching, precedence, profile, logging và error handling. Với hạ tầng phổ biến, thư viện Spring Cloud đã cung cấp nhiều phần integration đó.

### 3.5. Spring Boot thuần không tự làm những gì?

Không mặc định cung cấp:

1. Một service độc lập phục vụ cấu hình từ Git cho toàn bộ microservices.
2. Giao thức tìm cấu hình theo `{application}/{profile}/{label}` của Spring Cloud Config Server.
3. Consul agent, Consul KV, catalog service discovery hoặc watch Consul.
4. Vault secret backend, cơ chế auth Vault, audit log hay lease cho dynamic credentials.
5. Một luồng fan-out tự động để tất cả instance cập nhật cấu hình khi Git thay đổi.
6. Đảm bảo `@Value` hoặc bean singleton đang chạy tự động được inject lại chỉ vì file nguồn thay đổi.

Boot cho phép **tích hợp và mở rộng**, nhưng không phải mọi hệ thống điều phối remote và secret đều được cài sẵn.

## 4. So sánh bốn lựa chọn trước khi thiết kế

| Tiêu chí | Boot thuần | Spring Cloud Config | Consul Config | Spring Cloud Vault |
| --- | --- | --- | --- | --- |
| Nguồn dữ liệu chính | File/YAML/env/CLI/config tree | Config Server và backend của server, thường Git | Consul KV | Vault secrets backends |
| Thêm hạ tầng riêng? | Không bắt buộc | Có Config Server | Có Consul agent/server | Có Vault server/cluster |
| Mục tiêu nổi bật | Đọc/bind cấu hình trong ứng dụng | Cấu hình tập trung, phân theo app/profile/label | KV cấu hình và tích hợp hệ sinh thái Consul | Secret, policy, auth, leases, rotation |
| Cấu hình phiên bản qua Git | Do pipeline/file quản lý | Có thể thông qua Git backend | Không phải mặc định là Git workflow | Không phải mục tiêu mặc định |
| Secret management chuyên dụng | Không | Không tự thay Vault | KV không tự thay Vault | Có |
| Service discovery | Không tự có | Không phải vai trò Config Server | Consul Discovery là module riêng | Không phải vai trò chính |
| Import hiện đại | File, configtree, v.v. | `configserver:` | `consul:` | `vault://` |
| Thay đổi khi đang chạy | Không tự làm | Cần refresh/bus hoặc restart được thiết kế | Có watch/refresh tùy cấu hình | Secret lifecycle cần thiết kế riêng |
| Phụ thuộc mạng lúc startup | Không, nếu chỉ local | Thường có | Thường có | Thường có |
| Bảo mật cần thiết | Quyền file/env và quản trị deployment | TLS, auth tới server, quyền Git/backend | ACL, TLS, KV policies, agent | Auth method, policies, TLS, token/lease lifecycle |

Những ô trên nói về **khả năng sản phẩm**; không có nghĩa mọi tính năng tự động bật khi thêm một dependency.

Ví dụ: dự án có `spring-cloud-starter-consul-config` không tự biến nó thành một ứng dụng service discovery. Consul discovery dùng module và cấu hình riêng, thường là `spring-cloud-starter-consul-discovery`.

## 5. Spring Cloud Config: nguồn cấu hình tập trung theo application/profile/label

### 5.1. Hai vai trò cần tách

Hệ sinh thái Spring Cloud Config có hai phần chính:

**Config Server:** một ứng dụng server cung cấp HTTP API để client lấy cấu hình. Nó đọc dữ liệu từ một `EnvironmentRepository`, thường là Git, nhưng có những backend khác tùy tích hợp.

**Config Client:** thư viện trong ứng dụng nghiệp vụ giúp nó đọc cấu hình remote từ Config Server và đưa các property vào `Environment` lúc khởi động.

Sơ đồ:

```text
 Git config repository
       |
       | branch/tag/commit, app config, profiles
       v
 +----------------------+
 | Spring Cloud Config  |
 |       Server         |
 |  HTTP API / configs  |
 +----------+-----------+
            |
       HTTP(S) requests
            |
      +-----+-------------+----------------+
      |                   |                |
      v                   v                v
 service-a           service-b        service-c
 Config Client       Config Client    Config Client
      |                   |                |
   Environment        Environment     Environment
```

Config Server không nhất thiết lưu tất cả giá trị trong Git. Nó là một **lớp phục vụ cấu hình** và một backend provider; Git chỉ là phương án rất thông dụng. Nếu chọn Git, bạn được lịch sử thay đổi và cơ chế review phù hợp quy trình, nhưng vẫn phải quản lý quyền repo và đường triển khai server.

### 5.2. Tên ứng dụng, profile, label

Một client thường có:

```yaml
spring:
  application:
    name: payment-service
  profiles:
    active: dev
```

Config Server có API theo dạng:

```text
/{application}/{profile}/{label}
```

Trong đó:

- `application`: thường là `spring.application.name`.
- `profile`: profile ứng dụng, ví dụ `default`, `dev`, `prod`.
- `label`: thường liên hệ branch/tag/commit ở Git backend; cách diễn giải phụ thuộc backend.

Ví dụ một request đọc metadata/config remote:

```text
GET http://localhost:8888/payment-service/dev
```

hoặc:

```text
GET http://localhost:8888/payment-service/dev/main
```

Response trả về tập các property sources theo app/profile/label. Việc `label` có phải `main` hay một branch khác cần thống nhất với repository thực tế.

**Đừng** mặc định mỗi lần một Git commit mới thì toàn bộ client đang chạy đã lập tức áp dụng cấu hình mới. Server đọc dữ liệu mới và client làm mới state là **hai quá trình**.

### 5.3. Cú pháp import của Config Client

Ví dụ client:

```yaml
spring:
  application:
    name: payment-service
  config:
    import: "configserver:http://config-server.internal:8888"
```

Cần có dependency **Spring Cloud Config Client** tương ứng trên classpath. Prefix `configserver:` không phải location do Boot thuần biết đọc.

Một biến thể cho dev khi server có thể vắng mặt:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

Trong mô hình Config Client, bỏ `optional:` giúp startup fail nếu không kết nối được Config Server. Thêm `optional:` cho phép xử lý trường hợp server không sẵn sàng theo hành vi client; ứng dụng phải có default local đủ an toàn nếu chọn startup trong tình huống đó.

**Cảnh báo:** `optional:` không phải cam kết vạn năng rằng mọi lỗi HTTP, auth, định dạng, secret hoặc bất kỳ integration nào đều bị bỏ qua. Mỗi provider có quy tắc xử lý lỗi riêng.

### 5.4. `bootstrap.yml` truyền thống và Config Data

Các phiên bản Spring Cloud cũ có mô hình **Bootstrap Context** với `bootstrap.yml`. Từ Spring Boot 2.4, Config Data API là hướng nhập cấu hình hiện đại và Spring Cloud Config Client dùng:

```properties
spring.config.import=optional:configserver:
```

Theo hướng này, **không cần tạo `bootstrap.yml` chỉ để kết nối Config Server**.

Chỉ dùng Bootstrap Context kiểu cũ khi có lý do cụ thể và hiểu các property như `spring.cloud.bootstrap.enabled` hoặc dependency `spring-cloud-starter-bootstrap`. Không trộn hai mô hình rồi mặc định chúng tương đương về thứ tự ưu tiên, startup và refresh.

### 5.5. Config Server không tự thay thế Vault

Git có thể quản lý cấu hình thường theo cách review được, nhưng không nên đẩy mật khẩu production, access token hoặc private key dạng plaintext lên Git rồi xem đó là secret management.

Ngay cả khi Config Server hỗ trợ mã hóa/giải mã hoặc backend tích hợp, quyền đọc repository, quyền truy cập server, đường vận chuyển, secret rotation và audit vẫn phải được thiết kế. Nếu nhu cầu cốt lõi là **quản lý vòng đời secret**, Vault hoặc secret manager chuyên dụng phù hợp hơn.

## 6. Consul: KV config và service discovery là hai chức năng khác nhau

HashiCorp Consul có thể đóng nhiều vai trò:

1. **Consul KV:** lưu dữ liệu key/value.
2. **Service Catalog/Discovery:** đăng ký, tìm service, health checks.
3. Các khả năng mạng và vận hành khác của nền tảng Consul.

Trong Spring Cloud:

- `spring-cloud-starter-consul-config` tích hợp **cấu hình từ Consul KV**.
- `spring-cloud-starter-consul-discovery` tích hợp **discovery và registration**.

Không dùng từ “Consul” như thể những module này là một tính năng duy nhất. Một ứng dụng có thể cần Consul Config mà không cần đăng ký service, hoặc dùng Discovery nhưng không đọc KV cho cấu hình ứng dụng.

### 6.1. Consul Config đưa KV vào Environment

Ví dụ:

```yaml
spring:
  application:
    name: payment-service
  config:
    import: "consul:localhost:8500"
```

Có thể dùng:

```yaml
spring:
  config:
    import: "optional:consul:"
```

với agent Consul ở `localhost:8500` trong môi trường dev. Spring Cloud Consul tạo các property sources theo tên ứng dụng/profile và các context chung. Theo cấu hình mặc định, những key có thể nằm dưới:

```text
config/payment-service,dev/
config/payment-service/
config/application,dev/
config/application/
```

Các context cụ thể và thứ tự ưu tiên có thể điều chỉnh qua `spring.cloud.consul.config.*`.

Một nguồn kiểu `config/application` có thể dùng chung; `config/payment-service` dành cho một ứng dụng. Nhưng đây là **quy ước tổ chức KV của integration**, không phải cấu trúc bắt buộc với mọi người dùng Consul.

### 6.2. Format KV, YAML, PROPERTIES

Consul KV lưu key/value. Spring Cloud Consul Config có thể diễn giải:

- Những key/value riêng lẻ theo layout tương ứng.
- Một blob YAML trong key `data` khi format được cấu hình là `YAML`.
- Một blob `.properties` trong key `data` khi format là `PROPERTIES`.
- Một số cách biểu diễn file tùy cấu hình và phiên bản.

Ví dụ:

```yaml
spring:
  cloud:
    consul:
      config:
        format: PROPERTIES
```

Khi đó key như:

```text
config/payment-service/data
```

có thể chứa:

```properties
demo.display-label=from-consul
demo.retry-delay=750ms
```

Cách này hữu ích cho demo hoặc một nhóm cấu hình nhỏ, nhưng với nhiều service nên xác định rõ quyền ghi KV, cơ chế review, backup và audit. Consul KV không tự mang lại một Git pull-request workflow.

### 6.3. Consul Watch không đồng nghĩa mọi bean tự cập nhật

Spring Cloud Consul có Config Watch theo dõi thay đổi key prefix (thông qua Consul API) và có thể phát `RefreshEvent` khi dữ liệu liên quan thay đổi.

Nhưng cần phân biệt:

```text
KV thay đổi
   -> watch phát hiện
      -> Spring nhận sự kiện refresh
         -> các bean/config cần refresh theo cơ chế hỗ trợ
            -> service thực sự dùng giá trị mới
```

Nếu một service giữ một `final String` đã được inject từ lúc startup hoặc một đối tượng có state phức tạp không được thiết kế refresh, không nên kết luận nó tự thay đổi tức thì.

**Watch là một khả năng phối hợp sự kiện**, không phải phép màu thay mọi object trong JVM.

### 6.4. Consul Discovery không phải Config Server

Nếu mục tiêu chỉ là “tìm endpoint hiện tại của service X”, service discovery có thể phù hợp. Không nên đưa mọi host/IP động vào một Git config file rồi coi đó là giải pháp discovery khi đã có service catalog hoặc Kubernetes Service DNS.

Ngược lại, nếu mục tiêu là “thuộc tính timeout của payment-service ở profile dev”, Consul Config hay Config Server mới là những phương án cấu hình cần xem.

## 7. Vault: quản lý secret chứ không chỉ là một KV khác

HashiCorp Vault có hệ thống chuyên dụng cho:

- Authentication: ứng dụng chứng minh identity trước khi được đọc secret.
- Authorization/policies: giới hạn đường secret và thao tác được phép.
- Audit: lưu dấu việc truy cập theo cấu hình Vault.
- Secret engines: KV, credentials động, PKI và các backend khác.
- Leases, renewal, revocation và rotation tùy secret engine.
- TLS và mô hình vận hành riêng cho hạ tầng bảo mật.

Spring Cloud Vault cho phép ứng dụng lấy secret và đưa chúng vào `Environment` như các property sources. Nhưng bản thân việc đưa secret vào `Environment` **không biến toàn bộ ứng dụng thành một hệ thống tự rotation hoàn chỉnh**.

### 7.1. Cú pháp import Vault

Trong Spring Cloud Vault:

```yaml
spring:
  application:
    name: payment-service
  config:
    import: "vault://"
```

`vault://` có thể import các context mặc định từ các secret backends được bật, chẳng hạn KV backend theo tên ứng dụng và profile. Với một context cụ thể, tài liệu có dạng:

```yaml
spring:
  config:
    import: "vault:///my/context/path"
```

Chính sách backend, mount, tên path, profile và quyền đọc phải được cấu hình theo hệ thống Vault đang dùng.

`vault://` **không phải** đường dẫn file và không phải URI của Config Server. Đây là một location resolver do Spring Cloud Vault tích hợp vào Config Data.

### 7.2. Authentication và identity của workload

Trong production, ứng dụng nên dùng một phương thức xác thực gắn với workload identity hoặc cơ chế được đội bảo mật phê duyệt, chẳng hạn Kubernetes authentication, AppRole hoặc Vault Agent tùy hạ tầng.

Trong lab, **token tĩnh** có thể được cấp từ biến môi trường để thử nghiệm, nhưng không nên commit token thật vào YAML/Git/image. Một static token bị lộ có thể được sử dụng theo quyền của token đó cho đến khi bị thu hồi/hết hạn.

Quy tắc quan trọng:

- Dùng TLS và xác thực certificate.
- Áp dụng least-privilege policies.
- Giới hạn đường KV/secret engines ứng dụng được đọc.
- Quản lý bootstrap credentials riêng, không nhét chúng vào cùng nơi đang cần quyền để lấy.
- Không ghi token, password hoặc secret values vào log.
- Phân loại endpoint health và actuator để tránh lộ giá trị.

### 7.3. Secret tĩnh và secret động

**KV secret** có thể chứa một API key hoặc password được đặt trước. Bạn có thể thay giá trị trong Vault nhưng ứng dụng đang chạy không nhất thiết nhận giá trị mới ngay.

**Dynamic secret** có thể được sinh theo role, có TTL/lease và có cơ chế thu hồi. Ví dụ database credentials có thể được cấp tạm thời.

Tuy nhiên, nếu một JDBC connection pool đã tạo connection bằng credential cũ, việc Vault cấp credential mới **không tự làm mọi connection sống đổi danh tính**. Bạn cần thiết kế lifecycle của pool, lease renewal, recreation, retry và xử lý truy cập bị thu hồi.

### 7.4. Vault không thay toàn bộ Config Server

Vault có thể lưu cả giá trị cấu hình thường qua KV, nhưng không vì thế mà nó luôn là lựa chọn tốt nhất cho hàng nghìn thông số không nhạy cảm. Cần cân nhắc:

- Quyền truy cập và chi phí quản lý secret engines.
- Nhu cầu review/diff các tham số thông thường.
- Tần suất thay đổi và chính sách rollout.
- Tương tác giữa quyền bảo mật với nhóm phát triển.
- Khả năng vận hành và mức độ sẵn có khi startup.
- Tài liệu versioning và lịch sử thay đổi.

Một thiết kế phổ biến là **Git/Config Server hoặc ConfigMap cho non-secret config**, còn **Vault hoặc secret manager cho sensitive data**.

## 8. Phân biệt thêm với Kubernetes ConfigMap và Secret

Trong Kubernetes:

- `ConfigMap` dùng cho cấu hình thường.
- `Secret` là một API object dành cho dữ liệu nhạy cảm; bảo mật thực tế phụ thuộc vào RBAC, encryption-at-rest, node access và cách mount/use.
- Cả hai có thể được truyền cho container qua environment hoặc mounted files.

Spring Boot thuần có thể đọc những giá trị đã được kubelet đưa vào process:

```text
Kubernetes ConfigMap/Secret
              |
          env hoặc volume
              |
      Spring Boot Environment
              |
       @ConfigurationProperties
```

Ví dụ dùng config tree mount:

```yaml
spring:
  config:
    import: "optional:configtree:/run/app-config/"
```

Nếu volume có file:

```text
/run/app-config/demo.display-label
```

thì Boot có thể đọc nội dung file làm value cho key `demo.display-label`.

Đây là **khả năng Boot thuần cộng với Kubernetes mounting**, không đồng nghĩa với việc bạn đã triển khai Spring Cloud Config hoặc Vault.

### 8.1. “Kubernetes Secret” và “Vault secret” có giống nhau không?

Không. Kubernetes Secret là object trong Kubernetes API có mô hình phân quyền/lưu trữ riêng; Vault là một hệ thống secret management với auth, policies và secret engines riêng.

Một operator hoặc CSI driver có thể đồng bộ/mount secret từ Vault vào pod để Boot đọc như file. Trong mô hình đó:

```text
Vault -> operator/CSI/agent -> file trong pod -> Boot configtree
```

App Spring Boot **có thể không cần Spring Cloud Vault dependency** vì việc truy xuất Vault do thành phần ngoài tiến trình thực hiện. Đây là một kiến trúc hợp lệ khi muốn tách ứng dụng khỏi Vault API, nhưng cần định nghĩa rõ refresh và thời điểm file được cập nhật.

### 8.2. Mounted file có tự refresh bean không?

Việc nội dung volume có thể được cập nhật không có nghĩa Spring Boot tự rebind `@ConfigurationProperties` hay thay field `@Value` đang lưu.

Với ứng dụng chỉ đọc cấu hình khi startup, chiến lược **rollout/restart có kiểm soát** thường rõ ràng hơn. Nếu cần cập nhật live, phải có một đường refresh riêng, kiểm thử cả dữ liệu và lifecycle của các service sử dụng.

## 9. Trách nhiệm chung của Config Data API và thư viện provider

Tại sao cùng một property:

```yaml
spring:
  config:
    import: "configserver:http://localhost:8888"
```

lại hoạt động khi có Cloud Config Client nhưng không hoạt động trên một ứng dụng Boot-only?

Bởi vì:

```text
Spring Boot core:
  - quản lý spring.config.import
  - tìm resolver theo loại location
  - nạp ConfigData khi có loader tương ứng
  - kết hợp PropertySources và precedence
  - làm dữ liệu khả dụng cho Binder

Thư viện provider:
  - nhận diện prefix configserver:/consul:/vault://
  - triển khai resolver/loader phù hợp
  - kết nối tới backend
  - auth, retry, error mapping, context resolution
```

Nếu không có provider, Boot không biết `"configserver:"` hoặc `"vault://"` là gì. Ngược lại, nếu thêm provider nhưng thiếu URL, import hoặc cấu hình auth, có thể gặp lỗi ngay từ giai đoạn startup.

**Một URL không tự cài plugin.** Hãy kiểm tra cả **dependency trên classpath** lẫn **import location**.

## 10. Version alignment: Boot 3.3.13 và Spring Cloud 2023.0.6

Khi tích hợp Spring Cloud, không nên chọn ngẫu nhiên từng version của Config Client, Consul hoặc Vault theo package trên Maven Central.

Bản lab:

```text
Java:             21
Spring Boot:      3.3.13
Spring Cloud:     2023.0.6 (release train)
Gradle:           một bản được Boot 3.3 hỗ trợ
```

Tài liệu release train 2023.0.6 liệt kê Spring Boot 3.3.13 là bản được hỗ trợ cho train đó. Một project khác dùng Boot mới hơn cần xem **bảng tương thích tại thời điểm nâng cấp**, thay vì giữ nguyên BOM 2023.0.6.

Trong Gradle, ví dụ thêm Spring Cloud BOM:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}
```

Sau đó khai báo starter mà không tự đặt version riêng:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-config'
```

Hoặc:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-consul-config'
```

Hoặc:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-vault-config'
```

Trong bài lab, **chọn một integration cho mỗi biến thể**, thay vì thêm tất cả starter cùng lúc rồi không biết thư viện nào đang chủ động tải property khi startup.

Các file build sắp tới dùng ví dụ Spring Boot 3.3.13; đây là phiên bản cố định để học có thể tái lập, không phải lời khẳng định nó là bản Spring Boot mới nhất tại mọi thời điểm.

## 11. Lab A: Spring Boot thuần, không hạ tầng remote

Trước tiên, tạo một ứng dụng console chạy được mà **không phụ thuộc mạng hay ba integration bên ngoài**.

Cấu trúc:

```text
external-config-boundaries/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/boundary/
    │   │   ├── BoundaryApplication.java
    │   │   └── DemoSettings.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/boundary/
            └── DemoSettingsTest.java
```

Dùng Spring Initializr với Java 21, Gradle, Spring Boot 3.3.x, không cần web dependency. File Gradle Wrapper (`gradlew`, `gradlew.bat`) lấy từ project được khởi tạo, không cần tự viết.

### 11.1. Gradle thuần

`settings.gradle`:

```groovy
rootProject.name = 'external-config-boundaries'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không có bất kỳ dependency Spring Cloud nào. Đây là điểm xuất phát để chứng minh Boot có thể nạp và bind cấu hình local mà không cần gọi Config Server.

### 11.2. Configuration record

`src/main/java/dev/example/boundary/DemoSettings.java`:

```java
package dev.example.boundary;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoSettings(
        String displayLabel,
        Duration retryDelay,
        boolean featureEnabled
) {}
```

YAML dùng kebab-case; record component dùng camelCase. Spring Boot Binder thực hiện relaxed binding và conversion cho `Duration`.

### 11.3. Main class

`src/main/java/dev/example/boundary/BoundaryApplication.java`:

```java
package dev.example.boundary;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }

    @Bean
    ApplicationRunner printSettings(
            DemoSettings settings,
            Environment environment) {
        return args -> {
            System.out.println("=== CONFIG BOUNDARIES ===");
            System.out.println("displayLabel = "
                    + settings.displayLabel());
            System.out.println("retryDelay = "
                    + settings.retryDelay());
            System.out.println("featureEnabled = "
                    + settings.featureEnabled());
            System.out.println("activeProfiles = "
                    + String.join(",", environment.getActiveProfiles()));
        };
    }
}
```

`@ConfigurationPropertiesScan` đăng ký record để Binder tạo bean. `ApplicationRunner` được gọi sau khi context đã chuẩn bị bean cần thiết, nên có thể quan sát dữ liệu đã binding.

### 11.4. YAML nền

`src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none

demo:
  display-label: "boot-local"
  retry-delay: 500ms
  feature-enabled: false
```

Tất cả key `demo.*` có giá trị local. Không có network call đến Config Server, Consul hoặc Vault.

### 11.5. Profile dev

`src/main/resources/application-dev.yaml`:

```yaml
demo:
  display-label: "boot-dev"
  feature-enabled: true
```

Chạy trên macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Kết quả chính:

```text
=== CONFIG BOUNDARIES ===
displayLabel = boot-local
retryDelay = PT0.5S
featureEnabled = false
activeProfiles =
```

Khi bật dev:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Kỳ vọng:

```text
displayLabel = boot-dev
retryDelay = PT0.5S
featureEnabled = true
activeProfiles = dev
```

Như vậy, profile, giá trị mặc định và type conversion đã hoạt động **không cần Spring Cloud**.

### 11.6. CLI và biến môi trường

Chạy:

```bash
./gradlew bootRun --args='--demo.display-label=from-cli --demo.retry-delay=2s'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.display-label=from-cli --demo.retry-delay=2s"
```

Hoặc từ môi trường:

Bash:

```bash
DEMO_DISPLAYLABEL=from-env ./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_DISPLAYLABEL = 'from-env'
.\gradlew.bat bootRun
Remove-Item Env:DEMO_DISPLAYLABEL
```

Các nguồn này được xử lý bằng cơ chế chuẩn của Spring Boot. Không có một server tập trung nào đang tham gia.

### 11.7. Integration test cho Boot-only

`src/test/java/dev/example/boundary/DemoSettingsTest.java`:

```java
package dev.example.boundary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.display-label=from-test",
        "demo.retry-delay=750ms",
        "demo.feature-enabled=true"
})
class DemoSettingsTest {

    @Autowired
    DemoSettings settings;

    @Test
    void bindsWithoutAnyCloudProvider() {
        assertEquals("from-test", settings.displayLabel());
        assertEquals(Duration.ofMillis(750), settings.retryDelay());
        assertTrue(settings.featureEnabled());
    }
}
```

Chạy:

```bash
./gradlew test
```

hoặc:

```powershell
.\gradlew.bat test
```

Test xác nhận Binder hoạt động mà không cần Config Server, Consul hay Vault. Đây là **đường nền**, rất quan trọng để khi thêm một provider có thể xác định lỗi nào do tích hợp remote và lỗi nào vốn thuộc application code.

## 12. Lab B: biến thể Spring Cloud Config Client

Từ project Boot-only, tạo một **nhánh thực hành hoặc bản sao thử nghiệm** cho Config Client. Đừng thêm tất cả integration vào build gốc rồi thay import liên tục nếu muốn cô lập lỗi.

### 12.1. Bổ sung BOM và starter

Giữ phần plugins, Java toolchain và test của `build.gradle`, thêm:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là bản **thay thế hoàn chỉnh phần `dependencies`**, không phải đoạn copy để tạo hai block trùng nhau trong cùng file.

### 12.2. Khai báo import trong application.yaml

Thay phần cấu hình bằng:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none
  config:
    import: "configserver:http://localhost:8888"

demo:
  display-label: "local-fallback"
  retry-delay: 500ms
  feature-enabled: false
```

Khi Config Server không sẵn sàng, import không có `optional:` khiến client không khởi động. Đây là **quyết định fail-fast** trong lab để cho thấy một dependency bên ngoài đã được thêm vào đường khởi động.

Để thử fallback ở môi trường dev:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

Khi server vắng mặt và được xử lý như optional, client có thể dùng local values. Trong production, hãy định nghĩa rõ trường hợp thiếu remote config có được phép tiếp tục hay phải thất bại.

### 12.3. Tạo Config Server độc lập để học

Tạo **project khác** tên `demo-config-server` với Spring Boot 3.3.13, Java 21, Spring Cloud BOM 2023.0.6 và dependency:

```groovy
implementation 'org.springframework.cloud:spring-cloud-config-server'
```

Main class:

```java
package dev.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

Để tránh cần Git server trong lab local, dùng **native filesystem backend** trong Config Server:

```yaml
server:
  port: 8888

spring:
  application:
    name: demo-config-server
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations: "file:./config-repo"
```

Tạo thư mục `config-repo` tại **working directory của Config Server**:

```text
demo-config-server/
  config-repo/
    demo-client.yaml
    demo-client-dev.yaml
```

`config-repo/demo-client.yaml`:

```yaml
demo:
  display-label: "from-config-server"
  retry-delay: 1s
  feature-enabled: true
```

`config-repo/demo-client-dev.yaml`:

```yaml
demo:
  display-label: "from-config-server-dev"
```

Đường `file:./config-repo` phụ thuộc working directory nơi process server chạy. Đường dẫn trên chỉ dành cho lab; production nên có backend được quản trị, xác thực và bảo vệ phù hợp.

### 12.4. Chạy hai tiến trình

1. Ở project server, chạy `./gradlew bootRun` hoặc `.\gradlew.bat bootRun`.
2. Kiểm tra server có thể trả cấu hình:

```bash
curl http://localhost:8888/demo-client/default
```

Khi không có curl trên Windows PowerShell:

```powershell
Invoke-RestMethod 'http://localhost:8888/demo-client/default'
```

3. Ở project client, chạy `bootRun`.
4. Quan sát `DemoSettings` được bind từ nguồn remote có hiệu lực.

Với server của ví dụ, kỳ vọng giá trị từ Config Server như:

```text
displayLabel = from-config-server
retryDelay = PT1S
featureEnabled = true
```

Trong một cấu hình phức tạp có nhiều property sources, giá trị cuối còn phụ thuộc precedence và các override như CLI/test/env. Một cách thử rõ là không khai báo cùng key ở quá nhiều nơi trong lab.

### 12.5. Chạy với profile dev

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Server có thể trả cấu hình theo `demo-client/dev`, dùng `demo-client-dev.yaml` làm một nguồn theo profile. Kỳ vọng `displayLabel` đến từ cấu hình dev, còn `retryDelay` có thể giữ giá trị remote nền nếu không có nguồn ưu tiên cao hơn ghi đè.

Spring Config Data có thể thực hiện nhiều request ở những pha khác nhau để xác định profile và nạp cấu hình theo profile. Nhìn thấy hơn một request đến Config Server **không tự có nghĩa** client đang lỗi hoặc bị lặp vô hạn.

### 12.6. Thay file server có tự cập nhật client?

Không nên mặc định như vậy. Sửa `demo-client.yaml` ở server chỉ thay **nguồn cấu hình phía server**. Client đang chạy có thể vẫn giữ những giá trị đã được bind lúc startup.

Để áp dụng thay đổi, bạn có thể:

- Restart client có kiểm soát.
- Dùng Spring Cloud Context/Actuator refresh nếu triển khai hỗ trợ và bảo vệ đúng.
- Dùng Spring Cloud Bus để phát tín hiệu refresh tới nhiều instance, kèm policy rollout.
- Thiết kế lại bean theo cơ chế refresh phù hợp, không giữ state bất biến mà vẫn mong mutate.

Refresh là một chủ đề riêng, được phân tích tại mục 15.

## 13. Lab C: biến thể Consul Config

Tạo một biến thể khác từ **Boot-only project**, không trộn dependency Config Client/Vault trong lần đầu thử.

### 13.1. Dependency và import

Giữ BOM:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}
```

Trong `dependencies` dùng:

```groovy
implementation 'org.springframework.boot:spring-boot-starter'
implementation 'org.springframework.cloud:spring-cloud-starter-consul-config'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

Trong `application.yaml`:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none
  config:
    import: "consul:localhost:8500"
  cloud:
    consul:
      config:
        format: PROPERTIES

demo:
  display-label: "local-fallback"
  retry-delay: 500ms
  feature-enabled: false
```

`consul:` là location do Spring Cloud Consul Config hỗ trợ, không phải bởi Boot-only. Với `optional:consul:`, client có thể thử môi trường dev khi Consul agent không sẵn sàng, nhưng policy production cần chọn rõ.

### 13.2. Chuẩn bị Consul dev agent

Nếu máy đã có Consul CLI, có thể chạy một agent dev riêng:

```bash
consul agent -dev
```

Đây là chế độ **chỉ để học**: không có các cam kết HA, ACL và TLS cần thiết cho production.

Với `format: PROPERTIES`, tạo một KV entry tại đường:

```text
config/demo-client/data
```

và value là nội dung text:

```properties
demo.display-label=from-consul
demo.retry-delay=900ms
demo.feature-enabled=true
```

Có thể tạo bằng giao diện HTTP của Consul, CLI hoặc API phù hợp. Trên Bash với Consul API:

```bash
curl -X PUT --data-binary \
  'demo.display-label=from-consul
demo.retry-delay=900ms
demo.feature-enabled=true' \
  http://localhost:8500/v1/kv/config/demo-client/data
```

Chỉ dùng endpoint localhost của agent dev trong bài học. Production Consul nên bật ACL, TLS và quản lý token/quyền theo hạ tầng hiện có.

### 13.3. Chạy client và quan sát

Chạy client:

```bash
./gradlew bootRun
```

hoặc PowerShell:

```powershell
.\gradlew.bat bootRun
```

Khi import và KV context đúng, giá trị được bind có thể là:

```text
displayLabel = from-consul
retryDelay = PT0.9S
featureEnabled = true
```

Không có logic parsing KV mới trong `DemoSettings`: đó vẫn là cùng bean Spring Boot. Điểm khác biệt là **property source đến từ Consul**.

### 13.4. Cập nhật KV: đọc lúc startup và Config Watch

Thay `demo.display-label` trong KV rồi quan sát client đang chạy. Đừng kết luận việc file/kv đã đổi sẽ tự rebind mọi bean.

Spring Cloud Consul Config có Config Watch theo dõi thay đổi prefix và phát refresh event. Tùy cấu hình và loại bean, việc áp dụng thay đổi có thể yêu cầu `@RefreshScope`, rebinding của Spring Cloud hoặc restart. Với một record constructor-bound, đừng kỳ vọng nó được mutate an toàn như một mutable JavaBean.

### 13.5. Nếu chỉ cần Discovery

Nếu một project chỉ muốn tìm các instance của `payment-service` để gọi HTTP thì **Consul Discovery starter** và load-balancing phù hợp hơn `consul-config` đơn thuần. Đó là một bài toán khác với `demo.retry-delay` lấy từ Consul KV.

Không nên thêm `spring-cloud-starter-consul-discovery` vào lab này trừ khi mục tiêu thực sự là service catalog.

## 14. Lab D: biến thể Spring Cloud Vault

Biến thể Vault phải được thử trong môi trường tách biệt và không dùng secret thật.

### 14.1. Dependency và import

Từ Boot-only project, giữ Spring Cloud BOM và thêm:

```groovy
implementation 'org.springframework.boot:spring-boot-starter'
implementation 'org.springframework.cloud:spring-cloud-starter-vault-config'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

Trong một cấu hình lab đơn giản:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "http://127.0.0.1:8200"
      authentication: TOKEN
      token: "${VAULT_TOKEN}"
      kv:
        enabled: true
        backend: secret
```

Lưu ý:

- URI HTTP chỉ dùng cho **Vault dev server localhost**; production phải dùng TLS.
- `${VAULT_TOKEN}` lấy giá trị từ môi trường; không ghi token thật vào file source.
- `vault://` import default KV contexts theo cấu hình backend, application name và profile.
- Mọi chính sách auth/policy/secret path trong hệ thống thật phải tuân theo môi trường Vault đó.

### 14.2. Khởi động Vault dev server

Nếu đã cài Vault CLI, trong môi trường local riêng:

```bash
vault server -dev
```

Vault dev mode có thể in ra token thử nghiệm và endpoint localhost. Đừng sao chép token vào Git, log lâu dài hay gửi qua kênh công khai. Cấu hình shell `VAULT_ADDR` và `VAULT_TOKEN` theo hướng dẫn của dev server **chỉ cho bài học**.

Ví dụ sau khi dev server sẵn sàng và CLI đã được xác thực, ghi dữ liệu giả:

```bash
vault kv put secret/demo-client \
  demo.display-label=from-vault \
  demo.retry-delay=1500ms \
  demo.feature-enabled=true
```

Đường secret thực tế có thể phụ thuộc KV v1/v2, mount path và config của Vault. Bài này dùng default KV backend trong dev mode để minh họa.

### 14.3. Không in secret trong runner

Trong lab, chúng ta đưa những key `demo.*` **không nhạy cảm** vào Vault để quan sát binding. Trong production, Vault nên phục vụ các secret như:

```text
payment.api-token
spring.datasource.password
```

Không thêm `System.out.println(settings.apiToken())`, không log toàn bộ record có token và không mở endpoint `/actuator/env` cho mọi người. Khi cần kiểm chứng, chỉ xác nhận cấu hình có được nạp và các phần không nhạy cảm, ví dụ trạng thái `present/absent`.

### 14.4. `optional:vault://` cần hiểu theo semantics của Vault

Một số provider xử lý `optional:` khác nhau. Theo tài liệu Spring Cloud Vault, optional Vault location đặc biệt liên quan trường hợp Vault support đã bị vô hiệu hóa bằng `spring.cloud.vault.enabled=false`; secret context trả 404 có quy tắc xử lý riêng và tùy `fail-fast`.

Vì vậy, **đừng giả định** rằng:

```yaml
spring:
  config:
    import: "optional:vault://"
```

luôn có nghĩa “Vault down thì âm thầm dùng default” giống hệt một optional file hoặc optional Config Server. Cần test đúng phiên bản Spring Cloud Vault, tình huống mất kết nối, lỗi auth (401/403), secret path không tồn tại và các option fail-fast.

Đối với cấu hình phụ thuộc secret bắt buộc, phương án an toàn thường là **không cho ứng dụng sẵn sàng nếu không lấy được secret hoặc secret không hợp lệ**.

## 15. Thay đổi runtime: startup load, refresh, watch, bus, restart

Một lỗi tư duy rất phổ biến:

> “Tôi đã đưa cấu hình vào một server tập trung, nên sửa server là mọi ứng dụng nhận ngay.”

Thực tế có ít nhất bốn giai đoạn:

```text
A. Source changed
   Git commit / Consul KV update / Vault secret rotation
                       |
                       v
B. Change detected
   manual poll / webhook / watch / bus / restart
                       |
                       v
C. Environment updated
   property sources được tải lại theo cơ chế hỗ trợ
                       |
                       v
D. Application components apply change
   bean rebind, @RefreshScope, recreate resource, restart...
```

Nếu hệ thống chỉ thực hiện A và B mà không có D, nghiệp vụ có thể tiếp tục sử dụng giá trị cũ.

### 15.1. `@Value` là một snapshot tại điểm inject

Một field:

```java
@Value("${demo.display-label}")
private String displayLabel;
```

thường được gán lúc tạo bean. Khi backend remote thay đổi, field này không tự theo dõi một topic hay một file watcher. Một cơ chế refresh có thể giúp tạo lại bean hoặc inject lại tùy scope, nhưng không nên mặc định tất cả field đều live-update.

### 15.2. `@ConfigurationProperties` cũng cần chiến lược refresh

Spring Cloud có cơ chế rebinding một số bean `@ConfigurationProperties`, nhưng kết quả phụ thuộc type và cấu hình:

- Mutable JavaBeans có thể được rebind trong một số luồng refresh.
- Record và đối tượng constructor-bound bất biến **không tự được rebind như JavaBean mutable**.
- Một service giữ tham chiếu hoặc copy giá trị từ lúc khởi động có thể tiếp tục dùng state cũ.
- Tài nguyên như `DataSource`, HTTP client, scheduler và connection pool cần kiểm soát vòng đời thay vì chỉ đổi một String.

Với các cấu hình ảnh hưởng tới invariant hệ thống, một rolling restart có thể dễ quản lý và kiểm thử hơn live refresh từng phần.

### 15.3. `@RefreshScope` có giới hạn

`@RefreshScope` trong Spring Cloud tạo khả năng làm mới target bean khi cache scope bị invalidated. Nó giúp một bean được tạo lại với những giá trị mới trong những tình huống được hỗ trợ.

Tuy vậy:

- Không phải mọi loại bean đều refresh an toàn.
- Tài nguyên được chia sẻ có thể cần xử lý graceful shutdown/recreation.
- Constructor-bound configuration records không tự trở thành mutable.
- Những bean phụ thuộc vào bean được refresh không nhất thiết đều được tái tạo.
- Spring Cloud refresh scope **không được hỗ trợ theo cách tương tự trên AOT/native images**; tài liệu khuyến nghị vô hiệu hóa refresh khi cần native.

Đừng thêm `@RefreshScope` lên mọi class và xem như đã có một cơ chế rollout không gián đoạn.

### 15.4. `/actuator/refresh` là endpoint quản trị nhạy cảm

Spring Cloud Context có thể cung cấp `/actuator/refresh` khi có dependency/cấu hình phù hợp. Endpoint không được mặc định công khai cho Internet.

Nếu bật:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: refresh
```

phải có cơ chế xác thực, phân quyền, network policy và audit. Trong hệ thống thật, nên dùng deployment workflow có thể kiểm soát, thay vì cho bất kỳ caller nào ép refresh instance.

### 15.5. Consul Watch, Cloud Bus và refresh khác nhau

- **Consul Watch:** phát hiện KV thay đổi và phát event theo integration.
- **Spring Cloud Bus:** truyền sự kiện điều phối giữa nhiều instances khi có hạ tầng message broker và cấu hình tương ứng.
- **Actuator refresh:** một cơ chế kích hoạt nạp lại một phần context/config cho instance.
- **Restart/rolling deployment:** tạo tiến trình/bean graph mới từ cấu hình hiệu lực.

Đây là những cơ chế **bổ sung**, không phải tên gọi khác nhau của cùng một chức năng. Chọn chúng dựa trên yêu cầu consistency, tốc độ áp dụng và khả năng rollback.

## 16. `optional`, fail-fast và hành vi mất kết nối

Khi nguồn cấu hình ở xa, sự cố hạ tầng có thể trở thành sự cố khởi động ứng dụng.

Hãy phân loại dữ liệu:

**Nhóm A — cấu hình quan trọng, không được chạy sai:** database credentials, security policy, endpoint production bắt buộc, encryption material.

**Nhóm B — cấu hình có fallback hợp lệ:** nhãn hiển thị, timeout có giá trị mặc định an toàn, feature flag với default rõ và đã kiểm thử.

Chính sách cần khác nhau.

| Trường hợp | Hành vi phù hợp để cân nhắc |
| --- | --- |
| Thiếu file local tùy chọn | `optional:file:` và default đã kiểm thử |
| Config Server down, mọi cấu hình bắt buộc là remote | Fail startup, retry có giới hạn, health/readiness phù hợp |
| Config Server down, remote chỉ bổ sung một tính năng không quan trọng | Optional với local fallback an toàn |
| Consul KV down nhưng dữ liệu là chính sách quan trọng | Fail-fast hoặc cơ chế cache/restart được phê duyệt |
| Vault authentication thất bại | Không tự dùng credential giả; báo lỗi và không nhận traffic |
| Vault secret không tồn tại | Kiểm tra backend path, role, policy và fail-fast |
| Server trả dữ liệu sai schema | Conversion/validation phải từ chối dữ liệu không hợp lệ |
| Nguồn remote thay đổi trong lúc phục vụ | Refresh/restart với tính nhất quán được thiết kế |

**Không áp dụng một chính sách `optional:` cho mọi loại provider rồi coi toàn bộ hệ thống đã an toàn.**

### 16.1. Retry không thay validation

Có những lỗi nên retry: network timeout tạm thời, backend đang khởi động. Có những lỗi retry không giúp gì: sai token, sai ACL, URL không hợp lệ, cấu hình thiếu field bắt buộc.

Một retry policy tốt cần:

- Giới hạn số lần thử và tổng thời gian.
- Backoff hợp lý, có jitter khi nhiều client cùng khởi động.
- Phân biệt lỗi khả năng khôi phục.
- Không in thông tin nhạy cảm trong log.
- Đưa readiness về trạng thái phù hợp khi không có cấu hình bắt buộc.
- Có cảnh báo và số liệu để vận hành biết backend đang bị sự cố.

### 16.2. Caching và fallback có rủi ro

Một client/Config Server có thể giữ bản dữ liệu đã tải hoặc backend có caching. Khi backend source tạm không sẵn sàng, cache có thể duy trì hoạt động.

Nhưng cần hỏi:

- Cache còn hạn sử dụng bao lâu?
- Nó thuộc về server, client hay một sidecar?
- Giá trị có được phép quá hạn không?
- Có chứa secret đã bị thu hồi không?
- Khi khôi phục, hệ thống biết dùng version nào?
- Có cơ chế đánh dấu stale configuration không?

Không coi cache là bằng chứng dữ liệu đang mới hoặc an toàn.

## 17. Thứ tự ưu tiên nguồn: “remote” không mặc định là tuyệt đối

Khi nhiều nguồn có cùng key:

```text
demo.display-label
```

giá trị cuối phụ thuộc **PropertySource precedence** và cách provider chèn nguồn vào `Environment`.

Ví dụ có thể tồn tại đồng thời:

```text
application.yaml
application-dev.yaml
Consul KV
Config Server
Vault KV
Java system properties
environment variables
command-line arguments
```

Không nên lấy một thứ tự tĩnh từ một dự án rồi áp đặt cho mọi cách cấu hình. Một số integration còn có cơ chế remote override, profile context và import ordering riêng.

Hãy thiết kế quy ước:

1. Key nào chỉ do platform quản lý?
2. Key nào được local override?
3. Key nào là secret, không bao giờ có fallback từ file plaintext?
4. Khi key trùng thì nguồn nào có quyền quyết định?
5. Với nhiều imports, thứ tự khai báo có chủ đích không?
6. Khi profile thay đổi, context remote được chọn như thế nào?

Trong lab, sử dụng các key **không trùng** giữa local và remote để chứng minh import hoạt động, rồi mới tạo phép thử trùng key có kiểm soát. Cách này giúp tách lỗi kết nối khỏi lỗi precedence.

### 17.1. Boot Config Data có thứ tự import

`spring.config.import` có thể nhận nhiều location. Theo nguyên tắc của Boot, các tài liệu import được xử lý theo thứ tự và có quy tắc precedence so với tài liệu khai báo import.

Tuy nhiên, mỗi provider có thể có cơ chế resolve theo nhiều profile/context. Khi cần kết hợp Config Server, Consul và Vault trong một app, hãy đọc docs của **đúng phiên bản provider** và viết integration tests cho key colliding thay vì dựa trên một sơ đồ khái quát.

### 17.2. Tránh cùng một secret được khai báo nhiều nơi

Một thiết kế thiếu rõ ràng:

```text
spring.datasource.password:
  application.yaml = dev-password
  Config Server = another-password
  Vault = production-password
  environment = password-from-ci
```

Kết quả rất khó audit, và một override có thể khiến ứng dụng dùng credential ngoài dự kiến. Với secret production, nên có **một owner rõ ràng**, một đường auth/policy được quản trị và test xác nhận nguồn cần dùng.

## 18. Phân quyền: ai được sửa, ai được đọc, ai được triển khai?

Ranh giới sản phẩm đi cùng ranh giới tổ chức.

### 18.1. Boot-only file/configtree

Người có quyền thay container image, môi trường hoặc mounted file có thể ảnh hưởng cấu hình. Các cơ chế kiểm soát chủ yếu nằm ở CI/CD, image registry, filesystem/container security và Kubernetes RBAC.

### 18.2. Spring Cloud Config

Thường có ít nhất hai quyền:

- Quyền sửa backend repository (ví dụ Git).
- Quyền client đọc Config Server và Config Server đọc backend.

Có thể thêm pull-request approval, branch/tag release, signed commits và kiểm soát hành vi của Config Server. Đừng vì Git có lịch sử mà mặc định Config Server đã bảo vệ đường HTTP khỏi mọi client.

### 18.3. Consul

Cần xác định:

- ACL token được phép đọc những KV prefixes nào.
- Ai được ghi KV.
- Consul agent/server có bật TLS đúng không.
- Các service discovery permissions có tách khỏi KV config permissions không.
- Watch được giám sát thế nào và có gây reload storm không.

### 18.4. Vault

Cần xác định:

- Identity của workload và phương thức auth.
- Policies theo secret path/role.
- TTL, lease renewal, revocation.
- Audit, seal/unseal, HA và backup theo hạ tầng.
- Cách ứng dụng và sidecar nhận secret mà không lộ token.
- Cơ chế xử lý credential hết hạn trong các resource đang mở.

Một hệ thống dùng Vault nhưng hardcode root token trong repository không phải một thiết kế an toàn chỉ vì tên sản phẩm có chữ “Vault”.

## 19. Quyết định chọn công nghệ theo nhu cầu thực

### 19.1. Một ứng dụng nhỏ, một vài môi trường

Dùng:

```text
Spring Boot Config Data + profile + env vars
```

và một pipeline quản lý secrets phù hợp. Không nhất thiết triển khai Config Server riêng nếu vận hành một server đó tốn kém hơn lợi ích đem lại.

### 19.2. Nhiều microservices, cần GitOps/config rollout có review

Cân nhắc:

```text
Spring Cloud Config Server + Config Client
```

nếu muốn một API cấu hình tập trung theo application/profile/label và có mô hình backend Git. Đặt yêu cầu HA, ACL, TLS, caching và refresh rõ ràng.

### 19.3. Tổ chức đã vận hành Consul

Nếu đã dùng Consul cho service catalog và KV có quản trị tốt:

```text
Spring Cloud Consul Config
```

có thể phù hợp cho shared/service-specific KV. Cần xác định có thực sự cần Consul Discovery trong app hay chỉ cần Consul Config.

### 19.4. Secret nhạy cảm, short-lived credentials, rotation

Cân nhắc:

```text
Vault + Spring Cloud Vault
```

hoặc:

```text
Vault Agent/CSI -> files -> Spring Boot configtree
```

Lựa chọn phụ thuộc việc application nên trực tiếp biết Vault API hay hạ tầng đã chịu trách nhiệm mount secret.

### 19.5. Kubernetes đã có ConfigMap/Secret workflow

Có thể dùng:

```text
Kubernetes volume/env -> Spring Boot
```

mà không cần Cloud Config/Consul, nếu requirements phù hợp. Nhưng đừng nhầm Kubernetes Secret với Vault secret lifecycle; cần kiểm tra cụ thể bảo mật và rotation.

### 19.6. Dùng kết hợp hai hoặc ba hệ thống

Ví dụ:

```text
Config Server: feature flags và operational settings
Vault: credentials và keys
Consul Discovery: tìm endpoint service
```

Đây là một kiến trúc hợp lệ, nhưng có nhiều đường dependency và tăng chi phí vận hành. Chỉ kết hợp khi mỗi hệ thống có một trách nhiệm rõ. Không dùng cả ba nơi để cùng quản lý một property mà không có quy tắc ownership.

## 20. Thiết kế fallback cho một service thanh toán

Giả sử service cần:

```yaml
payment:
  retry:
    max-attempts: 3
  display-label: "Payments"
```

và những secret:

```text
payment.gateway-token
spring.datasource.password
```

Một cách chia trách nhiệm:

| Property | Nguồn gợi ý | Lý do |
| --- | --- | --- |
| `payment.retry.max-attempts` | Config Server hoặc Boot file | Non-secret, có thể review và rollback |
| `payment.display-label` | Boot file/profile | Không cần remote nếu ít thay đổi |
| `payment.gateway-token` | Vault | Secret, cần policy và rotation |
| `spring.datasource.password` | Vault hoặc secret manager tương đương | Tránh plaintext trong Git/JAR |
| Địa chỉ service hiện tại trong cluster | DNS hoặc service discovery | Thường không phải cấu hình tĩnh được review bằng Git |

Nếu Config Server bị mất kết nối và chỉ còn fallback label, app vẫn có thể chạy an toàn. Nhưng nếu Vault không cấp được gateway token, app không nên giả vờ kết nối thanh toán bình thường bằng giá trị dummy.

**Trách nhiệm startup cần dựa trên mức độ quan trọng của cấu hình**, không chỉ vào khả năng dùng `optional:` của từng plugin.

## 21. Kiểm thử tích hợp: test ranh giới thay vì test mọi thứ cùng lúc

Một bộ test thực tế nên có nhiều tầng.

### 21.1. Unit test application code

Khởi tạo `DemoSettings` bằng giá trị giả, kiểm tra service logic. Không cần Config Server, Consul hay Vault.

Ví dụ:

```java
DemoSettings settings = new DemoSettings(
        "unit", Duration.ofMillis(500), true);
```

Đây là test Java thuần, không chứng minh bất kỳ remote integration nào.

### 21.2. Spring Boot-only integration test

Dùng `@SpringBootTest(properties = ...)` để xác nhận Binder/record hoạt động mà không có Cloud dependencies. Lab A đã có ví dụ.

### 21.3. Contract test với Config Server

Chạy Config Server test instance, trả config theo một app/profile/label cụ thể rồi kiểm tra client nhận key mong đợi. Đồng thời test trường hợp server down và policy fail-fast/optional.

### 21.4. Contract test với Consul KV

Dùng Consul test agent/container do CI chuẩn bị, tạo key prefix và format đã thống nhất. Kiểm tra data xuất hiện trong Environment. Nếu có watch, thay key và quan sát refresh behavior **trên đúng loại bean**.

### 21.5. Contract test với Vault

Dùng Vault dev/test cluster tách biệt, auth policy có quyền tối thiểu, ghi secret giả. Kiểm tra:

- Auth hoạt động và sai token bị từ chối.
- Đúng secret path và profile.
- Không in secret trong log.
- Secret không có được xử lý đúng fail-fast policy.
- Refresh/rotation/lease lifecycle nếu đó là yêu cầu sản phẩm.
- Các test không dùng root credentials ở CI production.

### 21.6. Resilience test

Mô phỏng:

```text
Config Server down
Consul agent down
Vault trả 403
Vault trả 404 cho path
DNS fail
Network timeout
Có config cũ nhưng không đủ mới
```

Đo xem app **không khởi động, tiếp tục với fallback, không ready hoặc restart** theo policy thực tế nào. Một lần startup thành công với backend sẵn sàng chưa chứng minh ứng dụng an toàn khi nguồn remote gặp sự cố.

## 22. Các lỗi thường gặp và cách phân loại

### 22.1. `Unable to load config data from 'configserver:'`

Kiểm tra:

- Có `spring-cloud-starter-config` đúng version không?
- `spring.config.import` có URL/format đúng không?
- Config Server có khởi động và truy cập được từ mạng của client không?
- Có TLS, DNS, auth hoặc timeout không?
- Có bật legacy bootstrap khiến config xử lý khác dự kiến không?

### 22.2. Thêm Config Client starter nhưng quên import

Trong mô hình Config Data hiện đại, cần một entry như:

```properties
spring.config.import=optional:configserver:
```

hoặc import non-optional. Nếu thư viện Config Client được đưa vào classpath nhưng thiếu import, ứng dụng có thể cảnh báo hoặc không khởi động theo cơ chế kiểm tra của phiên bản đó. Đừng vội tắt import check; hãy xác định rõ app có chủ đích lấy config từ Config Server hay không.

### 22.3. Config Server trả dữ liệu nhưng service vẫn dùng local value

Có thể là:

- Sai `spring.application.name` hoặc profile/label.
- Sai file name trong config repository.
- Import precedence/remote override khác mong đợi.
- Đối số CLI hoặc env đang ghi đè.
- Client chưa restart/refresh sau khi server thay đổi.
- Bean đã copy giá trị cũ vào một field khác.

Lần lượt tách dữ liệu **server trả về** khỏi dữ liệu **client nhận** và dữ liệu **bean đang dùng**.

### 22.4. Consul agent chạy nhưng app không tìm thấy key

Kiểm tra:

- Consul KV path có đúng `config/<application>/...` không?
- Application name có đúng không?
- Active profile nào đang dùng?
- `format` có phù hợp với layout KV hay không?
- Với YAML/PROPERTIES format, key `data` có đúng không?
- ACL token có quyền `read` prefix liên quan không?
- Có một Consul agent khác ở địa chỉ/port cấu hình không?

Đừng sửa cả key prefix, profile, import và format cùng lúc; thay một yếu tố để dễ xác định nguyên nhân.

### 22.5. Consul Watch phát event nhưng giá trị trong service không đổi

Cần kiểm tra Bean có thật sự được rebinding/refresh theo cơ chế hỗ trợ không. `@Value` hay record constructor-bound không tự biến thành live property chỉ vì event đã được phát.

### 22.6. Vault trả 403

Đây thường là vấn đề auth/policy/path. Kiểm tra identity, token lease, Vault namespace (nếu có), mount path và policy. **Không** tự bỏ TLS, log token hay cấp root token cho production để “sửa nhanh”.

### 22.7. Vault path 404

Phân biệt:

- Secret path không tồn tại.
- Sai mount KV v1/v2/path.
- Sai `spring.application.name` hoặc profile context.
- Sai contextual location.
- Fail-fast policy không khớp yêu cầu.

Vault optional có semantics cụ thể; không suy diễn từ cách xử lý `optional:file:`.

### 22.8. `@ConfigurationProperties` có `null` trong khi Environment có key

Có thể lỗi tên property, constructor binding, validation, dùng sai bean instance, đọc quá sớm hoặc config đã thay đổi mà Bean chưa được refresh. Đây là vấn đề **binding/lifecycle** có thể xảy ra với cả bốn nguồn, không nhất thiết do provider.

### 22.9. Token bí mật xuất hiện trong Actuator hoặc log

Dừng việc in raw property, xem lại endpoint exposure/roles, sanitize/masking, audit trail và quy trình rotation. Không dựa vào mặc định masking của mọi version để coi việc expose `/actuator/env` hoặc `configprops` là an toàn trước tất cả caller.

### 22.10. Nhiều provider cùng ghi đè một key

Xác định owner. Không cố dùng thứ tự ngầm để giải quyết xung đột lâu dài. Đặt namespace rõ, viết test precedence và mô tả trong runbook một cách có thể audit.

## 23. Quy trình di chuyển từ Boot-only sang cấu hình tập trung

Một migration nên có từng bước:

**Bước 1 — Kiểm kê các khóa đang dùng.** Phân loại non-secret, secret, feature flag, connection settings và thông số chỉ cần build-time.

**Bước 2 — Đặt owner cho từng nhóm.** Ví dụ Config Server cho policy không nhạy cảm, Vault cho credentials.

**Bước 3 — Chuẩn hóa names.** Dùng canonical kebab-case và prefix rõ ràng để tránh trùng với thuộc tính framework.

**Bước 4 — Đặt default an toàn cho non-secret.** Xác định key nào bắt buộc và key nào có fallback.

**Bước 5 — Chọn đúng integration starter và release train.** Không thay đổi phiên bản Spring Cloud vô kiểm soát.

**Bước 6 — Chuyển một nhóm key nhỏ trước.** Giữ test binding, quan sát Environment sau import và không đưa secret vào log.

**Bước 7 — Test fail-fast/optional.** Giả lập backend remote offline và ghi rõ quyết định sẵn sàng của ứng dụng.

**Bước 8 — Quyết định refresh hay restart.** Với config ảnh hưởng cấu trúc bean hoặc resources, ưu tiên rollout/restart khi phù hợp.

**Bước 9 — Bật cơ chế bảo mật và vận hành.** TLS, ACL/policies, audit, backup, HA, monitoring, alerting.

**Bước 10 — Kiểm thử rollback.** Đảm bảo có thể quay lại một phiên bản cấu hình trước hoặc tắt một thay đổi mà không vô tình quay lại credentials đã bị thu hồi.

Không nên đồng thời di chuyển tất cả keys, thêm remote provider, đổi schema `@ConfigurationProperties`, đổi profile và bật refresh động trong một release. Điều đó khiến việc xác định lỗi trở nên khó khăn.

## 24. Ma trận quyết định cho người thiết kế

| Câu hỏi | Nếu “có” thì cân nhắc |
| --- | --- |
| Chỉ cần file + biến môi trường, có CI/CD quản lý? | Boot thuần |
| Nhiều app chia sẻ non-secret config theo app/profile/label, muốn Git history? | Config Server |
| Đã có Consul và cần dùng KV contexts theo app/profile? | Consul Config |
| Cần service registration/health/discovery? | Consul Discovery hoặc DNS tương đương, không nhầm với KV Config |
| Cần đọc token/password với policy và audit chuyên dụng? | Vault/secret manager |
| Cần dynamic DB credentials có lease? | Vault backend và thiết kế rotation |
| Kubernetes đã mount ConfigMap/Secret vào pod? | Boot env/configtree có thể đủ |
| Muốn refresh trong khi chạy? | Đánh giá Spring Cloud refresh, watch, bus hoặc rollout |
| Muốn HA và không phụ thuộc mạng khi startup? | Phân tích caching/fallback, local mount, strategy vận hành |
| Dùng native image/AOT? | Kiểm tra hỗ trợ provider và giới hạn refresh đặc thù |

Không có lựa chọn “tốt nhất cho mọi dự án”. Điều quan trọng là chọn **ít thành phần nhất** vẫn đáp ứng yêu cầu vận hành, bảo mật và khả năng thay đổi.

## 25. Bài tập thực hành

### Bài A — Nhận diện ranh giới

Cho danh sách yêu cầu:

1. Đọc `application.yaml` theo profile.
2. Bind timeout `250ms` thành `Duration`.
3. Cấp cấu hình Git theo tên app và profile.
4. Tìm IP hiện tại của một service đăng ký Consul.
5. Đọc token động từ secret backend.
6. Lấy giá trị file secret mounted vào container.
7. Làm mới một bean khi Consul KV thay đổi.
8. Audit lần nào service đọc secret.

Hãy phân loại: Boot core, Cloud Config, Consul Config/Discovery, Vault hoặc cơ chế phối hợp refresh.

### Bài B — Thiết kế fail-fast

Ứng dụng có hai nhóm:

```text
feature.banner-title
payment.gateway-token
```

Tùy trường hợp, hãy chọn `optional`/required cho import và giải thích vì sao fallback hợp lệ với banner có thể không hợp lệ với gateway token.

### Bài C — Config Server profile

Tạo:

```text
demo-client.yaml
demo-client-dev.yaml
```

trong config repository local của lab B. Chạy server, GET `/demo-client/default` và `/demo-client/dev`, rồi chạy client với `--spring.profiles.active=dev`. Ghi lại giá trị `demo.display-label` và giải thích quan hệ giữa application name, profile và file server.

### Bài D — Consul KV

Tạo key `config/demo-client/data` chứa properties. Kiểm tra client Consul có bind `demo.retry-delay` sang `Duration` không. Sau đó đổi key và quan sát liệu một instance đang chạy có tự cập nhật hay không.

### Bài E — Vault secret không được log

Thêm property `payment.gateway-token` trong Vault dev. Viết Java code chỉ in:

```text
gatewayTokenPresent = true
```

khi có token, tuyệt đối không in giá trị. Giải thích vì sao record `toString()` có thể làm lộ secret nếu thêm token vào một record cấu hình rồi log cả record.

### Bài F — Kubernetes không dùng Spring Cloud

Giả sử pod mount file:

```text
/run/secrets/payment.gateway-token
```

Hãy viết import `configtree:` để Boot đọc key đó và mô tả ranh giới giữa Kubernetes Secret, CSI driver, Vault và Spring Boot.

### Bài G — Refresh và consistency

Một Config Server thay đổi timeout, nhưng một singleton service đã copy timeout vào `final Duration` trong constructor. Hãy liệt kê các điều kiện để service thật sự dùng giá trị mới. Khi nào nên thay bằng rolling restart?

### Bài H — Version alignment

Một project dùng Spring Boot 3.3.13 nhưng thêm một starter Spring Cloud từ release train không tương thích. Hãy giải thích vì sao BOM tương thích quan trọng và cách kiểm tra version matrix trước khi nâng cấp.

### Bài I — Mất kết nối

Thử ba kịch bản ở môi trường lab:

1. Tắt Config Server trước khi client start.
2. Tắt Consul agent trước khi client start.
3. Truy cập Vault bằng token không đủ quyền.

So sánh thông báo và chính sách fail-fast/optional. Không đưa token thật hoặc stacktrace chứa secret vào báo cáo.

### Bài J — Ai sở hữu một property?

Hai nhóm đều muốn quản lý `demo.feature-enabled`: nhóm app đặt trong YAML, nhóm platform đặt trong Consul KV. Hãy đưa ra một quy tắc ownership rõ ràng và một integration test để tránh xung đột nguồn.

## 26. Câu hỏi tự kiểm tra

**1.** Spring Boot thuần có hỗ trợ file ngoài JAR, profile và `configtree:` không?

**2.** Spring Boot thuần có tự cung cấp một Config Server HTTP để đọc Git repository không?

**3.** Config Server và Config Client khác nhau về vai trò nào?

**4.** Prefix `configserver:` được nhận diện nhờ Boot core hay nhờ integration Spring Cloud Config?

**5.** `spring.config.import=optional:configserver:` thường dùng khi nào?

**6.** Trong Consul, KV Config và service discovery có là cùng một API/starter không?

**7.** Vì sao Consul KV không mặc định thay thế quy trình review Git?

**8.** Vault có khả năng gì mà một `application.yaml` không cung cấp?

**9.** `vault://` là một đường file local có thể mở bằng Java NIO phải không?

**10.** `optional:vault://` có bảo đảm bỏ qua mọi lỗi mất Vault không?

**11.** Vì sao đã cập nhật Git/Consul/Vault vẫn có thể cần restart hoặc refresh client?

**12.** `@RefreshScope` có làm mọi singleton và record constructor-bound tự thay dữ liệu an toàn không?

**13.** Khi chạy native image, nên kiểm tra giới hạn nào của Spring Cloud refresh?

**14.** Một Kubernetes Secret được mount thành file có thể được Boot thuần đọc bằng cơ chế nào?

**15.** `ConfigMap` và `Vault` có cùng mô hình secret lifecycle không?

**16.** Tại sao phải kiểm tra Spring Boot/Spring Cloud version compatibility?

**17.** Vì sao không nên commit root Vault token vào `application.yaml` dù file này là private repo?

**18.** Cấu hình nào nên fail-fast nếu thiếu: tên banner hay database password?

**19.** Nếu service đang dùng credential đã bị Vault thu hồi, điều gì ngoài property value có thể cần xử lý?

**20.** Khi nhiều provider cùng khai báo một key, cần kiểm tra những gì?

### Gợi ý đáp án

1. Có.
2. Không; cần Spring Cloud Config Server hoặc giải pháp tương đương.
3. Server cung cấp API và truy cập backend; client đưa remote properties vào Environment.
4. Integration Spring Cloud Config.
5. Khi ứng dụng cho phép xử lý server vắng mặt với local fallback phù hợp.
6. Không; đây là các khả năng và starter khác nhau.
7. KV có API quản trị riêng, không tự tạo pull-request workflow.
8. Auth, policies, audit, secrets engines, leases/rotation tùy backend.
9. Không; đó là Config Data location được Spring Cloud Vault cung cấp.
10. Không; semantics phụ thuộc provider và loại lỗi.
11. Vì đổi nguồn, phát hiện sự kiện và áp dụng bean state là những giai đoạn khác nhau.
12. Không; refresh có phạm vi, type và lifecycle cụ thể.
13. RefreshScope không được hỗ trợ như JVM trong AOT/native theo docs Spring Cloud Context.
14. `configtree:` hoặc môi trường nếu secret được truyền vào process.
15. Không; cần xét quyền, storage, policies và rotation cụ thể.
16. Để tránh API/dependency incompatibilities và lỗi startup không đáng có.
17. Vì repo/image/log/backup có thể làm lộ token có quyền lớn.
18. Database password, trừ khi có cơ chế cấp credential khác được phê duyệt.
19. Connection pool, session, lease, resource recreation và retry.
20. Precedence, profile, location/import ordering, owner, override policies và tests.

## 27. Checklist production và vận hành

Trước khi duyệt một giải pháp externalized configuration:

- [ ] Có tài liệu ownership cho từng prefix và mỗi hệ thống nguồn.
- [ ] Không có secret production hardcode trong code, JAR hoặc Git plaintext.
- [ ] Spring Cloud BOM tương thích với Spring Boot đang chạy.
- [ ] Config Server/Consul/Vault được cấu hình TLS và auth phù hợp.
- [ ] Quyền đọc/ghi KV, config repo hoặc secrets tuân theo least privilege.
- [ ] Có health, metrics và logs cho lỗi tải cấu hình (không lộ secret).
- [ ] Có chính sách khi nguồn remote down hoặc trả dữ liệu sai.
- [ ] Có retry/backoff được kiểm soát, tránh thundering herd.
- [ ] Có cách rollback non-secret config.
- [ ] Có kế hoạch rotate/revoke secrets và xử lý connection pools.
- [ ] Có test precedence khi nhiều nguồn cùng định nghĩa property quan trọng.
- [ ] Có quyết định refresh hay rolling restart với từng nhóm cấu hình.
- [ ] Endpoints Actuator quản trị được bảo vệ, không expose bừa bãi.
- [ ] Có kiểm thử môi trường local, staging và production-like.
- [ ] Có runbook khi startup lỗi vì Config Server, Consul hoặc Vault.
- [ ] Có quy tắc build AOT/native nếu dự án dùng native image.
- [ ] Có cơ chế audit ai đã thay đổi cấu hình và ai được quyền đọc secret.

Một lựa chọn công nghệ chỉ tốt nếu đội vận hành có thể giải thích **nguồn hiện tại của từng giá trị**, cách một thay đổi được triển khai và cách hệ thống phản ứng khi nguồn đó không còn sẵn sàng.

## 28. Kết luận

Spring Boot Externalized Configuration đã cung cấp một **bộ máy mạnh để đọc, ưu tiên và bind cấu hình**. Các integration Cloud không thay thế bộ máy này; chúng **bổ sung những nguồn dữ liệu và khả năng vận hành** khác nhau.

```text
Boot core
    = Environment + Config Data + Binder + Profile + PropertySources

Spring Cloud Config
    = Config Server/Client + remote configuration distribution

Spring Cloud Consul Config
    = Consul KV -> Spring Environment

Spring Cloud Consul Discovery
    = service registration / discovery (khác nhiệm vụ KV config)

Spring Cloud Vault
    = Vault secret backends -> Spring Environment
      + chính sách auth/secret lifecycle của Vault

Kubernetes volume/env
    = một đường đưa cấu hình vào Boot, có thể không cần Cloud plugin
```

Điểm quan trọng nhất cần ghi nhớ: **“Cấu hình được lưu tập trung” không đồng nghĩa “mọi instance lập tức nhận và áp dụng dữ liệu mới”; “một key được lấy từ Vault” không đồng nghĩa “mọi resource dùng secret đó đã tự rotation”; và “có Spring Cloud dependency” không đồng nghĩa “đã có hệ thống bảo mật/HA hoàn chỉnh”.**

Hãy chọn công nghệ dựa trên trách nhiệm: cấu hình thường, phân phối tập trung, service discovery, secret management hay refresh. Sau đó thiết kế rõ phiên bản, auth, quyền, precedence, fail-fast, refresh/restart và kiểm thử.

### Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `Environment`, property precedence, Config Data import, config tree và type-safe binding.
2. [Spring Cloud Release Train 2023.0](https://docs.spring.io/spring-cloud-release/reference/2023.0/index.html): phiên bản Spring Cloud và Boot tương thích.
3. [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/4.1/client.html): `configserver:` import, profiles, fail-fast, retry và bootstrap.
4. [Spring Cloud Config — Server](https://docs.spring.io/spring-cloud-config/reference/4.1/server.html): cấu hình server và `@EnableConfigServer`.
5. [Spring Cloud Consul — Distributed Configuration](https://docs.spring.io/spring-cloud-consul/reference/config.html): Consul KV, `consul:` import, contexts, watch và format.
6. [Spring Cloud Vault — ConfigData API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html): `vault://`, contextual locations, optional và backend integration.
7. [Spring Cloud Vault — Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html): các phương thức xác thực Vault được hỗ trợ.
8. [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): refresh scope, rebinding và giới hạn.
9. [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): Git repositories, labels và vận hành server.
