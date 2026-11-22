# Quản lý cấu hình mongod, mongos và tham số khởi động trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Vận hành và nâng cấp  
> **Bài học:** Quản lý cấu hình mongod, mongos và tham số khởi động

## 1. Vì sao cấu hình MongoDB là một phần quan trọng của vận hành?

Một hệ thống thương mại điện tử có MongoDB replica set ở môi trường staging và sharded cluster tại production. Sau một đợt triển khai, nhóm vận hành gặp các tình huống:

- Server không khởi động vì sai YAML indentation.
- Dịch vụ chạy được nhưng chỉ lắng nghe trên `127.0.0.1`; ứng dụng từ host khác không kết nối được.
- Đổi `storage.dbPath` trong cấu hình nhưng MongoDB khởi động với data directory trống.
- Replica set member không tham gia được vì `replication.replSetName` khác các thành viên.
- `mongos` không kết nối được config server replica set.
- Người vận hành sửa `mongod.conf` nhưng một CLI flag hoặc environment override khiến giá trị thực tế khác mong đợi.
- Bật `security.authorization` trên replica set mà chưa chuẩn bị internal authentication, làm node không liên lạc được.
- Đổi certificate TLS nhưng không restart/reload đúng quy trình; một số clients mất kết nối.
- Một `setParameter` có hiệu lực ngay, trong khi thay `net.port` lại cần restart.
- Sau upgrade, một option cũ đã bị loại bỏ và MongoDB từ chối startup.

Các lỗi này không phải vấn đề CRUD hay query syntax; chúng thuộc **quản trị lifecycle của tiến trình MongoDB**.

Một quy trình đúng phải trả lời được:

1. Tiến trình đó là `mongod` hay `mongos`?
2. File cấu hình được nạp từ đâu?
3. Có những command-line arguments hoặc environment overrides nào?
4. Các giá trị thực tế mà server đã parse là gì?
5. Option áp dụng lúc startup hay đổi được lúc runtime?
6. Ảnh hưởng đến một process, một replica set hay toàn sharded cluster?
7. Thay đổi có cần rolling restart, failover hay migration không?
8. Cách kiểm tra thành công và khôi phục khi lỗi?
9. Các secret/private keys trong cấu hình được bảo vệ thế nào?

**Nguyên tắc cốt lõi:** Đừng chỉ “sửa YAML và restart”. Hãy xác định đúng **scope, hiệu lực, phiên bản hỗ trợ, trạng thái thực tế, dependency và rollback**.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt trách nhiệm của `mongod` và `mongos`.
- Viết cấu hình YAML hợp lệ cho standalone, replica set member, shard và router.
- Ánh xạ file config với CLI options như `--dbpath`, `--port`, `--replSet`, `--configdb`.
- Hiểu mức ưu tiên của CLI overrides và những trường hợp options xung đột.
- Dùng `getCmdLineOpts` để xem startup configuration đang có hiệu lực.
- Phân biệt `setParameter` startup-only và runtime-changeable.
- Cấu hình network, storage, system log, authorization, TLS, member authentication và sharding.
- Quản lý systemd, Windows service và container/Kubernetes deployments.
- Xây runbook validate, rolling restart, rollback và monitoring.
- Nhận diện khi nào config change phải gắn với upgrade và Feature Compatibility Version (FCV).

---

## 2. Hai tiến trình khác nhau: mongod và mongos

MongoDB có hai loại process cần phân biệt rõ.

### 2.1. mongod — tiến trình lưu trữ và xử lý dữ liệu

`mongod` là MongoDB database server. Nó có thể hoạt động với những vai trò:

- Standalone server.
- Replica set member.
- Shard server trong sharded cluster.
- Config server member trong config server replica set.

`mongod` quản lý:

- Storage engine và data files.
- Đọc/ghi documents.
- Indexes.
- Replication/oplog khi là replica set member.
- Authorization.
- Transaction/query execution.
- Cache, journaling và background tasks.

Các options tiêu biểu:

```yaml
storage:
  dbPath: /var/lib/mongodb

replication:
  replSetName: rs0

net:
  port: 27017
```

### 2.2. mongos — query router của sharded cluster

`mongos` là router nhận request từ MongoDB clients rồi điều phối tới các shards.

Nó:

- Dùng metadata/routing information của sharded cluster.
- Chuyển query tới shards phù hợp.
- Phối hợp kết quả một số distributed operations.
- Quản lý kết nối tới config server replica set.
- Có network/TLS/logging/process runtime của riêng nó.

Nó **không** lưu collections như một `mongod` shard, không có `storage.dbPath` để lưu dữ liệu ứng dụng.

Option quan trọng:

```yaml
sharding:
  configDB: cfgRS/cfg1.example.internal:27019,cfg2.example.internal:27019,cfg3.example.internal:27019
```

### 2.3. Sơ đồ vai trò

```text
                 Application / Java Driver
                           │
                           ▼
                    mongos routers
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
              Shard rsA     Shard rsB
              mongod x3     mongod x3
                    │           │
                    └─────┬─────┘
                          │
                     Config RS
                     mongod x3
```

Trong standalone hoặc replica set không sharding, ứng dụng kết nối tới `mongod` trực tiếp qua connection string topology phù hợp, **không cần mongos**.

### 2.4. Bảng so sánh

| Thuộc tính | mongod | mongos |
|---|---|---|
| Lưu data collections | Có | Không |
| Có `storage.dbPath` | Có | Không |
| Dùng `replication.replSetName` khi là replica set member | Có | Không |
| Dùng `sharding.clusterRole` | Có khi là shard/config server | Không |
| Dùng `sharding.configDB` | Không để thay thế shard role | Có, cần config server RS |
| Lắng nghe client TCP | Có | Có |
| Có `net.tls` | Có | Có |
| Có `systemLog` | Có | Có |
| Có `setParameter` | Có, tùy parameter | Có, tùy parameter |
| Có `security.authorization` option | Có | Không theo cùng config field |
| Dùng `security.keyFile` khi member authentication bằng keyfile | Có | Có thể cần trên mongos |
| Dùng `getCmdLineOpts` | Có | Có |

**Không sao chép nguyên `mongod.conf` sang `mongos.conf`.** Các nhóm storage, replication và sharding có phạm vi riêng.

---

## 3. Các lớp cấu hình: mặc định, file YAML, CLI và runtime

Một MongoDB process nhận các settings từ nhiều nguồn:

```text
Server binary + version defaults
       │
       ├─ Configuration file (*.conf/*.cfg)
       │      net.port, storage.dbPath, ...
       │
       ├─ Startup CLI arguments
       │      --config, --port, --bind_ip, ...
       │
       ├─ Supported environment overrides /
       │   external expansion directives
       │
       └─ Runtime changes khi được hỗ trợ
              setParameter, setLogLevel, ...
```

Các lớp này có thể tác động lên nhau. **Không nên áp dụng một thứ tự ưu tiên tổng quát cho mọi option** nếu tài liệu quy định override hoặc conflict riêng.

Ví dụ trong tài liệu chính thức:

- `--bind_ip` có thể override `net.bindIp` của config file.
- `net.bindIp` và `net.bindIpAll` **loại trừ nhau**: không được khai báo đồng thời.
- `MONGODB_CONFIG_OVERRIDE_NOFORK` có tác động riêng lên `processManagement.fork`.
- Một số flags/values không được phép dùng cùng nhau, gây startup failure chứ không phải tự chọn một bên.

**Luôn kiểm tra effective parsed startup options** thay vì chỉ tin nội dung một file.

### 3.1. Những nơi thường chứa cấu hình

| Môi trường | Đường dẫn phổ biến | Ghi chú |
|---|---|---|
| Debian/Ubuntu cài bằng package | `/etc/mongod.conf` | Package service có thể giả định đường dẫn data/log mặc định |
| RHEL/CentOS cài bằng package | `/etc/mongod.conf` | Kiểm tra unit file và distribution |
| macOS qua Homebrew | `/usr/local/etc/mongod.conf` hoặc `/opt/homebrew/etc/mongod.conf` | Tùy CPU/installation |
| Windows MSI | Thường có `mongod.cfg` trong thư mục `bin` | Kiểm tra Windows service command |
| Docker/container | Image entrypoint/config volume/env | Không có một path chung bất biến |
| Kubernetes Operator | Custom Resource, Secret, ConfigMap | Operator có thể tái tạo Pod/config |
| MongoDB Atlas | Control plane/service configuration | Không tự sửa `mongod.conf` |

Đường dẫn ví dụ không thay thế việc kiểm tra **tiến trình thực tế**.

### 3.2. File chỉ là một phần của desired state

Trạng thái server phụ thuộc cả:

- Binary version.
- Config file và CLI.
- OS/service permissions.
- DNS/TLS CA/certificates.
- Dữ liệu trong `storage.dbPath`.
- Replica set/shard metadata đã tồn tại.
- Secrets/keyfiles.
- Runtime settings.
- Orchestrator lifecycle.

Một file YAML hợp lệ không đảm bảo cluster hoạt động khỏe nếu các điều kiện còn lại sai.

---

## 4. Cú pháp YAML của MongoDB

MongoDB self-managed sử dụng file cấu hình định dạng YAML.

### 4.1. Cấu trúc cơ bản

Ví dụ standalone lab, **chưa bật authorization**:

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod-lab.log
  logAppend: true

storage:
  dbPath: /var/lib/mongodb-lab

net:
  bindIp: 127.0.0.1
  port: 27017
~~~

Mỗi cấp được thụt dòng bằng **dấu cách**. YAML không dùng tab để indent.

### 4.2. Data types

Các giá trị thường gặp:

~~~yaml
net:
  port: 27017
  bindIp: "127.0.0.1"

systemLog:
  logAppend: true
  verbosity: 0

security:
  authorization: enabled
~~~

- `27017` là integer.
- `true` là boolean.
- `0` là integer.
- `"127.0.0.1"` là string.
- `enabled` là string enum đúng kiểu viết.

Một typo như `authorization: Enabled` có thể làm MongoDB từ chối startup trên phiên bản yêu cầu case-sensitive enum.

### 4.3. Tabs, thụt dòng và duplicate keys

Sai:

~~~yaml
net:
    port: 27017
  bindIp: 127.0.0.1
~~~

Indent không nhất quán, không hợp lệ.

Sai cách tổ chức:

~~~yaml
net:
  port: 27017

net:
  bindIp: 127.0.0.1
~~~

Duplicate YAML keys có thể bị reject hoặc diễn giải ngoài kỳ vọng, không được xem là cách merge config.

Đúng:

~~~yaml
net:
  port: 27017
  bindIp: 127.0.0.1
~~~

### 4.4. Quoting khi có ký tự đặc biệt

