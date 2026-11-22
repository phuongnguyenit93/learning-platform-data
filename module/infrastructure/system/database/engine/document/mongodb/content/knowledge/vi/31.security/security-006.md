# Xác thực giữa các thành viên replica set hoặc sharded cluster trong MongoDB

## 1. Bài toán: tại sao các thành viên MongoDB phải xác thực lẫn nhau?

Trong MongoDB, một **replica set** gồm nhiều tiến trình `mongod` cùng giữ bản sao của một tập dữ liệu. Một **sharded cluster** còn có `mongos`, các shard (thường là replica sets), và các config servers lưu metadata định tuyến. Những thành phần này liên lạc với nhau liên tục để:

- Bầu và duy trì **primary** trong một replica set.
- Truyền **oplog** và duy trì secondary replication.
- Đồng bộ cấu hình và trạng thái replica set.
- Định tuyến truy vấn từ `mongos` tới shards.
- Truy cập metadata từ config server replica set (CSRS).
- Điều phối các thao tác quản trị phân tán.

Nếu một tiến trình lạ có thể giả mạo thành viên nội bộ, hậu quả có thể nghiêm trọng hơn một kết nối client thông thường: làm gián đoạn replication, gây lỗi routing hoặc giành quyền truy cập đặc quyền trong phạm vi cluster.

**Internal authentication**, còn gọi là **membership authentication** hay **cluster authentication**, là cơ chế để những tiến trình MongoDB chứng minh chúng thuộc **cùng một deployment đáng tin cậy**.

MongoDB self-managed hỗ trợ hai họ cơ chế chính:

1. **Keyfile authentication:** các thành viên sử dụng bí mật chia sẻ trong keyfile; MongoDB dùng cơ chế thử thách–đáp ứng SCRAM cho membership authentication.
2. **X.509 certificate authentication:** các thành viên xuất trình chứng chỉ X.509 được CA tin cậy và đáp ứng tiêu chí membership, trong kết nối TLS.

Tài liệu chính thức khuyến nghị **X.509 cho production**, trong khi keyfile là cơ chế đơn giản hơn, đặc biệt hữu ích cho môi trường lab/test và một số deployment hiện hữu.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **internal member authentication**, **client authentication/RBAC**, **TLS encryption** và **storage encryption**.
- Biết tiến trình nào trong replica set/sharded cluster cần cùng một mô hình xác thực nội bộ.
- Thiết kế keyfile đúng định dạng, quyền truy cập và chính sách bảo vệ bí mật.
- Hiểu các thuộc tính chứng chỉ X.509: CA, SAN, DN, `O`/`OU`/`DC`, EKU/KU.
- Đọc và viết cấu hình `security.keyFile`, `security.clusterAuthMode`, `net.tls.clusterFile`, `net.tls.certificateKeyFile`, `net.tls.CAFile`.
- Hiểu bốn chế độ `keyFile`, `sendKeyFile`, `sendX509`, `x509`.
- Lập kế hoạch bootstrap, thay đổi từ cluster không xác thực, chuyển keyfile → X.509, xoay khóa/chứng chỉ.
- Chẩn đoán lỗi `Authentication failed`, certificate mismatch, permission denied và mất majority mà không vô tình nới lỏng bảo mật.
- Thiết kế checklist production gồm secret management, TLS, monitoring, least privilege, backup và recovery.

**Phạm vi:** bài tập trung vào MongoDB **self-managed**. Với Atlas hoặc dịch vụ được quản lý, một phần xác thực giữa thành viên do nền tảng triển khai; không nên sửa trực tiếp `mongod.conf` theo các ví dụ self-managed.

---

## 2. Bốn lớp bảo mật dễ bị nhầm

| Lớp | Câu hỏi | Cơ chế ví dụ | Điều không tự làm |
| --- | --- | --- | --- |
| **Internal/member authentication** | “Tiến trình này có phải thành viên được phép của cluster không?” | Shared keyfile; member X.509 | Không thay ACL cho user ứng dụng |
| **Client authentication** | “Người/ứng dụng đang kết nối là ai?” | SCRAM users, X.509 users, cơ chế ngoài phù hợp | Không tự xác thực mọi liên kết nội bộ |
| **Authorization / RBAC** | “User đã xác thực được làm gì?” | Roles `read`, `readWrite`, `clusterMonitor`... | Không mã hóa network |
| **TLS transport protection** | “Đường truyền có mã hóa và xác minh đầu cuối không?” | `net.tls.mode: requireTLS`, CA, server cert | Không tự định nghĩa user permissions |
| **Encryption at rest** | “Dữ liệu lưu trên đĩa được mã hóa thế nào?” | Storage encryption, cloud KMS | Không phải keyfile membership |

Một hiểu nhầm nguy hiểm là “đã dùng keyfile nên dữ liệu giữa các nodes đã được mã hóa”. **Không đúng.** Keyfile được dùng để **xác thực thành viên**; cần **TLS** để mã hóa traffic trên mạng. Cũng không nên nhầm keyfile membership với **key của encrypted storage engine**: mục đích và quy trình rotation khác nhau.

### 2.1. Xác thực nội bộ và xác thực người dùng là hai kênh khác nhau

Ví dụ:

```text
Ứng dụng / mongosh
     |
     | Client auth (ví dụ SCRAM user + password)
     v
   mongos
     |
     | Internal auth (keyfile hoặc X.509)
     v
 Shard replica set
```

Client có thể đăng nhập bằng SCRAM, còn `mongos` kết nối tới `mongod` bằng **X.509 member certificate**. Hai loại thông tin xác thực **không nhất thiết giống nhau**.

MongoDB quy định bật internal authentication **cũng bật yêu cầu client access control/authorization**. Sau khi cấu hình `security.keyFile`, client không thể tiếp tục truy cập tài nguyên tùy ý như cluster không bật xác thực.

### 2.2. X.509 cho member khác X.509 cho người dùng

- **Member certificate:** chứng minh tiến trình `mongod`/`mongos` thuộc cluster; được cấp quyền nội bộ đặc biệt theo cơ chế membership.
- **Client X.509 certificate:** có thể đại diện user trong database `$external` để xác thực bằng `MONGODB-X509`; cần user/role phù hợp.
- Không dùng **member certificate** làm client certificate ứng dụng.
- Phải phân biệt nhóm thuộc tính DN của client user với nhóm thuộc tính membership để tránh nhầm danh tính và đặc quyền.

Không bao giờ coi chỉ việc một client có chứng chỉ do CA ký là đủ để trở thành MongoDB cluster member.

---

## 3. Sơ đồ những liên kết cần xác thực

### 3.1. Replica set

```text
                       Application
                      Client auth
                           |
                           v
                   mongod R1 (PRIMARY)
                         /   \
             Internal auth   Internal auth
                       /       \
                  mongod R2    mongod R3
                 (SECONDARY)  (SECONDARY)

      Mỗi kết nối member-to-member được xác thực.
      Mỗi node dùng cơ chế/chính sách cluster giống nhau.
```

Các member phải tin cậy danh tính của nhau. Nếu R3 có keyfile khác không có khóa chung, nó có thể nhìn thấy hostname và port của R1/R2 nhưng **không được xác nhận là thành viên hợp lệ**.

### 3.2. Sharded cluster

```text
                            Application
                                 |
                          Client auth / TLS
                                 |
                           +-----+-----+
                           |  mongos   |
                           | routers   |
                           +-----+-----+
                               /   \
                Member auth   /     \   Member auth
                             v       v
                 +----------------+  +----------------+
                 | Shard A RS     |  | Shard B RS     |
                 | A1 A2 A3       |  | B1 B2 B3       |
                 +----------------+  +----------------+
                             \        /
                              \      /
                               v    v
                       Config Server RS
                          CS1 CS2 CS3
```

Trong mô hình self-managed tiêu chuẩn, **`mongos`, mọi `mongod` thuộc các shard, và mọi `mongod` thuộc CSRS** phải sử dụng cùng một cơ chế membership auth đã được cấu hình. Với keyfile, tất cả phải có **ít nhất một bí mật chung**; không chỉ các node trong cùng một shard.

**Phân biệt vai trò:**

- **Primary member của replica set:** node nhận write cho replica set.
- **Primary shard của database:** khái niệm sharding metadata, không phải “primary MongoDB server” của cả cluster.
- **Config server replica set:** lưu metadata; không phải database ứng dụng để đăng nhập tùy tiện.
- **`mongos`:** router, không lưu toàn bộ bản sao dữ liệu của shard.

Việc một shard có replication không có nghĩa shard khác chứa cùng dữ liệu. Internal authentication không thay replication/backup.

---

## 4. Keyfile authentication: bí mật chia sẻ cho các members

Keyfile chứa password bí mật dùng để xác thực nội bộ giữa `mongod`/`mongos`. Với chế độ này, MongoDB dùng **SCRAM challenge-response** và các tiến trình được phép phải biết key được chấp nhận.

### 4.1. Các điều kiện kỹ thuật

Theo MongoDB Manual:

- Một khóa hợp lệ có độ dài **từ 6 đến 1024 ký tự**.
- Ký tự khóa phải thuộc **tập base64**, không phải tùy ý UTF-8 hay toàn bộ printable ASCII.
- Nội dung keyfile có thể là **một chuỗi khóa** hoặc **YAML sequence nhiều khóa** để hỗ trợ rotation.
- Trong cùng deployment, các `mongod`/`mongos` phải chia sẻ **ít nhất một khóa**.
- Trên **Unix/Linux**, keyfile không được có group/world permissions; đặt quyền chỉ owner đọc là thực hành tốt.
- Trên **Windows**, MongoDB không áp dụng cùng kiểm tra permission bit Unix, nhưng phải bảo vệ bằng Windows ACL và hạn chế user service.
- Keyfile phải khả dụng tại **từng host** chạy component; không phụ thuộc vào ổ mạng hoặc thiết bị có thể bị tháo.

