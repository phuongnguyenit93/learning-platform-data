# Service binding và ánh xạ thông tin kết nối do nền tảng cung cấp

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối các dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud, SDK và connector tương ứng. Khi triển khai lên Kubernetes, Cloud Foundry hoặc một nền tảng application khác, ứng dụng thường không tự tạo credential hay endpoint. Nền tảng hoặc service broker cấp thông tin kết nối, rồi đưa thông tin đó vào workload qua environment variables, secret volume, binding directory hoặc metadata riêng.

**Service binding** là cách nền tảng gắn một ứng dụng với một instance dịch vụ và cung cấp thông tin cần thiết để ứng dụng sử dụng dịch vụ đó. Thông tin có thể gồm host, port, database name, username, password, URI, certificate, topic, queue, resource identifier hoặc metadata. Ứng dụng cần ánh xạ các giá trị này vào cấu hình Spring Boot và khởi tạo client tương ứng.

**Spring Cloud Bindings** hỗ trợ ứng dụng Spring tiêu thụ service binding theo các convention của nền tảng như Kubernetes Service Binding Specification và Cloud Foundry `VCAP_SERVICES`. Thư viện giúp đưa thông tin binding vào Spring Environment theo các mapping được hỗ trợ. Nó không tạo service, không cấp IAM role và không tự biến mọi managed cloud service thành một kết nối chuẩn hóa.

Trong môi trường AWS, Azure và Google Cloud, nhiều dịch vụ dùng workload identity thay vì username/password tĩnh. Ví dụ ứng dụng có thể nhận tên bucket/queue từ deployment, sau đó dùng IAM role, Managed Identity hoặc Workload Identity để gọi API. Service binding cung cấp endpoint/resource metadata; identity provider xác thực quyền truy cập. Hai cơ chế này bổ trợ nhau.

Sau bài học, bạn có thể:

1. Giải thích service binding, service instance, service broker và binding credentials.
2. Phân biệt Kubernetes Service Binding Specification, Cloud Foundry `VCAP_SERVICES` và cấu hình environment/secret thông thường.
3. Cấu hình Spring Cloud Bindings để ánh xạ binding data vào Spring Boot.
4. Thiết kế cấu trúc binding directory, metadata và secret files.
5. Ánh xạ database, messaging, storage và endpoint của AWS, Azure, Google Cloud.
6. Kết hợp service binding với workload identity và least privilege.
7. Quản lý property precedence, profile, rotation, refresh và lỗi binding.
8. Kiểm thử binding local, CI, Kubernetes/Cloud Foundry staging và managed service.
9. Vận hành binding an toàn qua audit, permission, monitoring và runbook.

> **Phạm vi:** Service binding là contract giữa platform và application. Khả năng provision/bind, format metadata, refresh và identity phụ thuộc nền tảng, service broker, operator và phiên bản thư viện. Không giả định mọi AWS/Azure/GCP service đều có binding provider chuẩn hoặc được Spring Cloud Bindings tự động nhận diện.

## 2. Service binding giải quyết vấn đề gì?

### 2.1. Tách provisioning khỏi application

Một ứng dụng cần kết nối PostgreSQL managed. Nếu tự hard-code hostname, username và password vào file YAML, mỗi môi trường phải chỉnh source hoặc đóng image riêng. Khi platform cấp một database instance, platform có thể tạo binding chứa endpoint và credential, rồi gắn binding vào workload.

Quy trình khái quát:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / Operator
    participant Platform as Platform / Service Broker
    participant Service as Managed Service
    participant App as Spring Boot App

    Dev->>Platform: Provision service instance
    Platform->>Service: Create database / queue / storage
    Service-->>Platform: Resource endpoint and access details
    Dev->>Platform: Bind service to application
    Platform->>Platform: Create binding metadata / secret
    Platform->>App: Mount binding or inject environment
    App->>App: Map binding data to Spring properties
    App->>Service: Connect using credential or workload identity
~~~

Application image không cần biết database của môi trường production có hostname nào. Platform chịu trách nhiệm cấp thông tin kết nối; application chịu trách nhiệm đọc contract, validate và sử dụng đúng thông tin.

### 2.2. Các khái niệm

- **Service offering/catalog:** loại dịch vụ nền tảng có thể provision, ví dụ PostgreSQL, Redis, RabbitMQ hoặc object storage.
- **Service instance:** một tài nguyên đã được provision, ví dụ database `reservation-db-prod`.
- **Service broker/operator:** thành phần thực hiện provision, bind, unbind và có thể quản lý lifecycle tài nguyên.
- **Binding:** liên kết một application/workload với service instance.
- **Binding data/credentials:** thông tin endpoint, username, password, certificate, URI hoặc metadata được cấp cho workload.
- **Consumer application:** ứng dụng đọc binding và tạo client connection.
- **Unbind/deprovision:** gỡ liên kết hoặc xóa tài nguyên theo lifecycle của platform; hai thao tác này không nhất thiết giống nhau.

Một service instance có thể có nhiều binding, ví dụ một database được bind tới nhiều application. Mỗi binding có thể có credential riêng để dễ thu hồi và audit. Không nên chia sẻ một credential quản trị database cho mọi workload.

### 2.3. Service binding không phải service discovery

Service discovery giúp tìm địa chỉ instance/service tại runtime, thường qua DNS, registry hoặc control plane. Service binding thường cung cấp một bộ metadata/credential gắn với một workload hoặc deployment.

Hai khái niệm có thể kết hợp:

- Binding cấp hostname, port, database và credential.
- DNS/service discovery giải quyết hostname thành địa chỉ network.
- Workload identity cấp token hoặc quyền truy cập API.
- SDK/client sử dụng endpoint và credential để kết nối.

Nếu chỉ có hostname nhưng không có authorization, kết nối vẫn có thể bị từ chối. Nếu có token nhưng endpoint sai, request cũng không thành công.

