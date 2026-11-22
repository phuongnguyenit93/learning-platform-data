# Quản lý URI, bí mật, TLS và quyền tối thiểu của tài khoản

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_DATA_MONGODB**, chúng ta sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua **MongoTemplate** hoặc **repository**. Việc thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu đều phụ thuộc vào kết nối database được cấu hình đúng. Chương **Bảo mật và vận hành** tập trung vào cách quản lý kết nối đó một cách an toàn.

Giả sử dịch vụ quản lý đơn hàng kết nối tới database **shop**. Dịch vụ cần đọc và cập nhật collection **orders**, chỉ đọc collection **customers**, không cần đọc **payroll** hoặc quản trị tài khoản MongoDB. Dữ liệu giữa Spring Boot và MongoDB phải được mã hóa; password không được ghi vào Git hoặc log; tài khoản ứng dụng phải có đúng các quyền phục vụ nghiệp vụ.

Một kết nối hoạt động chưa đủ chứng minh cấu hình an toàn. Cần trả lời đồng thời bốn câu hỏi:

1. **URI:** ứng dụng đang trỏ tới cluster, database, authSource và môi trường nào?
2. **Bí mật:** credential được cấp, sử dụng, xoay vòng và thu hồi bằng quy trình nào?
3. **TLS:** kênh truyền có mã hóa và xác minh chứng chỉ, hostname máy chủ không?
4. **Quyền tối thiểu:** tài khoản chỉ có các action cần thiết trên đúng database/collection không?

Sau bài học, bạn có thể phân tích URI, cấu hình Spring Boot nhận secret từ bên ngoài source, thiết lập TLS, tạo role MongoDB giới hạn, kiểm tra permission và xây dựng quy trình xoay vòng secret có thể kiểm chứng.

## 2. Các lớp bảo vệ của một kết nối MongoDB

~~~mermaid
flowchart LR
  A[HTTP client] --> B[Spring Boot service]
  C[Secret manager] -->|Credential| B
  B -->|MongoDB Driver qua TLS| D[(MongoDB server)]
  D --> E[Authentication]
  E --> F[MongoDB RBAC]
  F --> G[(Collections được phép)]
~~~

| Cơ chế | Bảo vệ điều gì | Không thay thế được |
| --- | --- | --- |
| Connection URI | Chọn đúng endpoint, database, cơ chế xác thực và tùy chọn | Không tự giữ bí mật password |
| Secret manager | Quản lý quyền truy cập, cấp và thu hồi credential | Không mã hóa đường truyền đến MongoDB |
| TLS | Mã hóa, bảo vệ tính toàn vẹn và xác minh server khi cấu hình đúng | Không giới hạn quyền đọc/ghi của account |
| MongoDB authentication | Xác định danh tính kết nối | Không có nghĩa được phép truy cập mọi collection |
| MongoDB RBAC | Giới hạn action và resource ở tầng database/collection | Không thay quyền của người dùng cuối theo tenant |
| Quan sát và ứng phó | Phát hiện lỗi, rò rỉ secret, chứng chỉ hết hạn | Không thay cho cấu hình phòng ngừa |

Ví dụ role cho phép account ứng dụng tìm mọi document của collection orders. Role đó **không** tự ngăn người dùng tenant A xem đơn hàng thuộc tenant B. Ứng dụng phải dùng authentication của HTTP client và điều kiện tenant/owner trong truy vấn.

## 3. Cấu trúc MongoDB Connection URI

### 3.1. URI mongodb://

Mẫu tổng quát:

~~~text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]
           /[database][?option1=value1&option2=value2]
~~~

Ví dụ với các giá trị **placeholder**, không phải thông tin đăng nhập thật:

~~~text
mongodb://{USER}:{ENCODED_PASSWORD}@db1.example.internal:27017,db2.example.internal:27017/shop?authSource=shop&replicaSet=rs0&tls=true
~~~

| Thành phần | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| mongodb:// | Danh sách host hoặc seed replica set | Có thể bật TLS qua connection options |
| username/password | Credential dùng để xác thực | Password trong URI có thể cần percent-encoding |
| host:port | Endpoint MongoDB | Driver có thể khám phá thêm member của topology |
| /shop | Database mặc định của thao tác sử dụng database từ URI | Không tự quyết định user được tạo ở database nào |
| authSource=shop | Database chứa danh tính user MongoDB | Có thể khác database dữ liệu |
| replicaSet=rs0 | Tên replica set được kỳ vọng | Cần khớp hạ tầng thực tế |
| tls=true | Bật TLS | Vẫn phải xác minh CA và hostname |

