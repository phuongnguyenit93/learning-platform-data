# CAS, thời gian hết hạn và mã thông báo thay đổi trong Couchbase

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; hiểu metadata để thiết kế TTL, optimistic locking, tính nhất quán truy vấn, transaction và luồng reactive.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Giải thích **CAS (Compare-And-Swap)**, **expiry/TTL** và **mutation token** là ba loại thông tin phục vụ những bài toán khác nhau.
2. Dùng CAS để tránh lỗi *lost update* khi nhiều request đọc rồi cùng sửa một document.
3. Đặt, gia hạn, giữ nguyên hoặc bỏ thời gian hết hạn theo đúng vòng đời dữ liệu; tránh nhầm TTL với trường `expiresAt` trong JSON.
4. Hiểu mutation token gắn với vị trí thay đổi trong luồng cập nhật phân vùng và dùng **MutationState** cho truy vấn SQL++ cần nhìn thấy thay đổi trước đó.
5. So sánh các chế độ scan consistency `not_bounded`, `request_plus` và `at_plus`/`consistentWith`.
6. Liên hệ các cơ chế trên với `@Id`, `@Version`, repository, `CouchbaseTemplate` và API reactive trong Spring Data Couchbase.
7. Thiết kế retry, idempotency, giám sát và xử lý lỗi dựa trên ranh giới thực tế của từng cơ chế.

## 2. Ba cơ chế phục vụ ba câu hỏi khác nhau

Một document Couchbase có **document ID**, nội dung (ví dụ JSON) và metadata do hệ thống quản lý. CAS, expiry và mutation token liên quan đến document/mutation nhưng không cùng chức năng.

| Cơ chế | Trả lời câu hỏi | Phạm vi chính | Dùng khi |
|---|---|---|---|
| **CAS** | “Document có còn đúng phiên bản tôi đã đọc không?” | Kiểm tra điều kiện cập nhật một document | Optimistic concurrency, phát hiện ghi đè |
| **Expiry / TTL** | “Document còn được xem là tồn tại cho đến lúc nào?” | Vòng đời một document, chịu ảnh hưởng cấu hình bucket/collection | Phiên đăng nhập, cache, dữ liệu tạm |
| **Mutation token** | “Mutation này nằm ở vị trí nào trong luồng thay đổi của phân vùng?” | Kết quả mutation, thông tin tiến độ vBucket | Ràng buộc độ mới khi đọc qua GSI/SQL++ |

Vài khái niệm dễ bị nhầm:

- **Document ID** là khóa logic để đọc/ghi KV, không phải CAS.
- **`@Version`** của Spring Data Couchbase thường ánh xạ đến CAS, không phải `schemaVersion` trong JSON.
- **`createdAt`/`updatedAt`** do ứng dụng ghi là dữ liệu nghiệp vụ, không phải expiry metadata.
- **Mutation token** không xác nhận giao dịch đa document đã commit và không phải idempotency key.
- **Durability level** kiểm soát mức xác nhận/persistence/replication của ghi, là bài toán khác với CAS và scan consistency.

### Ví dụ một document

~~~text
Keyspace: commerce.sales.sessions
Document ID: session::token-123

JSON body:
{
  "userId": "customer::87",
  "device": "mobile",
  "createdAt": "2026-11-25T02:00:00Z"
}

Metadata minh họa:
  CAS       = token phiên bản do server cấp
  Expiry    = thời điểm hết hạn nếu đã đặt
  Mutation token = thông tin vBucket/sequence trả về từ một mutation được hỗ trợ
~~~

Không nên tự chép CAS hoặc mutation token vào JSON và coi đó là giá trị luôn được Couchbase đồng bộ. Body và metadata có API, cách lưu và quy tắc thay đổi riêng.

## 3. CAS: kiểm soát cập nhật cạnh tranh

### 3.1. Vấn đề lost update

Giả sử hai request đồng thời xử lý một đơn hàng:

~~~text
T0: Trạng thái order::1001 = NEW, CAS = V1
T1: Request A đọc status=NEW, CAS=V1
T2: Request B đọc status=NEW, CAS=V1
T3: A đổi status=PAID, ghi thành công → CAS=V2
T4: B đổi status=CANCELLED dựa trên bản V1
~~~

Nếu B ghi đè mà không xác minh phiên bản, thay đổi của A có thể bị mất. Với **optimistic locking**, B gửi điều kiện CAS=V1 kèm yêu cầu `replace`; khi server thấy CAS hiện tại không còn V1, thao tác bị từ chối.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Couchbase Data Service
    A->>DB: GET order::1001
    DB-->>A: NEW, CAS V1
    B->>DB: GET order::1001
    DB-->>B: NEW, CAS V1
    A->>DB: REPLACE PAID if CAS=V1
    DB-->>A: Thành công, CAS V2
    B->>DB: REPLACE CANCELLED if CAS=V1
    DB-->>B: CAS mismatch / conflict
~~~

Điểm mấu chốt: CAS là **token opaque**, không phải số thứ tự nghiệp vụ. Không tự `cas + 1`, không suy ra thời điểm cập nhật từ CAS và không dùng CAS để so sánh thứ tự toàn cục giữa các document.

### 3.2. CAS thay đổi khi nào?

Mỗi lần document bị mutation thành công, Couchbase có thể cấp CAS mới; các thao tác đọc thông thường không sinh ra một bản thay đổi mới. CAS dùng để xác nhận *đúng phiên bản đã đọc* trên **một document trong keyspace tương ứng**.

