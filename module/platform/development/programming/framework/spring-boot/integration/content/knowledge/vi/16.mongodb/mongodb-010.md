# TLS, xác thực và truy cập dữ liệu theo quyền tối thiểu với MongoDB trong Spring Boot

Một dịch vụ Spring Boot có thể kết nối MongoDB, đọc và ghi document thành công ở môi trường phát triển nhưng vẫn **không đạt yêu cầu bảo mật production**. Những trường hợp thường gặp gồm: client truy cập MongoDB qua đường truyền không được mã hóa; kết nối TLS chấp nhận mọi chứng chỉ; ứng dụng dùng tài khoản `root`; nhiều service dùng chung một mật khẩu; API lấy `tenantId` trực tiếp từ request rồi truy vấn tài liệu của tenant khác; hoặc nhóm vận hành cấp thêm quyền admin chỉ để health check chuyển sang màu xanh.

Chương **MongoDB** của module **SPRING_BOOT_INTEGRATION** xem MongoDB là một phụ thuộc trong các luồng tích hợp Spring Boot qua HTTP client, database, cache, broker thông điệp và các adapter Spring Integration. Vì vậy, ngoài cách nối client, bài tập trung vào **hợp đồng dữ liệu, quyền truy cập, giao dịch, idempotency, lỗi xác thực, kiểm thử, observability và vận hành an toàn**.

Ba mục tiêu độc lập phải cùng được thực hiện:

1. **TLS**: bảo vệ tính bí mật và toàn vẹn của kết nối, xác thực danh tính server MongoDB.
2. **Authentication**: xác định **client/service nào** được phép kết nối với MongoDB.
3. **Authorization theo least privilege**: sau khi xác thực, service chỉ được thực hiện **những thao tác cần thiết** trên database/collection thích hợp.

Một đường truyền TLS hợp lệ **không** có nghĩa tài khoản đã được phân quyền an toàn. Một user có quyền đọc ít collection cũng **không** có nghĩa dữ liệu được mã hóa trên đường truyền. Và MongoDB RBAC theo collection **không tự phân tách document theo tenant**.

> **Phạm vi phiên bản:** Ví dụ hướng đến Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB Java Driver 4.x/5.x. Một số Spring Boot 3.x có SSL bundles nhưng tên property và cơ chế customizer tùy minor version. Ví dụ MongoDB server giả định bản hỗ trợ SCRAM-SHA-256, TLS và role-based access control (RBAC). Khi nâng cấp Boot/driver/MongoDB hoặc dùng MongoDB Atlas, hãy kiểm tra cơ chế cấu hình và quyền được sản phẩm triển khai thực sự hỗ trợ.

## 1. Mô hình đe dọa: ta đang bảo vệ điều gì?

Giả sử `order-service` lưu collection `orders`, `processed_events` và `outbox_events` vào database `orders`. REST controller nhận yêu cầu tạo đơn hàng; worker nhận sự kiện từ RabbitMQ và ghi trạng thái thanh toán; outbox relay đọc document chưa phát rồi gửi sang broker.

~~~mermaid
flowchart TD
    USER["HTTP caller"] --> API["Spring Boot order-service"]
    API --> AUTH["Xác thực caller + kiểm tra tenant"]
    AUTH --> MONGOCLIENT["MongoClient singleton / TLS"]
    MONGOCLIENT --> SERVER["MongoDB cluster"]
    SERVER --> ORD[("orders")]
    SERVER --> INBOX[("processed_events")]
    SERVER --> OUTBOX[("outbox_events")]
    OUTBOX --> RELAY["Outbox relay có MongoDB identity riêng"]
    RELAY --> MQ[("RabbitMQ / Kafka")]
    ADMIN["Migration/operator identity"] --> SERVER
~~~

Các mối đe dọa chính:

| Điểm tấn công/sai sót | Ví dụ | Kiểm soát phù hợp |
| --- | --- | --- |
| Nghe lén mạng | Một node mạng đọc thông tin đơn hàng | TLS cho kết nối client–MongoDB |
| Giả mạo database server | DNS/proxy đưa client tới endpoint giả | CA tin cậy, xác minh hostname/SAN, TLS đúng chuẩn |
| Lộ credentials | URI chứa password xuất hiện trong log hoặc Git | Secret manager, workload identity nếu hỗ trợ, xoay vòng |
| Đánh cắp tài khoản app | Kẻ tấn công dùng user `root` của service | Quyền chỉ trên các collection bắt buộc |
| Tài khoản quá quyền | Worker có thể `dropDatabase` | Custom role, tách role DDL và runtime |
| Truy cập chéo tenant | Caller tự thay `tenantId` trong JSON | Xác thực ở app, query luôn ràng buộc tenant |
| NoSQL query injection | Input JSON có `$ne`, `$where` được dùng thẳng làm filter | DTO typed, validation, query builder |
| Retry sau lỗi mạng | Ghi document đã commit nhưng caller nhận timeout | Idempotency key, unique index, đối soát kết quả |
| Rò dữ liệu qua log/metrics | Full document, connection URI, certificate key | Redaction, data classification, giới hạn quyền |
| Phụ thuộc ngoài MongoDB lỗi | DB transaction commit nhưng publish broker thất bại | Transactional outbox và worker riêng |

**Security boundary** không dừng ở MongoDB authentication: client HTTP/broker phải xác thực caller; ứng dụng phải bảo vệ identity và payload; và infrastructure phải bảo vệ network path, certificate, secret cũng như dữ liệu sao lưu.

## 2. TLS bảo vệ kết nối gì và không bảo vệ điều gì?

MongoDB wire protocol truyền query, response và lệnh quản trị trên kết nối TCP; TLS cung cấp mã hóa, xác thực server qua certificate và kiểm tra toàn vẹn trong quá trình trao đổi.

Một TLS handshake an toàn thường gồm:

1. Client thiết lập TCP tới hostname/port đã cấu hình, có thể qua load balancer.
2. Server gửi certificate chain.
3. Client xác minh certificate được CA tin cậy ký, chưa hết hạn, đúng mục đích và **hostname nằm trong Subject Alternative Name (SAN)**.
4. Hai bên thương lượng protocol/cipher suite phù hợp policy.
5. Sau khi thiết lập TLS, MongoDB tiếp tục bước **xác thực người dùng** theo cơ chế SCRAM/X.509 hoặc cơ chế được triển khai.

~~~mermaid
sequenceDiagram
    participant C as Java MongoDB Driver
    participant S as MongoDB Server
    C->>S: TCP connect (hostname)
    C->>S: TLS ClientHello / SNI
    S-->>C: Certificate chain
    Note over C: Verify CA, validity, SAN hostname
    C->>S: TLS handshake finished
    C->>S: MongoDB authentication (ví dụ SCRAM)
    S-->>C: Auth success / auth failure
    C->>S: find / insert / update theo RBAC
    S-->>C: Result hoặc Unauthorized
~~~

TLS **không tự** bảo vệ các dữ liệu sau khi chúng đã được giải mã trong JVM, JSON trả cho HTTP caller, disk backup không được mã hóa, query/log ứng dụng hay quyền DB bị cấp quá rộng.

### Những anti-pattern phải tránh

- `tls=false` hoặc kết nối plaintext tới MongoDB production khi yêu cầu chính sách phải mã hóa.
- `invalidHostNameAllowed(true)` hoặc cách tương đương tắt kiểm tra hostname.
- Trust manager chấp nhận mọi certificate, truststore tự nhập một server certificate tùy tiện mà không có quy trình rotation.
- Dùng IP trực tiếp khi certificate chỉ có DNS SAN rồi tắt hostname validation để “cho kết nối chạy”.
- Dùng HTTP proxy/sidecar TLS ở một đoạn và mặc định đoạn còn lại tới MongoDB vẫn được mã hóa.
- Đưa private key, password truststore hoặc URI chứa credential vào log lỗi handshake.

