# Đóng gói cấu hình theo môi trường và phân tách bí mật

Một ứng dụng Spring Cloud thường chạy ở nhiều môi trường như local, test, staging và production. Mỗi môi trường có endpoint, giới hạn tài nguyên, feature flag và thông tin kết nối khác nhau. Nếu tạo một bản build riêng cho từng môi trường hoặc đặt mật khẩu trực tiếp trong file cấu hình đóng gói, việc phát hành và kiểm soát bảo mật sẽ trở nên khó khăn.

Cách tiếp cận phù hợp là **build một artifact bất biến và cấp cấu hình từ bên ngoài khi triển khai**. Các giá trị không nhạy cảm có thể được tổ chức theo profile, file cấu hình ngoài hoặc Spring Cloud Config. Password, token, private key và credential nên được cấp từ secret manager hoặc kho bí mật của nền tảng triển khai, với quyền truy cập riêng cho từng workload.

Spring Boot cung cấp Config Data, profile, biến môi trường và configuration tree để hợp nhất các nguồn cấu hình vào Environment. Spring Cloud Config bổ sung kho cấu hình tập trung theo application, profile và label. Spring Cloud Vault có thể đưa secret từ Vault vào Environment qua Config Data API. Các cơ chế này phối hợp được với nhau, nhưng mỗi cơ chế có trách nhiệm riêng.

Bài học thuộc chương **Vận hành** của module **SPRING_CLOUD_CORE**. Người học sẽ thiết kế cách đóng gói cấu hình cho nhiều môi trường, tách dữ liệu công khai khỏi secret, lựa chọn nguồn cấu hình phù hợp, kiểm soát thứ tự ưu tiên và kiểm thử quá trình triển khai.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích nguyên tắc một artifact triển khai cho nhiều môi trường.
2. Phân loại cấu hình mặc định, cấu hình theo môi trường và dữ liệu bí mật.
3. Dùng Spring profile và Config Data để nạp cấu hình theo môi trường.
4. Đưa cấu hình bên ngoài JAR bằng file, biến môi trường hoặc configuration tree.
5. Dùng Spring Cloud Config theo application, profile và label.
6. Dùng Spring Cloud Vault hoặc secret manager để cung cấp credential.
7. Phân biệt ConfigMap với Secret và hiểu giới hạn của mã hóa Base64.
8. Kiểm soát PropertySource precedence và tránh fallback secret không an toàn.
9. Bind cấu hình có kiểu bằng ConfigurationProperties và validation.
10. Thiết kế pipeline promotion, rollback, rotation và kiểm thử cấu hình.
11. Bảo vệ secret trong repository, container image, log, Actuator và runtime.
12. Chẩn đoán lỗi do profile, Config Server, Vault hoặc secret mount không đúng.

## 2. Nguyên tắc: một artifact, nhiều môi trường

### 2.1. Không build lại chỉ để đổi endpoint

Giả sử cùng một dịch vụ Orders cần chạy ở ba môi trường:

| Thuộc tính | Development | Staging | Production |
| --- | --- | --- | --- |
| API inventory | inventory-dev.internal | inventory-stg.internal | inventory.internal |
| Log level | DEBUG | INFO | WARN |
| Số kết nối tối đa | 5 | 10 | 40 |
| Feature thử nghiệm | Có thể bật | Kiểm tra có kiểm soát | Theo phê duyệt |
| Database credential | Credential dev | Credential staging | Credential production |

Mã nguồn và artifact thực thi không cần thay đổi chỉ vì endpoint hoặc giới hạn tài nguyên khác nhau. Mỗi môi trường cung cấp giá trị cấu hình riêng lúc khởi chạy.

~~~mermaid
flowchart TD
    A[Source code] --> B[Build một lần]
    B --> C[Artifact bất biến]
    C --> D[Deploy Development]
    C --> E[Deploy Staging]
    C --> F[Deploy Production]
    D --> G[Config dev + secrets dev]
    E --> H[Config staging + secrets staging]
    F --> I[Config production + secrets production]
~~~

Cùng một JAR hoặc container image được promotion qua các môi trường. Pipeline chỉ thay đổi tham số triển khai và nguồn cấu hình được cấp cho workload.

### 2.2. Vì sao artifact nên bất biến?

Nếu mỗi môi trường có một bản build khác nhau, có thể xảy ra tình trạng:

- Staging đã kiểm thử một binary nhưng production chạy binary khác.
- Một bản build chứa nhầm endpoint hoặc secret của môi trường khác.
- Rollback phải tìm đúng artifact theo môi trường.
- Khó chứng minh binary production là binary đã được kiểm thử.
- Thay đổi cấu hình vô tình kéo theo build và deploy lại code.

Dùng cùng artifact giúp tách hai hoạt động:

- **Build:** tạo binary hoặc image từ source code và dependency đã khóa phiên bản.
- **Deploy/configure:** chạy artifact đó với cấu hình và secret của môi trường đích.

Artifact nên được nhận diện bằng version hoặc digest. Pipeline có thể ghi nhận digest đã chạy ở staging rồi promotion đúng digest đó lên production.

### 2.3. Cấu hình không phải mọi thứ đều là secret

Không phải mọi giá trị thay đổi theo môi trường đều cần đưa vào secret manager. Ví dụ:

- URL của service nội bộ.
- Log level.
- Timeout.
- Số worker.
- Feature flag không nhạy cảm.
- Tên queue hoặc topic.
- Giới hạn retry.

Những giá trị này có thể nằm trong profile hoặc Config Server. Password, API token, private key, signing key và credential phải được bảo vệ riêng.

## 3. Phân loại dữ liệu cấu hình

Trước khi chọn công cụ, phân loại từng property theo tính chất và vòng đời.

| Nhóm | Ví dụ | Nơi lưu phù hợp | Ghi chú |
| --- | --- | --- | --- |
| Giá trị mặc định an toàn | Timeout mặc định, log pattern | application.yml trong artifact | Không chứa môi trường cụ thể |
| Cấu hình môi trường | Endpoint, region, replica hint | Profile, file ngoài, Config Server | Có thể version control |
| Feature flag | Chế độ tính năng | Config Server hoặc feature flag service | Cần audit và rollout |
| Credential | Password, token, API key | Vault, secret manager, platform Secret | Không commit plaintext |
| Khóa mã hóa | Private key, signing key | KMS, HSM, Vault hoặc secret store | Hạn chế workload được phép đọc |
| Dữ liệu runtime | Port thực tế, instance ID | Runtime/platform | Không đóng gói vào artifact |

### 3.1. Giá trị mặc định nên an toàn

File cấu hình đóng gói nên chứa những giá trị mặc định không gây rủi ro nếu ứng dụng khởi chạy trong môi trường mới.

~~~yaml
spring:
  application:
    name: orders-service

server:
  shutdown: graceful

app:
  partner:
    connect-timeout: 500ms
    read-timeout: 2s
    retry:
      max-attempts: 2
