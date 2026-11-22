# mongodump, mongorestore và điều kiện tương thích công cụ trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Sao lưu và phục hồi

## 1. Vì sao phải hiểu cả công cụ lẫn phiên bản trước khi khôi phục?

Một hệ thống đặt hàng dùng MongoDB gặp sự cố: nhân viên vô tình xóa một collection, dữ liệu từ bản triển khai mới ghi sai, hoặc cần tạo một môi trường staging chứa bản sao dữ liệu production đã được xử lý theo chính sách bảo mật. Nhóm vận hành có một file `backup.archive.gz` tạo bằng `mongodump` và dự định chạy `mongorestore`.

Những câu hỏi phải trả lời **trước** khi chạy lệnh là:

1. Backup là bản sao **logical** hay snapshot vật lý? Có nhất quán trong lúc ghi dữ liệu không?
2. File backup được tạo bằng **MongoDB Database Tools phiên bản nào**?
3. MongoDB Server ở nguồn và đích chạy phiên bản nào, với **Feature Compatibility Version (FCV)** nào?
4. Backup là toàn bộ deployment, một database hay một collection? Có `oplog.bson` không?
5. Nguồn là standalone, replica set hay sharded cluster?
6. File archive được tạo có `--gzip` không? Đích có cùng kiểu metadata/index được hỗ trợ không?
7. Khôi phục có cần **xóa collection hiện có bằng `--drop`** hay phải bảo toàn dữ liệu?
8. User được cấp quyền `backup`/`restore` phù hợp chưa? Kết nối có TLS không?
9. Có backup checksum, kiểm tra readback, xác minh dữ liệu và quy trình rollback không?
10. Mục tiêu thực sự là khôi phục data sau sự cố, di chuyển data hay **nâng cấp major version**? Ba mục tiêu cần các quy trình khác nhau.

Công cụ hoạt động theo hướng:

```text
          MongoDB nguồn
                │
          mongodump
                │
     ┌──────────┴───────────┐
     │                      │
BSON + metadata         archive
theo thư mục            (có thể gzip)
     │                      │
     └──────────┬───────────┘
                │
      bảo quản/kiểm tra
       checksum/retention
                │
          mongorestore
                │
          MongoDB đích
                │
       xác minh count/index/
     query/role/application
```

**Điểm chính:** `mongodump` và `mongorestore` là công cụ **logical backup/restore**, không tự động trở thành giải pháp full disaster recovery, physical snapshot, point-in-time recovery hay upgrade MongoDB Server.

Bài này sẽ xây dựng tư duy và quy trình an toàn cho các thao tác backup/restore, đi kèm ví dụ thực hành `mongosh`, câu lệnh shell và workflow từ ứng dụng Java.

---

## 2. MongoDB Database Tools là gì?

**MongoDB Database Tools** là bộ chương trình dòng lệnh được cung cấp riêng, bao gồm:

- `mongodump`: xuất dữ liệu MongoDB dưới dạng BSON và metadata phục vụ khôi phục.
- `mongorestore`: nạp lại dữ liệu từ BSON dump, archive hoặc standard input.
- `bsondump`: đọc/chuyển dữ liệu BSON để kiểm tra ở dạng văn bản.
- `mongoexport` / `mongoimport`: xuất/nhập dữ liệu ở dạng JSON hoặc CSV theo mục đích trao đổi dữ liệu.
- `mongostat`, `mongotop`: quan sát thống kê vận hành.

Từ MongoDB 4.4, Database Tools được **phát hành độc lập với MongoDB Server**, theo nhánh phiên bản `100.x`; công cụ không nhất thiết có cùng số phiên bản với server.

Ví dụ minh họa:

```text
MongoDB Server:        8.0.x
MongoDB Database Tools: 100.x.y
mongosh:                2.x
Java Sync Driver:       5.x
```

Bốn nhóm phiên bản này **không phải cùng một sản phẩm**. Chúng có ma trận tương thích và lịch phát hành riêng.

### 2.1. Kiểm tra phiên bản đang dùng

Trong terminal của máy cài Database Tools:

```bash
mongodump --version
mongorestore --version
bsondump --version
```

Trong `mongosh` kết nối MongoDB Server:

```javascript
db.version();

db.adminCommand({ buildInfo: 1 });
```

Để xem FCV nếu tài khoản có quyền:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

**Không so `mongodump 100.20.1` với `MongoDB Server 9.0` rồi kết luận chúng không tương thích vì số không giống nhau.** Phải xem bảng Server Compatibility của đúng Database Tools release.

### 2.2. Tải và cài đặt

Cài MongoDB Database Tools từ package hoặc bản phát hành dành cho hệ điều hành/kiến trúc của bạn theo trang chính thức:

- <https://www.mongodb.com/docs/database-tools/installation/>
- <https://www.mongodb.com/try/download/database-tools>

Bản cài MongoDB Server hoặc `mongosh` **không bảo đảm** đã có đủ Database Tools ở mọi hệ thống. Kiểm tra `mongodump --version` thay vì chỉ kiểm tra `mongod --version`.

### 2.3. Tài liệu theo phiên bản

Công cụ có thể được bổ sung option, thay đổi hành vi hoặc bỏ hỗ trợ trong từng bản. Đối với lệnh chạy trên production:

1. Ghi lại phiên bản chính xác của `mongodump`.
2. Ghi lại phiên bản chính xác của `mongorestore`.
3. Đọc documentation/release notes của bản đó.
4. Chạy thử trên isolated restore target.
5. Ghi phiên bản vào backup manifest.

Không thiết kế automation mặc định theo tài liệu của một bản mới hơn trong khi host đang dùng binary cũ.

---

## 3. Logical backup khác physical backup như thế nào?

### 3.1. Logical backup

`mongodump` truy xuất dữ liệu từ MongoDB và ghi:

- BSON documents.
- Metadata của collection.
- Định nghĩa index và các collection options được hỗ trợ.
- Thông tin users/roles khi dump theo phạm vi và options phù hợp.
- Oplog entries nếu đủ điều kiện sử dụng `--oplog`.

Lợi ích:

- Có thể chọn database/collection/namespace.
- Dễ dùng để clone một phần dữ liệu sang lab.
- Khá độc lập với bố cục file storage engine bên dưới.
- Hỗ trợ archive và gzip.

Giới hạn:

- Có thể tạo tải CPU/I/O/network đáng kể trên source.
- Restore cần xử lý BSON, dựng collections/indexes và thực hiện writes.
- Mất thời gian lớn với dữ liệu hàng TB.
- Không mặc định là một snapshot nhất quán khi dữ liệu đang thay đổi.
- Không phải bản sao toàn bộ cấu hình hệ điều hành, secrets, network policy hoặc cluster topology.

### 3.2. Physical backup/snapshot

Một physical snapshot thường sao chép trạng thái các file/volumes theo cơ chế nhất quán của storage engine/backup service.

Lợi ích có thể gồm:

- Restore data lớn nhanh hơn trong một số workload.
- Phù hợp khi backup engine quản lý transaction/storage consistency đúng cách.
- Có thể tích hợp point-in-time recovery hoặc incremental backup.

Đánh đổi: phụ thuộc công nghệ snapshot, topology, filesystem, journal, encryption và quy trình recovery được hỗ trợ.

**Không tự chụp một thư mục WiredTiger đang chạy bằng lệnh copy file thông thường rồi coi đó là backup hợp lệ.** Sử dụng hướng dẫn và công cụ snapshot/backup được MongoDB hỗ trợ.

### 3.3. Mục tiêu quyết định công cụ

| Mục đích | Công cụ/chiến lược cần xem xét |
|---|---|
| Clone một database nhỏ sang lab | `mongodump` + `mongorestore` |
| Backup một collection để thử migration | Partial logical dump |
| Restore nhất quán một replica set còn ghi liên tục | Full dump + `--oplog`/`--oplogReplay` nếu điều kiện thỏa |
| Backup sharded cluster có ghi liên tục | Quy trình cluster-aware hoặc managed backup; không chỉ một `--oplog` |
| RPO tính bằng phút/giây | PITR/continuous backup phù hợp |
| Restore hàng chục TB trong RTO thấp | Đánh giá snapshot/managed backup |
| Upgrade major MongoDB Server | Quy trình upgrade được hỗ trợ; không mặc định dump/restore là đường upgrade |
| Data interchange CSV/JSON | `mongoexport`/`mongoimport` nếu phù hợp, không thay thế backup BSON |

---

## 4. Định dạng đầu ra của mongodump

### 4.1. Dump dạng thư mục

Một lệnh cơ bản trong lab:

```bash
mongodump --host 127.0.0.1 --port 27017 --db inventory_lab --out ./backups/inventory-001
```

Cấu trúc thường thấy:

```text
backups/
└── inventory-001/
    └── inventory_lab/
        ├── products.bson
        ├── products.metadata.json
        ├── orders.bson
        ├── orders.metadata.json
        └── ...
```

- `products.bson` chứa documents BSON.
- `products.metadata.json` chứa metadata cần cho việc dựng lại collection/index theo khả năng hỗ trợ.
- Các file metadata không phải một bản JSON export của toàn bộ document.

Cấu trúc và nội dung cụ thể có thể khác theo collection type, namespace hoặc phiên bản công cụ.

### 4.2. Dump dạng archive

```bash
mongodump --host 127.0.0.1 --port 27017 --db inventory_lab --archive=./backups/inventory.archive
```

Archive gói dump thành một file tiện di chuyển/lưu trữ. Nó **không tự là tar hoặc zip**; `mongorestore --archive` hiểu format archive do `mongodump` tạo.

Không dùng:

```text
unzip inventory.archive
```

và mong đợi nhận được BSON files theo định dạng ZIP.

### 4.3. Nén bằng gzip

Đối với archive:

```bash
mongodump --host 127.0.0.1 --db inventory_lab --archive=./backups/inventory.archive.gz --gzip
```

Khôi phục tương ứng:

```bash
mongorestore --host 127.0.0.1 --archive=./backups/inventory.archive.gz --gzip
```

Đối với directory dump:

```bash
mongodump --host 127.0.0.1 --db inventory_lab --out ./backups/inventory-gz --gzip
```

