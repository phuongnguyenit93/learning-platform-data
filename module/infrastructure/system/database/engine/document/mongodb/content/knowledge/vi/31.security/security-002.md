# Xác thực SCRAM, authentication database và cơ chế chứng chỉ trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Bảo mật

## 1. Bài toán: vì sao kết nối được tới MongoDB nhưng vẫn không đăng nhập được?

Giả sử một hệ thống bán hàng có MongoDB ở địa chỉ `mongo1.example.internal:27017`, dữ liệu ứng dụng nằm trong database `commerce`. Nhóm phát triển nhận được các yêu cầu:

- Ứng dụng Java phải đăng nhập bằng username/password.
- Người dùng `app_reader` chỉ được đọc collection trong `commerce`.
- Tài khoản quản trị được tạo trong database `admin` nhưng vẫn cần thao tác trên `commerce`.
- Kết nối phải được mã hóa và xác minh máy chủ bằng chứng chỉ TLS.
- Một dịch vụ CDC nội bộ cần dùng **chứng chỉ client** thay vì mật khẩu.
- Replica set có thể dùng chứng chỉ riêng cho **xác thực giữa các thành viên**, không chỉ cho ứng dụng.
- Không lưu password hoặc private key trực tiếp trong mã nguồn.

Vấn đề thường gặp là kỹ sư biết có một connection string nhưng chưa phân biệt rõ:

1. **Authentication mechanism**: client chứng minh danh tính bằng cách nào? SCRAM hay X.509?
2. **Authentication database**: server tìm user credential tại database nào? `admin`, `commerce` hay `$external`?
3. **Authorization**: sau khi đăng nhập, user được phép chạy lệnh gì, trên database/collection nào?
4. **Transport security**: TLS mã hóa đường truyền và xác minh certificate của server/client thế nào?

Bốn điều này liên quan, nhưng **không thay thế nhau**.

Ví dụ:

```text
Client ──(TCP/TLS)──> MongoDB server
          │
          ├── TLS: mã hóa + xác minh server certificate
          │
          ├── Authentication:
          │     SCRAM → username/password + authSource
          │     X.509 → client certificate + $external
          │
          └── Authorization:
                role readWrite/read/user-defined role
                quyết định các thao tác được phép
```

Một kết nối có thể:

- **Bị từ chối ở TLS** vì hostname không khớp chứng chỉ.
- **Qua TLS nhưng thất bại authentication** vì `authSource` sai.
- **Authentication thành công nhưng gặp Unauthorized** vì thiếu role.
- **Authentication thành công qua SCRAM mà vẫn thiếu TLS**, dẫn đến rủi ro lộ thông tin/traffic trên đường truyền.

**Mục tiêu bài học:** hiểu chính xác SCRAM, cách chọn authentication database, cấu hình TLS và MONGODB-X509, phân biệt user certificate với server certificate và cluster member authentication, triển khai an toàn trên `mongosh` và Java Sync Driver, cuối cùng tự chẩn đoán những lỗi thường gặp.

---

## 2. Authentication, authorization và TLS khác nhau thế nào?

### 2.1. Authentication: bạn là ai?

Client gửi bằng chứng danh tính để server xác nhận. Với MongoDB, hai trường hợp quan trọng:

- **SCRAM**: username và password, thông qua giao thức challenge-response có sử dụng salt/khóa dẫn xuất.
- **MONGODB-X509**: client trình chứng chỉ X.509 được hệ thống tin cậy, server xác thực và ánh xạ danh tính chứng chỉ tới một MongoDB user.

Các cơ chế khác có thể tồn tại theo edition/deployment và tích hợp danh tính doanh nghiệp, nhưng bài này tập trung vào SCRAM và X.509.

### 2.2. Authorization: được làm gì?

Sau khi xác thực thành công, MongoDB kiểm tra quyền từ role.

Ví dụ:

```javascript
{
  user: "app_reader",
  roles: [
    { role: "read", db: "commerce" }
  ]
}
```

Người dùng này có quyền đọc tương ứng với role trên database `commerce`; không tự có quyền `readWrite` hoặc quản trị database khác.

Một user có thể được lưu ở database `admin` nhưng được cấp role trên `commerce`. **Vị trí lưu user không phải phạm vi quyền duy nhất.**

### 2.3. TLS: kết nối được bảo vệ như thế nào?

TLS giải quyết vấn đề khác:

- Mã hóa traffic đi qua mạng.
- Client xác minh server là endpoint dự kiến qua certificate/CA/hostname.
- Khi cấu hình mutual TLS, server có thể yêu cầu và xác minh client certificate.

TLS server authentication **không mặc định** có nghĩa MongoDB user đã đăng nhập bằng X.509. Một kết nối TLS vẫn có thể dùng SCRAM để xác thực user.

### 2.4. Bảng so sánh

| Câu hỏi | Thành phần trả lời |
|---|---|
| Password dùng thuật toán xác thực nào? | SCRAM-SHA-256 hoặc SCRAM-SHA-1 |
| Server tra user `app_reader` ở đâu? | Authentication database, ví dụ `commerce` |
| Vì sao login thành công nhưng insert bị từ chối? | Authorization/role |
| Vì sao certificate server không khớp hostname? | TLS certificate verification |
| Vì sao X.509 client không đăng nhập được? | Client certificate, CA trust, DN mapping, `$external`, role |
| Vì sao `authSource=admin` khác `authSource=commerce`? | User là database-scoped identity |
| Cluster members xác thực nhau bằng gì? | Internal member authentication, ví dụ keyfile hoặc X.509 |
| TLS có thay SCRAM bằng X.509 tự động? | **Không** |

---

## 3. SCRAM là gì?

**SCRAM** viết tắt của *Salted Challenge Response Authentication Mechanism*.

MongoDB hỗ trợ cơ chế như:

- `SCRAM-SHA-256`.
- `SCRAM-SHA-1`.

**Ưu tiên SCRAM-SHA-256** cho triển khai mới khi driver/server hỗ trợ; SCRAM-SHA-1 chủ yếu có ý nghĩa tương thích hệ thống cũ.

### 3.1. Ý tưởng challenge-response

Trong mô hình đơn giản hóa:

1. Client cung cấp danh tính user.
2. Server và client trao đổi nonce/challenge, salt và thông tin cần thiết.
3. Client tạo proof bằng khóa dẫn xuất từ password; không gửi password như một trường dữ liệu plaintext đơn giản trong SCRAM exchange.
4. Server xác minh proof dựa trên credential đã lưu.
5. Client cũng có thể xác minh server proof theo giao thức.

```text
Java / mongosh                              MongoDB server
     │                                          │
     │ user + client nonce                       │
     ├─────────────────────────────────────────>│
     │                server nonce + salt        │
     │<─────────────────────────────────────────┤
     │ client proof                              │
     ├─────────────────────────────────────────>│
     │                server proof / outcome     │
     │<─────────────────────────────────────────┤
     │                                          │
     └──── authenticated identity + role checks ┘
```

Đây là sơ đồ khái niệm, không phải bảng field chính xác của từng gói SCRAM.

### 3.2. Password có được gửi thẳng trên mạng không?

SCRAM sử dụng proof/challenge-response để tránh mô hình truyền password plaintext như một chuỗi trần trong bước xác thực.

**Nhưng điều này không thay thế TLS.** Traffic ứng dụng, dữ liệu query/kết quả và những thông tin khác vẫn cần bảo vệ bằng TLS. Không nên vận hành MongoDB chứa dữ liệu nhạy cảm qua mạng không có TLS chỉ vì đã bật SCRAM.

### 3.3. Salt, iteration và credential storage

SCRAM sử dụng cơ chế dẫn xuất khóa gắn với salt và số lần lặp để hỗ trợ xác minh password. MongoDB không cần lưu password plaintext để kiểm tra một proof hợp lệ.

Các tham số cụ thể và credential record do MongoDB quản lý; không chỉnh trực tiếp user credential trong các system collections.

**Không tự chế thuật toán SCRAM trong ứng dụng**: để MongoDB driver thực hiện handshake, server quản lý cơ chế credential và policy.

### 3.4. SHA-256 khác SHA-1

| Tiêu chí | SCRAM-SHA-256 | SCRAM-SHA-1 |
|---|---|---|
| Thuật toán nền | SHA-256 | SHA-1 |
| Lựa chọn cho hệ thống mới | Thường ưu tiên | Chỉ khi cần tương thích |
| Cần server/driver hỗ trợ | Có | Có |
| Có thay cho TLS? | Không | Không |
| Cần authentication database? | Có | Có |
| Dùng username/password? | Có | Có |

