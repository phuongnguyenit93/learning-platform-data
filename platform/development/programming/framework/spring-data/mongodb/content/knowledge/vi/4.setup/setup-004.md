# Chuỗi kết nối, tên database, `authSource` và tài khoản ứng dụng

> **Chương:** Khởi tạo  
> **Phạm vi:** MongoDB và Spring Data MongoDB (`MongoTemplate`, repository, reactive).  
> **Mục tiêu:** Hiểu URI kết nối, phân biệt database ứng dụng với database xác thực, tạo tài khoản có quyền phù hợp, cấu hình ứng dụng theo phiên bản Spring Boot và tự chẩn đoán lỗi kết nối phổ biến.

## 1. Một ứng dụng cần những thông tin nào để kết nối MongoDB?

Ứng dụng Spring Data MongoDB kết nối tới MongoDB qua **MongoDB Java Driver**. Phía ứng dụng, các thành phần `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` hoặc repository sử dụng cùng thông tin kết nối để chọn máy chủ, xác thực và truy cập dữ liệu.

Một cấu hình tối thiểu thường cần:

1. **Địa chỉ máy chủ**: hostname/IP và cổng MongoDB hoặc địa chỉ cluster.
2. **Tên database nghiệp vụ**: nơi ứng dụng đọc và ghi các collection.
3. **Thông tin xác thực**: tên người dùng, mật khẩu hoặc cơ chế khác.
4. **Database xác thực** (`authSource`): nơi MongoDB tra cứu danh tính của tài khoản khi dùng cơ chế xác thực tương ứng.
5. **Tùy chọn kết nối**: TLS, replica set, timeout, write concern… tùy môi trường.

Ví dụ URI cho môi trường thực hành có bật xác thực:

~~~text
mongodb://inventory_app:<PASSWORD_DA_MA_HOA_URI>@127.0.0.1:27017/inventory_db?authSource=admin
~~~

Trong URI này, `inventory_db` là database **ứng dụng thao tác**, còn `admin` là database **xác thực** của tài khoản `inventory_app`. Hai database có thể giống hoặc khác nhau. Giá trị trong cặp dấu `<...>` là chỗ điền, **không phải một mật khẩu có thể dùng ngay**.

## 2. Giải mã chuỗi kết nối MongoDB

### 2.1. URI dạng chuẩn: `mongodb://`

~~~text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/[database][?option1=value1&option2=value2]
~~~

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `mongodb://` | Dùng danh sách host/cổng khai báo trực tiếp | `mongodb://` |
| `username:password@` | Thông tin tài khoản; cần mã hóa ký tự đặc biệt trong giá trị | `inventory_app:abc%40123@` |
| `host:port` | Địa chỉ MongoDB có thể truy cập từ ứng dụng | `127.0.0.1:27017` |
| `/database` | Database mặc định cho các thao tác của ứng dụng | `/inventory_db` |
| `?authSource=...` | Database dùng để kiểm tra tài khoản | `?authSource=admin` |
| `&tls=true` | Yêu cầu kênh kết nối TLS | `&tls=true` |
| `&replicaSet=...` | Tên replica set cần kết nối | `&replicaSet=rs0` |

Nếu không khai báo cổng trong URI chuẩn, cổng mặc định thường là **27017**. Các host trong URI phải có ý nghĩa đối với môi trường chạy ứng dụng: `localhost` trong container Docker là **container đó**, không tự động là máy tính chạy Docker hoặc container MongoDB khác.

Ba ví dụ có mục đích khác nhau:

~~~text
# Máy local chưa bật xác thực: chỉ phù hợp môi trường thử nghiệm cô lập.
mongodb://127.0.0.1:27017/inventory_db

# Máy local có user được tạo trong database admin.
mongodb://inventory_app:<ENCODED_PASSWORD>@127.0.0.1:27017/inventory_db?authSource=admin

# Replica set: khai báo các host và yêu cầu TLS khi kết nối qua mạng.
mongodb://inventory_app:<ENCODED_PASSWORD>@db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/inventory_db?replicaSet=rs0&authSource=admin&tls=true
~~~

Các hostname có hậu tố `example.net` chỉ mang tính minh họa. Trong production, cấu hình hostname thực tế, tài khoản riêng, TLS và các quy tắc mạng theo hạ tầng đã cấp.

### 2.2. URI dạng DNS seed list: `mongodb+srv://`

~~~text
mongodb+srv://inventory_app:<ENCODED_PASSWORD>@cluster.example.net/inventory_db?authSource=admin&retryWrites=true&w=majority
~~~

