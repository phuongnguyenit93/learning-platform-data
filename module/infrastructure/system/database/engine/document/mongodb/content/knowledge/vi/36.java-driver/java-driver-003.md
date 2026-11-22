# Cấu hình URI, xác thực, TLS và lựa chọn database, collection trong MongoDB Java Driver

Một ứng dụng Java muốn đọc đơn hàng từ MongoDB phải trả lời nhiều câu hỏi trước khi chạy lệnh `find()`: kết nối tới máy nào, có phải replica set hay Atlas cluster, tài khoản được xác thực ở database nào, đường truyền có TLS hay không, CA nào được tin cậy, và ứng dụng sẽ chọn database/collection nào để thao tác. Sai một tham số có thể gây lỗi kết nối; nguy hiểm hơn, dùng sai database hoặc bỏ xác minh chứng chỉ có thể dẫn tới thao tác trên môi trường không mong muốn hoặc làm suy yếu bảo mật.

Với **MongoDB Java Sync Driver**, chuỗi kết nối (connection URI), `MongoClientSettings` và `MongoCredential` giúp cấu hình kết nối. Sau khi tạo `MongoClient`, ứng dụng lấy `MongoDatabase` rồi `MongoCollection<T>` để đọc/ghi. Các handle này được thiết kế để tái sử dụng: không cần tạo một kết nối mạng riêng cho từng collection hoặc mỗi request HTTP.

Bài thuộc chương **Java Driver** của module *Database Engine Document MongoDB*. Nội dung tập trung vào Java Sync Driver, đồng thời giải thích sự khác biệt với các lựa chọn driver khác. Ví dụ dùng hostname, tên database và chứng chỉ **minh họa**, không đại diện cho một cụm thật. API và defaults có thể khác theo MongoDB Java Driver, JDK, MongoDB Server và Atlas version; khi áp dụng vào hệ thống thật, cần kiểm tra compatibility matrix và documentation của các phiên bản đã chọn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `mongodb://` và `mongodb+srv://`, hiểu seed hosts, replica set discovery và DNS SRV/TXT.
2. Đọc cấu trúc URI gồm hosts, database path, query options và authentication parameters.
3. Giải thích `authSource`, `authMechanism` và khác biệt giữa authentication database với application database.
4. Cấu hình username/password an toàn bằng `MongoCredential` mà không nhúng secret vào source code.
5. Hiểu SCRAM-SHA-256, một số cơ chế authentication khác và giới hạn hỗ trợ theo môi trường.
6. Bật TLS, xác minh CA chain, SAN/hostname và certificate validity.
7. Dùng JVM truststore hoặc một `SSLContext` có trust manager phù hợp.
8. Phân biệt TLS server authentication và mTLS/client certificate, gồm `MONGODB-X509`.
9. Tạo `MongoClient` bằng URI trực tiếp hoặc `MongoClientSettings.builder()`.
10. Hiểu connection pool, timeouts, server selection và vòng đời đối tượng client.
11. Chọn database với `getDatabase()` và collection với `getCollection()`; hiểu rằng lấy handle không tự tạo dữ liệu.
12. Sử dụng `MongoCollection<Document>`, type mapping và POJO codec theo nhu cầu.
13. Cấu hình read preference, read concern và write concern mà không nhầm với credentials.
14. Kết nối replica set hoặc Atlas đúng topology, TLS và network requirements.
15. Phân tích các lỗi `Authentication failed`, `Unauthorized`, certificate, DNS và server selection.
16. Thiết kế cấu hình nhiều môi trường, secrets, logging và kiểm thử kết nối an toàn.

## 2. Phạm vi: Java Sync Driver và các kiểu ứng dụng

MongoDB có các driver/libraries Java phục vụ nhiều mô hình:

| Lựa chọn | Đặc điểm | Ví dụ nhu cầu |
|---|---|---|
| **MongoDB Java Sync Driver** | API blocking, trả kết quả trực tiếp hoặc cursor | Java service đồng bộ, batch job, command-line tool |
| Java Reactive Streams Driver | API nonblocking theo Reactive Streams | Ứng dụng reactive |
| Spring Data MongoDB | Abstraction repositories/templates trên driver | Ứng dụng Spring muốn dùng mapping/repositories |
| MongoDB Java Driver core | Thành phần cấp thấp của hệ sinh thái driver | Thường do driver cấp cao sử dụng |

Bài này sử dụng chủ yếu các kiểu:

~~~java
com.mongodb.client.MongoClient
com.mongodb.client.MongoDatabase
com.mongodb.client.MongoCollection
org.bson.Document
~~~

Không nhầm `com.mongodb.client.MongoClient` của Java Sync Driver với những API MongoDB Java cũ hoặc reactive client có package khác.

### 2.1. Dependency

Với Gradle, cần thư viện Java Sync Driver phiên bản phù hợp JDK và MongoDB Server đang dùng:

~~~kotlin
dependencies {
    // Thay bằng version cụ thể đã được dự án kiểm thử và khóa dependency.
    implementation("org.mongodb:mongodb-driver-sync:REPLACE_WITH_PINNED_VERSION")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>REPLACE_WITH_PINNED_VERSION</version>
</dependency>
~~~

`REPLACE_WITH_PINNED_VERSION` là placeholder, **không phải số phiên bản hợp lệ**. Dùng một release tương thích được quản lý qua dependency catalog/BOM/chính sách dự án; tránh chọn bừa phiên bản chỉ vì ví dụ trên Internet dùng nó.

### 2.2. Khi nào cần mongosh?

`mongosh` hữu ích để kiểm tra cluster, database user và TLS độc lập với Java runtime. Nhưng nếu mongosh kết nối thành công còn Java không, điều đó có thể liên quan **JVM truststore, driver version, URI parsing hoặc runtime dependencies**. Không coi một test mongosh là đủ để chứng minh cấu hình Java đúng.

## 3. Từ URI đến collection: sơ đồ kiến trúc

~~~mermaid
flowchart TD
    Config["URI + credentials + TLS policy"] --> Settings["MongoClientSettings"]
    Settings --> Client["MongoClient: topology + connection pools"]
    Client --> DB1["MongoDatabase: shop"]
    Client --> DB2["MongoDatabase: audit"]
    DB1 --> C1["MongoCollection<Document>: orders"]
    DB1 --> C2["MongoCollection<Document>: customers"]
    DB2 --> C3["MongoCollection<Document>: events"]
    C1 --> Query["find / insertOne / aggregate"]
    C2 --> Query
    C3 --> Query
~~~

Một `MongoClient` quản lý quá trình chọn server và các **connection pools**. Từ nó có thể tạo nhiều handle `MongoDatabase` và `MongoCollection` để thao tác nhiều namespace.

### 3.1. Namespace MongoDB

Một collection được xác định bằng cặp:

~~~text
<database>.<collection>

shop.orders
shop.customers
audit.events
~~~

`shop.orders` và `audit.orders` là hai collections khác nhau. URI chọn database mặc định hoặc authentication database không làm mọi lệnh tự động chạy ở collection đúng; code vẫn phải chọn rõ ràng.

### 3.2. Kết nối thực tế xảy ra khi nào?

Tạo `MongoClient` có thể khởi tạo monitor/pool/topology management nhưng **không bảo đảm** đã có một lệnh đến MongoDB thành công. Lấy `getDatabase()`/`getCollection()` chỉ tạo handle. Để kiểm tra khả năng kết nối và authentication, cần thực hiện lệnh như `ping`.

## 4. Cấu trúc cơ bản của connection URI

MongoDB dùng hai dạng chính:

~~~text
mongodb://[username:password@]host1[:port1][,host2[:port2]...]/[defaultDb][?options]

mongodb+srv://[username:password@]dnsServiceName/[defaultDb][?options]
~~~

Dấu ngoặc vuông trong mô tả biểu thị thành phần tùy chọn, **không phải toàn bộ chuỗi phải bao gồm các dấu đó**. Với URI thực, IPv6 literals cần cú pháp ngoặc vuông của URI riêng.

Các phần:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Scheme | Kết nối seed hosts trực tiếp hay khám phá DNS SRV | `mongodb://`, `mongodb+srv://` |
| Host/seed list | Điểm bắt đầu khám phá cluster | `mongo1.db.internal:27017` |
| Database path | Database mặc định / có thể ảnh hưởng authSource default | `/shop` |
| Auth credentials | Database user nếu đặt trong URI | `username:password@` |
| Query options | TLS, replica set, authSource, timeouts... | `?tls=true&replicaSet=rs0` |

### 4.1. URI một MongoDB standalone trong lab

~~~text
mongodb://127.0.0.1:27017/
~~~

Chỉ phù hợp khi MongoDB lab đang lắng nghe ở localhost và security policy cho phép. Không mặc định dùng plaintext cho production. Với TLS có certificate cho `mongo1.db.internal`:

~~~text
mongodb://mongo1.db.internal:27017/?tls=true
~~~

### 4.2. URI có database path

~~~text
mongodb://mongo1.db.internal:27017/shop?tls=true
~~~

`shop` ở đây là database trong connection string; khi dùng Sync Driver, ứng dụng vẫn nên gọi `client.getDatabase("shop")` rõ ràng. Đừng nhầm path này với tên collection; URI không tự chọn `shop.orders`.

### 4.3. URI có nhiều options

~~~text
mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/shop?replicaSet=rs0&authSource=admin&tls=true&appName=order-service
~~~

Ứng dụng nhận seed host list, replica set name, authSource và các options. Hệ thống phải có DNS/network tới **mọi advertised member** mà driver khám phá, không chỉ host đầu.

## 5. `mongodb://` với replica set

Khi kết nối replica set, nên có nhiều seed hosts để giảm phụ thuộc một member:

~~~text
mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/?replicaSet=rs0&tls=true
~~~

Driver sử dụng seed hosts để khám phá topology, theo dõi primary/secondaries và chọn node dựa trên read preference, health và server selection rules.

### 5.1. Seed host không phải danh sách node cố định

Driver có thể nhận thông tin từ `hello`/topology discovery và kết nối các hostname do replica set công bố. Vì vậy:

- DNS của advertised host phải phân giải được từ nơi chạy Java.
- Network policy phải cho phép kết nối.
- Certificate SAN phải khớp hostname driver thực sự dùng.
- `replicaSet=rs0` phải đúng tên replica set.

Một URI seed qua hostname trung gian thành công lúc đầu không bảo đảm failover ổn nếu các advertised hosts không thể truy cập.

### 5.2. `directConnection=true`

`directConnection=true` yêu cầu driver kết nối trực tiếp một server thay vì discovery topology thông thường trong các tình huống được hỗ trợ. Nó hữu ích cho một số bài test hoặc topology đặc thù, nhưng **không phải cách chuẩn để vô hiệu hóa replica set failover** cho ứng dụng production.

~~~text
mongodb://mongo1.db.internal:27017/?directConnection=true&tls=true
~~~

Không dùng direct mode để che lỗi DNS/advertised host của replica set. Khi cần automatic primary discovery và failover, cấu hình replica set đúng.

### 5.3. Không đưa port sau service DNS của SRV

`mongodb+srv://` được thiết kế với một DNS service hostname, không viết danh sách host:port như `mongodb://`. Cần phân biệt rõ hai schemes.

## 6. `mongodb+srv://` và DNS SRV/TXT

Với DNS SRV connection:

~~~text
mongodb+srv://cluster0.example.mongodb.net/?retryWrites=true&w=majority
~~~

Driver tra cứu DNS SRV để biết các hosts/ports theo bản ghi dịch vụ, và có thể đọc TXT records chứa options được hỗ trợ. Đây là cách kết nối phổ biến với Atlas, nhưng có thể dùng ở deployment khác nếu DNS và driver support được cấu hình đúng.

### 6.1. TLS mặc định với SRV

`mongodb+srv://` thường **bật TLS theo mặc định** trừ khi cấu hình hợp lệ ghi đè. Với production/Atlas, nên giữ TLS và hostname verification theo yêu cầu bảo mật, không tắt TLS để vượt lỗi certificate.

### 6.2. Những rủi ro về DNS

Kết nối SRV phụ thuộc DNS resolution và bản ghi đúng. Nếu máy chạy Java không truy vấn được SRV/TXT hoặc DNS trả hostname không thể route, driver có thể fail trước khi login MongoDB.

### 6.3. Không hiểu nhầm SRV là một proxy

SRV giúp **khám phá danh sách endpoints**; nó không tự là load balancer MongoDB protocol. Driver vẫn cần xử lý topology discovery, connections và failover.

### 6.4. Copy Atlas URI có chọn lọc

Atlas thường cung cấp connection string để khởi đầu. Trước khi đặt vào production config, kiểm tra:

- Project và cluster đúng.
- Database user và auth mechanism đúng.
- TLS/CA trust.
- Đường mạng, allowlist/private endpoint.
- `retryWrites`, write concern, timeouts phù hợp.
- Không có password thật nằm trong source code.

## 7. URI, secrets và ký tự đặc biệt

Một URI chứa password trực tiếp có thể xuất hiện trong source control, startup logs, crash dumps, process arguments hoặc metrics. Không đưa secrets thật vào ví dụ copy/paste hay exception message.

### 7.1. Phần nào cần percent-encode?

Nếu username/password được đặt trong URI, các ký tự reserved như `@`, `:`, `/`, `?`, `#` và `%` có thể cần percent-encoding theo URI grammar:

| Ký tự | Percent encoding |
|---|---|
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |

Nếu password là `a@b/c` và ghi nguyên vào URI, parser có thể nhầm dấu `@` là dấu tách credentials/host và `/` là path. Tránh tự nối một URI từ nhiều giá trị nhạy cảm không được encode.

### 7.2. `URLEncoder` không phải generic URI encoder

`java.net.URLEncoder` dùng quy tắc `application/x-www-form-urlencoded` (ví dụ spaces thành dấu cộng), không đồng nghĩa percent-encoding mọi thành phần URI theo RFC 3986. Dùng cơ chế của driver hoặc một encoder đúng cho **URI userinfo component** khi thật sự cần nhúng credentials.

### 7.3. Phương án tốt hơn

Không để password trong URI. Dùng host-only URI trong cấu hình và cung cấp `MongoCredential` bằng secrets manager/secret injection có kiểm soát. Secrets qua environment variables cũng cần bảo vệ vì có thể bị đọc bởi process/user có quyền; tốt nhất dùng nền tảng secret management của tổ chức.

## 8. Authentication database và application database

**Authentication database** là nơi MongoDB tìm định danh user trong cơ chế phù hợp. **Application database** là nơi code đọc/ghi collections. Hai database này có thể khác nhau.

Ví dụ:

~~~text
Application database: shop
Authentication database: admin
MongoDB user: shopAppUser được tạo ở admin
~~~

Connection URI:

~~~text
mongodb://mongo1.db.internal:27017/shop?authSource=admin&tls=true
~~~

Trong Java:

~~~java
MongoDatabase db = client.getDatabase("shop");
MongoCollection<Document> orders = db.getCollection("orders");
~~~

Ứng dụng đăng nhập bằng user thuộc `admin` nhưng đọc dữ liệu `shop.orders` dựa trên roles được cấp.

### 8.1. `authSource` default

Với những cơ chế authentication phổ biến như SCRAM, nếu URI có database path mà không đặt `authSource`, path database có thể được dùng làm authentication database mặc định; nếu không có path thường mặc định là `admin`. Cơ chế khác như x.509 dùng `$external`. **Đặt `authSource` rõ ràng** giúp tránh lệch cấu hình giữa môi trường.

### 8.2. `getDatabase("shop")` không thay `authSource`

Nếu MongoClient đã xác thực ở `admin`, gọi `getDatabase("shop")` không khiến driver chuyển sang tìm user ở `shop`. Nó chỉ chọn namespace cho thao tác tiếp theo.

### 8.3. Authenticated không đồng nghĩa authorized

User tồn tại và password đúng nhưng thiếu quyền `read` trên `shop.orders` vẫn có thể nhận lỗi **Unauthorized**. Authentication trả lời “bạn là ai”; authorization trả lời “bạn được làm gì”.

## 9. SCRAM-SHA-256 và các authentication mechanisms

Đối với ứng dụng dùng username/password, `SCRAM-SHA-256` là cơ chế phổ biến, được hỗ trợ trong các phiên bản MongoDB hiện đại.

| Mechanism | Mục đích | Lưu ý |
|---|---|---|
| `SCRAM-SHA-256` | Username/password authentication | Ưu tiên khi deployment hỗ trợ và policy cho phép |
| `SCRAM-SHA-1` | Compatibility với cấu hình cũ | Đánh giá migration/policy |
| `MONGODB-X509` | Xác thực client certificate | Cần PKI, TLS client cert, `$external` |
| `MONGODB-AWS` | AWS IAM-based auth ở deployment hỗ trợ | Phụ thuộc runtime, phiên bản và provider |
| OIDC/enterprise mechanisms | Federated identity ở môi trường hỗ trợ | Cấu hình/roles/credential provider riêng |

Không tự suy rằng mọi mechanism khả dụng ở một MongoDB Server/Atlas tier/driver. Các cơ chế dựa trên cloud identity hoặc enterprise có policy và credential provider riêng.

### 9.1. SCRAM không thay TLS

SCRAM không phải lý do bỏ TLS. Kênh TLS bảo vệ query/results, connection metadata và các dữ liệu khác ngoài quá trình login. Dùng TLS trong production ngay cả khi authentication mechanism đã bảo vệ password theo cách riêng.

### 9.2. Chọn một nguồn credentials

Ứng dụng có thể cung cấp credentials trong URI hoặc bằng `MongoCredential`; tránh cấu hình chồng chéo khiến khó biết user/authSource cuối cùng. Tách connection topology khỏi secret là hướng dễ quản trị hơn.

## 10. Tạo MongoClient với URI cơ bản

Ví dụ tối thiểu:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class SimpleMongoConnection {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("admin");
            Document result = db.runCommand(new Document("ping", 1));
            System.out.println(result.toJson());
        }
    }
}
~~~

### 10.1. Tại sao cần `ping`?

`MongoClients.create()` tạo client object nhưng không đảm bảo kết nối MongoDB, DNS, TLS và auth đều thành công ngay tại dòng đó. `db.runCommand({ping:1})` buộc driver thực hiện server selection và một command, giúp phát hiện lỗi cấu hình sớm.

### 10.2. URI từ environment vẫn cần validation

Đừng ghi nguyên URI vào exception/log nếu nó có chứa password. Nếu giá trị thiếu, chỉ log tên biến cấu hình thiếu; nếu URI parser lỗi, redact credentials trước khi gửi error context tới hệ thống observability.

### 10.3. Chọn database cho `ping`

`admin` thường là lựa chọn cho lệnh `ping`, nhưng availability của command phụ thuộc server và privilege policy. Lệnh `ping` chủ yếu kiểm tra client có thể giao tiếp, không chứng minh mọi collection được quyền đọc/ghi.

## 11. Tạo MongoClient bằng MongoClientSettings

Khi ứng dụng cần kiểm soát pool/timeouts/auth/TLS, dùng builder:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class ConfiguredMongoClient {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        String username = System.getenv("MONGODB_USERNAME");
        char[] password = System.getenv("MONGODB_PASSWORD").toCharArray();

        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                username,
                "admin",
                password
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applicationName("order-service")
            .applyToConnectionPoolSettings(pool -> pool.maxSize(50))
            .applyToClusterSettings(cluster ->
                cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
            )
            .applyToSocketSettings(socket ->
                socket.connectTimeout(10, TimeUnit.SECONDS)
            )
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            System.out.println(
                client.getDatabase("admin")
                    .runCommand(new Document("ping", 1))
                    .toJson()
            );
        }
    }
}
~~~

