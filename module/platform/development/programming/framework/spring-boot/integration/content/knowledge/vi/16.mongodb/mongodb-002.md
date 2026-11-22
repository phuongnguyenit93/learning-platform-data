# URI kết nối, database và cấu hình `spring.data.mongodb.*`

## 1. Mục tiêu và bối cảnh

Khi Spring Boot tích hợp MongoDB, điều đầu tiên cần làm rõ là **ứng dụng kết nối đến cụm MongoDB nào, sử dụng danh tính nào và thao tác trên database nào**. Một URI có thể kết nối tới đúng máy chủ nhưng lại xác thực sai database, đọc sai bộ dữ liệu hoặc dùng một chính sách timeout không phù hợp với luồng tích hợp.

Trong module **SPRING_BOOT_INTEGRATION**, MongoDB có thể giữ dữ liệu nghiệp vụ, read model, nhật ký tích hợp, inbox/outbox hoặc trạng thái của một workflow. Các luồng này thường còn kết nối tới HTTP client, cache và broker thông điệp. Vì vậy, việc cấu hình MongoDB cần tính đến hợp đồng dữ liệu, giao dịch, lỗi, chống xử lý trùng, kiểm thử và khả năng quan sát, bên cạnh chuyện “kết nối thành công”.

Sau bài học, bạn có thể:

1. Phân tích URI `mongodb://` và `mongodb+srv://`, đặc biệt là host, database, `authSource` và các tùy chọn.
2. Cấu hình kết nối MongoDB qua `spring.data.mongodb.*` trong Spring Boot 3.x.
3. Phân biệt database ứng dụng dùng với database lưu thông tin xác thực.
4. Cấu hình replica set, TLS, timeout, connection pool, read/write concern có chủ đích.
5. Sử dụng `MongoTemplate` và `MongoRepository` do Spring Boot tự cấu hình.
6. Chẩn đoán lỗi kết nối, bảo vệ thông tin bí mật và kiểm thử với MongoDB thật.

> **Phạm vi phiên bản:** Ví dụ dùng Java 17+, **Spring Boot 3.x / Spring Data MongoDB 4.x** và MongoDB Java Sync Driver phù hợp với BOM của Spring Boot. Thuộc tính `spring.data.mongodb.*` trong bài theo cấu trúc Boot 3.x. Khi nâng sang **Spring Boot 4.x**, cần đối chiếu migration guide và configuration metadata của đúng phiên bản vì các nhóm thuộc tính MongoDB đã được tổ chức lại; không tự sao chép nguyên `application.yml` từ 3.x mà không kiểm chứng.

## 2. Kiến trúc kết nối trong Spring Boot

```mermaid
flowchart LR
    APP["Business service / Integration adapter"] --> REPO["MongoRepository"]
    APP --> TPL["MongoTemplate"]
    REPO --> FACT["MongoDatabaseFactory"]
    TPL --> FACT
    FACT --> CLIENT["MongoClient<br/>MongoDB Java Driver"]
    CLIENT --> POOL["Connection pool / TLS / Auth"]
    POOL --> RS[("MongoDB replica set<br/>hoặc sharded cluster")]
    CFG["spring.data.mongodb.*<br/>Environment / Secret"] --> CLIENT
    CFG --> FACT
```

Spring Boot kết hợp Spring Data MongoDB với MongoDB Java Driver:

| Thành phần | Vai trò |
| --- | --- |
| `MongoClient` | Quản lý kết nối và pool tới các server trong topology MongoDB. |
| `MongoDatabaseFactory` | Quyết định cách lấy `MongoDatabase` để Spring Data thao tác. |
| `MongoTemplate` | API cấp thấp thuận tiện cho query, update, aggregate, index và các thao tác MongoDB khác. |
| `MongoRepository` | API repository cho entity/document, query method và CRUD. |
| `MongoTransactionManager` | Quản lý client session và transaction MongoDB khi được đăng ký, nếu hạ tầng hỗ trợ. |
| `spring.data.mongodb.*` | Khai báo vị trí, database, credential và các thiết lập tích hợp Spring Data của Boot 3.x. |

Một `MongoClient` nên được **tái sử dụng** cùng connection pool trong vòng đời ứng dụng. Không tạo `MongoClient` mới cho mỗi HTTP request, mỗi Kafka message hoặc mỗi repository operation.

**Lưu ý về kết nối lười (lazy):** việc khởi tạo `MongoClient` hoặc Spring context không phải lúc nào cũng chứng minh cluster truy cập được. Kết nối và server selection có thể diễn ra khi thực thi thao tác đầu tiên. Muốn xác minh thực sự, dùng lệnh `ping`, health indicator hoặc một test đọc/ghi có kiểm soát.

## 3. Hai định dạng MongoDB connection string

MongoDB dùng connection string/URI để mô tả cluster, thông tin xác thực, database mặc định và driver options. Có hai dạng chính.

### 3.1. URI tiêu chuẩn: `mongodb://`

```text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/[database][?options]
```

Ví dụ đọc được topology của một replica set:

```text
mongodb://app_user:<encoded-password>@mongo-1.example.internal:27017,mongo-2.example.internal:27017,mongo-3.example.internal:27017/orders_integration?authSource=admin&replicaSet=rs0&tls=true&retryWrites=true&w=majority
```

Trong ví dụ:

| Phần | Ý nghĩa |
| --- | --- |
| `mongodb://` | Dùng danh sách host theo URI chuẩn. |
| `app_user` và password | Danh tính kết nối. Password được mã hóa theo quy tắc URI nếu chứa ký tự đặc biệt. |
| Ba host | Các địa chỉ để driver khám phá replica set; không phải ba database độc lập. |
| `/orders_integration` | Database mặc định trong URI, thường là database ứng dụng truy cập. |
| `authSource=admin` | Database dùng để xác thực credential; không nhất thiết là database nghiệp vụ. |
| `replicaSet=rs0` | Tên replica set mong đợi; giúp driver xác minh topology. |
| `tls=true` | Yêu cầu kết nối TLS. |
| `retryWrites=true` | Cho phép driver thử lại một số thao tác ghi đủ điều kiện khi điều kiện triển khai đáp ứng. |
| `w=majority` | Đặt write concern: chờ mức xác nhận majority theo topology. |

Danh sách host trong URI phục vụ **khám phá và failover**, không có nghĩa mỗi thao tác sẽ được ghi lên mọi host trực tiếp bởi client. Driver theo dõi topology và chọn server phù hợp với thao tác, read preference, trạng thái replica set và chính sách server selection.

### 3.2. URI DNS Seed List: `mongodb+srv://`

```text
mongodb+srv://app_user:<encoded-password>@cluster.example.mongodb.net/orders_integration?retryWrites=true&w=majority
```

Với tiền tố `mongodb+srv://`, driver tra DNS SRV/TXT theo quy tắc kết nối MongoDB để khám phá các endpoint và một số tùy chọn. Đây là định dạng thường gặp khi dùng MongoDB Atlas hoặc hệ thống có DNS SRV:

- Phần host là **một hostname** dùng để tra SRV; không liệt kê nhiều host/port trong URI SRV.
- TLS được bật mặc định với URI SRV, trừ trường hợp cấu hình phù hợp ghi đè theo quy tắc driver; trong production nên kiểm tra chính sách TLS thực tế.
- Container/Kubernetes cần phân giải được bản ghi SRV/TXT và có đường mạng tới những endpoint DNS trả về.
- Không suy diễn rằng hostname SRV trỏ tới một server duy nhất; driver vẫn cần truy cập topology do DNS và metadata MongoDB cung cấp.

Nếu DNS của môi trường không hỗ trợ SRV hoặc việc truy cập endpoint quảng bá bị firewall chặn, ứng dụng có thể báo server selection timeout dù cú pháp URI đúng.

### 3.3. Mã hóa tên người dùng và mật khẩu trong URI

Các ký tự dành riêng trong URI như `@`, `:`, `/`, `?`, `#`, `%` trong credential cần được **percent-encode** theo cú pháp URI. Ví dụ password logic là `p@ss:word` thì phần password trong URI phải mã hóa các ký tự dành riêng, chẳng hạn `p%40ss%3Aword`.

Không coi mã hóa URI là mã hóa bảo mật: chuỗi vẫn có thể bị giải mã dễ dàng. URI chứa credential phải được quản lý như **secret**: cung cấp qua secret manager/environment, hạn chế xuất hiện trong log, exception, tracing, màn hình debug và mã nguồn.

Khi không chắc quy tắc encode, dùng thư viện xây URI hoặc cấu hình username/password riêng theo khả năng của phiên bản, không tự ghép credential thô vào connection string.

## 4. Database đích và `authSource` khác nhau thế nào?

Đây là một trong những lỗi phổ biến nhất khi tích hợp MongoDB.

Giả sử ứng dụng quản lý dữ liệu tại database `orders_integration` nhưng user `order_app` được tạo trong database `admin`:

```text
mongodb://order_app:<encoded-password>@mongo.example.internal:27017/orders_integration?authSource=admin
```

Hợp đồng của URI:

- `orders_integration`: **database đích** cho các collection như `orders`, `integration_events`.
- `admin`: **authentication database** nơi server tìm thông tin tài khoản `order_app`.
- Quyền truy cập collections vẫn do role/privilege của user quyết định; xác thực thành công ở `admin` không tự cấp quyền đọc ghi mọi database.

Trong URI có username/password nhưng **không có `authSource`**, MongoDB dùng quy tắc xác định authentication database từ phần path database (nếu có) hoặc mặc định phù hợp, thường là `admin` khi không chỉ định database. Do đó, việc đổi phần `/orders_integration` có thể đồng thời làm thay đổi nơi driver tìm user nếu không khai báo `authSource` tường minh.

### 4.1. URI khác với tên database của Spring Data

Trong Spring Boot 3.x có hai cách thông dụng để chỉ định database ứng dụng:

```yaml
# Cách A: database nằm trong URI.
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/orders_integration
```

```yaml
# Cách B: để Spring Data chọn database qua thuộc tính riêng.
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017
      database: orders_integration
```

Trong Boot 3.x, `spring.data.mongodb.database` có thể xác định database mà `MongoDatabaseFactory` sử dụng ngay cả khi URI cũng có database path. Dù vậy, **không nên khai báo hai tên database khác nhau** ở URI và property: có thể gây nhầm về database đang đọc/ghi và authentication fallback. Nếu user xác thực ở database khác, hãy chỉ rõ `authSource=...`.

Một cấu hình dễ gây hiểu nhầm:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://order_app:secret@mongo:27017/legacy_db
      database: orders_integration
