# Quay lui bản phát hành mà không dùng lại trạng thái nghiệp vụ không hợp lệ

Khi một bản phát hành Java mới gặp lỗi trong production, đội vận hành thường muốn quay lại phiên bản trước càng nhanh càng tốt. Với ứng dụng dùng CRaC, thao tác này có thêm một yếu tố cần kiểm soát: checkpoint lưu trạng thái của một tiến trình tại một thời điểm, trong khi dữ liệu nghiệp vụ và các hệ thống bên ngoài vẫn tiếp tục thay đổi.

Vì vậy, rollback bản phát hành phải khôi phục đúng **mã ứng dụng và runtime tương thích**, đồng thời nạp lại **trạng thái nghiệp vụ hiện hành từ nguồn dữ liệu có thẩm quyền**. Không được mặc định rằng heap snapshot của bản phát hành trước vẫn phản ánh trạng thái đơn hàng, số dư, tồn kho, quyền truy cập hoặc tiến độ xử lý hiện tại. Một checkpoint có thể hợp lệ về mặt kỹ thuật nhưng chứa dữ liệu đã cũ hoặc không còn tương thích với schema và sự kiện đang được sử dụng.

## 1. Phân biệt rollback ứng dụng và rollback dữ liệu

Rollback ứng dụng là đưa workload về một artifact phần mềm đã biết là ổn định: OCI image, phiên bản ứng dụng, JDK/CRaC runtime, cấu hình và checkpoint tương ứng. Rollback dữ liệu là thay đổi dữ liệu bền vững trở về một trạng thái trước đó hoặc thực hiện các thao tác bù để sửa kết quả nghiệp vụ.

Hai hoạt động này không đồng nghĩa:

| Hoạt động | Thay đổi | Có tự khôi phục dữ liệu nghiệp vụ không? |
|---|---|---|
| Rollback Deployment | Pod template, image digest, cấu hình phát hành | Không |
| Restore checkpoint | Trạng thái tiến trình JVM tại thời điểm checkpoint | Không khôi phục database, broker hoặc dịch vụ ngoài |
| Invalidate/rebuild cache | Trạng thái dẫn xuất trong bộ nhớ/cache | Không thay đổi nguồn dữ liệu chính |
| Compensating transaction | Ghi nghiệp vụ mới để bù một thao tác trước đó | Có thể sửa hiệu ứng nghiệp vụ, nhưng không xóa lịch sử |
| Database point-in-time recovery (PITR) | Khôi phục database về một thời điểm | Có thể làm mất các giao dịch sau thời điểm đó nếu không replay/đối soát |

Ví dụ: phiên bản `2.4.0` ghi một đơn hàng thành công nhưng sau đó phát hiện tính thuế sai. Triển khai lại `2.3.5` chỉ đổi code xử lý request tiếp theo. Nó không tự sửa các đơn hàng đã ghi bởi `2.4.0`, cũng không xóa message đã publish. Nếu dữ liệu đã bị sai, cần một quy trình sửa dữ liệu hoặc bù nghiệp vụ riêng.

## 2. Vì sao checkpoint cũ có thể chứa trạng thái nghiệp vụ không hợp lệ?

Checkpoint là ảnh chụp trạng thái tiến trình, không phải snapshot nhất quán của toàn bộ hệ thống phân tán. Heap có thể chứa:

- Object nghiệp vụ được nạp trước checkpoint như đơn hàng, tồn kho hoặc trạng thái workflow.
- Cache được dựng từ database tại thời điểm trước đó.
- Session người dùng hoặc thông tin phân quyền đã thay đổi.
- Message đang được xử lý, offset hoặc cursor của consumer.
- Cờ leader, lease owner hoặc trạng thái distributed lock.
- Token, DNS result, địa chỉ service và kết nối phụ thuộc môi trường.
- Bộ đếm hoặc ID được tạo trong bộ nhớ thay vì từ nguồn cấp ID bền vững.

Trong lúc tiến trình không chạy, một Pod khác hoặc dịch vụ khác có thể cập nhật database, xử lý message, thay đổi quyền, thu hồi token hoặc nhận lease mới. Khi restore checkpoint cũ, object trong heap không tự động đồng bộ với những thay đổi đó.

