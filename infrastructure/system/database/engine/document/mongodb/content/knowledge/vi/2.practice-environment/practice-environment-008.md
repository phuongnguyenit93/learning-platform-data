# Kiểm tra kết nối, log khởi động và dọn dữ liệu thử nghiệm an toàn

## 1. Mục tiêu của buổi thực hành

Sau khi cài đặt hoặc khởi chạy MongoDB, ba việc cần làm trước khi phát triển ứng dụng là **kiểm tra kết nối**, **đọc log khởi động** và **dọn dữ liệu thử nghiệm có kiểm soát**. Đây là các thao tác nhỏ nhưng ảnh hưởng trực tiếp đến khả năng phát hiện lỗi cấu hình và tránh xóa nhầm dữ liệu.

Bài thực hành này hướng đến một **MongoDB local hoặc môi trường thử nghiệm do bạn quản lý**. Các ví dụ sử dụng MongoDB Shell (`mongosh`), lệnh hệ điều hành và Docker. Có thể chọn nhánh thao tác phù hợp với cách bạn đang chạy MongoDB; không cần cài cả Docker lẫn MongoDB service.

Kết quả mong đợi:

1. Biết xác định MongoDB server có chạy và đang lắng nghe đúng cổng hay không.
2. Kết nối bằng `mongosh`, kiểm tra lệnh `ping` và phân biệt kết nối mạng với quyền truy cập database.
3. Tìm đúng nguồn log và nhận ra thông báo khởi động thành công, lỗi bind cổng, cấu hình, lưu trữ, xác thực.
4. Tạo một document kiểm thử có **dấu nhận diện duy nhất**, đọc lại và xóa chính document đó.
5. Biết cách xem trước phạm vi xóa và xác nhận kết quả mà không dùng thao tác xóa toàn database/collection.

> **Phạm vi an toàn:** Chỉ thực hiện lệnh ghi và xóa trên database thử nghiệm đã được xác định. Trước mọi lệnh xóa, kiểm tra lại địa chỉ server, tên database, collection và điều kiện lọc. Không dùng thao tác `dropDatabase()`, `drop()` hoặc lệnh xóa không có bộ lọc trong bài học này.

## 2. Hiểu đường đi của một kết nối MongoDB

Một kết nối từ ứng dụng đến MongoDB thường đi qua các thành phần:

```text
Ứng dụng / mongosh
      |
      | MongoDB connection string (URI)
      v
Host / DNS + cổng TCP (thường là 27017)
      |
      v
MongoDB server (mongod hoặc cụm MongoDB)
      |
      +--> Xác thực tài khoản (nếu bật authentication)
      |
      +--> Kiểm tra quyền với lệnh / database / collection
      |
      v
Trả kết quả truy vấn
```

**Có thể mở được cổng TCP chưa có nghĩa là đã xác thực thành công.** Tương tự, một lệnh `ping` thành công chứng minh server phản hồi lệnh đó nhưng chưa chứng minh tài khoản có quyền ghi vào collection cần dùng. Vì vậy cần kiểm tra theo từng lớp: tiến trình → mạng → lệnh MongoDB → quyền đọc/ghi thực tế.

Các thông số kết nối thường gặp:

| Thông số | Ý nghĩa | Ví dụ trong môi trường local |
| --- | --- | --- |
| Host | Máy đang chạy MongoDB | `127.0.0.1` |
| Port | Cổng server lắng nghe | `27017`; Docker ví dụ bên dưới dùng `27018` ở host |
| Database | Database ứng dụng hoặc bài tập | `mongo_lab` |
| Username/password | Thông tin xác thực nếu server bật xác thực | Tài khoản riêng cho môi trường thử nghiệm |
| `authSource` | Database chứa thông tin tài khoản xác thực | Thường là `admin` khi tạo user ở `admin` |
| TLS | Mã hóa kết nối; thường bắt buộc với dịch vụ cloud | Theo cấu hình server/cụm |

MongoDB lưu document dưới định dạng BSON. Việc thực hiện được các lệnh truy vấn `db...` chỉ có ý nghĩa khi client đã kết nối đến server phù hợp.

## 3. Chuẩn bị môi trường và xác định đúng server

### 3.1. Nếu MongoDB chạy như dịch vụ trên máy

