# Audit, che dữ liệu nhạy cảm trong log và kiểm soát quyền sao lưu MongoDB

## 1. Bài toán: có backup và log chưa chắc đã an toàn

Một hệ thống thương mại điện tử có collection `orders` chứa địa chỉ giao hàng, `customers` chứa số điện thoại và `payments` chứa thông tin đối soát. API Java kết nối MongoDB bằng một service account; nhân viên vận hành dùng Atlas hoặc các công cụ quản trị; dữ liệu được sao lưu hằng ngày.

Hãy xem ba tình huống:

1. Một tài khoản quản trị MongoDB bị chiếm. Attacker cấp thêm quyền cho một identity mới, tải dữ liệu rồi cố che dấu vết. **Có sự kiện audit nào ghi nhận việc cấp quyền không, và ai có thể sửa/xóa log?**
2. Ứng dụng ghi mọi request và MongoDB driver command vào hệ thống giám sát. Một số lệnh chứa email, số điện thoại hoặc token. **Log có đang trở thành bản sao dữ liệu nhạy cảm nằm ngoài chính sách bảo vệ database không?**
3. Một nhân viên chỉ được giao trách nhiệm “kiểm tra backup” nhưng sở hữu quyền xuất mọi snapshot ra máy cá nhân hoặc khôi phục đè lên production. **Quyền kiểm tra, tạo, xuất, khôi phục và xóa backup đã tách biệt chưa?**

Ba vấn đề trên là ba trụ cột của bài:

- **Audit:** ghi lại bằng chứng về hành động và danh tính theo một chính sách có thể kiểm chứng.
- **Log redaction/data minimization:** hạn chế dữ liệu bí mật lọt vào diagnostic log, audit stream, application log và hệ thống SIEM.
- **Backup authorization:** bảo vệ bản sao dữ liệu khỏi đọc trộm, sửa/xóa, khôi phục sai và thất bại khi phục hồi.

Chúng liên quan nhau nhưng **không thay thế nhau**. Audit đầy đủ không cứu được một snapshot không được mã hóa và bị chia sẻ công khai. Mã hóa log không ngăn service account bị cấp `root`. Backup bất biến không tự cho biết ai đã sửa một document.

### 1.1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **MongoDB database audit**, **diagnostic/server log**, **Atlas Activity Feed**, **application log** và **backup access log**.
- Nhận diện các loại audit event, hiểu `atype`, `param`, `users`, `roles`, `result` và giới hạn bảo đảm audit.
- Cấu hình audit destination/filter trên **MongoDB Enterprise tự quản trị** theo môi trường phù hợp; hiểu các điều kiện của Atlas.
- Nêu rủi ro khi bật audit mọi truy vấn thành công, khi lọc audit quá hẹp, và khi bảo vệ log không đủ.
- Sử dụng `security.redactClientLogData` đúng phạm vi; triển khai **logging có chủ đích, masking, pseudonymization và access control**.
- Tách quyền backup cho **MongoDB database**, **Atlas control plane**, **object storage**, **KMS** và **restore target**.
- Thiết kế backup bảo mật với encryption, retention, immutable copies, PITR, RPO/RTO và restore drills.
- Xây audit/backup runbook, alert, threat scenarios và bài kiểm tra thực hành an toàn.

## 2. Những luồng dữ liệu cần xét

```text
                       Người dùng
                            |
                       HTTPS / API
                            |
                     +-------------+
                     | Java service|
                     +-------------+
                       |         |
               TLS/DB AuthN    App logs / Traces
                       |         |
                       v         v
              +----------------+   +------------------+
              | MongoDB cluster|   | Log pipeline/SIEM|
              +----------------+   +------------------+
                |         |               ^
                |         +-- Audit log --+
                |
            Backup / Snapshot
                |
                v
       +-----------------------+
       | Backup storage        |
       | encryption, IAM, WORM |
       +-----------------------+
                |
         Restore workflow
                |
                v
       Isolated target / Production

                 KMS / Secrets
                ↗        ↖
        app encryption   backup encryption
```

Đây là sơ đồ khái niệm. Với Atlas, nhà cung cấp quản lý các thành phần hệ thống nhất định; với self-managed, đội vận hành sở hữu nhiều phần hơn. Trong cả hai trường hợp, **quyền truy cập database không đồng nghĩa quyền truy cập Atlas project, backup bucket hoặc KMS**.

### 2.1. Ba thuộc tính bảo mật xuyên suốt

| Mục tiêu | Audit | Log redaction | Backup controls |
|---|---|---|---|
| **Confidentiality** | Phát hiện truy cập lạ | Giảm PII/secret trong log | Hạn chế xem/xuất snapshot |
| **Integrity** | Ghi bằng chứng thay đổi | Giảm nguy cơ sửa log khi phân quyền tốt | Bảo vệ snapshot khỏi sửa/xóa |
| **Availability** | Phát hiện dấu hiệu sự cố | Giảm rủi ro rò rỉ gây gián đoạn ứng phó | Phục hồi theo RPO/RTO |

Một backup chỉ có ý nghĩa khi **đọc được đúng dữ liệu tại thời điểm mong muốn và người được phép có thể khôi phục nó**. Một audit event chỉ có giá trị điều tra khi log chưa bị sửa, có timestamp/identity và phạm vi ghi nhận đủ rõ.

## 3. Phân biệt năm nguồn thông tin “log”

### 3.1. MongoDB diagnostic/server log

Ghi tình trạng tiến trình, kết nối, lỗi, cảnh báo, thao tác chậm và hoạt động vận hành. Nó phục vụ **chẩn đoán và quan sát**, không mặc nhiên bảo đảm lưu đủ mọi hành động của user cho compliance.

Ví dụ:

```text
Connection accepted
Slow query
Replication lag warning
Index build progress
Authentication failure message
```

### 3.2. MongoDB database audit

Audit subsystem dành cho **sự kiện hệ thống, xác thực, phân quyền và các hành động được cấu hình audit**. Nó có cấu trúc event, filter và những tính chất ghi log riêng.

Ví dụ:

```text
authenticate
authCheck
createUser
grantRolesToUser
dropCollection
```

**Không suy từ “diagnostic log có dòng kết nối” rằng database auditing đã được bật.**

### 3.3. Atlas Activity Feed / control-plane events

Ghi hoạt động ở mặt phẳng quản trị Atlas như thay đổi project/cluster/backup policy theo khả năng sản phẩm. Đây không phải là mọi truy vấn CRUD chạy trong database.

Một sự kiện “user thay đổi IP access list” thuộc control plane; một sự kiện “service chạy `find`” thuộc database plane.

### 3.4. Application audit và application log

API có thể cần ghi:

```text
actorId=staff-17
action=APPROVE_REFUND
resourceRef=refund-938
result=APPROVED
requestId=...
```

MongoDB database audit **không tự biết** vì sao một thay đổi có nghĩa “hoàn tiền đã được phê duyệt”. Business-level audit cần application event có danh tính và ngữ nghĩa nghiệp vụ.

### 3.5. Backup/storage/KMS access logs

Ghi ai liệt kê, tải xuống, export, restore, thay đổi retention, truy cập object storage hoặc sử dụng khóa giải mã.

Đây là những nguồn đặc biệt quan trọng khi database hoạt động bình thường nhưng bản copy bị lấy trộm qua backup.

### 3.6. Bảng phân biệt

| Nguồn | Đích kiểm soát | Không nên kỳ vọng |
|---|---|---|
| Diagnostic log | Vận hành, lỗi, slow operations | Nhật ký đầy đủ mọi CRUD thành công |
| Database audit | Sự kiện quyền truy cập và quản trị được chọn | Business meaning của giao dịch |
| Atlas control-plane log | Thay đổi quản trị Atlas | Mọi lệnh của driver |
| Application audit | Actor/action/decision nghiệp vụ | Bằng chứng đầy đủ về host MongoDB |
| Backup access log | Đọc/xuất/xóa/khôi phục bản sao | Chi tiết mọi lần sửa document ở nguồn |

## 4. MongoDB database auditing: edition và deployment

### 4.1. Self-managed MongoDB Enterprise

MongoDB Enterprise cung cấp cơ chế database auditing tích hợp. Có thể cấu hình cho `mongod` và `mongos` với các đích như file JSON/BSON, console hoặc syslog (syslog không hỗ trợ trên Windows).

Một giải pháp hoàn chỉnh cần xét **toàn bộ node và router liên quan**, không chỉ primary.

### 4.2. MongoDB Community

Không được tự suy rằng Community có đầy đủ **Enterprise audit subsystem** và các tham số `auditLog.*`. Với Community, ứng dụng vẫn có diagnostic logging, application audit, OS/network/storage logs và các giải pháp giám sát, nhưng **không gọi chúng là thay thế tương đương cho native database auditing**.

Nếu yêu cầu compliance bắt buộc một loại audit event cụ thể, phải chọn edition/deployment và kiến trúc đủ khả năng.

### 4.3. MongoDB Atlas

Theo tài liệu MongoDB Atlas, database auditing có trên **dedicated clusters M10+** và không hỗ trợ trên Free/Flex. Thiết lập qua Atlas UI/API/CLI theo quyền project; có audit filter builder hoặc JSON filter tùy cấu hình.

Phân biệt:

- **Atlas project/organization activity:** thay đổi control-plane.
- **MongoDB database audit:** sự kiện audit của quá trình truy cập database.
- **Application logs:** do ứng dụng riêng phát.

Không nhầm một vai trò như `Project Backup Manager` với database role `backup`.

## 5. Audit event có những trường gì?

Một audit event tiêu biểu có các thành phần, tên/chi tiết tùy sự kiện và version:

| Trường | Ý nghĩa |
|---|---|
| `atype` | Loại hành động: `authenticate`, `authCheck`, `createUser`... |
| `ts` | Thời gian ghi nhận event |
| `local` | Endpoint cục bộ có liên quan |
| `remote` | Endpoint phía client có liên quan |
| `users` | Những user identity được ghi nhận |
| `roles` | Các roles liên quan |
| `param` | Tham số đặc thù của event |
| `result` | Kết quả mã hóa theo event (ví dụ `0` thường là thành công) |

Một ví dụ **minh họa đã đơn giản hóa và không phải event thật để copy làm kiểm thử**:

```json
{
  "atype": "authenticate",
  "ts": { "$date": "2026-11-14T03:20:00Z" },
  "remote": { "ip": "10.10.1.22", "port": 49210 },
  "users": [{ "user": "orders_reader", "db": "admin" }],
  "param": {
    "user": "orders_reader",
    "db": "admin",
    "mechanism": "SCRAM-SHA-256"
  },
  "result": 0
}
```

Không cố định mọi field của mọi `atype` theo ví dụ. Một event liên quan DDL hay quyền sẽ có `param` khác; một số địa chỉ/username có thể không được trình bày giống nhau ở mọi trường hợp.

### 5.1. `result` không phải HTTP status

`result: 0` thường là thành công ở nhiều sự kiện; mã khác có thể đại diện lỗi. Không xây quy tắc “mọi result khác 200 là thất bại” như khi xử lý HTTP.

### 5.2. `users` và application identity

Nếu toàn bộ microservice cùng dùng một user database:

```text
database user = shared_app
```

audit khó phân biệt yêu cầu từ OrderService, BillingService hay InventoryService. Nên dùng **service identity tách biệt** khi phù hợp, cùng application request/correlation ID để nối các nguồn.

### 5.3. Thông tin trong `param` có thể nhạy cảm

Audit event có thể mang namespace, query arguments hoặc metadata khác tùy event/filter/cấu hình. Không giả định audit logs **không thể** chứa PII chỉ vì chúng là log bảo mật. **Giới hạn truy cập, retention và chính sách redaction** vẫn cần thiết cho audit.

## 6. Những hành động nên đưa vào phạm vi audit

### 6.1. Xác thực và cấp quyền

- Authentication successes/failures theo chính sách.
- Authorization failures (`authCheck`).
- Tạo/xóa user.
- Cấp/thu hồi role.
- Thay đổi role hoặc cấu hình xác thực.

Mục tiêu: phát hiện credential abuse, role escalation và quyền mới xuất hiện bất thường.

### 6.2. Hành động quản trị dữ liệu

- Drop database/collection.
- Rename collection hoặc thay đổi cấu trúc quan trọng.
- Thay đổi quyền/role liên quan hệ thống.
- Thao tác quản trị mà tổ chức coi là rủi ro cao.

Cần đối chiếu tên `atype` được hỗ trợ theo MongoDB version, không tự đặt tên event tùy ý rồi kỳ vọng filter sẽ match.

### 6.3. Truy cập dữ liệu nhạy cảm

Một số yêu cầu compliance muốn ghi các lệnh đọc/ghi thành công đối với namespace có PII. Điều này cần cân bằng **chi phí, lượng log, tính riêng tư và giới hạn audit**.

Điểm cốt lõi:

> **Mặc định, audit `authCheck` thường chỉ ghi authorization failures. Muốn audit cả authorization successes cho CRUD, phải cấu hình `auditAuthorizationSuccess` phù hợp và đánh giá hiệu năng.**

Không khẳng định “đã bật audit” đồng nghĩa mọi `find`/`update` thành công đã có log.

## 7. `authCheck` và `auditAuthorizationSuccess`

### 7.1. Authorization attempt khác authentication

- `authenticate`: danh tính đăng nhập/được xác thực.
- `authCheck`: server kiểm tra quyền cho một thao tác cụ thể.

Một user có thể đăng nhập thành công nhưng bị từ chối quyền thực hiện `dropCollection` hoặc đọc một namespace khác.

### 7.2. Mặc định `authCheck` ưu tiên thất bại

Khi `auditAuthorizationSuccess` không bật, việc filter vào `authCheck` không mặc nhiên tạo audit event cho **mọi thao tác đọc/ghi thành công**.

Ví dụ:

```text
Service đăng nhập thành công         -> authenticate
Service đọc collection được phép    -> không mặc định audit mọi read success
Service đọc namespace không có quyền -> authCheck failure có thể được audit
```

### 7.3. Bật audit successes phải cân nhắc

Mỗi document đọc/ghi ở workload nhiều request có thể tạo tải audit đáng kể. Theo tài liệu MongoDB, ghi authorization successes có thể **ảnh hưởng nghiêm trọng đến hiệu năng** của cluster.

Trước khi áp dụng rộng:

1. Xác định namespace và hành động thực sự phải audit.
2. Kiểm tra filter và tính năng theo phiên bản.
3. Đo throughput, p95 latency, log volume, disk/network.
4. Dự trù storage/SIEM ingestion/retention.
5. Thiết kế xử lý khi audit sink đầy/hỏng.

Audit logging không miễn phí, và “ghi tất cả rồi tính sau” không phải chính sách tốt cho mọi môi trường.

## 8. Lọc audit: ghi đủ để điều tra, không tạo bão log

### 8.1. Ví dụ chính sách

Một tổ chức muốn ưu tiên:

- Authentication events.
- Những thao tác user/role administration.
- Drop collection/database.
- Authorization failures.

Đây là một **policy định hướng**, cần ánh xạ chính xác sang danh sách `atype` hiện có trên version triển khai.

### 8.2. Một filter minh họa

```javascript
{
  atype: {
    $in: [
      "authenticate",
      "authCheck",
      "createUser",
      "dropUser",
      "grantRolesToUser",
      "revokeRolesFromUser",
      "dropCollection",
      "dropDatabase"
    ]
  }
}
```

**Không dùng filter này để tuyên bố coverage 100%.** Những loại hành động khác như updateRole, rename, thay đổi cấu hình hoặc sự kiện platform có thể nằm ngoài danh sách. Cần xác định event catalog và yêu cầu compliance cụ thể.

### 8.3. Filter quá rộng và quá hẹp

| Chính sách | Ưu điểm | Rủi ro |
|---|---|---|
| Audit mọi event | Coverage rộng | Tốn tài nguyên, chứa nhiều dữ liệu nhạy cảm |
| Chỉ audit login failure | Dễ triển khai | Không có dấu vết privilege escalation/DDL |
| Audit admin + auth failures | Giá trị điều tra khá cao | Có thể bỏ đọc dữ liệu thành công |
| Audit selected sensitive namespace | Gắn rủi ro cụ thể | Dễ sót đường truy cập/namespace mới |
| Audit thành công với filter phù hợp | Cải thiện forensic coverage | Cần thử nghiệm tải/retention |

### 8.4. Không lọc theo username rồi quên tên user mới

Nếu chỉ audit:

```text
users.user = "admin_a"
```

thì hành động của admin mới hoặc credential bị tạo trái phép có thể bị loại khỏi log.

Chính sách thường cần **event categories độc lập với identity hiện tại**, sau đó bổ sung filter user/namespace khi có cơ sở.

## 9. Cấu hình audit trên MongoDB Enterprise self-managed

Ví dụ cấu hình **minh họa**:

```yaml
# mongod.conf (Enterprise, điều chỉnh cho deployment cụ thể)
security:
  authorization: enabled
  redactClientLogData: true

auditLog:
  destination: file
  format: JSON
  path: /var/log/mongodb/audit.json
  filter: '{"atype":{"$in":["authenticate","authCheck","createUser","dropUser","grantRolesToUser","revokeRolesFromUser","dropCollection","dropDatabase"]}}'
```

**Điều kiện:**

- Sử dụng edition/phiên bản hỗ trợ audit.
- Đường dẫn audit tồn tại, account chạy `mongod` có quyền ghi tối thiểu.
- Quyền file, rotation, monitoring disk và log shipping đã thiết kế.
- RBAC/cluster internal authentication/TLS thiết lập riêng.
- Nếu là replica set/sharded cluster, lên kế hoạch cấu hình toàn bộ `mongod` và `mongos` theo chính sách.
- Việc thay đổi cấu hình có thể yêu cầu restart/rolling update; phải xem impact và maintenance window.

### 9.1. JSON so với BSON

Audit output dạng file hỗ trợ **JSON** và **BSON**. JSON dễ đọc bằng pipeline text; BSON thường giảm một số chi phí ghi log so với JSON.

Đừng nhầm:

```text
format: BSON
```

với **mã hóa**: BSON là định dạng biểu diễn nhị phân, không phải encryption.

### 9.2. Console và syslog

Audit destination có thể là:

- `file`: JSON/BSON.
- `console`: ghi stdout.
- `syslog`: gửi syslog, không khả dụng trên Windows.

Việc chọn destination ảnh hưởng độ bền, quyền, rotation, pipeline SIEM và rủi ro lộ dữ liệu. In audit stdout trong container có thể khiến logs đi vào log collector chung của platform; cần rà soát quyền và retention ở nơi thu thập.

### 9.3. Audit configuration động

Các phiên bản MongoDB hỗ trợ cấu hình audit ở runtime trong những điều kiện cụ thể, ví dụ distributed audit configuration với `auditLog.runtimeConfiguration` và lệnh tương ứng.

Không trộn tùy tiện:

```text
auditLog.runtimeConfiguration = true
auditLog.filter = ...
auditAuthorizationSuccess = ...
```

ở startup khi tài liệu phiên bản quy định chúng xung đột. Hãy chọn **startup configuration** hoặc **runtime/distributed configuration** nhất quán.

Trong production, thay đổi filter cần **change record, review, thử trên staging và xác nhận coverage sau triển khai**.

