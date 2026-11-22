# User, role và phân quyền theo nguyên tắc tối thiểu trong MongoDB

## 1. Bài toán bảo mật: một dịch vụ không nên có mọi quyền

Giả sử nền tảng cho thuê nhà có bốn collections: **listings**, **owners**, **payments** và **auditLogs**. Một API tìm căn hộ chỉ cần đọc tin đăng đang hoạt động. Một API quản lý tin đăng cần thêm/sửa tin. Worker đối soát thanh toán cần đọc payment và cập nhật một trạng thái đã được xác nhận. Nhân viên vận hành cần quan sát tình trạng cluster.

Nếu cả bốn thành phần dùng cùng một MongoDB account có quyền **root**, một lỗ hổng ở API tìm kiếm có thể trở thành quyền xóa giao dịch, đổi tài khoản quản trị hoặc phá hủy index. Đây là lý do của **nguyên tắc đặc quyền tối thiểu (least privilege)**:

> Mỗi danh tính chỉ được cấp những hành động cần thiết, trên đúng tài nguyên, trong đúng thời gian và phạm vi phục vụ công việc.

Trong MongoDB, một cơ chế cốt lõi để thực hiện nguyên tắc này là **Role-Based Access Control (RBAC)**:

~~~text
Ứng dụng / nhân viên / worker
              |
       AUTHENTICATION
       "Bạn là ai?"
              |
              v
           DATABASE USER
              |
        Được gán ROLE(s)
              |
              v
      ROLE chứa PRIVILEGE(s)
              |
      +-------+----------+
      |                  |
   RESOURCE            ACTION
 DB / collection    find/insert/
                    update/remove...
      |                  |
      +---------+--------+
                |
         AUTHORIZATION
    "Có được thực hiện không?"
                |
         Allow / Deny
~~~

Trong ví dụ này, user dành cho Search API nên có action **find** trên **listings**; không cần **insert**, **update**, **remove**, **createIndex**, **userAdmin** hay quyền trên **payments**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **authentication** với **authorization**.
2. Hiểu **user**, **authentication database**, **role**, **privilege**, **resource** và **action**.
3. So sánh **built-in roles** với **custom roles**.
4. Xây ma trận least privilege cho API, worker, analytics, CDC, monitoring và migration.
5. Tạo role giới hạn ở **một collection**, chỉ có actions thực sự cần.
6. Tạo database users, kết nối với **authSource** đúng và kiểm tra quyền hiện tại.
7. Phân biệt lỗi đăng nhập với **Unauthorized**.
8. Giải thích vì sao MongoDB RBAC không tự giới hạn documents theo **tenantId**.
9. Xử lý credentials, TLS, rotation, audit, cấp/thu hồi quyền và sự cố.
10. Thực hành lab mongosh an toàn với hai roles, hai users và phép thử read/write.

> **Phạm vi lab:** những lệnh tạo users/roles dành cho **MongoDB self-managed lab cô lập đã bật authorization**, do người có quyền quản trị thực hiện. Trên **MongoDB Atlas**, quản lý database users/custom roles có giao diện và API riêng; không giả định mọi lệnh quản trị self-managed đều chạy được ở Atlas. Không dùng các ví dụ cấp quyền này để thử trên production hoặc cluster chia sẻ.

## 2. Authentication và authorization là hai câu hỏi riêng

### 2.1. Authentication: xác minh danh tính

Khi client kết nối, MongoDB có thể xác minh:

- Username và password với cơ chế **SCRAM**.
- X.509 client certificate.
- Kerberos/LDAP trong những editions và triển khai hỗ trợ.
- OIDC/federated authentication ở các deployment hỗ trợ.

Tính khả dụng phụ thuộc **phiên bản, edition và loại deployment**. Authentication có thể thành công mà user vẫn không được phép đọc bất kỳ collection nào.

### 2.2. Authorization: kiểm tra quyền thao tác

Sau authentication, MongoDB kiểm tra lệnh:

~~~text
User X chạy find() trên app.listings:
  có privilege find trên app.listings?
    -> Có: cho phép
    -> Không: Unauthorized

User X chạy deleteMany() trên app.payments:
  có privilege remove trên app.payments?
    -> Có: cho phép
    -> Không: Unauthorized
~~~

Đây không chỉ là bước kiểm tra khi user đăng nhập. Authorization áp dụng tới các commands cần privileges trong suốt thời gian user làm việc.

### 2.3. Các lỗi cần phân biệt

| Triệu chứng | Ý nghĩa thường gặp | Kiểm tra |
| --- | --- | --- |
| **AuthenticationFailed** | Không xác minh được danh tính | User, password, authSource, mechanism |
| **Unauthorized**, thường code 13 | Đã xác thực nhưng action không được phép | Roles, resource, inherited privileges |
| **Connection refused/timeout** | Không kết nối tới server | Host, port, DNS, firewall |
| **TLS handshake/certificate error** | Kênh TLS hoặc danh tính server có vấn đề | CA, hostname, trust chain |
| **Command not found/unsupported** | Tính năng/version/triển khai khác | MongoDB version và API hỗ trợ |

**Không cấp root để chữa tất cả lỗi.** Đổi role không sửa lỗi mạng hoặc certificate; đổi mật khẩu cũng không cấp quyền find.

### 2.4. Có user chưa chắc authorization đã bật

Một MongoDB local chạy không bật access control có thể cho phép thao tác mà không yêu cầu role. Vì vậy, một câu find chạy thành công trên máy dev không chứng minh bạn đã kiểm tra RBAC.

Bật authorization trên server là công việc quản trị riêng: cần chuẩn bị user quản trị, cơ chế bootstrap, kế hoạch chuyển đổi client, TLS và đường phục hồi. Bài này **không** thực hiện hoặc khuyến nghị đổi cấu hình mongod trong lúc học.

## 3. User là danh tính, không phải collection

### 3.1. User và authentication database

Trong MongoDB với internal database users, một user được tạo trong **database xác thực**.

Ví dụ:

~~~text
admin.svc_search
mongo_security_lab_329.svc_search
~~~

Đây là hai danh tính khác nhau dù có cùng username.

Nếu tạo:

~~~javascript
db.getSiblingDB("mongo_security_lab_329").createUser({
  user: "svc_search",
  pwd: passwordPrompt(),
  roles: []
});
~~~

thì user thuộc authentication database **mongo_security_lab_329**. Client cần xác thực đúng database đó, chẳng hạn qua **authSource=mongo_security_lab_329**. Nếu tạo user ở **admin** và gán role ở database ứng dụng, authSource vẫn thường là **admin**.

### 3.2. Tên user không đại diện cho quyền

Một account tên **readonly** vẫn có thể được gán role **readWrite**. Một account tên **service_admin** có thể chỉ có quyền find. Tên chỉ là quy ước, không phải kiểm soát bảo mật.

Để biết quyền thật, phải kiểm tra roles và privileges được gán cũng như quyền kế thừa.

### 3.3. Danh tính riêng cho từng workload

Nên tách:

~~~text
svc_listing_search_prod
svc_listing_writer_prod
job_payment_report_prod
job_audit_append_prod
job_schema_migration_prod
ops_cluster_monitor
human_operator_...
~~~

