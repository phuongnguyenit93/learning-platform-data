# Kết hợp Git với kho bí mật và kiểm thử phân quyền

Trong một hệ thống Spring Cloud Config, Git phù hợp để quản lý các thuộc tính vận hành có thể review cùng mã nguồn, còn Vault phù hợp để lưu password, API token và credential cần kiểm soát truy cập. Config Server có thể ghép hai nguồn thành một Environment theo application và profile. Tuy nhiên, khi server giữ quyền đọc nhiều secret, nó cũng trở thành ranh giới bảo mật: mỗi Config Client phải chỉ đọc được cấu hình thuộc ứng dụng của chính nó.

Bài thực hành xây dựng một Config Server dùng Git cho cấu hình thông thường và HashiCorp Vault KV v2 cho secret. Hai client là orders-service và payment-service. Người học sẽ tạo Git repository, bật Vault, cấp policy đọc cho Config Server, cấu hình thứ tự ưu tiên, triển khai xác thực HTTP Basic có kiểm soát theo application name và kiểm thử cả truy cập hợp lệ lẫn truy cập chéo ứng dụng.

Kết quả cần đạt là:

- Config Server đọc được cấu hình từ Git và secret từ Vault.
- Client nhận được Environment hợp nhất theo application/profile.
- Secret không nằm trong Git và client không cần giữ Vault token.
- orders-service đọc được cấu hình của orders-service nhưng bị từ chối khi yêu cầu payment-service.
- payment-service chỉ đọc được cấu hình của payment-service.
- Có thể chứng minh nguồn nào thắng khi hai backend cùng khai báo một key.

## 1. Kiến trúc của bài thực hành

Mô hình gồm một Git repository, một Vault server, một Config Server và hai Config Client:

~~~mermaid
flowchart TD
    G[Git repository<br/>non-secret configuration] --> CS[Spring Cloud Config Server]
    V[Vault KV v2<br/>credentials and tokens] --> CS
    O[orders-service<br/>Basic identity: orders-service] -->|GET /orders-service/prod/main| CS
    P[payment-service<br/>Basic identity: payment-service] -->|GET /payment-service/prod/main| CS
    CS -->|Environment: Git + Vault| O
    CS -->|Environment: Git + Vault| P
    CS -->|Vault token / policy| V
    CS -->|Read-only deploy token| G
~~~

Config Server dùng hai backend:

- **Git** lưu timeout, feature flag, tên queue, endpoint không bí mật và cấu hình mặc định.
- **Vault KV v2** lưu database username/password, API token và các giá trị nhạy cảm.
- **Config Server** xác thực client, kiểm tra application path, đọc hai backend và trả Environment đã hợp nhất.
- **Config Client** chỉ cần credential để gọi Config Server. Client không cần Git token hoặc Vault token trong mô hình server-side Vault authentication.

Phạm vi quyền cần nhớ: Config Server có thể đọc nhiều path trong Vault, nhưng mỗi client chỉ được phép yêu cầu application mà danh tính của nó đại diện. Nếu bỏ qua kiểm tra phân quyền theo application, một client đã xác thực có thể thử đổi URL từ orders-service sang payment-service để lấy secret của service khác.

## 2. Chuẩn bị công cụ và cấu trúc workspace

Cần có:

- JDK và Maven tương thích với phiên bản Spring Boot/Spring Cloud của dự án.
- Git CLI.
- Vault CLI và một Vault server cho môi trường lab.
- curl; jq hữu ích để kiểm tra JSON mà không in secret.
- Một IDE để chạy Config Server và hai client.

Tạo workspace:

~~~text
config-security-lab/
├── config-repo/
│   ├── application.yml
│   ├── orders-service-prod.yml
│   └── payment-service-prod.yml
├── config-server/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/configserver/
│       │   ├── ConfigServerApplication.java
│       │   └── ConfigServerSecurity.java
│       └── resources/application.yml
├── orders-service/
│   ├── pom.xml
│   └── src/main/resources/application.yml
└── payment-service/
    ├── pom.xml
    └── src/main/resources/application.yml
~~~

Tách repository cấu hình khỏi source code của các client giúp review và phát hành cấu hình độc lập. Trong lab, config-repo có thể là Git local. Trong production, dùng remote Git server với deploy token hoặc project token chỉ có quyền đọc.

Không tạo file chứa password thật trong workspace hoặc commit chúng vào Git. Các giá trị secret trong bài được cấp trực tiếp cho Vault bằng biến môi trường hoặc secret manager.

## 3. Tạo Git repository cho cấu hình không bí mật

Tạo file chung application.yml:

~~~yaml
platform:
  region: ap-southeast-1
  connect-timeout: 2s

config:
  release-id: lab-release-001
  precedence-probe: from-git

observability:
  metrics-enabled: true
~~~

File này chứa các thuộc tính dùng chung và một key kiểm tra thứ tự ưu tiên. Key precedence-probe sẽ được khai báo lại trong Vault để chứng minh backend có độ ưu tiên cao hơn thắng khi trùng tên.

Tạo orders-service-prod.yml:

~~~yaml
orders:
  feature:
    reservation-enabled: true
  http:
    read-timeout: 3s
  retry:
    max-attempts: 3

spring:
  datasource:
    hikari:
      maximum-pool-size: 12
~~~

Tạo payment-service-prod.yml:

~~~yaml
payment:
  feature:
    fraud-check-enabled: true
  http:
    read-timeout: 4s
  retry:
    max-attempts: 2
~~~

Khởi tạo Git:

~~~bash
cd config-repo
git init
git add application.yml orders-service-prod.yml payment-service-prod.yml
git commit -m "Add non-secret application configuration"
git branch -M main
~~~

Config Server sẽ dùng label main cho Git backend. Trong production, nên phát hành bằng tag bất biến hoặc commit SHA để có thể tái lập và rollback. Các file Git không được chứa password, token, private key hoặc credential đã giải mã.

Nếu dùng remote repository, Config Server có thể nhận credential đọc Git từ secret manager:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
          default-label: main
~~~

Git token phải chỉ có quyền đọc repository cần thiết. Không nhúng token trong URI hoặc Docker image.

## 4. Khởi chạy Vault cho môi trường lab

Có thể dùng Vault dev server trên máy cá nhân để thực hành. Ví dụ:

~~~bash
vault server -dev -dev-listen-address=127.0.0.1:8200
~~~

Mở terminal khác và cấu hình địa chỉ:

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
read -r -s -p "Vault dev root token: " VAULT_TOKEN
printf '\n'
export VAULT_TOKEN
~~~

Vault dev server dùng token quản trị cho lab và dữ liệu không có độ bền production. Chỉ chạy trên loopback hoặc môi trường local cô lập; không mở cổng dev server ra mạng dùng chung, không dùng root token trong production và không tái sử dụng token lab ở hệ thống thật.

Tạo mount KV v2 riêng:

~~~bash
vault secrets enable -path=config-kv kv-v2
vault secrets list
~~~

Xác nhận mount config-kv có version 2. KV v2 lưu metadata/version cho mỗi secret. Khi dùng Spring Cloud Config Vault backend, đặt kv-version bằng 2 để server gọi đúng API có phần data/ trong đường dẫn nội bộ.

## 5. Tạo secret theo application và profile

Spring Cloud Config Vault backend mặc định sử dụng tên backend secret, key mặc định application và profile separator là dấu phẩy. Bài lab dùng mount config-kv, nên các path được tổ chức như sau:

| Path KV v2 | Phạm vi |
| --- | --- |
| config-kv/application | Secret dùng chung cho mọi ứng dụng |
| config-kv/application,prod | Secret dùng chung cho mọi ứng dụng đang chạy profile prod |
| config-kv/orders-service | Secret mặc định của orders-service |
| config-kv/orders-service,prod | Secret của orders-service trong profile prod |
| config-kv/payment-service | Secret mặc định của payment-service |
| config-kv/payment-service,prod | Secret của payment-service trong profile prod |

Hai context `application` và `application,prod` là context dùng chung: Vault backend có thể trả chúng cho mọi Config Client. Chỉ đặt tại đây secret thực sự được chia sẻ có chủ đích giữa tất cả ứng dụng, chẳng hạn một credential dùng chung theo kiến trúc đã phê duyệt. Không đặt database password, API token hoặc private credential riêng của orders/payment vào context chung; giữ chúng trong `orders-service[,prod]` hoặc `payment-service[,prod]`.

Trong phạm vi truy xuất, context application là dữ liệu chung cho mọi Config Client; context application,prod là dữ liệu chung cho mọi Config Client đang dùng profile prod. Cả hai context phải chỉ chứa secret được chủ động chia sẻ cho toàn bộ phạm vi tương ứng. Credential riêng của orders-service và payment-service luôn nằm trong path riêng của từng ứng dụng.

Tạo secret cho orders-service:

~~~bash
umask 077
chmod 600 /run/credentials/orders-service-prod.json
vault kv put -mount=config-kv orders-service,prod \
  @/run/credentials/orders-service-prod.json
~~~

Tạo secret cho payment-service:

~~~bash
chmod 600 /run/credentials/payment-service-prod.json
vault kv put -mount=config-kv payment-service,prod \
  @/run/credentials/payment-service-prod.json
~~~

Hai file JSON trên được secret provisioning pipeline tạo ngoài Git, chứa các key tương ứng với ví dụ (username, password, API token và `config.precedence-probe`). Pipeline phải ghi file với quyền `0600`, thư mục cha `0700`, và xóa file tạm sau khi nạp Vault. Lệnh `vault kv put @file` chỉ đưa đường dẫn file vào argv; secret values không xuất hiện trong command line, shell history hoặc process listing. Không dùng `cat`, `type` hoặc `jq` để in nội dung file.

Giá trị config.precedence-probe=from-vault cố ý trùng với key trong Git. Sau khi Config Server được cấu hình order, client sẽ nhận giá trị từ backend có độ ưu tiên cao hơn.

## 6. Tạo policy đọc tối thiểu cho Config Server

Config Server cần đọc các path ứng dụng và context chung. Với KV v2, policy phải dùng đường dẫn API có segment data/. Ví dụ file policy:

~~~hcl
path "config-kv/data/application" {
  capabilities = ["read"]
}

path "config-kv/data/application,prod" {
  capabilities = ["read"]
}

path "config-kv/data/orders-service" {
  capabilities = ["read"]
}

path "config-kv/data/orders-service,prod" {
  capabilities = ["read"]
}

path "config-kv/data/payment-service" {
  capabilities = ["read"]
}

path "config-kv/data/payment-service,prod" {
  capabilities = ["read"]
}
~~~

Lưu nội dung trên thành config-server-read.hcl rồi nạp policy:

~~~bash
vault policy write config-server-read config-server-read.hcl
VAULT_TOKEN_FILE="$HOME/.config/vault/config-server-token"
install -d -m 700 "$(dirname "$VAULT_TOKEN_FILE")"
umask 077
vault token create -policy=config-server-read -ttl=1h -renewable=true -format=json \
  | jq -er '.auth.client_token' > "$VAULT_TOKEN_FILE"
chmod 600 "$VAULT_TOKEN_FILE"

# Chuyển CLI khỏi dev/root token sang scoped Config Server token.
unset VAULT_TOKEN
export VAULT_TOKEN="$(< "$VAULT_TOKEN_FILE")"
vault token lookup -format=json | jq -e '{
  hasConfigServerRead: (.data.policies | index("config-server-read") != null),
  hasRoot: (.data.policies | index("root") != null),
  renewable: .data.renewable,
  ttlSeconds: .data.ttl
}'
~~~

Token chỉ được ghi vào file có quyền `0600`; output của lệnh tạo token được lọc thẳng vào file, không hiển thị trên terminal. Sau `unset` và nạp lại từ file, các lệnh Vault CLI tiếp theo dùng scoped token trong `VAULT_TOKEN`, không còn dùng dev/root token. Config Server nhận cùng token qua secret injection; không cấp token này cho orders-service hoặc payment-service.

Policy ở đây cấp quyền đọc cho Config Server đối với cả hai ứng dụng. Việc giới hạn từng Config Client được thực hiện tại Config Server bằng authorization policy. Đây là một ranh giới tin cậy quan trọng: nếu Config Server bị chiếm quyền hoặc authorization bị cấu hình sai, identity server-side có thể đọc nhiều secret. Trong môi trường lớn, có thể tách Config Server theo miền tin cậy hoặc dùng identity/policy Vault riêng cho từng nhóm ứng dụng.