**Một chứng chỉ “đã được mã hóa” nhưng không được kiểm tra danh tính server vẫn có thể cho phép man-in-the-middle.** Việc chấp nhận hostname sai thường phá mục tiêu xác thực đầu xa.

## 3. Spring Boot: cấu hình MongoClient và TLS theo cấu hình môi trường

Với Spring Data MongoDB imperative, một project Maven thông thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Spring Boot auto-configuration có thể tạo `MongoClient` và `MongoTemplate` dựa trên các property MongoDB nếu ứng dụng chưa tự thay thế bean. `MongoClient` từ Java driver quản lý connection pool, chọn server, giám sát cluster và authentication; **nên tái sử dụng như singleton**, không tạo một client cho mỗi HTTP request hoặc message.

Đặt cấu hình trong `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Ví dụ **dạng cấu trúc** của biến môi trường, với password đã được percent-encode và DNS SAN khớp certificate:

~~~text
MONGODB_URI=mongodb://order_app:<encoded-secret>@mongo-0.db.example:27017,mongo-1.db.example:27017/orders?authSource=orders&authMechanism=SCRAM-SHA-256&replicaSet=rs0&tls=true
~~~

Đây là **mẫu**, không phải URI chứa credential thật. URI gồm:

- `mongodb://`: scheme kết nối driver; biến thể `mongodb+srv://` dùng DNS SRV/TXT discovery khi hạ tầng hỗ trợ.
- `order_app:...`: MongoDB principal và password, **không phải** identity của HTTP caller.
- `mongo-0.db.example,mongo-1.db.example`: host tương ứng với certificate/SAN và topology.
- `/orders`: database mặc định của client.
- `authSource=orders`: database chứa danh tính `order_app` trong ví dụ.
- `authMechanism=SCRAM-SHA-256`: yêu cầu cơ chế xác thực cụ thể được cấu hình phía server.
- `replicaSet=rs0`: xác minh client kết nối đúng replica set khi ứng dụng dùng topology này.
- `tls=true`: bật TLS ở driver; server cũng phải được cấu hình TLS thích hợp.

**Không ghi mật khẩu dạng nguyên văn trong file repository** và không log toàn bộ biến `MONGODB_URI`. Nếu password có `@`, `:`, `/`, `?`, `#` hoặc `%`, phải encode phù hợp URI userinfo; lỗi encode thường dẫn tới parsing/authentication failure hoặc vô tình trỏ sai hostname.

Nếu dùng `mongodb+srv://`, việc phát hiện host và mặc định TLS có đặc thù riêng; đừng dựa vào suy đoán mà hãy xác minh driver config và chính sách TLS thật trong môi trường triển khai.

### URI so với property rời rạc

Không trộn các property host/port/username/password/URI mà không biết phiên bản Boot quy định độ ưu tiên thế nào. Một URI nên là **nguồn cấu hình chủ đạo**, hoặc chọn một cấu hình `MongoClientSettings` rõ ràng nếu hệ thống có nhiều cluster/tenant. Với Spring Boot auto-config, việc khai báo một `MongoClient` tự tạo có thể khiến auto-configuration back off; khi đó những builder customizer/SSL bundle mà ứng dụng trông đợi có thể không còn tác dụng.

## 4. CA, truststore, SSL bundle và hostname verification

Trong mạng nội bộ, MongoDB thường sử dụng certificate do CA nội bộ cấp. JVM không tự tin CA riêng đó nếu certificate chưa nằm trong truststore thích hợp. Cần đưa **public CA certificate** vào một truststore, không đưa private key của CA.

### Cách 1: truststore của JVM

Khi driver sử dụng JSSE TLS context mặc định, có thể cung cấp truststore cho JVM qua system properties:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/run/secrets/mongo-truststore.p12 \
  -Djavax.net.ssl.trustStorePassword="$MONGO_TRUSTSTORE_PASSWORD" \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

Ví dụ dùng tham số JVM để trình bày nguyên lý; trong môi trường production, **password trên command line/process arguments có thể bị quan sát bởi công cụ quản trị hoặc hệ điều hành**. Ưu tiên cơ chế mount secrets và cấu hình SSL context riêng cho client hoặc SSL bundle để tránh đưa secret vào command line. Truststore hệ thống có thể ảnh hưởng các HTTP/TLS client khác trong cùng JVM; nếu muốn tin **CA khác nhau theo từng downstream**, nên dùng cấu hình per-client.

### Cách 2: Spring Boot SSL bundle và MongoClientSettingsBuilderCustomizer

Với phiên bản Spring Boot **có hỗ trợ SSL bundles** (3.1+), cấu hình JKS/PKCS12 truststore thành một bundle đặt tên:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
  ssl:
    bundle:
      jks:
        mongo-client:
          truststore:
            location: file:/run/secrets/mongo-truststore.p12
            password: ${MONGO_TRUSTSTORE_PASSWORD}
            type: PKCS12
~~~

Để chủ động áp dụng đúng bundle này cho MongoDB driver do Boot tạo, có thể cấu hình customizer:

~~~java
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MongoTlsConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoTlsCustomizer(
            SslBundles sslBundles) {

        return settings -> settings.applyToSslSettings(ssl -> ssl
                .enabled(true)
                .context(sslBundles.getBundle("mongo-client")
                        .createSslContext())
                .invalidHostNameAllowed(false));
    }
}
~~~

Ý nghĩa:

1. `SslBundles` cung cấp SSL context từ truststore do Spring Boot quản lý.
2. `MongoClientSettingsBuilderCustomizer` điều chỉnh cấu hình driver khi Boot dựng client theo luồng auto-configuration.
3. `enabled(true)` buộc kết nối có TLS tại cấu hình này.
4. `invalidHostNameAllowed(false)` giữ hostname verification; **không** “sửa” lỗi certificate bằng cách bật true.
5. Không tạo thêm `MongoClients.create(...)` trong cùng cấu hình nếu muốn customizer này áp dụng lên bean Boot auto-configured.

Một số minor version Spring Boot hỗ trợ property SSL bundle trực tiếp cho MongoDB, ví dụ dưới prefix `spring.data.mongodb.ssl.*`. Khi có hỗ trợ, có thể chọn cách **cấu hình thuần property** thay vì viết bean tùy biến; **tránh cấu hình TLS hai nơi với giá trị mâu thuẫn**. Cần kiểm tra metadata/property documentation của phiên bản ứng dụng, vì chi tiết auto-configuration thay đổi theo release.

### Hostname phải khớp certificate

Nếu certificate chỉ có SAN `mongo-0.db.example`, đừng kết nối bằng `10.10.1.17` hoặc `localhost` rồi tắt verify. Hãy cấp chứng chỉ có SAN cho hostname thật, điều chỉnh DNS/service discovery hoặc dùng endpoint được chứng chỉ hỗ trợ.

Nếu đứng sau proxy/LB, cần kiểm tra certificate mà **driver thấy tại TLS peer**, SNI, có TLS termination hay chỉ TCP passthrough, và hostname nào được dùng khi driver phát hiện primary/secondary. Một kết nối đầu tiên đến proxy thành công chưa chứng minh các host trong replica set discovery đều có certificate hợp lệ.

### Quản lý certificate rotation

Certificate có hạn sử dụng; hệ thống cần:

- Theo dõi ngày hết hạn trước khi ứng dụng kết nối lỗi.
- Có overlap CA cũ/mới trong cửa sổ chuyển đổi nếu chính sách cho phép.
- Đảm bảo từng replica MongoDB trình bày chain hợp lệ.
- Kiểm tra ứng dụng/driver có tự tải lại truststore hay cần **recreate client/restart**. Không mặc định thay file trên disk khiến SSL context đã tạo tự cập nhật.
- Xác minh cả kết nối mới sau rotation, không chỉ connection đang mở từ trước.

