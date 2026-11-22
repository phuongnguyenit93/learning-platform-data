# Quản lý thông tin xác thực bằng cấu hình và kho bí mật

Ứng dụng Spring Data R2DBC cần thông tin xác thực để kết nối database, thường gồm URL, username, password và đôi khi cả chứng thư TLS hoặc tùy chọn xác thực riêng của driver. Đây là cấu hình triển khai, không nên gắn cứng trong source code, file cấu hình được commit hoặc image container.

Cách tổ chức an toàn là **externalize credentials**: ứng dụng nhận cấu hình từ môi trường triển khai hoặc secret manager, sau đó Spring Boot dùng các giá trị đó để tạo ConnectionFactory. Mỗi môi trường có thể dùng database và tài khoản riêng mà không phải thay đổi mã nguồn.

Quản lý secret không chỉ là giấu password. Cần kiểm soát ai được đọc secret, quyền của tài khoản database, cách truyền secret vào process, cách xoay vòng credentials, vòng đời connection pool và cách ngăn secret xuất hiện trong log, trace, exception hoặc artifact build.

## 1. Những thông tin nào cần được bảo vệ?

Một ứng dụng R2DBC thường cần:

| Cấu hình | Ví dụ | Mức độ nhạy cảm |
|---|---|---|
| spring.r2dbc.url | r2dbc:postgresql://db.internal:5432/orders | Có thể nhạy cảm nếu URL chứa user info hoặc token |
| spring.r2dbc.username | orders_app | Thông tin nhận diện tài khoản |
| spring.r2dbc.password | Giá trị bí mật | Secret |
| TLS client private key | Nội dung khóa riêng | Secret nhạy cảm cao |
| TLS client certificate | Chứng thư client | Cần bảo vệ tính toàn vẹn |
| Trust store password | Mật khẩu trust store | Secret |
| Driver-specific token | Token xác thực | Secret |

Nhiều driver cho phép đưa username/password trực tiếp vào URL. Cách đó tiện nhưng làm tăng nguy cơ secret xuất hiện trong log, exception, metric label hoặc màn hình quản trị. Với Spring Boot, nên tách URL, username và password thành các property riêng khi driver và cấu hình cho phép.

Ví dụ URL không chứa credentials:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/orders
~~~

Các giá trị username/password có thể được cấp trực tiếp bằng environment variables SPRING_R2DBC_USERNAME và SPRING_R2DBC_PASSWORD. Không ghi giá trị thật vào file được commit.

## 2. Externalized configuration trong Spring Boot

Spring Boot có cơ chế externalized configuration: cùng một ứng dụng có thể đọc property từ YAML/properties, environment variables, system properties, command-line arguments, config tree và các property source được tích hợp.

Điều này cho phép cấu hình được bind tại một nơi:

~~~java
@ConfigurationProperties(prefix = "spring.r2dbc")
public record R2dbcConnectionSettings(
    String url,
    String username,
    String password
) {}
~~~

Hoặc để Spring Boot tự cấu hình ConnectionFactory từ namespace spring.r2dbc.*.

Không cần tự đọc file secret trong từng repository. Hãy để Spring bind cấu hình và để ConnectionFactory/driver nhận các giá trị phù hợp.

### 2.1. Dùng environment variables

Spring Boot ánh xạ property chữ thường có dấu chấm sang environment variable viết hoa, dùng dấu gạch dưới để phân tách:

| Property | Environment variable |
|---|---|
| spring.r2dbc.url | SPRING_R2DBC_URL |
| spring.r2dbc.username | SPRING_R2DBC_USERNAME |
| spring.r2dbc.password | SPRING_R2DBC_PASSWORD |
| spring.r2dbc.pool.max-size | SPRING_R2DBC_POOL_MAXSIZE |

Platform có thể cấp trực tiếp các environment variables này. Spring Boot sẽ bind chúng vào các property tương ứng mà không cần ghi credentials trong application.yml.

Environment variables tiện cho container và CI, nhưng không phải secret manager chuyên dụng. Trên một số hệ điều hành, process inspection, diagnostic dump hoặc công cụ vận hành có quyền cao có thể đọc environment của process. Với yêu cầu bảo mật cao, cân nhắc mount secret thành file hoặc dùng secret manager integration.

### 2.2. Dùng placeholder và giá trị bắt buộc