Nên quote các chuỗi chứa dấu phẩy, ký tự đặc biệt hoặc dễ bị YAML hiểu là type khác:

~~~yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
~~~

YAML `*` có ý nghĩa alias. Nếu cần bind wildcard theo syntax MongoDB, sử dụng dạng có quote và phải đánh giá security:

~~~yaml
net:
  bindIp: "*"
~~~

**Không dùng wildcard ở production chỉ vì tiện:** nó mở listener trên nhiều network interfaces.

### 4.5. Đường dẫn trên Windows

Trong YAML, dùng forward slash là cách dễ tránh escape:

~~~yaml
storage:
  dbPath: "C:/MongoDB/data"

systemLog:
  destination: file
  path: "C:/MongoDB/log/mongod.log"
  logAppend: true
~~~

Nếu dùng Windows backslashes trong chuỗi YAML double quotes, cần chú ý escaping. Không kết luận Windows path luôn hợp lệ khi copy nguyên syntax của Linux.

### 4.6. Encoding của config file

Tài liệu `mongod`/`mongos` chính thức nêu yêu cầu file cấu hình dùng **ASCII encoding**, không dựa vào việc MongoDB hỗ trợ mọi nội dung Unicode trong YAML.

Để tương thích tốt:

- Chỉ dùng ASCII trong file config.
- Đặt chú thích config bằng tiếng Anh ASCII, tránh comment tiếng Việt có dấu trong file.
- Không tạo file có UTF-8 BOM hoặc chuyển đổi encoding tùy tiện.
- Nội dung Markdown hướng dẫn này vẫn là UTF-8 tiếng Việt; **đừng nhầm encoding bài học với encoding của file MongoDB config thực tế**.

### 4.7. Không đưa secret vào ví dụ public

Tránh:

~~~yaml
net:
  tls:
    certificateKeyFilePassword: super-secret-real-password
~~~

Nếu phải có secret, dùng secret management và các cơ chế cấu hình được server hỗ trợ theo version; không commit password/private keys trong repository.

---

## 5. Khởi động bằng --config hoặc -f

### 5.1. mongod

~~~bash
mongod --config /etc/mongod.conf
~~~

Hoặc:

~~~bash
mongod -f /etc/mongod.conf
~~~

### 5.2. mongos

~~~bash
mongos --config /etc/mongos.conf
~~~

Hoặc:

~~~bash
mongos -f /etc/mongos.conf
~~~

Nếu cài MongoDB qua package và chạy systemd service, service thường đã biết file config của nó. Không tự khởi chạy thêm một tiến trình `mongod` bằng tay trên cùng `dbPath` khi service đang chạy.

### 5.3. Tham số CLI tương ứng YAML

| Config file | CLI tương ứng | Process |
|---|---|---|
| `storage.dbPath` | `--dbpath` | mongod |
| `net.port` | `--port` | mongod, mongos |
| `net.bindIp` | `--bind_ip` | mongod, mongos |
| `net.bindIpAll` | `--bind_ip_all` | mongod, mongos |
| `systemLog.path` | `--logpath` | mongod, mongos |
| `systemLog.logAppend` | `--logappend` | mongod, mongos |
| `replication.replSetName` | `--replSet` | mongod |
| `sharding.configDB` | `--configdb` | mongos |
| `sharding.clusterRole: shardsvr` | `--shardsvr` | mongod |
| `sharding.clusterRole: configsvr` | `--configsvr` | mongod |
| `security.keyFile` | `--keyFile` | mongod, mongos |
| `net.tls.mode` | `--tlsMode` | mongod, mongos |
| `net.tls.certificateKeyFile` | `--tlsCertificateKeyFile` | mongod, mongos |
| `setParameter.<name>` | `--setParameter name=value` | Theo parameter/process |

Tham khảo bảng mapping chính thức để biết mọi option của **đúng MongoDB Server version**.

### 5.4. CLI có thể override config file

Giả sử file:

~~~yaml
net:
  bindIp: 127.0.0.1
  port: 27017
~~~

Và startup:

~~~bash
mongod --config /etc/mongod.conf --bind_ip 127.0.0.1,10.20.0.15
~~~

Trong tình huống này, `--bind_ip` override `net.bindIp`. Muốn biết process thật sự nghe ở địa chỉ nào, kiểm tra parsed options và listener, không chỉ mở file.

**Cảnh báo:** Không được dùng ví dụ override để mở listener ra network ngoài khi access control/TLS/firewall chưa được bảo vệ.

### 5.5. Không xem mọi option là “last flag wins”

Một số options:

- Mutually exclusive.
- Chỉ có trên mongod hoặc mongos.
- Đã bị removed.
- Phải đi kèm một option khác.
- Chỉ hỗ trợ ở một edition/version.
- Không được thay đổi nếu deployment đã có metadata/data không tương thích.

Nếu có conflict, server có thể không khởi động. Luôn kiểm tra log lỗi.

---

## 6. Chuyển CLI flags thành YAML

Nếu đang chạy lệnh dài:

~~~bash
mongod --dbpath /var/lib/mongodb --port 27017 --bind_ip 127.0.0.1 --logpath /var/log/mongodb/mongod.log --logappend
~~~

có thể chuyển các options sang YAML:

~~~yaml
storage:
  dbPath: /var/lib/mongodb

net:
  port: 27017
  bindIp: 127.0.0.1

systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
~~~

MongoDB hỗ trợ `--outputConfig` để xuất cấu hình tương đương của command-line options trong những phiên bản hỗ trợ:

~~~bash
mongod --dbpath /var/lib/mongodb-lab --port 27018 --bind_ip 127.0.0.1 --outputConfig
~~~

**Lưu ý:** Lệnh trên là ví dụ chuyển đổi cấu hình, không phải hướng dẫn chạy thêm mongod trên data directory đang được service sử dụng. Kiểm tra help/version và nơi output trước khi dùng automation.

### 6.1. Lợi ích của config file

- Dễ review/diff.
- Dễ giữ lịch sử thay đổi.
- Dễ triển khai đồng nhất giữa nodes.
- Ít sai sót hơn command line dài.
- Dễ phân tách cấu hình theo mongod/mongos.
- Phù hợp với infrastructure as code.

### 6.2. Rủi ro của config file

- Chứa đường dẫn secrets.
- Có thể bị sửa ngoài deployment pipeline.
- Không tự đảm bảo runtime đã reload.
- Có thể bị CLI/environment overrides.
- Có thể không tương thích khi nâng cấp server version.
- Tệp cấu hình trên disk và effective running settings có thể lệch nhau.

**Config file là desired state; effective parsed startup settings mới là bằng chứng một phần của actual state.**

---

## 7. Cấu hình mongod standalone trong local lab

Một mẫu tối thiểu cho self-managed lab trên Linux, **chỉ bind localhost**:

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod-lab.log
  logAppend: true
  verbosity: 0

storage:
  dbPath: /var/lib/mongodb-lab

net:
  bindIp: 127.0.0.1
  port: 27017

operationProfiling:
  mode: off
  slowOpThresholdMs: 100
~~~

### 7.1. Giải thích

- `systemLog.destination: file`: ghi diagnostic messages vào file.
- `systemLog.path`: file log.
- `logAppend: true`: xử lý append vào log khi khởi động theo cấu hình.
- `verbosity: 0`: không bật debug chi tiết toàn server.
- `storage.dbPath`: vị trí dữ liệu.
- `net.bindIp`: chỉ lắng nghe loopback.
- `net.port`: cổng MongoDB.
- `operationProfiling.mode: off`: tắt database profiler, không phải tắt mọi slow logs.

### 7.2. Chuẩn bị thư mục và quyền

Ví dụ người quản trị Linux có quyền thực hiện trong lab:

~~~bash
sudo mkdir -p /var/lib/mongodb-lab /var/log/mongodb
sudo chown -R mongodb:mongodb /var/lib/mongodb-lab /var/log/mongodb
~~~

Tên service user tùy bản cài. Không chạy `chown -R` lên data directory production khi chưa kiểm tra owner, ACL và yêu cầu của hệ thống.

### 7.3. Khởi động

~~~bash
mongod --config /etc/mongod-lab.conf
~~~

Nếu chạy mongod dưới service manager, phải dùng service config tương ứng thay vì khởi chạy thêm tiến trình trên cùng data directory.

### 7.4. Kiểm tra từ mongosh

~~~bash
mongosh "mongodb://127.0.0.1:27017/"
~~~

Trong shell:

~~~javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ getCmdLineOpts: 1 });
~~~

Không coi `ping:1` thành công là bằng chứng authorization/TLS/replication đang đúng; đó là một kiểm tra kết nối hạn chế.

### 7.5. Có nên dùng cấu hình này ở production?

Không nguyên xi. Đây chỉ là local lab; production cần:

- Authentication/authorization.
- TLS.
- Member authentication khi có replica set.
- Backup và DR.
- Network segmentation/firewall.
- Monitoring/logging.
- Least-privilege service account.
- Capacity planning, disk/headroom.
- Version/upgrade policy.

---

## 8. storage: data path, engine và WiredTiger

### 8.1. storage.dbPath

`storage.dbPath` là nơi mongod lưu data files:

~~~yaml
storage:
  dbPath: /var/lib/mongodb
~~~

Nó **chỉ dành cho `mongod`**.

Sai lầm nguy hiểm:

1. Dữ liệu thật nằm ở `/var/lib/mongodb`.
2. Ai đó sửa config thành `/data/new-mongodb`.
3. Server khởi động với đường dẫn rỗng mới.
4. Ứng dụng thấy database “mất hết dữ liệu”.

Dữ liệu có thể vẫn ở đường dẫn cũ; nhưng startup trên data dir sai là sự cố nghiêm trọng. **Không copy/move data files của WiredTiger khi mongod đang chạy mà không có quy trình được hỗ trợ.**

### 8.2. Package defaults khác nhau

Đường dẫn phổ biến:

| Kiểu cài | data dir thường gặp |
|---|---|
| Ubuntu/Debian apt | `/var/lib/mongodb` |
| RHEL/CentOS yum | `/var/lib/mongo` |
| Manual binary Linux/macOS | Thường `/data/db` nếu không override |
| Windows manual | Thường `\data\db` trong các ví dụ/default |
| Container image | Tùy image/volume mapping |

Không hardcode path cũ khi triển khai mới; kiểm tra config của chính service.

### 8.3. WiredTiger

WiredTiger là storage engine mặc định trong các MongoDB versions hiện đại.

Các options có thể gặp:

~~~yaml
storage:
  dbPath: /var/lib/mongodb
  wiredTiger:
    engineConfig:
      cacheSizeGB: 2
    collectionConfig:
      blockCompressor: snappy
