# Quản lý mật khẩu, chuỗi kết nối và chứng chỉ bằng cấu hình bí mật

## Mục tiêu bài học

Trong một ứng dụng **Spring Data Couchbase**, thông tin để kết nối database thường bao gồm **connection string**, **username**, **password** và đôi khi là **CA certificate**, **client certificate**, **private key** hoặc mật khẩu của keystore. Chỉ cần cấu hình sai một yếu tố, `CouchbaseRepository` có thể gặp lỗi authentication/TLS trước khi truy cập document; nguy hiểm hơn, nếu lưu bí mật trong Git hoặc container image, một lần rò rỉ có thể cho phép truy cập dữ liệu ở nhiều bucket.

Bài thuộc chương **Bảo mật** của module `SPRING_DATA_COUCHBASE` hướng dẫn cách **nhận dạng, lưu trữ, cung cấp, kiểm thử và xoay vòng** những giá trị này. Mục tiêu là dùng cùng một mã nguồn Spring Boot cho Docker local, integration test, staging và Couchbase Capella mà không hardcode bí mật. Sau khi kết nối an toàn, ứng dụng mới thực hiện document mapping, `CouchbaseTemplate`, repository, SQL++, chỉ mục, TTL, CAS, transaction và reactive API theo quyền đã được cấp.

Kết thúc bài, bạn có thể:

- Phân loại chính xác **secret**, **thông tin cấu hình**, **trust certificate** và **private key**.
- Dùng **Spring Boot Externalized Configuration**, biến môi trường, mounted files/`configtree:` và secret manager mà không ghi password vào artifact.
- Chọn `couchbase://` cho lab không TLS trong mạng được cô lập, `couchbases://` cho Capella/TLS; hiểu bootstrap, DNS SRV và hostname verification.
- Cấu hình **CA tin cậy**, **SSL bundle PEM/JKS** khi cần, đồng thời nhận diện các tình huống yêu cầu **client certificate authentication (mTLS)**.
- Tách credentials giữa application runtime, admin, migrator; local/test/staging/prod có bí mật riêng.
- Thiết kế xoay **database password**, **CA/trust** và **client certificate/private key** mà không mặc định SDK sẽ reload tự động.
- Kiểm tra kết nối KV/SQL++ mà không log mật khẩu, chuỗi cấu hình nhạy cảm hoặc private key.
- Viết checklist GO/NO-GO và quy trình phản ứng khi credential hoặc khóa bị rò rỉ.

> **Điều kiện nền:** Ví dụ dùng Spring Boot và Couchbase Java SDK 3.x tương thích với nhau. Cluster đã có bucket `training`, scope `commerce`, collection `orders`; user runtime có quyền phù hợp. Mọi giá trị mật khẩu trong ví dụ là **tên biến/placeholder**, không phải credential thật. TLS phía Couchbase Server self-managed cần edition, certificate và cấu hình hỗ trợ tương ứng; **không** kết luận một Server Community Docker không cấu hình TLS có thể được bảo mật chỉ bằng cách đổi URI.

## 1. Phân loại những giá trị phải quản lý

| Giá trị | Có phải secret? | Được phép nằm ở đâu? | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Application password** (`CB_APP_PASSWORD`) | **Có** | Vault/secret manager hoặc mounted secret, giới hạn quyền | Hardcode trong `application-prod.yml`, truyền qua URL hoặc commit `.env` |
| **Admin/provisioning password** | **Có, đặc biệt nhạy cảm** | Secret manager riêng, chỉ cấp cho job/người được ủy quyền | Đưa vào container API để lúc startup tự tạo index/user |
| **Connection string** | Thường là cấu hình; vẫn có thể nhạy cảm về hạ tầng | Config không bí mật hoặc secret store theo chính sách tổ chức | Nhúng `user:pass@host`, in cả URI có token/parameters ra log |
| **Bucket/scope/collection name** | Thường không phải secret | Config theo môi trường | Chọn nhầm bucket production trong test |
| **CA/root certificate (public)** | **Không chứa khóa riêng**, nhưng cần kiểm tra tính xác thực/toàn vẹn | Config volume, truststore, artifact được quản lý, nguồn đã xác minh | Coi nó là password hoặc tải từ nguồn không tin cậy |
| **Client certificate (public)** | Bản thân certificate không bí mật, nhưng có tính định danh | TLS config/cert manager | Nhầm client certificate với server CA |
| **Client private key** | **Có, cực kỳ nhạy cảm** | Secret manager/HSM hoặc volume mount bảo vệ chặt | Commit `client.key`, đưa vào image, chia sẻ kèm certificate |
| **Keystore/truststore password** | **Có** (nếu bảo vệ khóa/keystore) | Secret manager / configtree | Hardcode vào YAML hoặc dòng lệnh `-D...password=...` |
| **JWT/API key của secret provider** | **Có** | Workload identity/short-lived token/secret manager | Thêm credential cloud dài hạn vào pod để đọc secret khác |
| **Server certificate public** | Không phải secret | Chuỗi TLS do Server gửi, được CA xác nhận | "Khắc phục" hostname mismatch bằng tắt verification |

**Nguyên tắc:** *Secret cần bảo mật tính bí mật; CA/trust certificate cần bảo mật tính xác thực và toàn vẹn.* Một file `ca.pem` công khai không nguy hiểm như `client.key` bị lộ, nhưng tin cậy nhầm CA cũng có thể khiến app kết nối vào server giả.

### 1.1. Luồng đi của bí mật phải được kiểm soát

```mermaid
flowchart LR
    OPS["Security / Platform Team"]
    VAULT["Secret Manager / KMS / Vault"]
    CFG["Non-secret deploy config"]
    APP["Spring Boot Runtime"]
    SDK["Couchbase Java SDK"]
    DB["Couchbase Server / Capella"]
    OPS -->|"Tạo, phân quyền, xoay"| VAULT
    VAULT -->|"Inject password/keys qua cơ chế được phép"| APP
    CFG -->|"Endpoint, bucket, profile, trust path"| APP
    APP -->|"Spring Environment / SSL bundle"| SDK
    SDK -->|"TLS + xác thực + RBAC"| DB
```

Không đưa secret qua repo/CI log/image registry chỉ để rút ngắn đường triển khai. Một secret đã đọc vào process memory vẫn có nguy cơ bị người có quyền host/container truy cập; **Externalized Configuration giảm nơi phân phối bí mật, không làm bí mật biến mất khỏi runtime**.

## 2. Phân biệt connection string và credential

### 2.1. Chọn scheme theo môi trường

| Môi trường | Connection string ví dụ | Yêu cầu kèm theo |
| --- | --- | --- |
| Couchbase Server local chạy Docker, app trên host | `couchbase://127.0.0.1` | Chỉ lab loopback/cô lập; 8091/11210/8093 và cluster đã thiết lập |
| Spring Boot ở container cùng Docker network | `couchbase://couchbase` | `couchbase` là tên service DNS, node advertise địa chỉ truy cập được |
| Self-managed Enterprise có TLS | `couchbases://cb.internal.example` | TLS trên cluster, tên máy hợp lệ trong certificate, CA đáng tin |
| Capella public | **Chuỗi `couchbases://...` từ Connect → SDK** | DNS SRV, TLS, public egress IP allowlist, cluster access credential |
| Capella private | **Chuỗi private do Capella cung cấp** | Private DNS/route/endpoint được cấu hình đúng, TLS |

`couchbase://` thường dùng giao thức không TLS trong lab. `couchbases://` buộc giao thức TLS phía client; **không** thay nó bằng `couchbase://` để bỏ qua lỗi chứng chỉ. Đối với Capella, endpoint có thể được khám phá qua **DNS SRV**; khi có một hostname không kèm port, Java SDK có thể tìm các service nodes/ports thích hợp. **Không tự suy hostname từ bucket hoặc username.**

### 2.2. Không nhét username/password vào URI

**Không làm:**

```text
couchbases://orders-api:<password>@cb.example.invalid
```

Ví dụ trên thể hiện anti-pattern; đừng dùng cấu trúc `user:password@...` làm connection string của Couchbase SDK. Hãy truyền **connection string chỉ chứa địa chỉ và tham số SDK hợp lệ**, còn username/password trong các nguồn cấu hình riêng. URI có chứa secret rất dễ bị in qua exception, log startup, tracing, command history hoặc monitoring.

**Kể cả URI không chứa mật khẩu**, hostname cluster, query options và đường private endpoint có thể là thông tin nội bộ. Ghi log ở mức **environment alias** và fingerprint đã được phê duyệt thay vì đưa toàn bộ endpoint vào log công khai.

### 2.3. Bootstrap thành công chưa đủ

Java SDK dùng seed address để nhận topology rồi kết nối đến các **Data/Query/Index service nodes**. Nếu app chạy ngoài Docker network nhưng Couchbase quảng bá IP bridge nội bộ, SDK vẫn có thể timeout dù Web Console 8091 mở được. Đây là vấn đề **DNS/NAT/alternate addresses**, không phải password.

