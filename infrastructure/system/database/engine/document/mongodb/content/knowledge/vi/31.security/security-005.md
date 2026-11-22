# TLS cho kết nối ứng dụng và liên lạc nội bộ cụm MongoDB

Một ứng dụng gửi lệnh truy vấn, thông tin xác thực và dữ liệu người dùng tới MongoDB qua mạng. Trong replica set, các thành viên trao đổi heartbeat, oplog và dữ liệu đồng bộ. Trong sharded cluster, `mongos` liên lạc với shards và config servers. Nếu một phần đường truyền này không được bảo vệ, người có khả năng quan sát hoặc can thiệp vào mạng có thể đọc dữ liệu, giả mạo endpoint hoặc sửa traffic.

**TLS (Transport Layer Security)** bảo vệ kết nối đang truyền trên mạng bằng mã hóa, kiểm tra toàn vẹn và xác minh danh tính dựa trên chứng chỉ số. Với MongoDB, phải phân biệt **hai phạm vi**:

1. **Kết nối ứng dụng → MongoDB**: driver, `mongosh`, dịch vụ backend và batch jobs kết nối tới `mongod` hoặc `mongos`.
2. **Liên lạc nội bộ cụm**: thành viên replica set, routers, config servers và shards kết nối với nhau.

Một cluster chỉ bật TLS cho ứng dụng nhưng để liên lạc giữa các nodes ở dạng plaintext **không được mã hóa toàn tuyến**. Ngược lại, TLS nội bộ không bảo vệ kết nối từ ứng dụng nếu client vẫn dùng plaintext. Việc có TLS cũng không đồng nghĩa user đã được **xác thực và phân quyền** trong MongoDB.

Bài thuộc chương **Bảo mật** của module *Database Engine Document MongoDB*. Ví dụ có cấu hình `mongod.conf`, lệnh `mongosh`, Node.js Driver, Java Sync Driver và sơ đồ rollout. Tất cả hostname, đường dẫn certificate và danh tính trong ví dụ đều **giả lập**. Các option và cơ chế thay chứng chỉ phụ thuộc MongoDB server/driver, Feature Compatibility Version, hệ điều hành và dịch vụ managed; phải xác minh theo phiên bản triển khai trước khi dùng trong production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích TLS bảo vệ confidentiality, integrity và server identity.
2. Phân biệt TLS server authentication, mutual TLS (mTLS), SCRAM, `MONGODB-X509` và internal cluster authentication.
3. Hiểu Root CA, intermediate CA, certificate chain, trust store, private key, SAN, EKU và thời hạn.
4. Đọc cấu hình `net.tls.mode`, `certificateKeyFile`, `CAFile`, `clusterFile` và `clusterCAFile`.
5. Bắt buộc TLS cho `mongod`/`mongos` và kiểm soát đường truyền plaintext.
6. Mô tả TLS giữa các thành viên replica set và giữa các thành phần sharded cluster.
7. Phân biệt TLS + keyFile authentication và TLS + x.509 cluster authentication.
8. Kết nối TLS từ `mongosh`, Node.js và Java mà không tắt certificate validation.
9. Thiết lập client certificate khi dùng `MONGODB-X509` theo policy phù hợp.
10. Xây dựng quy trình triển khai theo từng node, xác minh failover và luân chuyển CA/leaf certificate.
11. Phân tích các lỗi certificate chain, SAN, expired cert, EKU, TLS version, clock, DNS và key permissions.
12. Theo dõi TLS handshakes, certificate expiry và cluster availability.
13. Tránh những lựa chọn nguy hiểm như `tlsInsecure` hoặc dùng proxy terminate TLS mà không mã hóa chặng phía sau.

## 2. Threat model: TLS bảo vệ điều gì?

Giả sử một API server gửi query đến `mongo1.db.internal:27017`. Ngay cả trong private network, traffic có thể đi qua nhiều thiết bị mạng, máy ảo, vùng quản lý và gateway. Nếu một thành phần bị xâm nhập, plaintext có thể làm lộ query, dữ liệu nhạy cảm hoặc thông tin kết nối.

| Thuộc tính | TLS đóng góp | Tình huống |
|---|---|---|
| Confidentiality | Mã hóa bytes trên đường truyền | Kẻ nghe lén không đọc nội dung document |
| Integrity | Phát hiện thay đổi trái phép | Gói dữ liệu không thể bị sửa lặng lẽ rồi vẫn được chấp nhận như nguyên vẹn |
| Server authentication | Xác minh server certificate/hostname | Client tránh kết nối nhầm endpoint giả mạo |
| Client authentication (khi mTLS) | Server xác minh client certificate | Áp chính sách certificate identity phía client |

### 2.1. TLS không thay các lớp an ninh khác

- **MongoDB authorization:** kiểm tra user/role, quyền đọc/ghi database và collection.
- **Ứng dụng:** xác thực principal, kiểm tra quyền tenant/owner, ngăn injection.
- **Encryption at rest:** bảo vệ dữ liệu lưu trên disk/backup.
- **Field-level encryption:** bảo vệ trường nhạy cảm ngay từ client nếu cần.
- **Network controls:** firewall, private subnet, least exposure.
- **Audit và secret management:** theo dõi truy cập, bảo vệ credentials và private keys.

Một kết nối được mã hóa tới server thật vẫn có thể thực thi query sai nếu ứng dụng xây truy vấn không an toàn hoặc cấp role quá rộng.

### 2.2. Internal network không tự an toàn

Việc một hostname có đuôi `.internal` hoặc nằm trong VPC không bảo đảm traffic không bị quan sát. Vẫn cần TLS, nhất là giữa availability zones, clusters, datacenters hoặc nhiều nhóm quản trị hạ tầng.

## 3. Sơ đồ hai tuyến kết nối

### 3.1. Replica set

~~~mermaid
flowchart TD
    App["Ứng dụng / mongosh"] -->|"TLS"| P["mongod Primary"]
    App -->|"TLS khi đọc member tương ứng"| S1["mongod Secondary A"]
    App -->|"TLS khi đọc member tương ứng"| S2["mongod Secondary B"]
    P <-->|"TLS nội bộ: replication/heartbeat"| S1
    P <-->|"TLS nội bộ: replication/heartbeat"| S2
    S1 <-->|"TLS nội bộ"| S2
~~~

Với driver replica set, ứng dụng thường khám phá những hostname từ cấu hình cluster. Vì vậy certificate phải phù hợp **hostname mà driver thực tế kết nối**, không chỉ hostname ban đầu trong URI.

### 3.2. Sharded cluster

~~~mermaid
flowchart TD
    Client["Application/driver"] -->|"TLS"| Router["mongos"]
    Router <-->|"TLS nội bộ"| Config["Config Server Replica Set"]
    Router <-->|"TLS nội bộ"| ShardA["Shard A Replica Set"]
    Router <-->|"TLS nội bộ"| ShardB["Shard B Replica Set"]
    ShardA <-->|"Các kết nối quản trị/metadata cần bảo vệ"| Config
    ShardB <-->|"Các kết nối quản trị/metadata cần bảo vệ"| Config
~~~

Mỗi shard và config server lại có những `mongod` members trao đổi replication traffic. Cần kiểm kê toàn bộ luồng, không chỉ đường ứng dụng đến router.

## 4. TLS handshake và MongoDB authentication