**Database trong đường dẫn và authSource khác nhau.** Nếu user orders_api được tạo ở shop, có thể chọn /shop?authSource=shop. Nếu user được tạo ở admin nhưng có role với quyền trên shop thì có thể chọn /shop?authSource=admin. Việc account được phép truy cập collection nào do roles quyết định.

Nếu authSource không được khai báo, driver dùng quy tắc mặc định theo URI và cơ chế xác thực. Trong hệ thống nhiều môi trường, nên ghi rõ authSource để tránh kết nối thất bại khi thay đổi account hoặc database.

### 3.2. URI mongodb+srv://

Ví dụ:

~~~text
mongodb+srv://{USER}:{ENCODED_PASSWORD}@cluster.example.net/shop?authSource=admin
~~~

Với URI SRV, driver tra bản ghi DNS **SRV** để tìm máy chủ và có thể đọc một số option từ bản ghi **TXT**. Theo quy tắc MongoDB URI, **mongodb+srv bật TLS mặc định** nếu không có tùy chọn tắt tường minh.

Không thay prefix mongodb:// thành mongodb+srv:// nếu cluster không có DNS SRV đúng. Với dịch vụ quản lý, phải dùng hostname và cấu hình được cấp cho cluster, kể cả yêu cầu mạng và certificate.

### 3.3. Percent-encoding credential

Password có thể chứa @, :, /, ?, #, [, ], % là những ký tự đặc biệt của URI. Cần percent-encode đúng phần credential khi đưa vào URI.

~~~text
Password minh họa:  a@b/c?d
Trong URI:          a%40b%2Fc%3Fd
~~~

Nếu secret manager lưu URI hoàn chỉnh đã encode, ứng dụng nhận nguyên chuỗi; tránh encode hai lần. Nếu secret được lưu dưới dạng username/password riêng, dùng API dựng connection string/credential đúng chuẩn thay vì tự ghép chuỗi từ input không đáng tin.

**Percent-encoding không phải mã hóa bảo mật**: người có URI có thể giải mã password. Toàn bộ URI chứa credential phải được bảo vệ như một secret.

### 3.4. Các tùy chọn thường gặp

| Tùy chọn | Tác dụng | Cần lưu ý |
| --- | --- | --- |
| authSource | Chọn database xác thực | Phải khớp nơi tạo user |
| tls | Bật/tắt mã hóa đường truyền | Production cần TLS và certificate validation |
| replicaSet | Chỉ định replica set | Chỉ sử dụng khi đúng topology |
| retryWrites | Retry thao tác ghi nếu driver và server hỗ trợ | Không thay xử lý lỗi/idempotency ở tầng nghiệp vụ |
| readPreference | Chọn nơi đọc | Có thể ảnh hưởng độ mới dữ liệu |
| w | Write concern | Ảnh hưởng mức xác nhận ghi, không phải quyền hoặc mã hóa |
| serverSelectionTimeoutMS | Giới hạn thời gian chọn server | Điều chỉnh theo hạ tầng và SLO |
| appName | Gắn tên ứng dụng vào chẩn đoán | Không đưa secret vào tên |

Không thêm các tùy chọn chưa hiểu chỉ để làm biến mất lỗi. Hãy đối chiếu driver, phiên bản MongoDB và chính sách deployment.

## 4. Cấp bí mật cho Spring Data MongoDB

### 4.1. Cấu hình Spring Boot

Với ứng dụng sử dụng **Spring Boot 3.x** và auto-configuration MongoDB thông thường:

~~~yaml
# application.yml: chỉ giữ tên biến cấu hình
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Biến MONGODB_URI được cấp từ môi trường chạy, hệ thống triển khai hoặc secret manager. Không đặt URI chứa password thật trong source code. Tên property có thể thay đổi giữa các dòng Spring Boot (ví dụ cấu trúc thuộc tính MongoDB trên Spring Boot 4), nên xác nhận metadata/tài liệu **đúng phiên bản** dự án đang dùng. Nếu tự tạo MongoClient hoặc quản lý nhiều client, cần kiểm tra cấu hình auto-configuration thực sự được sử dụng.

MongoTemplate, MongoRepository hoặc ReactiveMongoTemplate dùng MongoClient đã được cấu hình; tầng nghiệp vụ không phải truy cập password:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final MongoTemplate mongoTemplate;

    public OrderReadService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public long countPaidOrders(String authenticatedTenantId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(authenticatedTenantId)
                .and("status").is("PAID")
        );
        return mongoTemplate.count(query, "orders");
    }
}
~~~

