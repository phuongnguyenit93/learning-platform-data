# Cấu hình kết nối Spring Boot và quản lý thông tin bí mật trong Spring Data MongoDB

## 1. Bối cảnh: kết nối cơ sở dữ liệu là một hợp đồng vận hành

Ứng dụng Spring Boot thường kết nối MongoDB chỉ với một cấu hình URI. Nhưng trong môi trường thực tế, “kết nối được” chỉ là bước đầu. Hệ thống còn phải:

- Chọn đúng MongoDB deployment, database và authentication source.
- Sử dụng TLS và kiểm tra danh tính máy chủ.
- Dùng một principal có quyền tối thiểu theo từng ứng dụng/môi trường.
- Không đưa password hoặc token vào mã nguồn, image, log và hệ thống theo dõi.
- Quản lý pool connections, timeout, retry, topology discovery và workload.
- Xoay vòng credentials/chứng chỉ mà không tạo gián đoạn bất ngờ.
- Chạy được tests và có tín hiệu sức khỏe phù hợp.
- Giải thích rõ tại sao cấu hình Spring Boot 3.x khác 4.x.

Bài thuộc module **Database Engine Document MongoDB**, chương **Spring Data MongoDB**, với đề bài **Cấu hình kết nối Spring Boot và quản lý thông tin bí mật**.

### Mục tiêu

Sau bài học bạn có thể:

1. Phân biệt MongoDB Java Driver, Spring Data MongoDB và Spring Boot auto-configuration.
2. Chọn dependency đồng bộ hoặc reactive cho đúng mô hình ứng dụng.
3. Cấu hình URI, hostname, replica set, `authSource`, TLS và SSL bundle.
4. Hiểu khác biệt namespace cấu hình giữa Spring Boot 3.5 và 4.x.
5. Dùng `application.yml`, profiles, environment variables và externalized configuration mà không hardcode secrets.
6. Nạp secret từ Kubernetes-mounted configuration tree hoặc secret manager.
7. Tùy chỉnh `MongoClientSettings`, connection pool và timeout đúng phiên bản.
8. Cấu hình authentication SCRAM/X.509 và nhận biết lựa chọn IAM/OIDC khi deployment hỗ trợ.
9. Thiết kế rotation dùng hai principals để chuyển ứng dụng an toàn.
10. Thiết kế health checks, metrics, logging và kiểm thử kết nối.
11. Chẩn đoán lỗi DNS SRV, TLS, authentication, authorization, topology, timeout và cấu hình sai precedence.
12. Tạo checklist triển khai production và tự luyện tập bằng các bài tập tình huống.

**Phạm vi:** Ví dụ dựa trên các API phổ biến của Spring Boot 3.5/4.x và MongoDB Java Driver/Spring Data tương thích. Những chi tiết cấu hình phụ thuộc phiên bản được ghi riêng. Không sao chép credentials ví dụ vào production.

## 2. Hệ thống gồm những tầng nào?

~~~text
HTTP Controller / Scheduled Worker
              |
              v
         Service layer
              |
      +-------+-------+
      |               |
      v               v
MongoRepository    MongoTemplate
      |               |
      +-------+-------+
              |
              v
       MongoDatabaseFactory
              |
              v
        MongoDB Java Driver
              |
        MongoClient / Pool
              |
      DNS + TLS + SCRAM/X.509
              |
              v
   MongoDB Atlas / Self-managed
~~~

- **MongoDB Java Driver:** quản lý network protocol, topology discovery, connection pools, server selection, BSON và authentication.
- **Spring Data MongoDB:** cung cấp `MongoTemplate`, mapping documents, repository abstractions, converters và tích hợp Spring.
- **Spring Boot:** cấu hình tự động các beans liên quan nếu dependencies/properties phù hợp.

Một lỗi connection có thể xuất phát từ mọi tầng. Ví dụ repository method chính xác nhưng `MongoClient` đang dùng sai `authSource` thì không truy vấn được.

### 2.1. Một MongoClient nên có vòng đời dài

`MongoClient` thread-safe và được thiết kế để tái sử dụng connection pool. Thông thường, một application process dùng một bean singleton do Spring Boot quản lý.

**Không** tạo một `MongoClient` mới cho mỗi HTTP request. Cách đó gây connection churn, thêm TLS/SCRAM handshakes và có thể cạn giới hạn connections.

### 2.2. Spring Data không tạo secret manager thay bạn

Spring Boot có cơ chế externalized configuration, nhưng bản thân `application.yml` hoặc `@Value` không cung cấp chính sách mã hóa/lưu trữ/rotation. Cần kết hợp với secrets manager, IAM, TLS, ACL và vòng đời credentials.

## 3. Chọn đúng starter: synchronous hay reactive?

Nếu sử dụng Spring MVC với phần lớn code blocking:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Nếu ứng dụng dùng WebFlux và muốn non-blocking database access:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
~~~

### 3.1. Không trộn sync/reactive chỉ vì “reactive nhanh hơn”

- Đồng bộ: `MongoTemplate` và `MongoRepository`; gọi blocking, dễ hiểu khi phần còn lại blocking.
- Reactive: `ReactiveMongoTemplate`, `ReactiveMongoRepository` và Reactor types.
- Một reactive endpoint gọi blocking repository sẽ chặn thread nếu không được xử lý đúng; không đạt non-blocking toàn chuỗi.

Chỉ dùng dependencies thực sự cần thiết. Phần lớn ví dụ sau dùng **synchronous Spring Data MongoDB**.

### 3.2. Để Spring Boot quản lý phiên bản thư viện

Với Maven/Gradle dùng Spring Boot BOM/dependency management, tránh khóa tùy tiện phiên bản MongoDB Java Driver/Spring Data lệch khỏi tổ hợp được kiểm thử.

Khi nâng MongoDB server, phải kiểm tra compatibility matrix của **server version + driver + Spring Data + Spring Boot**. Không đồng nhất phiên bản server 8.x với việc mọi Boot/Driver phiên bản cũ đều hỗ trợ.

## 4. Điểm đặc biệt quan trọng: Spring Boot 3.x và 4.x dùng prefix khác nhau

Spring Boot đã thay đổi **namespace cấu hình MongoDB** trong dòng 4.x.

| Mục đích | Spring Boot 3.5 | Spring Boot 4.x |
|---|---|---|
| MongoDB connection URI | `spring.data.mongodb.uri` | `spring.mongodb.uri` |
| Database name | `spring.data.mongodb.database` | `spring.mongodb.database` |
| Username | `spring.data.mongodb.username` | `spring.mongodb.username` |
| Password | `spring.data.mongodb.password` | `spring.mongodb.password` |
| Authentication database | `spring.data.mongodb.authentication-database` | `spring.mongodb.authentication-database` |
| SSL enabled | `spring.data.mongodb.ssl.enabled` | `spring.mongodb.ssl.enabled` |
| SSL bundle | `spring.data.mongodb.ssl.bundle` | `spring.mongodb.ssl.bundle` |
| Host / port | `spring.data.mongodb.host/port` | `spring.mongodb.host/port` |
| Repository settings | `spring.data.mongodb.repositories.*` | Xem configuration metadata đúng bản, không suy diễn từ URI |

Nguồn để đối chiếu: **Spring Boot 3.5 Common Application Properties** và **Spring Boot 4.x Common Application Properties**. Khi dùng dòng 4.1, hãy xem tài liệu đúng bản đã chọn.

### 4.1. Ví dụ Spring Boot 3.5

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-api
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

Variable môi trường tương ứng với **property** khi dùng relaxed binding trực tiếp là `SPRING_DATA_MONGODB_URI`.

Tuy nhiên với ví dụ trên, ứng dụng đọc biến tùy chỉnh có tên `MONGODB_URI` qua placeholder; đó là hai cách khác nhau và không cần khai báo cả hai.

### 4.2. Ví dụ Spring Boot 4.x