## 5. MongoDB authentication: SCRAM-SHA-256, authSource và X.509

TLS xác minh server; **MongoDB authentication** xác minh principal của ứng dụng đối với database/cluster. Một MongoDB deployment có thể hỗ trợ nhiều authentication mechanism, nhưng client phải dùng cơ chế được bật và account được tạo đúng cách.

### SCRAM-SHA-256

Đây là phương án phổ biến cho MongoDB database users tự quản lý. Một số điều kiện:

- User được tạo trong **authentication database**; ví dụ user `order_app` được tạo trong database `orders`.
- Client dùng `authSource=orders`, không phải tùy ý `admin` theo thói quen.
- Server bật authentication và cơ chế SCRAM phù hợp.
- Password đủ mạnh, được lưu trong secret manager và có quy trình rotation.
- Role của account được cấp trên database/collection cần thiết.

**`authSource` không phải là database được quyền đọc/ghi mặc định.** Nó là database xác thực user. Một user xác thực ở `admin` vẫn có thể được cấp role giới hạn trên `orders`, hoặc xác thực ở `orders` với role chỉ trên một số collection. Quyền thực tế do role/privilege quyết định.

Sai `authSource` có thể gây lỗi `Authentication failed` dù username/password đúng trong database khác. Cần kiểm tra bằng một identity của test, không khắc phục bằng cách chuyển ứng dụng sang tài khoản cluster admin.

### X.509 client certificate

MongoDB có thể xác thực client bằng certificate trong mô hình **mutual TLS (mTLS)** nếu server được cấu hình cho MongoDB X.509 authentication. Đây là lựa chọn khác với SCRAM:

- Client xuất trình certificate/private key tương ứng trong TLS handshake.
- Server xác minh certificate và ánh xạ subject danh tính thành MongoDB user trong `$external` theo quy ước server.
- User X.509 vẫn cần **role** được cấp rõ ràng; có certificate không có nghĩa có quyền CRUD.
- TLS client certificate cần policy về EKU, CA, SAN/subject, private key protection và rotation.

Một URI cấu trúc cho X.509 (không chứa password):

~~~text
mongodb://mongo-0.db.example:27017/orders?tls=true&authMechanism=MONGODB-X509&authSource=%24external
~~~

`%24external` là `$external` đã URL-encode. Cần cấu hình **client key material** cho SSL context (keystore/chứng chỉ + private key) và đăng ký MongoDB user tương ứng ở `$external`. **Chỉ đổi URI** từ SCRAM sang X.509 mà không có certificate và user mapping sẽ không xác thực được.

Không dùng certificate/key của server làm credential client; phải có danh tính và phạm vi sử dụng riêng. Khi có sidecar/service mesh mTLS, xác thực tại mesh **không tự tương đương** MongoDB X.509 authentication trừ khi MongoDB thực sự nhận và xác minh client certificate theo cơ chế nó hỗ trợ.

### Những phương án identity khác

MongoDB Atlas và một số môi trường enterprise có thể cung cấp authentication tích hợp cloud identity/OIDC/AWS IAM/Kerberos tùy phiên bản/tier và driver. Không giả định một connection string tùy ý sẽ bật được mọi mechanism trên self-managed MongoDB. Lựa chọn cơ chế cần dựa vào **sản phẩm MongoDB, phiên bản driver, cấu hình Atlas/cluster và quy trình rotation** đang dùng.

## 6. Least privilege trong MongoDB RBAC

**RBAC** xác định danh tính có thể thực hiện những **action** nào trên các resource, điển hình là database/collection. Một role có thể bao gồm nhiều privileges hoặc kế thừa role khác.

Các built-in role hữu dụng nhưng đôi khi rộng hơn yêu cầu tối thiểu:

| Built-in role | Mục đích | Rủi ro nếu cấp cho runtime app |
| --- | --- | --- |
| `read` | Đọc dữ liệu trong database | Có thể đọc nhiều collection hơn chức năng thực tế cần |
| `readWrite` | Đọc/ghi database theo quyền của role | Rộng hơn `find/insert/update` trên vài collection; có thêm thao tác quản lý collection/index tùy bản |
| `dbAdmin` | Công việc quản trị database/index/schema | Không nên cấp cho service nghiệp vụ |
| `userAdmin` | Tạo/sửa user/role theo phạm vi tương ứng | Có thể tăng quyền gián tiếp; chỉ cấp vận hành được kiểm soát |
| `clusterMonitor` | Theo dõi cluster | Không biến thành tài khoản nghiệp vụ vì health check cần thống kê |
| `root` | Quyền quản trị rất rộng | Tuyệt đối không dùng làm account cho HTTP service/worker |

Với một `order-service` chỉ cần tìm, thêm và cập nhật đơn hàng, **custom role theo collection và action** thường rõ ràng hơn `readWrite` toàn database.

### Phân tích quyền theo operation

| Component | Collection | Actions dự kiến | Không cần |
| --- | --- | --- | --- |
| Order API runtime | `orders` | `find`, `insert`, `update` | `dropCollection`, `createIndex`, `remove` nếu không xóa |
| Inbox idempotency | `processed_events` | `find`, `insert` | `drop`, `remove` |
| Outbox producer | `outbox_events` | `insert` | `remove`, `createIndex` |
| Outbox relay | `outbox_events` | `find`, `update` | Toàn quyền trên `orders` |
| Report read-only service | `orders` (hoặc view được kiểm soát) | `find` | `insert`, `update`, `remove` |
| Schema migration | Collection/index mục tiêu | `createCollection`, `createIndex` theo phạm vi | Quyền runtime dài hạn |
| Administrator có trách nhiệm | Phạm vi bảo trì được phê duyệt | Theo quy trình vận hành | Không dùng làm credential nhúng vào app |

**Action** phải dựa trên lệnh code thật. Nếu service gọi `findAndModify`, change stream, aggregation có `$out/$merge` hoặc tự tạo index, hãy đối chiếu privilege tương ứng của MongoDB version. Không mặc định tất cả thao tác nâng cao đều chỉ cần `find` hoặc `update`.

## 7. Tạo role/user MongoDB có phạm vi nhỏ

Ví dụ với self-managed MongoDB hoặc môi trường cho phép dùng `mongosh` tạo custom role, thực hiện **bằng tài khoản quản trị có quyền phù hợp**:

~~~javascript
use orders

db.createRole({
  role: "order_runtime",
  privileges: [
    {
      resource: { db: "orders", collection: "orders" },
      actions: ["find", "insert", "update"]
    },
    {
      resource: { db: "orders", collection: "processed_events" },
      actions: ["find", "insert"]
    },
    {
      resource: { db: "orders", collection: "outbox_events" },
      actions: ["insert"]
    }
  ],
  roles: []
});

db.createUser({
  user: "order_app",
  pwd: passwordPrompt(),
  roles: [{ role: "order_runtime", db: "orders" }]
});
~~~

`passwordPrompt()` nhập password tương tác để tránh đặt secret thẳng trong command history. Nếu ứng dụng đã có collection/index, runtime role không cần tạo chúng.

Một danh tính **khác** dành cho outbox relay:

~~~javascript
use orders

db.createRole({
  role: "outbox_relay",
  privileges: [
    {
      resource: { db: "orders", collection: "outbox_events" },
      actions: ["find", "update"]
    }
  ],
  roles: []
});

db.createUser({
  user: "relay_app",
  pwd: passwordPrompt(),
  roles: [{ role: "outbox_relay", db: "orders" }]
});
~~~

