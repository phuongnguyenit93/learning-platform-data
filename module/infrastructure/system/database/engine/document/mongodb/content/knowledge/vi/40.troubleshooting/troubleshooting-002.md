# Phân biệt lỗi xác thực với thiếu quyền thao tác trong MongoDB

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot truy vấn MongoDB. Khi gọi `findOne`, dữ liệu trả về bình thường; nhưng khi gọi `insertOne`, ứng dụng báo lỗi. Người trực vận hành nói “có lẽ sai mật khẩu”, đổi mật khẩu tài khoản database và khởi động lại toàn bộ Pods. Lỗi vẫn còn, trong khi quá trình đổi secret làm thêm một số connections thất bại.

Nguyên nhân thực tế: tài khoản đã **xác thực thành công** nhưng chỉ có role `read`; nó không có action `insert`. Đây là vấn đề **authorization**, không phải **authentication**.

~~~text
Application
    |
    v
DNS / TCP / TLS
    |
    v
MongoDB authentication
    |
    +--> Fail: Who are you? (AuthenticationFailed, code 18)
    |
    v
Authenticated principal
    |
    v
MongoDB authorization
    |
    +--> Fail: May you perform this action on this resource?
    |          (Unauthorized, code 13)
    |
    v
Command execution / business logic
~~~

Bài thuộc module **Database Engine Document MongoDB**, chương **Xử lý sự cố**, với đề bài **Phân biệt lỗi xác thực với thiếu quyền thao tác**.

### 1.1. Bạn sẽ làm được gì?

- Giải thích sự khác nhau giữa MongoDB authentication và authorization.
- Đọc đúng code `18 AuthenticationFailed` và `13 Unauthorized`.
- Phân biệt sai username/password, authSource, mechanism, secret version, URI encoding và vấn đề TLS.
- Đọc identity và effective privileges trên kết nối hiện tại.
- Hiểu roles, inheritance, resource, action và least privilege.
- Phân biệt Atlas UI/project users với MongoDB database users.
- Tạo lab cho trường hợp đăng nhập thành công nhưng bị từ chối ghi dữ liệu.
- Tạo custom role chỉ cho phép một số thao tác.
- Chẩn đoán lỗi ở MongoDB Java Driver và Spring Data MongoDB.
- Xử lý permission errors khi chạy aggregation, change streams, transactions, index migration và backup.
- Thiết kế secret rotation và thay đổi quyền có kiểm soát.
- Xây runbook, báo cáo incident, tests và checklist production.

**Nguyên tắc:** Luôn xác định lỗi xảy ra tại **lớp nào** trước khi sửa. Không reset password nếu root cause là thiếu một privilege; không cấp `root` để chữa lỗi chưa xác định.

## 2. Authentication: danh tính của kết nối

Authentication trả lời câu hỏi **“Ai đang kết nối?”**.

Một MongoDB principal có thể xác thực bằng:

1. SCRAM-SHA-256 hoặc SCRAM-SHA-1.
2. X.509 client certificate.
3. OIDC trong deployment/driver hỗ trợ.
4. AWS IAM trong Atlas và cơ chế tương ứng.
5. LDAP/Kerberos ở edition và môi trường hỗ trợ.

Cơ chế cụ thể phụ thuộc MongoDB Server, Atlas tier, Java Driver và cấu hình tổ chức.

### 2.1. SCRAM

Với SCRAM, client chứng minh mình biết password tương ứng với database user. Server kiểm tra user, cơ chế và authentication database.

Nếu không đúng:

~~~text
MongoServerError: Authentication failed.
code: 18
codeName: AuthenticationFailed
~~~

Đây là ví dụ lớp lỗi; cách hiển thị của mongosh và Java Driver có thể khác.

### 2.2. Authentication database là một phần quan trọng của identity

Hai principal được đặt tên giống nhau ở hai authentication databases có thể là hai đối tượng khác nhau:

~~~text
reader@admin
reader@reporting
~~~

Nếu user được tạo ở `reporting` nhưng URI yêu cầu `authSource=admin`, password đúng vẫn có thể bị từ chối xác thực.

### 2.3. Đăng nhập được nhưng không có role

Một database user có `roles: []` vẫn có thể xác thực được nếu credentials đúng. Khi gọi `find` hoặc `insert`, server sẽ từ chối vì không có quyền thao tác.

Đừng suy luận “login thành công” có nghĩa “mọi nghiệp vụ của ứng dụng đều chạy được”.

## 3. Authorization: được làm gì trên dữ liệu nào?

Authorization trả lời **“Principal này được thực hiện operation nào trên resource nào?”**

MongoDB dùng Role-Based Access Control (RBAC):

~~~text
Database User
     |
     +--> Role A
     |      |
     |      +--> find on orders.orders
     |
     +--> Role B
            |
            +--> insert on orders.outbox
     |
     v
Effective privilege set
~~~

Một privilege được mô tả như:

~~~javascript
{
  resource: {
    db: "orders",
    collection: "outbox"
  },
  actions: ["insert"]
}
~~~

### 3.1. Resource khác action

| Thành phần | Ví dụ | Câu hỏi |
|---|---|---|
| Principal | `orders_api@admin` | Kết nối đang là ai? |
| Action | `insert` | Lệnh cần làm gì? |
| Database | `orders` | Nằm trong DB nào? |
| Collection | `outbox` | Trên collection nào? |
| Scope | Collection/database/cluster | Quyền có phủ tài nguyên đó không? |

Quyền `find` trên `orders.orders` không cho phép `insert` vào `orders.orders`.

### 3.2. Role trong database khác không tự cấp quyền

Nếu user có `readWrite` trên `orders_dev`, nó không tự ghi được `orders_prod`. Kiểm tra đúng database trong lỗi.

### 3.3. Quyền cluster-level khác CRUD

Một tài khoản có thể đọc orders bình thường nhưng không được chạy `serverStatus`, `replSetGetStatus`, `createUser` hay backup admin commands. Đây không phải tình trạng password sai.

## 4. Mã lỗi 18 và 13

Theo MongoDB Manual Error Codes:

| Mã | codeName | Bước thất bại | Hướng điều tra |
|---:|---|---|---|
| 18 | `AuthenticationFailed` | Chứng minh danh tính | Username, secret, authSource, mechanism |
| 13 | `Unauthorized` | Kiểm tra quyền | Principal, command, resource, role/action |

### 4.1. Ví dụ AuthenticationFailed

~~~text
Command failed with error 18 (AuthenticationFailed):
'Authentication failed.'
~~~

Các khả năng: mật khẩu sai, user không tồn tại trong authSource, secret đã rotate, mechanism sai, URI encoding lỗi.

### 4.2. Ví dụ Unauthorized

~~~text
MongoServerError: not authorized on orders
to execute command { insert: "outbox", ... }
code: 13
codeName: Unauthorized
~~~

Các khả năng: principal đã authenticated nhưng thiếu `insert`, role được cấp trên database khác, deployment dùng custom role scope hẹp.

### 4.3. Đừng chỉ khớp chuỗi message

Có thể có wrapper, translation hoặc message thay đổi theo MongoDB/driver version. Ưu tiên server error code, codeName và exception cause chain.

### 4.4. Phân loại sơ bộ trước khi thao tác

~~~text
Error code 18?
  --> Xem Authentication

Error code 13?
  --> Xem Authorization

Không phải hai mã trên?
  --> Xem DNS, TLS, network, topology, command syntax,
      schema/validation hoặc business logic.
~~~

## 5. Những lỗi trông giống authentication nhưng không phải

| Triệu chứng | Phân loại gần đúng | Hướng điều tra |
|---|---|---|
| `UnknownHostException` | DNS | Host, SRV/TXT, resolver |
| `MongoSocketOpenException` | TCP/network | Firewall, endpoint, port |
| `SSLHandshakeException` | TLS | Certificate chain, CA, SAN, expiry |
| `PKIX path building failed` | TLS trust | Java truststore |
| `MongoTimeoutException` | Timeout/topology | Server selection, network, primary |
| `HostUnreachable` | Network | Node, routing, firewall |
| `CommandNotFound`, code 59 | Command/version | Command có được hỗ trợ? |
| `NamespaceNotFound`, code 26 | Namespace | Collection tồn tại không? |
| `DuplicateKey`, code 11000 | Data constraint | Unique index |
| `WriteConflict` | Concurrency | Transaction/retry logic |
| `Unauthorized`, code 13 | RBAC | Action/resource |