Với MongoDB local đang dùng cổng mặc định, thử kết nối:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Trong `mongosh`, chạy:

```javascript
db.adminCommand({ ping: 1 })
```

Khi thành công, kết quả thường có trường `ok: 1`. Nếu `mongosh` không có trong `PATH`, cần cài MongoDB Shell hoặc dùng đường dẫn thực thi phù hợp. `mongosh` là công cụ client; việc cài shell không đồng nghĩa server `mongod` đã được cài hoặc đang chạy.

Kiểm tra dịch vụ tùy hệ điều hành:

**Linux với systemd** (nếu MongoDB được đăng ký dưới tên `mongod`):

```bash
sudo systemctl status mongod
```

**Windows PowerShell** (nếu MongoDB được cài dưới dạng Windows service):

```powershell
Get-Service -Name MongoDB
Test-NetConnection -ComputerName 127.0.0.1 -Port 27017
```

Tên service và cổng có thể khác nếu cài đặt tùy chỉnh. Khi báo `TcpTestSucceeded : True`, đường TCP đến cổng được mở; vẫn phải dùng `mongosh` để xác nhận đây là MongoDB server mong muốn.

### 3.2. Nếu muốn dùng một container thực hành tách biệt

Ví dụ chạy MongoDB trong Docker, ánh xạ **cổng 27018 của máy host** đến **27017 của container**; chỉ bind trên loopback của host:

```bash
docker run --name mongo-row37 -d -p 127.0.0.1:27018:27017 mongo:8.0
```

Kiểm tra container:

```bash
docker ps --filter name=mongo-row37
docker logs --tail 80 mongo-row37
```

Kết nối từ máy host khi đã cài `mongosh`:

```bash
mongosh "mongodb://127.0.0.1:27018/?directConnection=true"
```

Hoặc dùng shell có sẵn trong container để không phụ thuộc `mongosh` trên máy host:

```bash
docker exec -it mongo-row37 mongosh
```

Ví dụ Docker này dành cho **thực hành trên máy cá nhân**, không bật authentication và không cấu hình lưu trữ lâu dài. Việc giới hạn cổng host về `127.0.0.1` giúp tránh công bố trực tiếp cổng MongoDB ra các giao diện mạng khác của host. Không dùng nguyên cấu hình này để triển khai server có thể truy cập công khai.

> Nếu cổng 27018 đã bị chiếm hoặc container `mongo-row37` đã tồn tại, cần kiểm tra tiến trình/container trước khi lựa chọn cổng hoặc tên mới; không dừng hay xóa tài nguyên chưa xác định quyền sở hữu.

### 3.3. Nếu dùng MongoDB Atlas hoặc server có xác thực

Sử dụng đúng URI do môi trường cung cấp, thường thuộc một trong hai dạng:

```text
mongodb://HOST:PORT/?authSource=admin
mongodb+srv://CLUSTER_HOST/?retryWrites=true&w=majority
```

Với server yêu cầu tài khoản, có thể cung cấp tên user bằng tham số dòng lệnh và nhập mật khẩu qua prompt của `mongosh` theo phương thức được phiên bản shell hỗ trợ. Không đưa mật khẩu thực vào ví dụ, tài liệu, history terminal hoặc ảnh chụp log. Với Atlas, cần kiểm tra thêm quyền mạng/IP access list, DNS SRV và TLS theo cấu hình cụm.

Trong suốt bài học, hãy giữ lại một ghi chú ngắn chỉ gồm: **môi trường**, **host/cổng**, **tên database thử nghiệm** và **tên collection thử nghiệm**. Không ghi lại secret.

## 4. Kiểm tra kết nối theo từng lớp

### 4.1. Xác nhận đang kết nối đúng nơi

Mở `mongosh` bằng URI đã xác định rồi chạy:

```javascript
// Database hiện tại do shell đang chọn
db.getName()

// Thông tin nhận diện máy chủ trả về từ MongoDB
db.adminCommand({ hello: 1 })

// Kiểm tra khả năng server phản hồi lệnh
db.adminCommand({ ping: 1 })
```

Kết quả `ping` điển hình:

```javascript
{ ok: 1 }
```