### 4.2. Tạo keyfile ngẫu nhiên — lab trên Linux

**Chỉ dùng trên máy lab/đường dẫn lab; không ghi key vào Git, Docker image, log hoặc chat.**

```bash
# Tạo một bí mật ngẫu nhiên theo ví dụ MongoDB.
umask 077
openssl rand -base64 756 > /etc/mongodb/cluster.key

# Chỉ owner được đọc; service account cần có quyền đọc file.
chmod 400 /etc/mongodb/cluster.key
```

Lệnh `openssl rand -base64 756` sinh giá trị ngẫu nhiên đủ dài (đầu ra base64 khoảng 1024 ký tự, ngoài newline). Trên production, dùng hệ thống quản lý bí mật, truyền file qua kênh bảo vệ và đặt owner là MongoDB service identity.

Nếu user chạy `mongod` là `mongodb` và file thuộc `root` với `chmod 400`, `mongod` có thể **không đọc được**. Chọn owner/ACL thích hợp; không sửa bằng cách mở `chmod 777`.

### 4.3. Phân phối keyfile an toàn

- Dùng secrets manager hoặc pipeline bảo mật có audit để phân phối.
- Giữ file ngoài repository, CI logs và container image layers.
- Tránh truyền bí mật trên command line hiện ra trong process list.
- Chỉ cho OS account chạy MongoDB có quyền đọc.
- Tránh backup plaintext keyfile chung kho public artifacts.
- Kiểm tra file không đổi do copy/encoding.
- Không dùng cùng một bí mật keyfile cho nhiều môi trường production, staging, development không liên quan.

**Đừng gửi nội dung keyfile** khi yêu cầu hỗ trợ hoặc đính kèm incident ticket. Hash metadata/audit có thể được sử dụng một cách phù hợp, nhưng không cần log khóa.

### 4.4. Một keyfile có nhiều khóa

Định dạng YAML:

```yaml
# Minh họa cấu trúc, KHÔNG phải khóa dùng thực tế.
- "<OLD_BASE64_RANDOM_KEY>"
- "<NEW_BASE64_RANDOM_KEY>"
```

MongoDB sẽ không chấp nhận các placeholder có ký tự `<`/`>` như key hợp lệ. Chúng chỉ để giải thích quy trình. Khi triển khai, phải thay bằng **hai key ngẫu nhiên base64 thực**, có độ dài hợp lệ.

Cơ chế chấp nhận **ít nhất một khóa chung** cho phép rotation theo kiểu rolling, thay vì yêu cầu mọi member đổi bí mật đồng thời.

---

## 5. Cấu hình replica set dùng keyfile

Giả sử ba host DNS:

```text
mongo1.example.net:27017
mongo2.example.net:27017
mongo3.example.net:27017

Replica set name: rs0
Keyfile: /etc/mongodb/cluster.key
```

Mỗi host có data directory của riêng mình và được phân phối cùng membership key.

### 5.1. File cấu hình cho `mongo1`

Ví dụ `/etc/mongod.conf` của **host mongo1**, chỉ để minh họa:

```yaml
storage:
  dbPath: /var/lib/mongodb

net:
  port: 27017
  bindIp: localhost,mongo1.example.net

replication:
  replSetName: rs0

security:
  keyFile: /etc/mongodb/cluster.key
  authorization: enabled
```

Trên `mongo2` và `mongo3`, thay hostname trong `net.bindIp` theo máy, giữ:

- `replication.replSetName: rs0`.
- Keyfile chứa bí mật chung.
- Cơ chế xác thực nội bộ nhất quán.
- Network policy cho phép các members nói chuyện qua đúng port.

`security.keyFile` **ngụ ý bật authorization**; dòng `authorization: enabled` làm rõ ý định. Đây **chưa phải cấu hình production hoàn chỉnh**, vì ví dụ chưa cấu hình TLS. Với production, cần bổ sung TLS và những bảo vệ mạng/OS phù hợp.

### 5.2. Không dùng IP thay DNS bừa bãi

MongoDB khuyến cáo dùng **DNS hostname** cho cấu hình replica set và sharded cluster, đặc biệt khi có network horizons. Từ MongoDB 5.0, cấu hình chỉ dùng IP có ràng buộc startup validation và có thể không khởi động.

DNS tên member phải:

- Có thể phân giải từ các host khác.
- Trỏ đúng endpoint/port.
- Tương thích SAN certificate nếu dùng TLS.
- Ổn định khi VM/container được thay thế.
- Không bị route tới host không được phép bằng DNS/network misconfiguration.

### 5.3. Bật xác thực trên cluster mới

Trình tự khái niệm:

1. Tạo keyfile bảo mật và phân phối tới **mọi member**.
2. Cấu hình `replSetName`, network, keyfile, TLS theo topology.
3. Khởi động `mongod` trên ba hosts.
4. Bootstrap replica set bằng `rs.initiate()` ở môi trường được phép.
5. Dùng **localhost exception** nếu thích hợp khi chưa có user, tạo user administrator đầu tiên.
6. Tạo cluster administrator/application users với quyền tối thiểu.
7. Kết nối từ client bằng credential hợp lệ.
8. Xác minh `rs.status()`, replica sync, election và không có auth errors.

Lệnh khởi tạo **chỉ dùng khi replica set chưa được khởi tạo**, không chạy lại trên cluster production đang hoạt động:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1.example.net:27017" },
    { _id: 1, host: "mongo2.example.net:27017" },
    { _id: 2, host: "mongo3.example.net:27017" }
  ]
});
```

**Localhost exception:** Khi bật authorization nhưng chưa tồn tại user, MongoDB có ngoại lệ được giới hạn nhằm bootstrap user đầu tiên từ local connection. Nó **không** là phương thức vận hành lâu dài. Sau khi tạo user đầu tiên, ngoại lệ không còn. Cần làm theo tutorial tương ứng và kiểm soát local access; nếu đã có users, không dựa vào ngoại lệ này.

### 5.4. Tạo user admin ban đầu

Ví dụ chạy từ session MongoDB được phép bootstrap và kết nối tới primary:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "securityAdmin",
  pwd: passwordPrompt(),
  roles: [
    { role: "userAdminAnyDatabase", db: "admin" }
  ]
});
```

`userAdminAnyDatabase` có thể cấp quyền rất mạnh thông qua quản trị users/roles; đây là user bootstrap bảo vệ nghiêm ngặt, **không dùng làm credential cho application**.

Sau đó, đăng nhập bằng admin để tạo thêm user theo least privilege. Nên có tài khoản khẩn cấp/break-glass và quy trình recovery được bảo vệ.

### 5.5. Client authentication khi đã bật keyfile

Ví dụ `mongosh`:

```bash
mongosh "mongodb://mongo1.example.net:27017,mongo2.example.net:27017,mongo3.example.net:27017/?replicaSet=rs0&authSource=admin" \
  --username securityAdmin --password
```

Command sẽ prompt password thay vì ghi plaintext vào shell history. Ví dụ này **chưa bao gồm TLS options**; khi deployment có `requireTLS`, client phải kết nối TLS và xác minh CA/hostname đúng.

Đừng cung cấp keyfile nội bộ cho client application. Client đăng nhập bằng user-specific credentials.

---

## 6. Thêm TLS khi dùng keyfile: xác thực và mã hóa khác nhau

Chỉ bật keyfile không thay thế mã hóa network. Trong production, thực hành khuyến nghị là **TLS 1.2+**, certificate hợp lệ, CA trust, network segmentation và membership authentication.

Cấu hình rút gọn trên mỗi host:

```yaml
net:
  port: 27017
  bindIp: localhost,mongo1.example.net
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1-server.pem
    CAFile: /etc/mongodb/tls/ca.pem

replication:
  replSetName: rs0

security:
  keyFile: /etc/mongodb/cluster.key
  authorization: enabled
```

Các file PEM phải được cấp trước, đúng SAN/CA/trust chain, và private key được bảo vệ. Mỗi server thường có **server certificate/key riêng** theo hostname.

Khi **`requireTLS`**:

- Connections đến server phải có TLS.
- Server trình certificate để peer xác minh.
- Keyfile vẫn là bí mật cho membership.
- Client user authentication vẫn là cơ chế user riêng như SCRAM.
- CA certificate phải được phân phối đến nơi cần xác minh.

Cảnh giác: bản thân TLS server certificate hợp lệ **không tự chứng minh member có quyền tham gia replica set** nếu `clusterAuthMode` đang là `keyFile`: membership auth vẫn dựa keyfile.

---

## 7. Cấu hình keyfile cho sharded cluster

Một sharded cluster ví dụ:

```text
Router:    router1.example.net:27017

CSRS:      cfg1.example.net:27019
           cfg2.example.net:27019
           cfg3.example.net:27019

Shard A:   a1.example.net:27018
           a2.example.net:27018
           a3.example.net:27018

Shard B:   b1.example.net:27018
           b2.example.net:27018
           b3.example.net:27018
```