## 10. Audit trên MongoDB Atlas

### 10.1. Hai nhóm sự kiện

**Database auditing:** audit hoạt động database theo filter/role/identity trên cluster hỗ trợ.

**Project/organization activity:** thao tác quản trị Atlas, như thay đổi cấu hình và quyền control plane.

Một sự kiện export snapshot có thể liên quan Atlas control plane và cloud storage access; đừng chỉ xem database audit khi điều tra exfiltration qua backup.

### 10.2. Điều kiện truy cập

Theo tài liệu Atlas, cấu hình database auditing yêu cầu quyền **Project Owner** hoặc **Organization Owner** theo phạm vi thích hợp; sản phẩm có chính sách role cụ thể.

Quyền bật/tắt audit, quyền đọc audit log, quyền cấp database user và quyền quản lý backup **không nên được cấp đại trà cho cùng một identity**.

### 10.3. Lựa chọn audit filter

Atlas cung cấp cấu hình theo loại action, user/role và custom JSON filter. Khi dùng custom filter:

- Định nghĩa đúng event type và command/namespace.
- Ghi rõ mặc định của authorization successes.
- Test event có được tạo khi thao tác thành công/thất bại.
- Theo dõi tác động của audit trên workload và chi phí lưu trữ.

### 10.4. Không giả định mọi gói Atlas đều giống nhau

Free/Flex không cung cấp database auditing như dedicated M10+. Backup options, log download, retention và bộ quyền còn phụ thuộc loại deployment/tính năng tại thời điểm sử dụng.

## 11. Bảo đảm của hệ thống audit và giới hạn

MongoDB Enterprise audit subsystem có những **bảo đảm thứ tự và ghi** liên quan đến từng connection và các thao tác ảnh hưởng trạng thái bền vững.

Tuy nhiên, không nên diễn giải thành “audit luôn không thể mất event”:

- Audit events có thể được buffer trong bộ nhớ và flush xuống đĩa.
- Khi server kết thúc trước một số lần flush, những event chưa bền vững có thể mất.
- MongoDB có quy tắc ghi audit trước journal đối với một số thao tác ảnh hưởng trạng thái bền vững.
- Nếu server không thể ghi tới audit destination, **server có thể chấm dứt** để bảo vệ tính chất audit.

### 11.1. Hệ quả với availability

Một ổ đĩa audit đầy không chỉ làm mất log; nó có thể ảnh hưởng **tính sẵn sàng của MongoDB**. Do đó:

```text
Audit policy
  -> disk capacity
  -> log rotation
  -> off-host shipping
  -> alerts
  -> runbook khi sink lỗi
```

là một phần bắt buộc của thiết kế.

### 11.2. Không dùng audit như business event store

Audit events có thể xuất hiện cả cho thao tác thuộc transaction **bị abort**; không mặc định một audit CRUD event chứng minh **business transaction đã commit**.

Nếu nghiệp vụ cần lịch sử đơn hàng thay đổi trạng thái có thể phát lại, cần **application audit/outbox/ledger** theo cơ chế giao dịch phù hợp, không chỉ dùng database audit.

## 12. Chống chỉnh sửa và mất audit logs

### 12.1. Những mối đe dọa

1. Admin trên DB host xóa file audit local.
2. Log agent mất kết nối, queue đầy hoặc gửi lặp.
3. Audit log bị chỉnh sửa trước khi vào SIEM.
4. Retention quá ngắn so với thời điểm phát hiện sự cố.
5. Người có quyền xem log lấy được PII/credential.

### 12.2. Thiết kế đề xuất

```text
mongod/mongos
   |
   v
Local audit file (OS permissions)
   |
   v
Agent/collector (mTLS, bounded spool)
   |
   v
Central audit storage / SIEM
   |
   +-- Retention + immutable/tamper-evident copy
   +-- Role-based access
   +-- Encryption/KMS
   +-- Alerting, parsing, search
```

### 12.3. Điều kiện để log có giá trị pháp chứng

- Timestamp được đồng bộ và có timezone rõ.
- Có định danh node/router và môi trường.
- Có nguồn event/`atype`/actor/namespace/result.
- Có dấu thời điểm nhận từ collector và correlation ID khi có thể.
- Log đã xuất khỏi host bị xâm nhập trong thời gian phù hợp.
- Có checksum/signature/immutable storage nếu yêu cầu.
- Chỉ người được ủy quyền có thể điều chỉnh retention.
- Có test chứng minh log shipping và alert vận hành.

**Đừng hứa audit log có tính bất biến chỉ vì nó nằm trong một file JSON.**

## 13. Diagnostic log có thể chứa dữ liệu nhạy cảm nào?

Từ chính MongoDB server, driver hoặc ứng dụng, log có thể vô tình mang:

- Document/filter arguments có email, số điện thoại, số định danh.
- Connection string chứa username/password.
- Query literal values trong slow operation messages.
- Exception có namespace, statement hoặc dữ liệu lỗi.
- Header auth token khi logger ghi HTTP request.
- MongoDB command payload do `CommandListener` của driver cung cấp.
- Aggregation pipeline chứa dữ liệu nội bộ.
- Username, host, IP, tenant ID, trace context.

Ngay cả thông tin **không phải plaintext password** vẫn có thể nhạy cảm. Một tenant ID hoặc collection name có thể tiết lộ hệ thống khách hàng đang dùng.

### 13.1. Hệ quả từ dữ liệu sao chép vào log

Một field PII ban đầu có retention 30 ngày trong MongoDB có thể xuất hiện trong log được giữ **365 ngày** ở một hệ thống khác.

```text
MongoDB source retention: 30 ngày
          |
          v
Diagnostic log chứa PII
          |
          v
Central logging retention: 365 ngày
```

Khi đó chính sách xóa dữ liệu nguồn **không đảm bảo** dữ liệu đã được xóa khỏi log/backup. Cần data classification và retention xuyên các hệ thống.

## 14. `security.redactClientLogData`: che nội dung trong diagnostic log

### 14.1. Tác dụng

MongoDB Enterprise có tùy chọn:

```yaml
security:
  redactClientLogData: true
```

Đây là tính năng **Enterprise log redaction**; tài liệu MongoDB cũng mô tả khả năng tương ứng ở Atlas. Khi bật, MongoDB che **message content** có thể chứa thông tin nhạy cảm ở diagnostic/server logs và giữ một số metadata như mã lỗi, source file, line.

### 14.2. Không phải “xóa mọi field nhạy cảm ở mọi nơi”

**Phạm vi đặc biệt quan trọng:**

- Nó không thay thế việc **redact ở application logs**.
- Nó không tự kiểm soát quyền xem **audit files** hoặc backup.
- Nó không bảo đảm mọi event của **mọi collector, driver và SIEM** đã được xử lý.
- Nó có thể giảm chi tiết phục vụ debugging.
- Nó không thay TLS/encryption at rest/RBAC.

Trước khi bật, phải biết những log nào sẽ còn, những trường nào bị che và cách troubleshooting trong điều kiện đã redact.

### 14.3. Kích hoạt lúc startup hoặc runtime

Ví dụ cấu hình startup:

```yaml
security:
  authorization: enabled
  redactClientLogData: true
```

Với Enterprise và quyền thích hợp, tài liệu MongoDB còn mô tả thay đổi thông qua parameter ở runtime:

```javascript
db.adminCommand({
  setParameter: 1,
  redactClientLogData: true
});
```

**Chỉ chạy khi đã xác nhận edition/version và trên môi trường được phép.** Thay đổi runtime có thể cần quy trình lưu cấu hình bền vững và áp dụng nhất quán cho các node để tránh trở lại thiết lập cũ khi restart.

### 14.4. Trade-off điều tra

```text
Redaction OFF:
  + Dễ xem literal query khi debug
  - Rủi ro PII trong slow query/error log

Redaction ON:
  + Giảm PII trong message
  - Mất một phần chi tiết troubleshooting
```

Giải pháp không phải tắt redaction mỗi khi gặp bug production. Nên bổ sung **structured metadata an toàn**, request IDs, query shape, metrics, reproducer giả lập và quy trình break-glass có kiểm soát.

## 15. Log redaction và audit filter giải quyết hai việc khác nhau

| Kiểm soát | Tác động chính | Không đảm bảo |
|---|---|---|
| `auditLog.filter` | Chọn loại **audit event** nào được ghi | Loại bỏ PII khỏi mọi event đã chọn |
| `auditAuthorizationSuccess` | Có ghi authorization success cho `authCheck` không | Tối ưu hiệu năng tự động |
| `redactClientLogData` | Che nội dung message ở **diagnostic log** | Che application/backup/all audit logs |
| Application redaction | Giảm PII/secret ở service logs | Che dữ liệu người có DB role đọc |
| SIEM ingest filtering | Mask/drop một số field lúc nhận | Bảo vệ dữ liệu đã lưu ở upstream |
| KMS/encryption | Bảo vệ log/backup khi lưu | Thay quyền truy cập hoặc retention |

Một sai lầm nghiêm trọng là bật `redactClientLogData` rồi ghi trong tài liệu compliance: “Mọi audit, driver log, application log và snapshot đều đã được che”. **Kết luận đó không có cơ sở.**

## 16. Thiết kế logging theo phân loại dữ liệu

### 16.1. Phân loại

Một mô hình tối thiểu:

| Mức | Ví dụ | Cách xử lý log |
|---|---|---|
| Public | Operation name chung | Có thể log theo policy |
| Internal | Service name, namespace, correlation ID | Cấp quyền phù hợp |
| Confidential | User email, order details, tenant business ID | Tránh log raw; mask/tokenize |
| Restricted | Password, API key, access token, private key, card data | **Không log** |

Phân loại theo **ngữ cảnh**: địa chỉ IP, tenant ID, query pattern cũng có thể là confidential trong một hệ thống.