MongoDB có cơ chế negotiation/default tùy phiên bản và cách user được tạo. Nếu muốn bảo đảm dùng một cơ chế cụ thể, có thể chỉ định `authMechanism=SCRAM-SHA-256` trong URI hoặc MongoCredential tương ứng.

Không tự kết luận “cứ đặt SCRAM-SHA-256 là tài khoản cũ sẽ đăng nhập được”; credential của user phải phù hợp với cơ chế được yêu cầu.

### 3.5. SASLprep và password semantics

SCRAM-SHA-256 có những quy tắc xử lý password liên quan chuẩn hóa ký tự theo cơ chế hỗ trợ. Không nên tự trim, lowercase hoặc Unicode-normalize password trong ứng dụng trước khi đưa cho driver.

Password là **bí mật nguyên vẹn theo quy tắc của server/driver**, không phải tên người dùng hay search key.

---

## 4. Authentication database: khái niệm dễ nhầm nhất

Trong MongoDB, tên user có **ngữ cảnh database dùng để xác thực**. Hai user:

```text
admin.app_service
commerce.app_service
```

không mặc nhiên là cùng một identity, dù username giống nhau.

Nếu tạo:

```javascript
use admin

db.createUser({
  user: "app_service",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

thì credential của `app_service` nằm ở **authentication database `admin`**, dù role cấp quyền cho database `commerce`.

Muốn đăng nhập đúng user này từ ứng dụng Java:

```text
mongodb://app_service:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=admin
```

Trong URL trên:

- `app_service` là username.
- `/commerce` là **default database** dùng làm ngữ cảnh kết nối.
- `authSource=admin` là database server dùng để tra credential của `app_service`.

**Hai database ở đây phục vụ hai vai trò khác nhau.**

### 4.1. Auth source không phải database sẽ được phép truy cập

Một account xác thực trong `admin` có thể được cấp quyền trên `commerce`:

```javascript
{
  user: "app_service",
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
}
```

Sau login:

- User có thể thực hiện thao tác được role `readWrite` cho phép trên `commerce`.
- User không tự có quyền admin hay root chỉ vì authentication database là `admin`.
- Nếu query sang một database khác không được cấp role, server có thể trả `Unauthorized`.

### 4.2. User lưu trong chính application database

Có thể tạo user ở `commerce`:

```javascript
use commerce

