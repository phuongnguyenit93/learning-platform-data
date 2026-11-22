# Operation có tác dụng phụ và yêu cầu xác nhận trong Spring Framework JMX

## Mục tiêu

Trong JMX, một operation có thể là lệnh đọc, chẩn đoán hoặc điều khiển. Với Spring Framework, annotation \`@ManagedOperation\` giúp đưa phương thức Java lên bề mặt quản trị MBean. Tuy nhiên, việc phương thức xuất hiện trong JConsole hoặc một JMX client không nói gì về **mức độ an toàn của tác động**. Một lời gọi như \`resetCounters()\`, \`clearCache()\`, \`pauseConsumers()\`, \`reloadConfiguration()\` hoặc \`forceReconnect()\` có thể ảnh hưởng đến trạng thái runtime, tính liên tục của dữ liệu quan sát, tải của dependency và cả quá trình xử lý nghiệp vụ.

Với operation có tác dụng phụ, cần xác định chính xác **điều gì thay đổi, ai được phép yêu cầu thay đổi, cơ chế xác nhận thực hiện ở đâu, và kiểm chứng kết quả như thế nào**. Không nên xem hộp thoại “Are you sure?” là toàn bộ giải pháp: xác nhận chỉ là một lớp trong quy trình quản trị, còn hệ thống thực thi vẫn cần phân quyền, kiểm tra điều kiện trước, kiểm soát việc gọi lặp và lưu dấu vết.

Sau bài học, bạn có thể:

- Phân biệt operation quan sát/chẩn đoán với operation có tác dụng phụ, kể cả những method có tên gây hiểu lầm.
- Mô tả tác dụng phụ theo phạm vi, khả năng đảo ngược, tính lặp lại và hậu quả khi chạy nhầm.
- Hiểu rằng \`@ManagedOperation\` chỉ công bố operation, không tự thêm xác thực, phân quyền hay hộp thoại xác nhận.
- Thiết kế cơ chế xác nhận phù hợp cho client thao tác thủ công và script tự động.
- Áp dụng mô hình yêu cầu → chuẩn bị/xác nhận → thực thi → kiểm chứng, bao gồm timeout, race condition và audit.
- Viết MBean quản trị có input validation, state/version precondition và mã yêu cầu để hạn chế thực thi ngoài ý muốn.
- Lập runbook cho các lệnh reset, reload, pause, resume, reconnect hoặc thay đổi tham số runtime.

## 1. Một operation JMX có thể tạo tác dụng phụ ở nhiều tầng

JMX client gọi operation bằng \`MBeanServerConnection.invoke(ObjectName, String, Object[], String[])\`. Khi MBean được Spring export, lời gọi được chuyển tới phương thức quản trị tương ứng theo metadata.

\`\`\`text
JMX Client
   |
   | invoke(ObjectName, operationName, params, signature)
   v
MBeanServer / JMX Connector
   |
   v
Spring-managed MBean / @ManagedOperation
   |
   +--> thay đổi bean state
   +--> gọi service nội bộ
   +--> sửa cấu hình runtime
   +--> làm sạch cache
   +--> tạo network request
   +--> kích hoạt tác vụ bất đồng bộ
\`\`\`

Một phương thức có thể có nhiều tác dụng phụ đồng thời:

| Operation ví dụ | Tác dụng trực tiếp | Hậu quả thứ cấp có thể xảy ra |
|---|---|---|
| \`resetStatistics()\` | Đặt lại counter trong bộ nhớ | Mất baseline chẩn đoán; dashboard có discontinuity |
| \`clearCache()\` | Evict dữ liệu cache | Tăng tải DB/downstream do cache miss |
| \`requestPause()\` | Đặt pause intent | Backlog tăng; timeout hoặc SLA bị ảnh hưởng |
| \`setLogLevel("DEBUG")\` | Thay mức log runtime | I/O và dung lượng log tăng; có nguy cơ lộ dữ liệu |
| \`forceReconnect()\` | Đóng và mở lại connection | Request đang chạy lỗi, retry tăng tải |
| \`reloadConfiguration()\` | Đọc lại cấu hình | Thay đổi hành vi của request mới, có thể ảnh hưởng mọi tenant |
| \`drainQueue()\` | Tiếp tục xử lý tồn đọng | Tăng áp lực lên các hệ thống phụ thuộc |
| \`runDiagnostics()\` | Quét trạng thái hệ thống | CPU, heap, lock hoặc network bị sử dụng |

Vì vậy, “tác dụng phụ” không chỉ là ghi database. Một lệnh **chỉ thay đổi metric**, **đặt cờ điều khiển**, **gửi notification**, **khởi tạo probe tốn tài nguyên** hoặc **thay đổi cách dịch vụ phục vụ request** đều đáng được phân tích.

## 2. Phân loại mức tác động trước khi yêu cầu xác nhận

Không phải mọi operation đều cần cùng mức xác nhận. Hãy mô tả tác động theo ít nhất bốn chiều:

1. **Phạm vi**: một bean, một thread pool, một JVM, một tenant, một shard hay cả cluster?
2. **Khả năng đảo ngược**: có thể phục hồi ngay, cần chờ hội tụ, hay dữ liệu đã mất vĩnh viễn?
3. **Tính lặp lại**: gọi nhiều lần có tạo side effect mới không?
4. **Mức ảnh hưởng**: chỉ chi phí nhỏ, giảm chất lượng dịch vụ, gián đoạn xử lý hay thay đổi dữ liệu quan trọng?

Bảng gợi ý chính sách:

| Loại thao tác | Ví dụ | Chính sách hợp lý |
|---|---|---|
| Read-only nhẹ | \`getQueueDepth()\` | Quyền đọc và giới hạn dữ liệu |
| Chẩn đoán có chi phí | \`captureThreadSummary()\` | Giới hạn tài nguyên, timeout và rate limit |
| Điều khiển hồi phục dễ | \`requestPause()\` | Quyền điều khiển, tiền điều kiện, xác minh effective state |
| Điều khiển ảnh hưởng rộng | \`clearAllCaches()\` | Xác nhận có phạm vi, audit và kế hoạch rollback |
| Thao tác khó đảo ngược | \`purgeDeadLetterQueue()\` | Quy trình phê duyệt nghiệp vụ độc lập; có thể không nên export qua JMX |

Đây là khung tư duy, không phải quy tắc rằng “đã có xác nhận thì an toàn”. Với operation nguy hiểm, lựa chọn đúng có thể là **không đưa operation đó vào MBean**, hoặc chỉ công bố một yêu cầu được kiểm tra và thực thi qua kênh vận hành có kiểm soát.

## 3. @ManagedOperation cung cấp điều gì?

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=CacheAdmin,name=Catalog",
    description = "Catalog cache management")
public class CacheAdmin {

    @ManagedOperation(
        description = "Clear all catalog cache entries")
    public void clearAll() {
        // gọi cacheService.clearAll() trong ứng dụng thực tế
    }
}
\`\`\`

Khi Spring exporter được bật, method \`clearAll\` có thể xuất hiện như một operation của MBean. Nhưng annotation **không tự thêm**:

- Authentication cho JMX connection.
- Authorization theo role, tenant hay hành động.
- Hộp thoại xác nhận.
- Idempotency hoặc chống double-click.
- Transaction hoặc rollback.
- Rate limit, timeout và audit trail.
- Chặn execution nếu một operator khác vừa thay đổi trạng thái.

Mô tả \`description = "Dangerous operation"\` giúp con người hiểu tác động, nhưng chỉ là metadata; một script vẫn có thể gọi trực tiếp mà không đọc description.

\`@ManagedOperation\` là **lớp công bố hợp đồng**, còn chính sách thực thi cần được thiết kế ở application/service và boundary truy cập.

## 4. Xác nhận ở client và kiểm tra tại server là hai việc khác nhau

Một giao diện quản trị có thể hiển thị hộp thoại:

> Bạn đang yêu cầu xóa cache Catalog trên instance A. Hành động có thể làm tăng tải database. Xác nhận?

Điều này hữu ích khi con người thao tác thủ công, nhưng JMX API không bắt buộc mọi client đi qua cùng UI. JConsole, custom client, script CI hoặc JMX connector khác có thể gọi operation theo cách riêng. Do đó:

\`\`\`text
Xác nhận tại UI
   |
   | giúp operator nhận biết hậu quả
   v
Yêu cầu JMX
   |
   v
Authorization + validation + precondition tại server
   |
   v
Thực thi
   |
   v
Audit + đọc lại trạng thái
\`\`\`

**Xác nhận phía client** giải quyết vấn đề thao tác vô ý. **Kiểm tra phía server** giải quyết vấn đề quyền, dữ liệu đầu vào, trạng thái hiện hành và ảnh hưởng thực tế. Không đặt an toàn hệ thống lên giả định tất cả người gọi đều dùng một UI có xác nhận.

### 4.1 Metadata không phải enforcement

Một operation có mô tả đầy đủ, tham số tên rõ ràng và cảnh báo trong runbook vẫn có thể bị gọi từ script thiếu kiểm soát. Các thành phần bắt buộc cho lệnh điều khiển quan trọng nên được thực thi ở server: validate input, chống trạng thái không hợp lệ, ghi nhận mã yêu cầu và kiểm soát quyền phù hợp với JMX access boundary.

### 4.2 Tránh dùng tham số boolean \`confirmed\` làm lớp bảo vệ duy nhất

Mẫu dễ gây ngộ nhận:

\`\`\`java
@ManagedOperation
public void clearAll(boolean confirmed) {
    if (!confirmed) throw new IllegalArgumentException("confirm first");
    cache.clear();
}
\`\`\`

Bất cứ client nào có quyền gọi cũng có thể truyền \`true\`. Tham số đó chỉ là dấu hiệu lựa chọn của người gọi, **không chứng minh** một người có thẩm quyền đã đọc tác động hoặc xác nhận thao tác. Nó cũng không ngăn retry trùng sau timeout.

Nếu một operation cần độ bảo vệ cao, sử dụng quy trình phê duyệt/ủy quyền có identity, scope, TTL và audit được kiểm soát tại phía server hoặc nền tảng vận hành.

## 5. Phân biệt preview, confirmation và execution

Một cách thiết kế an toàn hơn là tách việc **đánh giá tác động** khỏi **thực thi**.

\`\`\`text
1. Operator chọn thao tác và phạm vi
2. Hệ thống chuẩn bị bản đánh giá hiện trạng
3. Operator xem:
   - target
   - phạm vi
   - đối tượng bị ảnh hưởng
   - điều kiện trước
   - thời gian/chi phí dự kiến
4. Operator xác nhận theo cơ chế được hệ thống hỗ trợ
5. Server xác minh lại quyền và trạng thái
6. Thực thi hoặc từ chối do trạng thái đã thay đổi
7. Đọc lại effective state và audit record
\`\`\`

Ví dụ tác động cần preview đối với \`evictCacheRegion(String region)\`:

\`\`\`text
Target instance: inventory-02
Operation: evictCacheRegion
Region: product-details
Current entries: 128,420
Expected effect: cache misses increase until warm-up
Precondition: region exists and no cache rebuild in progress
Recovery: automatic refill, no instant rollback
\`\`\`

Đây là thông tin tại **thời điểm preview**, có thể đã thay đổi khi người dùng bấm xác nhận. Với operation nhạy cảm, confirmation nên gắn với trạng thái/phiên bản hoặc expiry, và server kiểm tra lại trước execution.

### 5.1 Preview không nhất thiết là operation “read-only” nhẹ

Một preview có thể cần quét hàng triệu key hoặc query dữ liệu bên ngoài. Hãy giới hạn số lượng, timeout và kích thước kết quả. Thông tin ước tính nên có timestamp và được ghi rõ là approximate nếu phù hợp.

## 6. Thiết kế state/version precondition để tránh xác nhận trên dữ liệu lỗi thời

Giả sử một operator đọc:

\`\`\`text
workerState = RUNNING
version = 41
\`\`\`

Sau đó một operator khác đã pause worker và tăng version lên 42. Nếu lệnh cũ tiếp tục chạy mà không kiểm tra precondition, một hành động có thể dựa trên snapshot không còn đúng.

Thiết kế operation có expected version:

\`\`\`java
public interface WorkerControlMBean {
    String getState();
    long getStateVersion();
    boolean requestPause(long expectedVersion);
}
\`\`\`

Implementation minh họa:

\`\`\`java
import java.util.concurrent.locks.ReentrantLock;

public final class WorkerControl implements WorkerControlMBean {

    private final ReentrantLock lock = new ReentrantLock();
    private String state = "RUNNING";
    private long version;

    @Override
    public String getState() {
        lock.lock();
        try {
            return state;
        } finally {
            lock.unlock();
        }
    }

    @Override
    public long getStateVersion() {
        lock.lock();
        try {
            return version;
        } finally {
            lock.unlock();
        }
    }

    @Override
    public boolean requestPause(long expectedVersion) {
        lock.lock();
        try {
            if (version != expectedVersion) {
                return false;
            }
            if (!"RUNNING".equals(state)) {
                return false;
            }
            state = "PAUSE_REQUESTED";
            version++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
\`\`\`

Điểm cần hiểu: \`true\` ở đây chỉ báo **yêu cầu pause đã được chấp nhận ở trạng thái hiện tại**, chưa chứng minh worker đã dừng nhận job. Một worker loop thực tế phải áp dụng pause ở điểm an toàn rồi cập nhật \`effectiveState\`. Nếu cần atomic preview của state và version, cung cấp snapshot duy nhất thay vì đọc hai attribute lần lượt có thể bị race.

Các điều kiện có thể gồm expected state, version, generation ID, thời gian hết hạn của preview hoặc target instance. Cách chọn phụ thuộc vào loại operation; đừng thêm version chỉ để phức tạp hóa một lệnh quan sát vô hại.

## 7. Phân biệt request được nhận và side effect đã hoàn tất

Với operation bất đồng bộ:

\`\`\`java
@ManagedOperation(description = "Request cache rebuild")
public String requestCacheRebuild(String region) {
    // enqueue job và trả ID
    return "operation-123";
}
\`\`\`

Kết quả trả về ID chỉ có nghĩa hệ thống chấp nhận/ghi nhận yêu cầu theo hợp đồng. Cần một cách kiểm tra:

\`\`\`text
getOperationStatus("operation-123")
  -> ACCEPTED
  -> RUNNING
  -> SUCCEEDED / FAILED / CANCELLED
\`\`\`

Thao tác đồng bộ có thể trả số bản ghi bị ảnh hưởng hoặc trạng thái cuối cùng; thao tác bất đồng bộ nên trả operation ID và công bố cách poll trạng thái/notification phù hợp.

Khi có side effect không đảo ngược, client không được diễn giải “JMX invoke timeout” là “lệnh chưa thực hiện”. Server có thể đã chạy xong nhưng phản hồi bị mất. Cần kiểm tra operation ID hoặc trạng thái thực tế trước khi gửi lại.

## 8. Idempotency và duplicate execution

Một người dùng có thể nhấn hai lần, một script retry sau timeout, hoặc hai operator cùng gọi operation.

### 8.1 Các loại hành động khác nhau

| Operation | Gọi lại có thể an toàn? | Vấn đề thực tế |
|---|---|---|
| \`requestPause()\` | Thường có thể idempotent về state | Vẫn có thể gián đoạn dịch vụ khi gọi sai thời điểm |
| \`setLogLevel("INFO")\` | Có thể đưa về cùng cấu hình | Thay đổi log level khác đang diễn ra |
| \`clearCache()\` | Không đảm bảo side effect như nhau | Cache refill bị kích hoạt nhiều lần |
| \`rotateCredential()\` | Không nên retry mù | Có thể xoay khóa hai lần và làm hỏng client |
| \`resetStatistics()\` | Kết quả giá trị giống nhau | Mất dấu vết ở thời điểm khác nhau |

**Idempotent về giá trị cuối** không đồng nghĩa **không có tác dụng phụ khi gọi lặp**.

### 8.2 Request ID cho operation quan trọng

Một operation cần chống duplicate có thể nhận mã yêu cầu:

\`\`\`java
String requestRefresh(String region, String requestId);
String getRequestStatus(String requestId);
\`\`\`

Server giữ record theo request ID và phạm vi phù hợp, trả kết quả của request đã có thay vì chạy lại nếu request trùng. Cần xác định retention, concurrency, restart behavior và cơ chế xử lý khi cùng ID được gửi với tham số khác. Nếu request phải đảm bảo qua JVM restart, trạng thái idempotency phải lưu bền vững, không chỉ ở memory.

JMX chỉ cung cấp invocation mechanism; nó không tự cấp exactly-once execution cho operation của bạn.

## 9. Authorization, quyền thao tác và audit

Ngay cả khi MBean có một operation nguy hiểm, không phải mọi người được đọc metric đều phải được thực thi nó.

Một thiết kế quản trị cần:

- Xác thực JMX connector hoặc kênh truy cập.
- Phân biệt quyền quan sát với quyền gọi operation điều khiển.
- Giới hạn endpoint JMX ở mạng quản trị, dùng mã hóa phù hợp.
- Giảm phạm vi operation được công bố qua MBean.
- Kiểm tra authorization trên request theo identity và scope nếu loại lệnh yêu cầu.
- Ghi audit ai, khi nào, trên target nào, operation nào, tham số nào sau redaction, kết quả nào.
- Tách quản lý MBean của ứng dụng khỏi quyền quản trị toàn JVM nếu hệ thống hỗ trợ.

Spring \`@ManagedOperation\` không tự áp dụng Spring Security của HTTP endpoint lên JMX connector. Trong một số thiết lập, JMX access control chỉ phân biệt quyền đọc/ghi ở mức thô; cần kiểm tra khả năng bảo vệ operation cụ thể của connector hoặc dùng một kênh điều khiển riêng nếu cần quyền chi tiết.

### 9.1 Audit là gì?

Một bản ghi quản trị hữu ích có thể gồm:

\`\`\`text
timestamp: 2026-01-01T10:15:20Z
actor: operator-id-from-trusted-authentication
target: inventory-02 / CatalogCache
operation: requestRefresh
scope: region=product-details
requestId: 9a7f...
previousState: IDLE
decision: ACCEPTED
finalState: SUCCEEDED
durationMs: 8200
\`\`\`

Đây là ví dụ cấu trúc; không ghi raw credential, token hoặc payload có dữ liệu cá nhân. Với operation bất đồng bộ, có thể cần hai bản ghi: request được chấp nhận và kết quả thực thi cuối cùng.

Nếu một JMX access path không đưa trusted identity vào application method, đừng để caller tự truyền chuỗi \`actor\` rồi coi đó là danh tính đã xác thực. Identity/audit nên được cấp bởi boundary đáng tin cậy, không phải một tham số tự khai báo.

## 10. Ví dụ Spring: operation có xác minh điều kiện trước và kết quả rõ ràng

Thiết kế một lớp quản trị cho việc bật chế độ bảo trì cục bộ. Nó công bố trạng thái read-only và operation thay đổi trạng thái có expected version. Ví dụ không thể hiện đầy đủ authentication/authorization; các lớp đó cần cấu hình ở kết nối JMX và tầng điều khiển phù hợp.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Maintenance,name=Primary",
    description = "Controlled runtime maintenance switch")
public class MaintenanceControl {

    private boolean maintenance;
    private long version;

    @ManagedAttribute(description = "Current local maintenance state")
    public synchronized boolean isMaintenance() {
        return maintenance;
    }

    @ManagedAttribute(description = "State generation number")
    public synchronized long getVersion() {
        return version;
    }

    @ManagedOperation(
        description = "Set maintenance only if expectedVersion matches")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "enabled",
            description = "Desired maintenance state"),
        @ManagedOperationParameter(
            name = "expectedVersion",
            description = "Version observed by operator")
    })
    public synchronized String setMaintenance(
            boolean enabled, long expectedVersion) {
        if (expectedVersion != version) {
            return "REJECTED_STALE_STATE";
        }
        if (maintenance == enabled) {
            return "UNCHANGED";
        }
        maintenance = enabled;
        version++;
        return "APPLIED";
    }
}
\`\`\`

Trong ứng dụng thật, đây mới là control state nội bộ của bean. Để đạt **effective maintenance**, request routing/service layer phải thực sự tôn trọng flag; nếu chuyển trạng thái bất đồng bộ, cần tách \`requestedMaintenance\` khỏi \`effectiveMaintenance\`. Nếu có nhiều instance, mỗi MBean thường chỉ điều khiển một JVM; cluster-wide maintenance cần cơ chế phối hợp khác.

Lưu ý thêm: việc đọc \`maintenance\` và \`version\` riêng có thể gặp race giữa hai lời gọi. Trong workflow cần xác nhận chặt chẽ, cung cấp snapshot gắn kết hoặc operation chuẩn bị có precondition token.

## 11. Mô hình xác nhận hai pha với token ngắn hạn

Đối với thao tác có ảnh hưởng đáng kể, có thể thiết kế:

\`\`\`text
previewEviction(region)
  -> planId, target, impactSummary, expectedVersion, expiresAt

executeEviction(planId)
  -> operationId / accepted-or-rejected
\`\`\`

Một hệ thống thực tế cần lưu server-side plan và kiểm tra:

1. Plan gắn với hành động/target/scope cụ thể.
2. Plan có thời hạn ngắn.
3. Caller hiện tại có quyền thực thi action.
4. Version/precondition vẫn hợp lệ.
5. Plan chưa được tiêu thụ hoặc duplicate có hành vi được định nghĩa.
6. Việc đánh dấu tiêu thụ và bắt đầu tác vụ được xử lý nguyên tử theo mục tiêu.
7. Mọi kết quả được audit.

**Plan token tự nó không phải bằng chứng phê duyệt.** Nếu bất cứ JMX client nào cũng có thể gọi \`preview\` rồi \`execute\` mà không có authorization, quy trình hai pha chỉ giúp chống thao tác nhầm hoặc stale state, không bảo vệ trước caller không được phép.

Ví dụ không nên lưu toàn bộ secret hoặc thông tin nhạy cảm trong plan summary do JMX trả về. Một preview phải đủ thông tin cho operator nhưng giới hạn dữ liệu.

### 11.1 Khi nào không nên đưa confirmation token vào JMX?

Nếu hệ thống đã có control plane/approval workflow chuẩn cho production, nên dùng nó để điều phối thao tác có rủi ro cao. JMX lúc đó có thể chỉ công bố read-only trạng thái và kết quả, hoặc nhận một request đã được ủy quyền từ control plane. Không cần xây dựng một cơ chế phê duyệt riêng yếu hơn chỉ để có thể bấm lệnh từ JConsole.

## 12. Tác dụng phụ do operation chẩn đoán

Một nhóm operation thường bị đánh giá thấp là \`diagnose\`:

\`\`\`java
@ManagedOperation
public String dumpRecentErrors(int limit) { ... }
\`\`\`

Nếu implementation:
- Query database.
- Quét dữ liệu lớn.
- Serialize graph object.
- Đọc raw request payload.
- Trigger remote probe.
- Gây stop-the-world pause do lấy snapshot nặng.

thì nó vẫn là operation có tác dụng phụ tài nguyên hoặc nguy cơ thông tin. Không nhất thiết cần hộp thoại xác nhận của destructive operation, nhưng cần **timeout, giới hạn kích thước, rate limit, redaction và quyền phù hợp**.

Tên bắt đầu bằng \`get\` không đủ để kết luận method chỉ đọc nhẹ. Mọi operation có chi phí cao nên có tài liệu mô tả ảnh hưởng và cách hạn chế.

## 13. Các tình huống cụ thể

### 13.1 Reset metric trước khi thu thập bằng chứng

**Tình huống:** CPU tăng đột ngột; operator muốn gọi \`resetCounters()\` để “làm sạch dashboard”.

**Rủi ro:** reset mất dấu vết cần chẩn đoán, tạo đường gãy trong time series.

**Thiết kế tốt hơn:** snapshot hoặc xuất metric trước khi reset; giới hạn quyền reset; nêu rõ loại counter, phạm vi và thời điểm reset. Nếu chỉ cần xem tỷ lệ trong một khoảng thời gian, dùng metrics time series phù hợp thay vì reset để tính toán.

### 13.2 Clear cache trên nhiều node

**Tình huống:** một cache có dữ liệu lỗi thời, operator gọi \`clearAllCaches()\` trên ba node.

**Rủi ro:** nhiều node đồng thời cache miss, gây tải đột biến cho database.

**Thiết kế tốt hơn:** xác định cache region/key cần xóa, thực hiện từng node hoặc theo đợt, theo dõi hit ratio/DB latency, có điều kiện dừng rollout. Nếu cache phân tán, xác định rõ phạm vi operation; không suy luận mọi node có cache độc lập.

### 13.3 Thay log level runtime

**Tình huống:** bật DEBUG để tìm lỗi.

**Rủi ro:** log volume tăng, có thể ghi thông tin nhạy cảm và ảnh hưởng I/O.

**Thiết kế tốt hơn:** chỉ cho phép logger được duyệt, có thời hạn tự hết và khôi phục giá trị cũ, audit người thực hiện và kiểm tra effective log level.

### 13.4 Reconnect tới downstream

**Tình huống:** connection tới dịch vụ ngoài lỗi, operator gọi \`forceReconnect()\`.

**Rủi ro:** cắt request còn đang xử lý, retry storm và mất trạng thái phiên.

**Thiết kế tốt hơn:** kiểm tra circuit breaker/health, xác định mục tiêu, giới hạn concurrent reconnect, trả operation ID, theo dõi trạng thái connection sau thay đổi.

### 13.5 Pause/resume worker

**Tình huống:** queue backlog tăng và dependency quá tải.

**Rủi ro:** pause sai khiến SLA trễ; resume đồng loạt tăng tải.

**Thiết kế tốt hơn:** có requested/effective state, điều kiện trước, giới hạn thay đổi concurrency, audit và quy trình phục hồi. Nếu lệnh ảnh hưởng toàn cụm, dùng điều phối thay vì gọi từng MBean không kiểm soát.

## 14. Vì sao “một lần xác nhận” không đủ?

Xét chuỗi sự kiện:

\`\`\`text
T0: Operator xem preview: 1,000 cache entries
T1: Một job khác thêm 50,000 entries
T2: Operator xác nhận
T3: Server xóa toàn bộ 51,000 entries
\`\`\`

Operator đã xác nhận một phạm vi khác với thực tế ở thời điểm thực thi. Một cách bảo vệ là yêu cầu version, scope giới hạn hoặc ngưỡng tác động:

\`\`\`text
executeEviction(planId, maxAffectedEntries)
\`\`\`

Server từ chối nếu phạm vi đã thay đổi quá mức được phê duyệt. Với một số hành động không thể biết trước chính xác số lượng, có thể dùng giới hạn tác động, batching và khả năng dừng, cùng thông tin “ước lượng” được công bố rõ.

Điểm thiết kế không nằm ở số lần bấm xác nhận mà là **xác nhận phải ràng buộc với điều được phép thực thi**.

## 15. Kiểm tra và quan sát sau thao tác

Mỗi lệnh quản trị nên có một cách chứng minh kết quả độc lập với response ban đầu.

| Operation | Kiểm chứng sau khi gọi |
|---|---|
| \`requestPause()\` | \`RequestedState\`, \`EffectiveState\`, số job mới được nhận |
| \`clearCache(region)\` | Size/hit ratio của đúng region, downstream load |
| \`setLogLevel(...)\` | Effective log level, tốc độ log, thời hạn khôi phục |
| \`requestRefresh(...)\` | Operation status, timestamp refresh thành công |
| \`forceReconnect()\` | Connection state, lỗi request, số retry |
| \`resetStatistics()\` | Counter reset marker/time và baseline mới |

Một operation trả \`"SUCCESS"\` không đủ nếu hệ thống chưa chuyển sang trạng thái kỳ vọng. Với lệnh bất đồng bộ, cần trạng thái hiệu lực hoặc event hoàn thành. Nếu telemetry không có, operator không thể phân biệt “lệnh được chấp nhận” và “lệnh có hiệu quả”.

## 16. Runbook cho operation có tác dụng phụ

Trước khi gọi:

1. Chỉ rõ target và phạm vi: JVM, component, resource, tenant, cluster.
2. Đọc trạng thái và thu thập bằng chứng hiện tại.
3. Kiểm tra tác dụng phụ, giới hạn, quyền và khả năng phục hồi.
4. Có kế hoạch dừng/rollback nếu thao tác có thể gây ảnh hưởng.
5. Nếu cần approval, hoàn tất bằng workflow có identity và audit.
6. Ghi lại expected state/version và yêu cầu duy nhất nếu có.

Khi gọi:

1. Dùng đúng operation name/signature và tham số giới hạn.
2. Không retry mù nếu timeout hoặc kết quả không rõ.
3. Chú ý operation ID, trạng thái accepted/rejected và error.
4. Nếu có phiên bản trạng thái, xử lý stale-state rejection bằng cách đọc lại thay vì ép thực thi.

Sau khi gọi:

1. Đọc lại trạng thái hiệu lực/metric, không chỉ thông báo trả về.
2. Kiểm tra downstream và tác dụng thứ cấp.
3. Ghi kết quả cuối cùng kèm thời điểm, target và request ID.
4. Nếu không đạt mục tiêu, thực hiện recovery theo runbook và quyền hạn đã định.

## 17. Những nhầm lẫn thường gặp

**“@ManagedOperation tự hỏi xác nhận.”** Không. Annotation công bố operation và metadata; xác nhận do client hoặc workflow riêng thiết kế.

**“Thêm tham số confirmed=true là bảo mật.”** Không. Caller tự đặt giá trị này; authorization phải dựa trên danh tính và quyền thực.

**“Operation return void thì không có cách biết đã chạy.”** Có thể bổ sung effective state, operation status, metric và audit. Đừng dựa riêng vào return type.

**“Chỉ lệnh xóa dữ liệu mới cần kiểm soát.”** Thay log level, restart connector, pause worker hoặc reset metric đều có thể có hậu quả lớn.

**“Timeout tức là lệnh chưa thực hiện.”** Không. Có thể side effect đã xảy ra nhưng response bị mất.

**“Idempotent nên gọi lại thoải mái.”** Một lệnh idempotent về giá trị cuối vẫn có thể gây I/O, tải hoặc gián đoạn lặp lại.

**“Xác nhận ở UI thay thế phân quyền phía server.”** Không. Client khác có thể gọi trực tiếp qua JMX connection.

**“Một thao tác trên MBean áp dụng toàn cluster.”** Thường MBean thuộc một JVM; phạm vi cần được thiết kế và công bố.

## 18. Bài tập vận dụng

### Bài 1: phân loại tác dụng phụ

Cho các operation:

\`\`\`java
String diagnoseBacklog(int maxSamples);
void clearAllCache();
boolean requestPause();
void resetCounters();
String requestReindex(String indexName);
\`\`\`

Hãy phân loại theo quan sát/chẩn đoán/điều khiển, xác định phạm vi, tác dụng thứ cấp và điều kiện cần kiểm tra. Ví dụ \`diagnoseBacklog\` là chẩn đoán có giới hạn; \`clearAllCache\` là điều khiển có thể gây cache stampede; \`resetCounters\` làm mất baseline quan sát.

### Bài 2: thiết kế xác nhận có phạm vi

Một operator muốn xóa cache \`product-details\` chỉ trên instance \`node-02\`. Hãy thiết kế thông tin preview, expected version, expiry và result. Nếu cache region đã tăng kích thước gấp 20 lần sau preview, server nên từ chối hoặc yêu cầu xác nhận lại.

### Bài 3: xử lý timeout

Một script gọi \`requestReconnect(requestId)\`, sau đó JMX connection timeout. Script có nên gọi lại với request ID mới? Không nên. Đọc trạng thái operation/connection và kiểm tra request ID cũ trước. Nếu không thể biết kết quả, ghi trạng thái bất định và áp dụng runbook thay vì tạo thêm side effect.

### Bài 4: phân quyền

Một MBean có attribute \`QueueDepth\` và operation \`clearDeadLetters()\`. Hai nhóm vận hành chỉ đọc và điều khiển có quyền khác nhau. Hãy mô tả cách bảo vệ boundary JMX, phạm vi operation và audit. Lưu ý: method không tự biết identity đáng tin cậy chỉ qua một string caller truyền vào.

### Bài 5: state version

Thiết kế \`requestPause(long expectedVersion)\` và \`getStatusSnapshot()\`. Giải thích vì sao hai getter riêng có thể không cung cấp snapshot nguyên tử và vì sao trạng thái \`PAUSE_REQUESTED\` không đồng nghĩa \`PAUSED\`.

## Tổng kết

\`@ManagedOperation\` là cách Spring công bố một hành động quản trị qua JMX; nó không tự cung cấp cơ chế xác nhận hay kiểm soát tác dụng phụ. Với operation có ảnh hưởng, cần xác định **hành động thay đổi gì, tác động đến phạm vi nào, quyền của người gọi ra sao, điều kiện trước có còn đúng không, và hệ thống đã thực sự đạt trạng thái mong muốn chưa**. Xác nhận tại UI giúp giảm thao tác nhầm, nhưng an toàn thực chất nằm ở authorization, validation, precondition, idempotency, audit và quan sát sau thực thi. Những thao tác có rủi ro lớn nên đi qua quy trình điều khiển phù hợp với hệ thống thay vì được phơi bày tùy tiện trên một MBean.