```

Ngay cả khi Spring Data dùng `orders_integration` để đọc/ghi, driver có thể dựa vào phần URI để xác định cơ sở xác thực nếu không có `authSource`. Nên sửa thành **một nguồn chân lý** cho database và authentication source rõ ràng.

> **Phân biệt khi debug:** database “ứng dụng đang đọc/ghi” lấy từ `MongoDatabaseFactory`, còn authentication source lấy từ cấu hình credential của MongoDB driver. Hai giá trị có thể khác nhau một cách hợp lệ.

### 4.2. Cách kiểm tra database thực tế

Trong một test hoặc diagnostic endpoint chỉ dùng nội bộ:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class MongoConnectionCheck {
    private final MongoTemplate template;

    public MongoConnectionCheck(MongoTemplate template) {
        this.template = template;
    }

    public String databaseName() {
        return template.getDb().getName();
    }

    public Document pingServer() {
        return template.executeCommand(new Document("ping", 1));
    }
}
```

`template.getDb().getName()` cho biết tên database Spring Data đang dùng, nhưng **không chứng minh kết nối mạng đã thành công**. `pingServer()` mới yêu cầu driver thực hiện lệnh thật. Không trả toàn bộ thông tin cluster hoặc URI chứa credential qua một endpoint công khai.

## 5. Dependency và auto-configuration trong Spring Boot 3.x

Với ứng dụng Spring MVC/imperative, starter:

```xml
<!-- pom.xml: dự án đã có Spring Boot parent/BOM tương ứng -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu ứng dụng reactive, có `spring-boot-starter-data-mongodb-reactive` và các bean như `ReactiveMongoTemplate`, `ReactiveMongoRepository`; không tráo API đồng bộ và reactive mà không xét kiến trúc. Bài này dùng starter **đồng bộ** để làm rõ URI và cấu hình.

Khi có dependency phù hợp và không bị ứng dụng tự định nghĩa bean thay thế, Spring Boot 3.x thường tự tạo:

1. `MongoClient` từ các thuộc tính kết nối.
2. `MongoDatabaseFactory` chọn database.
3. `MongoTemplate` dùng converter/mapping của Spring Data.
4. Hạ tầng Spring Data MongoDB Repository cho các interface `MongoRepository` nằm trong vùng package được scan.

Vì thế, ứng dụng thường chỉ cần inject `MongoTemplate` hoặc repository. Không phải tự viết `MongoClients.create(...)` trừ khi có yêu cầu đặc biệt như nhiều MongoDB cluster, custom credential provider hoặc topology riêng.

```mermaid
sequenceDiagram
    participant B as Spring Boot
    participant C as Configuration
    participant D as MongoDB Driver
    participant M as MongoDB
    B->>C: Bind spring.data.mongodb.*
    C-->>B: URI + database + options
    B->>D: Tạo MongoClient / MongoTemplate
    Note over B,D: Khởi tạo bean chưa chắc đã ping server
    B->>D: Query / ping đầu tiên
    D->>M: Server selection, auth, TLS, command
    M-->>D: Result / lỗi
    D-->>B: Document hoặc exception