Phản hồi có thể chứa thêm metadata tùy phiên bản và môi trường. Lệnh `hello` giúp quan sát thông tin liên quan đến server hoặc topology; trong một replica set, những trường như `isWritablePrimary` có thể giúp hiểu vai trò của node. Không suy ra địa chỉ môi trường chỉ từ tên database hiện tại, vì `use mongo_lab` chỉ đổi database làm việc ở client.

Một cách kết nối có nêu database rõ ràng:

```bash
mongosh "mongodb://127.0.0.1:27018/mongo_lab?directConnection=true"
```

Đối với MongoDB chạy trên cổng mặc định, thay `27018` bằng cổng tương ứng. Đừng sao chép cổng của ví dụ Docker sang môi trường đang chạy theo cách khác.

### 4.2. Kiểm tra quyền trước khi ghi thử

Trong `mongosh`:

```javascript
// Xem user đã xác thực nếu môi trường dùng authentication
db.runCommand({ connectionStatus: 1 })

// Chọn database bài tập
const lab = db.getSiblingDB("mongo_lab");
lab.getName();
```

`db.getSiblingDB("mongo_lab")` trả về đối tượng thao tác với database đó; riêng thao tác lựa chọn này **không tạo dữ liệu mới**. Một số lệnh quản trị, liệt kê collection hoặc đọc trạng thái yêu cầu quyền bổ sung. Khi trả về `not authorized`, cần kiểm tra đúng user, `authSource` và role được cấp; không vội kết luận MongoDB server đã hỏng.

Để xác minh quyền ghi thật, ta sẽ thêm và xóa **một document có đánh dấu riêng** ở phần 6.

### 4.3. Diễn giải các lỗi kết nối thường gặp

| Triệu chứng | Khả năng liên quan | Kiểm tra tiếp |
| --- | --- | --- |
| `ECONNREFUSED 127.0.0.1:27017` | Không có tiến trình lắng nghe ở host/cổng đó hoặc ánh xạ cổng không đúng | Trạng thái service/container, cổng `port`, `bindIp`, ánh xạ Docker |
| `Server selection timed out` | Client không tìm được server phù hợp trong thời hạn; có thể do mạng, DNS, topology hoặc cấu hình cụm | URI, kết nối mạng, replica set, DNS/SRV, TLS và log server |
| `Authentication failed` | Sai tài khoản, mật khẩu, cơ chế xác thực hoặc `authSource` | Nguồn user, quyền đăng nhập, cấu hình auth |
| `not authorized on ...` | Đã tới server nhưng tài khoản thiếu quyền với thao tác | Role, database đích, thao tác được cho phép |
| `Address already in use` khi khởi động | Cổng đã có tiến trình khác giữ | Xác định chủ sở hữu cổng; đổi cấu hình nếu phù hợp |
| `Connection closed`, lỗi TLS | Kết nối bị ngắt hoặc không khớp cấu hình bảo mật | TLS, chứng chỉ, proxy, firewall, log hai phía |
| Kết nối được nhưng không thấy dữ liệu | Có thể đang ở database/cluster khác hoặc lọc sai | URI, `db.getName()`, database và tên collection, điều kiện truy vấn |

Thông báo lỗi chỉ là gợi ý ban đầu. Một lỗi mạng ở client có thể bắt nguồn từ server khởi động thất bại; log khởi động là nguồn cần đối chiếu ở bước tiếp theo.

## 5. Đọc log khởi động MongoDB

### 5.1. Tìm nguồn log phù hợp với cách chạy

**Docker container:**

```bash
docker logs --tail 100 mongo-row37
docker logs --since 10m mongo-row37
```

Nếu MongoDB chạy bằng Docker Compose với service mang tên `mongo`:

```bash
docker compose logs --tail 100 mongo
```

**Linux systemd:**

```bash
sudo journalctl -u mongod -n 100 --no-pager
sudo journalctl -u mongod --since "10 minutes ago" --no-pager
```

Tùy cấu hình `mongod.conf`, MongoDB có thể ghi ra file riêng qua `systemLog.path`. Khi đó hãy kiểm tra đúng file đang được instance sử dụng, chẳng hạn:

```bash
sudo tail -n 100 /var/log/mongodb/mongod.log
```

Đường dẫn trên chỉ là một giá trị phổ biến trong một số bản cài Linux, không phải mặc định bắt buộc cho mọi hệ thống.