Giá trị authenticatedTenantId trong hệ thống thật phải đến từ security context/claims đã xác minh, không tin trực tiếp request parameter. Đoạn mã minh họa truy cập MongoDB, không triển khai đầy đủ Spring Security.

### 4.2. Không để bí mật xuất hiện trong các nguồn phổ biến

Các vị trí cần đặc biệt kiểm tra:

- application.yml, application.properties, Dockerfile, Helm values hoặc README đã commit.
- Git history, CI job logs, test reports, build artifacts, ticket và pull request.
- Command-line argument và lịch sử shell có chứa password.
- Startup logs, exception dump, debug logs của driver, hệ thống thu thập lỗi.
- Dashboard monitoring, endpoint quản trị Actuator env/configprops hoặc bản sao cấu hình chạy.

Ví dụ **không an toàn**:

~~~java
// Không dùng: làm lộ URI chứa username/password.
logger.info("MongoDB URI: {}", System.getenv("MONGODB_URI"));
~~~

Thay bằng thông tin không nhạy cảm:

~~~java
logger.info("MongoDB client initialized for service {}", "orders-api");
~~~

Nếu cần chẩn đoán host/database, nên log alias môi trường đã phê duyệt. Không mặc định một regex tự chế che URI là đủ an toàn; password có thể xuất hiện ở nhiều định dạng và tùy chọn. Hạn chế quyền xem Actuator và kiểm thử masking thực tế.

### 4.3. Nguồn secret theo môi trường

| Môi trường | Nguồn quản lý | Yêu cầu |
| --- | --- | --- |
| Development | Secret local không commit hoặc trình quản lý credential cho developer | Không tái sử dụng password production |
| CI/Test | User/database test riêng, có vòng đời ngắn nếu có thể | Không cấp credential production cho PR không tin cậy |
| Staging | Secret manager cho staging | Tách quyền và dữ liệu khỏi production |
| Production | Secret manager hoặc identity/workload được quản lý | Phân quyền chặt, audit, rotate và thu hồi |

Trong Kubernetes, dữ liệu Secret thường được biểu diễn bằng base64; **base64 không phải mã hóa an toàn**. Cần kết hợp Kubernetes RBAC, bảo vệ Secret khi lưu trữ, giới hạn Pod/namespace được đọc và chính sách triển khai. Secret đưa qua environment variable có thể lộ qua debug/process dump; secret được mount cần filesystem permission và kế hoạch nạp lại thích hợp.

### 4.4. Vòng đời credential

Quy trình chuẩn nên bao gồm:

1. **Cấp phát:** chỉ service identity/nhân sự cần thiết được đọc secret theo môi trường.
2. **Sử dụng:** không đưa credential vào log, telemetry, lỗi trả về client hoặc shell history.
3. **Audit:** ghi nhận ai, workload nào đã đọc/thay đổi secret mà không ghi giá trị.
4. **Rotation:** có lịch hoặc trigger khi nghi lộ; cập nhật ứng dụng có kiểm soát.
5. **Thu hồi:** vô hiệu hóa danh tính cũ sau khi mọi instance và job phụ thuộc đã đổi sang secret mới.
6. **Khôi phục:** có quy trình cấp lại khi triển khai lỗi hoặc secret hết hạn.

Nếu URI đã từng bị commit, xóa khỏi file hiện tại **không đủ**: Git history, CI logs hoặc bản sao có thể còn giữ secret. Phải xử lý như credential đã có nguy cơ lộ và xoay vòng theo quy trình ứng phó.

## 5. TLS: bảo vệ đường truyền và danh tính máy chủ

### 5.1. TLS bảo đảm điều gì?

TLS đúng cấu hình mang lại:

- Mã hóa dữ liệu yêu cầu, phản hồi và thông tin xác thực trên đường truyền.
- Bảo vệ tính toàn vẹn để phát hiện dữ liệu bị can thiệp.
- Kiểm tra certificate chain của server theo CA tin cậy.
- Kiểm tra hostname kết nối khớp Subject Alternative Name (SAN) của chứng chỉ.

**TLS không cấp quyền truy cập** và không thay thế mã hóa dữ liệu khi lưu trữ hoặc kiểm soát quyền trên từng trường dữ liệu. Account có role quá rộng vẫn có thể thực hiện nhiều lệnh trên một kết nối TLS hoàn toàn hợp lệ.

### 5.2. Bật TLS và không bỏ qua xác minh

~~~text
mongodb://{USER}:{ENCODED_PASSWORD}@db.example.internal:27017/shop?authSource=shop&tls=true
~~~

Với replica set, driver có thể khám phá và kết nối tới nhiều member khác nhau. Chứng chỉ, hostname và đường mạng phải hợp lệ cho **mọi member có thể được chọn**, không chỉ seed host ban đầu.