### 16.2. Allowlist logging tốt hơn blacklist

Không nên log nguyên request rồi “xóa những field đã biết nhạy cảm”:

```javascript
logger.info("request={}", req.body);
```

Một field mới `personalId` xuất hiện ngày mai có thể lọt qua blacklist.

Nên xây sự kiện riêng:

```text
event=ORDER_UPDATE_ATTEMPT
requestId=...
actorRef=...
resourceRef=...
operation=updateStatus
durationMs=...
outcome=DENIED
```

### 16.3. Giá trị dữ liệu và metadata

Ví dụ query:

```javascript
db.customers.find({
  email: "customer@example.test"
});
```

Trong observability thông thường chỉ cần:

```text
operation=find
collection=customers
queryShape=email_eq
durationMs=8
resultCount=1
```

Không nhất thiết ghi email literal. Khi điều tra sâu, dùng quy trình được duyệt trên môi trường/bản dữ liệu đã xử lý an toàn.

## 17. Masking, tokenization và HMAC pseudonymization

### 17.1. Masking

Ví dụ:

```text
email gốc: alice@example.test
log:       a***@example.test

phone gốc: +84xxxxxxxxx
log:       +84******123
```

Masking phù hợp khi vẫn cần nhận biết một phần để hỗ trợ người dùng, nhưng **không tự bảo đảm không tái định danh**.

### 17.2. Tokenization

Thay giá trị thật bằng định danh thay thế được tạo/quản lý an toàn:

```text
customerId = C-123456
log token  = tok_7e4a...
```

Service log không cần giữ mapping token → dữ liệu thật. Nếu mapping tồn tại, quyền truy cập vào mapping đó cần được bảo vệ riêng.

### 17.3. HMAC thay vì hash thuần

Nếu muốn liên kết cùng user qua nhiều logs mà không ghi PII:

```text
fingerprint = HMAC_SHA256(secret, normalizedIdentifier)
```

HMAC với secret đủ mạnh thường tốt hơn:

```text
SHA256(email)
```

vì email/phone có không gian đầu vào dễ đoán; attacker có thể dictionary-attack hash thuần. Tuy nhiên **HMAC fingerprint vẫn có thể là dữ liệu cá nhân/pseudonymous**, cần retention và access controls.

### 17.4. Không gắn ngẫu nhiên để rồi mất điều tra

Nếu mỗi request dùng random token mới không có correlation ID, rất khó nối các event của cùng actor. Cân bằng:

- Logging tối thiểu.
- Stable correlation theo nhu cầu điều tra.
- Không để pseudonym trở thành tracking identifier vượt mục đích.
- Tách quyền truy cập salt/secret/mapping.

## 18. Java: logging an toàn cùng MongoDB driver

### 18.1. Event ứng dụng có chủ đích

Ví dụ với SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderAuditLogger {
    private static final Logger log =
        LoggerFactory.getLogger(OrderAuditLogger.class);

    public void orderViewed(
        String requestId,
        String actorReference,
        String orderReference,
        long durationMs,
        boolean allowed
    ) {
        // Các reference đã là mã không chứa PII trực tiếp,
        // hoặc đã pseudonymize theo chính sách tổ chức.
        log.info(
            "event=ORDER_VIEW requestId={} actorRef={} orderRef={} " +
            "durationMs={} result={}",
            requestId,
            actorReference,
            orderReference,
            durationMs,
            allowed ? "ALLOWED" : "DENIED"
        );
    }
}
```

**Không truyền password, JWT, raw document hoặc email trực tiếp vào các argument trên.** Một tên biến `actorReference` không tự che PII; giá trị phải được xác định/validate theo contract logging.

### 18.2. Không log nguyên MongoDB URI

```java
// Không nên:
log.info("Mongo URI = {}", mongoUriWithPassword);

// Nên:
log.info("MongoDB connection initialized; service={}", serviceName);
```

Exception có thể chứa nhiều ngữ cảnh, vì vậy production logger cần cơ chế xử lý exception/stack trace không làm rò raw query/connection string.

### 18.3. `CommandListener` rất nhạy cảm

Driver MongoDB hỗ trợ command monitoring. Nếu bật rồi ghi:

```java
// Chống chỉ định với production không có redaction:
log.debug("Mongo command: {}", event.getCommand());
```

thì command BSON có thể chứa query literals, dữ liệu update và các metadata không phù hợp xuất log.

Đối với metrics, thường chỉ cần:

```text
commandName=find
database=shop
requestId=...
durationMs=...
success=true
```

Hãy dùng những API metadata an toàn theo version driver, tránh serializing toàn command object. Không giả định mọi driver đều tự redact command do ứng dụng chủ động log.

### 18.4. Correlation ID

Một HTTP request có thể đi qua:

```text
API Gateway -> OrderService -> MongoDB -> Event publisher
       requestId = R-abc123
```

Nếu mỗi component ghi cùng request ID, SIEM có thể liên hệ các sự kiện mà không cần nhét toàn bộ payload vào log.

**Cần tránh tin requestId do client tự cung cấp vô điều kiện**; gateway/backend nên chuẩn hóa, giới hạn và chống log injection khi nhận correlation data.

## 19. Log ingestion, SIEM và retention

### 19.1. Redact ở nguồn trước khi phát

Pipeline tối ưu về bảo mật:

```text
Sensitive operation
    |
    v
Create safe structured log at source
    |
    v
Collector with mTLS
    |
    v
SIEM with scoped access
    |
    v
Retention / archival / deletion
```

Nếu PII đã tới collector rồi mới redact, bản sao raw có thể còn trong buffer, crash dump hoặc pipeline phụ. Vì vậy **redact càng gần nguồn càng tốt**.

### 19.2. Quyền truy cập log

Đề xuất vai trò:

- Developer: xem metrics và sanitized app logs theo service.
- On-call SRE: xem operational logs, giới hạn secret.
- Security analyst: xem audit alerts và điều tra theo policy.
- Compliance: xem báo cáo/evidence đã lọc.
- Break-glass: quyền sâu theo phê duyệt, time-bound và được audit.

Không cho mọi developer quyền tải tất cả audit logs production chứa user identities và query details.

### 19.3. Retention đúng mục đích

Ví dụ định hướng:

```text
App debug logs:    retention theo nhu cầu vận hành ngắn hơn
Security audit:    retention theo pháp lý/compliance
Backup snapshots:  retention theo RPO/PITR/khôi phục
```

**Không áp một thời hạn mặc định cho mọi tổ chức.** Một retention quá dài tăng diện tích dữ liệu nhạy cảm; quá ngắn làm không đủ điều tra/khôi phục.

### 19.4. Log tamper-evidence

Biện pháp có thể gồm:

- Immutable object storage hoặc WORM.
- Hash chain/chữ ký theo batch.
- Ghi off-host nhanh.
- Hạn chế quyền delete/overwrite.
- Quản lý KMS keys độc lập.
- Theo dõi gaps và sequence ingestion.

Hash của một file trên **cùng host bị chiếm** không đủ chống sửa nếu attacker có thể thay cả file và hash.

## 20. Monitoring cho audit và redaction

| Tín hiệu | Vì sao quan trọng? |
|---|---|
| Audit event rate giảm đột ngột | Có thể filter sai, collector lỗi hoặc thiếu coverage |
| Authentication failures tăng | Brute force, credential lỗi hoặc deploy sai |
| Tạo user/role bất thường | Privilege escalation |
| Đổi audit config | Có thể giảm khả năng điều tra |
| Audit destination gần đầy | Nguy cơ gián đoạn server |
| Log shipping lag | Mất visibility gần thời gian thực |
| Parse error/unknown event types | Nâng version hoặc schema event thay đổi |
| DLP detector tìm thấy PII/secret trong log | Chính sách redaction bị vi phạm |
| Nhiều read/export operations bất thường | Có thể exfiltration |
| KMS access tăng | Rủi ro dùng key trái phép |

### 20.1. Đừng nhầm thiếu alert với không có sự cố

Nếu hệ thống không audit thành công CRUD, nó không thể phát hiện một số mẫu đọc dữ liệu **chỉ từ những audit event chưa được cấu hình ghi**. Cần phối hợp application audit, egress monitoring và hành vi service.

### 20.2. Kiểm tra hoạt động định kỳ

Một test hợp lệ trên lab có thể:

1. Đăng nhập bằng identity test.
2. Thực hiện một thao tác được phép.
3. Thử một thao tác không được phép trên namespace test.
4. Xác minh event được ghi theo audit policy.
5. Kiểm tra log tới SIEM đúng identity/timestamp.
6. Xác nhận không có password/PII test plaintext trong đường log được thiết kế redact.

Không thực hiện các thử nghiệm giả lập độc hại trên production mà không có phê duyệt/quy trình.

## 21. Backup cũng là dữ liệu production

Một snapshot có thể chứa:

- PII, transaction history và business data.
- Database user/role metadata trong trường hợp backup liên quan.
- Index definitions, schema, collection options.
- Encrypted fields/ciphertexts và key vault metadata tùy backup type.
- Thông tin topology/cluster metadata khi sao lưu đầy đủ.

Nếu snapshot bị tải về thiết bị không được kiểm soát, attacker có thể phân tích offline mà không cần đi qua MongoDB RBAC nữa.

### 21.1. Tác động của lộ backup

```text
MongoDB production:
  TLS = enabled
  RBAC = correct
  Network = private
  Audit = enabled

Nhưng:
  backup.zip được tải sang public storage
             |
             v
     attacker đọc offline