**Windows service:** xem phần cấu hình `systemLog.path` của file cấu hình instance MongoDB đang dùng, sau đó đọc đuôi file. Ví dụ khi đã biết đúng đường dẫn:

```powershell
Get-Content -LiteralPath "C:\path\to\mongodb\mongod.log" -Tail 100
```

**Atlas:** mở phần giám sát/log tương ứng trong MongoDB Atlas cho đúng project và cluster, tùy quyền truy cập được cấp. Không giả định có quyền đọc log ở cấp hệ điều hành của dịch vụ managed.

### 5.2. Đọc nội dung log như một sự kiện

Ở nhiều bản MongoDB hiện đại, log ở dạng JSON với các trường thường gặp như:

```json
{
  "t": { "$date": "2026-01-05T09:00:00.000+00:00" },
  "s": "I",
  "c": "NETWORK",
  "id": 23016,
  "ctx": "listener",
  "msg": "Waiting for connections",
  "attr": { "port": 27017 }
}
```

Đây là **đoạn minh họa cấu trúc**; ID, timestamp, `ctx`, `attr` và câu chữ có thể khác theo phiên bản, nền tảng và cách khởi chạy.

| Trường | Cách đọc |
| --- | --- |
| `t` | Thời điểm ghi log; chú ý múi giờ |
| `s` | Mức độ: thường `I` = informational, `W` = warning, `E` = error |
| `c` | Nhóm thành phần, ví dụ `NETWORK`, `STORAGE`, `ACCESS` |
| `id` | Mã thông điệp, hữu ích để tìm tài liệu tương ứng |
| `ctx` | Bối cảnh/luồng thực hiện |
| `msg` | Nội dung sự kiện |
| `attr` | Thuộc tính bổ sung giúp xác định cổng, đường dẫn, nguyên nhân... |

Một log `Waiting for connections` hoặc tương đương là dấu hiệu server đã đi đến trạng thái chờ client. Tuy nhiên, việc khởi động có thể hoàn tất rồi phát sinh lỗi sau đó; cần đối chiếu cả thời điểm kiểm tra, trạng thái process và thử `ping`.

### 5.3. Những điểm cần quan sát theo trình tự

1. **Tiến trình bắt đầu từ đâu?** Xác định timestamp và cấu hình instance/phiên bản đã tải.
2. **Cấu hình có hợp lệ không?** Đọc lỗi YAML, tham số không hỗ trợ, quyền truy cập file hay thư mục dữ liệu.
3. **Storage engine khởi tạo được không?** Tìm các thông điệp về `dbPath`, quyền ghi thư mục, khóa file hoặc dung lượng đĩa.
4. **Network đã bind thành công chưa?** Kiểm tra host/IP và port mà server báo.
5. **Server sẵn sàng nhận kết nối chưa?** Tìm thông điệp chờ kết nối và chạy `ping` ngay sau đó.
6. **Kết nối bị từ chối do auth hay quyền?** Đối chiếu timestamp của lỗi client với log server, không lẫn với lỗi khởi động.

Không phải dòng `W` nào cũng là nguyên nhân khởi động thất bại. Ví dụ cảnh báo về thiết lập hệ điều hành hoặc cấu hình an toàn có thể xuất hiện khi server vẫn chạy. Ngược lại, một lỗi `E` kết hợp process thoát ngay cần được xử lý trước khi kiểm thử CRUD.

### 5.4. Mẫu chẩn đoán nhanh

**Trường hợp A — `mongosh` báo không kết nối được:**

```text
mongosh -> ECONNREFUSED
    |
    +--> Service/container có đang chạy? -- Không --> xem log khởi động
    |
    +--> Có --> host/port có khớp? --> bindIp, mapping Docker, firewall
    |
    +--> Khớp --> kiểm tra URI và chi tiết lỗi client/server
```

**Trường hợp B — Kết nối được nhưng không thể ghi:**

```text
ping ok: 1
    |
    +--> insertOne -> Authentication failed?
    |      Kiểm tra user/password/authSource
    |
    +--> insertOne -> not authorized?
    |      Kiểm tra quyền ghi database/collection
    |
    +--> insertOne thành công
           Đọc lại bằng _id + runId, rồi dọn đúng dữ liệu đã tạo
```