`mongodb+srv` tra cứu bản ghi DNS SRV/TXT để tìm các node và tùy chọn kết nối; ứng dụng thường chỉ cần một hostname của cluster, không ghi danh sách cổng. Driver MongoDB mặc định bật **TLS** khi dùng SRV, trừ khi cấu hình thay đổi điều này. Định dạng này phổ biến trong dịch vụ MongoDB quản lý như Atlas.

Lưu ý khi dùng `mongodb+srv`:

- Host trong URI là tên DNS có bản ghi SRV phù hợp, không phải địa chỉ IP bất kỳ; thường không khai báo cổng ngay sau hostname SRV.
- Phải có DNS và đường mạng cho phép phân giải hostname, truy cập các node của cluster.
- TLS vẫn cần chứng chỉ tin cậy và hostname phù hợp; không vô hiệu hóa kiểm tra chứng chỉ để xử lý nhanh lỗi cấu hình.
- Tùy chọn được cấp bởi nhà cung cấp, bao gồm `authSource`, nên đối chiếu với nguồn tạo user và cấu hình thực tế.

### 2.3. Mã hóa tên người dùng và mật khẩu trong URI

Các ký tự dành riêng trong URI có thể làm driver hiểu sai ranh giới giữa username, password, host và query parameters. Khi nhúng credentials vào URI, **percent-encode từng giá trị username và password**, không mã hóa cả URI.

| Ký tự gốc trong password | Biểu diễn percent-encoded |
| --- | --- |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `$` | `%24` |
| `%` | `%25` |

Ví dụ password thực `Abc@123` phải xuất hiện dưới dạng `Abc%40123` trong URI:

~~~text
mongodb://inventory_app:Abc%40123@127.0.0.1:27017/inventory_db?authSource=admin
~~~

Đây là mật khẩu **giả định để giải thích cú pháp**, không dùng trong triển khai thật. Percent-encoding chỉ đảm bảo URI được phân tích đúng; **không phải mã hóa bảo mật**. Bảo vệ password bằng secret manager, quyền truy cập cấu hình và TLS khi truyền qua mạng.

## 3. Phân biệt database ứng dụng và `authSource`

Hai câu hỏi cần trả lời độc lập:

- **Dữ liệu nằm ở đâu?** → Database nghiệp vụ, thường là `inventory_db` trong đường dẫn URI.
- **Tài khoản được tạo ở đâu?** → Authentication database, được chọn bởi `authSource` hoặc mặc định theo quy tắc URI.

Với xác thực username/password kiểu SCRAM, nếu không ghi `authSource`, MongoDB dùng database trong đường dẫn URI (`defaultauthdb`) để xác thực; nếu đường dẫn không khai báo database thì mặc định dùng `admin`. Viết `authSource` rõ ràng giúp giảm nhầm lẫn khi hai database khác nhau.

| URI (rút gọn) | Database dùng cho dữ liệu | Database dùng xác thực |
| --- | --- | --- |
| `.../inventory_db?authSource=admin` | `inventory_db` | `admin` |
| `.../inventory_db?authSource=inventory_db` | `inventory_db` | `inventory_db` |
| `.../inventory_db` | `inventory_db` | `inventory_db` (nếu không có giá trị khác từ cấu hình) |
| `.../?authSource=admin` | Không xác định từ đường dẫn; ứng dụng cần chọn rõ | `admin` |

**Tình huống A:** Quản trị viên tạo user `inventory_app` trên database `admin` và cấp vai trò `readWrite` cho `inventory_db`. Khi kết nối, ứng dụng phải chỉ định `authSource=admin`; các thao tác đọc ghi vẫn đi vào `inventory_db`.

**Tình huống B:** Quản trị viên tạo user `inventory_app` ngay trong `inventory_db`, với quyền đọc ghi trên `inventory_db`. Khi đó, có thể dùng `authSource=inventory_db` hoặc bỏ `authSource` trong URI có đường dẫn `/inventory_db`.

**Không đánh đồng xác thực và phân quyền:** đăng nhập được chưa có nghĩa có quyền `find`, `insert` hay `createIndex` tại database nghiệp vụ. Tài khoản có danh tính hợp lệ vẫn có thể nhận lỗi `not authorized` khi thiếu vai trò cần thiết.

## 4. Tạo tài khoản ứng dụng theo nguyên tắc quyền tối thiểu