Khôi phục:

```bash
mongorestore --host 127.0.0.1 --gzip ./backups/inventory-gz
```

**Cần dùng `--gzip` khi đầu vào thực sự được tạo với `--gzip`.** Đổi đuôi tên file thành `.gz` không biến file thành gzip.

### 4.4. Không kết hợp sai output flags

Với `mongodump`, không kết hợp `--archive=<file>` và `--out=<directory>` trong cùng một lệnh.

Chọn **một định dạng** cho từng job backup, ghi rõ trong manifest và dùng cặp tham số tương ứng lúc restore.

### 4.5. Archive qua stdin/stdout

MongoDB hỗ trợ:

```bash
mongodump --archive | mongorestore --archive
```

nhưng đây là chuyển dữ liệu trực tiếp giữa hai tiến trình, **không tạo một bản backup lưu trữ lâu dài** nếu không đồng thời ghi và bảo quản archive.

Cảnh báo:

- Trong các shell xử lý pipeline như luồng text thay vì byte stream, binary archive có thể bị biến đổi.
- Đặc biệt tránh tự sử dụng pipeline nhị phân kiểu này trong **Windows PowerShell 5.1** khi chưa có cơ chế binary-safe được kiểm chứng.
- Đường pipe có thể đứt, cần kiểm tra exit code của cả hai process.
- Nếu cần audit/retention, ưu tiên ghi file archive, checksum rồi restore từ file.

---

## 5. Mongodump: các lựa chọn phạm vi

### 5.1. Dump toàn bộ instance được kết nối

```bash
mongodump --host 127.0.0.1 --port 27017 --out ./backups/instance-001
```

Phạm vi và collection hệ thống mà công cụ xuất được phụ thuộc quyền, MongoDB topology và options. Không hiểu “full dump” là bản snapshot toàn bộ cấu hình mạng, keyfiles, certificates, storage engine hay hệ điều hành.

### 5.2. Dump một database

```bash
mongodump --host 127.0.0.1 --db inventory_lab --out ./backups/inventory-001
```

Phù hợp để clone/backup một database trong lab hoặc khi application có quy trình ngừng ghi/đồng bộ phù hợp.

### 5.3. Dump một collection

```bash
mongodump --host 127.0.0.1 --db inventory_lab --collection products --out ./backups/products-001
```

Nếu collection tham chiếu các collection khác, chỉ lưu một collection có thể không đủ để khôi phục nghiệp vụ.

Ví dụ:

```text
orders.customerId → customers._id
orders.items[].sku → products.sku
```

Chỉ dump `orders` có thể khiến dữ liệu khôi phục thiếu các records liên quan.

### 5.4. Filter bằng query

Với phiên bản hỗ trợ:

```bash
mongodump --host 127.0.0.1 --db inventory_lab --collection orders --query='{"status":"CLOSED"}' --out ./backups/closed-orders
```

Quy tắc:

- `--query` dùng với collection cụ thể.
- Query phải là JSON hợp lệ theo yêu cầu công cụ.
- Trên Windows shell, quy tắc quoting khác Bash; có thể dùng `--queryFile` để tránh lỗi escaping.
- Partial dump không tự bảo toàn quan hệ tham chiếu hoặc consistency giữa các collection.

**Không xem selective query dump là bản backup đầy đủ của toàn database.**

### 5.5. Giới hạn quyền và độ nhạy cảm dữ liệu

Một dump có thể chứa:

- Thông tin khách hàng.
- Dữ liệu tài chính/nghiệp vụ.
- PII.
- Tokens hoặc secrets ứng dụng nếu chúng được lưu trong MongoDB.
- User/role metadata trong một số phạm vi backup.

Do đó backup phải được mã hóa ở nơi lưu trữ, kiểm soát truy cập, audit, có retention và xử lý xóa khi hết hạn.

`--gzip` chỉ là **nén**, không phải **mã hóa**.

---

## 6. Kết nối có authentication và TLS

### 6.1. SCRAM và authentication database

Một user có role `backup` được tạo trong `admin` có thể được sử dụng qua Database Tools:

```bash
mongodump \
  --host mongo1.example.internal \
  --port 27017 \
  --username backup_operator \
  --authenticationDatabase admin \
  --password \
  --db inventory_lab \
  --archive=./backups/inventory.archive.gz \
  --gzip
```

Tham số `--password` không kèm secret được dùng để yêu cầu nhập password tương tác ở những phiên bản công cụ hỗ trợ. Trên automation production, ưu tiên `--config` có permission chặt hoặc secret injection phù hợp thay vì password lộ trong process arguments.

Nếu user được tạo trong `admin` nhưng dump database `inventory_lab`:

```text
--authenticationDatabase admin
--db inventory_lab
```

đó là cấu hình hợp lý. **Authentication database không nhất thiết trùng database được dump.**

### 6.2. Connection URI

```bash
mongodump \
  --uri="mongodb://mongo1.example.internal:27017/?authSource=admin&tls=true" \
  --username backup_operator \
  --password \
  --archive=./backups/full.archive.gz \
  --gzip
```

Tránh đưa password trực tiếp vào URI hay vào command line. Nếu có URI chứa user/password, cần URL-encode ký tự đặc biệt đúng cách và kiểm soát khả năng lộ qua shell history/process listing.

Đừng trộn URI và flags có giá trị mâu thuẫn cho `authSource`, `host`, `TLS`, `username`; công cụ có thể báo lỗi thay vì tự chọn một giá trị.

### 6.3. TLS và CA

Một công cụ có thể dùng connection string `tls=true` hoặc những TLS options tương ứng của release, kèm CA file nếu cần.

Ví dụ minh họa:

```bash
mongodump \
  --host mongo1.example.internal \
  --port 27017 \
  --ssl \
  --sslCAFile /secure/certs/root-ca.pem \
  --username backup_operator \
  --authenticationDatabase admin \
  --password \
  --db inventory_lab \
  --archive=./backups/inventory.archive.gz
```

Tên các TLS flags có thể có phiên bản/alias khác nhau. Kiểm tra `mongodump --help` đúng binary đang dùng.

**Không dùng `--sslAllowInvalidCertificates` hoặc cơ chế bỏ hostname verification trên production chỉ để chạy backup cho xong.** Thay vào đó sửa CA trust, certificate chain hoặc DNS/SAN.

### 6.4. Config file chứa secret

Một số Database Tools phiên bản mới hỗ trợ `--config=<yaml>` để truyền options nhạy cảm như password hoặc URI, nhằm tránh lộ trong process command line.

Ví dụ **cấu trúc minh họa, không ghi secret thật**:

```yaml
uri: mongodb://mongo1.example.internal:27017/?authSource=admin&tls=true
password: REPLACE_BY_SECRET_IN_SECURE_ENVIRONMENT
```

Dùng permission chỉ cho backup service account, xóa theo chính sách, và không commit file vào repository.

Với Windows, cần áp dụng ACL; với Linux/Unix, đặt owner và mode phù hợp. Đừng coi file YAML có password là an toàn chỉ vì nó nằm ngoài URI.

### 6.5. Roles cho backup và restore

MongoDB có các built-in roles như:

- `backup`: quyền đọc cần thiết cho backup trên phạm vi phù hợp.
- `restore`: quyền phục hồi trên phạm vi phù hợp.

Nhưng một workflow cụ thể có thể cần quyền bổ sung:

- Đọc user/role metadata.
- Khôi phục indexes và collection options.
- Tạo/drop collections.
- Replay oplog.
- Thao tác với hệ thống hoặc namespaces đặc biệt.

Thực tế phải đối chiếu **required access** của `mongodump` và `mongorestore` theo phạm vi job.

Không mặc định cấp `root` cho automation. Tách account backup-only và restore-only, kiểm tra khả năng thực hiện job trong lab.

---

## 7. Mongorestore: hiểu đúng hành vi trước khi chạy

`mongorestore` đọc BSON dump/metadata/archive và ghi vào deployment đích.

### 7.1. Restore directory dump

Giả sử `./backups/inventory-001` có thư mục con `inventory_lab`:

```bash
mongorestore --host 127.0.0.1 ./backups/inventory-001
```

Nếu database/collection đích chưa tồn tại, công cụ tạo các namespace cần thiết trong phạm vi hỗ trợ.

### 7.2. Restore archive

```bash
mongorestore --host 127.0.0.1 --archive=./backups/inventory.archive
```

Nếu file được gzip:

```bash
mongorestore --host 127.0.0.1 --archive=./backups/inventory.archive.gz --gzip
```

### 7.3. Restore không có --drop

Mặc định, `mongorestore` **không xóa trước collection đích** chỉ vì bạn có backup.

Nếu collection đã chứa documents trùng `_id`:

- Có thể phát sinh duplicate key errors.
- Có thể có documents được insert và documents khác thất bại.
- Kết quả không phải một thao tác “replace toàn bộ database” mặc định.
- Không nên kỳ vọng tool tự merge/update theo business key.

Với các version hiện hành, `mongorestore` mặc định có thể **tiếp tục** sau duplicate key hoặc document validation errors. Muốn dừng khi gặp những lỗi đó, cân nhắc `--stopOnError`.

### 7.4. Restore với --drop

```bash
mongorestore --host 127.0.0.1 --drop ./backups/inventory-001
```

`--drop` có nghĩa: **trước khi restore collection có trong dump, xóa collection tương ứng trên đích**.

Điểm cần hiểu:

- Dữ liệu đang có ở collection đích bị xóa nếu collection thuộc phạm vi restore.
- Các collection **không có trong dump** không tự bị xóa.
- Nó không phải lệnh drop toàn bộ database/cluster.
- Indexes/options được tạo lại theo metadata/khả năng hỗ trợ và các flags.
- Nếu restore thất bại giữa chừng, collection bị drop có thể chỉ được khôi phục một phần.

**Không chạy `--drop` trên production khi chưa có kế hoạch và xác nhận rõ namespace đích.**

### 7.5. Cảnh báo đặc biệt khi restore admin

Khi restore bao gồm database `admin` và dùng `--drop`, quá trình có thể thay thế user credentials và roles đang tồn tại. Điều này có thể khiến tài khoản dùng để restore **mất quyền hoặc không còn xác thực được** giữa quá trình.

