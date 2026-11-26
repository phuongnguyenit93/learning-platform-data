# Thời gian chờ và tình huống chưa biết chắc kết quả ghi trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; phối hợp bucket/scope/collection, chỉ mục, TTL, CAS, transaction và API reactive nhằm bảo đảm hiệu năng, nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **thời gian chờ ở HTTP gateway, service, Java SDK và Couchbase Server**; hiểu timeout ở một tầng không đồng nghĩa mutation đã bị hủy ở tầng khác.
2. Giải thích vòng đời **pre-dispatch → dispatch → response** và lý do một mutation đã commit vẫn có thể làm client nhận timeout.
3. Phân loại **`AmbiguousTimeoutException`**, **`UnambiguousTimeoutException`**, **`DurabilityAmbiguousException`** và các lỗi durability khác theo hướng xử lý an toàn.
4. Hiểu mối quan hệ giữa `kvTimeout`, `kvDurableTimeout`, timeout riêng cho mutation và deadline HTTP/reactive.
5. Xử lý kết quả chưa rõ bằng **document ID ổn định, idempotency key, đọc đối chiếu, retry có điều kiện và reconciliation**.
6. Biết tại sao **`insert`, `replace`, `upsert`, `remove`, counter** có tính chất retry khác nhau; không lầm “SDK có retry” với “nghiệp vụ exactly-once”.
7. Thiết kế trả lời HTTP không khẳng định sai rằng một order đã được tạo hoặc chắc chắn chưa được tạo.
8. Tích hợp Spring Data repository, `CouchbaseTemplate`, Java SDK và Reactor mà không bỏ qua semantics timeout/durability.
9. Đo lỗi và độ trễ thực tế, diễn tập failover/network jitter trên test cluster, có checklist để đưa vào production.

## 2. Tình huống mở đầu: đơn đã lưu nhưng API trả timeout

Một hệ thống đặt hàng nhận:

~~~http
POST /orders
Idempotency-Key: checkout-abc
Content-Type: application/json

{"tenantId":"42","items":[{"sku":"A1","quantity":1}],"total":1490000}
~~~

Ứng dụng gọi Couchbase KV:

~~~java
orders.insert(
    "tenant::42::checkout::checkout-abc",
    orderJson,
    insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Giả sử server đã đạt điều kiện majority và commit mutation, nhưng **response bị mất trên mạng**. SDK hoặc HTTP caller có thể trả timeout, dù document đã tồn tại.

Nếu client kết luận “timeout = chưa ghi”, tạo ID mới rồi thử lại:

~~~text
Lần 1: insert(order::random-A) -> server commit, response thất lạc
Lần 2: insert(order::random-B) -> success
Kết quả: hai document cho cùng một checkout
~~~

Durability mạnh không giải quyết lỗi này. Nó chỉ thay đổi **điều kiện ghi được xác nhận**; nó không bảo đảm client **luôn nhận được** thông báo thành công.

Nguyên tắc xuyên suốt bài học:

> **Không nhận được xác nhận không có nghĩa mutation chắc chắn chưa xảy ra. Khi outcome chưa rõ, hãy bảo toàn identity của yêu cầu và đối soát trước khi phát side effect tiếp theo.**

## 3. Ba thời điểm của một request ở Java SDK

Java SDK nhận yêu cầu rồi thực hiện các giai đoạn chính:

~~~mermaid
flowchart LR
    A["Pre-dispatch<br/>Tạo request, lấy config, tìm socket"]
    B["Dispatch<br/>Gửi request qua mạng"]
    C["Server work<br/>KV + replication/persistence nếu có"]
    D["Response<br/>SDK nhận và phân loại"]
    E["Application<br/>Success/error"]
    A --> B --> C --> D --> E
~~~

### 3.1. Trước khi dispatch

Ví dụ SDK chưa có cluster map, không tìm được endpoint hay không thể gửi request. Nếu SDK **chắc chắn chưa có side effect server**, timeout có thể được phân loại **unambiguous**.

Tuy nhiên, đừng tự suy diễn chỉ từ một dòng log mạng rằng gói tin chưa tới server. Phân loại này thuộc contract và thông tin mà SDK có.

### 3.2. Đã dispatch nhưng mất response

Server có thể:

- Chưa xử lý mutation.
- Đang chờ điều kiện synchronous durability.
- Đã commit, nhưng response chưa đến.
- Đã trả lỗi, nhưng response thất lạc.

Khi không có bằng chứng phân biệt, SDK có thể báo **ambiguous**. Thời điểm client ngừng chờ **không tự động hủy** một mutation đã gửi.

### 3.3. Nhận response chắc chắn

Nếu SDK nhận `DocumentExistsException` cho `insert`, operation hiện tại không tạo document mới cùng ID; nhưng điều đó **không chứng minh document hiện có thuộc cùng request**. Nếu nhận CAS mismatch, có writer khác thay version hoặc điều kiện đã khác; cần đọc lại business state.

### 3.4. Lý do “timeout là triệu chứng”

Timeout chỉ báo một giới hạn thời gian đã hết. Nguyên nhân có thể là:

- Network RTT/jitter, DNS/TLS/connectivity.
- Data node CPU/disk quá tải.
- Replica chưa xác nhận majority hoặc chưa persist.
- Rebalance/failover làm routing thay đổi.
- Quá nhiều request in-flight, queue hoặc retry storm.
- SDK timeout đặt không phù hợp với SLO.
- Một key đang có SyncWrite pending.

Tăng timeout mà không phân tích nguyên nhân có thể chỉ **đẩy thời gian chờ** sang caller hoặc làm nhiều request cùng treo lâu hơn.

## 4. Nhiều tầng timeout không đồng nghĩa nhau

Hãy xem một request checkout đi qua:

~~~mermaid
flowchart LR
    C["Mobile/Web client"]
    G["API gateway"]
    S["Spring service"]
    SDK["Couchbase Java SDK"]
    CB["Data Service<br/>SyncWrite protocol"]
    C --> G --> S --> SDK --> CB
~~~

| Tầng | Ví dụ giới hạn | Khi hết hạn có thể xảy ra điều gì? |
|---|---|---|
| **Client** | Mobile chờ 5 s | Người dùng thấy lỗi, có thể nhấn lại |
| **Gateway/load balancer** | Upstream timeout | Gateway trả 504; service/server có thể vẫn đang xử lý |
| **Spring MVC/WebFlux** | Request timeout, Reactor `Mono.timeout` | Caller ngừng chờ; không chứng minh DB đã rollback |
| **Java SDK KV thường** | `kvTimeout` | SDK ngừng đợi theo deadline của operation không yêu cầu sync durability bổ sung |
| **Java SDK durable KV** | `kvDurableTimeout` hoặc per-operation timeout | SDK ngừng chờ durable write theo deadline áp dụng |
| **Couchbase Server** | SyncWrite durability timeout | Server chờ điều kiện durability trong giới hạn protocol |
| **SQL++ Query Service** | `queryTimeout` | Timeout của truy vấn, không phải trực tiếp timeout KV durable mutation |

Ví dụ: gateway timeout **2 giây** và SDK durable write có deadline **10 giây**. Gateway có thể trả 504 ở giây 2 trong khi service/SDK/server còn đang xử lý mutation. Không thể bảo đảm request bị hủy đồng bộ dọc các tầng chỉ vì caller đã rời kết nối.

### 4.1. Timeout là deadline, không phải “thời gian server chắc chắn ghi xong”

`timeout(Duration.ofSeconds(5))` đặt giới hạn cho lời gọi ở SDK; nó không phải lệnh bảo server “ghi xuống disk trong tối đa 5 giây rồi nếu không xong phải hoàn nguyên mọi hệ thống ngay”.

### 4.2. Deadline ngắn có thể tăng số outcome chưa rõ

Khi server vẫn có thể hoàn tất mutation nhưng client đã hết thời gian chờ, số **ambiguous outcomes** tăng. Vì vậy cần đo đạc thay vì chọn một timeout quá thấp để latency graph nhìn đẹp.

### 4.3. Deadline dài không tự tăng độ an toàn

Giữ request 60 giây không biến `DurabilityLevel.NONE` thành `PERSIST_TO_MAJORITY`. Độ bền được quyết định bởi **effective durability level + điều kiện cluster**, không phải thời gian đã chờ.

## 5. Giá trị timeout mặc định trong Java SDK hiện hành

Theo trang **Couchbase Java SDK Client Settings** đang tham khảo:

| Nhóm operation | Tên cấu hình SDK | Giá trị mặc định được tài liệu công bố |
|---|---|---|
| **KV thường** | `kvTimeout` | **2,5 giây** |
| **KV với enhanced durability** | `kvDurableTimeout` | **10 giây** |
| **SQL++ query** | `queryTimeout` | **75 giây** |
| **Thời gian SyncWrite phía server** | Giới hạn protocol | SDK docs lưu ý **không đặt `kvDurableTimeout` vượt 65 giây** |

Các giá trị là **mặc định trong tài liệu Java SDK hiện hành**, không phải cấu hình tất cả project. Spring Boot, SDK version, connection string, system properties và per-operation override có thể thay đổi hiệu lực.

Đặc biệt, tài liệu ghi `kvDurableTimeout` **không phải phần stable API** và có thể đổi hoặc bị bỏ trong tương lai. Đừng xây framework nội bộ phụ thuộc cứng vào một giá trị mà chưa khóa phiên bản.

### 5.1. Đặt timeout toàn SDK khi thực sự cần

~~~java
import java.time.Duration;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;

Cluster cluster = Cluster.connect(
    connectionString,
    ClusterOptions.clusterOptions(username, password)
        .environment(env -> env.timeoutConfig(timeout -> timeout
            .kvTimeout(Duration.ofMillis(2500))
            .kvDurableTimeout(Duration.ofSeconds(10))
        ))
);
~~~

Đây là cách minh họa API Java SDK; code production cần quản lý lifecycle của `Cluster`, TLS/secrets và cấu hình theo phiên bản. Không tạo một cluster mới cho mỗi HTTP request.

### 5.2. Đặt timeout theo operation

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

orders.insert(
    orderId,
    orderBody,
    insertOptions()
        .durability(DurabilityLevel.MAJORITY)
        .timeout(Duration.ofSeconds(6))
);
~~~

Per-operation timeout hữu ích khi endpoint có SLA riêng. Nhưng phải đo xác suất hoàn tất trong 6 giây dưới tải và khi cluster degraded; không được coi số 6 giây là bảo đảm timeout không ambiguous.

### 5.3. Query timeout không chữa KV durability timeout

Nếu `findById` hoặc `insert` dùng KV, `queryTimeout` không phải cấu hình đúng. Nếu danh sách `findByStatus` dùng SQL++ và Index Service, cần phân tích SQL++ timeout/index lag/scan consistency **riêng**, không chỉnh `kvDurableTimeout` để giải quyết truy vấn.

## 6. Vòng đời SyncWrite và thời điểm dữ liệu có thể hiển thị

Couchbase Server dùng cơ chế synchronous durability để mutation được commit khi đạt yêu cầu majority/persistence.

~~~mermaid
sequenceDiagram
    participant W as Writer A
    participant Active as Active vBucket
    participant Replica as Replica vBucket
    participant Reader as Reader B
    W->>Active: replace(key, newValue, MAJORITY)
    Active->>Replica: Prepare/replicate pending mutation
    Reader->>Active: get(key) khi đang pending
    Active-->>Reader: Giá trị cũ đã commit
    Note over Active,Replica: Đợi điều kiện durability
    Replica-->>Active: Đủ điều kiện
    Active->>Active: Commit
    Active-->>W: Success
    Reader->>Active: get(key) sau commit
    Active-->>Reader: Giá trị mới
~~~

Trong khi mutation vẫn pending, đọc có thể thấy **giá trị cũ đã commit**. Một mutation mới vào cùng key có thể nhận trạng thái `SYNC_WRITE_IN_PROGRESS`. Khi server abort durable write, các thay đổi pending được hoàn nguyên theo giao thức.

### 6.1. SyncWrite timeout phía server

Khi server không đạt yêu cầu trước deadline của nó, server có thể abort pending write và thông báo **ambiguous result**. Đây là ngữ nghĩa từ góc nhìn client: không nhận biết chắc trạng thái cuối trong mọi trường hợp, nhất là khi failover, rebalance hoặc response bị mất.

Đừng đồng nhất:

- “Server đã abort mutation pending sau một timeout xác định”.
- “Ứng dụng nhận timeout và biết chắc mutation không tồn tại”.

Hai mệnh đề trên chỉ liên hệ với nhau khi ứng dụng **có bằng chứng về response/kết quả của đúng thao tác**, không phải suy luận từ đồng hồ của client.

### 6.2. Active node lỗi khi đang pending

Nếu active node lỗi, request có thể mất response; replica được promote và trạng thái pending mutation có thể được xử lý theo protocol/recovery. Kết quả phía caller phải được coi là **không chắc chắn** nếu chưa được xác nhận.

### 6.3. Rebalance cũng có thể làm outcome ambiguous

Trong một số tình huống hiếm, active vBucket được chuyển node trong lúc durable write đang chạy, khiến SDK nhận ambiguous. Không mặc định rebalance phải tắt mọi mutation, nhưng phải **test retry/idempotency** trên môi trường được phép.

## 7. “Unambiguous” và “ambiguous” nghĩa là gì?

Hai từ mô tả **mức độ chắc chắn về tác động của một operation**, không phải mức độ nghiêm trọng của exception.

| Phân loại | SDK biết gì? | Có thể kết luận gì? |
|---|---|---|
| **Unambiguous timeout** | SDK có cơ sở để xác nhận operation chưa thành công/tạo side effect | Có thể lên kế hoạch retry theo loại operation, deadline và business rule |
| **Ambiguous timeout** | SDK không biết operation có hoàn tất ở server không | Không được tự khẳng định “chưa ghi” hoặc “đã ghi” |
| **Durability ambiguous** | Kết quả synchronous durability không thể xác nhận rõ ràng với caller | Cần đối soát trạng thái; tránh retry non-idempotent |
| **Success** | SDK đã nhận response thành công | Có thể tiếp tục theo **effective durability contract** |
| **Explicit failure** | Server/SDK trả lỗi được phân loại, ví dụ duplicate/CAS | Xử lý nguyên nhân cụ thể; không gộp vào ambiguous |

Lưu ý: `DurabilityAmbiguousException` là một loại exception riêng của Java SDK core; **không nên mặc định nó kế thừa `AmbiguousTimeoutException`** hoặc bị bắt bởi mọi `catch (TimeoutException)`. Cần phân loại rõ khi viết code.

### 7.1. Trường hợp “đã gửi request nhưng không có response”

~~~mermaid
sequenceDiagram
    participant Client as SDK
    participant Active as Active
    participant Rep as Replica
    Client->>Active: INSERT id + MAJORITY
    Active->>Rep: Prepare/replicate
    Rep-->>Active: Đủ điều kiện
    Active->>Active: Commit
    Active--xClient: Response bị mất
    Note over Client: Hết deadline
    Client-->>Client: AmbiguousTimeoutException hoặc lỗi tương ứng
~~~

Điểm quan trọng là **success ở server và success được client quan sát không phải một sự kiện duy nhất**.

### 7.2. Unambiguous cũng không có nghĩa retry vô hạn

Nếu SDK xác định operation chưa tạo tác động, retry cùng request có thể hợp lý. Nhưng:

- API còn deadline không?
- Thao tác còn hợp lệ theo business state mới nhất không?
- Client có thể đã gửi **một request khác** với cùng idempotency key không?
- Hệ thống đang quá tải, thêm retry có làm hại availability không?

Không có “unambiguous” nào tự bảo đảm toàn bộ workflow ngoài Couchbase an toàn.

## 8. Những exception chính cần phân biệt trong Java SDK

Java SDK Core IO có các exception dạng:

~~~java
import com.couchbase.client.core.error.AmbiguousTimeoutException;
import com.couchbase.client.core.error.UnambiguousTimeoutException;
import com.couchbase.client.core.error.DurabilityAmbiguousException;
import com.couchbase.client.core.error.DurabilityImpossibleException;
import com.couchbase.client.core.error.DurabilityLevelNotAvailableException;
import com.couchbase.client.core.error.DurableWriteInProgressException;
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.core.error.CasMismatchException;
~~~

| Exception/nhóm lỗi | Ý nghĩa chính | Hướng xử lý |
|---|---|---|
| `AmbiguousTimeoutException` | Timeout và không chắc mutation đã có side effect | Đối soát theo ID, không tạo ID mới |
| `UnambiguousTimeoutException` | SDK chắc thao tác timeout chưa thành công | Retry có điều kiện và budget, kiểm tra khả năng quá tải |
| `DurabilityAmbiguousException` | Outcome durable write không thể xác định | Reconciliation, xác minh business state và yêu cầu durability |
| `DurabilityImpossibleException` | Điều kiện durability hiện không thể đạt (ví dụ replica) | Kiểm tra topology, không tự hạ level |
| `DurabilityLevelNotAvailableException` | Level không có trên server/bucket | Sửa cấu hình/support, không retry vô hạn |
| `DurableWriteInProgressException` | Key đang có pending SyncWrite | Backoff, giới hạn retry, kiểm tra hot key |
| `DocumentExistsException` | `insert` gặp ID đã tồn tại | Đọc/so payload của yêu cầu trước |
| `CasMismatchException` | `replace` với CAS cũ | Đọc lại và tái đánh giá chuyển trạng thái |
| `RequestCanceledException` | SDK hủy request do retry strategy/IO/backpressure/shutdown... | Xem error context; không tự đồng nhất với chưa có side effect |

Tên và phân loại cần đối chiếu phiên bản Java SDK. **Một timeout loại nào cũng là tín hiệu phải tìm nguyên nhân gốc**, không phải lý do tự tăng mọi deadline.

### 8.1. Timeout khác lỗi không đủ replica

`DurabilityImpossibleException` có thể phản ánh bucket với số replica không hỗ trợ Sync Writes, hoặc trạng thái replica không thể đáp ứng điều kiện. Tăng timeout từ 10 giây lên 60 giây không tạo thêm Data replica.

### 8.2. Pending write trên cùng key

`SYNC_WRITE_IN_PROGRESS` không chứng minh mutation trước sẽ thành công; nó chỉ cho thấy key đang có thay đổi pending. Retry nên giới hạn và có backoff; nếu nhiều writer đang đụng một hot key, cần xem lại thiết kế dữ liệu và concurrency control.

### 8.3. ErrorContext và retry reasons

Java SDK đính kèm `ErrorContext` vào nhiều exception để điều tra lý do retry, endpoint, thời gian và trạng thái request. Khi ghi log cần:

- Lấy exception class, operation, latency, correlation ID.
- Xem các retry reasons/attempts khi SDK cung cấp.
- Che document content, credentials, session/payment tokens.
- Đối chiếu timestamp với failover/rebalance và sức khỏe Data node.

Không tự cho rằng mỗi lần SDK retry tương ứng một mutation đã được commit. SDK có chiến lược retry theo lifecycle và idempotence ở tầng giao thức.

## 9. Idempotence của SDK khác idempotency nghiệp vụ

**SDK idempotence:** một operation được xem an toàn để gửi lại theo mô hình SDK khi request không có phản hồi. Java SDK có danh sách operation mà nó coi idempotent sẵn: `get`, `lookupIn`, `exists`, đọc replica, ping, v.v. Nó **rất thận trọng với mutation** vì side effect có thể bị áp hai lần hoặc ghi đè dữ liệu mới.

**Idempotency nghiệp vụ:** cùng một lệnh checkout dù request HTTP được gửi nhiều lần thì **không tạo nhiều đơn hoặc charge nhiều lần**.

Hai tầng khác nhau:

| Câu hỏi | SDK trả lời? | Business application trả lời? |
|---|---|---|
| Có nên retry request trước dispatch không? | Có ngữ cảnh ở SDK | Không cần biết socket |
| Request mutation đã tới server chưa? | Có thể biết hoặc phải báo ambiguous | Phải xử lý nếu chưa chắc |
| Cùng checkout ID đã được xử lý chưa? | Không biết business workflow | **Phải kiểm tra** |
| Duplicate ID là cùng payload hay request khác? | SDK chỉ biết key đã tồn tại | **Phải đối chiếu fingerprint/tenant** |
| Có được charge lại payment gateway không? | Không | **Phải dùng idempotency ở gateway** |

Không thay `RetryStrategy` mặc định thành “retry mọi write” khi chưa chứng minh side effect an toàn. SDK `BestEffortRetryStrategy` đã xử lý những tình huống có thể retry theo logic mặc định; phần ứng dụng bổ sung **retry dựa trên business invariant**, không chạy lại non-idempotent mutation một cách mù quáng.

### 9.1. Retry là thêm tải lên một hệ thống đang lỗi

Nếu replica/disk đang quá tải, 1000 request timeout đồng loạt mà mỗi request retry 5 lần có thể khiến hệ thống càng nghẽn. Cần:

- Exponential backoff có jitter.
- Retry budget theo deadline tổng.
- Giới hạn concurrency.
- Circuit breaker khi có cơ sở.
- Reconciliation queue cho outcome chưa rõ thay vì spam server.

## 10. Đừng coi mọi mutation là idempotent

| Operation | Nếu gửi lại sau outcome ambiguous | Điều cần bảo vệ |
|---|---|---|
| `insert(id, body)` | Lần hai có thể báo duplicate nếu lần đầu commit | ID cố định và fingerprint; duplicate không đồng nghĩa sai nếu cùng request |
| `upsert(id, body)` | Có thể ghi lại body và ghi đè thay đổi người khác | CAS/ownership, version, kiểm tra business rule |
| `replace(id, body, CAS)` | CAS cũ có thể conflict nếu lần đầu đã commit | Đọc lại, tái tính trạng thái; không bỏ CAS |
| `remove(id)` | Lần hai có thể not-found | Xác minh business đã hoàn tất; lưu audit khi cần |
| `increment/decrement` | Có thể tăng/giảm hai lần | Command ID/dedupe, transaction hoặc thiết kế khác |
| `mutateIn` | Tùy phép toán: replace field khác counter/array append | Đánh giá từng subdoc operation |
| Transaction callback | Có thể bị SDK chạy lại | Không side effect ngoài không idempotent trong callback |

### 10.1. “Upsert cùng JSON” không luôn an toàn

Nếu request A `upsert` một body, rồi request B sửa vài trường, A retry muộn có thể ghi đè thay đổi của B. Tính lặp lại của một giá trị JSON không đủ để khẳng định workflow idempotent trong môi trường nhiều writer.

### 10.2. “Insert trùng key” cần đối chiếu

Nếu document `orderId` đã có và phù hợp tenant/fingerprint của checkout trước, trả lại kết quả đã có là một **lựa chọn idempotent cấp nghiệp vụ**. Nếu payload khác, phải từ chối hoặc báo conflict; không dùng bản ghi của người khác.

### 10.3. Counter nguy hiểm khi timeout

Giả sử `increment("inventoryReserved")` đã thành công nhưng response mất, retry sẽ có thể tăng thêm lần nữa. Đừng coi counter mutation đơn lẻ là exactly-once. Với inventory/finance cần mô hình command dedupe hoặc transactional invariant phù hợp.

## 11. Thiết kế document ID và idempotency key

Một mẫu đơn giản:

~~~text
Input:
  tenantId = 42
  checkoutId = checkout-abc
  canonicalRequestFingerprint = SHA-256(canonical payload)

Document key:
  tenant::42::checkout::checkout-abc
~~~

Trường quan trọng:

~~~json
{
  "tenantId": "42",
  "checkoutId": "checkout-abc",
  "requestFingerprint": "sha256-of-canonical-request",
  "status": "NEW",
  "total": 1490000
}
~~~

Quy tắc:

1. Cùng tenant và checkout phải ra **cùng document ID** trong mọi retry.
2. Một key không được tái sử dụng cho payload khác; nếu khác fingerprint thì **conflict**.
3. Không đưa PII/token nhạy cảm trực tiếp vào document key hoặc log.
4. Xác định thời hạn lưu idempotency record đủ dài so với khả năng client retry.
5. Nếu TTL dùng cho idempotency record, đừng để record hết hạn trước khi một retry muộn có thể tái tạo side effect.
6. Không dùng timestamp/random ID mới tại mỗi retry của cùng business action.

### 11.1. Canonical fingerprint phải ổn định

Nếu JSON request có thứ tự field khác nhau nhưng cùng ý nghĩa, cách hash raw string có thể khác. Cần chuẩn hóa hoặc lưu các trường so sánh quan trọng, tránh dùng một fingerprint không ổn định khiến request hợp lệ bị coi là khác.

### 11.2. ID ổn định chưa thay thế transaction

Một order record và một payment record có thể cần cập nhật nhất quán. Idempotency giúp không tạo duplicate business command, còn transaction/saga/outbox giải quyết **atomicity hoặc phối hợp nhiều hệ thống** tùy phạm vi.

## 12. Quy trình xử lý kết quả ghi chưa rõ

### 12.1. State machine của một business command

~~~mermaid
flowchart TD
    A["Nhận POST + Idempotency-Key"]
    B["Sinh document ID cố định + fingerprint"]
    C["INSERT với required durability"]
    D{"Outcome"}
    S["Success: xác nhận trạng thái đã lưu"]
    X["Duplicate: đọc/so fingerprint"]
    U["Ambiguous: đưa vào luồng xác minh"]
    H{"KV read được bản phù hợp?"}
    Y["Có: hoàn tất business command theo quy tắc đối soát"]
    N["Không/chưa rõ: retry có giới hạn hoặc NEEDS_RECONCILIATION"]
    F["Payload khác: conflict"]
    A --> B --> C --> D
    D -->|"Success"| S
    D -->|"Duplicate"| X
    D -->|"Ambiguous"| U
    X --> H
    U --> H
    H -->|"Khớp"| Y
    H -->|"Không thấy/chưa biết"| N
    H -->|"Khác"| F
~~~

**Chú ý:** KV readback xác minh **trạng thái dữ liệu quan sát được**, không tự chứng minh mutation trước đã đạt durability level cụ thể nếu server áp fallback hoặc bạn không biết effective policy. Không suy luận từ `get` thấy record rằng response cũ “thực ra là thành công `PERSIST_TO_MAJORITY`”.

### 12.2. Tại sao một lần `get(id)` trả not-found chưa đủ?

Với durable write còn pending, client khác có thể thấy **giá trị cũ** hoặc chưa thấy document mới. Nếu request đến trước commit/abort, đọc lần đầu không tìm thấy không bảo đảm mutation sẽ **không** commit sau đó.

Vì thế:

- Giữ ID cố định để retry không tạo **document thứ hai**.
- Nếu chưa có trạng thái rõ, dùng policy chờ/backoff có giới hạn.
- Khi hết deadline tổng, đánh dấu cần reconciliation.
- Không thực hiện external side effect mới dựa trên “not found” tức thời.
- Dùng workflow record/queue bền **độc lập và được thiết kế trước** nếu cần theo dõi lâu dài.

### 12.3. Duplicate không phải bằng chứng của cùng request

Nếu `insert` báo `DocumentExistsException`, đọc bản hiện có và so sánh fingerprint, tenant, checkoutId, trạng thái. Chỉ trả idempotent success khi **khớp nghiệp vụ**, không chỉ trùng string ID.

## 13. Đối soát business state thay vì chỉ “đọc document”

Một đơn hàng có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> STORED: Có bản ghi hợp lệ
    REQUESTED --> NEEDS_RECONCILIATION: Ambiguous vượt budget
    NEEDS_RECONCILIATION --> STORED: Xác minh đã tạo
    NEEDS_RECONCILIATION --> FAILED: Xác minh chưa hoàn tất và hết hạn xử lý
    STORED --> PAID: Gateway xác nhận và state transition hợp lệ
    STORED --> CANCELLED: Nghiệp vụ hủy
~~~

Không đưa một request chưa rõ trực tiếp sang `FAILED` chỉ vì HTTP timeout. `FAILED` nên có nghĩa **đã có bằng chứng/thủ tục kết luận** rằng không thể hoặc không cần hoàn tất business command.

Trong hệ thanh toán, record tồn tại không chứng minh gateway đã charge; cần đối chiếu payment provider bằng idempotency key và receipt/reference đáng tin cậy.

### 13.1. Reconciliation job cần dữ liệu từ đâu?

- Request ID/idempotency key.
- Tenant và fingerprint.
- Tên operation, document ID, expected business state.
- Timestamp, attempt count, observed errors.
- Thông tin nguồn ngoài (gateway transaction ID nếu có).
- Quy trình cuối cùng để ghi nhận processed/rejected.

Một job được lập lịch không thể “chữa” mọi lỗi nếu record ban đầu chưa được lưu ở đâu tin cậy. Cần kiến trúc lưu command/inbox/outbox thích hợp với RPO.

## 14. Java SDK: chỉ định durability và timeout rõ ràng

Ví dụ Java SDK 3.x:

~~~java
import java.time.Duration;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

String id = "tenant::42::checkout::checkout-abc";

JsonObject orderBody = JsonObject.create()
    .put("tenantId", "42")
    .put("checkoutId", "checkout-abc")
    .put("requestFingerprint", requestFingerprint)
    .put("status", "NEW")
    .put("total", 1490000);

var result = orders.insert(
    id,
    orderBody,
    insertOptions()
        .durability(DurabilityLevel.MAJORITY)
        .timeout(Duration.ofSeconds(6))
);
~~~

Trong ví dụ:

- `orders` là `com.couchbase.client.java.Collection` đã cấu hình.
- `requestFingerprint` được tính một lần từ canonical business request.
- `insert` từ chối ID có sẵn.
- `MAJORITY` là **yêu cầu xác nhận**, không phải timeout.
- `timeout(6s)` là deadline SDK per-operation được lựa chọn theo SLO; không bảo đảm xong trong 6 giây.

Không tạo lại `Cluster.connect(...)` cho từng request. Ứng dụng Spring nên tái dùng lifecycle kết nối và đặt TLS/secret management đúng môi trường.

## 15. Java SDK: một mẫu phân loại exception

Sau đây là ví dụ **lõi phân loại**, chưa phải service production hoàn chỉnh:

~~~java
import com.couchbase.client.core.error.AmbiguousTimeoutException;
import com.couchbase.client.core.error.UnambiguousTimeoutException;
import com.couchbase.client.core.error.DurabilityAmbiguousException;
import com.couchbase.client.core.error.DurabilityImpossibleException;
import com.couchbase.client.core.error.DocumentExistsException;

enum WriteDecision {
    SUCCESS,
    CHECK_EXISTING,
    RECONCILE,
    RETRY_WITH_BUDGET,
    FAIL_ENVIRONMENT
}

// Diễn giải outcome của một lời gọi create-only.
WriteDecision attemptInsert(
        com.couchbase.client.java.Collection collection,
        String id,
        com.couchbase.client.java.json.JsonObject body) {
    try {
        collection.insert(
            id, body,
            com.couchbase.client.java.kv.InsertOptions.insertOptions()
                .durability(
                    com.couchbase.client.core.msg.kv.DurabilityLevel.MAJORITY
                )
                .timeout(java.time.Duration.ofSeconds(6))
        );
        return WriteDecision.SUCCESS;
    } catch (DocumentExistsException e) {
        // Chưa thể trả success: phải đọc và so fingerprint.
        return WriteDecision.CHECK_EXISTING;
    } catch (DurabilityAmbiguousException | AmbiguousTimeoutException e) {
        // Không được kết luận chưa ghi hoặc đã ghi.
        return WriteDecision.RECONCILE;
    } catch (UnambiguousTimeoutException e) {
        // Retry chỉ khi còn budget và business rule vẫn cho phép.
        return WriteDecision.RETRY_WITH_BUDGET;
    } catch (DurabilityImpossibleException e) {
        // Không hạ level tự động; chuyển điều tra topology.
        return WriteDecision.FAIL_ENVIRONMENT;
    }
}
~~~

**Phạm vi ví dụ:** không xử lý toàn bộ `CouchbaseException`, không trả HTTP, không implement reconcile và không bao gồm mọi SDK exception. Code production cần phân loại thêm lỗi bucket/permission, `DurabilityLevelNotAvailableException`, `RequestCanceledException` và các case version-specific.

### 15.1. Đừng bắt tất cả thành retry

Sai:

~~~java
try {
    orders.insert(id, body, insertOptions().durability(DurabilityLevel.MAJORITY));
} catch (RuntimeException ex) {
    orders.insert(generateAnotherRandomId(), body); // NGUY HIỂM
}
~~~

Lệnh trên có thể tạo duplicate nếu mutation đầu đã commit. Nó cũng có thể tạo retry storm khi cluster thiếu replica.

### 15.2. `UnambiguousTimeout` không miễn kiểm tra business rule

Với operation hiện tại được SDK xác định chưa tạo side effect, retry cùng **ID và payload** có thể hợp lý, nhưng caller có thể đã gửi một command khác hoặc state nghiệp vụ có thể đổi. Bảo vệ ở tầng business vẫn cần thiết.

## 16. CAS và replace sau timeout

Giả sử `order.status = NEW` với CAS V1. API muốn chuyển thành `PAID`:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import java.time.Duration;

var old = orders.get(orderId);
var oldBody = old.contentAsObject();

if (!"NEW".equals(oldBody.getString("status"))) {
    throw new IllegalStateException("Order không còn NEW");
}

var next = oldBody.put("status", "PAID");

orders.replace(
    orderId, next,
    replaceOptions()
        .cas(old.cas())
        .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
        .timeout(Duration.ofSeconds(8))
);
~~~

Nếu response mất:

- Mutation có thể đã commit: CAS có thể đã đổi; retry với CAS V1 có thể bị từ chối.
- Mutation có thể chưa commit: CAS có thể còn V1 hoặc có mutation pending.
- Writer khác có thể đã đổi state sang `CANCELLED` hay trạng thái khác.

**Chiến lược:** đọc lại, kiểm tra state/payload/business rule rồi mới quyết định retry; không bỏ CAS để ép cập nhật. Nếu trạng thái đã `PAID` do cùng business command, có thể đánh giá idempotent success sau đối chiếu transaction reference.

### 16.1. Retry bằng CAS mới nhưng body cũ cũng nguy hiểm

Sau CAS mismatch, lấy CAS mới rồi gửi body cũ mà không đọc/merge dữ liệu mới có thể xóa thay đổi của request khác. CAS chỉ hiệu quả khi **lấy lại bản hiện tại và tính toán lại mutation**.

### 16.2. TTL không phải câu trả lời cho timeout

Một mutation có expiry/TTL vẫn chịu ambiguity khi response mất. Đặt TTL 30 phút không nói gì về sự thành công của SyncWrite hoặc độ bền của order; expiration quyết định **vòng đời**, không xác nhận replication/persistence.

## 17. Spring Data Couchbase: entity default không giải quyết ambiguity

Trong Spring Data Couchbase, entity có thể khai báo mặc định durability:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String checkoutId;
    private String requestFingerprint;
    private String status;
    private Long total;

    // Constructors/getters/setters được lược bỏ.
}
~~~

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument stored = orderRepository.save(order);
~~~

