# Tương thích giữa MongoDB Server, Driver và Database Tools

## Mục tiêu bài học

Trong quá trình **vận hành và nâng cấp MongoDB**, một thay đổi tưởng chừng đơn giản như nâng `mongod` từ 7.0 lên 8.0, cập nhật Java Sync Driver từ 4.x sang 5.x hoặc cài gói `mongodb-database-tools` mới có thể ảnh hưởng đến nhiều lớp khác nhau. Một ứng dụng kết nối được không đồng nghĩa mọi tính năng mới đều hoạt động; một công cụ `mongodump` hỗ trợ kết nối đến server không đồng nghĩa mọi bản dump có thể khôi phục an toàn sang server bất kỳ; còn việc thay binary server không có nghĩa Feature Compatibility Version (FCV) đã được bật.

Bài thuộc **Database Engine Document MongoDB → Vận hành và nâng cấp → Tương thích giữa server, driver và Database Tools**.

Sau khi học, bạn có thể:

- Phân biệt phiên bản **MongoDB Server**, **MongoDB Driver**, **MongoDB Database Tools**, **mongosh** và **FCV**.
- Đọc bảng tương thích chính thức thay vì dùng quy tắc “phiên bản phải giống nhau”.
- Kiểm tra phiên bản/thực trạng của server từ `mongosh`, ứng dụng Java và command line.
- Hiểu khác biệt giữa **kết nối được**, **được kiểm thử**, **fully compatible** và **chạy được một tính năng cụ thể**.
- Chọn Java Sync Driver phù hợp server và Java runtime, tránh xung đột dependency.
- Phân biệt `mongodump/mongorestore` với `mongoexport/mongoimport` và những giới hạn BSON/Extended JSON.
- Kiểm tra khả năng restore dump theo **server major version/FCV**, metadata, archive và oplog.
- Thiết kế trình tự nâng cấp replica set/sharded cluster và giai đoạn xác nhận FCV.
- Hiểu vì sao Database Tools `100.x` không phải MongoDB Server `100.x`.
- Lập ma trận tương thích và kế hoạch rollout/canary/rollback.
- Chẩn đoán lỗi bắt tay wire protocol, authentication, TLS, DNS, server selection, tool flags và lỗi restore.
- Viết smoke tests cùng runbook cho môi trường dev, staging và production.

> **Nguyên tắc vận hành:** Xác nhận tương thích theo **đúng cặp sản phẩm, phiên bản, deployment và tính năng**. Không dùng việc một command chạy thành công trên máy cá nhân để bảo đảm việc nâng cấp toàn cluster an toàn.

**Thời điểm tài liệu:** các ví dụ phiên bản có đối chiếu tài liệu MongoDB đang công bố ngày **14/11/2026**. Các bảng hỗ trợ thay đổi khi có driver/database tools/server release mới. Khi triển khai, luôn kiểm tra bảng tương thích chính thức của **phiên bản đang định sử dụng**, đặc biệt những bản minor/patch hoặc release chưa được kiểm thử.

---

## 1. Một ứng dụng MongoDB thực sự có những thành phần gì?

~~~text
                 Java application / Spring Boot
                        |
                MongoDB Java Sync Driver
                        |
       TLS + authentication + MongoDB wire protocol
                        |
              mongos / mongod / Atlas router
                        |
              MongoDB Server deployment
              binary version + cluster FCV
                        |
              collections, indexes, data

Administrators / CI:
  mongosh                     (shell, version riêng)
  mongodump / mongorestore    (Database Tools 100.x)
  mongoexport / mongoimport   (Database Tools 100.x)
  mongostat / mongotop        (Database Tools 100.x)
  mongofiles / bsondump       (Database Tools 100.x)
~~~

Trong hệ thống thực tế còn có:

- Atlas UI/CLI và Atlas control plane.
- MongoDB Search/Vector Search services.
- Ops Manager/Cloud Manager nếu dùng self-managed.
- TLS/PKI, DNS/SRV records, IAM và KMS.
- Container images, Kubernetes Operator, OS distribution, CPU architecture.
- Backup service và lịch sử restore.

Mỗi thành phần có chu kỳ phát hành/compatibility riêng.

### 1.1. Năm version thường cần ghi lại

| Thành phần | Ví dụ minh họa | Để làm gì? |
|---|---|---|
| MongoDB Server binary | `8.0.x` | Engine, commands, wire protocol, storage, query semantics |
| Feature Compatibility Version | `8.0` hoặc `7.0` tùy trạng thái nâng cấp | Cho phép một số persistent features không tương thích bản cũ |
| Java Sync Driver | `5.12.x` | Kết nối từ JVM, codec, retry, command APIs |
| Database Tools | `100.20.1` | Dump/restore, import/export, diagnostics |
| mongosh | `2.x` hoặc bản tương ứng | Giao diện shell và helper methods |

Các con số này **không cần và không thể** trùng nhau về mặt số học.

### 1.2. Phiên bản của deployment có thể khác phiên bản công cụ cục bộ

Máy chạy command `mongodump --version` hiển thị một phiên bản của chương trình **trên máy đó**, không phải phiên bản `mongod` trong Atlas mà nó kết nối tới.

Tương tự, `mongosh --version` không nói cluster chạy MongoDB Server version nào.

### 1.3. Những câu hỏi nên hỏi trước khi nâng cấp

1. Server source/target đang chạy bản nào?
2. Cluster FCV là gì?
3. Đang là standalone, replica set, sharded cluster hay Atlas-managed?
4. Ứng dụng dùng driver bản nào, Java runtime nào?
5. Database Tools bản nào tạo backup, bản nào sẽ restore?
6. Dữ liệu có tính năng/metadata mới bị server cũ không hiểu không?
7. Có encryption, Search, time-series, change streams hoặc sharding không?
8. Mục tiêu nâng cấp và rollback window là gì?

---

## 2. MongoDB Server binary version

### 2.1. `mongod` và `mongos`

- `mongod`: database server process, chạy standalone/replica set/shard/config server tùy topology.
- `mongos`: query router cho sharded cluster.
- Atlas quản lý nhiều khía cạnh triển khai/upgrade và có thể giới hạn quyền truy cập trực tiếp vào host binaries.

Nâng cấp sharded cluster không phải chỉ thay một `mongod` binary duy nhất; phải theo **quy trình chính thức** về components và thứ tự upgrade.

### 2.2. Major, minor và patch releases

Các ví dụ như `7.0`, `8.0`, `8.2`, `8.3` và `9.0` thể hiện các nhánh được MongoDB tài liệu hóa trong năm 2026. Mỗi release train có support policy, deployment support và feature set riêng.

Một patch release có thể chứa bug fixes, bảo mật hoặc thay đổi liên quan compatibility. Đừng ghi rule “nâng giữa 8.x bất kỳ luôn tương thích đầy đủ” khi chưa đọc release notes.

### 2.3. Không suy version từ package installer

Gói OS có thể tên `mongodb-org` nhưng chứa mongod/mongos cùng những packages phụ khác. Docker tag `mongo:8` cũng có thể trỏ tới patch khác theo thời gian. Nên pin phiên bản cụ thể trong production thay vì dùng tag quá rộng khi cần reproducibility.

### 2.4. Version hiện tại của binary cục bộ

~~~bash
mongod --version
mongos --version
~~~

Lệnh này chạy trên máy có binary, không cần kết nối database. Máy developer có thể cài binary 9.0 nhưng ứng dụng đang kết nối Atlas 8.0.

---

## 3. Kiểm tra phiên bản thực của server

### 3.1. Mongosh

~~~javascript
db.version();
~~~

Ví dụ kết quả minh họa:

~~~text
8.0.12
~~~

### 3.2. `buildInfo`

~~~javascript
db.adminCommand({
  buildInfo: 1
});
~~~

Command có thể trả các thông tin như `version`, build metadata, modules và environment. Hãy kiểm tra output thực thay vì tự suy ra từ URI.

### 3.3. `hello`

~~~javascript
db.adminCommand({
  hello: 1
});
~~~

Output có thể bao gồm thuộc tính topology và wire protocol như `maxWireVersion`/`minWireVersion`. Đây là thông tin driver sử dụng khi thực hiện handshake, nhưng **không tự là bảng tương thích sản phẩm**.

### 3.4. FCV

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

Ví dụ một deployment đang nâng cấp:

~~~javascript
{
  featureCompatibilityVersion: {
    version: "7.0"
  },
  ok: 1
}
~~~

Server binary có thể đã lên 8.0 nhưng FCV vẫn là 7.0 trong giai đoạn chuyển tiếp. Đây là trạng thái có chủ đích theo quy trình upgrade.

### 3.5. Lệnh riêng cho tự quản lý và Atlas

Trong Atlas, một số admin commands hoặc thông tin topology có thể bị giới hạn theo roles/service. Dùng Atlas UI/management API để xác nhận deployment version và upgrade state khi cần.

### 3.6. Điều gì không được chứng minh chỉ từ `db.version()`?

- Java driver đang dùng trong ứng dụng.
- Database Tools trên máy backup.
- FCV (phải kiểm tra riêng).
- Search/Vector Search infrastructure có sẵn.
- Quyền tạo index/backup.
- Network/DNS/TLS connectivity từ môi trường ứng dụng.
- Backup archive có thể restore vào target.