Không cấp quyền list, write, delete hoặc sudo nếu Config Server chỉ cần đọc secret. Nếu phiên bản backend cần metadata permission cho một thao tác cụ thể, chỉ bổ sung quyền sau khi xác định request thực tế và kiểm tra audit log.

Kiểm tra capability bằng chính scoped identity vừa nạp. Token của Config Server phục vụ cả orders và payment nên phải đọc được hai application path này; kiểm tra một application ngoài allowlist để chứng minh quyền đọc bị giới hạn:

~~~bash
# Allowed application path.
vault token capabilities -format=json config-kv/data/orders-service,prod \
  | jq -e 'index("read") != null'

# Config Server also needs this second served application path.
vault token capabilities -format=json config-kv/data/payment-service,prod \
  | jq -e 'index("read") != null'

# An application outside this Config Server allowlist must be denied.
vault token capabilities -format=json config-kv/data/payroll-service,prod \
  | jq -e 'index("deny") != null'

# The allowed data path must not grant write.
vault token capabilities -format=json config-kv/data/orders-service,prod \
  | jq -e 'index("read") != null and index("write") == null'

# KV v2 list is checked on the metadata path and must be denied.
vault token capabilities -format=json config-kv/metadata/orders-service,prod \
  | jq -e 'index("deny") != null and index("list") == null'
~~~

Không truyền token làm đối số cho `vault token capabilities`; khi bỏ qua token argument, Vault CLI kiểm tra token đã xác thực trong `VAULT_TOKEN` bằng endpoint capabilities-self. Vì Config Server cần đọc cả orders và payment, việc Vault từ chối payment path sẽ làm client payment không lấy được cấu hình. Quyền orders-client không đọc được payment được kiểm tra ở lớp HTTP Config Server trong AUTH-03; Vault policy ở đây giới hạn server identity với các application path đã khai báo.

### Gia hạn và cấp lại token có TTL một giờ

Token lab được tạo renewable với TTL một giờ. Khi token còn hiệu lực, gia hạn chính token hiện tại và chỉ xuất metadata:

~~~bash
vault token renew -increment=1h -format=json \
  | jq -e '{renewable: .auth.renewable, ttlSeconds: .auth.lease_duration}'
~~~

Nếu token đã hết hạn hoặc chạm max TTL, dùng Vault Agent auto-auth AppRole đã được platform admin cấu hình với `token_policies=config-server-read`, `token_ttl=1h` và max TTL theo policy. Role ID và Secret ID phải được provision thành file chỉ đọc bởi service account, quyền `0600`; không in chúng hoặc truyền qua argv. Ví dụ cấu hình Agent:

Nếu auth method AppRole chưa được bật, platform admin bật nó một lần. Sau đó admin provision role trong phiên quản trị riêng (không dùng scoped runtime token):

~~~bash
vault auth list -format=json | jq -e 'has("approle/")' >/dev/null \
  || vault auth enable approle
vault write auth/approle/role/config-server \
  token_policies=config-server-read token_ttl=1h token_max_ttl=4h \
  secret_id_ttl=24h secret_id_num_uses=1
~~~

Role ID và Secret ID được cấp vào file bảo vệ trên host Config Server. Các lệnh dưới đây chạy bằng admin identity/credential helper được duyệt; Secret ID chỉ được ghi vào file, không xuất ra terminal:

~~~bash
ROLE_ID_FILE=/run/credentials/config-server-role-id
SECRET_ID_FILE=/run/credentials/config-server-secret-id
install -d -m 700 /run/credentials /run/secrets
umask 077
vault read -field=role_id auth/approle/role/config-server/role-id > "$ROLE_ID_FILE"
vault write -f -format=json auth/approle/role/config-server/secret-id \
  | jq -er '.data.secret_id' > "$SECRET_ID_FILE"
chmod 600 "$ROLE_ID_FILE" "$SECRET_ID_FILE"
~~~

~~~hcl
vault {
  address = "https://vault.example.internal"
  tls_skip_verify = false
}

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path = "/run/credentials/config-server-role-id"
      secret_id_file_path = "/run/credentials/config-server-secret-id"
      remove_secret_id_file_after_reading = false
    }
  }

  sink "file" {
    config = {
      path = "/run/secrets/config-server-vault-token"
      mode = "0600"
    }
  }
}
~~~

#### Luân chuyển SecretID dùng một lần

Với `secret_id_num_uses=1`, mỗi SecretID chỉ được dùng cho một lần AppRole login. File SecretID được giữ lại để Vault Agent có thể đọc lại, nhưng nội dung trong file đã bị tiêu thụ sau lần đăng nhập thành công; không xem file này là credential vĩnh viễn. Vault Agent cache credential đã đọc và sử dụng giá trị mới nếu một file mới được ghi vào đúng `secret_id_file_path` trước lần authentication kế tiếp.

Managed provisioning process phải theo dõi lần AppRole login thành công qua Vault audit log hoặc tín hiệu vận hành tương đương. Ngay sau khi xác nhận SecretID hiện tại đã được dùng, process tạo SecretID mới và thay file theo cách atomic. Đồng thời, process kiểm tra tuổi SecretID đang chờ sử dụng và cấp lại trước khi TTL 24 giờ hết hạn. Role ID có thể giữ ổn định; SecretID phải được thay mới sau mỗi lần dùng và trước khi hết hạn.

Ví dụ lệnh dưới đây chạy bằng provisioning identity được cấp quyền tạo SecretID, không chạy bằng scoped Config Server token. `SECRET_ID_FILE` là đường dẫn đã khai báo ở phần trên:

~~~bash
SECRET_ID_NEXT_FILE="${SECRET_ID_FILE}.next"
umask 077
vault write -f -format=json auth/approle/role/config-server/secret-id \
  | jq -er '.data.secret_id' > "$SECRET_ID_NEXT_FILE"
chmod 600 "$SECRET_ID_NEXT_FILE"
mv -f "$SECRET_ID_NEXT_FILE" "$SECRET_ID_FILE"
~~~

