# Không kết nối được: URI, DNS, TLS, `authSource` hoặc quyền

## Mục tiêu học tập

Trong **Spring Data MongoDB**, cùng một triệu chứng “không kết nối được” có thể bắt nguồn từ nhiều lớp: URI sai cú pháp, DNS không tìm được máy chủ, mạng chặn cổng, TLS handshake thất bại, đăng nhập vào sai database hoặc tài khoản thiếu quyền thực hiện lệnh trên collection.

Ví dụ, một lệnh `mongoTemplate.findOne(...)` thất bại có thể là do driver chưa tìm được primary, do mật khẩu đúng nhưng `authSource` sai, hoặc do đã xác thực thành công nhưng không được cấp quyền `find`. Cách xử lý giữa các trường hợp khác nhau hoàn toàn.

Bài học thuộc chương **Lỗi và chẩn đoán**. Sau bài này, bạn có thể:

- Đọc và kiểm tra MongoDB connection string dạng `mongodb://` và `mongodb+srv://`.
- Phân biệt **database ứng dụng** với **authentication database (`authSource`)**.
- Kiểm tra DNS (A/AAAA, SRV/TXT), TCP, replica set topology và TLS theo một thứ tự có thể lặp lại.
- Phân biệt lỗi **authentication** với **authorization** qua thông báo, mã lỗi và thao tác thực tế.
- Kiểm tra trực tiếp `MongoClient`, `MongoTemplate`, repository và reactive client.
- Chẩn đoán an toàn mà không lộ credentials hoặc tắt xác minh TLS.

> Các đoạn mã tập trung vào API Java Driver và Spring Data MongoDB. Tên property cấu hình của Spring Boot, tên exception và tùy chọn của driver cần đối chiếu với phiên bản dự án đang chạy.

## 1. Xác định lớp lỗi trước khi thay đổi cấu hình

Một request đọc MongoDB phải đi qua nhiều bước. Mỗi bước có triệu chứng và phép kiểm tra riêng:

```mermaid
flowchart TD
    A[Spring Data MongoDB gọi MongoClient] --> B[Parse URI và tạo settings]
    B --> C[DNS: phân giải host hoặc SRV/TXT]
    C --> D[TCP: host, port, firewall]
    D --> E[TLS handshake và kiểm tra certificate]
    E --> F[Hello, khám phá topology và chọn server]
    F --> G[Authentication: user, password, authSource]
    G --> H[Authorization: database, collection, command]
    H --> I[MongoTemplate / repository xử lý truy vấn]
```

Đây là sơ đồ các lớp chẩn đoán, không phải thứ tự giao thức bắt buộc cho từng socket: driver có thể khám phá node, mở thêm connection và thực hiện authentication trong quá trình vận hành.

| Triệu chứng | Khả năng cần kiểm tra đầu tiên | Dấu hiệu giúp phân biệt |
| --- | --- | --- |
| Lỗi ngay khi phân tích URI | Sai scheme, ký tự đặc biệt, option không hợp lệ | Exception cấu hình trước khi có traffic |
| `UnknownHostException` | DNS hoặc hostname sai | Không phân giải được tên từ môi trường app |
| `Connection refused`, `ConnectException` | Sai port, dịch vụ chưa lắng nghe, firewall | Không thiết lập được socket |
| `SSLHandshakeException`, `PKIX path building failed` | TLS, CA, hostname verification | TCP có thể thông nhưng handshake không thành công |
| `MongoTimeoutException` khi chọn server | DNS/TCP/TLS/topology/read preference | Xem `ClusterDescription` và nguyên nhân bên dưới |
| `AuthenticationFailed`, thường code `18` | User/password, `authSource`, auth mechanism | Đã đến server nhưng không xác thực được |
| `not authorized`, thường code `13` | Role hoặc privilege không đủ | Xác thực xong nhưng command bị từ chối |
| `ping` được nhưng `find`/`save` lỗi | Sai database đích hoặc thiếu quyền | Phải thử đúng thao tác và namespace |

Một lỗi server selection timeout **không tự chứng minh MongoDB quá tải**. Nó có thể chứa nguyên nhân gốc là DNS, certificate hoặc network.

## 2. MongoDB URI: host, database và `authSource`

Hai dạng URI phổ biến:

```text
mongodb://<username>:<password>@host1:27017,host2:27017/orders?authSource=admin&tls=true

mongodb+srv://<username>:<password>@cluster.example.net/orders?authSource=admin
```

Các phần có mục đích khác nhau:

- `mongodb://`: chỉ định một hoặc nhiều seed host và port; driver tiếp tục khám phá topology.
- `mongodb+srv://`: lấy danh sách host/port từ DNS SRV và các tùy chọn phù hợp từ TXT; không chỉ định port trực tiếp ở phần host.
- `/orders`: database mặc định cho thao tác ứng dụng khi không chỉ rõ database khác.
- `authSource=admin`: database dùng xác thực tài khoản; **không** quyết định database mà service phải đọc/ghi.
- `tls=true`: yêu cầu TLS cho connection. URI SRV thường bật TLS mặc định trừ khi có cấu hình ghi đè; kiểm tra settings cuối cùng.
- Các option `replicaSet` và `readPreference`: ảnh hưởng server nào có thể được chọn.

### 2.1. Ví dụ sai `authSource`

Giả sử người quản trị tạo user `orders_app` trong `admin`, sau đó cấp quyền đọc/ghi ở `orders`. Một URI thiếu `authSource`:

```text
mongodb://orders_app:<encoded-password>@mongo1.internal:27017/orders?tls=true
```

Với username/password SCRAM và URI có database `orders`, authentication database mặc định có thể là `orders`. Vì user nằm ở `admin`, thao tác đăng nhập có thể báo `AuthenticationFailed`. URI cần nêu rõ:

```text
mongodb://orders_app:<encoded-password>@mongo1.internal:27017/orders?authSource=admin&tls=true
```

Nếu user được **tạo trong `orders`**, `authSource=orders` mới phù hợp. Hãy xác minh nguồn tạo user thay vì thử bừa nhiều giá trị.

Đối với SCRAM thông dụng, nếu URI không chỉ định database nào, auth database mặc định thường là `admin`. Với X.509, OIDC, LDAP hoặc mechanism khác, quy tắc và yêu cầu có thể khác; cần dùng thông số tương ứng với cơ chế thực tế.

### 2.2. Percent-encode ký tự đặc biệt trong password

Nếu password có `@`, `:`, `/`, `?`, `#`, `%` hoặc ký tự dành riêng khác của URI, phải **percent-encode riêng username/password** trước khi chèn vào chuỗi URI.

Ví dụ password giả định `p@ss:word`:

```text
mongodb://demo:p%40ss%3Aword@mongo1.example.net:27017/orders?authSource=admin
```

Nếu bỏ encode, dấu `@` có thể bị hiểu là ranh giới thông tin đăng nhập và hostname. Không encode toàn bộ URI thành một chuỗi duy nhất vì sẽ làm mất cấu trúc scheme, dấu phân cách và query parameters.

**Bảo vệ secrets:** không in URI chứa password vào log, ticket, ảnh chụp terminal hay báo cáo CI. Tham số CLI có thể xuất hiện trong process list hoặc shell history; ưu tiên secret manager, password prompt và cấu hình có kiểm soát.

### 2.3. Những lỗi URI nên kiểm tra

| Lỗi cấu hình | Hậu quả thường gặp |
| --- | --- |
| `mongodb+srv://cluster:27017` | Sai cú pháp: SRV URI không chứa port trên hostname |
| Thừa/thiếu `/orders` | Database mặc định khác dự kiến |
| Sai `authSource` | Không xác thực được tài khoản |
| Không encode `@`/`:` trong password | Driver phân tích sai thông tin URI |
| Chọn `replicaSet` không khớp topology | Driver không chọn được server phù hợp |
| Dùng URI trong property nhưng code tạo `MongoClient` riêng | Bean Spring Data có thể dùng cấu hình khác |
| Host sai hoặc dán nhầm URI của môi trường khác | DNS/connection/auth/permission có thể thất bại |

## 3. DNS: kiểm tra ngay tại nơi ứng dụng chạy

DNS trên laptop phát triển **không nhất thiết giống DNS trên container/pod/VM**. Chẩn đoán phải thực hiện từ môi trường có đường mạng và DNS gần với ứng dụng nhất.

### 3.1. URI `mongodb://`: A/AAAA record

URI `mongodb://mongo1.internal:27017/orders` cần phân giải được `mongo1.internal`.

Linux hoặc container có công cụ thích hợp:

```bash
getent hosts mongo1.internal
nslookup mongo1.internal
```

Windows PowerShell:

```powershell
Resolve-DnsName -Name mongo1.internal -Type A
Resolve-DnsName -Name mongo1.internal -Type AAAA
```

Không phải mọi container tối giản đều có `dig`, `getent` hay `nslookup`; nếu thiếu, sử dụng diagnostic container được phép trong cùng môi trường mạng thay vì cài công cụ tùy tiện lên production workload.

### 3.2. URI `mongodb+srv://`: SRV và TXT

Với `mongodb+srv://cluster.example.net/orders`, driver cần tra SRV tại:

```text
_mongodb._tcp.cluster.example.net
```

Linux:

```bash
dig SRV _mongodb._tcp.cluster.example.net
dig TXT cluster.example.net
```

PowerShell:

```powershell
Resolve-DnsName -Name _mongodb._tcp.cluster.example.net -Type SRV
Resolve-DnsName -Name cluster.example.net -Type TXT
```

Sau đó kiểm tra **từng target hostname và port trong SRV record**. Tra SRV thành công không bảo đảm tất cả target mở TCP; DNS cũng có thể trả record khác do private zone hoặc cơ chế cache.

Những nguyên nhân điển hình:

1. Corporate DNS, firewall hoặc resolver trong cluster không hỗ trợ/không cho tra SRV/TXT.
2. Tên SRV sai miền hoặc record không phù hợp quy tắc validation của driver.
3. Target từ SRV không phân giải được A/AAAA, hoặc chỉ có địa chỉ ở mạng mà pod không đi tới.
4. VPN, VPC peering, private endpoint hoặc DNS zone chưa được triển khai cho môi trường ứng dụng.
5. TXT record chứa tùy chọn không được driver cho phép hoặc xung đột với URI.

**Cách kiểm chứng:** ghi nhận tên record được tra, target và loại lỗi, nhưng không đưa username/password vào kết quả log.

## 4. TCP, firewall, allowlist và replica set topology

Sau DNS, app phải mở TCP tới host/port mà driver cần. Ví dụ:

Linux (nếu có `nc`):

```bash
nc -vz mongo1.internal 27017
```

Windows:

```powershell
Test-NetConnection -ComputerName mongo1.internal -Port 27017
```

Nếu thất bại, xác minh từ môi trường chạy app:

- Server có đang lắng nghe đúng interface/cổng?
- Có firewall, security group, IP allowlist, Kubernetes `NetworkPolicy` hoặc proxy chặn lưu lượng không?
- DNS đang trả public IP hay private IP? Tuyến mạng có phù hợp với endpoint đó?
- App cần truy cập **những node nào của replica set** sau khi driver khám phá topology?
- `replicaSet` trong URI có đúng tên thực tế không? Có primary cho thao tác ghi không?
- Read preference có yêu cầu node không tồn tại hoặc không sẵn sàng không?

Một seed host truy cập được chưa bảo đảm driver có thể đến **các hostname được trả về trong cấu hình replica set**. Đây là nguyên nhân hay gặp khi kết nối MongoDB từ container, Kubernetes hoặc qua NAT.

**Phân biệt:** `Connection refused` thường có nghĩa kết nối bị từ chối tại host/port hoặc bởi thiết bị trên đường đi; `connection timed out` có thể do packet bị drop hoặc host không phản hồi. `MongoTimeoutException` khi chọn server có thể xuất hiện ở lớp cao hơn các lỗi này.

Mở được TCP **không chứng minh** TLS, authentication hoặc quyền collection đã hoạt động.

## 5. TLS: phân biệt lỗi certificate với lỗi credentials

TLS bảo vệ dữ liệu trên đường truyền và xác minh danh tính server qua certificate. Sau khi TCP thông, TLS handshake có thể thất bại.

| Thông báo | Kiểm tra |
| --- | --- |
| `SSLHandshakeException: PKIX path building failed` | JVM không tin CA của server hoặc thiếu intermediate certificate |
| `No subject alternative DNS name matching ...` | Host trong URI không khớp SAN của certificate |
| `bad_certificate` | Certificate phía client hoặc server bị từ chối; xem yêu cầu mTLS |
| Handshake fail sau khi đổi endpoint/proxy | Certificate chain, SNI, TLS termination và host đích |
| Lỗi chỉ xảy ra sau khi nâng JDK | TLS version/cipher và truststore trong runtime mới |