~~~

Ví dụ này không chứa host production, username hoặc password. Những giá trị có thể thay đổi theo môi trường sẽ được cung cấp từ nguồn bên ngoài.

### 3.2. Không dùng giá trị mặc định cho secret bắt buộc

Không nên viết:

~~~yaml
spring:
  datasource:
    password: default-password
~~~

Nếu secret source bị thiếu, ứng dụng có thể khởi động bằng credential mặc định mà người vận hành không nhận ra.

Với secret bắt buộc, hãy để property không có giá trị mặc định và validation làm startup thất bại khi thiếu. Nếu ứng dụng có chế độ local cần credential giả, hãy cung cấp credential đó từ test fixture hoặc secret local riêng, không đóng gói nó như mặc định production.

### 3.3. Profile không phải ranh giới bảo mật

Profile như dev, staging và prod giúp chọn cấu hình phù hợp. Nhưng profile không tự cấp quyền truy cập dữ liệu. Một người có thể thay profile hoặc gọi endpoint nếu hạ tầng không kiểm soát quyền.

Không đặt secret production trong application-prod.yml rồi cho rằng file này an toàn chỉ vì chỉ được nạp khi profile prod active. Nếu file nằm trong JAR hoặc repository mà nhiều người có thể đọc, secret đã bị chia sẻ cho họ.

## 4. Spring Boot Config Data và profile

### 4.1. File chung và file profile-specific

Spring Boot hỗ trợ các file như:

- application.yml: cấu hình chung.
- application-local.yml: cấu hình local.
- application-test.yml: cấu hình test.
- application-staging.yml: cấu hình staging.
- application-prod.yml: cấu hình production.

Ví dụ cấu trúc:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

File application.yml chứa cấu hình chung. Khi profile được kích hoạt, file tương ứng được nạp và các key trùng có thể ghi đè giá trị chung.

Ví dụ application.yml:

~~~yaml
app:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 500ms
    read-timeout: 2s

logging:
  level:
    root: INFO
~~~

application-staging.yml:

~~~yaml
app:
  inventory:
    base-url: https://inventory-stg.internal
    connect-timeout: 1s
    read-timeout: 3s
~~~

application-prod.yml:

~~~yaml
app:
  inventory:
    base-url: https://inventory.internal
    connect-timeout: 700ms
    read-timeout: 2s

logging:
  level:
    root: WARN
~~~

Không đưa credential vào các file này. Chúng phù hợp cho cấu hình không nhạy cảm có thể review trong Git.

### 4.2. Kích hoạt profile từ môi trường triển khai

Profile production nên được chọn từ deployment configuration, ví dụ:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Trong Kubernetes, có thể khai báo biến môi trường trong Deployment hoặc Helm values. Với container khác, dùng cơ chế tương ứng của nền tảng.

Tránh hard-code spring.profiles.active=prod trong artifact. Nếu profile được đóng đinh trong binary, cùng artifact khó được promotion qua các môi trường.

### 4.3. Nhiều profile và thứ tự

Spring Boot cho phép kích hoạt nhiều profile:

~~~bash
SPRING_PROFILES_ACTIVE=prod,observability
~~~

Nếu nhiều profile cùng khai báo một key, profile được xử lý sau có thể ghi đè profile trước. Vì vậy, thứ tự danh sách profile có ý nghĩa.

Có thể dùng profile group để gom các profile theo mục đích. Ví dụ:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod
        - metrics
        - tracing
~~~

Khi kích hoạt production, nhóm profile liên quan có thể được bật cùng nhau. Không dùng profile group để phân quyền truy cập secret; quyền đó phải do secret manager hoặc nền tảng quản lý.

### 4.4. Không kích hoạt profile từ profile-specific document

Các thuộc tính điều khiển việc chọn profile, như spring.profiles.active, không được đặt tùy tiện trong một document đã được kích hoạt theo profile. Hãy đặt profile active ở deployment layer hoặc nguồn cấu hình không profile-specific.

Nếu cần profile group hoặc include profile, sử dụng cơ chế profile group/include được Spring Boot hỗ trợ cho đúng phiên bản.

### 4.5. File đóng gói và file bên ngoài

Spring Boot có thể đọc Config Data từ classpath và từ filesystem. Theo thứ tự thông dụng:

1. application.yml đóng gói trong JAR.
2. application-{profile}.yml đóng gói trong JAR.
3. application.yml bên ngoài JAR.
4. application-{profile}.yml bên ngoài JAR.

Nguồn được xử lý sau có thể ghi đè nguồn trước. Do đó, file bên ngoài có thể điều chỉnh cấu hình mà không cần build lại JAR.

## 5. Đưa cấu hình không nhạy cảm ra ngoài artifact

### 5.1. Dùng spring.config.additional-location

Nếu muốn giữ Config Data mặc định trong JAR và bổ sung thư mục cấu hình bên ngoài, dùng spring.config.additional-location.

Ví dụ:

~~~bash
java -jar orders-service.jar --spring.config.additional-location=optional:file:/etc/orders/
~~~

Thư mục có thể chứa:

~~~text
/etc/orders/
  application.yml
  application-prod.yml
~~~

Khi profile prod active, Spring Boot có thể nạp file profile-specific trong location đó.

Dùng additional-location khi muốn **bổ sung** location. spring.config.location thay thế các location tìm kiếm mặc định và dễ làm mất cấu hình đã đóng gói nếu không khai báo đầy đủ.

### 5.2. Dùng spring.config.import

Có thể import file riêng từ application.yml:

~~~yaml
spring:
  config:
    import: optional:file:/etc/orders/overrides.yml
~~~

Nguồn được import được xử lý như Config Data. Giá trị từ file import có thể ghi đè giá trị trong file khai báo import theo quy tắc Config Data.

Tiền tố optional: cho phép ứng dụng tiếp tục nếu location không tồn tại. Chỉ dùng optional cho cấu hình thật sự tùy chọn. Nếu ứng dụng cần một file cấu hình bắt buộc để hoạt động an toàn, bỏ optional: để startup báo lỗi khi thiếu.

### 5.3. Đường dẫn phải phù hợp runtime

Đường dẫn trên máy lập trình có thể khác container hoặc VM production. Hãy khai báo location theo đường dẫn mount ổn định của runtime, không dựa vào thư mục home của developer.

Với container, nên mount cấu hình vào một thư mục được quy ước, ví dụ /etc/orders/config. Đảm bảo user chạy ứng dụng có quyền đọc và không có quyền ghi nếu không cần.

### 5.4. Không nhúng file bí mật vào image

Dockerfile không nên COPY file chứa credential vào image layer. Xóa file ở layer sau không bảo đảm bí mật biến mất khỏi các layer trước.

Cấu hình không nhạy cảm có thể được mount hoặc cấp bằng Config Data. Secret nên được mount hoặc inject lúc chạy từ secret manager hoặc platform secret facility.