**Tất cả** `mongos` và `mongod` trong các replica sets/config servers phải chia sẻ ít nhất một key khi dùng keyfile membership.

### 7.1. Config server replica set

Cấu hình trên `cfg1`:

```yaml
sharding:
  clusterRole: configsvr

replication:
  replSetName: cfgRS

net:
  port: 27019
  bindIp: localhost,cfg1.example.net

storage:
  dbPath: /var/lib/mongodb-config

security:
  keyFile: /etc/mongodb/cluster.key
```

`cfg2`, `cfg3` dùng cấu hình tương tự với hostname/dbPath riêng. Trong cluster thực tế cần TLS, firewall và các tùy chọn service management. Không copy nguyên ví dụ vào production.

### 7.2. Shard replica set

Cấu hình trên `a1`:

```yaml
sharding:
  clusterRole: shardsvr

replication:
  replSetName: shardA

net:
  port: 27018
  bindIp: localhost,a1.example.net

storage:
  dbPath: /var/lib/mongodb-shard

security:
  keyFile: /etc/mongodb/cluster.key
```

Các member `a2`, `a3` có cùng `replSetName: shardA`. Shard B có `replSetName: shardB`. Khóa nội bộ vẫn phải tương thích với CSRS và routers.

### 7.3. `mongos` router

File cấu hình cho router:

```yaml
sharding:
  configDB: cfgRS/cfg1.example.net:27019,cfg2.example.net:27019,cfg3.example.net:27019

net:
  port: 27017
  bindIp: localhost,router1.example.net

security:
  keyFile: /etc/mongodb/cluster.key
```

`mongos` không có `storage.dbPath` như data-bearing shard. Nó cần kết nối nội bộ tới config servers/shards với đúng membership authentication.

**Lưu ý:** Các ví dụ ở mục này chỉ biểu diễn phần auth và topology. Production cần TLS trên **mọi** liên kết, cấu hình theo version và plan triển khai gồm bootstrap từng replica set, đăng ký shard đúng quy trình, users/RBAC và backup.

### 7.4. Vì sao keyfile chỉ đặt trên shards là chưa đủ?

Nếu thiếu keyfile hoặc clusterAuthMode không tương thích ở router:

```text
Application -> mongos (không có internal key)
                     |
                     X  Auth thất bại
                     |
                  Shard A
```

Ứng dụng có thể xác thực vào `mongos` thành công, nhưng router không được phép kết nối nội bộ đến shard, làm query thất bại.

Tương tự, CSRS có thể không được xác thực bởi routers nếu được cấu hình tách biệt không tương thích.

---

## 8. X.509 member authentication: danh tính bằng chứng chỉ

Ở chế độ X.509, các tiến trình MongoDB dùng **TLS certificates** để chứng minh danh tính nội bộ. Một kết nối thành viên phải vượt các bước quan trọng:

1. Kết nối mạng tới endpoint đúng.
2. Thiết lập TLS thành công.
3. Xác minh certificate chain qua CA tin cậy.
4. Kiểm tra certificate chưa hết hạn/không bị từ chối.
5. Kiểm tra hostname/SAN và mục đích dùng certificate phù hợp.
6. Kiểm tra **membership identity** (DN attributes hoặc cấu hình thay thế) hợp lệ.
7. Sau đó mới tham gia các thao tác nội bộ.

**Có TLS không đồng nghĩa có membership auth X.509.** Một deployment có thể dùng TLS để mã hóa traffic nhưng vẫn dùng keyfile làm membership credential. Chỉ khi `clusterAuthMode: x509` (hoặc giai đoạn chuyển đổi phù hợp), certificates mới là cơ chế membership chính.

### 8.1. CA: nguồn tin cậy

Các member certificates trong một replica set/sharded cluster phải được cấp theo yêu cầu CA của MongoDB. Dùng CA nội bộ/doanh nghiệp hoặc nhà cung cấp tin cậy với lifecycle/rotation rõ ràng.

Không tự ký một certificate riêng lẻ trên mỗi node rồi mong tất cả nodes tin cậy nhau mà không quản lý CA/trust chain. Đừng phân phối **private key của CA** tới máy database; chỉ phân phối **CA public certificate chain** cần để xác minh.

### 8.2. Subject Distinguished Name

Ví dụ certificate subjects:

```text
CN=mongo1.example.net, OU=MongoDBMembers, O=ExampleOrg, DC=example, DC=net
CN=mongo2.example.net, OU=MongoDBMembers, O=ExampleOrg, DC=example, DC=net
CN=mongo3.example.net, OU=MongoDBMembers, O=ExampleOrg, DC=example, DC=net
```

- `CN` là tên từng server, có thể khác nhau.
- `OU`, `O`, `DC` là những thuộc tính membership mặc định MongoDB đối chiếu.
- Các thành viên cùng cluster phải có các giá trị membership phù hợp và **khớp chính xác theo quy tắc MongoDB**.
- Nếu certificate có nhiều `OU`, danh sách nhiều giá trị đó phải giống nhau theo quy tắc kiểm tra.

Cơ chế xác minh không đơn giản là “cùng CA thì là cùng cluster”. Một certificate user do cùng CA ký nhưng không thỏa thuộc tính membership **không được coi là member**.

### 8.3. Subject Alternative Name (SAN)

Certificate của `mongo1.example.net` phải có ít nhất một SAN phù hợp hostname mà các peers dùng để kết nối:

```text
DNS:mongo1.example.net
```

Nếu peer cấu hình `mongo1.example.net` nhưng certificate chỉ có `DNS:other.example.net`, quá trình TLS hostname validation có thể thất bại.

MongoDB có fallback sang Common Name khi thiếu SAN ở một số điều kiện, nhưng **CN-only hostname verification đã lỗi thời** và có cảnh báo/giới hạn client. Production phải cấp SAN đúng.

### 8.4. EKU và KU

X.509 có các extension định nghĩa mục đích sử dụng khóa:

| Certificate | Extended Key Usage khi extension có mặt | Ý nghĩa |
| --- | --- | --- |
| `net.tls.certificateKeyFile` | `serverAuth` | Server trình certificate với clients/peers |
| `net.tls.clusterFile` | `clientAuth` | Member dùng certificate cho internal client authentication |
| Chỉ dùng `certificateKeyFile` chung, không có `clusterFile` | Cần `serverAuth` **và** `clientAuth` nếu EKU có mặt | Một certificate cho hai vai trò |

Khi KU extension có mặt, tài liệu MongoDB đưa ra các yêu cầu/khuyến nghị tương ứng; ví dụ:

```ini
# Server certificate:
keyUsage = digitalSignature, keyEncipherment, keyAgreement
extendedKeyUsage = serverAuth

# Cluster/member certificate:
keyUsage = digitalSignature
extendedKeyUsage = clientAuth
```

Không tự kết luận chỉ có `serverAuth` là đủ cho member X.509 nếu file được dùng để kết nối như một client nội bộ. Cần kiểm tra đúng EKU/KU, đường dẫn TLS và MongoDB version.

### 8.5. `clusterFile` và `certificateKeyFile`

- `net.tls.certificateKeyFile`: PEM chứa server certificate/private key phục vụ TLS server và một số kết nối nội bộ.
- `net.tls.clusterFile`: PEM member certificate/private key riêng cho membership authentication.
- `net.tls.CAFile`: CA chain dùng để xác minh peers.

Nếu `clusterFile` không được đặt, MongoDB có thể dùng `certificateKeyFile` làm certificate membership; certificate đó phải được cấp phù hợp **cả serverAuth và clientAuth** khi có EKU.

Tách hai file giúp quản trị vòng đời chứng chỉ server và member riêng biệt, nhưng tăng số secrets phải bảo vệ.

---

## 9. Ví dụ replica set dùng X.509 và requireTLS

Ví dụ trên `mongo1.example.net`:

```yaml
storage:
  dbPath: /var/lib/mongodb

net:
  port: 27017
  bindIp: localhost,mongo1.example.net
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1-server.pem
    clusterFile: /etc/mongodb/tls/mongo1-member.pem
    CAFile: /etc/mongodb/tls/ca.pem

replication:
  replSetName: rs0

security:
  clusterAuthMode: x509
  authorization: enabled
```

Các nodes khác dùng:

- Cùng replica set name.
- Cùng định nghĩa/tiêu chí membership X.509.
- CA/trust chain đúng.
- **Certificate/key riêng** cho từng node, với SAN khớp hostname node đó.
- Member certificate có `O`/`OU`/`DC` phù hợp hoặc cấu hình membership alternative tương ứng.

Điều này **không có nghĩa** phải sao chép một private key PEM giống hệt cho mọi node. X.509 thường cho phép mỗi node có keypair riêng, với chuỗi tin cậy và membership attributes tương thích.

### 9.1. Cấu hình X.509 cho sharded cluster

Trên từng `mongod` của shards/CSRS và từng `mongos`, thêm các thuộc tính TLS và auth phù hợp:

```yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/this-node-server.pem
    clusterFile: /etc/mongodb/tls/this-node-member.pem
    CAFile: /etc/mongodb/tls/ca.pem

security:
  clusterAuthMode: x509
```

Kết hợp snippet này với các phần `replication`, `sharding`, `storage`, `net.bindIp` dành riêng từng role. Đây **chỉ là phần chung**, không phải một file mongod/mongos hoàn chỉnh.

### 9.2. Cấu hình membership DN tùy biến ở MongoDB 7.0+