Đây là thiết kế role **minh họa**, không phải script migration có thể chạy nguyên xi ở bất kỳ Atlas tier hay cấu hình enterprise nào. Trên MongoDB Atlas, việc tạo database user, custom role và quyền quản trị có thể phải thông qua Atlas UI/API; cần tuân theo cơ chế của deployment. Tên role, user và resource trong production phải được version hóa, quản lý qua IaC/automation có review và tránh ghi mật khẩu trong diff.

### Không trộn user quản trị với user ứng dụng

Không để Spring Boot app tự chạy `db.createUser`, `db.createRole`, `createIndex` hoặc `dropCollection` trong mỗi lần startup bằng chính runtime identity rồi dùng quyền admin mãi mãi. Tách:

1. **Migration/deployment identity**: quyền DDL cần thiết, tồn tại hoặc được cấp trong thời gian ngắn.
2. **Runtime service identity**: chỉ đọc/ghi đúng collection đã định nghĩa.
3. **Outbox/consumer identity**: quyền theo mục đích xử lý.
4. **Operator/backup identity**: quyền quản trị/đọc backup theo role và quy trình riêng.

Tách identity giúp giảm blast radius nếu một container bị xâm nhập.

## 8. Quyền tối thiểu phải được kiểm chứng bằng “positive và negative tests”

Một ứng dụng chạy được với user root **không chứng minh** bộ quyền runtime đủ và cũng không chứng minh nó không bị cấp quá rộng. Test phân quyền nên có cả:

- **Positive test**: user `order_app` có thể `find`, `insert`, `update` document hợp lệ trong `orders` và ghi vào `processed_events`.
- **Negative test**: cùng user **không** thể `drop`, `createIndex` hoặc đọc collection nhạy cảm không được cấp.
- **Cross-service test**: `relay_app` không đọc được `orders` chỉ vì nó cần `outbox_events`.
- **No-admin fallback**: nếu thao tác thất bại do quyền thiếu, ứng dụng trả lỗi/cảnh báo; không retry bằng root credential.
- **Migration boundary test**: migration identity tạo được index, runtime identity không có quyền DDL sau deploy.

Ví dụ với Java driver trong một integration test chạy trên user bị hạn chế:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mongodb.MongoCommandException;
import com.mongodb.client.MongoClient;
import org.bson.Document;
import org.junit.jupiter.api.Test;

class MongoPrivilegeIntegrationTest {

    private final MongoClient restrictedMongoClient;

    MongoPrivilegeIntegrationTest(MongoClient restrictedMongoClient) {
        this.restrictedMongoClient = restrictedMongoClient;
    }

    @Test
    void runtimeCanReadOrdersButCannotDropCollection() {
        var collection = restrictedMongoClient
                .getDatabase("orders")
                .getCollection("orders");

        collection.find(new Document("_id", "ORDER-42")).first();

        assertThatThrownBy(collection::drop)
                .isInstanceOf(MongoCommandException.class)
                .satisfies(error -> assertThat(
                        ((MongoCommandException) error).getErrorCode())
                        .isEqualTo(13)); // MongoDB Unauthorized
    }
}
~~~

Đây là **mẫu test**: trong project thật phải tạo `restrictedMongoClient` bằng credentials test, tạo sẵn database/collection qua setup identity, sau đó inject vào class test theo JUnit/Spring Test phù hợp. Không dùng user quản trị cho test negative. MongoDB error code `13` chỉ kiểm tra trường hợp cụ thể `Unauthorized`; nếu lỗi TLS/auth đã xảy ra trước, sẽ có exception khác và đó là một nguyên nhân cần điều tra riêng.

Một test chỉ mock `MongoTemplate` ném `AccessDenied` không chứng minh server đã chặn quyền; cần test thật trên MongoDB triển khai RBAC.

## 9. Tách quyền database khỏi quyền truy cập dữ liệu theo tenant

MongoDB RBAC theo collection và database **không tự bảo vệ từng document theo tenantId** trong một collection dùng chung. Giả sử document:

~~~json
{
  "_id": "ORDER-42",
  "tenantId": "tenant-a",
  "customerId": "CUSTOMER-9",
  "state": "PAID"
}
~~~

Nếu user `order_app` có `find` trên `orders`, MongoDB RBAC thông thường cho phép nó tìm các document thuộc **mọi tenant trong collection đó**, không chỉ `tenant-a`. Lớp application phải xác thực caller và ràng buộc query theo tenant đã xác minh.

### Spring Data MongoTemplate với scope bắt buộc

Document DTO:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public record OrderDocument(
        @Id String id,
        String tenantId,
        String customerId,
        String state,
        Instant updatedAt
) {
}
~~~