## 6. Biến môi trường và relaxed binding

### 6.1. Dùng biến môi trường cho cấu hình đơn giản

Spring Boot có thể đọc OS environment variables. Ví dụ:

~~~bash
SPRING_PROFILES_ACTIVE=staging
SERVER_PORT=8080
APP_INVENTORY_BASE_URL=https://inventory-stg.internal
APP_INVENTORY_READ_TIMEOUT=3s
~~~

Tên property dạng app.inventory.read-timeout thường được biểu diễn bằng chữ hoa và dấu gạch dưới trong biến môi trường.

Biến môi trường thuận tiện cho cấu hình triển khai đơn giản và các giá trị không quá dài. Nhưng với credential, cần xem xét cách nền tảng quản lý quyền đọc environment và khả năng lộ qua process diagnostics, crash dump hoặc công cụ debug.

### 6.2. Không truyền secret qua command line nếu có thể tránh

Ví dụ không nên:

~~~bash
java -jar orders-service.jar --spring.datasource.password=secret-value
~~~

Command line có thể xuất hiện trong process inspection hoặc log của hệ thống quản lý process. Dùng secret file mount hoặc secret manager phù hợp hơn.

### 6.3. Placeholder kết nối các property

Spring hỗ trợ placeholder để ghép giá trị:

~~~yaml
app:
  partner:
    base-url: ${PARTNER_BASE_URL:https://partner.local}
    timeout: ${PARTNER_TIMEOUT:2s}
~~~

Ví dụ trên dùng fallback cho cấu hình không nhạy cảm. Với password hoặc token bắt buộc, tránh đặt fallback là một credential giả hoặc mặc định. Hãy để thiếu secret làm validation thất bại.

## 7. Configuration tree và secret file mount

### 7.1. Vì sao configuration tree hữu ích?

Một số nền tảng có thể mount ConfigMap hoặc Secret thành thư mục chứa nhiều file. Spring Boot có prefix configtree: để chuyển cấu trúc file thành property source.

Ví dụ thư mục:

~~~text
/run/secrets/
  spring/
    datasource/
      username
      password
    rabbitmq/
      username
      password
~~~

Tên thư mục và file tạo thành property key:

| File | Property |
| --- | --- |
| /run/secrets/spring/datasource/username | spring.datasource.username |
| /run/secrets/spring/datasource/password | spring.datasource.password |
| /run/secrets/spring/rabbitmq/username | spring.rabbitmq.username |
| /run/secrets/spring/rabbitmq/password | spring.rabbitmq.password |

### 7.2. Import configuration tree

Khai báo trong application.yml:

~~~yaml
spring:
  config:
    import: configtree:/run/secrets/
~~~

Vì các secret này là bắt buộc, ví dụ không dùng optional:. Nếu thư mục không tồn tại, startup nên thất bại thay vì chạy với cấu hình thiếu.

Nếu secret chỉ có ở một môi trường nhất định, có thể khai báo import trong file hoặc document phù hợp, nhưng cần kiểm tra profile và import được xử lý đúng ở runtime đó.

### 7.3. Config tree có thể import tùy chọn

Trong môi trường local không cần secret mount, có thể dùng:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Chỉ dùng cách này khi ứng dụng có một nguồn secret thay thế an toàn trong local hoặc test. Không chuyển cấu hình production sang optional chỉ để container không báo lỗi khi mount bị thiếu.

### 7.4. Mount nhiều nhóm cấu hình

Có thể tách các secret theo nguồn:

~~~text
/run/secrets/
  database/
    spring.datasource.username
    spring.datasource.password
  messaging/
    spring.rabbitmq.username
    spring.rabbitmq.password
~~~

Hoặc dùng thư mục con theo quy tắc property name. Spring Boot hỗ trợ wildcard config tree cho các thư mục con trực tiếp:

~~~yaml
spring:
  config:
    import: configtree:/run/secrets/*/
~~~

Các thư mục wildcard được xử lý theo thứ tự tên. Nếu hai cây cùng cung cấp một property, cần tránh va chạm hoặc chỉ rõ thứ tự import.

### 7.5. Giá trị có thể là String hoặc byte[]

Configuration tree có thể bind nội dung file thành String hoặc byte[] tùy kiểu property được yêu cầu. Điều này hữu ích cho chứng thư, key hoặc dữ liệu nhị phân, nhưng cần xác định rõ encoding và cách thư viện nhận dữ liệu.

Không đọc private key thành String rồi ghi log hoặc đưa vào exception message.

## 8. Kubernetes ConfigMap và Secret

### 8.1. Phân biệt hai loại resource

Trong Kubernetes:

- ConfigMap dành cho dữ liệu cấu hình không bí mật.
- Secret dành cho password, token, key và dữ liệu nhạy cảm.

Ví dụ:

| Dữ liệu | Resource |
| --- | --- |
| URL của inventory service | ConfigMap |
| Log level | ConfigMap |
| Feature flag không nhạy cảm | ConfigMap |
| Database password | Secret |
| API token | Secret |
| TLS private key | Secret hoặc secret manager tích hợp |

### 8.2. Base64 không phải mã hóa

Kubernetes Secret biểu diễn một số trường dưới dạng Base64. Base64 chỉ là encoding, không cung cấp tính bí mật. Người có thể đọc manifest hoặc giá trị đã decode có thể lấy secret.

Không commit manifest Secret chứa dữ liệu thật vào Git chỉ vì trường data đang ở dạng Base64.

### 8.3. Bảo vệ Kubernetes Secret

Với Kubernetes, cần:

- Bật encryption at rest cho dữ liệu Secret trong etcd.
- Dùng RBAC least privilege để giới hạn ai có thể get, list hoặc watch Secret.
- Chỉ mount Secret vào container cần sử dụng.
- Giới hạn quyền truy cập file mount.
- Không đưa secret vào image, Helm chart values công khai hoặc log.
- Bảo vệ backup etcd và backup của manifest.
- Xác minh ứng dụng không log secret sau khi đọc.

Một Pod có nhiều container không nên chia sẻ mọi Secret cho tất cả container nếu chỉ một container cần credential đó.

### 8.4. ConfigMap không phải nơi lưu credential

Không đặt password vào ConfigMap rồi coi namespace hoặc private cluster là đủ bảo vệ. Tách dữ liệu không nhạy cảm và secret ngay từ thiết kế để quyền truy cập có thể được giới hạn riêng.

## 9. Spring Cloud Config cho cấu hình tập trung

### 9.1. Vai trò của Config Server

Spring Cloud Config Server cung cấp cấu hình từ xa cho nhiều Config Client. Nguồn dữ liệu thường là Git repository, nhưng server cũng hỗ trợ backend khác.

Config Server định danh một bộ cấu hình theo ba thành phần:

- application: thường tương ứng spring.application.name.
- profile: các active profile của client.
- label: phiên bản cấu hình, thường là branch, tag hoặc commit trong Git backend.

Một client có thể yêu cầu cấu hình theo application, profile và label. Nhờ đó, nhiều service có thể dùng cấu hình chung và bổ sung cấu hình riêng.

### 9.2. Ví dụ cấu trúc Git repository

~~~text
config-repo/
  application.yml
  application-prod.yml
  orders-service.yml
  orders-service-prod.yml
  inventory-service.yml
  inventory-service-prod.yml
~~~

Ý nghĩa:

- application.yml: cấu hình chung cho các client.
- application-prod.yml: cấu hình chung cho profile prod.
- orders-service.yml: cấu hình riêng cho Orders.
- orders-service-prod.yml: cấu hình Orders ở production.
- inventory-service.yml: cấu hình riêng cho Inventory.
- inventory-service-prod.yml: cấu hình Inventory ở production.

Theo quy tắc Environment Repository, cấu hình riêng theo application và profile-specific có thể có ưu tiên cao hơn cấu hình mặc định. Hãy kiểm tra property source response thực tế khi có nhiều file cùng khai báo một key.

### 9.3. Khai báo Config Data import

Trong Config Client:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: configserver:
  cloud:
    config:
      label: release-2026-11
~~~

Địa chỉ Config Server có thể được cấu hình qua spring.cloud.config.uri hoặc khai báo trực tiếp trong import location. Ví dụ:

~~~yaml
spring:
  config:
    import: configserver:https://config.internal
~~~

Cách dùng Config Data import được hỗ trợ từ Spring Boot 2.4. Đây là cách mặc định hiện hành của Spring Cloud Config Client. Bootstrap legacy vẫn có thể tồn tại trong dự án cũ, nhưng không nên trộn hai mô hình khi chưa hiểu thứ tự property source của từng mô hình.

### 9.4. optional và bắt buộc kết nối Config Server

Hai cách cấu hình có ý nghĩa khác nhau:

~~~properties
spring.config.import=optional:configserver:
~~~

~~~properties
spring.config.import=configserver:
~~~

Có optional:, ứng dụng có thể tiếp tục startup nếu Config Server không truy cập được. Không có optional:, client fail startup nếu không lấy được cấu hình từ server.

Với cấu hình production bắt buộc như endpoint quan trọng, policy hoặc property ảnh hưởng bảo mật, không nên để ứng dụng âm thầm chạy với giá trị mặc định khi Config Server mất kết nối.

Nếu ứng dụng có thể hoạt động an toàn bằng local defaults khi Config Server tạm thời unavailable, optional có thể phù hợp, nhưng cần ghi rõ điều kiện và quan sát cảnh báo.

### 9.5. Config Client có thể gọi server nhiều lần khi startup

Với Config Data, client có thể lấy cấu hình theo profile default trước để phát hiện profile được kích hoạt từ remote configuration, rồi gọi lại với active profile. Nhiều request lúc startup là hành vi bình thường trong cơ chế này.

Đừng coi nhiều request là lỗi ngay lập tức. Kiểm tra application name, profile và label mà client gửi.

### 9.6. Dùng label để version hóa cấu hình

Label có thể là branch, tag hoặc commit ID tùy backend. Để triển khai lặp lại được, nên chọn revision ổn định cho mỗi đợt deploy thay vì để production luôn đọc một branch thay đổi liên tục mà không ghi nhận revision.

Một pipeline có thể:

1. Tạo commit cấu hình.
2. Review và kiểm tra thay đổi.
3. Gắn tag hoặc lưu commit ID.
4. Triển khai staging với label đó.
5. Kiểm tra kết quả.
6. Promotion cùng label lên production.
7. Nếu cần rollback, quay lại label đã được kiểm thử trước đó.

### 9.7. Config Server không nên chứa plaintext secret trong Git

Config Server giúp quản lý cấu hình tập trung, nhưng repository Git không tự trở thành secret manager. Nếu lưu password plaintext trong Git, mọi người có quyền đọc repository có thể lấy credential.

Có thể dùng các hướng sau:

- Lưu cấu hình không nhạy cảm trong Git Config Repository.
- Lưu secret trong Vault hoặc secret manager.
- Dùng Config Server Vault backend nếu kiến trúc yêu cầu.
- Dùng encrypted properties khi phù hợp, với key được quản lý riêng.

## 10. Phân tách secret bằng Spring Cloud Vault

### 10.1. Vault là nguồn secret riêng

Spring Cloud Vault tích hợp HashiCorp Vault để đưa secret backend thành PropertySource trong Spring Environment. Ứng dụng có thể lấy secret theo application name và active profile.

Cách này giúp:

- Secret không cần lưu plaintext trong Git.
- Quyền đọc secret gắn với danh tính workload.
- Tách secret theo service và môi trường.
- Hỗ trợ backend KV có version.
- Tập trung audit và quản lý vòng đời secret theo chính sách Vault.

### 10.2. Dùng Config Data API

Spring Cloud Vault hỗ trợ Config Data API. Cấu hình cơ bản:

~~~yaml
spring:
  config:
    import: vault://
  cloud:
    vault:
      uri: https://vault.internal
~~~

Ứng dụng cần dependency Spring Cloud Vault Config phù hợp với release train. Kết nối Vault cần TLS và cơ chế xác thực. Không đặt root token hoặc token dùng chung lâu dài trong application.yml.

### 10.3. Context path theo application và profile

Với KV backend mặc định, Spring Cloud Vault có thể lấy dữ liệu theo các context path như:

~~~text
/secret/application
/secret/application/prod
/secret/orders-service
/secret/orders-service/prod
~~~

Tên backend, default context, application name, profile separator và KV version có thể được cấu hình. Cấu trúc thực tế phụ thuộc cấu hình Vault của tổ chức.

Ví dụ, Vault có thể chứa:

~~~text
secret/
  application/
    common-property: value
  orders-service/
    datasource-username: orders_app
  orders-service/
    prod/
      datasource-password: ...
~~~

Ví dụ minh họa cấu trúc logic; với KV v2, đường dẫn API có phần data riêng do Vault xử lý. Không tự ghép đường dẫn HTTP KV v1/v2 bằng tay khi đã dùng Spring Cloud Vault.

### 10.4. Import context cụ thể

Nếu không muốn dùng các context mặc định, có thể import đường dẫn cụ thể:

~~~yaml
spring:
  config:
    import: vault:///apps/orders-service/prod
~~~

Có thể kết hợp nhiều Vault location và nguồn Config Data khác. Thứ tự import có ý nghĩa; nếu nhiều nguồn cung cấp cùng một property, hãy xác minh nguồn thắng trong Environment.

### 10.5. Xác thực workload

Vault cần xác thực client trước khi cấp secret. Tùy nền tảng, có thể dùng Kubernetes auth, AppRole, cloud IAM hoặc cơ chế khác được hỗ trợ.

Nguyên tắc:

- Mỗi workload có danh tính riêng.
- Policy chỉ cho đọc path cần thiết.
- Không dùng root token trong ứng dụng.
- Hạn chế token có thời hạn dài.
- Bảo vệ TLS certificate và auth material.
- Audit việc đọc secret.
- Thu hồi danh tính khi workload hoặc service không còn được phép truy cập.

### 10.6. Không nhầm Config Server Vault backend với Config Client Vault

Có hai cách tích hợp khác nhau:

1. Config Server sử dụng Vault làm backend để lấy cấu hình rồi phục vụ Config Client.
2. Config Client sử dụng Spring Cloud Vault trực tiếp để import secret vào Environment.

Hai kiến trúc có ranh giới quyền và đường đi dữ liệu khác nhau. Chọn một cách phù hợp với mô hình quản trị; không cấu hình cả hai cho cùng một property mà không kiểm soát precedence.

## 11. Mã hóa property trong Spring Cloud Config

### 11.1. Encrypted property

Spring Cloud Config hỗ trợ giá trị có tiền tố {cipher}. Config Server có thể giải mã trước khi gửi property source cho client. Cách này giúp ciphertext được lưu trong Git thay vì plaintext.

Ví dụ trong YAML:

~~~yaml
spring:
  datasource:
    password: '{cipher}ENCRYPTED_VALUE'
~~~

### 11.2. Mã hóa at rest không thay thế secret manager

Trong mô hình server-side decryption:

1. Git lưu ciphertext.
2. Config Server đọc ciphertext.
3. Config Server dùng key để giải mã.
4. Client nhận plaintext qua kết nối Config Server.

Vì vậy, Config Server và key material trở thành thành phần có quyền truy cập plaintext. Cần bảo vệ server, key, endpoint, TLS và authorization.

Mã hóa property phù hợp với một số quy trình Git-based configuration, nhưng không tự cung cấp đầy đủ các khả năng như danh tính workload, lease, audit secret access hoặc rotation policy của secret manager.

### 11.3. Khi nào chọn Vault thay cho encrypted property?

| Tiêu chí | Encrypted property trong Config Server | Vault/secret manager |
| --- | --- | --- |
| Cấu hình không nhạy cảm | Có thể lưu trong Git | Có thể lưu nhưng không nhất thiết cần |
| Secret at rest | Lưu ciphertext | Secret được quản lý trong backend riêng |
| Phân quyền theo workload | Phụ thuộc Config Server authorization và key design | Có thể gắn policy với workload identity |
| Rotation | Cần tạo ciphertext mới và triển khai key/cấu hình | Có thể quản lý version/rotation theo backend |
| Dynamic credentials | Không phải mục tiêu chính | Một số backend hỗ trợ credential động |
| Audit đọc secret | Phụ thuộc hệ thống Config Server | Vault cung cấp audit theo cấu hình |

Không có lựa chọn duy nhất cho mọi tổ chức. Có thể dùng Config Server cho cấu hình chung và Vault cho secret; điều quan trọng là không tạo hai nguồn bí mật cạnh tranh mà không có quy tắc rõ ràng.

## 12. Thiết kế lớp cấu hình có kiểu

### 12.1. Không rải property key trong toàn bộ code

Thay vì đọc property tùy ý ở nhiều class:

~~~java
String url = environment.getProperty("partner.api.base-url");
String token = environment.getProperty("partner.api.token");
~~~

nên gom cấu hình liên quan vào một type có prefix và validation.

~~~java
@ConfigurationProperties(prefix = "partner.api")
@Validated
public record PartnerApiProperties(
        @NotBlank String baseUrl,
        @NotBlank String token,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout
) {
}
~~~

Đăng ký bằng ConfigurationPropertiesScan hoặc EnableConfigurationProperties.

### 12.2. Validation làm startup thất bại khi thiếu secret

Nếu token là bắt buộc, @NotBlank giúp ứng dụng không khởi động với giá trị rỗng. Không đặt token mặc định trong record.

Ví dụ cấu hình không nhạy cảm:

~~~yaml
partner:
  api:
    base-url: https://partner.internal
    connect-timeout: 500ms
    read-timeout: 2s
~~~

Token được cấp từ secret source với key partner.api.token. Khi source không có property đó, validation thất bại thay vì âm thầm dùng giá trị giả.

### 12.3. Tách nhóm properties theo trách nhiệm

Có thể chia thành:

- DatabaseConnectionProperties.
- MessagingConnectionProperties.
- PartnerApiProperties.
- FeatureProperties.
- ObservabilityProperties.

Không tạo một class khổng lồ chứa mọi property của hệ thống. Nhóm theo thành phần sở hữu và vòng đời giúp xác định nguồn cấu hình, quyền secret và cách refresh rõ ràng hơn.

### 12.4. Không expose secret qua toString

Record mặc định tạo toString có thể in mọi field. Nếu class chứa password hoặc token, tránh log object trực tiếp. Có thể dùng class thay vì record hoặc override toString để che field nhạy cảm.

Không trả secret trong Actuator, error response, metric tag hoặc exception message.

## 13. Thứ tự ưu tiên và tránh shadowing

### 13.1. Nhiều nguồn có thể cùng khai báo một key

Một property có thể xuất hiện trong:

- application.yml trong JAR.
- application-prod.yml.
- File external.
- Environment variable.
- JVM system property.
- Command line.
- Config Server.
- Vault.
- Configuration tree.
- Test property source.

Giá trị cuối cùng phụ thuộc thứ tự Config Data import và PropertySource được tạo trong Environment. Không nên đoán rằng Vault hoặc Config Server luôn thắng chỉ vì đó là nguồn remote.

### 13.2. Thứ tự import có ý nghĩa

Spring Boot xử lý Config Data import như các nguồn bổ sung được chèn vào vị trí khai báo. Nhiều import được xử lý theo thứ tự khai báo; import sau có thể ghi đè import trước.

Ví dụ:

~~~yaml
spring:
  config:
    import: configserver:,vault://
~~~

Nếu cả Config Server và Vault cùng cung cấp partner.api.token, cần xác định nguồn nào được ưu tiên trong phiên bản và cách khai báo đang dùng. Tốt nhất là chỉ một nguồn sở hữu một secret key cụ thể.

### 13.3. Không tạo fallback cho secret production

Ví dụ nguy hiểm:

~~~yaml
spring:
  datasource:
    password: ${DB_PASSWORD:local-password}
~~~

Nếu DB_PASSWORD bị thiếu trong production, ứng dụng vẫn chạy với local-password. Điều này che giấu lỗi triển khai và có thể khiến ứng dụng dùng nhầm credential.

Với secret bắt buộc, dùng placeholder không có fallback hoặc validation bắt buộc. Có thể có một profile local riêng, nhưng phải được chọn rõ ràng và không được tự động kích hoạt trong production.

### 13.4. Kiểm tra nguồn thắng

Khi một giá trị không như dự kiến:

1. Đọc Environment.getProperty(key) trong môi trường được bảo vệ.
2. Liệt kê tên PropertySource chứa key.
3. Xác nhận active profiles.
4. Kiểm tra Config Server application/profile/label.
5. Kiểm tra Vault context path.
6. Kiểm tra config tree mount.
7. Kiểm tra biến môi trường và system properties.
8. Kiểm tra bean ConfigurationProperties sau binding.

Không dump toàn bộ Environment hoặc property source vào log vì có thể làm lộ secret.

## 14. Quản lý cấu hình theo môi trường trong Git

### 14.1. Repository cấu hình tách khỏi source code

Một cấu trúc thường dùng:

~~~text
orders-config/
  application.yml
  application-staging.yml
  application-prod.yml
  orders-service.yml
  orders-service-staging.yml
  orders-service-prod.yml
  inventory-service.yml
  inventory-service-prod.yml
~~~

Repository này lưu cấu hình không nhạy cảm và được review như code. Quyền merge vào branch/tag production cần chặt chẽ hơn cấu hình development.

### 14.2. Phân tách theo application và profile

Dùng application.yml cho giá trị chung. Dùng orders-service.yml cho cấu hình riêng của Orders. Dùng orders-service-prod.yml cho khác biệt production của Orders.

Không nhân bản toàn bộ file chung vào từng service nếu chỉ một vài key khác nhau. Việc duplicate làm tăng rủi ro cấu hình lệch giữa các ứng dụng.

### 14.3. Version control và rollback

Mỗi thay đổi cấu hình nên có:

- Người tạo và người review.
- Mục đích thay đổi.
- Environment chịu ảnh hưởng.
- Commit/tag hoặc label.
- Cách xác minh.
- Kế hoạch rollback.

Với production, ưu tiên label bất biến như commit ID hoặc tag release đã được phê duyệt. Một branch đang thay đổi có thể khiến cùng một deployment khởi động lại với cấu hình khác ở thời điểm khác.

### 14.4. Không commit file local secret

Các file như .env, application-local-secret.yml, credentials.json hoặc keystore cá nhân cần được loại khỏi Git bằng .gitignore phù hợp. Tuy nhiên, .gitignore không xóa dữ liệu đã commit trước đó. Nếu secret từng được commit, cần rotate credential và xử lý lịch sử repository theo chính sách.

Không dùng file local bị ignore làm cơ chế secret production. Production cần nguồn secret do nền tảng quản lý và audit.

## 15. Pipeline promotion cấu hình

Một quy trình triển khai có kiểm soát:

1. Build artifact một lần.
2. Quét dependency và image theo policy.
3. Lưu artifact digest.
4. Review cấu hình không nhạy cảm trong repository.
5. Cấp secret cho workload bằng identity hoặc secret mount.
6. Deploy cùng artifact digest lên development.
7. Kiểm thử startup, health và kết nối dependency.
8. Promotion cùng digest và config revision lên staging.
9. Chạy integration/smoke test.
10. Phê duyệt production.
11. Deploy cùng digest với profile, Config Server label và secret scope production.
12. Kiểm tra readiness và revision đã nạp.
13. Ghi nhận trạng thái để rollback.

~~~mermaid
flowchart TD
    A[Build artifact once] --> B[Record digest]
    B --> C[Review config revision]
    C --> D[Deploy dev]
    D --> E[Smoke and integration tests]
    E --> F[Deploy staging same digest]
    F --> G[Validate and approve]
    G --> H[Deploy production same digest]
    H --> I[Verify config revision and secret access]
    I --> J[Monitor health and rollback readiness]
~~~

### 15.1. Cấp secret theo workload

Mỗi service chỉ nên nhận secret cần cho chính nó. Orders không cần đọc toàn bộ secret của Inventory. Development không cần quyền đọc secret production.

Với Vault, tạo policy riêng theo application/path. Với Kubernetes, giới hạn Secret được mount vào Pod và RBAC của ServiceAccount. Với cloud secret manager, dùng workload identity và policy theo resource.

### 15.2. Không đưa secret vào pipeline log

Pipeline chỉ nên ghi nhận secret reference, version hoặc tên credential không nhạy cảm. Không echo secret, in toàn bộ environment hoặc bật debug HTTP request chứa token.

Nếu pipeline cần tạo secret, dùng secret store của CI/CD với masking và quyền hạn tối thiểu. Masking không thay thế việc tránh in secret.

## 16. Rotation, refresh và restart

### 16.1. Thay secret ở nguồn chưa chắc thay secret trong bean

Một ứng dụng có thể đọc password lúc startup và bind vào singleton bean hoặc connection pool. Khi secret source đổi, object đã tạo có thể vẫn giữ giá trị cũ.

Cần xác định:

- Secret source có cơ chế thông báo hoặc refresh không?
- Config Client có lấy lại property source không?
- Bean có nằm trong RefreshScope không?
- Connection pool có hỗ trợ thay credential an toàn không?
- Có cần restart instance để tạo resource mới không?

Không giả định file secret mount thay đổi là Environment và mọi bean tự cập nhật.

### 16.2. Refresh hay restart?

| Thay đổi | Cách xử lý thường cân nhắc |
| --- | --- |
| Feature flag được đọc động | Có thể cập nhật qua config refresh hoặc feature service |
| Timeout của client refreshable | Có thể refresh target nếu thiết kế hỗ trợ |
| Database credential | Cần pool replacement/drain hoặc restart có kiểm soát |
| JVM flags hoặc heap | Restart process |
| Classpath hoặc dependency | Build và deploy artifact mới |
| TLS private key | Phụ thuộc client/server reload support; có thể cần restart |

Spring Cloud Context cung cấp refresh cho các bean phù hợp. Nó không tự biến mọi singleton thành object đọc cấu hình động.

### 16.3. Rotation có thời gian chuyển tiếp

Khi đổi credential, hệ thống đích có thể hỗ trợ hai credential đồng thời trong một khoảng thời gian. Quy trình an toàn thường là:

1. Tạo credential mới.
2. Cấp credential mới cho secret manager.
3. Cập nhật ứng dụng hoặc client.
4. Xác minh mọi instance dùng credential mới.
5. Thu hồi credential cũ.
6. Kiểm tra connection pool và lỗi xác thực sau rotation.

Không thu hồi credential cũ trước khi các instance còn dùng nó đã được chuyển đổi, trừ khi đang xử lý sự cố compromise và cần thu hồi khẩn cấp.

### 16.4. Rollback phải bao gồm cấu hình và secret

Rollback chỉ code mà không rollback cấu hình tương thích có thể làm ứng dụng không khởi động. Ngược lại, khôi phục secret cũ đã bị thu hồi cũng không phải giải pháp.

Mỗi đợt deploy nên ghi nhận:

- Artifact digest.
- Config label/revision.
- Secret version hoặc secret reference.
- Profile.
- Thời điểm deploy.
- Trạng thái health.

Khi rollback, khôi phục một bộ tương thích đã được kiểm thử, không chỉ một file application.yml.

## 17. Bảo mật dữ liệu cấu hình

### 17.1. Phân quyền theo nguyên tắc least privilege

Người hoặc workload chỉ được đọc những property và secret cần cho nhiệm vụ. Không cấp quyền đọc toàn bộ config repository hoặc secret namespace nếu không cần.

### 17.2. Bảo vệ đường truyền

Config Client, Config Server, Vault và secret manager cần giao tiếp qua TLS khi đi qua network. Xác minh certificate và hostname; không tắt SSL validation để né lỗi chứng thư trong production.

### 17.3. Bảo vệ dữ liệu sau khi đọc

Secret có thể xuất hiện trong:

- Environment.
- Object ConfigurationProperties.
- Connection pool.
- HTTP client.
- Heap dump.
- Debugger.
- Log hoặc exception.
- Actuator endpoint.

Sau khi ứng dụng đọc secret, vẫn cần bảo vệ process, host/container, log pipeline và quyền debug. Secret manager không thể ngăn secret bị lộ nếu ứng dụng tự ghi plaintext ra log.

### 17.4. Actuator và endpoint cấu hình

Không expose env, configprops hoặc endpoint quản trị rộng rãi. Nếu cần kiểm tra cấu hình, dùng endpoint được bảo vệ, che giá trị nhạy cảm và chỉ cấp cho role vận hành.

### 17.5. Backup và lịch sử

Backup Config Server repository, Vault và secret store đều có thể chứa thông tin nhạy cảm hoặc ciphertext có thể giải mã. Bảo vệ backup, audit quyền đọc và có chính sách retention.

## 18. Kiểm thử cấu hình theo môi trường

### 18.1. Kiểm tra profile

Dùng ActiveProfiles để xác nhận file profile-specific được nạp trong test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrdersConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void usesTestProfile() {
        assertThat(environment.getActiveProfiles())
                .contains("test");

        assertThat(environment.getProperty("app.inventory.base-url"))
                .isEqualTo("http://localhost:18081");
    }
}
~~~

Không dùng profile production trong test chỉ để kiểm tra file. Có thể tạo fixture test với các giá trị không nhạy cảm.

### 18.2. Kiểm tra cấu hình bắt buộc

Dùng ApplicationContextRunner hoặc SpringBootTest để xác nhận context fail khi thiếu secret bắt buộc. Đây là test quan trọng vì nó ngăn fallback sai.

Ví dụ:

~~~java
@Test
void missingPartnerTokenPreventsStartup() {
    new ApplicationContextRunner()
            .withUserConfiguration(PartnerConfiguration.class)
            .withPropertyValues(
                    "partner.api.base-url=https://partner.test",
                    "partner.api.connect-timeout=500ms",
                    "partner.api.read-timeout=2s"
            )
            .run(context -> {
                assertThat(context).hasFailed();
            });
}
~~~

Ví dụ giả định PartnerConfiguration đăng ký PartnerApiProperties đã bật validation. Không thêm property partner.api.token để kiểm tra ứng dụng từ chối startup.

### 18.3. Kiểm tra nguồn secret

Với config tree, có thể tạo thư mục test chứa file username/password và khởi động context dùng import configtree. Với Vault, dùng Vault test environment hoặc mock phù hợp, không gọi Vault production từ test tự động.

### 18.4. Kiểm tra Config Server theo label cố định

Integration test nên:

1. Dùng Config Server test hoặc repository fixture.
2. Chọn application name rõ ràng.
3. Chọn profile test.
4. Chọn label/commit cố định.
5. Khởi động Config Client.
6. Kiểm tra property source và giá trị đã resolve.
7. Xác nhận thiếu remote config dẫn tới fail hoặc fallback đúng chính sách.
8. Không dùng production secret trong test.

### 18.5. Kiểm tra không log secret

Có thể kiểm tra log capture trong test khi startup và khi lỗi validation. Đảm bảo message không chứa token hoặc password đã cung cấp. Không chỉ kiểm tra response object; một exception hoặc toString có thể làm lộ giá trị.

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Ứng dụng dùng nhầm cấu hình local ở production | Profile không active hoặc external source chưa nạp | Kiểm tra SPRING_PROFILES_ACTIVE và PropertySource |
| File ngoài không ghi đè file trong JAR | Dùng spring.config.location sai hoặc path không được tìm thấy | Kiểm tra additional-location, path và log Config Data |
| Config Server không được gọi | Thiếu configserver import hoặc dependency | Kiểm tra Config Client starter và spring.config.import |
| Startup vẫn thành công khi Config Server lỗi | Import có optional: | Quyết định rõ có cho phép chạy với local config hay không |
| Client đọc sai bộ cấu hình | Sai application name, profile hoặc label | Kiểm tra request path và config revision |
| Secret rỗng | Secret mount/Vault path sai hoặc quyền đọc bị từ chối | Kiểm tra mount, Vault policy và startup logs đã che secret |
| Secret mặc định bị dùng | Placeholder có fallback hoặc bean có default | Bỏ fallback và thêm validation bắt buộc |
| Vault 403 | Workload identity hoặc policy không cho đọc path | Kiểm tra auth method, role và policy |
| Vault 404 | Context path hoặc profile path không tồn tại | Kiểm tra application name, profile, backend và KV version |
| Kubernetes Secret không được cập nhật | Volume update semantics hoặc ứng dụng chưa reload | Xác minh file mount và kích hoạt refresh/restart phù hợp |
| Secret xuất hiện trong log | Log object config hoặc exception chứa plaintext | Che dữ liệu, sửa logging và rà soát log retention |
| Một số replica dùng cấu hình khác | Config label/secret version không đồng nhất | Ghi nhận revision trên từng instance và rollout theo nhóm |
| Rollback không hoạt động | Artifact, config revision và secret version không tương thích | Khôi phục bộ phiên bản đã được kiểm thử |
| Local chạy được nhưng container lỗi | File path, permission hoặc environment khác | Kiểm tra mount và user runtime |
| Secret Base64 bị xem là đã mã hóa | Nhầm encoding với encryption | Dùng Secret store đúng cách, encryption at rest và RBAC |

## 20. Quy trình vận hành đề xuất

Với một service Orders dùng Config Server cho cấu hình và Vault cho secret:

1. Đóng gói application.yml chỉ với tên ứng dụng, cấu hình an toàn và Config Data imports.
2. Build một container image và ghi nhận digest.
3. Cấu hình profile từ deployment environment.
4. Config Server trả cấu hình Orders theo application/profile/label.
5. Vault cấp datasource credential và partner token theo identity của workload.
6. Ứng dụng bind cấu hình qua ConfigurationProperties và validate.
7. Readiness chỉ đạt khi cấu hình bắt buộc và dependency thiết yếu đã sẵn sàng.
8. Pipeline triển khai cùng image digest qua staging rồi production.
9. Mỗi lần deploy ghi nhận config revision và secret version.
10. Rotation cập nhật secret source, sau đó refresh/restart thành phần cần thiết.
11. Rollback khôi phục artifact/configuration tương thích và xác minh credential vẫn hợp lệ.
12. Audit quyền đọc secret, thay đổi cấu hình và thao tác quản trị.

~~~mermaid
flowchart TD
    A[Immutable application image] --> B[Spring Boot Config Data]
    C[Deployment profile] --> B
    D[Spring Cloud Config] --> B
    E[Vault or secret manager] --> B
    F[Mounted config tree] --> B
    B --> G[Environment and PropertySources]
    G --> H[ConfigurationProperties binding]
    H --> I[Validation]
    I --> J[Application starts]
    J --> K[Readiness and dependency checks]
~~~

## 21. Checklist trước khi đưa cấu hình vào production

### Artifact và profile

- [ ] Cùng artifact digest được dùng ở các môi trường.
- [ ] Profile được chọn từ deployment layer.
- [ ] application.yml chỉ chứa giá trị mặc định an toàn.
- [ ] Profile-specific files không chứa plaintext secret.
- [ ] Không có endpoint production hoặc credential bị hard-code trong code.

### Config Data và Config Server

- [ ] Config Data locations được xác định rõ.
- [ ] Dùng additional-location khi cần bổ sung file ngoài.
- [ ] Config Server import có optional hay không được quyết định theo yêu cầu availability.
- [ ] Application name, profile và label đúng.
- [ ] Config revision được ghi nhận.
- [ ] Không dùng branch thay đổi liên tục nếu cần deployment tái lập.

### Secret

- [ ] Password/token/private key không nằm trong Git hoặc image.
- [ ] Secret được cấp từ Vault, secret manager hoặc platform Secret.
- [ ] Workload chỉ có quyền đọc secret cần thiết.
- [ ] Secret bắt buộc không có fallback mặc định.
- [ ] Kubernetes Secret được bảo vệ bằng RBAC và encryption at rest.
- [ ] Secret không xuất hiện trong log, metric hoặc Actuator.
- [ ] Có quy trình rotation và thu hồi credential.

### Runtime và rollback

- [ ] ConfigurationProperties được validate.
- [ ] Startup thất bại khi cấu hình bắt buộc bị thiếu hoặc sai.
- [ ] Readiness phản ánh khả năng phục vụ thực tế.
- [ ] Rotation có kế hoạch refresh/restart resource.
- [ ] Artifact, config revision và secret version được ghi nhận.
- [ ] Rollback đã được kiểm thử.

## 22. Bài tập vận dụng

**Bài tập 1 — Một artifact nhiều môi trường.** Tạo application.yml và application-staging.yml. Build một JAR, chạy hai lần với hai profile khác nhau và chứng minh artifact không đổi nhưng endpoint cấu hình thay đổi.

**Bài tập 2 — File cấu hình ngoài.** Mount thư mục /etc/orders vào container. Dùng spring.config.additional-location để nạp application-prod.yml. Kiểm tra giá trị ngoài JAR ghi đè giá trị mặc định.

**Bài tập 3 — Configuration tree.** Tạo thư mục /run/secrets/spring/datasource chứa username và password. Import bằng configtree: và xác nhận DataSource nhận đúng property.

**Bài tập 4 — Secret bắt buộc.** Tạo PartnerApiProperties với token @NotBlank. Chạy context khi có và khi thiếu token; xác nhận trường hợp thiếu làm startup thất bại.

**Bài tập 5 — Config Server.** Tạo repository có application.yml, orders-service.yml và orders-service-prod.yml. Chọn application/profile/label rồi kiểm tra property source và giá trị cuối cùng.

**Bài tập 6 — Optional và fail-fast.** Ngắt Config Server trong test. So sánh configserver: với optional:configserver: và xác định chính sách phù hợp cho production.

**Bài tập 7 — Vault.** Dùng môi trường Vault test, tạo secret theo application và profile. Import vault://, xác nhận client đọc được secret bằng workload authentication.

**Bài tập 8 — Kubernetes Secret.** Tạo ConfigMap cho URL và Secret cho password. Mount từng resource vào đúng container. Kiểm tra RBAC, encryption at rest và quyền file.

**Bài tập 9 — Property precedence.** Cố ý khai báo cùng một key trong application.yml, Config Server và Vault. Kiểm tra PropertySource nào thắng, sau đó loại bỏ sự trùng lặp để chỉ một nguồn sở hữu key.

**Bài tập 10 — Rotation.** Đổi database password ở secret store. Xác định pool có thể reload hay cần restart. Thực hiện rotation có giai đoạn chuyển tiếp và thu hồi credential cũ.

**Bài tập 11 — Rollback.** Deploy artifact digest A với config label X và secret version 1. Sau đó triển khai digest B với label Y và secret version 2. Mô phỏng lỗi và khôi phục một bộ phiên bản tương thích đã kiểm thử.

**Bài tập 12 — Kiểm tra rò rỉ.** Chạy ứng dụng với secret test, thu thập log và Actuator output. Xác nhận không có plaintext secret trong log, response hoặc metric tag.

## 23. Ghi nhớ và nguồn tra cứu

- Dùng một artifact bất biến cho nhiều môi trường; cấp profile, cấu hình và secret tại thời điểm deploy.
- Phân biệt cấu hình không nhạy cảm với credential, token và private key.
- Profile giúp chọn Config Data và bean; profile không phải ranh giới bảo mật.
- application.yml nên chứa mặc định an toàn; file profile-specific không nên chứa secret plaintext.
- spring.config.additional-location bổ sung location ngoài; spring.config.location thay thế các location mặc định.
- Configuration tree cho phép đưa file mount thành property source bằng configtree:.
- Kubernetes ConfigMap dành cho dữ liệu không bí mật; Secret dành cho dữ liệu nhạy cảm, nhưng Base64 không phải mã hóa.
- Spring Cloud Config cung cấp cấu hình theo application, profile và label; dùng label ổn định để triển khai có thể tái lập.
- Spring Cloud Vault có thể import secret backend vào Environment qua Config Data API với vault://.
- Config Server encrypted properties bảo vệ ciphertext khi lưu, nhưng server-side decryption vẫn đưa plaintext tới client.
- Secret bắt buộc cần validation và không nên có fallback mặc định.
- Rotation cần phối hợp secret source, bean/resource, refresh hoặc restart và thu hồi credential cũ.
- Rollback phải xem xét đồng thời artifact digest, config revision và secret version.
- Không log secret hoặc expose Environment/configuration qua endpoint quản trị công khai.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
3. [Spring Cloud Config – Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
4. [Spring Cloud Config – Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
5. [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
6. [Spring Cloud Vault – Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html)
7. [Spring Cloud Vault – Secret Backends](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html)
8. [Spring Cloud Vault – Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
9. [Kubernetes – Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
10. [Kubernetes – Encrypting Confidential Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
11. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
