# Kiểm thử quyền truy cập, xác thực và bảo vệ dữ liệu nhạy cảm trong MongoDB

Một hệ thống sử dụng MongoDB có thể vượt qua toàn bộ bài kiểm thử CRUD mà vẫn gặp lỗi bảo mật nghiêm trọng. Ví dụ, một API trả đúng đơn hàng khi người dùng đăng nhập nhưng cũng trả đơn hàng của **tenant khác** khi thay ID; một database user chỉ đáng lẽ được đọc lại có thể xóa collection; hoặc thông tin thẻ/tài khoản và connection string chứa mật khẩu vô tình xuất hiện trong log khi integration test thất bại.

Bài **“Kiểm thử quyền truy cập, xác thực và bảo vệ dữ liệu nhạy cảm”** thuộc chương **Kiểm thử** của module **Database Engine Document MongoDB**. Mục tiêu là xây dựng một hệ thống kiểm thử bảo mật có thể lặp lại, từ các tầng **network → TLS → authentication → MongoDB RBAC → application authorization → data minimization → audit/retention**, thay vì chỉ kiểm tra “có kết nối được database không”.

Sau bài này, bạn có thể:

1. Phân biệt kiểm thử xác thực (**authentication / AuthN**) và phân quyền (**authorization / AuthZ**).
2. Thiết kế **ma trận quyền** cho các database users, collection actions và người dùng ứng dụng.
3. Kiểm tra các trường hợp **đúng credentials, sai credentials, sai authSource, user thiếu role, thiếu tenant scope**.
4. Viết integration tests với MongoDB Java Sync Driver và Spring Data MongoDB bằng **identities thật có quyền khác nhau**.
5. Kiểm chứng TLS/network policy, IP Access List hoặc private connectivity mà không mở database cho Internet.
6. Phát hiện rò rỉ PII/secrets qua API response, projections, logs, errors, backups và test artifacts.
7. Xác định ranh giới của encryption in transit, encryption at rest và client-side field-level encryption.
8. Đưa các kiểm thử quan trọng vào CI/CD, có cleanup, evidence, negative assertions và tiêu chí release gate.

> **Ranh giới an toàn:** toàn bộ địa chỉ, users, databases và dữ liệu trong ví dụ là giả định cho lab. Chỉ chạy kiểm thử trên hệ thống được giao quyền quản trị, sử dụng database thử nghiệm cô lập và credentials riêng. Không dùng thử nghiệm đăng nhập sai hàng loạt, không scan Internet, không chạy `dropDatabase()` trên dữ liệu thật và không đưa PII production vào tài liệu/CI.

## 1. Bản đồ các lớp bảo vệ

Một request đọc đơn hàng có thể đi qua nhiều cổng:

```text
Người dùng / client
       |
       v
HTTPS API + user session/token
       |
       v
Application authorization
  - roles
  - tenantId/ownerId
  - business state
       |
       v
Backend service identity
       |
       v
DNS + network route + firewall / Atlas IP Access List
       |
       v
TLS handshake + server certificate validation
       |
       v
MongoDB authentication (SCRAM/x.509/... nếu hỗ trợ)
       |
       v
MongoDB roles / privileges (RBAC)
       |
       v
MongoDB collection / document
       |
       v
Output projection + masking + logging/retention
```

Không có một bài test duy nhất chứng minh mọi lớp an toàn:

- `ping` thành công **không chứng minh** database user có role chỉ đọc.
- DB user có `readWrite` trên `ordersdb` **không chứng minh** người dùng HTTP A chỉ được xem đơn hàng của A.
- TLS được bật **không chứng minh** password không xuất hiện trong logs.
- API chỉ trả đúng fields **không chứng minh** backup/snapshot được mã hóa, phân quyền đúng và có retention.
- Atlas IP Access List hẹp **không thay thế** database authentication hoặc application authorization.

### Bốn câu hỏi độc lập

| Lớp | Câu hỏi kiểm thử | Ví dụ |
| --- | --- | --- |
| Network | Nguồn nào có thể tới database port? | App subnet được phép, Internet lạ bị chặn |
| AuthN | Client có đúng danh tính không? | SCRAM user/password hợp lệ |
| Database AuthZ | Database identity được phép làm gì? | `read` nhưng không `insert`/`drop` |
| Application AuthZ | Người dùng được xem/sửa dữ liệu nghiệp vụ nào? | User tenant A không đọc đơn tenant B |

Các tầng khác nhau cần **test cases và bằng chứng khác nhau**. Không gộp chúng thành kết luận “login pass”.

## 2. Xác định security requirements trước khi viết test

Kiểm thử cần dựa trên **chính sách mong muốn**, không chỉ chụp lại hành vi hiện tại.

Ví dụ yêu cầu:

```text
REQ-AUTH-01  Client sai password không truy cập dữ liệu
REQ-AUTH-02  Service chỉ đọc không thể insert/update/delete
REQ-AUTH-03  Service orders không có quyền đọc payroll database
REQ-TENANT-01 Tenant A không thể xem order của Tenant B
REQ-TENANT-02 Tenant A không thể sửa order của Tenant B
REQ-DATA-01  API customer response không chứa internalNotes
REQ-DATA-02  Secret/token không xuất hiện trong error logs
REQ-TLS-01   Kết nối production chỉ dùng TLS hợp lệ
REQ-BACKUP-01 Backup có giới hạn quyền và kiểm soát retention
REQ-AUDIT-01 Sensitive operations có audit correlation
```

Mỗi requirement nên có:

1. **Đối tượng cần bảo vệ**: database, collection, document, field, secret.
2. **Actor/identity**: anonymous, người dùng HTTP, MongoDB service user, operator.
3. **Hành động**: connect, find, insert, update, delete, createIndex, export.
4. **Kết quả mong muốn**: allow/deny/masked/audited.
5. **Điểm kiểm tra**: network, API, DB command, log, backup platform.
6. **Evidence**: result/exception/error code/sanitized event, không chứa dữ liệu nhạy cảm.

### Security test khác functional test thế nào?

Functional test thường hỏi “người được phép làm được việc hay không?”. Security test còn phải hỏi “**người không được phép** có bị chặn đúng không?”.

Ví dụ:

```text
Functional:
  reader đọc được order -> PASS

Security:
  reader đọc được order -> PASS
  reader insert order -> DENIED -> PASS
  reader drop collection -> DENIED -> PASS
  reader đọc payroll -> DENIED -> PASS
```

Một test suite chỉ có positive cases không đủ chứng minh least privilege.

## 3. Threat model cho dữ liệu nhạy cảm

Trong ứng dụng thuê nhà/đặt hàng, các loại dữ liệu có thể gồm:

| Loại dữ liệu | Ví dụ giả định | Tác động khi lộ |
| --- | --- | --- |
| PII | Họ tên, email, số điện thoại, địa chỉ | Vi phạm quyền riêng tư |
| Dữ liệu tài chính | Tài khoản thanh toán, giao dịch | Gian lận, thất thoát |
| Dữ liệu xác thực | Access token, reset token, session secret | Chiếm tài khoản |
| Dữ liệu vị trí | Địa chỉ, lịch sử lưu trú | Rủi ro an toàn cá nhân |
| Dữ liệu nội bộ | Giá thương lượng, internal notes | Lộ bí mật thương mại |
| Operational secrets | MongoDB URI/password, TLS key | Chiếm quyền database |
| Audit metadata | User ID, IP, hành động | Có thể là PII hoặc dữ liệu điều tra |

Threat model nên xét các tác nhân:

- Người dùng bình thường cố truy cập tài nguyên của người khác.
- Service bị lộ credential và có role quá rộng.
- Operator hoặc CI runner vô tình export dữ liệu thật.
- Một kết nối mạng bị nghe lén hoặc định tuyến sai.
- Log aggregator, backup store hoặc dashboard có người xem ngoài phạm vi.
- Background job dùng raw MongoDB driver và bỏ application-level tenant filtering.

**Không dùng dữ liệu PII thật để kiểm thử nếu dữ liệu giả đã đủ tái hiện lỗi.** Với dữ liệu production-like cần masking/tokenization và phê duyệt riêng.

## 4. Chuẩn bị môi trường kiểm thử cô lập

Một môi trường lab:

```text
Test runner (JUnit / CI)
      |
      v
MongoDB test deployment
  database: security_lab
  collections:
    orders
    customers
    audit_events
      |
      +--> User svc_orders_read
      +--> User svc_orders_write
      +--> User svc_customer_read
      +--> User admin_bootstrap  (chỉ setup fixture)
```

Yêu cầu:

1. Database/cluster **dành riêng** cho kiểm thử và có thể xóa khi kết thúc.
2. Credentials cho reader/writer/test admin **tách biệt**.
3. Seed data giả với business keys riêng của từng test.
4. Network access chỉ từ test runner/CI theo cơ chế được hỗ trợ.
5. TLS và auth **bật** ở những bài test muốn xác thực security properties.
6. Có cơ chế cleanup và giới hạn retention cho fixture, logs và artifact.
7. Không dùng tài khoản quản trị production để chạy negative tests.

### Vì sao embedded/in-memory MongoDB không đủ?

Mock repository hoặc fake in-memory database có thể tốt cho logic ứng dụng, nhưng **không thể chứng minh**:

- SCRAM handshake thực.
- AuthSource, users/roles thật của MongoDB.
- Quyền denied của MongoDB server.
- TLS certificate validation và network path.
- Index/validator thật.
- Audit/backup/access list thực.

Các security requirements liên quan **MongoDB server** cần integration test với MongoDB deployment thật, dù deployment đó chạy dưới container test. Còn authorization ở tầng controller/service có thể được kiểm thử thêm bằng unit tests để chạy nhanh.

## 5. Dữ liệu fixture an toàn

Ví dụ hai tenants và hai đơn hàng:

```javascript
use security_lab

db.orders.insertMany([
  {
    _id: "order-a-001",
    tenantId: "tenant-a",
    ownerId: "user-a",
    total: NumberDecimal("120000.00"),
    currency: "VND",
    status: "NEW",
    internalNotes: "fixture only",
    contactEmail: "fake-a@example.invalid"
  },
  {
    _id: "order-b-001",
    tenantId: "tenant-b",
    ownerId: "user-b",
    total: NumberDecimal("99000.00"),
    currency: "VND",
    status: "PAID",
    internalNotes: "fixture only",
    contactEmail: "fake-b@example.invalid"
  }
]);
```

`example.invalid` là domain dành cho ví dụ; các giá trị ở đây không trỏ đến người dùng thật.

Test data cần có **ít nhất một document mà actor có quyền** và **ít nhất một document actor không có quyền**. Nếu fixture chỉ có đơn hàng tenant A, một query bỏ điều kiện tenantId vẫn trả đúng kết quả và test dễ **pass giả**.

### Đặt mã test dễ tìm và cleanup

Ví dụ:

```text
testRunId: "security-it-20261114-001"
```