Cần hiểu:

- `@Document(durabilityLevel = ...)` là **metadata mức durability mặc định** cho mutation qua mapping Spring Data khi phiên bản hỗ trợ.
- `@Version` dùng **CAS/optimistic locking**, không phải durability hoặc timeout.
- `save` trả entity khi hoàn tất thành công theo contract hiện hành; một exception khi `save` timeout **không tự chứng minh mutation đã rollback**.
- Một đường code gọi SDK `Collection.insert(id, JsonObject)` **không tự đọc annotation Spring**.
- Tên exception có thể đã được Spring Data chuyển đổi; phải kiểm tra exception translation ở version dùng trong dự án.

### 17.1. Chọn create-only thay vì save nếu yêu cầu nghiệp vụ

`save` là abstraction CRUD; khi tạo đơn theo idempotency key, có thể muốn dùng đường `insertById` để **báo duplicate thay vì ghi đè**:

~~~java
OrderDocument created = template
        .insertById(OrderDocument.class)
        .withDurability(DurabilityLevel.MAJORITY)
        .one(order);
~~~

Cách này rõ về operation semantics. Vẫn cần logic kiểm tra duplicate/idempotency và timeout; `insertById` không tự giải quyết reconciliation.

### 17.2. Override level không loại bỏ nguy cơ timeout