Một service truy vấn bằng `MongoTemplate`:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class TenantOrderReader {

    private final MongoTemplate mongo;

    public TenantOrderReader(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public OrderDocument getOrder(
            AuthenticatedTenant caller,
            String orderId) {

        Query query = Query.query(
                Criteria.where("_id").is(orderId)
                        .and("tenantId").is(caller.tenantId()));

        OrderDocument result =
                mongo.findOne(query, OrderDocument.class);

        if (result == null) {
            throw new OrderNotFoundException();
        }
        return result;
    }
}
~~~

`AuthenticatedTenant` và `OrderNotFoundException` là các type do ứng dụng định nghĩa. **`caller.tenantId()` phải lấy từ principal/token đã được xác minh hoặc session an toàn**, không lấy từ một field JSON tùy ý do người dùng truyền vào rồi coi là đáng tin.

Với thao tác sửa:

~~~java
Query query = Query.query(
        Criteria.where("_id").is(orderId)
                .and("tenantId").is(caller.tenantId()));

Update update = new Update().set("state", "SHIPPED");

var result = mongo.updateFirst(
        query, update, OrderDocument.class);

if (result.getMatchedCount() != 1) {
    throw new OrderNotFoundException();
}
~~~

**Cả đọc và ghi** phải có điều kiện tenant. Một endpoint GET có filter đúng nhưng endpoint PATCH/DELETE chỉ filter theo `_id` vẫn tạo lỗ hổng cross-tenant.

### Tenant isolation mạnh hơn

Nếu yêu cầu cách ly ở **database/collection level** vì chính sách tuân thủ, cân nhắc collection hoặc database riêng cho từng tenant và role/credential tương ứng, nhưng đổi lại cần quản lý số connection/client, migration, index, backup và quyền truy cập phức tạp hơn. Không thể thay thế quyết định kiến trúc này bằng cách thêm một field `tenantId` rồi tuyên bố MongoDB RBAC tự bảo đảm document-level authorization.

## 10. Chống NoSQL injection và truy vấn vượt hợp đồng

MongoDB query document dùng operator như `$ne`, `$gt`, `$in`, `$regex`, `$where`. Nếu API nhận một JSON filter tùy ý rồi đưa thẳng vào database, caller có thể thay điều kiện theo hướng không mong muốn.

Ví dụ nguy hiểm (minh họa điều **không nên** làm):

~~~java
// KHÔNG NÊN: caller có quyền điều khiển cấu trúc query MongoDB.
Document rawFilter = Document.parse(untrustedJsonFilter);
mongo.getCollection("orders").find(rawFilter);
~~~

Caller có thể gửi:

~~~json
{"tenantId":{"$ne":"tenant-a"}}
~~~

Nếu query này đi thẳng tới MongoDB, kết quả khác rất xa một tìm kiếm tenant theo giá trị string. `$where` và pipeline operator khác còn có rủi ro tài nguyên nếu được mở tự do.

Cách bảo vệ:

1. Chỉ nhận **DTO typed** với các field/filter được hỗ trợ.
2. Validate giới hạn độ dài, tập giá trị enum, ngày và kiểu số.
3. Tạo query bằng `Criteria`/Spring Data Query hoặc DSL riêng đã kiểm soát.
4. **Bổ sung tenant scope bắt buộc** từ trusted principal trong mọi truy vấn.
5. Whitelist sort fields, projection và aggregation stages; không cho client tự quyết định collection/database.
6. Giới hạn query timeout, limit/pagination, regex và số phần tử trong `$in`.
7. Nếu có admin-only query DSL, bảo vệ bằng identity riêng, audit và rate limit.

Khai báo role chỉ có `find` không ngăn một truy vấn `find` đọc hết dữ liệu trong collection. Least privilege tại database phải kết hợp với least privilege **tại API và truy vấn ứng dụng**.

## 11. Bảo vệ dữ liệu nhạy cảm: TLS khác mã hóa dữ liệu lưu trữ

Có ít nhất ba lớp bảo vệ dữ liệu:

| Lớp | Cơ chế | Giới hạn |
| --- | --- | --- |
| In transit | TLS từ Java driver tới MongoDB | Không mã hóa dữ liệu trong bộ nhớ JVM hoặc sau khi response được giải mã |
| At rest | Volume/disk encryption, managed storage encryption, backup encryption | Database operator/app có quyền đọc vẫn có thể thấy plaintext |
| Field/application level | Client-side Field Level Encryption (CSFLE), Queryable Encryption hoặc mã hóa ứng dụng được thiết kế | Tăng độ phức tạp khóa, query, index và rotation; không giải quyết mọi vấn đề RBAC |

TLS và encryption at rest giải quyết **hai ranh giới đe dọa khác nhau**. Nếu business lưu số giấy tờ hoặc token nhạy cảm, cần xác định ai được quyền thấy plaintext, dữ liệu có cần truy vấn theo field được mã hóa không, và khóa nằm ở KMS/HSM nào.

CSFLE/Queryable Encryption của MongoDB có yêu cầu về driver, thư viện mã hóa, schema/encryptedFields, key vault, KMS và một số giới hạn truy vấn theo phiên bản. Không bật bằng cách chỉ thêm `encrypted=true` vào DTO. Cần một kế hoạch quản lý khóa, backup/restore, rotation và test compatibility trước khi áp dụng.

Các nguyên tắc vận hành:

- Không ghi dữ liệu bí mật đầy đủ vào MongoDB command monitoring/log.
- Giới hạn field được trả về bằng projection nếu caller chỉ cần một phần.
- Phân loại dữ liệu cho retention/deletion/backup và quyền đọc backup.
- Ký/mã hóa token trong ứng dụng phù hợp threat model; không dùng user-provided object ID để trao quyền.
- Kiểm tra query plan/projection khi dữ liệu tăng; một endpoint “read-only” vẫn có thể gây DoS bằng aggregation tốn tài nguyên.

## 12. TLS và authentication không giải quyết giao dịch, retry hoặc trùng lặp

Giả sử `payment-consumer` nhận message từ RabbitMQ, cập nhật document `orders`, rồi ghi `processed_events`. Nó có thể commit MongoDB thành công nhưng mất connection tới broker trước khi ACK; message được redeliver. TLS và user role đúng **không ngăn** việc xử lý cùng sự kiện lần nữa.

### Idempotency trong MongoDB

Một cách tiếp cận là đặt khóa unique ổn định cho mỗi consumer/event:

~~~javascript
db.processed_events.createIndex(
  { consumerId: 1, eventId: 1 },
  { unique: true, name: "uk_consumer_event" }
);
~~~

Chỉ migration identity có quyền `createIndex` nên chạy DDL này. Runtime identity chỉ cần `find`, `insert` trên collection.

Event:

~~~java
public record PaymentCaptured(
        String eventId,
        String orderId,
        long amountCents
) {
}
~~~

Trong một transaction MongoDB khi cấu hình topology hỗ trợ:

1. INSERT receipt `(consumerId, eventId)`.
2. Cập nhật `orders` dựa trên state/phiên bản hợp lệ.
3. Ghi `outbox_events` nếu cần phát message tiếp.
4. Commit transaction.
5. Sau commit, listener kết thúc thành công để broker có thể ACK.

~~~mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant C as PaymentConsumer
    participant TX as MongoTransactionManager
    participant DB as MongoDB
    MQ->>C: PaymentCaptured(eventId)
    C->>TX: BEGIN
    TX->>DB: INSERT processed_events unique key
    TX->>DB: UPDATE orders
    TX->>DB: INSERT outbox_events
    TX->>DB: COMMIT
    C--xMQ: ACK bị mất do connection lỗi
    MQ->>C: Redelivery cùng eventId
    C->>TX: BEGIN / kiểm tra key
    TX->>DB: Duplicate key / receipt đã tồn tại
    Note over C,DB: Không lặp side effect nghiệp vụ
    C-->>MQ: ACK sau xử lý duplicate phù hợp
~~~

**Chú ý:** nếu một INSERT duplicate ném lỗi trong transaction, transaction có thể bị abort. Không bắt DuplicateKeyException rồi tiếp tục các thao tác MongoDB trong **cùng transaction đã lỗi**. Có thể để transaction rollback, phân loại duplicate ở tầng ngoài và đọc biên nhận bằng thao tác hợp lệ trong transaction mới, rồi quyết định coi đó là message đã xử lý. Mọi đường đua đồng thời phải được chứng minh bằng unique index thực, không chỉ `find rồi insert` không ràng buộc.

### MongoTransactionManager và điều kiện topology

Spring Data MongoDB có `MongoTransactionManager` cho transaction imperative. Ví dụ bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Spring Boot không phải lúc nào cũng tự tạo bean transaction MongoDB theo nhu cầu ứng dụng; nếu muốn `@Transactional` quản lý Mongo transaction, cần kiểm tra manager đã có và đúng `MongoDatabaseFactory`. **MongoDB multi-document transactions yêu cầu deployment topology phù hợp** như replica set hoặc sharded cluster được hỗ trợ; standalone MongoDB thông thường không đáp ứng cùng điều kiện. Kiểm thử trên một MongoDB standalone local có thể cho cảm giác ứng dụng chạy được nhưng transaction multi-document sẽ lỗi.

Trong project có cả JDBC và MongoDB, **`@Transactional` phải chọn đúng manager**: ví dụ `@Transactional(transactionManager = "mongoTransactionManager")` cho thao tác Mongo nếu có nhiều manager. Một Mongo manager không commit/rollback PostgreSQL hay RabbitMQ trong cùng ACID transaction. Khi cần tích hợp SQL/broker/HTTP, dùng outbox/saga/reconciliation phù hợp.

## 13. Retry, timeout và “unknown commit result”

Lỗi có thể xuất hiện ở nhiều giai đoạn:

| Lỗi | Ý nghĩa | Chính sách hợp lý |
| --- | --- | --- |
| TLS handshake không tin CA | Client từ chối identity server | Sửa chain/truststore, không tự bật insecure mode |
| Hostname/SAN mismatch | Server cert không khớp endpoint | Sửa DNS/certificate/endpoint |
| Authentication failed | User/password/authSource/mechanism sai | Kiểm tra secret và cấu hình, không retry vô hạn bằng credential sai |
| Unauthorized (code 13) | User đã auth nhưng không có privilege | Sửa role/operation contract; không đổi sang root |
| Server selection timeout | Driver không tìm được node phù hợp | Kiểm tra DNS, replicaSet, TLS, topology, network |
| Socket/read timeout | Request hoặc response không hoàn tất đúng hạn | Có thể chưa rõ server đã ghi hay chưa |
| Duplicate key (code 11000) | Unique constraint bị vi phạm | Phân biệt idempotent duplicate và data conflict |
| TransientTransactionError label | Transaction bị lỗi có thể thử lại toàn transaction theo policy | Retry có giới hạn, cùng business key |
| UnknownTransactionCommitResult label | Client không biết commit có thành công hay chưa | Retry commit theo hướng dẫn driver hoặc tra cứu receipt; không tái thực thi business mù |
| Rate/overload/connection pool pressure | Tài nguyên bị quá tải | Backoff, giới hạn concurrency, quan sát pool |

Các exception cụ thể trong Java driver và cách Spring Data chuyển thành `DataAccessException` tùy code path và phiên bản. Không bắt mọi exception rồi gán là lỗi retry được. Cần phân loại theo **MongoDB error labels, code, cause và transaction state**, đồng thời giới hạn attempts và thời gian tổng.

### Timeout có nhiều tầng

| Loại | Ví dụ driver configuration | Câu hỏi |
| --- | --- | --- |
| Connect timeout | `SocketSettings.connectTimeout` | Mở socket tối đa bao lâu? |
| Server selection timeout | `ClusterSettings.serverSelectionTimeout` | Chờ driver tìm node hợp lệ tối đa bao lâu? |
| Read/socket timeout | Driver socket settings | Chờ mạng đọc kết quả tối đa bao lâu? |
| Operation deadline | `timeoutMS`/client-side operation timeout theo driver version | Toàn operation được phép chờ bao lâu? |
| MongoDB `maxTimeMS` | Option per query/command | Server được chạy operation tối đa bao lâu? |
| Transaction lifetime limit | Chính sách server | Transaction có vượt giới hạn phía server không? |
| Business deadline | HTTP/broker orchestration | Toàn workflow qua nhiều phụ thuộc tối đa bao lâu? |

Không coi `serverSelectionTimeoutMS` là thời hạn mọi query. Chẳng hạn driver có thể tìm được primary sau 100 ms nhưng câu aggregation vẫn chạy lâu nếu không có giới hạn query. Ngược lại, client đã timeout không chứng minh server chưa commit.

### Định cấu hình timeout qua MongoClientSettings

Nếu muốn đưa policy dưới code và vẫn để Boot quản lý `MongoClient`:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MongoTimeoutConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoTimeouts() {
        return builder -> {
            builder.applyToClusterSettings(cluster ->
                    cluster.serverSelectionTimeout(3, TimeUnit.SECONDS));
            builder.applyToSocketSettings(socket ->
                    socket.connectTimeout(2, TimeUnit.SECONDS));
        };
    }
}
~~~