Không dùng **tlsAllowInvalidCertificates=true**, **tlsAllowInvalidHostnames=true** hoặc **tlsInsecure=true** như cách xử lý lỗi trong production. Chúng có thể bỏ qua việc xác minh danh tính máy chủ và mở rộng nguy cơ bị giả mạo endpoint.

### 5.3. Java truststore và CA nội bộ

MongoDB Java Driver dùng hạ tầng TLS của Java. Nếu certificate server do CA nội bộ cấp, cần cấu hình JVM/MongoClient tin tưởng đúng CA đó.

Ví dụ tùy chọn JVM về **đường dẫn**, không chứa password:

~~~text
-Djavax.net.ssl.trustStore=/run/certs/mongodb-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Nếu truststore có mật khẩu, mật khẩu đó cũng cần được bảo vệ. Thuộc tính JVM có thể ảnh hưởng toàn tiến trình; nếu ứng dụng sử dụng nhiều backend với CA khác nhau, cân nhắc SSLContext riêng cho từng MongoClient để tránh thay đổi trust policy của các kết nối không liên quan.

Nếu sử dụng **mTLS**, client phải trình bày certificate/private key và xác minh máy chủ. Cơ chế MongoDB X.509 có thể ánh xạ certificate thành danh tính user; phần role/authorization vẫn cần được quản lý riêng. Private key phải được bảo vệ và xoay vòng như một bí mật.

### 5.4. Lỗi TLS thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| PKIX path building failed | CA chưa được tin hoặc thiếu intermediate certificate | Kiểm tra chain và truststore thực tế của JVM |
| Hostname verification failed | Host URI không khớp SAN | Sửa DNS/URI hoặc cấp chứng chỉ đúng, không tắt hostname validation |
| SSLHandshakeException | Protocol/cipher, mTLS hoặc certificate không tương thích | Đối chiếu client/server/JDK và logs đã lọc secret |
| Server selection timeout | DNS, mạng, TLS hoặc topology | Kiểm tra từng lớp thay vì kết luận ngay do password |
| Một member của replica set không kết nối | DNS/certificate/network của member đó không đúng | Kiểm tra từng member mà driver khám phá |

Không đính kèm private key, password, URI đầy đủ hoặc dump nhạy cảm khi gửi báo cáo lỗi.

## 6. MongoDB Authentication và quyền tối thiểu với RBAC

### 6.1. Authentication khác authorization

MongoDB có thể xác thực danh tính user bằng SCRAM (phổ biến là **SCRAM-SHA-256** khi server hỗ trợ) hoặc những cơ chế được hệ thống triển khai cho phép như X.509. **Authentication** trả lời *đang kết nối bằng danh tính nào*; **authorization** trả lời *danh tính đó được phép thực hiện action nào trên resource nào*.

MongoDB sử dụng **Role-Based Access Control (RBAC)** với các role dựng sẵn và role tùy chỉnh. Nếu chỉ cần vài thao tác trên một vài collection, nên cấp role theo đúng phạm vi đó, thay vì cấp quyền quản trị rộng.

Ví dụ phân tách các account:

| Tài khoản | Công việc | Phạm vi quyền nên có |
| --- | --- | --- |
| orders_api | Đọc/thêm/cập nhật đơn, đọc khách hàng | find/insert/update trên shop.orders; find trên shop.customers |
| orders_report | Báo cáo chỉ đọc | find trên các collection thực sự cần |
| migration_job | Chuyển schema, tạo/chỉnh index trong triển khai | Role chuyên dụng, quyền theo công việc và thời gian thực hiện |
| db_operator | Tạo user/role, quản trị database | Account riêng, không dùng làm credential runtime |

Các role dựng sẵn như **read** hoặc **readWrite** có thể phù hợp khi mỗi ứng dụng sở hữu một database riêng và được phép thao tác toàn bộ database. Nhưng một API chỉ cần quyền trên collection orders không nên tự động nhận **dbOwner**, **root** hoặc **readWriteAnyDatabase**.

### 6.2. Ví dụ tạo role chỉ theo collection

Giả sử database **shop** đã bật access control và operator đăng nhập bằng account có quyền tạo role/user. Trong **mongosh**:

~~~javascript
use shop

db.createRole({
  role: "orders_api_role",
  privileges: [
    {
      resource: { db: "shop", collection: "orders" },
      actions: [ "find", "insert", "update" ]
    },
    {
      resource: { db: "shop", collection: "customers" },
      actions: [ "find" ]
    }
  ],
  roles: []
});