Ví dụ, checkpoint lưu `inventoryAvailable = 5`. Trong thời gian Pod dừng, một replica khác bán hết 5 sản phẩm. Nếu Pod được restore tiếp tục dùng giá trị trong heap, nó có thể nhận thêm đơn hàng dựa trên tồn kho cũ. Nguồn tồn kho có thẩm quyền phải là database hoặc inventory service; cache trong heap cần được invalidated hoặc refresh trước khi phục vụ request.

## 3. Phân loại trạng thái trước khi quyết định tái sử dụng

Mỗi thành phần trong ứng dụng cần có quy tắc rõ ràng khi rollback:

| Loại trạng thái | Ví dụ | Cách xử lý khi rollback/restore |
|---|---|---|
| Cấu trúc bất biến | Route metadata, serializer metadata, object graph không chứa dữ liệu thay đổi | Có thể giữ nếu tương thích với release và runtime |
| Cache dẫn xuất | Giá sản phẩm, tồn kho, quyền, profile, cấu hình từ database | Invalidate hoặc refresh từ nguồn authoritative |
| Trạng thái workflow trong bộ nhớ | Đơn hàng đang xử lý, bước thanh toán, task đang chạy | Đối soát với durable store; resume bằng state machine và idempotency |
| Kết nối và resource hệ điều hành | Socket, connection pool, file descriptor, thread | Đóng trước checkpoint; tạo lại sau restore |
| Credential và session | Token, TLS context, session người dùng | Đọc/refresh theo chính sách hiện tại; kiểm tra version và expiry |
| Consumer/queue state | Offset, subscription, message in-flight | Đọc cursor bền vững, xác nhận/claim lại theo semantics broker |
| Leadership và lease | Leader flag, lock owner, lease deadline | Acquire/renew bằng identity hiện tại; dùng fencing token |
| Dữ liệu nghiệp vụ bền vững | Đơn hàng, thanh toán, ledger, inventory | Giữ nguồn authoritative; chỉ sửa bằng migration hoặc thao tác bù có kiểm soát |

Không có một lệnh tổng quát để xóa mọi object cũ trong heap. Hãy thiết kế các resource và cache provider để có thể refresh có chọn lọc, rồi chặn readiness cho tới khi những trạng thái bắt buộc đã được xác nhận.

## 4. Gắn checkpoint với đúng release

Checkpoint phải được quản lý như artifact bất biến và gắn với phiên bản đã tạo ra nó. Không chọn checkpoint chỉ dựa vào tên `latest` hoặc thư mục dùng chung có thể bị ghi đè.

Một release bundle nên ghi tối thiểu:

| Metadata | Mục đích |
|---|---|
| Application version và OCI image digest | Chọn đúng code và dependency đã build |
| JDK vendor/version và CRaC runtime version | Xác định runtime tạo checkpoint |
| OS, kernel/architecture và điều kiện restore | Kiểm tra khả năng tương thích nền tảng |
| Checkpoint ID và SHA-256 manifest | Chọn đúng snapshot và xác minh nội dung |
| Configuration version | Xác định cấu hình được dùng lúc tạo checkpoint |
| Database schema range | Xác định release có thể chạy với schema hiện tại |
| Event/message schema range | Xác định release có thể đọc dữ liệu đang nằm trong queue |
| Migration version | Theo dõi migration đã áp dụng tới đâu |

Ví dụ metadata phát hành:

```yaml
release:
  applicationVersion: "2.3.5"
  image: "registry.example.com/orders-api@sha256:..."
  jdk: "vendor-jdk-version"
  cracRuntime: "runtime-version"
  checkpointId: "orders-api-2.3.5-build-1842"
  checkpointManifestSha256: "..."
  configVersion: "orders-api-config-17"
  databaseSchema:
    minimum: 41
    maximum: 43
  eventSchema:
    readable: ["order.v1", "order.v2"]
    writable: ["order.v1"]
  migrationVersion: 43
```

Giá trị trong ví dụ chỉ minh họa schema metadata. Pipeline cần tạo các giá trị thật từ build và migration ledger. Checkpoint manifest cần được xác minh trước khi runtime đọc image.