File mới được thay thế nguyên tử trên cùng filesystem và có quyền `0600`; SecretID không xuất hiện trên terminal, argv hoặc log. Vault Agent dùng giá trị mới ở lần authentication kế tiếp. Nếu provisioning không xác nhận được việc thay file thành công, phải cảnh báo và cấp credential mới trước khi token hiện tại chạm `token_max_ttl=4h`; không chờ đến khi Config Server mất khả năng xác thực. Khi SecretID đã quá hạn hoặc bị lộ, provisioning thu hồi/revoke theo accessor nếu có và phát hành SecretID mới qua cùng kênh được bảo vệ.

Chạy Agent dưới service manager với thư mục credentials/secrets có quyền `0700` và token sink `0600`. Agent tự renew token và re-auth qua AppRole khi cần. Config Server trong lab đang nhận token qua biến môi trường lúc khởi động; sau khi Agent cấp token mới, nạp lại từ sink file rồi restart Config Server để process dùng token mới:

~~~bash
export VAULT_TOKEN="$(< /run/secrets/config-server-vault-token)"
chmod 600 /run/secrets/config-server-vault-token
# Restart config-server with the approved service supervisor.
~~~

Không dùng lại dev/root token để gia hạn hoặc cấp lại token runtime. Nếu AppRole credential bị thu hồi, dừng và yêu cầu platform admin provision lại qua kênh secret delivery; không chuyển Secret ID vào command line.

## 7. Cấu hình Config Server dùng đồng thời Git và Vault

Config Server cần các dependency chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
    </dependency>
</dependencies>
~~~

Dùng Spring Cloud BOM tương thích với Spring Boot version của dự án và dependency management tương ứng cho Spring Vault. spring-vault-core cho phép Config Server dùng các phương thức xác thực được Spring Vault hỗ trợ, chẳng hạn AppRole hoặc Kubernetes auth. Bài lab dùng token server-side để minh họa luồng cơ bản; production nên dùng workload identity thay cho token quản trị dài hạn.

Ứng dụng bật Config Server:

~~~java
package com.example.configserver;

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
~~~

Cấu hình application.yml của Config Server:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  profiles:
    active: git,vault
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI:file:///opt/config-repo}
          default-label: main
          clone-on-start: true
          order: 2
        vault:
          host: ${VAULT_HOST:127.0.0.1}
          port: ${VAULT_PORT:8200}
          scheme: ${VAULT_SCHEME:http}
          backend: config-kv
          default-key: application
          profile-separator: ","
          kv-version: 2
          authentication: TOKEN
          token: ${VAULT_TOKEN}
          skip-ssl-validation: false
          order: 1

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Hai profile git và vault kích hoạt hai loại Environment Repository. Thuộc tính order điều khiển ưu tiên giữa các repository: số nhỏ hơn có độ ưu tiên cao hơn. Trong bài lab, Vault có order 1 nên ghi đè Git có order 2 khi cùng một key xuất hiện ở cả hai nguồn.

Config Server dùng token Vault được inject từ môi trường server. Vì vậy client chỉ gửi credential xác thực với Config Server; client không phải gửi X-Config-Token hoặc giữ token Vault. Nếu dùng cách mặc định chuyển Vault token qua header X-Config-Token, mỗi request tới Config Server cần token đó. Không dùng mô hình header này cho client không đáng tin cậy nếu mục tiêu là giấu Vault credential khỏi client.

Với production, ưu tiên Vault authentication gắn với workload identity như Kubernetes auth hoặc AppRole được quản lý đúng cách. Dùng HTTPS tới Vault, xác minh certificate và giữ skip-ssl-validation=false. Token có TTL, policy hẹp và quy trình renew/rotate; không dùng root token.

## 8. Hiểu precedence giữa Git và Vault

Với cấu hình order ở trên:

| Backend | Order | Vai trò |
| --- | ---: | --- |
| Vault | 1 | Ưu tiên cao hơn, chứa secret và override được phê duyệt |
| Git | 2 | Cấu hình vận hành có review và lịch sử thay đổi |

Trong Git có:

~~~yaml
config:
  precedence-probe: from-git
~~~

Trong Vault có:

~~~text
config.precedence-probe = from-vault
~~~

Khi gọi Config Server cho orders-service/prod, giá trị hiệu lực dự kiến là from-vault. Response Environment giữ các PropertySource của backend; thứ tự và tên nguồn giúp xác minh key nào thắng.

Mặc định Vault backend không dùng label khi tìm secret. Vì vậy label main trong request ở bài lab áp dụng cho Git, còn Vault tìm theo application/profile. Nếu cần ghim secret theo label, bật enable-label và tổ chức path có đủ ba phần application, profile, label theo tài liệu Vault backend. Không coi Git commit SHA là phiên bản Vault KV; hãy ghi nhận Vault KV version riêng trong release manifest.

Không nên dùng precedence để giấu một cấu hình quan trọng trong Vault mà không có tài liệu. Nếu cùng một key xuất hiện ở hai backend, ghi rõ backend sở hữu key và lý do override. Tốt nhất, Git quản lý phần lớn thuộc tính không bí mật, Vault quản lý secret; chỉ tạo key trùng trong bài lab hoặc khi có yêu cầu override có chủ đích.

Nếu dùng composite profile với danh sách repository, thứ tự trong danh sách quyết định precedence. Nếu dùng các profile backend riêng biệt như git,vault, dùng thuộc tính order. Không nhầm thứ tự property source trong Config Server với thứ tự ưu tiên toàn cục của mọi nguồn trong Spring Environment phía client.

## 9. Bảo vệ Config Server theo application name

HTTP Basic chỉ xác thực người gọi. Mặc định, một người dùng đã xác thực có thể yêu cầu cấu hình của application bất kỳ nếu biết tên application. Khi Environment chứa secret, cần thêm authorization theo application path.

Ví dụ, username của client phải bằng application name mà nó được phép đọc:

- orders-service chỉ được GET /orders-service/**.
- payment-service chỉ được GET /payment-service/**.
- Một client orders-service gọi GET /payment-service/prod/main phải nhận HTTP 403.

Thêm code security vào Config Server:

~~~java
package com.example.configserver;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.authorization.AuthorizationDecision;

@Configuration
public class ConfigServerSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            Environment environment,
            PasswordEncoder passwordEncoder) {

        return new InMemoryUserDetailsManager(
                User.withUsername("orders-service")
                        .password(passwordEncoder.encode(
                                environment.getRequiredProperty(
                                        "ORDERS_CONFIG_PASSWORD")))
                        .roles("CONFIG_CLIENT")
                        .build(),
                User.withUsername("payment-service")
                        .password(passwordEncoder.encode(
                                environment.getRequiredProperty(
                                        "PAYMENT_CONFIG_PASSWORD")))
                        .roles("CONFIG_CLIENT")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/{application}/**")
                .access((authentication, context) -> {
                    String requestedApplication =
                            context.getVariables().get("application");
                    String principal =
                            authentication.get().getName();

                    boolean allowed = "GET".equals(
                            context.getRequest().getMethod())
                            && requestedApplication != null
                            && principal.equals(requestedApplication);

                    return new AuthorizationDecision(allowed);
                })
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đoạn code dùng InMemoryUserDetailsManager để bài lab dễ chạy. Password lấy từ biến môi trường và được PasswordEncoder mã hóa trong bộ nhớ. Không dùng in-memory user store cho hệ thống nhiều service production; hãy thay bằng identity provider, LDAP hoặc OAuth2/JWT và map claim/service identity vào application name.

Authorization ở đây dựa trên path segment application. Nếu client dùng tên application khác với username, request sẽ bị từ chối. Đây là chủ ý: danh tính và application name cần được liên kết rõ ràng. Nếu một workload cần đọc nhiều application, cấp một role/policy riêng có danh sách allowlist thay vì bỏ kiểm tra.

Quy tắc anyRequest().denyAll() giới hạn server chỉ phục vụ endpoint health và Config API đã được kiểm tra. Nếu triển khai thêm webhook /monitor, endpoint mã hóa hoặc API quản trị, hãy khai báo rule riêng cho danh tính vận hành tương ứng.

## 10. Cấp credential cho Config Server

Trước khi khởi động server, cấp các biến môi trường từ secret manager hoặc terminal lab:

~~~bash
export CONFIG_REPO_URI=file:///absolute/path/to/config-repo
export VAULT_HOST=127.0.0.1
export VAULT_PORT=8200
export VAULT_SCHEME=http
test -n "$VAULT_TOKEN" || { echo "Load the scoped Config Server token from the protected file created in section 6" >&2; exit 1; }
read -r -s -p "Orders Config Client password: " ORDERS_CONFIG_PASSWORD
printf '\n'
export ORDERS_CONFIG_PASSWORD
read -r -s -p "Payment Config Client password: " PAYMENT_CONFIG_PASSWORD
printf '\n'
export PAYMENT_CONFIG_PASSWORD
~~~

Token Vault là identity của Config Server, không phải của client. Hai password HTTP Basic được nhập bằng prompt ẩn trong terminal tương tác và chỉ được đưa vào environment của tiến trình client; không gõ chúng thành nội dung lệnh. Git token, nếu dùng remote repository, cũng là credential riêng và chỉ có quyền đọc; cấp nó qua credential helper hoặc secret file được bảo vệ.

Kiểm tra các biến đã tồn tại mà không in giá trị:

~~~bash
test -n "$VAULT_TOKEN" && echo "Vault token is configured"
test -n "$ORDERS_CONFIG_PASSWORD" && echo "Orders client credential is configured"
test -n "$PAYMENT_CONFIG_PASSWORD" && echo "Payment client credential is configured"
~~~

Không dùng lệnh env, printenv hoặc echo biến secret trong log CI. Không truyền secret trong command-line argument nếu nền tảng có secret file hoặc workload identity.

Khởi động Config Server:

~~~bash
cd config-server
mvn spring-boot:run
~~~

Nếu server không khởi động, kiểm tra lần lượt Git URI, quyền đọc repository, Vault address, token policy và TLS. Không tắt certificate verification để bỏ qua lỗi TLS trong production.

## 11. Kiểm tra Environment hợp nhất trước khi chạy client

Gọi endpoint của orders-service:

~~~bash
curl --fail --silent --show-error \
  --user orders-service \
  http://localhost:8888/orders-service/prod/main \
  | jq -e '{
      name,
      profiles,
      label,
      version,
      sourceCategories: [
        .propertySources[]? |
        ((.name // "" | ascii_downcase) as $source
          | if ($source | contains("vault")) then "vault"
            elif ($source | contains("git")) then "git"
            else "other"
            end)
      ],
      keyPresence: {
        datasourcePassword: any(.propertySources[]?;
          ((.source // {}) | has("spring.datasource.password"))),
        ordersReadTimeout: any(.propertySources[]?;
          ((.source // {}) | has("orders.http.read-timeout"))),
        precedenceProbe: any(.propertySources[]?;
          ((.source // {}) | has("config.precedence-probe")))
      },
      precedenceProbeSourceCategories: [
        .propertySources[]?
        | select((.source // {}) | has("config.precedence-probe"))
        | ((.name // "" | ascii_downcase) as $source
            | if ($source | contains("vault")) then "vault"
              elif ($source | contains("git")) then "git"
              else "other"
              end)
      ]
    }'
~~~

Khi chạy lệnh trong terminal tương tác, curl với tùy chọn --user orders-service sẽ hỏi password mà không đặt password trong command line hoặc shell history. Nhập password từ credential store đã được duyệt. Trong mô hình này không gửi header X-Config-Token. Config Server tự xác thực với Vault bằng token server-side.

Response JSON dự kiến có metadata application/profile/label và nhiều property source. Tên property source cụ thể phụ thuộc phiên bản backend. Kiểm tra:

- Có source từ Git chứa platform.region và orders.http.read-timeout.
- Có source từ Vault chứa spring.datasource.username và spring.datasource.password.
- Git version phản ánh commit đã đọc.
- config.precedence-probe có giá trị hiệu lực from-vault.
- Response được trả cho đúng application và profile.

Projection trên chỉ xuất application/profile/label/version, category nguồn được ánh xạ, và trạng thái key có mặt; không xuất property values hoặc raw property source names. precedenceProbeSourceCategories phải liệt kê vault trước git theo thứ tự repository đã cấu hình. Nếu key password không có mặt hoặc category không đúng, dừng kiểm tra và xem lại policy, Vault path, profile và repository order trong kênh quản trị; không in raw Environment response.

## 12. Tạo Config Client orders-service

Thêm dependency Config Client:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Dùng Spring Cloud BOM tương thích với Config Server. Cấu hình application.yml:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      username: orders-service
      password: ${ORDERS_CONFIG_PASSWORD}
      label: main
~~~

Trong production, dùng HTTPS thay cho HTTP và inject password qua secret manager. Không commit giá trị password. Config Client không cần khai báo Git URI, Git token, Vault address hoặc Vault token; tất cả được giữ ở phía Config Server.

Một bean có thể bind thuộc tính thông thường và secret:

~~~java
@ConfigurationProperties(prefix = "spring.datasource")
public record OrdersDatabaseProperties(
        String username,
        String password) {
}
~~~

Không expose record này qua endpoint chẩn đoán hoặc log object. Trong ứng dụng thật, Spring Boot datasource auto-configuration có thể bind trực tiếp các property spring.datasource; ví dụ record chỉ minh họa việc secret đã vào Environment phía client.

## 13. Tạo Config Client payment-service

Cấu hình payment-service/application.yml:

~~~yaml
spring:
  application:
    name: payment-service
  profiles:
    active: prod
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      username: payment-service
      password: ${PAYMENT_CONFIG_PASSWORD}
      label: main
~~~

Payment service nhận Git properties của payment-service và secret từ Vault path tương ứng. Nó không cần biết token Vault hoặc token Git.

Nếu hai client dùng chung một username/password, authorization theo application name sẽ không còn phân biệt được service. Mỗi workload phải có danh tính riêng, credential riêng và quyền chỉ đọc application của nó.

## 14. Kiểm thử phân quyền bằng curl

Đây là phần quan trọng nhất của bài lab. Thực hiện cả truy cập hợp lệ và truy cập chéo.

Các lệnh bên dưới chỉ ghi HTTP status bằng --output /dev/null và --write-out; chúng không in response body chứa Environment. Với request có Basic auth, dùng --user chỉ kèm username để curl hỏi password tương tác. Chạy trong terminal thật, không dùng shell script/CI non-interactive cho prompt này.

| Test | Credential | Request | Kết quả mong đợi |
| --- | --- | --- | --- |
| AUTH-01 | Không có | GET orders-service/prod/main | 401 Unauthorized |
| AUTH-02 | orders-service | GET orders-service/prod/main | 200 OK |
| AUTH-03 | orders-service | GET payment-service/prod/main | 403 Forbidden |
| AUTH-04 | payment-service | GET payment-service/prod/main | 200 OK |
| AUTH-05 | payment-service | GET orders-service/prod/main | 403 Forbidden |
| AUTH-06 | Sai password | GET orders-service/prod/main | 401 Unauthorized |

Kiểm thử không xác thực:

~~~bash
curl --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  http://localhost:8888/orders-service/prod/main
~~~

Kiểm thử orders-service đọc cấu hình của chính nó:

~~~bash
curl --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  --user orders-service \
  http://localhost:8888/orders-service/prod/main
~~~

Kiểm thử orders-service cố đọc secret của payment-service:

~~~bash
curl --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  --user orders-service \
  http://localhost:8888/payment-service/prod/main
~~~

Kết quả phải là 403. Request đã xác thực thành công nhưng application path không khớp principal.

Kiểm thử payment-service đọc cấu hình của chính nó:

~~~bash
curl --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  --user payment-service \
  http://localhost:8888/payment-service/prod/main
~~~

Kiểm thử payment-service cố đọc orders-service:

~~~bash
curl --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  --user payment-service \
  http://localhost:8888/orders-service/prod/main
~~~

Kết quả phải là 403. Không chỉ kiểm tra response code; ghi nhận test result, application path và principal trong audit log mà không ghi password hoặc Authorization header.

Kiểm thử AUTH-06 với password sai:

~~~bash
curl --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  --user orders-service \
  http://localhost:8888/orders-service/prod/main
~~~

Khi curl hỏi password, nhập một password giả không đúng trong môi trường lab. Kết quả phải là HTTP 401. Không thêm password giả vào command line hoặc script; lệnh chỉ xuất status và bỏ response body.

## 15. Kiểm thử Git và Vault độc lập

Khi request Environment thất bại, cần biết backend nào gây lỗi. Có thể tạm thực hiện các kiểm tra độc lập trong môi trường lab.

**Kiểm tra Git**

~~~bash
git -C config-repo status --short
git -C config-repo log -1 --oneline
~~~

Xác nhận Config Server dùng đúng repository và label main. Với remote Git, thử clone/fetch bằng danh tính read-only từ môi trường kiểm thử, không in token.

**Kiểm tra Vault**

Lệnh metadata cần quyền read trên metadata path; chạy phần này bằng identity vận hành metadata-reader đã được duyệt. Config Server token chỉ cần quyền read trên data path và cố ý không được cấp quyền metadata/list. Sau đó nạp lại scoped Config Server token từ file bảo vệ trước khi chạy capability checks.

~~~bash
vault kv metadata get -format=json -mount=config-kv orders-service,prod \
  | jq -e '{
      currentVersion: .data.current_version,
      oldestVersion: .data.oldest_version,
      versions: ((.data.versions // {}) | with_entries(
        .value |= {created_time, deletion_time, destroyed}
      ))
    }'
export VAULT_TOKEN="$(< "$HOME/.config/vault/config-server-token")"
vault token capabilities -format=json config-kv/data/orders-service,prod \
  | jq -e 'index("read") != null and index("write") == null'
vault token capabilities -format=json config-kv/metadata/orders-service,prod \
  | jq -e 'index("deny") != null and index("list") == null'
~~~

Lệnh metadata chỉ xuất version/timestamp/deletion state, không đọc secret data. Capability check dùng token hiện tại trong VAULT_TOKEN; trước khi chạy phải xác nhận đó là scoped Config Server token như phần 6, không phải dev/root token. Không truyền token vào argv.

Nếu Vault đọc được nhưng Config Server không trả secret, kiểm tra token server-side, mount path, kv-version và profile separator. Với KV v2, CLI dùng mount/path logic, còn API nội bộ có data/; cấu hình kv-version=2 giúp backend xử lý khác biệt này.

## 16. Kiểm thử thứ tự ưu tiên Git và Vault

Trong Git có giá trị:

~~~yaml
config:
  precedence-probe: from-git
~~~

Trong Vault có giá trị:

~~~text
config.precedence-probe = from-vault
~~~

Do Vault có order 1 và Git có order 2, kết quả hiệu lực dự kiến là from-vault. Dùng lệnh jq ở phần trước để kiểm tra giá trị đầu tiên xuất hiện trong propertySources.

Thử bỏ key precedence-probe khỏi Vault trong môi trường lab. Khi đó Config Server phải trả giá trị từ Git là from-git. Việc này chứng minh Git vẫn là nguồn fallback cho key không có ở Vault.

Không nên dùng Vault như nơi ghi đè tùy tiện mọi property. Định nghĩa ownership:

- Git sở hữu timeout, feature flag, endpoint không nhạy cảm, retry policy và release metadata.
- Vault sở hữu password, token, private credential và secret theo service.
- Nếu cùng key có mặt ở cả hai backend, ghi rõ lý do và test precedence.

## 17. Kiểm thử khi một backend không sẵn sàng

Mặc định, composite Environment có thể thất bại toàn bộ nếu một repository thành phần không lấy được dữ liệu. Điều này thường phù hợp với cấu hình có secret bắt buộc: Config Server không nên âm thầm trả Environment thiếu password rồi để client chạy với trạng thái không xác định.

Các tình huống thử trong lab:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Git repository không truy cập được | Config fetch thất bại hoặc báo lỗi backend |
| Vault token hết hạn/bị thu hồi | Secret fetch thất bại; không coi secret là giá trị rỗng hợp lệ |
| Vault policy thiếu read | Request thất bại và audit ghi nhận permission denied |
| Secret path sai | Environment không có secret; startup/validation của client phải fail theo policy |
| Git có giá trị nhưng Vault key bắt buộc mất | Client không được dùng một password mặc định nguy hiểm |

Chỉ cấu hình failOnCompositeError=false khi đã định nghĩa rõ backend nào có thể thiếu và ứng dụng có fallback an toàn. Với credential bắt buộc, fail closed thường là lựa chọn đúng hơn.

Có thể thêm validation khi startup:

~~~java
@Component
public class RequiredConfigurationCheck implements ApplicationRunner {

    private final Environment environment;

    public RequiredConfigurationCheck(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        environment.getRequiredProperty("spring.datasource.username");
        environment.getRequiredProperty("spring.datasource.password");
    }
}
~~~

Đoạn kiểm tra chỉ minh họa yêu cầu key bắt buộc. Không log giá trị. Trong ứng dụng thật, dùng Bean Validation với @ConfigurationProperties để xác thực nhóm cấu hình và trả lỗi rõ ràng nếu secret thiếu.

## 18. Kiểm thử bằng JUnit cho authorization

Có thể tự động hóa các trường hợp truy cập chéo bằng Spring Boot integration test. Ví dụ dùng TestRestTemplate trong Config Server test context:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ConfigServerAuthorizationIT {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void ordersClientCanReadOrdersConfiguration() {
        ResponseEntity<String> response = restTemplate
                .withBasicAuth("orders-service", "orders-test-password")
                .getForEntity("/orders-service/prod/main", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void ordersClientCannotReadPaymentConfiguration() {
        ResponseEntity<String> response = restTemplate
                .withBasicAuth("orders-service", "orders-test-password")
                .getForEntity("/payment-service/prod/main", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void paymentClientCannotReadOrdersConfiguration() {
        ResponseEntity<String> response = restTemplate
                .withBasicAuth("payment-service", "payment-test-password")
                .getForEntity("/orders-service/prod/main", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }
}
~~~

Các import chính gồm SpringBootTest, Autowired, TestRestTemplate, ResponseEntity, HttpStatus, JUnit Test và AssertJ. Test password phải là giá trị giả dành riêng cho test; không dùng secret production.

Nếu muốn test toàn bộ Git/Vault integration, dùng test environment cô lập với Git fixture và Vault test server/Testcontainer. Test phải kiểm tra cả status code, property source và precedence. Không để integration test phụ thuộc Vault production hoặc một Git repository dùng chung.

## 19. Xác minh client nhận secret mà không in secret

Một bài test end-to-end cần chứng minh client nhận đúng secret nhưng không đưa giá trị ra terminal.

Các cách an toàn hơn:

- Kiểm tra property key tồn tại trong Environment mà không in value.
- Thực hiện kết nối database thử bằng credential được cấp.
- Gọi API test yêu cầu token và chỉ ghi nhận HTTP status.
- Dùng metric hoặc health contributor chỉ trả trạng thái credential hợp lệ.
- So sánh Vault KV version hoặc release metadata, không so sánh plaintext.

Không expose /actuator/env hoặc /actuator/configprops rộng trong production chỉ để kiểm tra secret. Nếu bật endpoint trong lab, giữ authentication, giới hạn network và sanitization; sau khi kiểm tra, tắt hoặc thu hẹp exposure.

## 20. Thay đổi secret và refresh client

Khi password hoặc token thay đổi trong Vault, cần bảo đảm Config Server đọc version mới và client nạp lại Environment. Git webhook không tự thông báo thay đổi Vault KV. Phải có quy trình refresh riêng cho nguồn Vault, ví dụ thao tác vận hành có kiểm soát hoặc cơ chế kiểm tra version/refresh do nền tảng xây dựng.

Quy trình cơ bản:

1. Ghi version mới vào Vault KV v2.
2. Xác nhận Config Server đọc được secret mới cho đúng application/profile.
3. Xác nhận Config Server không cache hoặc giữ version cũ theo cấu hình hiện tại.
4. Gọi refresh một client canary hoặc triển khai lại canary.
5. Xác nhận bean/DataSource/client dùng credential mới bằng kết nối thử.
6. Refresh hoặc rollout các instance còn lại.
7. Chỉ thu hồi credential cũ sau khi mọi instance đã chuyển đổi và connection cũ đã drain.

Endpoint /actuator/refresh làm mới Environment của một client instance; Spring Cloud Bus có thể phát refresh cho nhiều client nếu hệ thống đã cấu hình Bus. Không coi HTTP 200 là bằng chứng secret đã được áp dụng. Nếu bean hoặc pool giữ credential lúc khởi tạo, cần thay thế resource có kiểm soát hoặc rolling restart.

## 21. Rollback và versioning

Git và Vault có lịch sử/version riêng:

| Nguồn | Cách truy vết | Cách rollback |
| --- | --- | --- |
| Git | Commit SHA, branch, immutable tag | Revert commit hoặc chọn label đã phát hành |
| Vault KV v2 | Secret version và metadata | Xác minh metadata; dùng automation provider-side để restore/reissue thành version mới mà không xuất payload |
| Config Server | Application/profile/label và Git version | Xác minh Environment sau khi backend đã rollback |
| Config Client | Release ID và trạng thái runtime | Refresh/restart theo từng instance và kiểm tra hành vi |

Vault KV v2 cho phép xem metadata của một version cũ mà không đọc secret data. Chạy truy vấn metadata bằng identity metadata-reader được cấp quyền read metadata; không mở rộng policy runtime của Config Server chỉ để chạy truy vấn vận hành:

~~~bash
vault kv metadata get -format=json -mount=config-kv orders-service,prod \
  | jq -e '{
      currentVersion: .data.current_version,
      versionOne: .data.versions["1"] |
        if . == null then "not-present"
        else {created_time, deletion_time, destroyed}
        end
    }'
~~~

Không dùng vault kv get trong runbook/evidence vì lệnh đó hiển thị secret values. Để khôi phục, dùng secret provisioning pipeline hoặc automation đã được phê duyệt để copy/reissue provider-side và ghi một version mới mà không đưa payload qua terminal. Không sửa lịch sử hoặc xóa version cũ chỉ để làm cho metadata trông như chưa từng thay đổi.

Git rollback và Vault rollback phải được phối hợp trong cùng release manifest. Một commit Git cũ không tự khôi phục Vault secret version cũ.

## 22. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Config Server không khởi động | Git URI, Vault address hoặc token sai | Kiểm tra log backend đã sanitize và biến môi trường tồn tại |
| Config Server trả lỗi Vault | Sai mount, kv-version hoặc policy | Kiểm tra mount KV v2, path và token capabilities |
| Git có cấu hình nhưng không có secret | Vault backend không hoạt động hoặc secret path sai | Gọi Vault test path và Config Server endpoint |
| Client nhận 401 | Basic credential thiếu hoặc sai | Kiểm tra client identity/password và server user store |
| Client nhận 403 khi đọc chính nó | Username không khớp application path | So sánh spring.application.name với principal |
| Orders đọc được payment | Authorization matcher không được áp dụng hoặc filter chain khác thắng | Kiểm thử request chéo và kiểm tra SecurityFilterChain |
| Vault token xuất hiện ở client | Dùng X-Config-Token header thay vì server-side auth | Chuyển Vault authentication sang Config Server identity |
| Giá trị Git thắng ngoài dự kiến | order hoặc active profiles không đúng | Kiểm tra order và propertySources |
| Secret cũ sau refresh | Config Server chưa thấy Vault version mới hoặc bean giữ giá trị cũ | Kiểm tra backend version, Environment và bean lifecycle |
| Một backend lỗi nhưng client vẫn khởi động | Composite failure bị bỏ qua hoặc fallback không an toàn | Kiểm tra failOnCompositeError và validation |
| Secret xuất hiện trong log | In response Environment hoặc bật HTTP debug | Xóa log nhạy cảm, rotate secret và sửa logging |

## 23. Checklist hoàn thành dự án

- [ ] Git repository chỉ chứa cấu hình không bí mật.
- [ ] Config Server đọc Git bằng danh tính read-only.
- [ ] Vault mount được xác nhận là KV v2.
- [ ] Vault policy chỉ cấp read cho các path cần thiết.
- [ ] Config Server dùng token/identity Vault server-side.
- [ ] Client không cần Git token hoặc Vault token.
- [ ] Git và Vault được cấu hình order có chủ đích.
- [ ] Key trùng được kiểm thử precedence.
- [ ] Orders client đọc được orders Environment.
- [ ] Orders client bị 403 khi yêu cầu payment Environment.
- [ ] Payment client đọc được payment Environment.
- [ ] Payment client bị 403 khi yêu cầu orders Environment.
- [ ] Request không xác thực nhận 401.
- [ ] Secret key có mặt nhưng giá trị không bị in ra log.
- [ ] Git revision và Vault KV version được ghi trong release metadata.
- [ ] Có quy trình refresh/rotation và rollback cho cả hai backend.
- [ ] Config Server dùng HTTPS trong môi trường triển khai thật.
- [ ] Actuator và endpoint quản trị được bảo vệ.

## 24. Mục tiêu cần đạt sau bài học

Sau khi hoàn thành lab, người học cần có thể:

- Giải thích vì sao Git và Vault phục vụ hai loại dữ liệu cấu hình khác nhau.
- Cấu hình Config Server đọc đồng thời Git và Vault KV v2.
- Tổ chức secret theo application/profile.
- Tạo Vault policy read-only cho identity của Config Server.
- Giải thích vì sao client không nên giữ Vault token khi Config Server xác thực với Vault ở server-side.
- Thiết lập thứ tự ưu tiên giữa Git và Vault.
- Bảo vệ Config Server bằng xác thực và authorization theo application path.
- Viết kiểm thử 401, 403 và 200 cho các danh tính client.
- Xác minh Environment hợp nhất mà không in plaintext secret.
- Thiết kế refresh, rotation và rollback phối hợp giữa Git và Vault.

**Tự kiểm tra:** orders-service dùng đúng credential vẫn nhận HTTP 403 khi gọi endpoint của chính nó, trong khi payment-service truy cập thành công. Hãy xác định các bước cần kiểm tra: username của Basic authentication, application path, SecurityFilterChain, client name, và log authorization. Sau đó giải thích vì sao không nên sửa lỗi bằng cách cho mọi client quyền đọc tất cả application.

## Tài liệu tham khảo

- [Spring Cloud Config — Vault Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/vault-backend.html)
- [Spring Cloud Config — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html)
- [Spring Cloud Config — Security and Per-Application Access Control](https://docs.spring.io/spring-cloud-config/reference/server/security.html)
- [Spring Cloud Vault — Secret Backends](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html)
- [HashiCorp Vault — KV Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/kv)