Ví dụ URI:

```text
mongodb://mongo1.example.net:27017/orders?tls=true&authSource=admin
```

MongoDB Java Driver trên JVM thường dùng TLS/SSL settings theo Java runtime. Khi server dùng CA nội bộ, **truststore của ứng dụng phải tin CA thích hợp**. Nếu triển khai mTLS, còn phải cung cấp certificate và private key phía client theo cấu hình SSL context/keystore tương ứng.

Với replica set hoặc SRV, certificate phải phù hợp **từng hostname thực được driver sử dụng**, không chỉ seed hostname đầu tiên. Dùng IP thay cho DNS để “né lỗi” có thể gây mismatch nếu certificate không có IP SAN.

Không khắc phục bằng cách tắt TLS, bỏ hostname verification hoặc chấp nhận mọi certificate. Những thay đổi đó khiến ứng dụng không còn bảo đảm đang nói chuyện với đúng server được tin cậy.

## 6. Authentication: `authSource`, secret và mechanism

Authentication kiểm tra tài khoản được phép đăng nhập hay không. Với SCRAM:

- Tài khoản được tạo trong database nào?
- Username đã chính xác chưa?
- Password được cấp từ secret manager có đúng phiên bản không?
- Password trong URI đã encode đúng chưa?
- `authSource` có trỏ đến database chứa user không?
- MongoDB server và client có dùng mechanism tương thích không?
- Có một bean `MongoClient` khác đang dùng URI/secret cũ không?

Nếu dùng X.509 hoặc cơ chế khác, cần kiểm tra principal, certificate và các option của mechanism đó, không áp dụng máy móc cách sửa của SCRAM.

### 6.1. Thử bằng `mongosh` với password prompt

Ví dụ dành cho môi trường có shell và đã được phép kết nối:

```bash
mongosh "mongodb://mongo1.internal:27017/orders?tls=true" \
  --username orders_app \
  --authenticationDatabase admin \
  --password
```

Tùy phiên bản/shell, `--password` không có giá trị sẽ cho phép nhập tương tác. Không đưa password vào dòng lệnh. Sau khi login, cần thử **command cùng namespace với ứng dụng**; shell mở thành công chưa chứng minh app có quyền ghi.

Một thử nghiệm bằng `mongosh` cũng cần dùng đường mạng, CA và DNS tương đương với JVM ứng dụng. Nếu công cụ hoạt động trên laptop nhưng không hoạt động trong pod, chưa thể kết luận password là đúng cho deployment đó.

### 6.2. Khi nào cần xem mã lỗi 18?

MongoDB thường báo `AuthenticationFailed` với code `18` cho lỗi đăng nhập. Sửa theo thứ tự **user → authSource → secret → mechanism**, thay vì đổi database nghiệp vụ hoặc cấp role quản trị. Nếu authentication đã thành công mà một command báo `Unauthorized` (code `13`), chuyển sang điều tra **authorization**.

## 7. Authorization: đúng user nhưng thiếu quyền

Authentication và authorization là hai lớp khác nhau. Tài khoản `orders_reader` có thể được tạo trong `admin`, xác thực thành công và có role `read` trên `orders`, nhưng không được phép thêm/xóa/sửa document.

Ví dụ thử đọc trong `mongosh`:

```javascript
use orders
db.orders.find({ _id: "healthcheck-nonexistent" }).limit(1)
```

Không viết một document test vào collection production chỉ để kiểm tra quyền. Nếu cần xác minh ghi, hãy dùng **collection kiểm tra riêng** và tài khoản/môi trường được cho phép.

| Thao tác Spring Data MongoDB | Quyền cần có trong MongoDB |
| --- | --- |
| `MongoTemplate.findOne`, repository `findById` | Quyền `find` trên collection |
| `insert`, `save` đối tượng mới | Quyền `insert` |
| `updateFirst`, `findAndModify` | Quyền `update` |
| `remove` / repository delete | Quyền `remove` |
| Tạo index, tạo collection | Quyền riêng cho tạo index/collection |
| Aggregation có truy cập nhiều collection | Quyền trên các collection mà pipeline sử dụng |
| Transaction gồm nhiều command | Quyền của từng command và deployment hỗ trợ transaction |