db.createUser({
  user: "orders_api",
  pwd: passwordPrompt(),
  roles: [
    { role: "orders_api_role", db: "shop" }
  ]
});
~~~

Hàm **passwordPrompt()** trong mongosh giúp nhập password tương tác, tránh lưu nguyên password trong lịch sử lệnh. Với môi trường có secret manager, operator cần dùng quy trình cấp phát thích hợp, đồng thời không in password trong script hoặc logs.

Role trên **chỉ cấp**:

- find, insert, update cho collection shop.orders.
- find cho collection shop.customers.
- Không cấp remove trên orders hoặc ghi customers.
- Không cấp quyền lên shop.payroll, collection khác, database khác.
- Không cấp createIndex, dropCollection, createRole, createUser hoặc lệnh quản trị.

Điều này đúng nếu account không được gán thêm những role rộng khác; cần kiểm tra role hiệu lực và role kế thừa. Không chạy **db.createRole/db.createUser trong startup ứng dụng**: quyền quản trị phải nằm ở bước provisioning/operation riêng.

### 6.3. Tách quyền runtime khỏi quyền migration/index

Spring Data MongoDB có thể tạo index qua MongoTemplate.indexOps hoặc cơ chế annotation. Với role ở trên, thao tác tạo index sẽ bị từ chối vì thiếu quyền **createIndex**. Đây là một chủ ý thiết kế: ứng dụng runtime không cần tự thay đổi schema/index mỗi khi khởi động.

Có thể áp dụng một trong các mô hình sau:

1. Dùng account migration_job có quyền phù hợp để tạo hoặc thay đổi index trong quy trình deploy, sau đó thu hồi quyền tạm thời.
2. Nếu kiến trúc thật sự yêu cầu ứng dụng tự quản lý index, chỉ cấp action cần thiết với phạm vi cụ thể và theo dõi những thay đổi đó.

Đối với aggregation có stage **$out** hoặc **$merge**, phải xét quyền ghi vào collection đích và các quyền liên quan; quyền find không tự cho phép ghi. Tương tự, backup, monitoring hoặc schema migration thường có bộ quyền khác API đọc/ghi thông thường.

### 6.4. Chú ý GridFS và nhiều collection

GridFS thường lưu metadata ở **fs.files** và nội dung nhị phân ở **fs.chunks** (với bucket mặc định). Nếu API sử dụng GridFsTemplate để tải tệp, tài khoản cần có quyền đọc **cả hai collection**. Nếu upload hoặc delete, phải bổ sung quyền ghi/xóa thích hợp trên cả metadata và chunks.

Một số driver hoặc quy trình thiết lập bucket có thể cần tạo collection/index; nên thực hiện bước này qua tài khoản migration/provisioning. Khi đổi bucket prefix, cần kiểm tra tên collection thực tế thay vì chỉ cấp cố định fs.files/fs.chunks.

### 6.5. RBAC không thay thế quyền nghiệp vụ

Account orders_api có thể đọc mọi đơn hàng trong collection orders. Khi người dùng HTTP yêu cầu một order, tầng ứng dụng còn phải giới hạn theo tenant/owner:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("tenantId").is(authenticatedTenantId)
);
~~~

Trong hệ thống thật, authenticatedTenantId phải xuất phát từ identity đã được xác thực và ủy quyền, không lấy nguyên tham số query do người gọi truyền. Nếu API chỉ tìm theo _id và bỏ qua quyền nghiệp vụ, người dùng có thể gặp lỗi **IDOR** dù MongoDB account được cấp role rất đúng.

## 7. Kiểm chứng xác thực và quyền truy cập

### 7.1. Kết nối mà không đưa password lên command line

Ví dụ mongosh với URI không chứa password, yêu cầu TLS:

~~~bash
mongosh "mongodb://db.example.internal:27017/shop?authSource=shop&tls=true" \
  --username orders_api \
  --password
~~~

Khi chạy tương tác, mongosh sẽ hỏi password. Thao tác này tránh in password trực tiếp trong command line, nhưng môi trường terminal, quyền đọc process và các công cụ thu thập lỗi vẫn cần được quản lý. Nếu dùng CA riêng, phải cấu hình cơ chế trust phù hợp trước khi kết nối.

Trong session:

~~~javascript
// Cho biết danh tính và quyền hiệu lực của session hiện tại.
db.runCommand({ connectionStatus: 1, showPrivileges: true });

// Hai truy vấn read-only tương ứng với quyền đã cấp.
db.orders.find({}, { _id: 1 }).limit(1).toArray();
db.customers.find({}, { _id: 1 }).limit(1).toArray();
~~~