~~~mermaid
sequenceDiagram
    participant App as MongoDB Driver
    participant Server as mongod / mongos
    App->>Server: TLS handshake
    Server-->>App: Certificate và chain
    App->>App: Verify CA, SAN, expiry, key usage
    App->>Server: Hoàn tất tạo khóa phiên
    Note over App,Server: Kênh TLS được thiết lập
    App->>Server: MongoDB authentication (ví dụ SCRAM)
    Server-->>App: Auth outcome
    App->>Server: ping / find / aggregate
~~~

Sơ đồ mô tả ý nghĩa, không phải thứ tự chính xác của mọi TLS 1.2/1.3 packet. Điểm quan trọng là **TLS channel được tạo trước MongoDB protocol commands**.

### 4.1. Các câu hỏi xác minh

Client cần xác nhận:

1. Certificate được ký bởi CA/chuỗi issuer đáng tin.
2. Chứng chỉ có hiệu lực về thời gian.
3. DNS name/IP dùng khi kết nối khớp **Subject Alternative Name**.
4. Key usage và Extended Key Usage (EKU) phù hợp mục đích.
5. TLS protocol, cipher suites và algorithms được phép.
6. Revocation được xử lý theo cơ chế/chính sách của triển khai nếu hỗ trợ.

Nếu certificate hợp lệ về chữ ký nhưng SAN không khớp hostname, client phải từ chối theo hostname verification thông thường.

### 4.2. TLS ≠ login

Sau khi hoàn tất TLS, MongoDB vẫn có thể yêu cầu **SCRAM username/password** hoặc **MONGODB-X509 certificate-based authentication**. Cơ chế login và roles là lớp độc lập với việc mã hóa transport.

## 5. TLS server-auth, mTLS, SCRAM và x.509

| Kịch bản | Server trình certificate | Client trình certificate | Authentication vào MongoDB |
|---|---|---|---|
| TLS + SCRAM | Có | Không nhất thiết | Username/password SCRAM |
| mTLS + SCRAM | Có | Có | Có thể vẫn là SCRAM theo policy |
| TLS + `MONGODB-X509` | Có | Có | Certificate subject/identity ánh xạ MongoDB user |
| TLS nội bộ + keyFile | Có TLS credentials | Theo trust/internal TLS configuration | Shared keyFile secret |
| TLS nội bộ + cluster x.509 | Có | Có certificate identity phù hợp | Internal x.509 authentication |

### 5.1. Khi ứng dụng dùng SCRAM

Ứng dụng có thể kết nối TLS mà **không có client certificate** nếu server policy cho phép. Client vẫn phải xác minh server certificate, và user vẫn phải login bằng SCRAM.

### 5.2. Khi ứng dụng dùng mTLS

Server có thể yêu cầu/trust certificate client. Tuy nhiên, một client certificate được TLS layer chấp nhận **không tự động cấp MongoDB roles**. Nếu sử dụng `MONGODB-X509`, phải provision identity trong `$external` và gán roles phù hợp.

### 5.3. Internal auth khác app auth

Các thành viên replica set/sharded cluster dùng phương thức riêng để chứng minh là members hợp lệ. Không dùng credential/member certificate nội bộ như credential cho một ứng dụng nghiệp vụ.

## 6. PKI: CA, leaf certificate, key và trust store

Một hệ thống PKI thường có:

- **Root CA:** gốc tin cậy, private key phải được bảo vệ nghiêm ngặt.
- **Intermediate CA:** có thể ký server/client certificates thay root.
- **Leaf server certificate:** certificate của `mongod`/`mongos`.
- **Leaf client certificate:** khi client mTLS/x.509 được yêu cầu.
- **Private key:** bí mật tương ứng certificate leaf; chỉ đặt ở chủ thể sở hữu.
- **Trust store / CA bundle:** các CA certificate công khai được tin cậy.

~~~mermaid
flowchart TD
    Root["Root CA"] --> Intermediate["Intermediate CA"]
    Intermediate --> MongoCert["MongoDB server leaf"]
    Intermediate --> AppCert["Application client leaf (nếu dùng mTLS)"]
    TrustApp["Application trust store"] -->|"Xây certificate chain"| MongoCert
    TrustMongo["MongoDB trust CA"] -->|"Xác minh peer"| AppCert
~~~

### 6.1. Certificate chain

Peer cần xây được đường tin cậy từ leaf tới CA đã được trust. Thiếu intermediate có thể gây lỗi dù root CA hiện diện trong trust store. Tùy hệ thống, cần server gửi leaf và intermediate chain thích hợp.

### 6.2. Public certificate khác private key

Certificate chứa public key/identity và có thể được phân phối theo policy. Private key là bí mật: không commit Git, không gắn vào Docker image public, không gửi qua issue tracker hay email không an toàn. Giới hạn file permissions và áp dụng secret manager/volume bảo mật.

### 6.3. PEM và các đường dẫn minh họa

~~~text
/etc/mongodb/tls/mongo1.pem       server certificate + private key
/etc/mongodb/tls/ca-chain.pem     CA/intermediate public certificates
/etc/mongodb/tls/cluster1.pem     internal client certificate/key khi tách riêng
/etc/mongodb/secrets/cluster.key  keyFile secret nếu dùng keyFile auth
~~~

`certificateKeyFile` có thể chứa private key, còn `CAFile` là trust material. Không hoán đổi hai loại file.

## 7. SAN, CN và EKU

### 7.1. SAN

Nếu replica set quảng bá:

~~~javascript
rs.conf().members.map(m => m.host)
// [
//   "mongo1.db.internal:27017",
//   "mongo2.db.internal:27017",
//   "mongo3.db.internal:27017"
// ]
~~~

Certificate của `mongo1` cần có `DNS:mongo1.db.internal` trong SAN. Port không thuộc DNS SAN. Nếu ứng dụng kết nối bằng IP, phải có IP SAN phù hợp hoặc thay bằng DNS hostname được certificate bao phủ.

### 7.2. Không dựa CN-only

Các TLS clients hiện đại chủ yếu xác minh hostname qua **SAN**, không xem CN-only certificate như cấu hình đáng tin cậy lâu dài. Cấp leaf certificates với DNS SAN rõ ràng theo tên endpoint canonical.

### 7.3. EKU

- `serverAuth` dành cho certificate đóng vai TLS server.
- `clientAuth` dành cho certificate đóng vai TLS client.

MongoDB member có thể vừa nhận kết nối vừa mở kết nối nội bộ. Certificate dùng cho từng vai trò phải có EKU/usage phù hợp. Với cluster x.509 có quy tắc subject và EKU cụ thể, phải kiểm tra profile theo phiên bản.

### 7.4. Thời hạn và đồng hồ

`NotBefore`, `NotAfter` quyết định thời gian hiệu lực. Clock sai/NTP hỏng có thể khiến một certificate được hiểu là hết hạn hoặc chưa có hiệu lực. Cần giám sát **đồng hồ hệ thống và expiry của mọi endpoint**.

## 8. Chuẩn bị certificate lab

Với một replica set lab do bạn quản lý, nên:

1. Cấp CA riêng cho môi trường lab, không dùng CA production.
2. Cấp mỗi server leaf certificate có SAN phù hợp hostname.
3. Chọn EKU `serverAuth`, thêm `clientAuth` khi vai trò nội bộ yêu cầu.
4. Tạo PEM certificate + private key theo cấu hình MongoDB.
5. Bảo đảm server đọc được key, user khác không đọc được.
6. Phân phối CA public cert cho app/peer trust.
7. Xác minh certificate chain, SAN và thời hạn trước khi khởi động.

### 8.1. Kiểm tra certificate với OpenSSL

~~~bash
openssl x509 -in mongo1.crt -noout -subject -issuer -dates
openssl x509 -in mongo1.crt -noout -ext subjectAltName
openssl x509 -in mongo1.crt -noout -ext extendedKeyUsage
~~~