~~~java
OrderDocument result = template
        .upsertById(OrderDocument.class)
        .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
        .one(order);
~~~

`withDurability` chỉ định yêu cầu cho mutation; không hứa rằng mọi response sẽ về trước deadline HTTP, không ngăn đồng thời update ngoài ý muốn và không bỏ qua minimum bucket.

### 17.3. Repository và SDK có error taxonomy khác hình thức

SDK có thể ném `DurabilityAmbiguousException` hoặc `AmbiguousTimeoutException`. Tùy Spring Data version, repository/template có thể bọc hoặc dịch một số lỗi thành `DataAccessException` hoặc lớp khác.

Không viết catch theo một SDK exception class ở tầng repository **rồi mặc định đã xử lý mọi ambiguous**. Integration test phải xác minh loại exception/cause chain thực tế khi test inject fault.

## 18. Reactive và cancellation: caller ngừng chờ không phải rollback

Reactive Couchbase SDK và Spring Data Couchbase dùng các publisher `Mono`/`Flux`. Khi thêm operator timeout:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<?> write = orders.reactive()
        .insert(
            orderId,
            orderBody,
            insertOptions().durability(DurabilityLevel.MAJORITY)
        )
        .timeout(Duration.ofSeconds(4));
~~~

`Mono.timeout(...)` đặt giới hạn **ở pipeline Reactor**. Khi timeout, Reactor có thể cancel subscription, nhưng **không có bảo đảm mutation đã dispatch được rollback tại Data Service**. Nếu server commit trước hoặc sau khi caller ngừng chờ, business command vẫn có thể thành công.