Vì mỗi thành phần có chức năng và blast radius khác nhau, chúng không nên chia sẻ một user/password dùng chung.

### 3.4. Human identities khác service identities

Nhân viên cần tài khoản gắn cá nhân, SSO/MFA hoặc cơ chế tập trung khi triển khai hỗ trợ, phê duyệt và audit. Service nên có credentials được cấp theo workload, không có nhân viên nhập mật khẩu thủ công vào code. CI/CD migration có tài khoản riêng với quyền quản trị schema trong thời gian cần thiết.

## 4. Role, privilege, resource và action

### 4.1. Một privilege cụ thể

~~~javascript
{
  resource: {
    db: "mongo_security_lab_329",
    collection: "listings"
  },
  actions: ["find"]
}
~~~

Privilege này cho phép **find** trên collection **listings** thuộc database **mongo_security_lab_329**. Nó không cho phép insert vào listings và cũng không cho phép find trên payments.

### 4.2. Resource rộng/hẹp

Các kiểu phạm vi resource trong MongoDB gồm:

- **Một collection cụ thể** trong một database.
- **Các collections trong một database** theo quy tắc khai báo tương ứng.
- **Một phạm vi cluster** dành cho những actions quản trị tương ứng.

Role custom ở database không phải admin có các giới hạn khi định nghĩa privileges trên database khác hoặc cluster; nếu cần cross-database/cluster privileges, phải tuân thủ quy tắc tạo role của server. **Không** dùng một role phạm vi cluster khi tác vụ chỉ cần một collection.

### 4.3. Một số actions tiêu biểu

| Action | Thao tác/nhu cầu |
| --- | --- |
| **find** | Đọc documents |
| **insert** | Thêm documents |
| **update** | Sửa documents |
| **remove** | Xóa documents |
| **createIndex** | Tạo index |
| **listIndexes** | Xem index definitions |
| **createCollection** | Tạo collection |
| **dropCollection** | Xóa collection |
| **listCollections** | Xem metadata collections |
| **collStats**, **dbStats** | Xem thống kê |
| **changeStream** | Theo dõi Change Streams trong scope hỗ trợ |
| **listDatabases** | Liệt kê database theo quyền |

Tên hành động **remove** trong RBAC liên quan đến thao tác xóa như deleteOne/deleteMany. **userAdmin** là tên của một built-in role, không phải một action thay thế cho toàn bộ các hành động quản lý user.

### 4.4. Multiple roles là phép hợp quyền

Giả sử user U có:

~~~text
Role A: find trên app.listings
Role B: insert/update trên app.listings
Role C: readWrite trên app
~~~

Quyền hiệu dụng của U gồm privileges của **cả A, B, C**. Role A hẹp không hạn chế quyền được role C cấp.

Đây là hiểu lầm nguy hiểm: **MongoDB RBAC thông thường không có mô hình “deny role” tự động phủ định quyền rộng từ role khác**. Nếu user đã có readWrite trên cả database, thêm một role read-only không khiến nó mất quyền ghi.

### 4.5. Role inheritance

Một custom role có thể kế thừa role khác:

~~~javascript
{
  role: "listingViewerPlus329",
  privileges: [],
  roles: [
    {
      role: "listingReader329",
      db: "mongo_security_lab_329"
    }
  ]
}
~~~

User được gán listingViewerPlus329 có thể nhận quyền từ listingReader329. Quyền hiệu dụng phải xem cả **direct privileges** và **inherited privileges**. Khi role gốc được sửa, các role/user kế thừa cũng có thể bị ảnh hưởng.

## 5. Built-in roles dùng khi nào?

### 5.1. Roles quản lý dữ liệu

| Built-in role | Ý nghĩa khái quát | Cảnh báo |
| --- | --- | --- |
| **read** | Quyền đọc dữ liệu trong database theo role definition | Có thể rộng nếu chỉ cần một collection |
| **readWrite** | Quyền đọc/ghi và các thao tác liên quan trong database | Quá rộng cho read-only API |
| **dbAdmin** | Quản trị metadata, index, schema... trên database | Không phải role CRUD hay root |
| **userAdmin** | Quản lý users/roles ở scope thích hợp | Rủi ro leo thang đặc quyền |
| **dbOwner** | Bao gồm các nhóm quyền dữ liệu, database và quản lý user | Không cấp cho ứng dụng thông thường |

Danh sách actions chính xác của từng built-in role do MongoDB quy định và có thể thay đổi theo phiên bản. Khi audit, hãy đối chiếu **tài liệu phiên bản server** hoặc **rolesInfo** thay vì đoán quyền từ tên role.

### 5.2. Roles cluster và vận hành

| Role | Nhu cầu thường gặp |
| --- | --- |
| **clusterMonitor** | Quan sát thông tin/metrics cluster |
| **clusterManager** | Một số tác vụ quản lý cluster |
| **hostManager** | Quản lý hệ thống/host theo khả năng server |
| **backup** | Tác vụ backup được công cụ hỗ trợ |
| **restore** | Tác vụ restore |
| **root** | Quyền quản trị rất rộng |

Một monitoring agent không cần khả năng restore hoặc userAdmin chỉ để xem CPU/replication. Một backup job cũng không cần trở thành credential của web API.

### 5.3. readWrite không phải least privilege cho mọi tác vụ ghi

Role readWrite trên database có phạm vi rộng hơn quyền **find, insert, update trên collection listings**. Nếu database có payments và users, API quản lý tin đăng không nên có quyền ghi vào các collections đó.

Tạo custom role để giới hạn cả **resource** lẫn **actions**.

### 5.4. dbAdmin khác userAdmin

Một job tạo index có thể cần quyền schema/index. Nó không cần quản lý password hay cấp roles. Ngược lại, IAM admin cần quản lý user/role, không nhất thiết phải truy cập dữ liệu giao dịch.

Đừng gộp mọi nhu cầu quản trị vào một account **dbOwner** nếu có thể tách chức năng.

### 5.5. Cẩn trọng với userAdmin

Role **userAdmin** cho phép nhiều thao tác quản lý users và roles theo phạm vi. Nếu có thể gán privileges rộng, nó trở thành đường leo thang quyền. Tài khoản dùng userAdmin phải được quản lý như tài khoản đặc quyền, không đưa vào environment variables của web API.

## 6. Thiết kế ma trận quyền theo nghiệp vụ

| Thành phần | Resource | Actions cần cân nhắc | Không nên cấp |
| --- | --- | --- | --- |
| **Listing Search API** | listings | find | insert, update, remove, createIndex |
| **Listing Write API** | listings | find, insert, update | remove nếu không xóa, userAdmin |
| **Payment Dashboard** | paymentSummaries | find | readWrite toàn app, truy cập raw PII không cần |
| **Payment Settlement Worker** | settlements | find/update hoặc insert theo nhiệm vụ | quyền trên user/admin |
| **Audit Append Worker** | auditLogs | insert | update/remove nếu audit append-only |
| **Change Stream Worker** | collection nguồn | find + changeStream theo watch scope | cluster admin |
| **Migration Job** | collections được đổi | createIndex, listIndexes, createCollection... khi cần | root thường trực |
| **Monitoring** | thông tin cluster phù hợp | monitoring privileges | data writes, userAdmin |
| **Backup** | dữ liệu/metadata theo công cụ backup | backup role/quyền tương đương | credential API |
| **Human DBA** | scope được ủy quyền | quyền quản trị theo approval | dùng hằng ngày trong API |