Đây là một thao tác nhạy cảm, cần runbook riêng:

- Xác định user/role nằm trong backup.
- Đảm bảo phương án tiếp tục xác thực sau khi drop/recreate.
- Thử trên environment cô lập.
- Có đường recovery theo quy trình bảo mật.
- Không đơn giản chạy `mongorestore --drop` cho toàn deployment bất kỳ.

### 7.6. --stopOnError

```bash
mongorestore --host 127.0.0.1 --stopOnError ./backups/inventory-001
```

Flag này buộc restore dừng khi gặp những lỗi insert/validation được công cụ xử lý theo quy tắc của nó, thay vì tiếp tục và để lại một số records không thành công.

Lưu ý: `--stopOnError` không biến toàn bộ restore thành **transaction atomic**. Khi đã ghi thành công một phần trước lúc lỗi, dữ liệu đó có thể vẫn tồn tại.

### 7.7. --dryRun

Với Database Tools version hỗ trợ:

```bash
mongorestore --host 127.0.0.1 --dryRun --verbose ./backups/inventory-001
```

`--dryRun` giúp xem kế hoạch/tóm tắt restore mà **không thực sự import data**. Nó hữu ích trước thao tác chính, nhưng không chứng minh:

- File BSON hoàn toàn hợp lệ.
- Tất cả indexes sẽ build được.
- Đích có đủ disk/RAM.
- Validation/permissions sẽ cho phép mọi document.
- Restore sẽ không gặp lỗi runtime.

**Dry-run không thay thế khôi phục thử thật vào target cô lập.**

---

## 8. Namespace: restore chọn lọc và đổi tên database

### 8.1. Namespace là gì?

Một namespace thường có dạng:

```text
<database>.<collection>
```

Ví dụ:

```text
inventory_lab.products
inventory_lab.orders
commerce.customers
```

Trong restore từ directory/archive, nên dùng các options:

- `--nsInclude`: chỉ restore namespaces phù hợp.
- `--nsExclude`: bỏ qua namespace.
- `--nsFrom`/`--nsTo`: đổi tên namespaces lúc restore.

Các flags `--db` và `--collection` khi restore từ directory/archive đã được tài liệu Database Tools ghi là **deprecated** trong ngữ cảnh này; chúng còn có các use cases khi restore từ BSON file đơn.

### 8.2. Restore một collection

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsInclude="inventory_lab.products"
```

Chỉ collection `inventory_lab.products` được chọn theo namespace pattern. Không cần tách file archive bằng tay.

### 8.3. Restore một database

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/instance.archive.gz \
  --gzip \
  --nsInclude="inventory_lab.*"
```

Pattern wildcard cho phép chọn các collections trong database.

### 8.4. Restore sang database mới

Một cách an toàn để kiểm tra backup là khôi phục vào database staging:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsFrom="inventory_lab.*" \
  --nsTo="inventory_restore_test.*" \
  --stopOnError
```

Ví dụ này map:

```text
inventory_lab.products
    ↓
inventory_restore_test.products

inventory_lab.orders
    ↓
inventory_restore_test.orders
```

**Không dùng cùng tên namespace nếu định bảo toàn database nguồn đang chạy.**

### 8.5. Restore một collection sang tên khác

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsInclude="inventory_lab.products" \
  --nsFrom="inventory_lab.products" \
  --nsTo="inventory_restore_test.products_copy"
```

Tùy bản dump và quy tắc namespace, kiểm tra dry-run/restore thử để xác nhận mapping đúng.

### 8.6. Thứ tự include/exclude

Nếu dùng cả:

```text
--nsInclude="inventory_lab.*"
--nsExclude="inventory_lab.sensitive"
```

thì pattern `--nsExclude` có quyền loại trừ namespace phù hợp, kể cả khi `--nsInclude` cũng khớp.

### 8.7. Cẩn thận shell wildcard

Trong Bash và PowerShell, các dấu `*` và `$` có thể có ý nghĩa cho shell. Hãy quote namespace patterns theo shell thích hợp.

Trên Bash:

```bash
--nsInclude='inventory_lab.*'
```

Trên PowerShell, dùng quoting phù hợp; không để shell tự expand wildcard thành tên file.

---

## 9. Backup nhất quán khi MongoDB có ghi: vấn đề snapshot

### 9.1. Vì sao một dump đơn thuần có thể không nhất quán?

Giả sử ứng dụng có hai collection:

```text
orders:    đơn hàng
payments:  trạng thái thanh toán
```

Trong lúc `mongodump` đang đọc `orders`, ứng dụng cập nhật order. Sau đó trong lúc đọc `payments`, ứng dụng ghi payment.

Nếu dump đọc collections ở hai thời điểm khác nhau, bản sao có thể chứa:

- Order ở thời điểm T1.
- Payment ở thời điểm T2.
- Trạng thái không cùng một mốc logic.

Vì vậy dump trong khi có writes **không mặc định là một consistent point-in-time snapshot**.

### 9.2. Các hướng giải quyết

- Ngừng/đóng băng writes trong một cửa sổ có kiểm soát.
- Dùng cơ chế `--oplog` cho full dump của **replica set member** khi điều kiện phù hợp.
- Dùng snapshot/managed backup có consistency guarantee theo topology.
- Với sharded cluster, dùng quy trình backup cluster-aware, không áp dụng máy móc một node dump.

### 9.3. Cần xác định RPO và RTO

- **RPO – Recovery Point Objective:** tối đa mất bao nhiêu dữ liệu tính theo thời gian.
- **RTO – Recovery Time Objective:** cần khôi phục dịch vụ trong bao lâu.

Ví dụ:

```text
Backup nightly 02:00
Sự cố xảy ra 17:30
→ Nếu chỉ có full dump lúc 02:00, RPO thực tế
   có thể gần 15 giờ 30 phút.

Restore 200 GB cần 2 giờ
→ Nếu ứng dụng cần hoạt động trong 15 phút,
   chiến lược này không đáp ứng RTO.
```

Con số chỉ minh họa. Phải đo restore thực nghiệm theo data size, indexes, throughput và hạ tầng đích.

---

## 10. mongodump --oplog trên replica set

MongoDB hỗ trợ:

```bash
mongodump --oplog --out ./backups/rs-full-001
```

khi kết nối tới một **replica set member** và tạo full dump theo các điều kiện hỗ trợ.

Trong quá trình dump, tool lưu những oplog entries cần thiết để có thể replay, giúp bản restore phản ánh một điểm nhất quán trong phạm vi tính năng.

### 10.1. Oplog là gì?

**Oplog** là nhật ký thao tác replication được các thành viên replica set sử dụng để đồng bộ writes.

Trong thư mục backup, `mongodump --oplog` có thể ghi:

```text
backups/
└── rs-full-001/
    ├── admin/
    ├── commerce/
    ├── inventory_lab/
    ├── ...
    └── oplog.bson
```

Nếu dump ra archive, oplog entries được chứa trong archive.

**Oplog của mongodump không phải chỉ đơn giản copy toàn bộ `local.oplog.rs`**; công cụ thu thập các entries phục vụ mục tiêu restore một mốc phù hợp.

### 10.2. Khôi phục với --oplogReplay

```bash
mongorestore \
  --host 127.0.0.1 \
  --oplogReplay \
  ./backups/rs-full-001
```

Với archive:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/rs-full.archive.gz \
  --gzip \
  --oplogReplay