### 5.1. Lớp kết nối theo thứ tự

~~~text
Hostname resolved
       |
TCP connection established
       |
TLS handshake / server identity verified
       |
MongoDB handshake/topology discovered
       |
Authentication attempted
       |
Authorization for command
       |
Command executed
~~~

Nếu DNS không hoạt động, chưa có bằng chứng password sai. Nếu TLS fail vì CA chưa được trust, cấp role `readWrite` cũng không sửa được.

### 5.2. Tránh thay hai thứ cùng lúc

Không đồng thời mở firewall rộng, tắt TLS và đổi password chỉ để “xem cái nào chạy”. Việc này làm mất bằng chứng, tăng rủi ro và khó rollback.

## 6. Cây quyết định xử lý sự cố

~~~text
Ứng dụng báo MongoDB error
         |
         v
Lấy code / codeName / operation / namespace
         |
         +--> Không có server response?
         |       |
         |       +--> DNS / TCP / TLS / topology
         |
         +--> Code 18?
         |       |
         |       +--> Xác thực: user, authSource,
         |             password/token/cert, version
         |
         +--> Code 13?
         |       |
         |       +--> Phân quyền: principal,
         |             action, resource, roles
         |
         +--> Code khác?
                 |
                 +--> Dùng bảng MongoDB errors,
                       query/server logs và runbook
~~~

Các câu hỏi triage:

1. Command nào thất bại?
2. Namespace nào xuất hiện trong lỗi?
3. App dùng URI/secret source và active profile nào?
4. Principal thực sự đã authenticated là ai?
5. Lệnh nào vẫn chạy được?
6. Lỗi bắt đầu sau change gì?
7. Có ảnh hưởng dữ liệu, bảo mật hoặc SLO không?

## 7. URI: phân biệt database và authSource

Một URI minh họa:

~~~text
mongodb://<user>:<encoded-password>@db1.example.test:27017,db2.example.test:27017/orders?replicaSet=rs0&authSource=admin&tls=true
~~~

Các phần:

- `/orders`: default database khi ứng dụng không override.
- `authSource=admin`: authentication database chứa SCRAM user.
- `replicaSet=rs0`: topology được mong đợi.
- `tls=true`: bảo vệ transport.
- Hostnames: seed addresses.
- Username/password: secret thông tin xác thực.

### 7.1. Authentication DB và operation DB độc lập

Một user ở `admin` có thể được cấp `readWrite` trên `orders`. Kết nối vẫn dùng `authSource=admin`.

### 7.2. Password có ký tự đặc biệt

Các ký tự reserved như `@`, `:`, `/`, `?`, `#`, `%` cần được percent-encode đúng khi nằm trong URI userinfo.

Nếu chèn nguyên password có `@` vào URI, parser có thể đọc sai host/userinfo; lỗi cuối cùng có thể là parse error hoặc AuthenticationFailed.

### 7.3. Không log connection string đầy đủ

URI chứa credentials là secret. Incident record nên dùng URI đã redacted hoặc secret reference ID, không xuất nguyên giá trị.

### 7.4. Không suy luận quyền từ path database

Kết nối có `/orders` không có nghĩa MongoClient bị khóa cứng vào database đó. Code vẫn có thể truy vấn `client.getDatabase("payments")`; MongoDB RBAC quyết định có được phép hay không.

## 8. mongodb+srv:// trên Atlas

Atlas thường cung cấp SRV connection strings:

~~~text
mongodb+srv://<user>:<encoded-secret>@cluster0.example.mongodb.net/orders?authSource=admin&retryWrites=true&w=majority
~~~

Với SRV, driver dùng DNS SRV/TXT để khám phá hosts; TLS được bật mặc định trừ cấu hình khác theo MongoDB URI rules.

### 8.1. Ba loại cấu hình khác nhau

- **Network access:** IP access list, private endpoint, VPC routing, DNS.
- **Authentication:** Database user, SCRAM/X.509/OIDC/IAM.
- **Authorization:** Database roles và specific privileges.

Một lỗi network thường không được server trả code 18/13 vì request chưa đi đến giai đoạn tương ứng.

### 8.2. Không mở IP allowlist vô hạn để debug

Hạn chế quyền theo mạng, dùng test runner/Pod có IP được phê duyệt và hoàn nguyên temporary access. Không dùng `0.0.0.0/0` trên production như cách sửa lâu dài.

### 8.3. Sai replica set topology

Nếu URI dùng `directConnection=true` vào một node rồi ứng dụng kỳ vọng failover, server selection sau election có thể lỗi. Đây là topology setup problem, không mặc nhiên là authentication.

## 9. SCRAM: nguyên nhân thường gặp của code 18

1. Sai username, ký tự hoa/thường.
2. Sai password hoặc secret chưa được cập nhật.
3. Sai authentication database.
4. User thực tế được tạo ở môi trường khác.
5. Authentication mechanism không khớp.
6. URI password chưa encode đúng.
7. Database user đã bị xóa hoặc hết hạn.
8. Secret rotation đã thay phía server, ứng dụng còn dùng bản cũ.
9. Một số Pods/workers lấy secret version khác nhau.
10. Properties của Spring Boot/profile ghi đè URI dự kiến.

### 9.1. Password đúng nhưng authSource sai

~~~text
User created at authz_lab

URI uses authSource=admin

Server looks for user in admin
   |
   v
AuthenticationFailed(18)
~~~

Sửa `authSource`, không cấp thêm role trước khi chứng minh user đã authenticate.

### 9.2. Mechanism sai

Nếu user chỉ được cấu hình SCRAM-SHA-256 nhưng client buộc cơ chế khác không hỗ trợ, authentication có thể lỗi. Kiểm tra user mechanisms và driver/server compatibility.

### 9.3. Không reset password mù quáng

Đổi password khi chỉ có code 13 vừa không giúp thao tác có quyền, vừa làm invalid các connections mới đang dùng secret cũ.

## 10. X.509 và hai lớp TLS / database identity

X.509 có hai khái niệm:

- TLS trust/certificate validation thiết lập kết nối an toàn.
- MongoDB X.509 authentication ánh xạ client identity và role tương ứng.

### 10.1. TLS handshake fail

~~~text
Java SSLHandshakeException
  -> Certificate chain/SAN/expiry/truststore
~~~

Chưa thể suy ra database user thiếu quyền.

### 10.2. TLS pass nhưng MongoDB principal không hợp lệ

Một client certificate có thể được TLS layer chấp nhận nhưng subject/identity không có MongoDB user mapping đúng. Khi đó là lỗi authentication.

### 10.3. Authentication pass, role thiếu

Nếu X.509 principal đã xác thực nhưng không có `find` trên collection, MongoDB có thể trả code 13 như các cơ chế khác.

### 10.4. authSource với external mechanisms

X.509 và các cơ chế ngoài SCRAM thường sử dụng `$external` theo tài liệu tương ứng. Đừng tự đổi sang `admin` chỉ vì account SCRAM khác dùng admin.

### 10.5. Không tắt TLS verification

`tlsInsecure`, `tlsAllowInvalidHostnames` hoặc trust-all Java SSLContext là giải pháp không an toàn. Chúng không thêm MongoDB privileges.

## 11. OIDC và AWS IAM cũng cần RBAC

Trong môi trường hỗ trợ, OIDC và IAM cho phép workload dùng identity-based authentication thay cho password SCRAM dài hạn.

~~~text
External Identity Provider
            |
            v
Token / AWS credentials
            |
            v
MongoDB Authentication
            |
            v
Database Principal / Role Mapping
            |
            v
MongoDB Authorization
~~~

Nếu token hết hạn, issuer/audience sai, identity mapping không hợp lệ: vấn đề authentication.

Nếu token hợp lệ và MongoDB nhận principal nhưng principal thiếu action `insert`: vấn đề authorization.

### 11.1. IAM role không thay MongoDB database role

AWS IAM policy và MongoDB collection privileges là hai bộ quyền khác nhau. Workload có thể được AWS cho phép lấy credential nhưng vẫn bị MongoDB từ chối lệnh.

### 11.2. Không đoán cơ chế theo URI

`authMechanism=MONGODB-OIDC` hoặc AWS IAM cần driver, provider, callback/credential configuration và server support đúng. Không chỉ thêm query parameter rồi coi quá trình chuyển đổi đã hoàn tất.