Lệnh connectionStatus có thể giúp xác minh user và role đã thực sự xác thực. Kết quả cần được kiểm soát quyền chia sẻ. Phép kiểm tra phải dùng **chính account runtime**, nếu dùng root/operator thì không thể chứng minh role tối thiểu.

Trên **staging/test**, có thể kiểm tra các thao tác bị cấm (ví dụ ghi customers hoặc đọc payroll) trả lỗi không có quyền. Không tạo negative test có thể làm thay đổi hoặc xóa dữ liệu production.

### 7.2. Chẩn đoán theo từng lớp

~~~mermaid
flowchart TD
  A[Lỗi truy cập MongoDB] --> B{DNS và network hoạt động?}
  B -->|Không| C[Kiểm tra DNS, firewall, network policy]
  B -->|Có| D{TLS handshake và cert hợp lệ?}
  D -->|Không| E[Kiểm tra CA, SAN, truststore, protocol]
  D -->|Có| F{Authentication thành công?}
  F -->|Không| G[Kiểm tra authSource, credential, mechanism]
  F -->|Có| H{Command có quyền?}
  H -->|Không| I[Kiểm tra role, action và collection]
  H -->|Có| J[Đo pool, latency và query plan]
~~~

| Triệu chứng | Lớp cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| UnknownHost / SRV lookup failed | DNS/URI | Hostname, SRV/TXT, DNS và network policy |
| Server selection timeout | Mạng/TLS/topology | Kiểm tra kết nối đến các member, certificate và firewall |
| SSLHandshakeException / PKIX | TLS | CA chain, truststore, hostname, ngày hết hạn |
| Authentication failed | Auth | authSource, username, password encoding, cơ chế xác thực |
| Not authorized to execute command | RBAC | Role thực tế, action và namespace được truy cập |
| Index creation denied at startup | RBAC/index lifecycle | Tách migration account hoặc sửa quy trình quản lý index |
| Đọc nhầm tenant | Quyền nghiệp vụ | Xác minh điều kiện tenant/owner và xác thực HTTP |
| Độ trễ tăng | Pool/query/index/tải DB | Theo dõi timeout, metrics và explain; không tăng quyền để giải quyết |

Một lệnh **ping thành công** chỉ cho biết có thể trao đổi với máy chủ tại thời điểm kiểm tra. Nó không chứng minh đã dùng đúng cluster hoặc tài khoản có quyền phù hợp, và cũng không thay thế kiểm thử certificate/hostname.

## 8. Xoay vòng credential và certificate

### 8.1. Vì sao thay password cần phối hợp nhiều instance?

MongoDB Java Driver duy trì **connection pool**. Kết nối cũ và kết nối mới có thể ở những trạng thái xác thực khác nhau khi password được thay trên server. Nếu đổi password trước khi ứng dụng dùng credential mới, các instance mở kết nối mới có thể bắt đầu thất bại.

Một quy trình dùng hai danh tính (khi hạ tầng cho phép):

1. **Cấp credential mới** cho user kế tiếp với role giống account hiện tại, quyền tối thiểu được kiểm tra lại.
2. **Kiểm tra kết nối mới** có TLS hợp lệ và truy vấn trong phạm vi cho phép.
3. **Cập nhật secret và rolling deployment**; các instance mới tạo MongoClient/connection pool với credential mới.
4. **Quan sát** authentication errors, pool usage, request failures, độ trễ và tỷ lệ instance đã đổi.
5. **Thu hồi tài khoản cũ** khi toàn bộ instance và job phụ thuộc đã chuyển đổi thành công.
6. **Ghi nhận** thời điểm, version secret, kết quả kiểm thử và owner; không đưa password vào báo cáo.

Nếu hệ thống chỉ cho phép thay password của một username, không mặc định cả password cũ và mới cùng được chấp nhận. Cần tính đến maintenance window, khả năng đồng bộ triển khai hoặc cơ chế chuyển tiếp mà hạ tầng hỗ trợ.

### 8.2. Xoay vòng CA và TLS certificate

- Phân phối truststore có CA mới đến client trước khi thay certificate server, theo khoảng chồng lấn tin cậy được phê duyệt.
- Xác minh SAN/hostname đúng cho từng member và ngày hết hạn.
- Nếu dùng mTLS, thay private key/certificate của client và đối chiếu lại danh tính X.509/role nếu cần.
- Theo dõi handshake trong giai đoạn chồng lấn; chỉ loại CA cũ sau khi toàn bộ client đã chuyển đổi.

Password, CA và certificate có vòng đời khác nhau; không gộp thay đổi mà thiếu kế hoạch quan sát và rollback.

