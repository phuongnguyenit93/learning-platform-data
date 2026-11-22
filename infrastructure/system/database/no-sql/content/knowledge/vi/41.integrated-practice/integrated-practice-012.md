# Kiểm tra quyền truy cập, dữ liệu tenant và kết nối bảo vệ

## 1. Bối cảnh thực hành: một hệ NoSQL phục vụ nhiều tenant

Giả sử bạn triển khai dịch vụ quản lý đơn hàng bằng Java. Ứng dụng phục vụ nhiều doanh nghiệp (tenant) trên cùng hạ tầng. Tenant T17 và T18 đều có người dùng, đơn hàng, bộ nhớ đệm và báo cáo riêng. Phần dữ liệu chính nằm trong một cơ sở dữ liệu NoSQL; dữ liệu còn được đồng bộ sang cache và search index.

~~~text
                  Browser / API client
                          |
                          | HTTPS + access token
                          v
                  API gateway / service
                          |
               Verify identity + membership
                          |
                  Trusted TenantContext
                          |
           +--------------+-----------------+
           |              |                 |
        NoSQL DB       Redis cache       Search index
        Orders         Cached views       Product/orders
           |              |                 |
           +---------- Audit events ----------+

Tenant T17: users U17A, U17B; orders O101, O102
Tenant T18: users U18A, U18B; orders O101, O103
~~~

Lưu ý: cả T17 và T18 **đều có thể sử dụng cùng mã đơn hàng O101**. Một truy vấn chỉ theo orderId mà không kiểm tra tenant có nguy cơ trả dữ liệu của doanh nghiệp khác. Nguy cơ còn tồn tại ở thao tác ghi, truy vấn thứ cấp, phân trang, tìm kiếm, cache, event consumer, backup, export và môi trường khôi phục.

Trong bài thực hành này, ta cần chứng minh đồng thời:

1. **Đúng người, đúng quyền:** chỉ danh tính hợp lệ được phép thực hiện hành động mà vai trò của họ cho phép.
2. **Đúng tenant:** mọi tài nguyên được truy cập phải thuộc tenant được ủy quyền, kể cả khi mã định danh giữa các tenant trùng nhau.
3. **Đúng ranh giới kết nối:** ứng dụng kết nối tới hệ dữ liệu qua kênh đã xác thực và được mã hóa, không bỏ qua chứng chỉ hoặc cấp mật khẩu/quyền quá rộng.
4. **Không rò rỉ qua đường phụ:** cache, search, logs, exports, events, error messages và backups không làm lộ dữ liệu chéo tenant.
5. **Kiểm thử được:** các trường hợp cho phép và từ chối đều có bằng chứng, logs an toàn và điều kiện pass/fail rõ ràng.

Bài này thuộc module **Database No SQL**, chương **Thực hành tổng hợp**. Nó kết hợp thiết kế mô hình dữ liệu, bảo mật truy cập, Java service, kiểm thử tích hợp và thực nghiệm kết nối an toàn thành một quy trình kiểm tra hoàn chỉnh.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt xác thực danh tính (authentication), phân quyền (authorization), quyền dữ liệu tenant và quyền database service account.
- Thiết lập trusted tenant context từ identity đã xác minh thay vì tin trực tiếp header/body do client gửi.
- Viết các truy vấn đọc/ghi/xóa và điều kiện unique/upsert bao gồm tenant scope.
- Kiểm tra trường hợp trùng orderId, đổi tenantId giả, vai trò chỉ đọc, user bị vô hiệu hóa và cross-tenant enumeration.
- Thiết kế key patterns, indexes, cache keys, search filters, CDC/outbox và batch jobs không vượt ranh giới tenant.
- Cấu hình TLS certificate validation, hostname checking, truststore, secret rotation và quyền tối thiểu của service.
- Mô tả công cụ kiểm tra qua MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và Elasticsearch/OpenSearch theo giới hạn từng engine.
- Viết kiểm thử Java/JUnit, test matrix, audit/telemetry và checklist vận hành để phát hiện vi phạm.
- Đánh giá failure modes như expired certificate, stale IAM role, secret leak, revoked membership, lost tenant filter và restore nhầm dữ liệu.

## 2. Mô hình đe dọa và ranh giới tin cậy

Một kẻ hoặc chương trình không có quyền có thể thử:

| Điểm vào | Rủi ro | Bằng chứng phải có |
|---|---|---|
| HTTP request | Sửa tenantId trong URL/body/header | Server không tin tenantId tự khai |
| Access token | Token hết hạn, sai issuer/audience, giả vai trò | Token bị từ chối trước khi truy vấn |
| API query | Truy cập object ID của tenant khác | Không trả/ghi dữ liệu trái quyền |
| DB query builder | Quên tenant predicate | Test phát hiện, repository contract ngăn |
| Index/search | Tìm kiếm trên toàn tenants | Filter/authorization tại search boundary |
| Redis cache | Key collision hoặc global cache | Không nhận nhầm cached value |
| Background worker | Job chạy với admin credential | Mọi job có explicit tenant/job scope |
| Logs/traces | Ghi raw payload/PII/token | Redaction và quyền truy cập telemetry |
| Network | MITM, kết nối nhầm máy chủ | TLS verify certificate + hostname |
| Secrets | Mật khẩu hard-coded/lộ trong image | Secret manager, rotation, least privilege |
| Backups/exports | Khôi phục hoặc tải dữ liệu vượt quyền | RBAC/tenant scope, encryption, audit |

### 2.1. Client là vùng không đáng tin

Ngay cả khi giao diện chỉ hiện đơn của T17, người dùng có thể sửa URL, token, JSON body hoặc gửi API request riêng. Không coi việc ẩn nút trên UI là phân quyền.

### 2.2. API service không tự động đáng tin

Một developer có thể tạo repository method không nhận tenantId; một background job có thể dùng quyền admin; một dependency có thể đẩy dữ liệu vào logs. Cần ràng buộc từ thiết kế và kiểm thử tự động.

### 2.3. Cơ sở dữ liệu không biết nghiệp vụ nếu không được mã hóa vào mô hình

Trong shared collection, database có thể cho phép tìm document theo ID bất kỳ nếu service account có quyền rộng. Ứng dụng phải áp tenant scope; nếu engine hỗ trợ row/document-level policy hoặc IAM constraints, dùng thêm defense in depth.

### 2.4. Không đặt niềm tin chỉ ở một lớp

Kiểm tra tenant trong controller nhưng bỏ qua ở background worker vẫn gây rò rỉ. Thiết kế phải đi qua authentication → authorization → repository query → storage/network → derived systems → operations.

## 3. Thuật ngữ phải phân biệt

| Thuật ngữ | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang gọi? | U17A đăng nhập qua IdP |
| Authorization | Được làm gì? | Viewer chỉ đọc, editor có quyền cập nhật |
| Tenant isolation | Được truy cập dữ liệu của ai? | U17A không đọc Order của T18 |
| Least privilege | Service cần quyền tối thiểu nào? | Orders-reader không thể DropCollection |
| RBAC | Quyền theo vai trò | viewer, editor, tenant-admin |
| ABAC | Quyền theo thuộc tính/bối cảnh | tenantId, department, resource.owner |
| Data residency | Dữ liệu được lưu/xử lý ở đâu? | Tenant EU không xuất dữ liệu sai vùng |
| Transport security | Kết nối có được xác thực/mã hóa? | TLS với CA và hostname verify |
| Encryption at rest | Dữ liệu trên storage có được bảo vệ? | Encrypted disks/managed keys |
| Auditability | Có thể truy vết quyết định truy cập? | actor, tenant, action, outcome |

### 3.1. Authentication không đủ để đọc dữ liệu

Một JWT hợp lệ chứng minh ai gửi request trong phạm vi token contract, không chứng minh người đó có quyền với T17 hay Order O101.

### 3.2. Database credential không phải user identity

Ứng dụng thường kết nối bằng một service principal. Khi đó database nhìn thấy principal ứng dụng, còn tenant/user authorization phải được truyền qua trusted context và thi hành đúng ranh giới. Nếu engine hỗ trợ fine-grained access policy, có thể bổ sung.

### 3.3. Tenant admin không phải platform admin

Tenant-admin được quản lý người dùng/dữ liệu của T17, không được đọc dữ liệu T18 hoặc cấu hình toàn cụm.

### 3.4. TLS không tự giải quyết authorization

Kết nối được mã hóa tới đúng server vẫn có thể chạy truy vấn bỏ tenant predicate. Cần kiểm soát cả hai chiều: **quyền dữ liệu** và **đường truyền**.

## 4. Chuẩn bị một phòng lab cô lập

Chỉ sử dụng môi trường test/staging hoặc local containers được phép; **không chạy các lệnh kiểm thử phá hủy, thay quyền hoặc xoay khóa trên production**. Dùng dữ liệu giả:

~~~text
Tenants:
  T17 = Acme Test
  T18 = Beta Test

Users:
  U17A = T17 tenant-admin
  U17B = T17 viewer
  U18A = T18 tenant-admin
  U17X = disabled user, former member of T17

Orders:
  T17/O101 = totalMinor=125000, status=CONFIRMED
  T17/O102 = totalMinor=35000, status=DRAFT
  T18/O101 = totalMinor=777000, status=CANCELLED
  T18/O103 = totalMinor=92000, status=PAID
~~~

### 4.1. Tại sao cố tình dùng trùng O101?

Đó là một **negative test mạnh**: nếu repository tìm theo orderId mà quên tenantId, test có thể đọc nhầm dữ liệu ngay cả khi tất cả API responses có vẻ hợp lệ.

### 4.2. Chuẩn bị user bị vô hiệu hóa

U17X giúp kiểm tra quyền đã bị thu hồi: token cũ còn hạn hoặc cache authorization chậm cập nhật không được tiếp tục cho phép truy cập trái chính sách.

### 4.3. Chuẩn bị nhiều vai trò

Viewer U17B đọc được T17/O101 nhưng không xóa; tenant-admin U17A có thể sửa theo policy nhưng không truy cập T18/O101.

### 4.4. Tách credential của lab

Môi trường lab cần riêng IdP test, database credentials, KMS/secret policy và audit sink. Không dùng dữ liệu thật, không sao chép production secrets sang máy cá nhân.

### 4.5. Điều kiện thành công

Thành công không chỉ là API trả 200 cho test hợp lệ. Cần chứng minh từ chối các truy cập sai, không có dữ liệu thay đổi trái phép, kết nối không hạ cấp plaintext và không có leak qua logs/derived systems.

## 5. Chọn chiến lược lưu trữ tenant-aware

| Thiết kế | Ưu điểm | Rủi ro phải kiểm |
|---|---|---|
| Shared collection/table, trường tenantId | Ít overhead, phù hợp nhiều tenants nhỏ | Quên tenant predicate, index không đúng |
| Shared table với partition key có tenant prefix | Dễ khoanh key-range và truy cập | GSI/scan/fan-out bỏ tenant |
| Collection/keyspace riêng mỗi tenant | Ranh giới cấu hình rõ hơn | Provisioning, quota, nhầm namespace |
| Database/cluster riêng mỗi tenant | Tách biệt tài nguyên/credentials tốt hơn | Chi phí, vận hành và cross-env connection |
| Hỗn hợp tenant tier | Linh hoạt theo nhu cầu | Routing/provisioning/backup phức tạp |

### 5.1. Shared table cần tenant ở access path

Một document có tenantId nhưng query luôn theo orderId trần thì field tenantId chỉ là metadata, chưa tạo isolation. Key/index/query phải cho phép áp tenant filter hiệu quả và đầy đủ.

### 5.2. Database-per-tenant cũng có thể nhầm

Nếu routing lấy database name trực tiếp từ header X-Tenant-Id do client gửi, attacker có thể chọn DB khác. Router phải dùng trusted authorized tenant context và registry server-side.

### 5.3. Tenant key không thay authorization

Một PK dạng TENANT#T17 vẫn có thể được query bởi principal có quyền toàn bảng. API phải kiểm membership, IAM/ACL có thể giới hạn thêm.

### 5.4. Phân tách ảnh hưởng vận hành