### 18.1. Hai deadline cần thiết kế cùng nhau

~~~text
HTTP/gateway timeout:  5 giây
Reactor timeout:       4 giây
SDK durable timeout:   6 giây
Server SyncWrite:      theo protocol/timeouts hỗ trợ

Đây chỉ là cấu hình minh họa, KHÔNG phải đề xuất mặc định.
~~~

Nếu Reactor timeout trước SDK và không có cơ chế đối soát, caller có thể nhận lỗi trong khi SDK/server tiếp tục hoặc vừa hoàn tất side effect.

Không chọn các số chỉ vì “đi từ ngoài vào trong nhỏ dần”; cần phân tích **khi nào trả trạng thái chưa chắc chắn, ai còn giữ operation ID và ai có trách nhiệm reconciliation**.

### 18.2. `retryWhen` có thể gửi lại mutation

Sai:

~~~java
Mono<?> unsafe = Mono.defer(() ->
        orders.reactive().insert(
            java.util.UUID.randomUUID().toString(),
            orderBody,
            insertOptions().durability(DurabilityLevel.MAJORITY)
        )
    )
        .retryWhen(reactor.util.retry.Retry.max(3));
~~~

Vì `Mono.defer` chạy lại lambda khi có subscription mới, mỗi lần retry trong ví dụ có thể sinh một document ID khác, làm tạo trùng đơn. Quan trọng hơn, retry mọi exception có thể tái thực hiện mutation trong trạng thái ambiguous.

Cách an toàn hơn:

~~~java
String stableOrderId = "tenant::42::checkout::checkout-abc";

Mono<?> controlled = orders.reactive()
        .insert(
            stableOrderId,
            orderBody,
            insertOptions().durability(DurabilityLevel.MAJORITY)
        )
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                    2, Duration.ofMillis(100)
                )
                .filter(error ->
                    error instanceof
                    com.couchbase.client.core.error.UnambiguousTimeoutException
                )
        );
~~~

Đoạn code chỉ minh họa retry **nhóm lỗi đã được SDK xác định không tạo side effect**; production cần phối hợp tổng deadline, duplicate handling, tracing và business state. Không dùng `retryWhen` cho ambiguous mutation nếu chưa có thiết kế verify/reconcile.

### 18.3. Spring WebFlux cũng phải giữ idempotency key

Dù controller trả `Mono<ServerResponse>` hay Spring MVC trả synchronous response, client HTTP có thể gửi lại yêu cầu khi timeout. Một idempotency key phải được xử lý ở **service/business layer** chứ không chỉ trong một subscription.

## 19. Thiết kế response HTTP khi database outcome chưa rõ

Khi xử lý `POST /orders`, không chỉ có thành công và thất bại:

| Trạng thái thực tế | Có nên trả “đơn đã tạo” không? | Gợi ý contract |
|---|---|---|
| Mutation trả success rõ ràng, đạt level | Có | `201 Created` kèm order ID |
| Document trùng và khớp idempotency request | Có thể trả kết quả cũ | `200/201` theo API contract đã công bố |
| Cùng idempotency key nhưng fingerprint khác | Không | `409 Conflict` |
| Mutation unambiguous failure, chưa có effect | Không | Error phù hợp; có thể retry cùng key |
| Mutation ambiguous | **Không khẳng định đã tạo hay chưa tạo** | Trả lỗi/“kết quả chưa xác minh” với operation ID và hướng tra cứu |
| Command đã được lưu bền **ở một hệ thống inbox/queue độc lập** | Có thể xác nhận **đã nhận yêu cầu**, chưa xác nhận đơn đã ghi Couchbase | `202 Accepted` kèm status endpoint, nếu điều đó đúng sự thật |

**Cảnh báo:** không nên trả `202 Accepted` chỉ vì Couchbase timeout nếu **chưa thực sự có nguồn tin cậy giữ command để xử lý tiếp**. Nếu toàn bộ tiến trình sẽ mất command khi process crash, gọi “đã tiếp nhận bền” là sai.

### 19.1. Một response minh họa khi chưa xác minh