Đây là công cụ **kiểm tra**, không tạo ra chứng chỉ production. PKI production cần chuẩn issuer, SAN, subject, EKU, key algorithm, expiration và rotation.

### 8.2. Bảo vệ private key

Không copy private key vào tickets, logs, artifacts hay các câu lệnh chia sẻ. Nếu nghi ngờ lộ private key, phải có quy trình thu hồi/thay certificate phù hợp và đánh giá blast radius.

## 9. `net.tls.mode: requireTLS` cho `mongod`

Ví dụ một thành viên replica set dùng TLS với SCRAM clients và keyFile nội bộ:

~~~yaml
# /etc/mongod.conf, ví dụ rút gọn
net:
  bindIp: 127.0.0.1,mongo1.db.internal
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1.pem
    CAFile: /etc/mongodb/tls/ca-chain.pem
    allowConnectionsWithoutCertificates: true

replication:
  replSetName: rs0

security:
  authorization: enabled
  keyFile: /etc/mongodb/secrets/cluster.key
~~~

### 9.1. Ý nghĩa option

| Option | Vai trò |
|---|---|
| `net.tls.mode: requireTLS` | Yêu cầu kết nối TLS, không nhận MongoDB plaintext traffic |
| `certificateKeyFile` | PEM chứa server certificate/private key |
| `CAFile` | CA trust material dùng xác minh peer theo cấu hình |
| `allowConnectionsWithoutCertificates: true` | Cho phép TLS client không trình certificate; hữu ích khi app dùng SCRAM |
| `security.authorization: enabled` | Bật kiểm tra MongoDB user roles |
| `security.keyFile` | Shared secret xác thực nội bộ theo keyFile mode |
| `replication.replSetName` | Tên replica set; không phải thiết lập TLS |

**Chú ý:** `allowConnectionsWithoutCertificates:true` không cho phép **plaintext** khi `mode:requireTLS`. Nó chỉ cho phép clients không trình **TLS client certificate**. Nếu không dùng client cert, vẫn phải có database credentials đúng.

### 9.2. `bindIp`/firewall vẫn quan trọng

TLS không thay network segmentation. Không mở `27017` ra Internet tùy tiện. Chỉ bind network interfaces cần thiết và giới hạn nguồn truy cập.

### 9.3. Một cert cho mọi node?

Theo policy có thể dùng SAN certificate chứa nhiều tên, nhưng chia sẻ một private key giữa nhiều máy sẽ làm tăng phạm vi rủi ro nếu một máy bị chiếm. Ưu tiên identity/key riêng cho mỗi endpoint khi PKI/topology cho phép.

## 10. Các chế độ TLS ở MongoDB server

`net.tls.mode` thường có:

| Mode | Ý nghĩa | Vai trò |
|---|---|---|
| `disabled` | TLS không được bật | Không phù hợp mục tiêu mã hóa traffic production |
| `allowTLS` | Chấp nhận TLS và non-TLS trong cấu hình chuyển tiếp | Migration có kiểm soát |
| `preferTLS` | Chấp nhận mixed inbound, ưu tiên TLS cho outbound nội bộ theo cơ chế server | Chuyển tiếp giữa các modes |
| `requireTLS` | Chỉ nhận kết nối TLS | Trạng thái đích |

### 10.1. Chuyển đổi theo từng node

Không bật `requireTLS` trên một primary khi peers/clients chưa được phát hành certificate/trust. Nếu các member không thể kết nối, replica set có thể mất majority, replication hoặc availability.

### 10.2. Transitional modes phải có hạn chót

`allowTLS`/`preferTLS` tồn tại để hỗ trợ mixed cluster trong giai đoạn chuyển đổi; còn plaintext thì traffic vẫn có khả năng bị quan sát. Theo dõi luồng không TLS và đặt lịch hoàn tất `requireTLS`, không để mixed mode kéo dài không kiểm soát.

### 10.3. Config vs driver options

Trong `mongod.conf` dùng `net.tls.*`; ở Node.js thường dùng `tls`/`tlsCAFile`; ở URI dùng `tls=true`. Không dùng tên option của driver trong file server config.

## 11. TLS nội bộ replica set: keyFile và x.509

**TLS** bảo vệ network; **internal authentication** xác thực một node được phép tham gia cụm. Hai khái niệm này có thể kết hợp theo nhiều cách.

### 11.1. TLS + keyFile

~~~text
Kênh member A ↔ member B: được bảo vệ bằng TLS
Internal identity: shared security.keyFile secret
Application auth: SCRAM hoặc cơ chế client auth đã cấu hình
~~~

Đây là cấu hình có thể dùng trong replica set. KeyFile không tự mã hóa replication, và TLS không tự thay shared internal secret.

### 11.2. TLS + x.509 cluster authentication

MongoDB có thể xác thực members bằng certificates qua `security.clusterAuthMode: x509` theo phiên bản/topology hỗ trợ.

~~~yaml
# Ví dụ hướng thiết kế x.509 internal authentication
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1-server.pem
    CAFile: /etc/mongodb/tls/app-client-ca.pem
    clusterFile: /etc/mongodb/tls/mongo1-cluster.pem
    clusterCAFile: /etc/mongodb/tls/cluster-ca.pem

replication:
  replSetName: rs0

security:
  authorization: enabled
  clusterAuthMode: x509
~~~

`clusterFile` có thể cung cấp certificate/private key riêng khi node xác thực tới peers; `clusterCAFile` đóng vai trò trust nội bộ trong mô hình tách CA. Cấu hình này chỉ là **minh họa các vai trò**, phải đối chiếu chuẩn cert subject, DN, EKU, CA trust và phiên bản cụ thể trước khi áp dụng.

### 11.3. Quy tắc cluster member certificate

Internal x.509 authentication có những yêu cầu riêng đối với certificate identity, như sự nhất quán các thuộc tính subject **O/OU/DC** giữa members theo quy tắc MongoDB, cùng chứng chỉ phù hợp vai trò client/server TLS. Không tự ký một leaf cert bất kỳ rồi kỳ vọng `clusterAuthMode:x509` chấp nhận.

### 11.4. Migrate internal auth là thay đổi riêng

Chuyển từ keyFile sang x.509 internal auth **không chỉ là bật TLS**. Nó thay cách nodes xác minh nhau và có thể cần modes chuyển tiếp/rolling procedure riêng. Không đổi đồng thời CA, hostname, clusterAuthMode và network topology trong một lần không có phương án rollback.

## 12. Internal TLS ở sharded cluster

| Nguồn | Đích | Lý do bảo vệ |
|---|---|---|
| Application | `mongos` | Query/data/auth |
| `mongos` | Config server replica set | Metadata/cluster control |
| `mongos` | Shard replica sets | Routed commands/data |
| Các members trong từng shard | Peers trong replica set | Replication/heartbeat |
| Các config server members | Peers CSRS | Replication/heartbeat |
| Cluster components khác | Endpoints cần thiết | Coordination và maintenance |

### 12.1. `mongos` có certificate

Vì client kết nối router, `mongos` phải có server certificate phù hợp hostname mà client sử dụng. Đồng thời router phải xác minh và được peers nội bộ chấp nhận theo policy.

### 12.2. Không chỉ một shard

Khi thêm shard mới, cần cấp certificate/SAN và internal identity hợp lệ cho mọi member của shard; kiểm tra trust của routers/config servers và replica set health. Một shard có certificate hết hạn có thể làm lỗi chỉ một phần workload, khó phát hiện nếu chỉ ping router.