Một test runner có thể bổ sung `testRunId` vào documents để xóa đúng dữ liệu của lượt kiểm thử. Tuy nhiên, với kiểm thử quyền đọc/ghi, cleanup nên do **fixture admin identity** thực hiện sau test, không yêu cầu user chỉ đọc có quyền xóa collection.

## 6. Ma trận quyền MongoDB cần kiểm thử

Một policy mẫu:

| Database identity | `find` orders | `insert/update` orders | `find` customers | `drop` collection | Quản lý users |
| --- | --- | --- | --- | --- | --- |
| `svc_orders_read` | Allow | Deny | Deny | Deny | Deny |
| `svc_orders_write` | Allow | Allow | Deny | Deny | Deny |
| `svc_customer_read` | Deny | Deny | Allow | Deny | Deny |
| `fixture_admin` | Theo quyền fixture | Theo quyền fixture | Theo quyền fixture | Có thể có | Chỉ lúc bootstrap |

Bảng này giả định **custom roles giới hạn theo collection**. Nếu cấp built-in role `readWrite` trên database `security_lab`, user thường có quyền rộng trên nhiều collections trong database, **không khớp ma trận “orders-only”**. Vì vậy khi cần collection-scoped privilege, phải cấu hình custom role hoặc tách database theo mô hình phù hợp.

### Least privilege là yêu cầu có thể kiểm chứng

Kiểm thử nên khẳng định cả:

- **Quyền phải có**: không chặn chức năng hợp lệ.
- **Quyền không được có**: không cho phép thao tác ngoài phạm vi.

Nếu một bài test thất bại vì service được cấp quyền quá rộng, không nên sửa test bằng cách đổi expectation sang Allow. Cần đối chiếu với security requirement và điều chỉnh role.

## 7. Built-in roles và custom roles

MongoDB cung cấp built-in roles như `read`, `readWrite` và những roles quản trị, với phạm vi theo database/cluster phù hợp.

Ví dụ trong lab:

```javascript
use security_lab

// Chỉ minh họa role built-in trên database thử nghiệm.
db.createUser({
  user: "svc_read_db",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "security_lab" }
  ]
});
```

User này là database reader theo phạm vi role; **không phải** user chỉ đọc riêng `orders` nếu trong database còn collections khác.

### Tạo custom role theo collection

Một ví dụ role **chỉ tìm kiếm documents của orders**:

```javascript
use security_lab

db.createRole({
  role: "ordersReader",
  privileges: [
    {
      resource: {
        db: "security_lab",
        collection: "orders"
      },
      actions: ["find"]
    }
  ],
  roles: []
});
```

Gán role cho user lab:

```javascript
db.createUser({
  user: "svc_orders_read",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersReader", db: "security_lab" }
  ]
});
```

Các lệnh quản trị trên cần chạy bằng **bootstrap/admin identity đủ quyền**, chỉ trong môi trường kiểm thử được phép. `passwordPrompt()` trong `mongosh` giúp nhập password thay vì hard-code plaintext trong script.

Một user có role find-only có thể bị từ chối khi gọi các lệnh khác như list collection metadata nếu role không bao gồm các actions cần thiết. Điều đó không tự chứng minh role bị lỗi; cần lựa chọn những API test phù hợp với quyền đang định nghĩa.

## 8. Tạo custom role writer với quyền tối thiểu

Ví dụ muốn service được đọc/insert/update/remove **chỉ collection orders**:

```javascript
use security_lab

db.createRole({
  role: "ordersDataWriter",
  privileges: [
    {
      resource: {
        db: "security_lab",
        collection: "orders"
      },
      actions: ["find", "insert", "update", "remove"]
    }
  ],
  roles: []
});

db.createUser({
  user: "svc_orders_write",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersDataWriter", db: "security_lab" }
  ]
});
```

Role này cố tình **không** chứa `dropCollection`, `createIndex`, `collMod` hoặc `createUser`. Một service writer không nên có quyền quản trị chỉ vì ứng dụng cần sửa dữ liệu.

### Quyền thực cần nhiều hơn những action trong ví dụ?

Một số operations có thể yêu cầu privileges khác tùy MongoDB version và command (ví dụ metadata/index handling). Đừng mở toàn quyền ngay khi một operation lỗi; hãy:

1. Ghi lại command thực sự cần chạy.
2. Xem MongoDB privilege action tương ứng.
3. Thêm đúng action/resource ở đúng phạm vi.
4. Viết lại positive và negative tests.
5. Review tác động của quyền mới.

Đây là cách biến ma trận quyền thành **hợp đồng có thể kiểm tra**, không phải bảng tham khảo trang trí.

## 9. Authentication với SCRAM và authSource

MongoDB hỗ trợ cơ chế username/password như SCRAM. Với một user được tạo trong `security_lab`, application cần xác thực với **authentication database** tương ứng.

Ví dụ URI sử dụng placeholder:

```text
mongodb://svc_orders_read:<password>@db.internal.example:27017/security_lab?authSource=security_lab&tls=true
```

Đây là minh họa cú pháp, **không phải URI có thể kết nối**. Khi triển khai, password phải được lấy từ secret manager/env injection phù hợp, và characters đặc biệt trong URI credentials cần được encoding đúng.

### Authentication database khác target database

`authSource` xác định database nơi MongoDB tìm **user identity để xác thực**; path `/security_lab` trong URI còn liên quan default database của connection.

Ví dụ user được tạo trong `admin` nhưng làm việc trên `ordersdb` có thể cần:

```text
mongodb://<user>:<password>@host:27017/ordersdb?authSource=admin
```

Sai `authSource` có thể dẫn tới lỗi authentication mặc dù username/password nhìn có vẻ đúng.

### Positive/negative test

| Case | Credentials/source | Kỳ vọng |
| --- | --- | --- |
| AUTH-01 | Đúng user/password/authSource | Authenticated command phù hợp thành công |
| AUTH-02 | Sai password | Không truy cập dữ liệu |
| AUTH-03 | User không tồn tại | Không xác thực |
| AUTH-04 | Đúng password nhưng authSource sai | Không xác thực nếu user không tồn tại ở source đó |
| AUTH-05 | Credential đã rotation | Credential cũ không dùng được, mới hoạt động |
| AUTH-06 | Bỏ credentials khi server require auth | Không truy cập protected data |

Không thiết kế test chỉ kiểm tra constructor `MongoClients.create()` không ném lỗi: Java driver có thể **kết nối/làm authentication khi thực thi command đầu tiên**, không phải ngay khi tạo client object.

## 10. Tránh kiểm thử password bằng brute-force

Negative test xác thực chỉ cần một vài **fixture credentials cố tình sai** trên deployment được phép, không cần đoán hàng nghìn mật khẩu.

Hướng dẫn:

- Không chạy credential stuffing vào Atlas hoặc tài khoản thật.
- Không ghi sai password vào logs/test reports.
- Chạy test trên identity dành riêng, có thể reset ngay.
- Đặt timeout và retry bounded để không tạo bão kết nối.
- Theo dõi authentication-failure metrics nếu hệ thống hỗ trợ.
- Tách test security khỏi load test; không vô tình kích hoạt alert hoặc làm mất khả năng truy cập hợp lệ.

**Kết quả đúng của một negative test là request bị chặn**, không phải bản thân tool chạy không lỗi. Nếu exception là điều mong đợi, test cần assert đúng loại/kết quả thay vì xem stack trace là thất bại.

## 11. Kiểm thử authorization độc lập với authentication

Giả sử `svc_orders_read` đăng nhập thành công. Nó không được phép ghi.

```text
Authentication:
  svc_orders_read -> OK

Authorization:
  find security_lab.orders  -> ALLOW
  insert security_lab.orders -> DENY
  drop security_lab.orders   -> DENY
```

Nếu test chỉ xác nhận `ping` hoặc `find` thành công, nó không phát hiện user bị cấp nhầm `readWrite`/quyền quản trị.

### Dấu hiệu server deny quyền

MongoDB có lỗi kiểu `Unauthorized` khi command/action không được phép theo role. Trong Java Sync Driver, các command exceptions có thể thuộc `MongoCommandException`, nhưng loại exception cụ thể có thể khác theo operation, server và driver version.

Một negative test nên:

1. Dùng database user xác định rõ.
2. Gọi **command thật** muốn cấm.
3. Assert operation **không thành công vì authorization** (không chỉ vì network timeout).
4. Assert dữ liệu **không thay đổi**.
5. Cleanup bằng identity đủ quyền khi cần.

Một `TimeoutException` không được xem là bằng chứng database role đúng.

## 12. Test matrix theo thao tác và phạm vi

Các test cases mẫu:

| Test ID | Identity | Operation | Resource | Kỳ vọng |
| --- | --- | --- | --- | --- |
| RBAC-01 | `svc_orders_read` | `find` | `security_lab.orders` | Allow |
| RBAC-02 | `svc_orders_read` | `insert` | `security_lab.orders` | Deny |
| RBAC-03 | `svc_orders_read` | `update` | `security_lab.orders` | Deny |
| RBAC-04 | `svc_orders_read` | `delete` | `security_lab.orders` | Deny |
| RBAC-05 | `svc_orders_read` | `find` | `security_lab.customers` | Deny |
| RBAC-06 | `svc_orders_write` | `insert` | `security_lab.orders` | Allow |
| RBAC-07 | `svc_orders_write` | `drop` | `security_lab.orders` | Deny |
| RBAC-08 | `svc_orders_write` | `find` | `payroll.salaries` | Deny |
| RBAC-09 | `svc_customer_read` | `find` | `security_lab.customers` | Allow |
| RBAC-10 | `svc_customer_read` | `find` | `security_lab.orders` | Deny |

Để test quyền theo collection như trong bảng, phải provision **custom roles** tương ứng; built-in `read` trên cả database có thể cho phép đọc `customers`, khiến expectation khác.

### Test quyền nguy hiểm mà không làm hỏng data

Một test cố chạy `drop()` với user bị cấm có thể an toàn **nếu role chắc chắn bị từ chối**; nhưng nếu hệ thống cấu hình sai, nó có thể xóa fixture collection. Vì vậy chỉ dùng database disposable, có setup/cleanup và identity admin phục hồi fixtures. Không chạy negative test destructive trên production.

## 13. Java Sync Driver: harness cho integration tests