```

**Chỉ dùng các lệnh này trên isolated target được chuẩn bị cho full deployment restore.** Đặc biệt cảnh giác với users/roles và `--drop` khi có `admin` trong dump.

### 10.3. --oplog chỉ dùng cho full dump phù hợp

Theo tài liệu Database Tools hiện hành, `mongodump --oplog` yêu cầu:

- Nguồn là replica set member duy trì oplog.
- **Full dump** của member.

Không kết hợp với các flags giới hạn phạm vi như:

- `--db`.
- `--collection`.
- `--query`.
- `--dumpDbUsersAndRoles`.

Ví dụ **không hợp lệ**:

```bash
mongodump --db commerce --oplog --out ./backups/invalid
```

Không suy ra rằng `--oplog` sẽ tự đảm bảo consistency cho một selective collection dump.

### 10.4. Mongorestore --oplogReplay cũng có giới hạn phạm vi

Với full replica set dump có oplog, không kết hợp `--oplogReplay` với các flags giới hạn/remap namespace như:

- `--nsInclude`.
- `--nsExclude`.
- `--nsFrom`.
- `--nsTo`.
- `--db`.
- `--collection`.

Điều này đặc biệt quan trọng vì nhiều người muốn **full dump + oplogReplay + rename database**. Đây **không phải** workflow được hỗ trợ bằng cách cộng mọi option trong một lệnh.

Nếu mục tiêu chỉ là clone một database sang tên khác, nên tạo backup chọn lọc trong maintenance window phù hợp hoặc theo phương án snapshot/consistency riêng, rồi restore với namespace mapping.

### 10.5. Có oplog vẫn có những giới hạn

`mongodump --oplog` không thể xử lý mọi loại thay đổi đồng thời.

Các thao tác như:

- `renameCollection`.
- Aggregation với `$out`.
- Một số thao tác sửa users/roles/privileges.
- Một số thay đổi settings cluster-wide.

có thể khiến full dump với oplog thất bại theo tài liệu.

Oplog window phải đủ dài để bao phủ thao tác dump, và nguồn phải đủ tài nguyên. Nếu bị mất oplog entries cần thiết hoặc có thay đổi không hỗ trợ, job không đáp ứng mục tiêu backup nhất quán.

### 10.6. Oplog replay không phải PITR tùy ý

`mongorestore` có `--oplogLimit` cho những tình huống cụ thể, nhưng dùng sai mốc hoặc ép replay các entries không phù hợp có thể gây mất nhất quán hay hỏng dữ liệu.

Không xem `--oplogReplay` là giải pháp continuous point-in-time recovery tương đương Atlas PITR/backup service.

### 10.7. Cảnh báo tương thích liên quan time series và FCV

Ở MongoDB Server 9.0, việc thay đổi FCV giữa 8.x và 9.0 có thể dẫn tới **time-series bucket format conversion**.

Tài liệu MongoDB cảnh báo `mongorestore --oplogReplay` không replay được một oplog range đi qua quá trình chuyển đổi định dạng này. Các Database Tools releases mới đã bổ sung kiểm tra để tránh tạo dump không thể khôi phục trong trường hợp liên quan.

Vì vậy, **không chạy `mongodump --oplog` xuyên qua một FCV transition/format conversion như vậy**. Freeze/coordinate backup và nâng cấp theo runbook version-specific.

---

## 11. Standalone, replica set và sharded cluster: chọn đúng quy trình

| Nguồn | mongodump thông thường | --oplog | Điều cần chú ý |
|---|---|---|---|
| Standalone | Có thể dùng | Không, không có oplog replica set | Ngừng ghi hoặc chọn consistency strategy khác |
| Replica set member | Có | Hỗ trợ full dump theo điều kiện | Kiểm tra oplog window/DDL/FCV |
| Replica set qua seed list | Có | Cần kết nối phù hợp tới member có oplog | Hiểu read preference và topology |
| Sharded cluster qua mongos | Có các workflow dump theo tài liệu | Không có cluster-consistent `--oplog` qua mongos | Coordination/balancer/writes/metadata |
| Atlas managed deployment | Dùng được trong phạm vi dịch vụ cho phép | Phụ thuộc topology và đường kết nối | Cân nhắc Atlas Backup/PITR |

### 11.1. Có nên dump từ secondary?

Dump từ secondary có thể giảm một phần đọc trên primary, nhưng:

- Secondary vẫn chịu CPU/I/O/disk/network load.
- Read consistency/replication lag cần được hiểu.
- Backup có thể là trạng thái chậm hơn primary.
- Dữ liệu cần trong oplog phải còn tồn tại.
- Topology failover có thể ảnh hưởng session.

Đừng mặc định “secondary không phục vụ user nên có thể dump không giới hạn”. Cần capacity plan và monitoring.

### 11.2. Sharded cluster: bẫy của mongos --oplog

Tài liệu MongoDB nêu rõ `--oplog` **không mang lại lợi ích nhất quán toàn cluster khi dump qua `mongos`**, và không dùng nó như cách backup toàn sharded cluster.

Vì sao?

- Các shards có oplog/transaction histories riêng.
- Chunks có thể di chuyển.
- Metadata cấu hình sharding có thể thay đổi.
- Writes liên quan nhiều shards cần một điểm nhất quán giữa các thành phần.

Một tập dump của từng shard **không tự** là snapshot phối hợp toàn cluster.

### 11.3. Quy trình cần cluster-awareness

Với self-managed sharded cluster, phải đọc đúng tài liệu:

- Back Up a Self-Managed Sharded Cluster with a Database Dump.
- Quy trình liên quan balancer, writes, snapshot windows và metadata.
- Thứ tự thao tác, trạng thái cluster, quyền backup và kiểm tra restore.

Nếu không chắc chắn, chọn managed backup/backup solution có hỗ trợ cluster consistency thay vì tự viết vài lệnh shell chạy song song trên shards.

### 11.4. Atlas Backup và mongodump

Atlas có những dịch vụ snapshot/continuous backup theo tier và tính năng. Với mục tiêu DR hoặc RPO thấp, ưu tiên kiểm tra khả năng Atlas Backup/PITR được hỗ trợ trong plan của cluster.

Dùng mongodump để xuất một collection hay seed môi trường có thể phù hợp, nhưng không mặc định đó là chiến lược DR tối ưu cho Atlas production.

---

## 12. Tương thích công cụ: ba chiều cần kiểm tra

Đây là phần trọng tâm của bài.

### 12.1. Chiều 1: Database Tools và MongoDB Server

Mỗi release Database Tools liệt kê server versions được hỗ trợ. Ví dụ, tài liệu Database Tools `100.20.1` liệt kê hỗ trợ các MongoDB Server releases từ `4.2` tới các releases mới hơn như `8.x` và `9.0` theo danh sách cụ thể.

Điều đó **không** cho phép suy ra:

- Mọi Database Tools `100.x` đều kết nối được mọi MongoDB Server.
- Một phiên bản tool có thể kết nối được thì mọi thao tác restore đều tương thích.
- Tool version mới hơn luôn hỗ trợ restore metadata từ server source mới sang destination rất cũ.
- Dùng tool v100 không cần kiểm tra server feature/FCV.

**Bước bắt buộc:** xem bảng tương thích của **đúng binary tool** đang chạy.

### 12.2. Chiều 2: Server nguồn và server đích

Tài liệu `mongodump/mongorestore` nhấn mạnh việc restore đầy đủ cần tương thích **major version** hoặc **Feature Compatibility Version (FCV)** giữa nguồn và đích.

Lý do:

- BSON document representation có thể dùng features theo server version.
- Index options và collection metadata có thể thay đổi.
- UUID, validator, time-series collection options có thể thay đổi.
- Oplog entries có semantics/version constraints.
- Features mới có thể không được server cũ chấp nhận.

**An toàn nhất:** khôi phục thử vào server cùng major version và FCV tương ứng với nguồn, rồi áp quy trình upgrade chính thức nếu cần lên version mới.

### 12.3. Chiều 3: mongodump và mongorestore

MongoDB docs khuyến nghị sử dụng **cùng Database Tools version cho hai bước**.

Ví dụ:

```text
mongodump:    100.20.1
mongorestore: 100.20.1
```

Dùng một bản cũ để dump và bản mới để restore có thể hoạt động trên nhiều dữ liệu, nhưng nếu dump/archive format hoặc metadata handling thay đổi, quá trình có thể fail hoặc nạp dữ liệu không đúng.

Do đó nên lưu binary version trong backup manifest cùng archive.

### 12.4. Phân biệt BSON data với metadata/archive/oplog

Đây là khác biệt rất quan trọng.

Tài liệu MongoDB phân biệt:

- **BSON data files** có thể có một số khả năng khôi phục từ source cũ sang server mới.
- **Metadata, archive và oplog replay files** không có cùng guarantee cross-version.

Chẳng hạn, việc restore BSON documents vào deployment mới hơn **không phải con đường được khuyến nghị để nâng cấp MongoDB**, và không bảo đảm định nghĩa index, collection options, user metadata hoặc oplog có thể chuyển đổi an toàn tương tự.

**Không suy luận từ “documents insert thành công” thành “backup/restore production hoàn toàn tương thích”.**

### 12.5. Version matrix tham khảo

| Tình huống | Đánh giá |
|---|---|
| Dump/restore bằng cùng Database Tools version, server nguồn/đích cùng version/FCV | Phương án tương thích rõ ràng nhất |
| Source Server cũ, target Server mới | Cần kiểm tra upgrade path, metadata/index features và docs; không coi dump/restore là upgrade chuẩn |
| Source Server mới, target Server cũ | Rủi ro tính năng, BSON, metadata, index không hỗ trợ; không mặc định hợp lệ |
| Cùng Server versions nhưng dump/restore tools khác version | Có thể xảy ra format mismatch; ưu tiên cùng tools version |
| Đem archive từ một major/FCV khác sang target | Không có guarantee tương tự BSON-only restore |
| Replay oplog qua FCV/time-series format conversion | Có thể không được hỗ trợ và thất bại |
| Target là sharded cluster, dump có standalone/replica oplog | Không tự dùng `--oplogReplay` qua mongos |
| Source collection có features mới, target thiếu support | Restore có thể thất bại khi tạo metadata/index/collection |

### 12.6. FCV không phải server binary version

Giả sử:

```text
Server binary: 9.0
FCV:           8.0
```

nếu một quá trình nâng cấp đang ở giai đoạn tương thích.

FCV kiểm soát một số khả năng/định dạng liên quan compatibility, nhưng nó không biến một server 9.0 thành server 8.0 ở mọi khía cạnh. **Không chỉ nhìn FCV rồi bỏ qua server binary, tool version và feature usage.**

### 12.7. Ghi version vào manifest

Ví dụ:

```yaml
backupId: 2026-11-14T02-00Z-inventory
source:
  topology: replicaSet
  serverVersion: "example-server-version"
  featureCompatibilityVersion: "example-fcv"
tools:
  mongodump: "100.x.y"
  plannedMongorestore: "100.x.y"
format:
  kind: archive
  gzip: true
  includeOplog: false
scope:
  databases:
    - inventory_lab
file:
  path: inventory.archive.gz
  sha256: "FILL_WITH_REAL_CHECKSUM"