~~~yaml
spring:
  application:
    name: orders-api
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Nếu cấu hình hoàn toàn bằng environment property name, Boot 4.x dùng `SPRING_MONGODB_URI`.

### 4.3. Vì sao copy ví dụ cũ có thể lỗi?

Một ứng dụng nâng Boot 3.5 → 4.x nhưng giữ duy nhất property `spring.data.mongodb.uri` có thể không cấu hình `MongoClient` như mong muốn và kết nối tới default target hoặc lỗi initialization. Không xác minh bằng việc grep YAML; kiểm tra **effective configuration đã redacted** và actual server endpoint.

### 4.4. Chọn một ví dụ có phiên bản xác định

Từ mục tiếp theo, khi không ghi chú khác, các block YAML chính dùng **Spring Boot 4.x**. Mỗi nơi quan trọng có chỉ dẫn đổi prefix tương ứng cho Boot 3.5.

## 5. Kết nối local development tối thiểu

Với MongoDB local chỉ dành cho lab, một cấu hình Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "mongodb://127.0.0.1:27017/learning_db"
~~~

Nếu dùng Boot 3.5:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://127.0.0.1:27017/learning_db"
~~~

Đây chỉ là ví dụ lab. MongoDB local không authentication/TLS **không phải** mô hình production.

### 5.1. Khi không khai báo URI thì sao?

Spring Boot có default MongoDB URL phù hợp với phiên bản (ví dụ tài liệu mô tả `mongodb://localhost/test`). Không dựa vào default trong production vì:

- Dễ kết nối nhầm database/host.
- Có thể che sự cố biến môi trường bị thiếu.
- Người vận hành có thể không biết target đang là đâu.

### 5.2. Production nên fail fast khi thiếu secret

Ví dụ:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Không đặt default password hoặc default production URI sau dấu `:` trong placeholder. Nếu biến không có, cần application startup thất bại có kiểm soát, thay vì âm thầm dùng tài khoản lab.

## 6. URI MongoDB: đọc đúng các thành phần

Một connection string giả định:

~~~text
mongodb://<user>:<percent-encoded-password>@db1.example.test:27017,db2.example.test:27017/orders?replicaSet=rs0&authSource=admin&tls=true&appName=orders-api
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `mongodb://` | Giao thức URI MongoDB thông thường |
| `user/password` | Credential SCRAM nếu cấu hình |
| `db1,db2` | Danh sách seed hosts; driver còn khám phá topology |
| `/orders` | Default database trong URI khi không override |
| `replicaSet=rs0` | Yêu cầu đúng replica set |
| `authSource=admin` | Nơi server tìm user để xác thực |
| `tls=true` | Yêu cầu TLS |
| `appName=orders-api` | Định danh ứng dụng trong thông tin client/diagnostics |

**Cảnh báo:** Placeholder không phải URI chạy được. Tuyệt đối không chép một URI chứa password thật vào tài liệu, PR hoặc issue.

### 6.1. Password có ký tự đặc biệt

Trong URI credentials, các ký tự reserved như `@`, `:`, `/`, `?`, `#`, `%` cần percent-encoding đúng quy tắc MongoDB connection string.

Ví dụ một password chứa ký tự `@` không thể đơn giản chèn thẳng vào đoạn userinfo rồi kỳ vọng parser hiểu đúng. Nếu có thể, để secret manager cung cấp URI đã được mã hóa đúng, hoặc dùng API `MongoCredential` và `MongoClientSettings` cho cấu hình tách credentials.

### 6.2. authSource khác default database

User có thể nằm tại database `admin` nhưng ứng dụng thao tác trên `orders`:

~~~text
database used by app = orders
authSource = admin
~~~

Nếu user được tạo ở một database khác, phải chọn đúng `authSource`. Lỗi `AuthenticationFailed` không nhất thiết là sai password.

### 6.3. URI có quyền ưu tiên hơn host/port/user/password rời

Theo configuration metadata, khi đặt URI, các thuộc tính host/port/username/password riêng có thể bị bỏ qua. Không cấu hình cả:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
    username: "another-user"
    password: "another-password"
~~~

rồi mong properties rời ghi đè credential trong URI. Chọn **một chiến lược cấu hình** và xác minh effective behavior theo Boot version.

### 6.4. Database override cần được hiểu

Ở Boot 4.x, `spring.mongodb.database` có thể override database trong URI theo docs; nhưng điều này **không tự đổi authSource**. Không dùng cùng một app connection cho nhiều tenants/databases mà không kiểm tra giới hạn permission và MongoDatabaseFactory.

## 7. mongodb+srv:// và MongoDB Atlas

Atlas thường cung cấp URI dùng DNS SRV:

~~~text
mongodb+srv://<user>:<encoded-password>@cluster0.example.mongodb.net/orders?authSource=admin&retryWrites=true&w=majority
~~~

Với `mongodb+srv://`:

- Driver tra DNS SRV (và TXT theo MongoDB URI rules).
- Host được khám phá từ DNS, không ghi danh sách seed hosts/ports tùy tiện.
- TLS được bật mặc định trong cách sử dụng SRV theo MongoDB connection string specification, trừ khi cấu hình khác.
- DNS resolution và network tới các hosts thực tế phải hoạt động.
- URI vẫn cần credentials/permission đúng.

### 7.1. Atlas cần cả ba điều kiện

- **Database user:** username, auth mechanism và roles đúng.
- **Network access:** IP access list, VPC/private endpoint hoặc network controls phù hợp.
- **TLS:** certificate chain/hostname được xác minh.

Thiếu một trong ba có thể tạo lỗi khác nhau: DNS/server selection, TLS handshake, authentication hoặc authorization.

### 7.2. Không dùng IP allowlist rộng vì tiện thử

Tránh mở mạng tới mọi IP trên internet trong production. Dùng network access policy hẹp, private connectivity khi có thể và theo dõi changes.

### 7.3. SRV DNS là một nguồn lỗi riêng

Nếu máy chạy ứng dụng không truy vấn DNS SRV/TXT hoặc policy chặn DNS, host có thể không được resolve dù username/password đúng. Kiểm tra DNS ở chính runtime container/VM thay vì từ laptop.

## 8. Replica set discovery và read/write semantics

Kết nối replica set cần driver nhận diện topology và primary/secondaries. Cấu hình seed list/replicaSet có thể giúp driver xác thực topology mục tiêu.

### 8.1. Không bật directConnection tùy tiện

`directConnection=true` khiến driver kết nối trực tiếp tới một node trong các tình huống cho phép, thay đổi topology discovery và behavior. Nó hữu ích trong vài lab/tunnel scenarios, nhưng thường không đúng cho ứng dụng cần failover của replica set.

### 8.2. Retryable writes không phải "retry vô hạn"

`retryWrites=true` giúp driver retry một số writes đủ điều kiện khi có transient network/failover errors. Nó không biến mọi operation thành idempotent.

- Một transaction có quy tắc retry riêng.
- Business operation gửi message ngoài DB có thể không idempotent.
- Duplicate key/validation errors không tự được sửa bằng retry.

### 8.3. Read preference, read concern, write concern

- **Read preference:** ưu tiên đọc primary hay secondary, có thể ảnh hưởng freshness.
- **Read concern:** tính chất nhất quán/visibility của dữ liệu đọc.
- **Write concern:** mức xác nhận ghi, ví dụ majority.
  
Không tùy tiện đổi `w=majority` thành `w=1` để “giảm latency” khi chưa đánh giá durability requirements.

### 8.4. Latency sau failover

Một primary election có thể làm lệnh đang chạy thất bại và driver cần server selection mới. Ứng dụng nên có request deadlines, bounded retries và các SLO phù hợp; không hứa rằng chỉ dùng replica set URI sẽ không bao giờ có lỗi thoáng qua.

## 9. Spring Data: một repository và domain tối giản

Định nghĩa một document để minh họa:

~~~java
package example.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import java.time.Instant;