~~~

**Đây chỉ là ví dụ minh họa cú pháp.** Đừng đặt cache size tùy ý trên production, nhất là trong container có memory limits, vì MongoDB đã có tính toán defaults theo môi trường/version.

### 8.4. Cache size và memory limits

Khi tune cache:

- Đo WiredTiger cache utilization.
- Đo page faults/disk I/O.
- Đo memory của OS/container.
- Dự trù bộ nhớ cho aggregation, connections, filesystem cache và process khác.
- Kiểm tra option/giới hạn trong server version đang dùng.

Tăng cache không luôn làm query nhanh hơn. Có thể khiến OOM nếu memory headroom không đủ.

### 8.5. Journaling

Từ MongoDB 6.1, journaling luôn được bật và các options `storage.journal.enabled`, `--journal`/`--nojournal` bị loại bỏ.

Không copy cấu hình cũ:

~~~yaml
storage:
  journal:
    enabled: false
~~~

vào server mới rồi kỳ vọng hợp lệ.

Nếu upgrade, phải rà soát removed options trước khi restart.

### 8.6. Storage engine không phải tùy chọn thay đổi tùy tiện

Đổi `storage.engine` hoặc các tham số định dạng dữ liệu không phải chỉ “sửa một dòng YAML”; cần migration/backup/upgrade procedure chính thức.

---

## 9. net: port, bindIp và mạng an toàn

### 9.1. net.port

~~~yaml
net:
  port: 27017
~~~

Các default thường gặp theo vai trò:

- `mongod` bình thường: 27017.
- `mongod` shard member: thường 27018.
- `mongod` config server member: thường 27019.
- `mongos`: thường 27017.

Đây là defaults/phổ biến, **không phải quy định bắt buộc mỗi topology phải dùng đúng các cổng ấy**. Quản trị viên có thể chọn ports khác, nhưng phải cập nhật DNS, firewall, connection strings và các peers.

### 9.2. bindIp chỉ định listener

~~~yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
~~~

Server chỉ lắng nghe trên các network interfaces được chỉ định và phù hợp với địa chỉ có trên host.

Nếu `mongo1.example.internal` không resolve về địa chỉ local, startup có thể báo lỗi bind.

### 9.3. Mở mọi interface

Cấu hình:

~~~yaml
net:
  bindIpAll: true
~~~

cho phép listen trên mọi interfaces theo cấu hình platform.

Rủi ro:

- Dịch vụ có thể bị lộ ra mạng không tin cậy.
- Firewall rules không đúng sẽ tạo đường truy cập ngoài ý muốn.
- Bật authorization/TLS vẫn cần network segmentation.

**Không dùng `bindIpAll: true` để sửa lỗi connection nhanh mà chưa có security review.**

### 9.4. bindIp và bindIpAll loại trừ nhau

Sai:

~~~yaml
net:
  bindIp: "127.0.0.1"
  bindIpAll: true
~~~

Server có thể từ chối startup.

Chọn một cách cấu hình phù hợp.

### 9.5. Hostname và replica set

Các MongoDB versions hiện đại khuyến nghị/đặt quy tắc hostname cho replica set configuration thay vì dùng IP thô, nhất là trong các deployment cần split-horizon DNS và TLS SAN.

Không đổi hostname/IP trong replica set bằng cách chỉ sửa `bindIp`; còn phải xét:

- `rs.conf()` member hostnames.
- DNS resolution từ tất cả members/clients.
- TLS certificate SAN.
- Replica set reconfiguration.
- Firewall/connectivity.
- Sharded cluster metadata.

### 9.6. IPv6

Nếu triển khai IPv6, kiểm tra `net.ipv6` và `net.bindIp` tương thích, và đảm bảo OS/network policy hỗ trợ. Đừng nghĩ thêm địa chỉ IPv6 vào bindIp tự bật mọi hành vi IPv6 trong các versions.

---

## 10. systemLog: destination, log path, rotation và verbosity

### 10.1. Ví dụ config

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0
  timeStampFormat: iso8601-utc
~~~

### 10.2. Log destination

Tùy triển khai:

- File: `systemLog.destination: file`.
- Stdout/stderr: qua service manager/container.
- Syslog trong các platform/config hỗ trợ.

Nếu destination là file, phải chuẩn bị path và permissions. Nếu stdout được collector xử lý, đừng tự redirect thêm vào một file không được rotate.

### 10.3. Log append và rotation

`logAppend: true` tránh việc truncate/overwrite log lúc khởi động theo semantics cấu hình.

MongoDB có cơ chế log rotation; ví dụ command:

~~~javascript
db.getSiblingDB("admin").runCommand({
  logRotate: 1
});
~~~

Các mode như rename/reopen ảnh hưởng cách phối hợp với OS logrotate.

Không xóa file `mongod.log` đang open rồi kỳ vọng server và collector tự xử lý hoàn hảo.

### 10.4. Verbosity

`verbosity: 0` không phải “không log gì”. MongoDB vẫn có informational/warning/error/slow-operation messages.

Tăng global verbosity có thể tạo quá nhiều logs và lộ dữ liệu nhạy cảm. Khi cần debug, ưu tiên targeted component verbosity theo thời gian được kiểm soát.

### 10.5. Phân biệt diagnostic log và profiler

- `systemLog` là diagnostic messages.
- `operationProfiling` là cơ chế profiler/slow operations.
- `system.profile` là collection lưu profile records khi profiler bật.

Không sửa `systemLog.verbosity` rồi mặc định nghĩ mọi `system.profile` behavior sẽ thay đổi tương ứng.

### 10.6. Log path quá nhỏ hoặc mất quyền

Startup failure có thể do:

- Thư mục log không tồn tại.
- Service user không có quyền ghi.
- Filesystem chỉ đọc.
- Disk đầy.
- SELinux/AppArmor policy.
- Log path trùng với file của tiến trình khác.

Đọc error output của service trước khi sửa permissions một cách bừa bãi.

---

## 11. security.authorization: bật quyền kiểm soát truy cập

### 11.1. Đúng process

`security.authorization` là setting dùng cho `mongod`:

~~~yaml
security:
  authorization: enabled
~~~

Nó bật role-based access control. Đừng tự thêm đúng field này vào `mongos.conf` rồi xem như cả sharded cluster đã có authentication.

### 11.2. Chưa có user admin: chuẩn bị bootstrap

Một instance chưa có user mà bật access control đột ngột có thể khiến việc quản trị phức tạp nếu không có bootstrap procedure.

MongoDB có localhost exception với các điều kiện cụ thể để tạo user đầu tiên khi authorization được bật. Đây **không phải** phương án phục hồi thay thế admin account trong mọi trường hợp.

Trong production, phải có:

- Admin principal đã chuẩn bị.
- Authentication database và roles.
- Credential rotation.
- Backup/recovery path.
- Internal authentication cho replica set/sharded components.

### 11.3. Mongod replica set cần internal authentication

Đối với replica set bật authorization, các thành viên cần chứng minh danh tính với nhau, ví dụ keyfile hoặc X.509.

Không chỉ thêm:

~~~yaml
replication:
  replSetName: rs0

security:
  authorization: enabled
~~~

rồi bỏ qua member authentication nếu cấu hình topology yêu cầu. Đây chưa phải cấu hình production hoàn chỉnh.

### 11.4. Keyfile

Một ví dụ replica set member dùng keyfile:

~~~yaml
replication:
  replSetName: rs0

security:
  keyFile: /secure/mongodb/keyfile
  authorization: enabled
~~~

MongoDB documentation nêu `security.keyFile` **ngụ ý bật authorization** trong ngữ cảnh mongod.

Keyfile phải:

- Được phân phối an toàn tới đúng members.
- Có nội dung phù hợp giữa các thành viên.
- Có quyền truy cập file chặt chẽ (đặc biệt trên Unix).
- Được quản lý rotation/overlap theo runbook.
- Không nằm trong git hoặc public image.

### 11.5. Keyfile không phải password ứng dụng

`security.keyFile` là internal shared secret cho member authentication, **không phải** `app_user` SCRAM password trong URI Java.

### 11.6. Secrets và access controls

Đừng dùng tài khoản ứng dụng có quyền root chỉ vì gặp `Unauthorized`. Cần sửa đúng users/roles, không tắt authorization.

---

## 12. TLS: bảo mật traffic trong cấu hình

### 12.1. TLS server config

Ví dụ self-managed:

~~~yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongodb/server.pem
    CAFile: /secure/mongodb/ca.pem
~~~

Điều này yêu cầu:

- Server certificate/private key hợp lệ.
- CA trust phù hợp.
- Hostname/SAN match.
- Client cấu hình TLS.
- Filesystem permissions cho PEM/key.

### 12.2. TLS không thay authorization

TLS bảo vệ transport và xác minh endpoint. User vẫn có thể xác thực qua SCRAM:

~~~text
mongodb://app_user:<SECRET>@mongo1.example.internal:27017/commerce?authSource=admin&tls=true
~~~

Trong đó `authSource=admin` quyết định nơi tra credential nếu user được tạo trong admin; TLS và authSource phục vụ hai mục đích khác nhau.

### 12.3. TLS client certificate vs SCRAM

Server có thể chấp nhận TLS clients không có client certificate nếu cấu hình cho phép, rồi xác thực user bằng SCRAM.

Nếu dùng MONGODB-X509, client cần certificate/private key và user identity được ánh xạ qua `$external`.

Không bật client certificate requirement trên toàn hệ thống mà chưa kiểm tra các SCRAM clients không có client cert.

### 12.4. Internal TLS giữa cluster members

Replica set/sharded cluster cần cân nhắc cả connections:

- Application → mongos/mongod.
- Mongos → config servers/shards.
- Mongod member → member.

Một TLS certificate chỉ dùng cho endpoint client chưa chắc đáp ứng mọi requirements internal authentication và cluster TLS.

### 12.5. Không tắt certificate validation

Options bỏ kiểm tra certificate/hostname có thể làm mất khả năng xác minh peer và mở rủi ro MITM.

Khi gặp TLS handshake error, kiểm tra:

- CA chain.
- SAN hostname.
- Expiry.
- Key/cert match.
- EKU.
- DNS.
- TLS mode.
- Driver trust store.

Không chữa bằng cách cho phép invalid certificates trên production.

---

## 13. Cấu hình một replica set member

Giả sử `rs0` gồm ba mongod instances, mỗi instance chạy trên một host và có data/log path riêng.

Mẫu **mongod của member thứ nhất**, trong deployment đã chuẩn bị keyfile, user/roles và security bootstrap:

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true

storage:
  dbPath: /var/lib/mongodb