---

## 4. Feature Compatibility Version (FCV)

FCV là cơ chế của MongoDB kiểm soát **những tính năng ghi dữ liệu/persisted state có thể khiến dữ liệu không còn tương thích với binary bản cũ**. Không đồng nghĩa với binary version.

### 4.1. Ví dụ nâng từ 7.0 lên 8.0

~~~text
Trước upgrade:
  mongod binary = 7.0.x
  FCV = 7.0

Sau rolling binary upgrade:
  mongod binary = 8.0.x
  FCV vẫn = 7.0

Sau burn-in và quyết định chấp nhận features mới:
  mongod binary = 8.0.x
  FCV = 8.0
~~~

Điều này không có nghĩa mọi tính năng mới đều chờ FCV mới; một số feature gates liên quan version/service khác. Nhưng **persisted features không tương thích ngược** là lý do phải quản lý FCV.

### 4.2. Kiểm tra FCV trước upgrade

MongoDB 8.0 upgrade guide yêu cầu source 7.0 có FCV `7.0` trước khi nâng 8.0. MongoDB 8.2 upgrade guide yêu cầu source 8.0 có FCV `8.0` trước khi theo đường nâng lên 8.2.

Đừng nâng qua nhiều major/minor versions bằng cách thay binary một lần. Làm theo upgrade path chính thức của đúng source/target.

### 4.3. Thay FCV là thao tác quản trị có hệ quả

Ví dụ minh họa cho bản 8.0 khi đã hoàn tất upgrade:

~~~javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.0",
  confirm: true
});
~~~

**Không chạy lệnh này chỉ để thử.** Nó thay đổi compatibility state toàn deployment, có thể làm downgrade khó hoặc không còn được hỗ trợ theo policy.

### 4.4. Burn-in period

MongoDB khuyến nghị chạy các binaries mới với FCV cũ trong một giai đoạn burn-in thích hợp rồi mới bật features không tương thích ngược. Giai đoạn này dùng để:

- Theo dõi application errors.
- Kiểm tra query plan/latency.
- Xác minh backup/restore.
- Chạy canary business workflows.
- Đánh giá có cần rollback binary theo đường được hỗ trợ hay không.

### 4.5. Downgrade không chỉ “cài lại binary cũ”

Một schema/index/feature mới có thể ghi định dạng mà server cũ không hiểu. MongoDB 8.2/8.3/9.0 có các thay đổi chính sách downgrade theo phiên bản và edition, gồm khái niệm **single-version downgrade** hoặc yêu cầu hỗ trợ từ MongoDB Support.

Cần đọc đúng downgrade procedure cho **đích**, FCV, server edition và tính năng đã sử dụng. Không dùng một script downgrade chung cho mọi nhánh.

### 4.6. Phiên bản 9.0

Tài liệu upgrade MongoDB 9.0 mô tả bước thay binaries sang 9.0, chạy trong trạng thái chưa bật backward-incompatible features, rồi cân nhắc chuyển FCV sang `9.0` sau burn-in. Đây là **ví dụ về phân tách binary upgrade và FCV activation**, không phải lời khuyên nâng thẳng mọi deployment lên 9.0.

---

## 5. MongoDB Driver là gì?

Driver là thư viện ứng dụng dùng để kết nối tới MongoDB và chuyển các thao tác ngôn ngữ lập trình thành MongoDB commands qua wire protocol.

Ví dụ Java:

~~~java
MongoClient client =
    MongoClients.create(connectionString);

MongoDatabase db =
    client.getDatabase("shop");

MongoCollection<Document> orders =
    db.getCollection("orders");

long count =
    orders.countDocuments();

System.out.println(count);
~~~

Driver xử lý nhiều việc mà code ứng dụng không nên tự viết:

- Connection pooling.
- Server discovery/SDAM.
- Handshake/wire protocol.
- Authentication mechanisms được hỗ trợ.
- TLS.
- BSON codec/serialization.
- Read/write concerns.
- Retryable reads/writes theo điều kiện.
- Sessions và transactions.
- Replica set/sharded topology routing.
- Compression và command monitoring.

### 5.1. Driver version khác MongoDB Server version

Một Java Sync Driver `5.12.x` hoàn toàn có thể kết nối MongoDB Server `8.0`. Không có yêu cầu “driver 8.0 cho server 8.0”.

### 5.2. Hai tầng tương thích

1. **Protocol compatibility:** Driver có thể bắt tay, xác thực và gửi commands tới server không?
2. **Feature/API compatibility:** Driver expose API phù hợp với một tính năng server/version cụ thể không, server có hỗ trợ command đó không?

Một driver kết nối được có thể vẫn **chưa fully support một tính năng MongoDB mới**.

### 5.3. Các thư viện khác nhau

Node.js, Python/PyMongo, Go, C#, Java có release trains và support policies riêng. Bài dùng Java Sync Driver làm ví dụ nhưng quy tắc chung là tra **compatibility table của đúng driver/language**.

---

## 6. Bảng tương thích Java Sync Driver và MongoDB Server

MongoDB công bố **Client Library Compatibility Tables** với các ký hiệu:

- **✓ Fully supported:** driver version tương thích đầy đủ theo định nghĩa bảng với server branch.
- **⊛ Partially supported:** có thể kết nối/làm việc nhưng chưa hỗ trợ đầy đủ mọi features mới.
- **✗ Incompatible:** không hỗ trợ kết nối an toàn theo bảng.
- **Ô trống:** không được thử nghiệm/chưa có support trong bảng, **không** suy ra sẽ hoạt động.

### 6.1. Ví dụ theo bảng đang công bố trong 2026

| Java Driver version | MongoDB Server 9.0 | MongoDB Server 8.3 | MongoDB Server 8.1–8.2 | MongoDB Server 8.0 | MongoDB Server 7.0 |
|---|---|---|---|---|---|
| **5.12–5.13** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **5.9–5.11** | ⊛ | ✓ | ✓ | ✓ | ✓ |
| **5.8** | Chưa có dấu hỗ trợ trong bảng | ✓ | ✓ | ✓ | ✓ |
| **5.2–5.7** | Chưa có dấu hỗ trợ trong bảng | ⊛ | ✓ | ✓ | ✓ |

Đây là **trích lược hướng dẫn** của bảng để luyện cách đọc, không thay bảng gốc. Bảng chính thức còn có các server `6.0`, `5.0`, `4.4`, `4.2` và các driver releases khác. Nếu deploy mới, kiểm tra lại URL:

[MongoDB Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync)

### 6.2. Ví dụ ra quyết định

- Ứng dụng chuẩn bị dùng Server **9.0**: MongoDB docs khuyến nghị Java Driver **5.12+** để đầy đủ hỗ trợ cho 9.0 trong bảng đang công bố.
- Ứng dụng dùng Server **8.0**: bảng công bố Java Driver **5.2+** fully compatible trong những dòng tương ứng.
- Driver cũ hơn một mốc đề cập trong ví dụ không tự được coi là incompatible; phải tìm đúng dòng compatibility của nó trong bảng chính thức.

### 6.3. “Có dấu ✓” vẫn chưa đủ

Phải kiểm tra thêm:

- Tính năng muốn dùng có xuất hiện trong server patch/minor version không?
- Cấu hình deployment có hỗ trợ không?
- Java runtime đủ version?
- Spring Data/ORM tích hợp có support driver major này không?
- Phương thức auth/TLS/sessions có hợp với hạ tầng không?
- Driver đã được kiểm thử với framework và application schema chưa?

### 6.4. Không suy ra theo số lớn nhỏ

“Driver 5.9 kết nối được Server 9.0” **khác** với “5.9 hỗ trợ mọi tính năng 9.0”. Ngược lại, một tính năng của Server 8.0 có thể bị hạn chế bởi FCV, deployment hoặc permission chứ không do driver.

---

## 7. Java runtime compatibility

Java Driver cũng có **bảng Java version compatibility** riêng.

Theo bảng đang công bố:

- Nhóm Java Driver **4.11–5.13** được đánh dấu tương thích với Java **8, 11, 17, 21**.
- Một số nhóm 4.x cũ có dấu tương thích khác nhau.
- Java 4.5–4.10 trên Java 21 có lưu ý riêng về virtual threads.
- Các runtime Java cũ hơn có support hạn chế, không tự được chấp nhận cho driver mới.

### 7.1. Kiểm tra JVM

~~~bash
java -version
~~~

### 7.2. Kiểm tra driver dependency

Maven:

~~~xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>5.12.0</version>
</dependency>
~~~

Version **chỉ minh họa**. Dùng patch được xác minh trong dependency management của dự án. Nếu Spring Boot quản lý driver version, cần biết nó có đang override dependency hay không.

Gradle dependency declaration, chỉ để minh họa file build:

~~~groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:5.12.0"
}
~~~

Không cần chạy build để hiểu tương thích phiên bản; khi triển khai thật, build/integration tests là trách nhiệm workflow riêng.

### 7.3. Tránh jar conflict

Nếu classpath chứa đồng thời các version không tương thích của:

- `mongodb-driver-sync`.
- `mongodb-driver-core`.
- `bson`.
- Spring Data MongoDB dependencies.

ứng dụng có thể gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc codec/runtime errors dù server tương thích.