Đây là **ma trận khởi đầu**, không phải một whitelist áp dụng cho mọi bản MongoDB. Để chuyển thành role thật, phải điều tra commands mà service/driver thực sự chạy, sau đó cấp quyền đúng resource.

### 6.1. Read-only API

~~~javascript
db.listings.find({ status: "active" });

db.listings.aggregate([
  { $match: { status: "active" } },
  { $group: {
    _id: "$city",
    count: { $sum: 1 }
  } }
]);
~~~

Nếu hai truy vấn chỉ đọc collection listings thì action **find** trên listings là quyền nền tảng. Tuy nhiên, các aggregation pipelines đọc collection khác hoặc ghi đầu ra cần quyền bổ sung.

### 6.2. Worker chỉ update

Một worker chỉ sửa trạng thái, không cần xem toàn document, có thể chỉ cần **update**. Nếu worker phải đọc dữ liệu đầu tiên để ra quyết định thì cần thêm find. Cần phân biệt nhiệm vụ thật, không cho rằng “đã cập nhật được thì phải đọc được mọi thứ”.

### 6.3. Migration không nên chạy bằng app user

Framework có thể tự động tạo index khi startup. Nếu app user không có **createIndex**, lỗi khởi động có thể xuất hiện. Giải pháp là:

1. Tách schema migration thành một job triển khai riêng.
2. Dùng identity có quyền index/schema cần thiết.
3. Ngừng tự tạo index ở mọi instance production nếu có thể.
4. Giữ app runtime với quyền CRUD hẹp.

Không cấp quyền tạo index cho mọi API instance chỉ để tránh sửa cấu hình framework.

## 7. Tạo custom roles giới hạn vào một collection

### 7.1. Role chỉ đọc

~~~javascript
{
  role: "listingReader329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find"]
    }
  ],
  roles: []
}
~~~

Role này **không có** các actions insert, update, remove, createIndex hoặc quyền trên payments.

### 7.2. Role chỉ cho chỉnh sửa

~~~javascript
{
  role: "listingEditor329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find", "insert", "update"]
    }
  ],
  roles: []
}
~~~

Role này cho phép đọc, thêm và cập nhật listings, nhưng **không có remove**. Một action không được liệt kê ở role chỉ có thể được dùng nếu user nhận nó từ role khác; vì thế cần xem **tất cả roles của user**.

### 7.3. Vai trò không nên theo tên endpoint

Đặt tên role **canUseAdminPage** chưa mô tả rõ quyền MongoDB. Một role tốt cần được định nghĩa bằng resource/action và có tài liệu về workloads được phép dùng.

Ví dụ:

~~~text
Role: listingReader329
Owner: Listing Search team
Resource: mongo_security_lab_329.listings
Actions: find
Denied by omission: insert/update/remove/createIndex
Reason: Search API chỉ cần đọc tin đăng
~~~

### 7.4. Role không tạo row-level policy

Một role find trên listings sẽ được MongoDB hiểu là quyền tìm kiếm **trên collection đó**. Nó **không tự bổ sung điều kiện tenantId** vào các query. Điều này sẽ được phân tích sâu ở mục 13.

## 8. Lab mongosh tự chứa: dữ liệu, role và user

### 8.1. Yêu cầu môi trường

Chỉ dùng trên **self-managed MongoDB lab** có:

- Authorization đang bật.
- Một user quản trị bạn được phép sử dụng để tạo database, role và user.
- Database riêng **mongo_security_lab_329**.
- Không có user/role trùng tên với bài học.
- Hai mongosh sessions: một kết nối bằng admin, một bằng user test.

Nếu đang dùng MongoDB Atlas, hãy tham khảo cơ chế tạo **Database Users/Custom Roles qua Atlas UI/API**. Không chạy createUser self-managed trên cluster Atlas khi deployment không hỗ trợ.

### 8.2. Seed ba tin đăng bằng admin lab

Chạy trong mongosh **đã xác thực bằng tài khoản quản trị**:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_security_lab_329");

  if (!lab.getCollectionNames().includes("listings")) {
    lab.createCollection("listings");
  }

  const listings = lab.getCollection("listings");
  const samples = [
    {
      _id: "lab329-001",
      title: "Studio có bàn làm việc",
      tenantId: "t001",
      city: "HCM",
      status: "active",
      rentMillion: 12
    },
    {
      _id: "lab329-002",
      title: "Căn hộ hai phòng ngủ",
      tenantId: "t001",
      city: "HN",
      status: "draft",
      rentMillion: 18
    },
    {
      _id: "lab329-003",
      title: "Căn hộ cạnh công viên",
      tenantId: "t002",
      city: "HCM",
      status: "active",
      rentMillion: 14
    }
  ];

  for (const item of samples) {
    listings.replaceOne(
      { _id: item._id },
      item,
      { upsert: true }
    );
  }

  printjson({
    count: listings.countDocuments({
      _id: { $in: samples.map(s => s._id) }
    }),
    docs: listings.find({
      _id: { $in: samples.map(s => s._id) }
    }).sort({ _id: 1 }).toArray()
  });
})();
~~~

**Kết quả mong đợi:** count = **3**, gồm hai tin t001 và một tin t002. Script chỉ dùng ba _id cố định của lab, không drop collection. Chạy lại sẽ đưa các document mẫu về trạng thái ban đầu.

### 8.3. Tạo role listingReader329

Chạy **một lần** bằng admin lab:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

lab.createRole({
  role: "listingReader329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find"]
    }
  ],
  roles: []
});
~~~

Không gán thêm built-in **read** trên toàn database; làm vậy sẽ mở quyền đọc cả những collections khác.

### 8.4. Tạo role listingEditor329

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

lab.createRole({
  role: "listingEditor329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find", "insert", "update"]
    }
  ],
  roles: []
});
~~~

Editor **không có remove** và cũng không có userAdmin.

### 8.5. Tạo hai users

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

lab.createUser({
  user: "svc_listing_reader329",
  pwd: passwordPrompt(),
  roles: [
    {
      role: "listingReader329",
      db: "mongo_security_lab_329"
    }
  ]
});

lab.createUser({
  user: "svc_listing_editor329",
  pwd: passwordPrompt(),
  roles: [
    {
      role: "listingEditor329",
      db: "mongo_security_lab_329"
    }
  ]
});
~~~

**passwordPrompt()** yêu cầu nhập bí mật tương tác. Mỗi user cần mật khẩu mạnh và khác nhau. Đừng chép mật khẩu thật vào code, commit, terminal history hoặc tài liệu học.

Hai users được tạo trong **mongo_security_lab_329**, nên authentication database của họ cũng là **mongo_security_lab_329**. Nếu user/role đã tồn tại, createUser/createRole có thể lỗi; không dùng updateUser để ghi đè một đối tượng không rõ nguồn gốc.

### 8.6. Kiểm tra role definitions

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.getRole(
  "listingReader329",
  { showPrivileges: true }
));

printjson(lab.getRole(
  "listingEditor329",
  { showPrivileges: true }
));
~~~