## 12. MongoDB RBAC: role, privilege và resource

MongoDB role gộp các privilege actions trên resources.

~~~javascript
{
  role: "ordersInserter",
  privileges: [
    {
      resource: {
        db: "authz_lab",
        collection: "orders"
      },
      actions: ["find", "insert"]
    }
  ],
  roles: []
}
~~~

### 12.1. Resource có phạm vi

- Collection cụ thể.
- Database với các collections phù hợp.
- Cluster-level action.
- Những đặc biệt khác theo privilege model.

### 12.2. Role có thể kế thừa role khác

Effective permissions là kết quả từ các grants trực tiếp và vai trò kế thừa. Chỉ xem tên `custom_reader` chưa đủ; cần xem actions cuối cùng.

### 12.3. Không có deny đơn giản để ghi đè grants rộng

MongoDB RBAC chủ yếu dựa trên positive grants. Đừng kỳ vọng một custom role tên `denyWrites` tự thu hồi quyền từ `readWrite`.

### 12.4. Authentication source không xác định role resource scope

Một user có thể được tạo ở `admin` nhưng có role trên `orders` hoặc `reporting`. Role definition database và target resource cần được xem riêng.

## 13. Built-in roles thường gặp

| Role | Quyền chính | Không nên suy ra |
|---|---|---|
| `read` | Đọc dữ liệu tại database được chỉ định | Không cho phép ghi |
| `readWrite` | Đọc/ghi và một số thao tác collection/index | Không phải root |
| `dbAdmin` | Quản trị database/metadata | Không tương đương readWrite |
| `userAdmin` | Quản users/roles ở scope | Không phải business CRUD role |
| `clusterMonitor` | Quan sát trạng thái cluster | Không tự cấp CRUD |
| `backup` | Backup operations phù hợp | Không đồng nghĩa restore |
| `restore` | Restore operations phù hợp | Không phải app role |
| `readAnyDatabase` | Đọc nhiều databases theo scope | Không tự ghi |
| `root` | Quyền rất rộng | Không cấp cho app bình thường |

Các actions chi tiết khác giữa Atlas/self-managed và theo version; xem trang Built-In Roles đúng deployment.

### 13.1. readWrite không là userAdmin

Một business service có readWrite không nên được phép quản user và cấp roles cho chính nó. Quản trị danh tính phải do DBA/Security workflow.

### 13.2. dbAdmin không đồng nghĩa find/insert

Tên role dễ gây hiểu nhầm. Kiểm tra effective privileges theo action, không chỉ suy luận từ tên.

### 13.3. Monitoring agent cần role phù hợp

`serverStatus`, `replSetGetStatus` hoặc cluster metrics có thể cần privileges ngoài một role `read` ứng dụng. Tách agent monitoring riêng.

## 14. Atlas UI users khác database users

MongoDB Atlas quản lý ít nhất hai loại identity cần phân biệt:

| Identity | Cấp quyền | Mục đích |
|---|---|---|
| Atlas organization/project user | Atlas IAM/project roles | Quản lý Atlas UI/API |
| Atlas service account/API key | Atlas management API roles | Tự động hóa Atlas |
| MongoDB database user | Database roles/custom privileges | MongoDB Driver, mongosh |
| Cloud IAM principal | Cloud permissions, đôi khi DB auth identity | Secrets/network/cloud resources |

### 14.1. Project Owner không phải SCRAM login

Đăng nhập Atlas web và thấy cluster không có nghĩa có thể điền email/password web vào MongoDB URI rồi authenticate.

### 14.2. Database users ở Atlas được quản lý qua Atlas

Dùng Atlas UI, Atlas CLI, Administration API hoặc integration được hỗ trợ. Không dùng `db.createUser()` trên Atlas như cách quản trị chuẩn; thay đổi có thể bị Atlas hoàn nguyên.

### 14.3. Chú ý cluster restriction

Atlas database users có thể được giới hạn truy cập từng cluster/federated instance. Cùng tên user nhưng kết nối tới project/cluster khác có thể không có access hợp lệ.

### 14.4. Custom database roles Atlas

Atlas hỗ trợ built-in roles, custom roles và specific privileges nhưng không phải mọi self-managed privilege action đều được áp dụng giống nhau trên tất cả Atlas tiers.

### 14.5. Atlas Data Explorer không chứng minh quyền driver

Một người dùng có thể truy cập dữ liệu qua Atlas UI theo UI role; ứng dụng Java vẫn cần MongoDB database principal và đúng auth mechanism/roles.

## 15. Công cụ quan trọng nhất: connectionStatus

MongoDB có command mô tả identity và quyền hiệu lực trên **current connection**:

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

Output ví dụ:

~~~javascript
{
  authInfo: {
    authenticatedUsers: [
      { user: "orders_reader", db: "authz_lab" }
    ],
    authenticatedUserRoles: [
      { role: "read", db: "authz_lab" }
    ],
    authenticatedUserPrivileges: [
      // Actions thực tế trên resources tương ứng
    ]
  },
  ok: 1
}
~~~

### 15.1. Ba trường quan trọng

- `authenticatedUsers`: principal nào đã authenticate.
- `authenticatedUserRoles`: những roles đang có.
- `authenticatedUserPrivileges`: tập privileges có hiệu lực khi `showPrivileges:true`.

### 15.2. Dùng đúng connection cần điều tra

Nếu mongosh đang login bằng admin, command này trả permissions của admin, **không** của MongoClient mà orders-api dùng. Phải thử trên connection của ứng dụng hoặc canary client cùng principal.

### 15.3. Có thể chỉ in dữ liệu cần thiết

~~~javascript
const result = db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});

printjson({
  users: result.authInfo.authenticatedUsers,
  roles: result.authInfo.authenticatedUserRoles,
  privileges: result.authInfo.authenticatedUserPrivileges
});
~~~

Dữ liệu privileges/namespace vẫn là operational metadata cần quyền truy cập phù hợp, dù không có password.

### 15.4. Không phải công cụ xem mọi user

`connectionStatus` chỉ nói về current connection. Với user khác, yêu cầu DBA dùng `usersInfo`/`rolesInfo` hoặc Atlas Access UI và quyền xem phù hợp.

## 16. Kiểm tra users và roles trên self-managed

Khi có admin privileges hợp lệ:

~~~javascript
use authz_lab

db.getUser("orders_reader", {
  showPrivileges: true
});
~~~

Để xem roles:

~~~javascript
db.getRoles({
  showPrivileges: true
});
~~~

Cần quyền tương ứng để xem users/roles; không cấp role root cho ứng dụng để chạy diagnostics.

### 16.1. So effective privileges với lệnh bị lỗi

Ví dụ:

~~~text
Operation: insertOne
Namespace: authz_lab.orders
Principal: orders_reader@authz_lab

Available: find on authz_lab
Missing: insert on authz_lab.orders

Conclusion: Authorization error, code 13.
~~~

### 16.2. Permission cache và thời điểm áp dụng

Thay role có thể không được mọi clients/mongos/servers nhìn thấy đồng thời vì caching và connection lifecycle. Sau change, kiểm tra bằng new connection và theo dõi trước khi đóng incident; không mặc định role propagation tức thì.

### 16.3. Không thay roles khi thiếu approval

Grant/revoke là security change. Ghi ai, role nào, resource nào, mục đích, thời điểm, kết quả và phương án rollback.

## 17. Phòng lab tự quản lý: bật authorization trước

Phần thực hành sử dụng MongoDB **self-managed trong môi trường lab cô lập**. Không chạy `createUser`/`createRole` của lab trên Atlas production.

Điều kiện:

- MongoDB bật `security.authorization: enabled`.
- Có user admin với quyền quản lý users.
- Data test không chứa PII.
- Nếu có kết nối qua mạng, dùng TLS.
- Có hai hoặc nhiều mongosh sessions để tách admin và low-privilege user.

### 17.1. Vì sao phải dùng session riêng?

MongoDB docs lưu ý `db.auth()` không hoạt động như nút “switch user” xóa mọi identity cũ trong cùng mongosh connection. Một session admin có thể vẫn có quyền admin khi bạn thử login reader.

Muốn kiểm thử quyền reader, **thoát hẳn shell admin và mở shell mới** bằng reader.

### 17.2. Chuẩn bị database thử

Đăng nhập bằng admin ở lab:

~~~javascript
use authz_lab

db.createCollection("orders");