### 8.3. Khi nghi ngờ secret đã bị lộ

Nếu URI chứa password xuất hiện trong Git, log hoặc artifact:

1. Hạn chế truy cập nơi bị lộ, báo người phụ trách an ninh/vận hành qua kênh phù hợp.
2. **Xoay vòng hoặc thu hồi credential**, vì chỉ xóa chuỗi khỏi file hiện tại không xóa nó khỏi Git history, cache và các bản sao.
3. Đối chiếu audit, hoạt động bất thường và phạm vi quyền của account bị lộ.
4. Triển khai secret mới, kiểm tra lại TLS và authentication.
5. Xử lý nguyên nhân: log masking, secret scanning, phân quyền secret store và chính sách CI.

Không đính kèm nguyên password đã lộ vào báo cáo điều tra.

## 9. Tích hợp và kiểm thử với Spring Data MongoDB

### 9.1. Một smoke test kết nối và quyền đọc

Trong một ứng dụng Spring Boot test có cấu hình URI qua secret nguồn test:

~~~java
package example.security;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class MongoSecuritySmokeTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void canPingAndQueryAllowedCollection() {
        Document ping = mongoTemplate.getDb()
            .runCommand(new Document("ping", 1));
        assertEquals(1.0, ((Number) ping.get("ok")).doubleValue());

        // Collection có thể rỗng; không ném lỗi là đủ cho smoke test này.
        mongoTemplate.findOne(
            new Query().limit(1),
            Document.class,
            "orders"
        );
    }
}
~~~

Test này **chỉ chứng minh** kết nối và một truy vấn đọc được thực thi bằng credential của test. Nó không tự chứng minh TLS đã xác minh hostname, role là tối thiểu hoặc API không cho phép truy cập chéo tenant. Cần thêm negative tests trong staging và kiểm tra cấu hình thật của môi trường triển khai.

### 9.2. Ma trận kiểm thử bảo mật

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Thiếu cấu hình URI bắt buộc | Ứng dụng không tự fallback sang database production ngoài ý muốn |
| Password chứa ký tự đặc biệt trong URI | Kết nối bằng giá trị percent-encode đúng; không ghi password ra log |
| authSource/password sai | Xác thực bị từ chối, lỗi không chứa bí mật |
| CA hoặc hostname không hợp lệ | TLS từ chối, không tự bật insecure mode |
| orders_api đọc orders/customers | Thành công với quyền được cấp |
| orders_api ghi customers | MongoDB từ chối trong test/staging |
| orders_api đọc payroll | MongoDB từ chối trong test/staging |
| orders_api tạo index/drop collection | MongoDB từ chối nếu role không cấp quyền |
| Người dùng tenant A yêu cầu order tenant B | HTTP/service từ chối theo quy tắc nghiệp vụ |
| Rotate credential khi nhiều instance chạy | Instance mới xác thực thành công, account cũ được thu hồi sau chuyển đổi |
| Certificate gần hết hạn | Alert được phát trước hạn theo quy định |

Không chạy các phép thử ghi/xóa phá hoại trên production. Ở production, kiểm tra role bằng thao tác đọc cấu hình, audit và read-only smoke tests; thực hiện negative tests với môi trường thử nghiệm có quyền tương đương.

### 9.3. Checklist trước khi mở traffic

1. **URI:** đúng hostname, database, authSource, replica set/SRV và version driver.
2. **Secret:** lấy từ nguồn được phê duyệt, không commit/log, chỉ workload cần thiết có quyền đọc.
3. **TLS:** CA chain, SAN/hostname, truststore và certificate hợp lệ; không cấu hình bypass.
4. **Account:** đúng user, role và action trên database/collection; account migration/operator tách biệt.
5. **Spring Boot:** property đúng phiên bản, MongoClient thực sự nhận cấu hình mong muốn.
6. **Ứng dụng:** kiểm thử truy cập chéo tenant, giới hạn dữ liệu theo quyền người dùng HTTP.
7. **Rotation:** diễn tập thay credential và certificate, có kế hoạch thu hồi/rollback.
8. **Monitoring:** cảnh báo authentication errors, TLS expiration, pool saturation, timeout và truy cập bất thường.