Với mongosh/version có helper tương ứng, output cho biết privileges. Có thể dùng **rolesInfo** theo cách chính thức nếu helper khác biệt.

### 8.7. Kiểm tra user roles

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.getUser(
  "svc_listing_reader329",
  {
    showPrivileges: true,
    showCredentials: false
  }
));
~~~

Xem **roles**, **inheritedRoles** và **inheritedPrivileges** khi được trả về, không chỉ xem username.

## 9. authSource và kết nối bằng user chỉ đọc

### 9.1. Đăng nhập từ mongosh

Với MongoDB lab local self-managed:

~~~bash
mongosh "mongodb://127.0.0.1:27017/mongo_security_lab_329" --username svc_listing_reader329 --authenticationDatabase mongo_security_lab_329 --password
~~~

Mongosh hỏi password tương tác. Nếu lab dùng hostname/port khác, thay bằng địa chỉ đúng. Đây là cấu hình local; **kết nối qua mạng ở production cần TLS và xác minh server**.

### 9.2. Authentication database khác target database

URI tương ứng có thể chứa:

~~~text
mongodb://127.0.0.1:27017/mongo_security_lab_329?authSource=mongo_security_lab_329
~~~

Nếu user tạo trong **admin** nhưng có role trên database lab, authSource thường phải là **admin**. Nếu user tạo trong lab nhưng client cố xác thực ở admin, có thể gặp AuthenticationFailed dù password đúng.

Không dùng việc cấp quyền rộng hơn để “sửa” vấn đề authSource.

### 9.3. Kiểm tra danh tính hiện tại

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

const status = lab.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});

printjson({
  users: status.authInfo?.authenticatedUsers,
  roles: status.authInfo?.authenticatedUserRoles,
  privileges: status.authInfo?.authenticatedUserPrivileges
});
~~~

Mục đích là xác định **kết nối hiện tại đang dùng account nào**. Khi có nhiều mongosh sessions, rất dễ vô tình chạy phép thử dưới quyền admin thay vì reader.

### 9.4. Positive test — read thành công

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");
const listings = lab.getCollection("listings");

printjson(
  listings.find(
    { status: "active" },
    { _id: 1, title: 1, tenantId: 1 }
  ).sort({ _id: 1 }).toArray()
);
~~~

Nếu đang đăng nhập đúng **svc_listing_reader329**, lệnh find trên listings được cấp quyền. Nó có thể trả **lab329-001 và lab329-003**, dù hai document thuộc hai tenant khác nhau. Đây là ví dụ quan trọng chứng minh RBAC collection-level **không tự áp tenant filter**.

### 9.5. Negative test — update phải bị từ chối

Để tránh hủy dữ liệu, test một **_id chắc chắn không tồn tại**, không dùng upsert và **kiểm tra danh tính trước**:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");
const status = lab.runCommand({
  connectionStatus: 1
});

const authenticatedUsers = status.authInfo?.authenticatedUsers || [];
const isReader = authenticatedUsers.some(u =>
  u.user === "svc_listing_reader329" &&
  u.db === "mongo_security_lab_329"
);

if (!isReader) {
  throw new Error(
    "Sai danh tính; không thực hiện phép thử quyền."
  );
}

let allowedUnexpectedly = false;

try {
  lab.getCollection("listings").updateOne(
    { _id: "lab329-NOT-EXISTING-permission-check" },
    { $set: { status: "active" } }
  );
  allowedUnexpectedly = true;
} catch (error) {
  printjson({
    expectedDenial: true,
    code: error.code,
    codeName: error.codeName,
    message: error.message
  });
}

if (allowedUnexpectedly) {
  throw new Error(
    "Phép update được cho phép ngoài kỳ vọng; kiểm tra role!"
  );
}
~~~

Kết quả mong đợi: MongoDB từ chối với **Unauthorized**. Nếu quyền bất ngờ rộng hơn, query không match document nào nên không thay đổi dữ liệu. **Không dùng deleteMany({})** hoặc dropCollection làm negative test — nếu bạn vô tình có quyền, dữ liệu thật có thể bị hủy.

### 9.6. “show collections” có thể lỗi dù find thành công

Role chỉ có **find** trên listings không nhất thiết có quyền:

~~~javascript
show dbs
show collections
db.listings.getIndexes()
db.stats()
~~~

Những lệnh đó có thể cần **listDatabases**, **listCollections**, **listIndexes** hoặc **dbStats**. Nếu application chỉ cần find() trên collection đã biết, việc “show collections” bị từ chối không phải lý do để cấp dbAdmin.

## 10. Kiểm tra quyền bằng connectionStatus, rolesInfo và usersInfo

### 10.1. Xem role đang có action gì

Với admin:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.runCommand({
  rolesInfo: {
    role: "listingReader329",
    db: "mongo_security_lab_329"
  },
  showPrivileges: true
}));
~~~

### 10.2. Xem user được gán gì

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.getUser(
  "svc_listing_reader329",
  {
    showPrivileges: true,
    showCredentials: false
  }
));
~~~

### 10.3. Xem connection hiện tại

~~~javascript
printjson(
  db.runCommand({
    connectionStatus: 1,
    showPrivileges: true
  })
);
~~~

**Đừng chỉ dựa vào tên role.** Một role tên reader có thể kế thừa quyền ghi. Quyền hiệu dụng là điều quan trọng để audit.

### 10.4. Khi thiếu quyền

Quy trình xử lý:

1. Ghi lại **database, collection, lệnh, action bị thiếu**.
2. Xác nhận current authenticated user và authSource.
3. Xem privileges hiệu dụng.
4. Xác định tác vụ đó có thuộc trách nhiệm service không.
5. Nếu có, cân nhắc cấp thêm **một action trên một resource cần thiết**.
6. Nếu không, thay đổi service để dùng identity/luồng triển khai đúng.
7. Test các hành động được phép và hành động phải bị từ chối.

Không xem một lỗi Unauthorized đơn lẻ là căn cứ để gán readWriteAnyDatabase.

## 11. Aggregation, $lookup và các actions bổ sung

### 11.1. Aggregation chỉ đọc

~~~javascript
db.getSiblingDB("mongo_security_lab_329")
  .getCollection("listings")
  .aggregate([
    { $match: { status: "active" } },
    {
      $group: {
        _id: "$city",
        count: { $sum: 1 }
      }
    }
  ]);
~~~

Đây là pipeline đọc listings. Quyền **find** trên source collection là cơ sở cho truy vấn này.

### 11.2. $lookup có thêm source

~~~javascript
db.listings.aggregate([
  {
    $lookup: {
      from: "owners",
      localField: "ownerId",
      foreignField: "_id",
      as: "owners"
    }
  }
]);
~~~

Pipeline đọc dữ liệu ở **owners**, nên phải xét quyền đọc owners theo lệnh/phiên bản. Không cấp read trên cả database chỉ vì một $lookup, đặc biệt nếu owners chứa PII. Có thể tạo **publicOwnerSummary** để tránh mở quyền vào bảng thông tin cá nhân chi tiết.

### 11.3. $out/$merge có side effects

Pipeline dùng **$out** hoặc **$merge** ghi dữ liệu sang collection đích. Một account chỉ có find trên nguồn không nên được kỳ vọng tự có quyền ghi đích.