net:
  bindIp: "127.0.0.1,mongo1.example.internal"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongodb/mongo1.pem
    CAFile: /secure/mongodb/ca.pem
    allowConnectionsWithoutCertificates: true

replication:
  replSetName: rs0

security:
  authorization: enabled
  keyFile: /secure/mongodb/keyfile
~~~

**Đây là skeleton**, không phải config áp dụng nguyên xi cho bất kỳ cluster. Cần đối chiếu internal member TLS, certificate identity, topology và keyfile policy. Tham số `allowConnectionsWithoutCertificates: true` trong ví dụ cho phép TLS clients dùng SCRAM không có client cert theo cấu hình, không có nghĩa tắt TLS.

### 13.1. Khởi tạo replica set là thao tác riêng

Startup có:

~~~yaml
replication:
  replSetName: rs0
~~~

chỉ xác định tên replica set process dự kiến tham gia. Nó **không tự thực hiện `rs.initiate()`** và không tự tạo membership config.

Trong `mongosh` với quyền:

~~~javascript
rs.status();
rs.conf();
~~~

Chỉ dùng `rs.initiate()`/`rs.reconfig()` theo runbook, không chạy lại tùy tiện trên cluster đang hoạt động.

### 13.2. Hostname phải đồng bộ

Các members trong `rs.conf()`, DNS, TLS SAN và firewall cần tương thích nhau.

Nếu đổi port/hostname của một member:

1. Cần cập nhật process config.
2. Có thể phải cập nhật replica set config.
3. Cần cập nhật DNS/TLS/firewall.
4. Cần xét impact lên election và client topology.
5. Phải thực hiện rolling change.

Không chỉnh `net.port` một node rồi mặc định replica set tự tìm đúng địa chỉ mới.

### 13.3. Rolling restart

Một quy trình phổ biến cho thay đổi an toàn khi topology hỗ trợ:

1. Ghi baseline `rs.status()` và replication lag.
2. Chuẩn bị/review config.
3. Thay đổi một secondary.
4. Restart secondary theo service manager.
5. Chờ nó healthy, SECONDARY và caught up.
6. Tiếp tục secondary khác nếu có.
7. Cuối cùng xử lý primary theo runbook stepdown/rolling upgrade.
8. Kiểm tra majority/write availability, application errors.
9. Ghi lại change result và rollback.

Không áp dụng cứng nhắc nếu cluster chỉ có hai data-bearing members, đang degraded hoặc không đủ majority.

### 13.4. Tác động của keyfile/TLS rotation

Thay member authentication là thay đổi nhạy cảm. Nếu các members không trust nhau sau restart, node có thể bị cô lập.

Phải có overlap/transition plan được MongoDB hỗ trợ khi đổi certificate, CA hoặc keyfile.

---

## 14. Sharded cluster: phân biệt config server, shard và mongos

Trong sharded cluster có ít nhất các nhóm:

1. Config server replica set.
2. Shards (thường là replica sets).
3. Mongos routers.

### 14.1. Config server mongod

Một config server member có cấu hình đặc thù:

~~~yaml
sharding:
  clusterRole: configsvr

replication:
  replSetName: cfgRS

storage:
  dbPath: /var/lib/mongodb-config

net:
  bindIp: "127.0.0.1,cfg1.example.internal"
  port: 27019
~~~

Đây chỉ là phần lõi để giải thích role; production cần thêm TLS, internal authentication, system log và security phù hợp.

### 14.2. Shard mongod

Một shard member có thể cấu hình:

~~~yaml
sharding:
  clusterRole: shardsvr

replication:
  replSetName: shardA

storage:
  dbPath: /var/lib/mongodb-shard

net:
  bindIp: "127.0.0.1,shard-a1.example.internal"
  port: 27018
~~~

Mỗi replica set shard có tên riêng và membership riêng.

### 14.3. Mongos router

Router dùng `sharding.configDB` để biết config server replica set:

~~~yaml
sharding:
  configDB: cfgRS/cfg1.example.internal:27019,cfg2.example.internal:27019,cfg3.example.internal:27019

net:
  bindIp: "127.0.0.1,mongos1.example.internal"
  port: 27017

systemLog:
  destination: file
  path: /var/log/mongodb/mongos.log
  logAppend: true
~~~

Đây là skeleton chưa có security. Mongos không có `storage.dbPath` của dữ liệu collection.

### 14.4. Mongos với keyfile/TLS

Trong cluster đã cấu hình keyfile internal authentication, mongos có thể cần:

~~~yaml
security:
  keyFile: /secure/mongodb/keyfile

net:
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongodb/mongos1.pem
    CAFile: /secure/mongodb/ca.pem
~~~

Kết hợp với phần `sharding.configDB` và listener ở trên; không dùng riêng một fragment. Nếu cluster dùng X.509 member authentication, config tương ứng khác keyfile.

### 14.5. configDB không phải URL MongoDB thông thường

Định dạng quan trọng:

~~~text
<config-server-replica-set-name>/<host1>:<port1>,<host2>:<port2>,...
~~~

Ví dụ:

~~~text
cfgRS/cfg1.example.internal:27019,cfg2.example.internal:27019,cfg3.example.internal:27019
~~~

Không viết:

~~~text
mongodb://cfg1.example.internal:27019
~~~

vào `sharding.configDB` nếu version yêu cầu replica set connection identifier.

### 14.6. Đổi config server list

Đây không phải thao tác chỉ đổi hostname trong YAML. Cần đảm bảo membership của config RS, DNS, security, router configuration và khả năng reload/restart được hỗ trợ.

Một `mongos` trỏ sai `configDB` có thể không khởi động hoặc không routing đúng.

### 14.7. Mongos không phải shard member

Không đặt:

~~~yaml
storage:
  dbPath: /data/shard

replication:
  replSetName: shardA
~~~

trong `mongos.conf` rồi mong rằng router lưu dữ liệu như shard mongod.

---

## 15. systemd và service manager trên Linux

### 15.1. Cách service được khởi động

Với package cài đặt qua apt/yum, MongoDB thường được quản lý bằng systemd:

~~~bash
sudo systemctl status mongod
~~~

Để xem unit config và start command (trong môi trường có quyền):

~~~bash
systemctl cat mongod
~~~

Dựa trên service unit để xác định:

- File config nào được nạp.
- Service user/group.
- Environment overrides.
- Restart policy.
- Working directory.
- Startup dependencies.

### 15.2. Không thay service default bừa bãi

MongoDB docs lưu ý package init scripts có thể phụ thuộc:

- `systemLog.path`.
- `storage.dbPath`.
- `processManagement.fork`.
- `MONGODB_CONFIG_OVERRIDE_NOFORK`.

Nếu đổi các values này, service có thể không start theo logic của package.

### 15.3. Restart và reload không giống nhau

Một thay đổi startup-only cần restart process. Không mặc định:

~~~bash
sudo systemctl reload mongod
~~~

sẽ nạp lại mọi cấu hình; nhiều MongoDB options không thể reload động.

Khi cần áp dụng config mới:

~~~bash
sudo systemctl restart mongod
~~~

**chỉ thực hiện theo runbook**, sau khi review, approval, backup/HA checks. Restart mongod primary có thể gây failover/ngắt kết nối.

### 15.4. Kiểm tra log khi startup lỗi

~~~bash
sudo systemctl status mongod
journalctl -u mongod -n 100 --no-pager
~~~

Nếu server ghi file diagnostic log riêng, phải kiểm tra cả file được chỉ định ở `systemLog.path`.

### 15.5. processManagement.fork

Trong môi trường chạy dưới service manager, mongod thường nên chạy foreground để service manager quản lý lifecycle theo cách package hỗ trợ.

Tự đặt:

~~~yaml
processManagement:
  fork: true
~~~

mà không xem unit defaults có thể làm service status/stop/restart sai.

### 15.6. Một process trên một dbPath

Không được chạy hai mongod cùng ghi vào một `storage.dbPath`. Cơ chế lock/data files không hỗ trợ kiểu chia sẻ này.

Khi gặp “Address already in use” hoặc “Unable to lock data directory”, kiểm tra process đang chạy trước khi xóa lock files hay kill processes.

---

## 16. Windows service và config file

### 16.1. Đường dẫn Windows

Ví dụ file `C:/MongoDB/conf/mongod.cfg`:

~~~yaml
storage:
  dbPath: "C:/MongoDB/data"

systemLog:
  destination: file
  path: "C:/MongoDB/log/mongod.log"
  logAppend: true

net:
  bindIp: "127.0.0.1"
  port: 27017
~~~

Tạo directories và ACL thích hợp cho service account trước khi khởi động.

### 16.2. Chạy thử trong terminal có quyền

~~~powershell
mongod --config "C:\MongoDB\conf\mongod.cfg"
~~~

Lệnh sẽ khởi động process trong terminal nếu không dùng Windows Service. Không chạy nếu một mongod Windows Service đang dùng cùng dbPath/port.

### 16.3. Kiểm tra Windows Service

~~~powershell
Get-Service -Name MongoDB
~~~

Kiểm tra startup command được đăng ký thực tế trong Service Control Manager; đừng giả định nó dùng file vừa sửa.

### 16.4. processManagement.fork không hỗ trợ Windows

MongoDB documentation nêu `processManagement.fork` không hỗ trợ trên Windows. Không copy Linux config và giữ `fork: true` trong Windows server config.

### 16.5. Quyền file

Windows cần ACL phù hợp trên:

- Data directory.
- Log directory.
- Config file.
- TLS private key / certificate.
- Internal keyfile nếu dùng.
- Backup file paths.

Chạy Service bằng tài khoản có privileges tối thiểu, không mặc định LocalSystem/root-like access khi không cần.

---

## 17. Docker/container và Kubernetes

### 17.1. Container thường dùng foreground process

Container runtime mong đợi process chính chạy foreground:

~~~text
ENTRYPOINT/CMD
  └── mongod --config /etc/mongod.conf
~~~

Không bật `processManagement.fork: true` trong container chỉ vì máy host trước đây dùng daemon mode.

### 17.2. Data volume

Ví dụ kiến trúc:

```text
Host/Persistent Volume
       │
       └── /data/db inside container
                 │
               mongod
~~~

Nếu container bị tạo lại nhưng data không gắn persistent volume, dữ liệu có thể không tồn tại như mong đợi. Cấu hình `storage.dbPath` phải tương thích mount paths.

### 17.3. ConfigMap/Secret

Trong Kubernetes:

- ConfigMap thường dùng cho nonsecret config.
- Secret dùng cho sensitive values/credentials, nhưng vẫn cần RBAC/encryption policy.
- PersistentVolumeClaim giữ data.
- StatefulSet/Operator điều phối members.
- Liveness/readiness probes cần phản ánh topology.
- TLS/keyfiles được mount qua volume/secret theo quyền phù hợp.

Không lưu private key trong ConfigMap hoặc ghi thẳng vào image/repository.

### 17.4. Cấu hình từ Operator là source of truth

Nếu MongoDB Operator quản lý cluster, sửa trực tiếp `mongod.conf` trong Pod có thể mất khi Pod được recreate.

Phải cập nhật Custom Resource/Operator spec theo cách được hỗ trợ.

### 17.5. Pod restart và replica set

Khi restart nhiều pods cùng lúc:

- Có thể mất majority.
- Election xảy ra.
- Replication lag tăng.
- Clients gặp server selection timeout.
- Writes có thể tạm ngưng.

Cần rollout strategy/PodDisruptionBudget/quorum đúng, không đơn giản restart toàn bộ StatefulSet cùng lúc.

### 17.6. Atlas managed MongoDB

Với Atlas, khách hàng thường cấu hình những lựa chọn được dịch vụ hỗ trợ qua Atlas UI/API, không tự chỉnh `mongod.conf`/`mongos.conf`.

Không dùng lệnh systemctl/kubectl của self-managed cluster để sửa hạ tầng Atlas được quản lý.

---

## 18. Startup parameters và runtime server parameters

Đây là hai khái niệm khác nhau.

### 18.1. Startup options

Một startup option được đọc khi tiến trình bắt đầu:

~~~yaml
net:
  port: 27017

storage:
  dbPath: /var/lib/mongodb
~~~

Đổi các giá trị này trong file khi process đang chạy **không tự thay đổi listener/data path**.

Thông thường phải có quy trình restart hoặc migration phù hợp.

### 18.2. Server parameters

MongoDB có các server parameters dùng để điều chỉnh hành vi triển khai.

Ví dụ cấu hình lúc startup:

~~~yaml
setParameter:
  enableLocalhostAuthBypass: false
~~~

Hoặc CLI:

~~~bash
mongod --setParameter enableLocalhostAuthBypass=false --config /etc/mongod.conf
~~~

**Lưu ý:** `enableLocalhostAuthBypass: false` chỉ là ví dụ server parameter liên quan bảo mật; tắt localhost exception trước khi có admin user có thể ảnh hưởng bootstrap. Không áp dụng nếu chưa có runbook tạo user đầu tiên.

### 18.3. Runtime setParameter command

Khi parameter được tài liệu đánh dấu **runtime-changeable**, có thể sử dụng:

~~~javascript
db.getSiblingDB("admin").runCommand({
  setParameter: 1,
  PARAMETER_NAME: "VALUE"
});
~~~

Ví dụ trên là khung minh họa; không phải lệnh có thể thực thi nguyên văn vì parameter name/value chưa được thay.

Một lệnh cụ thể cần:

- Parameter name đúng.
- Data type đúng.
- Quyền admin tương ứng.
- Hỗ trợ runtime trên version/process đang dùng.

### 18.4. Không phải parameter nào cũng runtime-changeable

MongoDB docs phân biệt:

- Chỉ startup.
- Startup và runtime.
- Chỉ mongod.
- Chỉ mongos.
- Chỉ một role/edition/version.
- Deprecated/removed.

Nếu cố `setParameter` một startup-only parameter, server sẽ báo lỗi. Không tìm cách ép qua direct storage edits.

### 18.5. setParameter khác setProfilingLevel/setLogLevel

Một số cấu hình động có helper riêng:

~~~javascript
db.getSiblingDB("admin").setLogLevel(1, "network");
~~~

Hoặc:

~~~javascript
db.getSiblingDB("commerce").setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.1
});
~~~

Các helper vẫn cần quyền và có tác động/phạm vi riêng. Không phải mọi helper đều tương đương thay một option startup.

---

## 19. Đọc cấu hình thực tế bằng getCmdLineOpts

### 19.1. Lệnh chính

Trong `mongosh` có quyền:

~~~javascript
db.getSiblingDB("admin").runCommand({
  getCmdLineOpts: 1
});
~~~

Hoặc helper:

~~~javascript
db.serverCmdLineOpts();
~~~

Kết quả có thể gồm:

- `argv`: các arguments dùng để gọi mongod/mongos.
- `parsed`: những options được parse từ CLI và file config.

### 19.2. Output minh họa

~~~javascript
{
  argv: [
    "/usr/bin/mongod",
    "--config",
    "/etc/mongod.conf"
  ],
  parsed: {
    config: "/etc/mongod.conf",
    net: {
      bindIp: "127.0.0.1",
      port: 27017
    },
    storage: {
      dbPath: "/var/lib/mongodb"
    },
    systemLog: {
      destination: "file",
      path: "/var/log/mongodb/mongod.log",
      logAppend: true
    }
  },
  ok: 1
}
~~~

Kết quả chỉ mang tính minh họa; thực tế phụ thuộc binary/version và các flags được chỉ định.

### 19.3. Vì sao nên dùng getCmdLineOpts?

Một incident điển hình:

- File `mongod.conf` ghi `bindIp: 127.0.0.1`.
- Service unit gọi thêm `--bind_ip 127.0.0.1,10.0.0.5`.
- Engineer chỉ mở YAML nên hiểu sai security posture.

`getCmdLineOpts.parsed` giúp biết process đã parse những gì lúc khởi động.

### 19.4. Không xem parsed là mọi runtime value

`parsed` phản ánh startup configuration được parse. Một runtime `setParameter` có thể khiến effective current value khác startup, và một số server defaults không nhất thiết hiện ra giống như explicit fields.

Do đó cần phân biệt:

~~~text
Desired config on disk
       ≠
Parsed startup config
       ≠
Current runtime parameters
       ≠
Cluster metadata / app observed behavior
~~~

### 19.5. Cảnh báo secrets trong output

`argv`/`parsed` có thể chứa những đường dẫn, cấu hình nhạy cảm hoặc options được phép hiển thị theo MongoDB version/redaction.

Không paste nguyên output `getCmdLineOpts` vào ticket công khai, especially khi có passwords/secret references. Kiểm tra và sanitize trước khi chia sẻ.

---

## 20. Xem runtime parameters bằng getParameter

### 20.1. Đọc parameter cụ thể

Ví dụ:

~~~javascript
db.getSiblingDB("admin").runCommand({
  getParameter: 1,
  logComponentVerbosity: 1
});
~~~

### 20.2. Xem thêm một số parameters được phép

~~~javascript
db.getSiblingDB("admin").runCommand({
  getParameter: 1,
  diagnosticDataCollectionEnabled: 1
});
~~~

**Không khẳng định mọi parameter hiện diện trên mọi MongoDB Server version.** Nếu parameter không có hoặc bị hạn chế trên managed deployment, lệnh có thể trả lỗi. Chọn parameter theo bảng chính thức.

### 20.3. getParameter không thay getCmdLineOpts

- `getCmdLineOpts`: startup CLI/config đã parse.
- `getParameter`: giá trị một server parameter hiện thời hoặc được hỗ trợ.
- `serverStatus`: runtime statistics.
- `hello`: thông tin topology/role.
- `rs.status()`: replica set health.

Mỗi nguồn trả lời một câu hỏi khác nhau.

### 20.4. Thay đổi log verbosity runtime

Trong lab được phép:

~~~javascript
const admin = db.getSiblingDB("admin");

admin.setLogLevel(1, "network");

// Sau điều tra, khôi phục đúng giá trị ban đầu.
admin.setLogLevel(0, "network");
~~~

Trong production, lưu **giá trị ban đầu**, kể cả inheritance settings; không tự coi 0 là rollback chính xác cho mọi trường hợp.

### 20.5. setParameter không luôn persist qua restart

Nếu parameter được thay đổi runtime nhưng không ghi vào startup config hoặc cơ chế quản trị, restart có thể đưa nó về giá trị mặc định/configured.

Vì vậy một runbook phải xác định:

1. Đổi tạm thời để debug.
2. Đổi lâu dài bằng IaC/config.
3. Kiểm tra runtime và startup source of truth.
4. Tránh drift sau restart.

---

## 21. Các nhóm tham số cần biết

| Nhóm | Ví dụ | Process | Tác động |
|---|---|---|---|
| Network | `net.port`, `net.bindIp`, `net.ipv6` | mongod/mongos | Listener/connectivity |
| TLS | `net.tls.mode`, `certificateKeyFile`, `CAFile` | mongod/mongos | Encryption/trust |
| Storage | `storage.dbPath`, WiredTiger cache | mongod | Files/IO/cache |
| Replication | `replication.replSetName`, oplog settings | mongod | Replica set membership |
| Sharding role | `sharding.clusterRole` | mongod | Shard/configsvr |
| Router config | `sharding.configDB` | mongos | Config RS routing |
| Security | `security.authorization` | mongod | RBAC |
| Member auth | `security.keyFile`, cluster auth mode | mongod/mongos theo role | Cluster identity |
| Logging | `systemLog.*` | mongod/mongos | Diagnostics |
| Profiling | `operationProfiling.*` | mongod | Profile/slow ops |
| Process | `processManagement.*` | mongod/mongos theo OS | Startup lifecycle |
| Server params | `setParameter.*` | Tùy parameter | Feature/tuning |
| Auditing | `auditLog.*` | Edition/version tương ứng | Security audit |

### 21.1. Startup-only hay runtime?

Không có quy tắc “toàn bộ net là startup-only, toàn bộ setParameter là runtime”.

Tốt nhất:

1. Chọn một option/parameter.
2. Tra reference theo exact Server version.
3. Kiểm tra `Available for mongod/mongos`.
4. Kiểm tra `Available at startup/runtime`.
5. Kiểm tra operational impact.
6. Chỉ thực hiện thay đổi theo supported mechanism.

### 21.2. Một startup parameter có thể có tính năng phụ thuộc

Ví dụ một server parameter liên quan query execution, sharding hay security có thể chỉ hỗ trợ khi role/feature tương ứng đã bật. Cấu hình mà không hiểu dependency có thể khiến startup fail hoặc có hiệu lực ngoài ý muốn.

---

## 22. External configuration values và expansion directives

Một số MongoDB versions hỗ trợ **external configuration values** nhằm lấy giá trị cấu hình từ nguồn khác.

Các directives được tài liệu mô tả như:

- `__rest`: tải từ REST endpoint.
- `__exec`: chạy lệnh bên ngoài để cung cấp giá trị.

Để cho phép expansion, có option:

~~~bash
mongod --config /etc/mongod.conf --configExpand "rest,exec"
~~~

Hoặc:

~~~bash
mongos --config /etc/mongos.conf --configExpand "rest,exec"
~~~

### 22.1. Tác dụng

- Tách một số secrets khỏi file config tĩnh.
- Dùng nguồn dữ liệu ngoài phù hợp với hệ thống secret management.
- Cho phép cấu hình được tạo động theo cơ chế được MongoDB hỗ trợ.

### 22.2. Rủi ro nghiêm trọng

`__exec` có thể gọi external commands trong startup context. Nếu attacker sửa config hoặc command path, họ có thể tác động đến process.

MongoDB docs đặt các yêu cầu chặt chẽ về file permissions với expansion directives trên Unix-like systems.

Không dùng:

~~~yaml
# Example only; do not paste an untrusted command here.
~~~

và không cho client/user ngoài kiểm soát tự đặt shell command trong cấu hình.

### 22.3. Không bật configExpand nếu không cần

Nếu file dùng directives mà startup không cho phép expansion, server có thể fail.

Ngược lại, bật `--configExpand "rest,exec"` không có lý do cũng làm tăng phạm vi cơ chế được phép dùng.

Ưu tiên whitelist các directives thật cần, source đáng tin và kiểm soát file permissions.

### 22.4. Secrets nên nằm ở đâu?

Có thể lựa chọn:

- Secret manager.
- Mounted files với permissions.
- Operator/Kubernetes Secret.
- OS secure store.
- External expansion supported configuration.
- TLS key material trong protected volume.

Không nên giữ private keys/password trực tiếp trong Git hoặc command history.

### 22.5. Chú ý lifecycle

Nếu secret đổi ở external source nhưng process chỉ đọc lúc startup, giá trị effective có thể không thay đổi cho tới khi process được reload/restart theo cơ chế hỗ trợ.

Phải xác minh rotation semantics cụ thể thay vì nghĩ “sửa secret manager là MongoDB tự dùng secret mới ngay”.

---

## 23. Kiểm tra cấu hình trước khi đổi production

### 23.1. Review theo schema/version

Với mỗi thay đổi, kiểm tra:

- Đúng option name và spelling.
- Đúng cấu trúc YAML.
- Kiểu dữ liệu đúng.
- Enum case-sensitive đúng.
- Process mongod/mongos phù hợp.
- Không có mutually exclusive options.
- Edition/version hỗ trợ.
- Startup-only vs runtime.
- OS path permissions.
- Cluster topology dependencies.

### 23.2. Dùng bảng mapping chính thức

Nếu chuyển command line cũ sang YAML:

- Dùng reference `Self-Managed Configuration and Command-Line Options Mapping`.
- Không tự suy luận camelCase của mọi CLI flag.
- Không copy flags đã deprecated.
- Không dùng mongo shell options làm mongod server options.

### 23.3. Chạy thử trong lab cô lập

Một file YAML có thể parse được nhưng không khởi động được vì:

- Port đang được sử dụng.
- dbPath bị khóa.
- Missing CA/PEM/keyfile.
- DNS không resolve.
- Replica set role/security mismatch.
- Không đủ quyền OS.

**Không dùng production data directory để thử file config lạ.**

### 23.4. Kiểm tra bằng --outputConfig khi phù hợp

MongoDB hỗ trợ `--outputConfig` cho việc biểu diễn config/CLI thành YAML trên version tương ứng. Đây là trợ giúp chuyển đổi/chẩn đoán.

Nhưng nó không thay thế việc test startup trong môi trường riêng, connectivity, cluster authentication hoặc application smoke tests.

### 23.5. Kiểm tra effective config sau startup

~~~javascript
const admin = db.getSiblingDB("admin");

printjson(admin.runCommand({
  getCmdLineOpts: 1
}));
~~~

Sau đó kiểm tra:

- Network listener.
- TLS handshake.
- `db.adminCommand({hello:1})`.
- `rs.status()` nếu là replica set.
- `sh.status()` nếu là sharded cluster/role phù hợp.
- Health/metrics.

Đừng coi `getCmdLineOpts` thành công là end-to-end validation đầy đủ.

---

## 24. Runbook thay đổi cấu hình mongod an toàn

### Bước 1 — Xác định phạm vi

Ghi:

~~~text
Change ID:
Environment:
Cluster:
Replica set:
Member host:
Binary version:
FCV:
Config file path:
Service manager:
Owner:
Rollback owner:
Maintenance window:
~~~

### Bước 2 — Snapshot hiện trạng

- Backup current config trong kho có kiểm soát.
- Ghi `getCmdLineOpts` đã sanitize.
- Ghi `getParameter` values liên quan.
- Ghi `rs.status()`/member health.
- Đo application p95/p99, CPU, memory, disk, lag.
- Kiểm tra backups và recovery readiness.

Không dump raw secrets vào ticket change.

### Bước 3 — Review thay đổi

Đối chiếu:

- Version support.
- Startup-only/runtime.
- Security impact.
- Network/TLS/DNS.
- Replication/quorum.
- Disk/storage path.
- Service user permissions.
- Compatibility của các members.

### Bước 4 — Thử trên staging/canary

- Dùng config tương tự.
- Test startup.
- Test authentication/TLS.
- Test replica membership.
- Test application.
- Quan sát log warnings.

### Bước 5 — Roll out có thứ tự

Nếu không cần restart và parameter hỗ trợ runtime:

- Thực hiện change qua API phù hợp.
- Quan sát và ghi hiệu lực.
- Đồng bộ IaC nếu cần persist.

Nếu cần restart:

- Thực hiện rolling restart theo topology.
- Tránh mất majority.
- Chờ replication catch-up.
- Kiểm tra status giữa mỗi bước.

### Bước 6 — Xác minh

- Process running.
- Parsed options đúng.
- Runtime parameters đúng.
- Port/bind/TLS đúng.
- Replica set/sharded routing healthy.
- App queries thành công.
- Metrics không xấu đi.

### Bước 7 — Rollback

- Khôi phục exact config/parameter values cũ.
- Khôi phục secret/trust chain nếu rollback được hỗ trợ.
- Restart theo runbook nếu cần.
- Quan sát healthy state.
- Ghi lại event timeline.

### Bước 8 — Kết thúc

- Cập nhật config repository/operational docs.
- Đóng temporary debug overrides.
- Lưu metrics.
- Ghi post-change review.

---

## 25. Rolling change cho replica set: chi tiết cần chú ý

### 25.1. Trạng thái ban đầu

Giả sử:

~~~text
rs0:
  mongo-a PRIMARY
  mongo-b SECONDARY
  mongo-c SECONDARY
~~~

Muốn đổi TLS certificate/command logging trên cả ba members.

### 25.2. Điều kiện trước khi bắt đầu

- Tất cả members healthy.
- Không có rollback risk hoặc replication lag lớn.
- Không có election đang diễn ra.
- Majority có thể duy trì khi một node restart.
- Certificate/CA mới được các members và clients tin cậy theo transition plan.
- Backup/rollback có sẵn.

### 25.3. Secondary trước

1. Thay config/cert của mongo-b.
2. Restart mongo-b theo service.
3. Chờ nó trở về SECONDARY.
4. Kiểm tra replication lag.
5. Lặp lại với mongo-c.

### 25.4. Primary sau

Có thể dùng controlled stepdown/maintenance theo runbook, rồi restart node từng là primary sau khi có primary mới healthy.

Không chỉ `systemctl restart mongod` trên primary mà không tính impact tới writers.

### 25.5. Với keyfile hoặc clusterAuthMode

Đây là nhóm thay đổi có rủi ro cao hơn logging. Cần protocol/transition path được MongoDB hỗ trợ, không thay tất cả credentials một lúc khiến members không xác thực được với nhau.

### 25.6. Nếu cluster degraded

Nếu chỉ còn một primary healthy và không đủ redundancy, việc restart có thể gây outage. Phải đánh giá lại change window/rủi ro thay vì tiếp tục theo checklist một cách máy móc.

---

## 26. Thay đổi cấu hình mongos trong sharded cluster

### 26.1. Mongos thường có thể được triển khai nhiều instances

Ví dụ:

~~~text
App clients
  ├── mongos-a
  └── mongos-b
         │
     Sharded cluster
~~~

Khi update mongos router config, thường có thể xử lý một router rồi chuyển traffic qua router khác, **nếu clients/topology/load balancer đã hỗ trợ**.

### 26.2. Không sửa mọi router cùng lúc

Một quy trình:

1. Xác nhận config server RS và shards healthy.
2. Xem `sharding.configDB` và TLS/keyfile.
3. Đổi mongos-a.
4. Restart mongos-a theo runbook.
5. Kiểm tra clients routing qua mongos-a.
6. Quan sát server selection/errors.
7. Thay mongos-b khi first router healthy.

### 26.3. Router config và cluster metadata

Đổi `sharding.configDB` trong mongos file không thay đổi membership của config server RS. Phải biết config server RS đang có các members nào.

Tương tự, đổi port trong mongos cần cập nhật application URI/service discovery/load balancer.

### 26.4. Mongos metrics/logging

Mongos có diagnostic logs và runtime parameters, nhưng không lưu dữ liệu collection như shard mongod. Đừng đọc `mongos storage.dbPath` như thể đó là shard volume.

---

## 27. Upgrade MongoDB Server và compatibility của config options

Một file cấu hình hợp lệ với MongoDB 5.0 có thể không được MongoDB 8.0 hoặc 9.0 chấp nhận do deprecated/removed options.

### 27.1. Ví dụ journaling option cũ

Từ MongoDB 6.1, journaling luôn bật và một số journal toggles cũ không còn được hỗ trợ.

Nếu config chứa `storage.journal.enabled` từ tutorial cũ, upgrade startup có thể fail.

### 27.2. Ví dụ thay đổi networking/role rules

Các server versions mới có thể đặt yêu cầu khác cho hostname, TLS minimum protocol, sharding configuration hoặc cluster parameters.

Không dùng tài liệu của phiên bản bất kỳ; chọn đúng MongoDB Manual theo target server binary.

### 27.3. FCV khác binary version

Server binary version và Feature Compatibility Version (FCV) không phải một thứ.

Một upgrade có thể có các bước:

1. Nâng binary theo supported upgrade path.
2. Đợi cluster healthy.
3. Đánh giá và cập nhật FCV theo runbook.
4. Bật những features tương ứng sau khi đủ điều kiện.

Không chỉ sửa `setParameter` hoặc config file để “đổi MongoDB version”. FCV là cluster setting quản lý theo quy trình được hỗ trợ.

### 27.4. Removed parameters

Một tham số từ blog cũ có thể không tồn tại ở target version. Server có thể báo lỗi unknown option/invalid value.

Giải pháp:

- Đọc release notes.
- Đọc removed/deprecated parameters.
- Cập nhật file config trong staging.
- Review binary/systemd/container compatibility.
- Test rolling upgrade.

### 27.5. Không tự đổi storage.engine để upgrade

Nâng cấp MongoDB version không đồng nghĩa có thể sửa storage engine/data paths tùy tiện. Dữ liệu hiện tại phải được xử lý theo supported upgrade path.

---

## 28. Troubleshooting: server không khởi động

### 28.1. YAML parse error

Dấu hiệu:

~~~text
Failed to parse config file
Invalid YAML
Unrecognized option
~~~

Hướng xử lý:

- Kiểm tra indentation không dùng tab.
- Kiểm tra duplicate keys.
- Kiểm tra quote/type.
- Kiểm tra ASCII encoding.
- Đọc line/option mà server báo.
- So config reference theo version.

### 28.2. Unknown option

Nguyên nhân:

- Typo field.
- Option thuộc mongod nhưng dùng ở mongos.
- Deprecated/removed option.
- Version/edition không hỗ trợ.

Không sửa thành option khác bằng cách đoán tên; dùng mapping chính thức.

### 28.3. Port already in use

Ví dụ:

~~~text
Address already in use
~~~

Kiểm tra service/process đang dùng port, không kill process production không rõ danh tính.

Linux:

~~~bash
ss -ltnp | grep 27017
~~~

PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 27017
~~~

Cần quyền phù hợp để xem process details.

### 28.4. Data directory inaccessible

Nguyên nhân:

- Path sai.
- Directory không tồn tại.
- Owner/permissions.
- SELinux/AppArmor.
- Volume không mount.
- Filesystem read-only/full.
- Data file lock của mongod khác.

Không xóa data/lock files tùy tiện. Xác nhận process nào thực sự đang sử dụng directory.

### 28.5. Log path inaccessible

Server có thể không ghi được log file do permissions/disk đầy. Nếu server vừa chết trước khi mở log, stderr/service journal có thể chứa lỗi quan trọng.

### 28.6. TLS certificate error

Kiểm tra:

- PEM file tồn tại/đọc được.
- Certificate và private key khớp.
- CA chain/hostname SAN.
- Certificate expiry.
- Mode/cluster TLS requirements.
- Member/client certificate trust.

Đừng bỏ verification trên production.

### 28.7. Keyfile authentication mismatch

Replica set members không liên lạc sau khi thay keyfile:

- Secret content khác nhau.
- File permissions sai.
- Cluster auth mode mismatch.
- Host/TLS identity không khớp.
- Rolling transition chưa đúng.

Dừng rollout và áp runbook member auth.

### 28.8. Replica set name mismatch

Server chạy:

~~~yaml
replication:
  replSetName: rsDifferent
~~~

trong khi cluster config yêu cầu `rs0`. Member có thể không tham gia đúng replica set.

Cần sửa theo metadata cluster, không tạo replica set mới trên data của cluster hiện có.

### 28.9. Mongos không thấy config server

Nguyên nhân:

- `sharding.configDB` sai.
- DNS/firewall/port.
- TLS/CA/keyfile mismatch.
- Config server RS không healthy.
- Config RS name không đúng.
- Routing metadata/chưa hoàn tất cấu hình sharded cluster.

Không thêm `storage.dbPath` vào mongos để “sửa”.

### 28.10. Sửa file nhưng runtime không đổi

Có thể do:

- Chưa restart startup-only option.
- Sửa nhầm file; service dùng config khác.
- CLI override.
- Config được Operator rewrite.
- Runtime parameter được thay nhưng startup config chưa đổi.
- Đang xem mongod node khác/mongos router khác.
- Restart thất bại nên process cũ vẫn chạy.

Dùng `getCmdLineOpts` và service/OS inspection để xác minh.

### 28.11. Server start nhưng app không kết nối

Có thể là:

- `net.bindIp` chỉ localhost.
- Firewall.
- URI sai host/port/replicaSet.
- TLS trust/hostname.
- `authSource` sai.
- Authorization roles.
- DNS propagation.
- Load balancer/Service discovery.

Không giải quyết mọi lỗi kết nối bằng `bindIpAll: true`.

---

## 29. Thực hành A: so sánh CLI và YAML trong standalone lab

### 29.1. Chuẩn bị environment

Dùng một local MongoDB lab không chứa dữ liệu quan trọng.

Tạo config tương ứng với:

~~~yaml
systemLog:
  destination: file
  path: /tmp/mongod-config-lab.log
  logAppend: true

storage:
  dbPath: /tmp/mongod-config-lab

net:
  bindIp: 127.0.0.1
  port: 27028
~~~

Tạo thư mục data và đảm bảo user chạy mongod có quyền. Các đường dẫn `/tmp` là ví dụ Linux/macOS, không phải hướng dẫn production.

### 29.2. Start

~~~bash
mongod --config /path/to/mongod-lab.conf
~~~

Không start nếu port 27028/dbPath đang được instance khác dùng.

### 29.3. Connect

~~~bash
mongosh "mongodb://127.0.0.1:27028/"
~~~

Trong shell:

~~~javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ getCmdLineOpts: 1 });
~~~

### 29.4. Thử override

Sau khi stop lab mongod an toàn, chạy:

~~~bash
mongod --config /path/to/mongod-lab.conf --port 27029
~~~

Kết nối:

~~~bash
mongosh "mongodb://127.0.0.1:27029/"
~~~

Xem `getCmdLineOpts.parsed.net.port`, ghi lại sự khác biệt giữa file config và argument.

Không dùng override để mở port production mà chưa review.

### 29.5. Câu hỏi

- Cấu hình trên disk nói port gì?
- Effective parsed startup options nói port gì?
- Việc đổi port có tác dụng khi server đang chạy không?
- CLI flag có được ghi ngược lại file YAML không?
- Nếu restart từ service chỉ đọc YAML, port nào được dùng?

---

## 30. Thực hành B: startup-only và runtime parameter

Trong lab:

1. Đọc `getCmdLineOpts`.
2. Đọc `getParameter` cho một parameter được hỗ trợ.
3. Thử thay đổi log level cho một component khi được phép.
4. Xác minh giá trị runtime.
5. Khôi phục giá trị ban đầu.
6. Xác định một option startup-only như `net.port`.
7. Giải thích vì sao thay YAML port không làm listener đổi ngay.

Lệnh mẫu:

~~~javascript
const admin = db.getSiblingDB("admin");

printjson(admin.runCommand({
  getParameter: 1,
  logComponentVerbosity: 1
}));

// In a permitted lab only:
admin.setLogLevel(1, "network");

// Restore based on actual original value, not assumption.
admin.setLogLevel(0, "network");
~~~

Nếu component đang kế thừa giá trị từ parent (ví dụ trạng thái tương ứng -1), rollback phải dùng giá trị gốc, không máy móc đặt 0.

---

## 31. Thực hành C: replica set configuration

Giả sử ba hosts:

~~~text
mongo1.example.internal
mongo2.example.internal
mongo3.example.internal
~~~

Hãy:

1. Thiết kế cấu hình `mongod` cho mỗi member.
2. Đặt cùng `replication.replSetName`.
3. Dùng data/log paths riêng trên mỗi host.
4. Thiết kế TLS SAN/CA và keyfile.
5. Xác định ai quản lý user/roles.
6. Mô tả thủ tục `rs.initiate()` hoặc membership config phù hợp.
7. Viết rolling restart plan cho thay đổi `systemLog.verbosity` hoặc certificate.
8. Đề xuất khi nào nên dùng runtime setLogLevel thay vì restart.

Chỉ triển khai trên replica set lab, không tự chạy cluster commands trên production.

---

## 32. Thực hành D: sharded cluster configuration

Cho:

~~~text
Config RS: cfgRS
  cfg1:27019
  cfg2:27019
  cfg3:27019

Shard RS: shardA
  shard-a1:27018
  shard-a2:27018
  shard-a3:27018

Routers:
  mongos1:27017
  mongos2:27017
~~~

Hãy viết 3 skeleton configs:

1. Config server mongod.
2. Shard mongod.
3. Mongos router.

So sánh:

- `sharding.clusterRole`.
- `replication.replSetName`.
- `sharding.configDB`.
- `storage.dbPath`.
- `security.keyFile`.
- TLS paths.

Giải thích vì sao `mongos` không có `storage.dbPath`.

---

## 33. Thực hành E: sự cố startup

Một config file:

~~~yaml
net:
    bindIp: "127.0.0.1"
  port: 27017

storage:
  dbPath: /var/lib/mongodb

security:
  authorization: Enabled
~~~

Hãy nêu:

1. Lỗi YAML indentation.
2. Giá trị enum authorization sai case theo MongoDB version mới.
3. Những kiểm tra OS path/permissions cần làm.
4. Cách xác minh service đang đọc đúng file.
5. Vì sao không sửa permission bằng `chmod 777`.
6. Cách test trên lab trước khi restart production.

---

## 34. Thực hành F: drift giữa file và runtime

File:

~~~yaml
net:
  bindIp: 127.0.0.1
  port: 27017
~~~

Service lại start với:

~~~text
mongod --config /etc/mongod.conf --bind_ip 127.0.0.1,10.0.0.5
~~~

Câu hỏi:

- Server thực tế lắng nghe ở đâu?
- Vì sao chỉ kiểm tra YAML là không đủ?
- Dùng `getCmdLineOpts` để lấy bằng chứng thế nào?
- Cần xem firewall/TLS/authorization gì?
- Làm sao sửa nguồn config để tránh drift lần sau?

---

## 35. Thực hành G: thay đổi trên Kubernetes

Một MongoDB cluster do Operator quản lý.

1. Chỉ ra desired state nằm ở CR, ConfigMap hay operator spec.
2. Vì sao sửa file trong Pod không bền?
3. Cần xử lý Secret/TLS/private key ra sao?
4. Data PVC, headless Service, DNS ảnh hưởng đến config thế nào?
5. Thiết kế rolling update giữ quorum.
6. Theo dõi Pod restart/replica set primary/lag.
7. Giải thích vì sao `processManagement.fork: true` thường không phù hợp container.

---

## 36. Thực hành H: upgrade compatibility

Một server config cũ có:

~~~yaml
storage:
  journal:
    enabled: false
~~~

Hãy:

1. Xác định phiên bản mà option này không còn được hỗ trợ.
2. Đọc release notes theo target version.
3. Đề xuất cách sửa config.
4. Giải thích vì sao không tắt journal ở versions mới.
5. Phân biệt nâng binary với thay FCV.
6. Thiết kế smoke tests sau rolling upgrade.

---

## 37. Thực hành I: bảo mật và secret management

Một mongos config bị commit vào Git với private key password hoặc keyfile nội dung.

Hãy:

1. Đánh giá rủi ro.
2. Xác định secret nào phải rotate.
3. Đề xuất cách lưu secret qua protected files/secret manager.
4. Phân biệt `__exec`/`__rest` với plain YAML.
5. Giải thích yêu cầu permissions.
6. Đề xuất audit/change control.
7. Không đưa secret thật vào câu trả lời, logs hoặc ticket.

---

## 38. Thực hành J: viết change runbook

Giả sử thay `net.tls.certificateKeyFile` trên replica set production.

Runbook cần:

1. Scope/approval.
2. Inventory members.
3. Version/FCV.
4. Backup và baseline health.
5. CA trust và SAN checks.
6. Secret/key permissions.
7. Rolling update order.
8. Quorum/stepdown policy.
9. Validation kết nối TLS/Java Driver.
10. Monitoring và stop conditions.
11. Rollback/overlap.
12. Post-change cleanup.

---

## 39. Checklist vận hành trước khi commit config

### 39.1. Cấu hình

- [ ] Đúng process `mongod` hoặc `mongos`.
- [ ] Đúng MongoDB Server version.
- [ ] Đúng YAML indentation/ASCII encoding.
- [ ] Không có duplicate keys hoặc options không hỗ trợ.
- [ ] Không có mutually exclusive options.
- [ ] Không dùng option deprecated/removed.
- [ ] Đã đối chiếu CLI mapping và environment overrides.
- [ ] File source of truth rõ ràng.
- [ ] Có kế hoạch kiểm tra `getCmdLineOpts`.

### 39.2. Network và storage

- [ ] `net.bindIp` giới hạn đúng interfaces.
- [ ] Port đúng, firewall/DNS phù hợp.
- [ ] Không mở wildcard binding thiếu kiểm soát.
- [ ] `storage.dbPath` trỏ đúng data directory nếu là mongod.
- [ ] Storage/volume mounted và có đủ disk.
- [ ] Owner/ACL/SELinux/AppArmor đã được xem xét.
- [ ] Không để hai mongod cùng dùng một dbPath.

### 39.3. Replica set/sharding

- [ ] `replSetName` khớp metadata.
- [ ] Member hostnames/ports/TLS SAN phù hợp.
- [ ] Keyfile/X.509 member auth đồng bộ.
- [ ] Config server có `clusterRole: configsvr`.
- [ ] Shard server có `clusterRole: shardsvr`.
- [ ] Mongos có `sharding.configDB` đúng.
- [ ] Có rolling restart đảm bảo majority.
- [ ] Không thay cluster roles bằng cách chỉ sửa YAML ngoài runbook.

### 39.4. Security

- [ ] Authorization và users/roles đã chuẩn bị.
- [ ] TLS trust chain/hostname validated.
- [ ] Không tắt certificate verification.
- [ ] Keyfile/private keys có permission hạn chế.
- [ ] Secret không nằm trong Git/logs.
- [ ] Không cấp root cho application vô cớ.
- [ ] Có rotation và rollback khi thay secret.

### 39.5. Lifecycle

- [ ] Service manager/Operator source of truth xác định.
- [ ] Biết option startup-only hay runtime-changeable.
- [ ] Biết runtime config có persist qua restart không.
- [ ] Đã ghi baseline metrics và parsed options.
- [ ] Có test staging.
- [ ] Có monitoring sau rollout.
- [ ] Có rollback plan.
- [ ] Đã cập nhật IaC/runbook.

---

## 40. Những nhầm lẫn phổ biến

| Nhầm lẫn | Sự thật |
|---|---|
| mongos cũng lưu collections như mongod | Mongos chỉ routing; data nằm trên mongod shards |
| Mongos cần storage.dbPath | Không theo nghĩa mongod data directory |
| Cứ có mongod.conf là server dùng file ấy | Phải xem service command và getCmdLineOpts |
| Sửa YAML là runtime thay đổi ngay | Nhiều options cần restart |
| Mọi CLI flag đều ghi ngược vào YAML | Không |
| CLI và YAML xung đột thì luôn chọn giá trị cuối | Một số options override, một số mutually exclusive hoặc fail |
| YAML cho phép tabs để indent | Không |
| Tên option không phân biệt hoa/thường | Nhiều enum names case-sensitive |
| Cứ lưu YAML tiếng Việt UTF-8 là tương thích | MongoDB docs yêu cầu config file ASCII |
| bindIpAll là cách sửa mọi lỗi kết nối | Có thể mở network nguy hiểm |
| security.authorization trên mongos giống mongod | Option này dành cho mongod |
| Bật authorization trên replica set không cần member auth | Cần internal authentication phù hợp |
| Keyfile là password của app | Là shared secret cho member authentication |
| TLS là thay thế mọi users/roles | TLS transport và authentication/authorization khác nhau |
| storage.dbPath có thể đổi để di chuyển dữ liệu nóng | Cần migration procedure |
| Có thể copy WiredTiger files lúc mongod đang ghi | Không phải backup/migration hợp lệ mặc định |
| storage.journal.enabled dùng trên mọi MongoDB version | Đã bị loại bỏ ở MongoDB 6.1+ |
| Replica set name đổi chỉ bằng một dòng YAML | Còn metadata/membership/reconfiguration |
| Mongos configDB là URL mongodb:// bất kỳ | Cần config server replica set identifier phù hợp |
| Restart tất cả replica set members cùng lúc là rolling | Có thể mất majority |
| systemctl reload luôn nạp lại mọi MongoDB settings | Không |
| setParameter dùng cho mọi cấu hình | Có startup-only và role/version restrictions |
| getCmdLineOpts cho thấy mọi current runtime values | Chủ yếu parsed startup options; cần getParameter/metrics |
| setParameter runtime tự persist vĩnh viễn | Có thể reset qua restart |
| processManagement.fork phù hợp mọi OS | Không hỗ trợ Windows và thường không phù hợp container |
| Sửa config trong Pod là durable | Operator có thể ghi đè khi reconcile |
| Atlas có thể sửa mongod.conf bằng SSH | Atlas quản lý hạ tầng/config |
| Bật log verbosity tối đa là an toàn | Có overhead và rủi ro lộ dữ liệu |
| Test ping là đủ xác nhận cấu hình | Còn TLS/auth/roles/replica/shard/client semantics |
| Rollback chỉ là copy file cũ | Còn runtime settings, secrets, topology và startup |
| Upgrade binary không ảnh hưởng config | Options có thể deprecated/removed |
| FCV và binary version là một | Khác nhau và có upgrade procedure riêng |

---

## 41. Tài liệu MongoDB chính thức

Các link dưới đây cung cấp reference theo version. Chọn đúng manual của MongoDB Server đang chạy, vì một số fields/behaviors thay đổi qua releases.

- [MongoDB Manual — Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — mongod](https://www.mongodb.com/docs/manual/reference/program/mongod/)
- [MongoDB Manual — mongos](https://www.mongodb.com/docs/manual/reference/program/mongos/)
- [MongoDB Manual — Configuration and Command-Line Options Mapping](https://www.mongodb.com/docs/manual/reference/configuration-file-settings-command-line-options-mapping/)
- [MongoDB Manual — Run-time Database Configuration for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/configuration/)
- [MongoDB Manual — Convert Command-Line Options to YAML](https://www.mongodb.com/docs/manual/tutorial/convert-command-line-options-to-yaml/)
- [MongoDB Manual — getCmdLineOpts command](https://www.mongodb.com/docs/manual/reference/command/getcmdlineopts/)
- [MongoDB Manual — db.serverCmdLineOpts()](https://www.mongodb.com/docs/manual/reference/method/db.servercmdlineopts/)
- [MongoDB Manual — MongoDB Server Parameters](https://www.mongodb.com/docs/manual/reference/parameters/)
- [MongoDB Manual — getParameter command](https://www.mongodb.com/docs/manual/reference/command/getParameter/)
- [MongoDB Manual — setParameter command](https://www.mongodb.com/docs/manual/reference/command/setParameter/)
- [MongoDB Manual — External Configuration Values](https://www.mongodb.com/docs/manual/core/security-external-config-values/)
- [MongoDB Manual — Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Self-Managed Internal Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/)
- [MongoDB Manual — Deploy a Self-Managed Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Deploy a Self-Managed Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/deploy-shard-cluster/)
- [MongoDB Manual — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Atlas — Configure Additional Settings](https://www.mongodb.com/docs/atlas/cluster-config/)

> **Lưu ý phiên bản:** MongoDB Server, MongoDB Atlas và các orchestration tools có những giới hạn cấu hình khác nhau. Những snippet minh họa ở đây tập trung vào self-managed MongoDB; luôn kiểm tra tài liệu target version, edition, platform và topology trước khi triển khai. Không chạy cấu hình production chỉ vì một YAML ví dụ trông hợp lệ.

---

## 42. Tổng kết

1. **`mongod` và `mongos` có nhiệm vụ khác nhau**: mongod lưu/truy vấn dữ liệu; mongos định tuyến truy vấn trong sharded cluster.
2. MongoDB nhận configuration qua **YAML file, CLI flags và các cơ chế environment/external được hỗ trợ**. Một số CLI settings override file, một số options xung đột và gây startup error.
3. **`getCmdLineOpts`** là công cụ quan trọng để xem parsed startup options; nhưng không thay thế `getParameter`/metrics cho runtime state.
4. Phân biệt **startup-only options** như listener/data path với **runtime-changeable server parameters**; không mọi thay đổi file đều có hiệu lực ngay.
5. **Network, storage, TLS và authorization** phải được xem trong bối cảnh bảo mật. `bindIpAll`, private keys, keyfiles và quyền file cần kiểm soát nghiêm.
6. **Replica set** cần `replSetName` đúng, internal authentication, hostname/certificate phù hợp và rolling changes giữ quorum.
7. **Sharded cluster** cần tách rõ config server mongod, shard mongod và mongos `sharding.configDB`. Không copy một file config cho mọi vai trò.
8. **systemd/Windows/container/Operator** khác nhau trong cách start và lưu desired state. Sửa nhầm file hoặc dùng sai `fork` có thể khiến service không khởi động.
9. **Upgrade** cần kiểm tra removed/deprecated options, binary version và FCV. Không coi config cũ luôn tương thích.
10. **Vận hành an toàn phải có baseline → review → staging → rollout → verify → rollback**, thay vì thay YAML rồi hy vọng mọi node sẽ tự hoạt động đúng.

**Kết luận:** Quản lý cấu hình MongoDB tốt là bảo đảm **đúng process, đúng phiên bản, đúng source of truth, đúng phạm vi tác động và có đường phục hồi**. Một dòng cấu hình chỉ thực sự “đúng” khi phiên bản hỗ trợ nó, process đã nạp hiệu quả, cluster vẫn khỏe, quyền truy cập được bảo vệ và ứng dụng vận hành theo mục tiêu.