Không giả định hai document cùng CAS là “cùng phiên bản” hoặc CAS trên document A có thể bảo vệ document B. Trong một số trường hợp như thao tác metadata/expiry, cách CAS thay đổi cần xem hành vi API/server cụ thể; nguyên tắc an toàn là **đọc CAS từ kết quả API gần nhất và xử lý conflict**.

### 3.3. Java SDK: cập nhật có điều kiện

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.MutationResult;

// orders trỏ tới collection commerce.sales.orders.
String orderId = "order::1001";
GetResult current = orders.get(orderId);

JsonObject changed = current.contentAsObject()
        .put("status", "PAID");

MutationResult result = orders.replace(
        orderId,
        changed,
        replaceOptions().cas(current.cas())
);

System.out.println("CAS mới: " + result.cas());
~~~

Trong mã thực tế, bắt đúng loại exception CAS mismatch mà SDK đang dùng và chuyển thành hành vi nghiệp vụ (ví dụ HTTP 409, đọc lại và xác minh trạng thái). **Không retry vô hạn với body cũ** hoặc âm thầm bỏ điều kiện CAS chỉ để ghi cho thành công.

### 3.4. CAS khác `insert` và `upsert`

| Thao tác | Phù hợp khi | Rủi ro cần kiểm soát |
|---|---|---|
| `insert(id, body)` | Chỉ tạo mới; phát hiện ID trùng | Duplicate từ retry hoặc client tạo lại đơn |
| `upsert(id, body)` | Chấp nhận tạo mới hoặc thay toàn bộ body | Có thể ghi đè dữ liệu mới hơn |
| `replace(id, body)` | Cập nhật document đang tồn tại | Không phát hiện lost update nếu thiếu CAS |
| `replace(id, body, cas=...)` | Cập nhật dựa trên bản đã đọc | Phải xử lý CAS mismatch theo nghiệp vụ |
| Sub-document mutation có điều kiện | Chỉ thay một đường dẫn JSON | Có thể cần CAS khi logic đọc–sửa phụ thuộc trạng thái trước đó |

Thao tác sub-document có thể giảm lượng dữ liệu truyền và giới hạn phần nội dung bị tác động, nhưng **không tự thay CAS** cho những business rule cần kiểm tra nhiều trường trên bản đã đọc.

### 3.5. CAS không thay thế transaction

CAS có tác dụng trên **một document**. Nếu nghiệp vụ cần đồng thời tạo đơn và cập nhật tồn kho ở hai document, CAS riêng cho mỗi bên không tạo ra tính nguyên tử toàn bộ. Khi cần atomicity nhiều document, hãy đánh giá **Couchbase Transactions** theo version/API cùng idempotency của quy trình.

## 4. Spring Data Couchbase: `@Version` và optimistic locking

Spring Data Couchbase ánh xạ document ID bằng `@Id`, và hỗ trợ optimistic locking qua `@Version` theo hành vi của phiên bản framework.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String status;
    private String tenantId;
    private Long total;

    // Constructor/getter/setter được lược bớt.
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

Ví dụ luồng logic:

~~~java
OrderDocument order = orderRepository.findById("order::1001")
        .orElseThrow();

// Kiểm tra chuyển trạng thái hợp lệ trước khi lưu.
if (!"NEW".equals(order.getStatus())) {
    throw new IllegalStateException("Đơn không còn ở trạng thái NEW");
}

order.setStatus("PAID");
orderRepository.save(order); // Có thể báo optimistic-locking conflict.
~~~

Đoạn minh họa giả định entity có getter/setter tương ứng. Khi `@Version` được mapping đúng, framework có thể dùng CAS để ngăn cập nhật khi document đã thay đổi từ lần đọc. **Tên exception, quy tắc entity mới và hành vi save** phụ thuộc phiên bản Spring Data Couchbase; cần kiểm tra API đang sử dụng.

Đừng nhầm:

- `@Version Long version`: dùng cho optimistic locking/CAS.
- `schemaVersion: 2` trong JSON: dùng cho migration định dạng document.
- `updatedAt` trong JSON: dấu thời gian do ứng dụng quản lý.
- **Mutation token**: vị trí thay đổi dùng cho consistency truy vấn, không phải một field `@Version`.

Trong service xử lý đơn, CAS nên đi kèm kiểm tra business rule và chiến lược trả xung đột, không chỉ thêm annotation rồi bỏ qua lỗi.

## 5. TTL và expiry: vòng đời document

**TTL (Time To Live)** là khoảng thời gian sau đó document được xem là hết hạn; **expiry** là thông tin hệ thống dùng để xác định thời điểm hết hạn. Couchbase có thể đặt expiry trên từng document và cung cấp chính sách liên quan ở cấp bucket/collection theo phiên bản, loại bucket và cấu hình.

Ví dụ:

| Loại document | Vòng đời mong muốn | Gợi ý |
|---|---|---|
| `sessions` | Phiên đăng nhập có thời hạn | TTL ngắn, có cơ chế refresh nếu cần |
| `verification_codes` | Mã xác minh hết hiệu lực sau vài phút | TTL ngắn + kiểm tra “đã sử dụng” |
| `shopping_carts` | Giỏ tạm có thể hết hạn sau thời gian không hoạt động | TTL được gia hạn theo chính sách |
| `orders` | Đơn hàng cần lưu theo retention nghiệp vụ | Không áp TTL ngắn tùy tiện |
| `audit_events` | Giữ đủ thời hạn kiểm toán/tuân thủ | Có chính sách retention và backup độc lập |