Ưu tiên một dependency BOM/management thống nhất, khóa các versions, không copy nhiều JAR thủ công.

### 7.4. Virtual threads và frameworks

Tương thích JVM không tự bảo đảm framework/app dùng virtual threads, reactive pipelines hoặc coroutine patterns theo cách tối ưu. Có thể cần xác minh driver và framework versions riêng.

---

## 8. Chọn driver trước khi nâng server

Ví dụ muốn nâng Server 8.0 lên 9.0:

~~~text
1. Ghi nhận driver/JVM/Spring versions đang chạy.
2. Đọc bảng compatibility cho Server 9.0.
3. Nâng driver lên version được hỗ trợ,
   trong khi Server vẫn ở 8.0 nếu matrix cho phép.
4. Canary ứng dụng với server hiện tại.
5. Staging nâng Server 9.0, FCV theo procedure.
6. Test application flows, failover, auth,
   query behavior và backup/restore.
7. Production rolling upgrade theo đúng topology.
8. Burn-in rồi mới bật FCV mới.
~~~

### 8.1. Vì sao nâng driver trước thường hữu ích?

Một driver version mới có thể hỗ trợ cả **server cũ và server mới**, giúp giảm số biến thay đổi cùng lúc. Nhưng không áp dụng vô điều kiện: nếu driver mới có breaking API/codec behavior, phải test ứng dụng trước.

### 8.2. Khi nào không đủ chỉ nâng driver?

Nếu một feature không được Server/FCV hỗ trợ, driver mới không làm server nhận thêm command. Ví dụ gửi aggregation stage mới tới binary cũ có thể báo `Unrecognized pipeline stage`.

### 8.3. Khi nào server nâng nhưng app cũ vẫn chạy?

Driver có thể hỗ trợ bản Server mới trong compatibility matrix. Tuy nhiên cần test reconnect/failover/retry, commands thực tế và các deprecations. Không coi “MongoClient.connect thành công” là end-to-end compatibility.

---

## 9. MongoDB Wire Protocol và capability negotiation

### 9.1. Handshake

Khi kết nối, driver khám phá topology và trao đổi thông tin server capability, ví dụ thông qua `hello`. Kết quả có các thông tin:

~~~javascript
{
  isWritablePrimary: true,
  minWireVersion: 0,
  maxWireVersion: 25,
  // fields khác tùy server/topology
}
~~~

**Các giá trị số trong ví dụ không phải cam kết version mapping.** Đừng hard-code `maxWireVersion` theo một bảng blog cũ rồi suy ra đầy đủ feature support.

### 9.2. Các lỗi có thể gặp

- Driver không hỗ trợ wire protocol range của server.
- Server selection timeout vì không tìm primary/router.
- DNS/SRV không resolve Atlas endpoint.
- Replica set name sai.
- TLS handshake/certificate error.
- Authentication mechanism/credentials sai.
- Proxy/load balancer định tuyến sai.

### 9.3. Đừng nhầm connectivity với compatibility

Nếu gặp `MongoTimeoutException` hoặc `MongoSocketException`, không vội kết luận server/driver version mismatch. Tìm lỗi gốc từ logs: DNS, TLS, auth, firewall và topology.

### 9.4. URI options cũng có version constraints

~~~text
mongodb+srv://...
mongodb://host1:27017,host2:27017/?replicaSet=rs0
~~~

`mongodb+srv` cần DNS SRV/TXT resolution và driver support. Một số connection string options mới chỉ có trong driver releases nhất định, không được server phiên bản cũ tự hiểu.

### 9.5. Mixed-version cluster trong rolling upgrade

Khi các nodes chạy phiên bản khác nhau trong khoảng upgrade được MongoDB hỗ trợ, client topology discovery và command routing vẫn phải tương thích. Không dùng feature mới đòi FCV mới giữa rolling process trước khi cluster hoàn thành nâng cấp và được phép bật feature.

---

## 10. Database Tools là gì?

MongoDB Database Tools là bộ tiện ích dòng lệnh độc lập, phục vụ backup/restore, import/export, thống kê và GridFS.

### 10.1. Những chương trình chính

| Tool | Mục đích | Tình huống |
|---|---|---|
| `mongodump` | Tạo BSON dump | Backup logical hoặc export dataset |
| `mongorestore` | Restore từ BSON dump | Phục hồi/migration có điều kiện |
| `bsondump` | Chuyển dump BSON thành JSON dễ đọc | Inspect diagnostic samples |
| `mongoexport` | Xuất JSON/CSV | Data interchange |
| `mongoimport` | Nhập JSON/CSV/TSV | ETL/import |
| `mongostat` | Tóm tắt số liệu hoạt động mongod/mongos | Chẩn đoán nhanh |
| `mongotop` | Thống kê thời gian reads/writes theo collection | Chẩn đoán I/O |
| `mongofiles` | Quản lý file GridFS | Upload/download/list/put/remove trong CLI |

### 10.2. Database Tools khác `mongosh`

- `mongosh` là shell để chạy queries/admin commands.
- `mongodump` không phải method gọi bên trong JavaScript shell.
- `mongorestore` chạy từ terminal/cmd/PowerShell.
- `bsondump` không yêu cầu một kết nối đang mở nếu chỉ đọc file BSON.
- Database Tools có release/version riêng với `mongosh` và Server.

### 10.3. Database Tools `100.x`

Kể từ MongoDB 4.4, Database Tools được phát hành **tách khỏi MongoDB Server**, dùng scheme version riêng, bắt đầu **100.0.0**.

Vì vậy:

~~~text
Server 8.0.x
Java Sync Driver 5.12.x
Database Tools 100.20.1
mongosh 2.x
~~~

là một tổ hợp **có thể** hợp lệ nếu tất cả điều kiện trong matrix đạt. Không đi tìm một bộ Database Tools `8.0.x` vì server 8.0.

### 10.4. Phiên bản Database Tools đang được tài liệu hóa

Tại thời điểm này, trang chính thức đang mô tả **Database Tools 100.20.1**. Bản này được liệt kê hỗ trợ các server:

- 9.0.
- 8.3.
- 8.2.
- 8.1.
- 8.0.
- 7.0.
- 6.0.
- 5.0.
- 4.4.
- 4.2.

Nó **không hỗ trợ** server trước 4.2 theo bảng đó. Đây là thông tin của **Tools 100.20.1**, không tự áp dụng cho mọi bản Tools 100.x cũ hay tương lai.