createdAt: "2026-11-14T02:00:00Z"
```

Metadata này phục vụ quản trị backup và compatibility, không cần đặt bên trong BSON archive. Giữ manifest cùng backup, có kiểm soát tính toàn vẹn.

---

## 13. Kiểu dữ liệu và collection metadata khi restore

### 13.1. BSON giữ nhiều loại dữ liệu mà JSON/CSV có thể mất

MongoDB BSON hỗ trợ các kiểu như:

- ObjectId.
- BSON Date.
- Decimal128.
- Binary.
- Timestamp.
- Arrays/embedded documents.
- GeoJSON objects và nhiều dạng dữ liệu ứng dụng.

Logical BSON dump phù hợp cho backup/restore MongoDB hơn việc dùng CSV như bản sao dữ liệu tổng quát.

### 13.2. Vì sao mongoexport/mongoimport không thay cho mongodump?

`mongoexport` chuyển dữ liệu sang JSON/CSV phục vụ trao đổi. Ngược lại, `mongodump` ghi BSON và metadata phục vụ khôi phục.

Dùng export/import có thể:

- Mất hoặc phải ánh xạ lại một số type.
- Không bảo toàn index definitions/collection options.
- Không chứa đầy đủ metadata users/roles.
- Không có cơ chế `--oplog` tương tự cho consistent dump.
- Cần xử lý Extended JSON formats khi round-trip.

Đừng dùng file CSV làm “backup production hoàn chỉnh” chỉ vì nó có cùng số dòng.

### 13.3. Index definitions có thể được tạo lại

Dump directory có thể chứa `collection.metadata.json` với index specs. `mongorestore` thường cố tạo indexes/options được dump khi không dùng các flags bỏ qua chúng.

Các vấn đề có thể xuất hiện:

- Index key/options không được hỗ trợ trên target.
- Unique index build thất bại vì dữ liệu có duplicates.
- Collation/schema restrictions khác.
- Tính năng index deprecated hoặc thay đổi.
- Disk/cache pressure khi build index lớn.
- Chênh lệch index format/feature compatibility.

Đừng chỉ so count; phải kiểm tra `getIndexes()` và query explain sau restore.

### 13.4. Bỏ restore indexes/options có chủ đích

Có các flags:

```text
--noIndexRestore
--noOptionsRestore
```

Chúng có thể hữu ích cho migration lab khi chỉ muốn dữ liệu, nhưng có đánh đổi:

- Bỏ index sẽ thay đổi query performance và constraint.
- Bỏ collection options có thể làm khác validation, collation, capped behavior hay những properties khác.
- Một số collection type đặc biệt không nên được khôi phục khi bỏ metadata.

**Không dùng flags này như “fix mọi lỗi restore” mà không hiểu dữ liệu đích còn tương đương nguồn không.**

### 13.5. Time series collections

Time-series collections có bucket metadata và những ràng buộc version-specific. Khi chuyển server major/FCV, không được mặc định raw BSON và metadata có thể dùng vô điều kiện trên mọi version.

Cẩn trọng đặc biệt:

- `timeField` và `metaField`.
- Bucket granularity/span.
- Index support.
- TTL.
- Oplog replay qua format conversions.
- Metadata/options được target server hỗ trợ.

### 13.6. Views và collection options

Views là định nghĩa query, không phải collection chứa documents như thông thường. Restore phải xét metadata của view và dependencies trên source collections.

Một view có thể bị lỗi nếu:

- Collection nền chưa được restore.
- Aggregation operators không được target version hỗ trợ.
- Collation/namespace mapping khác.
- Quyền của app không phù hợp.

Vì vậy phải kiểm tra cả views và application queries.

### 13.7. TTL sau restore

Nếu backup có collection với TTL index, dữ liệu lịch sử được restore có thể **bị xóa sớm sau khi service TTL hoạt động** nếu đã quá hạn theo chính sách.

Đây có thể là hành vi đúng trên production nhưng không mong muốn ở staging cần kiểm thử dữ liệu lịch sử.

Không vô hiệu hóa TTL trên production mà chưa xét retention/legal requirements; nếu cần lab có retention khác, thiết kế môi trường và indexes riêng, ghi lại chênh lệch.

---

## 14. Users, roles và authentication: phần rất dễ làm hỏng restore

### 14.1. Dump một database không mặc định backup mọi user/role

User có authentication database riêng. Khi dump một database cụ thể, không nên mặc định file dump đã chứa mọi users/roles của toàn cluster.

Database Tools có các options liên quan:

- `--dumpDbUsersAndRoles` khi dump database theo phạm vi hỗ trợ.
- `--restoreDbUsersAndRoles` khi restore từ dump tương ứng.

Điều kiện dùng các options này phụ thuộc phạm vi `--db` và phiên bản công cụ.

### 14.2. Restore admin cần lưu ý users/roles toàn deployment

Nếu backup bao gồm `admin` database, `mongorestore --drop` có thể thay thế user credentials. Nếu tài khoản đang thực hiện restore bị thay thế/mất khả năng xác thực, job có thể dừng giữa chừng.

Trước full restore, cần:

1. Xem phạm vi users/roles trong dump.
2. Xác định account có thể tiếp tục authentication sau khi thay thế.
3. Có rescue/recovery procedure phù hợp.
4. Không chạy thử trực tiếp trên production.
5. Kiểm tra quyền/roles sau restore.

### 14.3. Role backup/restore không mặc định có mọi quyền

Backup operator thường chỉ cần đọc các nguồn được phép và thông tin metadata phù hợp.

Restore operator có thể cần các actions như:

- Create/drop collections.
- Insert documents.
- Build indexes.
- Apply collection options.
- Restore users/roles.
- Apply oplog operations.

Cấp quyền theo **required access** của version công cụ và runbook, không gán root cho service chung một cách mặc định.

### 14.4. AuthSource khác database đang dump

Ví dụ:

```text
--username backup_operator
--authenticationDatabase admin
--db commerce
```

nghĩa là user được xác thực qua `admin` và đọc `commerce` theo quyền được cấp.

Nếu thay `--authenticationDatabase commerce` mà không có user tương ứng, công cụ có thể báo authentication failed dù password đúng cho user ở `admin`.

---

## 15. Performance: chi phí mongodump trên source

### 15.1. Mongodump gây tải như thế nào?

Logical dump yêu cầu đọc dữ liệu, serialize BSON và ghi ra disk/network. Tùy workload:

- CPU tăng do serialization/compression.
- Disk I/O tăng do đọc storage và ghi backup.
- WiredTiger cache bị ảnh hưởng bởi scan.
- Network throughput tăng.
- Secondary lag có thể tăng nếu dump từ secondary.
- Những query user-facing có thể tăng p95/p99 latency.

### 15.2. Compression không miễn phí

`--gzip` giúp giảm dung lượng lưu trữ/truyền dữ liệu khi dữ liệu nén được, nhưng cần CPU.

Nếu storage/network là bottleneck, gzip có thể giúp. Nếu CPU đang bão hòa, gzip có thể kéo dài backup hoặc ảnh hưởng ứng dụng.

### 15.3. Limit parallelism theo tài nguyên

Database Tools có các options điều chỉnh số thao tác song song ở dump/restore tùy version. Không tự tăng concurrency hết mức chỉ vì muốn nhanh hơn.

Một restore ghi quá mạnh có thể:

- Bão hòa disk.
- Tăng replication lag.
- Gây cache pressure.
- Tốn CPU khi build index.
- Làm query application chậm.
- Gây storage quota exceeded.

### 15.4. Có nên dump từ secondary?

Một lựa chọn là dump từ secondary phù hợp để hạn chế tải primary, nhưng cần:

- Kiểm tra lag.
- Bảo đảm read preference/target đúng.
- Theo dõi oplog window.
- Xem tác động tới khả năng failover.
- Đo CPU/I/O và network trên secondary.

Không cho rằng secondary “rảnh” và luôn an toàn để backup dưới tải nặng.

### 15.5. Backup window và SLA

Với một cluster:

```text
Backup size:     200 GB
Read throughput: 100 MB/s hiệu dụng

Thời gian đọc tối thiểu gần đúng:
200000 MB / 100 MB/s = 2000 giây ≈ 33 phút
```

Đây chỉ là ước lượng thô, không gồm index metadata, compression, mạng, filesystem, oplog và tải khác. Dữ liệu thực cần benchmark.

---

## 16. Performance: mongorestore và tốc độ build index

### 16.1. Restore thường nặng hơn việc chép file

Restore có thể phải:

1. Tạo database/collection.
2. Insert BSON documents.
3. Khôi phục collection options.
4. Xây indexes.
5. Apply oplog entries.
6. Đồng bộ writes tới replicas theo write concern.

Quy trình không chỉ là copy archive vào thư mục data của `mongod`.

### 16.2. numParallelCollections

Tùy Database Tools release:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --numParallelCollections=4
```

Số collections đồng thời tăng có thể làm restore nhanh hơn nếu target đủ tài nguyên, nhưng cũng tăng cạnh tranh I/O.

### 16.3. numInsertionWorkersPerCollection

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --numInsertionWorkersPerCollection=2
```

Tăng workers có thể giúp collection lớn, nhưng cần đo latency/replication/disk.

### 16.4. maintainInsertionOrder

Có option:

```text
--maintainInsertionOrder
```

để giữ thứ tự insert từ input, theo giới hạn công cụ. Theo tài liệu, option này cũng có thể bật `--stopOnError` và giới hạn insertion workers cho mỗi collection.

Nó **không đảm bảo ứng dụng sẽ nhận lại cùng thứ tự kết quả khi query không có `sort()`**. BSON collection không có thứ tự nghiệp vụ được bảo đảm chỉ vì restore insert theo thứ tự.

### 16.5. Write concern

Restore là write workload. MongoDB Database Tools có thể nhận `--writeConcern` tùy version:

```bash
mongorestore \
  --host 127.0.0.1 \
  --writeConcern="{w:'majority'}" \
  --archive=./backups/inventory.archive.gz \
  --gzip
```

Write concern tác động tới xác nhận ghi, durability, throughput và RTO. Không giảm write concern một cách mù quáng chỉ để restore nhanh hơn; cân nhắc topology và mục tiêu recovery.

### 16.6. Bulk/duplicate errors

Không có `--drop` và target đã có dữ liệu dễ sinh duplicate `_id`. Chạy `--stopOnError` cho các job cần fail-fast; nhưng vẫn phải xử lý cleanup của dữ liệu đã được ghi trước lúc lỗi.

Muốn idempotent restore, thường tốt hơn dùng target database mới rồi cutover, thay vì chạy lại nhiều lần vào collection đang có dữ liệu.

---

## 17. Backup/restore không phải transaction toàn cluster

Một quan niệm sai:

> “Mình đã dump tất cả databases, nên restore sẽ đưa cluster trở lại đúng một điểm thời gian.”

Chỉ đúng khi backup được tạo với **consistency guarantees thực sự** phù hợp với topology/conditions, và restore được thực hiện đúng cách.

### 17.1. Cross-collection invariants

Ví dụ:

```text
customers.balance = 100
payments:
  payment #1 deducted 20
orders:
  order #1 paid
```

Nếu backup đọc các collections ở các thời điểm khác nhau, invariants có thể lệch. Không nên dùng raw counts để kết luận dữ liệu khôi phục nhất quán về nghiệp vụ.

### 17.2. Multi-document transactions

Một transaction có thể sửa nhiều documents/collections. Bản dump thiếu consistency guarantees có thể không thể hiện đúng một mốc toàn cục của transaction history.

Không dựa vào việc MongoDB hỗ trợ transactions để suy ra mongodump tự giữ snapshot ở mọi kiểu backup.

### 17.3. Sharded transactions

Cross-shard consistency còn phức tạp hơn. Cần backup policy hỗ trợ topology, transaction metadata và trạng thái sharding.

---

## 18. Thực hành lab: tạo dữ liệu MongoDB và dump

Mục tiêu lab: tạo một database nhỏ, backup thành directory/archive, restore sang database khác, kiểm tra count và indexes.

### 18.1. Tạo dữ liệu

Trong `mongosh`, không yêu cầu sửa cấu hình server:

```javascript
const lab = db.getSiblingDB("inventory_lab");