```

**Bảo vệ tốt database gốc chưa đủ nếu backup có quyền truy cập yếu hơn.**

### 21.2. CIA cho backup

| Thuộc tính | Yêu cầu |
|---|---|
| Confidentiality | Mã hóa, quản lý key, hạn chế export/download |
| Integrity | Checksums, immutable copies, chống sửa/xóa |
| Availability | Snapshot định kỳ, PITR, restore drill, multi-region khi cần |
| Accountability | Audit access, restore, export, delete và policy changes |

## 22. Các lớp quyền trong một hệ thống sao lưu

Một nhiệm vụ backup có ít nhất **năm mặt phẳng quyền**:

1. **Database RBAC:** identity dùng để đọc từ MongoDB.
2. **Backup orchestration:** được tạo/lập lịch snapshot không?
3. **Backup storage:** được list/get/put/delete object không?
4. **KMS:** được encrypt/decrypt/unwrap key không?
5. **Restore target:** được ghi dữ liệu và thay đổi target cluster không?

Chỉ kiểm tra DB username mà không kiểm tra các mặt phẳng còn lại là đánh giá chưa đủ.

### 22.1. Ví dụ về hai identity

```text
backup_reader_db:
  đọc dữ liệu nguồn để backup, không có quyền app writes.

backup_writer_storage:
  ghi object backup, không tự xóa retention-locked objects.

restore_operator:
  khôi phục vào target được phê duyệt.

backup_exporter:
  tải/export snapshots, quyền rủi ro cao cần phê duyệt riêng.
```

Nhiều công nghệ không thể phân quyền chính xác từng hành động trong mọi trường hợp; khi đó phải bù bằng **workflow approval, environment separation, time-bound privileges và logging**.

## 23. MongoDB self-managed: built-in `backup` và `restore` roles

Trong database `admin`, MongoDB có những built-in roles như:

- `backup`: các quyền cần cho công cụ sao lưu theo phạm vi role.
- `restore`: các quyền cần cho nhiều thao tác khôi phục theo khả năng được cấp.

Đây là **database roles**, không phải Atlas project roles.

### 23.1. Tạo backup identity dành riêng cho lab

Trong môi trường **được bạn quản trị**, sau khi có user admin và cơ chế xác thực:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "backup_lab_337",
  pwd: passwordPrompt(),
  roles: [
    { role: "backup", db: "admin" }
  ]
});
```

`passwordPrompt()` tránh gõ password literal vào source/script. Role `backup` cho phép đọc dữ liệu cần cho backup: **nó là quyền tiếp cận khối dữ liệu rất lớn** và phải được cấp/giám sát cẩn trọng.

### 23.2. Không cấp `root` chỉ để chạy `mongodump`

Một cron job backup không cần quyền user administration, sharding administration hay sửa bất kỳ document nghiệp vụ nào chỉ để đọc snapshot.

Đừng dùng:

```text
application_root_user -> mongodump
```

để “tiện”; nếu job/secret lộ, quyền quá rộng.

### 23.3. Restore thường cần quyền khác backup

Quyền đọc nguồn không đồng nghĩa quyền ghi đè target. Với một số phương thức `mongorestore` đặc biệt như `--oplogReplay`, tài liệu MongoDB có yêu cầu quyền rộng hơn built-in `restore` thông thường.

Vì vậy:

- Tách identity backup và restore.
- Chỉ cấp quyền restore khi có change/incident được phê duyệt.
- Phân biệt restore toàn instance, database, collection và oplog replay.
- Test role trên staging trước.

Không mặc định “cứ có `restore` built-in role là mọi kiểu restore đều được”.

## 24. Thực hành backup bằng `mongodump`: đọc, không ghi

### 24.1. Lệnh minh họa trên replica set lab

Trên máy thực thi được bảo vệ, có MongoDB Database Tools và user backup:

```bash
# Ví dụ trên replica set lab có TLS và account backup.
# Lệnh không chạy trong mongosh.
mongodump \
  --uri="mongodb://db1.internal.example:27017/?replicaSet=rsLab&tls=true" \
  --tlsCAFile="/secure/path/ca.pem" \
  --username="backup_lab_337" \
  --authenticationDatabase="admin" \
  --archive="/secure/backups/rsLab-20261114.archive.gz" \
  --gzip \
  --oplog
```

Lệnh minh họa **không nhúng mật khẩu**; công cụ/phương pháp xác thực phải được cấu hình để nhận password/identity an toàn theo môi trường. Các hostname/đường dẫn là placeholder. `--oplog` dùng cho **full replica set dump** trong phạm vi được hỗ trợ, không phải một lựa chọn áp dụng tùy ý cho mọi topology.

**Quan trọng:** `--gzip` chỉ nén, **không mã hóa** backup.

### 24.2. Giới hạn `--oplog`

Tài liệu MongoDB Database Tools nêu:

- `mongodump --oplog` có thể thu thập thay đổi trong khi dump từ replica set để phục hồi nhất quán.
- Không dùng `--oplog` cho một dump chỉ chọn `--db`/`--collection`.
- Không coi `--oplog` là một chức năng hoạt động cho **toàn bộ sharded cluster qua `mongos`**.
- Một số DDL/user/role changes trong lúc dump có thể khiến dump thất bại.
- `mongodump` là logical backup và có tác động lên I/O/cache; cluster lớn có thể cần giải pháp snapshot/backup được thiết kế riêng.

### 24.3. Kiểm tra an toàn

Không nên:

```text
Backup tạo xong -> upload trực tiếp public bucket -> xóa bản local
```

Nên:

```text
AuthN + TLS -> Backup -> Encrypt -> Restricted storage
                                 -> Checksum/catalog
                                 -> Retention/immutability
                                 -> Restore drill
```

### 24.4. Restore chỉ trên target cách ly khi thực hành

Ví dụ minh họa:

```bash
# CHỈ khôi phục lên MongoDB lab riêng, không trỏ production.
mongorestore \
  --uri="mongodb://restore-lab.internal.example:27017/?tls=true" \
  --tlsCAFile="/secure/path/ca.pem" \
  --archive="/secure/backups/rsLab-20261114.archive.gz" \
  --gzip
```

Trong môi trường thật, restore cần identity/phân quyền riêng, xác minh nội dung archive và có thể cần tùy chọn khôi phục metadata/oplog. Lệnh trên **không** tự là lời hứa rằng backup với oplog đã được replay hoặc cluster đã trở lại một snapshot nhất quán.

**Không dùng `--drop`, `--oplogReplay` hoặc nhắm target production khi chưa có kế hoạch/phê duyệt rõ**; việc ghi đè sai có thể gây mất dữ liệu.

## 25. Atlas: quyền backup chi tiết

Atlas có một số **Project Roles** cho backup; tên role chính xác và capabilities cần đối chiếu tài liệu hiện hành.

| Atlas project role | Vai trò chính |
|---|---|
| **Project Read Only** | Xem một số metadata/project/backup policy theo phạm vi được cấp, không mặc định tạo/export/restore |
| **Project Backup Creator** | Liệt kê snapshots, tạo snapshot theo yêu cầu |
| **Project Backup Recovery Operator** | Liệt kê và khôi phục snapshot, **không** cấp quyền export/download |
| **Project Backup Export Operator** | Liệt kê và export/download snapshot |
| **Project Backup Manager** | Kế thừa quyền tạo, recovery, export; quản lý backup/policies theo phạm vi |
| **Project Owner** | Quyền rộng trên project, bao gồm nhiều hoạt động backup và quản trị |

Đây là **quyền Atlas control plane**, không phải MongoDB `readWrite`/`backup` role trong database.

### 25.1. Vì sao Export Operator là quyền nhạy cảm?

```text
Không có quyền find() trong database
              |
              v
Có quyền export/download backup snapshot
              |
              v
Có thể sở hữu bản sao dữ liệu để phân tích offline
```

**Không cấp Export Operator chỉ để người dùng kiểm tra “backup hôm nay đã chạy chưa”.** Nếu chỉ cần kiểm tra trạng thái, dùng quyền xem metadata thấp nhất đáp ứng công việc.

### 25.2. Recovery Operator khác Export Operator

- **Recovery Operator:** có thể khôi phục snapshots về target theo điều kiện sản phẩm, nhưng không được export/download chỉ vì có role này.
- **Export Operator:** tải/xuất snapshot, không mặc định có quyền restore.
- **Backup Manager:** quyền mạnh hơn vì bao gồm nhiều khả năng.

Tách các quyền làm giảm blast radius khi identity bị chiếm.

### 25.3. Project Owner cũng cần giới hạn

Một Project Owner có khả năng quản trị lớn hơn. Không dùng Owner cho automation chỉ để tạo snapshot theo lịch nếu có role chuyên biệt đủ dùng.

### 25.4. Cross-project/cross-organization restore

Khôi phục sang project/organization khác có yêu cầu quyền trên **cả source và destination** theo quy định Atlas. Đặc biệt các workflow có encryption at rest/KMS có thêm điều kiện key và target.

**Không giả định có quyền restore ở project đích là có thể tự lấy mọi snapshot ở project nguồn.**

## 26. Mô hình separation of duties cho backup

### 26.1. Ma trận trách nhiệm

| Hành động | Người/role đề xuất |
|---|---|
| Xem backup status | On-call/read-only monitoring |
| Tạo snapshot on-demand | Backup Creator/job chuyên biệt |
| Sửa retention/policy | Backup Manager qua change approval |
| Export/download snapshot | Export Operator qua phê duyệt rõ |
| Restore lên staging | Recovery Operator bị giới hạn target |
| Restore đè lên production | Workflow break-glass với hai bước phê duyệt |
| Xóa snapshot | Chính sách riêng; hạn chế mạnh/retention lock |
| Giải mã dữ liệu bằng KMS | Key-use principal độc lập, scoped |
| Quản lý KMS key policy | Security/KMS administrators |
| Xem audit của các hành động backup | Security/SOC, retention độc lập |