```

## 6. Cấu hình `spring.data.mongodb.*` cơ bản

### 6.1. Cách khuyến nghị cho một cluster: dùng URI

```yaml
# application.yml cho môi trường local.
spring:
  application:
    name: order-integration
  data:
    mongodb:
      uri: ${MONGODB_URI:mongodb://localhost:27017/orders_integration}
      auto-index-creation: false
```

Trong production, đặt `MONGODB_URI` bằng secret/environment của nền tảng triển khai. Tránh dùng default URI local trên môi trường production mà không có cơ chế kiểm tra cấu hình, vì ứng dụng có thể kết nối nhầm cluster hoặc tự sinh dữ liệu ở một database không mong muốn.

`auto-index-creation: false` thể hiện chính sách quản trị index có kiểm soát: index được tạo qua migration/deployment thay vì tự tạo bất ngờ khi ứng dụng khởi động. Nếu bật tự động tạo index, cần kiểm thử tác động của index build, unique constraint và thay đổi schema trước khi deploy.

### 6.2. Cấu hình rời host/port/database/credential

Khi chỉ có một server hoặc cấu hình đơn giản, có thể dùng cách khai báo field riêng:

```yaml
# application-local.yml: PHƯƠNG ÁN THAY THẾ URI, không gộp với ví dụ trên.
spring:
  data:
    mongodb:
      host: localhost
      port: 27017
      database: orders_integration
      username: ${MONGODB_USERNAME}
      password: ${MONGODB_PASSWORD}
      authentication-database: admin
```

Nếu username/password không được dùng ở local, hãy bỏ hẳn các field thay vì để chuỗi bí mật giả và trông đợi server bỏ qua. Các tên như `authentication-database` là property của Spring Boot 3.x; khác với tùy chọn URI `authSource` của MongoDB driver nhưng cùng mô tả nơi xác thực.

**Không cấu hình cả URI và host/port/username/password một cách mâu thuẫn.** Spring Boot có quy tắc lựa chọn và bind property theo phiên bản; khi có URI, nhiều thông tin driver được lấy từ URI. Sử dụng một phương án nhất quán giúp giảm rủi ro ứng dụng kết nối sai môi trường.

### 6.3. Bảng thuộc tính thường gặp

| Thuộc tính Boot 3.x | Mục đích | Ghi chú |
| --- | --- | --- |
| `spring.data.mongodb.uri` | MongoDB connection string. | Chứa host/topology, database, auth và options. Coi là secret nếu có credential. |
| `spring.data.mongodb.host` | Host cho kết nối đơn giản. | Ưu tiên URI cho replica set/SRV/phương án nhiều host. |
| `spring.data.mongodb.port` | Cổng MongoDB. | Thường 27017, nhưng phụ thuộc môi trường. |
| `spring.data.mongodb.database` | Database Spring Data sử dụng. | Tránh khác tên với path database của URI. |
| `spring.data.mongodb.username` | Tài khoản kết nối. | Bổ sung password và authentication database tương ứng. |
| `spring.data.mongodb.password` | Password kết nối. | Secret, không commit giá trị thực. |
| `spring.data.mongodb.authentication-database` | Database dùng xác thực với cách cấu hình field. | Tương đương mục đích `authSource` trong URI. |
| `spring.data.mongodb.auto-index-creation` | Có tự tạo index từ mapping annotation không. | Thường để `false` khi quản trị index bằng migration. |
| `spring.data.mongodb.gridfs.database` | Database riêng cho GridFS nếu dùng GridFS. | Chỉ cần khi ứng dụng thực sự lưu file qua GridFS. |

Các tên như `maxPoolSize`, `serverSelectionTimeoutMS` hay `retryWrites` là **option của MongoDB driver trong URI**, không phải tùy tiện thêm thành `spring.data.mongodb.max-pool-size` hay `spring.data.mongodb.retry-writes` rồi kỳ vọng Boot nhận diện.

## 7. Cấu hình URI cho môi trường production

Một ví dụ URI tiêu chuẩn có nhiều tùy chọn driver:

```text
mongodb://app_user:<encoded-password>@mongo-1.example.internal:27017,mongo-2.example.internal:27017,mongo-3.example.internal:27017/orders_integration?authSource=admin&replicaSet=rs0&tls=true&retryWrites=true&w=majority&appName=order-integration&serverSelectionTimeoutMS=5000&connectTimeoutMS=2000&socketTimeoutMS=10000&maxPoolSize=40&maxConnecting=4&waitQueueTimeoutMS=3000
```

Các giá trị là **ví dụ**, không phải một preset cho mọi ứng dụng. Nên phân tích từng nhóm:

### 7.1. Server selection và timeout

| URI option | Tác dụng | Điều cần lưu ý |
| --- | --- | --- |
| `serverSelectionTimeoutMS` | Giới hạn thời gian driver tìm được server phù hợp để thực hiện operation. | Có thể timeout do topology/network chứ không chỉ do query chậm. |
| `connectTimeoutMS` | Giới hạn thời gian thiết lập một kết nối socket. | Không phải timeout của toàn bộ business flow. |
| `socketTimeoutMS` | Thời gian chờ thao tác socket theo driver. | Có thể làm operation timeout khi server xử lý lâu; cần kiểm chứng theo driver/version. |
| `waitQueueTimeoutMS` | Giới hạn thời gian chờ lấy connection từ pool. | Giúp phát hiện saturation thay vì chờ vô hạn. |
| `appName` | Gắn tên client vào metadata kết nối. | Hữu ích cho chẩn đoán, tránh đưa user/tenant ID vào tên. |

Ví dụ một command timeout sau khi gửi không chứng minh MongoDB chưa xử lý write. Với lệnh có side effect và được retry từ application, cần business key/unique index hoặc cơ chế idempotency phù hợp.

### 7.2. Connection pool

`MongoClient` quản lý connection pool theo server/topology. Các option:

- `maxPoolSize`: giới hạn số kết nối có thể được giữ trong pool tới một server.
- `minPoolSize`: số kết nối tối thiểu mà pool cố gắng duy trì, nếu cấu hình.
- `maxConnecting`: giới hạn số kết nối được tạo đồng thời trong mỗi pool.
- `waitQueueTimeoutMS`: thời gian operation đợi một kết nối sẵn sàng khi pool bận.

Kích thước pool cần được cân đối với số instance/pod, concurrency của HTTP request, Kafka listeners và giới hạn kết nối của cluster. Nếu mỗi pod có pool tối đa 100 và tăng số pod lên 50, tổng số kết nối tiềm năng lớn hơn nhiều so với một pod đơn lẻ. Tăng `maxPoolSize` không giải quyết được query thiếu index hoặc downstream chậm.

Đừng tạo một MongoClient mới cho từng sự kiện chỉ để thay database; cách đó tạo pool riêng và gây áp lực lên broker database. Với multi-tenancy, thiết kế rõ chiến lược database-per-tenant, collection-per-tenant hoặc tenant field, giới hạn nguồn tên database và pool thay vì chuyển database tùy ý từ HTTP header.

### 7.3. TLS và authentication

- Dùng `tls=true` với kết nối qua mạng không tin cậy hoặc cluster yêu cầu TLS. Hostname phải hợp lệ với chứng chỉ server.
- Đặt truststore/CA và các cấu hình Java TLS tương ứng theo chính sách hạ tầng. Đừng tắt xác minh hostname/certificate chỉ để kết nối được.
- Phân quyền user theo **least privilege**: tài khoản ứng dụng chỉ đọc/ghi đúng database/collection cần thiết.
- Tách tài khoản migration/admin khỏi tài khoản thực thi nghiệp vụ.
- Quản lý credential bằng secret manager, hỗ trợ rotation và tránh in toàn bộ URI trong log.
- Với SRV hoặc managed cluster, kiểm tra cơ chế authentication thực tế: SCRAM, x.509, AWS IAM/OIDC hoặc phương án provider hỗ trợ; không áp một cấu hình username/password cho mọi môi trường.

### 7.4. Replica set và chính sách độ bền

`replicaSet=rs0` cần khớp tên replica set hiện hành. URI chứa nhiều host nhưng không có topology phù hợp có thể gây lỗi chọn primary hoặc chậm failover.

Một số tùy chọn tác động đến độ bền/tính nhất quán:

| Option | Ý nghĩa | Không nên hiểu nhầm |
| --- | --- | --- |
| `retryWrites=true` | Driver có thể retry một số write eligible khi có lỗi tạm thời. | Không bảo đảm mọi command nghiệp vụ sẽ không chạy hai lần. |
| `w=majority` | Đợi mức xác nhận write concern majority theo topology. | Không thay thế yêu cầu schema, unique index hay application transaction. |
| `readPreference=primary` | Ưu tiên đọc từ primary. | Chọn server đọc, không tự đảm bảo snapshot thống nhất qua nhiều request. |
| `readConcernLevel=majority` | Yêu cầu đọc dữ liệu đáp ứng mức read concern majority. | Không đồng nghĩa một transaction xuyên HTTP/Kafka/database. |

Phối hợp read/write concern và session tùy yêu cầu. Nếu flow đọc ngay sau write và cần bảo đảm causal consistency, phải đánh giá session, topology và read/write concern, không tự mặc định rằng mọi đọc ở replica phụ sẽ thấy write vừa xảy ra.

## 8. Phân tách local, test và production

Các môi trường khác nhau về DNS, TLS, dữ liệu và quyền truy cập. Thay vì nhúng cluster production trong mã, hãy để Boot nhận cấu hình từ bên ngoài.

```yaml
# application.yml: chọn một đường cấu hình qua URI.
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
      auto-index-creation: false
```

Ví dụ giá trị env tương ứng:

```text
# Local development (MongoDB thực sự chạy trên chính máy này)
MONGODB_URI=mongodb://localhost:27017/orders_integration

# CI integration test (do test framework cung cấp)
MONGODB_URI=mongodb://test-mongo:27017/orders_it

# Production (mang tính cấu trúc, lấy secret từ secret manager)
MONGODB_URI=mongodb+srv://<user>:<encoded-password>@cluster.example.mongodb.net/orders_integration?retryWrites=true&w=majority
```

**Không đưa giá trị production thực vào file kiểm soát phiên bản**. Trên Docker, `localhost` trong một container trỏ tới chính container đó; nếu MongoDB chạy ở container khác, dùng tên service DNS trong network hoặc endpoint do nền tảng cung cấp. Trên Kubernetes, cần service/DNS, route, network policy và trust chain đúng với môi trường cluster.

### 8.1. Kiểm tra cấu hình khi khởi động

Một chính sách startup hữu ích:

1. Kiểm tra env `MONGODB_URI` tồn tại ở production.
2. Validate scheme/host và database có trong danh sách được phép, không in credential.
3. Kiểm tra quyền truy cập bằng health indicator/ping (nếu production readiness yêu cầu).
4. Xác nhận index quan trọng đã tồn tại trước khi tiêu thụ message.
5. Kiểm tra cấu hình retry, timeout, connection pool và metrics phù hợp với số instance.

Khi thiếu DNS, chứng chỉ hoặc credential, application có thể khởi động xong nhưng fail ở command đầu tiên. Vì vậy, health checks và integration tests cần dựa trên một operation thật, không chỉ xác minh bean `MongoTemplate` tồn tại.

## 9. Dùng `MongoTemplate` và `MongoRepository` với database đã cấu hình

Giả sử `order-service` ghi nhận một sự kiện tích hợp để phục vụ đối soát. Định nghĩa một document trong file `IntegrationAudit.java`:

```java
package com.example.integration.mongo;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "integration_audit")
public record IntegrationAudit(
    @Id String id,
    String sourceSystem,
    String eventType,
    Instant receivedAt
) {}
```

Khi Spring Data mapping một `IntegrationAudit`, trường `id` tương ứng với `_id` của document trên MongoDB. Collection là `integration_audit` **trong database được cấu hình**, ví dụ `orders_integration`.

### 9.1. Dùng repository

```java
package com.example.integration.mongo;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface IntegrationAuditRepository
    extends MongoRepository<IntegrationAudit, String> {

    List<IntegrationAudit> findByEventType(String eventType);
}
```

Service nghiệp vụ có thể inject repository:

```java
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class IntegrationAuditService {
    private final IntegrationAuditRepository repository;

    public IntegrationAuditService(IntegrationAuditRepository repository) {
        this.repository = repository;
    }

    public void recordReceivedEvent(
        String eventId,
        String sourceSystem,
        String eventType
    ) {
        repository.save(new IntegrationAudit(
            eventId,
            sourceSystem,
            eventType,
            Instant.now()
        ));
    }
}
```

Ví dụ này minh họa cấu hình và mapping. **Không coi `save(...)` trên cùng `_id` là đủ cho mọi bài toán dedup**: nó có thể ghi đè document cũ và phát sinh những side effect khác nếu logic xung quanh không lũy đẳng. Khi cần chống xử lý lại một event, dùng unique constraint/insert có kiểm tra hoặc transaction/inbox rõ ràng.

### 9.2. Dùng `MongoTemplate` trực tiếp

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component
public class AuditQueryGateway {
    private final MongoTemplate template;

    public AuditQueryGateway(MongoTemplate template) {
        this.template = template;
    }

    public List<IntegrationAudit> findBySource(String sourceSystem) {
        Query query = Query.query(
            Criteria.where("sourceSystem").is(sourceSystem)
        );
        return template.find(query, IntegrationAudit.class);
    }
}
```