Tương tự, Capella có thể trả lỗi network khi IP public egress chưa nằm trong Allowed IP Addresses. Hãy tách rõ thứ tự chẩn đoán: network/DNS → TLS → authentication → authorization/RBAC → bucket/collection/index → nghiệp vụ.

Nguồn: [Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html), [Capella — Connect](https://docs.couchbase.com/cloud/get-started/connect.html), [Capella — Allowed IP Addresses](https://docs.couchbase.com/cloud/clusters/allow-ip-address.html).

## 3. Cấu hình chung Spring Boot bằng placeholders

Với `spring-boot-starter-data-couchbase` và BOM phù hợp, một file `application.yml` an toàn có thể là:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: orders-service
  couchbase:
    connection-string: ${CB_CONNECTION_STRING}
    username: ${CB_APP_USERNAME}
    password: ${CB_APP_PASSWORD}
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME}
```

Các placeholder `${CB_...}` do Spring Boot giải từ môi trường/chế độ cấu hình đã thiết lập. **Không dùng default password** như `${CB_APP_PASSWORD:admin123}`. Khi thiếu một giá trị bắt buộc, startup hoặc lần khởi tạo bean cần giá trị đó phải **FAIL**; không tự fallback tới Administrator.

### 3.1. Tách cấu hình chung và profile

```text
src/main/resources/
  application.yml          # Placeholder chung; không chứa secret
  application-local.yml    # Endpoint/bucket lab; không có password
  application-staging.yml  # Non-secret differences ở staging
  application-prod.yml     # Non-secret policies/timeout prod
src/test/resources/
  application-test.yml     # Dùng credentials / cluster test chuyên biệt
```

Ví dụ cấu hình **lab host-only**:

```yaml
# application-local.yml
spring:
  config:
    activate:
      on-profile: local
  couchbase:
    connection-string: ${CB_CONNECTION_STRING:couchbase://127.0.0.1}
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME:training}
```

Chỉ `connection-string` và bucket lab có **default không bí mật**. Username/password luôn đến từ secret/config riêng. Không đặt `spring.profiles.active: local` trong file chung để tránh khởi chạy nhầm ở production; chọn profile từ deployment với `SPRING_PROFILES_ACTIVE`.

Ví dụ profile `test` cần các biến riêng:

```yaml
# src/test/resources/application-test.yml
spring:
  config:
    activate:
      on-profile: test
  couchbase:
    connection-string: ${CB_IT_CONNECTION_STRING}
    username: ${CB_IT_USERNAME}
    password: ${CB_IT_PASSWORD}
  data:
    couchbase:
      bucket-name: ${CB_IT_BUCKET_NAME}
```

**Lưu ý:** test profile không tự chặn truy cập prod. CI runner phải được cấp network/credentials **chỉ cho môi trường test**; các bài có mutation phải có data fixture và guard độc lập. Chỉ thay tên `CB_IT_*` mà vẫn dùng production secret là không an toàn.

### 3.2. Nguồn cấu hình và thứ tự ưu tiên

Spring Boot áp dụng thứ tự `PropertySource` có quy tắc. Dạng rút gọn:

```text
application.yml trong JAR
   ↓
application-{profile}.yml trong JAR
   ↓
application.yml và file profile ở external config location
   ↓
OS environment variables
   ↓
Java system properties / command-line arguments
   ↓
Test properties / DynamicPropertySource (trong test context, theo cơ chế riêng)
```

**Đây là mô hình giản lược**, không thay thế danh sách độ ưu tiên đầy đủ của Spring Boot; `spring.config.import`, `configtree:`, `SPRING_APPLICATION_JSON` và profile groups còn có quy tắc khác. Ví dụ command-line `--spring.couchbase.password=...` thường override file config, nhưng **không nên truyền secret theo command line** vì lộ qua process listing, shell history và audit/CI logs.

Khi dùng `spring.config.import`, cấu hình được import có thể ưu tiên hơn tài liệu khai báo nó; phải review **effective config** mà không in secret. Với các biến OS và placeholders, nên dùng tên thuộc tính thống nhất/đúng relaxed binding và tránh khai báo hai nguồn xung đột.

### 3.3. Fail-closed và kiểm tra sớm

Ứng dụng cần coi cấu hình thiếu hoặc rõ ràng không an toàn là lỗi deploy, ví dụ:

- Production đang dùng `couchbase://` khi policy yêu cầu TLS.
- `CB_APP_USERNAME` là `Administrator` hoặc trùng migration/admin identity.
- Test job có credential hoặc endpoint production.
- Không có password trong secret store hoặc certificate path trống.
- SSL trust config chỉ hoạt động khi tắt hostname validation.

**Đừng log value để kiểm tra đã nạp được hay chưa.** Có thể ghi `hasCredential = true`, profile, tên bucket đã được phê duyệt và trạng thái TLS, nhưng không ghi `CB_APP_PASSWORD`, full `Environment`, private key hoặc PEM contents.

Nguồn: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html).

## 4. Biến môi trường: thực dụng nhưng không phải secret manager

Biến môi trường dễ dùng với IntelliJ, Gradle, Docker và cloud runtime. Chúng **không tự được mã hóa** và có thể bị đọc qua quyền OS/container, process inspection, diagnostic dump hoặc công cụ orchestration.

### 4.1. Ví dụ local qua IDE hoặc terminal

Trên máy phát triển, cấu hình **tên biến** trong Run Configuration:

```text
SPRING_PROFILES_ACTIVE=local
CB_CONNECTION_STRING=couchbase://127.0.0.1
CB_BUCKET_NAME=training
CB_APP_USERNAME=orders-api
CB_APP_PASSWORD=<giá trị lấy từ password manager, không đưa vào Git>
```

Đây là **bảng minh họa**, không phải file `.env` nên commit hoặc một câu lệnh shell hoàn chỉnh. Nếu IDE lưu giá trị trong cấu hình project được chia sẻ, cần chuyển secret sang cấu hình private của người dùng hoặc secret provider. Nếu phải chạy từ terminal, tránh đặt mật khẩu thật ngay trong lệnh được lưu history; với CI, dùng kho secret của nền tảng và quyền job hẹp.

### 4.2. Những nơi dễ lộ environment

| Bề mặt | Nguy cơ | Kiểm soát |
| --- | --- | --- |
| `Dockerfile ENV`, `ARG` lúc build | Lộ qua image/layers/history/registry | Chỉ inject ở runtime; build dùng bí mật tạm thời qua cơ chế secret mount của build system nếu thật cần |
| `docker compose config` | Có thể in giá trị đã nội suy | Không đưa output lên CI log hoặc ticket |
| `ps`/command-line `-Dpassword=...` | Người có quyền OS/agent có thể đọc | Không đặt secret trong tham số process |
| IDE/terminal history | Secret lưu lại ngoài ý muốn | Dùng secret prompt/provider và xóa/rotate nếu đã lộ |
| Spring Actuator `/env`, `/configprops` | Có thể tiết lộ nguồn cấu hình hoặc dữ liệu nhạy cảm | Giới hạn quyền endpoint; kiểm tra sanitization theo phiên bản |
| Exception/diagnostic logs | Chuỗi URI, headers hoặc contents bị in khi lỗi | Redact và giới hạn log level/time-to-live |
| Heap dump/core dump | Secret tồn tại trong memory | Bảo vệ dump, hạn chế người có quyền download, retention ngắn |

**Không chạy `printenv` hoặc xuất full config vào ticket** để chứng minh ứng dụng có biến môi trường: hãy chỉ in **danh sách tên biến đã được set**, không in giá trị.

## 5. Mounted secrets và Spring Boot `configtree:`

Nếu nền tảng cung cấp secret dưới dạng **file trong volume**, Spring Boot có thể đọc qua `configtree:`. Giá trị mỗi file trở thành một property. Cách này tránh gắn toàn bộ secret vào biến môi trường, nhưng **quyền đọc volume, encryption-at-rest và quyền trên host vẫn cần kiểm soát**.

### 5.1. Một phương án thay thế cho `CB_APP_PASSWORD`

Trên runtime có thể mount cấu trúc:

```text
/run/secrets/couchbase/
  spring.couchbase.username
  spring.couchbase.password
```

Nội dung mỗi file là giá trị cần bind; tên file có dấu chấm hợp lệ với `configtree:`. Khi sử dụng mô hình này, tạo **một nhánh cấu hình dành cho deployment dùng mounted secrets**, thay vì buộc cả hai biến `CB_APP_USERNAME` và `CB_APP_PASSWORD`:

```yaml
# Ví dụ application-secrets.yml dùng cùng ứng dụng,
# chỉ activate qua deployment profile đã định nghĩa rõ.
spring:
  config:
    import: "configtree:/run/secrets/couchbase/"
  couchbase:
    connection-string: ${CB_CONNECTION_STRING}
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME}
```