**TTL không phải bộ lập lịch chính xác theo từng mili giây.** Khi hết hạn, document không còn được phục vụ như document tồn tại; công việc dọn vật lý, cập nhật index và quan sát thống kê có thể diễn ra sau đó. Đừng dùng expiry đơn thuần để kích hoạt một hành động cần chắc chắn xảy ra đúng giờ.

### 5.1. Expiry là metadata, không phải field JSON

Document:

~~~json
{
  "userId": "customer::87",
  "createdAt": "2026-11-25T02:00:00Z",
  "expiresAt": "2026-11-25T02:30:00Z"
}
~~~

Nếu chỉ lưu `expiresAt` vào JSON mà không cấu hình expiry metadata, Couchbase **không tự hiểu** rằng document phải hết hạn theo giá trị đó. Ngược lại, document có TTL thực tế có thể không có trường `expiresAt` trong JSON.

Trường JSON `expiresAt` có thể hữu ích để hiển thị countdown, tìm kiếm hoặc audit, nhưng ứng dụng phải đồng bộ nó với chính sách expiry nếu cần.

### 5.2. Java SDK: ghi document có TTL

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;
import com.couchbase.client.java.json.JsonObject;
import java.time.Duration;

// sessions là Collection tương ứng với commerce.identity.sessions.
JsonObject session = JsonObject.create()
        .put("userId", "customer::87")
        .put("device", "mobile");

sessions.upsert(
        "session::abc123",
        session,
        upsertOptions().expiry(Duration.ofMinutes(30))
);
~~~

API `expiry(Duration)` mô tả thời hạn theo tương đối. SDK/server chuyển đổi và áp dụng theo semantics, giới hạn và chính sách hiệu lực của phiên bản. Nếu yêu cầu đặt **một thời điểm tuyệt đối**, hãy dùng lựa chọn tương ứng được SDK hỗ trợ (thường là `Instant` hoặc biểu diễn expiry khác), thay vì tự giả định phép tính timestamp nào cũng hợp lệ.

### 5.3. Gia hạn phiên và giữ nguyên expiry

Trong ứng dụng phiên đăng nhập, cần phân biệt hai chính sách:

- **Absolute timeout:** phiên không được dùng quá một thời điểm cố định; update bình thường không được tự gia hạn.
- **Sliding timeout:** mỗi lần người dùng hoạt động hợp lệ có thể gia hạn TTL thêm một khoảng.

Để gia hạn, SDK có API như `touch` hoặc `getAndTouch`; để giữ expiry khi cập nhật nội dung, một số API/version hỗ trợ `preserveExpiry`.

Ví dụ cập nhật JSON và yêu cầu giữ expiry cũ:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

var current = sessions.get("session::abc123");
var next = current.contentAsObject()
        .put("device", "tablet");

sessions.replace(
        "session::abc123",
        next,
        replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true)
);
~~~

Đoạn này minh họa một lựa chọn Java SDK hiện đại; khả năng hỗ trợ `preserveExpiry` phụ thuộc SDK/server. Nó quan trọng vì nhiều thao tác mutation có thể **thay đổi hoặc làm mất expiry cũ** nếu không yêu cầu giữ lại hoặc đặt lại TTL.

Với chính sách sliding timeout, thao tác `touch`/`getAndTouch` phải được giới hạn tần suất để tránh tăng lượng write vô ích. Đừng tự động touch trong mọi request nếu hệ thống có lưu lượng lớn và yêu cầu nhất quán đặc biệt.

### 5.4. Mức cấu hình và thứ tự ưu tiên

Expiry có thể chịu tác động từ:

1. Giá trị expiry do thao tác ghi gửi lên.
2. Chính sách expiration/maxTTL của bucket.
3. Chính sách expiration/maxTTL của collection nếu phiên bản hỗ trợ.
4. Tùy chọn giữ expiry khi thay đổi document.
5. Các điều kiện riêng của loại bucket và tính năng.

**Không có một quy tắc ưu tiên đơn giản áp dụng cho mọi phiên bản.** Cần đọc cấu hình của bucket/collection trong môi trường triển khai, đối chiếu tài liệu SDK và test ba tình huống: tạo mới, cập nhật và gia hạn.

Đặc biệt, các giá trị như expiry bằng 0, maxTTL, “không đặt expiry” hoặc “giữ expiry cũ” có thể có semantics khác nhau tùy API. Đừng dùng một phép gán mặc định rồi cho rằng document chắc chắn tồn tại vô hạn.

## 6. Expiry tương tác với KV, CAS và SQL++

### 6.1. Khi document hết hạn

Hết TTL làm document bị coi là không còn hiện hữu đối với các thao tác thông thường. Một lần `get(id)` có thể trả not-found, dù việc dọn vật lý chưa hoàn tất.

Lưu ý:

- Không dùng **TTL** làm cơ chế duy nhất để gửi email, phát sự kiện hay hoàn tiền đúng thời điểm. Cần scheduler/queue/event workflow có xác nhận.
- Một document hết hạn có thể ảnh hưởng tới GSI và kết quả SQL++ theo tiến độ cập nhật/dọn; không dựa vào query index như đồng hồ expiry tuyệt đối.
- Retention, pháp lý và compliance thường yêu cầu cả backup policy, audit, data deletion policy chứ không chỉ TTL của bucket.

### 6.2. TTL và optimistic locking