Đây là ví dụ cấu hình, chưa xử lý đầy đủ trường hợp biến môi trường null, secret rotation hay lifecycle của service. Trong code production, kiểm tra biến bắt buộc trước khi gọi `toCharArray()`, tách builder vào configuration module và không log password.

### 11.1. Thứ tự áp dụng settings

`applyConnectionString` đặt những options từ URI, sau đó các setters gọi tiếp có thể ghi đè từng thiết lập tương ứng. Để dễ kiểm soát, đặt cơ chế config precedence rõ: ví dụ URI cung cấp topology/TLS, `MongoCredential` cung cấp secret, builder cung cấp pool/timeouts. Tránh cấu hình username ở URI rồi thay bằng user khác qua builder mà không có chủ đích.

### 11.2. `applicationName`

Một tên ứng dụng ngắn, ổn định giúp log/monitoring nhận diện kết nối. Không đặt user token hoặc dữ liệu nhạy cảm trong tên app.

### 11.3. Credential với char[]

`MongoCredential.createScramSha256Credential` nhận `char[]` thay vì bắt buộc một String. Có thể giảm thời gian giữ một số bản copy password ở nơi không kiểm soát, nhưng không đảm bảo mọi bản sao trong runtime được xóa. Quản lý secret lifecycle ở tầng ứng dụng và tránh in ra logs.

## 12. URI vs builder: chọn cách nào?

| Cách | Ưu điểm | Khi cần lưu ý |
|---|---|---|
| `MongoClients.create(uri)` | Ngắn, dễ dùng với config/Atlas | URI dài có thể khó quản lý secrets/options |
| `MongoClients.create(settings)` | Tách topology, auth, TLS, pool/timeouts | Cần rõ precedence, code cấu hình dài hơn |
| Framework auto-configuration | Tích hợp lifecycle/injection | Cần hiểu framework map properties vào driver ra sao |

Đối với dịch vụ có yêu cầu bảo mật cao, **URI không chứa password + credential provider + TLS config rõ ràng** thường dễ audit. Với ứng dụng nhỏ, URI lấy từ secret manager vẫn có thể dùng nếu được bảo vệ và không bị log.

### 12.1. Không tạo URI bằng nối String tùy tiện

Ví dụ anti-pattern:

~~~java
// KHÔNG khuyến khích: password chưa encode và dễ bị log.
String uri = "mongodb://" + username + ":" + password +
    "@mongo1.db.internal:27017/shop";
~~~

Nó có thể hỏng với password chứa `@`/`:`/`/` và làm credentials xuất hiện ở nhiều String copies. Cung cấp credentials qua `MongoCredential` giúp giảm rủi ro parser/encoding.

### 12.2. Không hardcode môi trường

Không viết production URI trực tiếp vào code. Tách dev/staging/prod bằng config deployment, với secret scope riêng và allowlist/cluster identifiers được review.

## 13. Các URI options thường gặp

| Option | Ví dụ | Mục đích |
|---|---|---|
| `replicaSet` | `rs0` | Xác nhận/khám phá replica set |
| `authSource` | `admin` | Database chứa user authentication |
| `authMechanism` | `SCRAM-SHA-256` | Cơ chế login |
| `tls` | `true` | Bật TLS |
| `appName` | `order-service` | Nhận diện application trong diagnostics |
| `retryWrites` | `true` | Bật retryable writes khi thao tác/topology hỗ trợ |
| `retryReads` | `true` | Retryable reads theo hỗ trợ |
| `readPreference` | `primary` | Chọn loại member cho reads |
| `w` | `majority` | Write concern |
| `readConcernLevel` | `majority` | Read concern |
| `serverSelectionTimeoutMS` | `5000` | Giới hạn chờ driver tìm server phù hợp |
| `connectTimeoutMS` | `10000` | Giới hạn thời gian thiết lập socket connection |
| `socketTimeoutMS` | `30000` | Timeout đọc socket theo driver settings |
| `maxPoolSize` | `50` | Số connection tối đa trong pool theo cấu hình |
| `minPoolSize` | `0` | Số connection tối thiểu theo cấu hình |
| `compressors` | `zstd,snappy,zlib` | Wire compression nếu hai bên hỗ trợ |
| `directConnection` | `true` | Kết nối trực tiếp endpoint trong tình huống phù hợp |

**Không sao chép mọi option vào một URI mà không đánh giá.** Timeouts, retries, read/write concern và pool phải phù hợp workload. Defaults và support thay đổi theo driver/server version.

### 13.1. URI options không thay collection selection

`authSource`, `readPreference` hoặc `tls` không chọn tên collection. Ứng dụng phải gọi `getDatabase("...").getCollection("...")`, hoặc framework mapping phù hợp.

### 13.2. Không dùng `socketTimeoutMS` để chữa index sai

Timeout tăng có thể che query chậm do COLLSCAN hoặc server overload. Phải kiểm tra query performance trước khi tăng timeout vô hạn.

## 14. Vòng đời MongoClient và connection pool

`MongoClient` là đối tượng **thread-safe** và được thiết kế để tái sử dụng. Một service thường tạo một MongoClient theo mỗi cluster/credential configuration và giữ cho tới khi ứng dụng shutdown.

~~~mermaid
flowchart TD
    Start["Application startup"] --> Load["Load config + secrets"]
    Load --> Client["Create MongoClient"]
    Client --> Ping["Run ping / readiness"]
    Ping --> Serve["Serve many HTTP requests"]
    Serve --> Reuse["Reuse MongoDatabase/MongoCollection handles"]
    Reuse --> Serve
    Serve --> Shutdown["Graceful shutdown"]
    Shutdown --> Close["Close MongoClient"]
~~~

### 14.1. Anti-pattern: client mỗi request

~~~java
// Không nên trong HTTP handler:
try (MongoClient client = MongoClients.create(uri)) {
    return client.getDatabase("shop")
        .getCollection("orders")
        .find().first();
}
~~~

Mỗi request có thể tạo pool mới, topology monitoring và TLS connections mới, làm tăng CPU/latency và số socket.

### 14.2. Lifecycle trong Spring/Jakarta services

Nếu framework tạo singleton MongoClient bean, để dependency injection quản lý lifecycle. Không tạo client thủ công ở mỗi repository hoặc mỗi transaction.

### 14.3. Nhiều clusters

Nếu dịch vụ thực sự kết nối hai MongoDB clusters với credentials/trust khác nhau, mỗi cluster thường có một MongoClient settings riêng. Không cố “chuyển cluster” bằng `getDatabase()`; method này chỉ đổi namespace **trong cluster của MongoClient**.

## 15. Pool size và server selection không phải authentication

Một số tham số hiệu năng thường gặp:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool ->
        pool.maxSize(50)
            .minSize(0)
            .maxWaitTime(2, TimeUnit.SECONDS)
    )
    .applyToClusterSettings(cluster ->
        cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
    )
    .build();
~~~

Các con số chỉ minh họa, không là recommendation cho mọi hệ thống.

### 15.1. Server selection timeout

`serverSelectionTimeoutMS` kiểm soát thời gian driver chờ server phù hợp. Nó không phải giới hạn tổng thời gian tất cả database operations. Lỗi server selection có thể bắt nguồn DNS, TLS, auth-related connection failure, replica set state hoặc network.

### 15.2. Connection timeout

`connectTimeoutMS` liên quan thiết lập socket; `socketTimeoutMS` liên quan hoạt động đọc/response socket theo semantics driver. Không coi cả hai là “query execution timeout” một cách đơn giản.

### 15.3. Max pool size

Tăng pool size quá mức có thể tạo rất nhiều connections/CPU/resource pressure mà không tăng throughput nếu bottleneck ở server/index. Đo pool wait, concurrency, thread count, CPU, DB connections và latency.

## 16. TLS là gì trong kết nối Java → MongoDB?

TLS mã hóa kết nối mạng và giúp xác minh server identity qua certificate. Với production, thường mong muốn:

1. Java driver bật TLS.
2. Server `mongod`/`mongos` có certificate hợp lệ.
3. JVM trust CA chain ký certificate.
4. Hostname kết nối khớp **Subject Alternative Name (SAN)**.
5. Certificate chưa hết hạn, có key usage/EKU phù hợp.
6. TLS protocol/cipher versions tương thích với JDK/server.

~~~mermaid
sequenceDiagram
    participant Java as Java MongoDB Driver
    participant DB as mongod / mongos
    Java->>DB: TLS handshake
    DB-->>Java: Server certificate chain
    Java->>Java: Verify trust, SAN, validity, policy
    Java->>DB: Establish encrypted channel
    Java->>DB: MongoDB authentication (SCRAM/X.509)
    DB-->>Java: Auth result
    Java->>DB: ping/find/insert
~~~

TLS không thay MongoDB RBAC. Một TLS connection đã mã hóa vẫn cần user có quyền đọc/ghi database/collection tương ứng.

### 16.1. URI bật TLS

~~~text
mongodb://mongo1.db.internal:27017/?tls=true
~~~

`mongodb://` không nên được giả định luôn bật TLS nếu không có cấu hình. `mongodb+srv://` thường bật TLS theo mặc định; vẫn cần JVM trust/certificate validation.

### 16.2. Bật TLS bằng MongoClientSettings

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSslSettings(ssl ->
        ssl.enabled(true)
           .invalidHostNameAllowed(false)
    )
    .build();
~~~

`invalidHostNameAllowed(false)` thể hiện chủ đích **không bỏ qua hostname validation**, phù hợp production. Thay đổi chi tiết builder/API theo version khi cần.

### 16.3. Không dùng trust-all SSLContext

Tạo TrustManager luôn trả “chấp nhận mọi certificate” khiến client có thể thiết lập kênh mã hóa với **server giả mạo**, làm mất phần xác minh danh tính. Sửa CA trust/SAN thay vì bypass validation.

## 17. Chứng chỉ TLS: CA, SAN, chain và thời gian