Với MongoDB tự quản lý và xác thực đã được cấu hình, quản trị viên có thể cấp user riêng cho ứng dụng. Ví dụ dưới đây dành cho người **đã có quyền quản trị** trên MongoDB; ứng dụng không tự chạy `createUser()` mỗi lần khởi động.

### 4.1. User được tạo ở `admin`, chỉ được ghi vào `inventory_db`

Đăng nhập bằng tài khoản quản trị qua `mongosh`, sau đó:

~~~javascript
// Dùng quyền quản trị viên để tạo tài khoản nghiệp vụ.
use admin

db.createUser({
  user: "inventory_app",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "inventory_db" }
  ]
});
~~~

Giải thích:

- `use admin` xác định database **nơi user được tạo**.
- `passwordPrompt()` yêu cầu nhập password, giúp tránh viết mật khẩu trực tiếp vào câu lệnh hoặc lịch sử lệnh.
- `readWrite` chỉ cấp quyền đọc/ghi phù hợp cho `inventory_db`. Ứng dụng không cần `root`, `userAdminAnyDatabase` hoặc `readWriteAnyDatabase`.
- Muốn tài khoản chỉ đọc báo cáo, cân nhắc role `read` trên đúng database cần thiết.

Để kết nối với user vừa tạo, URI ứng dụng có dạng:

~~~text
mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/inventory_db?authSource=admin&tls=true
~~~

Ví dụ `db.createUser()` này áp dụng cho **MongoDB self-managed**. Với **MongoDB Atlas**, tài khoản database được quản lý qua giao diện hoặc API quản trị Atlas; thao tác `db.createUser()` không được hỗ trợ trực tiếp trên cluster Atlas. Vì vậy hãy tạo database user và gán role từ hệ thống quản trị của nhà cung cấp, sau đó dùng URI do họ hướng dẫn.

### 4.2. Tạo user trực tiếp trong `inventory_db`

Nếu tổ chức muốn đặt danh tính ứng dụng ngay tại database nghiệp vụ:

~~~javascript
use inventory_db

db.createUser({
  user: "inventory_app_local",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "inventory_db" }
  ]
});
~~~

URI tương ứng:

~~~text
mongodb://inventory_app_local:<ENCODED_PASSWORD>@127.0.0.1:27017/inventory_db?authSource=inventory_db
~~~

Không tạo hai user trùng mục đích trên cả `admin` và `inventory_db` nếu chưa có yêu cầu rõ. Trong MongoDB, cùng một username nhưng ở hai authentication databases khác nhau là **hai danh tính khác nhau**.

### 4.3. Quy tắc sử dụng credentials trong ứng dụng

- Mỗi service/môi trường nên có user riêng để thu hồi, đổi mật khẩu và truy vết quyền mà không ảnh hưởng hệ thống khác.
- Không nhúng password thật trong code, `application.yml` commit lên Git, tài liệu hoặc log. Dùng biến môi trường do hệ thống triển khai cấp, secrets của container/orchestrator hoặc secret manager.
- Không gửi connection URI chứa password vào issue, màn hình chia sẻ hoặc báo cáo lỗi. Khi ghi log chỉ đưa thông tin **đã che credentials**.
- Bật TLS cho kết nối qua mạng; percent-encoding không bảo vệ thông tin khi truyền.
- Đặt chính sách đổi và thu hồi credentials; sau khi cấp quyền, kiểm tra bằng tài khoản **ứng dụng** thực tế thay vì tài khoản quản trị.

## 5. Cấu hình trong Spring Boot

Spring Data MongoDB cung cấp `MongoTemplate` và repository trên một `MongoDatabaseFactory`. Với Spring Boot và starter MongoDB phù hợp, thông thường chỉ cần truyền URI; Boot cấu hình `MongoClient` và các thành phần cần thiết.

**Lưu ý theo phiên bản Spring Boot:**

| Phiên bản | Thuộc tính URI | Biến môi trường tương đương cho cấu hình trực tiếp |
| --- | --- | --- |
| Spring Boot **3.x** | `spring.data.mongodb.uri` | `SPRING_DATA_MONGODB_URI` |
| Spring Boot **4.x** | `spring.mongodb.uri` | `SPRING_MONGODB_URI` |

Spring Boot 4 đã đổi tiền tố của nhiều thuộc tính kết nối MongoDB từ `spring.data.mongodb.*` sang `spring.mongodb.*`; một số thuộc tính **riêng của Spring Data** như `spring.data.mongodb.auto-index-creation` vẫn giữ tiền tố cũ. Khi nâng cấp phải kiểm tra lại cấu hình đang được nạp, nhất là biến môi trường triển khai.