Nếu API nhận pipeline tùy ý từ client, stage ghi dữ liệu là một nguy cơ đặc biệt. Server nên whitelist pipeline, giới hạn collection và dùng role đúng nhiệm vụ.

### 11.4. Change Streams

Consumer chỉ watch listings có thể cần:

~~~javascript
{
  resource: {
    db: "mongo_security_lab_329",
    collection: "listings"
  },
  actions: ["find", "changeStream"]
}
~~~

Đây là hình dạng privilege tham khảo cho collection-level Change Stream trong môi trường hỗ trợ. Watch cả database hoặc deployment có scope/quyền khác. **Không cấp root cho CDC worker** để giải quyết lỗi mở cursor.

### 11.5. Aggregation/transaction không nâng quyền

Nếu transaction cập nhật listings và ghi auditLogs, identity phải có **update trên listings** và **insert trên auditLogs**. Việc dùng transaction không cho phép lệnh vượt qua RBAC.

## 12. Least privilege theo vòng đời triển khai

### 12.1. Runtime user

Runtime user có quyền xử lý request nghiệp vụ. Khi API chỉ đọc, **find** là quyền cần ưu tiên. Không gắn IAM/schema migration vào runtime.

### 12.2. Migration user

Migration job có thể cần **createIndex**, **listIndexes**, **createCollection** và những actions khác phù hợp với schema migration thật. Nó có thể chỉ được dùng trong deploy window, qua môi trường CI/CD kiểm soát.

### 12.3. Monitoring user

Monitoring cần thông tin về server/replica set/shard, không tự cần truy vấn payments. Cân nhắc built-in **clusterMonitor** hoặc custom scope thích hợp với công cụ đang dùng.

### 12.4. Backup/restore user

Backup/restore có thể đòi quyền và quy trình cấp cluster, không chỉ find. Dùng identity riêng, hạn chế người/worker có thể truy cập credentials này. Quyền restore có thể gây thay đổi dữ liệu ở phạm vi rất lớn nếu bị lạm dụng.

### 12.5. Human administrator

Human DBA cần quyền quản trị theo quy trình, MFA/SSO khi khả dụng, audit và chính sách emergency access. Không dùng tài khoản này làm connection string cho API.

### 12.6. Temporary access

Một task tạo index trong một đêm không cần quyền createIndex ở API vĩnh viễn:

~~~text
Approval -> cấp quyền/identity tạm
        -> thực thi migration
        -> xác nhận output
        -> thu hồi quyền
        -> lưu audit/change record
~~~

Một role tồn tại lâu có quyền rộng nhưng không còn owner là nguồn rủi ro.

## 13. RBAC không tự tạo row-level tenant isolation

### 13.1. Vấn đề shared collection

Trong lab:

~~~javascript
{
  _id: "lab329-001",
  tenantId: "t001",
  title: "Studio..."
}

{
  _id: "lab329-003",
  tenantId: "t002",
  title: "Căn hộ..."
}
~~~

Một MongoDB user có action **find trên listings** có thể dùng:

~~~javascript
db.listings.find({});
~~~

và đọc documents của cả t001 và t002, nếu không có cơ chế ràng buộc khác ở application/architecture. Role đó **không chứa điều kiện** “chỉ cho thấy documents tenantId=t001”.

### 13.2. Bắt tenantId từ security context

Node.js backend:

~~~javascript
const tenantId = authenticatedContext.tenantId;
const requestedListingId = validatedParams.listingId;

const listing = await db
  .collection("listings")
  .findOne({
    _id: requestedListingId,
    tenantId: tenantId
  });
~~~

Trong production, tenantId phải do server xác minh từ token/session/quyền của user. Không được tin trực tiếp:

~~~javascript
const tenantId = req.query.tenantId;
~~~

nếu user không được phép chọn tenant ấy.

### 13.3. Update và delete cũng cần tenant predicate

~~~javascript
await db.collection("listings").updateOne(
  {
    _id: validatedListingId,
    tenantId: authenticatedContext.tenantId,
    status: "draft"
  },
  {
    $set: { status: "active" }
  }
);
~~~

Filter có **tenantId** và **status** nhằm bảo vệ cả quyền sở hữu và điều kiện nghiệp vụ. Role có update trên collection chỉ bảo đảm phạm vi collection, không bảo đảm ứng dụng update đúng document.

### 13.4. Lỗi object spread

Sai:

~~~javascript
const filter = {
  tenantId: authenticatedContext.tenantId,
  ...req.body.filter
};
~~~

Nếu client gửi tenantId khác, spread sau cùng có thể ghi đè tenantId đã xác minh.

Tốt hơn:

~~~javascript
const filter = {
  status: validatedStatus,
  city: validatedCity,
  tenantId: authenticatedContext.tenantId
};
~~~

Chỉ cho client đưa những filter fields và operators đã được whitelist; không cho chạy pipeline tùy ý nếu không có chính sách kiểm soát.

### 13.5. Nếu yêu cầu cách ly mạnh hơn

Cân nhắc:

| Mô hình | Lợi thế | Đánh đổi |
| --- | --- | --- |
| Shared collection + tenantId | Ít collections, vận hành tập trung | Application phải cưỡng chế tenant filter |
| Collection per tenant | Có thể scope collection roles riêng | Nhiều indexes/collections và lifecycle phức tạp |
| Database per tenant | Phân quyền, vận hành theo tenant rõ hơn | Provisioning, migration, connection management tăng |
| Dedicated cluster/region | Cách ly hạ tầng cao hơn | Chi phí/vận hành cao |

Không có lựa chọn “miễn phí”; nhưng cần trung thực rằng **core MongoDB RBAC thường cấp quyền theo resource như database/collection, không tự viết predicate row-level cho mọi find**.

## 14. Atlas project roles khác MongoDB database roles

Trên Atlas có ít nhất hai lớp:

1. **Atlas organization/project roles**: quyền quản lý dự án, cluster, mạng, backup và các cấu hình Atlas.
2. **MongoDB database users/roles**: quyền của connection identity khi thực thi find/insert/update/commands trong cluster.

Một người có quyền **Project Owner** trong Atlas UI không đồng nghĩa connection ứng dụng tự là database root. Một database user có readWrite cũng không có quyền tùy tiện thay Atlas project network settings.

Khi triển khai:

- Dùng Atlas UI/API để cấp quyền quản lý organization/project đúng người.
- Dùng **database access** để cấp identities/roles cho clients.
- Không đưa credentials Atlas Project Owner vào web API.
- Kiểm tra khả năng tạo **custom database roles** theo deployment.
- Không giả định **db.createUser()** dùng được cho mọi Atlas-managed cluster.

## 15. Secrets, TLS và phương thức authentication

### 15.1. SCRAM password

Với SCRAM, password phải mạnh, riêng theo service, được quản lý bằng secret manager. Khi cần chạy mongosh tương tác, dùng **--password** không kèm plaintext để chương trình yêu cầu nhập.

Không lưu:

~~~text
mongodb://admin:PlaintextPassword@prod-host:27017/app
~~~

trong source code, log hoặc ticket. URL-encoding password không làm nó trở thành dữ liệu công khai.

### 15.2. TLS