Không restore checkpoint của `2.4.0` rồi cố chạy code `2.3.5` nếu hai bản không có hợp đồng tương thích được kiểm chứng. Heap snapshot có thể chứa object layout, class metadata, framework state và dữ liệu phụ thuộc code của phiên bản tạo checkpoint. Hãy sử dụng checkpoint được tạo bởi đúng build/runtime tương thích với image rollback. Nếu không có checkpoint tương thích, cold-start phiên bản cũ thường an toàn hơn việc ép restore một snapshot không đúng release.

## 5. Trạng thái nghiệp vụ phải được nạp lại từ nguồn authoritative

Sau khi restore, cần xác định dữ liệu nào là nguồn sự thật. Ví dụ:

- Số dư và giao dịch tài chính: ledger/database có transaction và audit trail.
- Đơn hàng: order database hoặc service sở hữu đơn hàng.
- Tồn kho: inventory service/database có cơ chế reserve/commit.
- Quyền truy cập: identity provider hoặc authorization store hiện hành.
- Trạng thái workflow: durable state machine, event store hoặc bảng job.
- Tiến độ consumer: broker offset/ack và bảng inbox/outbox.

Cache trong heap chỉ là bản sao dẫn xuất. Nếu checkpoint có thể chứa cache cũ, hãy invalidate cache trước khi mở admission hoặc nạp lại từ nguồn chính. Không dùng giá trị trong checkpoint làm fallback âm thầm khi nguồn authoritative không truy cập được, nếu điều đó có thể dẫn tới quyết định nghiệp vụ sai.

Với một số dữ liệu công khai hoặc bất biến, giữ cache có thể hợp lệ. Hãy gắn TTL/version và xác minh freshness. Với dữ liệu có tác động đến tiền, tồn kho, quyền hoặc trạng thái đơn hàng, cần chính sách nghiêm ngặt hơn và kiểm tra từ nguồn authoritative.

## 6. CRaC lifecycle cho trạng thái cần làm mới

Một `Resource` có thể đóng resource trước checkpoint và làm mới trạng thái sau restore:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class BusinessStateResource implements Resource {
    private final BusinessStateCache cache;
    private final ConnectionManager connections;
    private final LeaseManager leases;

    public BusinessStateResource(
            BusinessStateCache cache,
            ConnectionManager connections,
            LeaseManager leases) {
        this.cache = cache;
        this.connections = connections;
        this.leases = leases;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        cache.stopRefreshJobs();
        leases.releaseIfOwned();
        connections.close();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        connections.reconnect();
        cache.invalidateAll();
        cache.reloadCriticalEntries();
        leases.acquireOrConfirmCurrentLease();
    }
}
```

Đây là ví dụ kiến trúc; các API `BusinessStateCache`, `ConnectionManager` và `LeaseManager` là abstraction của ứng dụng. Thứ tự bên trong callback phải phản ánh dependency thực tế: nếu cache cần database, database phải được mở trước khi cache reload. Nếu lease service cần identity mới, identity cần được refresh trước lease manager.

`afterRestore` chỉ nên hoàn tất khi trạng thái bắt buộc đã hợp lệ. Nếu một cache tùy chọn chưa nạp được, có thể để nó warm-up nền nếu request path có fallback an toàn. Nếu inventory hoặc authorization chưa xác thực được, không mở readiness cho các chức năng phụ thuộc vào chúng.

## 7. Thay đổi schema database và khả năng chạy lùi

Một rollback code có thể thất bại nếu bản phát hành mới đã thay đổi schema theo cách phiên bản cũ không hiểu. Vì vậy, migration database phải được thiết kế cùng chiến lược release.

### 7.1. Expand-contract

Mẫu expand-contract chia thay đổi schema thành các bước tương thích:

1. **Expand:** thêm bảng/cột/index mới theo cách không phá vỡ code cũ; giữ các cột cũ.
2. **Deploy compatible code:** phiên bản mới có thể đọc/ghi schema mở rộng; phiên bản cũ vẫn chạy được trong thời gian rollback.
3. **Migrate data:** backfill dữ liệu theo batch, có checkpoint/cursor và có thể tiếp tục an toàn.
4. **Switch usage:** chuyển dần read/write sang schema mới, có quan sát và khả năng quay lại.
5. **Wait rollback window:** giữ schema cũ và compatibility cho tới khi không còn cần rollback về release cũ.
6. **Contract:** chỉ sau đó mới xóa cột, bảng hoặc constraint cũ.

Ví dụ thêm `display_name` trong khi code cũ vẫn dùng `full_name`:

```sql
-- Expand: thêm cột mới, chưa xóa cột cũ.
ALTER TABLE customer ADD COLUMN display_name VARCHAR(200);