Đây là thiết kế tham khảo; Atlas roles không tự biểu đạt mọi workflow ở mức chính sách hai người. Các approval/just-in-time access có thể phải nằm ở **IAM/control plane/process**.

### 26.2. Chống quyền lạm dụng chéo

Không để một identity duy nhất có tất cả:

```text
DB root
AND Atlas Project Owner
AND Backup Export
AND Object Storage Delete
AND KMS Key Admin
AND Audit Log Delete
```

Nếu identity bị chiếm, attacker có thể vừa đọc/xóa dữ liệu, vừa xóa backup, vừa xóa dấu vết.

### 26.3. Break-glass access

Nếu buộc phải dùng quyền rộng:

- Giới hạn thời gian.
- Ghi lý do/ticket và người phê duyệt.
- MFA/conditional access ở identity provider nơi được hỗ trợ.
- Audit việc cấp quyền và hành động tiếp theo.
- Thu hồi/kiểm tra lại sau sự kiện.

## 27. Bảo vệ storage chứa backup

### 27.1. Object storage/IAM

Backup nằm trong S3/GCS/Azure Blob hoặc kho tương đương cần:

- Chỉ backup writer được ghi đúng prefix/bucket.
- Chỉ restore identity được đọc dữ liệu cần khôi phục.
- Không public anonymous read.
- Hạn chế liệt kê dữ liệu khi không cần.
- Ngăn/xem xét quyền delete/overwrite.
- Cloud audit logs cho GetObject/PutObject/DeleteObject.
- Network access restrictions/private endpoints phù hợp.

### 27.2. Encrypt at rest + encrypt in transit

Backup cần mã hóa khi lưu, TLS khi chuyển và key management rõ ràng.

```text
Dump/snapshot
  |
  +-- TLS on transfer
  |
  +-- KMS-managed encryption at rest
  |
  +-- IAM limits access to encrypted object
  |
  +-- KMS policy limits decrypt capability
```

Một user có quyền đọc object nhưng không thể giải mã là một lớp bảo vệ, nhưng cấu hình KMS cần bảo đảm service hợp lệ vẫn restore được khi xảy ra sự cố.

### 27.3. Multi-region/multi-account

Copy backup sang region/account tách biệt có thể giảm rủi ro thiên tai/ransomware trong một miền hỏng.

**Không sao lưu đa vùng chỉ bằng cách copy sang cùng account với cùng credentials có quyền delete mọi copy.** Trong trường hợp attacker chiếm tài khoản đó, blast radius vẫn còn.

### 27.4. Versioning và WORM

Object versioning và Write Once Read Many/retention lock giúp hạn chế việc một identity xóa/sửa bản backup trước thời gian giữ.

Nhưng cần hiểu:

- Versioning không tự cấm xóa mọi version bởi user đủ quyền.
- WORM/retention lock có điều kiện cấu hình cụ thể.
- Chính sách immutability có thể tăng chi phí/làm khó yêu cầu xóa hợp lệ.
- Quyền thay đổi retention hoặc khóa compliance có thể là điểm yếu quan trọng.

## 28. Atlas Backup Compliance Policy

MongoDB Atlas cung cấp **Backup Compliance Policy** cho những cluster/tier được hỗ trợ, nhằm bảo vệ yêu cầu retention/khôi phục nghiêm ngặt.

Theo tài liệu Atlas, khi chính sách này có hiệu lực, nó có thể ngăn:

- Xóa backup snapshot.
- Giảm thời gian retention dưới yêu cầu.
- Tắt Cloud Backup trái với chính sách.
- Điều chỉnh một số cấu hình PITR/continuous backup theo cách làm yếu mức bảo vệ.
- Xóa project khi còn snapshots theo điều kiện.

Tắt chính sách cần quy trình xác minh/hỗ trợ đặc biệt của MongoDB; **không phải một toggle mà Project Owner bất kỳ có thể tự tùy tiện tắt**.

### 28.1. Không bật compliance policy chỉ vì “nghe an toàn”

Trước khi bật phải tính:

- Yêu cầu pháp lý và retention.
- Chi phí lưu trữ không thể hạ tùy ý.
- Trường hợp cần xóa dữ liệu có căn cứ pháp lý.
- Cách yêu cầu thay đổi/giảm retention.
- Tác động tới project lifecycle.
- Quyền phê duyệt và người liên hệ hỗ trợ.

Với môi trường production, đây là quyết định **governance và compliance**, không phải lab toggle.

### 28.2. Không đồng nghĩa export hoàn toàn vô hại

Snapshot bất biến chống xóa/sửa nhưng **không tự ngăn user có quyền Export Operator tải bản sao về nơi khác**. Vẫn phải kiểm soát quyền export/download và log hoạt động này.

## 29. Backup retention, RPO, RTO và PITR

### 29.1. Retention

Ví dụ định hướng:

```text
Hourly snapshots: giữ 7 ngày
Daily snapshots:  giữ 30 ngày
Monthly snapshots: giữ 12 tháng
```

Thời hạn chỉ là minh họa. Cần đối chiếu:

- Rủi ro phát hiện sai dữ liệu trễ.
- Yêu cầu khôi phục point-in-time.
- Quyền riêng tư/data deletion.
- Chi phí và backup immutability.
- Bảo mật bản sao ở các region.

### 29.2. RPO và RTO

**RPO (Recovery Point Objective)** là độ mất dữ liệu tối đa chấp nhận được.

**RTO (Recovery Time Objective)** là thời gian phục hồi dịch vụ tối đa chấp nhận được.

Ví dụ:

```text
Business requirement:
  RPO <= 15 phút
  RTO <= 2 giờ
```

Một snapshot mỗi 24 giờ **không tự đáp ứng RPO 15 phút**. Cần cơ chế continuous backup/PITR hoặc chiến lược tương đương hỗ trợ điểm khôi phục cần thiết.

### 29.3. PITR không phải backup vĩnh viễn từng giây

Point-in-Time Restore chỉ hoạt động **trong restore window và điều kiện được hỗ trợ**. Không coi PITR là event store không giới hạn.

Một bản snapshot và một tập oplog dùng cho PITR có thể cần được giữ/khôi phục đồng bộ theo thiết kế hệ thống.

### 29.4. Độ đúng của snapshot sharded cluster

Một sharded cluster có nhiều replica sets và balancer. Sao lưu từng shard không được phối hợp đúng có thể tạo **bản backup không nhất quán toàn cluster**.

Với self-managed, cần phương pháp backup được MongoDB hỗ trợ và xem xét DDL, cross-shard transactions, balancer. Không sử dụng `mongodump --oplog` qua `mongos` rồi mặc định có consistent PITR cho toàn sharded cluster.

## 30. Restore không chỉ là tải file rồi chạy lệnh

### 30.1. Kiểm soát trước restore

1. Xác minh lý do và target environment.
2. Xác định snapshot/timepoint.
3. Xác minh backup integrity và key khả dụng.
4. Kiểm tra quyền người yêu cầu và phê duyệt.
5. Xác định tác động lên dữ liệu hiện có ở target.
6. Kiểm tra topology, MongoDB version, encryption mode.
7. Lập rollback/recovery plan nếu restore thất bại.
8. Chuẩn bị kiểm tra ứng dụng sau restore.

### 30.2. Atlas cluster-level restore có thể phá dữ liệu đích

Theo tài liệu Atlas, một cluster-level restore có thể **xóa dữ liệu hiện có trên target cluster trước khi khôi phục**. Vì vậy một operator có quyền restore là một identity nhạy cảm dù không có quyền export/download snapshot.

**Luôn xác minh source/target và ưu tiên phục hồi vào cluster mới/cách ly để kiểm tra khi use case cho phép.**

### 30.3. Restore drill trong môi trường cách ly

```text
Select snapshot
      |
      v
Restore to isolated cluster
      |
      v
Check key/cert/network access
      |
      v
Validate collections/indexes/counts
      |
      v
Run business invariants / app smoke tests
      |
      v
Record elapsed time vs RTO
      |
      v
Destroy/retain test target under approved policy
```

Một restore drill có thể tạo **bản sao PII** ở môi trường test. Không tự cho staging quyền truy cập/dữ liệu production đầy đủ khi không có chính sách bảo vệ và căn cứ.

### 30.4. Sự sẵn sàng của key

Với mã hóa do khách hàng quản lý và CSFLE/Queryable Encryption:

- Có thể cần master key/DEK/key vault và quyền giải mã.
- Key bị revoke/mất có thể khiến restore không dùng được.
- Restore document ciphertext không tự bảo đảm app có thể đọc plaintext.

Kiểm tra key lifecycle là **một phần của backup testing**, không phải việc tách rời chỉ thuộc security team.

## 31. Audit các hành động backup

Các sự kiện cần quan sát:

- Thay đổi backup policy, retention hoặc PITR window.
- Tạo snapshot on-demand.
- Tạo và hoàn thành export/download.
- Khởi tạo restore job, target và actor.
- Xóa snapshot hoặc thử xóa.
- Thay đổi IAM role liên quan backup.
- Thay đổi KMS grant/key policy.
- Object storage read/delete ở mức bất thường.
- Backup job failures và snapshot age vượt ngưỡng.

### 31.1. Nguồn log không nằm ở một chỗ

```text
Backup policy changed   -> Atlas Activity Feed/control plane
Snapshot exported       -> Atlas backup activity + storage logs
Object downloaded       -> Cloud object storage access logs
KMS Decrypt called      -> KMS audit logs
Restore writes database -> Restore job logs + database/application checks
```

Không dựa duy nhất vào MongoDB database `authCheck` để giám sát export snapshots.

### 31.2. Alert có ý nghĩa