Nguồn: [MongoDB Database Tools Compatibility](https://www.mongodb.com/docs/database-tools/).

### 10.5. Kiểm tra local tools

~~~bash
mongodump --version
mongorestore --version
mongoexport --version
mongoimport --version
mongostat --version
mongotop --version
mongofiles --version
mongosh --version
~~~

Trên Windows PowerShell:

~~~powershell
Get-Command mongodump
Get-Command mongorestore
Get-Command mongosh
~~~

`Get-Command` xác định binary được PATH chọn. Có thể có hai bản cùng cài, một bản mới hơn nằm ở folder khác không được shell ưu tiên.

---

## 11. Bốn dạng “tương thích” cần phân biệt

Một cặp tool/server được gọi “tương thích” thường chỉ thể hiện một khía cạnh.

| Loại | Câu hỏi | Ví dụ |
|---|---|---|
| **Connection** | Có kết nối/auth/wire handshake được? | Driver đọc `hello` |
| **Command/API** | Command cụ thể tồn tại và được hỗ trợ? | `$vectorSearch`, index APIs |
| **Data format** | Dữ liệu/metadata/feature persisted có hiểu được? | BSON dump, FCV |
| **Operational** | Có đạt RPO/RTO, performance, security, correctness? | Restore production, index rebuild |

### 11.1. Database Tools hỗ trợ kết nối không bảo đảm restore mọi dump

`mongorestore 100.20.1` có thể hỗ trợ kết nối cả 7.0 lẫn 8.0, nhưng việc restore **dữ liệu tạo từ Server 8.0 về Server 7.0** có thể không được hỗ trợ. Phải xét source/target version/FCV và archive/metadata format.

### 11.2. Driver tương thích server không bảo đảm mọi feature

Java Driver 5.x có thể kết nối Server 8.0 nhưng một tính năng mới thuộc server 9.0 không tự chạy trên server 8.0.

### 11.3. FCV không thể biến server cũ thành server mới

Một Server 7.0 không trở thành 8.0 bằng việc gửi `setFeatureCompatibilityVersion:"8.0"`. FCV chỉ có thể đổi sang các giá trị server phiên bản hiện tại hỗ trợ theo quy trình.

### 11.4. Tool mới không thể thay backup policy

`mongodump` bản mới không tự tạo PITR nếu không có snapshot/oplog history retention system phù hợp.

---

## 12. Quy tắc restore MongoDB BSON dump: source, target và FCV

MongoDB Database Tools docs mô tả yêu cầu restore dump được tạo bởi `mongodump`:

- Source và target deployments nên chạy **cùng major version** hoặc **cùng Feature Compatibility Version** theo quy tắc docs.
- Tài liệu cũng lưu ý **BSON files** có thể được restore vào server cùng hoặc mới hơn, nhưng **không nên dùng restore vào server mới như quy trình nâng cấp Server được khuyến nghị**.
- Bảo đảm công cụ `mongorestore` dùng để đọc dump có **cùng Database Tools version** với `mongodump` đã tạo dump nếu có thể.

### 12.1. Vì sao hai rule có vẻ khác?

Tài liệu phân biệt **BSON collection data** với **metadata, archive và oplog replay files**. Quy tắc “BSON file có thể sang server mới hơn” **không bảo đảm**:

- Metadata indexes/collection options sẽ giữ đúng.
- Oplog replay an toàn giữa versions.
- Archive format tương thích tuyệt đối.
- Những features được persist sẽ được server cũ hiểu.

Do đó các kế hoạch production phải dựa vào điều kiện đầy đủ của nguồn/đích và nội dung backup.

### 12.2. Ví dụ nên làm

~~~text
Source: MongoDB 8.0 / FCV 8.0
Target: MongoDB 8.0 / FCV 8.0
Tools dump: 100.20.1
Tools restore: 100.20.1
~~~

Đây là kế hoạch ít biến số hơn về mặt version, nhưng vẫn cần kiểm tra topology, users/roles, encrypted data và data consistency.

### 12.3. Ví dụ phải kiểm tra kỹ

~~~text
Source: MongoDB 9.0
Target: MongoDB 8.0
~~~

Không suy rằng vì mongorestore tool hỗ trợ cả 8.0 và 9.0 nên dữ liệu 9.0 restore được vào 8.0. Những persisted features mới có thể không tương thích; đây **không phải downgrade route chuẩn**.

### 12.4. Nguyên tắc tránh “silent metadata corruption”

MongoDB docs cảnh báo với restore metadata/archive/oplog files giữa những version source/target khác nhau có thể gây failure, silent failure hoặc corrupted metadata. Không chấp nhận chỉ vì process exit code 0; cần restore thử, kiểm tra indexes, validators, data types và business invariants.

---

## 13. `mongodump` và `mongorestore`: ví dụ có kiểm soát

### 13.1. Dump một database

~~~bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --db=shop \
  --out=./backups/shop
~~~

Đây là ví dụ chạy terminal Linux/macOS, không phải mongosh. Với dữ liệu nhạy cảm cần bảo vệ backup file, process arguments/URI và quyền truy cập storage.

### 13.2. Dump archive nén

~~~bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --archive=./backups/shop-all.archive.gz \
  --gzip
~~~

### 13.3. Restore vào cluster thử nghiệm

~~~bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --archive=./backups/shop-all.archive.gz \
  --gzip
~~~

**Cẩn thận:** Dump toàn deployment có thể chứa nhiều databases; đừng chạy vào target có dữ liệu quan trọng khi chưa kiểm tra namespaces và restore options. Với backup nhỏ/lab, bạn có thể tạo target database trống.

### 13.4. Restore chọn namespace

~~~bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --nsInclude="shop.orders" \
  --nsFrom="shop.orders" \
  --nsTo="recovery.orders" \
  ./backups/shop
~~~

Mục đích là copy collection vào namespace tạm, không overwrite production. Cần kiểm tra format directory và namespace mapping thật.

### 13.5. `--drop` có nguy cơ gì?

`mongorestore --drop` xóa collection target liên quan trước khi restore để tránh duplicates. Trên production, option này có thể làm mất writes mới. Chỉ dùng trong kế hoạch có xác nhận scope, backup của target và phê duyệt.

### 13.6. Quyền truy cập

`mongodump` cần quyền đọc các collections; `mongorestore` cần quyền tạo/ghi indexes/metadata phù hợp. Database Tools connection success chưa chứng minh roles đủ thực hiện mọi lệnh.

---

## 14. `--oplog` và `--oplogReplay`

### 14.1. Tại sao dùng oplog khi dump?

Một full logical dump của replica set có thể kéo dài trong khi ứng dụng vẫn ghi. `mongodump --oplog` lưu oplog entries phát sinh trong dump window, giúp `mongorestore --oplogReplay` đưa dump về trạng thái nhất quán theo cơ chế hỗ trợ.

### 14.2. Ví dụ lab replica set

~~~bash
mongodump \
  --uri="$REPLICA_SET_SOURCE_URI" \
  --oplog \
  --archive=./backup-rs.archive.gz \
  --gzip
~~~

Restore vào target **cách ly**:

~~~bash
mongorestore \
  --uri="$REPLICA_SET_TARGET_URI" \
  --archive=./backup-rs.archive.gz \
  --gzip \
  --oplogReplay
~~~

### 14.3. Giới hạn kỹ thuật quan trọng

- `--oplog` áp dụng cho **full dump** của replica set theo điều kiện docs, không tùy ý kết hợp `--db`/`--collection`/`--query`.
- `mongorestore --oplogReplay` không cho phép một số namespace-limiting options như `--db`, `--collection`, `--nsInclude`/`--nsExclude`/`--nsFrom`/`--nsTo` trong chế độ replay full dump.
- **Sharded clusters không hỗ trợ** `mongorestore --oplogReplay` theo cách này.
- Các thay đổi FCV có thể dẫn đến chuyển đổi định dạng time-series collection giữa các phiên bản (ví dụ khi chuyển 8.x ↔ 9.0), tạo ràng buộc đặc biệt cho oplog replay.
- `--oplogReplay` chỉ replay những oplog entries có trong backup, không tạo continuous arbitrary PITR.

### 14.4. Không nhầm với Change Streams

Oplog và Change Streams liên quan lịch sử thay đổi nhưng Change Stream consumer checkpoint không phải file backup đảm bảo restore toàn database. Source restore và consumer checkpoint còn ở tương lai phải được xử lý riêng.

### 14.5. Giới hạn theo Atlas tier

Một số command options của Database Tools có hạn chế trên các Atlas tiers như Free/Flex. Chọn backup/restore path theo **deployment type/tier**, không chỉ server version và tool version.

---

## 15. `mongoexport/mongoimport` không thay `mongodump/mongorestore`

### 15.1. Dùng để trao đổi dữ liệu

~~~bash
mongoexport \
  --uri="$MONGODB_URI" \
  --db=shop \
  --collection=products \
  --type=json \
  --out=products.json
~~~

~~~bash
mongoimport \
  --uri="$MONGODB_URI" \
  --db=shop \
  --collection=products_imported \
  --file=products.json
~~~

### 15.2. BSON type fidelity

BSON có các kiểu `ObjectId`, `Decimal128`, `Date`, `Binary`, `Timestamp`, `Int64`. JSON thông thường không diễn đạt trực tiếp đầy đủ các kiểu này.

MongoDB Extended JSON v2 (canonical/relaxed) biểu diễn nhiều kiểu BSON, nhưng vẫn cần chọn format và hiểu parsing semantics. CSV càng làm mất tính phong phú kiểu dữ liệu/arrays/documents nested.

### 15.3. Không mặc định import/export là backup đầy đủ

`mongoexport` không phải thay thế an toàn cho `mongodump` khi cần:

- Collection options.
- Index definitions.
- Validators/collations.
- Raw BSON type precision.
- Atomic point-in-time consistency.
- Oplog-based restore.
- Database privileges/users/roles theo policy.
- GridFS binary data ở hai collections.

### 15.4. Dấu chấm và dollar-prefixed field names

MongoDB 5.0+ có support field names chứa dấu chấm và bắt đầu bằng `$` trong những trường hợp nhất định. MongoDB docs cảnh báo một số trường hợp `mongoimport/mongoexport` xử lý những tên field này không phù hợp/ambiguous, nhất là CSV và Extended JSON wrappers.

Không suy rằng một JSON round-trip sẽ bảo toàn 100% BSON document với keys đặc biệt. Kiểm tra trước khi dùng như migration path.

### 15.5. CSV và numbers

Nếu `Decimal128("12.30")` được xuất ra CSV rồi import theo inference sai, có thể thành string/double hoặc mất precision. Với tiền, cần schema kiểm tra numeric type sau import.

---

## 16. `bsondump`, `mongostat`, `mongotop`, `mongofiles`

### 16.1. `bsondump`

~~~bash
bsondump ./backups/shop/orders.bson
~~~

Dùng để inspect BSON dump dưới dạng JSON để hỗ trợ chẩn đoán. Không dùng `bsondump` làm backup mới rồi cho rằng JSON giữ nguyên mọi metadata.

### 16.2. `mongostat`

~~~bash
mongostat --uri="$MONGODB_URI"
~~~

Hữu ích để quan sát hoạt động chung. Output/metrics phụ thuộc Server/Tools version, privilege và deployment. Không thay Prometheus/Atlas monitoring dài hạn.

### 16.3. `mongotop`

~~~bash
mongotop --uri="$MONGODB_URI"
~~~

Dùng để thấy thời gian dành cho read/write theo collection trong deployment phù hợp. Không mặc định tool có quyền/khả năng chạy trong mọi Atlas môi trường.

### 16.4. `mongofiles`

Tool quản lý GridFS files ở CLI, ví dụ liệt kê và tải về theo tên/định danh theo các options được docs hỗ trợ. Các thao tác GridFS cần lưu ý filenames không unique và multiple revisions; không dùng `mongofiles` thay API quản lý version/tenant logic của ứng dụng.

### 16.5. Database Tools compatibility vẫn khác feature compatibility

Một bản `mongostat` có thể kết nối server nhưng một metric cụ thể đã được đổi tên hoặc yêu cầu role cao hơn. Một bản `mongofiles` có thể xử lý bucket nhưng không thay business retention/versioning. Test thao tác cụ thể.

---

## 17. Kiểm tra cài đặt trên Linux, Windows và container

### 17.1. Linux

MongoDB cung cấp packages tách biệt như:

~~~text
mongodb-org-server        -> mongod
mongodb-org-mongos        -> mongos
mongodb-mongosh           -> mongosh
mongodb-database-tools    -> Database Tools
~~~

Một meta-package có thể cài nhiều phần, nhưng versions từng phần vẫn độc lập theo packaging. Đừng chỉ nhìn `dpkg -l mongodb-org` rồi suy ra chính xác version của mọi binary.

### 17.2. Windows

PowerShell:

~~~powershell
Get-Command mongod
Get-Command mongosh
Get-Command mongodump

mongod --version
mongosh --version
mongodump --version
~~~

Nếu `mongodump` báo command not found, có thể Database Tools chưa cài hoặc folder chưa nằm trong PATH; không suy rằng MongoDB Server không hỗ trợ dump.

### 17.3. Docker

~~~bash
docker run --rm mongo:8 mongod --version
~~~

Container có server binary; **không mặc định** container này có đúng Database Tools/mongosh mong muốn. Tùy image/tag/release, cần image riêng hoặc cài tools tương ứng.

### 17.4. CPU architecture

Database Tools packages được hỗ trợ theo OS/architecture combinations như x86_64/ARM64 và một số Linux architectures. Không giả định một archive build cho Ubuntu x86_64 sẽ chạy trên macOS ARM64 hoặc Alpine musl.

### 17.5. Pin versions

Trong CI/production, lưu chính xác:

- Server image/package tag và digest nếu có.
- Database Tools 100.x version.
- mongosh version.
- Java driver/BSON artifacts.
- JVM version.
- OS/CPU architecture.
- MongoDB Operator/Atlas API version nếu liên quan.

---

## 18. Kế hoạch nâng cấp một ứng dụng Java + MongoDB Server

### 18.1. Trước khi thay đổi

Ghi baseline:

~~~yaml
service: order-api
environment: staging
server:
  binaryVersion: "8.0.x"
  fcv: "8.0"
  topology: replica-set
driver:
  language: java-sync
  version: "5.12.x"
  javaRuntime: "21"
databaseTools:
  dumpVersion: "100.20.1"
  restoreVersion: "100.20.1"
target:
  serverVersion: "9.0.x"
  fcvAfterBurnIn: "9.0"
  backupRestoreTested: true
~~~

Đây là **manifest minh họa**, không phải cấu hình Atlas/MongoDB Server được engine hiểu trực tiếp.

### 18.2. Bước 1 — Đọc compatibility và release notes

- Chọn source/target versions cụ thể.
- Kiểm tra Java driver compatibility table.
- Kiểm tra JVM/framework support.
- Đọc Server upgrade/downgrade procedures.
- Đọc Database Tools compatibility của bản dùng làm backup.
- Xem feature compatibility changes và các deprecations.

### 18.3. Bước 2 — Thử nâng driver riêng

Nâng driver trên staging/khả năng canary nhưng giữ server cũ. Kiểm tra:

- Connectivity và auth.
- CRUD.
- Aggregation.
- Index creation/listing theo quyền.
- Transactions và retry.
- Change Streams.
- Serialization (ObjectId/Date/Decimal128/UUID).
- Timeouts và connection pool.
- TLS/SRV.
- Failure recovery.

### 18.4. Bước 3 — Backup và restore thử

Dùng backup thực tế, restore vào target cách ly, kiểm tra data/metadata và ứng dụng. Không coi backup success là restore proof.

### 18.5. Bước 4 — Nâng server theo topology

- Standalone: theo standalone upgrade guide.
- Replica set: theo rolling upgrade guide chính thức, kiểm tra member eligibility/election.
- Sharded: theo sharded cluster upgrade guide, thứ tự config servers/shards/mongos phải theo phiên bản hướng dẫn.
- Atlas: sử dụng Atlas upgrade workflow/maintenance windows, không SSH thay binary theo hướng self-managed.

### 18.6. Bước 5 — Burn-in với FCV cũ

Theo dõi các metrics/traces/smoke tests. Không dùng persisted features mới không tương thích trước khi quyết định final FCV.

### 18.7. Bước 6 — Chuyển FCV theo đúng procedure

Đây là thay đổi quản trị có thể ảnh hưởng downgrade. Không thực hiện trước khi có approval và backup/rollback plan.

### 18.8. Bước 7 — Post-upgrade validation

Xác nhận:

- Server versions của tất cả members/routers.
- FCV đồng nhất và đúng.
- Replica set/shard health.
- Java app operations.
- Change Stream consumers.
- Search index/Vector Search readiness khi liên quan.
- Backup jobs và restore test.
- p95/p99 latency, connection pool, errors.
- Security/audit compliance.

---

## 19. Nâng cấp replica set và mixed-version window

### 19.1. Không cập nhật tất cả nodes một lúc

Một rolling upgrade theo tài liệu có thể thay binaries trên secondaries theo thứ tự được hướng dẫn, chuyển leadership khi cần, rồi cập nhật primary. Nhưng **trình tự chi tiết thay đổi theo phiên bản/topology**, không copy một lệnh tự xây chung.

### 19.2. Mixed-version mode là tạm thời

Trong khoảng rolling upgrade, cluster có thể có members thuộc hai versions được cho phép đồng thời. Đây là trạng thái chuyển tiếp, không phải kiến trúc lâu dài.

### 19.3. Driver phải xử lý election/SDAM

Application cần dự phòng các lỗi transient khi primary thay đổi; driver dùng topology discovery, retryable operations theo điều kiện. Mọi business writes quan trọng cần idempotency keys để tránh duplicate side effects nếu retry.

### 19.4. Không bật FCV mới giữa upgrade

FCV upgrade thường chỉ thực hiện **sau khi** binaries/topology đã hoàn thành theo procedure và burn-in phù hợp. Bật sớm có thể làm incompatible writes/metadata khiến rollback bất khả thi.

### 19.5. Backup trước upgrade

Sao lưu có thể khôi phục được, có tài liệu restore thử và key access. Snapshot gần nhất không đủ nếu không biết có thể dựng target với version/FCV cũ tương ứng.

---

## 20. Nâng cấp sharded cluster

### 20.1. Components

~~~text
Application
    |
   mongos
    |
    +-- Config Server Replica Set
    |
    +-- Shard 1 Replica Set
    +-- Shard 2 Replica Set
    +-- Shard 3 Replica Set
~~~

### 20.2. Vì sao khó hơn standalone?

- Server binaries có ở config server, shard members và mongos.
- Metadata sharding và routing cache liên quan.
- Chunk migrations/balancer/resharding.
- Cross-shard transactions và change streams.
- Tools backup/restore cũng cần hiểu sharded topology.

### 20.3. Trình tự không nên đoán

Không thể chỉ chạy upgrade trên `mongos` trước rồi mongod ở bất kỳ thứ tự nào. Phải theo **upgrade instructions chính thức** của source/target, gồm trạng thái balancer/feature compatibility và preconditions.

### 20.4. `mongodump --oplog` không là full sharded backup

Không ghép các full dumps của từng shard rồi giả định đó là một recovery point nhất quán toàn cluster. Dùng backup solution/consistency procedure hỗ trợ sharded clusters.

### 20.5. Driver có thể vẫn kết nối được trong một phần upgrade

Nhưng các operations nhạy cảm như transactions, change streams, new feature calls hoặc chunk migration có thể có additional constraints. Integration tests phải phản ánh sharded workloads thật.

---

## 21. Atlas khác self-managed khi nâng cấp

### 21.1. Atlas

- Atlas quản lý server provisioning, nodes và upgrade workflow.
- Maintenance windows/auto upgrades tùy tier/contract.
- Một số admin operations bị hạn chế.
- Restore/backup functionality phụ thuộc cluster tier và plan.
- Search/Vector Search có deployment capabilities riêng.
- Không sửa binary trực tiếp trên managed hosts.

### 21.2. Self-managed

- Đội vận hành chịu trách nhiệm OS packages, mongodb binaries và procedures.
- Kiểm soát FCV, topology, snapshots, backup tools và downtime.
- Phải chuẩn bị upgrade rollback path theo supported policy.
- Tự quản lý TLS, users, storage và monitoring.

### 21.3. Dev laptop không phải production

Kết nối local standalone và restore 1 GiB thành công không chứng minh sharded production 5 TiB có RTO phù hợp. Nên test trên staging có topology, indexes, size và roles tương tự.

---

## 22. Chẩn đoán lỗi Server/Driver

### 22.1. Wire version mismatch

Triệu chứng: driver không hỗ trợ wire protocol range hoặc thông báo server wire version không tương thích.

Cách xử lý:

1. Lấy driver version chính xác từ dependency/runtime.
2. Lấy `db.version()` và `hello` của server.
3. Đối chiếu Client Library Compatibility Tables.
4. Nâng driver theo compatibility matrix; không sửa `maxWireVersion` bằng hard-code.
5. Test lại cùng JVM/framework.

### 22.2. `MongoTimeoutException`

Không mặc định là version mismatch. Có thể do:

- DNS/SRV lỗi.
- Firewall/IP allowlist.
- TLS.
- Replica set name/URI sai.
- No primary.
- Connection pool exhaustion.
- Network routing/latency.
- Server saturation.

### 22.3. Authentication failure

Driver/server có thể không chia sẻ auth mechanism mong muốn, hoặc credentials/authSource sai. Xem mã lỗi và auth mechanism docs; không tắt authentication chỉ để test production.

### 22.4. TLS handshake failure

Kiểm tra CA, certificate hostname/SAN, TLS versions, JDK truststore, server cert rotation. Đừng tắt TLS certificate validation trong production.

### 22.5. Unsupported command/stage

Nếu Java gửi command mới nhưng Server cũ báo unrecognized, cần server capability/tier/FCV tương ứng. Driver update không tự giải quyết.

### 22.6. Serialization errors

`CodecConfigurationException`, `ClassCastException`, `NoSuchMethodError` có thể do codec/POJO mapping hoặc dependency conflict, không phải do server version trực tiếp. Kiểm tra dependency graph và BSON type changes.

---

## 23. Chẩn đoán lỗi Database Tools

### 23.1. `mongodump: command not found`

Tool chưa cài hoặc PATH chưa chứa binary. Không đồng nghĩa MongoDB Server không hỗ trợ backup.

### 23.2. Tool chỉ ra version 100.x

Đây là version độc lập; không phải lỗi vì Server version 8.x/9.x khác.

### 23.3. Không kết nối server

Kiểm tra URI, TLS, auth, DNS và supported server versions của đúng Tools release. Phân biệt connection error với dữ liệu dump không tương thích.

### 23.4. `mongorestore --oplogReplay` lỗi

Kiểm tra backup được tạo bằng full `mongodump --oplog`, topology replica set, archive chứa oplog, namespace options có bị kết hợp sai và version/FCV conversion issues.

### 23.5. Duplicate keys khi restore

Nếu target đã có documents/indexes, restore thêm có thể gặp duplicate `_id` hoặc unique index conflict. Restore vào target trống hoặc chọn overwrite có kế hoạch, không vô tình bật `--drop`.

### 23.6. Dump cũ restore sang target mới

BSON files có compatibility khác metadata/archives/oplog. Dùng đúng phiên bản Database Tools tạo dump để restore nếu có thể, kiểm tra server/FCV source/target, thực hiện isolated restore và validation.

### 23.7. `mongoimport` làm thay BSON types

Kiểm tra `--type`, `--jsonFormat`/Extended JSON input, field types, CSV options và precision. Đừng dùng CSV round-trip cho financial data mà không có schema validation.

### 23.8. Failed restore không chỉ là process exit

Một số metadata/definitions có thể không phù hợp dù documents xuất hiện. Kiểm tra validators, indexes, TTL, collation, collections options và application invariants.

---

## 24. Tương thích của tính năng nâng cao

### 24.1. Transactions

Cần Server topology/version hỗ trợ và driver sessions/transaction APIs phù hợp. Không giả định một standalone mongod cũ hỗ trợ multi-document transaction chỉ vì Java Driver có `ClientSession`.

### 24.2. Change Streams

Đòi deployment/topology phù hợp và có oplog/change history. Khi nâng server hoặc restore, resume tokens có thể không hợp lệ nếu history mất hoặc source đã rollback. Cần bootstrap/reconcile consumers.

### 24.3. Time-series collections

Tính năng này có thay đổi giữa major versions, kể cả persisted format/FCV. Database Tools docs có cảnh báo về `mongorestore --oplogReplay` khi oplog range đi qua một lần time-series format conversion giữa 8.x và 9.0.

### 24.4. Search/Vector Search

Một Java Driver có thể gửi aggregation `$vectorSearch` nhưng tính năng còn phụ thuộc server/deployment/search service/indexes và patch-version support. Self-managed/Atlas availability có ngưỡng riêng; không suy chỉ từ driver compatible.

### 24.5. Queryable Encryption / CSFLE

`mongorestore` có những hạn chế với collections sử dụng Queryable Encryption hoặc Client-Side Field Level Encryption theo tài liệu hiện hành. Nếu hệ thống dùng encryption, hãy làm theo backup/restore procedures chuyên biệt, kèm KMS/key management; không dùng generic dump/restore mà chưa kiểm tra.

### 24.6. Indexes và schema validation

Một index/validator được tạo bằng feature mới có thể khiến downgrade/restore vào server cũ thất bại. Đọc release notes và feature compatibility changes trước khi rollback.

### 24.7. UUID/BSON representation

Các ngôn ngữ/driver versions có quy tắc UUID representation khác nhau. Khi migrate Java Driver hoặc import/export, xác định binary subtype/UUID representation để không làm lookup sai IDs. Tạo round-trip tests cho UUID, ObjectId, Decimal128, ZonedDateTime/Instant, arrays và null/missing.

---

## 25. Runtime Java: kiểm tra driver version đang dùng

### 25.1. Phụ thuộc khai báo chưa chắc là phụ thuộc runtime

Maven/Gradle dependency management có thể resolve version khác với version bạn nghĩ. Framework và transitive dependencies có thể override; container có thể dùng artifact cũ.

### 25.2. Ví dụ đọc package metadata

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public class DriverDiagnostics {

    public static void main(String[] args) {
        Package p = MongoClient.class.getPackage();

        System.out.println(
            "Implementation version: "
            + p.getImplementationVersion()
        );

        String uri =
            System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "Missing MONGODB_URI"
            );
        }

        try (MongoClient client =
                 MongoClients.create(uri)) {

            System.out.println(
                client.getDatabase("admin")
                    .runCommand(
                        new org.bson.Document("ping", 1)
                    )
                    .toJson()
            );
        }
    }
}
~~~