### 2.4. Service binding và Spring Boot ServiceConnection

Spring Boot `@ServiceConnection` và Testcontainers hỗ trợ tự cấu hình connection details cho service dùng trong development/test. Đây là cơ chế kết nối trong vòng đời test/development, không phải Kubernetes Service Binding Specification hoặc Cloud Foundry service broker binding.

| Cơ chế | Mục tiêu | Nguồn thông tin |
| --- | --- | --- |
| Platform service binding | Cấp thông tin kết nối cho workload đã deploy | Service broker/operator/platform |
| Spring Cloud Bindings | Đọc binding data và ánh xạ vào Spring Environment | Binding directory hoặc `VCAP_SERVICES` |
| Spring Boot `@ServiceConnection` | Tự tạo connection details cho service test/dev | Testcontainers hoặc Docker Compose integration |
| Environment variables | Truyền cấu hình deployment đơn giản | Container runtime/orchestrator |
| Config tree | Nạp file key-value, thường dùng mounted secret/config | Filesystem mount |

Không dùng `@ServiceConnection` để thay thế binding trong production. Ngược lại, không cần triển khai service broker chỉ để chạy PostgreSQL Testcontainer trong unit/integration test.

## 3. Các contract service binding phổ biến

### 3.1. Kubernetes Service Binding Specification

Kubernetes Service Binding Specification định nghĩa một cách biểu diễn binding data trong filesystem để ứng dụng có thể đọc thống nhất. Một service binding thường được mount thành một thư mục con bên dưới binding root. Environment variable `SERVICE_BINDING_ROOT` chỉ ra đường dẫn root.

Ví dụ cấu trúc:

~~~text
/bindings/
  reservation-db/
    type
    provider
    name
    host
    port
    database
    username
    password
    ca.crt
  reservation-cache/
    type
    provider
    name
    uri
    host
    port
~~~

Mỗi file thường chứa một giá trị. Metadata nhận diện binding có thể gồm `type`, `provider`, `name`, `version`, `tags` hoặc thông tin khác tùy specification/provider. Dữ liệu kết nối như host, port, username, password hoặc certificate nằm trong file riêng.

Trong Kubernetes, Service Binding Operator hoặc thành phần tương thích có thể tạo binding từ resource/service và mount secret vào pod. Cách khai báo CRD, tên secret và operator behavior phụ thuộc implementation; không giả định mọi cluster đều cài operator.

Ví dụ deployment nhận binding root:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: reservation-service
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/reservation-service:1.0
          env:
            - name: SERVICE_BINDING_ROOT
              value: /bindings
          volumeMounts:
            - name: service-bindings
              mountPath: /bindings
              readOnly: true
      volumes:
        - name: service-bindings
          projected:
            sources:
              - secret:
                  name: reservation-db-binding
                  items:
                    - key: type
                      path: reservation-db/type
                    - key: host
                      path: reservation-db/host
                    - key: port
                      path: reservation-db/port
                    - key: username
                      path: reservation-db/username
                    - key: password
                      path: reservation-db/password
~~~

Đây là ví dụ minh họa volume projection. Với operator thật, resource binding và mount thường được operator tạo; không nhất thiết tự viết projected volume như trên. Secret phải mount read-only và chỉ tới container cần sử dụng.

### 3.2. Cloud Foundry VCAP_SERVICES

Cloud Foundry cung cấp binding data trong environment variable `VCAP_SERVICES`, thường là JSON được nhóm theo service label. Một cấu trúc minh họa:

~~~json
{
  "postgresql": [
    {
      "name": "reservation-db",
      "label": "postgresql",
      "tags": ["relational", "database"],
      "plan": "standard",
      "credentials": {
        "hostname": "db.internal",
        "port": 5432,
        "database": "reservation",
        "username": "reservation_app",
        "password": "injected-at-runtime"
      }
    }
  ],
  "redis": [
    {
      "name": "reservation-cache",
      "label": "redis",
      "credentials": {
        "uri": "rediss://cache.internal:6379"
      }
    }
  ]
}
~~~

Platform tạo JSON khi bind service vào application. Ứng dụng không nên tự viết `VCAP_SERVICES` vào image hoặc commit JSON có credential vào repository. Local development có thể dùng fixture giả lập với credential test.

Cloud Foundry cũng có thể cung cấp `VCAP_APPLICATION` chứa metadata về application/instance. Đây là metadata runtime, không thay thế `VCAP_SERVICES` và không phải nơi lưu secret tùy ý.

### 3.3. Binding directory và config tree không giống nhau hoàn toàn

Spring Boot ConfigData hỗ trợ `configtree:` để nạp một thư mục file key-value thành property source. Ví dụ:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Cơ chế này phù hợp với mounted secret/config directory có cấu trúc phẳng. Kubernetes Service Binding directory thường chứa nhiều thư mục binding và metadata `type/provider/name`; chỉ import binding root như một config tree không tự động tạo ra semantic mapping của từng binding.

Dùng Spring Cloud Bindings khi muốn đọc service binding contract. Dùng ConfigTree khi platform chỉ mount file config/secret theo quy ước key-value mà application đã định nghĩa. Có thể kết hợp hai cơ chế nếu mỗi nguồn có owner và precedence rõ.

### 3.4. Binding data nên có cấu trúc và metadata

Một binding tốt cần cho consumer biết:

- Binding thuộc service type nào (`postgresql`, `redis`, `rabbitmq`, `s3`...).
- Provider hoặc platform nào tạo binding.
- Tên service instance hoặc logical resource.
- Endpoint và protocol.
- Credential hoặc cách lấy credential.
- Certificate/trust material nếu cần TLS.
- Version/plan/tags nếu application cần lựa chọn behavior.
- Hạn sử dụng/rotation reference nếu platform cung cấp.

Không tự suy ra loại dịch vụ chỉ từ tên thư mục hoặc `name`. Hai service cùng tên có thể là database và cache; dùng `type`/metadata theo contract.