TLS bảo vệ kênh truyền và xác minh server endpoint. Password mạnh không thay thế TLS. Nếu gặp lỗi certificate:

- Kiểm tra CA bundle/trust chain.
- Kiểm tra hostname đúng với certificate.
- Kiểm tra server/client TLS version và cấu hình.
- Không tắt certificate verification trên production như một “quick fix”.

### 15.3. X.509

X.509 có thể dùng chứng chỉ client để xác thực trên môi trường hỗ trợ. Vẫn phải:

- Quản lý private keys.
- Rotation certificates.
- Xác thực CA/hostname thích hợp.
- Ánh xạ user/roles theo chính sách.

Chứng chỉ hợp lệ **không cấp quyền find hay update tự động** nếu authorization chưa cho phép.

### 15.4. OIDC/federated authentication

Deployment hỗ trợ OIDC có thể tích hợp IdP. Authentication có thể do identity provider thực hiện, nhưng cần ánh xạ danh tính/roles trong hệ MongoDB/Atlas theo đúng cơ chế. SSO không đồng nghĩa có mọi database privileges.

### 15.5. Không log secrets

Không viết:

~~~javascript
console.log(process.env.MONGODB_URI);
~~~

nếu URI có username/password. Error reporting, analytics và crash logs cũng cần **redact credentials**. Không chia sẻ output chứa secret hoặc nội dung data nhạy cảm ra diễn đàn công khai.

## 16. Rotation và thu hồi đặc quyền

### 16.1. Grant và revoke

MongoDB cung cấp các commands/helper như **grantRolesToUser** và **revokeRolesFromUser** để quản lý role assignments.

Ví dụ **chỉ minh họa**, không phải bước nên chạy trong lab vì nó nâng quyền reader:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

// KHÔNG CHẠY trên reader của lab nếu muốn giữ đúng negative test.
lab.grantRolesToUser(
  "svc_listing_reader329",
  [
    {
      role: "listingEditor329",
      db: "mongo_security_lab_329"
    }
  ]
);
~~~

Nếu đã cấp ngoài ý muốn, quản trị viên cần điều tra/review rồi thu hồi role tương ứng:

~~~javascript
lab.revokeRolesFromUser(
  "svc_listing_reader329",
  [
    {
      role: "listingEditor329",
      db: "mongo_security_lab_329"
    }
  ]
);
~~~

**Revoke role không đồng nghĩa drop user.** Thu hồi role thay đổi quyền, còn drop user làm danh tính không còn tồn tại trong authentication database.

### 16.2. Sửa role ảnh hưởng nhiều users

Nếu admin sửa custom role listingReader329 để thêm update, mọi user kế thừa role đó có thể bị mở quyền. Trước khi sửa role, kiểm tra:

1. Những user đang gán/kế thừa role.
2. Danh sách actions/resources trước và sau.
3. Có tạo đường leo thang quyền không.
4. Positive/negative tests ở staging.
5. Cơ chế rollout, audit và rollback.

### 16.3. Rotation nhiều instances

Nếu năm API replicas dùng cùng một credential:

~~~text
1. Chuẩn bị identity/secret mới với đúng roles.
2. Cấp secret mới tới runtime.
3. Chuyển dần replicas sang credential mới.
4. Xác minh tất cả replicas kết nối thành công.
5. Giám sát authentication failures.
6. Thu hồi credential cũ sau khi xác nhận.
~~~

Không xóa password cũ ngay khi mới cập nhật một instance, trừ khi cần phản ứng khẩn cấp trước credential đã bị lộ. Trong incident, ưu tiên an toàn và điều phối phục hồi theo playbook.

### 16.4. Quyền trên kết nối đang mở

Hiệu lực của thay đổi role/credential trên connections đang mở có thể liên quan đến topology/cache và phiên bản. Với thay đổi nhạy cảm, phải kiểm tra trên **new connections** và **existing connections** theo tài liệu server/deployment, không chỉ nhìn lệnh grant/revoke trả OK.

## 17. Node.js: ứng dụng chỉ đọc với identity riêng

Ví dụ độc lập (driver MongoDB, URL được cung cấp từ secret manager):

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_SEARCH_READ_URI
);

await client.connect();

try {
  const listings = client
    .db("mongo_security_lab_329")
    .collection("listings");

  // Production: lấy từ security context sau xác thực.
  const authorizedTenantId = "t001";

  const result = await listings.find(
    {
      tenantId: authorizedTenantId,
      status: "active"
    },
    {
      projection: {
        _id: 1,
        title: 1,
        city: 1,
        rentMillion: 1
      },
      limit: 20,
      maxTimeMS: 3000
    }
  ).toArray();

  console.log(result);
} finally {
  await client.close();
}
~~~

Đây là **script demo**, không phải kiến trúc runtime. Trong HTTP service production, MongoClient thường nên tồn tại lâu với connection pool, không tạo và đóng mỗi request.

### 17.1. Separate read và write identities

~~~text
Search API:
  MONGODB_SEARCH_READ_URI
  role = listingReader329

Mutation API:
  MONGODB_LISTING_EDIT_URI
  role = listingEditor329
~~~

Nếu hai URIs cùng nằm trong một process, compromise process có thể truy cập cả hai. Tách identities là bước tốt, nhưng cách ly thực sự mạnh hơn khi **tách workloads/processes/secrets delivery**.

### 17.2. Update theo tenant và trạng thái

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_LISTING_EDIT_URI
);

await client.connect();

try {
  const listings = client
    .db("mongo_security_lab_329")
    .collection("listings");

  const result = await listings.updateOne(
    {
      _id: "lab329-002",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: { status: "active" }
    }
  );

  console.log({
    matched: result.matchedCount,
    modified: result.modifiedCount
  });
} finally {
  await client.close();
}
~~~

Không cần action remove/createIndex để thực hiện update này. Tuy nhiên, nếu service cần các thao tác khác, hãy liệt kê đúng actions, không cấp root.

## 18. Change Streams, monitoring và backup cần scope riêng

### 18.1. CDC theo collection

Một CDC worker cần xem các thay đổi của listings. Nếu watch cả deployment, worker có thể cần quyền rộng hơn và nhận events từ nhiều namespaces. Hãy **watch collection hẹp nhất** đáp ứng nghiệp vụ.

### 18.2. Monitoring

Monitoring agent cần quan sát serverStatus/replication/performance. Không nên cấp readWrite để “thu thập số liệu” khi bản chất tác vụ là đọc metadata/metrics. Đối chiếu built-in **clusterMonitor** hoặc custom privileges với commands thực tế của monitoring tool.

### 18.3. Backup

Backup có thể yêu cầu privileges trên nhiều collections/metadata và phải tuân theo quy trình nhất quán của replica set hoặc sharded cluster. Backup identity nên tách application identity, bảo vệ credential và theo dõi quyền truy cập bản sao lưu.

### 18.4. Restore

Restore có rủi ro thay đổi/xóa dữ liệu trên phạm vi lớn. Người có thể restore không mặc nhiên cần chức năng đó trong công việc hằng ngày. Hãy dùng approval, runbook và identity riêng.

### 18.5. Sharded cluster