**Trường hợp C — Container chạy rồi thoát:** dùng `docker ps -a --filter name=mongo-row37` để xem trạng thái, sau đó `docker logs mongo-row37` để xác định lỗi ngay trước khi thoát. Không cố lặp lệnh kết nối đến một server chưa khởi động thành công.

## 6. Thực hành kiểm tra ghi/đọc/xóa một document an toàn

Một lệnh `ping` chỉ xác nhận server phản hồi. Để kiểm tra trọn đường đi cho môi trường ứng dụng, ta thử **ghi một document**, **đọc lại chính document** và **xóa document đó**. Mọi thao tác đều giới hạn trong database `mongo_lab` và collection `row37_probe`.

### 6.1. Tạo dấu nhận diện riêng cho lượt thử

Trong một phiên `mongosh` đã kết nối đúng môi trường thử nghiệm:

```javascript
const lab = db.getSiblingDB("mongo_lab");
const probes = lab.getCollection("row37_probe");

// Một nhãn riêng cho lượt thực hành; lưu lại nếu phải dọn sau khi ngắt kết nối.
const runId = "row37-" + new ObjectId().toHexString();
print("runId=" + runId);

// Tạo đúng một document thử nghiệm.
const inserted = probes.insertOne({
  runId: runId,
  kind: "connection-check",
  note: "temporary lab data",
  createdAt: new Date()
});
printjson(inserted);
```

Ở đây:

- `mongo_lab` là database chỉ dành cho thực hành. Hãy thay bằng database được cấp phép nếu khóa học đã chỉ định một tên khác.
- `row37_probe` là collection dành riêng cho dữ liệu kiểm thử.
- `runId` giúp phân biệt dữ liệu của lượt chạy này với dữ liệu khác, kể cả khi có nhiều người dùng chung môi trường.
- `inserted.insertedId` là định danh document vừa được tạo. Không nên phụ thuộc vào thời gian tạo hoặc tên ghi chú để xác định bản ghi cần xóa.

Lệnh `insertOne()` thường trả về `acknowledged: true` cùng `insertedId` khi được server chấp nhận theo write concern hiện hành. Nếu lệnh thất bại, ghi nhận lỗi và không chạy bước xóa dựa trên biến chưa tồn tại.

### 6.2. Đọc lại để xác nhận đúng bản ghi

```javascript
const filter = { _id: inserted.insertedId, runId: runId };
const saved = probes.findOne(filter);
printjson(saved);

if (saved === null) {
  throw new Error("Không tìm thấy document vừa tạo; dừng thao tác dọn dữ liệu.");
}
```

Điều kiện có **cả `_id` lẫn `runId`** giúp kiểm tra đúng document của phiên hiện tại. Kết quả có `runId`, `kind` và `createdAt` như đã ghi chứng minh thao tác ghi và đọc cơ bản hoạt động trên collection thử nghiệm.

### 6.3. Xóa đúng một document do mình tạo

Sau khi xem kết quả `saved` và xác nhận đúng môi trường:

```javascript
// Phạm vi xóa: một document có cả _id và runId khớp.
const removal = probes.deleteOne(filter);
printjson(removal);

// Phải bằng 0 nếu bản ghi vừa xóa không còn tồn tại.
print("remaining=" + probes.countDocuments(filter));
```

Với một lần thử thông thường, `deletedCount` là `1` và `remaining` là `0`. Nếu `deletedCount` bằng `0`, có thể bản ghi đã bị xóa, điều kiện lọc không khớp hoặc đang xem nhầm môi trường; cần kiểm tra lại thay vì nới rộng bộ lọc một cách tùy tiện.

**Tại sao không dùng `deleteMany({})`?** Bộ lọc rỗng sẽ chọn mọi document trong collection hiện tại. Sai database hay collection có thể gây mất dữ liệu. Phương pháp kết hợp `_id` và `runId` minh bạch hơn và phù hợp với kiểm tra kết nối.

## 7. Dọn dữ liệu thử nghiệm còn sót từ phiên trước

Nếu phiên shell đóng sau khi đã chèn document nhưng trước khi xóa, có thể mở phiên mới để dọn. Điều kiện tiên quyết là **biết chính xác `runId` đã in ở bước tạo** và đã xác định đúng server/database/collection.

### 7.1. Xem trước các bản ghi sẽ bị ảnh hưởng