**Lưu ý:** Package `ImplementationVersion` có thể null tùy cách JAR được build; không coi nó là cách duy nhất. Với production, còn phải đối chiếu resolved dependency tree/build manifest.

### 25.3. Không log secrets

Khi chẩn đoán, không in connection URI chứa password/token ra logs. Dùng configuration redaction và credential management.

### 25.4. Connection pool và timeout changes

Sau driver major upgrade, kiểm tra connection pool sizing, default timeouts, retry behavior, compression và telemetry. Tương thích server không chứng minh performance giống hệt phiên bản cũ.

---

## 26. Smoke test sau nâng server/driver

Một smoke test nên kiểm tra nhiều hơn `ping`.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoSmokeTest {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI required"
            );
        }

        try (MongoClient client =
                 MongoClients.create(uri)) {

            MongoDatabase db =
                client.getDatabase(
                    "mongo_compat_lab"
                );

            db.runCommand(
                new Document("ping", 1)
            );

            MongoCollection<Document> coll =
                db.getCollection("smoke");

            String testId =
                "smoke-test-2026-11-14";

            coll.updateOne(
                new Document("_id", testId),
                new Document(
                    "$set",
                    new Document(
                        "kind", "COMPAT"
                    )
                ),
                new com.mongodb.client.model
                    .UpdateOptions()
                    .upsert(true)
            );

            Document found =
                coll.find(
                    new Document(
                        "_id", testId
                    )
                ).first();

            if (found == null) {
                throw new IllegalStateException(
                    "Read after write failed"
                );
            }

            System.out.println(
                "CRUD smoke test passed"
            );
        }
    }
}
~~~