Nếu error code `13` trên `orders`, hãy kiểm tra **database/collection đích** và role được cấp, chứ không mặc định sửa `authSource`. Role `readWrite` trên database ứng dụng có thể phù hợp cho workload cần ghi, nhưng nhiều service chỉ cần `read` hoặc một custom role hẹp hơn.

Không cấp `root` hoặc quyền toàn cụm chỉ để vượt qua lỗi thiếu privilege. Tốt hơn là tách account chạy ứng dụng với account migration/index và chỉ cấp quyền cần thiết.

### 7.1. Sai namespace cũng biểu hiện thành “thiếu quyền”

Giả sử `MongoTemplate` được cấu hình database `admin` thay vì `orders`. Query `admin.orders` có thể bị từ chối dù user có `readWrite` trên `orders`. **Sửa database đích** mới là thay đổi đúng.

Trong hệ đa tenant, phải kiểm tra ánh xạ tenant → database đã được xác thực. `authSource` có thể giống nhau giữa các tenant, còn database nghiệp vụ và quyền truy cập phải được giới hạn theo chính sách.

## 8. Spring Data MongoDB: xác định client đang được sử dụng

### 8.1. Kiểm tra cấu hình ứng dụng

Với những phiên bản Spring Boot sử dụng property `spring.data.mongodb.uri`:

```properties
spring.data.mongodb.uri=${MONGODB_URI}
```

Ở một số phiên bản Spring Boot mới, tên property MongoDB đã thay đổi. Cần đối chiếu **configuration reference của đúng phiên bản** thay vì đoán tên thuộc tính. Nếu project có bean `MongoClient` hoặc `MongoDatabaseFactory` tự định nghĩa, cấu hình bằng code có thể thay thế phần auto configuration từ properties.

URI chứa credentials nên được lấy từ environment/secret manager và không xuất ra endpoint configuration/log.

### 8.2. Tạo `MongoClient` chưa phải phép thử kết nối

MongoDB Java Driver quản lý connection pool và khám phá server. Khởi tạo `MongoClient` hay `MongoTemplate` không nhất thiết kiểm chứng ngay kết nối, TLS hoặc permission. Một ứng dụng có thể startup bình thường nhưng request đầu tiên mới báo timeout.

Smoke test minh họa cho Java Driver:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .build();

try (MongoClient client = MongoClients.create(settings)) {
    var db = client.getDatabase("orders");

    // Kiểm tra server response ở mức cơ bản.
    db.runCommand(new Document("ping", 1));

    // Kiểm tra thêm quyền đọc trên collection nghiệp vụ.
    // Không in nội dung document ra log.
    db.getCollection("orders")
      .find(new Document("_id", "healthcheck-nonexistent"))
      .limit(1)
      .first();
}
```

Đây là đoạn code độc lập để chẩn đoán, không phải thứ nên chạy trên mỗi HTTP request.

**`ping` không chứng minh tài khoản đọc hoặc ghi được collection.** Một account có thể ping thành công nhưng `find` hay `update` bị `Unauthorized`. Cần kiểm tra thao tác phù hợp với quyền thực tế của ứng dụng.

### 8.3. Kiểm tra `MongoTemplate` thực tế

Sau khi test trực tiếp driver, phải kiểm tra bean `MongoTemplate` mà service hoặc repository đang dùng:

```java
@Service
public class MongoConnectionProbe {
    private final MongoTemplate mongoTemplate;