| Tình huống | Cảnh báo gợi ý |
|---|---|
| Export snapshot ngoài change window | High-severity notification |
| Tăng số lượng download | Investigate potential exfiltration |
| Thay đổi retention giảm bất thường | Require approval/review |
| Restore nhắm production không có ticket | Block/escalate theo process |
| KMS Decrypt từ identity lạ | Security alert |
| Backup không có snapshot mới | Availability alert |
| Restore drill thất bại | RTO/recoverability risk |
| Audit collector gián đoạn | Detection coverage gap |

## 32. Kịch bản 1: credential backup bị lộ

### 32.1. Ngữ cảnh

Một secret trong CI chứa credential của `backup_lab_337` bị đưa vào log. User có role `backup` trong `admin`.

### 32.2. Rủi ro

Nếu attacker tiếp cận mạng và sử dụng credential, họ có thể đọc đủ dữ liệu phục vụ backup trong phạm vi role, dẫn tới exfiltration trên quy mô lớn dù app user thông thường không có quyền như vậy.

### 32.3. Các lớp bảo vệ

- Private network/mTLS hoặc TLS xác minh server.
- Role `backup` tách với `root`.
- Secret manager/rotation.
- Egress restriction.
- Audit authentication/access và anomaly detection.
- KMS encryption cho snapshot sau khi tạo.

### 32.4. Runbook

1. Xác minh secret thực sự bị lộ và phạm vi sử dụng.
2. Giới hạn network/access theo incident policy.
3. Tạo credential mới, chuyển backup job.
4. Revoke/rotate credential lộ.
5. Đối chiếu audit logs, source IP, dump/export jobs và egress.
6. Xác minh không có backup bị thay đổi/xóa.
7. Sửa nguồn lộ trong CI/repository/log.
8. Cập nhật secret scan và controls.

**Không chỉ xóa dòng log rồi kết luận credential vẫn an toàn.**

## 33. Kịch bản 2: log chứa PII

### 33.1. Ngữ cảnh

Java app có một `CommandListener` ghi toàn BSON command vào log. Query tìm customer chứa số điện thoại; log được gửi tới hệ thống quan sát mà mọi developer đều xem được.

### 33.2. Tác động

- PII có bản sao mới.
- Retention khác với collection nguồn.
- Nhiều người có quyền đọc hơn.
- Log có thể được xuất ra bên thứ ba.

### 33.3. Xử lý

1. Dừng/đổi logging raw command theo quy trình không phá phục vụ.
2. Bổ sung allowlist structured fields.
3. Kiểm tra MongoDB diagnostic redaction nếu tính năng hỗ trợ.
4. Đánh giá phạm vi log đã lưu/replicated.
5. Áp quy trình deletion/retention theo dữ liệu nhạy cảm.
6. Giới hạn quyền xem log và xem xét security notification/compliance.
7. Test regression để raw phone/email/password không còn được ghi.

### 33.4. Không dùng một regex làm toàn bộ chính sách

Redaction kiểu “thay mọi chuỗi có dấu `@` thành `***`” không bắt được số điện thoại, nested JSON, binary payload, token hoặc dữ liệu mới. Ưu tiên **không ghi raw data ngay từ đầu**.

## 34. Kịch bản 3: export snapshot trái phép

### 34.1. Ngữ cảnh

Một contractor chỉ được giao xem backup status nhưng được cấp Project Backup Manager, gồm cả quyền export/download. Họ xuất snapshot chứa dữ liệu khách hàng ra môi trường ngoài kiểm soát.

### 34.2. Phòng ngừa

- Cấp quyền read-only hoặc role thấp nhất đủ cho nhiệm vụ.
- Tách Backup Export Operator khỏi người chỉ quản lý lịch backup.
- Approval cho export/download.
- IAM/mTLS/conditional access và logging.
- Chính sách đối với thiết bị/đích lưu trữ export.

### 34.3. Phát hiện

Theo dõi Atlas backup activities và cloud storage access logs, so với change tickets, thời gian thường dùng, lượng bytes/đích xuất.

### 34.4. Giới hạn của immutability

Snapshot WORM vẫn có thể bị **sao chép** bởi identity có quyền đọc/export. Immutability bảo vệ **tính toàn vẹn/khả dụng**, không tự bảo vệ **tính bí mật**.

## 35. Kịch bản 4: ransomware xóa nguồn và backups

### 35.1. Ngữ cảnh

Attacker chiếm một account có quyền rộng:

```text
MongoDB admin + Backup Manager + Storage Delete + KMS Admin
```

Attacker xóa dữ liệu, thử xóa snapshots và tìm cách vô hiệu hóa key.

### 35.2. Giảm blast radius

- Tách DB, backup, cloud storage và KMS identities.
- Backup immutable/retention lock, copy khác account/region khi cần.
- Audit/alert cho drop, user role, snapshot policy, key changes.
- JIT/break-glass cho quyền nguy hiểm.
- Restore drill và RPO/RTO có bằng chứng.

### 35.3. Không coi replica set là backup

Một lệnh xóa hợp lệ ở primary có thể được replication sang secondary. Replica set tăng availability với lỗi node, nhưng không thay thế **lịch sử backup bảo vệ trước xóa/sửa nhầm hoặc ransomware**.

## 36. Kịch bản 5: audit destination đầy đĩa

### 36.1. Ngữ cảnh

Security bật `auditAuthorizationSuccess` cho mọi workload. Log volume tăng gấp nhiều lần, ổ chứa audit gần đầy.

### 36.2. Hai rủi ro đồng thời

1. **Confidentiality:** nhiều audit events có thể chứa metadata/truy vấn nhạy cảm.
2. **Availability:** việc không ghi audit destination được có thể ảnh hưởng nghiêm trọng tới MongoDB server.

### 36.3. Phản ứng

- Alert sớm từ disk usage và audit event rate.
- Xác minh filter và chính sách đã được phê duyệt.
- Tăng capacity/ship log/rotation theo process.
- Chỉ điều chỉnh coverage audit sau khi đánh giá yêu cầu security.
- Test performance và cập nhật budget log ingestion.

**Không chỉ tắt audit trong production mà không có incident/change approval** để giải quyết hết chỗ lưu.

## 37. Bài tập thực hành

### Bài 1 — Xác định nguồn log

Phân loại nguồn thích hợp cho:

1. User đăng nhập MongoDB thất bại.
2. Admin đổi backup retention trên Atlas.
3. Operator tải snapshot từ object storage.
4. Java service từ chối hoàn tiền vì role nghiệp vụ không đủ.
5. MongoDB báo slow query.

Tại sao không thể dùng duy nhất một nguồn để trả lời tất cả?

### Bài 2 — Đọc audit event

Cho event minh họa:

```json
{
  "atype": "authenticate",
  "users": [{ "user": "orders_reader", "db": "admin" }],
  "remote": { "ip": "10.10.1.22", "port": 49210 },
  "result": 0
}
```

Hãy xác định action, actor, endpoint và kết quả. Nếu `result` khác 0, tại sao cần tra bảng mã theo `atype` thay vì coi là HTTP status?

### Bài 3 — Audit coverage

Một công ty bật database auditing nhưng `auditAuthorizationSuccess` vẫn tắt. CEO hỏi: “Đã có log mọi lần nhân viên đọc PII thành công chưa?”. Trả lời thế nào và cần kiểm chứng những cấu hình nào?

### Bài 4 — Viết audit filter

Thiết kế filter gồm `authenticate`, `authCheck`, `createUser`, `grantRolesToUser`, `revokeRolesFromUser` và `dropCollection`. Nêu ít nhất ba loại sự kiện quan trọng có thể chưa được cover và cách kiểm tra coverage.

### Bài 5 — Chi phí audit

Cluster có 25.000 read operations/giây. Security muốn audit tất cả read successes. Hãy nêu những metric cần benchmark trước khi bật và kế hoạch chống audit disk/collector quá tải.

### Bài 6 — Diagnostic vs database audit

Một developer thấy dòng `"connection accepted"` trong server log và kết luận “mọi CRUD đã có audit”. Vì sao kết luận sai?

### Bài 7 — `redactClientLogData`

Giải thích:

1. Tính năng thuộc edition/deployment nào?
2. Che loại nội dung nào?
3. Trade-off khi debug là gì?
4. Tại sao vẫn cần application log redaction?
5. Có thể coi audit logs và backup đã được che tự động không?

### Bài 8 — Allowlist logging

Một API đang log nguyên `req.body`. Hãy thiết kế event có tối đa tám trường phục vụ điều tra mà không cần log raw email, phone, password hoặc request token.

### Bài 9 — HMAC vs hash

Tại sao `SHA256(email)` không đủ mạnh để bảo vệ email trong log? Khi nào dùng HMAC và khi nào nên bỏ hẳn identifier?

### Bài 10 — Driver command monitoring

Một `CommandListener` Java log `event.getCommand()` ở DEBUG. Hãy giải thích rủi ro và đề xuất tập metadata an toàn để đo latency/query type.

### Bài 11 — Bảo vệ audit file

Audit JSON file nằm trên cùng host và user MongoDB có quyền ghi. Attacker chiếm OS admin. Hãy đề xuất kiến trúc ghi off-host, immutability, retention và kiểm tra tamper evidence.

### Bài 12 — MongoDB backup role

Vì sao dùng built-in `backup` trên `admin` tốt hơn cấp `root` cho backup job? Quyền backup vẫn nhạy cảm thế nào dù không có quyền quản trị user?

### Bài 13 — Atlas backup roles

Một nhân viên cần:

- Chỉ kiểm tra backup health.
- Tạo snapshot khi deploy.
- Khôi phục lên staging.
- Export snapshot theo yêu cầu pháp lý.

Hãy ghép từng nhiệm vụ với project role có đặc quyền thấp nhất và giải thích tại sao không cấp Project Backup Manager cho tất cả.