~~~json
{
  "code": "ORDER_WRITE_UNCONFIRMED",
  "requestId": "checkout-abc",
  "message": "Chưa xác minh được kết quả lưu đơn.",
  "nextAction": "Tra cứu bằng requestId hoặc thử lại với cùng Idempotency-Key."
}
~~~

HTTP status có thể là `503 Service Unavailable`, `504 Gateway Timeout` hoặc mã phù hợp gateway/API policy. Điểm cốt lõi không phải một mã cố định, mà là **contract không tuyên bố chắc chắn mutation đã thất bại hoặc đã thành công**.

### 19.2. Query status endpoint cần sự thật có thể kiểm chứng

~~~http
GET /operations/checkout-abc
~~~

Endpoint này có thể trả trạng thái business command **nếu ứng dụng có record/status store đáng tin cậy để tra cứu**. Nếu chỉ đọc một `orderId` sau timeout, phải xử lý tình huống pending write và query chưa mới, tránh nhận định quá sớm.

### 19.3. Idempotency key được truyền xuyên các tầng

Gateway, service, SDK adapter, reconciliation worker và payment gateway nên có correlation dựa trên cùng business operation ID khi phù hợp. Không yêu cầu mọi nơi lộ ID nhạy cảm; có thể hash/redact trong log.

## 20. Ngân sách timeout end-to-end thay vì tăng một con số

Một endpoint có nhiều bước:

~~~text
POST /orders
  1. Parse + authorize
  2. Validate cart, price, inventory
  3. KV insert order với MAJORITY
  4. External side effect hoặc outbox
  5. Serialize response
~~~

Tổng thời gian gồm network RTT, queueing, business CPU, DB I/O, transaction contention và response. Nếu DB durable write có default 10 giây nhưng HTTP SLO p99 mục tiêu 800 ms, **đây là một chênh lệch cần quyết định kiến trúc**, không chỉ đổi timeout vô điều kiện.

### 20.1. Ví dụ bảng budget

| Thành phần | Giả định để thiết kế | Cần kiểm tra |
|---|---:|---|
| Auth/validation | 40 ms | p99 thực tế, không chỉ trung bình |
| Read business state | 80 ms | KV/SQL++ khác nhau |
| Durable mutation | 450 ms | p95/p99 theo load và level |
| Response/network | 60 ms | Gateway/zone |
| Headroom | 170 ms | GC, jitter, contention |
| **Tổng minh họa** | **800 ms** | Không được coi đây là SLO đã chứng minh |

Các số chỉ là ví dụ. p99 end-to-end không được suy ra chính xác bằng cách cộng p99 của từng bước vì phân phối và tương quan khác nhau; phải đo HTTP request thật.

### 20.2. Khi p99 durable write vượt SLO

Đầu tiên cần:

1. Xác định một hay nhiều vBucket/hot key bị ảnh hưởng.
2. Kiểm tra replica health, rebalance/failover và quorum.
3. Kiểm tra disk latency/network, nhất là persistence levels.
4. Đo SDK retries và caller retries; tránh nhân tải.
5. Xem cluster scaling/capacity hoặc thay đổi workflow nếu thực sự cần.
6. Chỉ thay durability khi business owner đã đánh giá thay đổi RPO.

Tăng timeout có thể giảm một số timeout do deadline quá ngắn nhưng **không loại bỏ bottleneck**; đồng thời có thể kéo dài thời gian người dùng chờ.

## 21. GSI và SQL++: timeout khác, “đã ghi nhưng chưa thấy” cũng khác

Sau khi `insert` theo KV hoàn tất durable write, `findById(id)` truy cập Data Service theo ID. Một query derived repository theo `status` thường dùng SQL++ và GSI cập nhật **bất đồng bộ**.

~~~text
T0: insert orderId với MAJORITY -> success
T1: SQL++ WHERE status="NEW" -> chưa thấy row
T2: GSI bắt kịp mutation
T3: SQL++ query thấy row
~~~

Đây có thể là **index freshness**, không phải lỗi durability hay timeout.

| Nhu cầu | Cơ chế |
|---|---|
| Đã biết orderId, cần đối chiếu sau timeout | KV get theo ID, rồi kiểm tra fingerprint/state |
| Danh sách có thể chậm cập nhật | SQL++ `not_bounded` |
| Cần GSI theo kịp mutation trước request | `request_plus` |
| Cần đọc-your-own-write theo token cụ thể | `consistentWith(MutationState)` nếu có token hợp lệ |

Không dùng SQL++ mặc định làm bước xác minh duy nhất cho ambiguous KV insert: index có thể stale, khiến false negative. Ngược lại, `request_plus` có thể tăng query latency nhưng **không sửa được một durable mutation chưa rõ đã commit hay chưa**.

## 22. Bảo đảm của transaction và outbox không thay timeout

Một workflow có thể cập nhật `orders` và `inventory` trong Couchbase Transactions. Transaction có retry, timeout và commit semantics riêng; callback có thể được chạy lại theo SDK khi conflict.

- Một transaction timeout cũng có thể yêu cầu kiểm tra trạng thái, không được coi mọi mutation đã rollback chỉ từ HTTP timeout.
- Mutation ngoài transaction không tự thuộc atomicity của transaction.
- Không gọi payment gateway/email/Kafka không idempotent trực tiếp trong transaction callback.
- Durability option của một KV write **không thiết lập durability của cả transaction** ngoài API/cấu hình transaction thực tế.

### 22.1. Transaction xử lý nhiều document, idempotency xử lý lặp command

| Mục tiêu | Cơ chế |
|---|---|
| Các KV mutation nhiều document cùng commit/rollback | Couchbase Transactions theo contract hỗ trợ |
| Một business command HTTP không tạo hai order | Idempotency key + dedupe + reconciliation |
| Không charge payment gateway hai lần | Idempotency ở gateway và workflow orchestration |
| Sự kiện outbound không mất/trùng không kiểm soát | Outbox/inbox, retry và idempotent consumer |
| Một mutation được xác nhận đủ replica/persistence | `DurabilityLevel` và topology |
| Khôi phục sau mất site hoặc xóa nhầm | Backup/DR và retention policy |

Không một cơ chế đơn lẻ giải quyết tất cả các cột này. Thiết kế timeout đúng cần nhìn **toàn bộ đường đi của side effect**.

## 23. Một runbook ứng dụng xử lý ambiguous mutation

Đây là runbook ở tầng application, không phải hướng dẫn thực hiện failover production.

### Bước 1 — Ghi nhận identity và context

Ghi: `requestId`, idempotency key hash, keyspace, operation, document ID hash, durability yêu cầu, timeout ngân sách, SDK exception, timestamp.

### Bước 2 — Phân loại lỗi

Đâu là `DocumentExists`, CAS mismatch, `DurabilityImpossible`, `UnambiguousTimeout` hay ambiguous? Đừng gộp tất cả thành `IOException` rồi retry.

### Bước 3 — Xác minh theo KV ID

Đọc record nếu có thể; so tenant, checkout ID và fingerprint. Nếu thấy bản phù hợp, xác định business workflow đã đạt mốc nào. Nếu chưa thấy, ghi nhận **chưa xác minh**, không coi chắc chắn không tồn tại.

### Bước 4 — Giới hạn retry và side effect

Retry cùng business ID/ID document theo policy. Không gọi cổng thanh toán lần hai hoặc phát event mới nếu trạng thái chưa rõ. Có backoff/jitter và total deadline.

### Bước 5 — Ghi nhận reconciliation

Nếu vượt budget, chuyển command vào **hệ thống theo dõi tin cậy đã thiết kế**, hoặc báo cần can thiệp nếu không có cách giữ state an toàn. Reconciliation cần owner, SLA và cảnh báo.

### Bước 6 — Escalate đúng người

Nếu quan sát nhiều error do replica missing, active failover, rebalance, disk/network, gửi dữ liệu tổng hợp đến DBA/SRE; không tự tắt TLS hay hạ durability level.

### Bước 7 — Kết thúc incident bằng đối soát

Không chỉ khôi phục success rate; xác minh các request ambiguous còn tồn, đơn trùng, charge trùng và record chưa được quyết định.

## 24. Observability: các chỉ số thật sự giúp tìm nguyên nhân timeout

### 24.1. Phía service/Java SDK