MongoDB cung cấp các cấu hình mới để kiểm tra member X.509 theo những thuộc tính khác mặc định. Ví dụ khi tổ chức chọn matching theo `O` và `OU`:

```yaml
net:
  tls:
    clusterAuthX509:
      attributes: "O=ExampleOrg, OU=MongoDBMembers"
```

Các thành viên phải dùng **cùng cấu hình và cùng giá trị phù hợp**. Không áp dụng vào một node rồi kỳ vọng cả cluster vẫn tương thích mà không có kế hoạch.

Có thể dùng extension OID membership:

```text
1.3.6.1.4.1.34601.2.1.2
```

với `net.tls.clusterAuthX509.extensionValue` trong các phiên bản hỗ trợ, khi tổ chức muốn dựa trên extension thay vì DN attributes. Cấu hình certificate extension phải dùng **đúng ASN.1 UTF8String** và giá trị tương ứng. Những cơ chế này không phải lý do bỏ qua hostname validation hoặc CA verification.

### 9.3. Nguy cơ nhầm client certificate với member certificate

Chỉ member certificates mới được dùng giá trị thuộc tính/extension dành riêng cho membership. Client certificate dùng cho `$external` authentication phải có danh tính khác.

**Không đặt `enforceUserClusterSeparation=false` như biện pháp “sửa lỗi X.509”**. Theo MongoDB documentation, giá trị này tạo điều kiện nhầm lẫn client/membership identity và không tương thích các chế độ X.509 cluster auth tương ứng. Đây là một kiểm soát bảo mật quan trọng, không phải cờ tùy ý bỏ qua trong production.

---

## 10. `security.clusterAuthMode`: bốn chế độ cần ghi nhớ

MongoDB hỗ trợ:

| Mode | Node **gửi** khi xác thực mình | Node **chấp nhận** từ peer | Mục đích |
| --- | --- | --- | --- |
| `keyFile` | Keyfile credential | **Chỉ keyfile** | Cluster đang dùng shared secret |
| `sendKeyFile` | Keyfile credential | **Keyfile hoặc X.509** | Giai đoạn chuẩn bị migration |
| `sendX509` | Member X.509 certificate | **Keyfile hoặc X.509** | Giai đoạn chuyển đổi |
| `x509` | Member X.509 certificate | **Chỉ X.509** | Trạng thái đích khuyến nghị |

`sendKeyFile` và `sendX509` không phải trạng thái bảo mật tối ưu lâu dài. Chúng là những **transitional modes** để thay đổi dần các member.

### 10.1. Vì sao không chuyển thẳng tất cả nodes sang x509?

Giả sử:

```text
Node A: x509 -> chỉ chấp nhận certificates
Node B: keyFile -> chỉ gửi/nhận keyfile
```

Hai nodes có thể **không có phương thức chung** để xác thực nhau. Nếu chuyển node theo thứ tự không có bước trung gian, cluster có thể mất replication/quorum hoặc không định tuyến được.

Vì vậy quy trình migration phải đưa tất cả nodes qua trạng thái **chấp nhận cả hai**, sau đó thay thứ được gửi, cuối cùng mới chỉ chấp nhận X.509.

### 10.2. Không nhầm `clusterAuthMode` với `tls.mode`

- `security.clusterAuthMode` chọn **membership credential**.
- `net.tls.mode` chọn **cách dùng TLS** trên kết nối, ví dụ `requireTLS`.
- `sendX509` không tự chứng minh mọi client connection đều đã yêu cầu TLS nếu `tls.mode` và quá trình migration chưa được cấu hình đúng.

Production đích thường kết hợp `clusterAuthMode: x509` và `net.tls.mode: requireTLS`.

---

## 11. Chuyển từ keyfile sang X.509 theo quy trình rolling

**Đây là hướng dẫn tư duy và ví dụ cấu hình để học.** Không thực hiện trực tiếp trên cluster production mà chưa đọc tutorial đúng phiên bản, có backup, admin access, runbook, maintenance plan và giám sát election/quorum.

Giả sử cluster đang chạy keyfile và **đã bật TLS**.

### Giai đoạn 1: Chuẩn bị certificate và cho phép hai phương thức

Trên **từng** `mongod`/`mongos`:

1. Cấp member certificate/key từ CA được tin cậy.
2. Kiểm tra SAN, `O`/`OU`/`DC` hoặc membership extension, EKU và thời hạn.
3. Thêm `net.tls.clusterFile` và CA/trust settings.
4. Đặt `security.clusterAuthMode: sendKeyFile`.
5. Giữ `security.keyFile` cũ.
6. Rolling restart từng tiến trình theo topology để không mất availability.

Ví dụ:

```yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/node-server.pem
    clusterFile: /etc/mongodb/tls/node-member.pem
    CAFile: /etc/mongodb/tls/ca.pem

security:
  clusterAuthMode: sendKeyFile
  keyFile: /etc/mongodb/cluster.key
```

Ở trạng thái này node **vẫn gửi keyfile** nhưng có thể **chấp nhận keyfile hoặc X.509**. Phải đạt trạng thái tương thích trên **toàn cluster** trước khi bước tiếp.

### Giai đoạn 2: Chuyển thứ mỗi node gửi thành X.509

Theo tutorial version hỗ trợ, từ phiên `mongosh` có quyền quản trị thích hợp **kết nối đến từng node**:

```javascript
db.adminCommand({
  setParameter: 1,
  clusterAuthMode: "sendX509"
});
```

Khi mode `sendX509`, member **gửi X.509** và **vẫn chấp nhận cả hai phương thức**. Trạng thái này giúp tránh cắt đứt peer còn đang chuyển đổi.

Chỉ chuyển tiếp khi mọi node đã chuẩn bị certificate, CA trust và `sendKeyFile` đúng; đừng dùng lệnh này để thử trên một node rời rạc khi các peer chưa sẵn sàng.

### Giai đoạn 3: Chỉ chấp nhận X.509

Sau khi tất cả member đã dùng `sendX509`, chuyển thành:

```javascript
db.adminCommand({
  setParameter: 1,
  clusterAuthMode: "x509"
});
```

Khi đó member gửi và chỉ chấp nhận X.509.

### Giai đoạn 4: Lưu trạng thái bền vững

Vì `setParameter` runtime có thể không sống qua restart, cập nhật file cấu hình:

```yaml
security:
  clusterAuthMode: x509
```

Giữ cấu hình TLS, CA và member cert. Gỡ keyfile cũ theo kế hoạch sau khi xác thực toàn cluster ổn định. Kiểm tra restart canary không quay lại mode cũ.

### 11.1. Cluster trước đó chưa có TLS

Khi từ keyfile không TLS sang X.509, phải chuyển thêm **TLS transport mode** theo quy trình được MongoDB hỗ trợ. Tutorial có các pha `allowTLS`/`preferTLS`/`requireTLS` thích hợp để không cắt kết nối quá sớm.

Không được chỉ thêm `clusterAuthMode: x509` vào cluster không TLS rồi mong thành công. Cần chuẩn bị certificate và rolling sequence riêng.

### 11.2. Không nhầm chuyển thành X.509 với client migration

Việc chuyển **member authentication** từ keyfile sang X.509 **không bắt buộc** user ứng dụng đang dùng SCRAM phải chuyển thành client X.509. Hai kênh auth độc lập.

---

## 12. Bật keyfile authentication trên cluster đang chạy không auth

Đây là tình huống khác với migration keyfile → X.509. Cluster hiện tại có thể đã chạy không `authorization` và không membership auth.

### 12.1. Phương án downtime

Tutorial MongoDB hướng dẫn dừng members theo thứ tự và khởi động lại với `security.keyFile`, sau đó tạo admin user bằng localhost exception nếu điều kiện cho phép.

Rủi ro:

- Có downtime theo kế hoạch.
- Ứng dụng cũ không có user credential sẽ bị từ chối.
- Có thể mất majority nếu thao tác restart không đúng.
- Nếu không tạo được admin ban đầu, đội vận hành có thể tự khóa quyền quản trị.

### 12.2. Phương án chuyển đổi không downtime

MongoDB còn có tutorial riêng dùng `security.transitionToAuth: true` để cho phép một pha chuyển đổi:

```yaml
security:
  keyFile: /etc/mongodb/cluster.key
  transitionToAuth: true

replication:
  replSetName: rs0
```

**Cực kỳ quan trọng:** Khi `transitionToAuth` đang bật, server có thể **chấp nhận các kết nối chưa xác thực** và vì vậy chưa thực thi mô hình bảo mật đích. Đây là một pha migration **tạm thời**, không phải cấu hình production lâu dài.

Một lộ trình chính xác cần:

1. Chuẩn bị keyfile và user accounts.
2. Phân phối cấu hình/secret đầy đủ.
3. Rolling restart các members vào transition state theo hướng dẫn.
4. Di chuyển applications sang credentials phù hợp.
5. Rolling restart bỏ `transitionToAuth`.
6. Kiểm tra client không credentials bị từ chối.
7. Xác minh cluster khỏe và không có unprotected endpoint.

Không tự ngắt hoặc kéo dài pha transition. Nếu deployment có sharded cluster, trình tự cho CSRS, shards và routers còn có yêu cầu riêng.

---

## 13. Key rotation an toàn, không phá quorum

Keyfile là một **shared secret**, nên cần thay định kỳ hoặc khi nghi ngờ lộ khóa.

MongoDB hỗ trợ keyfile YAML chứa **nhiều keys**, miễn các nodes có ít nhất một key chung. Có thể rotate theo chiến lược **old + new overlap**.