CRUD trong sharded cluster thường đi qua **mongos**, không nối trực tiếp từng shard mongod để tự định tuyến. Quyền của application không trở thành quyền quản trị config server/shard replication vì cluster có sharding.

## 19. Operational audit và chính sách rà soát quyền

### 19.1. Kiểm kê identity

Một buổi kiểm tra quyền cần biết:

- User nào thuộc service nào, môi trường nào.
- Ai là owner, còn được sử dụng không.
- Roles trực tiếp và roles được kế thừa.
- Collections/database nào thực sự được truy cập.
- Accounts có quyền root/userAdmin/dbOwner/restore.
- Quyền tạm thời nào quá hạn.
- Credentials nào bị dùng chung.
- Có tài khoản không được rotate đúng lịch.

### 19.2. Không tự xóa user ít dùng

Một account backup chạy mỗi tháng có thể không xuất hiện trong logs hằng ngày. Một account DR chỉ dùng khi khôi phục vẫn có mục đích. Phải xác minh owner và dependency trước khi xóa.

### 19.3. Audit trails

Các khả năng audit logging và phạm vi hoạt động phụ thuộc MongoDB edition/Atlas deployment. Với môi trường hỗ trợ, theo dõi các hoạt động nhạy cảm như tạo user, sửa role, thay authentication policy và truy cập dữ liệu nhạy cảm.

Không xem database audit log là nguồn duy nhất cho **actor nghiệp vụ** nếu ứng dụng dùng một service account chung cho nhiều end users. Cần thêm audit ở tầng API với userId/requestId và chính sách dữ liệu phù hợp.

### 19.4. Khi credential bị lộ

Quy trình phản ứng:

1. Xác định user bị lộ và privileges hiệu dụng.
2. Khoanh phạm vi dữ liệu có thể bị đọc/sửa.
3. Thu hồi/rotate theo mức độ khẩn cấp.
4. Theo dõi những connections/sessions liên quan.
5. Xem audit/operation logs theo quyền và retention.
6. Kiểm tra những role grants hoặc metadata changes bất thường.
7. Khôi phục cấu hình least privilege, cập nhật kiểm thử.

Nếu credential chỉ có **find trên listings**, blast radius nhỏ hơn account root — nhưng dữ liệu listings vẫn có thể bị đọc trái phép. Least privilege giảm hậu quả chứ không loại bỏ nhu cầu incident response.

## 20. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Dùng root cho mọi service | Một lỗi có thể gây tác động toàn cluster | Identity scoped từng workload |
| Dùng readWrite cho Search API | Cho phép ghi dù chỉ cần đọc | find trên collection |
| Dùng read trên cả database để đọc listings | Có thể đọc payments/users | Custom role resource listings |
| Gán role hẹp nhưng vẫn giữ role rộng | Quyền hiệu dụng là phép hợp | Bỏ role rộng |
| Tin tên role “readonly” | Role có thể kế thừa quyền ghi | Xem inheritedPrivileges |
| Nghĩ authenticated đồng nghĩa authorized | Đăng nhập thành công nhưng vẫn thiếu action | Kiểm tra hai bước riêng |
| authSource sai | AuthenticationFailed dù password đúng | Dùng database chứa user |
| Gặp Unauthorized thì cấp root | Tăng blast radius | Xác định action/resource |
| Role chỉ có find nhưng worker mở Change Stream | Có thể thiếu changeStream | Cấp scope đúng |
| Framework tự createIndex bằng app user | Runtime đòi quyền schema | Tách migration job |
| Dùng userAdmin trong API | Có nguy cơ leo thang đặc quyền | Tách IAM account |
| Nghĩ RBAC tự lọc tenantId | Có thể đọc chéo tenant trong cùng collection | Application authorization |
| Dùng client filter ghi đè tenantId | Người dùng có thể chọn tenant khác | Server enforce tenant filter |
| Ghi URI/password vào logs | Lộ secret | Secret manager, redact |
| Tắt TLS verify để kết nối nhanh | MITM/giả mạo endpoint | Sửa CA/hostname |
| Dùng credential dev trên prod | Lộ dev ảnh hưởng prod | Tách identities/môi trường |
| Nhầm Atlas project role với DB user | Cấp sai lớp quyền | Phân biệt project vs database |
| Shared human account | Khó truy vết | Danh tính cá nhân, audit |
| Grant thêm role không review inheritance | Vô tình mở quyền | Xem effective privileges |
| Xóa credential cũ trước rollout xong | Service outage | Rotation từng bước |
| Test deny bằng deleteMany({}) | Nếu quyền rộng, mất dữ liệu | Test non-existing ID có guard |

## 21. Checklist triển khai least privilege

### 21.1. Trước khi cấp user

1. Xác định service/job/human owner.
2. Liệt kê collections cần truy cập.
3. Liệt kê commands và MongoDB actions cần thiết.
4. Chọn built-in hay custom role có phạm vi nhỏ nhất.
5. Đọc các inherited privileges.
6. Chọn authentication mechanism, authSource và secret lifecycle.
7. Ghi lại lý do, môi trường và ngày review tiếp theo.

### 21.2. Trước khi deploy

1. Kiểm tra authentication và TLS.
2. Kiểm tra URI không bị ghi log.
3. Test thao tác **được phép**.
4. Test thao tác **phải bị từ chối** bằng test an toàn.
5. Kiểm tra app cưỡng chế tenantId trên read/write.
6. Kiểm tra schema/index migration được chạy qua identity khác.
7. Thiết lập alerts cho Unauthorized bất thường và authentication failures.
8. Đảm bảo có playbook rotation/revocation.

### 21.3. Khi review định kỳ

1. Lấy danh sách users/roles có thẩm quyền xem.
2. So với ma trận quyền dự kiến.
3. Phát hiện accounts không có owner/đã nghỉ dùng.
4. Tìm roles quản trị ngoài phạm vi.
5. Kiểm tra secrets và rotation history.
6. Kiểm tra application authorization đa tenant.
7. Ghi kết quả và phê duyệt quyền còn cần thiết.

## 22. Bài tập thực hành

### Bài 1 — Phân biệt authn/authz

User đăng nhập thành công nhưng insertOne trả Unauthorized. Hãy giải thích bước nào thành công, bước nào thất bại và vì sao đổi password không giải quyết lỗi quyền.

### Bài 2 — Resource/action

Viết privilege chỉ có **find** trên mongo_security_lab_329.listings. Vì sao privilege đó không cho phép find trên payments?

### Bài 3 — Read vs readWrite

Một service chỉ cần find. So sánh built-in read, readWrite và custom role find trên một collection. Chọn phương án ít quyền nhất.

### Bài 4 — Role inheritance

Một user có listingReader329 và readWrite trên database lab. User đó có thể update payments không? Vì sao custom role hẹp không phủ định role rộng?

### Bài 5 — Tạo dữ liệu mẫu

Chạy seed lab mục 8. Kiểm tra ba IDs, tenantId, trạng thái và database đang dùng. Vì sao phải dùng tài khoản quản trị để tạo collection và seed trước?

### Bài 6 — Tạo custom roles

Tạo listingReader329 và listingEditor329. Liệt kê action khác nhau, đặc biệt remove có xuất hiện trong Editor không?

### Bài 7 — Tạo database users