| Thành phần | Ý nghĩa |
|---|---|
| Root CA | Gốc tin cậy, cần được bảo vệ |
| Intermediate CA | Ký leaf certificate theo policy |
| Server leaf certificate | Chứng minh danh tính mongod/mongos |
| Private key | Bí mật của chủ thể sở hữu certificate |
| CA truststore | Nơi JVM tìm các CA public được tin |
| SAN | DNS/IP names mà certificate hợp lệ |
| EKU | Mục đích như `serverAuth` hoặc `clientAuth` |
| NotBefore/NotAfter | Khoảng thời gian certificate có hiệu lực |

### 17.1. SAN phải khớp URI host

Nếu URI dùng `mongo1.db.internal`, leaf certificate cần có `DNS:mongo1.db.internal`. Nếu URI dùng IP `10.20.0.5`, DNS SAN không tự thay thế IP SAN.

### 17.2. Replica set có nhiều SAN requirements

Driver có thể sau đó kết nối `mongo2.db.internal`/`mongo3.db.internal` từ topology discovery. Certificate mỗi member phải hợp lệ đối với hostname mà driver sử dụng. Test một seed host là chưa đủ.

### 17.3. Không nhầm CN-only với SAN

Hostname validation hiện đại chủ yếu dựa vào SAN. Không cấp certificate chỉ có Common Name rồi kỳ vọng mọi Java/JDK version chấp nhận.

### 17.4. Clock và expiry

JVM/server đồng hồ sai có thể gây “certificate not yet valid” hoặc expired. Dùng NTP, giám sát expiry và rotation trước hạn.

## 18. JVM default truststore

Java có truststore mặc định tùy JDK distribution/runtime. Nếu server certificate được ký bởi CA mà JVM đã tin, có thể không cần chỉ định truststore riêng.

Nếu dùng **private CA**, Java thường cần được cung cấp CA certificate qua:

- JVM truststore riêng (JKS/PKCS#12).
- Một custom `SSLContext` được xây từ TrustManagerFactory.
- Cơ chế trust management do framework/platform hỗ trợ.

Không suy ra “máy Linux đã cài CA” thì **mọi JVM** tự sử dụng CA đó; nhiều JVM có truststore riêng.

### 18.1. Java truststore bằng PKCS#12

Ví dụ properties:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/tls/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=TRUSTSTORE_SECRET
~~~

Đây là tên options để giải thích, không phải script production có secret thật. Đặt password ngay trong command-line arguments có thể lộ qua process inspection, deployment manifests hoặc logs. Dùng secret injection/configuration được tổ chức phê duyệt.

### 18.2. Truststore chứa CA, không phải MongoDB password

Truststore giúp kiểm tra **server certificate**, không phải cơ chế lưu MongoDB database user password. SCRAM credentials và CA trust là hai lớp khác nhau.

### 18.3. Không import leaf certificate tùy tiện

Trong một số trường hợp có thể pin certificate cụ thể, nhưng việc import leaf thay vì CA chain có thể gây outage khi server rotate leaf. Thường nên trust issuer CA được phê duyệt và có quy trình rotation; pinning chỉ dùng khi threat model/chính sách yêu cầu và có overlap plan.

## 19. Tạo SSLContext từ truststore trong Java

Với ứng dụng cần truststore khác theo cluster mà không thay toàn JVM, có thể tạo custom `SSLContext`:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

public class MongoTlsContextFactory {
    public static SSLContext fromTrustStore(
            Path path,
            char[] trustStorePassword
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(path)) {
            trustStore.load(stream, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            null,
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );
        return context;
    }
}
~~~

Đưa context vào driver:

~~~java
SSLContext tlsContext = MongoTlsContextFactory.fromTrustStore(
    Path.of("/etc/app/tls/mongo-truststore.p12"),
    trustStorePassword
);

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSslSettings(ssl ->
        ssl.enabled(true)
           .context(tlsContext)
           .invalidHostNameAllowed(false)
    )
    .build();
~~~

Các imports `Path`, `SSLContext` và driver classes phải được khai báo trong file Java thực tế. Ví dụ factory chỉ cấu hình **trust managers**, không cấu hình client certificate. Với mTLS, còn cần key managers tương ứng.

### 19.1. Tại sao tạo context riêng?

- Nhiều clusters sử dụng các CA khác nhau.
- Muốn tránh ghi đè global JVM truststore cho tất cả HTTP/TLS clients trong process.
- Cần kiểm soát lifecycle/reload certificate theo chính sách.

### 19.2. Truststore password khác password MongoDB

Truststore password bảo vệ file truststore ở mức định dạng/key management. MongoDB SCRAM password dùng để xác thực database user. Không dùng một secret cho cả hai theo thói quen.

### 19.3. Rotation

Khi CA/leaf đổi, process có thể phải tạo `SSLContext`/MongoClient mới hoặc reload trust theo runtime support. Không giả định thay file `.p12` trên disk khiến những existing TLS connections hoặc trust managers tự đổi ngay.

## 20. TLS kết hợp SCRAM: cấu hình đầy đủ

Một mẫu rõ ràng cho Java:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class ScramTlsApp {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        String username = System.getenv("MONGODB_USERNAME");
        String passwordText = System.getenv("MONGODB_PASSWORD");

        if (uri == null || username == null || passwordText == null) {
            throw new IllegalStateException(
                "Missing MongoDB connection configuration"
            );
        }

        char[] password = passwordText.toCharArray();
        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                username, "admin", password
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applyToSslSettings(ssl -> ssl.enabled(true))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document ping = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            System.out.println(ping.toJson());
        }
    }
}
~~~

URI từ môi trường nên **chỉ chứa hosts/options**, không chứa username/password khác. Nếu dùng CA private, bổ sung JVM truststore hoặc `SSLContext` ở các mục trước.

### 20.1. Biến mật khẩu dưới dạng String

Ví dụ đọc từ environment cho dễ hiểu; trong hệ thống cần bảo mật cao, dùng secret injection/provider phù hợp để giảm việc giữ plaintext password trong String. Dù gọi `passwordText.toCharArray()`, String ban đầu vẫn tồn tại trong heap cho tới khi JVM quản lý vòng đời.

### 20.2. TLS client certificate không bắt buộc cho SCRAM

Với server TLS cho phép clients không trình certificate, ứng dụng có thể dùng TLS server-auth và đăng nhập SCRAM. Đừng nhầm “có TLS” với “phải tạo keyStore client”.

## 21. TLS và MONGODB-X509: khi cần client certificate

Trong mTLS, MongoDB server xác minh certificate client. Nếu dùng `MONGODB-X509` làm cơ chế database authentication, MongoDB map identity từ certificate subject thành user/roles theo policy.

Một URI minh họa:

~~~text
mongodb://mongo1.db.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external
~~~

`%24external` là cách encode `$external` trong URI.

### 21.1. Cần keyStore và trustStore

Ứng dụng Java phải:

1. Tin CA ký **server certificate** qua truststore.
2. Có **client certificate và private key** để trình lên server.
3. Có client cert với EKU/subject phù hợp x.509 auth.
4. Có MongoDB user/roles tương ứng, thường trong `$external`.

Một JVM có thể được cấu hình các properties:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/tls/server-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.keyStore=/etc/app/tls/app-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
~~~

Password của keyStore/trustStore phải được cấp an toàn qua secret mechanism, không viết giá trị thật trong command-line, repo hoặc log.

### 21.2. Custom SSLContext với client key managers

Nếu không dùng global JVM properties, tạo `KeyManagerFactory` từ client keyStore và `TrustManagerFactory` từ server CA trustStore, sau đó gọi `SSLContext.init(keyManagers, trustManagers, ...)`. Có thể tái sử dụng cấu trúc ở mục 19 và bổ sung client key managers.

### 21.3. Authentication khác TLS handshake

Client certificate có thể được TLS layer chấp nhận nhưng `MONGODB-X509` vẫn fail do subject không match user, authentication mechanism/source sai hoặc thiếu quyền. Ngược lại, cert server thiếu SAN có thể làm TLS fail **trước khi** MongoDB login diễn ra.

### 21.4. Không dùng cluster member certificate cho app

Certificate dùng internal replica set/sharded membership có yêu cầu identity/privilege đặc biệt. Không tái sử dụng certificate/secret đó như ứng dụng bình thường. Phân tách PKI profiles và least privilege.

## 22. TLS của Atlas và các hệ thống managed

Một Atlas connection string thường có `mongodb+srv://...`. Bên cạnh username/password hoặc IAM/OIDC configuration được hỗ trợ, Java runtime cần:

- DNS SRV/TXT resolution.
- Network access (IP access list, peering/private endpoint theo deployment).
- TLS và certificate trust.
- Credentials đã được provision đúng database/role.
- Driver/JDK version tương thích với cluster.

Ví dụ URI **không chứa password**:

~~~text
mongodb+srv://cluster0.example.mongodb.net/?retryWrites=true&w=majority&appName=order-service
~~~

Đây là hostname minh họa, không phải Atlas cluster thật. Chèn `MongoCredential` hoặc dùng secret injection theo chính sách, rồi `getDatabase("shop")`.

### 22.1. Cần xác nhận authSource của Atlas

Đa số ứng dụng dùng database user do Atlas provision và phương thức SCRAM phù hợp; tuy vậy, không suy luận từ scheme SRV rằng mọi mechanism/authSource đều giống nhau. Dùng connection instructions của deployment thật.

### 22.2. Không tắt TLS nếu gặp `PKIX path building failed`

Lỗi chain trust của JVM phải sửa bằng CA/JDK/truststore phù hợp. Bỏ xác minh certificate làm ứng dụng có nguy cơ kết nối server giả mạo.

### 22.3. Đúng project/cluster

Atlas có thể có nhiều projects và clusters tương tự tên nhau. Ghi cluster identity/environment trong configuration management, kiểm soát production secrets và tránh nhầm target khi chạy migration.

## 23. Lấy MongoDatabase: `getDatabase()`

Sau khi có client:

~~~java
MongoDatabase shop = client.getDatabase("shop");
MongoDatabase audit = client.getDatabase("audit");
~~~

Hai biến là handles tới hai databases **trong cùng MongoDB cluster của client**.

### 23.1. Lấy handle không tạo database