```javascript
const lab = db.getSiblingDB("mongo_lab");
const probes = lab.getCollection("row37_probe");

// Thay bằng runId thực tế đã lưu từ lần thực hành của chính bạn.
const runId = "row37-PASTE_YOUR_SAVED_RUN_ID";
const filter = { runId: runId, kind: "connection-check" };

print("database=" + lab.getName());
print("collection=" + probes.getName());
print("matchCount=" + probes.countDocuments(filter));

// Xem một số bản ghi thuộc phạm vi sẽ xóa.
printjson(
  probes.find(filter, { _id: 1, runId: 1, kind: 1, createdAt: 1 })
    .limit(10)
    .toArray()
);
```

Đừng thực hiện bước tiếp theo nếu:

- Chưa xác nhận được URI hoặc server đang kết nối.
- Không tìm lại được `runId` gốc, hoặc số bản ghi khớp không phù hợp với lượt thực hành.
- Danh sách xem trước chứa dữ liệu không do bạn tạo hoặc có mục đích khác.
- Tài khoản đang trỏ đến database chia sẻ/sản xuất mà chưa có quy trình xóa được phê duyệt.

### 7.2. Xóa với bộ lọc đã kiểm tra

Chỉ khi đã thấy chính xác **một** document thuộc lượt thực hành trong bước xem trước:

```javascript
const expectedCount = probes.countDocuments(filter);
if (expectedCount !== 1) {
  throw new Error("Không có đúng một document cần dọn; dừng lại để kiểm tra.");
}

const target = probes.findOne(filter, { _id: 1, runId: 1 });
if (!target) {
  throw new Error("Document đã thay đổi; dừng lại để kiểm tra.");
}

const result = probes.deleteOne({
  _id: target._id,
  runId: runId,
  kind: "connection-check"
});
printjson(result);
print("remaining=" + probes.countDocuments(filter));
```

Cách này vẫn có thể gặp trường hợp dữ liệu bị thay đổi đồng thời giữa lúc xem trước và lúc xóa. Tuy nhiên, điều kiện xóa gắn với `_id` cụ thể và dấu nhận diện riêng, nên phạm vi tác động vẫn rất hẹp. Với môi trường nhiều người sử dụng, cần phối hợp quy trình riêng nếu phải dọn hàng loạt.

Nếu một lượt thực hành cố ý tạo nhiều document, dùng bộ lọc chính xác theo `runId`, xem trước toàn bộ phạm vi và cân nhắc xóa từng `_id`; không mặc định chuyển sang `deleteMany()` chỉ để tiết kiệm thao tác.

### 7.3. Phân biệt dọn document với dọn container

Xóa document trong MongoDB và xóa Docker container là hai hành động khác nhau. Nếu bạn **tự tạo** container `mongo-row37` dành riêng cho bài tập và không cần giữ dữ liệu bên trong, có thể dừng và xóa container đó:

```bash
docker stop mongo-row37
docker rm mongo-row37
```

Chỉ chạy hai lệnh này khi đã xác nhận container đúng tên thuộc môi trường thực hành của bạn. Ví dụ `docker run` ở phần 3 không gắn volume dữ liệu bền vững; xóa container đó có thể làm mất dữ liệu đang nằm trong filesystem của container. Với container có gắn volume hoặc hệ thống dùng chung, phải kiểm tra nguồn dữ liệu và quyền sở hữu riêng trước khi dọn tài nguyên.

## 8. Cách ghi nhận kết quả thực hành

Một biên bản ngắn giúp người khác hiểu lỗi mà không cần nhận thông tin nhạy cảm. Ví dụ:

```text
Môi trường: Docker MongoDB local (chỉ host loopback)
Endpoint: 127.0.0.1:27018
Database thử nghiệm: mongo_lab
Collection thử nghiệm: row37_probe
Trạng thái container/server: Running
Ping: ok = 1
Log khởi động: Có thông điệp chờ kết nối, không có lỗi dừng server
Kiểm tra CRUD: 1 document insert -> find -> delete thành công
Số document còn lại theo _id + runId: 0
Không lưu mật khẩu, access token hoặc toàn bộ URI có credentials
```