Ví dụ đơn giản:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class MongoTestConnection {

    public static MongoClient connectFromEnv(String envName) {
        String uri = System.getenv(envName);
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "Thiếu biến môi trường cho test: " + envName);
        }
        return MongoClients.create(uri);
    }

    public static MongoCollection<Document> orders(
            MongoClient client) {
        return client.getDatabase("security_lab")
            .getCollection("orders");
    }
}
```

Test runner dùng các biến môi trường do CI secret manager cấp:

```text
MONGO_TEST_READER_URI
MONGO_TEST_WRITER_URI
MONGO_TEST_WRONG_AUTH_URI
MONGO_TEST_FIXTURE_ADMIN_URI
```

Trong đó:

- Reader/writer users có roles như policy.
- URI dùng hostname/TLS theo môi trường thật.
- Wrong-auth URI sử dụng **dummy credential** dành cho test.
- Fixture admin URI không được in ra console hoặc attach vào test artifacts.

Không sử dụng **một URI admin duy nhất** cho mọi test rồi kiểm tra quyền bằng một cờ giả trong Java. Khi ấy test không kiểm chứng MongoDB RBAC.

## 14. Java/JUnit: test đọc được và ghi bị từ chối

Ví dụ JUnit 5:

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MongoRbacIntegrationTest {

    @Test
    void readerCanFindButCannotInsert() {
        try (MongoClient client =
                MongoTestConnection.connectFromEnv(
                    "MONGO_TEST_READER_URI")) {

            MongoCollection<Document> orders =
                MongoTestConnection.orders(client);

            // Positive: role có action find.
            Document sample = orders.find(
                new Document("_id", "order-a-001"))
                .first();
            assertNotNull(sample);

            // Negative: user read-only không được insert.
            MongoException ex = assertThrows(
                MongoException.class,
                () -> orders.insertOne(
                    new Document("_id", "negative-insert")
                        .append("tenantId", "tenant-a")
                )
            );

            assertNotNull(ex);
        }
    }
}
```

Test trên chứng minh hai điều ở mức cơ bản. Để mạnh hơn, nên:

1. Xác nhận exception thật sự có **authorization failure** chứ không phải lỗi kết nối.
2. Query bằng fixture admin sau test để chắc document `negative-insert` **không xuất hiện**.
3. Bảo đảm fixture precondition tồn tại; nếu positive find trả null vì fixture thiếu, test fail rõ.
4. Gắn unique test run IDs để nhiều CI jobs không đụng nhau.

**Không dùng cùng một collection đang phục vụ người dùng thật** cho test cố insert/deny, vì một role cấu hình sai có thể khiến write thành công.

## 15. Xác nhận negative result đúng nguyên nhân

Một test như:

```java
assertThrows(
    MongoException.class,
    () -> readerOrders.insertOne(forbiddenDocument)
);
```

có thể **pass giả** khi MongoDB không reachable, TLS lỗi hoặc URI sai. Test bảo mật nên assert thêm **error category/cause**.

Ví dụ với `MongoCommandException`:

```java
import com.mongodb.MongoCommandException;
import static org.junit.jupiter.api.Assertions.*;

MongoCommandException error = assertThrows(
    MongoCommandException.class,
    () -> readerOrders.insertOne(
        new Document("_id", "forbidden-test")
    )
);

assertEquals(13, error.getErrorCode());
```

Trong MongoDB, error code **13** thường ứng với `Unauthorized`. Một số driver/server operations có thể surface lỗi khác hoặc wrap exception; cần tùy chỉnh assertion theo phiên bản/tool và **không nhầm với authentication failure**.

Nếu user không thể authenticate, command có thể không đến được giai đoạn authorization. Bài test “reader không được insert” phải dùng **reader đã authenticate thành công**.

### Xác nhận dữ liệu không bị thay đổi

Sau test negative, dùng fixture admin để đọc:

```javascript
db.getSiblingDB("security_lab").orders.findOne({
  _id: "forbidden-test"
});
```

Kỳ vọng không có document mới. Chỉ đọc kết quả này trong test setup cô lập; việc đưa tác vụ kiểm chứng vào cùng test transaction hoặc cleanup cần thiết kế theo môi trường.

## 16. Java/JUnit: xác thực sai phải không truy cập được

Một test dùng credential sai:

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoClient;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MongoAuthIntegrationTest {

    @Test
    void wrongPasswordCannotRead() {
        try (MongoClient client =
                MongoTestConnection.connectFromEnv(
                    "MONGO_TEST_WRONG_AUTH_URI")) {

            MongoException error = assertThrows(
                MongoException.class,
                () -> client
                    .getDatabase("security_lab")
                    .runCommand(new Document("ping", 1))
            );

            assertNotNull(error);
        }
    }
}
```

Lưu ý rằng nhiều driver có thể báo lỗi authentication theo exception type riêng (chẳng hạn `MongoSecurityException`), hoặc nested error sau khi server selection/connection handshake. Đừng chỉ assert một chuỗi error message vì wording có thể thay đổi giữa versions.

### Đừng nhầm network failure với auth failure

Trước test credential sai, nên có precondition:

```text
Correct credentials + same network path -> CONNECT PASS
Wrong credentials + same endpoint       -> AUTH DENY
```

Nếu cả correct và wrong credentials đều fail vì DNS/firewall, bài test chưa chứng minh auth policy.

## 17. Test xác thực ở Spring Data MongoDB

Spring Data repository thường dùng credentials được cấu hình trong `MongoClient`/Spring Boot datasource context, không có user MongoDB mới cho mỗi HTTP request.

Sơ đồ:

```text
HTTP user Alice/Bob
      |
      v
Spring Security + application authorization
      |
      v
Spring Data MongoRepository
      |
      v
MongoDB service user "svc_orders_api"
```

Điều này dẫn đến hai nhóm test:

**A. Database identity tests:** service account có đúng privileges không? Chạy qua MongoDB thật với identity đó.

**B. API/user authorization tests:** Alice không được xem Bob's data dù cả hai request dùng cùng MongoDB service account.

**Một DB account readWrite không thể tự thực thi mọi rule của HTTP users**. MongoDB nhìn thấy app service identity, không nhất thiết nhìn thấy principal end-user khi service dùng connection pool chung.

## 18. Multi-tenant authorization: lỗi IDOR/BOLA

Một rủi ro phổ biến là **Broken Object Level Authorization (BOLA)**, thường còn gọi là IDOR trong các tình huống truy cập theo ID.

Ví dụ endpoint:

```text
GET /api/orders/order-a-001
GET /api/orders/order-b-001
```

Khi người dùng tenant A thay ID từ `order-a-001` thành `order-b-001`, API **không được** trả dữ liệu tenant B chỉ vì document ID hợp lệ.

### Code dễ sai

```java
public OrderDto getOrder(String id) {
    Order order = repository.findById(id)
        .orElseThrow();
    return mapper.toDto(order);
}
```

Đoạn code chỉ kiểm tra document tồn tại, **không kiểm tra tenant/owner**. Cần đưa điều kiện scope từ **authenticated principal** vào truy vấn hoặc kiểm tra quyền rõ ràng.

### Chỉ tin tenantId lấy từ security context

```text
Principal đã xác thực:
  tenantId = tenant-a

Request query:
  orderId = order-b-001

Database filter:
  _id = order-b-001
  AND tenantId = tenant-a

Không match -> không trả order tenant-b
```

**Không lấy `tenantId` từ query param/body rồi tin nó là nguồn phân quyền.** Client có thể gửi `tenantId=tenant-b`. Chỉ dùng client-supplied tenantId nếu API có contract ủy quyền rõ ràng và kiểm tra principal được phép hành động thay tenant đó.

## 19. Spring Data: truy vấn có tenant scope

Ví dụ entity giản lược:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class OrderEntity {
    @Id
    private String id;
    private String tenantId;
    private String ownerId;
    private String status;

    public OrderEntity() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }
    public String getOwnerId() { return ownerId; }
    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }
    public String getStatus() { return status; }
    public void setStatus(String status) {
        this.status = status;
    }
}
```

Repository với query đã scope:

```java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderEntity, String> {

    Optional<OrderEntity> findByIdAndTenantId(
        String id,
        String tenantId
    );
}
```

Service:

```java
public OrderEntity findOrderForTenant(
        String orderId,
        String tenantIdFromAuthenticatedPrincipal) {

    return repository.findByIdAndTenantId(
        orderId,
        tenantIdFromAuthenticatedPrincipal
    ).orElseThrow(() ->
        new ResourceNotFoundException("Order not found"));
}
```

`ResourceNotFoundException` là exception ứng dụng cần định nghĩa; có thể chọn trả 404 để tránh tiết lộ sự tồn tại của tài nguyên ngoài tenant, theo API policy.

### Nâng yêu cầu đến owner-level

Nếu mọi user trong tenant không được xem toàn bộ orders, query còn phải có `ownerId` hoặc role scopes:

```text
_id == request.orderId
AND tenantId == principal.tenantId
AND (ownerId == principal.userId OR principal has authorized role)
```

Scope thực tế là một phần của **business authorization**, không chỉ là field name.

## 20. Tenant scoping phải áp dụng cho UPDATE và DELETE

Một ứng dụng có thể bảo vệ GET tốt nhưng quên kiểm tra PATCH hoặc DELETE:

```java
// Thiếu tenant scope:
template.updateFirst(
    Query.query(Criteria.where("_id").is(orderId)),
    new Update().set("status", "CANCELLED"),
    OrderEntity.class
);
```

Nếu API cho tenant A gửi order ID của B, câu lệnh trên có thể sửa document B.

### Conditional update có tenant scope

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query filter = Query.query(
    Criteria.where("_id").is(orderId)
        .and("tenantId").is(principalTenantId)
        .and("status").is("NEW")
);

Update change = new Update()
    .set("status", "CANCELLED");

UpdateResult result = template.updateFirst(
    filter, change, OrderEntity.class
);

if (result.getMatchedCount() == 0) {
    // Không có document được phép và đủ điều kiện để sửa.
}
```

**Kiểm tra scope và business state trong cùng MongoDB update predicate** giúp tránh race giữa bước “check access” và bước “write”.

Nếu dùng `@Version` optimistic locking, có thể cần thêm expectedVersion trong cùng filter theo version contract. AuthZ, optimistic locking và domain invariant là ba điều kiện có thể kết hợp.

## 21. Ma trận tenant-level positive và negative tests

| Case | Principal | Hành động | Target | Kỳ vọng |
| --- | --- | --- | --- | --- |
| TENANT-01 | user-a/tenant-a | GET | order-a-001 | Allow |
| TENANT-02 | user-a/tenant-a | GET | order-b-001 | Deny/404 |
| TENANT-03 | user-a/tenant-a | PATCH | order-a-001 | Allow nếu state hợp lệ |
| TENANT-04 | user-a/tenant-a | PATCH | order-b-001 | Deny, không thay đổi dữ liệu |
| TENANT-05 | user-a/tenant-a | DELETE | order-b-001 | Deny |
| TENANT-06 | user-b/tenant-b | GET | order-b-001 | Allow |
| TENANT-07 | Anonymous | GET | order-a-001 | Unauthorized |
| TENANT-08 | tenant-a admin | GET | order-b-001 | Deny nếu không có cross-tenant privilege |
| TENANT-09 | user-a/tenant-a | List orders | Tập A và B | Chỉ nhận orders A |
| TENANT-10 | user-a/tenant-a | Aggregation/report | Nhiều tenants | Chỉ dữ liệu được phép |

Test GET by ID **chưa đủ**. Các điểm thường quên:

- Pagination/list/search/filter.
- Export CSV/PDF.
- Aggregation `$lookup`.
- Bulk update/delete.
- Change streams/notifications/websocket.
- Batch jobs/reports.
- File attachments/GridFS.
- Admin “impersonation” hoặc support tools.

Tenant isolation phải được kiểm chứng trên **mọi đường đọc và ghi có thể truy cập dữ liệu**.

## 22. JUnit: test application authorization

Một service test đơn giản với fixture giả định:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderAccessIntegrationTest {

    private OrderService service;

    @Test
    void tenantCannotReadForeignOrder() {
        OrderEntity own = service.findOrderForTenant(
            "order-a-001", "tenant-a");
        assertEquals("tenant-a", own.getTenantId());

        assertThrows(
            ResourceNotFoundException.class,
            () -> service.findOrderForTenant(
                "order-b-001", "tenant-a")
        );
    }
}
```