lab.products.insertMany([
  {
    _id: "P-100",
    name: "Bàn phím",
    price: NumberDecimal("299000.00"),
    tags: ["computer", "accessory"],
    createdAt: ISODate("2026-11-14T08:00:00Z")
  },
  {
    _id: "P-101",
    name: "Chuột không dây",
    price: NumberDecimal("199000.00"),
    tags: ["computer", "accessory"],
    createdAt: ISODate("2026-11-14T08:01:00Z")
  },
  {
    _id: "P-102",
    name: "Màn hình",
    price: NumberDecimal("2499000.00"),
    tags: ["display"],
    createdAt: ISODate("2026-11-14T08:02:00Z")
  }
]);

lab.orders.insertMany([
  {
    _id: "O-1",
    productId: "P-100",
    quantity: 2,
    status: "PAID"
  },
  {
    _id: "O-2",
    productId: "P-102",
    quantity: 1,
    status: "NEW"
  }
]);

lab.products.createIndex(
  { name: 1 },
  { name: "idx_product_name" }
);

lab.orders.createIndex(
  { status: 1, productId: 1 },
  { name: "idx_status_product" }
);

printjson({
  productCount: lab.products.countDocuments({}),
  orderCount: lab.orders.countDocuments({})
});
```

Kết quả kỳ vọng:

```text
productCount: 3
orderCount:   2
```

Thực hành chỉ nên chạy trong database lab trống; chạy lại `insertMany` với cùng `_id` sẽ gặp duplicate key.

### 18.2. Directory backup

Trong shell/terminal của máy cài Database Tools:

```bash
mongodump \
  --host 127.0.0.1 \
  --port 27017 \
  --db inventory_lab \
  --out ./backups/inventory-directory
```

Trong môi trường lab localhost không có auth/TLS, câu lệnh đơn giản là đủ. Trên deployment bảo mật phải thêm cấu hình authentication/TLS tương ứng.

### 18.3. Archive backup

```bash
mongodump \
  --host 127.0.0.1 \
  --db inventory_lab \
  --archive=./backups/inventory.archive.gz \
  --gzip
```

Không cần dùng cả directory và archive trong cùng một job; bài lab tạo cả hai chỉ để so sánh.

### 18.4. Lưu ý consistency của lab

Trong lúc dump, **không tạo thêm writes/DDL**. Bài tập này nhỏ và mục tiêu là hiểu thao tác, không phải chứng minh backup nhất quán dưới tải.

---

## 19. Thực hành lab: restore sang database kiểm tra

### 19.1. Restore archive và đổi namespace

Trong terminal:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsFrom="inventory_lab.*" \
  --nsTo="inventory_restore_test.*" \
  --stopOnError
```

Câu lệnh sẽ cố khôi phục:

```text
inventory_lab.products → inventory_restore_test.products
inventory_lab.orders   → inventory_restore_test.orders
```

Chọn namespace đích mới để tránh ghi đè `inventory_lab`.

### 19.2. Kiểm tra dữ liệu

Trong `mongosh`:

```javascript
const original = db.getSiblingDB("inventory_lab");
const restored = db.getSiblingDB("inventory_restore_test");

printjson({
  sourceProducts: original.products.countDocuments({}),
  restoredProducts: restored.products.countDocuments({}),
  sourceOrders: original.orders.countDocuments({}),
  restoredOrders: restored.orders.countDocuments({})
});

printjson(restored.products.getIndexes());
printjson(restored.orders.getIndexes());

printjson(restored.products.findOne({ _id: "P-100" }));
```

Kỳ vọng:

- Products: 3 ở source và restore.
- Orders: 2 ở source và restore.
- Indexes tương ứng được dựng lại nếu metadata/target compatible và không bỏ index restoration.
- Document `P-100` còn kiểu `Decimal128` ở `price` và BSON Date ở `createdAt`.

### 19.3. Kiểm tra types

Trong `mongosh`:

```javascript
const item = db
  .getSiblingDB("inventory_restore_test")
  .products.findOne({ _id: "P-100" });

printjson(item.price);
printjson(item.createdAt);
```

Đừng chỉ so text JSON; hãy kiểm tra BSON types nếu nghiệp vụ phụ thuộc Decimal128/Date/ObjectId.

### 19.4. Kiểm tra query pattern

```javascript
const testDb = db.getSiblingDB("inventory_restore_test");

testDb.products.find({
  name: "Bàn phím"
}).explain("executionStats");

testDb.orders.find({
  status: "PAID"
}).explain("executionStats");
```

Kết quả collection nhỏ có thể dùng COLLSCAN hợp lý; mục tiêu là xác minh query hoạt động, indexes tồn tại và application không gặp lỗi metadata.

### 19.5. Đừng đo RTO từ lab 5 documents

Restore 5 documents rất khác restore hàng trăm GB có indexes lớn, replica set write concern, storage quota và ứng dụng chạy song song.

Dùng lab để học options; để capacity plan, đo trên khối lượng và shape dữ liệu đại diện.

---

## 20. Checklist tương thích trước restore

Trước khi thực thi, thu thập:

### 20.1. Nguồn

- Source Server version.
- Source FCV.
- Topology standalone/replica set/sharded.
- Namespace scope.
- MongoDB features đang dùng.
- Users/roles cần hay không.
- Dump có `--oplog` không.
- Tình trạng writes/DDL trong backup window.

### 20.2. Công cụ

- `mongodump --version`.
- `mongorestore --version`.
- Định dạng backup directory/archive/gzip.
- Có support cho `--dryRun`/namespace flags/cluster topology theo docs version.
- Same tools version được lưu lại không.
- Binary phù hợp OS/architecture không.

### 20.3. Đích

- Target Server version.
- Target FCV.
- Có hỗ trợ BSON/metadata/index features trong dump không.
- Có đủ disk, IOPS, CPU, memory không.
- AuthSource/backup-restore roles đã chuẩn bị chưa.
- TLS trust/hostname đã khớp chưa.
- Collection đang tồn tại không.
- Có TTL indexes/validation ảnh hưởng restored data không.
- User/role restoration có thể ảnh hưởng tài khoản hiện tại không.
- Có đang restore vào `mongos` hoặc một thành viên replica set phù hợp không.

### 20.4. Business readiness

- RPO và RTO được xác định.
- Có approved restore window.
- Đã giữ backup nguyên bản bất biến.
- Có target cô lập để thử.
- Có dữ liệu đối soát/sample query.
- Có backout/cutover plan.
- App writers đã được kiểm soát khi cần.
- Đã xét encryption và audit.

---

## 21. Backup manifest, checksum và lưu trữ an toàn

Một file backup không tự chứng minh nó đọc lại được. Nên lưu metadata:

```yaml
backupId: inventory-lab-20261114-0200
source:
  topology: standalone
  serverVersion: "record-actual-value"
  fcv: "record-actual-value"
tool:
  mongodumpVersion: "record-actual-value"
  expectedMongorestoreVersion: "same-release-recommended"
format:
  type: archive
  gzip: true
  withOplog: false
  scope: inventory_lab
file:
  name: inventory.archive.gz
  sha256: "record-real-checksum"
policy:
  retentionDays: 30
  encryptedAtRest: true
  access: restricted
validation:
  restoreTested: false
```

### 21.1. Hash file

Linux:

```bash
sha256sum ./backups/inventory.archive.gz
```

PowerShell:

```powershell
Get-FileHash -LiteralPath ".\backups\inventory.archive.gz" -Algorithm SHA256
```

Lưu checksum bên ngoài backup cùng với manifest được bảo vệ.

### 21.2. Verify sau khi chuyển backup

Sau khi upload/download hoặc copy giữa hosts:

1. Tính SHA-256 của file tại source.
2. Tính SHA-256 tại destination.
3. So sánh chính xác.
4. Kiểm tra file size.
5. Khôi phục thử trên isolated target.

Checksum xác nhận file không đổi so với mốc đã hash; **không chứng minh source dump từng nhất quán hoặc application data có thể phục hồi đầy đủ**.

### 21.3. Encryption và retention

Backup chứa dữ liệu nhạy cảm. Cần:

- Encryption at rest.
- Encryption in transit.
- RBAC và limited access.
- Secret/key management tách khỏi archive.
- Retention/lifecycle policies.
- Audit access/download/delete.
- Periodic restore drills.
- Immutable/offline/offsite copy theo mô hình rủi ro.

Không coi gzip là encryption.

### 21.4. Không lưu binary dump trong git

Git không phù hợp cho những bản BSON dump lớn và có thể chứa secrets/PII. Dùng object storage/backup repository có access controls và retention phù hợp.

---

## 22. Khôi phục dữ liệu lớn: runbook trước, trong và sau

### 22.1. Trước restore

1. Xác định yêu cầu nghiệp vụ và điểm khôi phục.
2. Chọn backup đã kiểm tra checksum.
3. Xác định tools version và source/target server/FCV.
4. Xác nhận topology/namespace mapping.
5. Phân tích có `admin`/users/roles trong phạm vi restore không.
6. Dự trù disk (data + indexes + temporary headroom), CPU và thời gian.
7. Dự trù networking và write concerns.
8. Chọn target cô lập hoặc maintenance window.
9. Ngừng/điều tiết writers khi quy trình cần.
10. Chạy dry-run và restore thử nếu hỗ trợ.
11. Đặt monitoring CPU/I/O/lag/latency.
12. Chuẩn bị rollback.

### 22.2. Trong restore

- Ghi log command **đã che secrets** và tools versions.
- Ghi thời điểm bắt đầu và kết thúc.
- Theo dõi số restored/failed documents.
- Theo dõi disk space, CPU, IO latency, cache.
- Theo dõi replication lag nếu target là replica set.
- Không tăng concurrency quá mức nếu thấy overload.
- Không tự chạy song song nhiều `--drop` restore trùng namespace.
- Dừng và điều tra khi xuất hiện duplicate/schema/index/authentication errors.
- Không coi process exit code 0 là bằng chứng duy nhất về correctness.

