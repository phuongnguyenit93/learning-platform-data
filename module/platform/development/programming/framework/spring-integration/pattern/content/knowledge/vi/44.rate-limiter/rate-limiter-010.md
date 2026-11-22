# Cấu hình động và nhất quán nhiều instance

## 1. Bài toán: đổi quota khi hệ thống có nhiều instance

Trong module **SPRING_INTEGRATION_PATTERN**, Spring Integration nối các Enterprise Integration Patterns (EIP) như Gateway, Filter, Transformer, Router, Service Activator, Splitter và Aggregator bằng message channel. Một luồng xử lý có thể chạy trên nhiều pod hoặc nhiều JVM để tăng throughput. Khi gọi dependency ngoài, ta thường đặt **rate limiter** trước điểm gọi nhằm giới hạn số message được phép tiếp tục trong một khoảng thời gian, tránh vượt quota hoặc gây quá tải upstream.

Giả sử Stock API chỉ cho phép hệ thống gọi trung bình **120 request/giây**, với một burst tối đa 120 permit. Ứng dụng đang chạy **ba pod**, mỗi pod đều nhận message từ Gateway hoặc consumer.

Nếu mỗi pod tạo một rate limiter **120 request/giây** trong RAM, tổng mức được cấp có thể tới **360 request/giây**. Việc cập nhật cấu hình từ 120 xuống 60 mà chỉ có hai pod nhận được còn khiến giới hạn toàn hệ thống thay đổi theo nơi request được route.

Bài toán có **hai yêu cầu độc lập**:

1. **Cấu hình động:** thay đổi tốc độ, burst, quota tenant hoặc chính sách từ chối mà không cần restart tất cả pod.
2. **Nhất quán nhiều instance:** các pod thực thi cùng một giới hạn **trên toàn cụm** theo mức bảo đảm đã chọn, không nhân quota theo số pod.

**Đồng bộ file cấu hình không đồng nghĩa đồng bộ bộ đếm permit.** Mỗi pod có thể nhận cùng con số 120 nhưng vẫn tự phát 120 permit. Muốn giới hạn toàn cụm, cần một cơ chế phân phối quota có phối hợp, ví dụ kho token dùng chung với thao tác nguyên tử hoặc một gateway thực thi quota tập trung.

~~~mermaid
flowchart TD
    A[Policy control plane] -->|Versioned update| B[Policy store]
    B --> C[Pod 1: Spring Integration]
    B --> D[Pod 2: Spring Integration]
    B --> E[Pod 3: Spring Integration]
    C --> F[Shared atomic rate gate]
    D --> F
    E --> F
    F -->|Permit| G[Stock API]
    F -->|Reject| H[429 / fallback / defer]
~~~

Bài này tập trung vào cách **chọn phạm vi quota, quản lý phiên bản cấu hình, thực thi permit nguyên tử, xử lý lỗi và kiểm thử đa instance** trong một flow Spring Integration.

## 2. Xác định trước: quota đang giới hạn điều gì?

Cấu hình “120 req/s” chưa đủ để triển khai đúng. Cần viết rõ **phạm vi**, **thuật toán**, **đơn vị tính**, **burst** và **độ chính xác mong muốn**.

| Quyết định | Ví dụ | Hệ quả |
| --- | --- | --- |
| **Scope** | stock.read trên toàn hệ thống | Mọi pod dùng chung ngân sách |
| **Tenant scope** | stock.read:tenant-group-A | Group A có quota riêng |
| **Cost** | Mỗi HTTP call tốn 1 permit | Retry vật lý có thể tốn permit thêm |
| **Refill** | 120 token mỗi giây | Tốc độ trung bình mục tiêu |
| **Capacity** | Tối đa 120 token | Cho phép burst ngắn |
| **On reject** | Fail fast, retry-after hoặc defer | Quy định trải nghiệm caller |
| **Consistency** | Chính xác theo một key hay xấp xỉ có sai số | Quyết định mô hình lưu trữ/độ trễ |

**Token bucket với refill 120 token/giây và capacity 120 không có nghĩa “không bao giờ quá 120 request trong bất kỳ cửa sổ trượt một giây”.** Token đã tích lũy có thể cho phép một burst và các token mới được bổ sung trong khoảng thời gian kế tiếp. Nếu hợp đồng upstream yêu cầu **trần cứng trong mọi rolling window**, cần chọn một thuật toán cửa sổ phù hợp thay vì hiểu nhầm token bucket.

Cũng phải xác định giới hạn áp dụng tại đâu:

- **Ingress:** giới hạn request trước khi đi vào hệ thống, thường gắn với khách hàng/API.
- **Egress:** giới hạn mỗi lần gọi dependency ngoài, có thể thấp hơn lưu lượng Gateway.
- **Consumer:** giới hạn tốc độ tiêu thụ từ queue hoặc xử lý message.
- **Theo tenant/operation:** tạo công bằng giữa nhóm người dùng và loại tác vụ.

Một request Gateway có thể tạo **ba** lời gọi ngoài qua Splitter. Khi đó “100 request Gateway/s” không bằng “100 HTTP call/s”; phải chọn điểm đặt limiter theo chi phí thực tế.

## 3. Control plane và data plane: không trộn hai trách nhiệm

**Control plane** quản lý chính sách; **data plane** quyết định cho một message đi tiếp hay không.

| Thành phần | Chức năng | Điều cần bảo đảm |
| --- | --- | --- |
| Policy admin/API | Thay đổi rate, burst, scope, hiệu lực | Authorization, validation, audit |
| Policy repository | Lưu snapshot/version đã được duyệt | Không mất cập nhật; rollback xác định |
| Config distribution | Thông báo cho pod có phiên bản mới | Có retry/reconcile, chịu được event trùng hoặc sai thứ tự |
| Local policy view | Đọc snapshot cho log/UI/quyết định không nhạy quota | Thay toàn bộ snapshot nguyên tử, không trộn field |
| **Shared rate gate** | Cấp hoặc từ chối permit | Quyết định nguyên tử theo cùng bucket và policy |
| Gateway/error/fallback path | Trả kết quả khi từ chối | Không retry vô hạn hay mất message |