Đây là **phần thân test**; để chạy thực cần cấu hình `OrderService`, repository, context và seed data. Trong HTTP integration test, tenant ID phải được suy ra từ authenticated principal thực hoặc mock security context được kiểm soát — **không chỉ gọi service với chuỗi tùy ý rồi kết luận endpoint an toàn**.

### Test ở tầng controller

Kết hợp các tools tương ứng với Spring Security:

- Request với principal tenant A và tài nguyên A.
- Request với principal tenant A và tài nguyên B.
- Request không có token.
- Request có token hết hạn/sai chữ ký.
- Request role không đủ.

Sau negative PATCH/DELETE, đọc lại bằng fixture admin để xác minh dữ liệu **không đổi**.

## 23. Test projection và response data minimization

Một database document có nhiều fields:

```javascript
{
  _id: "customer-a-001",
  tenantId: "tenant-a",
  displayName: "Khách thử nghiệm",
  contactEmail: "fixture@example.invalid",
  passwordHash: "fixture-not-a-real-hash",
  internalRiskScore: 7,
  paymentReference: "TEST-REF",
  internalNotes: "Chỉ hỗ trợ nội bộ"
}
```

Endpoint public chỉ cần:

```json
{
  "id": "customer-a-001",
  "displayName": "Khách thử nghiệm"
}
```

Nếu API serialize nguyên `Document` hoặc entity MongoDB, nó có thể làm lộ `passwordHash`, `internalRiskScore`, `internalNotes` hoặc fields mới được thêm sau này.

### Dùng allowlist DTO

```java
public record CustomerPublicDto(
    String id,
    String displayName
) {}
```

Mapper chỉ lấy fields được phép. Ưu điểm: thêm field nhạy cảm vào entity không tự xuất hiện trong API response.

### Dùng projection để giảm dữ liệu truy xuất

Ví dụ:

```java
Query query = Query.query(
    Criteria.where("_id").is(customerId)
        .and("tenantId").is(principalTenantId)
);

query.fields()
    .include("displayName")
    .exclude("_id");

CustomerPublicProjection projection =
    template.findOne(
        query, CustomerPublicProjection.class, "customers");
```

Đây là ví dụ hướng thiết kế; `CustomerPublicProjection` cần class/mapping tương ứng. **Projection không thay authorization**: nếu filter thiếu tenant, endpoint vẫn có thể trả displayName của người không được phép.

**Projection và DTO nên bổ sung cho nhau**, không chỉ dựa vào việc annotation ẩn JSON field, vì dữ liệu nhạy cảm có thể bị log/serialize ở code paths khác.

## 24. Negative tests cho dữ liệu nhạy cảm trong response

Một bài test API:

```text
GET /api/customers/customer-a-001
Principal tenant-a
Expected 200

Response MUST contain:
  id
  displayName

Response MUST NOT contain:
  passwordHash
  internalRiskScore
  paymentReference
  internalNotes
  mongoConnectionUri
```

Một response JSON có thể nested. Không chỉ tìm chuỗi `passwordHash` trong raw response; test nên parse JSON, kiểm tra JSON paths và **schema allowlist**. Nếu API dùng error envelope, pagination hoặc GraphQL, cũng phải kiểm tra payloads theo loại response.

### Bài test “không có dữ liệu” phải dùng fixture thực sự có field

Nếu fixture **không chứa** `internalNotes`, test “response không chứa internalNotes” có thể pass dù mapper vẫn serialize field này khi nó có mặt.

Để kiểm tra redaction/projection hiệu quả, fixture phải có giá trị giả **ở field nhạy cảm**, rồi xác nhận giá trị đó không lọt qua response.

## 25. Tránh NoSQL query injection

Một số lỗi phát sinh khi ứng dụng nhận JSON tùy ý từ client rồi ghép trực tiếp vào MongoDB filter.

Ví dụ payload ngoài ý muốn:

```json
{
  "email": {
    "$ne": null
  }
}
```

Nếu một API đăng nhập/tra cứu mong `email` là string nhưng lại nhận object và sử dụng nó làm **MongoDB operator expression**, truy vấn có thể khác hoàn toàn so với ý định.

### Dạng viết rủi ro

```java
// Cảnh báo: không đưa Map tùy ý của client
// vào filter hay raw command khi chưa validate schema.
Document rawQuery = new Document(userSuppliedMap);
collection.find(rawQuery);
```

### Cách viết rõ type

```java
public record FindCustomerRequest(String email) {}

if (request.email() == null || request.email().isBlank()) {
    throw new IllegalArgumentException("email bắt buộc");
}

collection.find(
    Filters.eq("email", request.email())
);
```

Khi `email` là một Java `String`, driver encode nó như một **BSON String value** trong equality filter, không phải một document chứa toán tử do client quyết định.

### Test negative

- Client gửi email là string bình thường: được xử lý theo contract.
- Client gửi email là object với key `$ne`: API trả validation error, không thực hiện raw operator.
- Client gửi JSON có `$where` hoặc unexpected keys: reject nếu schema không cho phép.
- Client gửi `tenantId` trái với principal: filter vẫn phải dùng principal.

Không khuyến khích dùng các expression nguy hiểm tùy ý trong production để “test injection”. Chạy negative inputs với fixture và quan sát **API validation**, không mở rộng sang tấn công ngoài phạm vi.

## 26. Phân biệt input validation và database authorization

Input validation trả lời “payload có hợp lệ theo schema API không?”. Authorization trả lời “actor có quyền thực hiện hành động không?”.

Ví dụ:

```text
Payload:
  status = "PAID"
  orderId = "order-b-001"

Input validation:
  status là một enum hợp lệ -> PASS

Authorization:
  user tenant-a không sở hữu order-b-001 -> DENY
```

Một payload hợp lệ về kiểu dữ liệu vẫn có thể không được phép về **nghiệp vụ/quyền**. Ngược lại, user có quyền vẫn không được phép gửi một raw MongoDB expression không được hỗ trợ vào REST API.

### Schema validation của MongoDB bổ sung gì?

MongoDB collection validator có thể kiểm tra:

- Fields bắt buộc.
- BSON types.
- Enum/ranges/những ràng buộc được hỗ trợ.

Nhưng collection validator thông thường **không biết authenticated HTTP principal** hoặc tenant policy của ứng dụng. Validator và tenant authorization cần được kiểm thử độc lập.

## 27. TLS: test mã hóa trên đường truyền

MongoDB có thể yêu cầu TLS. Mục tiêu test:

1. Client kết nối thành công khi dùng TLS và certificate hợp lệ.
2. Client **không** được chấp nhận kết nối plaintext nếu policy requireTLS.
3. Client từ chối certificate không tin cậy hoặc hostname không khớp.
4. Không có cấu hình bỏ qua xác minh certificate trong production.
5. Certificate rotation không phá kết nối hợp lệ.

Ví dụ ý tưởng cấu hình self-managed:

```yaml
net:
  bindIp: "127.0.0.1,10.10.20.12"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: "/etc/mongodb/tls/server.pem"
    CAFile: "/etc/mongodb/tls/ca.pem"
security:
  authorization: enabled
```

Đây là **trích đoạn**, không phải cấu hình production hoàn chỉnh. Cần internal authentication phù hợp đối với replica set/sharded cluster và certificate SAN/trust chain đúng.

### Positive test TLS

```text
Trusted CA + correct hostname + tls=true
  -> TLS handshake thành công
  -> tiếp tục AuthN/AuthZ
```

### Negative test TLS

```text
Wrong hostname / untrusted CA
  -> client từ chối server identity
```

**Không sửa test bằng `tlsInsecure=true` hoặc bỏ hostname validation** nếu yêu cầu thực tế là kết nối an toàn. Những tùy chọn insecure chỉ có thể được xem xét trong lab đặc biệt, không làm tiêu chí PASS của production security tests.

## 28. Test network controls, Atlas IP Access List và private connectivity

Với Atlas public endpoint, một đường kết nối có thể chịu kiểm soát của **Project IP Access List**. Nhưng IP list chỉ là lớp network, không phải database user.

Ma trận:

| Nguồn test | Network policy | Credential | Kỳ vọng |
| --- | --- | --- | --- |
| Allowed CI egress | Allow | Đúng | Kết nối, sau đó RBAC |
| Allowed CI egress | Allow | Sai | AuthN deny |
| Disallowed test source | Deny | Đúng | Không tiếp cận endpoint tương ứng |
| Private endpoint workload | Private path hợp lệ | Đúng | Kết nối qua DNS/route private |
| Private endpoint workload | Private DNS sai | Không liên quan | Không thể dùng path kỳ vọng |

Không cần phát động traffic từ Internet không kiểm soát. Negative test network nên dùng **một nguồn thử nghiệm được phê duyệt** nằm ngoài access list và không gây scan/traffic bất thường.

### Điều gì cần lưu ý với NAT?

Đối với public Atlas path, địa chỉ nguồn mà Atlas nhìn thấy thường là **public egress IP sau NAT**, không phải IP private của Pod/VM.

Ví dụ:

```text
CI Pod: 10.2.1.5
Cloud NAT: 198.51.100.24
Atlas public endpoint
```

`198.51.100.24` là địa chỉ ví dụ. Thay đổi NAT có thể khiến test fail vì network dù credentials đúng.

### Private Endpoint không tự chứng minh traffic đã đi private

Test cần kiểm tra DNS, routing, endpoint state và connection string phù hợp. Một ứng dụng có thể đã tạo Private Endpoint nhưng vẫn dùng URI resolve tới public endpoint. Chỉ kiểm tra “connect succeeds” là chưa đủ.

## 29. Kiểm thử TLS khác kiểm thử authentication

Khi client không xác minh được certificate, lỗi xảy ra **trước khi database user được authenticated**. Nếu test sai password nhưng TLS cũng sai, lỗi trả về có thể là TLS handshake error, không phải “password bị từ chối”.

Thiết kế test theo tầng:

```text
TEST-TLS:
  valid server cert? yes/no

TEST-AUTHN:
  TLS đã đúng
  valid credentials? yes/no

TEST-AUTHZ:
  TLS đã đúng
  credentials đã đúng
  privilege for operation? yes/no
```

Điều này giúp negative tests không pass nhầm do một tầng khác hỏng.

## 30. Encryption at rest, in transit và field-level encryption

Ba hình thức bảo vệ khác nhau:

| Cơ chế | Bảo vệ chủ yếu ở đâu? | Điều không tự bảo đảm |
| --- | --- | --- |
| TLS in transit | Network traffic client–server | Không mã hóa bản sao data tại application/logs |
| Encryption at rest | Storage files/backups theo backend/platform | Authorized DB user vẫn đọc được plaintext qua query |
| Client-Side Field Level Encryption (CSFLE) | Chọn fields được mã hóa **trước khi đến server** | Không thay mọi authorization hoặc secret hygiene |
| Queryable Encryption (khi hỗ trợ) | Selected encrypted fields và một số query patterns | Không miễn phí về hiệu năng/index, không mã hóa mọi field mặc định |

**Lưu ý:** MongoDB Atlas/Enterprise, cloud disk encryption và các feature client-side encryption có tính năng/requirements khác nhau. Không mặc định Community self-managed có toàn bộ capability của Enterprise/Atlas.

### Test encryption at rest ra sao?

Không nên SSH vào production disk rồi tự mở WiredTiger files để xem có plaintext. Phương án xác minh phù hợp gồm:

- Đọc chính sách/configurations của storage encryption và KMS.
- Kiểm tra encryption keys, rotation/access policy theo quyền được cấp.
- Xác minh backup/snapshots cũng được mã hóa theo policy.
- Audit ai được phép truy cập volumes, snapshots và key material.
- Kiểm tra compliance evidence/infra-as-code controls phù hợp.

Một test đọc document thành plaintext qua authorized MongoDB query **không bác bỏ encryption at rest**: server giải mã dữ liệu cho client được phép theo thiết kế.

## 31. Test client-side encrypted fields

Giả sử collection `customers` có trường `identityNumber` cần được mã hóa ở phía client theo chính sách:

```text
Application Java
  plaintext identityNumber
       |
       v
  CSFLE / encryption library + KMS key
       |
       v
MongoDB lưu ciphertext cho field đã chọn
       |
       v
Client có key + quyền phù hợp -> decrypt
Client không có key -> không tự giải mã được
```

Các test cần kiểm tra:

1. Client có key và role phù hợp ghi/đọc dữ liệu đúng.
2. Một client không có decryption key không nhận được plaintext field qua cơ chế giải mã tự động.
3. Dữ liệu lưu thực sự ở dạng encrypted BSON/value đúng feature, không chỉ chuỗi đã được base64-encode.
4. KMS key policy không mở rộng hơn yêu cầu.
5. Sensitive plaintext không xuất hiện trong application logs hoặc exception trace.
6. Key rotation/migration scenarios có kế hoạch và test.
7. Query/filter trên encrypted field chỉ dùng operators/feature được hỗ trợ.

**Base64 không phải encryption.** Một chuỗi base64 có thể decode ngược trực tiếp mà không cần key. Masking và hashing cũng không đồng nghĩa encryption; chúng phục vụ mục đích khác nhau.

## 32. Test secrets và cấu hình MongoDB URI

Một connection URI có thể chứa:

```text
mongodb://<username>:<password>@host:27017/<db>?authSource=...
```

Nếu URI bị log đầy đủ, attacker có thể lấy credential mà không cần vượt qua một lỗi authentication nào.

### Các vị trí dễ lộ secret

- `application.properties`/`application.yml` commit trong repository.
- Environment dumps được đính kèm CI artifacts.
- Log message kiểu `"Connecting to " + mongoUri`.
- Exception handler trả nguyên stack trace/driver settings.
- Unit test snapshot chứa URI có password.
- Docker Compose files có plaintext credentials.
- Metrics/tracing tags ghi toàn bộ connection string.
- Shell history hoặc process command line khi dùng tools.

### Positive configuration checks

- Secrets lấy từ secret manager/CI secret store.
- Ứng dụng không in plaintext password.
- Role/service account có quyền tối thiểu.
- Credential rotation workflow tồn tại và được kiểm thử trên staging.
- TLS private keys được bảo vệ bằng file permissions/KMS phù hợp.

### Negative test redaction

Tạo một **fake secret marker** đặc biệt cho fixture, ví dụ `TEST_SECRET_NEVER_LOG_001`. Khởi tạo một đường lỗi đã dự đoán và xác nhận:

```text
Application log contains "TEST_SECRET_NEVER_LOG_001"?
  YES -> FAIL
  NO  -> PASS theo phạm vi logs đã kiểm tra
```

Không ghi secret thật vào test log chỉ để xem hệ thống có mask nó được không. Dùng giá trị giả và bảo đảm log capture bao phủ những đường lỗi thực.

## 33. Kiểm thử logging và exception handling

Một exception database có thể chứa:

- Hostname và port.
- Database/collection names.
- Query hoặc command details.
- Document fragments hay sensitive fields theo code logging.
- Stack traces.

Đừng tự trả exception thô về HTTP:

```java
// Không nên:
return ResponseEntity.status(500)
    .body(exception.toString());
```

Một response an toàn hơn:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu",
  "correlationId": "test-correlation-001"
}
```

Server log có thể lưu thêm chi tiết chẩn đoán theo chính sách, nhưng phải redact/mask fields nhạy cảm và giới hạn người xem. Không phải cứ “ẩn lỗi khỏi client” là xong nếu backend log vẫn lưu đầy đủ token/PII.

### Test log redaction nên có những tình huống nào?

1. Authentication thất bại.
2. Authorization denied.
3. Validation error với field PII.
4. Duplicate key error trên field nhạy cảm.
5. Query timeout hoặc network disconnect.
6. Failed encryption/KMS access.
7. Unexpected exception trong controller.

Không dựa vào một regex duy nhất cho mọi loại secret; cần danh mục fields nhạy cảm và contract logging.

## 34. Audit logging và hành động nhạy cảm

**Audit** cần trả lời: ai làm gì, khi nào, trên resource nào, kết quả allow/deny ra sao, và request nào dẫn tới hành động.

Một audit event ứng dụng minh họa:

```json
{
  "eventType": "ORDER_ACCESS_DENIED",
  "actorId": "user-a",
  "tenantId": "tenant-a",
  "resourceType": "order",
  "resourceId": "order-b-001",
  "outcome": "DENIED",
  "correlationId": "req-test-001"
}
```

Không cần log **toàn bộ payload PII** của order để biết có truy cập trái phép. Audit log cũng có thể chứa thông tin cá nhân, nên cần access control và retention.

### Phân biệt MongoDB audit và application audit

- MongoDB server/Atlas audit (khi feature/tier hỗ trợ) có thể ghi những security/database events.
- Application audit biết **HTTP user, tenant, business operation, approval chain** — thông tin mà database server không tự biết nếu mọi request dùng chung một MongoDB service user.

Vì vậy một ứng dụng multi-tenant có thể cần **cả hai cấp độ** audit nếu policy yêu cầu.

### Kiểm thử audit

| Operation | Kỳ vọng audit |
| --- | --- |
| Successful sensitive read | Ghi event theo policy, không chứa PII quá mức |
| Denied cross-tenant read | Có actor/target/outcome phù hợp |
| Denied DB write privilege | Có database/auth event nếu hệ hỗ trợ |
| Credential rotation | Có change/approval event |
| Export/backup/restore | Có actor, scope, purpose và audit trail |
| Admin role change | Có event và alert khi cần |

Một audit test nên xác nhận **event tồn tại**, fields tối thiểu đúng và secrets không bị ghi. Nếu audit feature chưa được bật/tier không hỗ trợ, không được đánh dấu PASS một cách giả định.

## 35. Data retention, TTL và privacy deletion

Bảo vệ dữ liệu nhạy cảm không chỉ là ngăn đọc trái phép; còn gồm **không giữ dữ liệu quá thời hạn cần thiết**.

Một collection `temporary_tokens` có thể dùng TTL:

```javascript
db.temporary_tokens.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

Nhưng:

- TTL deletion **không diễn ra tức thời đúng mili giây** sau thời hạn.
- TTL không bảo đảm dữ liệu đã biến mất khỏi tất cả backups/snapshots.
- Một token bị xóa khỏi collection nhưng còn trong log có thể vẫn bị lộ.
- TTL index không phải cơ chế authorization hoặc encryption.

### Test retention

1. Document có expiry phù hợp được TTL cleanup theo thời gian cho phép.
2. Document chưa hết hạn không bị xóa sớm.
3. Backup retention phù hợp chính sách.
4. Logs/test artifacts có thời hạn lưu được quy định.
5. Deletion workflow xử lý dependencies, exports và backups theo yêu cầu pháp lý/chính sách.

**Không dùng `Thread.sleep(1000)` rồi assert TTL document chắc đã biến mất**; TTL monitor chạy theo lịch riêng. Integration test nên có bounded polling/time tolerance trong môi trường lab.

## 36. Backup và snapshot cũng là nơi chứa dữ liệu nhạy cảm

Một production database có RBAC rất chặt nhưng backup archive được upload vào bucket public sẽ vẫn có nguy cơ rò rỉ.

Test/checklist cho backup:

| Hạng mục | Kỳ vọng |
| --- | --- |
| Access control | Chỉ backup/restore operators được cấp quyền |
| Encryption | At-rest và transport phù hợp |
| Retention | Đủ phục hồi, không giữ vô thời hạn ngoài policy |
| Isolation | Backup nằm ngoài failure domain production phù hợp |
| Restore destination | Staging có network/RBAC tương đương độ nhạy dữ liệu |
| Temporary artifacts | Archive dump, logs, CSV exports được dọn đúng hạn |
| Audit | Backup/export/restore có actor và change record |
| Recovery test | Có restore drill mà không xuất PII rộng ra môi trường dev |

### Không copy production data vào test DB thiếu bảo vệ

Nếu bắt buộc dùng dữ liệu giống production, phải:

- Mask/tokenize các identifiers, email, điện thoại, địa chỉ, tài khoản.
- Xem xét tính nhất quán giữa collections sau masking.
- Hạn chế quyền operator/test runner.
- Có retention và cleanup rõ.
- Không dùng dữ liệu có thể re-identify nếu không được phép.

Mã hóa backup không tự khiến môi trường restore trở nên an toàn nếu restore giải mã vào collection được cấp quyền rộng.

## 37. Testing role change và credential rotation

Service identities và roles thay đổi theo thời gian. Kiểm thử cần bao quát các thay đổi đó.

### Credential rotation

```text
Trước rotation:
  credential V1 -> connect OK

Sau rotation/cutover:
  credential V2 -> connect OK
  credential V1 -> denied theo policy
```

Ứng dụng có connection pool; khi rotate credentials, các connections hiện hữu có thể chưa phản ánh policy ngay theo cách một new connection làm. Vì vậy cần **phân biệt new connection test và active pool behavior**, có kế hoạch drain/recreate connections và chấp nhận temporary overlap khi chính sách yêu cầu.

### Role regression

Nếu một release thêm chức năng export orders, có thể developer yêu cầu cấp `readAnyDatabase` cho service. Đây thường là quyền quá rộng.

Thay vào đó:

1. Xác định database/collection thực cần truy cập.
2. Thêm quyền tối thiểu.
3. Test chức năng export hợp lệ.
4. Test không export collection/database không thuộc phạm vi.
5. Review các đường log/CSV artifact vì export có thể chứa PII.

## 38. Kiểm thử quyền quản trị Atlas khác database RBAC

Atlas có **project/organization access roles** cho quản trị UI/API, và **database users/roles** cho MongoDB commands. Đây là hai hệ thống quyền khác nhau.

Các câu hỏi test:

- Người chỉ có quyền xem project có thay Atlas IP Access List không?
- Người vận hành có được phép tạo/xóa database users không?
- Một application database user có thể tự thay Atlas project config không?
- Một Atlas console user có tự động được quyền đọc collections không?
- Chỉ authorized team có quyền backup/restore/export và thay private endpoint policies?

**Database role `readWrite` không cấp quyền quản lý Atlas project.** Ngược lại, quyền xem cluster trong UI không đồng nghĩa có MongoDB database credential đọc collections.

Trong CI, nếu không có môi trường Atlas test project, một số kiểm soát này nên được kiểm tra qua **policy/configuration assertions** hoặc một kiểm thử môi trường được phê duyệt, không cố chạy operations quản trị lên production.

## 39. Bảo vệ quyền truy cập ở cấp collection và field

Một MongoDB built-in role thường kiểm soát privilege ở mức database/collection/command, **không phải cơ chế tự động ẩn mọi field PII theo HTTP user**. Nếu một service có `find` trên collection, nó có thể đọc documents/fields mà role cho phép truy cập ở mức đó, trừ những cơ chế khác được thiết kế/bật.

Vì thế:

- **Application projection** giới hạn fields xuất ra API.
- **Application authorization** giới hạn documents theo tenant/owner.
- **CSFLE/Queryable Encryption** có thể bảo vệ những fields được mã hóa theo quyền key.
- **Database roles** giới hạn resources/actions.
- **Views** có thể cung cấp một bề mặt đọc giới hạn theo thiết kế và privilege phù hợp, nhưng cần kiểm tra view definition và source permissions theo MongoDB version.

Không tự cho rằng một `read` role trên `customers` sẽ tự ẩn `identityNumber` khỏi ứng dụng.

## 40. Multi-tenant: phân quyền cần chạy qua các truy vấn phức tạp

Một báo cáo dùng aggregation:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-a" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
]);
```

Nếu developer bỏ `$match` tenant, report có thể cộng dữ liệu của mọi tenant. Đây là **lỗi rò rỉ qua aggregate** dù không trả từng document.

### Những operators cần test

- `$match`: scope theo tenant/owner.
- `$lookup`: không join sang dữ liệu tenant khác khi policy cấm.
- `$facet`: mọi nhánh output có scope đúng.
- `$group`: aggregate counts/sums không cộng lẫn tenants.
- `$unionWith` (nếu được dùng): không mở rộng dữ liệu ngoài phạm vi.
- `$out`/`$merge`: chỉ cho writers được phép và destination đúng.

Nếu business requirement cho phép thống kê đa tenant đã được ẩn danh, cần định nghĩa policy riêng; không mặc định mọi báo cáo đa tenant đều hợp lệ hoặc đều bị cấm.

### Test aggregation với fixtures đối lập

Tạo tenant A có 2 orders và tenant B có 5 orders. Khi user A xem report:

```text
Expected count = 2
Not expected = 7
```

Fixture khác biệt rõ giúp phát hiện query thiếu tenant filter. Nếu mỗi tenant tình cờ có cùng số lượng/giá trị, test có thể không phát hiện kết quả trộn.

## 41. Dữ liệu nhạy cảm trong search, pagination và exports

Các endpoints đặc biệt dễ bị quên:

```text
GET /orders?page=...
GET /orders/search?email=...
GET /reports/orders.csv
POST /orders/bulk-export
GET /customers/{id}/attachments
GET /audit/events
```

Kiểm thử:

1. Search scope theo tenant và role, không chỉ exact ID query.
2. Pagination total/count không tiết lộ số records của tenant khác.
3. Sort/filter fields không cho phép truy cập các sensitive fields ngoài policy.
4. Export CSV chỉ chứa columns được phép, có giới hạn số dòng.
5. Generated files có access token/expiry và storage ACL phù hợp.
6. Download attachment kiểm tra document ownership trước khi trả bytes.
7. Error responses không tiết lộ ID tồn tại của tenant khác nếu policy che giấu.

Với CSV, còn cần cân nhắc **spreadsheet formula injection** khi một field do người dùng nhập bắt đầu bằng ký tự công thức. Đây là vấn đề ở **export format**, không phải MongoDB RBAC; nên kiểm thử escaping theo format/consumer được hỗ trợ.

## 42. Chạy security tests với Docker/Testcontainers

MongoDB chạy trong container có thể giúp integration tests lặp lại được. Tuy nhiên, một MongoDB container mặc định **không bật authentication** có thể đủ cho CRUD tests nhưng **không đủ để test RBAC/AuthN**.

Một test environment thật sự cho authentication nên provision:

- MongoDB server bật authorization.
- Users/roles test có quyền khác nhau.
- Fixture databases và collections.
- TLS certificates hoặc test PKI nếu test TLS.
- Network isolation.
- Cleanup/teardown.

### Tách test suites theo mục đích

| Suite | Môi trường | Kiểm chứng |
| --- | --- | --- |
| Unit tests | Mocks/fakes | Policy decisions, tenant scope builder |
| Repository integration | MongoDB test instance | BSON mappings, query predicates, indexes |
| DB AuthN/RBAC integration | Auth-enabled MongoDB | Credentials, role allow/deny |
| TLS/network integration | TLS-enabled test deployment | Certificate validation, deny/allow network |
| API security E2E | App + auth + MongoDB test | BOLA/IDOR, projections, errors, exports |
| Backup/restore/security config | Controlled staging | Backup encryption/access, restore privacy |

Không nhất thiết chạy mọi bài test nặng ở mỗi commit. Nhưng nên có tối thiểu **gates bắt buộc** cho những yêu cầu bảo mật trọng yếu và lịch chạy định kỳ cho các kiểm thử hạ tầng.

### Không publish test database rộng

Đối với Docker, không cần map `27017` lên tất cả host interfaces. Giới hạn test network, dùng host loopback nếu runner cần truy cập từ host và kiểm tra image/container configuration. Một container dùng `bindIpAll` bên trong namespace vẫn phải được bảo vệ ở layer Docker publishing/network.

## 43. Dùng Spring Security trong authorization tests

Trong một Spring Boot HTTP app, authentication có thể được xử lý bởi Spring Security, còn MongoDB service user hoạt động ở backend. Test nên bao phủ:

```text
Anonymous -> 401 nếu endpoint bắt buộc login
User login nhưng thiếu role -> 403 (hoặc policy khác)
User có role nhưng khác tenant -> 403/404 theo contract
User có role + đúng tenant -> 200/expected result
```

### Không mã hóa tenantId vào request rồi tin tưởng

Một service sử dụng:

```java
String tenantId = request.getParameter("tenantId");
```

để xác định quyền truy cập là rủi ro nếu client có thể thay tenantId. Nguồn đúng là **principal/claim được xác thực** và đã kiểm tra, kết hợp policy cho phép user chọn tenant khi họ thuộc nhiều tenants.

### Cẩn thận với JWT claims

Một JWT payload được base64url-encode không đồng nghĩa đã được xác thực. Security filter phải kiểm tra signature, issuer, audience, expiry và các ràng buộc thích hợp theo cấu hình. Test không nên cho một token tự tạo với `role=admin` vượt qua authentication.

Nếu token bị revoke nhưng vẫn còn hiệu lực đến expiry, cần có chính sách revoke/session/token lifecycle rõ; MongoDB RBAC không tự giải quyết vấn đề đó.

## 44. Kiểm thử tenant boundary khi có caching

Ứng dụng có thể query MongoDB đúng tenant nhưng cache sai key:

```text
cache key = "order:order-a-001"
```

Nếu ID không globally unique hoặc cache trả object không kiểm tra lại authorization, một tenant có thể nhìn thấy dữ liệu của tenant khác.

Khuyến nghị:

```text
cache key chứa identity/scope phù hợp,
ví dụ tenantId + resourceId,
và caching layer tuân thủ authorization policy.
```

Security test nên chạy cả **cache miss** và **cache hit**:

1. User A đọc order A để nạp cache.
2. User B thử cùng resource ID hoặc crafted path.
3. Kỳ vọng B vẫn bị từ chối.

Kiểm thử chỉ repository mà bỏ caching/controller có thể không phát hiện dạng rò rỉ này.

## 45. Error handling: 401, 403, 404 và thông tin bị lộ

Các response status phục vụ mục tiêu khác nhau:

| Status | Ý nghĩa thường dùng | Khi nào kiểm tra |
| --- | --- | --- |
| 400 | Input không hợp lệ | Sai JSON shape, unexpected operators |
| 401 | Chưa authenticated/credential không hợp lệ ở API | Thiếu hoặc sai HTTP token |
| 403 | Authenticated nhưng không có quyền | Role không đủ |
| 404 | Tài nguyên không được tìm thấy/có thể che existence | Cross-tenant theo policy |
| 409 | Trạng thái xung đột | CAS/business state conflict |
| 500 | Lỗi phía server đã được xử lý | Không lộ stack trace/secrets |

**MongoDB Unauthorized error không bắt buộc map trực tiếp thành HTTP 403** trong mọi service. Có thể đó là lỗi **service account provisioning**, lúc ấy API nên trả lỗi tổng quát và vận hành cần alert, thay vì đưa nội dung database command ra client.

### Enumeration risk

Nếu API trả 404 cho ID không tồn tại nhưng 403 cho ID tồn tại thuộc tenant khác, attacker có thể suy ra sự tồn tại của resources. Một policy có thể chọn trả 404 cho cả hai để giảm thông tin. Test nên kiểm tra **tính nhất quán với policy**, không áp một HTTP code cho mọi tình huống.

## 46. Test cases cho admin và operational commands

Những thao tác có thể gây tác động lớn:

- `dropCollection` / `dropDatabase`.
- `createUser` / `grantRolesToUser`.
- `createIndex` / `collMod`.
- `shutdown` / configuration commands tùy topology.
- Backup/export/restore.

Một application service account hiếm khi cần quyền thực hiện tất cả thao tác này.

### Phân tách trách nhiệm

```text
App runtime user:
  đọc/ghi nghiệp vụ cần thiết

Migration/DBA identity:
  index/schema migration theo change request

Backup identity:
  quyền backup/export cần thiết

Atlas project admin:
  quản lý hạ tầng/project theo role riêng