db.orders.insertMany([
  {
    _id: "order-001",
    status: "PENDING",
    amount: 100
  },
  {
    _id: "order-002",
    status: "CONFIRMED",
    amount: 250
  }
]);
~~~

Chuẩn bị collection trước để không nhầm lỗi `NamespaceNotFound` với permission.

## 18. Lab tạo user chỉ đọc

Trong admin session:

~~~javascript
use authz_lab

db.createUser({
  user: "orders_reader",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "authz_lab" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

`passwordPrompt()` yêu cầu nhập password mà không đặt plaintext vào command history. TLS vẫn cần nếu dữ liệu credential đi qua mạng.

### 18.1. Tạo writer

~~~javascript
db.createUser({
  user: "orders_writer",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "authz_lab" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

### 18.2. Không dùng một mật khẩu thật

Credentials chỉ dành cho lab; không copy secret sản xuất, không upload các file cấu hình chứa secrets vào repository.

### 18.3. Nếu user đã tồn tại

`db.createUser()` có thể báo duplicate user. Đừng tự động drop user rồi thử lại trên database không chắc là lab; kiểm tra đúng namespace và owner.

## 19. Lab kiểm thử AuthenticationFailed

Đóng admin mongosh, mở terminal mới. Ví dụ cho MongoDB local lab:

~~~bash
mongosh "mongodb://127.0.0.1:27017/authz_lab" \
  --username orders_reader \
  --authenticationDatabase authz_lab \
  --password
~~~

Terminal hỏi password.

### 19.1. Nhập sai mật khẩu

Kỳ vọng lỗi ở giai đoạn xác thực:

~~~text
AuthenticationFailed (18)
~~~

### 19.2. Nhập đúng mật khẩu nhưng chọn sai authSource

Nếu user được tạo trong `authz_lab` nhưng CLI dùng:

~~~bash
mongosh "mongodb://127.0.0.1:27017/authz_lab" \
  --username orders_reader \
  --authenticationDatabase admin \
  --password
~~~

thì có thể nhận AuthenticationFailed vì MongoDB tìm user ở sai database.

### 19.3. Không nhầm lỗi local lab với production

Nếu local mongod chưa bật authorization, test có thể không tạo được tín hiệu mong muốn. Nếu chưa có MongoDB process, lỗi connection refused; điều đó không chứng minh authentication.

## 20. Lab kiểm thử Unauthorized

Mở mongosh mới với đúng user `orders_reader` và password đúng:

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

Lệnh đọc:

~~~javascript
db.orders.findOne({
  _id: "order-001"
});
~~~

Dự kiến trả document.

Lệnh ghi:

~~~javascript
db.orders.insertOne({
  _id: "order-003",
  status: "PENDING",
  amount: 400
});
~~~

Dự kiến:

~~~text
MongoServerError: not authorized on authz_lab
to execute command ...
code: 13
codeName: Unauthorized
~~~

### 20.1. Vì sao password không cần thay?

Vì `findOne` đã thực thi thành công dưới principal reader. Nếu `insertOne` bị từ chối, điều cần kiểm tra là action `insert` trên collection.

### 20.2. Không cấp ngay readWrite

Trong lab, bạn có thể thử `orders_writer` để thấy role khác. Nhưng trong production, nếu chỉ cần insert trên một collection, custom role hẹp thường tốt hơn cấp `readWrite` toàn database.

### 20.3. Ma trận kỳ vọng

| Credential | Lệnh | Kết quả |
|---|---|---|
| Reader đúng password | Login | Thành công |
| Reader sai password | Login | Code 18 |
| Reader đúng password, sai authSource | Login | Code 18 hoặc lỗi config phù hợp |
| Reader | `findOne(orders)` | Thành công |
| Reader | `insertOne(orders)` | Code 13 |
| Writer | `insertOne(orders)` | Thành công |
| Writer | `find` trên database khác không có role | Code 13 |

## 21. Lab tạo custom role chỉ có find và insert

Đăng nhập lại bằng admin session riêng:

~~~javascript
use authz_lab

db.createRole({
  role: "ordersInserter",
  privileges: [
    {
      resource: {
        db: "authz_lab",
        collection: "orders"
      },
      actions: ["find", "insert"]
    }
  ],
  roles: []
});

db.createUser({
  user: "orders_ingest",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersInserter", db: "authz_lab" }
  ]
});
~~~

### 21.1. Positive tests

Đăng nhập bằng `orders_ingest` trong shell riêng:

~~~javascript
db.orders.findOne({ _id: "order-001" });

db.orders.insertOne({
  _id: "order-ingest-001",
  status: "CREATED"
});
~~~

Hai operations hợp lệ theo role.

### 21.2. Negative tests

~~~javascript
db.orders.updateOne(
  { _id: "order-ingest-001" },
  { $set: { status: "UPDATED" } }
);
~~~

Dự kiến code 13 do không có `update`.

~~~javascript
db.secret_records.findOne({});
~~~

Dự kiến code 13 vì custom role không có `find` trên collection này.

### 21.3. Ý nghĩa của negative tests

Security test không chỉ chứng minh “được làm việc cần thiết”, mà còn chứng minh “không thể làm việc bị cấm”. Điều đó giúp phát hiện privilege creep.

## 22. Cấp quyền trên đúng resource

Ví dụ app user được cấp `readWrite` trên `orders_dev`:

~~~text
User: app_writer@admin
Role: readWrite on orders_dev

Request: insert orders_prod.orders
Result: Unauthorized (13)
~~~

### 22.1. Không đổi authSource để sửa lỗi resource

Nếu app đã xác thực tại `admin`, chuyển `authSource` sang `orders_prod` có thể làm authentication hỏng. Cần role/privilege đúng resource, không thay identity.

### 22.2. Roles có thể đặt ở admin

Một user tạo trên `admin` có thể được gán role `readWrite` ở `orders_prod`. Khi điều tra phải xem identity database và role resource database riêng.

### 22.3. Thay quyền có phê duyệt

Nếu DBA quyết định cấp thêm privilege trong lab:

~~~javascript
use authz_lab

db.grantRolesToUser("orders_reader", [
  { role: "readWrite", db: "authz_lab" }
]);
~~~

Ví dụ giúp học cú pháp, **không phải khuyến nghị production** vì role `readWrite` rộng hơn nhiều nhu cầu.

### 22.4. Test lại bằng new connection

Sau role change, dùng mongosh mới login đúng principal và thử operation thực sự. Không chỉ xem lệnh grant trả `ok:1`.

## 23. Command-specific privileges

Không thể suy ra quyền lệnh từ tên collection duy nhất; phải xét loại operation.

| Command | Action điển hình |
|---|---|
| `find` | `find` |
| `insertOne`/`insertMany` | `insert` |
| `updateOne`/`replaceOne` | `update` |
| `deleteOne`/`deleteMany` | `remove` |
| `createIndex` | `createIndex` |
| `dropIndex` | `dropIndex` |
| `listIndexes` | `listIndexes` |
| `listCollections` | `listCollections` với ngoại lệ tài liệu quy định |
| `aggregate` | Phụ thuộc stages/namespaces |
| `watch` | `find` và `changeStream` theo scope |
| `serverStatus` | Monitoring privileges |
| `usersInfo`/`rolesInfo` | Xem user/role theo phạm vi |
| `createUser` | `createUser` và quyền grant role |
| Backup/restore | Các actions/roles backup/restore phù hợp |

### 23.1. Aggregation có thể cần quyền tại collection phụ

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
~~~

Nếu user chỉ có `find` trên `orders` mà thiếu trên `customers`, pipeline có thể fail code 13. Đọc các namespaces của toàn pipeline.

### 23.2. $out và $merge

Các aggregation stages này có thể ghi dữ liệu sang collection đích. Lúc đó cần privileges phù hợp với stage, không chỉ `find` trên source collection.

### 23.3. listCollections có ngoại lệ

MongoDB hỗ trợ một số trường hợp `listCollections` với `authorizedCollections:true` và `nameOnly:true` cho user thiếu database-wide listCollections nhưng có quyền trên các collections cụ thể. Không suy rộng ngoại lệ này cho mọi metadata command.

### 23.4. Index migration và server administration

Một business service có quyền CRUD không nên tự chạy quản users, cluster reconfiguration hoặc migrations ngoài scope. Tách danh tính runtime và danh tính migration.

## 24. Change Streams: cần quyền riêng

Một app có thể gọi `find` trên `orders` thành công nhưng `watch()` nhận code 13 nếu custom role thiếu `changeStream`.

~~~javascript
db.orders.watch();
~~~

### 24.1. Scope thay đổi quyền

- Collection-level change stream.
- Database-level change stream.
- Deployment-wide change stream.

Một role chỉ có `find` trên collection `orders` không chắc cho phép watch toàn deployment.

### 24.2. Built-in read roles

MongoDB built-in `read` roles thường bao gồm quyền cần thiết để sử dụng change streams trong scope của chúng. Custom roles cần kiểm tra actions chính xác.

### 24.3. Consumer có checkpoint

Consumer có thể cần `find` + `changeStream` trên source, đồng thời `find`/`insert`/`update` trên checkpoint collection. Đừng cấp `readWriteAnyDatabase` chỉ vì checkpoint ở database khác.

### 24.4. Không phải mọi stream error là 13

Invalidate event, resume token quá cũ, primary election, network error hoặc TLS cũng có thể làm change stream bị ngắt. Phân loại code và event semantics.

## 25. Transactions không vượt qua authorization

Một Spring `@Transactional` service:

~~~text
Transaction:
  update orders.orders
  insert orders.outbox
~~~

Nếu principal chỉ có `update` trên `orders` nhưng không có `insert` trên `outbox`, transaction có thể fail và abort.

### 25.1. @Transactional không cấp quyền

Annotation tạo transaction boundary qua MongoTransactionManager; nó không thể biến database user thành root.

### 25.2. Nhiều MongoClient có thể khác principal

Nếu Service A và B dùng hai MongoDatabaseFactory/MongoClient khác nhau, chúng có thể mang credentials/roles khác nhau ngay cả khi trỏ tới cùng cluster. Xem wiring, không chỉ database URI hostname.

### 25.3. Lỗi không được nuốt

Nếu transaction gặp `MongoCommandException(13)`, phải xử lý rollback/propagation đúng. Catch và bỏ qua có thể khiến application logic báo thành công giả.

## 26. Metadata, backup và monitoring

### 26.1. serverStatus

`serverStatus` là lệnh monitoring, không phải business read. App principal có `read` trên orders có thể không đủ quyền.

### 26.2. createIndexes

Spring Data MongoDB hoặc migration script có thể gọi `createIndexes`. CRUD vẫn ổn nhưng startup fail khi principal thiếu quyền tạo index hoặc đang dùng custom role hẹp.

### 26.3. usersInfo

Một app user không nhất thiết được quyền xem users/roles của người khác. Không cấp quản trị users để chỉ chẩn đoán.

### 26.4. Backup và restore

Backup/restore cần những operations/privileges riêng. Principal có role backup không tự nhiên có quyền restore, và ngược lại.

### 26.5. Tách identities

~~~text
orders-api        -> business CRUD
orders-indexer    -> changeStream/find/checkpoint
db-migrator       -> DDL/index changes theo release
monitoring-agent  -> monitoring privileges
backup-agent      -> backup privileges
security-admin    -> user/role management
~~~

Một tách biệt như vậy giúp giảm blast radius và xác định nhanh nguồn lỗi code 13.

## 27. Java Sync Driver: nguyên tắc phân loại

Trong ứng dụng Java, MongoDB errors có thể là:

- `MongoSecurityException`.
- `MongoCommandException`.
- `MongoException` tổng quát.
- `MongoTimeoutException`, `MongoSocketException` hoặc TLS/network cause.
- Spring `DataAccessException` bọc ở tầng cao.

### 27.1. Không dựa vào substring của message

Thay vì:

~~~java
if (error.getMessage().contains("auth")) {
    // Quá rộng và không đáng tin.
}
~~~

hãy ưu tiên server code và cause chain.

### 27.2. Classifier mẫu

~~~java
import com.mongodb.MongoCommandException;
import com.mongodb.MongoException;
import com.mongodb.MongoSecurityException;

import javax.net.ssl.SSLHandshakeException;
import java.net.UnknownHostException;

public final class MongoFailureClassifier {

    public enum Kind {
        AUTHENTICATION,
        AUTHORIZATION,
        TLS,
        DNS,
        OTHER
    }

    public static Kind classify(Throwable failure) {
        for (Throwable current = failure;
             current != null;
             current = current.getCause()) {

            if (current instanceof MongoCommandException cmd) {
                if (cmd.getErrorCode() == 18) {
                    return Kind.AUTHENTICATION;
                }
                if (cmd.getErrorCode() == 13) {
                    return Kind.AUTHORIZATION;
                }
            }

            if (current instanceof MongoException mongo) {
                if (mongo.getCode() == 18) {
                    return Kind.AUTHENTICATION;
                }
                if (mongo.getCode() == 13) {
                    return Kind.AUTHORIZATION;
                }
                if (current instanceof MongoSecurityException) {
                    return Kind.AUTHENTICATION;
                }
            }

            if (current instanceof SSLHandshakeException) {
                return Kind.TLS;
            }
            if (current instanceof UnknownHostException) {
                return Kind.DNS;
            }
        }

        return Kind.OTHER;
    }
}
~~~

Đây là classifier minh họa cho Java có pattern matching `instanceof`. Nó không thay error handling đầy đủ vì network/driver errors có nhiều dạng. Với `MongoSecurityException`, vẫn cần kiểm tra exact cause và auth mechanism.

### 27.3. Không in raw exception messages tùy tiện

Driver exception có thể chứa hostname/URI/metadata nhạy cảm. Chỉ ghi sanitized category, operation, principal reference, trace ID và error code khi có.

## 28. Java: thực hiện permission probe an toàn

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class ReadOnlyPermissionProbe {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                client.getDatabase("authz_lab")
                      .getCollection("orders");

            Document one = orders.find(
                new Document("_id", "order-001")
            ).first();

            System.out.println("Read operation completed; found="
                + (one != null));
        }
    }
}
~~~

### 28.1. MongoClients.create không xác nhận login

Java Driver thường thiết lập connections khi thực hiện operation. Chỉ tạo `MongoClient` thành công chưa đủ bằng chứng SCRAM/TLS đã thành công.

### 28.2. Ping không xác minh CRUD rights

`db.adminCommand({ping:1})` hữu ích cho khả năng kết nối nhưng không chứng minh `insert` trên `orders.orders` hợp lệ.

### 28.3. Đừng thử insert vào production data bừa bãi

Nếu phải kiểm tra quyền ghi, dùng canary fixture/collection riêng và cleanup policy được phê duyệt để tránh side effects hoặc trôi dữ liệu giả vào billing.

## 29. Spring Data MongoDB: exception được dịch

Spring Data MongoDB có thể chuyển driver exceptions thành `DataAccessException` subclasses. Khi một repository fail, exception cao nhất không nhất thiết là `MongoCommandException`.

### 29.1. Tìm cause gốc

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {

    private final OrderRepository orders;

    public OrderLookupService(OrderRepository orders) {
        this.orders = orders;
    }

    public Order load(String id) {
        try {
            return orders.findById(id).orElseThrow();
        } catch (DataAccessException e) {
            MongoFailureClassifier.Kind category =
                MongoFailureClassifier.classify(e);

            recordFailure(category, "find-order");
            throw e;
        }
    }

    private void recordFailure(
        MongoFailureClassifier.Kind category, String operation) {
        // Metric/tracing hook, không log document/URI.
    }
}
~~~

`Order` và `OrderRepository` là domain types của ứng dụng, không phải classes tích hợp sẵn vào Java Driver.

### 29.2. @Transactional không sửa role

Transaction interceptor quản commit/abort; nếu principal thiếu `insert` ở một collection, role vẫn thiếu. Test nghiệp vụ qua đúng repository và principal.

### 29.3. Multiple database factories

Hai repositories trong cùng app có thể dùng hai MongoClients mang identities khác nhau. Khi chỉ một repository báo 13, kiểm tra config bean và effective database name.

## 30. Spring Boot version và cấu hình URI

Với Spring Boot 3.5:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

Với Spring Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Cần xem Spring Boot properties metadata đúng phiên bản và xác minh active profile.

### 30.1. App kết nối nhầm nơi

Một app dùng Boot 4.x nhưng giữ property Boot 3.x có thể không dùng URI dự kiến; lỗi có thể là connection refused/timeout hoặc login sai user trên cluster khác.

### 30.2. Precedence của property sources

Environment, command-line, external config, configtree và application profiles có thể override nhau. Đừng grep một file YAML rồi kết luận runtime chắc dùng URI đó.

### 30.3. Đừng bật Actuator env/configprops công khai

Các endpoints này có nguy cơ tiết lộ config metadata và secrets. Kiểm tra effective config qua secured diagnostics đã redacted, không dump toàn bộ environment trong incident ticket.

## 31. Secret rotation: lúc nào code 18 xuất hiện rải rác?

~~~text
T0: orders_api_v1 + password v1
    12 Pods hoạt động

T1: Password server chuyển sang v2
    Secret Manager có v2

T2: 5 Pods được restart với secret v2
    7 Pods vẫn có client/pool v1

T3: Pods cũ cần tạo connection mới
    -> AuthenticationFailed(18)
~~~

### 31.1. Existing pooled connections có thể che lỗi

Một connection đã xác thực trước khi rotation có thể vẫn hoạt động trong thời gian nhất định. New connections mới lộ secret cũ. Test rotation phải tạo **MongoClient/TLS/SCRAM connection mới**.

### 31.2. Dual-account pattern

~~~text
Provision app_user_v2 with approved roles
            |
Stage secret v2
            |
Canary new MongoClient
            |
Business read/write permission tests
            |
Rollout all Pods/workers
            |
Confirm no consumers using v1
            |
Revoke app_user_v1
~~~

### 31.3. Role parity mới là cạm bẫy

Nếu user v2 được tạo với password đúng nhưng thiếu custom role của v1:

~~~text
Authentication PASS
find PASS
insert Unauthorized(13)
~~~

Không reset password v2; review approved roles/actions và làm permission smoke tests trước khi rollout tiếp.

### 31.4. Secret compromise khác rotation định kỳ

Nếu v1 bị lộ, không duy trì v1 mãi để thuận tiện rollback. Sử dụng security incident process, thu hồi, rotate và theo dõi abuse.

## 32. Atlas: phân biệt User Access và Database Access

Trong Atlas, bạn cần phân biệt:

- **Project/Organization access**: ai quản lý project.
- **Database users**: principal nào có thể authenticate với mongod/mongos.
- **Database roles/specific privileges**: được làm gì trên data.
- **Network Access**: ứng dụng có tới được cluster hay không.

### 32.1. Project Owner không thay database user

Đăng nhập Atlas web thành công không thể hiện rằng app dùng được cùng email/password làm SCRAM credentials.

### 32.2. Atlas user được quản qua UI/API phù hợp

Điều chỉnh database user và custom roles qua Atlas UI, Atlas CLI, Atlas Administration API hoặc integration hỗ trợ, không bằng `db.createUser` trong cluster Atlas.

### 32.3. Restrict Access to Specific Clusters

Một DB user có thể tồn tại ở project nhưng chỉ được phép dùng ở cluster được chọn. Khi auth fail trên cluster mới, kiểm tra restrictions, username/credential và project.

### 32.4. Temporary database users

Atlas hỗ trợ temporary database users có thời hạn. Khi hết hạn, không nên mặc định kết luận password bị đổi; kiểm tra user lifecycle và approved access window.

## 33. Case study A: service chỉ đọc nhưng cần ghi

### Triệu chứng

`orders-api` đã chạy nhiều tháng chỉ với API GET, nay release thêm POST tạo đơn. POST báo `Unauthorized(13)`, GET vẫn tốt.

### Điều tra

- Exact action: insert.
- Exact namespace: orders.orders.
- ConnectionStatus: authenticated principal vẫn đúng.
- Role: read on orders.
- Change timeline: POST mới phát hành.

### Xử lý

Thiết kế chính sách write cho service, approve privilege `insert` trên collection cần, hoặc tách write service principal nếu phù hợp. Test cả GET/POST bằng canary data.

### Không nên

Đổi password, bật auth false hoặc cấp root.

## 34. Case study B: MongoDB query có $lookup

### Triệu chứng

`find` trên orders thành công; aggregation mới có `$lookup` từ customers thất bại code 13.

### Điều tra

Pipeline chạm cả orders và customers. User có quyền find trên source nhưng chưa chắc có find trên foreign collection.

### Xử lý

Nếu nghiệp vụ hợp lệ, cấp quyền đọc đúng collection foreign, có phê duyệt. Không cấp readWrite toàn database khi chỉ cần find.

### Kiểm chứng

Chạy pipeline thật với principal đã cấp quyền, không chỉ ping hay find riêng source.

## 35. Case study C: sau deploy, Spring tạo index thất bại

### Triệu chứng

Application context startup báo lỗi ở `createIndexes`. User có thể read/write data nếu tự gọi CRUD.

### Nguyên nhân

Runtime user chỉ có data privileges, còn application đang cố tự tạo indexes hoặc dùng custom role thiếu createIndex.

### Xử lý

Chuyển schema/index migrations sang pipeline và principal có quyền đúng, không trao admin rights thường trực cho application.

### Kiểm chứng

Index đã được tạo theo kế hoạch, app runtime vẫn chạy với least privileges, và startup không thực thi migration ngoài scope.

## 36. Case study D: Atlas user thấy cluster nhưng app không login

### Triệu chứng

Nhân viên có Project Owner trên Atlas UI; Java Driver nhận `AuthenticationFailed(18)`.

### Điều tra

Đã tạo database user cho Java app chưa? Authentication mechanism, authSource, secret version, project/cluster restriction và URI có đúng không?

### Xử lý

Sử dụng database principal riêng, không đưa Atlas web credentials vào URI.

### Kiểm chứng

New MongoClient authenticate và chạy permission smoke test trên đúng database/collection.

## 37. Case study E: một Pod còn dùng password cũ

### Triệu chứng

Tỷ lệ authentication failures chỉ xuất hiện khi autoscaler tạo Pods mới hoặc khi connection pool mở thêm sockets.

### Điều tra

So secret reference/version theo Pod, app release, Kubernetes ConfigTree/environment và MongoClient lifecycle.

### Xử lý

Hoàn tất rollout secret mới và quyền đúng, tạo canary new connections; không sửa role nếu server code là 18.

### Kiểm chứng

Auth error rate về baseline trên tất cả Pods; write operations chạy; không có consumer cũ còn dùng v1.

## 38. Case study F: monitoring agent không đọc được serverStatus

### Triệu chứng

Application business queries bình thường. Monitoring exporter báo code 13 tại `serverStatus`.

### Nguyên nhân

Exporter đang dùng business user chỉ có read/CRUD quyền nhưng thiếu monitoring privileges.

### Xử lý

Tạo monitoring principal với role/action đúng, tách với app user. Test các commands mà exporter thực sự cần.

### Kiểm chứng

Exporter khỏe, metrics khôi phục, database business user không bị tăng quyền.

## 39. Runbook chung cho AuthenticationFailed(18)

1. Xác nhận MongoDB server có trả code 18, không phải lỗi TCP/TLS.
2. Xác định principal dự kiến và auth mechanism.
3. Kiểm tra database chứa user và `authSource`.
4. Kiểm tra secret source/version, percent-encoding và config precedence.
5. Xem thay đổi gần đây: rotation, deleted user, project change.
6. Thử new connection/canary với credentials qua đường truyền bí mật.
7. Nếu credential compromised, dùng incident security rotation thay vì rollback bừa bãi.
8. Kiểm chứng đúng business operations sau khi auth thành công.
9. Theo dõi error rate và retry/connection churn.
10. Lưu timeline, action và evidence đã redacted.

### 39.1. Stop condition

Nếu xuất hiện dấu hiệu brute force/credential leakage, phối hợp Security thay vì chỉ tăng retries hoặc khóa nhầm mọi tài khoản.

## 40. Runbook chung cho Unauthorized(13)

1. Lấy command và namespace bị từ chối.
2. Xác nhận user đã authenticate và connection dùng đúng principal.
3. Dùng `connectionStatus(showPrivileges:true)` trên current principal.
4. Xác định action thực sự cần cho command.
5. Đối chiếu resource scope: database/collection/cluster.
6. Kiểm tra custom role inheritance, Atlas restrictions, app profile.
7. Xem release/DDL/role change timeline.
8. Chỉ cấp quyền tối thiểu đã phê duyệt hoặc sửa code/target DB.
9. Kiểm tra đúng command trên canary fixture.
10. Thử negative permissions để bảo đảm không cấp thừa.
11. Ghi audit, owner, thời hạn nếu quyền tạm thời.
12. Theo dõi Unauthorized rate và service SLO sau change.

### 40.1. Không đổi password cho code 13 theo phản xạ

Một code 13 là bằng chứng cần xem authorization. Nếu cùng lúc có code 18, điều tra từng loại riêng thay vì trộn thành một nguyên nhân.

## 41. Incident evidence mẫu

~~~yaml
incidentId: INC-2026-11-14-DB-AUTH
service: orders-api
environment: production
firstObservedUtc: 2026-11-14T06:15:00Z
operation: insertOne
namespace: orders.outbox
errorCode: 13
errorCodeName: Unauthorized
databasePrincipal: orders_api_v2
authDatabase: admin
mechanism: SCRAM-SHA-256
secretReference: secret-version-id-not-the-value
changeReference: CHG-2026-0442
hypothesis: missing-insert-privilege
observedImpact: writes-fail-for-new-pods
status: investigating
~~~

Đây là YAML sự cố minh họa, không phải cấu hình MongoDB. Không lưu passwords, URI thực hoặc raw customer document.

### 41.1. Timeline ví dụ

~~~text
06:10Z  orders_api_v2 provisioned
06:12Z  Canary rollout
06:15Z  INSERT errors code 13
06:17Z  READ calls pass with same principal
06:20Z  Effective privileges lack insert on outbox
06:25Z  Approved role fix
06:29Z  New connection + canary write PASS
06:35Z  Error rate back to baseline
~~~

### 41.2. Observation và hypothesis khác nhau

- Observation: Server trả code 13 cho insertOne.
- Hypothesis: user v2 thiếu insert.
- Evidence: effective privileges không có insert trên target resource.
- Mitigation: cấp privilege hẹp hoặc sửa role provisioning.
- Root cause: credential rotation workflow không kiểm tra role parity.
- Prevention: positive/negative permission smoke tests.

## 42. Logs, alerts và bảo mật thông tin

Các fields có thể ghi:

- Error category/code/codeName.
- Operation name.
- Namespace nếu được policy cho phép.
- Principal logical ID.
- Application release/Pod ID.
- Secret version **reference**, không phải value.
- Trace ID và UTC timestamp.
- Relevant change/incident ID.

Không log:

- Full connection URI có password.
- Private key, JWT/IdP token, SCRAM secret.
- Full document hoặc query filter chứa PII.
- Full `process.env` hoặc Actuator `env` output.
- Raw stack trace gửi qua thông báo bên ngoài chưa qua redaction.

### 42.1. Alert AuthenticationFailed tăng

Có thể do rollout lỗi hoặc brute-force. Tách metrics theo logical principal/service, source network (nếu policy cho phép), environment và thời gian rotation.

### 42.2. Alert Unauthorized tăng

Có thể do release mới, role drift hoặc hành động truy cập trái phép. Kết hợp action/namespace, app version và change calendar.

### 42.3. Không tăng retry vô hạn

Bad password/role thiếu là lỗi cấu hình hoặc security policy, không nên retry vô hạn mỗi mili giây; nó tạo log storm và connection pressure.

## 43. 401 và 403 của HTTP không phải code 18 và 13 của MongoDB

~~~text
End user -> API authentication & authorization
                      |
                      v
                Spring service
                      |
                      v
              MongoDB app identity
                      |
                      v
             MongoDB authN / authZ
~~~

- HTTP 401 thường nói về credential của **người gọi API**.
- HTTP 403 thường nói về quyền của **người gọi API**.
- MongoDB code 18 và 13 nói về **database principal của ứng dụng**.

Nếu backend app user thiếu `insert`, trả HTTP 403 cho mọi end user có thể làm họ hiểu sai rằng họ bị cấm tạo đơn. Ứng dụng thường cần xử lý như backend failure và ghi incident theo API error policy.

### 43.1. Tenant authorization là lớp khác

MongoDB `readWrite` trên collection không tự bảo đảm service chỉ trả orders của tenant hiện tại. App phải có tenant/user authorization riêng và query filters phù hợp.

## 44. Kiểm thử tự động quyền dương và âm

| Scenario | User | Operation | Expected |
|---|---|---|---|
| Login đúng | reader | authenticate | PASS |
| Login sai password | reader | authenticate | Code 18 |
| Login sai authSource | reader | authenticate | Code 18 |
| Đọc data | reader | find orders | PASS |
| Ghi data | reader | insert orders | Code 13 |
| Đọc/ghi | writer | insert orders | PASS |
| Cross database | writer | find another DB | Code 13 |
| Hẹp collection | orders_ingest | insert orders | PASS |
| Hẹp action | orders_ingest | update orders | Code 13 |
| Tạo index | custom CRUD user | createIndex | Code 13 nếu thiếu action |
| Monitor | read-only user | serverStatus | Code 13 nếu thiếu privilege |
| Change stream | custom user | watch | Yêu cầu changeStream/find |
| Secret rotation | user v2 | CRUD canary | PASS nếu role parity đúng |
| Wrong CA | test client | connect | TLS failure |
| Broken DNS | test runner | connect | Network/DNS failure |

### 44.1. Test ở MongoDB thật

Mocks giúp test classifier nhưng không chứng minh server RBAC. Dùng lab MongoDB có authorization bật để kiểm tra credentials, roles và commands thực tế.

### 44.2. Test positive và negative

Không chỉ xác nhận `reader.find` thành công. Còn phải xác nhận `reader.insert` bị từ chối. Nếu cả hai đều PASS, có thể app đang dùng admin credentials hoặc roles quá rộng.

### 44.3. Không dùng production root trong CI

CI nên có users test riêng, database riêng và cleanup policy. Không gọi role management APIs trên production để chạy negative tests.

### 44.4. Re-test sau mọi thay đổi

Sau role grant/revoke hoặc rotation, tạo new client/connection rồi thử đúng business operation; một status green của cluster không chứng minh app permissions.

## 45. Chẩn đoán theo tình huống

| Tình huống | Nguyên nhân đáng kiểm tra |
|---|---|
| Lỗi ngay lúc login | Username/password/authSource/mechanism |
| Lỗi khi có Pod mới | Secret rotation/client lifecycle |
| find PASS, insert FAIL | Thiếu insert action |
| CRUD PASS, createIndex FAIL | Migration permission |
| CRUD PASS, serverStatus FAIL | Cluster-monitoring role |
| find PASS, aggregate lookup FAIL | Foreign collection find |
| find PASS, watch FAIL | changeStream privilege |
| App A PASS, App B FAIL | Principal/MongoClient config khác |
| Atlas UI PASS, Java auth FAIL | Atlas user vs DB user |
| Login PASS, thao tác DB khác FAIL | Role scope sai |
| Cùng user, role mới chưa có hiệu lực | Propagation/cache/client lifecycle |
| Network timeout, không có 18 | DNS/network/topology |
| TLS exception, không có 13 | CA/SAN/truststore |
| Backend 13, API trả 403 | Sai phân loại tầng HTTP |

## 46. Checklist production

### Authentication

- [ ] Mỗi service/environment có principal riêng.
- [ ] Mechanism phù hợp server/driver.
- [ ] `authSource` khớp nơi user tồn tại.
- [ ] URI credentials percent-encoded đúng.
- [ ] TLS CA/hostname verification đầy đủ.
- [ ] Không hardcode secret/URI trong Git hoặc image.
- [ ] Secret version được theo dõi bằng reference ID.
- [ ] New MongoClient được test sau rotation.
- [ ] Có kế hoạch thu hồi credential bị lộ.
- [ ] DNS/Atlas network access được quản lý an toàn.

### Authorization

- [ ] Có permission matrix theo service.
- [ ] Role/action/resource scope đúng.
- [ ] Không cấp `root` cho business runtime.
- [ ] Tách migration/backup/monitoring identities.
- [ ] Atlas users và DB users được quản đúng hệ thống.
- [ ] Có audit inherited/effective privileges.
- [ ] Có positive và negative tests.
- [ ] Role grants được phê duyệt.
- [ ] Temporary privileges có hạn thu hồi.
- [ ] Tenant/user authorization được kiểm tra tại app.

### Troubleshooting

- [ ] Log error codes 13/18 và đúng operation.
- [ ] Không gom network/TLS/timeout vào authentication.
- [ ] connectionStatus được đọc bằng đúng principal.
- [ ] Không test quyền bằng shell còn admin identity.
- [ ] Không in full URI/credentials/PII.
- [ ] Có runbook rotation và RBAC drift.
- [ ] Có alert auth failures và unauthorized activity.
- [ ] Incident có timeline, owner và change references.
- [ ] Có canary permission smoke test sau mitigation.
- [ ] Không đóng incident chỉ vì ping thành công.

## 47. Bài tập thực hành

Chỉ chạy những bài liên quan user/role/secret hoặc ghi dữ liệu trên MongoDB **lab** đã bật authorization.

### Bài 1 — Hai định nghĩa

Phân biệt authentication và authorization. Một user password đúng nhưng roles rỗng có login được không?

### Bài 2 — Mã lỗi

Giải thích code 18 và 13. Vì sao không nên phân loại chỉ theo từ “auth” trong message?

### Bài 3 — Layer chẩn đoán

Sắp xếp DNS, TCP, TLS, authentication, authorization và query execution.

### Bài 4 — authSource

User tạo tại admin, app DB là orders. URI cần authSource nào?

### Bài 5 — Sai authSource

User tồn tại ở orders nhưng authSource=admin. Có thể gặp lỗi gì?

### Bài 6 — URI encoding

Password chứa @ và #. Cách tránh parse sai và lộ secret?

### Bài 7 — Atlas SRV

Pod không resolve hostname trong URI SRV. Có thể kết luận password sai không?

### Bài 8 — TLS

Java báo PKIX path building failed. Đây là xác thực MongoDB hay certificate trust?

### Bài 9 — X.509

TLS handshake PASS, user mapping X.509 FAIL. Hai bước có giống nhau không?

### Bài 10 — OIDC/IAM

Token hợp lệ nhưng user thiếu find. Đây là lỗi gì?

### Bài 11 — connectionStatus

Giải thích authenticatedUsers, authenticatedUserRoles và authenticatedUserPrivileges.

### Bài 12 — Admin session

Vì sao không gọi db.auth(reader) trên admin mongosh cũ rồi dùng kết quả để kiểm tra quyền reader?

### Bài 13 — Role read

Tạo reader, thử findOne và insertOne. Kỳ vọng từng lệnh?

### Bài 14 — Role readWrite

User có role readWrite trên dev. Có tự được ghi prod không?

### Bài 15 — dbAdmin

Vì sao role dbAdmin không nên được coi là role business readWrite?

### Bài 16 — Custom role

Tạo role find + insert trên orders, không update. Thiết kế negative tests.

### Bài 17 — Role inheritance

Một role có thể kế thừa role khác. Làm sao kiểm tra effective privileges?

### Bài 18 — Atlas UI

Project Owner có thể dùng luôn Atlas email/password làm MongoDB SCRAM login không?

### Bài 19 — Atlas cluster restriction

Database user có thể chỉ được cấp quyền ở subset clusters không?

### Bài 20 — Aggregation

Pipeline $lookup foreign collection customers bị code 13. Nên kiểm tra gì?

### Bài 21 — Index

Spring Data startup createIndexes lỗi code 13. Có nên reset password?

### Bài 22 — Change streams

User có find nhưng watch bị code 13. Action nào có thể còn thiếu?

### Bài 23 — Transactions

Transaction cập nhật orders rồi insert outbox. Thiếu insert trên outbox dẫn tới gì?

### Bài 24 — Backup

Backup agent auth thành công nhưng thao tác metadata/oplog fail. Xem role nào?

### Bài 25 — Monitoring

Business read user bị serverStatus Unauthorized. Thiết kế monitoring account.

### Bài 26 — Spring Boot

So property prefix MongoDB của Boot 3.5 và 4.x.

### Bài 27 — Lazy connection

MongoClients.create(uri) chạy không ném lỗi. Có chắc SCRAM đã PASS không?

### Bài 28 — Java classifier

Viết code phân loại MongoCommandException.getErrorCode() thành AUTHENTICATION/AUTHORIZATION.

### Bài 29 — Spring Data cause chain

Repository ném DataAccessException. Làm thế nào tìm MongoException gốc?

### Bài 30 — Password rotation

Sau rotation chỉ một vài Pods nhận code 18. Kiểm tra secret version và new connections ra sao?

### Bài 31 — Role parity

Canary user v2 login PASS nhưng insert FAIL. Vì sao thay password không giải quyết?

### Bài 32 — HTTP mapping

Backend thiếu DB insert privilege có nên trả HTTP 403 cho user cuối không?

### Bài 33 — Data privacy

Nên log fields nào trong incident alert, fields nào phải redacted?

### Bài 34 — Permission matrix

Thiết kế quyền cho orders-api, order-indexer, migrator và backup-agent.

### Bài 35 — Negative tests

Vì sao cần assert reader không ghi được, ngoài assert reader đọc được?

### Bài 36 — Two faults

Một service có cả server selection timeout và code 18 ở các Pods khác nhau. Vì sao không gộp thành một nguyên nhân?

### Bài 37 — Brute force

AuthenticationFailed tăng từ IP lạ. Phân biệt secret rollout bug và malicious attempts.

### Bài 38 — Role propagation

DBA vừa grant role, Pod cũ vẫn báo code 13. Bạn sẽ kiểm tra client/session/cache/rollout thế nào?

### Bài 39 — Tenant isolation

MongoDB role readWrite trên orders có tự phân biệt tenantId không? App cần làm gì?

### Bài 40 — Incident RCA

Viết RCA cho case user v2 sau rotation authenticate được nhưng insert orders.outbox bị code 13: trigger, impact, evidence, fix và prevention.

## 48. Tổng kết

Khi MongoDB báo lỗi bảo mật, đừng xử lý mọi trường hợp như một vấn đề password:

1. **Authentication** trả lời *ai đang kết nối*. Lỗi điển hình: **18 — AuthenticationFailed**. Kiểm tra principal, authSource, cơ chế, credentials/token/certificate, secret version và URI encoding.
2. **Authorization** trả lời *principal đó có được làm action này trên resource này không*. Lỗi điển hình: **13 — Unauthorized**. Đọc effective privileges, command, namespace và scope của roles.
3. **Network/TLS/topology** là lớp riêng. Không tự thay password hoặc cấp root nếu chưa nhận được server authentication/authorization error.
4. **Atlas UI/project users khác MongoDB database users**. Quản DB principals bằng cơ chế Atlas hỗ trợ.
5. **Java/Spring Data** có exceptions và wrappers; cần đọc error codes/cause chain, không dựa vào log string hoặc việc MongoClient được tạo thành công.
6. **Khắc phục tối thiểu, có audit**. Chỉ cấp đúng action/resource đã phê duyệt, thử cả positive và negative permissions, không tắt TLS và không để lộ secrets.
7. **Vận hành tin cậy** đòi hỏi canary new connections, role parity sau rotation, monitoring và runbook cho auth failures/Unauthorized incidents.

**Ghi nhớ:** *Code 18 hỏi “Bạn là ai?”; code 13 hỏi “Bạn được phép thực hiện việc này ở đây không?”.*

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Error Codes](https://www.mongodb.com/docs/manual/reference/error-codes/)
- [MongoDB Manual — connectionStatus](https://www.mongodb.com/docs/manual/reference/command/connectionStatus/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Authorization](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual — Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB Manual — Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/)
- [MongoDB Manual — Create a User on Self-Managed Deployments](https://www.mongodb.com/docs/manual/tutorial/create-users/)
- [MongoDB Manual — db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/)
- [MongoDB Manual — db.createRole()](https://www.mongodb.com/docs/manual/reference/method/db.createRole/)
- [MongoDB Manual — db.getUser()](https://www.mongodb.com/docs/manual/reference/method/db.getUser/)
- [MongoDB Manual — listCollections](https://www.mongodb.com/docs/manual/reference/command/listCollections/)
- [MongoDB Atlas — Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [MongoDB Atlas — Custom Database Roles](https://www.mongodb.com/docs/atlas/security-add-mongodb-roles/)
- [MongoDB Atlas — Organization and Project Access](https://www.mongodb.com/docs/atlas/organizations-projects/)
- [MongoDB Atlas — Atlas User Roles](https://www.mongodb.com/docs/atlas/reference/user-roles/)
- [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/)
- [MongoDB Java Sync Driver — Authentication](https://www.mongodb.com/docs/drivers/java/sync/current/security/authentication/)
- [Spring Data MongoDB — Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