Tenant isolation là cả confidentiality/integrity lẫn resource isolation. Một tenant nóng gây overload cho tenant khác cần quota/rate limit/hot partition design; một DB riêng cũng có shared network/identity-plane risks.

## 6. Bất biến bảo mật phải viết trước khi code

Trong lab, thiết lập các invariants:

1. Không request nào được đọc/ghi tài nguyên khi identity chưa được xác minh.
2. Tenant scope lấy từ identity+membership đã được server xác nhận; không nhận từ client field như nguồn thẩm quyền.
3. Với tài nguyên thuộc T18, mọi principal chỉ được cấp quyền T17 đều bị từ chối hoặc nhận Not Found theo API policy.
4. Viewer không thực hiện create/update/delete, kể cả qua bulk endpoint hay background path.
5. List/search/aggregate/export chỉ trả records thuộc authorized tenant scope.
6. Một global key collision không làm cache trả giá trị của tenant khác.
7. Ghi/update/delete đều ràng buộc tenant, không dùng filter _id đơn độc.
8. Cross-tenant uniqueness, nếu có, chỉ áp khi business contract đòi hỏi; mặc định ID đơn hàng có thể trùng khác tenant.
9. Kết nối DB phải kiểm chứng certificate chain và hostname, không silently fallback plaintext.
10. Service account không được phép thực hiện tác vụ vượt quyền cần thiết.
11. Logs/metrics không chứa raw access token, secret, PII hoặc payload cross-tenant.
12. Thử lỗi xác thực/phân quyền không để lại mutation trái phép.

### 6.1. Safety cần kiểm ở mọi thời điểm

Một list query từng trả nhầm record T18 trong 100 ms rồi cuối cùng sửa không thể coi là “eventually correct”; rò rỉ dữ liệu là vi phạm ngay khi xảy ra.

### 6.2. Kiểm cả confidentiality và integrity

Đọc nhầm gây lộ thông tin; UPDATE/DELETE nhầm gây thay đổi dữ liệu. Một test suite chỉ GET chưa đủ chứng minh isolation.

### 6.3. Chính sách từ chối phải nhất quán

API có thể chọn 404 để không tiết lộ existence hoặc 403 cho truy cập bị từ chối theo policy; điều quan trọng là **không trả dữ liệu hoặc mutation trái quyền** và không biến khác biệt response thành enumeration leak ngoài ý muốn.

## 7. Luồng xác thực và chọn tenant

~~~mermaid
flowchart TD
    A["HTTP request + token"] --> B["Verify signature, issuer, audience, expiry"]
    B --> C{"Identity valid?"}
    C -->|No| R["401/deny"]
    C -->|Yes| D["Load/validate memberships and roles"]
    D --> E{"Requested tenant authorized?"}
    E -->|No| F["403/404 according to policy"]
    E -->|Yes| G["Create immutable TenantContext"]
    G --> H["Authorize action + resource"]
    H --> I["Tenant-scoped repository and index queries"]
    I --> J["Return permitted fields only"]
~~~

### 7.1. JWT phải được kiểm, không chỉ decode

Đọc phần payload của JWT để thấy tenantId không đủ. Server phải verify chữ ký bằng khóa/algorithm được cho phép, issuer, audience, expiration/not-before, key rotation và token revocation/session rules theo identity architecture.

### 7.2. TenantId trong header chỉ là ý định lựa chọn

Một người có thể thuộc T17 và T18, header X-Active-Tenant: T18 giúp chọn tenant **sau khi** membership được xác nhận. Header tự khai không cấp quyền.

### 7.3. Membership có thể thay đổi

User bị loại khỏi tenant ở t1 nhưng token cũ vẫn chứa claim cũ. Cần chính sách token TTL, cache invalidation, introspection/revocation hoặc versioned membership theo mức rủi ro; không mặc nhiên tin claim mãi tới lúc hết hạn dài.

### 7.4. Bắt buộc kiểm role theo hành động

Một user thuộc T17 không có nghĩa được xóa Order T17. Kiểm authorization với action READ_ORDER, UPDATE_ORDER, DELETE_ORDER, EXPORT_ORDERS, MANAGE_MEMBERS, không chỉ canAccessTenant().

## 8. Thiết kế TenantContext bất biến trong Java

Định nghĩa kiểu dữ liệu do middleware tin cậy tạo:

~~~java
import java.util.Set;

public record TenantContext(
        String actorId,
        String tenantId,
        Set<String> roles
) {
    public TenantContext {
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("Missing actor");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        roles = Set.copyOf(roles);
    }

    public boolean hasRole(String name) {
        return roles.contains(name);
    }
}
~~~

### 8.1. Ai được tạo TenantContext?

Chỉ một trusted authentication/authorization component sau khi verify token và membership. Không expose API cho client gửi tùy ý actorId, tenantId, roles rồi deserialize thành context tin cậy.

### 8.2. Không dựa vào ThreadLocal không được quản lý

Trong asynchronous/reactive pipelines, ThreadLocal có thể bị mất hoặc rò context giữa tasks nếu quản lý sai. Truyền context tường minh hoặc dùng framework context propagation được review và test.

### 8.3. Context không thay permission check

TenantContext chứa roles chỉ là dữ liệu đã xác nhận; service vẫn phải map roles → action permissions và kiểm resource-level rules.

### 8.4. Context phải có scope tuổi thọ

Một background job chạy hàng giờ không nên giữ membership snapshot cũ mãi nếu policy thay đổi; phải chọn cách revalidate authorization hoặc dùng service identity có scope rõ ràng.

## 9. Ma trận quyền cho lab

| Identity | Tenant | Read order | Create order | Update status | Delete order | Export |
|---|---|---|---|---|---|---|
| U17A tenant-admin | T17 | Cho phép | Cho phép | Cho phép | Theo policy | Theo policy |
| U17B viewer | T17 | Cho phép | Không | Không | Không | Không |
| U18A tenant-admin | T18 | Cho phép | Cho phép | Cho phép | Theo policy | Theo policy |
| U17X disabled | T17 | Không | Không | Không | Không | Không |
| Không token | T17/T18 | Không | Không | Không | Không | Không |
| Service export-T17 | T17 | Theo scope export | Không | Không | Không | Cho phép giới hạn |

### 9.1. Deny by default

Khi role/action không được khai báo, kết quả mặc định là từ chối. Không viết “không phải viewer thì cho delete”.

### 9.2. Role là quyền tương đối

Role tenant-admin của T17 không tự mở rộng sang T18. Cấu trúc membership cần gắn tenantId với role thay vì một global role string không có scope.

### 9.3. Service roles

Một export worker chỉ cần đọc/ghi artifact cho T17, không cần credential toàn bộ tenants hoặc quyền DropTable.

## 10. Tenant key và composite identity

Trong NoSQL, có hai cách biểu diễn:

~~~text
MongoDB:
  {tenantId:"T17", orderId:"O101", status:"CONFIRMED"}

DynamoDB:
  PK="TENANT#T17"
  SK="ORDER#O101"

Cassandra:
  PRIMARY KEY ((tenant_id, bucket), created_at, order_id)

Redis:
  tenant:T17:order:O101

Search index:
  {tenantId:"T17", orderId:"O101", ...}
~~~

### 10.1. ID trùng giữa tenants là bình thường

Nếu cả T17 và T18 có O101, unique key theo tenantId+orderId mới đúng. Unique orderId toàn collection có thể vô tình cấm một business scenario hợp lệ.

### 10.2. Tenant trong key giúp giảm quên lọc

Thiết kế PK bắt buộc tenant scope trong path truy vấn, nhưng quyền truy cập vẫn cần kiểm ngoài key; client có thể đoán prefix nếu service có quyền đọc bảng rộng.

### 10.3. Không tạo key bằng nối chuỗi không kiểm soát

Khi tenantId/orderId chứa ký tự phân cách, encode hoặc validate theo canonical format. Không cho client chèn namespace khác qua ký tự đặc biệt rồi dùng trực tiếp vào DB key.

### 10.4. Data model phải hỗ trợ mọi access pattern

Point lookup đúng tenant chưa đủ nếu admin dashboard còn query “orders by status”, export hoặc full-text search; mỗi secondary access path cần tenant scope tương ứng.

## 11. MongoDB: tạo unique index theo tenant

Với shared collection, một index phục vụ uniqueness:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true, name: "uniq_tenant_order" }
)
~~~

### 11.1. Index phải khớp quy tắc nghiệp vụ

Hai tenant được dùng cùng orderId, nhưng một tenant không được có hai orders trùng orderId. Compound unique index thể hiện đúng invariant này.

### 11.2. Dữ liệu cũ cần được kiểm trước

Khi collection hiện tại đã chứa duplicates, thao tác tạo unique index có thể thất bại. Dọn dữ liệu theo migration workflow được kiểm soát, không xóa records tùy tiện trong thử nghiệm bảo mật.

### 11.3. Unique index không tự kiểm membership

Một user T17 vẫn có thể tạo document tenantId=T18 nếu service bỏ qua authorization. Index chỉ bảo vệ tính duy nhất của key, không bảo vệ quyền tạo.

### 11.4. Phạm vi unique trong sharded MongoDB

Ràng buộc unique index trên sharded collections phụ thuộc shard-key/index rules cụ thể của phiên bản và topology. Trước khi dựa vào tính duy nhất toàn hệ, kiểm engine constraints và thực thi uniqueness đúng partition/tenant scope.

## 12. Java/MongoDB: một truy vấn đọc có tenant predicate

Ví dụ sau minh họa kiểu Java 17 với MongoDB Java Sync Driver. Giả sử TenantContext đã được tạo từ middleware xác thực đáng tin cậy và collection đã có index:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.Optional;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Projections.*;

public final class OrderReader {
    private final MongoCollection<Document> orders;