Một cấu hình đẩy bằng pub/sub có thể giúp các pod cập nhật nhanh, nhưng pub/sub **không phải bằng chứng rằng mọi pod đang có chính xác một phiên bản**. Pod đang restart, bị partition hoặc mất message có thể dùng cấu hình cũ. Do đó cần **periodic reconciliation** để lấy lại snapshot mới nhất, và data plane phải có quy tắc khi local view lệch bản authoritative.

### Ba mức nhất quán cần phân biệt

1. **Nhất quán cấu hình cuối cùng (eventual):** sau một thời gian các pod đều thấy phiên bản mới; trong lúc chuyển tiếp có thể khác nhau.
2. **Quota chính xác theo một bucket/key:** mọi thao tác cấp permit cho key được tuần tự hóa ở một nơi chung; tổng permit không nhân theo pod.
3. **Chuyển chính sách tuyến tính hóa theo key:** thay đổi chính sách và cấp permit cùng được sắp thứ tự nguyên tử, nên từ sau điểm cập nhật được commit, các lần cấp permit mới cho key đó dùng chính sách mới.

Mức 2 **không tự suy ra** mức 3 nếu mỗi pod gửi thông số policy cũ vào shared gate. Và mức 3 **theo từng key** không nhất thiết bảo đảm nhiều key được cập nhật cùng một thời điểm trên toàn cluster.

Nếu nghiệp vụ chỉ cho phép sai số quota rất nhỏ, thiết kế phải nói rõ sai số tối đa. Nếu đòi **trần nghiêm ngặt**, không nên dùng một cơ chế chỉ bảo đảm eventual consistency cho quyết định cấp permit.

## 4. Thiết kế khóa quota ổn định và có giới hạn

Một bucket key nên đại diện đúng quota, ví dụ:

~~~text
stock.read:GLOBAL
stock.read:TENANT_GROUP_A
pricing.read:REGION_APAC
~~~

Không lấy URL đầy đủ với query parameter, SKU, requestId hoặc correlationId làm key; mỗi request thành một bucket riêng sẽ làm limiter **không giới hạn được gì** và gây phình bộ nhớ.

Với đa tenant:

- Lấy tenant context từ **identity đã xác thực**, không tin một header tenantId do client tự điền.
- Chọn bucket theo **policy của provider**: quota toàn hệ thống thì dùng GLOBAL, quota riêng tenant thì mới phân vùng.
- Một số tenant lớn có thể dùng dedicated bucket; tenant nhỏ vào nhóm SHARED nếu đúng miền quota.
- **Bucket scope không thay thế authorization**; dữ liệu/cache vẫn phải được phân quyền riêng.
- Key và metric label không nên chứa email, token, thông tin bí mật hoặc định danh có cardinality rất cao.

Nếu upstream có **quota tổng 120/s** và thêm **quota riêng tenant A 50/s**, chỉ kiểm tra bucket tenant A là chưa đủ. Có thể cần cấp permit từ **cả bucket GLOBAL và bucket A theo một quyết định phối hợp**. Việc trừ token tuần tự mà không có rollback/atomicity có thể tạo tiêu thụ permit không chính xác hoặc vượt quota khi nhiều pod đua nhau.

## 5. So sánh các kiến trúc thực thi đa instance

| Kiến trúc | Ưu điểm | Rủi ro và điều kiện sử dụng |
| --- | --- | --- |
| **Mỗi pod dùng local limiter** | Rất nhanh, không có network hop | Chỉ đúng cho quota **per-pod**; quota toàn cụm có thể nhân N |
| **Chia quota tĩnh theo pod** | Dễ làm với số pod cố định | Load lệch, autoscaling, pod mất/rời cụm gây lãng phí hoặc vượt quota |
| **Shared atomic bucket** | Các pod có cùng ngân sách theo key | Có network/store latency, cần HA và failure policy |
| **Token leasing theo pod** | Giảm số lần round-trip tới kho chung | Có sai số do token đã cấp nhưng chưa dùng, cần lease/expiry và chặn over-allocation |
| **Gateway quota tập trung** | Chặn tại một điểm rõ ràng | Cần mọi đường đi đều qua gateway, gateway cũng phải HA và không bypass |
| **Sharding theo key** | Phân tán tải khi có nhiều key độc lập | Hot key, chuyển shard và mapping cần kiểm soát |

Ví dụ **3 pod × 120 permit/s** chỉ là ba limiter local, không phải một limiter toàn cluster. Chia tĩnh **40 permit/s/pod** cũng không hoàn hảo: nếu 90% traffic vào pod A, pod A có thể từ chối dù hai pod kia còn quota. Khi tăng lên bốn pod, tổng quota thay đổi nếu không chia lại nhất quán.

**Shared atomic bucket** thường là cách dễ giải thích nhất cho giới hạn chính xác **theo một key**, với điều kiện tất cả request đều dùng cùng key và cùng nơi thực thi nguyên tử.

## 6. Token bucket dùng chung cần nguyên tử như thế nào?

Một token bucket chứa ít nhất:

~~~text
bucketKey        = stock.read:GLOBAL
capacity         = 120 tokens
refillTokens     = 120
refillPeriod     = 1000 milliseconds
tokens           = số token hiện có (có thể là số thực theo mô hình)
lastRefillAt     = mốc thời gian cập nhật gần nhất
policyVersion    = 42
~~~

Ở mỗi lời gọi có **cost = 1**, backend cần thực hiện **đọc trạng thái → refill → kiểm tra → trừ token → ghi kết quả** trong **một thao tác nguyên tử** với cùng bucket.

~~~text
Atomic acquire(bucketKey, cost):

1. Lấy thời gian chuẩn từ backend đáng tin cậy.
2. Đọc policy hiện hành và trạng thái bucket trong cùng miền nhất quán.
3. elapsed = max(0, now - lastRefillAt)
4. tokens = min(capacity,
                oldTokens + elapsed * refillTokens / refillPeriod)
5. Nếu tokens >= cost:
       tokens = tokens - cost
       allowed = true
   Ngược lại:
       allowed = false
       tính retryAfter từ phần token còn thiếu.