db.createUser({
  user: "app_service",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

Khi đó:

```text
mongodb://app_service:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=commerce
```

hoặc URI tương đương theo quy tắc default auth database.

Đặt user ở `admin` hay database ứng dụng là quyết định quản trị danh tính/role, không phải tự động quyết định mức đặc quyền.

### 4.3. Giá trị mặc định của authSource trong URI thông thường

Với URI chuẩn và cơ chế username/password:

- Nếu chỉ định `authSource`, driver dùng database đó.
- Nếu không chỉ định `authSource` nhưng URI có thành phần database, database đó thường trở thành default authentication database.
- Nếu cả hai đều không có, default thường là `admin`.

Ví dụ:

| Connection string | Authentication database được dùng |
|---|---|
| `mongodb://u:p@host/commerce?authSource=admin` | `admin` |
| `mongodb://u:p@host/commerce` | `commerce` |
| `mongodb://u:p@host/?authSource=commerce` | `commerce` |
| `mongodb://u:p@host/` | `admin` |
| `mongodb://u:p@host/commerce?authSource=commerce` | `commerce` |

Bảng mô tả URI chuẩn theo những quy tắc phổ biến của SCRAM. Với `mongodb+srv` và DNS TXT connection options/managed provider, cần kiểm tra URI effective configuration trước khi giả định các default.

### 4.4. Vì sao login thất bại với đúng password?

Giả sử `app_service` được tạo tại `admin`.

URI sai:

```text
mongodb://app_service:<PASSWORD>@host:27017/commerce
```

Driver có thể tra credential ở `commerce`, không tìm đúng user/password, nên thất bại.

URI đúng:

```text
mongodb://app_service:<PASSWORD>@host:27017/commerce?authSource=admin
```

**Cách sửa là chỉ định authSource đúng với nơi tạo user**, không phải cấp role root hoặc tạo trùng thêm user chỉ để “thử xem”.

### 4.5. authSource khác database được chọn sau connect

Trong `mongosh`:

```javascript
use commerce
db.orders.findOne()
```

Lệnh `use commerce` thay đổi database context trong shell; nó **không tự thay đổi authentication identity đã xác thực lúc kết nối**.

Một session được xác thực là `admin.app_service` vẫn là cùng user đó khi chuyển sang `commerce` hoặc `reports`.

---

## 5. Chuẩn bị bài lab SCRAM an toàn

Ví dụ này dành cho MongoDB Server bạn quản lý hoặc một local test instance có quyền cấu hình security.

**Không đưa password thật vào repository, ticket, shell history hoặc screenshot.** Dùng `passwordPrompt()` của `mongosh` hoặc secret manager. Đừng chạy thao tác tạo user/đổi authorization trên production nếu chưa có runbook và backup đường truy cập quản trị.

### 5.1. Tạo user quản trị cho lab

Giả sử lab MongoDB chưa bật authentication hoặc vừa được dựng và chưa có user, người quản trị kết nối qua cơ chế hợp lệ để khởi tạo user.

```javascript
use admin

db.createUser({
  user: "lab_user_admin",
  pwd: passwordPrompt(),
  roles: [
    { role: "userAdminAnyDatabase", db: "admin" }
  ]
});
```

Role `userAdminAnyDatabase` có quyền quản lý user trên nhiều database, nên chỉ dùng cho tài khoản quản trị được bảo vệ; **không gán cho service ứng dụng**.

Trong production, ưu tiên tài khoản quản trị và roles được cấp theo chính sách least privilege, có audit và rotation.

### 5.2. Bật authorization

Một ví dụ cấu hình `mongod.conf` trong lab:

```yaml
security:
  authorization: enabled
```

Thao tác thay đổi file config/restart MongoDB cần quyền host và có thể ảnh hưởng kết nối hiện tại. Chỉ thực hiện trên môi trường lab đã kiểm soát.

Nếu máy có nhiều process replica set/sharded, phải thiết kế **internal member authentication** và startup sequencing phù hợp; không chỉ bật authorization tùy tiện ở một node rồi coi cluster đã được cấu hình an toàn.

### 5.3. Localhost exception

MongoDB có cơ chế **localhost exception** cho giai đoạn bootstrap khi access control được bật và hệ thống chưa có user/role, giúp tạo user đầu tiên từ localhost trong điều kiện hỗ trợ.

Những điểm quan trọng:

- Đây là một ngoại lệ khởi tạo có giới hạn, **không phải cơ chế admin login thường xuyên**.
- Sau khi tạo user phù hợp, ngoại lệ không còn là cách đăng nhập tùy ý.
- Có thể cấu hình để vô hiệu hóa nó; hành vi phụ thuộc deployment/version.
- Không cấu hình mở network công khai để “dùng localhost exception”.
- Không nên dựa vào localhost exception để khôi phục production khi không còn credential; cần runbook riêng.

### 5.4. Đăng nhập user quản trị

Trong shell (cú pháp command-line minh họa):

```bash
mongosh "mongodb://127.0.0.1:27017/admin" --username lab_user_admin --authenticationDatabase admin --password
```

Tùy phiên bản shell, `--password` không cung cấp giá trị có thể mở password prompt. Không ghi password trực tiếp trên command line vì có thể bị lộ trong lịch sử lệnh/process listing.

### 5.5. Tạo user ứng dụng trong database commerce

Sau khi admin authenticated:

```javascript
const commerce = db.getSiblingDB("commerce");

commerce.createUser({
  user: "app_reader",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "commerce" }
  ]
});

commerce.createUser({
  user: "app_writer",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

Hai user này được lưu trong **authentication database `commerce`**.

### 5.6. Kết nối thử đúng authSource

```bash
mongosh "mongodb://127.0.0.1:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256" --username app_reader --password
```

Trong shell:

```javascript
db.runCommand({ connectionStatus: 1 });
db.getName();
db.getCollectionNames();
```

Lệnh `connectionStatus` có thể cho biết các user/role đã xác thực trong session; phần role/privilege trả về phụ thuộc permissions và option command.

**Điểm kiểm tra:** `db.getName()` trả `commerce` chỉ cho biết database context. Để biết authenticated user, xem `connectionStatus`; không dùng `db.getName()` để suy ra authSource.

### 5.7. Kiểm tra least privilege

Với `app_reader`:

```javascript
db.orders.findOne();
```

Query read có thể được phép trong giới hạn role. Nhưng:

```javascript
db.orders.insertOne({
  _id: "lab-order-1",
  status: "NEW"
});
```

phải bị từ chối nếu user chỉ có role `read` và không có quyền ghi bổ sung.

Đây là ví dụ về **authorization failure** sau khi authentication đã thành công.

### 5.8. Những user vừa tạo có thể dùng cơ chế SCRAM nào?

Tùy server version, user create/update options và credential mechanisms, MongoDB có thể lưu credential cho những SCRAM mechanisms khác nhau.

Khi ứng dụng bắt buộc `SCRAM-SHA-256`, phải bảo đảm account được tạo hỗ trợ nó. Có thể chỉ định mechanisms khi tạo user trong môi trường hỗ trợ:

```javascript
db.getSiblingDB("commerce").createUser({
  user: "sha256_service",
  pwd: passwordPrompt(),
  mechanisms: ["SCRAM-SHA-256"],
  roles: [
    { role: "read", db: "commerce" }
  ]
});
```

Trong những MongoDB versions phù hợp, server sẽ lưu credential đáp ứng cơ chế chỉ định.

Nếu tài khoản cũ không có credential mechanism ấy, chỉ thêm `authMechanism=SCRAM-SHA-256` vào connection string có thể gây lỗi login.

---

## 6. Kết nối SCRAM bằng mongosh và connection string

### 6.1. URI đầy đủ

```text
mongodb://USERNAME:PASSWORD@HOST:27017/DEFAULT_DB?authSource=AUTH_DB&authMechanism=SCRAM-SHA-256
```

Ví dụ minh họa với user đã được tạo trong `commerce`:

```text
mongodb://app_reader:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256
```

**Không sử dụng ký hiệu `<PASSWORD>` như literal secret**; đó chỉ là placeholder.

Nếu bạn dùng URI có username/password thực, password cần được percent-encode theo quy tắc URI. Trong ví dụ thực hành nên nhập password qua prompt thay vì nhúng URI.

### 6.2. Password có ký tự đặc biệt

Trong URI, các ký tự như:

- `@`
- `:`
- `/`
- `?`
- `#`
- `[`
- `]`
- `%`

có thể làm sai cú pháp nếu không percent-encode đúng.

Ví dụ ý tưởng:

```text
Password gốc:  S3cr@t/Value
Dạng URL-safe: S3cr%40t%2FValue
```

Đừng tự viết bộ encode bằng phép thay thế vài ký tự thiếu trường hợp. Dùng URI-encoding API của ngôn ngữ lập trình hoặc MongoDB driver credentials API, và đọc secret từ kênh bảo mật.

### 6.3. SCRAM trong TLS connection

Ví dụ URI an toàn theo thông lệ:

```text
mongodb://app_reader:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256&tls=true
```

TLS xử lý mã hóa/xác minh server; SCRAM xác thực user.

Nếu CA của server không nằm trong trust store client, bạn cần cấu hình trust CA một cách hợp lệ. **Không bật `tlsInsecure` hoặc `tlsAllowInvalidCertificates` trên production để vượt lỗi certificate.**

### 6.4. SRV URI

Managed deployments có thể cung cấp:

```text
mongodb+srv://USERNAME:PASSWORD@cluster.example.mongodb.net/commerce?authSource=admin
```

Driver dùng DNS SRV/TXT theo driver spec. Không tự biến hostname `mongodb+srv` thành single-node host hoặc bỏ các options mà provider yêu cầu.

Luôn xác minh **authSource thực tế**, đặc biệt khi user được tạo trong `admin` nhưng application DB là `commerce`.

---

## 7. Quyền quản trị user và user lifecycle

### 7.1. Xem user trong authentication database

Với tài khoản có quyền thích hợp:

```javascript
use commerce

db.getUsers();
db.getUser("app_reader");
```

`getUsers()` trong database hiện tại không phải lệnh tìm mọi user toàn cluster.

Muốn xem user `admin.app_service`, chuyển sang `admin` hoặc truy vấn theo namespace tương ứng, nếu quyền cho phép.

### 7.2. Tạo user ở admin, role ở commerce

```javascript
use admin

db.createUser({
  user: "commerce_service",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

Khi đó:

```text
authSource = admin
granted role db = commerce
default database in URI can = commerce
```

Một số hệ thống tập trung user application trong `admin` để quản lý; các hệ thống khác đặt user trong database ứng dụng. Chọn theo chính sách và vận hành, **không coi admin user database đồng nghĩa root privileges**.

### 7.3. Đổi password

Trong authentication database của user, với quyền thích hợp:

```javascript
use commerce

db.changeUserPassword(
  "app_reader",
  passwordPrompt()
);
```

Lưu ý:

- Password thay đổi ảnh hưởng các lần xác thực mới.
- Đường triển khai/connection pool có thể giữ connection authenticated hiện có trong một thời gian, tùy driver và deployment.
- Rotation cần có cách tránh gián đoạn, đặc biệt nhiều service đang dùng chung account (nên tránh dùng chung user).
- Không log password mới.

### 7.4. Đổi roles

```javascript
use commerce

db.updateUser("app_reader", {
  roles: [
    { role: "read", db: "commerce" }
  ]
});
```

Trong production, hãy đánh giá tác động tới những query hiện chạy và triển khai theo cơ chế thay đổi quyền của tổ chức.

### 7.5. Vì sao không sửa trực tiếp system.users?

MongoDB quản lý credential, roles và metadata user qua lệnh quản trị. **Không update trực tiếp các collections nội bộ để đổi password hoặc roles**; dùng `createUser`, `updateUser`, `changeUserPassword`, `dropUser` theo quyền và runbook.

---

## 8. Chứng chỉ TLS và X.509: hai vai trò không được trộn lẫn

**X.509** là chuẩn về chứng chỉ khóa công khai. Trong MongoDB, chứng chỉ xuất hiện ở ít nhất hai ngữ cảnh:

1. **TLS transport**: máy khách xác minh server certificate; có thể dùng client certificate khi mutual TLS.
2. **MONGODB-X509 authentication**: MongoDB ánh xạ danh tính từ client certificate tới user có role, thay cho username/password SCRAM.

Đây là hai ngữ cảnh khác nhau dù đều sử dụng chứng chỉ.

### 8.1. One-way TLS

```text
Client                            MongoDB server
  │                                     │
  │──────── TLS handshake ─────────────>│
  │<──────── Server certificate ────────│
  │                                     │
  │ Verify CA + hostname + dates        │
  │ Establish encrypted channel         │
  │                                     │
  │──── SCRAM username/password proof ─>│
  │<──── Authentication result ─────────│
```

Trong trường hợp này:

- Server trình certificate.
- Client xác minh certificate.
- Client **không cần gửi client certificate** nếu server cho phép kết nối TLS không có client cert.
- MongoDB user vẫn xác thực bằng SCRAM.
- Authorization vẫn xét roles.

### 8.2. Mutual TLS + MONGODB-X509

```text
Client                            MongoDB server
  │                                     │
  │──────── TLS handshake ─────────────>│
  │<──────── Server certificate ────────│
  │──────── Client certificate ────────>│
  │                                     │
  │ Client validates server             │
  │ Server validates client             │
  │                                     │
  │──── MONGODB-X509 authentication ────>│
  │ Server maps certificate DN to user  │
  │ in $external and checks roles       │
  │<──── Authentication result ─────────│
```

Trong mutual TLS, server và client có thể xác minh chứng chỉ của nhau. Nhưng **có TLS client cert không tự tạo MongoDB application user**; muốn xác thực bằng MONGODB-X509 cần cấu hình mechanism/user mapping phù hợp.

### 8.3. Bảng so sánh

| Thành phần | TLS server cert | TLS client cert | MongoDB X.509 user |
|---|---|---|---|
| Chủ thể | Server | Ứng dụng/client | MongoDB principal |
| Dùng để làm gì? | Xác minh endpoint server | Xác minh danh tính client ở TLS | Cấp roles/authorization |
| Lưu ở đâu? | Server PEM/key | Client PEM/key hoặc key store | User trong `$external` |
| Có password MongoDB? | Không liên quan | Không liên quan | Không yêu cầu SCRAM password |
| Có liên quan CA trust? | Có | Có | Có, qua TLS/client cert trust |
| Có tự cấp readWrite? | Không | Không | Chỉ khi user được gán role |

### 8.4. CA certificate và leaf certificate

Trong một PKI thông thường:

- **CA certificate** là chứng chỉ nhà phát hành mà client/server tin tưởng.
- **Server certificate** là leaf cert dùng xác minh endpoint MongoDB.
- **Client certificate** là leaf cert đại diện client khi mutual TLS.
- **Private key** thuộc về certificate holder và phải được giữ kín.

Không đưa private key vào repository hoặc gửi qua chat/email không được phê duyệt. Một server cert không phải là “password chung” cho mọi client.

---

## 9. Xác minh server certificate khi dùng TLS

Một TLS client nên kiểm tra:

1. Certificate chain được CA tin cậy ký hợp lệ.
2. Certificate còn trong khoảng thời gian hiệu lực.
3. DNS name/IP kết nối khớp danh tính server được ghi trong certificate, thường qua **Subject Alternative Name (SAN)**.
4. Key usage/extended key usage phù hợp.
5. Certificate không bị thu hồi theo cơ chế/thiết lập đang dùng, nếu có.
6. Private key tương ứng phía server vẫn được giữ bí mật.

### 9.1. SAN và hostname mismatch

Giả sử certificate server có:

```text
DNS:mongo1.example.internal
DNS:mongo1
```

Client kết nối:

```text
mongodb://mongo1.example.internal:27017/?tls=true
```

có thể khớp DNS name khi CA và các điều kiện khác hợp lệ.

Nhưng kết nối trực tiếp qua:

```text
mongodb://192.0.2.10:27017/?tls=true
```

có thể thất bại hostname verification nếu certificate không chứa IP SAN tương ứng.

**Cách sửa:** dùng hostname đúng với cert hoặc cấp lại certificate có SAN phù hợp; không bật tùy chọn bỏ kiểm tra hostname trên production.

### 9.2. Kiểm tra PEM bằng openssl

Ví dụ cho người quản trị trong môi trường được phép:

```bash
openssl x509 -in server.pem -noout -subject -issuer -dates -ext subjectAltName
```

Nếu server PEM chứa cả private key, lệnh trên chỉ in thông tin certificate, không in private key. Nhưng file PEM vẫn là bí mật hệ thống và phải được bảo vệ quyền truy cập.

Có thể xác minh certificate chain với CA file phù hợp:

```bash
openssl verify -CAfile root-ca.pem server-cert.pem
```

Các lệnh kiểm tra certificate không thay thế việc kiểm tra connectivity/TLS negotiation thực tế từ driver.

### 9.3. Server configuration với TLS

Ví dụ cấu hình khái niệm trong `mongod.conf`:

```yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongo/server.pem
    CAFile: /secure/mongo/ca.pem
    allowConnectionsWithoutCertificates: true

security:
  authorization: enabled
```

Giải thích:

- `requireTLS` yêu cầu TLS cho incoming connections.
- `certificateKeyFile` là PEM chứa server certificate/private key theo cấu hình MongoDB.
- `CAFile` chứa chứng chỉ CA tin cậy, dùng trong những trường hợp phù hợp để xác minh peer cert.
- `allowConnectionsWithoutCertificates: true` cho phép TLS client không có client cert kết nối khi service dùng **SCRAM** thay cho MONGODB-X509.
- `authorization: enabled` bật kiểm tra auth/roles.

**Quan trọng:** Đây là mô hình cấu hình đơn giản minh họa. Trên replica set hoặc sharded cluster còn phải cấu hình internal authentication, hostname và TLS trust giữa các thành viên. Không áp dụng nguyên bản vào production khi chưa xét topology.

### 9.4. SCRAM client dùng TLS nhưng không có client certificate

Khi MongoDB server được cấu hình cho phép TLS client không cung cấp client cert, client có thể:

1. Xác minh server certificate.
2. Thiết lập kênh TLS.
3. Dùng SCRAM-SHA-256 với username/password.
4. Nhận quyền theo roles.

Đây là cấu hình hợp lệ. **Không cần tạo X.509 user chỉ vì đã bật TLS.**

---

## 10. MONGODB-X509: xác thực MongoDB user bằng client certificate

Khi dùng `MONGODB-X509`, server xác định danh tính từ client certificate, thay vì xác thực user bằng SCRAM password.

Đặc điểm:

- Client kết nối qua TLS.
- Client cung cấp certificate và private key tương ứng.
- Certificate phải phù hợp với trust chain và yêu cầu xác minh của server.
- MongoDB ánh xạ danh tính X.509 **Distinguished Name (DN)** tới user.
- User được quản lý trong authentication database **`$external`**.
- Roles quyết định thao tác được phép sau authentication.

### 10.1. Tại sao $external?

SCRAM users được tạo và xác thực bằng credential MongoDB ở một database như `admin` hoặc `commerce`.

X.509 identity đến từ cơ chế xác thực bên ngoài hệ password database, nên MongoDB sử dụng **`$external`** làm authentication database.

```text
SCRAM:
  username/password  ──> admin hoặc commerce

MONGODB-X509:
  client certificate  ──> $external
```

**Không tạo X.509 user với password trong `commerce` chỉ vì user ấy cần quyền đọc `commerce`.**

### 10.2. Distinguished Name của certificate

Một client certificate có subject DN, ví dụ minh họa:

```text
CN=payments-reader,OU=Services,O=Example
```

Trong thực tế, format DN phải **khớp chính xác định danh mà MongoDB dùng** theo quy tắc canonicalization/format được phiên bản server yêu cầu, thường liên quan RFC 2253.

Cần đặc biệt chú ý:

- Thứ tự và escaping các thành phần DN.
- Tên/tổ chức được cấp đúng trong certificate.
- Có nhiều certificate nhưng dùng cùng subject DN sẽ ảnh hưởng mapping identity.
- Certificate rotation có thay subject DN hay không.
- Không tự biến một CN ngắn thành full DN nếu server kỳ vọng identity đầy đủ.

### 10.3. Xem subject và issuer

Người quản trị có thể chạy:

```bash
openssl x509 -in client.pem -noout -subject -issuer -dates -nameopt RFC2253
```

Kết quả phải được đối chiếu với cách MongoDB chuẩn hóa subject của client certificate. Không lấy output trong một format khác rồi “đoán” username X.509.

### 10.4. Tạo user X.509 trong $external

Giả sử một client certificate được phát hành và MongoDB dùng username canonical phù hợp là:

```text
CN=payments-reader,OU=Services,O=Example
```

Admin đã authenticated bằng một account có quyền quản lý user có thể tạo:

```javascript
const externalDb = db.getSiblingDB("$external");

externalDb.runCommand({
  createUser: "CN=payments-reader,OU=Services,O=Example",
  roles: [
    { role: "read", db: "commerce" }
  ]
});
```

**Không có `pwd`** trong user X.509 này. Certificate là nguồn xác thực danh tính, không phải một SCRAM password.

Nếu certificate DN không khớp canonical username do server dùng, authentication có thể thất bại dù CA chain hợp lệ.

### 10.5. Kết nối bằng mongosh

Ví dụ, client certificate/private key được giữ trong file PEM có quyền đọc hạn chế:

```bash
mongosh "mongodb://mongo1.example.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external" --tlsCAFile /secure/certs/ca.pem --tlsCertificateKeyFile /secure/certs/payments-client.pem
```

Giải thích:

- `tls=true` bật TLS.
- `authMechanism=MONGODB-X509` chọn xác thực MongoDB user bằng X.509.
- `authSource=%24external` là URI-encoded representation của `$external`.
- `--tlsCAFile` giúp client xác minh server chain theo cấu hình.
- `--tlsCertificateKeyFile` cung cấp client certificate và private key.
- Không cần password MongoDB cho X.509 user.

Nếu chính sách của driver/mongosh yêu cầu username explicit, giá trị username phải khớp canonical DN của client certificate; không đưa username/password tùy ý như SCRAM.

### 10.6. X.509 user vẫn cần roles

Certificate được chấp nhận ở TLS không đồng nghĩa đã có quyền đọc/ghi. Server còn cần:

1. X.509 identity hợp lệ và ánh xạ tới user.
2. User có role trên database/collection ứng dụng.
3. Query/action nằm trong các privileges được cấp.

Ví dụ một certificate được ánh xạ tới `payments-reader` có role `read` trên `commerce` vẫn không có quyền `insert` nếu không được cấp quyền khác.

---

## 11. Vì sao client certificate hợp lệ mà MongoDB vẫn báo Authentication failed?

Đây là một bài toán nhiều tầng.

### 11.1. TLS handshake thất bại

Có thể do:

- Client certificate hết hạn.
- Client certificate không được CA mà server tin cậy ký.
- Private key không khớp certificate.
- Certificate chain thiếu intermediate CA.
- Extended Key Usage không phù hợp với client authentication.
- TLS version/cipher không tương thích.
- Server yêu cầu certificate nhưng client không gửi.
- Hostname của server certificate không khớp tên client dùng để kết nối.

Khi này lỗi có thể xuất hiện **trước** khi MongoDB authentication mechanism được thực thi.

### 11.2. TLS thành công nhưng MONGODB-X509 thất bại

Có thể do:

- Connection string vẫn đang dùng `SCRAM-SHA-256`.
- `authSource` không phải `$external`.
- User X.509 trong `$external` chưa được tạo.
- Subject DN được ghi sai thứ tự/canonical format.
- Username explicit không khớp client certificate.
- Server/driver/deployment không hỗ trợ hoặc không cho phép cơ chế được yêu cầu.

### 11.3. Authentication thành công nhưng Unauthorized

Đây là vấn đề khác:

- User chưa có role phù hợp.
- Role được cấp trên database khác.
- Command yêu cầu privilege không có trong role.
- Service thực hiện thao tác admin khi chỉ được cấp quyền read.

**Không chữa lỗi Unauthorized bằng cách tắt certificate validation.** Cần sửa role/authorization đúng mức.

---

## 12. Nội bộ replica set dùng X.509 khác client X.509

MongoDB có thể yêu cầu **internal member authentication** để các thành viên replica set/sharded cluster nhận biết nhau.

Các cách thường gặp:

- **Keyfile-based internal authentication**.
- **X.509-based internal authentication**.

Nhưng **X.509 member authentication** không hoàn toàn giống **MONGODB-X509 client user authentication**.

### 12.1. Hai mục đích

```text
Application ──(MONGODB-X509)──> Replica set
                                   │
                             Internal X.509
                                   │
                        Member A ←──→ Member B
```

- Application X.509: user trong `$external` có roles ứng dụng.
- Member X.509: các server mongod/mongos chứng thực tư cách thành viên cluster, liên quan `clusterAuthMode` và điều kiện certificate dành cho members.

### 12.2. clusterAuthMode

Một số deployment sử dụng:

```yaml
security:
  authorization: enabled
  clusterAuthMode: x509
```

trong cấu hình hoàn chỉnh có TLS và certificate phù hợp, trên các server/versions hỗ trợ.

**Không áp dụng snippet này một mình để “bật X.509 cho app”.** Chuyển cluster sang member authentication X.509 cần:

- Chuẩn bị certificate trên toàn bộ members.
- Trust CA và EKU/DN đáp ứng yêu cầu member authentication.
- Lập thứ tự rolling transition an toàn.
- Bảo đảm topology/routers tương thích.
- Runbook rollback.
- Kiểm tra khả năng tiếp tục giao tiếp giữa các members.

Nếu cấu hình sai, replica set có thể mất khả năng trao đổi nội bộ, gây gián đoạn dịch vụ.

### 12.3. Không dùng một certificate cho mọi mục đích

Về nguyên tắc bảo mật, nên phân tách identity và private keys:

- Certificate server endpoint.
- Certificate ứng dụng dùng client authentication.
- Certificate member authentication theo chính sách cluster.

Việc một deployment cho phép tái sử dụng một certificate kỹ thuật không có nghĩa đó là thiết kế tốt về vận hành/rotation/least privilege.

### 12.4. Keyfile không phải SCRAM user password

Internal keyfile là secret dùng cho member authentication, **không phải username/password của `app_reader`**. Không đưa keyfile vào connection URI ứng dụng.

---

## 13. So sánh SCRAM và MONGODB-X509

| Tiêu chí | SCRAM | MONGODB-X509 |
|---|---|---|
| Bằng chứng danh tính | Username/password | Client certificate/private key |
| Authentication database | Database nơi user được tạo, ví dụ `admin` hoặc `commerce` | `$external` |
| User có `pwd`? | Có khi tạo user | Không dùng SCRAM password |
| Có cần TLS? | Nên dùng TLS để bảo vệ traffic | TLS là một phần thiết yếu của flow X.509 |
| Certificate client bắt buộc? | Không, nếu server cho phép TLS client không cert | Có |
| Rotation | Password/credential rotation | Certificate/private key rotation |
| User roles | Có | Có |
| Secret cần bảo vệ | Password/token | Private key/key store password |
| Các lỗi phổ biến | authSource sai, password sai, mechanism mismatch | CA/DN/cert/`$external` mismatch |
| Dùng cho app thông thường | Rất phổ biến | Phù hợp khi tổ chức có PKI/mTLS |
| Có thay authorization? | Không | Không |

### 13.1. Khi nào chọn SCRAM?

- Môi trường cần tích hợp đơn giản.
- Có secret manager quản lý password.
- Ứng dụng dùng MongoDB drivers thông dụng.
- Chính sách xác thực bằng password được chấp nhận.
- TLS được triển khai đầy đủ.

### 13.2. Khi nào chọn MONGODB-X509?

- Doanh nghiệp đã có PKI và quy trình cấp/thu hồi/rotation certificate.
- Service-to-service identity dựa trên mutual TLS.
- Muốn dùng khóa riêng/certificate thay SCRAM password.
- Có khả năng quản lý DN mapping/roles trong `$external`.
- Có observability về TLS handshake, certificate expiry và revocation.

### 13.3. X.509 không mặc định mạnh hơn mọi SCRAM deployment

Security phụ thuộc toàn bộ hệ thống:

- Khóa riêng có bị đánh cắp không?
- Certificate có được luân chuyển/thu hồi đúng lúc?
- CA trust chain có quá rộng không?
- Roles có theo least privilege không?
- SCRAM password có đủ mạnh, được bảo vệ và dùng qua TLS không?
- Service có log credentials hoặc không?

Chọn cơ chế dựa trên khả năng vận hành bảo mật thực tế, không chỉ tên thuật toán.

---

## 14. Java Sync Driver: SCRAM-SHA-256

### 14.1. Dùng connection URI

Ví dụ Java app lấy URI từ secret manager hoặc environment:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ScramUriExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must be set securely");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("commerce");
            MongoCollection<Document> orders =
                    db.getCollection("orders");

            Document sample = orders.find().first();
            System.out.println(sample == null ? "No data" : "Read success");
        }
    }
}
```

Một URI SCRAM có dạng:

```text
mongodb://app_reader:<SECRET>@mongo1.example.internal:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256&tls=true
```

**Không commit URI chứa password thật vào git**. URI từ environment vẫn cần kiểm soát exposure qua process/container config và log.

### 14.2. Dùng MongoCredential để tránh nhúng password trong URI

Java driver cung cấp `MongoCredential`.

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.ServerAddress;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public final class ScramCredentialExample {
    public static void main(String[] args) {
        String password = System.getenv("MONGO_APP_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGO_APP_PASSWORD");
        }

        MongoCredential credential =
                MongoCredential.createScramSha256Credential(
                        "app_reader",
                        "commerce",
                        password.toCharArray()
                );

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyToClusterSettings(builder ->
                                builder.hosts(List.of(
                                        new ServerAddress(
                                                "mongo1.example.internal",
                                                27017)
                                )))
                        .credential(credential)
                        .applyToSslSettings(builder ->
                                builder.enabled(true))
                        .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoDatabase db = client.getDatabase("commerce");
            db.runCommand(new Document("ping", 1));
            System.out.println("Connected");
        }
    }
}
```

Ở đây:

- `createScramSha256Credential(user, source, password)` xác định rõ authentication database là `commerce`.
- `credential(...)` cài đặt cơ chế SCRAM với user.
- `enabled(true)` bật TLS; server certificate vẫn phải được JVM trust store xác minh.
- Không cần encode password vào connection URI.

**Lưu ý triển khai:** Với replica set/sharded cluster, không dùng một host riêng lẻ như ví dụ rồi coi đó là production topology; cấu hình seed list/replicaSet/SRV, TLS trust và timeouts theo hạ tầng thực tế.

### 14.3. Tách authSource khỏi getDatabase

Hai dòng sau không bắt buộc phải trùng database:

```java
MongoCredential credential =
        MongoCredential.createScramSha256Credential(
                "commerce_service",
                "admin",
                password.toCharArray()
        );