@Document("orders")
public class Order {
    @Id
    private String id;
    private String tenantId;
    private String status;
    private Instant createdAt;

    protected Order() {
    }

    public Order(String id, String tenantId, String status, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

Repository:

~~~java
package example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndStatus(String tenantId, String status);
}
~~~

Ở startup, Spring Data tạo repository bean khi component/repository scanning và dependencies phù hợp.

### 9.1. Tên collection không phải secret

Tên collection, database và môi trường vẫn có thể là metadata nhạy cảm về hạ tầng, nhưng password/private key/token mới là secret cần bảo vệ nghiêm ngặt. Không dùng collection name làm credential.

### 9.2. Least privilege

Repository đọc/ghi orders không cần user `root`. Tạo database principal có quyền tối thiểu; nếu service chỉ đọc, cân nhắc role `read` hoặc custom role phù hợp.

### 9.3. Auto index creation

Đừng dựa vào việc tự động tạo mọi index trong production mà không có migration plan, đặc biệt với indexes lớn/unique constraints. Quản lý index changes qua rollout có kiểm soát và quan sát write/storage effects.

## 10. MongoTemplate và MongoDatabaseFactory

Spring Boot có thể auto-configure `MongoTemplate` và `MongoDatabaseFactory` khi starter, settings và điều kiện phù hợp.

~~~java
package example.orders;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.bson.Document;

@Service
public class OrderLookupService {
    private final MongoTemplate template;

    public OrderLookupService(MongoTemplate template) {
        this.template = template;
    }