-- Backfill theo batch trong migration riêng.
UPDATE customer
SET display_name = full_name
WHERE display_name IS NULL;
```

Sau khi mọi release cần rollback đã kết thúc vòng đời, một migration contract mới mới xóa `full_name`. Không chạy contract migration ngay trong cùng bước deploy đầu tiên nếu cần giữ khả năng rollback code.

### 7.2. Không tự động rollback migration khi rollback ứng dụng

`kubectl rollout undo` hoặc đổi image tag không tự hoàn tác migration database. Việc chạy migration ngược một cách tự động có thể làm mất dữ liệu được phiên bản mới ghi vào cột/bảng mới.

Trong phần lớn hệ thống, rollback ứng dụng nên chạy trên schema hiện tại nếu schema đó vẫn backward-compatible. Migration thường được thiết kế tiến về phía trước; rollback dữ liệu cần quyết định riêng. Nếu schema đã contract và code cũ không còn tương thích, lựa chọn an toàn có thể là forward-fix code thay vì deploy lại bản cũ.

### 7.3. Migration dữ liệu có thể tiếp tục hoặc đối soát

Backfill dài cần có:

- Cursor hoặc key range đã xử lý được lưu bền vững.
- Batch size và giới hạn tải.
- Idempotent update để chạy lại không tạo dữ liệu trùng.
- Metric số bản ghi thành công/thất bại và thời gian còn lại.
- Quy tắc xử lý bản ghi mới phát sinh trong lúc backfill.
- Kế hoạch rollback hoặc forward repair nếu migration dừng giữa chừng.

Không dựa vào một biến counter trong heap checkpoint làm cursor duy nhất cho migration nghiệp vụ. Lưu cursor trong database hoặc durable store để mọi release có thể tiếp tục từ trạng thái thực tế.

## 8. Tương thích event, queue và message

Rollback ứng dụng có thể đưa consumer về code cũ trong khi queue đã chứa message được producer phiên bản mới tạo. Nếu schema message không backward-compatible, consumer cũ có thể parse lỗi hoặc bỏ qua field quan trọng.

Hãy quản lý schema event như một hợp đồng độc lập:

- Thêm field mới theo hướng optional/default trước khi consumer cũ bị loại bỏ.
- Tránh đổi ý nghĩa hoặc tái sử dụng tên field cho semantics khác.
- Giữ consumer cũ đọc được version message mới trong rollback window.
- Dùng schema registry hoặc versioned envelope nếu hệ thống cần kiểm soát schema.
- Với event store, dùng upcaster để chuyển event cũ sang model đọc hiện tại; không sửa lịch sử event tùy tiện.
- Với queue, giữ acknowledgment/offset bền vững và idempotency để message có thể được redeliver.

Ví dụ envelope:

```json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "eventId": "evt-7b9d...",
  "occurredAt": "2026-11-13T07:30:00Z",
  "payload": {
    "orderId": "ord-123",
    "currency": "VND",
    "total": 250000
  }
}
```

Nếu phiên bản cũ chỉ hiểu `schemaVersion: 1`, nó cần có adapter/upcaster hoặc producer phải tiếp tục phát version cũ trong giai đoạn tương thích. Không giả định chỉ cần rollback consumer là message đã nằm trong queue sẽ tự đổi schema.

Đối với consumer đang xử lý message khi checkpoint, cần xác định rõ message đã ack chưa, transaction đã commit chưa và side effect có thể đã xảy ra chưa. Dùng inbox/outbox, idempotency key hoặc transaction tích hợp broker/database nếu có để tránh xử lý trùng khi restore hoặc rollback.

## 9. Cache, session và dữ liệu dẫn xuất

Cache thường là nơi dễ tái sử dụng nhầm trạng thái cũ nhất vì heap checkpoint giữ object mà không có lỗi kết nối rõ ràng. Cần gắn cache với version hoặc nguồn dữ liệu:

- Cache key có thể chứa tenant, schema version hoặc data generation.
- Cache value quan trọng nên có `loadedAt`, source version hoặc TTL.
- Sau restore, invalidate dữ liệu có thể thay đổi trong thời gian tiến trình dừng.
- Nạp lại critical cache trước readiness; cache không quan trọng có thể warm-up nền.
- Không để cache cũ ghi ngược dữ liệu đã lỗi thời lên nguồn authoritative.

Session người dùng cũng cần chính sách. Session trong heap hoặc local memory có thể đã hết hạn, bị thu hồi hoặc không còn khớp với version serialization mới. Dùng shared session store hoặc token validation hiện hành; không tin session cũ chỉ vì object vẫn tồn tại sau restore.

Nếu session format thay đổi giữa release, hãy version hóa serialization và hỗ trợ đọc nhiều version trong rollback window. Khi không thể chuyển đổi an toàn, buộc re-authentication là lựa chọn có thể chấp nhận hơn việc dùng session không tương thích.

## 10. Lease, leader election và distributed lock

Checkpoint có thể giữ `isLeader = true`, lease token hoặc lock handle trong heap. Khi Pod cũ bị dừng hoặc release bị rollback, lease có thể đã hết hạn và được instance khác lấy.

Sau restore hoặc rollback:

1. Không dùng cờ leader trong heap làm bằng chứng quyền sở hữu hiện tại.
2. Tạo lại client kết nối coordination service.
3. Đọc lease hiện tại từ nguồn authoritative.
4. Acquire/renew lease bằng instance identity hiện hành.
5. Dùng fencing token hoặc version tăng đơn điệu để ngăn owner cũ ghi sau owner mới.
6. Chỉ chạy job leader sau khi lease được xác nhận.

Nếu dùng Kubernetes Lease API, `holderIdentity` cần phản ánh Pod/process hiện tại, không copy giá trị từ checkpoint. Nếu dùng distributed lock trong database/Redis, cần TTL và fencing để tránh lock stale sau network partition hoặc process pause.

## 11. Quy trình rollback release có CRaC

Một quy trình rollback an toàn có thể chia thành các bước sau.

### Trước khi phát hành

1. Lưu image digest và checkpoint artifact bất biến của release đang chạy.
2. Giữ artifact release trước trong thời gian rollback window.
3. Xác minh checkpoint manifest, chữ ký, JDK/CRaC version, OS và architecture.
4. Kiểm tra compatibility matrix giữa release cũ/mới và database/event schema.
5. Áp dụng expand migration trước khi deploy code cần schema mới.
6. Có backup/PITR phù hợp với RPO/RTO và kiểm tra khả năng restore database.
7. Xác định các trạng thái trong heap phải invalidate/reload sau restore.

### Khi phát hiện release mới lỗi

1. Dừng rollout hoặc ngừng tăng traffic tới release lỗi.
2. Nếu lỗi có thể gây ghi dữ liệu sai, giới hạn hoặc tạm dừng các thao tác ghi bị ảnh hưởng.
3. Ghi nhận release ID, checkpoint ID, schema migration version và khoảng thời gian ảnh hưởng.
4. Chọn image digest của release ổn định trước đó.
5. Chọn checkpoint đúng build/runtime của release đó; nếu không có checkpoint tương thích, cold-start release cũ.
6. Không tự động chạy migration ngược chỉ vì code được rollback.
7. Sau restore, refresh identity, credentials, connection, cache, session, lease và queue cursor.
8. Đối soát các workflow đang chạy với durable store; dùng idempotency khi resume.
9. Chỉ mở readiness khi schema và trạng thái nghiệp vụ đã được xác nhận.
10. Theo dõi lỗi, latency, dữ liệu mới ghi và consumer lag sau rollback.

### Sau rollback

1. Xác định bản phát hành mới đã tạo dữ liệu sai hoặc chỉ gây lỗi xử lý.
2. Nếu có dữ liệu sai, tạo migration sửa hoặc compensating transaction có audit trail.
3. Nếu cần PITR, đánh giá giao dịch phát sinh sau mốc phục hồi và kế hoạch replay/đối soát.
4. Giữ lại log, event và checkpoint metadata để điều tra.
5. Không xóa artifact release lỗi cho tới khi hoàn tất phân tích và retention policy cho phép.

## 12. Kubernetes Deployment rollback

Deployment revision lưu Pod template, không lưu database snapshot hoặc CRaC checkpoint theo semantics nghiệp vụ. Có thể xem lịch sử và rollback template:

```bash
kubectl rollout history deployment/orders-api -n production
kubectl rollout undo deployment/orders-api -n production
kubectl rollout status deployment/orders-api -n production
```

Nếu cần chọn revision cụ thể:

```bash
kubectl rollout undo deployment/orders-api \
  --to-revision=12 \
  -n production