MongoDatabase db = client.getDatabase("commerce");
```

User được tạo trong `admin` nhưng có role trên `commerce`. Authentication ở `admin`; query ở `commerce`.

### 14.4. Đừng xử lý password như search string

Password không được trim/lowercase/Unicode-normalize tùy tiện trước khi chuyển cho MongoDB driver. Secret manager cần cung cấp đúng bí mật; ứng dụng không nên log nó.

### 14.5. Java và trust store

Khi server certificate được CA công khai/enterprise CA cấp, JVM phải tin CA đó. Nếu CA nội bộ chưa nằm trong default trust store, cần trust store được quản trị triển khai đúng.

Ví dụ JVM options ở mức minh họa:

```text
-Djavax.net.ssl.trustStore=/secure/client/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<TRUSTSTORE_SECRET>
```

Không để trust store password thực trong startup scripts đọc được công khai hay process arguments nếu chính sách bảo mật không cho phép. Cân nhắc SSLContext tùy biến hoặc secret injection mechanism.

---

## 15. Java Sync Driver: X.509 với client certificate

Java driver có thể xác thực bằng MONGODB-X509 khi:

- TLS đã bật.
- JVM/client có certificate/private key để trình.
- Server tin CA và chấp nhận client certificate.
- Authentication mechanism là MONGODB-X509.
- Source là `$external`.
- MongoDB đã có user/role mapping phù hợp.

### 15.1. Kết nối qua X.509 URI

```text
mongodb://mongo1.example.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external
```

Không có SCRAM password trong URI.

### 15.2. Java client dùng SSL key store và trust store

Một cách phổ biến là cấu hình Java TLS ở JVM startup theo chính sách:

```text
-Djavax.net.ssl.keyStore=/secure/client/mongo-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
-Djavax.net.ssl.keyStorePassword=<KEYSTORE_SECRET>