Tương tự repository, `MongoTemplate` trên dùng database đã chọn bởi `MongoDatabaseFactory`. Nó không tự chuyển database mỗi khi method nhận sourceSystem/tenant khác; nếu ứng dụng có nhiều database, phải thiết kế routing rõ ràng và bảo vệ tên database khỏi input không tin cậy.

## 10. Index, lệnh ghi lặp và hợp đồng dữ liệu

Trong luồng nhận sự kiện từ Kafka hoặc RabbitMQ, message có thể được giao lại sau crash/rebalance. MongoDB hỗ trợ lũy đẳng ở tầng lưu trữ bằng unique index hoặc thao tác atomic trên một document.

Ví dụ thiết kế collection inbox:

```javascript
// Mongo shell: chạy qua migration hoặc tác vụ provisioning có kiểm soát.
db.processed_events.createIndex(
  { consumerName: 1, eventId: 1 },
  { unique: true, name: "uq_consumer_event" }
);
```

Nhờ index, hai consumer cố ghi cùng `(consumerName, eventId)` sẽ không thể cùng tạo hai marker. Tuy nhiên, cách **chỉ ghi marker rồi gọi HTTP/email ngoài transaction** có thể làm mất side effect nếu bước sau lỗi.

### 10.1. Phân biệt một document atomic với nhiều bước