Nên lưu hồ sơ triển khai gồm version cấu hình, alias cluster, role/collection/action, kết quả test, thời điểm và owner; **không lưu password, private key hoặc URI đầy đủ**.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Commit URI có password vào Git | Rò rỉ qua lịch sử và bản sao | Dùng secret manager; rotate nếu đã lộ |
| Xem percent-encoding là mã hóa | Password có thể giải mã ngay | Bảo vệ toàn URI |
| Dùng root cho service web | Lộ credential có thể gây tác động diện rộng | Role nhỏ theo collection/action |
| Bật TLS nhưng bỏ qua certificate validation | Rủi ro giả mạo endpoint | Sửa CA/certificate và xác minh SAN |
| Bỏ qua authSource | Khó chẩn đoán lỗi authentication giữa môi trường | Chỉ định database chứa user rõ ràng |
| Tạo index tự động bằng account runtime hạn chế | Lỗi unauthorized ở startup | Tách index migration/provisioning |
| Chỉ cấp find trên fs.files mà quên fs.chunks | Không tải được nội dung GridFS | Cấp đúng quyền cho cả hai collection |
| Nghĩ MongoDB role thay thế tenant authorization | Có thể đọc dữ liệu tenant khác | Kiểm tra owner/tenant trong API |
| Đổi password server trước khi triển khai client mới | Connection pool tạo kết nối mới thất bại | Rolling rotation có kiểm tra |
| Chỉ kiểm tra ping | Bỏ sót role quá rộng và endpoint nhầm | Kiểm tra TLS, user, roles và quyền nghiệp vụ |
| In URI trong log để debug | Tăng phạm vi lộ bí mật | Chỉ log alias môi trường và metadata được phép |

## 11. Bài thực hành

Chuẩn bị MongoDB test environment có authentication và TLS:

1. Dùng operator test tạo database shop với orders, customers và payroll.
2. Tạo orders_api_role như phần 6, cấp user orders_api bằng passwordPrompt hoặc công cụ cấp secret của môi trường.
3. Cấp URI cho Spring Boot qua MONGODB_URI, bật TLS và truststore nếu cần; giữ toàn bộ credential ngoài Git.
4. Kiểm tra MongoTemplate đọc orders/customers. Ở staging, xác nhận ghi customers và đọc payroll bị từ chối.
5. Cố ý dùng authSource sai và truststore không tin CA trong một lần thử được kiểm soát; xác nhận lỗi rồi khôi phục cấu hình đúng.
6. Viết endpoint đọc order theo tenantId từ security context; thử truy cập order khác tenant.
7. Tạo danh tính tiếp theo có role tương đương, rolling deploy với credential mới và thu hồi account cũ sau khi mọi instance ổn định.
8. Lập báo cáo chỉ chứa cấu hình không bí mật, role/action được cấp, kết quả kiểm thử, ngày hết hạn certificate và lịch rotation.

**Câu hỏi tự đánh giá:**

- Vì sao database path và authSource trong URI có thể khác nhau?
- Vì sao URI có password đã percent-encode vẫn cần bảo vệ như một bí mật?
- Khi TLS bật nhưng certificate/hostname không được xác minh, còn rủi ro gì?
- Khi nào nên dùng role tùy chỉnh thay vì cấp readWrite trên cả database?
- Vì sao quyền đọc orders ở MongoDB vẫn cần kiểm tra tenant trong ứng dụng?
- Tại sao xoay vòng credential phải xét nhiều instance và connection pool đang hoạt động?

Kết nối Spring Data MongoDB an toàn đòi hỏi quản lý đồng thời **đích kết nối, bí mật, TLS và quyền của tài khoản**. Khi cả bốn lớp đều được kiểm tra và có quy trình xoay vòng/thu hồi, ứng dụng có thể dùng MongoTemplate hoặc repository một cách ổn định, đồng thời giới hạn phạm vi ảnh hưởng nếu xảy ra cấu hình sai hoặc credential bị lộ.

## 12. Tài liệu tham khảo

- [MongoDB – Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string/): cú pháp mongodb:// và mongodb+srv://.
- [MongoDB – Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): các tùy chọn authSource, TLS và topology.
- [MongoDB – Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/): mã hóa đường truyền và certificate.
- [MongoDB – Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): mô hình RBAC.
- [MongoDB – User-Defined Roles](https://www.mongodb.com/docs/manual/core/security-user-defined-roles/): resource, action và role tùy chỉnh.
- [MongoDB – db.createRole()](https://www.mongodb.com/docs/manual/reference/method/db.createRole/): tạo role.
- [MongoDB – db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/): tạo account.
- [MongoDB Java Driver – TLS](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/): thiết lập TLS cho Java driver.
- [Spring Data MongoDB – Reference](https://docs.spring.io/spring-data/mongodb/reference/): truy cập MongoDB bằng Spring Data.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): quản lý cấu hình ngoài ứng dụng.
- [OWASP – Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): cấp phát, bảo vệ và xoay vòng bí mật.