-Djavax.net.ssl.trustStore=/secure/client/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<TRUSTSTORE_SECRET>
```

Ý nghĩa:

- **Key store** chứa client private key + certificate chain.
- **Trust store** chứa CA để xác minh certificate của MongoDB server.

Nếu ứng dụng dùng custom `SSLContext`, các JVM defaults có thể bị thay thế bởi SSLContext được cung cấp; phải cấu hình nhất quán.

### 15.3. Java X.509 example

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class X509Example {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_X509_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_X509_URI is required");
        }

        // JVM TLS keyStore/trustStore được cấu hình lúc khởi động.
        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("commerce");
            db.runCommand(new Document("ping", 1));

            Document first = db.getCollection("orders")
                    .find()
                    .first();

            System.out.println(
                    first == null ? "Authenticated" : "Read success");
        }
    }
}
```

**Cẩn trọng:** Lệnh `ping` không đủ để chứng minh đã có role đọc `commerce`, vì semantics quyền của ping khác lệnh đọc collection. Phải kiểm tra thao tác đòi hỏi privilege thực sự hoặc `connectionStatus` theo quyền phù hợp.

### 15.4. Định danh username từ certificate

Tùy driver và configuration, user name có thể được suy ra từ certificate subject hoặc chỉ định rõ dưới dạng X.509 identity. Nếu chỉ định username, phải khớp DN canonical mà MongoDB chấp nhận; không dùng username tùy tiện như `app_reader` chỉ vì certificate CN có tên tương tự.