Khi cần đưa log vào ticket hoặc báo cáo kỹ thuật, chỉ lấy đoạn có liên quan đến thời điểm xảy ra lỗi và che thông tin nhạy cảm như URI có credentials, token, IP nội bộ không cần thiết, thông tin khách hàng hoặc đường dẫn chứa dữ liệu cá nhân. Nên giữ timestamp, mã lỗi, thành phần, câu thông báo lỗi và ngữ cảnh cần thiết để chẩn đoán.

## 9. Một số tình huống thực tế

### Tình huống 1: Server báo chạy nhưng kết nối không được

Một container báo `Up`, nhưng `mongosh` đến `127.0.0.1:27017` nhận `ECONNREFUSED`. Kiểm tra `docker ps` thấy ánh xạ `127.0.0.1:27018->27017/tcp`. Sự cố nằm ở **cổng host đang dùng sai**. Thử URI với cổng `27018` và chạy lại `ping`; không cần thay đổi dữ liệu.

### Tình huống 2: Ping thành công, insert thất bại

Kết nối và `ping` trả `ok: 1`, nhưng `insertOne` báo `not authorized`. Server và kết nối có thể vẫn hoạt động bình thường. Cần kiểm tra tên database, tài khoản và role của user. Không dùng tài khoản đặc quyền hơn một cách tùy tiện chỉ để vượt qua lỗi.

### Tình huống 3: Khởi động xong rồi thoát

Không thấy `mongod` trong danh sách tiến trình, trong khi log có lỗi liên quan đến `dbPath` hoặc không thể mở file dữ liệu. Bắt đầu từ lỗi cuối cùng có liên quan trước khi process thoát, kiểm tra đường dẫn, quyền ghi, dung lượng và cấu hình volume. Thử `ping` liên tục không giải quyết nguyên nhân khởi động.

### Tình huống 4: Bài thực hành chạy lại nhiều lần

Các lượt thử cũ để lại vài document `row37_probe`. Mỗi lượt có một `runId` khác nhau. Người học chỉ dọn document có `runId` thuộc lượt của mình, xác nhận `matchCount` và xem trước trước khi xóa. Không xóa cả collection để “làm sạch nhanh” vì có thể chứa bản ghi của người khác.

## 10. Checklist trước khi kết thúc buổi thực hành

| Câu hỏi | Dấu hiệu hoàn thành |
| --- | --- |
| Đã xác định đúng MongoDB instance chưa? | Có host, port, môi trường và database rõ ràng |
| Server khởi động ổn định chưa? | Tiến trình/container chạy, log không báo lỗi làm server dừng |
| Lệnh MongoDB hoạt động chưa? | `db.adminCommand({ ping: 1 })` có `ok: 1` |
| Quyền ghi/đọc có phù hợp chưa? | `insertOne` và `findOne` hoạt động trong collection thử nghiệm |
| Đã dọn chính xác dữ liệu vừa tạo chưa? | `deleteOne` có `deletedCount: 1`, truy vấn lại theo `_id` + `runId` không còn document |
| Có tránh thao tác xóa rộng và lộ credentials không? | Bộ lọc xóa có nhận diện riêng; biên bản không chứa secret |

## 11. Câu hỏi luyện tập

1. Vì sao `Test-NetConnection` báo mở cổng TCP chưa đủ để kết luận ứng dụng đã truy cập được collection?
2. Sự khác nhau giữa `ECONNREFUSED`, `Authentication failed` và `not authorized` là gì?
3. Khi MongoDB không khởi động, vì sao phải xem log server trước khi thử lệnh chèn dữ liệu?
4. Vì sao mỗi lượt kiểm tra nên có `runId` khác nhau? `_id` và `runId` bổ sung cho nhau thế nào khi dọn dữ liệu?
5. Điều gì có thể xảy ra nếu chạy `deleteMany({})` trong một collection dùng chung?
6. Khi `deletedCount` bằng `0`, cần kiểm tra gì trước khi thay đổi bộ lọc xóa?

Khi hoàn thành, bạn có một quy trình lặp lại được: **xác định đúng môi trường → kiểm tra kết nối → đọc log nếu có lỗi → kiểm tra ghi/đọc có đánh dấu riêng → xóa có điều kiện → xác nhận không còn dữ liệu kiểm thử**. Quy trình này giúp phân biệt sự cố vận hành với sự cố truy vấn, đồng thời giới hạn tác động của thao tác thực hành lên dữ liệu.