Đây là ví dụ chạy trên **database lab/staging**; không tạo dữ liệu kiểm thử trong collection production mà chưa có kiểm soát. Khi triển khai, thêm tests có cleanup và không dùng ID cố định có thể va chạm giữa test runners.

### 26.1. Bộ tests rộng hơn

- CRUD với read/write concern.
- Aggregation indexes.
- Multi-document transaction nếu nghiệp vụ dùng.
- Change stream resume/restart.
- Retryable writes/failover.
- Decimal128/UUID/Date serialization.
- TTL/unique indexes.
- Atlas Search/Vector Search nếu có.
- Auth/TLS/SRV và pool saturation.
- Backup/restore sau nâng cấp.

---

## 27. Khác biệt giữa kiểm thử kết nối và kiểm thử dữ liệu

### 27.1. Kết nối được

~~~text
Driver -> TLS/auth/hello -> server OK
~~~

Điều này chỉ chứng minh đường kết nối cơ bản.

### 27.2. CRUD đúng

Mọi BSON types, unique constraints, codecs và read/write concerns phải hoạt động.

### 27.3. Business consistency

Order/payment/inventory đúng bất biến; trigger/events và retry không gây duplicate. Một server mới có thể trả query plan khác khiến latency thay đổi nhưng kết quả vẫn đúng, hoặc một migration driver có thể đổi UUID handling khiến query không tìm được document.

### 27.4. Backup/restore đúng

Dump của Server sau nâng cấp có thể cần target/FCV/Tools khác. Bảo đảm có một bản backup và target restore thực sự tương thích, không chỉ “job ghi file thành công”.

---

## 28. Restore drill với hai phiên bản Database Tools

### 28.1. Không trộn versions vô tình

Ví dụ đội A tạo archive bằng `mongodump 100.20.1`, đội B restore bằng `mongorestore 100.5.x` vì máy CI cũ.

Dù có trường hợp hoạt động, tài liệu khuyến nghị **cùng version** dump/restore để tránh thay đổi định dạng archive/metadata.