~~~java
MongoDatabase future = client.getDatabase("database_chua_ton_tai");
~~~

Thao tác này **không tạo database trên server** ngay lập tức. Một database/collection thường xuất hiện khi có dữ liệu được ghi hoặc thao tác tạo collection phù hợp và có quyền. Vì vậy việc gọi `getDatabase` không phải kiểm tra database tồn tại.

### 23.2. Không nên dùng tên database từ raw user input

Ví dụ anti-pattern:

~~~java
MongoDatabase db = client.getDatabase(request.getParameter("database"));
~~~

Nếu request có thể chọn bất kỳ database, ứng dụng có thể truy cập namespace ngoài ý muốn theo quyền của service account. Dùng allowlist, mapping theo tenant được xác thực, cấu hình môi trường và roles ít nhất đủ dùng.

### 23.3. Database không mặc định là auth database

`client.getDatabase("audit")` không xác thực lại ở `audit`; kết nối vẫn dùng credentials của MongoClient.

## 24. Lấy MongoCollection: `getCollection()`

~~~java
MongoDatabase db = client.getDatabase("shop");
MongoCollection<Document> orders = db.getCollection("orders");
MongoCollection<Document> customers = db.getCollection("customers");
~~~

`MongoCollection<Document>` là một handle có thể tái sử dụng để chạy queries, writes, indexes, aggregation, change streams và các thao tác phù hợp.

### 24.1. Lấy handle không tạo collection

~~~java
MongoCollection<Document> future = db.getCollection("new_collection");
~~~

Điều này không tạo collection trên server. Collection có thể được tạo ngầm khi ghi dữ liệu phù hợp, hoặc tạo tường minh:

~~~java
db.createCollection("new_collection");
~~~

Lệnh tạo collection yêu cầu quyền và sẽ báo lỗi nếu điều kiện không phù hợp, ví dụ collection đã tồn tại. Không chạy createCollection trong mỗi HTTP request.

### 24.2. Tên collection là một phần của API contract

`orders`, `order` và `Orders` có thể là những namespaces khác nhau theo quy tắc đặt tên/môi trường. Dùng constants/config mapping rõ ràng, không ghép tenant ID hoặc HTTP parameter trực tiếp vào tên collection mà thiếu validation.

### 24.3. Generics là cách decode documents

`MongoCollection<Document>` giải mã thành `Document`. `MongoCollection<Order>` có thể giải mã thành POJO khi codec phù hợp. Generic type **không thay authentication hay authorization**.

## 25. Một ví dụ đọc dữ liệu end-to-end

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class ReadShopOrders {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("shop");
            MongoCollection<Document> orders = db.getCollection("orders");

            try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "t-01"),
                        Filters.eq("status", "PAID")
                    ))
                .projection(Projections.fields(
                    Projections.include(
                        "_id", "orderNo", "status", "total"
                    )
                ))
                .sort(Sorts.descending("createdAt", "_id"))
                .limit(20)
                .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

Ví dụ giả sử database/collection tồn tại, URI đã có TLS và credentials được cấp đúng. Nếu `MONGODB_URI` thiếu, code cần validation như mục 10. Trong production, tránh in dữ liệu thật ra stdout/log.

### 25.1. Filter và projection phục vụ hai mục tiêu

- `Filters.eq("tenantId", "t-01")` giữ truy vấn trong phạm vi tenant đã được xác thực.
- `Projections.include(...)` giảm dữ liệu trả về.

Projection không cứu được một truy vấn thiếu tenant filter về mặt security.

### 25.2. Index vẫn quan trọng

Nếu filter theo tenant/status và sort theo createdAt, cần index phù hợp access pattern. Kết nối đúng và projection nhỏ không tự giúp query tránh COLLSCAN.

## 26. Ghi dữ liệu vào collection đã chọn

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

// Giả sử db và orders đã được lấy từ MongoClient hợp lệ.
orders.insertOne(new Document("_id", "O-1001")
    .append("tenantId", "t-01")
    .append("status", "PENDING")
    .append("total", 120000));

orders.updateOne(
    Filters.and(
        Filters.eq("_id", "O-1001"),
        Filters.eq("tenantId", "t-01")
    ),
    Updates.set("status", "PAID")
);
~~~

**Chỉ chạy trên lab**: `insertOne`/`updateOne` thay dữ liệu thật nếu URI trỏ tới production.

### 26.1. Database/collection có thể xuất hiện khi ghi

Nếu database hoặc collection chưa tồn tại, một write có quyền phù hợp có thể tạo ngầm namespace; behavior còn phụ thuộc validator/options. Vì vậy một tên database đánh sai có thể tạo collection mới thay vì báo lỗi như người viết code mong đợi. Dùng constants và integration test kiểm tra namespace.

### 26.2. Quyền ghi

Một user có role chỉ đọc có thể `find()` thành công nhưng `insertOne()`/`updateOne()` báo Unauthorized. Kiểm tra roles của user ở authentication database và phạm vi quyền đã được cấp.

### 26.3. Chú ý `_id`

MongoDB yêu cầu `_id` duy nhất trong mỗi collection. Nếu không cung cấp, driver/server có thể sinh ID phù hợp tùy API; với demo trên dùng ID rõ ràng để dễ kiểm tra và tránh vô ý insert trùng.

## 27. Định kiểu collection với POJO

`Document` linh hoạt, nhưng service Java thường muốn mapping sang một class:

~~~java
public class Order {
    private String orderNo;
    private String status;
    private long total;

    public Order() {}