### 13.1. Trạng thái ban đầu

```text
Node A: [OLD]
Node B: [OLD]
Node C: [OLD]
```

Mọi node xác thực được vì có `OLD`.

### 13.2. Pha 1 — Thêm NEW nhưng giữ OLD

Trên mỗi node, lần lượt thay keyfile thành:

```yaml
- "<OLD_RANDOM_KEY>"
- "<NEW_RANDOM_KEY>"
```

Sau **rolling restart** theo quy trình chính thức:

```text
Node A: [OLD, NEW]
Node B: [OLD, NEW]
Node C: [OLD, NEW]
```

Kể cả trong lúc có node chưa restart, vẫn còn khóa `OLD` chung.

### 13.3. Pha 2 — Chỉ giữ NEW

Sau khi tất cả nodes đã dùng `[OLD, NEW]`, thay từng node thành:

```yaml
- "<NEW_RANDOM_KEY>"
```

Rolling restart tiếp:

```text
Node A: [NEW]
Node B: [NEW]
Node C: [NEW]
```

Các nodes vẫn có khóa `NEW` chung. Khi kết thúc, **OLD bị thu hồi** khỏi toàn deployment.

### 13.4. Điều cần kiểm tra

- Không bao giờ có hai members cần liên lạc nhưng **không có key chung**.
- Restart một member mỗi lần để giữ đa số voting members.
- Với primary, làm theo quy trình **step down trước khi restart**.
- Kiểm tra replication lag, election, `rs.status()` và logs.
- Sharded cluster cần bao phủ CSRS, mọi shard replica sets và `mongos`.
- Không chỉ rotate ba nodes data khi còn routers/config servers giữ key cũ.
- Key mới phải là secret ngẫu nhiên, không copy từ ví dụ.
- Có audit và kế hoạch thu hồi secret cũ.

**Lưu ý:** Keyfile rotation ở đây **không áp dụng** trực tiếp cho local key management của encrypted storage engine. File key cho storage engine có ràng buộc và tài liệu rotation khác.

---

## 14. Chứng chỉ X.509: cấp mới, xoay và thu hồi

Khác keyfile chia sẻ, mỗi node có thể có certificate/private key riêng. Điều đó thuận lợi cho identity và khả năng thu hồi nhưng đòi hỏi PKI và quản lý vòng đời chứng chỉ.

### 14.1. Checklist khi cấp certificate

1. Tạo keypair cho node theo chính sách PKI.
2. Cấp certificate từ CA tin cậy.
3. SAN chứa DNS hostname chính xác mà peers dùng.
4. Các thuộc tính membership `O`/`OU`/`DC` (hoặc alternative) tương thích toàn cluster.
5. EKU phù hợp `serverAuth`/`clientAuth` theo file usage.
6. KU và certificate chain hợp lệ.
7. Private key được bảo vệ, không xuất ra logs.
8. Certificate có thời hạn/renewal plan.
9. Các thành viên tin cậy CA tương ứng.
10. Test trên staging và canary trước rollout rộng.

### 14.2. Đọc certificate bằng OpenSSL

Một ví dụ kiểm tra **chỉ metadata công khai của certificate**:

```bash
openssl x509 \
  -in /etc/mongodb/tls/mongo1-member.pem \
  -noout -subject -issuer -dates

openssl x509 \
  -in /etc/mongodb/tls/mongo1-member.pem \
  -noout -text
```

Tìm:

```text
Subject
Issuer
Not Before / Not After
X509v3 Subject Alternative Name
X509v3 Key Usage
X509v3 Extended Key Usage
```

**Không** in private key bằng `openssl pkey -text` vào log/ticket. File PEM có thể chứa cả private key nên bản thân file luôn phải được bảo vệ.

### 14.3. Rotation có thể cần overlap CA

Nếu đổi CA, các nodes trong giai đoạn rolling có thể phải tin cậy chain cũ và mới theo **quy trình CA rotation được hỗ trợ**. Chỉ đưa certificate mới cho một node trong khi peers không tin CA mới sẽ gây TLS handshake failure.

Cần xét:

- Từng cặp node trong giai đoạn hỗn hợp có xác thực nhau không?
- CA bundle đã được cập nhật trên tất cả hosts chưa?
- SAN/hostname có thay đổi không?
- Certificate riêng có EKU đúng không?
- Có thời gian rollback về certificate cũ còn hạn không?
- Có automatic certificate renewal và cảnh báo sớm trước ngày hết hạn không?

Không đổi CA, hostnames và cluster auth mode trong cùng một lần rollout nếu không có lý do/plan cụ thể; khó cô lập lỗi.

### 14.4. Certificate expiry và availability

Khi certificate hết hạn, member có thể không được xác thực, làm mất kết nối replication/routing. Nếu nhiều nodes cùng được cấp chứng chỉ với cùng expiration, sự cố có thể xảy ra đồng thời.

Theo tài liệu MongoDB, server phát cảnh báo khi chứng chỉ X.509 sắp hết hạn trong khoảng **30 ngày** trong tình huống tương ứng. Vẫn nên có monitoring riêng với ngưỡng dài hơn phù hợp chính sách tổ chức, không chỉ dựa vào startup logs.

---

## 15. TLS không phải tùy chọn “bỏ qua lỗi xác minh”

Các cấu hình sau **không phải cách sửa production**:

```yaml
net:
  tls:
    allowInvalidCertificates: true
    allowInvalidHostnames: true
```

Những cờ làm yếu xác minh TLS; trong nhiều tình huống chứng chỉ không hợp lệ có thể giúp hoàn thành phần handshake nhưng **không đủ cho X.509 member authentication**.

**Lý do thường khiến admin muốn bật chúng:**

- CN/SAN không khớp hostname.
- CA chưa được phân phối.
- Certificate hết hạn.
- `clusterFile`/`certificateKeyFile` bị trỏ nhầm.
- Certificate không có `clientAuth`/`serverAuth` cần thiết.
- Clock skew của host khiến thời hạn cert trông không hợp lệ.
- O/OU/DC khác giữa nodes.
- TLS mode chưa nhất quán trong rollout.

Cách đúng là **sửa certificate, trust chain và rollout plan**, không bỏ qua xác minh.

Ngoài ra, TLS server certificate hợp lệ mà không có membership identity phù hợp vẫn không đủ để node gia nhập cluster theo X.509 authentication.

---

## 16. Quy trình chẩn đoán khi member không kết nối được

### 16.1. Tách ba tầng lỗi

```text
Bước A: DNS + TCP connectivity
         |
         v
Bước B: TLS handshake + CA + SAN + EKU
         |
         v
Bước C: MongoDB membership authentication
         |
         v
Bước D: Replication / routing / election
```

**Không** bắt đầu bằng đổi `clusterAuthMode` nếu DNS không phân giải được hoặc port bị firewall chặn.

### 16.2. Những công cụ và quan sát hữu ích

**Tên/địa chỉ:**

```bash
# Chạy từ một host được phép trong môi trường lab.
getent hosts mongo2.example.net

# Kiểm tra TCP reachability (không chứng minh auth thành công).
nc -vz mongo2.example.net 27017
```

**TLS certificate:**

```bash
# Chỉ dùng trong môi trường và đường dẫn bạn sở hữu.
openssl s_client \
  -connect mongo2.example.net:27017 \
  -servername mongo2.example.net \
  -CAfile /etc/mongodb/tls/ca.pem
```

Kết nối TCP/TLS thành công **không** có nghĩa member đã được MongoDB chấp nhận. Cần xem logs server và trạng thái replica set.

**MongoDB (cần quyền tương ứng):**

```javascript
// Trạng thái member, heartbeat errors, election.
rs.status();

// Vai trò và thông tin chính của node.
db.hello();

// Với sharded cluster, kết nối đến mongos:
sh.status();
```

Trong môi trường self-managed, có thể kiểm tra cấu hình đã khởi động bằng lệnh quản trị có quyền phù hợp; tránh in password/key/certificate private key ra stdout.

### 16.3. Đọc log theo nguyên nhân

Các nhóm lỗi thường thấy:

- **Permission denied** khi đọc keyfile.
- **Authentication failed** giữa peers.
- **No common auth mechanism** hoặc mismatch clusterAuthMode.
- **SSL/TLS handshake failed**, certificate verify failed.
- **Hostname mismatch**.
- **Certificate expired/not yet valid**.
- **Member certificate subject/attributes mismatch**.
- **No primary**, unreachable members, heartbeat failures.
- **Unable to reach config servers** hoặc router không kết nối shard.

Thông điệp log thực tế thay đổi theo MongoDB version, không nên dựa vào đúng một string. Tập hợp timestamp, hostname, server version và những thay đổi gần nhất.

---