| Tình huống | Bảo đảm MongoDB hỗ trợ | Cần bổ sung |
| --- | --- | --- |
| Cập nhật một document bằng một lệnh phù hợp | Thao tác trên một document là atomic. | Điều kiện version/ID nếu cần tránh ghi lùi hoặc trùng. |
| Hai worker chèn cùng unique key | Unique index chặn hai bản ghi trùng. | Phân loại duplicate có chủ đích; không che lỗi schema. |
| Ghi marker vào collection A và projection vào collection B | Không tự atomic nếu là hai write riêng ngoài transaction. | Multi-document transaction hoặc thiết kế một document duy nhất. |
| Commit MongoDB xong rồi publish Kafka | Có thể crash trước khi gửi message. | Transactional outbox/CDC và consumer idempotent. |
| Xử lý event rồi commit offset Kafka | Có thể crash sau DB commit nhưng trước offset commit. | Inbox/dedup để an toàn khi redelivery. |
| Gọi HTTP/payment sau khi MongoDB commit | MongoDB không rollback được provider bên ngoài. | Stable idempotency key, inquiry, saga/compensation. |

Với những update có tính chất “đặt trạng thái”, ưu tiên lệnh có điều kiện theo version/sequence và một atomic update thay cho đọc-modify-ghi không được bảo vệ. Với các phép tăng/giảm số dư, tuyệt đối không suy luận rằng `$inc` tự lũy đẳng: phát lại cùng lệnh sẽ tăng/giảm thêm lần nữa.

### 10.2. Giao dịch MongoDB

Khi thật sự cần multi-document transaction và MongoDB chạy trên **replica set hoặc sharded cluster hỗ trợ transaction**, có thể đăng ký transaction manager:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory databaseFactory
    ) {
        return new MongoTransactionManager(databaseFactory);
    }
}
```

Khi gọi service method qua Spring proxy, `@Transactional` có thể ràng buộc các MongoDB writes cùng session/transaction, nếu template/repository sử dụng factory và transaction infrastructure tương ứng.

**Không mặc định MongoDB standalone dùng được multi-document transactions.** Không coi MongoDB transaction là transaction chung với PostgreSQL, Kafka hay HTTP API; điều phối giữa các hệ thống vẫn cần outbox, inbox, idempotency và đối soát.

## 11. Xử lý lỗi kết nối và lỗi dữ liệu

Một URI đúng cú pháp nhưng không đọc được dữ liệu có thể do nhiều nguyên nhân. Thường cần tách:

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `MongoTimeoutException` lúc query/ping | Không chọn được server phù hợp trong thời gian cho phép. | DNS, firewall, advertised endpoints, replica set state, latency. |
| `MongoSecurityException` | Username/password hoặc authentication source sai. | Kiểm tra user thuộc database nào, mechanism, secret rotation. |
| Lỗi TLS/certificate | CA/truststore, hostname, phiên bản TLS không tương thích. | Kiểm tra trust chain và hostname từ chính môi trường chạy. |
| Database rỗng dù kết nối thành công | Trỏ nhầm database/cluster hoặc credentials chỉ thấy tập dữ liệu khác. | `MongoTemplate.getDb().getName()`, env/profile, collection names. |
| `DuplicateKeyException` ở Spring Data | Vi phạm unique index khi insert/update. | Xem index và business ID, phân biệt replay hợp lệ với dữ liệu xung đột. |
| Lỗi unauthorized khi create index | User runtime thiếu quyền DDL. | Tách migration user và runtime user, kiểm tra `auto-index-creation`. |
| Pool wait/connection timeout | Query chậm, pool thiếu, số instance tăng, server bận. | Pool metrics, slow queries, index, topology và capacity. |
| URI SRV không phân giải | Không có DNS SRV/TXT hoặc bị chặn. | Kiểm tra DNS tại container/pod, không chỉ trên máy developer. |
| Failover làm tăng timeout tạm thời | Replica set election/server selection. | Kiểm tra topology events, retryable errors, timeout ngân sách. |

Một số lỗi MongoDB driver được Spring Data chuyển sang nhóm `DataAccessException`; trong các trường hợp khác có thể gặp driver exceptions. **Chỉ retry những lỗi được phân loại có thể phục hồi**, giữ cùng định danh nghiệp vụ nếu operation không thuần đọc, và giới hạn tổng số lần/thời gian retry.

### 11.1. Không đánh đồng lỗi mạng với “không tìm thấy”

Khi `repository.findById(id)` trả `Optional.empty()` sau truy vấn thành công, có thể không có document. Nhưng khi server selection timeout, auth sai hoặc lỗi decode, đó là **lỗi tích hợp**, không phải “không tìm thấy”. Đừng bắt toàn bộ exception rồi trả empty/default data: cách đó che sự cố, có thể dẫn tới tạo trùng hoặc quyết định nghiệp vụ sai.

## 12. Kiểm thử kết nối và database bằng MongoDB thật

Unit test mock `MongoTemplate` không kiểm tra URI, TLS, authentication, index hay mapping BSON. Để xác minh configuration, nên chạy MongoDB test container, replica set dùng cho CI hoặc cluster test phù hợp.

### 12.1. Dependency test

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mongodb</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ dành cho stack Testcontainers tương thích với Spring Boot 3.x; dùng dependency versions do BOM quản lý. Docker cần hoạt động trong môi trường CI để khởi chạy test container.

### 12.2. `@DataMongoTest` + Testcontainers

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataMongoTest
@Testcontainers
class MongoConnectionConfigurationTest {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void registerMongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            () -> mongo.getReplicaSetUrl("orders_it")
        );
    }

    @Autowired
    MongoTemplate template;

    @Test
    void usesConfiguredDatabaseAndCanExecuteCommand() {
        assertThat(template.getDb().getName())
            .isEqualTo("orders_it");

        Document result =
            template.executeCommand(new Document("ping", 1));

        assertThat(((Number) result.get("ok")).doubleValue())
            .isEqualTo(1.0);
    }
}
```