Có thể tham chiếu biến môi trường trong application.yml bằng placeholder Spring, nhưng cần bảo đảm không đặt password mặc định yếu. Nếu biến môi trường bị thiếu, ứng dụng nên fail fast thay vì âm thầm kết nối bằng một credential mặc định.

Username/password của datasource production thường là cấu hình bắt buộc. Dùng optional placeholder chỉ khi đã có nguồn dự phòng được thiết kế rõ ràng.

Không đưa giá trị secret vào ví dụ cấu hình trong repository. Nếu cần tài liệu hóa, chỉ ghi tên biến như SPRING_R2DBC_PASSWORD.

## 3. Đọc secret từ file bằng config tree

Một số nền tảng mount secret thành các file riêng. Spring Boot hỗ trợ config tree để đọc tên file làm property key và nội dung file làm giá trị.

Ví dụ thư mục secret:

~~~text
/run/secrets/
    spring.r2dbc.url
    spring.r2dbc.username
    spring.r2dbc.password
~~~

Trong application.yml:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Nếu các file tồn tại, Spring có thể đọc nội dung của chúng thành property tương ứng. Tên file spring.r2dbc.password trở thành property spring.r2dbc.password.

Khi secret bắt buộc, cân nhắc bỏ optional để ứng dụng báo lỗi nếu thư mục hoặc file không tồn tại. Dùng optional chỉ khi có nguồn cấu hình dự phòng được thiết kế rõ ràng.

Config tree hữu ích với Docker secrets, Kubernetes Secret volume hoặc secret agent ghi file. Quyền truy cập file cần được giới hạn cho user chạy ứng dụng.

### 3.1. File secret

Mỗi file chứa một giá trị, thường không cần YAML wrapper. Cần chú ý newline cuối file, encoding và file permission.

Không ghi secret vào file tạm có quyền đọc rộng. Không copy secret vào thư mục build, thư mục static hoặc artifact được publish.

### 3.2. Chọn environment variable hay file?

| Cách cấp | Phù hợp khi | Điểm cần chú ý |
|---|---|---|
| Environment variable | CI, container runtime, platform có secret injection | Có thể bị lộ qua process diagnostics hoặc dump |
| Config tree / mounted file | Docker/Kubernetes secret volume, secret agent ghi file | Cần kiểm soát file permission và cập nhật file |
| Secret manager integration | Cần audit, versioning, policy, rotation | Cần quản lý identity và quyền truy cập |
| File YAML được commit | Cấu hình không nhạy cảm | Không dùng để lưu password thật |

Các cách này có thể kết hợp. Ví dụ, application.yml giữ URL không nhạy cảm, config tree cấp username/password, còn TLS certificate được mount vào thư mục riêng.

## 4. Phân tách cấu hình theo môi trường

Local development, integration test, staging và production thường dùng database, username và password khác nhau.

Một cấu trúc hợp lý:

~~~text
src/main/resources/
    application.yml

src/test/resources/
    application-test.yml
~~~

application.yml chứa cấu hình mặc định không bí mật hoặc tên property cần bind. application-test.yml có thể chứa pool size hoặc logging riêng cho test. Credentials test được cấp từ Testcontainers hoặc secret test độc lập.

Production platform cung cấp secret riêng thông qua environment, mounted file hoặc secret manager. Không tạo một profile production có password được commit trong application-prod.yml.

### 4.1. Profile không phải kho bí mật

Profile giúp chọn nhóm cấu hình theo môi trường. Profile không mã hóa hay bảo vệ nội dung file. Một file application-prod.yml chứa password rõ vẫn là secret bị lưu trong source dù chỉ được bật ở production.

Hãy dùng profile để chọn hành vi và cấu hình không nhạy cảm; lấy credentials từ nguồn bảo mật bên ngoài.

### 4.2. Không dùng cùng credentials ở mọi môi trường

Dùng cùng một tài khoản database cho local, test, staging và production làm tăng phạm vi ảnh hưởng khi một môi trường bị lộ.

Nên tách tài khoản local developer, integration test, staging, runtime production và migration/schema administration. Tài khoản runtime thường không cần quyền tạo database, tạo role hoặc thay đổi schema.

## 5. Sử dụng secret manager

Secret manager lưu trữ và phân phối credentials với các tính năng như access policy, audit, versioning, rotation và lease. Một số lựa chọn phổ biến:

- HashiCorp Vault.
- AWS Secrets Manager hoặc AWS Systems Manager Parameter Store.
- Azure Key Vault.
- Google Cloud Secret Manager.
- Secret store do nền tảng nội bộ cung cấp.

Ứng dụng nên xác thực với secret manager bằng workload identity, service account hoặc cơ chế identity ngắn hạn của nền tảng. Tránh nhúng master token hoặc cloud access key cố định trong image.

### 5.1. Spring Cloud Vault

Spring Cloud Vault có thể tích hợp Vault với Spring Environment, để secret được cung cấp dưới dạng property source. Một cấu hình import phổ biến trong các phiên bản Spring Boot/Spring Cloud hỗ trợ Config Data là:

~~~yaml
spring:
  config:
    import: vault://
~~~

Cấu hình kết nối Vault, authentication method, secret backend và path phụ thuộc phiên bản Spring Cloud Vault và cách tổ chức Vault của hệ thống. Hãy dùng tài liệu đúng phiên bản dependency đang chạy.

Nếu KV backend cung cấp các property có tên spring.r2dbc.username và spring.r2dbc.password, Spring Boot có thể bind chúng như các property source khác. Tuy nhiên, không nên giả định mọi Vault path tự động tạo đúng namespace này; cần cấu hình mapping/path tương ứng.

### 5.2. Static secret và dynamic database credentials

Secret manager có thể lưu username/password tĩnh hoặc cấp credentials database động có lease/expiration.

**Static secret:**

- Một tài khoản database tồn tại trong thời gian dài.
- Secret manager lưu phiên bản hiện tại.
- Khi xoay vòng, password được thay đổi theo quy trình triển khai.

**Dynamic credentials:**

- Secret backend tạo username/password mới với quyền và thời hạn xác định.
- Credentials có lease và có thể hết hạn hoặc được revoke.
- Ứng dụng phải quản lý renew/reissue và vòng đời connection đang sử dụng.

Dynamic credentials giảm thời gian tồn tại của một secret bị lộ, nhưng yêu cầu tích hợp lifecycle cẩn thận. Chỉ lấy credentials một lần lúc startup rồi để connection pool sống vô thời hạn có thể khiến ứng dụng tiếp tục dùng credential đã hết hạn khi mở connection mới.

### 5.3. Identity thay cho master secret

Trên cloud hoặc Kubernetes, ưu tiên workload identity/service account để ứng dụng lấy secret với quyền giới hạn. Điều này tránh phải phân phối access key dài hạn chỉ để đọc password database.

Secret manager policy nên giới hạn path/secret được đọc, môi trường và service được phép truy cập, hành động được phép, thời gian xác thực và quyền audit. Không cấp quyền đọc toàn bộ secret store cho ứng dụng chỉ cần một database password.

## 6. Kubernetes Secret và Spring R2DBC

Kubernetes Secret có thể được expose vào Pod dưới dạng environment variable hoặc mounted volume.

Ví dụ Deployment dùng secret volume:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-service
spec:
  containers:
    - name: app
      image: example/orders-service:1.0
      volumeMounts:
        - name: db-credentials
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: db-credentials
      secret:
        secretName: orders-db-credentials
~~~

Nếu Secret chứa các key spring.r2dbc.username và spring.r2dbc.password, volume có thể tạo file tương ứng trong /run/secrets. Spring Boot import config tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Cấu hình Secret minh họa:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-db-credentials
type: Opaque
stringData:
  spring.r2dbc.username: orders_app
  spring.r2dbc.password: REPLACE_AT_DEPLOYMENT
~~~

Giá trị REPLACE_AT_DEPLOYMENT chỉ là placeholder minh họa, không phải password để dùng. Không commit secret production thực vào manifest Git. Có thể dùng External Secrets Operator, Secrets Store CSI Driver hoặc cơ chế tích hợp secret manager của nền tảng để đồng bộ secret vào Pod.

### 6.1. Kubernetes Secret không tự động là secret manager đầy đủ

Kubernetes Secret là đối tượng lưu trữ dữ liệu nhạy cảm trong cluster. Việc bảo vệ phụ thuộc cấu hình encryption at rest của etcd, RBAC, quyền node, quyền Pod, audit và cách secret được mount.

Base64 trong manifest không phải encryption. Không xem một chuỗi đã encode Base64 là password được bảo vệ.