## 17. Bảng xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra/hướng xử lý |
| --- | --- | --- |
| `mongod` không startup sau khi bật keyfile | Path không tồn tại, owner/permission sai, key format lỗi | Kiểm tra quyền file, service identity, parser và log |
| Node lên nhưng không tham gia replica set | Key không chung, clusterAuthMode lệch | So chính sách, membership secrets, logs |
| Secondary replication dừng sau rotation | Một node chỉ có NEW, peer chỉ có OLD | Khôi phục overlap và quy trình rolling |
| Client cũ không đăng nhập sau bật auth | Chưa tạo user hoặc không cấu hình credentials | Tạo admin/app users theo bootstrap/runbook |
| Client được auth nhưng lệnh bị `Unauthorized` | Thiếu RBAC role | Kiểm tra user roles, không cấp root vội |
| TLS `certificate verify failed` | CA sai, chain thiếu, expired | Xác minh CA, chain, dates |
| TLS hostname mismatch | SAN không khớp DNS hosts trong repl config | Cấp cert có SAN đúng, nhất quán DNS |
| Member X.509 bị reject | O/OU/DC hoặc alternative không khớp | Xem member certificate DN/extension |
| Member cert chỉ có serverAuth | Thiếu clientAuth cho internal client role | Cấp lại certificate EKU phù hợp |
| Lỗi ngay sau đổi CA | Các peers không tin CA mới | Kế hoạch overlap trust chain |
| `mongos` không đọc config metadata | Router/CSRS auth khác nhau hoặc DNS/TLS | Kiểm tra toàn topology, không chỉ shards |
| `rs.status()` thấy nhiều member unhealthy | Network, TLS/auth hoặc election | Thu logs mọi member, kiểm tra majority |
| Không còn primary sau restart nhiều node | Mất voting majority | Dừng rollout, khôi phục quorum an toàn |
| Node khởi động nhưng client chỉ có IP | DNS/TLS SAN khác hoặc address validation | Dùng hostnames phù hợp và SAN |
| Secrets lộ trong Git/CI | Quản lý bí mật sai | Thu hồi, rotate, audit và xóa khỏi luồng phân phối |
| X.509 user có access sai | Nhầm client certificate và member certificate | Tách PKI/identity, kiểm tra separation |
| Kết nối TLS thành công nhưng auth thất bại | TLS != MongoDB membership auth | Kiểm tra clusterAuthMode và DN/key |
| Tắt TLS validation để “sửa nhanh” | Che lỗi CA/SAN và giảm bảo mật | Sửa certificate, không bypass |
| Đổi keyfile trên một shard nhưng router cũ | Không có key chung toàn deployment | Rotation toàn cluster |
| Hết hạn đồng loạt certificate | Không quản lý renewal | Alert và staged rotation có dự phòng |

---

## 18. Replica set health và quorum khi bảo trì authentication

Để duy trì write availability, cần hiểu **majority** trong replica set.

Với **3 voting members**, majority là:

\[
\left\lfloor \frac{3}{2} \right\rfloor + 1 = 2
\]

Nếu restart **hai voting members cùng lúc**, một member còn lại không đủ majority để duy trì/bầu primary. Có thể mất write availability.

### 18.1. Rolling restart có kiểm soát

Một quy trình thường dùng:

1. Xác nhận replica set đang khỏe và replication lag thấp.
2. Restart **một secondary**.
3. Đợi member trở lại healthy/SECONDARY và replication bắt kịp.
4. Lặp với secondary khác nếu cần.
5. **Step down primary** có kế hoạch, chờ new primary election.
6. Restart old primary.
7. Xác nhận `rs.status()`, write path và app errors.

Không chạy đồng thời restart tất cả nodes chỉ vì keyfile rotation cần thay file. Trong sharded cluster, mỗi shard replica set **và CSRS** có quorum riêng; `mongos` routers cần đủ redundancy cho client ingress.

### 18.2. Auth failure có thể ảnh hưởng availability

Khi các members không xác thực được với nhau, một replica set có thể không đủ heartbeat/replication connections để hoạt động bình thường. Điều này có thể gián tiếp làm elections và application writes thất bại.

Chẩn đoán đúng: **mất primary** chỉ là triệu chứng cuối, cần phân biệt network, DNS, TLS handshake và membership authentication failure.

---

## 19. Thiết kế security policy cho production

### 19.1. Tách môi trường

- Production, staging, development có secrets/certificates riêng.
- Không chia sẻ một membership key giữa các clusters không liên quan.
- Member certificates có giới hạn membership rõ theo deployment.
- Có quy trình thu hồi key/certificate khi host hoặc account bị compromise.

### 19.2. Secrets management

- Keyfile và private keys lưu dưới OS ACL nghiêm ngặt.
- Chỉ tiến trình MongoDB/automation được cấp phép được đọc.
- Không log, echo hoặc commit credentials.
- Xoay secret theo chính sách và sau incident.
- Quản lý access trong CI/CD ở mức tối thiểu.
- Có audit ai đã phân phối, thay hoặc đọc secret.

### 19.3. Network protection

- Chỉ mở đúng ports giữa members/routers/config servers và các clients hợp lệ.
- Dùng private networks/security groups/firewalls.
- `net.bindIp` giới hạn endpoints cần thiết.
- Dùng TLS; không expose MongoDB trực tiếp ra Internet.
- DNS hostnames và cert SAN được quản lý cùng topology.

### 19.4. RBAC

- Tạo tài khoản application với role **theo database và thao tác cần thiết**.
- Tách security admin, cluster admin, backup/monitoring identities.
- Không dùng root hoặc `userAdminAnyDatabase` cho application.
- Dùng password prompt hoặc secrets manager thay vì hardcode.

### 19.5. Certificate policy

- Một CA/trust policy thống nhất cho members theo yêu cầu MongoDB.
- SAN chính xác.
- DN/membership extension nhất quán nhưng phân biệt client certificates.
- EKU/KU chính xác.
- Renewal automation và alert trước expiration.
- Quản lý CA rotation.
- Thử trên staging trước production.

### 19.6. Audit và recovery

- Ghi nhận changes tới `security.keyFile`, clusterAuthMode và TLS settings.
- Theo dõi authentication failures và changes tới replica set members.
- Có backup config, CA public chain và secrets retrieval plan.
- Không lưu plaintext secrets không mã hóa trong backup chung.
- Có runbook khi mất một member hoặc mất primary do auth mismatch.
- Tập dượt recovery để tránh “sửa” bằng cách vô hiệu hóa authorization.

---

## 20. Kịch bản 1: một node keyfile khác không được chấp nhận

Giả định:

```text
R1: keyfile = K1
R2: keyfile = K1
R3: keyfile = K2
```

R3 khởi động được `mongod`, nhưng membership auth với R1/R2 có thể thất bại. Vấn đề **không nhất thiết** do replica set config hoặc port 27017.

Các bước xử lý an toàn:

1. Xác minh DNS/TCP tới R3.
2. Xem logs authentication của R3 và peers.
3. Kiểm tra R3 có được phân phối đúng secret version không (không in key).
4. Nếu đây là rotation, xác định mỗi node có khóa overlap hay chưa.
5. Sửa keyfile thông qua secret manager, đúng permission.
6. Restart R3 theo runbook.
7. Đợi R3 healthy và replication bắt kịp.

Không sửa bằng cách bật `authorization: disabled` hoặc đổi replica set config để cho node không được xác thực vào cluster.

---

## 21. Kịch bản 2: X.509 CA đúng nhưng O/OU khác

Giả định:

```text
mongo1:
  CN=mongo1.example.net
  O=ExampleOrg
  OU=MongoDBMembers

mongo2:
  CN=mongo2.example.net
  O=ExampleOrg
  OU=ApplicationClients
```

Cả hai certificates có thể do **cùng CA** cấp, SAN đúng và TLS handshake hợp lệ. Nhưng MongoDB membership auth có thể từ chối `mongo2` vì giá trị `OU` không khớp.

Giải pháp: cấp lại certificate hoặc sửa membership configuration theo policy chính thức, thống nhất O/OU/DC hoặc alternative attributes. Không tắt `enforceUserClusterSeparation` và không bật `allowInvalidCertificates`.

**Bài học:** CA trust và membership identity là **hai kiểm tra khác nhau**.

---

## 22. Kịch bản 3: chỉ một router giữ keyfile cũ

Giả định sharded cluster vừa rotate:

```text
CSRS:     NEW
Shard A:  NEW
Shard B:  NEW
mongos 1: NEW
mongos 2: OLD
```

`mongos 2` có thể bị lỗi khi kết nối tới members chỉ chấp nhận NEW. Những clients được load balancer route tới `mongos 1` vẫn hoạt động, khiến sự cố xảy ra **không đều**.

Điều tra:

- Phân tách client error theo router instance.
- Kiểm tra versions/secrets rollout trên mọi `mongos`.
- Phối hợp rotation toàn cluster theo old+new overlap.
- Không coi thành công trên một router là bằng chứng toàn cluster đã hoàn tất.

---

## 23. Kịch bản 4: đổi keyfile sang X.509 bị mất primary

Một admin đổi ngay R1 thành `x509` trong khi R2/R3 vẫn `keyFile`. R1 và các peers không cùng phương thức chấp nhận/gửi nên authentication failures xuất hiện, làm election/replication không ổn định.

Cách phòng tránh: rollout theo trạng thái:

```text
keyFile
   |
sendKeyFile  (gửi keyfile, chấp nhận cả hai)
   |
sendX509     (gửi certificate, chấp nhận cả hai)
   |
x509         (gửi/nhận certificate)
```

Luôn bảo đảm TLS/CA/certs đã sẵn sàng, chuyển từng node theo hướng dẫn version, giữ majority và monitor recovery. Không sửa theo cách đổi toàn cluster trong một lần không có kế hoạch.

---

## 24. Bộ lệnh và thao tác kiểm chứng

Dưới đây là **bộ công cụ chẩn đoán**, không phải script tự động sửa production.

### 24.1. Kiểm tra trạng thái replica set

Từ user có quyền monitor:

```javascript
const s = rs.status();

printjson({
  set: s.set,
  myState: s.myState,
  members: s.members.map(m => ({
    name: m.name,
    stateStr: m.stateStr,
    health: m.health
  }))
});
```