### 15.5. Client certificate hết hạn

Một lỗi hay gặp: Java app có keyStore chứa cert hết hạn, còn server certificate vẫn tốt.

Khi đó TLS handshake hoặc X.509 auth có thể thất bại. Phải kiểm tra cả:

- Server cert.
- Client cert.
- Intermediate CA chain.
- Trust store.
- Key store.
- Validity periods.
- Certificate subject DN.
- Role mapping trong `$external`.

---

## 16. Username, certificate subject và permission: ví dụ đối chiếu

Giả sử system có:

```text
Server endpoint:
  mongo1.example.internal

Application database:
  commerce

SCRAM user:
  username = app_reader
  authentication database = admin
  roles = read on commerce

X.509 user:
  subject DN = CN=svc-reader,OU=Services,O=Example
  authentication database = $external
  roles = read on commerce
```

### 16.1. SCRAM connection

```text
mongodb://app_reader:<SECRET>@mongo1.example.internal:27017/commerce?authSource=admin&authMechanism=SCRAM-SHA-256&tls=true
```

### 16.2. X.509 connection

```text
mongodb://mongo1.example.internal:27017/commerce?authSource=%24external&authMechanism=MONGODB-X509&tls=true
```

Ở X.509, client còn phải cung cấp certificate/private key qua mongosh/JVM/driver TLS settings.

### 16.3. Cùng role không có nghĩa cùng credential

Hai principal có thể cùng có role `read` nhưng:

- User danh tính khác.
- Authentication database khác.
- Secret cần quản lý khác.
- Rotation và revocation khác.
- Audit attribution khác.

Không coi một certificate là cách “chuyển đổi password” của cùng SCRAM user.

---

## 17. Quy trình troubleshoot: chia thành bốn lớp

### 17.1. Lớp 1: network và endpoint

Kiểm tra:

- DNS resolution có đúng không?
- Host/port khả dụng không?
- Firewall/security group có cho phép không?
- Replica set seed list/SRV có đúng topology không?
- TLS mode giữa client/server có tương thích không?

Nếu TCP không kết nối được, đừng bắt đầu bằng cách đổi authSource.

### 17.2. Lớp 2: TLS handshake

Kiểm tra:

- Server certificate chain và CA trust.
- Hostname trong SAN.
- Expiry/notBefore.
- TLS protocol/cipher.
- Client cert nếu server yêu cầu mutual TLS.
- EKU/clientAuth/serverAuth.
- Key file permissions và private key match.
- CA rotation hoặc cert replacement gần đây.

Lỗi TLS xảy ra **trước** SCRAM/X.509 auth success.

### 17.3. Lớp 3: authentication

Với SCRAM:

- Username đúng không?
- Password đúng không?
- User được tạo trong auth DB nào?
- `authSource` có đúng không?
- Mechanism có được user/server hỗ trợ không?
- Password bị URI parser hiểu sai vì thiếu percent encoding không?

Với X.509:

- `authMechanism=MONGODB-X509` đã được bật trong client chưa?
- `authSource=$external` có chính xác không?
- Client certificate được gửi không?
- DN canonical khớp user trong `$external` chưa?
- Deployment có chấp nhận X.509 không?

### 17.4. Lớp 4: authorization

Nếu kết nối/authentication đã thành công nhưng query báo `not authorized`:

- User có role đúng database/collection không?
- Command cần action nào?
- Role có bị thay đổi gần đây không?
- Có đang thao tác trên database khác với dự kiến không?
- Ứng dụng có trộn `default DB` với `authSource` không?

### 17.5. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Authentication failed với SCRAM | Sai password/username | Xác minh secret và user |
| Password đúng nhưng không login được | Sai `authSource` | Xem user được tạo tại database nào |
| SCRAM-SHA-256 fails, cơ chế khác hoạt động | Mechanism credential chưa phù hợp | Kiểm tra user/server/driver support |
| Login được nhưng insert Unauthorized | Role read-only | Cấp đúng role theo chính sách |
| TLS certificate verify failed | CA chain không trusted | Cấu hình CA/trust store hợp lệ |
| TLS hostname mismatch | SAN không có hostname kết nối | Dùng DNS đúng hoặc cấp lại cert |
| TLS handshake fail khi client SCRAM | Server bắt client cert | Kiểm tra yêu cầu mutual TLS |
| X.509 auth fail sau TLS success | DN mapping chưa có hoặc sai | Xem `$external` user và certificate subject |
| X.509 auth fail vì authSource | Dùng admin/commerce | Dùng `$external` |
| X.509 app có role nhưng vẫn fail | Client cert không gửi/không trusted | Kiểm tra PEM/keyStore/trust |
| Replica set bị ảnh hưởng sau clusterAuthMode | Member cert/trust không đồng bộ | Theo member-auth runbook |
| Một client chạy, client khác fail | CA/hostname/driver settings khác nhau | So sánh endpoint và TLS settings |
| Kết nối chỉ fail sau cert rotation | CA chain/DN/secret thay đổi | So sánh cert cũ/mới, user mapping |
| Quên password admin | Credential recovery cần quy trình riêng | Không tắt auth tùy tiện trên production |

---

## 18. Đo và xác minh mà không lộ secret

### 18.1. Xem identity hiện tại

Trong `mongosh` với một session authenticated:

```javascript
db.runCommand({ connectionStatus: 1 });
```

Có thể xem thông tin authenticated users và roles theo command response. Không in credential secret ra console.

### 18.2. Xem users trong database hiện tại

Với user quản trị được cấp quyền:

```javascript
db.getSiblingDB("admin").getUsers();
db.getSiblingDB("commerce").getUsers();
db.getSiblingDB("$external").getUsers();
```

Trong `$external`, cần thực hiện theo tính năng/permission của deployment; không phải tài khoản ứng dụng nào cũng có quyền liệt kê user.

### 18.3. Kiểm tra quyền bằng thao tác thực

Đối với `read` role:

```javascript
db.getSiblingDB("commerce").orders.findOne();
```

Đối với `readWrite`, có thể kiểm tra insert/update trên collection **lab** được ủy quyền, không làm thử trên dữ liệu nghiệp vụ thật.

### 18.4. Không dùng ping làm authorization test

```javascript
db.adminCommand({ ping: 1 });
```

Chỉ xác nhận khả năng liên lạc ở mức command này; không chứng minh user có quyền đọc `commerce.orders` hay tạo user.

### 18.5. Tránh tiết lộ qua log

Không ghi:

- Password.
- URI đầy đủ có embedded credentials.
- Client PEM private key.
- Key store password.
- Full certificate private contents.
- Secret manager token.
- SCRAM internal credential material.