### 28.2. Quy trình an toàn

1. Ghi công cụ tạo dump: `mongodump --version`.
2. Ghi source Server binary + FCV.
3. Ghi deployment topology.
4. Lưu checksum của archive/BSON files.
5. Ghi options dump (`--oplog`, `--archive`, `--gzip`, filters).
6. Cài cùng tool version để restore.
7. Target được tạo với Server/FCV tương thích.
8. Restore thử trong isolated environment.
9. So sánh counts, selected records, indexes, validators, GridFS contents nếu có.
10. Ghi elapsed time, errors và business sign-off.

### 28.3. RPO/RTO

Một bản dump 100.x được tạo thành công không tự bảo đảm RPO/RTO. Thời gian restore logical BSON vào cluster lớn có thể kéo dài và không bao gồm index/search rebuild, validation, cutover.

---

## 29. Ma trận quyết định mẫu

| Tình huống | Hướng đánh giá | Điểm nguy hiểm |
|---|---|---|
| Server 8.0 + Java Driver 5.12 | Bảng driver hỗ trợ | Feature-specific gates |
| Server 9.0 + Java Driver 5.9 | Partially compatible theo bảng | Không đủ mọi 9.0 features |
| Server 9.0 + Java Driver 5.12 | Fully compatible theo bảng | Vẫn cần JVM/framework/feature tests |
| Server 8.0 + Tools 100.20.1 | Tools hỗ trợ server 8.0 | Dump source/target FCV riêng |
| Server 4.0 + Tools 100.20.1 | Ngoài server support list | Không dùng cho production |
| Dump 8.0 → Restore 8.0 cùng FCV | Dễ kiểm soát hơn | Vẫn kiểm tra encrypted data/indexes |
| Dump 9.0 → Restore 8.0 | Không tự suy tương thích | Persisted format mới/downgrade |
| JSON export → import | Dữ liệu exchange | BSON type/metadata loss |
| `--oplogReplay` trên sharded cluster | Không hỗ trợ theo tài liệu | Không tạo consistent cluster restore |
| Server nâng nhưng FCV cũ | Trạng thái chuyển tiếp phù hợp procedure | Feature mới có thể chưa bật |
| FCV mới bật trước burn-in | Rủi ro downgrade | Backward-incompatible persisted state |
| Atlas Search index restore | Tùy restore mode | Index data có thể rebuild/sync |

Bảng là **phương pháp tư duy**, không thể thay verification ở môi trường thật.

---

## 30. Những hiểu lầm thường gặp

**Sai lầm 1:** “Server 8.0 cần Java Driver 8.0.”  
Driver dùng release train độc lập, xem bảng hỗ trợ.

**Sai lầm 2:** “Tools 100.x nghĩa là Server 100.x.”  
Database Tools tách version từ MongoDB 4.4.

**Sai lầm 3:** “mongosh --version cho biết version Atlas.”  
Chỉ cho biết shell local.

**Sai lầm 4:** “db.version() cho biết driver và tools version.”  
Chỉ server version của endpoint.

**Sai lầm 5:** “Server binary nâng là FCV tự lên.”  
FCV có giai đoạn chuyển tiếp theo procedure.

**Sai lầm 6:** “Nâng FCV không ảnh hưởng downgrade.”  
FCV có thể cho phép persisted features không tương thích ngược.

**Sai lầm 7:** “Driver kết nối được là mọi feature support.”  
Có fully/partially compatible và feature gates.

**Sai lầm 8:** “Ô trống trong bảng driver nghĩa là hoạt động.”  
Không được thử nghiệm hoặc không có dấu hỗ trợ; không tự suy.

**Sai lầm 9:** “Driver version càng lớn luôn chạy đúng mọi server cũ.”  
Kiểm tra EOL/compatibility table, API/binary changes.

**Sai lầm 10:** “Java runtime nào cũng chạy cùng driver.”  
Cần đối chiếu JVM compatibility.

**Sai lầm 11:** “Maven đã khai version X nên runtime chắc dùng X.”  
Có dependency management, transitive conflicts hoặc artifact cũ.

**Sai lầm 12:** “NoSuchMethodError là lỗi MongoDB Server.”  
Có thể là JAR version conflict.

**Sai lầm 13:** “Wire protocol handshake thành công chứng minh business data đúng.”  
Cần CRUD/codec/schema/transaction tests.

**Sai lầm 14:** “mongodump 100.x hỗ trợ Server 9.0 nên dump 9.0 restore được vào Server 7.0.”  
Connection support khác data/FCV compatibility.

**Sai lầm 15:** “mongoexport JSON dùng thay backup BSON.”  
Có nguy cơ mất fidelity/metadata/index definitions.

**Sai lầm 16:** “--oplogReplay biến full dump thành PITR không giới hạn.”  
Chỉ replay oplog entries trong dump, có constraints.

**Sai lầm 17:** “Sharded cluster dùng --oplogReplay như replica set.”  
Không hỗ trợ theo cách đó.

**Sai lầm 18:** “Có archive là restore chắc chắn được.”  
Cần tool version, source/target version/FCV, integrity/key access.

**Sai lầm 19:** “Database Tools nằm sẵn trong mọi MongoDB Docker image.”  
Phải kiểm tra binary cụ thể.

**Sai lầm 20:** “Mọi MongoDB 8.x releases có cùng hỗ trợ tính năng.”  
Phụ thuộc release train, patch, edition và deployment.

**Sai lầm 21:** “Production nâng cấp thì thay tất cả nodes cùng lúc.”  
Theo rolling/upgrade procedure đúng topology.

**Sai lầm 22:** “Thay version sau nâng cấp là rollback đơn giản.”  
Phụ thuộc FCV và persisted incompatibilities.

**Sai lầm 23:** “Atlas upgrade giống self-managed SSH thay binary.”  
Atlas là managed deployment.

**Sai lầm 24:** “Kết quả restore documents đủ, không cần index/validation.”  
Metadata/query readiness có thể thiếu hoặc sai.

**Sai lầm 25:** “Một lần test ping ở staging là đủ.”  
Cần backup/restore và business integration tests dưới tải thực.

---

## 31. Checklist trước nâng cấp

### 31.1. Khảo sát môi trường

- [ ] Source Server version, patch, topology và edition.
- [ ] Target Server version, supported upgrade path.
- [ ] FCV hiện tại và FCV mục tiêu.
- [ ] Java Driver version thực tế.
- [ ] JVM version/Spring Data/framework compatibility.
- [ ] Database Tools versions tạo và restore dump.
- [ ] mongosh/Atlas CLI versions.
- [ ] OS/CPU architecture và container image.
- [ ] Authentication/TLS/URI/DNS/SRV.
- [ ] Search/Vector Search, encryption, time-series, transactions, sharding.
- [ ] RPO/RTO và business recovery scope.

### 31.2. Kiểm tra tương thích

- [ ] Driver/server matrix có dấu hỗ trợ thích hợp.
- [ ] Feature-specific minimum Server versions.
- [ ] FCV preconditions cho đường upgrade.
- [ ] Server downgrade policy tương ứng.
- [ ] Tool/server compatibility của Database Tools version.
- [ ] Source/target dump major version/FCV.
- [ ] Dump/restore dùng cùng Database Tools version khi có thể.
- [ ] Oplog/sharded constraints.
- [ ] BSON/Extended JSON type semantics.
- [ ] Permissions và encryption key access.

### 31.3. Staging/canary

- [ ] CRUD + aggregation + unique index.
- [ ] Transactions/change streams nếu có.
- [ ] Codec round trip (ObjectId, UUID, Decimal128, date).
- [ ] TLS/auth/network failure.
- [ ] Retryable writes/failover.
- [ ] Search/Vector Search readiness.
- [ ] Query latency p95/p99 under load.
- [ ] Backup created and restore verified.
- [ ] Driver dependency graph đồng nhất.
- [ ] Rollback decision window rõ ràng.

### 31.4. Production rollout

- [ ] Maintenance/notification plan.
- [ ] Backup/snapshot preflight.
- [ ] Tuân thủ rolling/sharded procedure chính thức.
- [ ] Burn-in trước khi thay FCV.
- [ ] Canary traffic và alerts.
- [ ] Kiểm tra tất cả nodes/routers đã nâng.
- [ ] Recovery runbook và nhân sự trực.
- [ ] Post-upgrade backup/restore test.
- [ ] Business sign-off.

---

## 32. Bài tập thực hành

### Bài tập 1 — Phân biệt versions

Hệ thống có Server 8.0, FCV 7.0, Java Driver 5.12, Tools 100.20.1 và mongosh 2.x. Giải thích vì sao không có “mismatch version” chỉ vì các số khác nhau.

### Bài tập 2 — Kiểm tra môi trường

Ghi kết quả `db.version()`, `buildInfo` và `getParameter featureCompatibilityVersion` từ một cluster lab; so với `mongodump --version`/`mongosh --version` trên máy bạn.

### Bài tập 3 — Đọc bảng Java Driver

Theo bảng hiện hành, đánh giá Java Driver 5.9 với Server 9.0 và giải thích partially compatible có nghĩa gì.

### Bài tập 4 — Chọn driver