Hãy giới hạn service account chỉ đọc tài nguyên cần thiết, tránh cấp quyền list/watch toàn bộ Secret trong namespace nếu workload chỉ cần mount một secret cụ thể.

### 6.2. Cập nhật mounted Secret không đồng nghĩa ứng dụng đã đổi credentials

Kubernetes có thể cập nhật nội dung secret volume theo cơ chế projection, nhưng ứng dụng cần đọc lại file và tái cấu hình tài nguyên sử dụng giá trị đó. Spring Boot không tự động tạo lại ConnectionFactory chỉ vì file config tree thay đổi.

Nếu secret được inject dưới dạng environment variable, giá trị trong process đang chạy không tự đổi khi Kubernetes Secret được sửa. Thường cần restart/rollout Pod hoặc dùng cơ chế reload có hỗ trợ rõ ràng.

## 7. CI/CD và secret injection

Pipeline build/test/deploy thường cần credentials để truy cập registry, database test hoặc secret manager. Cần phân biệt secret dùng trong pipeline với secret runtime của ứng dụng.

Nguyên tắc:

- Lấy secret từ CI secret store hoặc workload identity.
- Chỉ cấp secret cho job cần dùng.
- Không in secret ra stdout/stderr.
- Tắt shell tracing khi có nguy cơ lệnh chứa giá trị bí mật bị in.
- Không truyền secret qua command-line argument nếu có thể tránh vì process list hoặc log có thể lộ.
- Không lưu secret trong build artifact, cache build hoặc test report.
- Không dùng production credentials cho integration test.
- Dùng quyền tối thiểu và thời gian tồn tại ngắn.

### 7.1. Build time và runtime

Database credentials thường là runtime configuration. Không đưa chúng vào Docker build ARG hoặc ENV trong Dockerfile để tạo image. Image nên có thể triển khai ở nhiều môi trường mà không cần build lại và không chứa password.

Ví dụ Dockerfile không chứa credentials:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/orders-service.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Khi chạy container, platform cấp property qua secret environment hoặc mounted files. Một image giống nhau có thể chạy ở staging và production với secret khác nhau.

### 7.2. Secret trong pipeline log

Không dùng lệnh debug in toàn bộ environment khi pipeline có secret. Một số CI platform tự mask giá trị đã đăng ký, nhưng masking không phải bảo đảm tuyệt đối, đặc biệt khi secret được encode, cắt nhỏ hoặc biến đổi.

Không dùng URL có embedded password trong thông báo lỗi hoặc output test. Nếu cần chẩn đoán, log host, port, database name và connection state đã loại bỏ credentials.

## 8. Quyền tối thiểu cho tài khoản database

Một password được lưu an toàn vẫn không đủ nếu tài khoản có quyền quá rộng.

Tài khoản runtime của service nên chỉ có quyền cần thiết: CONNECT vào database, SELECT/INSERT/UPDATE/DELETE trên bảng service sở hữu, quyền sequence/identity cần thiết và EXECUTE trên stored procedure mà ứng dụng thực sự dùng.

Thông thường, runtime account không nên có CREATE DATABASE, CREATE ROLE, SUPERUSER, quyền truy cập bảng service khác hoặc quyền thay đổi schema trong production nếu migration dùng tài khoản riêng.

### 8.1. Tách tài khoản runtime và migration

Migration có thể cần CREATE/ALTER/DROP, trong khi ứng dụng runtime chỉ cần DML. Dùng hai tài khoản riêng:

| Tài khoản | Mục đích | Quyền điển hình |
|---|---|---|
| orders_app | Runtime R2DBC | SELECT/INSERT/UPDATE/DELETE cần thiết |
| orders_migrator | Flyway/Liquibase | DDL và quyền migration |
| orders_readonly | Reporting nếu cần | SELECT giới hạn |

Không chạy migration bằng tài khoản runtime chỉ vì tiện. Nếu ứng dụng bị compromise, quyền DDL rộng sẽ làm tăng phạm vi thiệt hại.

### 8.2. Tách theo service và database

Nếu nhiều service dùng cùng database server, không dùng chung một database user có quyền đọc/ghi toàn bộ schema nếu không cần. Tách user/schema/role theo service để giới hạn blast radius.

Credentials riêng cũng giúp audit biết thao tác đến từ service nào và thu hồi quyền của một workload mà không làm gián đoạn toàn bộ ứng dụng.