Có thể log các thông tin đã sanitize:

- Endpoint/replica set name.
- Mechanism dự định.
- AuthSource đã định cấu hình.
- Tên principal đã xử lý theo policy (tránh PII).
- Error code/category.
- Fingerprint public certificate hoặc expiry nếu policy cho phép.

---

## 19. Certificate rotation và password rotation

### 19.1. SCRAM rotation

Một kế hoạch cơ bản:

1. Xác định account nào đang dùng credential.
2. Chuẩn bị secret mới trong secret manager.
3. Thử trên staging/canary.
4. Thực hiện rotation theo chính sách hỗ trợ.
5. Bảo đảm clients tái xác thực bằng secret mới.
6. Quan sát authentication error rate.
7. Thu hồi credential cũ/không còn dùng nếu có cơ chế dual account.
8. Audit ai thực hiện thay đổi và thời gian.

Với hệ thống cần zero-downtime, đôi khi dùng **hai service accounts chuyển đổi theo từng đợt** dễ quản lý hơn đổi password duy nhất mà mọi process đang sử dụng đồng thời. Nhưng phải đảm bảo roles và cleanup cẩn thận.

### 19.2. X.509 rotation

Một kế hoạch có thể gồm:

1. Chuẩn bị cert mới và private key mới, được CA phù hợp cấp.
2. Xem SAN/EKU/validity và subject DN.
3. Nếu DN đổi, chuẩn bị user mapping/roles tương ứng trong `$external`.
4. Đảm bảo server trust chain mới (có thể cần overlap CA cũ/mới).
5. Triển khai cert/key mới theo wave, restart/reload client theo API hỗ trợ.
6. Quan sát TLS handshake và auth errors.
7. Thu hồi cert cũ và cleanup user mapping.
8. Giám sát expiry và revocation policy.

**Certificate rotation không chỉ là copy PEM mới**. Nếu DN thay đổi, MongoDB X.509 user identity có thể thay đổi theo, khiến login fail hoặc roles khác.

### 19.3. CA rotation

Nếu thay CA:

- Client phải tin CA ký server certificate mới.
- Server phải tin CA ký client certificate mới.
- Cluster members có thể cần CA overlap trong rolling transition.
- Không thay tất cả cùng lúc mà không có kế hoạch kiểm thử và rollback.

### 19.4. Certificate expiry monitoring

Đừng đợi certificate hết hạn mới xử lý. Theo dõi:

- Days-to-expiry của server certificates.
- Days-to-expiry của X.509 client certificates.
- CA/intermediate expiry.
- Những pods/services dùng cert cũ.
- Authentication/TLS failure rates sau deploy.
- Thời gian cần để phát hành và rollout cert mới.

---

## 20. Một số tình huống vận hành thực tế

### 20.1. Ứng dụng dùng đúng password nhưng kết nối vào sai authSource

User được tạo ở:

```javascript
use admin
db.createUser({
  user: "commerce_app",
  pwd: passwordPrompt(),
  roles: [{ role: "readWrite", db: "commerce" }]
});
```

Sai:

```text
mongodb://commerce_app:<SECRET>@host/commerce
```

Nếu không có `authSource`, driver có thể chọn `commerce` làm authentication database.

Đúng:

```text
mongodb://commerce_app:<SECRET>@host/commerce?authSource=admin
```

### 20.2. Application TLS chạy thành công dù không có client cert

Server certificate hợp lệ, client trust CA, server cho phép TLS clients không có certificate, app dùng SCRAM.

Đây là **TLS encryption + SCRAM authentication**, không phải X.509 user authentication.

### 20.3. X.509 client certificate đã được CA tin cậy nhưng không đăng nhập được

Có thể chưa tạo user tương ứng ở `$external` hoặc DN mapping sai. TLS trust là một bước; MongoDB user authentication là bước tiếp theo.

### 20.4. Client có certificate nhưng vẫn dùng SCRAM

Chỉ cung cấp client cert trong TLS config không nhất thiết chuyển authentication mechanism thành `MONGODB-X509`. Nếu URI/MongoCredential vẫn cấu hình SCRAM, driver xác thực như SCRAM trong phạm vi cơ chế hỗ trợ.

### 20.5. Authenticated user không có quyền đọc

Một user trong `admin` được gán role trên `reports` nhưng ứng dụng query `commerce`. Dù authSource đúng và SCRAM thành công, truy vấn `commerce` vẫn Unauthorized.

### 20.6. Kết nối qua IP thay hostname

Cert chỉ có SAN DNS, client kết nối bằng IP khiến hostname verification thất bại. Sửa DNS/certificate cho khớp; không tắt hostname verification production.

### 20.7. Server TLS cert bị thay nhưng Java client lỗi

JVM trust store chưa có CA mới hoặc hostname SAN thay đổi. Cần so sánh trust chain/server cert, không vội đổi SCRAM password.

### 20.8. Replica set đổi internal auth mà ứng dụng mất kết nối

Nếu member auth cấu hình sai, cluster có thể mất primary/healthy topology. Đây là lỗi server-to-server authentication, không nhất thiết do credential ứng dụng.

---

## 21. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| `/commerce` trong URI luôn là authSource | Có thể có `authSource=admin` | Database context khác nơi tra user |
| User nằm trong admin là root | Role mới quyết định quyền | `admin.app` có thể chỉ read commerce |
| Password đúng là login chắc chắn được | Có thể sai authSource/mechanism | Kiểm tra đủ user/source/mechanism |
| SCRAM mã hóa toàn bộ traffic | SCRAM là xác thực | TLS bảo vệ đường truyền |
| Bật TLS là đã dùng MONGODB-X509 | TLS có thể đi cùng SCRAM | Chọn auth mechanism riêng |
| X.509 user có password | X.509 dựa trên certificate | User trong `$external` không có `pwd` SCRAM |
| Cert hợp lệ là có readWrite | Authorization tách biệt | Gán role đúng |
| Client cert và server cert giống nhau | Chứng thực hai phía khác nhau | Quản lý cert và private keys theo vai trò |
| CA file là user certificate | CA xác minh chain, không phải principal | Client leaf cert đại diện app |
| authSource của X.509 là commerce | X.509 dùng `$external` | Roles có thể ở commerce |
| Đổi DN không ảnh hưởng user | DN là identity mapping | Cần chuẩn bị user mapping mới |
| Cert hết hạn là lỗi SCRAM | TLS có thể fail trước auth | Kiểm tra TLS first |
| Tắt cert validation để chữa lỗi | Mất xác minh endpoint | Sửa chain/SAN/CA |
| Bật clusterAuthMode x509 để app dùng X.509 | Internal member auth là lớp khác | Tách member và app auth |
| Keyfile là password ứng dụng | Keyfile dành cho member auth | App dùng user credential riêng |
| ping success chứng minh readWrite | Ping không kiểm tra privileges tương ứng | Test thao tác có quyền thực |
| `use db` đổi identity | Session vẫn là cùng authenticated principal | Identity gắn với auth handshake |
| Lưu password ở URI trong git là được nếu repo private | Secret dễ rò qua log/history/backup | Secret manager, rotation |
| Dùng chung user cho mọi service | Khó audit/rotate/least privilege | Principal riêng từng workload |
| Tạo root cho app để hết Unauthorized | Quyền vượt nhu cầu | Sửa role tối thiểu |
| Một certificate cho mọi service | Khó cô lập và thu hồi | Identity/key riêng cho service |
| Cấu hình TLS cho một node là đủ cho replica set | Topology có nhiều endpoints | Đồng bộ cert/trust giữa members |

---

## 22. Thực hành A: SCRAM với hai authSource khác nhau

**Mục đích:** phân biệt authentication database và database nhận quyền.

1. Trong lab, tạo `app_reader` ở `commerce` với role `read` trên `commerce`.
2. Kết nối với `authSource=commerce` và password đúng.
3. Thử URI cùng username/password nhưng `authSource=admin`; ghi nhận authentication outcome.
4. Tạo một user **khác** `app_admin_source` trong `admin` với role `read` trên `commerce`.
5. Kết nối với `authSource=admin` và default DB `commerce`.
6. Kiểm tra `connectionStatus` và `db.getName()`.
7. Giải thích vì sao hai user cùng quyền đọc `commerce` có thể nằm trong hai auth databases khác nhau.

**Điều cần kết luận:** Không phải `authSource` nào cũng dùng được; nó phải trỏ đúng database lưu credential.

## 23. Thực hành B: SCRAM-SHA-256 vs SCRAM-SHA-1