## 4. Spring Cloud Bindings trong ứng dụng Spring Boot

### 4.1. Thư viện làm gì?

Spring Cloud Bindings cung cấp auto-configuration để đọc binding do platform cung cấp và tạo các property phù hợp cho Spring Boot. Với các service type và format được hỗ trợ, thư viện có thể ánh xạ dữ liệu binding vào cấu hình mà Spring ecosystem hiểu, ví dụ datasource hoặc messaging connection.

Luồng xử lý khái quát:

1. Ứng dụng khởi động và phát hiện binding root hoặc platform environment.
2. Thư viện đọc các binding directory/metadata.
3. Binding type/provider được nhận diện.
4. Thông tin kết nối được chuyển thành property source.
5. Spring Boot auto-configuration dùng property để tạo datasource/client.
6. Ứng dụng dùng bean đã cấu hình để truy cập managed service.

Spring Cloud Bindings không provision tài nguyên, không tự cấp IAM policy và không đảm bảo mọi custom service type có mapper sẵn. Nếu service không được nhận diện hoặc mapping mặc định không phù hợp, cần cấu hình thủ công hoặc viết integration adapter riêng.

### 4.2. Dependency và compatibility

Dependency Maven thường có dạng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-bindings</artifactId>
</dependency>
~~~

Quản lý version qua Spring Cloud BOM tương thích với Spring Boot đang dùng. Kiểm tra release notes để xác nhận hỗ trợ binding specification, Cloud Foundry, các service mapper và property behavior. Không chọn version mới nhất độc lập với release train.

Một ứng dụng chỉ cần Spring Cloud Bindings khi platform thực sự cung cấp service binding theo contract thư viện hỗ trợ. Nếu ứng dụng chỉ nhận một vài environment variables, `@ConfigurationProperties` có thể đơn giản và dễ kiểm soát hơn.

### 4.3. Khởi tạo typed properties sau khi binding được nạp

Ví dụ application service dùng Spring Boot datasource:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ReservationRepository {

    private final JdbcTemplate jdbcTemplate;

    public ReservationRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countReservations() {
        return jdbcTemplate.queryForObject(
                "select count(*) from reservations",
                Integer.class);
    }
}
~~~

Nếu binding mapper cung cấp các property datasource được Spring Boot nhận diện, auto-configuration có thể tạo `DataSource` và `JdbcTemplate`. Application repository không cần đọc binding file hoặc parse JSON platform.