Ứng dụng chuẩn bị nâng Server 8.0 → 9.0. Đề xuất driver/Java runtime hỗ trợ theo official compatibility matrix, nêu các kiểm thử cần làm trước.

### Bài tập 5 — Dependency conflict

Giả sử ứng dụng có `mongodb-driver-sync:5.x` nhưng `bson` transitive của một framework là phiên bản khác. Nêu triệu chứng runtime và cách quản lý dependency thống nhất.

### Bài tập 6 — FCV

Vẽ timeline 7.0 binaries/FCV → 8.0 binaries/FCV cũ → 8.0 FCV mới. Tại sao không bật ngay trong giai đoạn rolling upgrade?

### Bài tập 7 — Docker

Chạy một container MongoDB Server trên môi trường lab, kiểm tra `mongod --version` và xác định liệu `mongodump` có thực sự được cài trong image không.

### Bài tập 8 — Dump/restore

Tạo archive bằng phiên bản Database Tools đã ghi nhận, restore vào target lab cùng Server major/FCV, đối soát count/indexes.

### Bài tập 9 — Restore cross-version

Lập ma trận source 8.0 → target 9.0 và source 9.0 → target 8.0. Phân biệt BSON files, metadata/archives và official upgrade path.

### Bài tập 10 — Oplog replay

Viết lệnh full replica set dump với `--oplog` và restore với `--oplogReplay`. Nêu lý do không dùng cho sharded cluster.

### Bài tập 11 — BSON vs JSON

Xuất một document có ObjectId, Decimal128, Date, Binary qua `mongoexport`; nhập lại bằng `mongoimport` và kiểm tra types.

### Bài tập 12 — Compatibility smoke test

Viết Java smoke test ping, insert/update/find, aggregation, codec Decimal128 và clean up trên database lab.

### Bài tập 13 — Auth/TLS failure

Mô tả cách phân biệt server version mismatch với certificate validation failure và DNS SRV error.

### Bài tập 14 — Atlas

Lập kế hoạch upgrade Server trong Atlas Dedicated có Java backend. Nêu những bước Atlas quản lý và những bước ứng dụng phải tự test.

### Bài tập 15 — Replica set

Thiết kế rolling upgrade plan dựa trên upgrade guide chính thức, monitoring election/failover và business transactions.

### Bài tập 16 — Sharding

Tìm các components phải nâng trong sharded cluster; giải thích vì sao không thể áp script standalone đơn giản.

### Bài tập 17 — Change Stream

Sau upgrade/restore, consumer gặp resume token invalid. Thiết kế bootstrap/rebuild logic, không bỏ events.

### Bài tập 18 — Search/Vector Search

Một Java Driver có thể gửi `$vectorSearch` nhưng server deployment không hỗ trợ. Phân tích vì sao client compatible chưa bảo đảm feature capability.

### Bài tập 19 — Runbook restore

Mô tả đầy đủ backup ID, Tools versions, source/target binary/FCV, archive checksum, encryption key, validation và RTO measured.

### Bài tập 20 — Rollback

Sau nâng Server 9.0, hệ thống đã dùng một persisted feature không tương thích 8.0. Vì sao “cài lại binary 8.0” không phải rollback plan được bảo đảm?

---

## 33. Câu hỏi ôn tập

1. Server binary version là gì?
2. FCV khác server version ra sao?
3. Khi nào nên chuyển FCV sau upgrade?
4. Vì sao downgrade có thể bị hạn chế sau FCV activation?
5. `mongod` khác `mongos` thế nào?
6. `mongosh --version` cho biết điều gì?
7. `db.version()` cho biết điều gì?
8. Có thể lấy FCV bằng lệnh nào?
9. Wire protocol compatibility nghĩa là gì?
10. Vì sao handshake thành công chưa chứng minh feature support?
11. Driver 5.x có bắt buộc Server 5.x không?
12. Fully/partially compatible khác nhau ra sao?
13. Ô trống trong compatibility table có ý nghĩa gì?
14. Vì sao Java runtime có compatibility matrix riêng?
15. Spring Data/BSON version conflict có thể gây lỗi gì?
16. MongoDB Database Tools tách version từ khi nào?
17. Tools `100.x` nghĩa là gì?
18. Bản Tools 100.20.1 hỗ trợ những Server versions nào theo docs hiện hành?
19. Các Database Tools gồm những binary nào?
20. `mongodump` khác `mongoexport` ở đâu?
21. `mongorestore` khác `mongoimport` ở đâu?
22. Vì sao JSON/CSV không phải backup thay BSON?
23. BSON types nào dễ mất precision qua import/export?
24. Quy tắc source/target major version hoặc FCV khi restore là gì?
25. Vì sao BSON data và metadata/archive/oplog có compatibility khác?
26. Tại sao nên dùng cùng Tools version cho dump/restore?
27. `--oplog` hỗ trợ loại deployment nào?
28. `--oplogReplay` có tạo arbitrary PITR không?
29. Sharded cluster có dùng `--oplogReplay` kiểu replica set không?
30. Vì sao tools hỗ trợ server version chưa chứng minh dump restore cross-version được?
31. Lỗi TLS/auth/network khác wire mismatch thế nào?
32. Vì sao nên kiểm tra exact binary được PATH chọn?
33. Chạy container `mongo:8` có chắc đã cài Database Tools không?
34. Driver mới có bật feature trên server cũ không?
35. Server mới có luôn hỗ trợ một feature nếu FCV chưa nâng không?
36. Khi nào chọn rolling upgrade?
37. Vì sao mixed-version cluster chỉ là giai đoạn chuyển tiếp?
38. Sharded upgrade cần kiểm tra thêm components nào?
39. Atlas và self-managed khác nhau về nâng cấp ra sao?
40. Những smoke tests ngoài ping cần làm?
41. Vì sao query plans/performance có thể đổi sau upgrade?
42. UUID representation có thể ảnh hưởng lookup thế nào?
43. Queryable Encryption cần restore procedure riêng vì sao?
44. Search indexes có thể phải rebuild sau restore không?
45. Làm thế nào đảm bảo rollback path được hỗ trợ?
46. Backup job thành công có chứng minh RTO được không?
47. Vì sao một thay đổi driver+server+tools đồng thời khó chẩn đoán?
48. Khi nào cần thử restore vào isolated target?
49. Các thông số nào nên lưu trong version inventory?
50. Vì sao compatibility phải được đánh giá theo từng feature chứ không chỉ major version?

---

## 34. Tổng kết

**MongoDB Server, Driver và Database Tools là ba dòng sản phẩm có phiên bản độc lập**, còn FCV là lớp điều khiển tính năng lưu trữ không tương thích ngược trong deployment.

- **Server** quyết định query engine, commands, storage, feature support và topology.
- **FCV** điều khiển một số persisted features mới; nâng binary không tự đồng nghĩa đã đổi FCV.
- **Driver** quyết định ứng dụng có thể kết nối/codec/retry và dùng API nào; phải kiểm tra bảng tương thích với Server và Java runtime.
- **Database Tools** có version riêng `100.x`; kết nối được tới Server không đồng nghĩa archive/dump nguồn bất kỳ restore an toàn tới Server đích.
- **mongosh** có release train riêng, không đại diện cho version Server.
- **BSON dump/restore** và **JSON/CSV import/export** có mục đích và mức bảo toàn metadata/types khác nhau.
- **Upgrade** cần làm theo topology/edition-specific procedure, test staging, backup verification, burn-in và FCV activation có kiểm soát.
- **Rollback** không chỉ là thay binary cũ; phải xét FCV, persisted data, feature usage và downgrade policy.

Cách ra quyết định đáng tin là **lưu inventory chính xác → đọc compatibility matrices → kiểm tra feature-specific gates → thử đầy đủ trên staging → nâng cấp theo quy trình → xác minh dữ liệu, ứng dụng và khả năng khôi phục**.

## Tài liệu MongoDB chính thức

- [MongoDB Client Library Compatibility Tables — Java Sync](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Sync Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/)
- [MongoDB Database Tools — Overview, Versioning, Compatibility](https://www.mongodb.com/docs/database-tools/)
- [MongoDB Database Tools — Install](https://www.mongodb.com/docs/database-tools/installation/)
- [mongodump Documentation](https://www.mongodb.com/docs/database-tools/mongodump/)
- [mongodump Compatibility and Installation](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-compatibility-and-installation/)
- [mongorestore Documentation](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [mongorestore Compatibility and Installation](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-compatibility-and-installation/)
- [mongorestore Behavior, Access and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [mongoexport Documentation](https://www.mongodb.com/docs/database-tools/mongoexport/)
- [mongoimport Documentation](https://www.mongodb.com/docs/database-tools/mongoimport/)
- [bsondump Documentation](https://www.mongodb.com/docs/database-tools/bsondump/)
- [MongoDB Manual — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Manual — MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/manual/administration/upgrade/)
- [MongoDB Manual — Upgrade from 7.0 to 8.0](https://www.mongodb.com/docs/manual/release-notes/8.0/)
- [MongoDB Manual — MongoDB 8.2 Release Notes](https://www.mongodb.com/docs/manual/release-notes/8.2/)
- [MongoDB Manual — Upgrade from 8.0 to 9.0 Replica Set](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-replica-set/)
- [MongoDB Manual — Upgrade from 8.0 to 9.0 Sharded Cluster](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-sharded-cluster/)
- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