Nếu member down, cần xem **logs và network** để xác định lỗi. `rs.status()` không chứng minh nội bộ đang dùng keyfile hay X.509; nó cho trạng thái replication/heartbeat.

### 24.2. Kiểm tra router/sharded topology

Từ `mongos` với quyền phù hợp:

```javascript
sh.status();
```

Khi auth mismatch, một phần output/query có thể fail; phân biệt các lỗi membership, TLS, DNS và config metadata.

### 24.3. Kiểm tra certificate không lộ private key

```bash
openssl x509 -in node-member.pem -noout \
  -subject -issuer -dates
```

Kiểm tra SAN và EKU bằng:

```bash
openssl x509 -in node-member.pem -noout -text
```

Lưu ý file đầu vào có thể chứa private key — **chỉ truy cập từ máy/role được phép**; không upload file PEM lên trang web kiểm tra chứng chỉ không tin cậy.

### 24.4. Kiểm tra keyfile permission (Linux)

```bash
# Lệnh đọc metadata trên lab; không in secret.
ls -l /etc/mongodb/cluster.key
stat /etc/mongodb/cluster.key
```

Nếu quyền file là `-rw-r--r--`, group/world có thể đọc secret: **không phù hợp**. Nếu file `-r--------` nhưng owner không phải service user, MongoDB không thể đọc. Sửa owner/permissions theo chính sách thay vì làm rộng quyền.

### 24.5. Không dùng test “không có password vẫn đọc được” trên production

Khi kiểm thử xác thực, dùng môi trường staging hoặc tài khoản kiểm thử và những câu lệnh đọc không gây thay đổi. Mục tiêu là bảo đảm các kết nối không có credentials **không đọc/ghi tài nguyên trái phép**, không phải cố tạo một node giả để kiểm thử trên production.

---

## 25. Câu hỏi quyết định: keyfile hay X.509?

| Tiêu chí | Keyfile | X.509 member auth |
| --- | --- | --- |
| Danh tính | Shared secret trong deployment | Certificate/keypair và membership attributes |
| Khởi tạo | Đơn giản hơn | Cần CA/PKI và cấu hình TLS/certs |
| Chính sách TLS | Phải cấu hình riêng | X.509 yêu cầu TLS |
| Granularity của credential | Thường một/bộ khóa chung | Có thể cấp certificate riêng cho từng node |
| Rotation | YAML nhiều keys + rolling restart | Renew/reissue certificates/CA trust + rollout |
| Khi lộ credential | Có thể ảnh hưởng nhiều members cùng dùng key | Certificate/key riêng có thể giúp khoanh vùng |
| Chi phí vận hành | Quản lý shared secret và file permissions | PKI, SAN, DN/EKU, expiry và CA rotation |
| Khuyến nghị MongoDB | Cơ chế tối thiểu, lab/dev phù hợp | Khuyến nghị cho production |

**Không nên** kết luận X.509 “không thể bị giả mạo”. Nếu private key hoặc CA bị compromise, rủi ro vẫn nghiêm trọng. Lợi ích của PKI phụ thuộc cấp phát, kiểm soát private key, certificate validity, rotation và monitoring đúng.

### 25.1. Với môi trường được quản lý

Atlas và một số giải pháp quản trị MongoDB có cơ chế membership security riêng do nền tảng triển khai. Không áp các lệnh `mongod --keyFile` của self-managed lên một cluster mà bạn không quản lý trực tiếp các tiến trình.

Trong tài liệu vận hành thực tế, phân biệt:

- **Self-managed MongoDB**: nhóm vận hành kiểm soát file config/secret/cert.
- **Managed deployment**: dùng provider UI/API và các controls được công bố.
- **Container/Kubernetes**: secret mounts, operator reconciliation, service DNS và rolling update policy; cấu hình thủ công có thể bị controller ghi đè.

---

## 26. Bảng phân biệt nhanh các thông số

| Thông số | Vai trò | Khi nào dùng |
| --- | --- | --- |
| `security.keyFile` | Đường dẫn shared secret | Membership auth keyfile |
| `--keyFile` | CLI tương đương keyfile config | Lab/automation có kiểm soát |
| `security.authorization` | RBAC cho clients | Bật quyền truy cập |
| `security.clusterAuthMode` | Chế độ internal auth | `keyFile`, `sendKeyFile`, `sendX509`, `x509` |
| `security.transitionToAuth` | Tạm hỗ trợ kết nối đã/chưa auth | Chỉ migration theo tutorial |
| `net.tls.mode` | Chế độ TLS transport | Thường `requireTLS` cho production đích |
| `net.tls.certificateKeyFile` | Server certificate/key | TLS server identity; có thể dùng membership nếu phù hợp |
| `net.tls.clusterFile` | Member certificate/key | Internal X.509 identity |
| `net.tls.CAFile` | CA trust bundle | Xác minh certificates |
| `net.tls.clusterAuthX509.attributes` | Match X.509 DN theo cấu hình | Tùy chọn từ MongoDB 7.0+ |
| `net.tls.clusterAuthX509.extensionValue` | Match certificate extension | Tùy chọn từ MongoDB 7.0+ |
| `replication.replSetName` | Tên replica set | Tất cả data members của set |
| `sharding.clusterRole` | `configsvr` hoặc `shardsvr` | Config servers, shard members |
| `sharding.configDB` | CSRS endpoint list cho `mongos` | Router |
| `net.bindIp` | Interfaces được bind | Giảm network exposure |
| `net.port` | Port tiến trình MongoDB | Kết nối liên thành viên/client |

Điều quan trọng là **nhiều tham số cần đi cùng nhau**. Có `clusterAuthMode: x509` mà thiếu certificate/trust đúng vẫn không chạy, và `security.keyFile` không tự bật `requireTLS`.

---

## 27. Checklist triển khai và thay đổi bảo mật

### Trước triển khai

- [ ] Xác định mọi `mongod` và `mongos`, kể cả CSRS, arbiters và routers dự phòng.
- [ ] Có diagram topology và DNS/ports chính xác.
- [ ] Chọn keyfile hoặc X.509 theo yêu cầu và phiên bản.
- [ ] Đã cấp secret/certificates và phân phối bằng kênh bảo vệ.
- [ ] Đã thử SAN/CA/EKU/DN membership requirements.
- [ ] Có users/RBAC và phương án bootstrap không tự khóa admin.
- [ ] Có TLS/network policy và firewall.
- [ ] Có backup, access to recovery secrets và runbook được duyệt.
- [ ] Có staging test tương đồng topology/version.
- [ ] Có maintenance window và thông tin incident communication.
- [ ] Có monitor quorum, replication lag, app errors và TLS expiry.

### Trong rollout

- [ ] Thay đổi từng member theo đúng thứ tự của tutorial.
- [ ] Không restart nhiều voting members cùng lúc.
- [ ] Đợi member trở lại healthy trước bước tiếp.
- [ ] Đo authentication failures và network/TLS errors.
- [ ] Nếu dùng transitional mode, ghi rõ thời hạn kết thúc.
- [ ] Bảo đảm có key overlap/dual acceptance ở giai đoạn chuyển.
- [ ] Kiểm tra tất cả routers, CSRS, shards đều tương thích.
- [ ] Không tắt certificate validation để xử lý lỗi nhanh.

### Sau rollout

- [ ] `rs.status()` healthy cho từng replica set.
- [ ] `mongos` phục vụ query theo đúng tenant/roles.
- [ ] Không còn node ở transitional mode ngoài kế hoạch.
- [ ] Test user không có quyền bị từ chối đúng cách.
- [ ] Test application credentials/rotation.
- [ ] Audit key/certificate versions và dates.
- [ ] Cập nhật runbook/monitoring/secret inventory.
- [ ] Lên lịch key/certificate rotation tiếp theo.

---

## 28. Bài tập thực hành

### Bài 1 — Hai kênh xác thực

Ứng dụng đăng nhập `mongos` bằng SCRAM user. `mongos` kết nối shard bằng X.509. Có mâu thuẫn không? Cơ chế nào kiểm soát quyền query của user?

**Đáp án:** Không. Client auth và member auth là hai kênh độc lập; RBAC kiểm soát quyền user.

### Bài 2 — Keyfile và TLS

Một replica set có `security.keyFile` nhưng không bật TLS. Dữ liệu replication trên mạng đã được mã hóa đầy đủ chưa?

**Đáp án:** Không suy ra được; keyfile chỉ xác thực thành viên. Cần TLS cho transport encryption.

### Bài 3 — Bí mật chung

Ba nodes có:

```text
A: [K1]
B: [K1, K2]
C: [K2]
```

Mỗi node có khóa chung với node nào? Vì sao không nên giả định trạng thái này luôn là topology ổn định trong một bước rotation đang diễn ra?

**Gợi ý:** A/B chia K1, B/C chia K2, A/C không có khóa chung. Duy trì overlap toàn deployment theo quy trình rolling để tránh đứt kết nối.

### Bài 4 — Linux file permissions

Keyfile có quyền `0644` và tiến trình mongod chạy bằng account `mongodb`. Có vấn đề gì? Quyền an toàn hơn là gì?

**Đáp án:** Group/world có thể đọc; thường đặt owner đúng và `0400`.

### Bài 5 — Khởi tạo replica set

Viết cấu hình `mongod` cho ba nodes có `replSetName: rs0`, keyfile, net.bindIp và TLS. Những field nào giống nhau, field nào riêng từng host?