Các mốc là ví dụ, không phải production default. Trong cùng ứng dụng có thể có nhiều customizer (TLS/timeout); hãy kiểm tra thứ tự và xung đột với URI settings, SSL bundles và custom MongoClient. API timeout mới hơn của Java driver cũng có khác biệt; chỉ copy đúng API của phiên bản quản lý trong BOM.

## 14. Tách connection pool, identity và lifecycle client

`MongoClient` của Java driver được thiết kế để tái sử dụng giữa nhiều thread và quản lý connection pool bên trong. Thông thường **một MongoClient cho một cluster/credential/policy** là lựa chọn hợp lý.

Tránh:

~~~java
// KHÔNG NÊN: tạo mới một MongoClient cho mỗi HTTP request.
public OrderDocument getOrder(String id) {
    try (var client = MongoClients.create(uri)) {
        return ...; // Tốn TLS handshake, auth, pool và giám sát topology.
    }
}
~~~

Nên inject `MongoTemplate`/repository từ Spring Boot bean được quản lý. Spring đóng `MongoClient` khi application shutdown theo ownership đã cấu hình.

Với nhiều tenant hoặc nhiều cluster/credential:

- Không tạo một client mới cho **mỗi tenant request** nếu chỉ khác `tenantId` trong cùng collection.
- Nếu mỗi tenant bắt buộc có MongoDB identity riêng, hãy giới hạn số MongoClient được cache, quản lý eviction, rotation và shutdown.
- Mỗi client có connection pool/monitoring thread riêng; hàng nghìn client có thể hết tài nguyên dù số query nhỏ.
- Dùng `@Qualifier` hoặc explicit configuration khi nhiều `MongoTemplate`/`MongoClient`, không để bean mặc định dùng nhầm credential admin.
- Nếu cần rotate SCRAM password mà client hiện tại không thể tự refresh credential, tạo client mới theo kế hoạch hoặc restart dần các instance, đồng thời cho phép cửa sổ chuyển đổi account/secret nếu policy hỗ trợ.

### Không lưu credential theo request trong một bean singleton

Một đối tượng singleton mang quyền kết nối chung sẽ chạy bằng DB principal đã cấu hình. Nếu app nhận một trường `username` từ HTTP request rồi thay toàn bộ URI để “impersonate” người dùng, vừa tạo nguy cơ rò mật khẩu vừa gây connection explosion. Quyền business caller nên được kiểm tra ở app; nếu thật sự cần end-user delegated identity tới MongoDB, đó là kiến trúc bảo mật riêng phải được hỗ trợ rõ và kiểm thử toàn bộ vòng đời.

## 15. Network perimeter, credentials và nguồn secret

TLS và RBAC cần được bổ sung bằng network isolation:

- MongoDB nên ở private network/VPC; hạn chế source security group/firewall tới service thực sự cần truy cập.
- Không public MongoDB port ra Internet chỉ vì có password.
- Bật TLS và xác thực trên mọi endpoint client/mongos và các kênh cluster liên quan theo mô hình triển khai.
- Bảo vệ Kubernetes Secrets, service account, mount path và quyền đọc secret; base64 encoding **không phải encryption**.
- Không đưa URI chứa password vào image layer, lệnh chạy được ghi vào audit log hoặc issue tracker.
- Dùng secret manager/KMS và rotation, cân nhắc đổi credential từng service thay vì một mật khẩu dùng chung.
- Chỉ cho migration/admin chạy từ máy/pipeline được phép, có approvals và logs.

Trong Kubernetes, việc tạo `Secret` không tự bảo đảm mọi container khác không đọc được: quyền RBAC Kubernetes, network namespace, mount và workload identity đều quan trọng. Dùng service account riêng cho từng deployment thay vì cấp cùng identity namespace-wide.

### Certificate và password rotation là hai quy trình khác nhau

| Rotation | Điều cần đổi | Có thể xảy ra trong runtime |
| --- | --- | --- |
| TLS server cert | Certificate chain trên mongod/mongos, SAN, CA nếu cần | Kết nối cũ vẫn sống; kết nối mới có thể lỗi nếu truststore chưa cập nhật |
| Truststore CA | Client trust material/SSLContext | SSL context đã load có thể cần client recreate hoặc restart |
| SCRAM password | Secret trong MongoDB và secret phía service | Client đang dùng credential cũ có thể auth lỗi khi mở connection mới |
| X.509 client cert | Certificate/private key và MongoDB user mapping nếu subject đổi | Các connection mới có thể bị từ chối nếu key/cert/user không đồng bộ |
| Encryption key | KMS/key vault/schema/key version | Cần đánh giá khả năng đọc dữ liệu cũ và migration trước khi đổi |

Bất kỳ quy trình rotation nào cũng nên có canary, kiểm tra negative/positive authentication, metrics lỗi mới mở connection, và khả năng rollback **không bằng cách tắt TLS hoặc dùng root**.

## 16. Health check và least privilege: tránh cấp quyền rộng chỉ để probe xanh

Một ứng dụng có thể liveness UP nhưng MongoDB không sẵn sàng; điều này không nhất thiết là lý do restart. Health check có thể thử kết nối/command nhẹ, nhưng không nên yêu cầu quyền `clusterAdmin` hoặc `dbAdmin` cho runtime app chỉ vì một indicator cụ thể cần thông tin mở rộng.

Với Spring Boot Actuator:

- `/actuator/health` có thể tích hợp MongoDB contributor khi classpath/bean phù hợp.
- `/actuator/health/readiness` thường gắn với trạng thái ứng dụng; dependency MongoDB chỉ nên được thêm theo chính sách nhận traffic, không tự động.
- Một consumer chỉ xử lý event có thể theo dõi thêm lag, outbox age và số thao tác MongoDB thành công thay vì chỉ ping.
- Một indicator tự viết nên dùng query/command **nhẹ, không side effect**, đúng quyền đã cấp, timeout nhỏ và không log credentials.

**Không cố sửa lỗi health indicator bằng cách cấp readWrite toàn database** nếu nghiệp vụ chỉ cần find một collection. Hãy chỉnh phép kiểm tra để không đòi hỏi quyền vượt business contract, hoặc triển khai monitoring identity riêng cho giám sát cluster.

## 17. Quan sát lỗi TLS, quyền và dữ liệu không lộ bí mật

Các tín hiệu production hữu ích:

| Signal | Cách sử dụng |
| --- | --- |
| TLS handshake/authentication failures | Phân biệt CA/SAN/rotation với password/mechanism |
| MongoDB Unauthorized code 13 | Phát hiện role thiếu hoặc hành động trái phép |
| Pool checked-out/available/wait time | Quan sát cạn connection, leak và thời gian chờ |
| Server selection timeout | DNS/topology/replica set/TLS/network có vấn đề |
| Query p95/p99 và maxTimeMS errors | Phân biệt truy vấn chậm với mất kết nối |
| Write errors và duplicate key 11000 | Kiểm tra data conflict, idempotency hits |
| Transaction abort/retry/commit uncertainty | Đánh giá hiệu ứng retry và độ nhất quán |
| Change stream resume failures (nếu dùng) | Đánh giá khả năng phục hồi consumer stream |
| Outbox backlog/age | Broker/downstream có nhận event đúng hạn không |
| Credential/certificate expiry | Cảnh báo rotation trước khi outages xảy ra |
| Audit events | Theo dõi thay đổi role, user, quyền và truy cập bất thường |

Không log full connection string, `Authorization` headers, private keys, MongoDB auth payload hoặc dữ liệu nhạy cảm của document. Một `query filter` chứa email, token, số giấy tờ cũng là dữ liệu nhạy cảm; command monitoring nên redaction hoặc không xuất bind values.

Nếu dùng Micrometer/Actuator và Java driver command listener, **không biến collection name, raw query hoặc document ID thành metric tag không giới hạn**. Chỉ dùng các nhãn đã kiểm soát như operation, collection category, exception category và service name.

### Audit khác application logs

Audit của MongoDB nhằm ghi nhận hoạt động bảo mật theo tính năng/tier đã hỗ trợ; application logs ghi ngữ cảnh nghiệp vụ. Không giả định mọi môi trường MongoDB community/Atlas đều có cùng khả năng audit và retention. Cần xác định nguồn, retention, identity của người sửa role và cách truy xuất khi điều tra sự cố.

## 18. Kiểm thử tích hợp TLS, authentication, authorization và idempotency

Unit test của `MongoTemplate` có thể xác minh cách code tạo `Criteria`, nhưng **không chứng minh MongoDB thật đang kiểm tra CA, role hoặc transaction**. Cần một tầng integration test kết nối MongoDB server với TLS/RBAC bật thật.

### Ma trận kiểm thử

| Trường hợp | Cách tạo điều kiện | Kỳ vọng |
| --- | --- | --- |
| TLS thành công | CA đúng, certificate còn hạn, SAN đúng | Client kết nối và truy vấn được |
| CA sai/không tin | Mount truststore không chứa CA ký server cert | TLS handshake thất bại, không fallback plaintext |
| Hostname mismatch | Kết nối tới hostname không thuộc SAN | TLS verification lỗi |
| Cert hết hạn | Dùng server cert quá hạn trong test | Client từ chối |
| TLS bị tắt phía client | Cố dùng `tls=false` tới TLS-only endpoint | Không kết nối thành công |
| SCRAM đúng | User/password/authSource đúng | Kết nối được với quyền giới hạn |
| SCRAM sai | Sai password hoặc authSource | Authentication failure |
| X.509 client không có cert | Kết nối X.509 tới server yêu cầu client cert | Handshake/authentication thất bại |
| X.509 subject không đăng ký | Cert hợp lệ nhưng MongoDB không có đúng principal | Authentication thất bại |
| Runtime CRUD được phép | Insert/find/update `orders` | Thành công |
| Runtime DDL bị từ chối | Thử drop/createIndex qua runtime identity | Unauthorized, code 13 |
| Read-only user viết | Attempt insert/update | Unauthorized |
| Relay user đọc orders | Query bằng `relay_app` | Unauthorized |
| Cross-tenant query | Caller A cố truy cập order của B | API không trả document B |
| Query injection | Filter JSON chứa `$ne` hoặc `$where` | Bị validation từ chối/không được truyền thẳng |
| Duplicate message | Hai event cùng eventId đồng thời | Một hiệu ứng nghiệp vụ, unique receipt |
| DB commit rồi broker ACK mất | Cắt connection trước ACK | Redelivery an toàn |
| Transaction rollback | Lỗi bước outbox sau update order | Cả các thay đổi transaction rollback |
| Commit unknown outcome | Mô phỏng ngắt response commit | Dò receipt, không tạo side effect trùng |
| Credentials rotation | Đổi secret và reconnect | Hành vi refresh/restart khớp runbook |
| Certificate rotation | Cập nhật CA/cert trong cửa sổ canary | Kết nối mới xác thực chính xác |
| Health check | Chỉ quyền runtime, indicator nhẹ | Không đòi hỏi dbAdmin/root |

### Testcontainers không mặc định đồng nghĩa với TLS test

MongoDB Testcontainers hoặc MongoDB chạy trong Docker cho phép kiểm thử schema, repository, index và một số transaction nếu cấu hình replica set. Nhưng **container mặc định có thể không bật TLS/auth và custom roles** như production; một integration test pass trong môi trường đó chưa chứng minh cấu hình bảo mật production.

Đối với bài toán TLS/RBAC:

1. Tạo MongoDB instance test chuyên biệt có TLS, CA/SAN và authorization đúng.
2. Seed schema/index/user/role bằng identity quản trị **trong setup test**.
3. Tạo Spring Boot application client với **runtime user**.
4. Chạy positive CRUD và negative privilege tests.
5. Chạy thêm profile/instance thử CA sai, hostname sai, password sai, authSource sai.
6. Dọn fixtures bằng setup/admin identity sau khi test, không để runtime app có quyền drop database.
7. Với transaction, dùng topology replica set/sharded hỗ trợ, không chỉ standalone.
8. Kiểm tra driver/server/JDK versions gần production, đặc biệt khi thay TLS protocol hoặc MongoDB major.

### Spring Data repository test với tenant boundary

Ví dụ nguyên tắc test:

~~~java
@Test
void cannotReadAnotherTenantsOrder() {
    // Fixtures đã có: ORDER-42 thuộc tenant-b.
    AuthenticatedTenant tenantA =
            new AuthenticatedTenant("tenant-a");

    assertThatThrownBy(() ->
            tenantOrderReader.getOrder(tenantA, "ORDER-42"))
            .isInstanceOf(OrderNotFoundException.class);
}
~~~

Đây là **phác thảo test** với type `AuthenticatedTenant` và `OrderNotFoundException` do ứng dụng định nghĩa, fixtures thật trên MongoDB. Bổ sung test cho UPDATE/DELETE/aggregation và các endpoint sử dụng query builder khác, không chỉ GET.

## 19. Runbook xử lý sự cố không làm suy yếu bảo mật

### Lỗi TLS handshake