Giả sử hai request cùng đọc session. Một request gia hạn TTL, request khác cập nhật body. Nếu nghiệp vụ cần giữ nguyên một snapshot, phải xem CAS và quy tắc mutation/expiry của phiên bản SDK để xử lý cạnh tranh.

Những hành vi không nên giả định:

- `replace` luôn tự giữ expiry ban đầu.
- `touch` không có bất kỳ ảnh hưởng concurrency nào.
- Ghi CAS thành công chứng minh session sẽ còn sống mãi.
- Document hết hạn được server phục hồi tự động nếu tiếp tục sử dụng ID cũ.

**Thiết kế một invariant có thể kiểm thử**, ví dụ: “Mọi session hoạt động được gia hạn tối đa 30 phút tính từ lần hoạt động hợp lệ, nhưng không vượt absolute expiry”. Invariant này có thể cần lưu trường JSON bổ sung và transaction/logic API rõ ràng, thay vì chỉ trông vào TTL.

### 6.3. TTL trong Spring Data

Spring Data Couchbase có các khả năng mapping expiry ở entity/cấu hình tùy phiên bản (chẳng hạn thuộc tính expiry của document và API để tùy chỉnh expiry). Khi đưa TTL vào repository hoặc `CouchbaseTemplate`, cần kiểm tra:

- TTL được áp dụng khi **insert** hay cả **update**?
- Save có làm reset hạn không?
- Có tùy chọn giữ expiry không?
- Những collection khác nhau (session, order) có chính sách nhất quán không?
- Có test với đồng hồ và thời gian hết hạn thực tế trên Server không?

Không lấy một ví dụ annotation từ phiên bản khác rồi giả định chính sách bảo toàn expiry giống Java SDK.

## 7. Mutation token là gì?

Khi Couchbase ghi một document thành công qua KV, các thay đổi đi vào luồng mutation của **vBucket**. Những phiên bản/giao thức hỗ trợ có thể trả về **mutation token** trong kết quả thao tác ghi.

Một mutation token mô tả vị trí thay đổi trong luồng của phân vùng, ở mức khái niệm gồm:

- **Partition/vBucket ID:** phân vùng xảy ra mutation.
- **Partition UUID/epoch:** nhận diện lịch sử/generation của phân vùng.
- **Sequence number:** vị trí tiến triển của mutation trong luồng tương ứng.

**Token không phải CAS.** Token liên quan đến thứ tự cập nhật trong một luồng phân vùng; CAS dùng kiểm tra phiên bản một document. Token cũng không phải timestamp, không phải khóa tài liệu, không phải toàn cục sequence đơn giản cho mọi document trong cluster.

~~~mermaid
flowchart LR
    W["KV mutation"]
    D["Data Service / active vBucket"]
    R["MutationResult"]
    C["CAS: optimistic locking"]
    T["Mutation token: vị trí trong mutation stream"]
    MS["MutationState"]
    Q["SQL++ Query với consistentWith"]
    W --> D
    D --> R
    R --> C
    R --> T
    T --> MS
    MS --> Q
~~~

### 7.1. Tại sao mutation token có ích?

Sau khi mutation KV thành công, document mới có thể đã được Data Service chấp nhận nhưng **GSI ở Index Service** chưa cập nhật kịp. Nếu ứng dụng lập tức gửi SQL++ lọc theo `status`, kết quả mặc định có thể không thấy document mới.

Mutation token giúp Query Service xác định ngưỡng thay đổi mà chỉ mục phải bắt kịp trước khi trả kết quả, trong những API hỗ trợ **`at_plus` / `consistentWith`**. Đây là một hình thức đảm bảo **read-your-own-writes cho truy vấn theo thay đổi đã biết**, có phạm vi khác với transaction.

### 7.2. Token không nói điều gì?

Token không tự bảo đảm:

- Mọi document khác trong cluster đã có cùng độ mới.
- Một business workflow đa document là nguyên tử.
- Thao tác gửi sau đã hoàn tất nếu chỉ lưu token của thao tác trước.
- Ghi đã đạt durability mong muốn: durability cần cấu hình riêng.
- Retry một mutation không idempotent sẽ an toàn.
- Ứng dụng có thể dùng sequence number làm ID nghiệp vụ hoặc khóa sắp xếp toàn cục.

Một token có ý nghĩa theo phân vùng và lịch sử của nó. Hãy chuyển token/`MutationState` qua API SDK thay vì tự ghép chuỗi hoặc tự so sánh các trường kỹ thuật.

## 8. SQL++ và độ trễ chỉ mục: ba lựa chọn consistency

Truy vấn SQL++ có thể dùng GSI, được Index Service cập nhật từ các mutation ở Data Service. Khi ghi vừa thành công, chỉ mục có thể chậm hơn một nhịp.

Giả sử:

~~~text
T0: insert order::1001 status=PAID qua KV → thành công
T1: ứng dụng gửi SQL++ WHERE status="PAID"
T2: index vẫn đang xử lý mutation T0
T3: index bắt kịp mutation T0
~~~

Ở thời điểm T1, mức scan consistency quyết định truy vấn có cần chờ tới T3 hay không.