### 22.3. Sau restore

- Xem exit code và log summary.
- Kiểm tra collections/views/indexes/options.
- Đối chiếu document counts theo namespace.
- Kiểm tra mẫu dữ liệu quan trọng và BSON types.
- So business invariants/cross-collection references.
- Chạy smoke test ứng dụng.
- Đo query explain/index usage.
- Kiểm tra roles/authentication.
- Quan sát TTL/retention behavior.
- Kiểm tra monitoring/alerts.
- Chỉ cutover sau khi đạt tiêu chí chấp nhận.
- Ghi lại RTO thực tế và học được gì cho lần sau.

### 22.4. Tiêu chí dừng

Nếu một trong các điều sau xảy ra:

- Tools/server compatibility chưa được xác nhận.
- Backup checksum sai.
- Mất quyền phục hồi do `admin` user restoration.
- Thiếu dung lượng disk.
- Dữ liệu restoration không đạt kiểm tra.
- Replication/shard topology không an toàn.
- Không còn phương án rollback.
- Mốc RPO/RTO không đạt yêu cầu và cần quyết định nghiệp vụ.

thì cần dừng/chuyển sang runbook recovery phù hợp, không tăng quyền hoặc bật insecure options để cố vượt lỗi.

---

## 23. Java ứng dụng nên làm gì trong backup/restore workflow?

`mongodump` và `mongorestore` là **CLI tools**, không phải những method trong MongoDB Java Sync Driver.

Java application có thể:

- Tạo dữ liệu lab.
- Chạy kiểm tra read-only đối với dữ liệu trước/sau restore.
- Ghi/đối chiếu business counts/invariants.
- Truy vấn database mới cho smoke test.
- Tham gia cutover theo config/feature flag.
- Trong một số hệ thống vận hành, gọi automation job được quản lý (không nên để request HTTP công khai chạy lệnh backup tùy ý).

### 23.1. Không viết mongodump giả bằng find()

Một chương trình Java chạy:

```java
collection.find()
```

rồi ghi JSON ra file **không tương đương** với mongodump. Nó không tự sao lưu:

- Toàn bộ BSON types chính xác.
- Collection metadata.
- Index definitions.
- Users/roles.
- Oplog consistency.
- Các namespace khác.

Nếu muốn dùng logical backup tool, gọi `mongodump` chuẩn qua trusted operational automation thay vì tự chế một bản sao chỉ chứa documents.

### 23.2. Java Smoke Test sau restore

Ví dụ sử dụng MongoDB Java Sync Driver:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class RestoreSmokeTest {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_RESTORE_TEST_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_RESTORE_TEST_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                    client.getDatabase("inventory_restore_test");

            long productCount =
                    db.getCollection("products").countDocuments();

            long orderCount =
                    db.getCollection("orders").countDocuments();

            System.out.println(
                    "products=" + productCount
                    + ", orders=" + orderCount
            );

            Document product =
                    db.getCollection("products")
                      .find(new Document("_id", "P-100"))
                      .first();

            if (product == null) {
                throw new IllegalStateException(
                        "Restored product P-100 missing");
            }

            System.out.println(
                    "Restore smoke test passed");
        }
    }
}
```

Đây chỉ là smoke test. Production validation cần thêm query theo nghiệp vụ, indexes, roles và đối soát tính nhất quán.

### 23.3. Đọc Indexes sau restore

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> products =
        database.getCollection("products");

for (Document index : products.listIndexes()) {
    System.out.println(index.toJson());
}
```

Dùng method này trong một application/admin test có quyền. Cần đối chiếu cả tên, key pattern và important options nếu có.

### 23.4. Vì sao không gọi ProcessBuilder tùy ý từ request API?

Để cho user upload một URI/filename rồi backend Java chạy:

```text
mongorestore --drop <untrusted-input>
```

có thể dẫn tới:

- Injection ở shell/command arguments nếu xây lệnh sai.
- Restore nhầm namespace.
- Lộ backup/password.
- Mất dữ liệu production.
- Exhaust disk/network/CPU.

Nếu thiết kế backup service, nên có **whitelisted jobs**, fixed target scopes, approval/authorization, audit, secret injection và sandboxed execution. Không biến mongorestore thành một endpoint chạy lệnh bất kỳ.

---

## 24. Những lỗi thực tế và cách chẩn đoán

### 24.1. Command not found

Triệu chứng:

```text
mongodump: command not found
```

Nguyên nhân:

- Chưa cài Database Tools.
- Binary không nằm trong PATH.
- Cài mongosh nhưng không cài Database Tools.
- Đang dùng container image thiếu tools.

Xử lý: kiểm tra cài đặt, `mongodump --version` và đường dẫn binary.

### 24.2. Authentication failed

Nguyên nhân:

- Sai username/password.
- Sai `--authenticationDatabase`/`authSource`.
- Authentication mechanism không phù hợp.
- Secret chứa ký tự URI special chưa được encode đúng.
- Server/DB user không tồn tại.

Xử lý: kiểm tra user/source/mechanism, không cấp root hay tắt auth để né lỗi.

### 24.3. Not authorized to execute command

Auth đã thành công nhưng role thiếu quyền đọc/backup/restore một namespace hoặc metadata.

Xử lý: so quyền với operation/namespace, thêm quyền tối thiểu theo docs version.

### 24.4. TLS certificate validation failed

Nguyên nhân:

- CA chain không trusted.
- Hostname/SAN không khớp.
- Certificate hết hạn.
- Client/server TLS config không tương thích.

Xử lý: sửa trust store/CA/certificate/hostname, không bật invalid certificate bypass production.

### 24.5. Duplicate key khi restore

Có dữ liệu đích với cùng `_id` hoặc unique indexed key.

Xử lý:

- Restore vào database/namespace mới.
- Nếu muốn replace có chủ đích, cân nhắc `--drop` sau review.
- Dùng `--stopOnError` để phát hiện sớm.
- Không xóa dữ liệu production nếu chưa có recovery plan.

### 24.6. Index build failed

Nguyên nhân:

- Duplicate dữ liệu.
- Index option không supported.
- Target Server/FCV không phù hợp.
- Không đủ disk/CPU.
- Collation/index metadata khác.

Xử lý: xác định index lỗi cụ thể, kiểm tra compatibility. Không tự bỏ toàn bộ index restore rồi tuyên bố hệ thống đã phục hồi hoàn toàn.

### 24.7. Restore namespace không đúng

Nguyên nhân:

- Dùng `--db`/`--collection` cho archive theo cách deprecated/không đúng.
- `--nsInclude` pattern không match.
- `--nsFrom`/`--nsTo` mapping sai.
- Shell expand `*` hoặc `$`.
- Nguồn backup không chứa namespace cần khôi phục.

Xử lý: xem dry-run, archive structure và explicit namespace patterns.

### 24.8. Unexpected zero documents restored

Có thể do:

- Dump rỗng.
- NsInclude không khớp.
- File input sai.
- Restore lỗi quyền nhưng script bỏ qua exit code.
- Tool bỏ qua các collections theo flags.
- Archive chưa được unzip/đọc đúng format.

Đừng coi 0 documents restored là success nếu expectation là có dữ liệu.

### 24.9. Unsupported BSON/metadata

Nguyên nhân:

- Server nguồn/đích khác major/FCV ngoài phạm vi được hỗ trợ.
- Index/collection feature mới không tồn tại ở đích.
- Dump/archive/tool versions không khớp.
- Oplog replay qua incompatible transition.

Xử lý: so version matrix và restore test; không ép bỏ metadata tùy tiện.

### 24.10. Restore xong dữ liệu bị xóa tiếp

Có thể do TTL index và documents đã quá thời hạn retention.

Xử lý: kiểm tra index definitions và TTL policy; nếu staging cần lưu lịch sử, dùng một môi trường thử nghiệm với retention được kiểm soát theo chính sách.

### 24.11. Sharded backup inconsistency

Backup qua mongos trong lúc chunk migration/writes diễn ra có thể thiếu cluster-wide consistency guarantee.

Xử lý: dùng quy trình sharded backup chính thức hoặc managed backup; không bổ sung `--oplog` vào lệnh qua mongos rồi xem là đủ.

### 24.12. Restore chậm hoặc đĩa đầy

Nguyên nhân:

- Nhiều indexes.
- Dữ liệu lớn.
- Network/disk throughput thấp.
- Too many insertion workers.
- Replication lag/write concern.
- Compression CPU overhead.
- Không đủ storage headroom.

Xử lý: capacity plan, tune concurrency, quan sát metrics và thử restore với dataset representative.

---

## 25. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| `mongodump` là snapshot filesystem | Nó là logical backup |
| Dump toàn bộ deployment nghĩa là backup mọi cấu hình hạ tầng | Không, network/secrets/storage settings không tự được bảo toàn |
| Có BSON là đủ phục hồi toàn ứng dụng | Còn indexes, metadata, users, roles, liên kết nghiệp vụ |
| `mongodump` tự consistent khi có concurrent writes | Không mặc định; cần bảo đảm consistency phù hợp |
| `--oplog` dùng với `--db` | Không hỗ trợ theo quy tắc full dump của replica set |
| `--oplog` bảo đảm consistency cho sharded cluster qua mongos | Không |
| `--oplogReplay` dùng với `--nsFrom`/`--nsTo` | Không với full oplog restore workflow |
| `--drop` xóa cả database | Xóa các target collections có trong dump, không tự xóa mọi collection khác |
| `mongorestore` luôn replace documents | Không; có thể gặp duplicate key khi collection đã có dữ liệu |
| Restore là transaction atomic | Không; có thể để lại một phần data khi thất bại |
| `--stopOnError` rollback mọi thứ | Chỉ dừng; không rollback writes đã thành công |
| `--dryRun` chứng minh khôi phục được | Nó không thay restore test thật |
| `--gzip` mã hóa backup | Gzip là nén, không phải encryption |
| Tools 100.x phải khớp Server 100.x | Tools và Server phát hành độc lập |
| Tool kết nối được mọi Server là dump/restore cross-version an toàn | Còn source/target FCV, metadata, archive và oplog |
| BSON restore sang version mới là upgrade chuẩn | MongoDB docs không khuyến nghị dùng dump/restore thay quy trình upgrade |
| Khác phiên bản mongodump/mongorestore chắc chắn tương thích | Nên dùng cùng release để tránh format mismatch |
| `mongoexport` là thay thế đầy đủ cho `mongodump` | Không, semantics và metadata khác nhau |
| `--noIndexRestore` chỉ tăng tốc, không có hệ quả | Có thể mất index/constraints/query performance |
| Có `readWrite` là đủ cho full restore | Quyền cần tùy namespace/users/roles/oplog |
| `ping` thành công chứng minh đủ quyền backup | Cần kiểm tra required access |
| Restore count bằng nhau nghĩa là dữ liệu đúng | Còn BSON types, indexes, business invariants |
| Restore nhanh trên 5 documents nghĩa là RTO đạt | Phải đo trên dữ liệu production-like |
| Backup trên secondary không ảnh hưởng production | Secondary lag/IO có thể ảnh hưởng HA |
| Đã tải archive là xong DR | Cần checksum, encryption, offsite và restore drills |
| TTL không ảnh hưởng dữ liệu đã restore | TTL có thể xóa bản ghi lịch sử theo policy |