    public String getOrderNo() { return orderNo; }
    public void setOrderNo(String orderNo) { this.orderNo = orderNo; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public long getTotal() { return total; }
    public void setTotal(long total) { this.total = total; }
}
~~~

Với POJO codec:

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.codecs.configuration.CodecRegistry;
import org.bson.codecs.pojo.PojoCodecProvider;

import static org.bson.codecs.configuration.CodecRegistries.fromProviders;
import static org.bson.codecs.configuration.CodecRegistries.fromRegistries;

CodecRegistry pojoRegistry = fromRegistries(
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(PojoCodecProvider.builder().automatic(true).build())
);

MongoDatabase db = client.getDatabase("shop")
    .withCodecRegistry(pojoRegistry);

MongoCollection<Order> typedOrders =
    db.getCollection("orders", Order.class);
~~~

Các đoạn code nằm trong những file/class tương ứng và cần imports đầy đủ khi tích hợp. `PojoCodecProvider.automatic(true)` là ví dụ dễ hiểu; trong production, cân nhắc mapping conventions, immutable classes, IDs, enums, schema evolution và kiểm thử.

### 27.1. Codec không tự thêm quyền

`MongoCollection<Order>` vẫn dùng MongoClient credentials ban đầu. POJO mapping chỉ quyết định cách chuyển BSON ↔ Java objects.

### 27.2. Field/ID mismatch

Nếu document có `_id:ObjectId` nhưng POJO khai báo `String id` không có mapping tương thích, decode có thể lỗi. Đừng chỉ thay generic type rồi cho rằng driver tự hiểu mọi schema.

### 27.3. Decimal/money

Với dữ liệu tiền tệ, chọn kiểu `Decimal128`/`BigDecimal` hoặc integer minor units theo schema, tránh `double` gây sai số không mong muốn. Đây là quyết định data modeling riêng, không phải URI setting.

## 28. Cấu hình concern và read preference trên handles

Sau khi chọn database, bạn có thể áp read/write policies cho handle:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

MongoDatabase shop = client.getDatabase("shop")
    .withReadConcern(ReadConcern.MAJORITY)
    .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> orders = shop.getCollection("orders")
    .withReadPreference(ReadPreference.primary());
~~~

### 28.1. `readPreference`

Điều khiển driver chọn loại member để đọc khi topology hỗ trợ. `primary` thường phù hợp các thao tác đòi đọc primary; `secondary` có thể giảm tải primary nhưng chấp nhận dữ liệu chưa đồng bộ mới nhất theo semantics của hệ thống.

### 28.2. `readConcern`

Điều khiển những bảo đảm nhất quán/visibility của dữ liệu đọc. Nó không phải authentication mechanism.

### 28.3. `writeConcern`

Điều khiển acknowledgement/durability policy của writes. Không tự hạ xuống mức yếu hơn chỉ để giảm latency nếu business yêu cầu majority durability.

### 28.4. Handle methods trả về handle mới

`withReadConcern`, `withWriteConcern` và `withReadPreference` trả về một handle được cấu hình tương ứng, không phải sửa toàn bộ MongoClient cho mọi namespace. Nên giữ rõ handle nào dùng cho workload nào.

## 29. Cấu hình nhiều database trong cùng ứng dụng

Ví dụ dịch vụ sử dụng:

~~~text
MongoClient: mongodb://replica-set-cluster
    shop.orders
    shop.customers
    audit.events
~~~

Code:

~~~java
MongoDatabase shopDb = client.getDatabase("shop");
MongoDatabase auditDb = client.getDatabase("audit");

MongoCollection<Document> orders =
    shopDb.getCollection("orders");
MongoCollection<Document> customers =
    shopDb.getCollection("customers");
MongoCollection<Document> auditEvents =
    auditDb.getCollection("events");
~~~

### 29.1. Một client không đổi thành nhiều clusters

Nếu `shop` ở cluster A và `audit` ở cluster B, cần hai MongoClients với URI/credentials/pools phù hợp. `getDatabase("audit")` trên client kết nối cluster A **không** tự chuyển sang cluster B.

### 29.2. Role boundaries

Một user được cấp quyền shop và audit có blast radius rộng hơn user chỉ có quyền shop. Nếu quyền giữa hai services khác nhau, cân nhắc clients/credentials tách biệt theo least privilege.

### 29.3. Dynamic tenant databases

Nếu mô hình mỗi tenant là một database, không lấy tên database trực tiếp từ request user mà thiếu validation. Kiểm tra tenant identity theo auth context, mapping namespace được phép, quotas và permission isolation.

## 30. Collection/database handles có tồn tại không?

`getDatabase` và `getCollection` không kiểm tra sự tồn tại:

~~~java
MongoDatabase maybe = client.getDatabase("typo_databse");
MongoCollection<Document> coll = maybe.getCollection("orders");
~~~

Hai dòng có thể chạy thành công dù database sai tên. Khi cần xác nhận:

~~~java
for (String databaseName : client.listDatabaseNames()) {
    System.out.println(databaseName);
}

MongoDatabase db = client.getDatabase("shop");
for (String collectionName : db.listCollectionNames()) {
    System.out.println(collectionName);
}
~~~

### 30.1. List không phải luôn đầy đủ với mọi user

Kết quả list databases/collections phụ thuộc privileges, authorization policy và các options của MongoDB. Một user ít quyền có thể không liệt kê được toàn bộ cluster dù có thể truy vấn namespace được cấp. Đừng dùng một admin list operation trong readiness check của app chỉ đọc nếu không cần.

### 30.2. Ping không chứng minh namespace tồn tại

`ping` thành công nhưng collection `shop.orders` có thể chưa được tạo hoặc user thiếu quyền. Để kiểm tra luồng nghiệp vụ, thực hiện một read/write smoke test **không phá dữ liệu** với đúng quyền.

## 31. MongoDB server authentication và internal cluster auth

Đối với ứng dụng Java:

- Driver gửi credentials của **application user**.
- Cluster tự quản có thể dùng keyFile hoặc x.509 giữa members; đó là **internal cluster authentication**, không phải credentials mà application Java cần cung cấp.
- TLS ứng dụng→mongod/mongos và TLS giữa cluster members là hai đoạn mạng khác nhau.

Không tìm cách đọc `security.keyFile` của mongod rồi gắn vào MongoClient của service. Làm vậy vừa sai lớp, vừa có thể làm lộ shared secret cấp cluster.

### 31.1. Ứng dụng không cần biết ai là primary cố định

Với replica set URI/topology đúng, driver quản lý server selection. Không hardcode primary hostname như một server đơn nếu cần automatic failover.

### 31.2. Sharded clusters

Ứng dụng bình thường kết nối tới `mongos` routers hoặc endpoint được dịch vụ managed cung cấp, không trực tiếp viết vào shard members để bỏ routing/metadata. TLS và credentials phải phù hợp router endpoint.

## 32. Lỗi URI phổ biến

| Lỗi | Triệu chứng | Cách sửa |
|---|---|---|
| Sai scheme `mongodb+srv` | Parser/DNS fail | Dùng `mongodb+srv://` đúng cú pháp |
| Gắn port sau SRV DNS name | URI không hợp lệ | SRV dùng một service hostname, không port như standard URI |
| Password có `@` chưa encode | Host parsing/auth failure | Dùng `MongoCredential` hoặc encode đúng |
| Thiếu dấu `?` trước options | URI parser không hiểu | Kiểm tra cú pháp path/options |
| Nhầm `&` trong shell | Command bị tách nếu không quote | Quote URI đúng shell |
| Sai `replicaSet` | Server selection fail | Kiểm tra replica set name |
| `directConnection=true` không đúng | Không discovery/failover | Dùng URI replica set bình thường |
| `authSource` sai | Authentication failed | Chọn database chứa user |
| Hostname không route được | Timeout/DNS | Sửa DNS/network/advertised hosts |
| Driver/JDK quá cũ | SRV/TLS/mechanism không hỗ trợ | Nâng lên bản compatible đã kiểm thử |

### 32.1. Không in nguyên URI để debug

Khi lỗi parser, ứng dụng có thể vô tình log `mongodb://username:secret@...`. Redact username nếu cần và luôn bỏ password/token trước khi đưa vào log.

## 33. Phân biệt các lỗi kết nối quan trọng

| Triệu chứng | Tầng khả năng lỗi | Kiểm tra |
|---|---|---|
| `MongoConfigurationException`/URI parser | Client config | Scheme/options/credential format |
| DNS SRV lookup fail | DNS | SRV/TXT records, resolver/network |
| `MongoSocketOpenException` | Network | Host, port, firewall, service running |
| `MongoTimeoutException` / server selection timeout | Topology/connection | Nested causes, replica set health, DNS, TLS |
| `SSLHandshakeException` | TLS | CA, SAN, expired cert, protocol/EKU |
| `PKIX path building failed` | JVM trust | Truststore CA/intermediate |
| `MongoSecurityException` / Authentication failed | Login | Username/password, authSource, mechanism |
| `MongoCommandException` code Unauthorized | Authorization | Roles/collection privilege |
| `MongoWriteException` duplicate key | Data/index | Duplicate `_id`/unique index |
| Successful `ping` but `find` fails | Namespace/privilege/query | Roles, database name, collection name |

Không có một exception duy nhất bao trùm tất cả; driver có thể wrap nhiều lớp nguyên nhân. Đọc **root cause đã redact secrets**.

### 33.1. ServerSelectionTimeout không có nghĩa luôn thiếu server

Driver không tìm được server phù hợp có thể vì network, TLS handshake, replica set name, server đang secondary, firewall hoặc DNS. Tăng timeout không sửa nguyên nhân gốc.

### 33.2. Authentication failed vs Unauthorized

“Authentication failed” nghĩa không xác nhận được identity với credentials/mechanism; “Unauthorized” thường nghĩa identity đã được xác nhận nhưng thiếu quyền cho command.

### 33.3. TLS fail trước SCRAM

Nếu certificate không được JVM trust, kết nối có thể dừng ở handshake, chưa tới bước password check. Đừng thay database password khi root cause là `PKIX path building failed`.

## 34. Chẩn đoán TLS an toàn

Để kiểm tra server certificate từ host được phép:

~~~bash
openssl s_client \
  -connect mongo1.db.internal:27017 \
  -servername mongo1.db.internal \
  -CAfile /etc/app/tls/mongo-ca.pem \
  -verify_return_error
~~~

Kiểm tra certificate file public:

~~~bash
openssl x509 -in mongo-server.crt \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

### 34.1. OpenSSL thành công chưa đủ

`openssl s_client` kiểm tra TLS endpoint, không xác minh toàn bộ MongoDB wire protocol, user auth, replica discovery hoặc Java truststore. Sau đó dùng chính ứng dụng Java hoặc smoke test Java với `ping`.

### 34.2. Java SSL handshake logging

JVM có các debug options liên quan `javax.net.debug`, nhưng logs có thể rất lớn và chứa metadata nhạy cảm. Chỉ dùng tạm trong sandbox/test với redaction và truy cập hạn chế, không bật vô hạn trên production.

### 34.3. Không dùng `invalidHostNameAllowed(true)`

Nếu SAN sai, cần sửa hostname/PKI. Vô hiệu hóa hostname verification khiến việc giả mạo endpoint dễ hơn và không phải cấu hình production phù hợp.

## 35. Secret management và config theo môi trường

Một thiết kế cấu hình:

~~~text
Environment: production
MONGODB_URI = mongodb+srv://cluster-prod.example.mongodb.net/?tls=true
MONGODB_AUTH_DB = admin
MONGODB_TARGET_DB = shop
MONGODB_USERNAME = đọc từ secret store
MONGODB_PASSWORD = đọc từ secret store
MongoDB CA trust = managed by TLS trust configuration
~~~

Trong code, dùng cấu hình strongly typed và validation lúc startup. Không cho phép Java service tự chọn production cluster từ raw HTTP input.

### 35.1. Dev/staging/prod isolation

Sử dụng các MongoDB users khác nhau cho các environments, ưu tiên clusters tách biệt và hạn chế network access. Một staging bug không nên có khả năng ghi lên production.

### 35.2. Rotation credentials

Khi thay password/CA, connections hiện có có thể tiếp tục tồn tại trong pool, còn kết nối mới dùng credentials/certificate theo cấu hình đã được driver load. Cần xác định cơ chế reload và có deployment/overlap plan; không giả định thay secret trên disk tự cập nhật mọi MongoClients.

### 35.3. Không hardcode connection string trong repository

Kể cả không có password, hostname/cluster IDs có thể tiết lộ network architecture. Quản lý config theo policy và không public production topology không cần thiết.

## 36. Một service configuration factory

Ví dụ một helper tạo MongoClientSettings từ cấu hình đã được kiểm tra:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.Objects;
import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {
    private MongoClientFactory() {}

    public static MongoClient create(
            String uri,
            String username,
            char[] password,
            String authDatabase
    ) {
        Objects.requireNonNull(uri, "uri");
        Objects.requireNonNull(username, "username");
        Objects.requireNonNull(password, "password");
        Objects.requireNonNull(authDatabase, "authDatabase");

        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                username, authDatabase, password
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applicationName("order-service")
            .applyToSslSettings(ssl -> ssl.enabled(true))
            .applyToClusterSettings(cluster ->
                cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
            )
            .applyToConnectionPoolSettings(pool -> pool.maxSize(50))
            .build();

        return MongoClients.create(settings);
    }
}
~~~

Factory chỉ là ví dụ: production còn cần truststore/SSLContext nếu dùng CA private, audit config và lifecycle management. URI phải không chứa credentials chồng chéo. Caller có trách nhiệm đóng client khi ứng dụng shutdown.

### 36.1. Lấy collection từ factory

~~~java
MongoClient client = MongoClientFactory.create(
    uri, username, password, "admin"
);

MongoCollection<Document> orders = client
    .getDatabase("shop")
    .getCollection("orders");
~~~

Ở service thực, code này nên thực hiện một lần trong startup/composition root và inject `orders` vào các components; không gọi mỗi HTTP request.

## 37. Integration smoke test

Một smoke test kết nối cần kiểm tra:

1. URI parse được.
2. Driver kết nối và TLS/auth thành công.
3. Namespace đúng (không nhầm staging/prod).
4. Quyền đọc collection được cấp.
5. Query trả đúng kiểu và dữ liệu mẫu.

~~~java
try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase admin = client.getDatabase("admin");
    admin.runCommand(new Document("ping", 1));