**Điều kiện:** Đừng đồng thời import file trên và giữ một cấu hình bắt buộc `spring.couchbase.password: ${CB_APP_PASSWORD}` từ base một cách không được kiểm thử. Nguồn nào thắng tùy property precedence; cần chủ động thiết kế **một nguồn credential có hiệu lực**, xem giá trị có mặt hay không theo cách redact. Với production, không thêm `optional:` vào `configtree:` nếu thiếu volume phải làm startup FAIL.

Mounted secret không bắt buộc phải tên `spring.couchbase.password`; có thể đặt `CB_APP_PASSWORD` rồi tham chiếu với placeholder, nhưng cần bảo đảm Spring Environment đọc tên file và placeholder theo đúng trường hợp. Mô hình property name trực tiếp thường ít tầng dịch hơn.

### 5.2. Docker Compose: secret ở file local vẫn là plaintext

Compose có thể mount một file local vào `/run/secrets/...`. Ví dụ **mảnh cấu hình** (không phải toàn bộ Compose file):

```yaml
services:
  app:
    image: orders-service:dev
    environment:
      SPRING_PROFILES_ACTIVE: compose-secrets
      CB_CONNECTION_STRING: couchbase://couchbase
      CB_BUCKET_NAME: training
    secrets:
      - source: couchbase_username
        target: spring.couchbase.username
      - source: couchbase_password
        target: spring.couchbase.password

secrets:
  couchbase_username:
    file: ./local-private/couchbase-username.txt
  couchbase_password:
    file: ./local-private/couchbase-password.txt
```

Trong mảnh này, secret targets mặc định nằm dưới `/run/secrets/`. Vì thế ví dụ Compose dùng **profile `compose-secrets` riêng** với file `application-compose-secrets.yml`:

```yaml
# src/main/resources/application-compose-secrets.yml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Profile `secrets` ở mục 5.1/5.3 dành cho mount `/run/secrets/couchbase/` của Kubernetes. **Hai đường mount khác nhau, không dùng chung một configtree path nếu file không nằm ở đó.** Trong cả hai trường hợp, thử cấu hình hiệu lực bằng test không tiết lộ secret và tránh các property password placeholder xung đột từ base.

**Cảnh báo bảo mật:** Docker Compose `secrets: file:` trên máy dev **không biến file nguồn thành secret được mã hóa tại nguồn**. File `./local-private/*.txt` là plaintext trên host; phải đặt trong `.gitignore`, giới hạn ACL, không chia sẻ và tránh backup/sync công khai. Production nên dùng secret manager hoặc hệ thống cấp secret được kiểm soát phù hợp nền tảng.

### 5.3. Kubernetes: mount Secret bằng volume

Ví dụ **mảnh Pod/Deployment spec**:

```yaml
spec:
  containers:
    - name: orders-service
      image: registry.example.invalid/orders-service:<immutable-image-tag>
      volumeMounts:
        - name: couchbase-credentials
          mountPath: /run/secrets/couchbase
          readOnly: true
      env:
        - name: SPRING_PROFILES_ACTIVE
          value: secrets
  volumes:
    - name: couchbase-credentials
      secret:
        secretName: orders-couchbase-credentials
```

Kubernetes Secret `orders-couchbase-credentials` phải được tạo **trước** bằng quy trình an toàn có các key `spring.couchbase.username` và `spring.couchbase.password`. **Không commit một Kubernetes Secret YAML chứa giá trị `data:` base64**: base64 chỉ là encoding, **không phải encryption**. Bảo vệ etcd/encryption-at-rest, namespace RBAC, service account, quyền `get/list/watch secrets`, admission/policy và volume mount. Cân nhắc CSI Secret Store/external secrets operator khi tổ chức sử dụng vault/cloud provider.

Trong Kubernetes, cập nhật Secret được mount vào volume có thể được phản ánh lên file sau một khoảng thời gian (trừ các cách mount như `subPath`), nhưng **ứng dụng Java SDK không mặc nhiên reload password hoặc TLS trust** chỉ vì byte trong file thay đổi. Thiết kế rollout/connection recreation và kiểm thử thực tế.

Nguồn: [Spring Boot — Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree), [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

## 6. TLS và certificate: ai xác thực ai?

**TLS** bảo vệ dữ liệu trên đường truyền và giúp client xác minh đúng Couchbase Server khi kiểm tra certificate chain/hostname. **Username/password** hoặc **client certificate authentication** xác định danh tính ứng dụng với Server. Hai cơ chế có trách nhiệm khác nhau:

```mermaid
sequenceDiagram
    participant App as Spring Boot / Java SDK
    participant Server as Couchbase Server / Capella
    App->>Server: Connect couchbases:// (TLS ClientHello)
    Server-->>App: Server certificate chain
    Note over App: Verify CA/trust, expiry, hostname/SAN
    opt Server có cấu hình xác thực client certificate
      Server->>App: Request client certificate
      App-->>Server: Client certificate + proof of private key
      Note over Server: Verify cert, extract identity, enforce RBAC
    end
    opt Xác thực bằng username/password thay cho client certificate
      App->>Server: Authenticate account over TLS
      Note over Server: Verify credential và RBAC
    end
    App->>Server: KV GET / SQL++ SELECT
    Server-->>App: Result hoặc error
```

| Vật liệu TLS | Chứa gì? | Bên nào dùng? | Cần lưu secret? |
| --- | --- | --- | --- |
| **Server certificate** | Public key, hostname/SAN, thời hạn, issuer | Server gửi; client xác minh | **Không**, nhưng phải xác minh CA/hostname |
| **Root/intermediate CA certificate** | Public key + thông tin CA | Client truststore để xác minh server; Server truststore khi xác minh client certificate | Không phải secret; phải lấy đúng nguồn |
| **Server private key** | Khóa riêng ký handshake của Server | Cluster/operator hoặc dịch vụ Capella quản lý | **Có**; không bao giờ cấp cho Spring Boot client |
| **Client certificate** | Định danh client đã được CA ký | App gửi khi Server yêu cầu client-certificate auth | Public cert; hạn chế lộ danh tính |
| **Client private key** | Khóa riêng tương ứng client certificate | App chứng minh sở hữu khi mTLS | **Có**; bảo vệ nghiêm ngặt |
| **Keystore/truststore password** | Mật khẩu bảo vệ store nếu có | App khi load store | **Có** |

### 6.1. Capella: dùng CA tích hợp sẵn khi phù hợp

Java SDK hiện đại **đóng gói root certificate tiêu chuẩn của Capella**; với cấu hình thông thường, đủ để dùng:

```text
CB_CONNECTION_STRING=couchbases://<endpoint-do-Capella-Connect-cung-cap>
CB_APP_USERNAME=<cluster-access-credential>
CB_APP_PASSWORD=<secret-tu-vault>
```

**Không cần import thêm root certificate nếu SDK đã hỗ trợ và cluster dùng CA tiêu chuẩn.** Capella Console cũng cung cấp root certificate tại phần security certificate cho trường hợp cần trust riêng, non-SDK client hoặc môi trường đặc biệt. Khi tải, cần kiểm tra đúng **cluster và nguồn tin cậy**; tài liệu Capella cung cấp tệp X.509 dạng `.txt`, có thể lưu lại `.pem`/`.crt` nếu ứng dụng yêu cầu.

Nếu tự cấu hình trust material mới và **thay** store mặc định, bạn có thể vô tình bỏ CA Capella đã được SDK tin cậy. **Đừng thêm custom SSL bundle khi không cần**; trước tiên thử `couchbases://` với SDK version tương thích, sau đó mới cấu hình CA riêng theo lỗi được quan sát.

Nguồn: [Java SDK — Managing Connections / Secure Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html), [Capella — Root Certificates](https://docs.couchbase.com/cloud/security/security-certificates.html).

### 6.2. Self-managed Enterprise: CA riêng hoặc JVM truststore

Khi Server dùng certificate do **CA được JVM tin cậy** ký, Couchbase Java SDK **3.4+** có thể xác minh thông qua JVM truststore mà không cần khai báo `securityConfig` riêng. Với CA nội bộ/self-signed chưa được JVM tin, bạn cần **xác minh nguồn CA certificate** và cấp trust đúng cách. Có thể:

1. Đưa CA vào JVM truststore theo quy trình platform, hoặc
2. Cấu hình SSL bundle/trust riêng cho kết nối Couchbase, hoặc
3. Customizer của Java SDK để chỉ định trust certificate/manager theo version.

**Không copy khóa riêng của Server sang client.** Ứng dụng chỉ cần public **CA trust anchor** và credential của chính nó (password hoặc client certificate+private key, nếu Server yêu cầu).

Khi kết nối bằng hostname `cb.internal.example`, certificate phải hợp lệ với hostname/SAN mà SDK kiểm tra. Trust một CA không sửa được lỗi **hostname mismatch**. Trong Docker/NAT, SDK có thể khám phá thêm node names; tất cả địa chỉ được client dùng phải tương thích network và certificate để tránh chỉ một node bị TLS error.

## 7. Cách cấu hình SSL bundle trong Spring Boot

Spring Boot hỗ trợ **SSL bundles** cho nhiều client connections, gồm Couchbase trong các phiên bản có property `spring.couchbase.env.ssl.bundle`. Chỉ áp dụng khi phiên bản Spring Boot và Couchbase Java SDK của dự án hỗ trợ các property tương ứng.

### 7.1. Dùng PEM CA certificate cho Couchbase Server tự quản lý

Giả sử platform đã mount file **CA công khai nhưng đã xác minh nguồn** vào `/etc/certs/couchbase/ca.pem`; tách khỏi file chứa username/password:

```yaml
# Cấu hình TLS cho Couchbase Server Enterprise có CA riêng.
spring:
  couchbase:
    connection-string: ${CB_CONNECTION_STRING}
    username: ${CB_APP_USERNAME}
    password: ${CB_APP_PASSWORD}
    env:
      ssl:
        enabled: true
        bundle: couchbase-trust
  ssl:
    bundle:
      pem:
        couchbase-trust:
          truststore:
            certificate: "file:/etc/certs/couchbase/ca.pem"
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME}
```

Trong môi trường này, `CB_CONNECTION_STRING` phải trỏ đến một cluster **thực sự đã cấu hình TLS**, ví dụ `couchbases://cb.internal.example`. PEM truststore chỉ xác định server nào đáng tin, **không** là client certificate và **không** thay thế `CB_APP_USERNAME`/`CB_APP_PASSWORD`. Nếu team dùng Capella với CA tiêu chuẩn, **không cần tự thêm** phần bundle này.

**Nếu hệ thống đã có `spring.couchbase.env.ssl.enabled: false` từ profile khác**, phải xóa override mâu thuẫn. Ưu tiên scheme `couchbases://` là biểu thị TLS rõ ràng theo Java SDK. Không dùng `http://`/`https://` thay cho Couchbase connection string.

### 7.2. Dùng PKCS12/JKS truststore khi tổ chức yêu cầu

Giả sử platform đã tạo truststore chứa CA đúng và đặt dưới volume:

```yaml
spring:
  ssl:
    bundle:
      jks:
        couchbase-trust:
          truststore:
            location: "file:/etc/certs/couchbase/truststore.p12"
            password: ${CB_TRUSTSTORE_PASSWORD}
            type: PKCS12
  couchbase:
    connection-string: ${CB_CONNECTION_STRING}
    username: ${CB_APP_USERNAME}
    password: ${CB_APP_PASSWORD}
    env:
      ssl:
        enabled: true
        bundle: couchbase-trust
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME}
```

`CB_TRUSTSTORE_PASSWORD` là **mật khẩu mở truststore**, khác với `CB_APP_PASSWORD` để xác thực Couchbase. Không tái sử dụng mật khẩu giữa các loại bí mật. Nếu truststore không cần password theo định dạng/cấu hình thực tế, không bịa một mật khẩu trong source; đối chiếu SSL bundle documentation.

**Lưu ý cấu hình:** Các ví dụ PEM và JKS ở trên là **hai phương án thay thế**, không khai báo hai bundle trùng tên trong cùng ứng dụng rồi để precedence tự quyết định. Khi dùng SSL bundle, kiểm tra certificate chain, hostname, quyền đọc file và version Boot. Trường hợp có **nhiều CA trong thời gian rotation**, hãy thiết kế truststore/bundle chứa đúng tập CA được phê duyệt, tránh chỉ pin một leaf certificate sắp hết hạn.

Nguồn: [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html), [Spring Boot — Couchbase SSL Bundles](https://docs.spring.io/spring-boot/reference/data/nosql.html).

## 8. Chỉ dùng client certificate/private key khi Server yêu cầu

Couchbase Server hỗ trợ **X.509 client-certificate authentication** khi được cấu hình phù hợp. Đây là chế độ mà **client chứng minh danh tính bằng certificate + private key**, ngoài việc client xác minh server. Nó khác với TLS thông thường dùng username/password:

| Chế độ | App xác minh server bằng | Server xác thực app bằng |
| --- | --- | --- |
| TLS thông thường + password | Server certificate/CA trust | Username/password |
| TLS + client certificate authentication | Server certificate/CA trust | Certificate có định danh được Server map tới user/RBAC + proof of private key |

Đừng "bật mTLS" chỉ bằng cách gửi certificate bất kỳ; Server phải tin CA ký client certificate, có cơ chế ánh xạ identity từ certificate và cấp RBAC phù hợp. Mật khẩu Couchbase và private key client là **hai phương thức authentication khác nhau**, không mặc định phải cấu hình đồng thời.

### 8.1. PEM certificate authentication (một cấu hình thay thế)

Spring Boot hỗ trợ các property PEM authentication khi Server và ứng dụng đã chủ động cấu hình phương án này:

```yaml
# Chỉ dùng nếu server đã được cấu hình xác thực bằng client certificate.
spring:
  couchbase:
    connection-string: ${CB_CONNECTION_STRING}
    env:
      ssl:
        enabled: true
        bundle: couchbase-trust
    authentication:
      pem:
        certificates: "file:/run/secrets/couchbase-client/client.crt"
        private-key: "file:/run/secrets/couchbase-client/client.key"
  ssl:
    bundle:
      pem:
        couchbase-trust:
          truststore:
            certificate: "file:/etc/certs/couchbase/ca.pem"
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME}
```

**Không thêm `spring.couchbase.username/password` vào cùng ví dụ** khi mục tiêu là xác thực bằng PEM client certificate. `client.key` là secret và phải được mount với quyền tối thiểu; `client.crt` là certificate public nhưng vẫn là định danh cần quản trị. Ví dụ này dành cho **Couchbase Server self-managed đã được bật client-certificate auth**, không áp dụng mặc định cho Capella cluster access credentials.

### 8.2. JKS/PKCS12 chứa client identity

Nếu đội platform cấp **keystore có client certificate và private key**, Spring Boot cũng có các property:

```yaml
spring:
  couchbase:
    connection-string: ${CB_CONNECTION_STRING}
    env:
      ssl:
        enabled: true
    authentication:
      jks:
        location: "file:/run/secrets/couchbase-client/client-identity.p12"
        password: ${CB_CLIENT_KEYSTORE_PASSWORD}
  data:
    couchbase:
      bucket-name: ${CB_BUCKET_NAME}
```

Nếu Server CA không nằm trong JVM truststore, cần thêm **truststore/SSL bundle** như mục 7.2; keystore **client identity** không tự đồng nghĩa với **trusted CA**. Keystore password là secret riêng. Cần xác minh định dạng PKCS12/JKS và alias theo version Boot/SDK trước triển khai.

### 8.3. Cấm những cách "sửa" TLS không an toàn

- Không vô hiệu hóa certificate validation, hostname verification hoặc dùng một `trust-all TrustManager`.
- Không chuyển từ `couchbases://` sang `couchbase://` chỉ vì bắt gặp `SSLHandshakeException`.
- Không đưa Server private key hoặc CA private signing key vào application image/secret volume.
- Không hardcode nội dung `-----BEGIN PRIVATE KEY-----` trong mã nguồn, ticket hoặc log.
- Không chấp nhận certificate có hostname không khớp DNS chỉ bằng cách gọi IP khác không nằm trong SAN.
- Không nhầm TLS certificate hết hạn với password/user bị từ chối; xem exception chain, cert validity và network.

Nguồn: [Couchbase Java SDK — Authentication](https://docs.couchbase.com/java-sdk/current/howtos/sdk-authentication.html), [Couchbase Server — Configure Client Certificates](https://docs.couchbase.com/server/current/manage/manage-security/configure-client-certificates.html), [Spring Boot — Couchbase](https://docs.spring.io/spring-boot/reference/data/nosql.html).

## 9. Phân tách bí mật theo vai trò và môi trường

Thiết kế least privilege cho các danh tính:

| Account/secret | Nơi được phép tồn tại | Quyền trong Couchbase | Không nên có |
| --- | --- | --- | --- |
| `orders-api-local` | Máy dev/lab secret store | Chỉ các KV/SQL++ operations cần cho `training.commerce.orders` | Full Admin trong app |
| `orders-api-staging` | Staging secret namespace | App data permissions trên bucket staging | Prod bucket hoặc credentials |
| `orders-api-prod` | Production vault và pods runtime được phép | KV Data Reader/Writer, Query Select khi cần, đúng collection | User Admin, Manage Index, Bucket Admin |
| `orders-migrator-prod` | Migration job có approval | Schema/index DDL trên resource được duyệt | Mount thường trực vào API pods |
| `security-operator` | System quản trị danh tính có audit | Quản lý users/roles theo nhiệm vụ | Dùng như password fallback của API |
| `client-key-orders-prod` | Secret store/HSM, workload TLS auth tương ứng | Chỉ danh tính X.509 của service này | Chia sẻ private key giữa nhiều service/cluster |

**Cấp quyền DB là bước khác với lưu trữ secret**. Secret manager có thể cấp một password đúng, nhưng user vẫn cần RBAC đúng thao tác và collection. Trên Enterprise/Capella, tách `data_reader`/`data_writer` (KV) khỏi `query_select` (SQL++); index provisioning cần quyền khác. Community Edition có tập role hạn chế, không dùng admin như workaround cho ứng dụng production.

### 9.1. Tại sao `_class` và metadata không phải secret?

Spring Data Couchbase có thể ghi metadata loại entity (`_class`), document ID, CAS/`@Version` và expiry. Chúng **không phải password hay TLS certificate**; nhưng document body và metadata có thể chứa PII, session tokens hoặc thông tin nghiệp vụ nhạy cảm. Đừng dump raw JSON chỉ để debug secret config. Trong session collection, token/refresh token nếu được lưu là **dữ liệu bí mật cần bảo vệ**; TTL không thay mã hóa/authorization và không ngăn đọc trước khi hết hạn.

### 9.2. Connection không tạo ra quyền nâng cao

Kết nối thành công với `couchbases://` không chứng minh user có thể chạy `findByStatus`, `@Query`, mutation với CAS, transaction hoặc SQL++ query qua Index Service. TLS xác minh Server và bảo vệ giao tiếp; RBAC quyết định operation được phép; index, consistency và topology quyết định đúng semantics/performance.

## 10. Xoay password mà không dùng chung tài khoản Administrator

Đổi password trên cluster là **một thay đổi phân phối secret**. Người vận hành phải biết **ai đang dùng secret cũ** và liệu client có cần tạo lại connection. Chỉ sửa một biến môi trường ở deployment không bảo đảm mọi Java SDK `Cluster` đang sống sẽ tự authenticate bằng giá trị mới.

### 10.1. Mô hình hai credentials A → B

Khi môi trường cho phép tạo hai account/credential ứng dụng với quyền tương đương:

```mermaid
flowchart LR
    A["A: credential hiện hữu"]
    B["Provision B: secret mới và RBAC hẹp"]
    V["Canary kiểm chứng KV/SQL++ và DENY admin"]
    D["Rollout workloads sang B"]
    I["Inventory consumers còn dùng A"]
    R["Thu hồi A + audit"]
    A --> B --> V --> D --> I --> R
```

**Quy trình có kiểm soát:**

1. **Lập danh sách consumers của A:** API pods, batch jobs, cronjobs, CI jobs, automation và môi trường nào có thể đang sử dụng cùng credential. Ghi owner, TTL và đầu mối liên hệ.
2. **Tạo B:** secret ngẫu nhiên mạnh, không reuse password; cấp role giới hạn ở đúng bucket/scope/collection như yêu cầu hiện tại. Nếu A đang có role quá rộng, thiết kế B với quyền **thật sự cần**, không copy nguyên quyền admin vô điều kiện.
3. **Cấp secret B** trong vault/secret manager cho workload được phép. Không gửi giá trị qua chat hoặc shell history. Có thể dùng version/alias secret để điều phối việc rollout.
4. **Canary:** khởi động một instance với B; thử `get(id)`, SQL++ `SELECT` khi cần và negative test trên collection khác. Không ghi document production chỉ để test secret.
5. **Rollout:** thay secret reference hoặc deployment revision, khởi động lại connection/process theo cơ chế đã thử nghiệm; quan sát authentication failures, latency, error rate và readiness.
6. **Kiểm tra mọi consumer:** đừng thu hồi A chỉ vì 12 API pods đã chuyển, trong khi job chạy hằng tuần còn dùng A.
7. **Revoke/Delete A:** khi không còn consumer hợp lệ hoặc theo quyết định ứng phó sự cố; xác minh A không authenticate được, B vẫn hoạt động và lưu audit.

**Khi không thể có hai credentials cùng lúc:** lập kế hoạch password change trực tiếp, phối hợp rollout và dự đoán khoảng gián đoạn. Với **Capella**, thay password Cluster Access Credentials yêu cầu **cập nhật ứng dụng** dùng secret mới; xóa credential có thể làm ứng dụng ngừng hoạt động. Đừng khẳng định zero downtime nếu chưa có canary, rollback và cơ chế phối hợp phía client.

### 10.2. Rotation trong secret manager có đồng nghĩa connection tự cập nhật?

Không. Một secret được rotate trong Vault/Cloud Secret Manager/Kubernetes Secret **không tự buộc** Couchbase Java SDK đang mở kết nối đọc lại password. Tương tự, một Spring Boot `@ConfigurationProperties` bind lúc startup có thể giữ giá trị ban đầu. Cần kiểm tra thực tế cách:

- Secret volume/env được cập nhật hay tạo một deployment revision mới.
- Application đọc lại giá trị ở thời điểm nào.
- `Cluster`/SDK connection pool được tái xác thực, tái tạo hoặc restart theo lifecycle nào.
- Quá trình chuyển đổi có ảnh hưởng background workers và in-flight requests/transactions hay không.

Không tự tạo `Cluster.connect(...)` cho **mỗi request** nhằm "luôn lấy mật khẩu mới": điều đó phá lợi ích connection pooling và có thể tăng tải/timeout. Thay thế theo **rollout có kiểm soát** là hướng an toàn thường gặp.

### 10.3. Credential động và thời hạn ngắn

Một số tổ chức dùng **Vault** hoặc secret provider hỗ trợ cấp credential động có TTL. Couchbase Capella có tài liệu về tích hợp **HashiCorp Vault** để quản lý credentials và có thể tạo credential ngắn hạn. Nếu áp dụng:

- Phân biệt **TTL của database credential** với **TTL của document Couchbase**; chúng hoàn toàn khác nhau.
- Thiết kế renew/revoke của secret lease và thời gian cập nhật client.
- Không để một transaction dài vượt thời hạn credential mà không có kế hoạch recovery.
- Chỉ cấp Vault policy cho đúng service identity và cluster, không đưa Vault root token vào container.

Nguồn: [Capella — Manage Cluster Access Credentials](https://docs.couchbase.com/cloud/clusters/manage-database-users.html), [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html).

## 11. Xoay certificate và trust chain

Certificate có **notBefore/notAfter**, issuer, chain, key usage, SAN/hostname và fingerprint. Khi CA hoặc Server certificate thay đổi, client có thể ngừng kết nối nếu truststore chưa cập nhật, dù username/password vẫn đúng. Phải lập kế hoạch trước khi certificate hết hạn hoặc sau khi nghi ngờ khóa riêng bị xâm nhập.

### 11.1. Thứ tự xử lý khi đổi CA

Nếu tổ chức **chủ động đổi CA** cho Couchbase Server self-managed, một quy trình có thể là:

1. **Inventory** các node, hostname/SAN, certificate chains, ứng dụng kết nối, truststores và JVM versions; xác minh CA mới được phê duyệt.
2. **Chuẩn bị trust ở client** chứa **CA cũ + CA mới** trong giai đoạn overlap, nếu chính sách và công nghệ cho phép. Rollout client trỏ tới truststore mới trước khi Server cắt sang certificate chỉ ký bởi CA mới.
3. **Cập nhật Server/node certificates** theo trình tự được Couchbase hỗ trợ; xác minh node-to-node trust, DNS/SAN, cổng TLS và trạng thái cluster.
4. **Thử app canary:** TLS handshake, KV read, SQL++ SELECT, các node/port thực được SDK truy cập. Không chỉ thử Web Console HTTPS.
5. **Quan sát và rollout** toàn bộ workloads, including batch/cron và các môi trường chạy Java JDK/truststore riêng.
6. **Gỡ CA cũ** khỏi truststores khi chắc không còn chứng chỉ hợp lệ phụ thuộc vào nó và thời hạn rollback đã kết thúc. Ghi lại ngày hết hạn, fingerprint, owner và change record.

**Nếu private key hoặc CA đã bị lộ:** quy trình khác rotation thông thường; có thể phải **thu hồi trust ngay**, phát hành keypair/certificate mới và chấp nhận gián đoạn nhằm hạn chế nguy cơ. Không kéo dài overlap với một CA đã bị xâm nhập chỉ để tránh downtime.

### 11.2. Xoay client certificate/private key

Với xác thực bằng client X.509:

- Tạo **keypair mới** trong secret manager/HSM; không reuse private key cũ.
- Cấp client certificate mới với identity/issuer/extension mà Couchbase Server đã cấu hình tin cậy và map đến user có RBAC đúng.
- Đưa `client.crt` và `client.key` phiên bản mới tới canary; kiểm tra server trust client identity trước khi rollout.
- Khi tất cả workload dùng key mới, vô hiệu hóa/thu hồi key và certificate cũ theo chính sách certificate management.
- Đảm bảo files private key có quyền đọc tối thiểu và không xuất hiện trong Docker image, configmaps, logs, snapshots công khai.

**Không trộn nhầm:** `client.key` không phải `ca.pem` và không được đưa vào `truststore.certificate`. Nếu chỉ cần TLS + password, **không phải** tự tạo client cert/key cho mọi service.

### 11.3. Lệnh kiểm tra thông tin CA public, không in private key

Nếu có `openssl` và một public CA certificate được cấp theo đường tin cậy:

```bash
openssl x509 \
  -in /etc/certs/couchbase/ca.pem \
  -noout -subject -issuer -dates -fingerprint -sha256
```

Lệnh này chỉ in **metadata của public certificate**. So sánh SHA-256 fingerprint với giá trị được phê duyệt qua **kênh độc lập** (platform/security team). Một fingerprint tự tính từ file tải về **không chứng minh** file ấy là CA thật nếu chưa có nguồn đối chiếu đáng tin.

**Đừng dùng `openssl rsa -text` hoặc in private key** để debug trên log/ticket; làm vậy có thể lộ khóa riêng. Certificate chain phải được xác minh trong TLS handshake thực tế với hostname, truststore và SDK đang dùng. Cần cảnh báo hết hạn trước khi thời điểm `notAfter` tới.

Nguồn: [Couchbase Server — Configure Server Certificates](https://docs.couchbase.com/server/current/manage/manage-security/configure-server-certificates.html), [Certificate Management API](https://docs.couchbase.com/server/current/rest-api/rest-certificate-management.html), [Couchbase Server — Certificates](https://docs.couchbase.com/server/current/learn/security/certificates.html).

## 12. Test kết nối bằng credential thật nhưng không in secret

Một bài kiểm tra cấu hình bí mật phải xác nhận rằng **Spring Boot thực sự đọc được secret và Java SDK sử dụng chúng**, không phải chỉ có biến môi trường. Đồng thời phép thử nên **read-only** và không làm lộ tên, dữ liệu hoặc password.

### 12.1. Xác minh môi trường trước khi tạo connection

Kiểm tra:

- Application profile đang bật là `local`, `test`, `staging` hoặc `prod` đúng deployment contract.
- Biến/secret volume tồn tại, permission đủ đọc, không mount nhầm namespace/cluster.
- `CB_APP_USERNAME` **không phải Administrator**; bí mật provisioning/admin không được đưa vào runtime.
- Capella dùng `couchbases://` và đúng hostname từ Console; private/public endpoint và egress IP policy đúng.
- Nếu cấu hình CA riêng, file path/tên bundle khớp nhau, certificate còn hạn và có thể được tin cậy.
- Bucket/scope/collection được provision, RBAC data/query phù hợp; index online khi dùng derived query.

**Không bao giờ log** `spring.couchbase.password`, `CB_APP_PASSWORD`, `CB_CLIENT_KEYSTORE_PASSWORD` hoặc nội dung raw secret files. Log chỉ kết quả kiểm tra **có/không**, loại môi trường đã được phê duyệt và mã lỗi đã redact.

### 12.2. Java SDK qua Spring Boot: KV read-only

Ví dụ test dùng `@SpringBootTest` khi ứng dụng đã có starter Couchbase; thông tin `Cluster` được Spring Boot auto-configure. Fixture `order::demo-1001` phải tồn tại trong `training.commerce.orders` **trên môi trường lab/test dành riêng**.

```java
package com.example.orders;

import com.couchbase.client.java.Cluster;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class CouchbaseSecretConfigIT {

    @Autowired
    Cluster cluster;

    @Value("${spring.data.couchbase.bucket-name}")
    String bucketName;

    @Test
    void canReadSeedWithoutLoggingCredentials() {
        // Chỉ chạy trên bucket test được provision theo policy.
        assertEquals("it_orders", bucketName);
        var bucket = cluster.bucket(bucketName);
        bucket.waitUntilReady(Duration.ofSeconds(30));

        var orders = bucket.scope("commerce").collection("orders");
        var result = orders.get("order::it-1001");
        assertEquals("NEW", result.contentAsObject().getString("status"));
    }
}
```

**Quan trọng:** Test trên dùng `@ActiveProfiles("test")` và kỳ vọng bucket `it_orders` với fixture `order::it-1001`. Cần provision fixture trước; nếu test fail vì không có key, chưa đủ để kết luận mật khẩu sai. Cần xem cause thật (network, TLS, authentication, RBAC, seed). Không chuyển test sang production chỉ để "dễ có dữ liệu".

### 12.3. SQL++ read-only để phân biệt role

Nếu account test có **Query Select** trên `it_orders.commerce.orders`, có thể thêm một test trong cùng class:

```java
@Test
void canQueryByIdWithoutRequiringAnIndex() {
    var result = cluster.query(
        "SELECT META(o).id AS docId, o.status " +
        "FROM `it_orders`.`commerce`.`orders` AS o " +
        "USE KEYS $id",
        com.couchbase.client.java.query.QueryOptions.queryOptions()
            .parameters(
                com.couchbase.client.java.json.JsonObject.create()
                    .put("id", "order::it-1001")
            )
    );
    assertEquals(1, result.rowsAsObject().size());
}
```

Đây là **đoạn method** để thêm vào class `CouchbaseSecretConfigIT` đã có import `@Test` và `assertEquals`, không phải class độc lập. `USE KEYS` không cần secondary index, phù hợp tách **Query connectivity + authentication/authorization** khỏi tình trạng index. Nếu repo dùng `findByStatus`, cần thêm index/`EXPLAIN` và test query thực theo metadata Spring Data.

**Kết quả PASS chỉ cho các thao tác đã test**: không chứng minh credential có quyền ghi, transaction metadata collection, client-certificate auth hoặc khả năng chịu lỗi. Với quyền hạn chế, cần negative test xác nhận account **không** thể truy cập collection khác và không quản trị index/user. Kiểm thử denial phải phân biệt 403 authorization với `DocumentNotFound`/timeout.

### 12.4. Kiểm thử certificate rotation trên canary

Sau thay CA hoặc client certificate:

1. Canary load secret bundle version mới và khởi tạo connection.
2. Kiểm tra TLS handshake thành công, certificate/SAN đúng tên miền được dùng.
3. KV `get/exists` thành công trên fixture hợp lệ.
4. SQL++ `SELECT ... USE KEYS` thành công nếu app có Query Select.
5. Kiểm tra client không vô tình trust một CA ngoài danh sách được duyệt.
6. Rollout cùng cơ chế cho app/batch jobs; chỉ gỡ CA/key cũ khi chính sách cho phép.

**Không dùng `curl -k`, `openssl s_client -verify 0` hoặc trust-all code làm tiêu chí PASS.** Chúng có thể khiến kết nối "thành công" bằng cách bỏ qua kiểm tra bạn đang cần chứng minh.

## 13. Chẩn đoán sự cố secret, kết nối và chứng chỉ

| Triệu chứng | Nguyên nhân có thể | Cách xử lý đúng |
| --- | --- | --- |
| App không khởi động vì `CB_APP_PASSWORD` chưa có | Secret chưa được inject, profile sai, configtree path không tồn tại | Kiểm tra secret provider/mount và effective property **không in giá trị**; FAIL sớm thay vì thêm password mặc định |
| Secret file tồn tại nhưng Spring báo missing password | Tên file không phải `spring.couchbase.password`, import path sai, precedence xung đột | Kiểm tra `spring.config.import`, filename, mountPath, profile và quyền đọc |
| `AuthenticationFailureException` ngay sau rotation | App instance/batch job còn dùng A, B chưa provision/role sai | Inventory consumers, secret version và rollout; xác minh bằng canary credential mới |
| Capella kết nối bằng `couchbase://` bị lỗi | Scheme không TLS hoặc endpoint không phù hợp | Dùng `couchbases://` do Capella Connect cung cấp |
| `SSLHandshakeException` do certificate unknown | CA không nằm trong truststore, bundle không được load, certificate chain thiếu | Xác minh CA nguồn, mount/truststore/SSL bundle, server certificate chain |
| TLS hostname mismatch | Kết nối bằng IP/alias không có trong SAN, Docker advertise hostname khác | Dùng DNS hostname phù hợp certificate và sửa topology/alternate addresses đúng thiết kế |
| Certificate hết hạn | Server/client certificate vượt `notAfter` | Lập kế hoạch cấp certificate/keypair mới và rollout; không tắt validation |
| Chuyển CA Server rồi client không kết nối | Client chưa trust CA mới hoặc đã gỡ CA cũ quá sớm | Chuẩn bị trust overlap theo policy, canary và rollout đúng thứ tự |
| Java SDK có TLS nhưng `findByStatus` trả 403 | User không có Query Select, query truy cập collection khác | Kiểm tra RBAC/statement thực; TLS không cấp Query role |
| KV hoạt động nhưng SQL++ timeout | Query Service/port 8093 hoặc 18093/network không đến được, hoặc Query Service quá tải | Kiểm tra service endpoints, firewall, topology; không suy password sai |
| `DocumentNotFoundException` khi smoke test | Fixture sai ID, collection khác, TTL hết hạn | Kiểm tra seed bằng provisioner; không coi là lỗi certificate |
| Đọc được secret trong `docker compose config` | Compose đã nội suy biến env, CI log quá rộng | Ngừng log cấu hình giải mã, rà soát quyền log, rotate nếu đã lộ |
| Key bị lộ qua image hoặc Git | Secret nằm trong layer/history/revision | Revoke/rotate ngay, review truy cập; dọn nguồn/lịch sử theo quy trình |
| Basic password auth và client certificate cùng cấu hình mâu thuẫn | Trộn hai mô hình authentication mà không xác định mode | Chọn phương thức Server hỗ trợ, cấu hình Boot phù hợp và test identity/RBAC |
| CA truststore có nhưng Query node thứ hai lỗi | Node certificate/SAN/chain không đồng nhất, node address SDK khám phá khác | Kiểm tra tất cả service nodes, SAN/CA và endpoints thực; không chỉ test bootstrap |
| Store password đúng nhưng app vẫn không đọc được file `.p12` | File permissions, path, định dạng/alias sai | Kiểm tra mount, process uid, format, truststore vs keystore và Boot version |
| Transaction thất bại dù KV GET PASS | Chưa cấp quyền Query/ATR metadata, topology/durability không phù hợp | Tách lỗi quyền/tính năng, không tăng quyền Admin hay tắt TLS |

### 13.1. Quy trình điều tra sáu bước

1. **Đúng runtime?** Xác nhận active Spring profile, namespace, cluster alias và bucket nhưng không log secret/URI có thông tin nhạy cảm.
2. **Đúng đường mạng?** DNS, advertised node addresses, Docker NAT, TCP/TLS ports, Capella Allowed IP của public egress thực.
3. **Đúng TLS?** `couchbases://` khi cần, CA chain, hostname/SAN, certificate expiry, truststore/bundle và version SDK.
4. **Đúng authentication?** Runtime identity là app user hay client certificate identity, secret version mới hay cũ; không dùng admin để thử thay.
5. **Đúng authorization/resource?** KV Data Reader/Writer, SQL++ Query Select, đúng bucket/scope/collection, Index Service/index online khi truy vấn theo thuộc tính.
6. **Đúng fixture/semantics?** Document ID, expiry, CAS, `_class` metadata, scan consistency và transaction metadata collection.

**Kỷ luật:** Giữ mã lỗi, timestamp, SDK/Server version và context **đã redact**. Một kết nối thành công với Administrator không chứng minh secret ứng dụng đúng; một `SELECT` thành công bằng admin không chứng minh Query Select trên user runtime.

## 14. Khi secret hoặc private key có thể bị rò rỉ

Rotation định kỳ có thể có thời gian overlap. **Incident do lộ secret/khóa riêng** đòi hỏi phản ứng ưu tiên containment:

1. **Kích hoạt quy trình incident:** Xác định giá trị nào bị lộ (password app/admin, Vault token, truststore password, client private key hay Server private key), môi trường và quyền hiệu lực. Không copy lại secret vào ticket.
2. **Thu hồi hoặc thay thế credential nhanh chóng** theo quyền của security/on-call, phối hợp gián đoạn có thể xảy ra. Với admin credential hoặc CA private key, ưu tiên containment do blast radius cao.
3. **Giảm phạm vi truy cập:** Giới hạn network, xóa vai trò rộng không cần thiết, vô hiệu credential bị lộ và triển khai secret/keypair mới.
4. **Audit:** Xem authentication attempts, role/user changes, bucket/index management và dữ liệu nhạy cảm có thể bị truy cập theo log có sẵn; đừng giả định audit tự ghi mọi KV GET nếu chưa bật cơ chế phù hợp.
5. **Xử lý nguồn rò rỉ:** Dọn secret trong CI config, log, container layers, Git history, snapshot và máy dev theo chính sách. **Xóa plaintext ở commit hiện tại không làm secret đã từng public trở nên an toàn**.
6. **Kiểm chứng phục hồi:** Canary B/CA mới/mTLS key mới thành công, secret cũ không dùng được, no additional permissions, giám sát không còn login bất thường.
7. **Rút kinh nghiệm:** Bổ sung secret scanning, pre-commit/CI policies, ownership và expire/rotation schedules.

### 14.1. Mỗi loại lộ lọt có biện pháp khác nhau

| Vật liệu bị lộ | Mức độ ảnh hưởng | Phản ứng chính |
| --- | --- | --- |
| Password ứng dụng | Truy cập trong phạm vi RBAC của user | Revoke/rotate user secret, review operations và data access |
| Admin/provisioner credential | Có thể thay role/schema/cluster, phạm vi rộng | Incident ưu tiên cao, đổi secret/role, audit admin actions |
| Client private key | Có thể mạo danh client certificate identity khi Server tin CA/map user | Revoke cert/identity, tạo keypair mới, review server trust/roles |
| Server private key | Có thể mạo danh Server nếu điều kiện network/trust bị khai thác | Phát hành cert/key mới, phối hợp Trust/CA và TLS migration |
| CA private signing key | Có thể ký chứng chỉ giả cho nhiều hệ thống tin CA đó | Thay trust anchor, revoke CA theo policy, triển khai rotation khẩn cấp |
| Public CA certificate | Thông thường không cấp quyền mạo danh nếu **không có private key** | Kiểm tra toàn vẹn/nguồn nếu file bị thay, không coi chỉ việc lộ public CA là lộ secret |

## 15. Bài tập thực hành và câu hỏi tình huống

### Bài 1 — Phân loại bí mật

Bạn có bốn tệp `ca.pem`, `orders-client.key`, `orders-client.crt` và `application-prod.yml` chứa `CB_APP_PASSWORD` bằng plaintext. Tệp nào là bí mật và bạn phải làm gì?

**Đáp án gợi ý:** `orders-client.key` là private key, phải ở secret store/HSM hoặc mount bảo vệ; password trong YAML là secret và cần rotate nếu đã commit/lộ. `ca.pem` và `orders-client.crt` là public certificates, nhưng phải kiểm tra nguồn/integrity. Đưa password vào secret manager và chỉ để placeholder trong `application-prod.yml`.

### Bài 2 — Vì sao TLS chưa đủ?

Một ứng dụng kết nối Capella bằng `couchbases://`, TLS handshake thành công nhưng `findByStatus("NEW")` bị từ chối quyền. Có nên cấp trust CA mới?

**Đáp án gợi ý:** Chưa có bằng chứng lỗi certificate. TLS đã thành công; kiểm tra Query Select trên collection đích, Query Service, query generated by Spring Data và index. CA không cấp quyền SQL++.

### Bài 3 — Secret trong Docker Compose

Developer tạo `./local-private/couchbase-password.txt` và khai báo `secrets: file:` trong Compose. Anh ấy nói rằng vì tên là "Docker Secret", file nguồn đã được mã hóa hoàn toàn, có thể commit lên Git.

**Đáp án gợi ý:** Sai. Với Compose file-backed secrets trên dev host, file nguồn vẫn là plaintext. Phải `.gitignore`, giới hạn ACL và không log `docker compose config`. Production dùng secret manager/hệ thống cấp secret được kiểm soát.

### Bài 4 — Kubernetes Secret là base64

Một CI job lưu toàn bộ manifest `kind: Secret` trong repo với field `data` base64. Nhóm cho rằng mã hóa đã an toàn. Nhận định đúng không?

**Đáp án gợi ý:** Base64 là **encoding**, không phải encryption. Cần bảo vệ Secret source, etcd encryption-at-rest, RBAC/namespace, CI IAM, secret manager/CSI và quyền mount; không commit manifest chứa giá trị thật lên repo dùng chung.

### Bài 5 — Capella có cần tải root cert về mọi máy?

Nhóm ứng dụng Java SDK 3.x được hỗ trợ đang dùng `couchbases://` chuẩn Capella nhưng định tải certificate công khai bằng tay rồi cấu hình custom truststore cho mọi pod.

**Đáp án gợi ý:** Java SDK hiện đại đã tin cậy root cert Capella tiêu chuẩn; thông thường không cần truststore riêng. Chỉ dùng certificate từ Capella UI khi có yêu cầu đặc biệt/non-SDK client hoặc lỗi trust thực, đồng thời kiểm tra đừng override mất bundled CA.

### Bài 6 — Đổi password trong secret manager

Secret manager đã cập nhật `CB_APP_PASSWORD` phiên bản mới, nhưng các pods Spring Boot vẫn xác thực bằng mật khẩu cũ. Có phải secret manager hoạt động sai?

**Đáp án gợi ý:** Không nhất thiết. Secret store đã cập nhật nhưng process/JVM/Spring Environment/SDK có thể giữ giá trị lúc khởi tạo; env var cũng thường không tự cập nhật trong container đang chạy. Dùng rollout/new connection lifecycle theo runbook và quan sát authentication failures.

### Bài 7 — Xoay CA theo thứ tự nào?

Cluster tự quản lý chuẩn bị đổi root CA. Nhóm vận hành thay certificate Server chỉ ký bằng CA mới rồi hôm sau mới cập nhật truststore client. Rủi ro gì?

**Đáp án gợi ý:** Ứng dụng có thể mất TLS handshake trong khoảng chênh lệch. Với rotation bình thường, chuẩn bị trust CA mới (và CA cũ nếu policy cho phép) ở client trước, sau đó đổi Server certificate, canary, rồi gỡ CA cũ khi an toàn. Nếu CA cũ bị lộ private key thì phải thay đổi quy trình để thu hồi nhanh, chấp nhận gián đoạn có kiểm soát.

### Bài 8 — mTLS khác truststore

Bạn đặt `ca.pem` vào `spring.couchbase.authentication.pem.private-key` và đặt `client.key` vào `truststore.certificate`, nhưng handshake fail. Sai ở đâu?

**Đáp án gợi ý:** `ca.pem` là public CA trust, không phải client private key; `client.key` là secret chứng minh danh tính, không phải public CA. Nếu Server yêu cầu client certificate auth, cần client.crt + client.key phù hợp, còn truststore phải chứa public CA Server đáng tin. Với TLS + password đơn thuần không nhất thiết cần client cert.

### Bài 9 — Chứng chỉ đúng CA nhưng sai hostname

Ứng dụng kết nối `couchbases://10.10.20.5`; Server trả certificate có SAN `cb.internal.example`, được ký bởi CA nội bộ đã tin. Có thể bỏ qua hostname verification để chạy ngay?

**Đáp án gợi ý:** Không. Dùng DNS hostname phù hợp SAN hoặc cấp certificate/advertised address chính xác cho topology; trust CA chỉ xác minh chuỗi ký, không làm IP tự khớp hostname. Không tắt verification.

### Bài 10 — Code khởi động bằng Administrator

Service thiếu `CB_APP_PASSWORD`, nên người viết thêm logic fallback sang admin credential từ biến `CB_ADMIN_PASSWORD`. Hệ quả?

**Đáp án gợi ý:** Đây là privilege escalation đường mặc định nguy hiểm. Cấu hình thiếu phải làm startup fail, báo tình trạng credential (không in secret), và operator sửa secret distribution. Account admin/provisioner không được mount vào API runtime.

### Bài 11 — Secret tốt nhưng pipeline vẫn nguy hiểm

CI có `CB_APP_PASSWORD` production trong secret store, nhưng integration test có thể chạy lệnh `UPSERT` vào `orders_prod` và job in toàn bộ `env` khi gặp lỗi. Cần sửa ở đâu?

**Đáp án gợi ý:** Tách credential/network của test để **không thể** chạm production; dùng `CB_IT_*` và bucket/cluster cô lập; cấm log full env, redact outputs và chỉ dùng read-only smoke khi cần production. Secret manager **không thay thế** RBAC và isolation.

## 16. Checklist GO / NO-GO trước khi phát hành

### Cấu hình và phân phối secret

- [ ] Không có password, API token, client private key, keystore password trong Git/JAR/image/CI log/ticket.
- [ ] Application, migrator và admin dùng credentials khác nhau, môi trường local/test/staging/prod tách biệt.
- [ ] Spring Boot dùng placeholders hoặc configtree/secret provider đã chọn rõ ràng, **không** default admin password.
- [ ] Secret volume có mount path, filename, permissions, owner và lifecycle được xác nhận.
- [ ] Secret provider chỉ cấp quyền đọc cho workload identity thực sự cần.
- [ ] `.env`, files mật khẩu local và debug dumps bị loại khỏi Git và backup/sync công khai.
- [ ] Có cơ chế rà quét secret ở pre-commit/CI và quy trình xử lý false positives/historical leaks.

### TLS và chứng chỉ

- [ ] Capella dùng `couchbases://` từ Connect → SDK, DNS SRV, TLS và Allowed IP/public egress đúng.
- [ ] Self-managed có TLS khi yêu cầu; certificate chain đáng tin, hostname/SAN hợp lệ.
- [ ] Với Java SDK Capella tiêu chuẩn, không thêm custom truststore vô cớ.
- [ ] Nếu CA riêng, SSL bundle/truststore và path được xác nhận, certificate chưa hết hạn.
- [ ] Client certificate/private key chỉ có khi Server cấu hình X.509 auth; file private key không nằm trong image.
- [ ] Không có trust-all, bỏ hostname verification hoặc `curl -k` làm đường kết nối production.
- [ ] Có lịch theo dõi hạn certificate và runbook xoay CA/keypair theo đúng thứ tự.

### Kiểm thử và vận hành

- [ ] Smoke test **KV** bằng user runtime thành công trên môi trường được phép.
- [ ] Smoke test **SQL++** riêng thành công nếu app dùng repository query; Index Service/index được kiểm tra khi cần.
- [ ] Negative test xác nhận user runtime không có quyền admin/index DDL/collection ngoài phạm vi.
- [ ] Application logs, Actuator và error diagnostics không lộ secret hoặc dữ liệu nhạy cảm.
- [ ] Có inventory consumer, version secret, owner và quy trình xoay A → B; xác minh revoke credential cũ.
- [ ] Đã thử restart/rollout `Cluster` khi đổi password/trust; không giả định file thay đổi là SDK tự reload.
- [ ] Test/CI không thể mutate production bằng credentials hoặc network production.
- [ ] Có incident response nếu lộ password, client private key hoặc CA/server signing key.

**GO** khi credentials và trust material được cấp đúng từ nguồn bảo vệ, TLS/RBAC/kv/query tests đạt theo nhu cầu, và đội vận hành có thể xoay/thu hồi bí mật mà không dựa vào tài khoản quản trị trong app. **NO-GO** khi production có password hardcode, dùng `Administrator`, bỏ TLS validation, hoặc secret manager có giá trị nhưng không ai biết process nào đang giữ secret phiên bản cũ.

## 17. Tài liệu chính thức để tra cứu

1. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
2. [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html).
3. [Spring Boot — SSL Bundles (PEM/JKS)](https://docs.spring.io/spring-boot/reference/features/ssl.html).
4. [Spring Boot — Working with Couchbase](https://docs.spring.io/spring-boot/reference/data/nosql.html).
5. [Couchbase Java SDK — Managing Connections / TLS](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html).
6. [Couchbase Java SDK — Authentication / Certificates](https://docs.couchbase.com/java-sdk/current/howtos/sdk-authentication.html).
7. [Couchbase Java SDK — Client Settings](https://docs.couchbase.com/java-sdk/current/ref/client-settings.html).
8. [Couchbase Server — Certificates](https://docs.couchbase.com/server/current/learn/security/certificates.html).
9. [Couchbase Server — Configure Server Certificates](https://docs.couchbase.com/server/current/manage/manage-security/configure-server-certificates.html).
10. [Couchbase Server — Configure Client Certificates](https://docs.couchbase.com/server/current/manage/manage-security/configure-client-certificates.html).
11. [Couchbase Server — Certificate Management REST API](https://docs.couchbase.com/server/current/rest-api/rest-certificate-management.html).
12. [Couchbase Capella — Connect to Your Cluster](https://docs.couchbase.com/cloud/get-started/connect.html).
13. [Couchbase Capella — Root Certificates](https://docs.couchbase.com/cloud/security/security-certificates.html).
14. [Couchbase Capella — Cluster Access Credentials / Rotation](https://docs.couchbase.com/cloud/clusters/manage-database-users.html).
15. [Couchbase Capella — Allowed IP Addresses](https://docs.couchbase.com/cloud/clusters/allow-ip-address.html).
16. [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
17. [Spring Data Couchbase — Repository Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html).
18. [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html).

## Tổng kết

**Quản lý mật khẩu, chuỗi kết nối và chứng chỉ bằng cấu hình bí mật** không chỉ là thay password cứng trong YAML bằng một biến môi trường. Thiết kế đúng cần phân loại secret/trust material, đưa bí mật vào secret provider phù hợp, tách quyền ứng dụng và quản trị, bảo đảm TLS/hostname/CA được xác minh, và có cơ chế cập nhật SDK khi rotation.

Khi hoàn thành, Spring Data Couchbase có thể dùng cùng mã cho Docker local, test và Capella; `CouchbaseRepository`, `CouchbaseTemplate`, truy vấn SQL++, CAS/TTL, giao dịch và reactive vẫn tuân thủ quyền dữ liệu theo RBAC **mà không buộc tiết lộ password hoặc private key** trong repository, build artifact hay log.