Ví dụ typed config cho resource metadata riêng:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.NotBlank;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageBindingProperties(
        @NotBlank String bucket,
        @NotBlank String region,
        String endpoint) {
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Với credential, không đưa password vào custom property object nếu SDK có thể dùng workload identity/default credential provider.

### 4.4. Kiểm tra binding thực tế khi khởi động

Không log toàn bộ binding object. Có thể log các thuộc tính không nhạy cảm như binding type, logical service name, provider và trạng thái resolved; mask endpoint nếu topology bị hạn chế. Kiểm tra property binding qua actuator trong management plane được bảo vệ, nhưng không expose secret values.

Nếu app khởi động mà không tìm thấy binding, quyết định rõ:
- Service bắt buộc: fail startup với lỗi dễ hiểu.
- Service tùy chọn: disable feature hoặc dùng implementation local/test đã được cấu hình.
- Không fallback sang production hostname/password hard-code.
- Không tạo credential giả hoặc quyền rộng hơn để "cho app chạy".

### 4.5. Binding type và mapper

Spring Cloud Bindings có thể hỗ trợ mapping cho một số service phổ biến tùy version. Cần xác minh type/tag/metadata convention mà mapper nhận diện. Không suy ra `type` phải là tên vendor hoặc tên SDK. Ví dụ `postgresql` mô tả loại service; `provider` có thể chỉ broker/platform tạo binding.

Nếu binding có type không được hỗ trợ, app vẫn có thể đọc raw binding bằng custom integration, nhưng phải chịu trách nhiệm parse, validate, tạo property và bảo vệ secret. Không sửa binding secret trên filesystem để ép mapper nhận diện.
## 5. Ánh xạ binding vào Spring Boot properties

### 5.1. Từ binding data tới connection properties

Service binding thường chứa dữ liệu ở dạng trung lập với framework. Spring Boot auto-configuration lại cần property cụ thể để tạo client. Mapping layer có nhiệm vụ chuyển đổi giữa hai mô hình.

Ví dụ binding database có:

~~~text
type=postgresql
host=db.internal
port=5432
database=reservation
username=reservation_app
password=<secret>
~~~

Ứng dụng có thể cần các property datasource:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/reservation
    username: reservation_app
    password: <resolved-secret>
~~~

Giá trị password phải được đọc từ secret file/secret store ở runtime. Không ghi literal placeholder hoặc password thật vào source. Nếu binding cung cấp URI hoàn chỉnh, mapper có thể dùng URI theo contract; vẫn phải kiểm tra TLS options, database name và encoding.

### 5.2. Mapping database

| Binding data | Spring Boot property/connection detail |
| --- | --- |
| host, port, database | Tạo JDBC URL hoặc R2DBC URL |
| username | `spring.datasource.username` |
| password | `spring.datasource.password` |
| URI/JDBC URL | `spring.datasource.url` |
| TLS CA/certificate | SSL/truststore property hoặc client configuration |
| pool size/timeout | Hikari/R2DBC pool settings theo policy ứng dụng |

Không giả định mọi mapper đều tạo đúng JDBC URL cho mọi database driver. Kiểm tra scheme, SSL mode, timezone, query parameters và driver dependency. Với R2DBC, dùng property prefix và driver tương ứng thay vì tái sử dụng JDBC URL.

Ví dụ application code chỉ inject datasource:

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DatabaseAccessConfiguration {

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

Ứng dụng không cần parse binding directory trong repository hoặc controller. Giữ mapping ở startup/configuration boundary để domain/application code không phụ thuộc platform contract.

### 5.3. Mapping messaging

Binding cho RabbitMQ/Kafka có thể chứa broker host, port, vhost, username, password, TLS certificate hoặc bootstrap servers. Các property cần thiết phụ thuộc binder:

- Rabbit binder: addresses, virtual host, username/password, SSL và queue/exchange options.
- Kafka binder: bootstrap servers, security protocol, SASL mechanism, truststore và topic/group config.
- Cloud-native messaging: project/namespace, topic/queue/subscription và identity provider.

Không dùng một property generic như `uri` rồi giả định mọi binder diễn giải giống nhau. Nếu có nhiều broker, định danh từng binding bằng type/name/provider và gắn rõ với destination/binder cần sử dụng.

### 5.4. Mapping object storage

Spring Cloud Bindings có thể không có mapper mặc định cho bucket/container của mọi provider. Một binding custom có thể cung cấp metadata không nhạy cảm:

~~~text
type=object-storage
provider=aws
bucket=rental-documents-prod
region=ap-southeast-1
~~~

Ứng dụng bind metadata vào type riêng:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record ObjectStorageProperties(
        String provider,
        String bucket,
        String region,
        String endpoint) {
}
~~~

Client AWS SDK dùng credential provider chain của runtime; bucket và Region là resource config. Không cần đặt access key/secret key vào binding nếu workload đã có IAM role.

### 5.5. Custom binding mapper

Khi service type chưa được Spring Cloud Bindings hỗ trợ, có thể tạo integration adapter nhỏ:

1. Đọc binding root từ environment theo contract platform.
2. Duyệt từng binding directory và parse metadata.
3. Chọn binding theo type/provider/name rõ ràng.
4. Validate required keys, URI scheme, port range và certificate.
5. Chuyển thành typed properties hoặc property source.
6. Tạo client qua Spring configuration bean.
7. Mask secret trong exception/log và không ghi credential vào disk.

Không viết custom mapper trong controller/service nghiệp vụ. Không chọn binding đầu tiên nếu có nhiều binding cùng type; dùng logical name hoặc explicit selection để tránh kết nối nhầm service.

### 5.6. Ví dụ custom binding reader đơn giản

Đoạn minh họa dưới đây đọc một binding directory theo tên đã cấu hình. Nó không thay thế đầy đủ parser/spec validation của Spring Cloud Bindings:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public final class BindingFiles {

    private final Path root;

    public BindingFiles(Path root) {
        this.root = root;
    }

    public Optional<String> read(
            String bindingName, String key) throws IOException {
        Path file = root.resolve(bindingName).resolve(key).normalize();

        if (!file.startsWith(root.normalize()) || !Files.isRegularFile(file)) {
            return Optional.empty();
        }

        return Optional.of(Files.readString(file).trim());
    }
}
~~~

Trong production, canonicalize root/path và kiểm soát symlink để ngăn path traversal. Chỉ cho phép binding name/key từ allow-list cấu hình tin cậy; không nhận path tùy ý từ HTTP request. Đọc secret file chỉ khi cần, không giữ nội dung secret trong debug message.

## 6. Kết hợp service binding với AWS

### 6.1. AWS không có một service binding contract chung cho mọi dịch vụ

AWS managed services thường được truy cập qua AWS API và AWS SDK. Credential thường đến từ IAM role/credential provider chain. Tùy runtime, workload có thể dùng ECS task role, EKS Pod Identity/IRSA hoặc EC2 instance profile.

Binding/platform metadata có thể cung cấp:
- Region.
- Resource identifier như bucket, queue URL, topic ARN hoặc database endpoint.
- Database name và connection options.
- Secret ARN/reference nếu service dùng password.
- Endpoint override cho local/test hoặc private endpoint.

Nó không nên chứa static AWS access key nếu runtime identity có thể cấp quyền trực tiếp.

### 6.2. RDS/Aurora database

Với RDS/Aurora dùng username/password, binding có thể cung cấp endpoint, port, database, username và secret reference/password. Mapper tạo JDBC URL và datasource properties. Workload role cần quyền đọc secret/KMS nếu password được lưu ở Secrets Manager.

Nếu dùng IAM database authentication, application cần tạo authentication token theo thời hạn ngắn qua AWS SDK; token không phải password tĩnh để lưu lâu trong binding. Datasource/connection pool cần hỗ trợ cấp token mới khi tạo connection. Xác minh driver, token lifecycle và pool integration.

### 6.3. S3 object storage

Binding cho S3 nên cung cấp bucket và Region; endpoint override chỉ dùng khi cần. AWS SDK dùng role của workload để ký request. Policy nên giới hạn bucket/prefix và operation như GetObject/PutObject. Không đặt access key/secret key vào file binding khi IAM role đã có.

### 6.4. SQS, SNS và EventBridge

Binding có thể cung cấp queue URL/name, topic ARN, event bus name và Region. Ứng dụng dùng AWSpring hoặc AWS SDK v2. Role chỉ cần quyền SendMessage/ReceiveMessage/DeleteMessage, Publish hoặc PutEvents tương ứng. Nếu binding chứa queue URL, vẫn cần kiểm tra account/Region và quyền; URL không phải credential.

EventBridge PutEvents có thể trả lỗi theo từng entry; adapter phải kiểm tra partial failure. Không coi một HTTP response thành công là mọi event đã được publish.

### 6.5. EKS và Kubernetes binding

Nếu ứng dụng chạy trên EKS, Kubernetes Service Binding Operator hoặc Secret volume có thể đưa resource metadata vào pod. AWS workload identity vẫn là lớp xác thực. Service binding không tự tạo IAM role association hoặc cấp quyền S3/SQS. Cấu hình ServiceAccount, Pod Identity/IRSA và IAM policy độc lập với binding directory.
## 7. Kết hợp service binding với Azure

### 7.1. Azure managed services và identity

Azure workload có thể dùng Managed Identity trên Azure-hosted compute hoặc Workload Identity khi chạy AKS. Service binding có thể cấp endpoint, namespace, database, container hoặc resource identifier; DefaultAzureCredential/credential provider lấy token theo identity runtime.

Nếu provider/platform tạo binding chứa connection string có SAS key/password, xử lý nó như secret. Với service hỗ trợ Entra ID authentication, ưu tiên identity-based auth khi phù hợp và có role assignment đúng scope.

### 7.2. Azure Database for PostgreSQL

Binding có thể cung cấp hostname, port, database, username và password hoặc chỉ connection endpoint khi dùng Entra ID authentication. Spring datasource nhận JDBC URL/username/password theo driver. Nếu dùng Entra ID token, cần cơ chế lấy token và làm mới khi connection mới được tạo; không coi access token là password dài hạn.

### 7.3. Blob Storage

Binding nên cung cấp account endpoint và container name. Managed Identity cần role data-plane phù hợp như quyền đọc/ghi blob ở scope container/account. Azure SDK dùng credential provider; không cần lưu account key nếu identity được cấp quyền.

### 7.4. Service Bus và Event Hubs

Binding có thể cung cấp namespace endpoint, queue/topic hoặc event hub name và consumer group. Managed Identity cần quyền sender/receiver hoặc role phù hợp trên entity/namespace. Nếu dùng SAS connection string, bảo vệ như secret và có quy trình rotate. Event Hubs partition/checkpoint semantics vẫn do service quyết định; binding chỉ đưa metadata/connection info.

### 7.5. AKS và Secret Store CSI

Trong AKS, binding directory có thể được tạo từ Kubernetes Secret hoặc operator tương thích. Secret Store CSI Driver với provider Azure có thể mount secret từ Key Vault. Đây là hai cách cung cấp file/runtime secret khác nhau; chọn theo platform contract và lifecycle. Không giả định mount CSI tự tạo cấu trúc Service Binding Specification nếu không có adapter/operator chuyển đổi.

## 8. Kết hợp service binding với Google Cloud

### 8.1. GCP workload identity và resource metadata

Trên GKE, dùng Workload Identity Federation for GKE; trên Cloud Run, gắn service identity cho service. Service binding hoặc deployment config có thể cấp project ID, bucket, topic, subscription, database instance connection name và endpoint. ADC/Google credential provider lấy credential từ workload identity.

Binding không nên chứa service account JSON key khi workload identity đã được cấu hình. IAM role cần giới hạn theo resource và operation.

### 8.2. Cloud SQL

Binding có thể cung cấp instance connection name, database, username và secret reference. Với Cloud SQL connector/auth proxy, ứng dụng cần instance identifier và identity có quyền connect; database user/authentication là lớp riêng. Nếu dùng TCP host/port trực tiếp, cần bảo vệ network path, TLS và credential.

Không nhầm quyền Cloud SQL Client với quyền đăng nhập database. Identity có thể được phép mở kết nối nhưng vẫn cần database user hoặc IAM database authentication phù hợp.

### 8.3. Cloud Storage

Binding có thể cung cấp bucket name/project ID. Workload identity cần quyền data-plane tối thiểu trên bucket. Google Cloud Storage client dùng ADC; không lưu service account key trong binding. Endpoint override chỉ dùng cho emulator/test hoặc môi trường đặc biệt.

### 8.4. Pub/Sub

Binding có thể cung cấp project ID, topic và subscription. Publisher cần quyền publish trên topic; subscriber cần quyền consume subscription. Workload identity cấp token. Ack deadline, ordering key, retry và dead-letter policy là cấu hình của subscription; không được suy ra từ binding name.

### 8.5. GKE Secret volumes và Secret Manager CSI

GKE có thể mount Kubernetes Secret hoặc tích hợp Secret Manager thông qua CSI/provider. Service Binding Specification directory vẫn cần được tạo đúng contract nếu application dùng Spring Cloud Bindings. Một secret file đơn lẻ được mount vào `/var/secrets` không tự trở thành binding có type/name/metadata.

## 9. Ma trận mapping theo service type và provider

| Service type | Binding data có thể cần | Spring integration/consumer |
| --- | --- | --- |
| PostgreSQL | host, port, database, username, password/secret ref, TLS | Spring Boot JDBC/R2DBC |
| Redis | host, port, username/password, TLS, database index | Spring Data Redis |
| RabbitMQ | host, port, vhost, username/password, TLS | Spring AMQP / Rabbit binder |
| Kafka | bootstrap servers, security protocol, SASL/TLS, topic metadata | Spring Cloud Stream Kafka binder |
| AWS S3 | bucket, Region, endpoint nếu cần | AWS SDK v2/AWSpring |
| AWS SQS/SNS | queue URL/topic ARN, Region | AWSpring/AWS SDK |
| Azure Blob | account endpoint, container | Azure Storage SDK |
| Azure Service Bus | namespace, queue/topic, subscription | Azure SDK/Spring Cloud Azure |
| GCP Cloud Storage | project, bucket | Google Cloud Storage client |
| GCP Pub/Sub | project, topic, subscription | Google Cloud Pub/Sub integration |

Bảng này mô tả dữ liệu ứng dụng có thể cần; nó không phải cam kết Spring Cloud Bindings tự động map mọi service type. Mapper built-in và property name phải được xác minh theo phiên bản thư viện. Với API-based managed service, endpoint/resource metadata và workload identity thường là đủ; không sinh username/password nếu provider không dùng mô hình đó.

## 10. Property precedence và chọn binding

Một pod có thể đồng thời nhận:
- Binding directory do platform mount.
- Environment variables từ Deployment.
- application.yaml trong image.
- ConfigData từ Config Server hoặc provider store.
- Secret/config tree mount riêng.

Nếu cùng một property xuất hiện ở nhiều nguồn, kết quả phụ thuộc thứ tự property source và thư viện binding. Không giả định Spring Cloud Bindings luôn thắng environment hoặc ngược lại.

Quy ước đề xuất:

1. Mỗi property có một source of truth.
2. Binding name được chọn tường minh nếu có nhiều service cùng type.
3. Environment override chỉ dành cho các key đã được phê duyệt.
4. Secret chỉ đến từ secret source được chỉ định; không fallback sang default rỗng.
5. Provider resource identifier có validation theo environment/account/project.
6. Khi startup, ghi log source/type/version không nhạy cảm để chẩn đoán.

Không đưa binding password vào `application.yaml` rồi kỳ vọng platform override chính xác mà không test. Dùng test context để chứng minh property source precedence của đúng Spring Cloud Bindings/Spring Boot release.
## 11. Lifecycle, rotation và refresh

### 11.1. Binding được đọc khi nào?

Nhiều integration đọc binding lúc startup để tạo Spring property sources và connection beans. Nếu platform cập nhật Secret hoặc binding directory sau đó, ứng dụng không nhất thiết tự đọc lại. Hành vi phụ thuộc filesystem mount, platform và library.

Phân loại:
- **Startup-only:** endpoint, driver, database name, TLS truststore hoặc client configuration.
- **Rotatable secret:** password, token, certificate có thể đổi trong khi app chạy.
- **Dynamic metadata:** feature/routing setting được thiết kế để refresh.
- **Deployment change:** binding mới hoặc resource mới yêu cầu rollout/restart.

Không giả định Spring Cloud Bindings tự refresh mọi datasource/client khi file thay đổi.

### 11.2. Kubernetes Secret update

Kubernetes projected Secret volume có thể được cập nhật sau một khoảng trễ; cách mount qua `subPath` có thể không nhận cập nhật theo cơ chế projected volume thông thường. Application phải biết file update có được quan sát hay không và có reload client hay không. Một cách đơn giản và dễ kiểm soát là rollout pod khi credential binding đổi.

Không dùng environment variable để mong secret tự thay đổi trong process đang chạy; environment của process chỉ được thiết lập khi container start.

### 11.3. Cloud Foundry binding lifecycle

Cloud Foundry service binding credentials có thể thay đổi khi service instance/binding được cập nhật. Application cần restage/restart hoặc cơ chế platform-supported refresh để nhận giá trị mới. Xác minh behavior của service broker và platform; không tự giả định `VCAP_SERVICES` đang chạy được cập nhật trong process.

### 11.4. Rotation an toàn

Quy trình rotation cần phối hợp provider và application:

1. Tạo credential/version mới hoặc kích hoạt rotation theo provider.
2. Cập nhật binding/secret reference.
3. Cấp overlap window nếu dịch vụ hỗ trợ hai credential đồng thời.
4. Restart/refresh workload theo lifecycle.
5. Kiểm tra connection pool/client đã dùng credential mới.
6. Thu hồi credential cũ sau khi mọi instance chuyển đổi.
7. Theo dõi auth failure và có rollback plan.

Với IAM/Managed Identity/Workload Identity, rotation thường do token provider/runtime đảm nhiệm. Không cache access token vô thời hạn; dùng SDK credential provider có refresh.

## 12. Bảo mật service binding

### 12.1. Binding credentials là secret

Binding có thể chứa password, access token, private key, SAS connection string hoặc certificate private key. Xem toàn bộ binding directory như dữ liệu nhạy cảm cho tới khi từng field được phân loại.

- Không commit binding fixture chứa secret thật.
- Không bake credential vào container image.
- Không in environment, JSON binding hoặc toàn bộ file ra log.
- Không expose binding qua actuator, debug endpoint hoặc support bundle.
- Mask secret trong exception và diagnostic output.
- Không đưa credential vào metric label, trace baggage hoặc message header.

Resource name, bucket, host và project ID có thể không phải secret nhưng vẫn có thể là internal topology. Chỉ log khi policy cho phép.

### 12.2. Least privilege trên platform

Chỉ bind workload với service cần dùng. Trong Kubernetes, RBAC giới hạn ai đọc Secret; service account chỉ cần quyền cần thiết. Không mount tất cả secret của namespace vào mọi pod. Trong Cloud Foundry, chỉ bind service instance cần thiết và dùng credential riêng theo application khi broker hỗ trợ.

Nếu service broker tạo binding credentials, kiểm tra:
- Credential có scope theo application/service instance không?
- Unbind có thu hồi credential không?
- Credential có rotation/revoke riêng không?
- Audit ghi nhận ai tạo, đọc hoặc xóa binding?
- Secret được mã hóa at rest và truyền qua TLS không?

### 12.3. Kubernetes Secret và filesystem permission

Kubernetes Secret volume thường được mount với permission phù hợp nhưng Base64 encoding trong manifest không phải encryption. Bật encryption at rest cho etcd, giới hạn RBAC, dùng external secret provider khi phù hợp và mount read-only.

Không mount binding vào container sidecar không cần credential. Chọn `defaultMode`/file permissions phù hợp với UID/GID của process; tránh chmod rộng như 0777. Không lưu copy secret ra writable `/tmp` hoặc image layer.

### 12.4. Cloud identity là lớp authorization riêng

Service binding không thay thế IAM/RBAC:

- AWS: IAM role/policy cho API operation và resource ARN.
- Azure: Managed Identity/Workload Identity và Azure RBAC/data-plane role.
- Google Cloud: service account/workload identity principal và IAM role.
- Kubernetes: service account, RBAC và network policy.
- Cloud Foundry: service broker credentials và platform isolation.

Endpoint/queue name không chứng minh application có quyền truy cập. Credential trong binding cũng phải được bảo vệ theo scope và rotation policy.

### 12.5. TLS và certificate

Nếu binding cung cấp CA certificate/client certificate, cấu hình client truststore/SSL đúng. Xác minh hostname, certificate chain, expiry và rotation. Không tắt hostname verification hoặc trust mọi certificate để khắc phục lỗi. Private key phải được đọc từ secret mount, không đưa vào source control.
## 13. Kiểm thử service binding

### 13.1. Fixture binding directory

Tạo fixture test không chứa secret thật:

~~~text
src/test/resources/bindings/
  reservation-db/
    type
    provider
    name
    host
    port
    database
    username
    password
~~~

Ví dụ file test:

~~~text
type=postgresql
provider=test
name=reservation-db
host=localhost
port=5432
database=reservation_test
username=test_user
password=test_password_only
~~~

Cấu hình test environment trỏ binding root tới fixture theo cách thư viện/version hỗ trợ. Không mount fixture này trong production image. Test cần kiểm tra mapping kết quả vào datasource properties và failure khi thiếu required key.

### 13.2. Kiểm thử Cloud Foundry VCAP_SERVICES

Dùng JSON fixture với credential giả. Kiểm tra:
- Parser đọc đúng service label/name.
- Nhiều service cùng label được chọn đúng theo policy.
- Missing credentials tạo lỗi rõ ràng.
- JSON malformed không làm app fallback sang production endpoint.
- Secret không xuất hiện trong log/test report.

Không đặt `VCAP_SERVICES` fixture vào environment developer toàn cục; giới hạn trong process test.

### 13.3. Test Spring context

Có thể dùng `ApplicationContextRunner` hoặc `@SpringBootTest` với property source test để xác minh typed configuration và auto-configuration. Với datasource, Testcontainers có thể cung cấp PostgreSQL/Rabbit/Kafka để kiểm tra kết nối thật ở CI. Test binding parser và test network connection là hai lớp khác nhau.

Các assertion hữu ích:
1. Binding type/name/provider được nhận diện.
2. Datasource URL/username được tạo đúng; password được kiểm tra mà không in ra.
3. Connection pool khởi tạo thành công.
4. Binding không bắt buộc có thể disable feature đúng policy.
5. Binding bắt buộc thiếu hoặc sai type làm startup fail.
6. Environment override chỉ xảy ra với key được phép.
7. Nhiều binding cùng type không kết nối nhầm resource.

### 13.4. Contract test trên platform

Test staging cần xác minh operator/service broker thật tạo đúng contract:
- `SERVICE_BINDING_ROOT` được thiết lập.
- Directory/metadata/secret keys đúng theo spec.
- Volume mount read-only và file permission phù hợp.
- Workload identity có quyền tới managed service.
- Rotation/restart/unbind có behavior dự kiến.
- Service endpoint reachable qua network policy/private endpoint.
- Audit và secret masking hoạt động.

Emulator/mock không chứng minh platform broker, IAM, RBAC, network policy hoặc secret rotation. Giữ ít nhất một contract test trên staging cho từng platform/service integration quan trọng.

## 14. Quan sát và troubleshooting

### 14.1. Log an toàn

Có thể log:
- Binding type và logical name.
- Provider/platform name.
- Trạng thái required/optional và resolved/unresolved.
- Endpoint class/protocol đã mask nếu cần.
- Client initialization success/failure và error category.

Không log:
- Password/token/SAS string.
- Private key/certificate private material.
- Full `VCAP_SERVICES`.
- Nội dung binding file.
- Environment hoặc Spring Environment dump.

### 14.2. Metric nên theo dõi

| Metric | Mục đích |
| --- | --- |
| Binding discovery success/failure | Platform có cung cấp binding đúng không |
| Binding parse/validation error | Contract/metadata sai |
| Client initialization failure | Endpoint/credential/TLS không hợp lệ |
| Connection pool active/idle/pending | Database capacity và connection issue |
| Auth failure theo provider | IAM/RBAC/credential rotation issue |
| Binding age/version | Credential hoặc metadata đã cũ |
| Secret refresh/restart count | Tần suất rotation và rollout |
| Downstream latency/error rate | Managed service health |

Không dùng binding name do user tạo, secret version hoặc tenant ID tùy ý làm metric label nếu có thể tạo cardinality không giới hạn.

### 14.3. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy binding root | Thiếu `SERVICE_BINDING_ROOT` hoặc volume mount sai | Kiểm tra pod env, mount path và operator status |
| Binding directory không được nhận diện | Thiếu file metadata/type hoặc sai contract | Kiểm tra spec và mapper version |
| Có nhiều binding cùng type | Mapper chọn nhầm binding | Chọn logical name tường minh |
| Datasource URL sai | Host/port/database mapping sai hoặc driver không tương thích | Validate URI và driver |
| AccessDenied dù binding tồn tại | Thiếu IAM/RBAC hoặc identity sai | Kiểm tra workload identity và resource scope |
| TLS handshake fail | CA/truststore/hostname không đúng | Kiểm tra certificate chain và endpoint |
| Secret mới không được áp dụng | App chỉ đọc lúc startup hoặc mount không cập nhật | Restart/refresh theo lifecycle |
| Cloud Foundry không thấy credentials mới | App chưa restage/restart hoặc broker chưa update | Kiểm tra binding lifecycle và platform |
| Ứng dụng chạy local nhưng lỗi trên cluster | Local fixture khác contract/permission thật | Chạy staging contract test |
| Secret xuất hiện trong log | Dump binding/environment/exception | Mask output, rotate credential và sửa diagnostic |

### 14.4. Runbook khi binding không hoạt động

1. Kiểm tra service instance đã provision và trạng thái healthy.
2. Xác minh binding đã gắn đúng application/workload.
3. Kiểm tra environment root và directory mount.
4. Xác minh file metadata, type, provider và required key.
5. Kiểm tra permission đọc file và UID/GID process.
6. Kiểm tra endpoint DNS/network/private link.
7. Xác minh workload identity và IAM/RBAC riêng.
8. Kiểm tra TLS, certificate và clock skew.
9. Xác minh Spring property mapping và precedence.
10. Chỉ log tên key/trạng thái; không dump secret để debug.

## 15. Quy trình đưa service binding vào một ứng dụng

Khi chuyển từ cấu hình hard-code sang platform binding, thực hiện theo trình tự:

1. Xác định service instance và application/workload cần bind.
2. Chọn contract platform hỗ trợ: Kubernetes Service Binding Specification, Cloud Foundry hoặc provider-specific mechanism.
3. Liệt kê metadata/credential application thực sự cần; tách resource identifier khỏi secret.
4. Chọn binding name/type rõ ràng nếu có nhiều service cùng loại.
5. Cấu hình operator/service broker, volume/environment và permission tối thiểu.
6. Thêm Spring Cloud Bindings hoặc custom adapter tương thích với platform contract.
7. Bind metadata vào typed configuration và validate lúc startup.
8. Cấu hình SDK credential provider/workload identity độc lập với resource metadata.
9. Kiểm thử local fixture, CI integration và staging contract.
10. Thiết kế rotation, restart/refresh, unbind và rollback.
11. Triển khai canary; xác minh app dùng đúng resource và identity.
12. Thu hồi credential cũ hoặc xóa binding cũ sau khi workload đã chuyển đổi.

Không đưa toàn bộ secret vào một binding chung nếu application chỉ cần một phần. Mỗi workload nên nhận đúng service và credential scope của nó.

## 16. Checklist trước production

1. **Contract:** xác định đúng Service Binding Specification, Cloud Foundry hoặc provider-specific format.
2. **Binding selection:** service type/name/provider được chọn rõ, không phụ thuộc thứ tự thư mục.
3. **Mapping:** property/URI được validate; JDBC/R2DBC, broker và SDK config đúng protocol.
4. **Identity:** workload identity/IAM/RBAC được cấu hình độc lập với binding metadata.
5. **Least privilege:** workload chỉ đọc binding và truy cập service cần thiết.
6. **Secret handling:** binding credential không ở Git, image, log, metric hoặc support bundle.
7. **Filesystem:** mount read-only, file permission phù hợp, path traversal được ngăn chặn.
8. **Precedence:** source of truth và override policy rõ ràng, có test.
9. **Lifecycle:** biết binding được đọc lúc startup hay refresh; có restart/rollout strategy.
10. **Rotation:** credential mới được kiểm tra trước khi revoke credential cũ.
11. **Network/TLS:** DNS, private endpoint, firewall và certificate được xác minh.
12. **Testing:** fixture, context test, broker/database integration và staging contract test.
13. **Observability:** binding discovery, mapping error, client init, auth failure và binding age có metric.
14. **Recovery:** có runbook cho bind/unbind, secret rotation và provider outage.
15. **Compatibility:** Spring Boot, Spring Cloud Bindings và provider integration nằm trong release train tương thích.

## 17. Bài tập tự luyện

1. Vẽ sequence từ provision PostgreSQL service instance tới lúc Spring Boot có thể inject JdbcTemplate.
2. Tạo một fixture Kubernetes Service Binding directory và giải thích vai trò của type, provider, name, host, port và password.
3. So sánh binding directory với Cloud Foundry VCAP_SERVICES và Spring Boot config tree.
4. Thêm Spring Cloud Bindings vào một ứng dụng Spring Boot; kiểm tra datasource được cấu hình từ binding fixture.
5. Tạo hai binding PostgreSQL cùng type; thiết kế cách chọn đúng service theo logical name.
6. Viết custom reader cho binding object storage gồm provider, bucket và Region; validate required keys.
7. Triển khai ứng dụng trên EKS: binding cung cấp bucket/queue metadata, IAM role cung cấp quyền; chứng minh hai lớp độc lập.
8. Triển khai ứng dụng trên AKS: binding cung cấp Blob endpoint/container, Managed Identity cấp quyền data-plane.
9. Triển khai ứng dụng trên GKE: binding cung cấp Pub/Sub topic/subscription, Workload Identity cấp quyền publish/consume.
10. Mô phỏng secret rotation khi pod đang chạy; xác định khi nào cần restart và cách kiểm tra connection pool dùng credential mới.
11. Viết test cho missing binding, malformed metadata, permission denied và nhiều binding trùng type.
12. Viết runbook xử lý trường hợp binding directory tồn tại nhưng application nhận AccessDenied từ managed service.

**Tiêu chí hoàn thành:** người học mô tả được contract service binding của platform, ánh xạ được binding data vào Spring Boot, phân biệt resource metadata với identity/secret, kết nối ít nhất một managed service qua binding, kiểm thử lifecycle và xử lý an toàn rotation/unbind.

## Tài liệu tham khảo

- [Kubernetes Service Binding Specification](https://servicebinding.io/spec/core/1.0.0/): contract binding directory, metadata và environment.
- [Kubernetes Service Binding Operator](https://github.com/redhat-developer/service-binding-operator): operator triển khai service binding trên Kubernetes.
- [Spring Cloud Bindings](https://github.com/spring-cloud/spring-cloud-bindings): hỗ trợ Spring application đọc platform service bindings.
- [Cloud Foundry VCAP_SERVICES](https://docs.cloudfoundry.org/devguide/deploy-apps/environment-variable.html#VCAP-SERVICES): cấu trúc service binding environment.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, environment và config tree.
- [Spring Boot Service Connections](https://docs.spring.io/spring-boot/reference/features/dev-services.html): connection details cho development/test services.
- [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html): credential resolution cho workload.
- [Amazon EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html): gắn IAM role với Kubernetes workload.
- [Azure Workload Identity for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview): xác thực workload trên AKS.
- [Azure DefaultAzureCredential](https://learn.microsoft.com/java/api/com.azure.identity.defaultazurecredential): credential chain cho Azure SDK.
- [Google Cloud Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity): workload identity trên GKE.
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs/overview): secret versions và access control.