```

Lệnh rollback chỉ khôi phục Pod template của revision được chọn. Pipeline phải bảo đảm template đó tham chiếu image digest và checkpoint artifact đúng release. Nếu template cũ trỏ tới tag mutable hoặc checkpoint path `latest`, rollback có thể vô tình chạy artifact mới. Ưu tiên digest bất biến và checkpoint ID/version tường minh.

Sau `rollout undo`, Pod mới vẫn phải qua restore, refresh resource và readiness. Pod cũ có thể tiếp tục phục vụ trong lúc rollout nếu strategy cho phép; cần bảo đảm cả phiên bản cũ và mới cùng tương thích với schema/message trong giai đoạn overlap.

## 13. Ví dụ guard kiểm tra release/checkpoint compatibility

Một ứng dụng có thể lưu metadata release bên ngoài checkpoint và xác minh trước khi restore. Ví dụ Java minh họa kiểm tra application version và schema range:

```java
public record ReleaseDescriptor(
        String applicationVersion,
        String imageDigest,
        String checkpointId,
        String jdkVersion,
        String cracRuntimeVersion,
        int minDatabaseSchema,
        int maxDatabaseSchema) {
}

public final class CompatibilityGuard {
    public void verify(
            ReleaseDescriptor release,
            RuntimeDescriptor runtime,
            int currentDatabaseSchema) {

        if (!release.jdkVersion().equals(runtime.jdkVersion())) {
            throw new IllegalStateException("JDK version mismatch");
        }
        if (!release.cracRuntimeVersion().equals(runtime.cracRuntimeVersion())) {
            throw new IllegalStateException("CRaC runtime mismatch");
        }
        if (currentDatabaseSchema < release.minDatabaseSchema()
                || currentDatabaseSchema > release.maxDatabaseSchema()) {
            throw new IllegalStateException(
                    "Database schema is outside the supported range");
        }
    }
}
```

`RuntimeDescriptor` là abstraction cung cấp thông tin runtime thực tế. Trong triển khai, kiểm tra checkpoint manifest và image digest nên diễn ra ở entrypoint trước khi JVM restore; code trong heap không thể thay thế bước xác minh artifact trước khi runtime đọc nó. Guard sau restore có thể xác nhận database schema và các hợp đồng bên ngoài trước khi readiness bật.

Không nên chỉ so sánh chuỗi version nếu version không phản ánh build identity. Dùng image digest, build ID và checkpoint ID để xác định chính xác artifact. Nếu schema compatibility không thể biểu diễn bằng một khoảng số đơn giản, dùng capability/schema registry hoặc migration contract tường minh.

## 14. Trạng thái workflow đang chạy và tác dụng phụ

Rollback thường xảy ra khi release mới đã xử lý một phần request hoặc job. Một request có thể đã:

- Ghi database nhưng chưa trả response.
- Publish message nhưng chưa commit transaction.
- Gọi API thanh toán nhưng chưa ghi kết quả về database.
- Gửi email hoặc notification không thể thu hồi.
- Giữ lock hoặc reserve inventory trong thời gian giới hạn.

Khi quay lại phiên bản cũ, không thể chỉ khôi phục object request từ heap rồi chạy lại toàn bộ. Cần kiểm tra durable state để xác định bước nào đã commit. Với thao tác ghi, dùng idempotency key ổn định qua release và retry. Với quy trình nhiều dịch vụ, dùng saga/compensating action để bù các bước đã thành công.

Ví dụ, nếu cổng thanh toán đã capture tiền nhưng database chưa ghi `PAID`, không nên gửi capture lần nữa chỉ vì worker được restore. Hãy truy vấn payment provider bằng transaction/idempotency ID, đối soát kết quả rồi tiếp tục workflow.

## 15. Compensating transaction và Point-in-Time Recovery

Khi dữ liệu nghiệp vụ đã bị thay đổi sai, có hai nhóm phương án khác nhau.

### Compensating transaction

Tạo một giao dịch mới để bù tác dụng của giao dịch sai. Ví dụ, tạo refund cho payment đã capture sai hoặc ghi bút toán điều chỉnh vào ledger. Cách này giữ audit trail và phù hợp với hệ thống cần lịch sử bất biến.

Compensation phải idempotent, có trạng thái theo dõi và được phê duyệt theo quy tắc nghiệp vụ. Không xóa trực tiếp lịch sử giao dịch để làm dữ liệu trông như chưa từng xảy ra.

### Point-in-time recovery

PITR phục hồi database về một thời điểm trước lỗi. Nó có thể làm mất các transaction hợp lệ phát sinh sau thời điểm đó. Trước khi chọn PITR, cần xác định:

- RPO: lượng dữ liệu tối đa có thể chấp nhận mất.
- RTO: thời gian tối đa để dịch vụ phục hồi.
- Các transaction hợp lệ sau mốc PITR cần replay hay đối soát ra sao.
- Message broker, outbox, object storage và database có cùng mốc nhất quán hay không.
- Consumer offset và idempotency record cần điều chỉnh thế nào.

Không restore database về quá khứ trong khi queue và dịch vụ ngoài vẫn giữ trạng thái sau thời điểm đó mà không có kế hoạch reconciliation. Hệ thống phân tán cần phục hồi các nguồn dữ liệu liên quan theo một quy trình phối hợp.

## 16. Canary và rollback tự động

Canary rollout giảm phạm vi ảnh hưởng bằng cách đưa một phần traffic tới release mới trước. Với CRaC, canary Pod cần dùng checkpoint cùng release và được quan sát như Pod bình thường.

Các điều kiện rollback tự động có thể gồm:

- Tỷ lệ HTTP 5xx vượt ngưỡng trong cửa sổ đủ dài.
- p95/p99 latency tăng vượt SLO.
- Tỷ lệ restore failure hoặc readiness timeout tăng.
- Số lượng OOM/restart bất thường.
- Business invariant bị vi phạm, ví dụ tổng ledger không cân bằng hoặc tồn kho âm.
- Consumer lag hoặc dead-letter queue tăng bất thường.

Không nên tự động rollback chỉ vì một metric nhiễu trong một vài giây. Dùng cửa sổ đánh giá, baseline và ngưỡng theo mức độ ảnh hưởng. Với lỗi có nguy cơ ghi sai dữ liệu, ưu tiên dừng đường ghi bị ảnh hưởng ngay cả khi các metric hạ tầng vẫn bình thường.

Rollback tự động cần chọn release bundle bất biến và chạy cùng quy trình refresh/validation như rollback thủ công. Nó không được tự động revert schema hoặc khôi phục checkpoint cũ chứa dữ liệu nghiệp vụ stale.

## 17. Kiểm thử rollback trước production

Rollback phải được diễn tập với dữ liệu và schema gần production. Các tình huống cần thử:

1. Deploy release mới trên schema đã expand, sau đó rollback code cũ; xác nhận code cũ vẫn đọc/ghi được.
2. Tạo checkpoint của release cũ, cập nhật database từ replica khác, restore checkpoint cũ; xác nhận cache nghiệp vụ được invalidate/reload.
3. Thử dùng checkpoint của release mới với image cũ; compatibility guard phải từ chối trước restore.
4. Đưa message schema mới vào queue rồi rollback consumer; xác nhận consumer cũ đọc được hoặc message được route an toàn.
5. Dừng worker giữa một workflow có side effect; restore/rollback và xác nhận idempotency ngăn thao tác trùng.
6. Làm hết hạn lease trong lúc Pod dừng; xác nhận Pod không tiếp tục hành động như leader cũ.
7. Giả lập token hoặc certificate bị rotate; xác nhận resource refresh sau restore.
8. Mô phỏng migration backfill dừng giữa chừng; xác nhận cursor durable giúp tiếp tục.
9. Giả lập dữ liệu nghiệp vụ bị ghi sai; xác nhận quy trình compensation/PITR tách biệt với image rollback.
10. Chạy canary, kích hoạt rollback tự động và xác nhận Pod mới chỉ Ready sau compatibility check.

Kiểm thử cần xác nhận không chỉ Pod đã chạy mà cả invariant nghiệp vụ: không tạo đơn trùng, không capture payment hai lần, không bán vượt tồn kho, không mất message và không có hai leader cùng ghi.

## 18. Logging và audit trong rollback

Mỗi Pod sau restore nên ghi các trường có thể liên kết:

- Application version, build ID và OCI image digest.
- Checkpoint ID, manifest digest và runtime version.
- Pod UID, process run ID và deployment revision.
- Database schema/migration version.
- Event schema version hoặc consumer group/offset liên quan.
- Thời điểm bắt đầu rollback, restore, refresh và readiness.
- Kết quả cache invalidation, credential refresh, lease acquisition và reconciliation.
- Số workflow đang chạy, retry, compensation hoặc DLQ.

Không ghi token, secret hoặc payload nghiệp vụ nhạy cảm vào log. Dùng ID giao dịch hoặc correlation ID để đối soát trong hệ thống có quyền truy cập phù hợp.

## 19. Checklist rollback release

- [ ] Image digest và checkpoint artifact được ghép đúng release/build/runtime.
- [ ] Checkpoint manifest và chữ ký được xác minh trước restore.
- [ ] Có fallback cold-start nếu không có checkpoint tương thích.
- [ ] Pod không dùng cache nghiệp vụ stale từ heap checkpoint.
- [ ] Database schema hiện tại vẫn tương thích với release rollback.
- [ ] Migration destructive/contract chưa chạy trong rollback window.
- [ ] Event/message schema vẫn được consumer cũ hỗ trợ.
- [ ] Consumer offset, in-flight message và workflow được đối soát.
- [ ] Socket, connection pool, token, DNS và subscription được refresh.
- [ ] Lease/leader election được acquire lại bằng identity mới và fencing token.
- [ ] Readiness chỉ bật sau khi dependency và business state hợp lệ.
- [ ] Image rollback không bị nhầm với data rollback.
- [ ] Có kế hoạch compensating transaction hoặc PITR nếu dữ liệu đã sai.
- [ ] Đã diễn tập rollback và kiểm tra business invariants.
- [ ] Log/audit liên kết release, checkpoint, schema và Pod identity.

## 20. Tài liệu tham khảo

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rollout, revision history và rollback Pod template.
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): readiness, startup và liveness trong vòng đời Pod.
- [CRaC Project](https://crac.org/): checkpoint/restore và quản lý tài nguyên trước/sau restore.
- [CRaC API — `Resource`](https://javadoc.io/doc/org.crac/crac/latest/org/crac/Resource.html): callback quản lý resource qua checkpoint và restore.
- [Martin Fowler — Parallel Change](https://martinfowler.com/bliki/ParallelChange.html): kỹ thuật expand-contract để thay đổi schema mà vẫn tương thích trong giai đoạn chuyển tiếp.
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/): danh tính và storage cho workload stateful.

Rollback an toàn là đưa code về một release đã biết ổn định trong khi vẫn tôn trọng trạng thái hiện tại của hệ thống. Hãy ghép image với checkpoint đúng build/runtime, giữ schema và message contract tương thích trong rollback window, rồi refresh cache, credential, connection, lease và workflow state từ nguồn authoritative sau restore. Nếu dữ liệu nghiệp vụ đã bị ghi sai, xử lý bằng migration sửa, compensating transaction hoặc PITR có kế hoạch riêng; đổi lại image hay restore heap cũ không thể tự hoàn tác các tác dụng phụ đã xảy ra.