- KV mutation p50/p95/p99 chia theo `insert/replace/upsert/remove`.
- `requestedDurability` và keyspace, theo endpoint.
- Error rate chia `ambiguousTimeout`, `unambiguousTimeout`, `durabilityAmbiguous`, `durabilityImpossible`, CAS mismatch, duplicate.
- Retry attempts/reasons, elapsed time, request queueing, timeout configuration.
- Số workflow `NEEDS_RECONCILIATION`, thời gian chờ đối soát, kết quả cuối cùng.
- API HTTP p95/p99, gateway timeouts và caller retries.
- Business duplicate và payment side effects bị lặp.

### 24.2. Phía cluster

- Data Service active/replica vBucket health, under-replication.
- CPU, disk latency/IOPS, memory, network saturation.
- Failover, rebalance và cluster map churn.
- Pending SyncWrites, timeout/abort và service health nếu telemetry có sẵn theo version.
- Sự kiện thay đổi minimum durability/fallback ở bucket.
- Backup success, RPO/RTO trong các bài phục hồi.

### 24.3. Mẫu log an toàn

~~~text
time=2026-11-25T03:10:00Z
service=order-api
operation=KV_INSERT
bucket=commerce scope=sales collection=orders
correlationId=checkout-abc
docKeyHash=redacted
durabilityRequested=MAJORITY
sdkTimeoutMs=6000
outcome=AMBIGUOUS
exceptionClass=AmbiguousTimeoutException
attempt=1
durationMs=...
retryReasons=redacted-summary
reconciliationStatus=OPEN
~~~

Các trường này là **định dạng minh họa** chứ không khẳng định SDK tự phát toàn bộ metric. Không ghi JSON payment, secrets, token hoặc nguyên document ID có PII vào logs.

## 25. Triage: timeout do cấu hình hay do hạ tầng?

| Triệu chứng | Kiểm tra tại ứng dụng | Cần DBA/SRE hỗ trợ khi |
|---|---|---|
| Nhiều `UnambiguousTimeout` ngay trước dispatch | Bootstrap, DNS, TLS, SDK routing, connection management | Network policies hoặc cluster endpoints không khả dụng |
| Chỉ `MAJORITY` timeout, `NONE` ít lỗi | Level/replica/bucket policy, p99 | Replica thiếu quorum, Data nodes failover |
| Persist levels chậm, majority memory ổn | So latency theo level, timeout | Disk I/O bottleneck và storage capacity |
| Timeout trùng giờ rebalance | Timestamp, retry reasons, ambiguous count | Data movement, vBucket owner churn |
| CAS conflicts nhiều ở một key | Business concurrency và retry loop | Hot key hoặc Data saturation ngoài thiết kế |
| Gateway trả 504 trước SDK timeout | Deadline từng tầng, caller cancellation | Sửa timeout budget/workflow, không chỉ cluster |
| Reactor `Mono.timeout` xuất hiện | Operator placement, side-effect publisher, cancellation | Chỉ chuyển hạ tầng nếu SDK latency thực cao |
| Duplicate sau timeout | Sinh ID, idempotency, retry HTTP | Thường phải sửa ứng dụng trước |
| `findById` thấy record, SQL++ chưa thấy | Scan consistency và GSI lag | Index Service quá tải, index offline |
| SDK báo `DurabilityImpossible` | Bucket type, replica count và level | Sửa topology/policy, không retry vô hạn |

Có thể có hơn một nguyên nhân đồng thời; dùng correlation ID/timestamp để liên hệ sự kiện thay vì suy luận từ một exception rời rạc.

## 26. Case study A — timeout HTTP sớm hơn durable write

**Tình huống:** gateway có upstream timeout 2 giây, app SDK durable timeout 10 giây. `POST /checkout` nhận 504 sau 2 giây. Một vài giây sau, server có thể đã commit order.

**Cách xử lý sai:** mobile tự tạo checkoutId mới và thử lại.

**Cách xử lý đúng:** mobile giữ idempotency key. Backend/API contract phân biệt “chưa xác minh” với “thất bại chắc chắn”, có đường đọc/đối soát đáng tin cậy. Nếu muốn xác nhận đã tiếp nhận để xử lý sau, cần một inbox/queue bền được thiết kế trước.

**Bài học:** HTTP timeout không tự rollback database mutation, và tính đúng đắn phải được thiết kế xuyên các tầng.

## 27. Case study B — một replica mất, `MAJORITY` không hoàn tất

**Tình huống:** bucket có một Data replica. Với vBucket liên quan, majority cần active và replica. Replica mất kết nối, active vẫn trả `get(id)`.

**Biểu hiện:** các mutation yêu cầu `MAJORITY` có thể timeout hoặc báo durability unavailable/impossible, trong khi một số lệnh đọc vẫn bình thường.

**Hướng xử lý:**

1. Kiểm tra level hiệu lực, replica count và topology.
2. Không bật fallback hoặc tự giảm durability để “làm hết lỗi” nếu chưa được chấp thuận thay đổi RPO.
3. Giới hạn caller retries để tránh tạo bão tải.
4. Xác minh các mutation ambiguous đã commit hay chưa theo business workflow.
5. Để DBA/SRE phục hồi redundancy/rebalance theo runbook.

**Bài học:** timeout có thể là hệ quả cố ý của contract “không báo success khi thiếu majority”.

## 28. Case study C — CAS conflict sau một lần timeout

**Tình huống:** order ở `NEW` với CAS V1. Request A dùng `replace(CAS V1)` chuyển thành `PAID`. Response của A mất. A retry với cùng CAS V1, nhận CAS mismatch.

**Sai lầm:** kết luận “A chưa thành công”, bỏ CAS rồi `upsert` `PAID` hoặc ghi đè trạng thái hiện hành.

**Đúng:** đọc lại document; nếu trạng thái `PAID` và transaction reference khớp A, có thể kết luận business command đã đạt state mong đợi sau kiểm tra. Nếu hiện tại là `CANCELLED` hoặc thuộc request khác, phải theo state machine, không ghi đè. Đồng thời đối chiếu gateway trước khi gọi payment lại.

**Bài học:** CAS mismatch sau timeout có thể chính là dấu hiệu phiên bản đã đổi, không cho biết **ai** đã đổi nếu chưa đọc và kiểm tra.

## 29. Case study D — reactive retry làm nhân mutation

**Tình huống:** pipeline tăng counter lượng đã bán:

~~~java
Mono<?> sold = counters.reactive()
    .binary()
    .increment("sold::sku-A1")
    .retryWhen(reactor.util.retry.Retry.max(5));
~~~

Đoạn trên chỉ là ví dụ phản ví dụ; API counter cụ thể phụ thuộc SDK overload và không nên copy vào production mà chưa xác minh. Nếu lần increment đầu đã xảy ra nhưng response mất, resubscribe có thể tăng lại.

**Thiết kế lại:** dùng command ID + bảng/record dedup hoặc transaction/invariant thích hợp, giới hạn retry và đối soát. Với quy trình đặt hàng, thay counter đơn lẻ bằng cập nhật tồn kho có CAS/transaction nếu business rule đòi không bán âm kho.

**Bài học:** reactive retry không bảo đảm exactly-once; mutation không idempotent cần workflow bảo vệ.

## 30. Kiểm thử lỗi trong môi trường được phép

Không hard failover production chỉ để kiểm chứng một bài học. Có thể dựng test cluster/staging hoặc môi trường mô phỏng mạng với **quyền và runbook** rõ ràng.

| Bài thử | Điều kiện | Xác nhận cần có |
|---|---|---|
| **SDK pre-dispatch timeout** | Cô lập endpoint trước khi gửi được request | Lỗi unambiguous khi SDK có bằng chứng; retry có giới hạn |
| **Response drop sau commit** | Test proxy/mock fault có kiểm soát | Ambiguous không tạo duplicate |
| **Server SyncWrite pending** | Replica chậm hoặc bị cách ly có chủ đích | Đọc thấy giá trị cũ; update cùng key có thể in-progress |
| **1 replica bị mất** | Test cluster có một replica | Majority writes không tự trở thành success yếu hơn policy |
| **2 replicas, một bản chậm** | Test cluster 3 Data nodes | Quan sát quorum/latency theo trạng thái thực |
| **Rebalance khi ghi** | Thực hiện theo runbook test | Đo ambiguous outcome, recovery và idempotency |
| **Gateway 504 trước SDK** | Timeout ở gateway ngắn hơn SDK | Caller retry cùng idempotency key; không tạo hai order |
| **Reactor `Mono.timeout`** | Subscriber cancel sớm | Không coi cancellation là rollback |
| **CAS after timeout** | Response bị mất trên replace | Readback/recompute state, không ép upsert |
| **SQL++ lag** | Ghi KV rồi query GSI | Không coi SQL++ not-found là write fail |
| **Backup/restore** | Restore sang môi trường riêng | RPO/RTO được đo riêng với durability |