## 9. TLS và bảo vệ đường truyền

Credentials cần được bảo vệ khi truyền qua mạng. Khi R2DBC kết nối database qua network không tin cậy, cấu hình TLS theo driver và database.

- Yêu cầu TLS nếu database hỗ trợ và môi trường cần bảo vệ đường truyền.
- Xác minh certificate chain và hostname; không tắt verification chỉ để hết lỗi kết nối.
- Bảo vệ private key và trust store password như secret.
- Dùng certificate có thời hạn và quy trình gia hạn.
- Tránh cấu hình trust-all hoặc insecure mode trong production.
- Kiểm tra option TLS theo đúng R2DBC driver và version.

Cú pháp SSL mode không đồng nhất giữa PostgreSQL, MySQL, SQL Server và các R2DBC driver. Không sao chép query parameter SSL từ driver này sang driver khác. Hãy cấu hình driver-specific properties hoặc ConnectionFactoryOptions theo tài liệu của driver đang dùng.

## 10. Xoay vòng credentials

Credential rotation thay password, username hoặc token theo lịch hoặc khi có dấu hiệu bị lộ. Rotation giúp giảm thời gian một secret bị sử dụng nếu nó bị lộ, nhưng cần tránh làm ứng dụng mất kết nối giữa chừng.

Một vòng đời rotation có thể gồm:

1. Tạo credential mới hoặc cập nhật password theo chính sách database.
2. Cấp secret mới vào secret manager.
3. Cập nhật cấu hình/runtime workload.
4. Tạo connection mới bằng credential mới.
5. Xác nhận ứng dụng hoạt động với credential mới.
6. Drain/đóng connection cũ theo kế hoạch.
7. Thu hồi credential cũ sau khi không còn workload sử dụng.

### 10.1. Vì sao đổi secret chưa đủ?

R2dbcTransactionManager và ConnectionFactory sử dụng cấu hình đã được tạo khi bean khởi tạo. Với connection pool, các connection hiện có đã xác thực bằng credential cũ. Thay đổi property source không tự động:

- Rebind mọi bean đã tạo.
- Tạo lại ConnectionFactory.
- Đóng các connection đang mở.
- Cập nhật password cho các connection đã xác thực.
- Bảo đảm connection mới dùng secret mới.

Do đó, rotation phải có cơ chế reload/recreate pool hoặc rollout application instance. Cách triển khai phụ thuộc cách tạo ConnectionFactory, pool và secret provider.

### 10.2. Rotation không gián đoạn

Một cách thường dùng với database hỗ trợ nhiều user/credential là tạo tài khoản mới trước:

1. Tạo orders_app_v2 với cùng quyền tối thiểu.
2. Cấp username/password mới vào secret store.
3. Khởi động instance mới hoặc làm mới pool để dùng credential mới.
4. Kiểm tra kết nối và request thực tế.
5. Chuyển traffic hoàn toàn sang instance mới.
6. Thu hồi orders_app_v1 sau khi các connection cũ đã được drain.

Cách này tránh phải đổi password của một user đang được mọi instance sử dụng đồng thời. Nếu database hoặc policy không cho phép hai user song song, cần kế hoạch rotation có maintenance window và rollback rõ ràng.

### 10.3. Dynamic credentials có lease

Với secret manager cấp database credential ngắn hạn, ứng dụng cần quản lý lease duration, thời điểm renew, hành vi khi renew thất bại, thời gian tạo connection mới, hiệu lực của connection cũ sau revoke và cách đóng/recreate pool khi credential thay đổi.

Không đợi đến khi lease hết hạn mới lấy credential mới. Hãy renew/reissue trước expiry với khoảng đệm phù hợp. Nếu credential cũ bị revoke trong khi pool còn connection, truy vấn đang chạy có thể bị lỗi tùy database.

## 11. Connection pool và vòng đời secret

Connection pool giảm chi phí tạo kết nối bằng cách tái sử dụng connection. Điều đó cũng có nghĩa credentials được dùng ở thời điểm tạo connection có thể tồn tại lâu hơn lần đọc secret ban đầu.

Khi secret thay đổi:

- Connection đang mở có thể vẫn hoạt động cho tới khi bị đóng hoặc server revoke session.
- Connection mới cần dùng credential hiện tại.
- Pool có thể tiếp tục giữ connection cũ.
- ApplicationContext có thể giữ ConnectionFactory cũ.
- Property source mới không tự đảm bảo pool được cập nhật.