### 12.3. TLS không định tuyến query

TLS bảo vệ network, không giúp `mongos` tìm đúng shard nhanh hơn và không thay shard key/index. Nếu query scatter-gather chậm, phải phân tích routing, data distribution, index và network, không tắt TLS để che vấn đề query plan.

## 13. Hostname discovery và SAN

Replica set driver có thể bắt đầu từ một seed host rồi khám phá toàn bộ members:

~~~text
Seed URI: mongo-entry.example.internal
Advertised: mongo1.db.internal
            mongo2.db.internal
            mongo3.db.internal
~~~

Vì vậy mọi advertised hostname cần:

- DNS resolution từ client environment.
- Network connectivity.
- Leaf certificate SAN phù hợp.
- Trust chain được client tin.

### 13.1. Failover làm lộ lỗi cert

Ứng dụng có thể kết nối `mongo1` tốt nhiều tuần, nhưng khi `mongo2` được bầu primary mới thì hostname mismatch hoặc unknown CA xuất hiện. Phải test failover/secondary selection trước production.

### 13.2. IP address và DNS SAN

URI `mongodb://10.20.0.5:27017` không nhất thiết khớp certificate chỉ có `DNS:mongo1.db.internal`. Dùng canonical DNS hoặc cấp IP SAN phù hợp. Đừng dùng `tlsAllowInvalidHostnames` làm cách sửa.

### 13.3. Kubernetes/containers

Trên Kubernetes, certificate phải bao phủ tên mà MongoDB members quảng bá qua StatefulSet/service discovery. Không chỉ cấp `DNS:localhost` rồi dùng qua tên Pod FQDN. Nếu dùng operator có certificate management tích hợp, ưu tiên quy trình của operator.

## 14. Mongosh với TLS server authentication + SCRAM

Kết nối:

~~~bash
mongosh "mongodb://mongo1.db.internal:27017/?tls=true" \
  --tlsCAFile /etc/app/tls/mongo-ca.pem \
  --username appUser \
  --authenticationDatabase admin
~~~

Mongosh có thể prompt password theo chế độ phù hợp, giúp tránh đưa secret trực tiếp vào command history.

Kết nối replica set:

~~~bash
mongosh "mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/?replicaSet=rs0&tls=true" \
  --tlsCAFile /etc/app/tls/mongo-ca.pem \
  --username appUser \
  --authenticationDatabase admin
~~~

Sau khi kết nối:

~~~javascript
db.adminCommand({ ping: 1 })
db.runCommand({ connectionStatus: 1 })
~~~

`ping` xác nhận server xử lý lệnh và TLS handshake đã vượt qua bước kết nối; `connectionStatus` cho thông tin auth/roles, không phải danh sách đầy đủ TLS protocol/cipher.

### 14.1. Không hardcode password

Không để password thật ở URI trong source code, CI logs, screenshot hoặc shell history. Dùng secret manager và cơ chế truyền credentials được bảo vệ. Những ký tự đặc biệt trong URI credentials còn phải được encode đúng khi dùng định dạng URI.

### 14.2. TLS validation ở client

`--tlsCAFile` phải trỏ CA public cert/bundle đúng. Nếu cert thiếu SAN hoặc hết hạn, sửa certificate/hostname thay vì bỏ kiểm tra.

## 15. Node.js Driver với TLS và SCRAM

~~~javascript
import { MongoClient } from "mongodb";

const uri =
  "mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/" +
  "?replicaSet=rs0&authSource=admin&tls=true";

const client = new MongoClient(uri, {
  auth: {
    username: process.env.MONGODB_USERNAME,
    password: process.env.MONGODB_PASSWORD
  },
  tls: true,
  tlsCAFile: "/etc/app/tls/mongo-ca.pem",
  serverSelectionTimeoutMS: 5000
});

try {
  await client.connect();
  console.log(await client.db("admin").command({ ping: 1 }));
} finally {
  await client.close();
}
~~~

### 15.1. Option Node.js

| Option | Ý nghĩa |
|---|---|
| `tls: true` | Bật TLS |
| `tlsCAFile` | CA bundle để xác minh server |
| `tlsCertificateKeyFile` | Client cert + private key nếu cần mTLS |
| `tlsCertificateKeyFilePassword` | Password mở client private key nếu cấu hình có hỗ trợ |
| `serverSelectionTimeoutMS` | Thời gian chọn server, không trực tiếp bỏ qua lỗi TLS |

Khi CA của MongoDB là private, `tlsCAFile` giúp ứng dụng tin issuer đúng. Với public CA được default trust store tin, yêu cầu cụ thể có thể khác.

### 15.2. Reuse MongoClient

Tạo một MongoClient cho mỗi HTTP request làm tăng TLS handshakes, CPU, latency và số sockets. Hãy reuse connection pool theo lifecycle service; chỉ đóng ở shutdown hoặc khi cần thay thiết lập có kiểm soát.

### 15.3. Tránh anti-pattern

~~~javascript
// KHÔNG dùng trên production.
const unsafe = new MongoClient(uri, {
  tls: true,
  tlsAllowInvalidCertificates: true,
  tlsAllowInvalidHostnames: true
});
~~~

Các flags bỏ qua kiểm tra certificate/hostname làm yếu cơ chế xác minh peer, có thể cho phép MITM. Chúng không phải giải pháp khi CA/SAN chưa đúng.