Ở test trên, `getReplicaSetUrl("orders_it")` tạo URI trỏ vào database test trên container, rồi `DynamicPropertySource` ghi đè URI trước khi Spring tạo client. `ping` thực sự mở kết nối và gửi command. Nếu test chạy cùng `application.yml` có `spring.data.mongodb.database` chỉ sang tên khác, phải loại bỏ/ghi đè property đó để tránh xung đột; test nên xác minh chính xác database mục tiêu.

**Chú ý môi trường:** tên image, API Testcontainers và dependency có thể khác khi dùng major version mới; chọn module và phiên bản phù hợp với BOM của dự án, không trộn cấu hình Testcontainers 1.x/2.x tùy tiện.

### 12.3. Ma trận kiểm thử quan trọng

| Test | Điều cần chứng minh |
| --- | --- |
| URI có database path | Spring Data chọn đúng database dự kiến. |
| `authSource` khác database đích | Đăng nhập thành công và có quyền trên đúng collection. |
| Password có ký tự đặc biệt | URI percent-encode đúng, không gặp lỗi parser/auth. |
| URI SRV | DNS SRV/TXT phân giải được từ container/pod thật. |
| TLS bắt buộc | Kết nối hợp lệ khi trust đúng và từ chối khi trust sai. |
| Replica set failover | Driver có thể phục hồi trong timeout/retry policy đã xác định. |
| Unique index | Hai write cùng business key không tạo bản ghi trùng. |
| Transaction | Các write cùng transaction commit/rollback theo yêu cầu. |
| Wrong database | Test phát hiện application trỏ nhầm database thay vì âm thầm dùng database rỗng. |
| Pool/timeout | Khi MongoDB bị chậm hoặc ngắt, client không chặn luồng vô hạn. |
| Health | Probe xác nhận cluster có thể nhận lệnh thực, không chỉ bean tồn tại. |

Đối với production, nên có smoke test chỉ đọc/`ping` hoặc kiểm tra riêng collection với dữ liệu không nhạy cảm. Không cho readiness probe tự ghi/xóa dữ liệu thật trên mỗi lần kiểm tra.

## 13. Quan sát và bảo mật khi vận hành

### 13.1. Health checks và metrics

Khi có Spring Boot Actuator, hệ thống có thể bật/khai thác health indicator MongoDB (nếu có bean và điều kiện auto-config tương ứng). Theo dõi:

- Thời gian chọn server, thời gian lấy kết nối từ pool, số connection đang dùng/chờ.
- Latency query, write, transaction, tỷ lệ timeout và retry.
- Lỗi xác thực, TLS, network và topology/failover.
- Số request HTTP/Kafka đang chờ database, consumer lag hoặc outbox backlog khi MongoDB chậm.
- Tăng trưởng collection/index, slow query, document size và write concern failures.

Driver metrics/command monitoring cần được cấu hình theo stack quan sát thực tế. Chỉ đưa nhãn ít biến thể như operation, collection, kết quả, exception class; tránh lấy customer ID, document ID hoặc full URI làm metric tag.

### 13.2. Log và secret

Không ghi trực tiếp `spring.data.mongodb.uri` khi chuỗi chứa username/password. Chỉ log những thuộc tính an toàn và cần thiết như database name, cluster alias đã khử nhạy cảm, application name, outcome của health check và exception category.

Khi debug:

1. Kiểm tra profile/env đang hoạt động, nhưng không in secret đầy đủ.
2. Xác nhận `MongoTemplate.getDb().getName()` là database mong đợi.
3. Ping hoặc chạy truy vấn đọc có kiểm soát.
4. Kiểm tra cluster topology, ACL và index.
5. Đối chiếu số liệu pool, timeout và request latency.