### 30.1. Assertion quan trọng nhất

Các test phải xác minh ở **business level**:

- Cùng `Idempotency-Key` không tạo hai order.
- Không phát sinh double charge.
- Không báo đã tạo order khi backend chưa có chứng cứ đúng contract.
- Mọi ambiguous outcome đều có quy trình đối soát và kết quả cuối.
- Không hạ durability level khi replica lỗi nếu chưa được phê duyệt.
- Các metric hỗ trợ phân biệt lỗi client, network, SDK và cluster.

### 30.2. Đừng kiểm thử durability bằng sleep rồi SQL++

Lệnh `Thread.sleep(500)` rồi `SELECT ...` không chứng minh mutation đã persist ở majority. Nó có thể chỉ đo độ mới GSI hoặc tình trạng query plan. Kiểm thử durability cần dựa trên operation contract/level, loại bucket/topology và fault scenarios.

## 31. Bài tập tự luyện

### Bài A — ba thời điểm request

Giải thích pre-dispatch, dispatch và response. Khi nào SDK có thể xác định unambiguous timeout? Vì sao timeout sau dispatch có thể ambiguous?

### Bài B — ba tầng deadline

HTTP gateway timeout 2 giây, Reactor timeout 3 giây, SDK `kvDurableTimeout` 10 giây. Những kết luận nào **không thể** đưa ra chỉ vì mobile nhận HTTP 504? Đề xuất API contract thay thế.

### Bài C — default timeouts

Nêu giá trị `kvTimeout` và `kvDurableTimeout` theo tài liệu Java SDK đang tham khảo. Vì sao docs lưu ý không đặt `kvDurableTimeout` trên 65 giây? Tại sao không nên tự tăng tất cả lên 60 giây?

### Bài D — phân loại exception

Phân biệt `AmbiguousTimeoutException`, `UnambiguousTimeoutException`, `DurabilityAmbiguousException`, `DurabilityImpossibleException` và `DocumentExistsException`. Lỗi nào cần reconciliation thay vì blind retry?

### Bài E — idempotent insert

Thiết kế document key từ tenantId và checkoutId. Nếu lần retry báo duplicate, cần đối chiếu thông tin gì trước khi trả kết quả cũ?

### Bài F — CAS và lost update

Một `replace` với CAS V1 timeout, sau đó retry báo mismatch. Có thể kết luận lần đầu đã commit không? Trình bày các bước đọc lại và kiểm tra business state.

### Bài G — upsert và counter

Tại sao `upsert` cùng body không luôn an toàn trong môi trường nhiều writer? Vì sao `increment` không nên tự động retry sau ambiguous timeout?

### Bài H — Reactor

Giải thích tại sao `Mono.timeout` và `retryWhen` không tự bảo đảm rollback/exactly-once. Viết pseudo-code tạo ID ổn định trước subscription, chỉ retry nhóm unambiguous.

### Bài I — SQL++ và GSI

KV `get(id)` thấy đơn nhưng derived query `findByStatus` không thấy. Đây là timeout, durability failure hay index lag? Làm sao chọn cách xác minh đúng?

### Bài J — runbook

Viết runbook 7 bước khi `POST /orders` xuất hiện 2% ambiguous outcomes trong thời điểm rebalance. Cần những metric, owner và reconciliation workflow nào?

### Bài K — thiết kế HTTP

Khi nào có thể trả `201`, `409` và `202`? Vì sao không thể dùng `202 Accepted` để che một Couchbase timeout nếu command chưa được lưu bền vào nơi khác?

### Bài L — fault injection

Thiết kế test “server commit nhưng response bị drop” trên staging. Chứng minh rằng một checkout chỉ tạo một order và trạng thái được đối soát sau khi SDK/client hết deadline.

## 32. Checklist trước production

- [ ] Ghi rõ level durability và loại mutation ở từng critical endpoint.
- [ ] Phân biệt timeout ở gateway, service/Reactor, SDK và server.
- [ ] Kiểm tra effective `kvTimeout`/`kvDurableTimeout` theo SDK/version; không đoán.
- [ ] Không tăng mọi timeout để che disk/replica/network saturation.
- [ ] Phân loại `AmbiguousTimeout`, `UnambiguousTimeout` và `DurabilityAmbiguous` riêng.
- [ ] Xác nhận Spring Data exception translation/cause chain trong integration test.
- [ ] Dùng ID ổn định và fingerprint cho mỗi business command.
- [ ] Với `insert` duplicate, đọc/so fingerprint trước khi trả success.
- [ ] Với `replace` CAS mismatch, đọc và tính lại business rule.
- [ ] Không retry counter/upsert/transaction side effect không idempotent một cách mù quáng.
- [ ] Không dùng `Mono.timeout` như một lệnh rollback Couchbase.
- [ ] Hạn chế retry/backoff, concurrency, overall deadline và circuit-breaker theo nhu cầu.
- [ ] Với ambiguous, có reconciliation owner, SLA và nguồn dữ liệu tin cậy.
- [ ] Không trả `202 Accepted` nếu chưa có inbox/queue đáng tin để tiếp tục xử lý.
- [ ] Không tự hạ `DurabilityLevel` khi thiếu replica mà chưa review RPO.
- [ ] Không dùng SQL++ query mặc định làm bằng chứng một KV mutation không tồn tại.
- [ ] Có dashboard p95/p99, retry reasons, timeout rate, ambiguous count, business duplicates.
- [ ] Có failure drills cho response loss, rebalance, replica failure và HTTP timeout.
- [ ] Không log PII/credentials/payment token khi điều tra.
- [ ] Có backup/DR và phương án đối soát ngoài phạm vi replica.

## 33. Tổng kết

**Timeout không đồng nghĩa thao tác ghi đã thất bại.** Một KV mutation Couchbase có thể đã được commit nhưng response không đến client. Java SDK phân biệt `UnambiguousTimeoutException` (có cơ sở tin operation chưa gây side effect) và `AmbiguousTimeoutException` (không thể chắc đã hoàn tất hay chưa); durable writes còn có `DurabilityAmbiguousException` và những lỗi riêng về điều kiện replication/persistence.

Trong **Spring Data Couchbase**, `repository.save`, `CouchbaseTemplate.withDurability(...)`, Java SDK mutation options và reactive publishers đều chịu ranh giới thực tế này. `@Version`/CAS giúp chống ghi đè, `DurabilityLevel` đặt điều kiện xác nhận, nhưng **không cơ chế nào đảm bảo client luôn nhận được response**. Reactor cancellation, HTTP 504 hoặc query SQL++ chưa thấy document cũng không phải bằng chứng mutation đã rollback.

Thiết kế đúng cần **document ID/idempotency key ổn định, fingerprint, phân loại exception, retry có giới hạn, KV readback có hiểu biết về trạng thái pending, reconciliation và API contract trung thực**. Đồng thời phải đo p99, quan sát replica/disk/network và diễn tập lỗi. Khi outcome chưa rõ, trạng thái chính xác là **“chưa xác minh được”**, không phải tự chọn “đã thành công” hoặc “chưa hề xảy ra”.

## Tài liệu tham khảo chính thức

1. [Couchbase Java SDK — Handling Errors](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): lifecycle request, ambiguous/unambiguous timeout, SDK retry/idempotence, error context và Reactor.
2. [Couchbase Java SDK — Client Settings](https://docs.couchbase.com/java-sdk/current/ref/client-settings.html): timeout cấu hình, `kvTimeout`, `kvDurableTimeout` và giới hạn SyncWrite.
3. [Couchbase Java SDK — Error Messages](https://docs.couchbase.com/java-sdk/current/ref/error-codes.html): nhóm timeout/cancellation và lỗi KV.
4. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): SyncWrite pending/commit/abort, timeout, ambiguous result, failover/rebalance và phạm vi bảo đảm.
5. [Couchbase Java SDK — KV Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): mutation options, timeout và durability.
6. [Spring Data Couchbase — Template and Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): `@Document` default và fluent `withDurability(...)`.
7. [Couchbase JVM Core IO — Exception Javadoc](https://docs.couchbase.com/sdk-api/couchbase-core-io/com/couchbase/client/core/error/package-summary.html): các lớp exception cụ thể.

Các code snippet và con số timeout cần được đối chiếu với **phiên bản Spring Data, Java SDK, Couchbase Server/Capella và cấu hình bucket** thực tế trước khi triển khai. Bài học minh họa cách tư duy; không thay thế load test, recovery drill và phê duyệt RPO của tổ chức.