---

## 26. Bài tập thực hành

### Bài A — Cài và kiểm tra tương thích

1. Chạy `mongodump --version` và `mongorestore --version`.
2. Trong `mongosh`, chạy `db.version()`.
3. Nếu có quyền, xem FCV.
4. Tra Server Compatibility cho đúng Database Tools release.
5. Giải thích vì sao tools version và Server version không cần cùng số.

### Bài B — Directory vs archive

1. Tạo `inventory_lab` theo dữ liệu mẫu.
2. Dump ra directory.
3. Dump ra archive.
4. Dump ra archive + gzip.
5. So sánh file layout, kích thước, restore flags cần dùng.
6. Giải thích tại sao `--gzip` không có nghĩa backup đã được mã hóa.

### Bài C — Restore vào database khác

1. Dump `inventory_lab`.
2. Restore bằng `--nsFrom/--nsTo` vào `inventory_restore_test`.
3. Kiểm tra productCount/orderCount.
4. Kiểm tra indexes.
5. So Decimal128/Date values.
6. Không dùng `--drop` trên database gốc.

### Bài D — Duplicate key và --stopOnError

Trong lab:

1. Restore một archive vào target có dữ liệu từ lần restore trước.
2. Ghi nhận duplicate errors.
3. Chạy lại có `--stopOnError`.
4. Giải thích vì sao một số writes trước khi lỗi có thể vẫn tồn tại.
5. Thiết kế cách restore idempotent bằng target mới.

### Bài E — Partial dump và consistency

Giả sử có `orders` và `payments`. Nếu dump từng collection trong lúc ứng dụng cập nhật cả hai, có thể xảy ra trạng thái lệch nào? Làm thế nào để xây backup nhất quán theo topology và yêu cầu RPO?

### Bài F — Replica set oplog

1. Giải thích yêu cầu full dump của `--oplog`.
2. Giải thích vì sao `--db commerce --oplog` không được hỗ trợ.
3. Mô tả file `oplog.bson`.
4. Nêu `--oplogReplay`.
5. Giải thích vì sao không kết hợp `--oplogReplay` với `--nsTo`.
6. Nêu rủi ro DDL và FCV transition.

Chỉ thực hiện backup/restore oplog thực sự trên lab replica set có runbook phù hợp.

### Bài G — Sharded cluster

Giải thích tại sao một mongos không có một oplog chung để tạo consistent backup bằng `--oplog`. Nêu các yếu tố cần phối hợp giữa shards, balancer, metadata và writers.

### Bài H — Version migration

Nguồn chạy Server major version A, target major version B.

1. Thu thập Server versions và FCV.
2. Thu thập Database Tools versions.
3. Xác định dữ liệu BSON vs metadata/archive/oplog.
4. Kiểm tra docs compatibility.
5. Chọn restored target cùng version hoặc quy trình upgrade được hỗ trợ.
6. Thực hiện restore test và đối chiếu indexes/collections.

### Bài I — Authentication/roles

Một user `backup_operator` được tạo trong `admin`, cần dump `commerce`.

- `--authenticationDatabase` cần là gì?
- `--db` là gì?
- Role nào phù hợp?
- Vì sao không cần root?
- Vì sao password không nên nằm trên command line?

### Bài J — TTL sau restore

Một backup có collection events với TTL 30 ngày. Restore dữ liệu 6 tháng trước vào staging, thấy dữ liệu biến mất. Hãy giải thích và lập kế hoạch lab retention an toàn để vẫn kiểm thử lịch sử.

### Bài K — RPO/RTO

Hệ thống backup 2:00 mỗi ngày, sự cố lúc 18:00. Restore full dump mất 3 giờ. Hãy ước tính data loss window tối đa và thời gian phục hồi thực tế theo dữ kiện, rồi đề xuất khi nào cần continuous backup.

### Bài L — Runbook an toàn

Viết runbook có:

- Scope và owner.
- Backup identifier/checksum.
- Source/target Server version và FCV.
- Tools versions.
- TLS/authSource và quyền.
- Dump format/flags.
- DDL/writes management.
- Test restore, smoke tests.
- Observability.
- Cutover/rollback.
- Retention/encryption.

---

## 27. Quy tắc quyết định nhanh

| Câu hỏi | Hướng xử lý |
|---|---|
| Muốn copy một database nhỏ sang lab? | Dump database, restore sang namespace mới |
| Backup đang có writes và nguồn là replica set? | Xem full `--oplog` với điều kiện được hỗ trợ |
| Nguồn sharded cluster có writes liên tục? | Dùng quy trình cluster-aware/managed backup |
| Muốn restore một collection từ archive? | `--nsInclude` |
| Muốn đổi tên database khi restore? | `--nsFrom`/`--nsTo` |
| Muốn replace collection đích? | Review `--drop` và đảm bảo có backup/cutover plan |
| Muốn giữ nguyên target cũ? | Restore sang namespace khác |
| Có duplicate key errors? | Xác định mục tiêu merge/replace, cân nhắc `--stopOnError` |
| Có BSON nhưng metadata không tương thích? | Không coi documents insert được là full restore |
| Tool versions không giống nhau? | Ưu tiên cùng release, thử restore trước |
| Server nguồn/đích khác major/FCV? | Xem docs compatibility và upgrade path |
| Cần RPO rất thấp? | PITR/continuous backup phù hợp |
| Chỉ có một file dump chưa từng restore thử? | Chưa chứng minh recovery readiness |

---

## 28. Tài liệu chính thức

- [MongoDB Database Tools documentation](https://www.mongodb.com/docs/database-tools/)
- [MongoDB Database Tools installation](https://www.mongodb.com/docs/database-tools/installation/)
- [MongoDB Database Tools release notes](https://www.mongodb.com/docs/database-tools/release-notes/database-tools-changelog/)
- [mongodump reference](https://www.mongodb.com/docs/database-tools/mongodump/)
- [mongodump behavior and compatibility](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-behavior/)
- [mongorestore reference](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [mongorestore behavior and compatibility](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [mongorestore compatibility and installation](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-compatibility-and-installation/)
- [Back Up and Restore Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/)
- [Back Up a Self-Managed Sharded Cluster with a Database Dump](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-database-dumps/)
- [Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Atlas Backup](https://www.mongodb.com/docs/atlas/backup/)
- [MongoDB Java Sync Driver documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)

> **Ghi chú:** Database Tools được phát hành độc lập với server. Những ví dụ `100.20.1` trong tài liệu chính thức phản ánh một thời điểm phát hành; khi triển khai, luôn kiểm tra compatibility matrix và behavior page của **đúng binary/tool/server versions** đang dùng. Không áp dụng các giới hạn phiên bản như một hằng số bất biến theo thời gian.

## 29. Tổng kết

1. `mongodump` xuất **logical BSON data và metadata**, còn `mongorestore` nạp lại dữ liệu/index/options trong phạm vi được hỗ trợ.
2. Database Tools có **version riêng** (nhánh `100.x`), cần kiểm tra tương thích với MongoDB Server source/destination.
3. Cần phân biệt **Server version, FCV, Database Tools version và định dạng backup**; khả năng restore BSON không đồng nghĩa metadata/archive/oplog sẽ an toàn cross-version.
4. **Ưu tiên dùng cùng release mongodump và mongorestore**, và khôi phục thử vào target có version/FCV tương thích.
5. Dump thông thường khi có concurrent writes **không mặc định là một consistent point-in-time snapshot**.
6. `--oplog`/`--oplogReplay` hữu ích cho **full replica set dump**, nhưng không kết hợp với phạm vi `--db`/`--collection` hay namespace remap khi replay.
7. `--oplog` **không** biến một mongos dump thành consistent full sharded-cluster backup.
8. `--drop` chỉ xóa các target collections được restore từ dump, nhưng có thể gây mất dữ liệu và đặc biệt nguy hiểm với `admin` users/roles.
9. `--nsInclude` và `--nsFrom/--nsTo` hỗ trợ selective restore và database rename an toàn hơn, nếu workflow không dùng oplog replay.
10. Gzip giảm dung lượng, **không mã hóa**; backup phải có checksum, encryption, RBAC, retention và restore drills.
11. Khôi phục phải xác minh **documents, BSON types, indexes, collection options, roles và business invariants**, không chỉ nhìn exit code hoặc count.
12. Với yêu cầu RPO/RTO nghiêm ngặt hoặc cluster lớn, cần cân nhắc backup/snapshot/PITR được hỗ trợ thay vì chỉ mongodump một lần mỗi ngày.

**Kết luận:** Một bản dump chỉ trở thành tài sản khôi phục đáng tin cậy khi nó có **định dạng đúng, tool/server/FCV tương thích, consistency phù hợp topology, bảo vệ bí mật, và đã được restore thử thành công**. Thiết kế runbook bắt đầu từ RPO/RTO và tương thích công cụ, không bắt đầu từ việc chạy ngay `mongorestore --drop`.