```

Test một release nên bảo đảm application runtime credential **không tự được nâng quyền** chỉ vì migration job chạy trong cùng pipeline.

### Không dùng root cho mọi test

Nếu tất cả integration tests đều kết nối bằng MongoDB root user, test sẽ không phát hiện:

- App code mới yêu cầu một privilege không được duyệt.
- Read-only account vô tình có write privilege.
- Collection scope rộng hơn dự định.

Hãy có test bằng chính **service identity production-like**, trong môi trường không chứa dữ liệu thật.

## 47. Các lỗi kiểm thử thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách hiểu/khắc phục |
| --- | --- | --- |
| Wrong password test pass nhưng correct user cũng fail | DNS/TLS/firewall lỗi | Khắc phục precondition network trước |
| User chỉ đọc vẫn insert được | Role thực quá rộng | Kiểm tra `usersInfo`/role definitions và provisioning |
| Reader không thể list collections | Custom role chỉ có `find` | Kiểm tra privilege hành động, không cấp root |
| Cross-tenant GET trả data | Query thiếu tenant scope | Scope từ authenticated principal |
| GET an toàn nhưng PATCH sửa tenant khác | Update filter chỉ có ID | Thêm tenant/owner/state predicate |
| Response lộ field nội bộ | Serialize entity trực tiếp | DTO allowlist/projection |
| Log chứa MongoDB URI có password | Log configuration hoặc exception handler | Redact credentials, test fake secret |
| CSFLE test fail | Key/KMS/ciphertext config không phù hợp | Kiểm tra feature và key access |
| TLS test dùng insecure thành công | Validation bị tắt | Kiểm tra default config và bật verification |
| Atlas user có quyền UI nhưng DB query fail | Project roles khác DB users | Provision đúng database user |
| Auth test fail khi app vừa tạo client | Chưa thực thi command | Gọi command có xác thực thật |
| Negative insert fail do duplicate key | Không phải authorization deny | Dùng unique fixture và assert code |
| Test pass với fixture trống | Không có target cross-tenant/sensitive data | Seed dữ liệu đối lập |
| CI artifacts có PII | Dump/log/test report lưu quá rộng | Dùng fixtures giả, scrub artifacts |
| TTL test timeout | TTL cleanup asynchronous | Poll bounded và hiểu thời gian monitor |
| Background job đọc cross-tenant | Job không dùng cùng authorization scope | Policy riêng cho service/job |
| MongoDB backup public | Storage ACL/encryption sai | Kiểm tra backup platform và network |
| Test nhiều CI jobs đè fixture | Dùng IDs cố định/chung DB | Tách namespace/testRunId, cleanup |

## 48. Runbook kiểm thử trước release

### Bước 1 — Kiểm tra yêu cầu và phạm vi

```text
Release:
MongoDB server/version:
Application version:
Environment:
Approved security requirements:
Roles under test:
Tenant fixtures:
Test operator:
```

Xác định tests nào bắt buộc ở mỗi PR, tests nào chạy nightly và tests nào cần staging Atlas/PKI/network.

### Bước 2 — Provision fixture cô lập

1. Tạo database/cluster test đúng network.
2. Tạo roles/users qua bootstrap automation với secret store.
3. Seed documents có tenant A/B và fake PII.
4. Bật auth/TLS như môi trường đích ở những suite tương ứng.
5. Đảm bảo fixture admin có thể cleanup, app users không được dùng admin credentials.

### Bước 3 — Chạy positive cases

- Đúng credentials/authSource.
- Reader đọc được authorized collection.
- Writer ghi được những fields/collections cần thiết.
- Tenant A đọc/ghi đúng dữ liệu A.
- API public chỉ trả fields được phép.

### Bước 4 — Chạy negative cases

- Sai password/authSource.
- Không có role hoặc thiếu privileges.
- Cross-database/collection access denied.
- Cross-tenant GET/PATCH/DELETE/list/export denied.
- Unsafe input shapes bị validation chặn.
- TLS invalid certificate bị từ chối.
- Sensitive fields/secrets không có trong response/log.

### Bước 5 — Kiểm tra evidence

```text
PASS phải có:
  expected result
  actual result
  correct failure layer
  no unauthorized data mutation
  sanitized test logs