### 5.1. Spring Boot 4.x: `application.yml`

~~~yaml
spring:
  mongodb:
    # MONGODB_URI do môi trường chạy hoặc secret manager cung cấp.
    uri: ${MONGODB_URI}
~~~

Ví dụ giá trị biến môi trường minh họa:

~~~text
MONGODB_URI=mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/inventory_db?authSource=admin&tls=true
~~~

Không đặt chuỗi chứa password thực trong file cấu hình version control. Hệ thống chạy ứng dụng cần cấp `MONGODB_URI` theo từng môi trường.

### 5.2. Spring Boot 3.x: `application.yml`

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Chỉ khác **đường dẫn thuộc tính Spring Boot**; cú pháp URI của MongoDB không đổi giữa hai ví dụ. Tránh khai báo đồng thời cả URI và các trường host/database/username/password rời rạc nếu không có chủ đích, vì có thể gây nhầm lẫn về nguồn cấu hình được áp dụng.

Nếu muốn dùng môi trường để ghi đè trực tiếp thuộc tính Boot, hãy dùng đúng tên ở bảng trên. Nếu ứng dụng dùng `uri: ${MONGODB_URI}` như hai ví dụ, biến `MONGODB_URI` dùng chung cho cả hai phiên bản.

### 5.3. Chọn database khi không nhúng trong URI

Cách dễ hiểu nhất là ghi trực tiếp database nghiệp vụ sau dấu `/` của URI:

~~~text
mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/inventory_db?authSource=admin&tls=true
~~~

Nếu URI không có đường dẫn database, có thể cấu hình database nghiệp vụ **tách riêng** thông qua thuộc tính `spring.mongodb.database` (Boot 4.x) hoặc `spring.data.mongodb.database` (Boot 3.x), tùy phiên bản:

~~~yaml
# Ví dụ Boot 4.x - chỉ minh họa kiểu cấu hình tách database.
spring:
  mongodb:
    uri: ${MONGODB_SERVER_URI}
    database: inventory_db
~~~

Giá trị `MONGODB_SERVER_URI` cần có authentication database phù hợp, chẳng hạn `mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/?authSource=admin&tls=true`. Khi đã có database trong URI, hãy chọn **một nguồn cấu hình nhất quán** để tránh việc người vận hành hiểu nhầm database nào đang được dùng.

### 5.4. Kiểm tra kết nối bằng `MongoTemplate`