Một chiến lược rotation nên phối hợp secret provider với lifecycle của pool. Có thể rollout Pod mới để tạo ConnectionFactory/pool mới rồi drain Pod cũ; hoặc dùng pool abstraction hỗ trợ refresh có kiểm soát nếu dự án đã triển khai.

Không tự tạo một ConnectionFactory mới cho mỗi request. Việc recreate pool phải được điều phối, có giới hạn và bảo đảm connection cũ được đóng sau khi tác vụ đang chạy hoàn tất.

### 11.1. Graceful shutdown

Khi rollout instance mới:

1. Ngừng nhận request mới ở instance cũ.
2. Chờ request/transaction đang chạy hoàn tất trong giới hạn.
3. Đóng pool/ConnectionFactory cũ.
4. Xác nhận instance mới dùng credentials mới.
5. Chỉ thu hồi secret cũ sau khi không còn connection cần nó.

Graceful shutdown giúp tránh cắt ngang transaction hoặc làm request đang xử lý thất bại không cần thiết.

## 12. Nhiều R2DBC datasource và secret riêng

Ứng dụng có thể dùng nhiều ConnectionFactory. Mỗi datasource cần credentials và secret path riêng. Ví dụ, custom configuration cho Orders có thể bind các property app.datasource.orders.url, app.datasource.orders.username và app.datasource.orders.password; Billing dùng namespace app.datasource.billing.* tương ứng.

| Property | Environment variable |
|---|---|
| app.datasource.orders.url | APP_DATASOURCE_ORDERS_URL |
| app.datasource.orders.username | APP_DATASOURCE_ORDERS_USERNAME |
| app.datasource.orders.password | APP_DATASOURCE_ORDERS_PASSWORD |
| app.datasource.billing.url | APP_DATASOURCE_BILLING_URL |
| app.datasource.billing.username | APP_DATASOURCE_BILLING_USERNAME |
| app.datasource.billing.password | APP_DATASOURCE_BILLING_PASSWORD |

Spring Boot có thể bind các environment variables này vào các property tương ứng theo relaxed binding. Các tên ở bảng là tên biến, không phải giá trị literal để gán vào YAML.

Ví dụ cấu hình kiểu:

~~~java
@ConfigurationProperties(prefix = "app.datasource.orders")
public record OrdersDatabaseProperties(
    String url,
    String username,
    String password
) {}
~~~

~~~java
@ConfigurationProperties(prefix = "app.datasource.billing")
public record BillingDatabaseProperties(
    String url,
    String username,
    String password
) {}
~~~

Các property này là cấu hình ứng dụng tùy chỉnh; Spring Boot không tự dùng app.datasource.* để tạo R2DBC factory nếu không có custom configuration. Khi tạo bean, cần gắn đúng credentials, ConnectionFactory, template/repository và transaction manager.

Tách secret giúp rotation hoặc revoke một datasource không ảnh hưởng trực tiếp tài khoản của datasource khác.

## 13. Tránh rò rỉ credentials trong log và diagnostics

Secret có thể bị lộ ngoài source code:

- Log URL kết nối có embedded username/password.
- In toàn bộ Environment hoặc System.getenv().
- Log exception chứa connection string.
- Ghi request/response có token.
- Đưa secret vào metric label hoặc tracing baggage.
- Để test failure dump chứa config object.
- Commit file .env, application-local.yml hoặc IDE run configuration.
- Đưa secret vào Docker build ARG, image layer hoặc build cache.
- Chia sẻ heap dump hoặc support bundle có cấu hình runtime.

### 13.1. Log an toàn

Nếu cần log thông tin kết nối, chỉ log các thành phần không nhạy cảm đã được kiểm soát, chẳng hạn database host, port, database name và datasource alias. Không log password, token, private key hoặc URL chứa credentials.

Không log toàn bộ object chứa username/password bằng toString() nếu record hoặc generated toString có thể hiển thị secret.

### 13.2. Exception và actuator

Một số endpoint diagnostics có thể hiển thị configuration properties hoặc environment. Giới hạn quyền truy cập Actuator, không expose endpoint env/configprops rộng ra internet và dùng sanitization cho các property nhạy cảm.