### Bài 6 — Client chưa có user

Sau khi bật `security.keyFile`, app vẫn dùng URI không credentials. Điều gì xảy ra? Tính năng localhost exception có ý nghĩa gì trong bootstrap?

**Đáp án:** Authorization được bật; app cần user/password hoặc cơ chế client auth được hỗ trợ. Localhost exception chỉ phục vụ tình huống bootstrap hạn chế khi chưa có users.

### Bài 7 — Sharded cluster

Cluster có hai shard replica sets, một CSRS và hai routers. Components nào phải dùng cùng membership auth/keyfile tương thích?

**Đáp án:** Tất cả `mongod` và `mongos`, không chỉ các shard primaries.

### Bài 8 — Cấu hình `mongos`

Vì sao `mongos` cần `sharding.configDB` và `security.keyFile` trong cluster dùng keyfile? Có cần `replication.replSetName` như shard node không?

**Đáp án:** Router cần kết nối CSRS/cluster nội bộ; nó không phải data-bearing replica set member.

### Bài 9 — X.509 attributes

Certificates:

```text
A: O=Company, OU=MongoDBMembers, CN=mongo1.example.net
B: O=Company, OU=MongoDBMembers, CN=mongo2.example.net
C: O=Company, OU=Developers,    CN=mongo3.example.net
```

Nếu chính sách membership match `O` và `OU`, node C có được chấp nhận không?

**Đáp án:** Không, `OU` khác.

### Bài 10 — SAN

Peers kết nối `mongo1.example.net`, nhưng certificate chỉ có `DNS:mongo1.internal.local`. Vấn đề gì và phải sửa bằng cách nào?

**Đáp án:** Hostname validation có thể fail; cấp certificate có SAN khớp tên kết nối hoặc thay cấu hình tên phù hợp theo quy trình. Không bật `allowInvalidHostnames`.

### Bài 11 — EKU

Member dùng `net.tls.clusterFile` nhưng cert chỉ có `serverAuth`. Điều gì có thể lỗi?

**Đáp án:** `clusterFile` cần `clientAuth` khi EKU được khai báo. Cấp lại cert với purpose phù hợp.

### Bài 12 — Dùng một certificate cho hai vai trò

Nếu không có `clusterFile` và dùng `certificateKeyFile` cho cả TLS server lẫn membership, EKU cần gì?

**Đáp án:** Nếu EKU có mặt, cần `serverAuth` và `clientAuth`.

### Bài 13 — Mode matrix

Điền phương thức gửi và nhận của `keyFile`, `sendKeyFile`, `sendX509`, `x509`.

**Đáp án:** Xem bảng mục 10; hai `send*` modes gửi một loại nhưng nhận cả hai.

### Bài 14 — Migration keyfile → X.509

Vì sao không đổi từng member thẳng từ `keyFile` sang `x509`? Hãy trình bày thứ tự rolling migration.

**Đáp án:** Các peers có thể không còn phương thức chung. Dùng `sendKeyFile` → `sendX509` → `x509` sau khi TLS/cert sẵn sàng.

### Bài 15 — Chuyển cluster chưa có authorization

`transitionToAuth` có tác dụng gì và vì sao phải loại bỏ sau migration?

**Đáp án:** Tạm cho phép kết nối đã/chưa xác thực để chuyển đổi; giữ lâu tạo lỗ hổng quyền truy cập.

### Bài 16 — Key rotation

Trình bày các bước `OLD` → `[OLD,NEW]` → `NEW`, bao gồm restart. Vì sao cần ít nhất một khóa chung?

### Bài 17 — Majority

Replica set ba voting members, cùng lúc restart hai nodes. Hậu quả khả dụng ghi có thể là gì?

**Đáp án:** Chỉ còn một vote, không đủ majority để duy trì primary; có thể mất write availability.

### Bài 18 — Certificate expiry

Ba nodes được cấp cert hết hạn cùng một ngày. Đề xuất alert/renewal plan để tránh outages đồng thời.

### Bài 19 — CA vs membership

Certificate client được CA tin cậy ký nhưng có `OU=ApplicationClients`, không khớp `MongoDBMembers`. Nó có được xác nhận là member chỉ vì CA đúng không?

**Đáp án:** Không; cần thỏa membership identity checks.

### Bài 20 — TLS handshake thành công nhưng replication fail

Bạn thấy TCP kết nối được và `openssl s_client` xác minh CA thành công. `rs.status()` vẫn ghi member unreachable/auth failure. Kể ba kiểm tra tiếp theo.

**Gợi ý:** `clusterAuthMode`, keyfile overlap hoặc member DN/extension, certificate EKU, MongoDB logs và replSetName.

### Bài 21 — Sharded router skew

Hai routers, chỉ router1 hoạt động sau rotate NEW. Router2 giữ OLD. Vì sao app có lỗi ngẫu nhiên tùy request?

**Đáp án:** Load balancer có thể đưa request vào router2, không xác thực được với shards/CSRS chỉ nhận NEW.

### Bài 22 — Secrets bị lộ

Một keyfile bị commit vào repo và CI logs. Phản ứng bảo mật nào cần làm ngoài “xóa commit”?

**Gợi ý:** Thu hồi/rotate theo overlap, audit ai truy cập, vô hiệu hóa secret cũ, thay đổi pipeline và lập incident report.

### Bài 23 — Security policy production

So sánh keyfile và X.509 về shared secret, CA/PKI, granular identity, rotation, TLS và operational cost. Chọn phương án cho production có PKI hiện hữu và giải thích.

### Bài 24 — Checklist vận hành

Thiết kế runbook xác thực nội bộ cho sharded cluster 2 shards + 3-node CSRS + 2 mongos: DNS, TLS, CA, secret/certs, rolling rotation, health checks, monitoring và cách xử lý khi mất quorum.

---

## 29. Tổng kết

**Xác thực giữa các thành viên** giúp bảo đảm chỉ những tiến trình `mongod`/`mongos` được cấp membership credential hợp lệ mới có thể tham gia các kết nối nội bộ quan trọng.

Những nguyên tắc cần nhớ:

1. **Internal auth khác client auth/RBAC và TLS.** Cần thiết kế đủ cả các lớp.
2. **Keyfile** dùng shared secret/SCRAM; mọi members cần ít nhất một key chung, file được bảo vệ bởi OS permissions.
3. **X.509** dùng certificate/CA/TLS và matching membership attributes; production nên có PKI/rotation rõ ràng.
4. **SAN và EKU/KU quan trọng**: CA đúng không có nghĩa hostname và membership đúng.
5. **`security.clusterAuthMode` có bốn trạng thái**; `sendKeyFile`/`sendX509` là bước trung gian migration.
6. **Sharded cluster cần bảo vệ mọi `mongod` và `mongos`**; không chỉ data shard primaries.
7. **`security.keyFile` ngụ ý bật client authorization**, vì vậy user bootstrap và RBAC là phần của rollout.
8. **Rotation phải giữ overlap và majority**; không restart nhiều voting members cùng lúc.
9. **Đừng bypass TLS verification hoặc `enforceUserClusterSeparation`** để giải quyết một lỗi certificate.
10. **Dùng logs và health checks theo tầng**: DNS/TCP → TLS → membership auth → replication/routing.
11. **Không đặt credentials trong repository/logs**; dùng secret manager và audit.
12. **Đối chiếu tài liệu theo MongoDB version** trước mọi thay đổi config hoặc migration production.

Một deployment bảo mật tốt không chỉ “bật auth” mà còn có **vòng đời secrets/certificates, khả năng xoay khóa an toàn, phục hồi khi node hỏng và kiểm soát quyền của client đúng mục đích**.

### Tài liệu MongoDB chính thức

- [Self-Managed Internal/Membership Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/) — keyfile/X.509, thuộc tính member certificates.
- [Self-Managed X.509 Authentication](https://www.mongodb.com/docs/manual/core/security-x.509/) — CA, SAN, EKU/KU, phân biệt client/member.
- [Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/) — `security.keyFile`, `security.clusterAuthMode`, `net.tls.*`.
- [Deploy Replica Set with Keyfile Access Control](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set-with-keyfile-access-control/) — bootstrap replica set.
- [Update Replica Set to Keyfile Authentication](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-replica-set/) — bật keyfile trên deployment hiện hữu.
- [Update Replica Set without Downtime](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-replica-set-without-downtime/) — `transitionToAuth` và rolling rollout.
- [Update Sharded Cluster to Keyfile Authentication](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-sharded-cluster/) — CSRS, shards, `mongos`.
- [Verify Cluster Membership with X.509](https://www.mongodb.com/docs/manual/tutorial/configure-x509-member-authentication/) — chuẩn bị chứng chỉ thành viên.
- [Upgrade Keyfile to X.509](https://www.mongodb.com/docs/manual/tutorial/upgrade-keyfile-to-x509/) — `sendKeyFile`, `sendX509`, `x509`.
- [Rotate Keys in Replica Sets](https://www.mongodb.com/docs/manual/tutorial/rotate-key-replica-set/) — nhiều khóa và rolling rotation.
- [Rotate Keys in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/rotate-key-sharded-cluster/) — rotation toàn cluster.
- [Configure MongoDB for TLS](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/) — TLS certificates và CA.
- [Authentication](https://www.mongodb.com/docs/manual/core/authentication/) — user authentication.
- [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/) — phân quyền MongoDB.
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — quorum/primary availability.