    MongoDatabase shop = client.getDatabase("shop");
    MongoCollection<Document> orders = shop.getCollection("orders");

    Document one = orders.find(
        Filters.eq("tenantId", "t-01")
    ).projection(Projections.include("_id", "orderNo")).first();

    System.out.println("Connectivity and authorized read OK");
}
~~~

Trong code thực cần imports, NULL handling và assertion phù hợp; `one` có thể null nếu collection không có record match. Không log document chứa PII nếu không cần. Test ở môi trường cô lập với dữ liệu định sẵn mới có thể khẳng định kết quả đúng.

### 37.1. Test thiếu quyền

Một tài khoản read-only nên không thể ghi nếu policy yêu cầu. Kiểm tra least privilege ở integration/security tests, nhưng **không thử ghi phá dữ liệu trên production**.

### 37.2. Test failover

Với replica set trong staging, test driver tiếp tục hoạt động sau failover có kiểm soát, bao gồm hostname SAN, DNS, server selection và retry behavior. Không phá primary production chỉ để xác minh URI.

## 38. Khả năng phục hồi và retryable operations

URI có thể chứa `retryWrites=true` và `retryReads=true` khi driver/topology hỗ trợ, nhưng:

- Không phải mọi operation đều retryable.
- Retry không làm một command phi-idempotent bất kỳ an toàn vô điều kiện.
- Một thao tác fail ở client có thể đã được server áp dụng trước khi connection bị mất.
- Ứng dụng cần idempotency keys và xử lý duplicate khi nghiệp vụ yêu cầu.

### 38.1. Username/password không phải retry strategy

Nếu credentials sai, tự retry liên tục không sửa lỗi; có thể tăng log/alert noise hoặc tạo lockout policy ở hệ thống bên ngoài.

### 38.2. TLS handshake errors không nên bypass

Nếu CA/SAN sai, retry nhiều lần vẫn không làm certificate đúng. Sửa trust/config.

### 38.3. Network partition

Khi không có primary phù hợp, server selection timeout có thể xuất hiện. Retry ở tầng application phải có deadline, backoff và xử lý business semantics để tránh overload sau khi cluster phục hồi.

## 39. Kiểm tra cấu hình production trước khi release

| Nhóm | Câu hỏi |
|---|---|
| URI | Scheme/hosts/replicaSet/SRV có đúng cluster không? |
| Credentials | User/authSource/authMechanism đúng và secret không hardcode? |
| TLS | TLS bật, CA trust, SAN, expiry và hostname verification đúng? |
| Network | DNS, firewall/IP allowlist/private endpoint hoạt động? |
| Driver | JDK/driver version hỗ trợ MongoDB Server và codecs/auth? |
| Lifecycle | MongoClient singleton/pool reused, đóng ở shutdown? |
| Namespace | Database/collection constants đúng production config? |
| RBAC | User chỉ có quyền cần thiết trên namespaces phù hợp? |
| Resilience | Pool, timeouts, retries được thử theo workload? |
| Observability | Metrics/logs có redaction và appName? |
| Tests | Ping, query, failover và negative auth tests đã chạy? |

Không đánh dấu “đã kết nối” chỉ vì object `MongoClient` được tạo trong JVM.

## 40. Bài thực hành A — đọc URI

Cho:

~~~text
mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017/shop?replicaSet=rs0&authSource=admin&tls=true&appName=warehouse-service
~~~

Trả lời:

1. Scheme là gì?
2. Các seed hosts là gì?
3. `shop` là database path hay collection?
4. Authentication database là gì?
5. Java lấy handle collection `orders` bằng code nào?
6. TLS đã được yêu cầu chưa?

## 41. Bài thực hành B — URI và ký tự đặc biệt

Password của tài khoản lab chứa `@`, `/` và `#`. Hãy giải thích vì sao nối trực tiếp vào URI có thể làm parser sai. Viết phương án dùng `MongoCredential.createScramSha256Credential` thay vì URI userinfo.

## 42. Bài thực hành C — authentication source

Một MongoDB user `orderApp` được tạo ở database `admin` và có role đọc `shop.orders`. Java dùng:

~~~text
mongodb://mongo1.db.internal:27017/shop?tls=true
~~~

nhưng authentication fail. Nếu credentials đúng, option nào cần kiểm tra thêm? Sau khi auth thành công, có phải `getDatabase("shop")` xác thực lần thứ hai không?

## 43. Bài thực hành D — truststore

Java app báo `PKIX path building failed` khi kết nối MongoDB có certificate do private CA ký. Mongosh dùng `--tlsCAFile` kết nối thành công. Hãy xác định các bước kiểm tra JVM truststore, intermediate chain, SAN và JDK TLS support.

## 44. Bài thực hành E — replica set failover

Seed URI kết nối `mongo1.db.internal` thành công. Sau khi primary chuyển sang `mongo2.db.internal`, Java báo hostname mismatch. Hãy giải thích cơ chế discovery, vì sao cert của mongo2 cần SAN phù hợp và vì sao không bật `invalidHostNameAllowed(true)`.

## 45. Bài thực hành F — chọn database/collection

Viết Java code dùng **một MongoClient** để lấy `shop.orders`, `shop.customers` và `audit.events`. Sau đó trả lời:

- Các lệnh `getDatabase/getCollection` có tự tạo namespace không?
- Chúng có xác thực lại với MongoDB không?
- Khi nào cần hai MongoClients thay vì một?

## 46. Bài thực hành G — POJO mapping

Viết `Order` class và cấu hình `CodecRegistry` để lấy `MongoCollection<Order>`. Nêu rủi ro nếu field `_id` trong MongoDB là ObjectId nhưng POJO chỉ chấp nhận String không có mapping.

## 47. Bài thực hành H — phân biệt lỗi

Ứng dụng gặp các lỗi:

~~~text
1. SSLHandshakeException: certificate_unknown
2. Authentication failed
3. Unauthorized
4. MongoTimeoutException: server selection timeout
~~~

Hãy phân loại từng lỗi theo TLS, authentication, authorization và topology/network; nêu hướng kiểm tra đầu tiên.

## 48. Bài thực hành I — settings precedence

URI đã chứa `authSource=shop`, nhưng builder tạo `MongoCredential` với auth database `admin`. Giải thích vì sao hai nguồn cấu hình có thể gây hiểu nhầm; đề xuất một policy rõ ràng để chỉ có một nguồn quyết định database authentication.

## 49. Bài thực hành J — Atlas SRV

Một service Java được cấp hostname:

~~~text
cluster0.example.mongodb.net
~~~

Hãy tạo URI `mongodb+srv://` hợp lệ về hình dạng, nêu các yêu cầu DNS SRV/TXT, TLS, network access và credentials. Vì sao không gắn `:27017` ngay sau tên SRV service?

## 50. Bài thực hành K — lifecycle và pool

Một HTTP service tạo `MongoClient` mới ở mỗi request rồi đóng ngay khi trả response. Hãy giải thích chi phí topology discovery/TLS/pool, cách đổi thành singleton và các metric cần đo (connections, pool wait, latency, CPU).

## 51. Bài thực hành L — namespace safety

Một endpoint nhận query parameters `database` và `collection` rồi gọi trực tiếp `getDatabase/getCollection`. Nêu các rủi ro lộ dữ liệu tenant khác hoặc vô tình ghi vào namespace sai. Thiết kế allowlist/mapping dựa trên identity.

## 52. Gợi ý đáp án thực hành

**A:** Scheme `mongodb://`; seed hosts mongo1/mongo2; `shop` là database path; `authSource=admin`; Java lấy `client.getDatabase("shop").getCollection("orders")`; `tls=true` yêu cầu TLS.

**B:** Password có reserved characters làm sai URI parsing nếu không encode. Đặt username/authDb/password qua `MongoCredential` và URI chỉ chứa topology/options.

**C:** Xác minh `authSource=admin` vì user ở admin. `getDatabase("shop")` chỉ chọn namespace, không login lại.

**D:** JVM truststore có thể thiếu private CA dù mongosh được cấp CA file riêng. Kiểm tra root/intermediate, SAN, validity, JDK protocol; không bypass validation.

**E:** Driver kết nối các advertised replica set hosts; mongo2 certificate phải có SAN cho hostname thực. Bỏ hostname validation tạo rủi ro MITM.

**F:** Một MongoClient có thể lấy nhiều databases/collections trong cùng cluster; get handles không tự tạo namespace hoặc authenticate lại. Hai clusters/credentials tách biệt cần clients/settings phù hợp.

**G:** Dùng PojoCodecProvider + CodecRegistry, getCollection("orders", Order.class); schema ID/type mismatches có thể gây decode/codec errors.

**H:** 1 TLS; 2 authentication user/mechanism/source; 3 authorization roles; 4 server selection/topology/DNS/TLS nested cause.

**I:** Tránh cấu hình chồng chéo; nếu chọn MongoCredential, URI không có auth user/password hoặc authSource mâu thuẫn, ghi rõ precedence trong app config.

**J:** `mongodb+srv://cluster0.example.mongodb.net/?tls=true` là ví dụ hình dạng. Driver cần DNS SRV/TXT, network access, CA trust và credentials; SRV host không thêm port như URI standard.

**K:** Tạo client mỗi request gây overhead và nhiều sockets. Dùng MongoClient singleton do DI/container quản lý; monitor pool wait, connections, CPU và p95/p99.

**L:** Validate tenant principal, map sang các database/collections được phép; không dùng raw user input để chọn namespace và không cấp service account quyền quá rộng.

## 53. Những lỗi và anti-pattern thường gặp