    public MongoConnectionProbe(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void verifyRead() {
        Query q = Query.query(
                Criteria.where("_id").is("healthcheck-nonexistent"));

        mongoTemplate.findOne(q, Document.class, "orders");
    }
}
```

Ví dụ dùng `MongoTemplate` đã cấu hình từ application context; `Document` ở đây là `org.bson.Document`. Lệnh không cần document phải tồn tại: thành công cho thấy truy vấn có thể được thực thi trên namespace, khác với lỗi quyền hoặc kết nối.

Cần kiểm tra:

1. `MongoDatabaseFactory` đang chọn database nào.
2. Repository có tham chiếu đúng template không nếu ứng dụng có **nhiều datasource/MongoClient**.
3. Connection string được cấu hình ở đâu: properties, environment, code hay container secret.
4. MongoDB có yêu cầu TLS/auth riêng giữa các môi trường không.
5. Nếu chạy reactive, client reactive có cùng URI và settings được dự định không.

Có thể ghi **tên database đích** qua API metadata nếu chính sách log cho phép, nhưng không bao giờ in đầy đủ connection string khi nó chứa mật khẩu.

### 8.4. Trường hợp `ReactiveMongoTemplate`

`ReactiveMongoTemplate` cũng sử dụng MongoDB Java Driver, nên các vấn đề URI, DNS, TLS, authSource và permission vẫn tồn tại. Điểm khác là reactive publisher chỉ được thực thi khi có subscriber.

```java
Mono<Document> check =
        reactiveMongoTemplate.executeCommand("{ ping: 1 }");

// Trong phương thức reactive của service/controller:
return check.then();
```

Tạo `Mono` mà không subscribe hoặc return cho framework là **chưa thử kết nối**. Không gọi `block()` trên WebFlux event loop. Trong integration test, dùng `StepVerifier` hoặc cơ chế subscription tương ứng.

### 8.5. Vì sao transaction và index có thể lỗi dù CRUD hoạt động?

- Account runtime có quyền đọc/ghi nhưng **không có quyền tạo index/collection**; tạo index lúc startup có thể thất bại.
- Transaction cần deployment và cơ chế transaction phù hợp; lỗi `Transaction numbers are only allowed ...` thuộc khả năng topology/deployment, không giống lỗi password.
- Một aggregation dùng `$lookup` vào collection khác có thể cần quyền trên collection đó.
- Lỗi do không có primary trong replica set có thể ảnh hưởng write dù một số read vẫn được đáp ứng theo read preference.

Cần ghi nhận **command nào** thất bại, thay vì kết luận toàn bộ MongoDB “không kết nối được”.

## 9. Đọc exception và log đúng cách

Ví dụ log minh họa:

```text
MongoTimeoutException:
Timed out while waiting for a server that matches WritableServerSelector.
ClusterDescription:
  ServerDescription{address=mongo1.internal:27017, type=UNKNOWN,
    exception=MongoSocketException:
    Exception opening socket,
    caused by java.net.ConnectException: Connection refused}
```

Lỗi ngoài cùng là `MongoTimeoutException`, nhưng nguyên nhân có thể là **socket không mở được**. Tăng `serverSelectionTimeoutMS` không sửa host/port sai.

Những nhóm exception nên phân biệt:

- `MongoConfigurationException` hoặc lỗi parse URI: settings không hợp lệ.
- `UnknownHostException`: không phân giải hostname.
- `MongoSocketException` / `MongoSocketOpenException`: lỗi socket hoặc kết nối.
- `SSLHandshakeException`: TLS, certificate hoặc tên host.
- `MongoSecurityException` hay `MongoCommandException` code `18`: lỗi authentication.
- `MongoCommandException` code `13`: thiếu authorization.
- `MongoTimeoutException`: chờ server selection hoặc bước chờ liên quan quá hạn.

Tên class và cách exception được bọc có thể khác tùy driver; Spring Data cũng dịch một số lỗi thành `DataAccessException`. **Đọc cause chain**, error code, namespace, server address và command name.

### 9.1. Phân biệt các timeout

| Tùy chọn/khái niệm | Ý nghĩa |
| --- | --- |
| `serverSelectionTimeoutMS` | Chờ chọn một server phù hợp topology và thao tác |
| `connectTimeoutMS` | Giới hạn thời gian thiết lập kết nối TCP |
| `socketTimeoutMS` | Giới hạn chờ I/O trên socket theo cấu hình driver |
| Connection pool checkout timeout | Chờ lấy connection rảnh trong pool |
| HTTP/gateway request timeout | Giới hạn toàn request, có thể xảy ra trước timeout MongoDB |

Nếu network ổn và server thực sự chậm, điều chỉnh timeout có thể hợp lý. Nhưng với DNS sai, TLS không trust hoặc account không có quyền, tăng timeout chỉ khiến chờ lâu hơn.

### 9.2. Bật logging có kiểm soát

Có thể tạm bật log về topology/connection của driver:

```properties
logging.level.org.mongodb.driver.cluster=DEBUG
logging.level.org.mongodb.driver.connection=DEBUG
```

Chỉ bật trong phạm vi cho phép, có thời hạn và lọc dữ liệu nhạy cảm. Logging command/query ở mức debug có thể ghi email, token hoặc payload PII. Không in URI, secret, request body hay toàn bộ document để làm bằng chứng kết nối.

## 10. Quy trình xử lý sự cố theo từng bước

1. **Xác nhận operation:** startup, `ping`, `find`, `save`, transaction, aggregation hay tạo index? Ghi lại thời điểm và exception/cause code.
2. **Kiểm tra cấu hình thực đang chạy:** scheme URI, host/port, database nghiệp vụ, `authSource`, TLS, topology options và client bean đang dùng.
3. **Kiểm tra cú pháp URI:** ký tự đặc biệt của password đã encode chưa; SRV không kèm port; `replicaSet` có khớp không.
4. **Kiểm tra DNS từ container/pod/VM ứng dụng:** A/AAAA hoặc SRV/TXT, rồi phân giải các target hostname.
5. **Kiểm tra TCP và topology:** tất cả node cần thiết có truy cập được không; firewall/network policy, private endpoint/allowlist và primary có ổn định không.
6. **Kiểm tra TLS:** truststore, CA chain, SAN/hostname, TLS settings và yêu cầu mTLS nếu có.
7. **Kiểm tra authentication:** vị trí user, `authSource`, cơ chế auth và secret version; code `18` thường thuộc lớp này.
8. **Kiểm tra authorization:** role đúng collection/command, database do `MongoDatabaseFactory` chọn; code `13` thường thuộc lớp này.
9. **Kiểm tra Spring Data:** bean `MongoTemplate`, repository và reactive client có dùng cùng settings được dự định không.
10. **Lặp lại phép thử nhỏ sau khi sửa:** `ping`, `find` và thao tác nghiệp vụ tối thiểu được phép. Xác nhận không mở rộng quyền ngoài nhu cầu.

### Tình huống A: thông báo AuthenticationFailed

```text
URI: mongodb://orders_app:<encoded-password>@mongo.internal:27017/orders?tls=true
User được tạo ở: admin
Kết quả: AuthenticationFailed (code 18)
```

Sửa URI để nêu rõ `authSource=admin`:

```text
mongodb://orders_app:<encoded-password>@mongo.internal:27017/orders?authSource=admin&tls=true
```

Sau sửa, kiểm tra thao tác `find` trong `orders`. Nếu `ping` được nhưng `find` trả code `13`, không tiếp tục thay `authSource`; hãy kiểm tra role trên namespace.

### Tình huống B: handshake thất bại

```text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
```

Xác minh CA và intermediate certificate trong JVM truststore, tên host với SAN và deployment TLS. Không đặt tùy chọn bỏ qua xác thực chứng chỉ để “chữa nhanh” lỗi production.

### Tình huống C: SRV chỉ lỗi trong Kubernetes

Tra `dig SRV _mongodb._tcp.cluster.example.net` trên laptop có kết quả, nhưng trong pod không có. Kiểm tra CoreDNS, DNS policy của pod, private zone, network policy và khả năng truy cập các target host/port. Việc đổi MongoDB password trong tình huống này không giải quyết được DNS.

### Tình huống D: đọc được nhưng ghi không được

```text
db.orders.find(...): success
db.orders.insertOne(...): not authorized (code 13)
```

Authentication đã có thể thành công; cần kiểm tra quyền `insert` trên `orders`. Không cấp quyền quản trị toàn cụm để thử. Nếu account chỉ dành cho báo cáo, việc không được ghi có thể hoàn toàn đúng theo thiết kế.

## 11. Kiểm thử để phát hiện lỗi cấu hình sớm

| Kịch bản kiểm thử | Hành vi mong đợi |
| --- | --- |
| URI sai scheme/option | Fail có thông tin cấu hình không hợp lệ |
| Password chứa `@`/`:` | Hoạt động nếu percent-encode đúng |
| DNS SRV không hoạt động | Lỗi resolver/SRV rõ ràng; không kết luận sai password |
| TCP bị firewall chặn | Timeout/socket error có thể theo dõi |
| JVM không trust CA | TLS bị từ chối; không bypass certificate validation |
| User ở `admin`, URI xác thực ở `orders` | Authentication fail nếu user không tồn tại ở `orders` |
| User có `read` nhưng không có `insert` | `find` thành công, ghi bị từ chối |
| `MongoTemplate` trỏ nhầm database | Test truy vấn đúng collection phát hiện mismatch |
| Reactive pipeline không được subscribe | Chưa có request MongoDB thật |
| Replica set mất primary ngắn hạn | Có cơ chế xử lý/retry phù hợp, không báo sai thành lỗi password |

Với lỗi tạm thời như failover hoặc gián đoạn mạng ngắn, có thể cân nhắc retry có **giới hạn, backoff và tính idempotent**. Không retry vô hạn lỗi URI, TLS trust, code `18` hoặc code `13` vì đây thường là lỗi cấu hình hoặc phân quyền.

Với thao tác ghi, đánh giá thêm retryable writes, transaction semantics và nguy cơ thao tác đã được server thực thi nhưng client chưa nhận phản hồi. Không tự động gọi lại toàn bộ nghiệp vụ chỉ vì thấy timeout.

## 12. Bảo mật trong chẩn đoán và vận hành

Một quá trình điều tra thành công vẫn phải giữ an toàn dữ liệu:

- Không đưa mật khẩu, connection string đầy đủ, token hoặc private key vào log, ticket hay command history.
- Không tắt TLS verification, hostname validation hoặc mở firewall toàn mạng để vượt qua lỗi.
- Không cấp role `root` để thử truy vấn; dùng account chỉ có quyền cần thiết.
- Khi cần log driver, giới hạn mức log, thời hạn thu thập và người được xem.
- Không ghi document/PII vào log của health check; chỉ ghi kết quả thành công/thất bại và mã lỗi phù hợp.
- Không dùng dữ liệu thật hoặc thao tác ghi ngẫu nhiên vào production collection để kiểm tra.
- Sau khi sửa, xác minh đúng database/tenant, quyền truy cập và thời gian đáp ứng thực tế.

Trong hệ thống nhiều database/tenant, `authSource` có thể chung nhưng database và role cho từng tenant khác nhau. Điều tra cần bắt đầu từ tenant đã được xác thực và namespace đang được query, tránh kết luận từ một phép thử với tenant khác.

## 13. Bài tập tự kiểm tra

1. App dùng `mongodb://user:pass@host/orders` nhưng user được tạo trong `admin`. Hãy nêu phần URI cần bổ sung và lý do.
2. `Resolve-DnsName` trả kết quả SRV hợp lệ, nhưng không kết nối được. Cần kiểm tra gì với target hostname/port?
3. Phân biệt `Connection refused`, `SSLHandshakeException` và `AuthenticationFailed` theo lớp lỗi.
4. Vì sao `ping` thành công vẫn có thể bị `Unauthorized` khi gọi `MongoTemplate.save(...)`?
5. Tại sao tăng `serverSelectionTimeoutMS` không sửa được hostname sai hoặc CA không được trust?
6. Đối với `ReactiveMongoTemplate`, tạo một `Mono` mà không subscribe có xác minh kết nối chưa?
7. Trường hợp role `read` phù hợp nghiệp vụ nhưng update bị chặn, có nên đổi sang `root` không?
8. Vì sao cần kiểm tra bean `MongoClient`/`MongoDatabaseFactory` thực tế thay vì chỉ nhìn vào application properties?

## Ghi nhớ

- **URI** xác định seed host, database và tùy chọn; **`authSource`** xác định nơi MongoDB kiểm tra danh tính user.
- **DNS → TCP → TLS → topology → authentication → authorization** là các lớp cần chẩn đoán riêng.
- **Code 18** thường gắn với lỗi xác thực; **code 13** thường là thiếu quyền command/namespace.
- `MongoClient` được tạo chưa chứng minh kết nối hoạt động; **`ping`** cũng chưa chứng minh quyền đọc/ghi.
- `MongoTemplate` và repository cần dùng **đúng client, database và quyền**; reactive client có cấu hình/đường thực thi riêng.
- Đọc **cause chain**, error code và cluster description trước khi đổi timeout, role hoặc URI.
- Chỉ sửa cấu hình tối thiểu cần thiết, giữ bí mật thông tin kết nối và luôn kiểm thử lại thao tác nghiệp vụ thực tế.

Trong Spring Data MongoDB, chẩn đoán có hệ thống giúp giải quyết sự cố kết nối nhanh hơn, ngăn sửa nhầm phân quyền hoặc vô hiệu hóa bảo mật, đồng thời tạo cơ sở cho logging, monitoring và kiểm thử vận hành đáng tin cậy.