Tạo hai users tương ứng bằng passwordPrompt. Chúng nằm trong authentication database nào?

### Bài 8 — authSource

Một user tạo ở lab database nhưng URI dùng authSource=admin. Dự đoán lỗi. Nếu user tạo ở admin và role nằm trên lab, authSource nên là gì?

### Bài 9 — ConnectionStatus

Đăng nhập reader và in authenticatedUsers, authenticatedUserRoles. Vì sao phải kiểm tra danh tính trước khi thử một lệnh bị cấm?

### Bài 10 — Positive/negative tests

Chạy find thành công và updateOne trên ID không tồn tại để nhận Unauthorized. Giải thích vì sao không dùng deleteMany({}) làm negative test.

### Bài 11 — Show collections

Reader có thể find listings nhưng show collections không hoạt động. Vì sao? Nên cấp listCollections hay thay đổi ứng dụng để không cần introspection?

### Bài 12 — Aggregation

Một pipeline chỉ có $match/$group trên listings, pipeline khác có $merge sang reports. Phân biệt privileges cần thiết.

### Bài 13 — $lookup

Pipeline truy vấn listings rồi $lookup owners. Nêu resource phụ cần xem xét và tại sao không nên cấp read trên mọi collections cho một API công khai.

### Bài 14 — Change Streams

Một worker chỉ theo dõi listings. Hãy mô tả role cần có và vì sao watch cả deployment không phải scope tối thiểu.

### Bài 15 — Audit insert-only

Thiết kế role chỉ có insert trên auditLogs, không có update/remove. Vì sao role này không bảo đảm log bất biến trước root admin?

### Bài 16 — Migration

Framework tự createIndex khi startup, nhưng app user chỉ có find. Hãy đề xuất CI/CD migration identity thay vì mở quyền app.

### Bài 17 — UserAdmin

Vì sao userAdmin là role nhạy cảm và có thể tạo đường leo thang quyền? Ứng dụng xử lý listing có cần role này không?

### Bài 18 — Atlas

Phân biệt Atlas Project Owner với MongoDB database user có quyền readWrite. Vì sao không đưa account quản trị Project vào runtime API?

### Bài 19 — Multi-tenant

Một collection chứa dữ liệu t001/t002; DB role có find trên collection. Tại sao MongoDB không tự loại t002 khỏi find({}) của user t001? Đề xuất app-level authorization.

### Bài 20 — Update theo tenant

Viết updateOne với filter _id + tenantId từ security context + status. Nếu chỉ có _id, nguy cơ gì xảy ra?

### Bài 21 — Object spread

Client gửi filter có tenantId khác. Hãy chỉ ra lỗi trong **{tenantId:authenticatedTenantId, ...clientFilter}**, rồi viết phiên bản không cho ghi đè.

### Bài 22 — Secret hygiene

Phân tích rủi ro khi lưu mongodb://user:password@host trong source code hoặc debug log. Đề xuất secret manager và redact.

### Bài 23 — TLS

Một developer muốn tắt certificate validation ở production vì lỗi kết nối. Bạn sẽ kiểm tra những gì và vì sao không nên tắt xác thực server?

### Bài 24 — Rotation

Năm API replicas dùng chung credential. Lập trình tự đưa credential mới, xác minh, chuyển dần và thu hồi cũ mà không gây outage.

### Bài 25 — Quyền tạm

Một job tạo index chỉ chạy trong một đêm. Hãy chọn danh tính/quyền, quy trình phê duyệt và bước thu hồi sau khi xong.

### Bài 26 — Audit role graph

Role có tên readonly nhưng inheritedPrivileges chứa update. Tại sao tên role không đủ chứng minh? Bạn sẽ dùng những command nào để kiểm tra?

### Bài 27 — Monitoring

Monitoring agent cần xem trạng thái replica set nhưng không đọc payments. Nêu vai trò clusterMonitor/custom scope cần cân nhắc.

### Bài 28 — Backup/restore

Vì sao backup/restore cần account riêng? Một credential có restore bị lộ có tác động khác account reader như thế nào?

### Bài 29 — Incident

Credential của Search API bị lộ. So sánh hậu quả nếu nó chỉ có find trên listings với trường hợp nó là root. Đưa ra các bước revoke/rotate/audit.

### Bài 30 — Deploy checklist

Soạn checklist trước production: accounts tách theo môi trường, TLS, authSource, roles, permission tests, tenant authorization, secret rotation và incident response.

### Bài 31 — Transaction

Transaction cập nhật listings rồi insert auditLogs. Nếu user chỉ có update trên listings, transaction có tự được phép insert vào auditLogs không?

### Bài 32 — Thiết kế hoàn chỉnh

Cho bốn workloads: Search API, Listing Editor, Audit Writer, Index Migration. Hãy lập ma trận resources/actions, tạo các custom roles phù hợp và chỉ rõ quyền nào phải **không cấp**.

## 23. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Authorization](https://www.mongodb.com/docs/manual/core/authorization/).
- MongoDB Manual — [Users](https://www.mongodb.com/docs/manual/core/security-users/).
- MongoDB Manual — [Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/).
- MongoDB Manual — [User-Defined Roles](https://www.mongodb.com/docs/manual/core/security-user-defined-roles/).
- MongoDB Manual — [Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/).
- MongoDB Manual — [db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/).
- MongoDB Manual — [db.createRole()](https://www.mongodb.com/docs/manual/reference/method/db.createRole/).
- MongoDB Manual — [rolesInfo](https://www.mongodb.com/docs/manual/reference/command/rolesInfo/).
- MongoDB Manual — [connectionStatus](https://www.mongodb.com/docs/manual/reference/command/connectionStatus/).
- MongoDB Manual — [grantRolesToUser](https://www.mongodb.com/docs/manual/reference/method/db.grantRolesToUser/).
- MongoDB Manual — [revokeRolesFromUser](https://www.mongodb.com/docs/manual/reference/method/db.revokeRolesFromUser/).
- MongoDB Manual — [Authentication](https://www.mongodb.com/docs/manual/core/authentication/).
- MongoDB Manual — [Transport Encryption/TLS](https://www.mongodb.com/docs/manual/core/security-transport-encryption/).
- MongoDB Atlas — [Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/).

**Kết luận:** Trong MongoDB, **authentication** xác định danh tính, **authorization** quyết định được làm gì. User được cấp một hoặc nhiều roles; mỗi role chứa privileges dưới dạng **resource + actions**, và quyền hiệu dụng bao gồm cả quyền kế thừa. **Least privilege** nghĩa là mỗi API/worker/job chỉ có đúng quyền cần thiết, không phải tự cấp readWrite hoặc root để hết lỗi. Hãy tạo **custom roles theo collection**, tách danh tính ứng dụng với migration/monitoring/backup, dùng **authSource và TLS đúng**, bảo vệ credentials, kiểm tra positive/negative permissions và review quyền định kỳ. Đặc biệt, **RBAC không tự lọc document theo tenantId trong shared collection**: ứng dụng vẫn phải cưỡng chế tenant authorization trong mọi read/write. Khi một service bị lỗi hoặc credential bị lộ, thiết kế quyền tốt sẽ **giới hạn phạm vi thiệt hại xuống những tài nguyên và hành động tối thiểu đã được chủ động cho phép**.