Không bật debug logging của driver hoặc connection factory trong production nếu chưa hiểu dữ liệu nào sẽ được ghi. Nếu cần debug tạm thời, giới hạn thời gian, phạm vi và quyền truy cập log.

### 13.3. File và repository

Thêm pattern vào .gitignore chỉ giúp ngăn một số file local bị add vô tình; nó không xóa secret đã commit trước đó và không bảo vệ file được tạo trong build artifact.

Nếu secret đã bị commit, hãy coi như đã lộ: rotate/revoke credential trước, sau đó xử lý lịch sử Git và các bản sao theo quy trình của tổ chức. Xóa dòng khỏi commit mới không làm credential cũ trở nên an toàn.

## 14. Local development và integration test

Developer cần chạy ứng dụng local mà không phải dùng production secret. Có thể dùng PostgreSQL container với user/password throwaway, file config local nằm ngoài Git, environment variables do IDE hoặc shell cấp, secret store dành riêng cho developer hoặc Testcontainers tạo database riêng cho integration test.

Không commit giá trị thật vào application-local.yml. Nếu file local chứa secret, giữ file ngoài version control và giới hạn quyền truy cập trên máy.

Với Testcontainers, có thể dùng @DynamicPropertySource để đăng ký URL/credentials từ container trong test context. Đây là credentials test tạm thời, không liên quan đến secret production.

### 14.1. Dùng tài khoản test quyền tối thiểu

Integration test có thể chạy migration, truncate hoặc reset schema. Hãy dùng database test cô lập với quyền chỉ trong database/schema đó. Không tái sử dụng production username/password chỉ để test chạy được.

## 15. Khi secret không thể truy cập

Ứng dụng cần có chính sách rõ ràng khi secret manager hoặc file secret không khả dụng.

Với credentials bắt buộc để kết nối database, thường nên fail fast khi khởi động nếu không lấy được secret. Khởi động ứng dụng trong trạng thái nửa hoạt động có thể làm request lỗi liên tục và khó phát hiện cấu hình sai.

Với secret rotation khi ứng dụng đang chạy, có thể giữ credential hiện tại trong khoảng thời gian ngắn nếu lease còn hiệu lực, đồng thời retry lấy secret mới theo backoff. Nhưng không tiếp tục vô hạn bằng credential đã hết hạn hoặc đã bị revoke.

Không ghi giá trị secret ra log khi báo lỗi. Chỉ ghi tên secret/path đã được làm sạch, datasource alias, thời điểm lỗi và mã lỗi từ provider nếu an toàn.

## 16. Kiểm thử và vận hành rotation

Quản lý secret cần được kiểm tra như một phần của vòng đời ứng dụng.

Các tình huống kiểm thử/vận hành có thể gồm:

- Thiếu username/password bắt buộc làm ứng dụng khởi động thất bại rõ ràng.
- Môi trường test dùng credentials riêng, không lấy nhầm production secret.
- ConnectionFactory được tạo từ property source mong muốn.
- Secret có ký tự đặc biệt không bị cắt hoặc parse sai.
- TLS xác minh certificate/hostname đúng.
- User runtime không có quyền DDL/quản trị không cần thiết.
- Secret version mới được cấp và instance mới kết nối thành công.
- Pool cũ được drain/close sau khi rollout.
- Secret cũ được revoke sau khi không còn workload sử dụng.
- Secret manager unavailable có hành vi đã định nghĩa.
- Log, trace và exception không chứa password/token.
- Nhiều datasource dùng đúng secret riêng.

Không in secret ra test assertion hoặc report. Khi cần chứng minh cấu hình đúng, hãy xác nhận connection thành công và datasource alias thay vì so sánh rồi in password.

## 17. Quy trình thiết kế credentials cho một ứng dụng R2DBC

1. Xác định từng database và ConnectionFactory mà ứng dụng sử dụng.
2. Tạo database user riêng cho từng service/datasource.
3. Cấp quyền tối thiểu theo thao tác runtime.
4. Tách tài khoản runtime khỏi tài khoản migration.
5. Giữ URL và cấu hình không nhạy cảm trong application config.
6. Cấp username/password qua environment, config tree hoặc secret manager.
7. Dùng workload identity để xác thực với secret manager khi có thể.
8. Bảo vệ kết nối bằng TLS và xác minh certificate.
9. Xác định TTL/lease và lịch rotation.
10. Thiết kế cách refresh hoặc recreate ConnectionFactory/pool khi secret thay đổi.
11. Drain connection cũ trước khi revoke credential cũ.
12. Giới hạn quyền đọc secret và bật audit.
13. Ngăn secret xuất hiện trong log, trace, image và repository.
14. Kiểm thử thiếu secret, rotation, pool lifecycle và outage.
15. Theo dõi lỗi xác thực và trạng thái secret lease mà không log giá trị bí mật.