Ví dụ service dùng API đồng bộ; các import thuộc Spring Data MongoDB và MongoDB BSON:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class MongoConnectionCheck {
    private final MongoTemplate mongoTemplate;

    public MongoConnectionCheck(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean canReachServer() {
        Document result = mongoTemplate.executeCommand(new Document("ping", 1));
        return result.getDouble("ok") == 1.0;
    }
}
~~~

Lệnh `ping` kiểm tra đường kết nối đến máy chủ; **không chứng minh** user có đủ quyền đọc/ghi collection nghiệp vụ. Để xác nhận phân quyền, hãy thử `find`/`insert`/`delete` trên một collection thử nghiệm trong `inventory_db` với tài khoản ứng dụng, sau đó dọn dữ liệu thử.

`MongoRepository` cũng sử dụng cấu hình `MongoClient`/database được Boot cung cấp; repository có thể trỏ đến collection theo `@Document(collection = "...")`. Khi cần nhiều MongoDB databases hoặc nhiều cụm trong cùng ứng dụng, phải khai báo rõ các `MongoDatabaseFactory`, `MongoTemplate` và repository tương ứng; đây là cấu hình nâng cao hơn một kết nối mặc định.

### 5.5. Reactive access

Với dependency Spring Data MongoDB Reactive, `ReactiveMongoTemplate` và `ReactiveMongoRepository` sử dụng driver reactive và trả về `Mono` / `Flux`. Chuỗi URI, `authSource` và các nguyên tắc bảo mật **vẫn giống nhau**; khác biệt nằm ở cách thực thi không đồng bộ.

~~~java
import org.bson.Document;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

// Trong một component có sẵn biến reactiveMongoTemplate:
Mono<Boolean> reachable = reactiveMongoTemplate
    .executeCommand(new Document("ping", 1))
    .map(result -> result.getDouble("ok") == 1.0);
~~~

Không gọi `block()` trên event loop của luồng xử lý reactive. Việc ứng dụng được kết nối hay không chỉ được xác minh khi publisher thực sự được **subscribe** trong một chuỗi reactive.

## 6. Xác minh cấu hình bằng `mongosh`

Khi cần khoanh vùng lỗi, hãy kiểm tra trực tiếp bằng `mongosh` từ **máy/container có cùng đường mạng** với ứng dụng. Để tránh lộ password trong tham số dòng lệnh, chỉ định URI không chứa credentials và dùng tùy chọn nhập password:

~~~bash
mongosh "mongodb://db.example.net:27017/inventory_db?authSource=admin&tls=true" --username inventory_app --password
~~~

Lệnh trên giả định server đích có TLS hợp lệ và user đã được tạo tại `admin`. `mongosh` sẽ yêu cầu nhập mật khẩu qua prompt.

Sau khi đăng nhập, thực hiện kiểm tra trên database nghiệp vụ:

~~~javascript
// Database hiện được chọn.
db.getName(); // "inventory_db"

// Kiểm tra server nhận kết nối.
db.runCommand({ ping: 1 });

// Kiểm tra server nhận danh tính nào.
db.runCommand({ connectionStatus: 1 }).authInfo.authenticatedUsers;

// Chỉ dùng collection riêng cho thử nghiệm để tránh tác động dữ liệu thật.
db.setup004_connection_probe.insertOne({ _id: "setup004-smoke", ok: true });
db.setup004_connection_probe.findOne({ _id: "setup004-smoke" });
db.setup004_connection_probe.deleteOne({ _id: "setup004-smoke" });
~~~

Các thao tác trên cần quyền phù hợp trong `inventory_db`; `ping` thành công nhưng `insertOne` thất bại vì `not authorized` là tín hiệu thiếu quyền, không phải lỗi mạng. Sau khi xóa document thử, collection kiểm tra có thể vẫn tồn tại; chỉ drop collection khi được phép và chắc chắn đó là collection thử riêng.

Trong thực tế, thứ tự khắc phục hợp lý là **xác minh URI và network → xác thực user → xác nhận database nghiệp vụ → kiểm tra quyền trên collection → kiểm tra Spring Boot có nạp đúng thuộc tính**.

## 7. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Hướng xử lý |
| --- | --- | --- |
| `Authentication failed`, lỗi mã 18 / `MongoSecurityException` | Sai user/password, sai `authSource`, password chứa ký tự đặc biệt chưa percent-encode | Xác nhận database nơi user được tạo, thử đăng nhập bằng `mongosh`, mã hóa đúng phần password |
| `not authorized on inventory_db` | Đăng nhập được nhưng role chưa có trên database nghiệp vụ | Kiểm tra role được cấp; bổ sung quyền tối thiểu qua quản trị viên |
| Đọc dữ liệu thấy rỗng dù kết nối thành công | URI trỏ sai database hoặc collection, hay môi trường đang dùng database test | Xem `/database` trong URI; đối chiếu `MongoTemplate`, `@Document` và cấu hình profile |
| `MongoTimeoutException` / server selection timeout | Không tới được host/cổng, firewall, replica set quảng bá hostname không truy cập được | Kiểm tra DNS, mạng/container, port, IP allowlist, địa chỉ của các node |
| Lỗi phân giải `mongodb+srv` | Bản ghi DNS SRV/TXT không hợp lệ hoặc DNS bị chặn | Kiểm tra hostname và DNS từ môi trường chạy ứng dụng |
| SSL handshake / lỗi certificate | TLS chưa bật, không tin CA hoặc hostname trong chứng chỉ không khớp | Kiểm tra `tls=true`, truststore/SSL bundle và chứng chỉ máy chủ |
| MongoDB chạy được bằng `mongosh` nhưng Boot vẫn kết nối nhầm máy | Sai tên property khi đổi Boot 3 ↔ Boot 4, profile/env không được nạp, tạo `MongoClient` tùy biến ghi đè | Soát đúng `spring.data.mongodb.uri` hoặc `spring.mongodb.uri`; kiểm tra cấu hình thực thi đã che mật khẩu |
| URI bị phân tích sai ở dấu `@`, `#`, `?` | Credentials chưa percent-encode | Encode riêng username/password trước khi ghép URI |
| Kết nối tới `localhost` thất bại trong container | `localhost` tham chiếu chính container ứng dụng | Dùng hostname dịch vụ MongoDB trên mạng container hoặc hostname phù hợp hạ tầng |

Không công khai nguyên văn URI trong stack trace, ticket hoặc screenshot khi URI chứa thông tin xác thực. Nếu ứng dụng tạo `MongoClient` hoặc `MongoClientSettings` thủ công, hãy kiểm tra nó có ghi đè auto-configuration của Spring Boot hay không.

## 8. Quy trình thiết lập thực tế

Giả sử cần triển khai dịch vụ quản lý tồn kho dựa trên Spring Data MongoDB:

1. **Chọn MongoDB endpoint** theo môi trường local/staging/production; bật TLS và kiểm tra mạng kết nối.
2. **Chọn database nghiệp vụ** là `inventory_db` và quy ước tên collection.
3. **Tạo user riêng** `inventory_app` tại `admin` (hoặc vị trí xác thực được quy định) và cấp role `readWrite` chỉ cho `inventory_db`.
4. **Tạo URI** với `/inventory_db`, `authSource=admin`, password đã percent-encode và tùy chọn TLS cần thiết.
5. **Cấp URI như secret**, thiết lập `application.yml` theo Spring Boot 3.x hay 4.x tương ứng.
6. **Xác minh bằng tài khoản ứng dụng** qua `mongosh` và một thao tác CRUD kiểm soát; sau đó thử kết nối từ ứng dụng với `MongoTemplate`/repository.
7. **Theo dõi lỗi** mà không ghi password ra log. Trong production, cần kế hoạch thay credential và kiểm soát quyền truy cập secret.

Sơ đồ mối quan hệ:

~~~mermaid
flowchart LR
  A["Spring Data MongoDB<br/>MongoTemplate / Repository"] --> B["MongoClient<br/>đọc URI và TLS"]
  B --> C["MongoDB server / cluster"]
  C --> D["Xác thực user<br/>authSource = admin"]
  D --> E["Kiểm tra quyền<br/>readWrite trên inventory_db"]
  E --> F["CRUD collection<br/>trong inventory_db"]
~~~

## 9. Bài tập tự kiểm tra

**Bài 1 — Phân tích URI.** Cho URI:

~~~text
mongodb://catalog_app:Example%402026@mongo.internal:27017/catalog_db?authSource=admin&tls=true
~~~

Hãy xác định host, port, database nghiệp vụ, database xác thực, username, password trước khi percent-encode và tùy chọn bảo vệ kết nối.

**Đáp án:** host `mongo.internal`, cổng `27017`, database `catalog_db`, `authSource=admin`, username `catalog_app`, password ví dụ `Example@2026`, `tls=true`. Đây chỉ là URI minh họa; không dùng thông tin này làm credentials thực.

**Bài 2 — Chẩn đoán lỗi.** User `billing_app` được tạo trong `admin`, được cấp `readWrite` cho `billing_db`. Ứng dụng dùng:

~~~text
mongodb://billing_app:<ENCODED_PASSWORD>@mongo.internal:27017/billing_db
~~~

Vì sao có thể nhận `Authentication failed`? **Đáp án:** URI mặc định xác thực vào `billing_db`, trong khi user được tạo tại `admin`. Sửa URI thành `.../billing_db?authSource=admin`, giữ nguyên database CRUD là `billing_db`.

**Bài 3 — Kiểm tra nâng cấp.** Ứng dụng chuyển từ Boot 3 sang Boot 4, biến triển khai hiện có là `SPRING_DATA_MONGODB_URI` nhưng không còn cấu hình `uri: ${MONGODB_URI}` trong YAML. Hãy xác định thay đổi cần thiết. **Đáp án:** dùng thuộc tính mới `spring.mongodb.uri` hoặc biến cấu hình trực tiếp `SPRING_MONGODB_URI`; kiểm tra các cấu hình MongoDB khác có tên thay đổi khi nâng cấp.

## Tài liệu tham khảo

- [MongoDB Manual — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string-formats/): cú pháp `mongodb://`, `mongodb+srv://`, cấu phần URI, database xác thực mặc định.
- [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): `authSource`, TLS, replica set và các tham số khác.
- [MongoDB Manual — `db.createUser()`](https://www.mongodb.com/docs/manual/reference/method/db.createUser/): cách tạo user và gán role trên MongoDB tự quản lý.
- [Spring Boot 3.4 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.4/reference/data/nosql.html): `spring.data.mongodb.uri` và cấu hình MongoDB qua Spring Boot 3.
- [Spring Boot 4 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/4.0/reference/data/nosql.html): `spring.mongodb.uri` và cơ chế auto-configuration.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): các property MongoDB đổi tên khi nâng cấp lên Boot 4.