1. Xác định đúng hostname và certificate SAN.
2. Kiểm tra certificate chain, CA trust, thời hạn, EKU và TLS policy.
3. Nếu qua load balancer, xác định TLS termination/passthrough và mọi node được driver discovery.
4. Kiểm tra secret mount/SSL bundle đã load đúng, có cần restart/recreate MongoClient sau rotation không.
5. Không dùng insecure trust manager hoặc tắt hostname verification chỉ để khôi phục traffic.

### Authentication failed

1. Kiểm tra user được tạo tại database nào và `authSource` trong URI.
2. Kiểm tra cơ chế SCRAM/X.509 và quyền truy cập secret.
3. Kiểm tra password đã được URI-encode đúng, thay đổi secrets có đồng bộ giữa app và server không.
4. Với X.509, kiểm tra client certificate, subject DN, `$external` principal và rotation.
5. Không đăng nhập bằng root rồi giữ root credential trong app để xử lý tạm.

### Unauthorized sau khi đăng nhập

1. Đọc MongoDB error code/action/collection đang bị từ chối theo log đã làm sạch.
2. Đối chiếu với **business operation** thật: query thường, update, createIndex, change stream hay aggregation đặc biệt.
3. Nếu code dùng DDL lúc startup, chuyển DDL sang migration pipeline.
4. Nếu đúng là quyền nghiệp vụ cần thêm, mở change request sửa custom role theo collection/action cụ thể, không tăng quyền toàn database.
5. Thêm negative test để ngăn quyền bị mở rộng quá mức ở lần deploy tiếp theo.

### Timeout/retry/duplicate sau khi lỗi mạng

1. Phân biệt connect/server-selection/query timeout, TLS, auth và thiếu quyền.
2. Xác định request ghi có **kết quả commit không rõ** hay đã rollback rõ ràng.
3. Kiểm tra receipt/idempotency key trước khi chạy lại nghiệp vụ.
4. Với broker, xác định thời điểm MongoDB commit so với ACK và outbox state.
5. Giới hạn retry/backoff, tránh connection storm khi database phục hồi.
6. Đo backlog/latency sau phục hồi và xác minh không có document trùng hoặc trạng thái mất đồng bộ.

## 20. Những hiểu nhầm thường gặp

**“MongoDB đã bật TLS nên account readWrite là an toàn?”**

Không. TLS bảo vệ traffic; `readWrite` có thể rộng hơn nhiều action/collection mà service thực sự cần. Cần quyền tối thiểu, phân biệt identity runtime và migration.

**“Chứng chỉ server hợp lệ nhưng hostname khác cũng nên cho kết nối?”**

Không. Việc kiểm tra SAN/hostname là một phần của xác thực server. Sửa endpoint/certificate thay vì bật `invalidHostNameAllowed(true)`.

**“`authSource=admin` luôn là cấu hình đúng?”**

Không. Nó phải trùng database chứa MongoDB user. Có user tạo trong `orders` thì dùng `authSource=orders` trừ khi cấu hình khác được chủ ý thiết kế.

**“RBAC chỉ cho find thì không thể đọc dữ liệu của tenant khác?”**

Sai nếu nhiều tenant chia sẻ một collection. `find` trên collection vẫn có thể tìm dữ liệu của các tenant khác; phải enforce tenant scope ở tầng application hoặc kiến trúc tách tài nguyên.

**“Spring @Transactional bao gồm MongoDB, JDBC và RabbitMQ trong một lần commit?”**

Không. `MongoTransactionManager` quản lý MongoDB resources phù hợp. JDBC/broker có transaction khác. Cần outbox, state machine, retry và idempotency để đạt nhất quán xuyên hệ thống.

**“Đổi truststore file là MongoClient sẽ tin CA mới ngay?”**

Không được mặc định như vậy. SSLContext/certificate material có thể đã được load và cache. Kiểm tra phiên bản driver/Boot và chuẩn bị recreate client hoặc rolling restart.

**“Health check muốn chạy lệnh admin nên chỉ cần thêm dbAdmin cho app?”**

Không. Chọn phép kiểm tra nhẹ không cần quyền cao hoặc dùng monitoring identity riêng. Runtime role không nên bị mở rộng chỉ để probe xanh.

**“Thêm field tenantId vào document là đã có row-level security?”**

Không. Đây là một thuộc tính dữ liệu; nếu query bỏ lọc hoặc caller giả mạo tenantId, dữ liệu vẫn có thể bị lộ. Phải bảo vệ scope ở mọi đường truy cập.

### Checklist production

1. Bật TLS, kiểm tra CA chain và SAN hostname; **không cho phép insecure hostname/trust-all**.
2. Cấp certificate/truststore và secret bằng cơ chế an toàn, không commit URI chứa password hoặc private key.
3. Chọn authentication mechanism theo deployment (SCRAM, X.509 hoặc managed identity được hỗ trợ), xác định đúng `authSource`.
4. Tạo identity riêng cho order API, worker, outbox relay, read-only, migration và operator; **không dùng root cho runtime**.
5. Mô tả quyền theo **collection + action**, dùng custom role khi built-in `readWrite` quá rộng.
6. Chạy positive và negative authorization tests trên MongoDB có RBAC bật.
7. Enforce tenantId từ authenticated principal trong cả find/update/delete/aggregation; chống NoSQL injection.
8. Tách DDL/index migrations khỏi runtime; kiểm tra auto-index-creation và quyền required khi nâng cấp schema.
9. Dùng MongoClient singleton với pool/timeouts phù hợp, đóng/recreate client đúng khi rotation.
10. Giữ transaction trong MongoDB topology hỗ trợ, có unique idempotency receipt; không nhầm transaction Mongo với broker/HTTP.
11. Phân loại TLS/auth/Unauthorized/query timeout/unknown commit result, tránh retry sai loại lỗi.
12. Bảo vệ dữ liệu at rest, field-level secrets, backup, logs và monitoring riêng; TLS không đủ cho toàn lifecycle.
13. Cấu hình network isolation, RBAC Kubernetes/secret manager, least-privilege access tới cluster.
14. Kiểm thử CA sai, hostname sai, credential rotation, role thiếu, cross-tenant, duplicate delivery và transaction rollback.
15. Thiết lập dashboard/alert cho auth failures, permission denied, certificate expiry, connection pool và outbox lag; có runbook không phá bảo mật.

### Tài liệu kỹ thuật để đối chiếu theo phiên bản

- [MongoDB – Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/): TLS, CA, certificate verification và cấu hình server.
- [MongoDB – Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): role, privileges và authorization.
- [MongoDB – Create a User-Defined Role](https://www.mongodb.com/docs/manual/tutorial/define-roles/): custom privileges theo database/collection.
- [MongoDB – SCRAM Authentication](https://www.mongodb.com/docs/manual/core/security-scram/): SCRAM mechanisms và xác thực.
- [MongoDB – X.509 Authentication](https://www.mongodb.com/docs/manual/core/security-x.509/): client certificate, `$external` và account mapping.
- [MongoDB Java Driver – TLS/SSL](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/tls/): Java driver SSL/TLS settings.
- [Spring Boot – Working with SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles.
- [Spring Boot – Data MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.mongodb): MongoDB auto-configuration.
- [Spring Data MongoDB – Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): transaction manager và session.
- [MongoDB – Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): mã hóa trường phía client và ràng buộc vận hành.

**Ghi nhớ:** TLS xác minh và bảo vệ đường truyền; authentication xác nhận **service identity**; authorization giới hạn **action và resource**; còn phân tách dữ liệu theo tenant, chống query injection và idempotency là trách nhiệm bổ sung của application. Một hệ thống Spring Boot–MongoDB an toàn cần thiết kế tất cả lớp này cùng nhau, sau đó chứng minh bằng các test **kết nối thành công khi đúng quyền và thất bại khi thiếu quyền**.