## 16. Java Sync Driver: TLS với CA trust

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class MongoTlsDemo {
    public static void main(String[] args) {
        String uri =
            "mongodb://mongo1.db.internal:27017," +
            "mongo2.db.internal:27017," +
            "mongo3.db.internal:27017/" +
            "?replicaSet=rs0&tls=true";

        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                System.getenv("MONGODB_USERNAME"),
                "admin",
                System.getenv("MONGODB_PASSWORD").toCharArray()
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

### 16.1. Java trust store

Nếu CA private không có trong JVM default truststore, có thể dùng PKCS#12 truststore hoặc custom SSLContext theo tổ chức.

~~~bash
# Chỉ minh họa tên option. Đừng đưa mật khẩu thật vào command history.
java \
  -Djavax.net.ssl.trustStore=/etc/app/tls/mongo-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=PLACEHOLDER_FROM_SECRET \
  -jar app.jar
~~~

Trên production, secret cần được cấp phát theo phương thức bảo mật, không commit vào script. JVM/JDK version và truststore reload policy có thể khác Node.js. Không dùng TrustManager “trust all”.

### 16.2. Hostname verification

Java driver phải xác minh SAN của server. Với replica set, certificate phải phù hợp mọi advertised hostname; một seed host thành công không chứng minh failover sẽ thành công.

### 16.3. TLS versions

Hỗ trợ TLS 1.2/1.3 phụ thuộc MongoDB server, JDK/Java TLS provider, hệ điều hành/OpenSSL và security policy. Nếu handshake failure do protocol/cipher mismatch, kiểm tra versions và ciphers, không tắt toàn bộ certificate validation.

## 17. Client certificate với `MONGODB-X509`

Để xác thực app bằng certificate:

1. PKI cấp client leaf cert + private key với EKU phù hợp (`clientAuth`).
2. Server trust CA ký client certificate.
3. Driver trình client certificate trong TLS handshake.
4. MongoDB nhận diện subject/identity theo cơ chế `MONGODB-X509`.
5. User tương ứng trong `$external` được cấp roles.

### 17.1. Mongosh

~~~bash
mongosh "mongodb://mongo1.db.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external" \
  --tlsCAFile /etc/app/tls/mongo-server-ca.pem \
  --tlsCertificateKeyFile /etc/app/tls/app-client.pem
~~~

`%24external` là cách encode `$external` trong URI. Username/subject mapping và tùy chọn driver phải theo MongoDB version, không đặt identity tùy ý.

### 17.2. Node.js

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  "mongodb://mongo1.db.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external",
  {
    tls: true,
    tlsCAFile: "/etc/app/tls/mongo-server-ca.pem",
    tlsCertificateKeyFile: "/etc/app/tls/app-client.pem"
  }
);

try {
  await client.connect();
  console.log(await client.db("admin").command({ ping: 1 }));
} finally {
  await client.close();
}
~~~

### 17.3. Không tự động có quyền

Client cert do CA tin ký chỉ cho phép TLS layer xác minh certificate; MongoDB vẫn cần user/identity và roles tương ứng để thực thi commands. Không dùng certificate của cluster member như client app credential.

### 17.4. mTLS không cần thiết cho mọi ứng dụng

Nếu policy cho phép TLS server-auth + SCRAM, ứng dụng không cần client certificate riêng. Quyết định dùng mTLS dựa trên threat model và chi phí cấp phát/rotation, không phải một mặc định bắt buộc của mọi MongoDB TLS deployment.

## 18. Phân biệt authentication failure và TLS handshake failure

| Triệu chứng | Tầng lỗi | Cần kiểm tra |
|---|---|---|
| `certificate verify failed` | TLS trust | CA/intermediate/chain |
| `hostname mismatch` | TLS peer identity | SAN, DNS, URI host |
| `certificate expired` | TLS validity | Expiry, NTP/clock |
| `unsupported protocol` | TLS negotiation | MongoDB/JDK/Node/OpenSSL versions |
| `bad decrypt`/PEM error | TLS private key | File format, key password |
| `permission denied` đọc PEM | OS security | Ownership/mount mode |
| `Authentication failed` | MongoDB auth sau TLS | User/password/authSource/x509 subject |
| `Unauthorized` | MongoDB RBAC | Roles/permissions |
| `ServerSelectionTimeout` | Driver topology/connectivity | Nested TLS/DNS/network cause |

Một lỗi TLS thường xuất hiện **trước** MongoDB user authentication. Nếu TLS đã thành công nhưng username/password sai, sửa database credentials/roles thay vì đổi server certificate.

### 18.1. Nested cause

Driver có thể chỉ báo `MongoServerSelectionError` hoặc Java `MongoTimeoutException` ở cấp ngoài. Cần xem nested cause/driver logs để phát hiện certificate/SAN/DNS thực sự lỗi, nhưng phải redact URI credentials.

### 18.2. Một client thành công không chứng minh clients khác cũng được

`mongosh` có thể dùng `--tlsCAFile` đúng, còn Java process thiếu CA trong truststore. Node có thể tin CA nhờ `tlsCAFile` trong khi một container image mới thiếu file. Hãy kiểm tra **môi trường tin cậy thực tế** của từng runtime.

## 19. Kiểm tra TLS endpoint bằng OpenSSL

Chỉ kiểm tra endpoint mà bạn được phép:

~~~bash
openssl s_client \
  -connect mongo1.db.internal:27017 \
  -servername mongo1.db.internal \
  -CAfile /etc/app/tls/mongo-server-ca.pem \
  -verify_return_error
~~~

Quan sát certificate chain, issuer, validity, verify result, SNI và protocol/cipher (nếu công cụ hiển thị). Kiểm tra leaf certificate trên filesystem:

~~~bash
openssl x509 -in /etc/mongodb/tls/mongo1.crt \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

### 19.1. Đừng bỏ verification trong tool rồi kết luận an toàn

Một probe có thể thiết lập TLS encryption nhưng không kiểm tra chain/hostname đầy đủ nếu gọi sai flags. Dùng output chẩn đoán với validation phù hợp và đối chiếu lại bằng driver thật.

### 19.2. Ping sau OpenSSL

`openssl s_client` chỉ giúp chẩn đoán TLS, không chứng minh MongoDB auth/topology hoạt động. Tiếp tục dùng `mongosh`/driver chạy `ping`, kiểm tra user roles và kết nối sau failover.

## 20. Rollout TLS cho replica set

Không bật requireTLS một cách ngẫu nhiên trên cluster đang hoạt động. Một rollout có kiểm soát:

1. Inventory members, advertised hostnames, client environments và CA/trust.
2. Cấp và phân phối certificate cho **mọi node**; kiểm tra SAN/EKU/expiry/key permissions.
3. Cập nhật driver trust và thử trên staging.
4. Dùng chế độ migration như `allowTLS`/`preferTLS` nếu cần, **theo quy trình hỗ trợ của version**.
5. Rolling update members, thường xử lý secondaries theo runbook trước và giữ majority.
6. Kiểm tra replication lag, heartbeat, election status và kết nối client.
7. Đảm bảo không còn plaintext clients, chuyển mọi member sang `requireTLS`.
8. Test failover và kết nối tới các advertised hostnames.
9. Thiết lập monitoring expiry/handshake và đánh dấu migration hoàn tất.

Đây là **kế hoạch khái niệm**, không thay thế command sequence của server version cụ thể. Một số thay đổi cần restart/rolling reconfiguration, một số certificate rotation có command riêng.

### 20.1. Vì sao secondary-first thường hữu ích?

Giữ primary và majority trong quá trình rolling update giúp hạn chế downtime, nhưng cần tính topology/độ sẵn sàng thực tế. Không restart nhiều voting members cùng lúc nếu có nguy cơ mất quorum.

### 20.2. Test failover thật

Một kết nối bình thường có thể chỉ tiếp xúc mongo1. Sau chuyển primary, driver phải nói chuyện với mongo2/mongo3; nếu các cert SAN khác nhau hoặc CA trust sai, sự cố mới xuất hiện. Kiểm tra tất cả nodes và routes.

## 21. Rollout trong sharded cluster

Ngoài những bước của từng replica set, cần kiểm tra:

- Các mongos routers có certificate/trust đúng.
- Config server replica set giữ majority và metadata availability.
- Các shard replica sets có TLS và internal auth đồng nhất.
- Mongos↔config servers và mongos↔shards hoạt động.
- Mọi cluster members dùng certificate identity phù hợp (nếu cluster x.509).
- Router mới thêm vào không bị thiếu CA/cert.
- Application chỉ truy cập qua endpoint mongos phù hợp topology, nếu đó là kiến trúc của cụm.

### 21.1. Không đổi toàn cụm cùng lúc

Đổi tất cả mongos, config servers và shards trong một bước không có overlap/rollback có thể làm mất availability. Phân nhỏ, test và giám sát chặt từng nhóm cấu phần.

### 21.2. Bảo vệ cả traffic điều phối

TLS ở ứng dụng→mongos chưa đủ. Nếu chặng mongos→shards là plaintext, dữ liệu MongoDB có thể hiện rõ trên đường nội bộ. Phải kiểm kê các network segments thực tế, kể cả giữa availability zones.

## 22. CA rotation và overlap trust

Đổi leaf certificate cùng CA thường ít tác động tới trust stores. Đổi **issuer CA** có thể làm client và nodes mất khả năng xác minh toàn bộ endpoints.

~~~mermaid
flowchart LR
    Old["Clients chỉ trust CA cũ"] --> Bundle["Phân phối trust: CA cũ + CA mới"]
    Bundle --> Rotate["Đổi leaf cert sang CA mới"]
    Rotate --> Verify["Kiểm tra mọi nodes/clients"]
    Verify --> Remove["Gỡ CA cũ khi không còn dependency"]
~~~

### 22.1. Quy trình tham khảo

1. Phát hành CA mới, kiểm tra chain và policy.
2. Thêm CA mới vào trust bundles của mọi clients/peers mà vẫn giữ CA cũ khi cần overlap.
3. Xác minh process Java/Node/mongosh thực sự sử dụng trust mới; một số process cần restart/reload.
4. Luân chuyển server/internal leaf certificates theo rolling plan.
5. Kiểm tra connections **mới**, auth, replication, failover và mongos routing.
6. Chỉ loại CA cũ khi đã xác nhận không còn certificate/dependency cần CA đó.

### 22.2. Sai thứ tự có thể gây outage

Nếu đổi mongod sang leaf ký bởi CA mới trước khi application truststore cập nhật, các clients có thể từ chối kết nối hàng loạt. Đối với cluster x.509, internal member trust cũng quan trọng tương tự.

### 22.3. Certificate pinning

Pin một leaf certificate có thể khiến rotation trong cùng CA vẫn fail. Nếu có pinning policy, cần inventory và overlap/rollout riêng, không hardcode fingerprint rồi quên vòng đời chứng chỉ.

## 23. Runtime certificate rotation

MongoDB có hỗ trợ cơ chế rotate certificate ở những phiên bản nhất định, với các quy tắc liên quan PEM path, nội dung file, CA và command.

~~~javascript
// Chỉ dùng theo runbook/version support, có quyền admin phù hợp.
db.adminCommand({ rotateCertificates: 1 })
~~~

Không mặc định lệnh này áp dụng cho mọi server version hoặc thay toàn bộ TLS sessions đang mở. Cần:

1. Kiểm tra phiên bản và hỗ trợ command.
2. Chuẩn bị cert/key mới với SAN, issuer, EKU và permissions đúng.
3. Thay material an toàn theo cơ chế OS/secret mount phù hợp.
4. Rotate hoặc rolling restart theo runbook.
5. Test handshake **mới**, vì existing pooled connections có thể giữ TLS session cũ.
6. Theo dõi replication, router health và lỗi client.

### 23.1. Cert expiry monitoring

Ví dụ ngưỡng:

~~~text
T-30 ngày: ticket và kế hoạch rotation
T-14 ngày: kiểm tra đã rollout chưa
T-7 ngày: escalation
T-1 ngày: cảnh báo khẩn cấp
~~~

Đây là mốc policy minh họa, không phải cài đặt MongoDB mặc định. Với short-lived certificates, dùng automation PKI/monitoring có cadence phù hợp.

## 24. Load balancer, TLS termination và encryption toàn tuyến

Một đường truyền có load balancer:

~~~text
App --TLS--> Load Balancer --plaintext--> mongos
~~~

Không thể gọi đây là mã hóa **end-to-end**. Dữ liệu ở chặng LB→mongos đi plaintext. Nếu policy yêu cầu toàn tuyến, có thể chọn:

- **TLS passthrough** tới endpoint MongoDB phù hợp.
- **TLS termination + re-encryption** từ LB đến mongos, với certificate validation/hostname đúng ở chặng sau.

### 24.1. Trust boundary

Load balancer có quyền terminate TLS sẽ nhìn thấy plaintext trong bộ nhớ. Nó phải được xem là thành phần tin cậy, có audit/admin controls và quy trình key management.

### 24.2. MongoDB không giống HTTP

MongoDB driver có topology discovery/pooling/failover. Không đặt một HTTP-only proxy trước replica set rồi giả định xử lý đúng protocol; chọn thiết bị/cấu hình mạng thực sự hỗ trợ MongoDB connection semantics.

### 24.3. Hostname phải khớp phía client

Nếu ứng dụng kết nối `mongo.example.com`, certificate trình ra cho nó cần SAN đúng với `mongo.example.com`. Nếu passthrough đến server chỉ có `mongo1.db.internal`, hostname verification có thể fail. Cần thiết kế DNS/PKI/LB đúng, không tắt hostname verification.

## 25. Những anti-pattern phải tránh

| Anti-pattern | Rủi ro | Thay thế |
|---|---|---|
| `tlsAllowInvalidCertificates:true` | Không xác minh issuer/cert đầy đủ, dễ MITM | Sửa trust chain |
| `tlsAllowInvalidHostnames:true` | Dễ kết nối endpoint giả mạo | Cấp SAN/dùng DNS đúng |
| `tlsInsecure:true` | Bỏ những kiểm tra TLS quan trọng | Cấu hình TLS an toàn |
| CN-only certificate | Không tương thích hostname verification hiện đại | DNS/IP SAN |
| Dùng IP nhưng cert chỉ có DNS SAN | TLS hostname mismatch | DNS canonical hoặc IP SAN |
| Tin keyFile tự mã hóa replication | Internal transport vẫn có thể plaintext | TLS cùng auth mode |
| Nghĩ `requireTLS` tự bật x.509 | Nhầm transport và member authentication | Chọn clusterAuthMode/keyFile riêng |
| Dùng cluster member cert cho app | Rủi ro identity/privilege | Client cert profile riêng |
| Commit PEM private key vào Git | Lộ danh tính endpoint | Secret manager/private storage |
| Một cert/key chia sẻ trên mọi node | Blast radius tăng | Identity/key mỗi node nếu khả thi |
| Chỉ kiểm tra seed hostname | Failover mới lộ SAN mismatch | Test mọi advertised member |
| CA rotation không overlap | Clients mất trust | Phân phối bundle trước leaf |
| Bật `requireTLS` một member trước khi peers sẵn sàng | Có thể mất majority/replication | Rolling migration có kiểm soát |
| TLS terminate ở LB rồi plaintext sau | Không mã hóa toàn tuyến | Passthrough/re-encrypt |
| Tạo MongoClient cho mỗi HTTP request | Handshake storm | Reuse pooled client |
| Tắt TLS khi latency tăng | Dữ liệu mất bảo vệ | Profile query/network/handshake |

## 26. Security policy: TLS không thay RBAC và encryption at rest

| Cơ chế | Phạm vi |
|---|---|
| TLS | Dữ liệu đang truyền qua mạng |
| SCRAM / MONGODB-X509 | Identity ứng dụng/người dùng |
| KeyFile / cluster x.509 | Internal member authentication |
| MongoDB RBAC | Quyền thực thi lệnh và truy cập dữ liệu |
| Application authorization | Quyền tenant/business |
| Encryption at rest | File dữ liệu/backup trên storage |
| Client-side/field-level encryption | Field nhạy cảm ở tầng ứng dụng |
| Audit/monitoring | Khả năng phát hiện và điều tra |

TLS giúp ứng dụng kết nối an toàn đến endpoint được tin cậy, nhưng server vẫn có thể xử lý nội dung plaintext của các trường không mã hóa ở ứng dụng. Nếu threat model yêu cầu hạn chế quyền đọc của database operator, cần đánh giá application-side/field-level encryption riêng.

## 27. Theo dõi và cảnh báo TLS

| Nhóm | Metric/quan sát | Tại sao cần? |
|---|---|---|
| Certificate inventory | Issuer, SAN, serial/fingerprint, NotAfter | Biết cert nào trên node nào |
| Expiry | Days until expiry | Chủ động rotation |
| TLS handshakes | Failure rate, protocol versions | Phát hiện CA/SAN/cipher lỗi |
| MongoDB auth | SCRAM/x509 authentication failures | Tách lỗi TLS và credentials |
| Connection pools | New/active/idle sockets | Phát hiện reconnect/handshake storm |
| Replica health | Members, elections, lag | TLS nội bộ ảnh hưởng quorum |
| Sharded health | Mongos reachability, shard/config errors | Lỗi chỉ một phần cụm |
| Rotation status | Deployed cert version mỗi node | Tránh sót members |
| Clock | NTP drift | Certificate not yet valid/expired giả |
| Key permissions | Mount/read errors | Tránh startup failure |

Những tên là **gợi ý instrumentation**, không nhất thiết là tên metrics được MongoDB xuất nguyên văn. Kết hợp monitoring hạ tầng, logs, driver command monitoring và PKI certificate exporter.

### 27.1. Không log credentials

Khi chẩn đoán, lưu hostname, error reason, timestamp và fingerprint theo policy; không log password, private key hay full URI chứa credentials. Nested exception hữu ích nhưng cần redact secrets.

### 27.2. Phân biệt handshake failure và login failure

TLS handshake fail nghĩa là client chưa thiết lập kênh tin cậy; login failure nghĩa là có thể đã qua TLS nhưng MongoDB user/authSource/roles không đúng. Cảnh báo hai nhóm riêng để tìm đúng nguyên nhân.

## 28. Bài thực hành A — xác minh CA và SAN

Giả sử:

~~~text
Root CA: CorpRoot
Intermediate CA: CorpIntermediate
Server leaf SAN: DNS:mongo1.db.internal
Client URI: mongo1.db.internal
Client trust: CorpRoot và chain đủ để xác minh
~~~

Trả lời:

1. URI hostname có khớp SAN?
2. Nếu đổi URI thành `10.20.0.5` nhưng certificate không có IP SAN thì sao?
3. Nếu thiếu intermediate nên sửa ở đâu?
4. Nếu leaf hết hạn, có thể dùng `tlsAllowInvalidCertificates:true` làm fix production không?

## 29. Bài thực hành B — TLS + SCRAM

Một hệ thống:

~~~text
Server: net.tls.mode=requireTLS
Server: allowConnectionsWithoutCertificates=true
User authentication: SCRAM
Application: tls=true, đúng CA và hostname
Application client certificate: không có
~~~

Application có kết nối được không nếu username/password đúng? Tại sao `allowConnectionsWithoutCertificates` không cho phép plaintext? Nếu credentials sai, lỗi thuộc tầng nào?

## 30. Bài thực hành C — hostname failover

Replica set:

~~~text
mongo1.db.internal:27017
mongo2.db.internal:27017
mongo3.db.internal:27017
~~~

Certificate mongo1 đúng SAN, mongo2 chỉ có `DNS:localhost`. Vì sao client có thể chạy được một thời gian nhưng fail khi topology thay đổi? Bạn sẽ sửa PKI/DNS thế nào, và kiểm thử gì?

## 31. Bài thực hành D — cấu hình mongod

Giải thích:

~~~yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1.pem
    CAFile: /etc/mongodb/tls/ca-chain.pem

security:
  authorization: enabled
  keyFile: /etc/mongodb/secrets/cluster.key
~~~

Phân biệt server certificate, CA trust, internal keyFile và MongoDB authorization. Tại sao không được bỏ `authorization` chỉ vì bật requireTLS?

## 32. Bài thực hành E — keyFile so với x.509 nội bộ

Một đồng nghiệp nói:

> “Replica set đã dùng TLS nên clusterAuthMode mặc định chắc chắn là x.509.”

Hãy sửa phát biểu và nêu hai cách **TLS + keyFile** và **TLS + cluster x.509**, cùng requirement về certificate/subject/secret.

## 33. Bài thực hành F — Node.js private CA

~~~javascript
const client = new MongoClient(uri, {
  tls: true,
  tlsCAFile: "/etc/app/tls/mongo-ca.pem",
  auth: {
    username: process.env.MONGODB_USERNAME,
    password: process.env.MONGODB_PASSWORD
  }
});
~~~

Giải thích `tlsCAFile` dùng làm gì. Nếu server cho SCRAM client không có cert, có bắt buộc `tlsCertificateKeyFile` không? Vì sao không tạo MongoClient cho mỗi request?

## 34. Bài thực hành G — Java trust store

Node kết nối được khi dùng `tlsCAFile`; Java bị `PKIX path building failed`. Hãy kiểm tra JVM trust store, CA intermediate, JDK TLS protocol và DNS/SAN. Tại sao không giải quyết bằng TrustManager tin mọi certificate?

## 35. Bài thực hành H — rotation CA

CA cũ ký leaf certificates của toàn cluster; team muốn đổi CA. Hãy lên kế hoạch từ **phân phối CA trust mới** đến **thay leaf** rồi **gỡ CA cũ**. Cần kiểm tra gì với Java containers chưa reload trust và với failover?

## 36. Bài thực hành I — load balancer

~~~text
App --TLS--> LB --plaintext--> mongos
~~~

Đây có được coi là mã hóa toàn tuyến không? Hãy nêu hai kiến trúc có thể đáp ứng policy bảo vệ chặng LB→mongos. Certificate phía client phải khớp hostname nào?

## 37. Bài thực hành J — MONGODB-X509

TLS handshake thành công với client certificate được CA tin cậy ký, nhưng database trả `Authentication failed`. Hãy xem:

- `authMechanism=MONGODB-X509`.
- `authSource=$external`.
- Certificate subject/DN mapping.
- MongoDB user được provision chưa.
- Roles và EKU/issuer policy.

Vì sao không dùng cluster member certificate như app certificate?

## 38. Bài thực hành K — observability

Thiết kế dashboard có:

~~~text
Certificate days-to-expiry
TLS handshake failure rate
MongoDB authentication failure rate
Replica set member health và lag
Mongos/config/shard connectivity
Client pool reconnect rate
Certificate version trên từng node
~~~

Đặt owner và ngưỡng alert; nêu cách phân biệt certificate expired với password sai.

## 39. Gợi ý đáp án

**A:** Hostname khớp DNS SAN. Dùng IP sẽ fail hostname verification nếu không có IP SAN. Cần đúng CA/intermediate chain, thay cert hết hạn thay vì tắt validation.

**B:** Có thể dùng server-auth TLS + SCRAM khi server cho client không trình certificate; `requireTLS` vẫn cấm plaintext. Sai credentials gây MongoDB auth failure sau TLS.

**C:** Driver có thể chuyển sang mongo2 lúc failover và từ chối cert vì SAN chỉ là localhost. Cấp certificate cho đúng advertised hostname; test từng member và failover.

**D:** `requireTLS` bảo vệ transport; `certificateKeyFile` cung cấp server identity; `CAFile` là trust; `keyFile` xác thực nội bộ; `authorization` kiểm soát user roles.

**E:** TLS không quyết định clusterAuthMode. KeyFile là shared secret auth; x.509 là certificate-based member identity với subject/EKU/trust requirements riêng.

**F:** `tlsCAFile` giúp xác minh private CA. SCRAM không nhất thiết cần client certificate. Pool MongoClient để tránh handshake storm.

**G:** Java có JVM truststore riêng; cần import CA đúng/SSLContext phù hợp và kiểm tra protocol/SAN. Trust-all mở nguy cơ MITM.

**H:** Phân phối trust mới trước, giữ overlap, rolling rotate leaf, test new connections/replication/failover, chỉ gỡ CA cũ khi hết dependency.

**I:** Không phải mã hóa toàn tuyến. Dùng TLS passthrough hoặc terminate+re-encrypt; client-visible endpoint certificate phải khớp hostname mà app dùng.

**J:** TLS certificate hợp lệ không tự cấp MongoDB user/roles. Cần x.509 mechanism/authSource/user identity đúng và profile app riêng khỏi member.

**K:** Giám sát expiry cùng handshake failures, auth failures và member health; phân loại theo tầng để xử lý đúng vấn đề.

## 40. Câu hỏi ôn tập

**1. TLS bảo vệ điều gì?** — Mã hóa và toàn vẹn traffic, xác minh endpoint theo certificate.

**2. TLS có tự bật MongoDB RBAC không?** — Không; phải cấu hình users/roles và authorization.

**3. TLS khác mTLS?** — Trong server-auth TLS client xác minh server; mTLS còn xác minh client certificate.

**4. SCRAM có thể hoạt động qua TLS không có client cert?** — Có, nếu server policy cho phép.

**5. SAN là gì?** — Subject Alternative Name, chứa DNS/IP identities để hostname verification.

**6. Vì sao không dựa vào CN-only cert?** — Các clients hiện đại ưu tiên SAN; CN-only không bảo đảm tương thích.

**7. `net.tls.mode: requireTLS` làm gì?** — Buộc kết nối dùng TLS.

**8. `certificateKeyFile` có phải CA trust store không?** — Không; nó chứa identity certificate và private key của server.

**9. `CAFile` dùng làm gì?** — Cung cấp CA trust cho peer certificate validation theo cấu hình.

**10. `clusterFile` khác `certificateKeyFile` thế nào?** — Có thể chứa identity riêng cho internal member authentication.

**11. `keyFile` có mã hóa replication traffic không?** — Không tự nó, TLS bảo vệ đường truyền.

**12. X.509 internal auth và MONGODB-X509 client auth có giống nhau?** — Cùng họ certificate-based nhưng khác vai trò, identity và trust policy.

**13. Vì sao phải test mọi replica set hosts?** — Driver discovery/failover có thể kết nối members khác seed host.

**14. IP URI có match DNS SAN không?** — Không mặc định; cần IP SAN hoặc dùng DNS tương ứng.

**15. Node.js dùng option nào cho private CA?** — Thường `tlsCAFile`.

**16. Java dùng CA ở đâu?** — JVM truststore hoặc SSLContext/trust manager được cấu hình đúng.

**17. Vì sao tránh `tlsAllowInvalidCertificates`?** — Nó làm yếu kiểm tra peer và tạo nguy cơ MITM.

**18. CA rotation cần overlap không?** — Thường có để clients tin cả CA cũ/mới trong giai đoạn chuyển.

**19. LB terminate TLS rồi gửi plaintext có end-to-end encrypted không?** — Không.

**20. Cert hết hạn có thể làm gián đoạn replica set?** — Có, internal handshakes có thể fail.

**21. `$external` dùng trong trường hợp nào?** — Authentication database của cơ chế như `MONGODB-X509`.

**22. TLS mã hóa dữ liệu at rest không?** — Không; cần cơ chế at-rest riêng.

**23. Một MongoClient trên mỗi request có tốt không?** — Không; làm tăng handshakes và resource overhead.

**24. Ping thành công chứng minh certificate rotation xong toàn cụm không?** — Không; phải test peers, new connections, failover và trust trên toàn bộ clients.

**25. Lỗi MongoDB Authentication failed có phải lỗi CA không?** — Không nhất thiết; thường cần kiểm tra credentials/authSource/x509 roles.

## 41. Bảng ghi nhớ nhanh

| Nhu cầu | Thiết lập |
|---|---|
| Buộc server TLS | `net.tls.mode: requireTLS` |
| Server cert/key | `net.tls.certificateKeyFile` |
| CA trust | `net.tls.CAFile` |
| Member cert/key | `net.tls.clusterFile` khi dùng |
| Member CA | `net.tls.clusterCAFile` khi dùng |
| Client không có cert nhưng dùng SCRAM | `allowConnectionsWithoutCertificates` theo policy |
| KeyFile internal auth | `security.keyFile` |
| X.509 internal auth | `security.clusterAuthMode: x509` |
| MongoDB RBAC | `security.authorization: enabled` |
| Mongosh TLS | `tls=true` và `--tlsCAFile` |
| Node TLS | `tls:true` và `tlsCAFile` |
| Node client mTLS | `tlsCertificateKeyFile` |
| Java CA | JVM truststore/SSLContext |
| Client x.509 login | `MONGODB-X509` và `$external` |
| Kiểm tra cert file | `openssl x509` |
| Probe TLS | `openssl s_client` |
| Kiểm tra MongoDB | Driver/mongosh `ping` |
| Rotation CA | Trust overlap + rolling leaf replacement |
| Tránh | `tlsInsecure`/invalid certificates/hostnames |

## 42. Checklist trước khi đưa TLS vào production

- [ ] Đã inventory tất cả application→mongod/mongos và internal connections?
- [ ] Mọi leaf certificates có SAN đúng advertised hostname?
- [ ] Có CA/intermediate chain đủ và truststore của từng driver phù hợp?
- [ ] EKU, thời hạn, key length và issuer theo PKI policy?
- [ ] Private keys được bảo vệ, không có trong repo/logs?
- [ ] `requireTLS` được áp trên mọi endpoints sau rollout?
- [ ] Có `authorization:enabled` và roles least privilege?
- [ ] Đã tách transport TLS với SCRAM/x.509/keyFile internal auth?
- [ ] Nếu app không trình client cert, server policy có cho phép rõ ràng?
- [ ] Nếu cluster x.509, DN/subject rules và cluster CA được xác minh?
- [ ] Replica set seed và advertised hosts đều phân giải được DNS?
- [ ] Test mỗi member, failover và secondary selection?
- [ ] Node/Java/mongosh không bật invalid-cert/hostname flags?
- [ ] MongoClient pooling và timeouts được cấu hình hợp lý?
- [ ] Firewall/private network hạn chế database exposure?
- [ ] LB/proxy không tạo plaintext hop trái policy?
- [ ] Có staging, rolling rollout và rollback plan theo server version?
- [ ] Cert expiry, handshake errors và auth errors được giám sát riêng?
- [ ] CA rotation có trust overlap và kiểm tra reload trust?
- [ ] Có test sharded cluster config/shard/mongos links?
- [ ] Có phân biệt TLS encryption với at-rest và field-level encryption?
- [ ] Secrets được cấp qua cơ chế phù hợp, không hardcode password?

## 43. Kết luận

**TLS bảo vệ đường truyền MongoDB ở cả hai lớp: ứng dụng kết nối tới database và các thành viên cụm liên lạc với nhau.** Một triển khai an toàn cần certificate chain đáng tin, SAN khớp hostname, certificate chưa hết hạn, private key được bảo vệ, và cuối cùng là `net.tls.mode: requireTLS` trên toàn bộ endpoints cần bảo vệ.

Cần tách rõ **transport encryption** khỏi **authentication**: SCRAM hoặc `MONGODB-X509` xác thực ứng dụng; keyFile hoặc cluster x.509 xác thực internal members; MongoDB RBAC kiểm soát quyền truy cập. `tls=true` không có ý nghĩa bảo vệ đầy đủ khi client bỏ certificate validation, và bật TLS không thay được encryption at rest, application authorization hay kiểm soát mạng.

Trong production, yếu tố quyết định là **vòng đời chứng chỉ và sự nhất quán của toàn cluster**. Hãy cấp đúng SAN/EKU, phân phối CA trước khi rotate, thay certificate theo rolling runbook, kiểm thử kết nối mới và failover, theo dõi expiry/handshake, và không để sót bất kỳ đoạn plaintext nào ngoài chính sách bảo mật được phê duyệt.