    public OrderReader(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Optional<Document> findById(
            TenantContext context, String orderId
    ) {
        if (!context.hasRole("viewer")
                && !context.hasRole("tenant-admin")) {
            throw new SecurityException("Read not permitted");
        }

        Document result = orders.find(and(
                    eq("tenantId", context.tenantId()),
                    eq("orderId", orderId)
                ))
                .projection(fields(
                    include("orderId", "status", "totalMinor", "version"),
                    excludeId()
                ))
                .first();

        return Optional.ofNullable(result);
    }
}
~~~

### 12.1. Nguồn tenant nằm trong context, không trong URL tự khai

Controller có thể nhận orderId từ route, nhưng tenantId phải được middleware xác nhận. Nếu URL chứa tenantId, controller phải đối chiếu nó với authorized tenant scope trước khi dựng context.

### 12.2. Filter bằng tenantId và orderId

Điều kiện AND chặn trường hợp T17/O101 đọc nhầm T18/O101. Một truy vấn theo orderId đơn độc là lỗi thiết kế với shared collection.

### 12.3. Projection cũng là bảo vệ

Reader chỉ trả fields được dùng trong API. Không trả raw document bao gồm internal notes, encryption metadata hoặc identifiers chưa được phép.

### 12.4. Role check trong ví dụ là tối giản

Thực tế nên dùng permission engine với policy version, membership status, resource ownership và action types; role labels trong snippet chỉ phục vụ lab.

### 12.5. Không log documents khi không tìm thấy

Nếu query không có kết quả, trả Not Found theo API policy; không chạy truy vấn phụ toàn collection để “xem order thuộc tenant nào” rồi ghi thông tin đó vào logs hoặc response.

## 13. Java/MongoDB: UPDATE phải gắn tenant và expected version

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class OrderWriter {
    private final MongoCollection<Document> orders;

    public OrderWriter(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public boolean changeStatus(
            TenantContext context,
            String orderId,
            long expectedVersion,
            String nextStatus
    ) {
        if (!context.hasRole("tenant-admin")) {
            throw new SecurityException("Update not permitted");
        }
        UpdateResult result = orders.updateOne(
                and(eq("tenantId", context.tenantId()),
                    eq("orderId", orderId),
                    eq("version", expectedVersion)),
                combine(set("status", nextStatus), inc("version", 1L))
        );
        return result.getModifiedCount() == 1;
    }
}
~~~

### 13.1. Vì sao tenant scope trong update filter quan trọng?

Nếu filter chỉ theo orderId, một update có thể sửa document của tenant khác khi ID bị trùng hoặc index/query planner chọn kết quả không mong muốn.

### 13.2. Optimistic concurrency

expectedVersion ngăn update từ client đã đọc state cũ ghi đè update mới. Đây là một bảo vệ khác với authorization, nhưng thường cần kết hợp.

### 13.3. Không dùng upsert vô điều kiện

Một updateOne với upsert=true có thể tạo tài nguyên dưới tenant/key sai nếu filter/body được dựng không nhất quán. Nếu nghiệp vụ cần upsert, kiểm tenantId trên cả condition và inserted fields, unique key và idempotency.

### 13.4. Không nhận nextStatus tùy ý

Ngoài quyền sửa, service còn cần valid state transition và validation schema; tenant admin không mặc nhiên được đánh dấu order PAID nếu payment chưa xác nhận.

### 13.5. ModifiedCount=0 có nhiều nguyên nhân

Không tìm thấy, sai tenant, version conflict hoặc giá trị không thay đổi. API cần phân loại theo policy mà không tạo resource enumeration leak cho caller trái quyền.

## 14. DELETE và bulk operations cũng phải tenant-aware

~~~java
var filter = and(
        eq("tenantId", context.tenantId()),
        eq("orderId", orderId)
);
var result = orders.deleteOne(filter);
~~~

### 14.1. Đọc bảo vệ, xóa bỏ lọc vẫn nguy hiểm

Một service có findById tenant-safe nhưng deleteById chỉ nhận orderId sẽ tạo integrity bug. Kiểm từng method chứ không chỉ có một predicate mẫu.

### 14.2. Bulk update

Mỗi filter trong bulkWrite/updateMany cần bao gồm scope đúng. Không lấy một mảng orderIds từ client rồi updateMany theo ID mà không gắn tenantId.

### 14.3. Export/scan

Admin export 10.000 orders vẫn phải filter tenant. Nếu cần platform-level export, đó là đặc quyền tách biệt, có approval/audit và purpose rõ, không dùng thông qua public tenant API.

### 14.4. Batch job không có HTTP user

Scheduled worker cần một scoped job identity như export:T17 hoặc lifecycle:tenant:T17; không dùng ngữ cảnh null rồi mặc định “all tenants”.

## 15. Pagination, sort và compound indexes

Ví dụ listOrders:

~~~javascript
db.orders.find(
  {tenantId: "T17", status: "CONFIRMED"},
  {orderId: 1, status: 1, totalMinor: 1, createdAt: 1}
).sort({createdAt: -1, orderId: -1}).limit(20)
~~~

Một index có thể phù hợp với query:

~~~javascript
db.orders.createIndex(
  {tenantId: 1, status: 1, createdAt: -1, orderId: -1}
)
~~~

### 15.1. Filter trước sort/pagination

Truy vấn phải chọn tenant trước khi tạo trang kết quả. Cách “lấy toàn hệ 100 records, phân trang rồi lọc tenant trên Java” không chỉ rò dữ liệu vào memory mà còn cho trang sai/thiếu.

### 15.2. Không dùng cursor của tenant khác

Nếu API có continuation token, nó phải gắn query contract, tenant, filter/sort và được xác thực/chống sửa theo thiết kế. Opaque token của T17 không được dùng để đọc trang T18.

### 15.3. Index performance không thay isolation

Một index tenant-first giúp query hiệu quả, nhưng không thay quyền; service vẫn phải từ chối khi caller không được phép T17.

### 15.4. Stable tie-break

Sort theo createdAt khi nhiều orders cùng timestamp cần orderId tie-break để tránh trang thiếu/trùng khi paging; với updates đồng thời còn cần snapshot/cursor semantics phù hợp.

## 16. Aggregation và JOIN/lookup phải bảo vệ tenant

Một aggregation đếm orders theo status:

~~~javascript
db.orders.aggregate([
  {$match: {tenantId: "T17"}},
  {$group: {_id: "$status", count: {$sum: 1}}}
])
~~~

### 16.1. Đừng đếm toàn hệ rồi chỉ lọc nhãn kết quả

Nếu group toàn collections trước khi tenant filter, tổng số đơn/thu nhập các tenants khác đã lọt vào phép tính. Query contract phải được tenant-scoped từ đầu.

### 16.2. Lookup tới collection thứ hai

Nếu orders và order_items đều có tenantId, lookup phải join bằng tenantId+orderId hoặc điều kiện tương đương. Join chỉ bằng orderId có thể gộp items T18/O101 vào T17/O101.

### 16.3. Multi-stage pipelines

Filter tenant ở stage đầu là thực hành tốt, nhưng không đủ nếu pipeline dùng $unionWith/$lookup tới nguồn khác không ràng buộc tenant hoặc downstream code bỏ scope. Review toàn bộ data flow.

### 16.4. Aggregation có thể ghi

MongoDB aggregation stages như $out/$merge có side effects; đừng cho read-only report endpoint tùy ý nhận pipelines do client gửi. Dùng allowlisted templates và least-privilege DB role.

## 17. DynamoDB: tenant-scoped primary keys

Ví dụ single-table:

~~~text
PK = TENANT#T17
SK = ORDER#O101

PK = TENANT#T18
SK = ORDER#O101
~~~

### 17.1. Điểm đọc phải dùng đúng partition

GetItem hoặc Query cần PK từ trusted TenantContext và SK từ resource ID đã kiểm. Không lấy TENANT#... trực tiếp từ request rồi xem nó là scope tin cậy.

### 17.2. GSI cũng cần tenant awareness

Nếu GSI phục vụ “orders by status”, hãy thiết kế GSI partition keys cho phép tenant restriction, chẳng hạn tenantId#status. Một GSI theo status toàn hệ có thể bị lạm dụng khi IAM/service principal có quyền query rộng.

### 17.3. IAM conditions là defense in depth

Trong một số access patterns, IAM conditions như dynamodb:LeadingKeys kết hợp principal tags có thể giới hạn leading partition keys. Nhưng phải kiểm tra áp dụng tới table/index/operation cụ thể, policy evaluation và key schema. Không xem IAM condition là thay thế cho xác minh tenant membership ở API.

### 17.4. Scan nguy hiểm

Một service chỉ nên đọc đơn theo tenant không cần quyền Scan toàn bảng. FilterExpression có thể loại kết quả sau khi đọc nhưng không thay khả năng tiếp cận dữ liệu ở quyền; hạn chế quyền và thiết kế đúng access pattern.

### 17.5. Transactions và conditional writes

Khi Create/Update, condition và item keys phải cùng tenant; transaction request gồm nhiều keys có thể vô tình trộn T17/T18 nếu input không được kiểm trước.

## 18. Cassandra/ScyllaDB: keyspace role và partition scope

Một schema minh họa:

~~~sql
CREATE TABLE orders_by_tenant (
  tenant_id text,
  bucket text,
  created_at timestamp,
  order_id text,
  status text,
  total_minor bigint,
  PRIMARY KEY ((tenant_id, bucket), created_at, order_id)
);
~~~

### 18.1. Partition tenant-first hỗ trợ access path

Ứng dụng xác định tenant_id từ context và bucket từ logic được kiểm soát, rồi query theo partition. Không cho client truyền tenant_id tùy ý.

### 18.2. CQL roles thường có scope table/keyspace

Khả năng phân quyền CQL có thể giới hạn theo keyspace/table/resource, nhưng **không nên mặc định mỗi row được bảo vệ theo tenant_id** khi dùng shared table. Nếu cần per-tenant DB credentials, cân nhắc keyspace/table-per-tenant hoặc kiến trúc proxy/policy phù hợp cùng chi phí.

### 18.3. Data partition không tự là security boundary

Một CQL role được SELECT table có thể truy cập nhiều partition keys. Ứng dụng phải enforce tenant scope hoặc tách thành resource scopes thực sự.

### 18.4. Repair, snapshots và backup

Operations có quyền rộng có thể đọc SSTables/snapshots chứa nhiều tenants. RBAC ở API không bảo vệ access vào backup files; cần role/policy storage riêng.

### 18.5. LWT không thay authorization

INSERT IF NOT EXISTS giúp conditional create nhưng không chứng minh caller được phép tạo order cho tenant đó. Quyền vẫn phải được xác minh trước write.

## 19. Redis: ACL và cache key phải cùng tenant boundary

Key patterns:

~~~text
tenant:T17:order:O101
tenant:T18:order:O101
tenant:T17:session:U17A
~~~

### 19.1. Key collision

Nếu cache key chỉ là order:O101, T17 và T18 có thể ghi đè/đọc chung cached value. Thử hai orders O101 khác tenant giúp phát hiện lỗi ngay.

### 19.2. Redis ACL có giới hạn

Redis ACL có thể giới hạn command categories và key patterns trong phạm vi hỗ trợ, hữu ích cho service chỉ đọc/cached sessions. Tuy nhiên key pattern ACL không tự chứng minh actor có quyền tenant; ứng dụng vẫn phải xác thực identity và chọn key đúng.

### 19.3. Không cho endpoint gửi raw Redis commands

Một endpoint debug pass-through cho client gọi KEYS/SCAN/GET/SET tùy ý có thể rò dữ liệu toàn Redis. Tách admin utilities với service account/approval.

### 19.4. Cache-aside phải kiểm scope trước khi lookup

Không lấy cache trước khi authorization rồi mới kiểm tenant trên kết quả. Một dữ liệu trái tenant có thể đã được log, traced hoặc serialized trước khi bị chặn.

### 19.5. TTL và invalidation

Khi user bị revoke membership, cache authorization hoặc data keys phải được invalidated theo chính sách; stale cache không được tiếp tục cấp quyền trái policy.

## 20. Search index: filter quyền theo tenant ở mọi loại truy vấn

Một document:

~~~json
{
  "tenantId": "T17",
  "orderId": "O101",
  "status": "CONFIRMED",
  "totalMinor": 125000
}
~~~

### 20.1. Query filter

Search request phải kết hợp tenant filter từ trusted context với full-text/filter/range query của user, không dựa vào việc UI chỉ hiển thị records của tenant hiện tại.

### 20.2. Search facets/aggregations cũng có thể rò

Nếu chỉ lọc hits sau khi query nhưng aggregations tính trên toàn index, biểu đồ trạng thái/tổng số/tên sản phẩm tenants khác vẫn có thể xuất hiện.

### 20.3. Document-level security (DLS)

Một số deployments/editions có DLS hoặc field-level security. Ghi rõ tính năng/giới hạn thực sự có trong phiên bản, cấu hình và license; không giả định mọi search backend đều có cùng DLS.

### 20.4. Alias hay index-per-tenant

Filtered alias hoặc index-per-tenant có thể bổ sung cách ly, nhưng alias/query routing do service cấu hình vẫn phải bảo đảm tenant ownership; admin credentials có thể bỏ qua các ranh giới logical nếu không bị hạn chế.

### 20.5. CDC projector

Khi đồng bộ từ NoSQL sang search, event phải mang đúng tenantId từ source; nếu projector chỉ lưu orderId và mất tenantId, search index không thể thi hành scope đúng.

## 21. Các đường phụ thường bị bỏ quên

Không chỉ GET /orders và UPDATE /orders:

| Đường phụ | Cách gây rò rỉ | Kiểm thử cần có |
|---|---|---|
| Background export | Job tenant T17 scan toàn bảng | Artifact chỉ chứa T17 |
| Scheduled cleanup | DELETE quá rộng | T18 không bị xóa nhầm |
| Report aggregation | GROUP trước tenant filter | Count/sum không gồm T18 |
| Message consumer | Event thiếu/giả tenantId | Reject/quarantine hoặc scoped lookup |
| Search index | Tenant filter chỉ trên hits | Facets/aggregates vẫn scoped |
| Cache | Key không có tenant prefix | O101 không trả nhầm |
| File/object storage | Tên tệp đoán được | IAM/signed URL có tenant/purpose |
| Backup/PITR | Operator đọc mọi tenant | RBAC, encryption, audit |
| Debug endpoint | Dump raw document | Endpoint disabled/restricted |
| Logs/traces | Serializing full DTO/token | Redaction/field allowlist |
| Pagination token | Dùng T17 cursor cho T18 | Token binding được xác minh |
| AI/analytics pipeline | Xuất dữ liệu vượt scope | Contract và access review |

### 21.1. Data lineage

Vẽ đường đi của dữ liệu từ canonical DB qua CDC, queue, projections, export và observability. Mỗi node và transfer cần giữ tenant ownership hoặc enforce policy phù hợp.

### 21.2. Tách quyền thao tác khỏi quyền đọc dữ liệu

Support staff có quyền xem trạng thái xử lý một ticket không nhất thiết có quyền mở full order payload; làm phân quyền theo mục đích và trường dữ liệu.

### 21.3. Deletion phải lan sang derived stores

Một yêu cầu xóa theo policy ở source cần được xử lý trên cache, search, exports và backups theo retention rules; không chỉ xóa ở collection chính.

## 22. TLS giải quyết điều gì?

TLS dùng để bảo vệ kết nối giữa client và server:

1. **Bảo mật nội dung trên đường truyền:** ngăn đọc trộm traffic trong phạm vi TLS session.
2. **Tính toàn vẹn:** phát hiện thay đổi gói tin không hợp lệ.
3. **Xác thực máy chủ:** client kiểm chứng certificate chain và hostname của endpoint.
4. **Có thể xác thực client:** khi dùng mutual TLS (mTLS) và engine/deployment hỗ trợ.

### 22.1. TLS không đồng nghĩa đúng người được đọc đúng tenant

Người dùng T17 có thể kết nối HTTPS thành công nhưng vẫn bị chặn đọc T18/O101. TLS là transport control, còn authorization nằm ở identity/policy/data path.

### 22.2. Kết nối phải bảo vệ từng hop quan trọng

HTTPS giữa browser và gateway không tự chứng minh gateway → API → database đều được bảo vệ. Nếu TLS bị terminate ở load balancer, phải xét đường đi tiếp theo và mối đe dọa trong network.

### 22.3. Không có TLS fallback âm thầm

Khi handshake thất bại, client phải fail closed và báo lỗi có kiểm soát; không tự chuyển từ encrypted sang plaintext để “cho hệ chạy”.

### 22.4. Encryption at rest là lớp khác

Storage encryption giúp bảo vệ data media/snapshots trong threat model nhất định, nhưng không thay TLS hoặc user/tenant authorization. Cần cả hai khi yêu cầu.

## 23. Kiểm tra chứng chỉ máy chủ đúng cách

Một TLS connection đáng tin phải kiểm:

- Certificate chain đi tới trust anchor được phép.
- Server name phù hợp Subject Alternative Name (SAN) của certificate.
- Certificate đang trong thời hạn hợp lệ.
- Signature/algorithm và TLS protocol/cipher suite đáp ứng security policy.
- CA/truststore được cập nhật đúng quy trình, không bị thay qua nguồn không tin cậy.
- Nếu môi trường yêu cầu revocation checking, có chính sách và khả năng xử lý lỗi OCSP/CRL cụ thể.

### 23.1. Hostname verification là bắt buộc

Một certificate có chữ ký CA hợp lệ nhưng thuộc máy chủ khác không thể coi là server DB đúng. Không tắt kiểm hostname để xử lý lỗi misconfiguration.

### 23.2. Tự ký trong lab

Trong môi trường lab, có thể tạo CA nội bộ và đưa public CA cert vào truststore test. Không cho JVM tin mọi certificate chỉ vì “đang ở internal network”.

### 23.3. Không bật trust-all

Custom TrustManager cho phép mọi certificate hoặc flag invalidHostNameAllowed(true) làm mất mục tiêu xác thực server. Đây là anti-pattern phải bị phát hiện trong security review.

### 23.4. Certificate expiry

Đặt monitoring trước khi cert hết hạn; diễn tập certificate rotation có overlap trust trong môi trường test. Không đợi production handshake fail mới phát hiện.

## 24. Java: cấu hình MongoDB TLS với xác thực máy chủ

Ví dụ Java với MongoDB Sync Driver API minh họa:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class SecureMongoConnection {
    public static MongoClient connect() {
        // Credentials are provided via a separately managed,
        // least-privilege workload identity or secret provider.
        ConnectionString uri = new ConnectionString(
                "mongodb://db.internal.example:27017/?tls=true"
        );
        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(uri)
                .applyToSslSettings(ssl -> ssl.enabled(true)
                        .invalidHostNameAllowed(false))
                .build();
        return MongoClients.create(settings);
    }
}
~~~

Đoạn mã tập trung vào TLS server validation; chưa bao gồm xác thực DB principal, cấu hình truststore, timeout, connection pool hoặc credential loading thực tế. Ứng dụng phải cung cấp các phần đó qua policy được duyệt trước khi dùng.

### 24.1. Truststore được quản lý riêng

JVM/driver dùng trust material từ runtime configuration hoặc SSLContext được cấp phù hợp. Không hard-code private key/password vào source; quản lý trust anchor theo hệ thống secret/config quản lý.

### 24.2. Kết nối thành công không chứng minh toàn bộ bảo mật

Sau TLS handshake, phải authenticate đúng database identity và chỉ được thao tác trên collections/tenants cho phép. Tách bài test TLS khỏi test authorization.

### 24.3. Connection errors phải có timeout và retry budget

Không retry handshake error vô hạn hoặc log URI có credentials. Cert invalid/hostname mismatch thường là lỗi cấu hình cần cảnh báo, không phải lỗi transient có thể bypass.

### 24.4. Driver versions

API settings và default TLS behavior phụ thuộc driver/connection-string/provider; lưu exact driver version và xác nhận thông số có hiệu lực trong lab trước khi dùng chính thức.

## 25. Kiểm tra TLS bằng công cụ quan sát

Với endpoint test do tổ chức kiểm soát, có thể dùng OpenSSL để kiểm handshake và hostname:

~~~bash
openssl s_client \
  -connect db.internal.example:27017 \
  -servername db.internal.example \
  -verify_hostname db.internal.example \
  -verify_return_error
~~~

### 25.1. Đây là một phép kiểm kết nối, không phải DB login

Lệnh quan sát TLS certificate/chain; nó không tự chứng minh rằng user có quyền đọc bảng hay tenant isolation đúng.

### 25.2. SNI

-servername gửi Server Name Indication khi endpoint dùng virtual hosting/managed proxy. Giá trị phải khớp hostname được cấp phép.

### 25.3. Certificate chain

Nếu CA không nằm trong trust store dùng bởi công cụ, test có thể báo không tin cậy dù ứng dụng có truststore riêng. Ghi trust source trong experiment; không tắt verification để “làm xanh”.

### 25.4. Kiểm trên đúng hop

Kết quả gateway TLS không thay kiểm API→DB connection. Nếu dùng TLS proxy/sidecar, phải hiểu từng ranh giới bảo vệ.

### 25.5. Không đưa credentials vào shell history

Không truyền password/token trong command line hoặc sao chép private keys để debug certificate nếu không được phê duyệt. Dùng secret provider/tooling an toàn.

## 26. Negative TLS tests: hệ phải từ chối kết nối sai

| Test | Cách tạo trong lab | Kết quả mong đợi |
|---|---|---|
| Untrusted CA | Server cert ký bởi CA không được tin | Handshake bị từ chối |
| Hostname mismatch | Kết nối bằng hostname không khớp SAN | Handshake bị từ chối |
| Expired certificate | Server test dùng cert đã hết hạn | Handshake bị từ chối |
| TLS disabled | Server chỉ nhận plaintext | Client không hạ cấp |
| Revoked cert | Kiểm theo revocation policy áp dụng | Hành vi theo policy rõ |
| Wrong client certificate | mTLS server không tin client | Client bị từ chối |
| Certificate rotation | Overlap trust/đổi cert hợp lệ | Kết nối mới thành công, không bypass |

### 26.1. Không dùng production certificate để thử sai

Tạo test CA/cert riêng trong môi trường cô lập. Không làm expire/revoke cert production chỉ để xem client phản ứng.

### 26.2. Chứng minh fail-closed

Test pass khi ứng dụng từ chối kết nối không xác thực, báo lỗi có kiểm soát và **không thử plaintext fallback**; không phải pass khi service cứ chạy bất chấp warning.

### 26.3. Không lộ nội dung certificate key

Ghi server name, cert fingerprint/expiry/cause trong telemetry theo policy; không log private keys hoặc toàn bộ sensitive connection material.

## 27. mTLS và client identity

mTLS là TLS mà server cũng xác thực certificate của client. Đây là lựa chọn hữu ích cho kết nối service-to-service/database ở môi trường hỗ trợ.

### 27.1. mTLS không tự tạo quyền tenant

Một workload identity có client cert hợp lệ có thể vẫn truy cập quá nhiều tenants nếu được cấp DB role rộng hoặc API bỏ tenant predicate.

### 27.2. Mapping certificate → principal

Nếu database dùng client cert để xác thực, phải thiết kế mapping từ SAN/subject hoặc SPIFFE ID được tin cậy tới database/service role. Không tự coi tên common name tùy ý là tenant identity.

### 27.3. Rotate key và certificates

Hỗ trợ renew trước expiry, reload connections, revoke compromised identities và không có downtime quá mức. Test pool đang giữ connections cũ khi cert mới đã được cấp.

### 27.4. Quyền file/key store

Private key không nằm trong container image hoặc Git. Giới hạn quyền đọc, memory exposure, backup và runtime volume mounts.

## 28. Secrets: không hard-code, không log, không phát tán

Những bí mật cần bảo vệ:

~~~text
DB password / connection URI credentials
Cloud IAM credentials
JWT signing private key
TLS client private key
KMS key material
Redis authentication secret
Search admin token
Backup encryption keys
~~~

### 28.1. Lấy secret từ hệ thống chuyên dụng

Ưu tiên workload identity/temporary credentials hoặc secret manager có rotation và audit. Environment variables cũng có thể bị lộ qua process dumps/debug/logs; không xem chúng tuyệt đối an toàn.

### 28.2. Không gửi secret qua tenant context

TenantContext chứa ID/role đã xác minh, không chứa MongoDB password hoặc IAM access key. Storage service adapter lấy credential từ server-side provider.

### 28.3. Không in URI đầy đủ

Nếu URI chứa username/password, việc log exception hoặc connection settings có thể để lộ secret. Sanitize logging và dùng access controls.

### 28.4. Secret rotation

Thiết kế có thể reload pool/credentials, xử lý grace period nếu cần và loại bỏ quyền của secret cũ. Đo số connections lỗi khi rotate và đảm bảo không fallback tới credential cũ vô hạn.

### 28.5. Kiểm quyền secret manager

Orders-reader chỉ nên đọc secret của reader role; không truy cập admin database password, payment provider secret hoặc key material của tenant khác.

## 29. Least privilege tại database và hạ tầng

Ví dụ phân vai trò:

| Principal | Read | Write | Admin/DDL | Tenant scope |
|---|---|---|---|---|
| orders-api-read | Collections/keys cần thiết | Không | Không | Do application policy và DB constraints |
| orders-api-write | Orders operations cần thiết | Có giới hạn | Không | Do application policy và DB constraints |
| export-job-T17 | Dữ liệu T17 theo mục đích | Artifact output được duyệt | Không | T17 |
| migration-worker | Scope migration được duyệt | Theo change plan | Tạm thời nếu cần | Scoped job/approval |
| database-operator | Metadata/ops được duyệt | Tùy nhiệm vụ | Có kiểm soát | Platform level |

### 29.1. Không dùng root/admin credentials cho API thường

Root role vượt quyền của public application. Một bug query injection hoặc credential leak có thể ảnh hưởng mọi tenant/cluster.

### 29.2. Read-only service cũng có nguy cơ lộ dữ liệu

Quyền SELECT toàn collection không sửa được dữ liệu nhưng có thể đọc hết tenants. Cần giới hạn access paths, network, application policy và fine-grained DB features khi hỗ trợ.

### 29.3. Break-glass access

Platform admin truy cập khẩn cấp cần approval, short-lived credentials, purpose, audit và review sau sử dụng; không biến nó thành mặc định của background workers.

### 29.4. Temporary elevation

Migration cần DDL/write rộng hơn? Cấp role tạm thời và tự động thu hồi theo thời hạn/CI job scope, không giữ vĩnh viễn trong image/secrets.

## 30. Network boundaries và private endpoints

### 30.1. Chỉ mở đúng đường kết nối

API service được kết nối tới DB/search/cache endpoints cần thiết. DB không nên public Internet chỉ vì môi trường test thuận tiện.

### 30.2. Egress policies

Để hạn chế thiệt hại khi service bị xâm nhập, chỉ cho phép outbound tới các dependencies đã duyệt; hạn chế truy cập admin endpoints và public exfiltration destinations.

### 30.3. DNS và hostname

Khi đổi endpoint, TLS SAN và trust policy phải khớp. Không dùng IP thay hostname một cách tùy tiện nếu làm hostname validation fail rồi tắt verification.

### 30.4. Gateway/service mesh

Network policies, mTLS sidecars và API authorization mỗi lớp có vai trò khác nhau; kiểm cả request identity propagation và connection từ sidecar tới DB.

### 30.5. Network isolation chưa đủ

Một attacker đã chiếm quyền service trong trusted subnet vẫn có thể dùng broad DB credentials. Cần least privilege và tenant-aware queries cùng TLS.

## 31. Kịch bản kiểm thử truy cập có kết quả dự kiến

| ID | Actor | Request | Expected |
|---|---|---|---|
| A01 | U17A/T17 admin | GET T17/O101 | 200, đúng T17 data |
| A02 | U17B/T17 viewer | GET T17/O101 | 200, theo field allowlist |
| A03 | U17B/T17 viewer | UPDATE T17/O101 | Deny, no mutation |
| A04 | U17A/T17 admin | GET T18/O101 | Deny/Not Found, no T18 data |
| A05 | U18A/T18 admin | GET T18/O101 | 200, đúng T18 data |
| A06 | U17A/T17 admin | DELETE T18/O101 | Deny, T18 record remains |
| A07 | U17X disabled | GET T17/O101 | Deny |
| A08 | No token | GET T17/O101 | 401 |
| A09 | Invalid signature token | GET T17/O101 | 401 |
| A10 | Wrong token audience | GET T17/O101 | 401 |
| A11 | U17A/T17 admin | List orders | Only T17 |
| A12 | U17A/T17 admin | Search + facets | Only T17 |
| A13 | U17A/T17 admin | Export CSV | Only T17 |
| A14 | U17A/T17 admin | Reuse T18 cursor | Rejected |
| A15 | orders-reader identity | Attempt DB DELETE | Denied at DB |
| A16 | TLS client | Connect wrong hostname | Handshake denied |
| A17 | TLS client | Connect untrusted CA | Handshake denied |

### 31.1. Chỉ kiểm status code chưa đủ

API có thể trả 404 nhưng đã log T18 document hoặc ghi cache key trước khi từ chối. Test data flow, audit và side effects.

### 31.2. Deny không mutate

Sau denied update/delete, xác minh dữ liệu vẫn nguyên bằng principal được phép trong test.

### 31.3. Không trả sự tồn tại của đối tượng trái quyền

Nếu API policy ẩn existence bằng 404, response/body/timing cũng không nên tạo một kênh enumeration hiển nhiên.

### 31.4. Một user có thể ở nhiều tenants

Test context chuyển T17→T18 chỉ khi membership cho phép; không để cache/session lẫn tenant cũ.

## 32. Seed dữ liệu test cố tình tạo va chạm

Trong **test-only** MongoDB collection:

~~~javascript
db.orders.insertMany([
  {
    tenantId: "T17", orderId: "O101", status: "CONFIRMED",
    totalMinor: NumberLong("125000"), version: NumberLong("1")
  },
  {
    tenantId: "T18", orderId: "O101", status: "CANCELLED",
    totalMinor: NumberLong("777000"), version: NumberLong("1")
  },
  {
    tenantId: "T17", orderId: "O102", status: "DRAFT",
    totalMinor: NumberLong("35000"), version: NumberLong("1")
  }
])
~~~

### 32.1. Chỉ seed test database

Không chạy trên production; dùng tên database riêng, credentials hạn chế và lifecycle cleanup dành cho test.

### 32.2. Khác giá trị để dễ phát hiện sai

T17/O101 có totalMinor=125000, T18/O101=777000 và status khác. Một truy vấn sai tenant sẽ lộ rõ trong assertion.

### 32.3. Cleanup theo namespace

Nếu dùng deleteMany({}) reset fixtures, chỉ chạy trên collection ephemeral do test tạo. Không copy thao tác vào hệ thật.

### 32.4. Thêm edge cases

Thử deleted order, legacy missing fields, items trùng IDs khác tenants, same timestamps, facets và cache misses.

## 33. JUnit 5: điểm đọc phải đúng tenant

Giả sử test harness cung cấp collection ephemeral đã seed:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.bson.Document;
import org.junit.jupiter.api.Test;

class OrderIsolationTest {
    private final OrderReader reader = testFixtureOrderReader();

    @Test
    void t17CannotReadT18VersionOfSameOrderId() {
        TenantContext t17 = new TenantContext(
                "U17A", "T17", Set.of("tenant-admin")
        );
        Document order = reader.findById(t17, "O101").orElseThrow();

        assertEquals("CONFIRMED", order.getString("status"));
        assertEquals(125000L, order.getLong("totalMinor"));
    }

    // Replace this stub with an isolated integration-test fixture.
    private static OrderReader testFixtureOrderReader() {
        throw new UnsupportedOperationException(
                "Inject a seeded test-only MongoDB collection here"
        );
    }
}
~~~

Đây là **test skeleton**, không chạy ngay: cần thay stub bằng integration fixture/Testcontainers hoặc test database được cấu hình riêng và seed data. Không có test nào được thực thi khi soạn bài.

### 33.1. Assert values, không chỉ isPresent

Nếu chỉ kiểm có document, query nhầm T18/O101 vẫn có thể pass. So status/amount để phát hiện record của tenant sai.

### 33.2. Kiểm qua HTTP và repository

Repository test phát hiện thiếu query predicate. HTTP integration test chứng minh token/membership và tenant URL không bị lạm dụng.

### 33.3. Pin phiên bản

Khi triển khai, pin JUnit, MongoDB Java driver, test harness và database image để tái lập.

## 34. JUnit: viewer không được sửa

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.junit.jupiter.api.Test;

class OrderWriteAuthorizationTest {
    private final OrderWriter writer = testFixtureOrderWriter();

    @Test
    void viewerCannotChangeOrderStatus() {
        TenantContext viewer = new TenantContext(
                "U17B", "T17", Set.of("viewer")
        );
        assertThrows(
                SecurityException.class,
                () -> writer.changeStatus(viewer, "O101", 1, "PAID")
        );
        // In a full integration test, also verify DB remains unchanged.
    }

    private static OrderWriter testFixtureOrderWriter() {
        throw new UnsupportedOperationException(
                "Inject a test-only order writer"
        );
    }
}
~~~

### 34.1. AssertThrows chưa đủ

Phải kiểm record vẫn unchanged, không có email/outbox event/cache mutation. Exception có thể bị ném **sau khi** side effect đã xảy ra.

### 34.2. Thử DELETE/bulk riêng

Một changeStatus() đúng không chứng minh deleteById(), updateMany() và exportAll() an toàn.

### 34.3. Version conflict không phải authorization deny

Tenant admin được phép sửa T17 nhưng expectedVersion sai phải bị từ chối theo optimistic concurrency.

## 35. HTTP integration test: không tin header/body tự khai

~~~http
GET /v1/tenants/T18/orders/O101 HTTP/1.1
Host: api.test.example
Authorization: Bearer <TEST_TOKEN_FOR_U17A_T17_ONLY>
X-Active-Tenant: T18
~~~

### 35.1. Dùng test token giả

Không đưa production token vào tài liệu/test log. Trên test, dùng test IdP/workload identity an toàn.

### 35.2. Kết quả mong đợi

Middleware verify token, membership và requested tenant. Do U17A không có quyền T18, từ chối **trước khi query**; API có thể trả 404 theo chính sách ẩn existence.

### 35.3. Thay cả body/query string

Với POST/PUT, attacker giữ URL tenant T17 nhưng đặt body.tenantId=T18. Service phải reject mismatch hoặc set tenantId từ trusted context.

### 35.4. Role giả

Header X-Role: tenant-admin hay JSON roles:["admin"] do client gửi không cấp quyền.

### 35.5. Membership revoked

Test U17X bị revoke giữa hai requests; kiểm time-to-revocation theo policy kể cả token cũ chưa hết hạn.

## 36. Test list/search/aggregate không rò tenant

Với fixtures T17={O101,O102}, T18={O101,O103}:

~~~text
T17 list:
  expected orderIds = {O101,O102}

T17 search:
  expected hit tenantId = T17 only

T17 aggregate:
  count all orders = 2
  sum totalMinor = 160000
~~~

### 36.1. So count để bắt leak

Nếu trả đúng hai hits nhưng count/facet của toàn hệ là bốn, aggregation đã rò thông tin. So hits và metadata.

### 36.2. Negative cache test

T17/O101 phải trả 125000 dù T18/O101 vừa được query và cache warm. Đảo thứ tự requests để phát hiện collision.

### 36.3. Pagination token binding

Tạo cursor từ T17 list rồi dùng với T18; API phải reject hoặc bảo đảm không trả dữ liệu trái quyền. Test cả token bị sửa bytes/signature.

### 36.4. Ownership trong search index

Nếu indexer làm mất tenantId, không thể lọc đúng ở query. Phải sửa pipeline, không đoán tenant qua orderId khi IDs có thể trùng.

## 37. Test service account quyền tối thiểu

Có hai lớp:

1. **Ứng dụng:** viewer bị từ chối update dù service writer có quyền ghi.
2. **Database:** reader principal bị từ chối mutation bất kể code caller.

### 37.1. Dùng test roles ephemeral

Tạo roles trong test env với quyền collection/keyspace/table rõ ràng. Không sửa production ACL để kiểm.

### 37.2. Kiểm cho phép và từ chối

Reader phải SELECT/GET thành công và write/DDL thất bại; writer có quyền update giới hạn nhưng không DropDatabase/ChangeRole.

### 37.3. Không suy quyền từ tên role

Role tên reader có thể kế thừa quyền write/admin. Kiểm effective grants/permissions chứ không chỉ tên.

### 37.4. DDL identity riêng

API thường không cần tạo/drop indexes runtime. Migration cần DDL thì dùng identity riêng, approval và time-bound elevation.

## 38. Audit logs: bằng chứng nhưng không rò dữ liệu

~~~json
{
  "timestampUtc": "2026-11-14T08:00:00Z",
  "requestId": "req-test-019",
  "actorRef": "pseudonym-U17A",
  "tenantRef": "pseudonym-T17",
  "action": "READ_ORDER",
  "resourceType": "ORDER",
  "decision": "DENY",
  "reasonClass": "TENANT_NOT_AUTHORIZED",
  "policyVersion": "orders-authz-v3",
  "serviceVersion": "orders-api-test"
}
~~~

### 38.1. Không log raw token/password

Không serialize Authorization header, cookie, DB URI có password hoặc private keys vào audit records.

### 38.2. Pseudonym chưa phải anonymization

Một pseudonym cố định vẫn có thể liên kết hoạt động của actor; bảo vệ audit sink bằng encryption, IAM và retention.

### 38.3. Audit integrity

Không cho application user tự sửa/xóa audit records. Dùng append-only/tamper-evident storage theo yêu cầu; không coi JSON log là security boundary.

### 38.4. Reason classes

Error response không cần tiết lộ owner tenant của record, nhưng audit server-side có thể ghi lý do chi tiết theo quyền truy cập.

## 39. Metrics và cảnh báo

Một số tên metric do ứng dụng tự instrument:

~~~text
authn_denied_total{reason}
authz_denied_total{action,reason_class}
cross_tenant_access_attempt_total{service,action}
tenant_filter_guard_rejection_total{query_class}
db_access_denied_total{principal_class,operation}
tls_handshake_failure_total{reason_class,service}
certificate_expiry_seconds{endpoint_class}
secret_rotation_failure_total{service}
audit_write_failure_total{service}
cache_tenant_scope_violation_total{cache_class}
search_filter_missing_total{query_template}
~~~

### 39.1. Không gắn raw IDs làm labels

ActorId/orderId là high-cardinality và có thể nhạy cảm; dùng action, reason class, cohort, restricted audit lookup.

### 39.2. Severity theo hậu quả

Một response chứa field của T18 trong request T17 là sự cố nghiêm trọng dù chỉ xảy ra một lần. Không đợi rate vượt 1%.

### 39.3. Authentication failures có thể hợp lệ

Token expired và probing có thể tạo nhiều denies; cần phân biệt attack signals với false rejection của legitimate users.

### 39.4. TLS failures có nhiều nguyên nhân

Untrusted CA, hostname mismatch, expired cert, protocol mismatch hoặc network timeout cần classification. Không “khắc phục” bằng cách disable TLS.

## 40. CI security gate cho thay đổi NoSQL

Mỗi thay đổi liên quan database nên qua:

1. Unit tests của TenantContext/permission policy.
2. Integration tests truy vấn theo tenant với IDs trùng.
3. Negative tests viewer, revoked user, wrong audience, invalid signatures.
4. Tests list/search/facets/export/cache/CDC.
5. DB effective-permissions tests ở môi trường cô lập.
6. TLS positive/negative handshake tests.
7. Static/dependency scanning phát hiện trust-all/hard-coded secrets/query nguy hiểm.
8. Artifact/log scan tránh raw secrets/PII.
9. Migration review cho indexes/ownership/backup scope.
10. Policy rollout/rollback và monitoring.

### 40.1. Static scan chưa đủ

Một repository có tenant predicate trong method A vẫn có thể thiếu nó trong aggregation B. Dynamic tests bổ sung bằng chứng.

### 40.2. Không thay CI bằng manual click-through

UI test bằng tay khó cover URLs bị sửa, concurrent requests và invalid tokens. Đưa security invariants vào automated test suite.

### 40.3. Lab không sửa production

DB privilege negative tests, cert expiry và rotation nên chạy trên ephemeral/approved staging, CI không cần quyền admin production.

## 41. Runbook: phát hiện một response chứa dữ liệu khác tenant

Giả sử U17A gọi GET /orders/O101 và nhìn thấy totalMinor=777000 thuộc T18. Đây không phải một mismatch thông thường; đó là sự cố rò rỉ dữ liệu.

### Bước 1 — Dừng đường gây rò

Tắt/tách route, canary hoặc feature flag liên quan theo quy trình incident. Nếu cần chặn read endpoint tạm thời, chọn phương án làm giảm thêm dữ liệu lộ; không tiếp tục thử bằng tài khoản thật.

### Bước 2 — Bảo toàn bằng chứng

Lưu requestId, code version, query class, tenant/actor references, database audit events, thời gian và các thay đổi gần đây trong evidence store có quyền hạn chế. Không gửi full customer payload qua group chat hoặc tickets công khai.

### Bước 3 — Xác định phạm vi

Bug ở API membership, repository filter, compound index, cache key, search query, aggregation hay data pipeline? Xác định tenants/records/routes bị ảnh hưởng theo audit, không suy diễn chỉ từ một screenshot.

### Bước 4 — Kiểm soát truy cập

Nếu nghi credential bị lộ, xử lý rotation/revocation theo incident policy. Nếu chỉ lỗi code tenant filter, vẫn xác minh các service paths khác dùng cùng adapter.

### Bước 5 — Sửa và kiểm thử lại

Bổ sung regression fixture T17/O101 và T18/O101; kiểm point GET, list, UPDATE/DELETE, cache, search, export, aggregation và background jobs.

### Bước 6 — Đưa vào vận hành có kiểm soát

Thực hiện remediation/notification theo nghĩa vụ tổ chức và pháp lý liên quan; lưu incident timeline, owner, rollback plan và xác minh sau sửa.

## 42. Runbook: TLS certificate hoặc hostname verification thất bại

Một deployment mới báo SSLHandshakeException khi kết nối database.

### 42.1. Không tắt validation để khởi động nhanh

Không bật trust-all hoặc invalidHostNameAllowed(true). Điều đó có thể biến lỗi cấu hình thành lỗ hổng man-in-the-middle.

### 42.2. Chẩn đoán lớp lỗi

Tách DNS/endpoint name, certificate SAN mismatch, missing intermediate CA, expired certificate, unsupported protocol, mTLS client identity hoặc truststore mismatch.

### 42.3. Xác nhận expected endpoint

So hostname trong approved configuration/service discovery với certificate SAN. Khi đổi private endpoint/proxy, cập nhật certificate/trust policy đúng quy trình.

### 42.4. Phục hồi an toàn

Triển khai đúng CA/truststore/cert rotation với staged rollout, health checks và rollback, không hạ cấp plaintext hoặc dùng certificate không xác minh.

### 42.5. Ghi bằng chứng

Lưu endpoint class, error category, cert expiry/fingerprint theo policy, driver/JDK version và thời điểm deployment; không log client private key.

## 43. Runbook: bí mật truy cập bị lộ hoặc bị cấp quá rộng

Một scanner phát hiện database password xuất hiện trong build log.

### 43.1. Xem secret đã bị lộ

Không chờ xác nhận có attacker sử dụng rồi mới xử lý. Kích hoạt incident protocol, hạn chế quyền logs/artifacts và đánh giá phạm vi.

### 43.2. Rotate và revoke

Cấp credential mới có least privilege, thay ứng dụng dùng credential mới, thu hồi credential cũ, kiểm các processes giữ kết nối cũ và đo lỗi sau rotation.

### 43.3. Kiểm data access audit

Xem các hành động bất thường theo time window, principal, endpoint và operations; tránh dựa hoàn toàn vào tên secret.

### 43.4. Sửa nguồn lộ

Loại bỏ logging URI, debug environment dumps hoặc artifact embedding secret. Thêm redaction tests/static secret scanning.

### 43.5. Không coi xóa log là phục hồi đầy đủ

Artifacts đã được tải, caches và backup logs có thể còn chứa secret. Xử lý key compromise theo phạm vi lưu trữ và retention, không dựa vào việc xóa một file.

## 44. Test tenant isolation khi có async jobs và CDC

~~~text
Order source (T17/O101)
   -> Outbox event (tenantId=T17, orderId=O101)
   -> Broker
   -> Search projection
   -> Cache invalidation
   -> Reporting consumer
~~~

### 44.1. Event ownership do nguồn tin cậy cấp

Không nhận tenantId của một message từ client không tin cậy như nguồn thẩm quyền. Producer phải xác nhận và gắn ownership theo canonical record.

### 44.2. Idempotency và scope

Nếu cùng eventId gửi nhiều lần hoặc eventId trùng giữa tenants, inbox/dedup key cần có namespace phù hợp. Không được làm T17 event chặn T18 event hợp lệ hoặc apply T17 mutation lên T18.

### 44.3. Projection version và ownership

Khi upsert search document, dùng tenantId+orderId hoặc composite document identity; nếu chỉ dùng orderId thì hai tenant cùng O101 sẽ ghi đè nhau.

### 44.4. Repair/replay workflows

Backfill T17 không được scan/ghi nhầm T18. Một service có quyền rộng khi phục hồi phải có explicit job scope, approval và audit.

### 44.5. Negative test

Tạo một event thử nghiệm với tenantId giả/mismatch với canonical record; consumer phải reject/quarantine hoặc kiểm lại source, không âm thầm chuyển owner của record.

## 45. Backup, export và data residency cũng là kiểm tra quyền

### 45.1. Backup đa tenant có phạm vi rộng

Một snapshot của shared DB thường chứa dữ liệu nhiều tenants. Chỉ người/role được phép mới truy cập được backup; không nghĩ “API đã tenant-safe” nghĩa backup cũng tenant-safe.

### 45.2. Encryption và key access

Backup cần encryption và key management; người có object storage read nhưng không có decrypt key có thể bị hạn chế, song vẫn phải thực thi storage IAM, audit và key lifecycle đúng.

### 45.3. Selective restore

Khi cần phục hồi T17, tốt hơn restore vào môi trường cô lập rồi xác minh/trích đúng T17 records theo policy, không đè cả production shared DB hoặc xuất nhầm T18.

### 45.4. Exports/signed URLs

URL tải báo cáo phải có thời hạn/phạm vi phù hợp, không dựa vào tên file khó đoán. Một user T17 không được dùng report ID của T18 để tải dữ liệu.

### 45.5. Data residency

Nếu tenant có yêu cầu lưu/khai thác dữ liệu theo Region, kiểm cả replication, search index, backups, logs và hỗ trợ vận hành; không chỉ database primary.

## 46. Resource isolation và giới hạn theo tenant

Bảo mật đa tenant không dừng ở confidentiality. Một tenant có thể gây cạn tài nguyên chung làm các tenant khác không truy cập được.

### 46.1. Hot tenant

Một tenant có 100.000 QPS có thể tạo hot partition, connection-pool exhaustion hoặc read capacity throttling. Cần quota/rate limit, partition design và isolation của workloads.

### 46.2. Bulk queries

Giới hạn page size, result bytes, query duration và server-side scan, không cho tenant admin tự chạy unbounded full-table scans qua API.

### 46.3. Fair scheduling

Background export hàng triệu rows của T17 không nên chiếm toàn bộ pool và làm T18 timeout. Tách queues hoặc budgets theo mục đích.

### 46.4. Denial-of-service test có giới hạn

Trong staging, mô phỏng tenant nóng theo QPS/threads đã duyệt; đo p99 của tenant còn lại. Có kill switch và cost cap, không bắn tải vô hạn lên production.

### 46.5. Quan sát bằng cohorts

Theo dõi p95/p99 và rate-limit/throttle theo tenant tier/cohort với quyền telemetry phù hợp; tránh raw tenant IDs trong public metrics labels.

## 47. Cross-Region replication và quyền truy cập

### 47.1. Phân biệt replicated data với read authorization

Dữ liệu T17 xuất hiện ở Region B không có nghĩa mọi service trong Region B được phép đọc nó. IAM/roles và data residency vẫn áp dụng.

### 47.2. Global tables/active-active

Khi nhiều Regions có thể nhận writes, mỗi write cần tenant ownership và conflict resolution; stale identity hoặc service credential ở Region B không được bỏ qua authz do failover.

### 47.3. Failover test

Sau khi route traffic qua Region khác, xác minh TLS endpoint/CA/hostname, DB roles, tenant filters, cache/search index scope và audit sinks vẫn đúng.

### 47.4. Backups ngoài Region

Cross-region copy có thể chạm data residency/sovereignty requirement, cần xét theo policy và luật áp dụng, không tự copy test/production dữ liệu tùy tiện.

## 48. Cách thiết kế một test oracle độc lập

Một test không nên dùng cùng implementation sai để tự xác nhận mình đúng.

### 48.1. Oracle cho point reads

Test fixtures xác định rõ tenant, orderId, status và monetary value. Response phải khớp đúng fixtures, không chỉ số lượng records.

### 48.2. Oracle cho authorization

Viết matrix từ business policy/requirements, không để unit test đọc ngược từ logic hasRole() rồi xác nhận tương tự.

### 48.3. Oracle cho search/aggregate

Tính count/sum theo fixtures ở bộ test tách biệt và kiểm tenant-scoped metadata, không chỉ top hits.

### 48.4. Oracle cho kết nối

Server test với CA hợp lệ phải kết nối; wrong CA/hostname phải fail. Đừng coi “client connected” là oracle duy nhất.

### 48.5. Oracle cho quyền DB

Lấy effective grants/policies từ database/iam và thử denied write bằng test identity; không chỉ tin config file nói reader.

## 49. Checklist kiểm tra thực hành trước release

### 49.1. Identity và authorization

- [ ] JWT/session được xác minh signature, issuer, audience, expiration và các rules liên quan.
- [ ] Tenant selection được đối chiếu membership server-side.
- [ ] Quyền theo action/resource, deny-by-default và revocation semantics rõ.
- [ ] Viewer, tenant-admin, platform-admin và service principal có scopes khác nhau.

### 49.2. NoSQL dữ liệu

- [ ] Point GET/CREATE/UPDATE/DELETE có tenant scope đúng.
- [ ] Compound uniqueness và indexes phục vụ tenant-aware access patterns.
- [ ] List, pagination, aggregates, lookup, scan và export không rò tenant.
- [ ] Search hits/facets và cache keys có tenant ownership.
- [ ] CDC/outbox, replay, backup và selective restore giữ ranh giới tenant.

### 49.3. Kết nối và credentials

- [ ] TLS verify chain/hostname và không fallback plaintext.
- [ ] mTLS/client identity nếu yêu cầu, private keys được bảo vệ.
- [ ] Secrets không nằm trong code, image, logs hoặc test artifacts.
- [ ] DB/service role least privilege, DDL/admin được tách.
- [ ] Rotation, certificate expiry và negative handshake tests đã có.

### 49.4. Kiểm thử và vận hành

- [ ] Test dataset có T17/O101 và T18/O101 trùng ID.
- [ ] Có negative test cho invalid/revoked token, wrong tenant, wrong role, altered cursor.
- [ ] Denied mutations thực sự không sửa DB/queue/cache.
- [ ] Có audit/metrics an toàn, không chứa PII/secrets trong log.
- [ ] Runbook cho cross-tenant leak, TLS failure và credential compromise.
- [ ] CI gate và rollback policy được xác định.

## 50. Mẫu biên bản kết quả một đợt kiểm tra

~~~yaml
securityVerification:
  experimentId: nosql-tenant-security-lab-590
  environment: isolated-test
  applicationVersion: orders-api-example
  databaseVersion: exact-version-recorded-separately
  policyVersion: tenant-authz-v3
  runTimeUtc: 2026-11-14T08:00:00Z
  scenarioCounts:
    allowed: 0        # fill from actual run
    denied: 0         # fill from actual run
    unexpected: 0     # fill from actual run
  evidence:
    - fixture-ref
    - test-result-ref
    - sanitized-audit-ref
    - tls-validation-ref
    - effective-db-permissions-ref
  outstanding:
    - verify-background-export-scope
  outcome: NOT_RUN
~~~

### 50.1. Không tự điền PASSED

Đây là mẫu, các bộ đếm 0 và trạng thái NOT_RUN có nghĩa chưa chạy. Chỉ đổi sang PASSED khi test đã thực thi và evidence tồn tại.

### 50.2. Ghi versions và environment

Với security/integration tests, kết quả có thể đổi sau identity-provider policy/driver/database upgrade; report phải ghi versions và config được kiểm.

### 50.3. Trạng thái rõ ràng

PASSED, FAILED, BLOCKED, NOT_RUN khác nhau. Không coi skipped TLS negative test là pass.

### 50.4. Evidence không chứa raw secrets

Ghi đường dẫn tới sanitized artifacts và RBAC-protected audit, không nhúng token/password vào YAML công khai.

### 50.5. Kết luận có phạm vi

Một đợt lab pass không chứng minh bảo mật tuyệt đối. Nó cho thấy những invariants đã định được kiểm trên versions/workload/environment cụ thể; cần tiếp tục review khi thay đổi code, identity hoặc dữ liệu.

## 51. Bài tập 1 — dựng môi trường test đa tenant

Bạn có tenant T17 và T18 cùng dùng mã orderId=O101, nhưng mỗi order có số tiền và trạng thái khác nhau.

1. Viết fixture data cho MongoDB gồm ít nhất bốn orders, hai users và hai roles.
2. Tạo unique index đúng theo tenantId+orderId.
3. Giải thích vì sao unique index chỉ theo orderId có thể sai nghiệp vụ.
4. Thiết kế credential dành riêng cho test, không có quyền với production.
5. Viết các expected values cho point reads T17/O101 và T18/O101.
6. Đề xuất cách dọn dữ liệu test mà không xóa nhầm môi trường khác.
7. Chọn ít nhất ba negative tests bắt buộc trước khi viết ứng dụng.

## 52. Bài tập 2 — phát hiện IDOR bằng mã đơn trùng

Một service có phương thức:

~~~java
Document findOrder(String orderId) {
    return orders.find(eq("orderId", orderId)).first();
}
~~~

1. Đây là lỗi loại gì trong shared collection?
2. Nếu user T17 gọi O101, điều gì có thể xảy ra?
3. Sửa method signature để bắt buộc TenantContext đáng tin.
4. Sửa query với tenantId+orderId và projection fields.
5. Viết integration test chứng minh T17 không bao giờ nhận totalMinor của T18.
6. Nếu API muốn trả 404 thay vì 403 cho resource trái quyền, logic và audit nên tách thế nào?
7. Vì sao chỉ kiểm UI không hiển thị T18/O101 là chưa đủ?

## 53. Bài tập 3 — giả mạo tenant và role trong HTTP

User U17A chỉ được phép T17. Client gửi:

~~~http
PUT /v1/tenants/T18/orders/O101 HTTP/1.1
Host: api.test.example
Authorization: Bearer <TOKEN_FOR_U17A_T17>
X-Active-Tenant: T18
X-Role: platform-admin
Content-Type: application/json

{"tenantId":"T18","status":"PAID"}
~~~

1. Những fields nào hoàn toàn do client kiểm soát?
2. Những checks nào phải diễn ra trước repository call?
3. Trusted TenantContext được tạo từ đâu?
4. Nếu token hợp lệ nhưng T18 membership không tồn tại, kết quả mong đợi là gì?
5. Nếu body.tenantId khác URL, nên reject hay ghi đè giá trị nào?
6. Test assert T18/O101 không bị sửa thế nào?
7. Vì sao một token hợp lệ không tự có quyền platform-admin?

## 54. Bài tập 4 — viewer và tenant-admin

U17B là viewer, U17A là tenant-admin. Service có GET, UPDATE, DELETE và EXPORT.

1. Lập action-based policy cho bốn endpoints.
2. Nếu viewer gửi PUT qua URL tự chế, middleware/repository cần làm gì?
3. Nếu tenant-admin được phép update nhưng không delete, sao tránh logic “admin được làm mọi thứ”?
4. Nêu cách test quyền kế thừa sai trong role hierarchy.
5. Làm sao tách platform break-glass role khỏi tenant-admin?
6. Nếu U17B bị revoke membership trong khi token còn hạn, chính sách thu hồi nào cần kiểm?
7. Thiết kế audit event an toàn cho một DENY.

## 55. Bài tập 5 — cập nhật thiếu tenant filter

Một writer dùng:

~~~java
orders.updateOne(
    eq("orderId", request.orderId()),
    set("status", request.status())
);
~~~

1. Khi hai tenants cùng O101, mutation có thể tác động record nào?
2. Sửa filter dùng TenantContext và expectedVersion.
3. Nếu UPDATE trả modifiedCount=0, những nguyên nhân khác nhau có thể là gì?
4. Tại sao upsert=true khiến lỗi nguy hiểm hơn nếu inserted tenant field không đúng?
5. Thiết kế test failed update vẫn giữ nguyên T18 document.
6. Bổ sung unique constraint/index nào hỗ trợ invariant?
7. Vì sao optimistic locking không thay authorization?

## 56. Bài tập 6 — aggregation làm lộ thống kê

Orders: T17 có hai bản ghi tổng 160000; T18 có hai bản ghi tổng 869000. Một báo cáo trả đúng top hits T17 nhưng aggregation tính bốn records toàn hệ.

1. Đây có phải leak dù không hiện order details của T18?
2. Viết MongoDB pipeline với tenant filter trước group.
3. Nếu dùng $lookup sang order_items, cần join keys nào?
4. Một $unionWith không ràng buộc tenant có thể làm gì?
5. Test count và sum expected cho T17 như thế nào?
6. Nếu API cho client gửi raw aggregation stages, rủi ro gì?
7. Đề xuất allowlisted query templates và DB read-only role.

## 57. Bài tập 7 — cache collision giữa hai tenants

Redis code dùng:

~~~text
cacheKey = "order:" + orderId
~~~

T17/O101 được cache trước, sau đó T18/O101 được GET.

1. T18 có thể nhận dữ liệu nào?
2. Thiết kế key pattern có tenant scope, version/schema khi cần.
3. Cache lookup phải diễn ra trước hay sau authz?
4. Nếu user chuyển active tenant trong session, cache nào cần đổi/invalidate?
5. Redis ACL read-only có tự bảo vệ logical tenant ownership không?
6. Viết test đảo thứ tự requests T17→T18 và T18→T17.
7. Nếu cache được rebuild từ source, làm sao tránh ghi nhầm tenant trong cache-aside?

## 58. Bài tập 8 — search hits đúng nhưng facets sai

Search backend nhận query cho T17 nhưng chỉ filter hits, không filter aggregations.

1. Thông tin nào có thể lộ qua facets/counts?
2. Tenant filter nên nằm ở đâu trong query?
3. Khi indexer thiếu tenantId trên một số docs, hệ nên làm gì?
4. Có được suy mọi OpenSearch/Elasticsearch deployment có DLS không?
5. Định nghĩa test với T17/O101 và T18/O101; kiểm cả hits và aggregate count.
6. Nếu dùng filtered alias, ai được phép tạo/sửa alias?
7. CDC event cần mang ownership gì để search index không bị overwrite cross-tenant?

## 59. Bài tập 9 — TLS certificate hostname mismatch

Client Java kết nối db-internal.example.test nhưng certificate chỉ có SAN db-prod.example.test.

1. TLS handshake nên thành công hay thất bại?
2. Vì sao certificate CA hợp lệ chưa đủ?
3. Nếu developer muốn bật invalidHostNameAllowed(true), hậu quả an ninh là gì?
4. Phương án sửa hostname/endpoint/certificate đúng quy trình?
5. Test dùng CA/SAN giả trong lab ra sao?
6. Cần ghi metric/incident evidence nào mà không lộ key?
7. Tại sao HTTPS ở API gateway chưa chứng minh DB connection an toàn?

## 60. Bài tập 10 — kết nối mTLS và secret rotation

Service A dùng client cert/mTLS vào endpoint NoSQL, certificate còn năm ngày sẽ hết hạn. Đồng thời DB password nằm trong config file đã được commit lên repository.

1. Đề xuất quy trình rotation cert và password.
2. Ai có quyền lấy private key/trust anchor mới?
3. Khi connection pool còn những connections cũ, cần xử lý lifecycle thế nào?
4. Vì sao không chỉ xóa password khỏi Git rồi coi sự cố đã xong?
5. Test revoked/expired/untrusted client certificate trong staging.
6. Ghi secretRef/keyVersion thay vì secret value thế nào?
7. DB service principal sau rotation cần những quyền tối thiểu nào?

## 61. Bài tập 11 — DynamoDB IAM và key design

Một DynamoDB table Orders có:

~~~text
PK = TENANT#T17
SK = ORDER#O101
GSI1PK = STATUS#CONFIRMED
GSI1SK = ORDER#O101
~~~

Ứng dụng có principal gắn tenant tag T17.

1. Điểm yếu của GSI1PK khi muốn query theo tenant là gì?
2. Đề xuất một GSI key bao gồm tenant+status.
3. Giải thích cách một IAM condition như dynamodb:LeadingKeys có thể tạo lớp bảo vệ bổ sung trong phạm vi hỗ trợ.
4. Nếu một Query chạy qua index, policy trên base table đã đủ hay phải review cả index resource/leading key?
5. Vì sao IAM principal tags/session tags phải xuất phát từ identity service đáng tin?
6. Nếu table service role có quyền Scan toàn bảng, nguy cơ gì còn tồn tại?
7. Test cố gửi PK=TENANT#T18 bằng principal T17; kỳ vọng về response, audit và dữ liệu?

## 62. Bài tập 12 — Cassandra role trên shared table

Một Cassandra keyspace chứa bảng orders_by_tenant, với partition key gồm tenant_id và month. Service account có quyền SELECT toàn table.

1. CQL role có tự kiểm tenant_id của mỗi row không?
2. Vì sao token/partition key không là security boundary đầy đủ?
3. Nếu business cần database-level isolation từng tenant, có những kiến trúc nào?
4. So trade-off keyspace-per-tenant và shared table.
5. Tenant-admin ở HTTP có được cấp quyền CQL admin không?
6. Tạo test consumer/job quên tenant_id và xác định lớp nào nên phát hiện/từ chối.
7. Nếu backup SSTables chứa nhiều tenants, API authorization còn bảo vệ backup đó không?

## 63. Bài tập 13 — Redis ACL không thay logic tenant

Ứng dụng dùng shared Redis cluster; API role viewer chỉ được đọc order cache.

1. Thiết kế key prefix có tenantId.
2. Nếu Redis reader credential có +@read nhưng cho mọi keys, nguy cơ nào còn lại?
3. Có thể giới hạn key patterns bằng ACL ở mức nào, và tại sao application authz vẫn cần?
4. Nếu service có quyền SET để cache-aside, làm sao giới hạn write access đúng paths?
5. Test user T17 cố truy vấn T18 key qua debug endpoint.
6. Nếu membership bị revoke, cache quyền access cần invalidation ra sao?
7. Có nên cho public endpoint gửi raw Redis commands không? Vì sao?

## 64. Bài tập 14 — background exporter và user không còn quyền

Một user U17A được phép export Orders T17. Job chạy sau 30 phút, lúc đó user đã bị rút membership. Job sử dụng service admin credential.

1. Quyền export nên được xác minh tại enqueue hay execution, hoặc cả hai?
2. Thiết kế job envelope chứa tenantId, actorRef, purpose, policyVersion và expiry, không chứa access token dài hạn.
3. Khi job đã bị hủy quyền, nó nên làm gì?
4. Nếu export đọc shared table, cách nào bảo vệ query scope?
5. Output file được lưu ở object storage; signed URL và object IAM cần ràng buộc gì?
6. Nếu job có quyền platform admin, làm sao giảm blast radius?
7. Viết test cho worker T17 không ghi nhầm file chứa T18/O101.

## 65. Bài tập 15 — selective restore từ backup đa tenant

Một snapshot của shared Orders database chứa T17 và T18. T17 mất một số đơn hàng và yêu cầu restore.

1. Vì sao không nên restore cả snapshot lên production rồi công bố T17 đã phục hồi?
2. Môi trường cô lập cần quyền, TLS và KMS như thế nào?
3. Khi trích records của T17, cần xác minh composite keys/indexes/data ownership ra sao?
4. Audit và approval cho operator có quyền đọc cả snapshot phải thiết kế thế nào?
5. Nếu snapshot ở Region không được phép theo data residency policy, cần cân nhắc gì?
6. Sau selective restore, search/cache/CDC projections cần reconciliation nào?
7. Những evidence nào chứng minh không xuất hoặc ghi dữ liệu của T18?

## 66. Bài tập 16 — token cũ sau khi thu hồi quyền

U17X có JWT hợp lệ thêm 45 phút nhưng vừa bị xóa khỏi tenant T17.

1. JWT signature/expiry hợp lệ có tự chứng minh quyền đọc T17 không?
2. Nếu access policy yêu cầu revoke dưới 5 phút, ứng dụng cần cơ chế gì?
3. So server-side membership revalidation, short-lived token và versioned membership cache.
4. Token introspection hoặc revocation list có tác động latency/availability nào?
5. Nếu identity service mất kết nối, khi nào phải fail closed theo policy?
6. Viết test revoke giữa hai API calls với fake clock.
7. Nếu service log full JWT khi deny, đó là một sự cố khác thuộc loại gì?

## 67. Bài tập 17 — credential bị lộ và database role quá rộng

Một orders-api MongoDB connection string có username/password xuất hiện trong CI logs. Database user đó có quyền đọc/ghi toàn database, kể cả audit collections.

1. Các tác động có thể xảy ra nếu kẻ khác dùng credential là gì?
2. Runbook incident cần làm gì trước và sau rotation?
3. Làm sao xác minh không còn build logs/images/backups chứa secret cũ?
4. Thiết kế reader/writer/migration/operator identities với quyền tối thiểu.
5. Nếu một service dùng chung credentials trên năm tenants, blast radius ra sao?
6. Sau rotation, connection pool và applications cũ có thể còn dùng credential nào?
7. Chứng minh quyền DDL/audit edit của orders-api đã bị chặn bằng một negative test an toàn.

## 68. Bài tập 18 — failover sang Region khác

Database primary Region A mất kết nối; API chuyển sang Region B. Region B có certificate chain/hostname, service IAM roles và search index khác.

1. Test TLS endpoint validation trong Region B gồm những điều gì?
2. Có được bỏ hostname validation khi failover diễn ra gấp không?
3. Data residency policy có cho phép đọc backup/index ở Region B không?
4. Những tenant-related tests nào phải chạy sau failover?
5. Nếu search index ở B có tài liệu T17 thiếu tenantId, ứng dụng nên làm gì?
6. Quá trình retry/redirect có thể lộ Authorization header sang endpoint sai như thế nào?
7. Thiết kế canary và rollback plan an toàn cho Region migration.

## 69. Bài tập 19 — một tenant làm cạn tài nguyên của tenant khác

Một tenant T17 gửi 100.000 queries/giây trong khi T18 chỉ có 100 queries/giây. Hai bên dùng cùng database pool, query budget và search cluster.

1. Đây chỉ là performance issue hay còn thuộc isolation/availability?
2. Đặt QPS, concurrent request và result-size limits theo tenant thế nào?
3. Nếu T17 query scan bảng rộng, cách nào hạn chế trước DB?
4. Cần tách connection pool hoặc worker queues ra sao?
5. Khi load shedding, làm sao đảm bảo T18 vẫn đạt SLO?
6. Thiết kế metrics và test stop conditions không lộ raw tenant IDs.
7. Nếu giới hạn quá thấp với tenant enterprise, business contract và exemption policy được quản trị thế nào?

## 70. Bài tập 20 — bài kiểm tra end-to-end cho Java NoSQL SaaS

Bạn đóng vai trò người phụ trách security verification cho một hệ thống:

~~~text
Java API + OIDC identity
MongoDB shared orders collection
DynamoDB idempotency ledger
Redis tenant-aware cache
OpenSearch orders index
Kafka/CDC projection
TLS for API and storage connections
Cloud secret manager + encrypted backups
~~~

Thiết kế một kế hoạch thực hành độc lập:

1. Xây test fixture gồm ít nhất ba tenants, các user viewer/admin, revoked user và mã orderId trùng nhau.
2. Vẽ trust boundaries từ token đến MongoDB, cache, search, broker, export và backup.
3. Xác định trusted TenantContext contract và policy kiểm membership/role.
4. Chọn MongoDB indexes và viết query predicates cho GET, LIST, UPDATE, DELETE, AGGREGATE.
5. Thiết kế DynamoDB idempotency keys không bị trùng/chặn chéo tenants.
6. Thiết kế Redis cache key và search document identity chứa tenant scope.
7. Tạo HTTP/API negative tests với wrong tenantId trong path/header/body, token sai issuer/audience, role giả, revoked membership.
8. Test pagination cursor và search facets có ràng buộc tenant.
9. Test job export, CDC backfill, replay, tombstone/delete và backup selective restore.
10. Kiểm effective database/IAM/Redis ACL grants của reader, writer, operator trong môi trường cô lập.
11. Tạo CA/cert lab, test TLS thành công và các trường hợp untrusted CA/hostname mismatch/expired certificate.
12. Thiết kế mTLS/secret rotation với rollback an toàn, không đưa private keys vào Git.
13. Ghi audit/telemetry có pseudonymous actor/tenant references và chính sách retention.
14. Xác minh denied operations không gây mutation hoặc gửi side effects.
15. Chạy load test hot tenant có quota, cost cap và stop conditions.
16. Viết báo cáo test outcomes PASSED/FAILED/BLOCKED/NOT_RUN với evidence refs.
17. Lập runbook cross-tenant leak, TLS failure, credential compromise.
18. Đề xuất CI gate cho mỗi lần đổi database schema/query/SDK/identity policy.
19. Phân biệt những điều đã chứng minh với các khoảng trống chưa kiểm thử.
20. Đặt tiêu chí release gate: những lỗi nào bắt buộc chặn deploy, dù tỷ lệ lỗi rất nhỏ?

## 71. Tổng kết: bảo mật NoSQL đa tenant cần kiểm chứng từ identity đến từng bản ghi

Kiểm tra quyền truy cập, dữ liệu tenant và kết nối bảo vệ không thể là một dấu tick “đã bật TLS” hay “đã kiểm JWT”. Đó là một tập các bất biến phải được bảo vệ xuyên suốt API, repository, database, cache, index, event pipeline và hạ tầng vận hành.

Các nguyên tắc cần ghi nhớ:

1. **Authentication khác authorization.** Token hợp lệ không có nghĩa được truy cập mọi tenant, object hoặc operation.
2. **TenantContext phải được tin cậy.** Xác thực identity và membership server-side trước khi tạo context; header/body tenantId chỉ là input cần kiểm.
3. **RBAC/ABAC phải có scope.** Tenant-admin của T17 không tự thành admin của T18 hoặc platform admin.
4. **Deny by default.** Quyền không được khai báo thì không cấp; kiểm các đường background/export/debug bên cạnh API thường.
5. **Mọi access path phải tenant-aware.** Point GET, UPDATE, DELETE, batch, aggregation, lookup, index, pagination, search facets và backup đều cần ownership protection.
6. **Composite key và unique index phải phản ánh scope.** T17/O101 và T18/O101 có thể cùng tồn tại mà không được đọc/ghi chéo.
7. **Database-level privilege là defense in depth.** Application role và DB principal có trách nhiệm khác nhau; read-only role vẫn có thể đọc quá rộng nếu không được scope.
8. **Tenant partitioning không đồng nghĩa security policy.** Một partition key có tenant prefix giúp query design, nhưng không tự ngăn principal có quyền toàn bảng.
9. **TLS phải xác thực server.** Kiểm CA chain, SAN/hostname, thời hạn và protocol; không trust-all hoặc fallback plaintext khi handshake lỗi.
10. **mTLS/credentials có lifecycle.** Rotate certificates/secrets, bảo vệ private keys, thu hồi identities cũ và không log nhạy cảm.
11. **Least privilege cho runtime.** Reader, writer, migration, operator và break-glass roles cần quyền/approval/expiry khác nhau.
12. **Derived data cũng phải tách tenant.** Cache, search, CDC, outbox, analytics và exports có thể rò ngay cả khi canonical database query đúng.
13. **Backups/restore cần access controls riêng.** Shared snapshot chứa nhiều tenants; selective restore phải được thực hiện/kiểm chứng an toàn.
14. **Đường vận hành và Region cũng thuộc threat model.** Failover, recovery, secret storage, support access và data residency không thể bỏ qua.
15. **Kiểm cả bí mật và tính toàn vẹn.** Không đọc nhầm T18 chưa đủ; denied UPDATE/DELETE cũng phải chứng minh không làm thay đổi T18.
16. **Test fixtures cố tình tạo va chạm.** Hai tenants dùng O101 với giá trị khác nhau là cách bắt lỗi thiếu predicate hiệu quả.
17. **Kiểm API, repository và database role.** Không chỉ test UI/status code; assert dữ liệu, side effects, policy decisions và quyền thực tế.
18. **Không dùng metrics/logs làm kênh rò rỉ mới.** Redact secrets/PII, giới hạn labels, bảo vệ audit và evidence artifacts.
19. **Sự cố phải có runbook.** Cross-tenant leak, TLS cert failure và credential compromise cần response/containment/recovery rõ ràng.
20. **Một lần test pass không là bảo mật tuyệt đối.** Ghi engine/driver/policy version, environment, phạm vi, evidence và những phần chưa thử; chạy lại khi hạ tầng hoặc schema thay đổi.

Trước khi đánh dấu một NoSQL deployment là sẵn sàng phục vụ nhiều tenant, hãy tự hỏi:

> **“Nếu một người dùng hợp lệ của T17 cố đọc hoặc sửa dữ liệu của T18 bằng mọi đường API, cache, search, job, export và backup; đồng thời hệ gặp lỗi TLS hoặc credential rotation, những lớp nào sẽ từ chối đúng, và ta đã có bằng chứng kiểm thử nào chứng minh điều đó?”**