| Chế độ | Hành vi khái quát | Khi phù hợp | Đổi lại |
|---|---|---|---|
| **`not_bounded`** | Không yêu cầu index chờ bắt kịp một mốc mutation cụ thể | Trang danh sách chấp nhận độ trễ cập nhật nhỏ | Có thể chưa thấy ghi vừa hoàn tất |
| **`request_plus`** | Chờ chỉ mục bắt kịp các mutation có trước thời điểm request query theo semantics server | Cần kết quả cập nhật tới mốc bắt đầu truy vấn | Có thể tăng latency/timeout khi index lag |
| **`at_plus` / `consistentWith`** | Chờ index đạt ít nhất các mutation token được cung cấp | Read-your-own-writes sau mutation có kết quả token | Cần thu và truyền MutationState hợp lệ |

**Mức mạnh hơn không tự đồng nghĩa một snapshot giao dịch toàn cluster.** Scan consistency kiểm soát độ mới của index phục vụ SQL++ và không thay thế transaction isolation hay durability.

### 8.1. Dùng `request_plus` khi không có token

Java SDK minh họa:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

cluster.query(
        "SELECT META(o).id AS id, o.status " +
        "FROM `commerce`.`sales`.`orders` AS o " +
        "WHERE o.tenantId = '42' AND o.status = 'PAID'",
        queryOptions()
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

Đây là lựa chọn dễ hiểu nhưng có thể chờ những cập nhật **không do request hiện tại tạo ra**. Trong hệ thống ghi nhiều, latency có thể tăng. Ưu tiên dùng đúng ở các đường truy vấn cần nhìn thấy cập nhật mới hơn, không bật toàn hệ thống vì thói quen.

### 8.2. Dùng mutation token/MutationState khi đã có kết quả ghi

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryResult;

String id = "order::1001";
MutationResult written = orders.upsert(
        id,
        JsonObject.create()
                .put("tenantId", "42")
                .put("status", "PAID")
                .put("total", 1490000)
);

QueryResult result = cluster.query(
        "SELECT META(o).id AS id, o.status " +
        "FROM `commerce`.`sales`.`orders` AS o " +
        "WHERE o.tenantId = $tenantId AND o.status = $status",
        queryOptions()
                .parameters(JsonObject.create()
                        .put("tenantId", "42")
                        .put("status", "PAID"))
                .consistentWith(MutationState.from(written))
);

System.out.println(result.rowsAsObject());
~~~

Mã minh họa API Java SDK 3.x; dùng đúng package/method theo dependency trong dự án. `MutationState.from(written)` sử dụng dữ liệu mutation do SDK cung cấp để truy vấn chờ index tương ứng. Khi môi trường không có token hợp lệ hoặc API không hỗ trợ, cần dùng chiến lược khác thay vì tự chế token. Đừng đồng thời áp hai cơ chế consistency mâu thuẫn vào cùng một cấu hình query.

### 8.3. Truy vấn theo ID có thể tránh chờ index

Nếu đã biết document ID, đọc trực tiếp KV thường phù hợp hơn:

~~~java
var doc = orders.get("order::1001");
~~~

Lệnh `get` không cần GSI, nên không chịu độ trễ index theo cách SQL++ lọc `status`. Tuy nhiên vẫn phải tính đến replica/failover, tình trạng durability và lỗi mạng. Khi dữ liệu cần được tìm theo nhiều field, GSI và scan consistency là vấn đề không thể bỏ qua.

## 9. Kết hợp kết quả của nhiều mutation

Trong một workflow, ứng dụng có thể ghi nhiều document trước khi chạy SQL++. Nếu cần truy vấn nhìn thấy **tất cả thay đổi của chính workflow**, có thể gom mutation state từ nhiều `MutationResult` theo API phiên bản SDK, rồi truyền vào `consistentWith`.

Ý tưởng:

~~~text
write A → mutation token A (vBucket X)
write B → mutation token B (vBucket Y)
MutationState = {token A, token B}
SQL++ consistentWith(MutationState)
→ chờ index đạt ít nhất các mốc liên quan
~~~

Không mặc định mutation A và B được commit nguyên tử chỉ vì query chờ cả hai token. Nếu A thành công còn B thất bại, MutationState không tự rollback A.

Khi code chỉ có `repository.save(entity)` trả về entity chứ không có `MutationResult` trực tiếp, ứng dụng **không nên bịa MutationState**. Các lựa chọn gồm:

- Dùng API SDK/template thích hợp khi thực sự cần nắm mutation result.
- Dùng `request_plus` cho truy vấn cần bảo đảm thấy những mutation trước đó theo mốc query.
- Đọc KV theo ID nếu chỉ cần xác minh chính document đã ghi.
- Sử dụng transaction cho nghiệp vụ cần atomicity của nhiều document, theo điều kiện SDK/server.

## 10. Mutation token và TTL/CAS có liên quan nhau thế nào?

Ba thông tin có thể cùng xuất hiện trong một workflow:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Data Service
    participant I as Index Service
    participant Q as Query Service
    A->>D: GET session::abc
    D-->>A: JSON + CAS V1
    A->>D: REPLACE nếu CAS=V1, giữ expiry
    D-->>A: MutationResult, CAS V2, mutation token T
    D-->>I: Mutation stream cập nhật
    A->>Q: SQL++ consistentWith(T)
    Q->>I: Chờ index đạt mutation T
    I-->>Q: Index sẵn sàng tại mốc yêu cầu
    Q-->>A: Kết quả theo query
~~~

Trong ví dụ:

- **CAS V1:** chứng minh body chưa đổi so với lần đọc trước; nếu mismatch, mutation không thành công nên không có một token thành công để chuyển tiếp.
- **Expiry:** được giữ hoặc đặt lại theo options của mutation; CAS không tự giữ TTL.
- **Mutation token T:** dùng để chờ GSI cập nhật khi query cần đọc sau ghi.
- **Transaction:** không được tạo chỉ nhờ phối hợp ba thuộc tính này.

Đây là các cơ chế bổ sung cho nhau. Mỗi cơ chế chỉ giải quyết một phần của bài toán đúng dữ liệu, đúng thời hạn và đúng kỳ vọng truy vấn.

## 11. Tình huống thực tế: session trượt hạn và xung đột cập nhật

Giả sử session có TTL 30 phút tính từ hoạt động gần nhất (*sliding expiration*). Hai request đến cùng lúc: A cập nhật thiết bị đăng nhập; B gia hạn hạn.

Các câu hỏi cần thiết kế:

1. Request A có thể vô tình reset TTL của session không?
2. Request B có cần CAS nếu gia hạn phụ thuộc vào trạng thái “session vẫn hợp lệ và chưa bị thu hồi”?
3. Nếu A đọc CAS cũ và B đã sửa metadata/body, A nên làm gì khi gặp conflict?
4. Nếu session vừa hết hạn giữa lần đọc và lần ghi, API trả “không tìm thấy” có hợp lý không?
5. Một trường JSON `lastSeenAt` có đủ thay thế expiry metadata không?

Một hướng giải quyết:

- Đặt rõ **absolute expiration** và **sliding expiration** của nghiệp vụ.
- Nếu cập nhật body không được làm dài thêm TTL, sử dụng preserve-expiry hoặc truyền expiry được tính có kiểm soát.
- Nếu gia hạn cần kiểm tra trạng thái chưa thu hồi, phối hợp điều kiện business và CAS/transaction theo thiết kế.
- Nếu gặp CAS conflict, đọc lại và xác minh business rule; không retry vô hạn.
- Dùng log có document ID đã ẩn/giảm nhạy cảm, thời gian thao tác và loại lỗi thay vì ghi nguyên token đăng nhập.

Không thể kết luận chỉ từ TTL rằng session chắc chắn bị thu hồi đồng bộ ở mọi cache hoặc replica read. Authentication cần kiểm tra thời hạn và trạng thái phù hợp với kiến trúc ứng dụng.

## 12. Tình huống thực tế: lưu đơn và truy vấn danh sách ngay sau đó

Một người dùng thanh toán đơn. API lưu `status=PAID` qua KV, sau đó ngay lập tức load trang “Đơn hàng đã thanh toán”.

### Cách dễ gặp lỗi

~~~text
A: repository.save(order) → hoàn tất qua KV
B: repository.findByTenantIdAndStatus("42", "PAID")
C: SQL++ dùng GSI chưa bắt kịp A → chưa có order vừa thanh toán
~~~

Đây có thể là **index lag**, không nhất thiết là lỗi save.

### Ba cách thiết kế

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| Trả lại order từ kết quả save hoặc đọc KV theo ID | Nhanh, tránh GSI trên đường xác nhận | Chỉ phù hợp khi đã biết ID/document |
| Query với `request_plus` | Không cần mutation token ở caller | Có thể chờ nhiều thay đổi ngoài workflow |
| Query với `consistentWith(MutationState)` | Chờ các mutation cụ thể từ workflow | Caller cần mutation result/token và API hỗ trợ |

Mỗi luồng có SLA khác nhau. Với trang báo cáo cho phép chậm vài giây, `not_bounded` có thể đủ. Với xác nhận ngay sau thanh toán, nên đáp ứng trực tiếp theo ID hoặc chọn consistency có chủ đích.

**Không thay vấn đề bằng việc bật CAS.** CAS chỉ chống lost update; nó không ép GSI cập nhật ngay.

## 13. TTL, CAS và retry trong hệ thống reactive

`ReactiveCouchbaseRepository` và reactive template có thể trả `Mono`/`Flux`, nhưng semantics server không thay đổi:

- Document vẫn có ID, CAS và expiry theo quy tắc Couchbase.
- KV mutation có thể thành công tại server trước khi reactive subscriber nhận response.
- Retry một publisher có side effect có thể **thực thi lại mutation**.
- Truy vấn SQL++ reactive vẫn có thể gặp index lag.
- Backpressure/concurrency giúp quản lý tải; nó không thay thế CAS, idempotency, durability hoặc transaction.

Ví dụ repository reactive:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
Mono<OrderDocument> loaded =
        reactiveOrderRepository.findById("order::1001");
~~~

Khi thiết kế `retryWhen` cho luồng ghi:

1. Phân biệt **conflict CAS** (thay đổi dữ liệu thực) với **timeout network**.
2. Với CAS conflict, đọc lại và kiểm tra rule; retry có giới hạn nếu cho phép.
3. Với timeout ambiguous, xác minh document bằng ID/idempotency key trước khi lặp mutation.
4. Với SQL++ yêu cầu read-your-own-writes, mang thông tin consistency qua pipeline nếu API hỗ trợ; không “chờ đại 100 ms” để thay thế logic đúng.
5. Đặt deadline và giới hạn concurrency để tránh tải dồn lên Data/Index Service khi cluster chậm.

Reactive **không tạo thêm bảo đảm nhất quán** chỉ vì sử dụng asynchronous pipeline.

## 14. Phân biệt CAS, mutation token, durability và transaction

| Yêu cầu | Cơ chế cần cân nhắc | Vì sao |
|---|---|---|
| Không ghi đè thay đổi đồng thời trên một đơn | CAS, `@Version` | Kiểm tra phiên bản document |
| Session hết hạn sau 30 phút | TTL/expiry | Quản lý vòng đời document |
| SQL++ thấy order vừa ghi | MutationState/`consistentWith` hoặc `request_plus` | Chờ GSI đạt mốc độ mới |
| Hạn chế mất mutation khi Data node lỗi | Synchronous durability + replica phù hợp | Ràng buộc xác nhận ghi |
| Hai document cùng thay đổi nguyên tử | Couchbase Transactions khi đáp ứng điều kiện | Atomicity nhiều document |
| Retry tạo đơn không gây trùng | ID ổn định/idempotency key, `insert` + xử lý duplicate | Bảo vệ business operation |
| Khôi phục sau xóa nhầm hàng loạt | Backup/restore | Bản sao lưu độc lập |
| Chống mất dữ liệu do sai schema | Schema version, validation và migration | Hợp đồng dữ liệu |

Nhiều yêu cầu cần **kết hợp** cơ chế. Ví dụ thanh toán có thể dùng ID idempotent, CAS khi chuyển trạng thái, durability theo RPO và transaction cho nhiều document; mutation token chỉ phục vụ một bước đọc qua GSI cần độ mới thích hợp.

## 15. Sự cố thường gặp và cách chẩn đoán

| Triệu chứng | Cần kiểm tra | Cách xử lý |
|---|---|---|
| `CasMismatchException`/optimistic locking conflict | Có request khác sửa document? CAS có từ lần đọc gần nhất? | Đọc lại, kiểm tra rule, báo conflict/retry có điều kiện |
| `get(id)` trả not-found sau một khoảng thời gian | Expiry, document bị xóa hoặc sai keyspace | Kiểm tra TTL, bucket/collection, ID và audit |
| Session bị kéo dài ngoài ý muốn | Upsert/replace đã reset expiry? Có touch mỗi request? | Xác định chính sách absolute/sliding, test preserve-expiry |
| SQL++ không thấy document mới | GSI lag, scan consistency và chỉ mục | Dùng KV, `request_plus` hoặc `consistentWith` |
| Query với `request_plus` đột ngột chậm | Chỉ mục backlog, write rate, Index Service | Đo index lag và query latency; hạn chế consistency nặng khi không cần |
| Không lấy được mutation token từ API | Đường thao tác không trả result/token; API/version hạn chế | Chọn SDK API phù hợp hoặc request_plus, không tự tạo token |
| Retry reactive gây ghi đôi | Publisher side effect bị resubscribe, thiếu idempotency | Thiết kế ID ổn định, xác minh kết quả ambiguous |
| CAS thay đổi nhưng `updatedAt` không đổi | Field audit do ứng dụng quên ghi | Cập nhật audit logic/transaction; đừng suy CAS là timestamp |
| Kết quả replica khác active | Replica lag | Chọn đường đọc theo yêu cầu nhất quán |
| Có CAS nhưng cập nhật nhiều document không nguyên tử | CAS chỉ bảo vệ từng document | Dùng transaction hoặc workflow bù trừ phù hợp |

**Thứ tự điều tra:** xác nhận keyspace/ID → xác định thao tác KV hay SQL++ → kiểm tra CAS conflict hoặc expiry → xác minh index lag/scan consistency → đánh giá durability, retry, network và trạng thái cluster.

## 16. Giám sát và thử nghiệm

### 16.1. Metrics nên có

- **CAS conflict rate:** số lần optimistic locking thất bại theo endpoint/collection.
- **KV mutation latency/error:** insert/replace/remove, timeout và ambiguous outcomes.
- **Expiry-related not-found:** phân biệt not-found do TTL với sai ID/quyền khi có log/audit phù hợp.
- **Query p95/p99 latency:** đặc biệt khi bật `request_plus` hoặc `consistentWith`.
- **Index lag/backlog:** giải thích truy vấn chờ cập nhật GSI.
- **Reactive retry count/concurrency:** phát hiện retry storm hoặc side effect bị gọi lại.

Không log nguyên token phiên đăng nhập, credential, payload nhạy cảm hoặc metadata bí mật để debug. Mutation token phục vụ kỹ thuật nên cũng chỉ ghi khi thực sự cần chẩn đoán và áp dụng chính sách log phù hợp.

### 16.2. Kiểm thử tối thiểu có giá trị

| Bài test | Điều kiện | Kết quả kỳ vọng |
|---|---|---|
| **CAS conflict** | Hai request đọc cùng CAS rồi ghi hai thay đổi | Một ghi có điều kiện bị từ chối khi CAS đã đổi |
| **Insert duplicate** | Tạo hai lần cùng ID | Lần hai không âm thầm tạo document khác |
| **TTL expiry** | Ghi session TTL ngắn, chờ qua hạn trong môi trường test | KV không còn xem document là tồn tại |
| **Preserve expiry** | Ghi document có TTL, update body | Thời hạn giữ nguyên nếu đúng API/tùy chọn |
| **Touch/sliding TTL** | Gia hạn session trước khi hết hạn | Có thời điểm hết hạn mới theo chính sách |
| **SQL++ index lag** | Ghi KV rồi query theo field | Đánh giá mặc định và consistency mạnh hơn |
| **MutationState** | Ghi KV lấy MutationResult, query consistentWith | Query đáp ứng mốc mutation được cung cấp |
| **Ambiguous retry** | Giả lập mất response sau ghi | Không tạo trùng nghiệp vụ |

Các test liên quan thời gian nên có khoảng đệm hợp lý, tách biệt TTL logic và thời điểm dọn vật lý. Không kỳ vọng thời gian thực thi từng bước chính xác tới mili giây trên CI chia sẻ.

## 17. Bài tập thực hành

### Bài tập A — CAS và lost update

Hai service cùng đọc `order::1001` trạng thái `NEW`, CAS V1. Service A đổi thành `PAID` và ghi thành công; service B cố ghi `CANCELLED` với CAS V1.

1. B nhận kết quả gì?
2. Nếu B tự đọc CAS mới rồi cố ghi `CANCELLED`, vì sao vẫn phải kiểm tra business rule?
3. `@Version` giúp ngăn lỗi nào, và không ngăn lỗi nào?

**Gợi ý:** CAS phát hiện bản đọc đã cũ, nhưng không tự quyết định nghiệp vụ có cho phép hủy đơn đã thanh toán hay không.

### Bài tập B — một trường JSON có phải TTL không?

Ghi JSON:

~~~json
{"expiresAt":"2026-12-01T00:00:00Z","status":"ACTIVE"}
~~~

Sau đó không đặt expiry metadata. Couchbase có tự xóa document khi đến ngày đó không? Hãy viết Java SDK `upsert` với `expiry(Duration.ofMinutes(30))` để tạo TTL thực sự, rồi giải thích khác nhau giữa timestamp JSON và metadata expiry.

### Bài tập C — preserve-expiry

Session có TTL 30 phút, sau 10 phút cập nhật field `device`. Nghiệp vụ yêu cầu session **vẫn hết hạn theo mốc ban đầu**. Nêu API/tùy chọn cần xem xét, test cách đo thời hạn còn lại và rủi ro khi dùng `upsert` mặc định.

### Bài tập D — SQL++ đọc sau ghi

API ghi order qua KV rồi query danh sách đơn `PAID`. Hãy so sánh `not_bounded`, `request_plus` và `consistentWith(MutationState)` theo:
- Độ mới của GSI.
- Có cần mutation token không.
- Khả năng tăng latency.
- Khi nào nên thay SQL++ bằng `get(id)`.

### Bài tập E — phân biệt các token

Một lập trình viên muốn dùng CAS làm timestamp sửa đổi và lấy mutation token làm idempotency key. Chỉ ra hai lỗi thiết kế này và đề xuất metadata/application field phù hợp hơn.

### Bài tập F — Spring Data reactive

Bạn có `Mono<OrderDocument> save(...)` và gọi `retryWhen(...)` cho mọi lỗi. Giải thích vì sao có thể gây side effect không mong muốn sau timeout ambiguous; đề xuất cách phân loại CAS conflict, duplicate và lỗi mạng.

## 18. Checklist triển khai

- [ ] Tách rõ document ID, trường JSON, CAS, expiry metadata và mutation token.
- [ ] Dùng CAS/`@Version` khi cập nhật dựa trên bản đọc cũ; có xử lý conflict theo nghiệp vụ.
- [ ] Không dùng CAS như timestamp, số đếm toàn cục hoặc schema version.
- [ ] Định nghĩa TTL/retention theo collection và nghiệp vụ; kiểm tra cấu hình bucket/collection liên quan.
- [ ] Phân biệt absolute expiry và sliding expiry; biết lúc nào cần preserve-expiry hoặc touch.
- [ ] Không dùng trường JSON `expiresAt` để thay thế TTL trừ khi ứng dụng chủ động xử lý.
- [ ] Kiểm tra TTL khi insert, update, migration và restore.
- [ ] Dùng KV theo document ID khi phù hợp; SQL++ theo field cần chỉ mục và consistency rõ ràng.
- [ ] Chọn `not_bounded`, `request_plus` hoặc `consistentWith` theo SLA, không bật mặc định một cách mù quáng.
- [ ] Chỉ tạo MutationState từ mutation result/token được SDK hỗ trợ; không tự chế token.
- [ ] Phân biệt durability, transaction và idempotency khỏi CAS/scan consistency.
- [ ] Reactive retry phải xét side effect, deadline, phân loại lỗi và kiểm soát concurrency.
- [ ] Theo dõi CAS conflicts, KV timeouts, expiry, query latency và index lag.
- [ ] Đối chiếu SDK/Spring Data/Couchbase Server version trước khi dùng annotation hoặc tùy chọn API cụ thể.

## 19. Tổng kết

**CAS** bảo vệ một document khỏi cập nhật dựa trên phiên bản đã cũ. **TTL/expiry** quản lý vòng đời document. **Mutation token** mô tả vị trí mutation trong luồng phân vùng và giúp truy vấn SQL++ chờ GSI cập nhật tới mốc cụ thể thông qua MutationState khi API hỗ trợ. Ba cơ chế không thay thế cho nhau và cũng không tự tạo durability, transaction hoặc idempotency.

Khi xây dựng tầng truy cập **Spring Data Couchbase**, hãy dùng `@Id`/`@Version` và repository cho document mapping/optimistic locking, lựa chọn `CouchbaseTemplate` hoặc SDK khi cần kiểm soát metadata/query options, và áp dụng các nguyên tắc tương tự cho API reactive. Thiết kế đúng CAS, expiry, mutation token cùng với index, retry và monitoring sẽ giúp hệ thống vừa tránh ghi đè, vừa quản lý vòng đời dữ liệu và đọc đúng mức nhất quán mà nghiệp vụ yêu cầu.