6. Lưu tokens, timestamp và policyVersion theo quy tắc áp dụng.
7. Trả decision + policyVersion + retryAfter (nếu reject).
~~~

Đây là **pseudocode thuật toán**, không phải script Redis có thể chạy nguyên văn. Khi triển khai thực, dùng thao tác nguyên tử phù hợp backend, chẳng hạn **Redis Lua script** hoặc transaction/CAS trên một kho lưu trữ có semantics rõ ràng. Nếu dùng Redis Cluster, những key mà một script truy cập phải thỏa điều kiện **cùng hash slot**; không thể giả định một script atomic với các key ở nhiều shard bất kỳ.

### 6.1. Race condition khi không nguyên tử

Giả sử bucket chỉ còn **1 token**. Hai pod đọc đồng thời:

~~~mermaid
sequenceDiagram
    participant A as Pod A
    participant S as Shared store
    participant B as Pod B
    A->>S: Đọc tokens = 1
    B->>S: Đọc tokens = 1
    S-->>A: 1
    S-->>B: 1
    A->>S: Ghi tokens = 0, ALLOW
    B->>S: Ghi tokens = 0, ALLOW
    Note over A,B: Hai lần ALLOW dù chỉ có 1 token
~~~

Giải pháp là để store **tuần tự hóa việc cấp permit**, không để từng pod tự đọc rồi ghi riêng lẻ. Khi thực thi đúng, chỉ **một pod** nhận ALLOW, pod còn lại nhận REJECT.

### 6.2. Đồng hồ của ai được dùng?

Nếu mỗi pod dùng đồng hồ cục bộ để refill, các pod có thể lệch giờ. Kẻ gọi cũng có thể lạm dụng sai lệch thời gian để nhận token sớm. Nên dùng **thời gian do backend cấp permit quản lý** hoặc một nguồn thời gian chung đáng tin cậy, với quy tắc xử lý clock going backward và migration.

Dù dùng server time, cần hiểu failover, clock adjustment và thuật toán nội bộ. Một lời gọi có cost khác nhau nên được quyết định cùng một đơn vị đo được định nghĩa rõ ràng, tránh float rounding làm vượt quota.

## 7. Cấu hình động phải có version, validation và audit

Một snapshot chính sách có thể mang các trường sau:

~~~yaml
policyId: stock-read-global
version: 42
scope: stock.read:GLOBAL
algorithm: TOKEN_BUCKET
capacity: 120
refillTokens: 120
refillPeriodMillis: 1000
rejectPolicy: FAIL_FAST
effectiveAt: "2026-11-21T10:00:00Z"
updatedBy: rate-admin-service
changeReason: "Align upstream quota"
~~~

Đây là **ví dụ schema nghiệp vụ**, không phải cấu hình mặc định của Spring Integration hoặc Resilience4j. Một policy thật cần định nghĩa rõ thời gian hiệu lực, timezone, quota dimensions và giới hạn giá trị.

Trước khi chấp nhận thay đổi, cần validate:

- **capacity > 0**, refill tokens và period hợp lệ; tránh phép chia 0/tràn số.
- Scope được khai báo và authorization hợp lệ; không tạo key tùy ý theo request.
- Version tăng đơn điệu, có **compare-and-swap** hoặc điều kiện phiên bản kỳ vọng.
- Hiệu lực không mơ hồ; snapshot có source, timestamp, người phê duyệt và lý do.
- Nếu giảm quota mạnh, có kế hoạch cho traffic đang chạy và token đang tồn.
- Nếu tăng burst, kiểm tra giới hạn thực tế upstream cho phép.
- Nếu đổi **algorithm** (token bucket sang rolling window), có phương án chuyển state thay vì tự ghép hai semantics.

### 7.1. Thứ tự update và chống nhận bản cũ

Giả sử control plane phát **v42**, tiếp theo **v43**, nhưng một pod nhận sự kiện v43 trước v42. Nếu pod chỉ ghi đè cấu hình mỗi lần có event, nó có thể **quay lại version cũ**.

Quy tắc an toàn:

1. Snapshot có **version/generation** đơn điệu.
2. Pod chỉ install snapshot mới hơn snapshot đang có.
3. Nếu mất event, định kỳ fetch phiên bản authoritative để reconcile.
4. Dùng **atomic replacement** cả snapshot, không update capacity/refill từng field riêng.
5. Expose **current_policy_version** và **config_age** để biết pod nào bị tụt.
6. Nếu backend cấp permit dùng policy authoritative, pod không được đưa policy cũ vào để ép backend cấp permit theo v42.

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant P as Policy service
    participant S as Shared quota backend
    participant A as Pod A
    participant B as Pod B
    O->>P: Update v42 -> v43
    P->>S: Publish authoritative policy v43
    S-->>P: Confirm commit
    P-->>O: Applied v43
    P-->>A: Notify v43
    P-->>B: Notify v43
    Note over B: Event bị trễ hoặc mất
    B->>P: Periodic reconciliation
    P-->>B: Snapshot v43
    Note over S: Permit dựa trên policy authoritative
~~~

**Lưu ý:** “publish authoritative policy” ở sơ đồ phải là một thao tác có ngữ nghĩa commit rõ ràng với backend thực thi quota. Nếu policy store và limiter state là hai hệ thống không có giao dịch chung, công bố v43 rồi hy vọng tất cả nơi cấp permit lập tức áp dụng v43 là một lời hứa quá mạnh. Cần một giao thức rollout/versioned acquire hoặc chấp nhận khoảng eventual consistency đã định nghĩa.

## 8. Đổi capacity và refill khi bucket đang có token

Cấu hình động không đơn giản là thay hai số trong một object. Bucket đang có trạng thái từ chính sách cũ.

Giả sử v42 có **capacity = 120**, hiện còn **90 token**; v43 giảm capacity xuống **40**.

Nếu chỉ đổi trường capacity mà giữ tokens = 90, hệ thống có thể cấp **90 permit** ngay sau update dù chính sách mới cho burst tối đa 40. Cần một quy tắc migration rõ:

~~~text
Khi áp dụng policy mới dưới lock/transaction của bucket:

1. Refill trạng thái cũ tới thời điểm chuyển theo policy cũ.
2. Thay policyVersion và các tham số mới.
3. Clamp tokens = min(tokens, newCapacity).
4. Ghi trạng thái và version nguyên tử.
5. Các acquire sau commit dùng policy mới.
~~~

Đây là **một chính sách chuyển đổi minh họa**. Tùy hợp đồng nghiệp vụ, có thể chọn **reset bucket về 0** khi giảm quota mạnh để tránh burst, hoặc giữ một phần credit. Không có một hành vi migration mặc định phù hợp mọi ứng dụng.

| Thay đổi | Quyết định cần ghi rõ |
| --- | --- |
| Tăng capacity | Cho phép tích token tới mức mới ngay hay dần dần? |
| Giảm capacity | Clamp token; có cần loại bỏ toàn bộ credit cũ không? |
| Giảm refill rate | Từ thời điểm nào dùng tốc độ mới? |
| Đổi rolling-window sang token-bucket | Chuyển state thế nào, có giai đoạn dual-run không? |
| Xóa quota theo tenant | Bucket cũ và số liệu audit được dọn khi nào? |
| Rollback v43 về thông số v42 | Tạo **v44** với giá trị cũ, không phát lại một version cũ |

**Một update không thể thu hồi request đã được cho phép và đang thực thi.** Nếu đổi từ 120 xuống 40 req/s, các call đã qua limiter trước commit vẫn có thể hoàn tất sau đó. Nếu mục tiêu là giảm concurrency ngay, cần thêm cơ chế bulkhead/cancellation riêng; rate limiter không tự hủy in-flight calls.

## 9. Mức độ nhất quán: đúng tuyệt đối hay có sai số được kiểm soát?

Một shared atomic store giúp tuần tự hóa permit của **một bucket**, nhưng cũng tạo network round-trip cho mỗi request. Ở tải rất cao, có thể cân nhắc cấp **token lease** theo pod.

Ví dụ backend có 120 token; nó phân 20 token cho Pod A, 20 cho Pod B, 20 cho Pod C theo thao tác nguyên tử. Mỗi pod tiêu thụ local các token đã được cấp mà không cần gọi backend mỗi lần. Khi hết lease, pod xin thêm.

Ưu điểm: giảm latency và tải backend. Đổi lại:

- Token được cấp nhưng chưa dùng vẫn là phần ngân sách bị giữ; pod khác có thể thiếu quota.
- Khi giảm capacity, một số lease cũ còn hiệu lực; nếu không chặn hoặc rút lease, có thể vượt ngưỡng mới.
- Pod crash làm token lease mất hiệu lực theo thời gian, cần expiry/reclaim policy.
- Nếu backend mất liên lạc, mỗi pod có thể tiếp tục dùng token lease còn hạn; giới hạn tổng chỉ đúng theo budget đã cấp và semantics lease.
- Cần định nghĩa **sai số/quãng chuyển tiếp tối đa** bằng số lease outstanding và thời hạn hiệu lực.

**Không tuyên bố lease per-pod nhất quán mạnh tức thì** nếu vẫn còn token cũ có thể được tiêu. Khi upstream có quota cứng và vi phạm dẫn tới bị khóa tài khoản, nên ưu tiên shared atomic permit hoặc một giải pháp có chứng minh được upper bound.

### Nhiều tầng quota

Một provider có thể giới hạn đồng thời:

- 120 req/s toàn hệ thống.
- 40 req/s cho tenant A.
- 10 in-flight requests cho một operation.

Rate limiter và **bulkhead/concurrency limiter** có vai trò khác nhau. Nếu cần áp dụng nhiều bucket trong **cùng một quyết định**, phải bảo đảm không xảy ra race khiến permit tổng và permit tenant bị trừ dở dang; có thể dùng backend hỗ trợ transaction/atomic script trong cùng miền dữ liệu hoặc một dịch vụ cấp quota chịu trách nhiệm phối hợp.

## 10. Ví dụ Java: config snapshot được cập nhật nguyên tử

Một pod cần có thể đọc policy snapshot ổn định để hiển thị hoặc ghi log, nhưng không nên dùng snapshot cục bộ làm nguồn cấp **permit toàn cụm** nếu contract đòi giới hạn chính xác.

Ví dụ dưới đây quản lý snapshot **chỉ ở mặt control plane của một pod**. Các import thông thường được lược bớt.

~~~java
public record RatePolicy(
        String scope,
        int capacity,
        int refillTokens,
        Duration refillPeriod
) {}

public record PolicySnapshot(
        long generation,
        Map<String, RatePolicy> policies
) {}

@Component
public final class PolicyView {

    private final AtomicReference<PolicySnapshot> current =
            new AtomicReference<>(
                    new PolicySnapshot(0L, Map.of())
            );

    public boolean install(PolicySnapshot incoming) {
        validate(incoming);
        for (;;) {
            PolicySnapshot previous = current.get();

            // Tránh event đến trễ ghi đè snapshot mới.
            if (incoming.generation() <= previous.generation()) {
                return false;
            }
            if (current.compareAndSet(previous, incoming)) {
                return true;
            }
        }
    }

    public PolicySnapshot snapshot() {
        return current.get();
    }

    private void validate(PolicySnapshot incoming) {
        if (incoming == null || incoming.generation() <= 0
                || incoming.policies() == null) {
            throw new IllegalArgumentException("Invalid policy snapshot");
        }
        for (RatePolicy policy : incoming.policies().values()) {
            if (policy == null || policy.scope() == null
                    || policy.capacity() <= 0
                    || policy.refillTokens() <= 0
                    || policy.refillPeriod() == null
                    || policy.refillPeriod().isZero()
                    || policy.refillPeriod().isNegative()) {
                throw new IllegalArgumentException("Invalid rate policy");
            }
        }
    }
}
~~~

Điểm quan trọng:

1. **AtomicReference** thay **cả snapshot** trong một bước, tránh đọc capacity mới với refill cũ.
2. Version cũ hơn bị bỏ qua, kể cả thông báo đến sai thứ tự.
3. **PolicyView không phải distributed limiter**. Hai pod có PolicyView giống nhau vẫn có thể cấp phép quá tổng quota nếu dùng bucket local.
4. Với dữ liệu production, nên **copy bất biến** bản đồ policies trước khi công bố snapshot và validate đầy đủ key/scope, để code khác không sửa Map qua một tham chiếu vẫn còn mutable.
5. Nguồn config nên có fetch/reconcile và kiểm soát authorization; **install()** chỉ minh họa cơ chế tại một pod.

Lệnh cấu hình được coi là applied với toàn hệ thống chỉ khi đáp ứng semantics đã chọn tại backend authoritative, không phải vì một Pod gọi install() trả true.

## 11. Spring Integration Java DSL với shared rate gate

Ví dụ sau triển khai rate limiting **tại handler egress**, ngay trước lời gọi Stock API. **SharedRateGate** là abstraction của ứng dụng; implementation thực phải cấp permit nguyên tử trên backend chung và dùng **policy authoritative**. Đoạn Java cho thấy cách tích hợp EIP, không giả vờ rằng một in-memory class là distributed token bucket.

### 11.1. Hợp đồng request và permit

~~~java
public record VerifiedStockRequest(
        String tenantGroup,
        String sku,
        String requestId
) {}

public record StockOutcome(
        String requestId,
        String status,
        Integer availableUnits,
        Long retryAfterMillis
) {}

public enum PermitStatus {
    ALLOWED,
    REJECTED,
    STORE_UNAVAILABLE
}

public record PermitDecision(
        PermitStatus status,
        long appliedPolicyVersion,
        long retryAfterMillis
) {}

public interface SharedRateGate {
    // Implementation phải lấy policy + bucket từ cùng nguồn authoritative.
    PermitDecision acquire(String bucketKey, int cost);
}

public interface StockClient {
    int availableUnits(String tenantGroup, String sku);
}

public class RateGateUnavailableException extends RuntimeException {
    public RateGateUnavailableException(String message) {
        super(message);
    }
}
~~~

**VerifiedStockRequest** chỉ nên được tạo sau khi ingress đã kiểm tra identity, tenant và operation. Không tin một tenantGroup do caller tự khai báo. **requestId** dùng để tracing/idempotency nếu nghiệp vụ cần, không dùng làm bucket key.

### 11.2. Service Activator quyết định permit rồi mới gọi upstream

~~~java
@Component
public class RateLimitedStockService {

    private final SharedRateGate rateGate;
    private final StockClient stockClient;

    public RateLimitedStockService(
            SharedRateGate rateGate,
            StockClient stockClient
    ) {
        this.rateGate = rateGate;
        this.stockClient = stockClient;
    }

    public StockOutcome lookup(VerifiedStockRequest request) {
        String bucketKey =
                "stock.read:" + request.tenantGroup();

        // Tất cả pod gọi cùng authoritative gate với cùng bucketKey.
        PermitDecision decision = rateGate.acquire(bucketKey, 1);

        if (decision.status() == PermitStatus.REJECTED) {
            return new StockOutcome(
                    request.requestId(),
                    "RATE_LIMITED",
                    null,
                    decision.retryAfterMillis()
            );
        }
        if (decision.status() == PermitStatus.STORE_UNAVAILABLE) {
            // Failure policy phải được xác định rõ;
            // không mặc định ALLOW nếu backend không trả quyết định.
            throw new RateGateUnavailableException(
                    "Shared quota backend unavailable"
            );
        }

        int units = stockClient.availableUnits(
                request.tenantGroup(),
                request.sku()
        );

        return new StockOutcome(
                request.requestId(),
                "FRESH",
                units,
                null
        );
    }
}
~~~

Không nên cho một request **STORE_UNAVAILABLE** đi vào StockClient chỉ vì nhánh if chỉ kiểm tra REJECTED. Sự cố của kho cấp permit phải có **failure policy** rõ ràng.

Khi rate gate trả REJECTED, StockClient không được gọi. Đây là **điều kiện quan trọng nhất** của test. Lời gọi đã cấp permit nhưng Stock API timeout vẫn đã tiêu permit theo chính sách “mỗi attempt tốn một token”, trừ khi backend có một cơ chế bù có điều kiện được định nghĩa riêng; không tự động hoàn token vì client mất response.

### 11.3. Nối bằng Gateway và IntegrationFlow