    public long countOrders() {
        return template.getCollection("orders")
            .countDocuments(new Document());
    }
}
~~~

Đây là ví dụ đơn giản, không khuyến nghị count toàn collection trên đường nóng có dữ liệu rất lớn.

### 10.1. Không tự tạo MongoClient nếu auto-configuration đủ

Khi ứng dụng khai báo `@Bean MongoClient` riêng, Spring Boot có thể back off từ việc tạo client mặc định và dùng client của bạn. Lúc đó những cấu hình Boot properties tưởng rằng có hiệu lực có thể không được áp dụng như mong đợi.

Chỉ tùy chỉnh bean khi có yêu cầu rõ, ghi lại trách nhiệm cấu hình URI, TLS, credentials, pooling và lifecycle.

## 11. Cấu hình bằng application.properties và application.yml

Hai cách tương đương (Boot 4.x):

~~~properties
spring.application.name=orders-api
spring.mongodb.uri=${MONGODB_URI}
~~~

Hoặc:

~~~yaml
spring:
  application:
    name: orders-api
  mongodb:
    uri: "${MONGODB_URI}"
~~~

### 11.1. Không trộn nhiều nơi khai báo cùng một property nếu không hiểu precedence

Spring Boot đọc nhiều property sources: command-line, system properties, environment variables, external config files, classpath config, profile-specific documents, config imports...

Một giá trị đến sau theo thứ tự ưu tiên có thể ghi đè giá trị trong `application.yml`. Đừng suy luận “đã có file YAML đúng thì runtime chắc dùng file đó”.

### 11.2. Kiểm tra source mà không in secret

Cần xác minh app đang kết nối đúng cluster nhưng không log full URI. Có thể log metadata **đã lọc** như environment, application name, logical cluster ID hoặc database name được cho phép, tránh password/token và hostname nhạy cảm khi không cần.

### 11.3. Không dùng default production secret

Không viết:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI:mongodb://admin:password@db.prod:27017/orders}"
~~~

Đây là **anti-pattern**: khi secret injection lỗi, ứng dụng âm thầm dùng credential hardcoded.

## 12. Spring profiles: local, test, staging và production

Phân môi trường:

~~~text
application.yml
application-local.yml
application-test.yml
application-staging.yml
application-prod.yml
~~~

Một cấu hình chung:

~~~yaml
spring:
  application:
    name: orders-api
~~~

Profile local (Boot 4.x):

~~~yaml
# application-local.yml
spring:
  mongodb:
    uri: "mongodb://127.0.0.1:27017/orders_lab"
~~~

Profile prod:

~~~yaml
# application-prod.yml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

### 12.1. Chỉ local/test mới có cấu hình yếu hơn nếu lab cô lập

Không deploy profile local vào production. Cần kiểm soát `SPRING_PROFILES_ACTIVE`, runtime environment và network access.

### 12.2. Đừng kích hoạt production profile trong source

Active profile nên được xác định ở deployment layer với cơ chế được kiểm soát. Tránh để developers đổi profile bằng sửa code rồi commit.

### 12.3. Không coi profile là ranh giới bảo mật

Một ứng dụng prod với profile đúng nhưng service account có quyền đọc secrets staging/prod quá rộng vẫn nguy hiểm. Phân tách IAM, project, database users và KMS policies thực tế.

## 13. Environment variables: tiện lợi nhưng có giới hạn

Ví dụ Boot 4.x có hai chiến lược:

**Chiến lược A — Placeholder tùy chỉnh**

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Deployment cấp `MONGODB_URI`.

**Chiến lược B — Relaxed binding trực tiếp**

Không khai báo URI trong YAML; deployment cấp `SPRING_MONGODB_URI`.

Với Boot 3.5, tên property tương ứng là `SPRING_DATA_MONGODB_URI`.

### 13.1. Không giả định environment variable là kho bảo mật

Environment variables có thể bị lộ trong:

- Process diagnostics/heap dumps.
- CI/CD job output.
- Debug logs, crash reporting.
- Scripts in giá trị environment.
- Operators có quyền trên container/host.

Không in `env` hoặc `printenv` toàn bộ trong ticket chỉ để kiểm tra một property.

### 13.2. Không truyền password trực tiếp trong shell history

Tránh kiểu lệnh chứa plaintext secret ở command arguments hoặc history:

~~~bash
# Anti-pattern: lộ secret trong shell history/process arguments.
java -jar app.jar --spring.mongodb.uri="mongodb://admin:real-password@..."
~~~

Ưu tiên secret injection an toàn từ runtime/secret manager. Với URI chứa password, xem toàn bộ value là secret.

### 13.3. Environment không tự reload sau rotation

Java process đọc environment lúc start; khi Kubernetes Secret thay đổi, process hiện tại không tự có environment value mới. Cần rolling restart hoặc cơ chế recreate client an toàn.

## 14. Spring configtree: đọc secret từ mounted files

Spring Boot hỗ trợ `spring.config.import` với prefix `configtree:`. Tên file trở thành property key, nội dung file trở thành value.

Giả sử runtime mount secret:

~~~text
/run/secrets/mongodb/
    spring.mongodb.uri
~~~

Nội dung file `spring.mongodb.uri` là URI thật và được quản lý ngoài Git.

Boot 4.x application.yml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/mongodb/"
~~~

Lúc khởi động, Spring Boot đọc file đó thành property `spring.mongodb.uri`.

### 14.1. Tương ứng với Boot 3.5

Nếu dùng Boot 3.5, mounted filename là:

~~~text
spring.data.mongodb.uri
~~~

Và `spring.config.import` vẫn dùng `configtree:/run/secrets/mongodb/`.

### 14.2. Không dùng optional cho production secret bắt buộc

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/mongodb/"
~~~

`optional:` cho phép bỏ qua thư mục không tồn tại. Nó hữu ích cho một số dev setups, nhưng trong production có nguy cơ app start với default/wrong URI. Nếu secret bắt buộc, **không** đặt optional trừ khi đã có validation và nguồn cấu hình bắt buộc khác.

### 14.3. File permissions

- Chỉ workload identity/container cần thiết có quyền đọc.
- Không lưu private secret ở world-readable path.
- Không mount cả thư mục chứa secrets không liên quan.
- Tránh chép volume secret vào debug artifacts.
- Giới hạn quyền truy cập node/container host.

### 14.4. Mounted file đổi không đồng nghĩa MongoClient đổi

`configtree:` chủ yếu nạp property khi Spring khởi động. Nếu file secret đổi trong lúc process chạy, `MongoClient` đã được tạo trước đó không mặc nhiên thay credentials/SSLContext. Cần lifecycle refresh/restart được kiểm thử.

## 15. Kubernetes Secrets và Spring Boot

Một hướng đi thực tế là **Secret** được cấp từ secret manager/External Secrets/CSI và mount thành file vào Pod.

~~~text
Cloud/Vault secret source
           |
           v
    Secret delivery controller
           |
           v
     Kubernetes Pod volume
           |
     /run/secrets/mongodb/
           |
           v
     Spring configtree import
           |
           v
        MongoClient
~~~

### 15.1. Ví dụ Pod spec rút gọn cho Boot 4.x

Đây là **trích đoạn deployment spec**, không phải manifest đầy đủ:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: orders-api
          image: registry.example.test/orders-api:approved-version
          volumeMounts:
            - name: mongodb-config
              mountPath: /run/secrets/mongodb
              readOnly: true
      volumes:
        - name: mongodb-config
          secret:
            secretName: orders-mongodb-connection
            items:
              - key: mongo-uri
                path: spring.mongodb.uri
~~~

Ứng dụng:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/mongodb/"
~~~

Secret object `orders-mongodb-connection` phải được tạo bởi một quy trình bảo mật. Không commit một manifest `stringData` chứa URI/password thật.

### 15.2. Base64 không phải encryption

Kubernetes Secret `data` thường biểu diễn bytes dưới base64. Điều này **không** làm nội dung an toàn trước người có quyền đọc Secret hoặc etcd snapshots. Cần Kubernetes RBAC, encryption at rest, network controls và secret lifecycle.

### 15.3. Chỉ cấp quyền cần thiết

Service account của Pod không nên có quyền `get/list` mọi Secrets trong namespace khi chỉ cần một mounted secret. Tách secrets theo service và môi trường.

### 15.4. Cẩn thận khi dùng subPath

Kubernetes Secret volume có cơ chế cập nhật tệp theo thời gian, nhưng mount qua `subPath` không nhận cập nhật theo cách thông thường. Dù volume được cập nhật, ứng dụng vẫn cần thiết kế reload MongoClient.

### 15.5. Rolling restart an toàn

Khi credentials thay đổi:

1. Provision secret mới và database principal tương ứng.
2. Khởi động một canary Pod dùng secret mới.
3. Kiểm tra TLS/auth và nghiệp vụ.
4. Rollout từng Pod.
5. Xác nhận toàn bộ workers/scheduled jobs đã chuyển.
6. Thu hồi credential cũ theo approved window.

## 16. Secrets manager: Vault, AWS, Azure, Google

Các lựa chọn điển hình:

- HashiCorp Vault / Vault Agent.
- AWS Secrets Manager.
- Azure Key Vault.
- Google Secret Manager.
- Kubernetes External Secrets / CSI Secret Store integrations.
- Spring Cloud Vault / Spring Cloud Config hoặc integrations có hỗ trợ phù hợp.

### 16.1. Ai đọc secret?

~~~text
Spring Boot workload identity
           |
           v
      Secret manager IAM
           |
           v
   Secret version "current"
           |
           v
   URI / username / password
           |
           v
     MongoClient startup
~~~

Ưu tiên **workload identity** hoặc short-lived cloud credentials thay vì hardcode API key của secret manager để đọc password database.

### 16.2. Đừng chuyển bí mật từ Git sang một file plaintext vô chủ

Đưa `application.yml` ra ngoài repository không đủ nếu file nằm trên shared filesystem, backup công khai, hoặc mọi Pods đều có quyền đọc.

### 16.3. Config import qua Spring Cloud tích hợp

Một số Spring Cloud starters cho phép import property sources từ Vault/Config Server. Syntax, authentication backend, fail-fast, lease renewal và compatibility phụ thuộc **Spring Cloud release train, Spring Boot version và provider**. Không coi mọi integration đều có cùng cơ chế tự làm mới `MongoClient`.

### 16.4. Cân nhắc tính sẵn sàng của secret manager

Ứng dụng có thể cần lấy secret trước khi tạo MongoClient. Nếu secret manager unavailable, startup có thể thất bại. Thiết kế retry có giới hạn, cache/lease theo chính sách và khôi phục an toàn; không fallback sang password hardcoded.

## 17. SCRAM và cơ sở dữ liệu xác thực

SCRAM là cơ chế password-based authentication phổ biến. MongoDB hỗ trợ `SCRAM-SHA-256` và `SCRAM-SHA-1`; prefer cơ chế mạnh/được deployment hỗ trợ.

### 17.1. authSource phải khớp nơi user được tạo

Ví dụ service user được quản lý ở `admin` nhưng thao tác database `orders`:

~~~text
mongodb://<user>:<password>@db.example.test:27017/orders?authSource=admin&tls=true
~~~

Nếu dùng `authSource=orders` trong khi user thực tế được định nghĩa ở `admin`, server có thể trả `AuthenticationFailed` dù password đúng.

### 17.2. Atlas database users phải quản lý qua Atlas

MongoDB Atlas database users được tạo/thay qua Atlas UI, CLI, Admin API hoặc integrations được hỗ trợ. Không dùng các lệnh self-managed như `db.changeUserPassword` trực tiếp trên Atlas để quản trị users.

### 17.3. Self-managed tạo user trên môi trường lab

~~~javascript
use orders

db.createUser({
  user: "orders_api_v1",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "orders" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

Chỉ dùng trên self-managed lab được bật TLS/auth và có quyền quản trị. Nếu user tạo ở database `orders` thì URI dùng `authSource=orders`, không tự đặt `admin`.

### 17.4. Không dùng user root cho ứng dụng

Một service chỉ cần đọc/ghi orders không cần role `root` hoặc `userAdminAnyDatabase`. Giảm blast radius bằng principal riêng cho mỗi service, môi trường và workload.

## 18. TLS: đường truyền và xác minh danh tính server

TLS làm hai việc quan trọng:

1. Mã hóa traffic từ Java Driver tới MongoDB.
2. Giúp driver xác minh server qua certificate chain và hostname.

~~~text
Spring Boot / MongoClient
        |
  TLS + CA trust + SAN check
        |
        v
MongoDB / mongos
~~~

### 18.1. TLS có thể được cấu hình qua URI

~~~text
mongodb://db.example.test:27017/orders?tls=true
~~~

Với Atlas SRV, TLS thường bật mặc định theo MongoDB SRV rules; vẫn phải giữ xác minh CA và hostname.

### 18.2. Không dùng tlsInsecure để “sửa nhanh”

Những tùy chọn như `tlsInsecure=true`, `tlsAllowInvalidHostnames=true` hoặc custom trust-all `SSLContext` làm giảm an toàn, có thể cho phép server giả mạo.

Sửa nguyên nhân: CA bundle, SAN, hostname, truststore, expiry hoặc network endpoint.

### 18.3. TLS và SCRAM khác lớp

TLS handshake thành công không có nghĩa username/password đúng; SCRAM thành công không chứng minh ứng dụng có role ghi collection cần thiết.

## 19. Spring Boot SSL bundles

Spring Boot có khái niệm **SSL bundle** cho trust material và tùy chọn TLS.

Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
    ssl:
      bundle: "mongo-ca"
  ssl:
    bundle:
      pem:
        mongo-ca:
          truststore:
            certificate: "file:/etc/certs/mongodb-ca.pem"
~~~

Boot 3.5 dùng đường dẫn `spring.data.mongodb.ssl.bundle` thay cho `spring.mongodb.ssl.bundle`.

### 19.1. Bundle giúp giải quyết gì?

Thay vì tự viết `SSLContext`/trust manager trong ứng dụng, cấu hình trust material qua Spring Boot SSL bundle được framework hỗ trợ.

### 19.2. Chứng chỉ CA có thể được quản lý như config có kiểm soát

CA public certificate không phải private key, nhưng tính toàn vẹn của truststore cực kỳ quan trọng: chèn một CA không đáng tin có thể khiến driver tin server giả mạo.

### 19.3. Client certificate/mTLS

Nếu dùng X.509 client authentication, cần certificate và private key phù hợp trong keystore/SSLContext, cùng user identity mapping được MongoDB hỗ trợ. Một truststore chứa CA không tự xác thực client bằng X.509.

### 19.4. Thay trust file có cần restart không?

Không mặc nhiên. Khả năng reload của SSL bundles/connection pool phụ thuộc framework, source, implementation và version. Với MongoClient, thường cần tạo TLS connections/client mới để kiểm tra cert mới; lập kế hoạch rolling restart hoặc cơ chế refresh có kiểm soát.

## 20. X.509, IAM và OIDC: khi nào không dùng password?

Tùy MongoDB deployment/tier/driver, có thể dùng:

- X.509 certificate authentication.
- AWS IAM authentication.
- OIDC workload identity federation.

### 20.1. X.509

Client có private key/certificate và MongoDB ánh xạ identity theo X.509 subject. Rotation cần quản lý cert/key, CA trust và có thể cả MongoDB user mapping.

### 20.2. AWS IAM

Driver xác thực bằng AWS identity/credentials theo cơ chế được hỗ trợ; tránh lưu MongoDB SCRAM password dài hạn. Nhưng workload vẫn cần IAM policies, credential refresh và protection.

### 20.3. OIDC

Ứng dụng có thể dùng token từ IdP/workload identity federation khi driver/server/tier hỗ trợ. Cần kiểm tra hỗ trợ MongoDB/Atlas và cấu hình `MONGODB-OIDC`/token callbacks theo driver version; không giả định chỉ thêm `authMechanism=MONGODB-OIDC` vào URI là đủ ở mọi môi trường.

### 20.4. Passwordless không có nghĩa không cần security policy

IAM policy quá rộng, token bị log hoặc client private key bị lộ vẫn gây rủi ro. Quyền database và token/cert lifecycle cần được đánh giá độc lập.

## 21. Tùy chỉnh MongoClientSettings thay vì thay toàn bộ client

Khi auto-configuration gần đúng, Spring Boot cho phép đăng ký `MongoClientSettingsBuilderCustomizer`.

**Điểm khác biệt theo phiên bản:**

| Spring Boot | Package của interface |
|---|---|
| 3.5 | `org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer` |
| 4.x | `org.springframework.boot.mongodb.autoconfigure.MongoClientSettingsBuilderCustomizer` |

### 21.1. Ví dụ Boot 4.x

~~~java
package example.orders.config;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.mongodb.autoconfigure.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MongoTuningConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoClientTuning() {
        return builder -> {
            builder.applicationName("orders-api");
            builder.applyToConnectionPoolSettings(pool -> {
                pool.maxSize(40);
                pool.minSize(5);
                pool.maxWaitTime(2, TimeUnit.SECONDS);
            });
            builder.applyToClusterSettings(cluster ->
                cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
            );
            builder.applyToSocketSettings(socket ->
                socket.connectTimeout(3, TimeUnit.SECONDS)
            );
        };
    }
}
~~~

### 21.2. Boot 3.5 thay import

Trong code trên, thay import bằng:

~~~java
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
~~~

Đừng chép cả hai imports cùng lúc. MongoDB Java Driver/Spring Boot version thực tế cần hỗ trợ các method signatures minh họa; dùng BOM tương thích.

### 21.3. Tác dụng

- `maxSize(40)`: giới hạn số connections trong pool theo server.
- `minSize(5)`: số lượng connections tối thiểu theo cấu hình pool.
- `maxWaitTime(2s)`: giới hạn thời gian chờ checkout khi pool bận.
- `serverSelectionTimeout(5s)`: thời gian tìm server đáp ứng operation.
- `connectTimeout(3s)`: thời gian chờ lập socket connection.

Các giá trị chỉ là **ví dụ có thể đo đạc**, không phải defaults/best settings cho mọi ứng dụng.

### 21.4. Đừng ghi đè security config

Customizer có thể thay `MongoClientSettings` ở thời điểm builder được xây dựng. Tránh set lại credential/SSL settings không có chủ đích. Sau khi thêm customizer, phải verify URI, TLS, auth và topology như trước.

### 21.5. Tự khai báo MongoClientSettings bean có thể khiến properties bị bỏ qua

Spring Boot docs nêu khi tự cung cấp `MongoClientSettings`, auto-configuration xử lý khác so với settings tự dựng; URI/host properties có thể không được áp như trước. Ưu tiên customizer nhỏ thay vì replace toàn bộ bean nếu không cần.

## 22. Chọn connection pool size bằng đo lường

Ví dụ có 20 application Pods, mỗi Pod `maxSize=100`, driver có thể mở nhiều connections tới từng server theo topology và pool settings. Không suy ra chính xác tổng cluster connections chỉ bằng 20×100 nếu chưa xét số target servers, monitoring connections và hoạt động thực tế.

### 22.1. Metrics nên theo dõi

- Pool checkout wait p95/p99.
- Pool checkout timeouts.
- Connections current/available trên MongoDB.
- Total connections created rate.
- MongoDB command duration.
- Driver retries/server-selection timeouts.
- Node CPU, disk I/O, queues.

### 22.2. Pool lớn không chữa được truy vấn chậm

Nếu query mất 3 giây vì thiếu index, tăng pool có thể làm nhiều truy vấn chậm chạy song song và khiến disk/CPU tệ hơn.

### 22.3. Min size, idle time và TLS handshakes

Min pool size có thể tăng connections lâu dài và startup overhead. Chọn theo traffic, CPU, số Pods và connection limits, không theo cảm giác “càng nhiều càng tốt”.

### 22.4. Không tạo pool mỗi request

Đảm bảo `MongoClient` singleton là một bean dùng lại. Trường hợp nhiều tenants/multiple clients có thể cần nhiều pools, nhưng phải tính tổng connection budget.

## 23. Timeout khác nhau, không có một "Mongo timeout"

| Timeout | Lớp | Dấu hiệu nếu vượt |
|---|---|---|
| DNS resolution | DNS/OS | Host không resolve |
| Connection establishment | Socket/TCP/TLS | Không mở được socket/TLS |
| Server selection | Driver topology | Không tìm server phù hợp |
| Pool checkout | MongoClient pool | Không lấy được connection kịp |
| Socket read | Driver network I/O | Đọc response quá lâu |
| Operation deadline | Client/operation | Operation vượt thời gian cho phép |
| HTTP request | Application gateway/service | User timeout |
| Transaction lifetime | MongoDB transaction | Transaction bị timeout theo server |

### 23.1. Ví dụ tác hại của timeout quá lớn

Nếu HTTP timeout 3 giây nhưng driver server-selection timeout 30 giây, request có thể timeout từ phía user trong khi background/thread vẫn chờ. Cần thiết kế deadlines xuyên tầng.

### 23.2. Timeout quá nhỏ cũng gây false failures

Một server election vài giây có thể nằm trong failover expectations. Đặt server selection timeout 100ms trên production replica set có thể gây lỗi không cần thiết.

### 23.3. Bounded retries, backoff và idempotency

Không retry vô hạn khi database quá tải hoặc unreachable. Retry phải có deadline, exponential backoff/jitter và hiểu rõ operation có idempotent không.

## 24. Quản lý secrets rotation: cùng user hay hai users?

Giả sử API đang dùng `orders_api_v1`. Có hai chiến lược:

| Tiêu chí | Đổi password cùng user | Tạo user v2 |
|---|---|---|
| Hai credentials hợp lệ đồng thời | Không theo cách cơ bản | Có trong cửa sổ chuyển |
| Canary trước khi thu hồi cũ | Khó hơn | Dễ |
| Khả năng tránh downtime | Phụ thuộc consumers reload chính xác | Thường tốt hơn |
| Cleanup | Ít hơn | Cần revoke user v1 |
| Rủi ro credential bị lộ | Cần revoke nhanh | Không giữ v1 nếu compromised |

### 24.1. Với Spring Boot, vấn đề lớn là pool đã được tạo

Đổi password trong MongoDB nhưng ứng dụng vẫn dùng `MongoClient` tạo từ password cũ có thể gây lỗi khi driver tạo connection mới. Một số connections cũ vẫn hoạt động trong thời gian ngắn, khiến lỗi xuất hiện không đồng đều.

### 24.2. Pattern dual-account

~~~text
Time T0:
 MongoDB: orders_api_v1 active
 Apps: all v1

Time T1:
 MongoDB: orders_api_v1 + orders_api_v2 active
 Secret Manager: v2 staged

Time T2:
 Canary app Pods: v2
 Remaining Pods: v1

Time T3:
 All Pods/workers/jobs: v2

Time T4:
 Revoke orders_api_v1
 Retire old secret version
~~~

### 24.3. Các bước thực hiện

1. Inventory tất cả services, batch jobs, ETL, scheduled tasks và CI automation dùng v1.
2. Sinh password v2 trong secrets manager.
3. Tạo database principal v2 với roles tương đương/thu hẹp.
4. Stage secret mới theo version.
5. Rollout canary Spring Boot Pod để **tạo MongoClient mới**.
6. Kiểm tra TLS, SCRAM, read/write, transaction và latency.
7. Rollout lần lượt, theo dõi auth code 18 và pool errors.
8. Kiểm tra scheduled consumers sau một chu kỳ.
9. Thu hồi user v1.
10. Thu hồi/retire secret version cũ và lưu audit.

### 24.4. Không dùng mật khẩu cũ làm rollback khi đã lộ

Nếu rotation do credential compromised, rollback về v1 tiếp tục mở đường tấn công. Lúc đó dùng incident response, thu hồi sớm và chấp nhận biện pháp containment theo SLO.

### 24.5. Giữ chứng cứ không chứa secret

Audit log có thể ghi:

~~~json
{
  "event": "mongodb-credential-rotation",
  "service": "orders-api",
  "principal": "orders_api_v2",
  "result": "success",
  "newClientAuthenticated": true
}
~~~

Không lưu plaintext password hoặc full URI.

## 25. Secret refresh không đồng nghĩa MongoClient refresh

Một trong những hiểu nhầm phổ biến:

~~~text
Kubernetes Secret updated
           |
           v
Mounted file changes
           |
        (chưa đủ)
           |
           v
Spring Environment có thể chưa đọc lại
           |
        (chưa đủ)
           |
           v
MongoClient pool vẫn dùng cấu hình cũ
~~~

### 25.1. Ba chiến lược

**A. Rolling restart:** đơn giản, đáng tin cậy nếu ứng dụng stateless/replicas đủ và startup/health tốt.

**B. Recreate MongoClient bean theo cơ chế ứng dụng có kiểm soát:** phức tạp hơn, cần chuyển traffic/pools/requests và đóng client cũ. Không chỉ gọi `@RefreshScope` rồi tự tin connection pools đã đổi.

**C. Driver-managed auth token refresh:** phù hợp với một số mechanisms như OIDC khi driver/provider hỗ trợ; cần tuân thủ callbacks/expiration semantics.

### 25.2. Chọn theo SLA và tần suất rotate

Nếu rotate password mỗi vài tháng, rolling restart có thể đơn giản hơn tự xây runtime client swap. Nếu credentials rất ngắn hạn, cân nhắc identity-based auth hoặc integration chuyên biệt.

### 25.3. Secret file atomic replacement

Secret mounts có thể thay symlink/file metadata thay vì ghi đè nội dung in-place. Một watcher tự viết cần xử lý events phù hợp; chỉ kiểm tra modification time không đủ trong mọi môi trường.

## 26. Health checks bằng Spring Boot Actuator

Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot có health contributor cho MongoDB khi có cấu hình/beans phù hợp. Endpoint `/actuator/health` có thể cho biết trạng thái nền tảng.

### 26.1. Chỉ expose các endpoints cần thiết

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
~~~

Trong production, `env`, `configprops`, `heapdump` và các endpoints khác cần policy bảo mật chặt; không expose toàn bộ chỉ để debug credential.

### 26.2. Liveness, readiness và startup khác nhau

- **Liveness:** process có cần restart không?
- **Readiness:** process đã sẵn sàng nhận request phù hợp?
- **Startup:** quá trình khởi tạo đã hoàn tất?

Nếu readiness phụ thuộc MongoDB theo cách không kiểm soát, một outage database có thể khiến toàn bộ Pods bị loại khỏi service hoặc gây restart storm. Thiết kế probes dựa trên failure mode và chiến lược traffic của ứng dụng.

### 26.3. Ping MongoDB chưa bảo đảm quyền ứng dụng

MongoDB `ping` thành công không chứng minh repository query được quyền đọc/writes hoặc unique indexes đúng. Cần canary business-level smoke tests và permission verification riêng.

### 26.4. Không làm health check thành query nặng

Dùng operation nhỏ, có timeout rõ và không scan collection lớn. Nếu mỗi Pod gọi `countDocuments()` trên hàng triệu documents mỗi giây, monitoring có thể trở thành nguồn tải.

## 27. Instrumentation driver và tránh lộ dữ liệu

MongoDB Java Driver có `CommandListener`, connection pool listeners và monitoring hooks. Một ứng dụng Spring Boot có thể theo dõi:

- Command success/failure count và duration.
- Pool checkout wait time.
- Server selection timeouts.
- Connections created/closed.
- TLS/auth failures.
- Retry patterns và topology changes.

### 27.1. Ví dụ listener không in raw command

~~~java
package example.orders.config;

import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import java.util.concurrent.TimeUnit;

public final class SafeCommandListener implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent e) {
        // Không log e.getCommand(): có thể chứa customer PII.
        System.out.println("started " + e.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent e) {
        System.out.println(
            e.getCommandName() + " success "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent e) {
        System.out.println(
            e.getCommandName() + " failed "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }
}
~~~

Đây chỉ là code minh họa API. Trong production, dùng Micrometer/metrics tracing với sampling và kiểm soát nhãn, thay `System.out`.

### 27.2. Cách đăng ký listener bằng customizer

Trong Boot 4.x:

~~~java
@Bean
MongoClientSettingsBuilderCustomizer commandObservability() {
    return builder -> builder.addCommandListener(new SafeCommandListener());
}
~~~

Bean này cần nằm trong `@Configuration` có import Boot 4.x ở mục 21. Boot 3.5 chỉ đổi import của interface.

### 27.3. Không ghi URI và query values

Những thứ tránh đưa vào log:

- Password, access token, private key.
- MongoDB URI đầy đủ có credentials.
- Full aggregation pipelines chứa user values.
- Driver exception messages chưa được redacted.
- Environment variables của secrets manager.
- Full Actuator `/env` payload.

## 28. Secret masking không phải kiểm soát duy nhất

Spring Boot Actuator có sanitization cho `env`/`configprops`, nhưng security policy không nên dựa duy nhất vào masking.

- Log framework có thể in property trước khi sanitization.
- Debug interceptor có thể in request/response.
- Heap dumps có thể chứa secrets trong memory.
- Build artifacts có thể chứa `application-prod.yml` bị hardcode.
- K8s RBAC có thể cho người khác đọc Secret.
- CI pipeline có thể echo command-line arguments.

### 28.1. Dùng secret scanners

Dùng repository scanning, pre-commit checks và CI secret detection. Nếu URI đã bị commit, xóa khỏi Git HEAD không đủ: credential phải được rotate/revoke và historical exposure phải được đánh giá.

### 28.2. Security tests

Có thể tự động kiểm tra:

- Không có password literal trong `src/main/resources/application*.yml`.
- Không có `tlsInsecure=true` trong production config.
- Không có `mongodb://admin:...` trong logs/config.
- Container không chạy với mounted secret directory world-readable.
- Principal không có role quản trị rộng ngoài nhu cầu.

## 29. Spring Boot test: cô lập môi trường test

Không dùng production URI trong CI/test suite.

### 29.1. Dùng một database riêng cho test

~~~yaml
# application-test.yml - Boot 4.x
spring:
  mongodb:
    uri: "${MONGODB_TEST_URI}"
~~~

Với Boot 3.5, chuyển sang `spring.data.mongodb.uri`.

### 29.2. Testcontainers

Spring Boot có tích hợp Testcontainers service connections ở những phiên bản/dependencies được hỗ trợ. Bạn có thể sử dụng MongoDB container để chạy integration tests với database cô lập.

Một số lựa chọn:

- `@ServiceConnection` khi sử dụng Spring Boot Testcontainers integration đúng version.
- `@DynamicPropertySource` để inject container replica URI vào property đúng prefix.
- `MongoDBContainer` từ Testcontainers (package có thể thay đổi theo major version của Testcontainers).

**Không** copy một import của Testcontainers 1.x sang 2.x mà không xem dependency đang dùng.

### 29.3. Ý tưởng với DynamicPropertySource

Pseudocode theo Spring Boot 4.x:

~~~java
// Đoạn minh họa - cần thay loại container/import theo phiên bản Testcontainers.
@DynamicPropertySource
static void mongoProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.mongodb.uri", mongoContainer::getReplicaSetUrl);
}
~~~

Với Boot 3.5, key là `spring.data.mongodb.uri`. Biến `mongoContainer` phải được khai báo/start đúng theo Testcontainers setup; không giả định đoạn rút gọn compile độc lập.

### 29.4. Test kết nối và quyền

Kiểm thử:

1. Repository save/find.
2. Index/unique constraint theo requirements.
3. Timeouts khi DB tạm unavailable.
4. Failover behavior nếu test topology hỗ trợ.
5. Không dùng root quyền vô hạn như production.
6. CI không có quyền đọc production secret.

## 30. Debug lỗi: một cây quyết định

~~~text
Ứng dụng không truy cập MongoDB
              |
              v
      Đọc error category
       /       |        \
      /        |         \
 DNS/socket   TLS      Authentication
    |          |           |
    v          v           v
 Host/SRV    CA/SAN    user/authSource
 network     expiry    secret version
    |          |           |
    +----------+-----------+
               |
               v
    Server selection / topology
               |
               v
       Authorization / queries
               |
               v
       Pool and timeout / SLO
~~~

### 30.1. DNS SRV failures

Kiểm tra SRV/TXT từ chính Pod/VM. Có thể gặp resolver không hỗ trợ SRV, network policy chặn DNS hoặc stale DNS caches. Không mặc định password sai.

### 30.2. ServerSelectionTimeoutException

Các hướng:

- Seed hosts không reachable.
- Network ACL/private endpoint sai.
- `replicaSet` tên không khớp.
- Driver không khám phá được members.
- TLS handshake failures.
- Primary unavailable.
- Timeout quá thấp cho failover.

### 30.3. AuthenticationFailed / code 18

Kiểm tra:

- Username/password/secret version.
- `authSource`.
- SCRAM vs X.509/OIDC mechanism.
- URI percent-encoding.
- Tài khoản bị disable/drop/rotate.
- User được tạo ở đúng database/Atlas project.

Không tự động reset password trước khi biết nguyên nhân.

### 30.4. Authorization failure

Nếu kết nối thành công nhưng save/read bị từ chối, user có thể thiếu role. Giải pháp là least-privilege role đúng resource, **không** cấp `root`.

### 30.5. SSLHandshakeException / PKIX failures

Thường kiểm tra CA chain, truststore, certificate SAN/hostname, expiry và proxy/network interception. Không bật trust-all SSL context.

### 30.6. Timeouts và pool exhaustion

Nếu MongoDB commands nhanh nhưng API chậm, xem pool checkout wait, server selection, retries và network. Không tăng `maxSize` một cách mù quáng.

### 30.7. Kết nối nhầm database

Kiểm tra Boot version property prefix, profile, environment precedence, database override, authSource và connection target. Không log full URI để “xem cho rõ”.

## 31. Bảng lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân hay gặp | Điều cần kiểm chứng |
|---|---|---|
| Startup dùng localhost | Property không được bind/missing | Boot 3 vs 4 prefix, profiles |
| URI đúng nhưng user auth fail | authSource hoặc secret sai | User auth DB, credential version |
| Có username/password rời nhưng không tác dụng | URI đã set | URI precedence |
| Password chứa @/# gây lỗi parse | Chưa percent-encode | URI syntax |
| Atlas SRV không resolve | DNS SRV/TXT/network | DNS từ runtime |
| Server selection timeout | Host/TLS/topology | Driver logs, network, replica set |
| SSL handshake fail | CA/SAN/expiry | Truststore/SSL bundle |
| Ping OK nhưng save fail | Authorization thiếu | Roles, collection privileges |
| App chạy nhưng pool bị cạn | Concurrency/retries/pool sizing | Checkout wait, current connections |
| Sau secret rotate chỉ vài Pods lỗi | Pods còn v1 credentials | Rollout status và pools |
| K8s Secret đã đổi nhưng app vẫn dùng cũ | Env/startup config không reload | Restart/client recreation |
| YAML prod có URI lab | Profile/precedence sai | Effective sanitized properties |
| Test suite ghi vào prod | CI dùng production secret | Namespaces/IAM isolation |
| Không nhận được metrics | Actuator/exporter cấu hình sai | Health endpoint exposure/permissions |
| Logs chứa URI | Unsafe debug/exception output | Redaction và log policy |
| TLS cert mới nhưng app cũ vẫn chạy | Pooled connections vẫn sống | New TLS handshake |
| Boot 4 customizer không compile | Package di chuyển | Import Boot 4.x |
| Boot 3 customizer không compile | Import Boot 4.x nhầm | Import Boot 3.5 |

## 32. Checklist production trước khi triển khai

### Version và dependencies

- [ ] Xác định Spring Boot 3.5 hay 4.x.
- [ ] Dùng property prefix đúng version.
- [ ] Dùng Spring Boot BOM cho Spring Data/Java Driver.
- [ ] Chọn sync/reactive đúng application architecture.
- [ ] Không khai báo MongoClient bean tùy ý nếu auto-config đủ.
- [ ] Kiểm tra API package customizer đúng version.

### Connection và topology

- [ ] MongoDB URI trỏ đúng cluster/region.
- [ ] authSource khớp principal.
- [ ] SRV DNS hoạt động trong runtime.
- [ ] TLS/CA/hostname verification bật.
- [ ] Network access/Atlas project đúng.
- [ ] Replica set discovery/primary failover được test.
- [ ] Retry/read/write concern được quyết định theo yêu cầu.
- [ ] Connection pool được benchmark và quan sát.
- [ ] Timeouts phù hợp HTTP request deadlines.

### Secrets

- [ ] Không có credentials hardcoded trong Git/image.
- [ ] URI/password đến từ runtime secret source được bảo vệ.
- [ ] Per-service/per-environment least-privilege DB users.
- [ ] Secret manager IAM có least privilege và audit.
- [ ] Kubernetes RBAC/encryption at rest phù hợp.
- [ ] Không dùng `optional:` cho secret bắt buộc nếu không có fallback an toàn.
- [ ] Có rotation owner, deadline và consumer inventory.
- [ ] Có dual-account/rolling restart plan.
- [ ] Không dùng credential compromised làm rollback.
- [ ] Logs, Actuator, metrics và tickets không lộ secrets.

### Tests và operations

- [ ] Có local/test database cô lập.
- [ ] CI không đọc production MongoDB secret.
- [ ] Health checks đúng vai trò và không quá tải.
- [ ] Có canary new MongoClient/TLS handshake.
- [ ] Có test query/permission/transaction nghiệp vụ.
- [ ] Có alert cho auth failures, pool wait và latency.
- [ ] Có runbook cho DNS, TLS, auth, topology và rotation.
- [ ] Có owner và audit khi thay config/secret.

## 33. Bài tập thực hành

### Bài 1 — Tầng công nghệ

Phân biệt vai trò Spring Boot, Spring Data MongoDB và MongoDB Java Driver trong một query repository.

### Bài 2 — Sync hay reactive?

Một ứng dụng Spring MVC gọi MongoRepository blocking. Có cần đổi sang reactive chỉ vì dùng MongoDB không?

### Bài 3 — Prefix Boot 3.5

Viết `application.yml` dùng `spring.data.mongodb.uri` và placeholder `${MONGODB_URI}`.

### Bài 4 — Prefix Boot 4.x

Viết cấu hình tương đương dùng `spring.mongodb.uri`. Nêu tên environment variable cho direct relaxed binding.

### Bài 5 — URI composition

Giải thích `authSource`, `replicaSet`, `tls` và `appName` trong một URI.

### Bài 6 — Credentials có ký tự đặc biệt

Vì sao password chứa `@` hoặc `#` cần percent-encode nếu nằm trong URI?

### Bài 7 — AuthSource

User được tạo tại `orders` nhưng URI dùng `authSource=admin`. Điều gì có thể xảy ra?

### Bài 8 — Atlas SRV

Khi `mongodb+srv://` không resolve trong Pod nhưng trên laptop chạy, nên kiểm tra gì?

### Bài 9 — Prefix migration

Ứng dụng Boot 3.5 chuyển sang 4.x nhưng giữ `spring.data.mongodb.uri`. Chẩn đoán triệu chứng.

### Bài 10 — Property precedence

`application-prod.yml` ghi URI A nhưng runtime dùng URI B. Những property sources nào có thể override?

### Bài 11 — Profiles

Thiết kế local, staging và production không dùng chung DB users.

### Bài 12 — No default secret

Vì sao `${MONGODB_URI:mongodb://admin:password@...}` là anti-pattern?

### Bài 13 — Configtree

Tạo mounted file `spring.mongodb.uri` và cấu hình `spring.config.import`. Có cần sửa code Repository không?

### Bài 14 — Kubernetes Secret

Giải thích vì sao base64 không phải mã hóa. Những RBAC permissions nào cần hạn chế?

### Bài 15 — Mounted file update

Secret mount thay đổi trong Pod nhưng MongoClient không đổi. Vì sao?

### Bài 16 — Secrets Manager

Thiết kế workload identity → secrets manager → Spring Boot và cơ chế khi secret manager unavailable.

### Bài 17 — Least privilege

Một API chỉ đọc reports đang dùng role `root`. Đề xuất principal/role phù hợp.

### Bài 18 — TLS verification

Ứng dụng lỗi PKIX khi server đổi CA. Tại sao không bật `tlsInsecure`?

### Bài 19 — SSL bundle

Boot 4.x dùng property nào để gán SSL bundle cho MongoDB? Boot 3.5 khác thế nào?

### Bài 20 — X.509

Phân biệt CA truststore với client certificate/keystore. Vì sao truststore không tự tạo X.509 database identity?

### Bài 21 — Customizer

Viết một `MongoClientSettingsBuilderCustomizer` giới hạn maxPoolSize và serverSelectionTimeout. Nêu import của Boot 3.5 và 4.x.

### Bài 22 — Pool sizing

Có 20 Pods và max pool=100. Vì sao không thể kết luận cluster luôn có đúng 2.000 active connections?

### Bài 23 — Timeout layers

Phân biệt socket connect timeout, server selection timeout và connection pool checkout wait.

### Bài 24 — Dual account

Thiết kế v1 → v2 credential rotation để có canary, rollout, verify và revoke.

### Bài 25 — Secret compromise

Một production URI bị commit công khai. Nêu các bước revoke, rotate và audit, không chỉ xóa commit.

### Bài 26 — Actuator

Vì sao không expose `/actuator/env` ra internet? Endpoint `/actuator/health` có chứng minh application read/write OK không?

### Bài 27 — Testcontainers

Dùng `@DynamicPropertySource` để inject MongoDB test URI. Property key thay thế nào cho Boot 3.5 và 4.x?

### Bài 28 — Driver metrics

Thiết kế CommandListener chỉ log command name/duration, không log payload chứa PII.

### Bài 29 — Authentication vs authorization

`ping`/authentication pass nhưng repository save bị denied. Nên điều tra điều gì trước khi thay password?

### Bài 30 — Topology failures

Phân biệt lỗi DNS, TLS, authentication và server-selection timeout.

### Bài 31 — Business correctness

Sau maintenance MongoDB, một health check pass nhưng query phân trang chậm gấp 10 lần. Thiết kế bước post-deploy verification.

### Bài 32 — Tổng hợp production

Thiết kế hệ thống Spring Boot 4.x + MongoDB Atlas phục vụ orders API:

- Dùng starter đồng bộ và repository.
- URI MongoDB SRV cấp từ secrets manager.
- TLS trust/Atlas network controls.
- Least-privilege database user.
- Configtree volume với IAM/RBAC.
- MongoClientSettingsBuilderCustomizer cho pool/timeouts.
- Actuator health và driver metrics.
- Integration tests với database cô lập.
- Rotation v1/v2 qua rolling restart.
- Alerting và incident runbook.

## 34. Tổng kết

**Cấu hình kết nối Spring Boot + MongoDB** phải được nhìn như một chuỗi thiết kế vận hành:

1. Spring Boot tự tạo MongoClient/Spring Data beans khi dependencies và properties phù hợp.
2. Spring Boot 3.5 dùng `spring.data.mongodb.*`; dòng 4.x chuyển connection settings sang `spring.mongodb.*`.
3. MongoDB URI quyết định host/SRV, database, authentication source, TLS và một phần driver options; credentials trong URI là secrets.
4. `application.yml` nên chứa placeholders hoặc external config references, **không** chứa production password.
5. Environment variables, configtree, Kubernetes Secrets và cloud secret managers giúp phân phối secrets nhưng vẫn phải có IAM/RBAC, audit, at-rest protection và lifecycle.
6. TLS truststore/SSL bundle phải xác minh CA/SAN; không tắt hostname verification để cứu lỗi kết nối.
7. MongoClient có connection pool nên được tái sử dụng; cấu hình timeouts/pool sizes phải đo từ workload, không copy số tùy ý.
8. Secret rotation yêu cầu tạo client/pool mới và kiểm tra canary; dual-account pattern giúp chuyển mà không cắt ngay principal cũ.
9. Health, logs, driver metrics và integration tests phải kiểm chứng không chỉ ping mà cả quyền và behavior nghiệp vụ.

Một hệ thống an toàn không chỉ có thể **kết nối đến MongoDB**, mà còn biết chính xác **đang kết nối đến đâu, bằng danh tính nào, ai kiểm soát credentials, và làm thế nào thay hoặc thu hồi chúng mà không phá ứng dụng**.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 4.x — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/4.0/reference/data/nosql.html)
- [Spring Boot 4.x — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot 3.5 API — MongoClientSettingsBuilderCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/mongo/MongoClientSettingsBuilderCustomizer.html)
- [Spring Boot 4.x API — MongoClientSettingsBuilderCustomizer](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/mongodb/autoconfigure/MongoClientSettingsBuilderCustomizer.html)
- [Spring Data MongoDB — Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html)
- [Spring Data MongoDB — MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [MongoDB Manual — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Java Sync Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-options/)
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Java Sync Driver — TLS](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/)
- [MongoDB Atlas — Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