| Anti-pattern | Hậu quả | Phương án |
|---|---|---|
| Hardcode password trong URI/source | Rò rỉ secret | Secret manager + MongoCredential |
| Không encode userinfo | Lỗi URI/auth bất thường | Encode đúng hoặc tách credentials |
| Nhầm authSource với target database | Authentication failed | Xác định DB chứa user |
| Dùng `getDatabase` để kiểm tra DB tồn tại | Kết luận sai | Query/list với quyền phù hợp |
| Tạo MongoClient mỗi request | Nhiều pools/TLS handshakes | Reuse singleton |
| Hardcode primary replica set | Failover kém | Replica set URI/topology discovery |
| `directConnection=true` để che DNS lỗi | Không discovery đúng | Sửa advertised hosts/network |
| Java thiếu CA nhưng mongosh có | TLS fail riêng Java | JVM truststore/SSLContext |
| Dùng trust-all SSLContext | Mất xác minh server identity | Cài CA chain đúng |
| Tắt hostname validation | Dễ MITM | Sửa SAN/DNS |
| Dùng cluster member cert cho app | Lộ internal identity | Client PKI riêng |
| URI từ staging trỏ prod | Ghi nhầm dữ liệu | Config environment isolation |
| Lấy collection từ raw URL parameter | Đọc/ghi namespace sai | Allowlist mapping |
| Dùng user root cho service | Blast radius lớn | RBAC least privilege |
| `ping` thành công rồi kết luận có quyền ghi | Lỗi Unauthorized khi ghi | Smoke test đúng namespace/role |
| Tăng pool/timeouts vô hạn | Resource pressure/che root cause | Benchmark/troubleshoot |
| Log full connection string | Lộ credentials/topology | Redact secrets |
| Coi `MongoCollection<Order>` là validation schema | Decode/logic lỗi | POJO codec + schema validation |
| Bỏ TLS vì certificate lỗi | Mất bảo mật network | Sửa PKI/truststore |

## 54. Câu hỏi ôn tập

**1. MongoDB Java Sync Driver dùng interface MongoClient nào?** — `com.mongodb.client.MongoClient`.

**2. `MongoClients.create(uri)` có chứng minh login đã thành công không?** — Không; chạy `ping`/operation để kiểm tra.

**3. `mongodb://` và `mongodb+srv://` khác thế nào?** — Chuẩn host seeds trực tiếp so với khám phá qua DNS SRV/TXT.

**4. Có được gắn port sau SRV hostname như URI chuẩn không?** — Không theo cú pháp SRV thông thường.

**5. `replicaSet` trong URI dùng để làm gì?** — Xác định/khám phá replica set đúng.

**6. `directConnection=true` có phù hợp automatic failover mặc định không?** — Không; chỉ dùng khi thực sự muốn direct mode.

**7. `authSource` là gì?** — Database dùng để xác thực MongoDB user.

**8. `authSource=admin` có buộc mọi queries chạy ở admin không?** — Không; `getDatabase("shop")` có thể chọn shop.

**9. `getDatabase()` có tạo database trên server không?** — Không, chỉ tạo handle.

**10. `getCollection()` có tạo collection trên server không?** — Không, chỉ tạo handle.

**11. Có thể dùng một client cho nhiều collections?** — Có, trong cluster/credentials của client đó.

**12. Có nên tạo client mỗi HTTP request không?** — Không; MongoClient là thread-safe và có pool.

**13. Nên lưu SCRAM password ở đâu?** — Secret management phù hợp, tránh hardcode và log.

**14. Vì sao password có `@` cần chú ý?** — Ký tự reserved làm URI parser hiểu sai nếu không encode.

**15. `MongoCredential.createScramSha256Credential` nhận gì?** — Username, authentication database và password char[].

**16. TLS server authentication khác SCRAM thế nào?** — TLS bảo vệ/xác minh kết nối; SCRAM xác thực database user.

**17. Java dùng truststore để làm gì?** — Tin CA/certificate chain của server.

**18. JVM truststore có luôn trùng OS CA store không?** — Không nhất thiết.

**19. SAN không khớp URI host có vấn đề không?** — Có, hostname validation có thể từ chối kết nối.

**20. `MONGODB-X509` dùng auth database nào?** — Thường là `$external` theo cơ chế.

**21. mTLS có tự cấp readWrite quyền MongoDB không?** — Không; user/role vẫn phải phù hợp.

**22. Atlas SRV dùng TLS không?** — `mongodb+srv://` thường bật TLS mặc định; kiểm tra deployment và giữ verification.

**23. `Unauthorized` nghĩa password sai?** — Không nhất thiết; thường là user thiếu quyền sau khi được xác thực.

**24. `MongoTimeoutException` luôn do server down?** — Không; có thể DNS, topology, TLS hoặc network.

**25. Read preference có thay authentication source không?** — Không, nó chọn member đọc theo topology.

**26. Write concern có tự sửa query index không?** — Không, nó liên quan write acknowledgement/durability.

**27. POJO codec dùng để làm gì?** — Mapping BSON ↔ Java class.

**28. Một MongoClient đổi cluster bằng getDatabase được không?** — Không, getDatabase chỉ chọn DB trên cluster đã kết nối.

**29. `ping` thành công có chứng minh collection tồn tại không?** — Không.

**30. Cách kiểm thử connection chuẩn?** — Kiểm tra URI/secrets/TLS, chạy ping và smoke test đúng namespace/role.

## 55. Bảng ghi nhớ nhanh

| Nhu cầu | Cơ chế/API |
|---|---|
| Kết nối MongoDB URI | `MongoClients.create(uri)` |
| Tạo cấu hình chi tiết | `MongoClientSettings.builder()` |
| Parse URI | `new ConnectionString(uri)` |
| SCRAM user | `MongoCredential.createScramSha256Credential(...)` |
| Database auth | URI `authSource` hoặc MongoCredential authDb |
| Chọn replica set | URI `replicaSet=rs0` |
| DNS SRV | `mongodb+srv://hostname/` |
| Bật TLS | URI `tls=true` hoặc SSL settings |
| Trust private CA | JVM trustStore hoặc custom SSLContext |
| Client mTLS | KeyStore + key managers/certificate |
| X.509 database auth | `MONGODB-X509`, `$external` |
| Connection pool | MongoClient shared + pool settings |
| Kiểm tra kết nối | `runCommand(new Document("ping",1))` |
| Chọn database | `client.getDatabase("shop")` |
| Chọn collection BSON | `db.getCollection("orders")` |
| Chọn collection POJO | `db.getCollection("orders", Order.class)` |
| Tạo collection tường minh | `db.createCollection("orders")` |
| Filter | `Filters.eq(...)` |
| Projection | `Projections.include(...)` |
| Query giới hạn | `find(...).limit(20)` |
| Read concern | `db.withReadConcern(...)` |
| Write concern | `db.withWriteConcern(...)` |
| Read preference | `collection.withReadPreference(...)` |
| Liệt kê DB | `client.listDatabaseNames()` |
| Liệt kê collections | `db.listCollectionNames()` |
| Đóng client | `client.close()` khi shutdown |

## 56. Checklist triển khai

- [ ] Đã chọn đúng Java Sync Driver/JDK version compatible?
- [ ] URI scheme đúng `mongodb://` hoặc `mongodb+srv://`?
- [ ] Replica set name/seed hosts/SRV records đúng?
- [ ] DNS/port/firewall/IP allowlist/private endpoint hoạt động?
- [ ] TLS bật theo policy, không dùng plaintext production ngoài ngoại lệ được duyệt?
- [ ] JVM tin CA chain, hostname SAN khớp mọi advertised host?
- [ ] Certificates chưa hết hạn và có kế hoạch rotation?
- [ ] Không dùng trust-all hoặc bỏ hostname verification?
- [ ] Username/password đến từ secret management, không hardcode/log?
- [ ] `authSource`, `authMechanism` đúng user đã provision?
- [ ] Không có cấu hình credentials chồng chéo giữa URI và builder?
- [ ] User có roles ít nhất đủ dùng trên target database/collection?
- [ ] MongoClient được tạo một lần mỗi cluster/settings và dùng pool?
- [ ] Pool size/timeouts đã benchmark và theo dõi?
- [ ] Có `ping` để kiểm tra server selection/auth/TLS khi startup?
- [ ] Chọn database/collection qua constants hoặc mapping được validate?
- [ ] Không lấy tên namespace từ raw user input?
- [ ] Đã hiểu `getDatabase/getCollection` chỉ lấy handles?
- [ ] POJO codec/schema mapping được kiểm thử nếu dùng typed collection?
- [ ] Read concern, write concern, read preference theo yêu cầu nghiệp vụ?
- [ ] Có retry/backoff/idempotency phù hợp?
- [ ] Integration smoke test kiểm tra đúng quyền và target environment?
- [ ] Test failover của replica set trong staging?
- [ ] Logs/metrics redact credentials, PII và URI nhạy cảm?
- [ ] Có runbook sửa TLS/DNS/authSource/Unauthorized/timeout errors?
- [ ] Có kế hoạch secret/CA rotation và graceful shutdown?

## 57. Kết luận

Kết nối MongoDB từ Java cần cấu hình **đúng topology, đúng identity và đúng namespace**. `mongodb://` cho phép chỉ rõ seed hosts, trong khi `mongodb+srv://` dùng DNS SRV/TXT để khám phá endpoints; các options như `replicaSet`, `authSource`, `authMechanism` và `tls` quyết định cách driver tìm server và xác thực. Nên tách password khỏi URI bằng `MongoCredential` hoặc cơ chế secret management để giảm rủi ro lộ credentials.

**TLS** bảo vệ mạng và xác minh MongoDB endpoint; private CA cần được JVM trust, hostname phải khớp SAN, certificate còn hiệu lực. Với client certificate/MONGODB-X509, cần thêm keyStore và database user/roles tương ứng. Không nhầm TLS handshake với SCRAM login, không dùng trust-all context để chữa lỗi certificate.

Sau khi tạo `MongoClient`, dùng `getDatabase()` và `getCollection()` để lấy handles, **không phải tạo database/collection mới mỗi lần**. Tái sử dụng MongoClient và connection pool theo vòng đời ứng dụng; chỉ cần client mới khi cluster/settings/credentials cần tách biệt. Cuối cùng, chỉ xem cấu hình đã hoàn tất khi thực hiện được `ping` và **read/write smoke test đúng quyền trên namespace được chọn**, đồng thời bảo đảm secret handling, TLS, logs và failover hoạt động an toàn.