~~~java
@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockOutcome lookup(VerifiedStockRequest request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockRateFlowConfiguration {

    @Bean
    public IntegrationFlow stockLookupFlow(
            RateLimitedStockService service
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(
                        VerifiedStockRequest.class,
                        (request, headers) -> service.lookup(request)
                )
                .get();
    }
}
~~~

Gateway đồng bộ nhận **StockOutcome** có status **FRESH** hoặc **RATE_LIMITED**, hoặc exception kỹ thuật nếu rate gate không khả dụng. Boundary REST có thể ánh xạ RATE_LIMITED thành **HTTP 429** với thông tin retry-after phù hợp, nhưng đây là **hợp đồng của lớp API**, không phải Spring Integration tự biến result thành 429.

Trong flow bất đồng bộ, message bị từ chối có thể đi sang **discard/rejected channel** hoặc durable queue có TTL. Không chỉ cho Filter trả false rồi bỏ message mà không có outcome và audit khi nghiệp vụ cần đối soát.

**Chỉ gọi một lần SharedRateGate tại điểm egress phù hợp.** Nếu cả Gateway, Filter và Service Activator đều trừ cùng một bucket cho cùng HTTP attempt, quota có thể bị tính nhiều lần. Nếu thật sự muốn giới hạn **logical requests** và **physical outbound calls** riêng, dùng hai bucket với tên, mục tiêu và metric khác nhau.

## 12. Cập nhật config và quyết định permit phải thống nhất

Một lỗi thiết kế hay gặp:

1. Pod A đã đọc **v43 (60 req/s)**.
2. Pod B vẫn giữ **v42 (120 req/s)**.
3. Hai pod cùng gửi lệnh acquire lên backend nhưng kèm capacity do chúng tự tính.
4. Backend chấp nhận tùy ý thông số của request đến cuối cùng.
5. Hệ thống có thể “nhảy” chính sách ngược giữa 60 và 120.

**Đừng để pod quyết định policy authoritative chỉ bằng một field capacity mà nó gửi kèm request.**

Một giao thức tốt hơn:

- **Backend lưu policyVersion** và tham số đang có hiệu lực cùng bucket hoặc trong cùng miền transaction hợp lệ.
- Lệnh **acquire(bucketKey, cost)** tự đọc chính sách authoritative; trả **appliedPolicyVersion**.
- Nếu thiết kế yêu cầu caller truyền **expectedVersion**, backend **không cấp permit theo version cũ** mà trả **CONFIG_STALE** để caller refresh (có giới hạn) hoặc lấy quyết định theo policy mới.
- Thay đổi policy và migrate bucket state phải được tuần tự hóa với acquire **theo cùng key**.
- Local PolicyView phục vụ quan sát hoặc những quyết định không ảnh hưởng quota cứng; nó không lật ngược quyết định của backend.

Một update v43 được commit **trong miền bucket** tạo thứ tự rõ: acquire trước commit dùng v42, acquire sau commit dùng v43. **Các HTTP request đã được cho phép trước commit có thể tiếp tục chạy**, và các request tới bucket khác có thể thấy version mới tại thời điểm khác nếu không có giao thức phối hợp đa key.

## 13. Lỗi mạng, failover và lựa chọn fail-open/fail-closed

Nếu shared store cấp permit bị timeout, đây **không phải** một phản hồi REJECT bình thường. Caller **không biết** token có được trừ hay chưa khi kết nối đứt sau khi gửi lệnh. Cần xử lý không chắc chắn kết quả thay vì retry vô hạn.

| Chính sách | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **Fail closed** | Không tự ý vượt quota khi không có quyết định | Từ chối cả traffic hợp lệ khi store hỏng |
| **Fail open** | Duy trì tính sẵn sàng | Có thể vượt upstream quota, ảnh hưởng hợp đồng hoặc security |
| **Bounded local fallback** | Phục vụ một phần có giới hạn rõ | Cần chứng minh sai số quota tối đa, dễ khó đồng bộ |
| **Queue/defer** | Không mất công việc có thể xử lý sau | Tăng backlog, cần TTL, backpressure và DLQ |

Không có một lựa chọn đúng cho mọi endpoint:

- **API bị khóa tài khoản nếu vượt quota:** thường nghiêng về fail closed hoặc bounded failover chặt chẽ.
- **Telemetry không quan trọng:** có thể chấp nhận fail open với quota/alert bổ sung nếu rủi ro được phê duyệt.
- **Tác vụ gửi notification bất đồng bộ:** có thể durable defer thay vì giữ worker đợi store.
- **Thanh toán hoặc dữ liệu cần bảo đảm:** không được im lặng chuyển mọi lỗi limiter thành thành công.

### 13.1. Một acquire không rõ kết quả có được retry không?

Giả sử backend đã trừ token nhưng response tới pod bị mất. Pod retry **cùng acquire**, backend có thể trừ token lần nữa. Điều này tạo **under-utilization** và làm caller bị rate limit sớm, dù không trực tiếp vượt quota.

Nếu cần chính xác theo logical attempt, có thể thiết kế **idempotency key** cho acquire và lưu quyết định một khoảng phù hợp, với phạm vi dedup rõ ràng. Tuy nhiên chính sách này làm tăng chi phí trạng thái và phải phân biệt retry của cùng một permit request với **một HTTP attempt mới** đáng được trừ permit mới.

Không mặc định **exactly-once** chỉ vì gọi Redis Lua hay dùng một queue. Atomicity của thao tác cấp permit khác với idempotency của toàn flow.

### 13.2. Redis failover và Redis Cluster

Redis/Lua có thể bảo đảm atomicity của script trong phạm vi node/key thích hợp, nhưng cần đánh giá **persistence, replication, failover và split-brain** trước khi hứa không bao giờ vượt quota qua mọi sự cố. Một primary vừa cấp token nhưng replica chưa nhận trạng thái rồi xảy ra failover có thể làm mất cập nhật nếu kiến trúc không bảo đảm durability/consistency cần thiết.

Đối với quota **cứng và hậu quả nghiêm trọng**, chọn backend/giao thức có mức bảo đảm phù hợp, kiểm thử failover và ghi rõ điều kiện lỗi. “Dùng Redis” không tự động đồng nghĩa nhất quán mạnh qua mọi network partition.

## 14. Retry, backpressure, Circuit Breaker và xử lý 429

Rate limiter trả REJECTED vì **hết ngân sách**, còn circuit breaker OPEN vì **dependency đang lỗi hoặc chậm**. Cần phân biệt trong metrics và phản hồi:

| Thành phần | Quyết định | Phản hồi thường thấy |
| --- | --- | --- |
| **Rate limiter** | Không còn permit | RATE_LIMITED, retry-after nếu tính được |
| **Circuit breaker** | Không cho call vì state lỗi | BREAKER_REJECTED / UNAVAILABLE |
| **Bulkhead** | Không còn slot đồng thời | BUSY / CONCURRENCY_LIMIT |
| **Retry** | Thử lại lỗi tạm thời có giới hạn | Attempts/backoff theo deadline |
| **Fallback** | Kết quả suy giảm khi dependency không khả dụng | STALE_REFERENCE / UNAVAILABLE |

Khi rate limiter trả RATE_LIMITED:

- **Không retry tức thời trong cùng handler** chỉ để giành token; điều đó tạo hot loop.
- Với REST caller, trả 429 có **Retry-After** đúng hợp đồng và được chuẩn hóa.
- Với message bất đồng bộ, có thể lên lịch lại bằng delayed queue/poller nếu còn TTL/attempt budget.
- Với Gateway đồng bộ, tránh sleep dài đợi permit khiến thread bị giữ và vượt deadline caller.
- Nếu fallback cache được phép, trả nhãn dữ liệu cũ rõ ràng; không trả 200 “fresh” giả.
- Nếu request đã qua limiter rồi client timeout, retry có thể cần **permit mới** tùy đơn vị quota vật lý; phải thống nhất chính sách trước khi đặt Retry quanh gate.

### 14.1. Thứ tự limiter và retry

~~~mermaid
flowchart LR
    A[Gateway] --> B[Retry hữu hạn]
    B --> C[Shared rate gate]
    C -->|ALLOW| D[Stock Client]
    C -->|REJECT| E[Không retry tức thời]
~~~

Với hình này, mỗi attempt đi qua gate và có thể tiêu permit. Nếu đặt gate ngoài Retry, **một permit có thể cho phép nhiều HTTP attempt**, làm vượt quota provider theo cuộc gọi vật lý. Chọn thứ tự dựa trên **cách provider tính quota** và kiểm thử số HTTP attempts.

Nếu request qua Splitter tạo nhiều lời gọi, mỗi nhánh outbound phải đánh giá quota tương ứng. Với Aggregator, khi một nhánh RATE_LIMITED, cần partial/timeout/error path để nhóm không chờ vô hạn và giữ correlation ID/sequence headers.

## 15. Rollout an toàn khi đổi chính sách production

Một quy trình thay đổi đáng tin cậy:

1. **Xác định scope và SLO:** quota tính theo request logic hay HTTP attempt; có cần giới hạn cứng không?
2. **Đánh giá tác động:** giảm quota có làm tăng reject/queue hay làm vượt deadline không?
3. **Validate schema + quyền:** người cập nhật được phép thay phạm vi nào, tham số có hợp lệ không?
4. **Prepare:** tạo version mới; kiểm tra migration bucket, capacity/refill, error policy.
5. **Commit authoritative:** backend quyết định hiệu lực tại một điểm có thứ tự rõ.
6. **Distribute & reconcile:** pod nhận thông báo, cài snapshot theo version và tự fetch bù khi lỡ event.
7. **Observe:** state policy version, allowed/rejected, store latency, config lag, upstream 429, queue age.
8. **Rollback bằng version mới:** nếu v43 lỗi, phát v44 có thông số đã kiểm chứng, không quay ngược version.
9. **Audit:** ghi thay đổi ai thực hiện, khi nào, lý do, scope, before/after và kết quả rollout.

Khi cần đổi đồng thời nhiều bucket hoặc nhiều region, phải xác định “hoàn tất” nghĩa là gì: **đã nhận yêu cầu**, **đã lưu policy**, **đã commit ở một shard**, hay **mọi shard đang áp dụng**. Không gộp các trạng thái đó thành một chữ “SUCCESS”.

### Rollback không xóa lịch sử đã cấp permit

Giảm quota hoặc rollback không thể gọi lại những request đã gửi. Do đó dashboard nên thể hiện **policy_version** tại thời điểm quyết định và sự kiện migration để phân biệt lượng ALLOW do v42 với v43 trong cùng một khoảng đo.

## 16. Kiểm thử cấu hình động và tính nhất quán đa instance

### 16.1. Unit test: local snapshot không nhận version cũ

~~~java
@Test
void ignoresOutOfOrderPolicySnapshots() {
    PolicyView view = new PolicyView();

    RatePolicy v2Policy = new RatePolicy(
            "stock.read:GLOBAL", 60, 60, Duration.ofSeconds(1)
    );
    RatePolicy v1Policy = new RatePolicy(
            "stock.read:GLOBAL", 120, 120, Duration.ofSeconds(1)
    );

    assertTrue(view.install(new PolicySnapshot(
            2L, Map.of("stock.read:GLOBAL", v2Policy)
    )));
    assertFalse(view.install(new PolicySnapshot(
            1L, Map.of("stock.read:GLOBAL", v1Policy)
    )));

    assertEquals(2L, view.snapshot().generation());
    assertEquals(
            60,
            view.snapshot().policies()
                    .get("stock.read:GLOBAL").capacity()
    );
}
~~~

Test này chỉ xác minh **atomic local snapshot và version monotonic**. Nó **không kiểm tra quota toàn cluster**.

### 16.2. Test với fake gate dùng chung

Để minh họa ý tưởng **nhiều caller cùng chia một ngân sách**, một fake đồng bộ hóa có thể dùng một counter chung. Test này không thay thế test backend Redis/SQL.

~~~java
@Test
void concurrentCallersDoNotExceedSharedPermitBudget()
        throws Exception {
    AtomicInteger remaining = new AtomicInteger(5);
    AtomicInteger allowed = new AtomicInteger();
    ExecutorService workers = Executors.newFixedThreadPool(10);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<?>> jobs = new ArrayList<>();

    try {
        for (int i = 0; i < 20; i++) {
            jobs.add(workers.submit(() -> {
                start.await();

                for (;;) {
                    int before = remaining.get();
                    if (before <= 0) {
                        return null;
                    }
                    if (remaining.compareAndSet(before, before - 1)) {
                        allowed.incrementAndGet();
                        return null;
                    }
                }
            }));
        }
        start.countDown();

        for (Future<?> job : jobs) {
            job.get();
        }
        assertEquals(5, allowed.get());
        assertEquals(0, remaining.get());
    } finally {
        workers.shutdownNow();
    }
}
~~~

**AtomicInteger ở đây chỉ là fake cùng JVM**, không phải cơ chế chia permit giữa pod. Một integration test thực sự phải chạy nhiều **process/client connection** tới **cùng backend**, dùng thời gian/refill có kiểm soát và xác nhận backend không cấp quá số permit của bucket.

### 16.3. Ma trận integration test cần có

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| 3 pod, cùng key, bucket có 120 token, không refill trong test | Tổng ALLOW tối đa 120, không phải 360 |
| 3 pod, request đồng thời khi còn 1 token | Chỉ một permit được cấp |
| Các key quota độc lập | Bucket A hết không làm trừ token của bucket B |
| GLOBAL + tenant quota | Không vượt bất kỳ giới hạn nào; phép cấp nhiều bucket có tính nguyên tử phù hợp |
| Pod nhận v43 trước v42 | Không cài ngược version |
| Một pod mất config notification | Reconciliation kéo về version mới |
| Giảm capacity 120 xuống 40 khi bucket còn 90 token | State được migrate/clamp theo policy đã chọn |
| Update policy trong lúc nhiều acquire chạy | Acquire theo key có thứ tự với commit policy |
| Gateway nhận REJECTED | StockClient không được gọi, outcome có retryAfter hợp lệ |
| Shared store timeout | Fail-open/closed/defer đúng policy, không tự coi là ALLOW |
| Response của acquire bị mất | Retry/idempotency không làm tiêu token ngoài ý muốn |
| Broker redelivery khi rate limited | Không hot loop; có backoff, TTL, DLQ |
| Retry HTTP khi đã có permit | Số permit tiêu thụ khớp số attempt theo hợp đồng |
| Splitter có nhánh bị reject | Aggregator không treo, giữ correlation |
| Scale từ 3 lên 6 pod | Tổng quota không tự nhân đôi |
| Failover store hoặc network partition | Mức bảo đảm/sai số quota vẫn nằm trong cam kết |
| Rollback v43 bằng v44 | Policy version không giảm, rule mới được dùng |
| Tenant header giả mạo | Không thể tạo/chọn bucket đặc quyền từ dữ liệu không xác thực |

**Không chỉ test ở một JVM.** Phải có test cạnh tranh thực tế giữa các instance, test khi update đang diễn ra và test xử lý sự cố backend. Một test với fake counter chứng minh thuật toán trong RAM, không chứng minh behavior của Redis Cluster hoặc database.

## 17. Metrics, tracing và cảnh báo

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **allowed / rejected by bucket scope** | Có áp dụng quota và phân vùng đúng không? |
| **applied_policy_version** | Lệnh acquire được quyết định theo phiên bản nào? |
| **pod_policy_generation / config_lag** | Pod nào bị lệch hoặc mất đồng bộ? |
| **shared_gate_latency p95/p99** | Chi phí round-trip của cơ chế dùng chung |
| **quota_backend_error / timeout** | Backend cấp permit có đang bị lỗi không? |
| **tokens remaining / utilization** | Bucket thường xuyên cạn hoặc còn dư nhiều? |
| **upstream HTTP 429 / 5xx** | Rate limiter có giúp tránh vượt quota provider không? |
| **Gateway latency / RATE_LIMITED outcomes** | Tác động đến người dùng |
| **retry attempts / delayed queue age / DLQ** | Có vòng retry hoặc backlog đang tăng không? |
| **Aggregator pending/expired groups** | Nhánh RATE_LIMITED có làm nhóm thiếu reply không? |

Cần phân biệt **limiter rejection**, **circuit-breaker rejection**, **bulkhead rejection** và **HTTP 429 do upstream trả về**. Chúng có cách khắc phục khác nhau. Correlation/trace ID dùng để theo dõi một message qua Gateway, Router, Splitter và error channel; không đưa từng ID vào metric tags.

Cảnh báo gợi ý:

- Nhiều pod có **policy_generation** cũ trong thời gian dài.
- Tổng ALLOW vượt phạm vi quota đã cam kết hoặc upstream liên tục trả 429.
- **shared_gate_latency** cao khiến Gateway p99 vượt SLO.
- **store_unavailable** tăng và hệ thống đang dùng fail-open theo thời gian dài.
- **RATE_LIMITED** tăng mạnh sau rollout v43, queue oldest age vượt TTL.
- Một key quá nóng (hot bucket) khiến backend shard nghẽn.
- Rejected tăng nhưng không có version/decision logs để giải thích.

Không đưa raw tenant ID, SKU, URL động hoặc requestId làm metric labels khi chúng có cardinality lớn hoặc nhạy cảm. Dùng **operation**, **tenant_group**, **region** và tên bucket đã được chuẩn hóa; log/trace chi tiết phải có phân quyền.

## 18. Checklist triển khai

- [ ] Xác định quota theo **logical request**, outbound attempt, tenant hay toàn cluster.
- [ ] Ghi rõ burst, refill, cost, thuật toán và mức sai số nhất quán được phép.
- [ ] Không nhân per-pod limiter với số pod để gọi là global quota.
- [ ] Phân biệt control-plane policy update và data-plane atomic permit.
- [ ] Có policy **version/generation**, validation, authorization, audit và rollback bằng version mới.
- [ ] Config notification có **reconciliation**, không cài ngược bản cũ.
- [ ] Bucket state và policy migration được tuần tự hóa với acquire trong phạm vi key.
- [ ] Các pod dùng cùng key ổn định, lấy tenant context từ ingress đáng tin cậy.
- [ ] Nếu dùng Redis/DB, kiểm chứng atomicity, cluster hash slot, clock, failover và dữ liệu được replicate.
- [ ] Nếu dùng lease/local fallback, có sai số tối đa, expiry và giới hạn token outstanding.
- [ ] Chọn fail-open, fail-closed hoặc defer dựa trên hậu quả nghiệp vụ, không do vô tình catch exception.
- [ ] Không retry tức thời khi bị reject; có retryAfter/backoff, TTL, DLQ và backpressure nếu cần.
- [ ] Permit được trừ đúng điểm egress, không nhầm với bulkhead hoặc circuit breaker.
- [ ] Gateway/error channel và Splitter/Aggregator có outcome/correlation để không mất message.
- [ ] Có test đa process/pod, concurrency, hot reload, config out-of-order, quota giảm và store outage.
- [ ] Quan sát version lag, accepted/rejected, store latency, upstream 429, queue age và ảnh hưởng caller.

**Cấu hình động và nhất quán nhiều instance** đòi hỏi hai việc phải đúng đồng thời: **mọi chính sách được cập nhật có phiên bản và áp dụng theo ngữ nghĩa rõ ràng**, còn **mỗi quyết định cấp permit toàn cụm được phối hợp tại một nguồn authoritative**. Khi thiết kế ranh giới này đúng, Spring Integration có thể mở rộng qua nhiều pod mà không nhân quota theo pod, vẫn giải thích được tại sao một message được cho phép hay bị từ chối và tiếp tục xử lý có kiểm soát bằng Gateway, Router, retry, error channel và correlation.