1. Trên lab server hỗ trợ, tạo user có credential cho `SCRAM-SHA-256`.
2. Kết nối bằng `authMechanism=SCRAM-SHA-256`.
3. Thử cơ chế không được user hỗ trợ nếu lab cho phép và ghi nhận lỗi.
4. Kiểm tra role/privileges.
5. Giải thích vì sao việc client yêu cầu mechanism không làm MongoDB tự tạo credential tương ứng.
6. Nêu lý do SCRAM vẫn nên chạy trên TLS.

Không thay đổi authentication mechanisms của production user chỉ để thử bài.

## 24. Thực hành C: TLS server authentication + SCRAM

Trên test instance đã có CA/server certificate hợp lệ:

1. Bật `requireTLS` và cấu hình server cert.
2. Client trust đúng CA.
3. Client kết nối với `tls=true` bằng SCRAM user.
4. Kiểm tra server hostname/SAN.
5. Thử kết nối bằng một hostname **không nằm trong SAN** trong môi trường lab và ghi nhận lỗi.
6. Sửa bằng DNS/cert hợp lệ, không bật insecure mode.
7. Giải thích vì sao client không cần X.509 user khi dùng SCRAM.

## 25. Thực hành D: MONGODB-X509

Trên lab có hỗ trợ mutual TLS:

1. Phát hành certificate client có `clientAuth` phù hợp.
2. Kiểm tra subject/issuer/validity bằng openssl.
3. Tạo user tương ứng trong `$external` với role `read` trên `commerce`.
4. Kết nối bằng `MONGODB-X509` và `authSource=%24external`.
5. Kiểm tra user authenticated và thực hiện query read trong lab.
6. Thử insert và xác nhận thiếu quyền ghi.
7. Kiểm tra behavior nếu user DN mapping chưa tồn tại, **không xóa user production**.
8. Giải thích vì sao một client certificate có CA trust vẫn cần user roles.

## 26. Thực hành E: Java Sync Driver

Viết hai chương trình:

**Chương trình 1 — SCRAM**

- `MongoCredential.createScramSha256Credential()`.
- `source="admin"` hoặc `source="commerce"` đúng user.
- TLS trust server.
- Query collection được cấp role.
- Không ghi password ra log.

**Chương trình 2 — X.509**

- URI có `authMechanism=MONGODB-X509`.
- `authSource=%24external`.
- JVM keyStore chứa client certificate/private key.
- JVM trustStore chứa CA.
- Query đúng database.
- Kiểm tra DN và roles khi authentication lỗi.

So sánh đường đi secret: password vs private key.

## 27. Thực hành F: troubleshoot theo tầng

Cho bốn tình huống:

| Tình huống | Nơi điều tra đầu tiên |
|---|---|
| Hostname mismatch trong TLS | Certificate SAN/endpoint |
| SCRAM Authentication failed | User/password/authSource/mechanism |
| X.509 TLS thành công nhưng auth failed | `$external` user, subject DN, mechanism |
| Login thành công nhưng Unauthorized insert | Role/privilege |

Viết runbook phân biệt từng lỗi. Không dùng `root`, `tlsInsecure` hoặc tắt authorization làm giải pháp nhanh.

## 28. Thực hành G: rotation

Lập phương án cho ba sự kiện:

1. SCRAM password bị nghi lộ.
2. Client X.509 cert sắp hết hạn.
3. CA nội bộ chuẩn bị được thay thế.

Với mỗi sự kiện, nêu:

- Identity bị ảnh hưởng.
- Secret/certificate phải rotate.
- Quyền đã cấp và thời gian overlap.
- Kiểm tra trước rollout.
- Cách quan sát lỗi.
- Cách rollback/thu hồi.
- Những dữ liệu không được log.

## 29. Checklist triển khai bảo mật

### 29.1. Authentication

- [ ] Biết rõ account đang dùng SCRAM hay X.509.
- [ ] SCRAM-SHA-256 được ưu tiên nếu version/credential hỗ trợ.
- [ ] User được tạo ở authentication database đã xác định.
- [ ] URI/MongoCredential đặt `authSource` chính xác.
- [ ] Password đọc từ secret manager, không commit vào source.
- [ ] Không normalize password tùy ý.
- [ ] Service có account riêng.
- [ ] Roles áp dụng nguyên tắc least privilege.
- [ ] Không dùng account root cho application.

### 29.2. TLS/certificate

- [ ] TLS bật trên các kết nối production theo chính sách.
- [ ] Client xác minh server certificate chain và hostname SAN.
- [ ] Server private key được bảo vệ.
- [ ] Không bật insecure certificate/hostname bypass.
- [ ] Nếu dùng mTLS, client cert được server tin cậy và có EKU phù hợp.
- [ ] X.509 user nằm trong `$external` với đúng canonical DN.
- [ ] Client certificate/private key không nằm trong repo.
- [ ] JVM/key stores/CA trust đã cấu hình đúng.
- [ ] Certificate expiry/rotation được theo dõi.
- [ ] Có kế hoạch CA rotation và thu hồi.

### 29.3. Topology và vận hành

- [ ] Replica set/sharded cluster có internal authentication phù hợp.
- [ ] Không nhầm clusterAuthMode với app authentication.
- [ ] Không dùng keyfile member làm secret cho app.
- [ ] Kiểm tra `connectionStatus` và quyền qua thao tác có giới hạn.
- [ ] Log errors đã loại bỏ secret/URI password.
- [ ] Có runbook phân biệt network/TLS/authentication/authorization.
- [ ] Đã thử staging/canary trước khi thay đổi certificate/password.
- [ ] Có audit, monitoring và rollback plan.

---

## 30. Tài liệu MongoDB chính thức

- [MongoDB Manual – Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual – SCRAM](https://www.mongodb.com/docs/manual/core/security-scram/)
- [MongoDB Manual – Authentication Database](https://www.mongodb.com/docs/manual/core/authentication/#authentication-database)
- [MongoDB Manual – Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/)
- [MongoDB Manual – db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/)
- [MongoDB Manual – db.updateUser()](https://www.mongodb.com/docs/manual/reference/method/db.updateUser/)
- [MongoDB Manual – db.changeUserPassword()](https://www.mongodb.com/docs/manual/reference/method/db.changeUserPassword/)
- [MongoDB Manual – Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual – Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual – X.509 Certificate Authentication](https://www.mongodb.com/docs/manual/core/security-x.509/)
- [MongoDB Manual – Configure MongoDB with X.509 Certificate Authentication](https://www.mongodb.com/docs/manual/tutorial/configure-x509-client-authentication/)
- [MongoDB Manual – Internal/Membership Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/)
- [MongoDB Manual – Localhost Exception](https://www.mongodb.com/docs/manual/core/localhost-exception/)
- [MongoDB Java Sync Driver – Authentication](https://www.mongodb.com/docs/drivers/java/sync/current/security/authentication/)
- [MongoDB Java Sync Driver – TLS/SSL](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/)

> Tên options và các yêu cầu X.509/internal authentication có thể khác theo MongoDB Server version, driver version hoặc cloud provider. Với deployment managed, dùng tài liệu của nhà cung cấp và xác minh tính năng được hỗ trợ; không áp dụng cấu hình `mongod.conf` của self-managed server như một hướng dẫn chỉnh sửa Atlas cluster.

## 31. Tổng kết

MongoDB có nhiều lớp bảo mật, và bài học quan trọng nhất là **không trộn chúng**:

1. **SCRAM** xác thực user bằng username/password theo cơ chế challenge-response, ưu tiên `SCRAM-SHA-256` cho môi trường hỗ trợ.
2. **Authentication database** xác định nơi MongoDB tra thông tin user. `authSource=admin` hay `authSource=commerce` phải phù hợp nơi user được tạo; không nhất thiết trùng database chứa dữ liệu.
3. **Authorization** dựa trên roles và privileges, không tự tăng khi account nằm trong `admin` hoặc khi TLS thành công.
4. **TLS server certificate** giúp client xác minh server và mã hóa traffic, có thể dùng đồng thời với SCRAM.
5. **MONGODB-X509** dùng client certificate làm cơ chế xác thực ứng dụng, thường ánh xạ subject DN tới user trong `$external`.
6. **Internal member X.509** là việc khác với application X.509; thay đổi nó phải theo runbook cluster.
7. **Java driver** nên lấy secret/key material từ nguồn bảo mật và cấu hình đúng credential source, TLS trust/key stores, replica set/SRV topology.
8. Khi gặp lỗi, hãy điều tra lần lượt **network → TLS → authentication → authorization** thay vì tắt kiểm tra hoặc cấp quyền quá rộng.

Một triển khai đúng không chỉ “connect được”, mà còn phải **xác minh đúng server, đăng nhập đúng identity, cấp đúng quyền, bảo vệ secrets và có kế hoạch rotation/khôi phục**.