Không nới quyền database user thành admin hoặc tắt TLS hostname verification chỉ để làm lỗi biến mất.

## 14. Những lỗi cấu hình thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Bỏ path database trong URI, không có `database` property | Ứng dụng có thể không chọn được database phù hợp hoặc dùng mặc định không mong muốn. | Khai báo database rõ ràng và test. |
| Nhầm `authSource` là database lưu dữ liệu | Xác thực sai hoặc dữ liệu xuất hiện ở DB khác dự kiến. | Phân biệt database nghiệp vụ và authentication database. |
| Khai báo URI và `spring.data.mongodb.database` mâu thuẫn | Debug khó, có thể sai database/auth fallback. | Một nguồn chân lý và authSource tường minh. |
| Để password thô chứa `@`/`:` trong URI | URI parse sai, xác thực thất bại. | Percent-encode credential hoặc dùng cấu hình credential phù hợp. |
| Copy `mongodb://localhost` vào container | Kết nối tới chính container ứng dụng. | Dùng DNS service/endpoint cluster. |
| Dùng URI SRV nhưng DNS pod không hỗ trợ | Server selection timeout. | Kiểm tra SRV/TXT và outbound network. |
| Chỉ bật `retryWrites=true` rồi tin mọi workflow lũy đẳng | Side effect trùng hoặc event replay vẫn xảy ra. | Business IDs, unique index, inbox/outbox. |
| Đặt `maxPoolSize` quá lớn trên mọi pod | Cluster quá tải kết nối. | Tính tổng số instance và đo pool utilization. |
| Bật `auto-index-creation` trong production tùy tiện | Index build bất ngờ, có thể fail nếu dữ liệu trùng. | Migration/index provisioning có kiểm soát. |
| Mong `@Transactional` MongoDB hoạt động với standalone | Transaction không được hỗ trợ như replica set/sharded cluster. | Dùng topology phù hợp và transaction manager. |
| Coi startup thành công là DB đã kết nối | Request đầu tiên mới fail. | Ping/readiness và integration test. |
| Bắt hết MongoDB exception rồi trả dữ liệu rỗng | Che downtime và dẫn tới quyết định nghiệp vụ sai. | Phân loại network/auth/not-found/schema. |
| Gắn toàn bộ URI hoặc user ID làm metric tag | Lộ secret và tăng cardinality. | Chuẩn hóa labels, redaction. |

## 15. Quy trình thiết lập kết nối trong dự án thật

1. **Chọn database và topology:** standalone chỉ cho local phù hợp; replica set/sharded cluster cho nhu cầu availability, transaction và production.
2. **Xác định authentication:** user nằm ở database nào, cần quyền gì và cơ chế xác thực/TLS ra sao.
3. **Chọn một cách cấu hình:** URI chứa database hoặc property `spring.data.mongodb.database`; không trộn mâu thuẫn với host/port.
4. **Quản lý secret:** URI/credential ở secret manager, không commit/log mật khẩu.
5. **Đặt timeout/pool:** server selection, connect, socket, wait queue, max pool phù hợp concurrency và SLO.
6. **Cấu hình Spring Data:** starter đúng loại sync/reactive, inject `MongoTemplate`/repository, quản lý index qua migration.
7. **Chốt giao dịch và idempotency:** khi luồng liên quan Kafka, HTTP hoặc nhiều collection, nêu rõ ranh giới atomic và cơ chế inbox/outbox.
8. **Kiểm thử đúng database:** Testcontainers/cluster test với ping, CRUD, unique index, auth/TLS và tình huống failover.
9. **Giám sát:** health, latency, pool, topology, lỗi auth, slow query và backlog của các adapter tích hợp.

**Câu hỏi tự kiểm tra**

1. Trong URI `mongodb://u:p@mongo:27017/orders_integration?authSource=admin`, đâu là database ghi dữ liệu và đâu là nơi xác thực user?
2. `mongodb+srv://` khác gì `mongodb://` ở việc tìm host và TLS?
3. Vì sao không nên để URI trỏ `legacy_db` nhưng `spring.data.mongodb.database` trỏ `orders_integration`?
4. `serverSelectionTimeoutMS` khác gì `connectTimeoutMS` và `waitQueueTimeoutMS`?
5. Tại sao Spring context khởi động thành công chưa chứng minh MongoDB truy cập được?
6. Vì sao `retryWrites=true` không bảo đảm một Kafka event được áp dụng đúng một lần vào business state?
7. Khi transaction MongoDB commit rồi Kafka publish thất bại, cần cơ chế nào để không mất event?
8. Tại sao cần kiểm tra tổng kích thước connection pool qua tất cả pod thay vì chỉ một instance?

## 16. Tài liệu tham khảo

- [Spring Boot 3.5 — Working with NoSQL Technologies: MongoDB](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html#data.nosql.mongodb): auto-configuration, MongoDB properties, template và repository.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): đối chiếu tên `spring.data.mongodb.*` trong phiên bản 3.5.
- [Spring Data MongoDB — Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/): mapping, MongoTemplate, repositories, index và transactions.
- [MongoDB — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string/): cú pháp URI thường/SRV, database path và authentication options.
- [MongoDB — Connection Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): TLS, retry writes, read/write concern, timeouts và pool options.
- [MongoDB Java Sync Driver — Connection Guide](https://www.mongodb.com/docs/drivers/java/sync/current/connection/): MongoClient, server selection và connection pooling.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): tích hợp Testcontainers trong test ứng dụng.