### Bài 14 — Khôi phục sản xuất

Atlas Project Backup Recovery Operator muốn restore snapshot lên production. Nêu các bước phê duyệt, xác minh target, kế hoạch rollback và tại sao restore có thể làm mất dữ liệu target.

### Bài 15 — Backup nhiều mặt phẳng quyền

Lập ma trận quyền cho database read, backup creation, object get, object delete, KMS decrypt và target restore. Tại sao một user không nên có tất cả?

### Bài 16 — Backup immutable

So sánh object versioning, retention lock/WORM và Atlas Backup Compliance Policy. Chúng bảo vệ điều gì? Có tự ngăn việc export dữ liệu không?

### Bài 17 — Logical backup

Một đội chạy `mongodump --oplog` qua `mongos` rồi nói “backup toàn sharded cluster chắc chắn nhất quán”. Vấn đề là gì? Hãy nêu hướng kiểm chứng backup thích hợp theo tài liệu MongoDB.

### Bài 18 — RPO/RTO

Yêu cầu RPO 15 phút, RTO 2 giờ, nhưng đội chỉ chụp một snapshot mỗi ngày và chưa từng restore test. Nêu vì sao mục tiêu chưa được chứng minh và đề xuất bài test đo cả key availability.

### Bài 19 — PITR và retention

Một lỗi dữ liệu được phát hiện sau 20 ngày; PITR window chỉ 7 ngày, monthly snapshot gần nhất là 30 ngày trước. Có thể khôi phục đúng điểm 20 ngày trước từ PITR hiện tại không? Cần thiết kế retention như thế nào dựa vào thời gian phát hiện sự cố?

### Bài 20 — Rò rỉ snapshot

Contractor có quyền export và tải một snapshot xuống thiết bị ngoài quản lý. Dù database gốc có TLS và RBAC, vì sao đây vẫn là sự cố? Những nguồn log nào giúp điều tra?

### Bài 21 — Threat modeling workshop

Lập sơ đồ:

```text
Java API -> MongoDB -> Atlas Cloud Backup
              |
              +-> Audit / SIEM
              +-> KMS
```

Chỉ ra tối thiểu sáu trust boundaries và đánh giá rủi ro Confidentiality/Integrity/Availability của mỗi boundary.

### Bài 22 — Incident response tabletop

Bạn phát hiện:

- Credential backup bị lộ.
- Audit event rate giảm bất thường.
- Có một snapshot được export ngoài lịch.

Hãy xây incident runbook bao gồm containment, preserving evidence, rotation, access review, storage/KMS logs, xác minh toàn vẹn và báo cáo cho người chịu trách nhiệm.

### Bài 23 — Kiểm tra giới hạn che log

Thiết kế lab test dùng **dữ liệu giả** chứa chuỗi `demo-secret-337`, số điện thoại giả và token giả. Xác định:

1. Log server trước/sau khi bật redaction.
2. Application log với và không có allowlist.
3. Audit event có `param` hay không.
4. Log collector có giữ bản raw không.

Không dùng dữ liệu PII thật hoặc thay đổi cấu hình production cho bài test.

### Bài 24 — Chính sách retention thống nhất

Cho nguồn MongoDB giữ dữ liệu 30 ngày, application logs 180 ngày, audit logs 2 năm và backup 12 tháng. Nêu các câu hỏi pháp lý/riêng tư cần làm rõ và rủi ro khi người dùng được xóa khỏi database nhưng PII vẫn tồn tại trong bản sao.

### Bài 25 — Thiết kế hoàn chỉnh

Tạo security design cho MongoDB production với:

- Audit authentication, quyền quản trị và selected sensitive reads.
- Log redaction ở server và Java application.
- SIEM có tamper-evident archive.
- Service identity riêng cho backup.
- Atlas roles phân tách create/recovery/export.
- Backup encryption/KMS, immutable retention, PITR và restore drills.
- Alert cho audit gaps, backup export, role changes và restore production.

Ghi **owner**, **evidence**, **risk còn lại** và **cách kiểm chứng** cho từng nhóm kiểm soát.

## 38. Quy trình triển khai từng bước

### Giai đoạn A — Xác định yêu cầu

1. Định nghĩa loại sự kiện bắt buộc ghi: auth failures, role changes, DDL, sensitive data access.
2. Phân loại PII/secrets trong database, commands, diagnostic log, audit log, backup.
3. Phân biệt requirement compliance với nhu cầu debug tạm thời.
4. Xác định nguồn Atlas/Enterprise/Community và tính năng thực tế.
5. Chỉ định owner cho database audit, application logging, backup, SIEM và KMS.

### Giai đoạn B — Thiết kế và thử nghiệm

1. Xây audit filters với coverage rõ và benchmark ảnh hưởng.
2. Cấu hình audit destination, disk capacity, off-host shipping.
3. Bật redaction được hỗ trợ và kiểm thử dữ liệu giả.
4. Thay raw logging bằng structured allowlist/trace IDs.
5. Thiết kế log RBAC, immutable/archive retention.
6. Chọn database `backup` role hoặc Atlas backup project roles phù hợp.
7. Xác định quyền ở backup storage, KMS và restore target.
8. Thiết kế encryption, immutability và policy backup.
9. Kiểm tra RPO/RTO và PITR bằng restore drill.

### Giai đoạn C — Go-live có kiểm soát

1. Thực hiện change review và rollout theo topology.
2. Kiểm tra audit event xuất hiện từ tất cả components cần thiết.
3. Xác nhận log collector/SIEM nhận đủ và alert hoạt động.
4. Kiểm tra quyền không cần thiết đã bị từ chối.
5. Xác nhận backup snapshots có retention/encryption đúng.
6. Thử đọc/xuất/khôi phục bằng identity đúng/sai trong lab.
7. Thu thập evidence và cập nhật runbook.

### Giai đoạn D — Vận hành liên tục

1. Review identities/privileges định kỳ.
2. Theo dõi audit volume, dropped/late events, disk usage, alert coverage.
3. Dò PII/secret trong logs bằng phương án được phê duyệt.
4. Kiểm soát thay đổi audit filters và backup policy.
5. Giám sát export/download/restore và KMS operations.
6. Thực hành credential rotation và restore drills.
7. Cập nhật retention, topology, compliance và version compatibility.

## 39. Tổng kết

**Audit MongoDB, log redaction và quyền backup là ba cơ chế bảo mật độc lập nhưng phải phối hợp.** Database audit giúp xác định hành động theo identity và event types đã cấu hình; diagnostic logs chủ yếu phục vụ vận hành; application audit mang ngữ nghĩa nghiệp vụ; Atlas/control-plane và cloud storage logs bổ sung dấu vết đối với backup/export.

**Che dữ liệu trong log cần nhiều lớp.** `security.redactClientLogData` trên Enterprise/Atlas giúp giảm dữ liệu nhạy cảm trong diagnostic message nhưng không tự che mọi driver, application, audit hoặc backup log. Nên ưu tiên không log raw payload/URI/command, dùng structured allowlist, correlation IDs, masking/HMAC có kiểm soát, cùng quyền/retention phù hợp ở SIEM.

**Backup là một bản sao production với quyền bảo mật tương đương.** MongoDB `backup` database role khác Atlas `Project Backup Creator`, `Recovery Operator`, `Export Operator` và `Backup Manager`. Phải tách quyền xem/tạo/xuất/khôi phục, quyền storage và KMS, áp encryption, immutable retention khi phù hợp, và giám sát các thao tác backup. Replica set không thay backup; backup không có key và restore drill cũng chưa chứng minh khả năng phục hồi.

**Điểm hoàn thành không phải “đã bật một checkbox”.** Cần một chính sách có mục tiêu, bằng chứng kiểm thử, owner, alert, kiểm soát dữ liệu nhạy cảm và runbook. Khi ba lớp được thiết kế đúng, tổ chức có thể điều tra sự cố đáng tin cậy mà không biến log hoặc backup thành chính nguồn rò rỉ dữ liệu.

## 40. Tài liệu tham khảo

- [MongoDB Manual — Auditing](https://www.mongodb.com/docs/manual/core/auditing/): hành động audit và các bảo đảm/giới hạn.
- [MongoDB Manual — Configure Auditing](https://www.mongodb.com/docs/manual/tutorial/configure-auditing/): file JSON/BSON, console, syslog.
- [MongoDB Manual — Configure Audit Filters](https://www.mongodb.com/docs/manual/tutorial/configure-audit-filters/): event filter và runtime configuration.
- [MongoDB Manual — Audit Messages](https://www.mongodb.com/docs/manual/reference/audit-message/mongo/): `atype`, `param`, `result` và hành động.
- [MongoDB Manual — Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/): `auditLog`, `redactClientLogData`.
- [MongoDB Manual — Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/): diagnostic logs và enterprise redaction.
- [MongoDB Atlas — Database Auditing](https://www.mongodb.com/docs/atlas/database-auditing/): hỗ trợ Atlas, audit filters và quyền.
- [MongoDB Atlas — Project Roles](https://www.mongodb.com/docs/atlas/reference/user-roles/): phân biệt backup creator, recovery, export và manager.
- [MongoDB Atlas — Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/): cơ chế và điều kiện backup.
- [MongoDB Atlas — Backup Compliance Policy](https://www.mongodb.com/docs/atlas/backup/cloud-backup/backup-compliance-policy/): giới hạn retention và chống xóa snapshots.
- [MongoDB Atlas — Restore from Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/): quyền, yêu cầu và tác động lên target.
- [MongoDB Manual — Built-In Backup and Restoration Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/): `backup` và `restore`.
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/): logical dump, `--oplog` và giới hạn sharded cluster.
- [MongoDB Manual — Back Up and Restore with Database Tools](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/): kiểm tra backup và quyền restore.