```

Một request không thực thi được vì network timeout không được ghi PASS cho authorization denial.

### Bước 6 — Cleanup

- Xóa fixture đúng database/testRunId.
- Xóa test secrets/temporary access list entries.
- Dọn dump/CSV/test artifacts nhạy cảm theo policy.
- Thu hồi quyền temporary admins/CI runners.
- Kiểm tra test cleanup không ảnh hưởng dữ liệu ngoài scope.

## 49. Tiêu chí release gate

Một hệ thống có thể đặt tiêu chí:

| Gate | Điều kiện |
| --- | --- |
| AuthN | Valid login pass, invalid login fail đúng tầng |
| Database RBAC | Các allow/deny trong role matrix đều được xác nhận |
| Tenant isolation | Không có cross-tenant read/write qua endpoints chính |
| Data minimization | Public API schema không có sensitive fields |
| Secret hygiene | Không có secrets trong repository/logs/artifacts được scan |
| TLS/network | Deployment phù hợp policy đã duyệt |
| Data encryption | Các control at rest/client-side cần thiết được cấu hình và có evidence |
| Backup | Quyền, encryption, retention và restore policy được xác nhận |
| Audit | Sensitive operations có event theo policy |
| Cleanup | Không còn users/entries/fixtures tạm ngoài thời hạn |

**Một security gate fail phải được xử lý theo severity và risk acceptance process**, không chỉ mark flaky rồi bỏ qua. Tuy nhiên, cần phân biệt lỗi hạ tầng test với bằng chứng control bị vi phạm; tránh báo “unsafe production” khi chỉ có một fixture missing.

## 50. Những nhầm lẫn thường gặp

| Nhận định | Vì sao chưa đúng? | Cách hiểu đúng |
| --- | --- | --- |
| “Ping MongoDB được nghĩa là đã có quyền đọc” | Ping không chứng minh collection privilege | Test operation thật |
| “AuthN thành công là AuthZ đúng” | Identity có thể bị cấp role quá rộng | Negative RBAC tests |
| “App dùng MongoDB readWrite thì tenant A không đọc được B” | DB role không biết HTTP tenant | App scope/authorization |
| “Tất cả tests dùng root cũng đủ” | Không kiểm tra least privilege | Test bằng service identities |
| “Failed insert là PASS cho deny” | Có thể do duplicate key/network | Assert authorization cause và no mutation |
| “Một user sai password là đã test brute-force protection” | Chỉ kiểm tra một negative authentication | Rate limit/monitoring policy riêng |
| “Cấu hình TLS là kết nối đã an toàn” | Có thể bỏ hostname verification | Negative certificate test |
| “IP Access List thay password” | Network control khác AuthN | Dùng nhiều lớp |
| “Private endpoint nghĩa là API không lộ PII” | Đường mạng không thay output minimization | DTO/projection/masking |
| “Bật storage encryption thì read user không thấy plaintext” | Server giải mã cho authorized query | RBAC + CSFLE khi cần |
| “Base64 là encryption” | Không có cryptographic secrecy | Dùng encryption đúng |
| “CSFLE thay tenant RBAC” | Encryption key access và document authorization khác nhau | Thiết kế cả hai |
| “Validator kiểm tra quyền user” | Schema validator không biết HTTP principal | Authorization riêng |
| “Search endpoint không cần tenant filter” | Vẫn có thể leak aggregates/list | Scope mọi data path |
| “Field không xuất response là log cũng an toàn” | Logging có thể in raw entity | Log redaction tests |
| “Backup không phải data nên ít nhạy cảm” | Backup có thể chứa toàn bộ PII | ACL/encryption/retention |
| “TTL xóa ngay và cả trong backup” | TTL asynchronous và không tự sửa backup | Retention workflow |
| “Project admin là MongoDB database user” | Atlas project role khác DB user | Test đúng control |
| “Client gửi tenantId là đủ xác định quyền” | Client có thể sửa tenantId | Dùng authenticated principal |
| “GET kiểm tra tenant rồi UPDATE theo ID là đủ” | Có race và update bỏ scope | Predicate chứa tenant/state |
| “JWT payload giải mã được tức là hợp lệ” | Cần verify signature/claims | Spring Security validation |
| “Không có PII trong fixture nên test redaction pass” | Không kích hoạt nhánh redaction | Seed fake sensitive fields |
| “Negative tests nên chạy trên production” | Role sai có thể gây thao tác thật | Dùng disposable environment |

## 51. Bài tập có đáp án

### Bài 1. AuthN và AuthZ

Một user MongoDB đăng nhập thành công nhưng chạy `insertOne()` bị Unauthorized. AuthN và AuthZ có kết quả gì?

**Đáp án:** AuthN thành công, AuthZ từ chối operation vì user thiếu quyền. Không sửa bằng cách tắt auth hoặc mở firewall.

### Bài 2. authSource

User được tạo trong database `security_lab`. URI dùng `authSource=admin`, đúng password nhưng authentication fail. Cần kiểm tra gì?

**Đáp án:** User identity được lưu ở auth database nào. Nếu user chỉ tồn tại trong `security_lab`, cần `authSource=security_lab`.

### Bài 3. Reader privilege

Service chỉ cần đọc orders nhưng có role `readWrite` trên cả `security_lab`. Test `insertOne()` thành công. Kết luận?

**Đáp án:** Role rộng hơn yêu cầu; least-privilege negative test thất bại. Cần role đọc với scope phù hợp.

### Bài 4. Database role và collection scope

Role `read` trên `security_lab` có chắc chỉ cho đọc collection orders không?

**Đáp án:** Không. Built-in role cấp quyền đọc theo phạm vi database. Muốn giới hạn riêng orders cần custom role hoặc kiến trúc phân tách phù hợp.

### Bài 5. Negative test pass giả

Test quyền deny assert mọi `MongoException`. Khi database không reachable, test pass. Sai ở đâu?

**Đáp án:** Lỗi network không chứng minh authorization. Cần positive connection precondition và assert Unauthorized cause/code, cùng no mutation.

### Bài 6. MongoClient

`MongoClients.create(uri)` không ném lỗi khi password sai. Có nghĩa auth thành công không?

**Đáp án:** Không. Client có thể trì hoãn connect/authentication cho đến command đầu tiên. Phải chạy command có liên quan.

### Bài 7. Tenant ID

API nhận query `?tenantId=tenant-b` từ user tenant A rồi dùng trực tiếp trong MongoDB filter. Rủi ro?

**Đáp án:** Client có thể giả tenant scope. Phải lấy tenant từ authenticated principal hoặc kiểm tra quyền chọn tenant rõ ràng.

### Bài 8. Cross-tenant GET

User A được trả order B khi biết ID. Đây là lỗi gì?

**Đáp án:** Broken Object Level Authorization (BOLA/IDOR). Kiểm tra query có tenant/owner predicate và authorization theo principal.

### Bài 9. Cross-tenant PATCH

GET endpoint đã scope tenant nhưng PATCH chỉ query bằng `_id`. Có thể an toàn chưa?

**Đáp án:** Chưa. Update cũng phải chứa tenant/owner/business-state predicate và kiểm tra matched count.

### Bài 10. Fixture

Test response “không lộ internalNotes” với fixture chưa bao giờ có internalNotes. Test đáng tin cậy không?

**Đáp án:** Không đủ. Phải seed một giá trị nhạy cảm giả rồi xác minh response thực sự loại bỏ field/value.

### Bài 11. MongoDB role so với HTTP role

Spring Boot dùng một MongoDB service user readWrite cho tất cả HTTP requests. MongoDB tự biết Alice và Bob không?

**Đáp án:** Không mặc định. Database nhìn thấy service identity. App phải kiểm tra HTTP principal và tenant/owner policy.

### Bài 12. Projection

API dùng projection chỉ lấy `displayName` nhưng query thiếu tenant filter. Đã an toàn chưa?

**Đáp án:** Chưa. Projection giới hạn field, không giới hạn ai được xem document nào.

### Bài 13. NoSQL injection

API mong email string nhưng chấp nhận JSON object chứa `$ne` và dùng object trực tiếp trong filter. Cần sửa gì?

**Đáp án:** Validate DTO field là string và dựng filter typed bằng driver; từ chối unexpected operator-shaped input.

### Bài 14. TLS

Client bỏ qua certificate hostname validation để test luôn pass. Có phải positive TLS security test không?

**Đáp án:** Không. Cần xác minh certificate/CA/hostname đúng và negative test từ chối chứng chỉ không hợp lệ.

### Bài 15. Atlas network

CI Pod private IP `10.2.1.5` ra Internet qua NAT `198.51.100.24`. IP Access List public nên dựa vào IP nào?

**Đáp án:** Public egress IP sau NAT của đường kết nối, trong ví dụ là `198.51.100.24`; địa chỉ chỉ mang tính minh họa.

### Bài 16. Private Endpoint

Đã tạo private endpoint nhưng app vẫn dùng URI public và DNS resolve ra public hosts. Có thể khẳng định traffic private không?

**Đáp án:** Không. Cần test URI, private DNS, routing và endpoint thực được dùng.

### Bài 17. Encryption at rest

Authorized MongoDB user query ra plaintext. Có chứng minh disk không được mã hóa không?

**Đáp án:** Không. Server có thể giải mã khi đọc; at-rest encryption cần kiểm chứng qua cấu hình storage/KMS và operational evidence.

### Bài 18. CSFLE

Một field được base64-encode trước khi ghi. Đã có CSFLE đúng không?

**Đáp án:** Không. Base64 chỉ là encoding, không phải encryption. Cần cơ chế mã hóa, key management và encrypted BSON representation phù hợp.

### Bài 19. Secret trong log

Ứng dụng không trả password qua API nhưng log `MongoDB URI` chứa password khi gặp lỗi. Có vượt kiểm thử bảo vệ dữ liệu không?

**Đáp án:** Không. Secret đã bị lộ qua log; cần masking/redaction, secret manager và log negative tests.

### Bài 20. HTTP 404/403

API trả 403 cho order B và 404 cho ID không tồn tại. Có thể lộ điều gì?

**Đáp án:** Attacker có thể phân biệt resource có tồn tại. Tùy policy, có thể trả 404 nhất quán cho cross-tenant resources.

### Bài 21. TTL

Token hết hạn đúng 12:00. TTL monitor phải xóa ngay đúng 12:00:00.000 không?

**Đáp án:** Không. TTL cleanup asynchronous; test phải có time tolerance và retention requirements phù hợp.

### Bài 22. Backup

MongoDB RBAC chặt nhưng `mongodump` archive bị upload public bucket. Có còn lỗ hổng không?

**Đáp án:** Có. Backup chứa dữ liệu nhạy cảm cần ACL/encryption/retention và monitoring riêng.

### Bài 23. Audit

MongoDB database log chỉ ghi service user `orders-api`. Làm sao biết HTTP user nào xem order B?

**Đáp án:** Cần application-level audit với actorId, tenant, operation, resource và correlationId; MongoDB service identity không tự truyền HTTP principal.

### Bài 24. Cache

Repository query đã scope tenant, nhưng cache key chỉ có orderId và dùng chung giữa users. Rủi ro?

**Đáp án:** Rò rỉ qua cache nếu thiếu scope/recheck authorization. Test cả cache miss/hit với principal khác.

### Bài 25. CI

Suite CRUD chạy trên MongoDB container không bật auth và tất cả tests đều pass. Đã chứng minh MongoDB RBAC production đúng chưa?

**Đáp án:** Chưa. Cần suite riêng trên auth-enabled MongoDB với users/roles thật và negative assertions.

### Bài 26. Admin commands

Service orders có thể gọi `dropCollection` vì được cấp role quản trị để migration thuận tiện. Đây có phù hợp least privilege?

**Đáp án:** Thường không. Migration/DBA identity nên tách khỏi runtime service account; kiểm thử phải chứng minh runtime không drop được.

### Bài 27. Aggregation

Report tenant A đếm 7 orders vì pipeline thiếu `$match`; fixture A có 2 và B có 5. Đây là lỗi gì?

**Đáp án:** Rò rỉ qua aggregation/tenant scope. Thêm đúng authorization filter và test expected count 2.

### Bài 28. Authentication rotation

Sau rotate password, client mới dùng V2 thành công nhưng một connection pool cũ vẫn hoạt động. Có thể kết luận V1 đã bị thu hồi hoàn toàn?

**Đáp án:** Chưa. Cần test new connections, pool lifecycle và chính sách cutover/revocation; không dựa vào một phiên hoạt động đã thiết lập.

### Bài 29. Negative query test

Thử insert bằng reader nhận duplicate key error. Có chứng minh reader không có write privilege không?

**Đáp án:** Không. Nếu thao tác tới giai đoạn duplicate key, có thể không phản ánh authorization deny như mong đợi. Dùng unique fixture và xác nhận server Unauthorized.

### Bài 30. Release gate

Functional tests pass nhưng test cross-tenant PATCH cập nhật được tài nguyên B. Có thể phát hành bình thường không?

**Đáp án:** Không nên. Đây là vi phạm authorization quan trọng; cần xử lý theo severity/release gate và chứng minh denial/no mutation trước khi phát hành.

## 52. Checklist thực hành

### Authentication và network

- [ ] MongoDB deployment kiểm thử thật đã bật authentication.
- [ ] Correct credentials/authSource thành công.
- [ ] Wrong/missing credentials không truy cập protected data.
- [ ] Test auth không pass giả vì DNS/TLS/network hỏng.
- [ ] TLS certificate chain và hostname verification được kiểm chứng.
- [ ] Không có `tlsInsecure` hoặc bypass verification trong production config.
- [ ] Atlas public egress/private endpoint policy được xác nhận đúng tuyến.

### Database authorization

- [ ] Có service users riêng với privileges tối thiểu.
- [ ] Có ma trận allow/deny theo operation/resource.
- [ ] Tests sử dụng **users thật**, không phải mọi test dùng root.
- [ ] Reader không insert/update/delete/drop.
- [ ] Writer không quản trị users/schema ngoài nhu cầu.
- [ ] Cross-database/collection access bị từ chối đúng scope.
- [ ] Negative tests assert đúng Unauthorized cause, không chỉ bất kỳ exception.
- [ ] Dữ liệu không thay đổi sau denied writes.

### Application authorization

- [ ] HTTP principal/roles/tenant được xác thực.
- [ ] Query dùng principal tenant/owner, không tin input tenantId tùy ý.
- [ ] GET/list/search/pagination/report/export đều có scope.
- [ ] PATCH/DELETE/bulk ops có điều kiện authorization trong write predicate.
- [ ] Có tests cross-tenant/owner/anonymous/role mismatch.
- [ ] Cache, files, notifications và background jobs tuân thủ policy.
- [ ] Error status không leak resource existence trái chính sách.

### Dữ liệu nhạy cảm

- [ ] Public API dùng DTO allowlist/projection.
- [ ] Fixture có fake sensitive fields để test không lộ.
- [ ] Logs/metrics/traces không chứa passwords, tokens, raw URIs hoặc PII ngoài policy.
- [ ] Secrets lấy từ secret manager và được rotation.
- [ ] Encryption in transit/at rest/field-level được kiểm chứng đúng yêu cầu.
- [ ] Backup/restore/export có ACL, encryption và retention.
- [ ] Audit logs có events cần thiết nhưng không chứa dữ liệu thừa.
- [ ] TTL/deletion và cleanup test artifacts được kiểm tra.

### Vận hành kiểm thử

- [ ] Security tests chạy trên môi trường cô lập với dữ liệu giả.
- [ ] Mỗi test có ID/scoped fixture/cleanup rõ.
- [ ] CI không xuất credentials hoặc production dump.
- [ ] Có positive preconditions trước negative cases.
- [ ] Có evidence đã sanitize và owner phê duyệt.
- [ ] Các gate bảo mật quan trọng không bị bỏ qua vì flaky infra.

## 53. Tổng kết

Kiểm thử bảo mật MongoDB không dừng ở việc tạo `MongoClient` và chạy `ping`. Một hệ thống đúng cần kiểm chứng **kết nối qua mạng/TLS hợp lệ**, **authentication đúng danh tính**, **MongoDB RBAC chỉ cho phép những actions được cấp**, và **application authorization giới hạn tenant/owner/business scope**. Với mọi đường ghi, negative test còn phải xác nhận **không có dữ liệu bị thay đổi**.

Trong ứng dụng Java/Spring Data MongoDB, các thử nghiệm thực tế nên dùng **service identities riêng** và MongoDB có authentication bật; dùng DTO/projection cho dữ liệu nhạy cảm, filter typed để tránh operator injection và scoping theo authenticated principal cho GET/PATCH/DELETE/aggregation/export. Một DB role đọc/ghi trên collection không tự bảo vệ tenants hoặc ẩn mọi field khỏi API.

Về bảo vệ dữ liệu, **TLS, encryption at rest, CSFLE, secret management, audit, backup retention và log redaction** là các controls bổ sung chứ không thay thế nhau. Một negative test chỉ có ý nghĩa khi thất bại **đúng nguyên nhân**, không phải do kết nối hỏng hoặc fixture thiếu.

Quy trình hiệu quả là **yêu cầu bảo mật → ma trận quyền → fixtures có dữ liệu đối lập → positive/negative integration tests → đối soát dữ liệu/logs → cleanup → release gate**. Khi kiểm thử được cả những hành động **không được phép**, đội phát triển mới có cơ sở đáng tin cậy để khẳng định dữ liệu MongoDB được bảo vệ theo đúng chính sách.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual — User-Defined Roles](https://www.mongodb.com/docs/manual/core/authorization/#user-defined-roles)
- [MongoDB Manual — createRole](https://www.mongodb.com/docs/manual/reference/method/db.createRole/)
- [MongoDB Manual — createUser](https://www.mongodb.com/docs/manual/reference/method/db.createUser/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [MongoDB Atlas — IP Access List](https://www.mongodb.com/docs/atlas/security/ip-access-list/)
- [MongoDB Manual — TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/)
- [MongoDB Atlas — Back Up and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