## 18. Những lỗi thường gặp

**Ghi password trực tiếp trong application.yml.** File có thể được commit hoặc đóng gói vào image. Dùng externalized configuration.

**Cho rằng Base64 là mã hóa.** Base64 chỉ là encoding. Dùng secret manager hoặc cơ chế secret storage được bảo vệ.

**Dùng cùng credentials ở mọi môi trường.** Một secret bị lộ có thể ảnh hưởng production. Tách tài khoản và secret theo môi trường.

**Dùng tài khoản database quyền quản trị cho ứng dụng.** Runtime service có thể bị chiếm quyền và thay đổi schema hoặc dữ liệu rộng hơn cần thiết. Dùng least privilege.

**Đưa credentials vào URL rồi log URL.** Password có thể xuất hiện trong log và diagnostics. Tách username/password thành property riêng.

**Đổi secret store nhưng không refresh pool.** ConnectionFactory và pool có thể giữ cấu hình cũ. Cần rollout hoặc cơ chế refresh lifecycle có kiểm soát.

**Revoke password cũ quá sớm.** Instance cũ có thể vẫn mở connection hoặc chưa nhận secret mới. Xác nhận rollout và drain trước khi revoke.

**Dùng environment variables như thể chúng không thể bị lộ.** Process diagnostics và dump có thể chứa environment. Dùng mounted secret/config tree hoặc secret integration khi phù hợp.

**Dùng production secret trong CI/test.** Test có thể xóa dữ liệu hoặc chạy migration. Dùng database và credentials test cô lập.

**Không tách migration user.** Runtime account có quyền DDL không cần thiết. Dùng migration identity riêng.

**Nuốt lỗi secret provider rồi dùng password cũ vô thời hạn.** Có thể tiếp tục bằng credential đã hết hạn hoặc bị revoke. Định nghĩa lease và fallback rõ ràng.

## 19. Nguyên tắc thiết kế

- Không hard-code credentials trong source code, file được commit hoặc Docker image.
- Dùng Spring Boot externalized configuration để bind R2DBC URL, username và password.
- Ưu tiên secret manager hoặc mounted config tree cho credentials nhạy cảm.
- Dùng environment variables khi platform phù hợp, nhưng hiểu rủi ro process diagnostics.
- Dùng workload identity thay cho master key dài hạn khi có thể.
- Tách secret theo môi trường, service và datasource.
- Tách runtime database user khỏi migration/admin user.
- Áp dụng least privilege và audit secret access.
- Bảo vệ kết nối database bằng TLS với certificate verification.
- Không log URL chứa credentials, password, token hoặc private key.
- Không giả định secret rotation tự cập nhật ConnectionFactory hoặc connection pool.
- Phối hợp rotation với pool refresh/recreation, rollout và graceful shutdown.
- Với dynamic credentials, theo dõi lease và renew trước expiry.
- Dùng credentials throwaway và database cô lập cho test.
- Kiểm thử cả khởi động, xác thực, rotation, revoke và secret-provider outage.

## 20. Ghi nhớ

Thông tin xác thực R2DBC nên được cấp từ bên ngoài ứng dụng và bind qua Spring Boot configuration. Environment variables, config tree, Kubernetes Secret và secret manager là các cách phân phối khác nhau; lựa chọn phụ thuộc nền tảng, yêu cầu audit, rotation và mức bảo vệ cần thiết. Không lưu password trong source, image hoặc log, và không dùng một tài khoản quyền cao cho mọi service.

Rotation phải tính đến ConnectionFactory và connection pool: thay đổi secret source không tự làm connection đã tạo dùng credentials mới. Hãy cấp credential mới, refresh/rollout pool, xác nhận kết nối, drain connection cũ rồi mới revoke credential cũ. Kết hợp least privilege, TLS, identity ngắn hạn, audit và test cô lập để giảm nguy cơ lộ secret và giới hạn tác động khi một credential bị xâm phạm.

