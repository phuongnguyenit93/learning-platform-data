# Xác nhận ghi trên node chính, sao chép và lưu bền trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase qua document mapping, repository, `CouchbaseTemplate` và SQL++; vận dụng kiến thức bucket/scope/collection, CAS, TTL, giao dịch, chỉ mục và API reactive để chọn đúng mức bảo đảm cho dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích điểm khác nhau giữa **node đang giữ active vBucket chấp nhận mutation**, **bản sao nhận mutation** và **dữ liệu được lưu bền (persist)**.
2. Hiểu vì sao **lời gọi ghi thành công** không nhất thiết chứng minh mutation đã nằm trên đĩa hoặc đủ bản sao, nếu không yêu cầu mức durability tương ứng.
3. Phân biệt các mức **synchronous durability**: `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY`.
4. Phân tích chi phí và điều kiện thành công của ghi khi có nhiều active/replica vBucket, khi node lỗi hoặc cluster rebalance.
5. Đọc mã Java SDK sử dụng `InsertOptions`, `ReplaceOptions` và `DurabilityLevel`; nhận ra giới hạn của abstraction Spring Data repository.
6. Xử lý đúng timeout, lỗi durability và **kết quả ghi không xác định** (*ambiguous outcome*) bằng ID ổn định, CAS và idempotency.
7. Xây dựng ma trận yêu cầu nghiệp vụ, kiểm thử lỗi và chỉ số quan sát cho **RPO, độ trễ ghi và availability**.

## 2. Ba mốc thời gian khác nhau của một thao tác ghi

Giả sử ứng dụng tạo đơn hàng:

~~~text
Collection: commerce.sales.orders
Document ID: tenant::42::order::1001

Body:
{
  "tenantId": "42",
  "status": "NEW",
  "total": 1490000
}
~~~

Khi gọi `collection.insert(id, body)`, Couchbase cần đưa mutation đến Data Service đang giữ **active vBucket** ứng với document ID. Từ active, thay đổi có thể được **sao chép sang replica** và **lưu bền vào thiết bị lưu trữ** tùy loại bucket, trạng thái cluster và mức durability.

Ba sự kiện không giống nhau:

- **Accepted on active:** active xử lý/chấp nhận một mutation theo semantics thao tác.
- **Replicated:** các bản dữ liệu liên quan ở Data node khác đã nhận mutation đến mốc yêu cầu.
- **Persisted:** mutation đạt mốc ghi bền lên storage theo cơ chế storage engine và phiên bản triển khai.

~~~mermaid
flowchart LR
    C["Spring Data / Couchbase Java SDK"]
    A["Active vBucket<br/>Data node A"]
    R["Replica vBucket<br/>Data node B"]
    DA[("Storage node A")]
    DB[("Storage node B")]
    C -->|"Mutation KV"| A
    A -->|"Replication"| R
    A -->|"Persistence"| DA
    R -->|"Persistence"| DB
    A -.->|"Ack về client theo mức durability"| C
~~~

Sơ đồ chỉ minh họa một replica. **Thứ tự thực thi nội bộ không phải một chuỗi cố định** kiểu “xong ghi RAM, xong ghi replica, xong ghi đĩa”. Những hoạt động có thể tiến triển đồng thời; điều cần học là **điều kiện nào phải đạt trước khi client được báo thành công**.

### 2.1. “Node chính” nghĩa là active vBucket, không phải một master cố định

Couchbase phân phối bucket qua nhiều **vBucket**. Mỗi vBucket có một **active** tại một Data node và có thể có các **replica** ở Data node khác. Một node giữ active cho một tập vBucket và giữ replica cho một tập khác.

Do đó, câu “ghi trên node chính” trong bài này chỉ **Data node đang giữ active của vBucket chứa document**; không có một node toàn cluster nhận mọi thao tác ghi như một primary server chung.

Ví dụ minh họa:

| Document ID | vBucket minh họa | Active | Replica |
|---|---|---|---|
| `order::1001` | V7 | Node A | Node B |
| `order::1002` | V19 | Node B | Node C |
| `order::1003` | V28 | Node C | Node A |

Các giá trị V7/V19/V28 chỉ dùng để giải thích, **không phải** kết quả băm thực tế. SDK Couchbase chính thức sử dụng cluster/vBucket map để chọn active owner; ứng dụng không tự tính vị trí document hay chuyển kết nối sang node được cho là “master”.

## 3. Khi nào một ghi được xem là thành công?

**Kết quả thành công phụ thuộc điều kiện xác nhận mà ứng dụng yêu cầu.** Không nên đọc một phản hồi thành công rồi suy ra mọi mục tiêu durability đều đã đạt.

| Tình huống | Có thể suy ra sau response thành công | Không nên tự suy ra |
|---|---|---|
| KV mutation không yêu cầu synchronous durability bổ sung | Mutation được xử lý/ack theo semantics mặc định của thao tác | Tất cả replica đã nhận hoặc tất cả bản đã persist |
| Mutation yêu cầu `MAJORITY` và hoàn tất thành công | Đạt điều kiện xác nhận của đa số bản dữ liệu liên quan | Mọi bản đã ghi bền xuống đĩa |
| Mutation yêu cầu `MAJORITY_AND_PERSIST_TO_ACTIVE` và hoàn tất thành công | Đạt đa số và persistence trên active theo semantics mức này | Mọi replica đều đã persist |
| Mutation yêu cầu `PERSIST_TO_MAJORITY` và hoàn tất thành công | Đạt điều kiện persistence trên đa số bản liên quan | Có backup độc lập hoặc miễn nhiễm xóa nhầm |

Cần phân biệt **server đã chấp nhận** với **client đã nhận response**. Một response có thể thất lạc vì mạng ngay sau khi server xử lý xong; client có thể thấy timeout dù mutation đã hoàn tất.

### 3.1. Default ack không phải xác nhận ghi bền ở mọi bản

Với thao tác không yêu cầu synchronous durability, việc active trả thành công có thể đến **trước** khi replica/persistence đạt các mốc mà nghiệp vụ mong muốn. Điều này có thể phù hợp với cache hoặc dữ liệu tái tạo được, nhưng cần cân nhắc đối với tài chính, thanh toán hoặc trạng thái đơn hàng khó khôi phục.

Chế độ không yêu cầu durability bổ sung **không có nghĩa Couchbase không sao chép hoặc không persist**. Nó chỉ có nghĩa ứng dụng **không đưa các điều kiện synchronous durability đó thành yêu cầu để trả success**.

### 3.2. Durability khác read consistency

Một đơn hàng được ghi với `PERSIST_TO_MAJORITY` vẫn có thể chưa xuất hiện ngay trong truy vấn SQL++ dựa vào GSI ở chế độ `not_bounded`. Chỉ mục thứ cấp được cập nhật bất đồng bộ. Ngược lại, query `request_plus` có thể chờ chỉ mục cập nhật nhưng **không biến một mutation trước đó thành ghi bền hơn**.

Vì vậy cần đặt riêng hai câu hỏi:

1. **Ghi đã đủ bền theo yêu cầu chưa?** → durability.
2. **Truy vấn theo field đã nhìn thấy ghi đó chưa?** → SQL++ scan consistency.

## 4. Replication và persistence khác nhau như thế nào?

**Replication** làm cho một hay nhiều Data node khác có bản mutation theo thiết kế replica của bucket. **Persistence** liên quan đến lưu dữ liệu bền trên thiết bị lưu trữ của node theo cơ chế storage engine.

| Khía cạnh | Replication | Persistence |
|---|---|---|
| Mục đích trực tiếp | Có bản dữ liệu tại node khác khi một Data node lỗi | Hạn chế mất thay đổi nếu một tiến trình/node khởi động lại hoặc trạng thái bộ nhớ mất, trong phạm vi bảo đảm |
| Phụ thuộc | Replica count, placement, liên lạc giữa Data node | Loại bucket, storage engine, disk/I/O và cấu hình liên quan |
| Failure domain | Lý tưởng trải trên nhiều node/hạ tầng độc lập | Bản persist vẫn chịu rủi ro thiết bị/khu vực chứa nó |
| Khi thiếu | Failover có thể thiếu bản đủ điều kiện | Restart/khôi phục có thể không có thay đổi mới nhất trên storage |
| Không thay thế | Backup/DR, transaction, correctness | Data replica, backup/DR, query freshness |

Một replica đã nhận mutation trong bộ nhớ **không nhất thiết** chứng minh nó đã persist mutation. Tương tự, active đã persist không đồng nghĩa mutation đã có bản trên Data node khác.

### 4.1. Vì sao phải tách hai khái niệm?

Xem hai loại lỗi:

**Tình huống A — Data node active mất hoàn toàn:** nếu replica đủ điều kiện còn hoạt động, cluster có cơ sở để promote một bản sao. Số mutation còn tồn tại phụ thuộc trạng thái bản sao và những yêu cầu durability đã hoàn tất.

**Tình huống B — tiến trình database trên active restart:** persistence có thể giúp node khôi phục dữ liệu từ storage. Nhưng bản persist trên chính node này **không thay thế** khả năng tiếp tục phục vụ ở node khác trong lúc nó không khả dụng.

Không có cơ chế riêng nào đảm bảo mọi khía cạnh availability và durability. Cấu hình phải phù hợp **loại lỗi mà tổ chức muốn chịu đựng**.

### 4.2. Bucket type và storage engine

Couchbase có các loại bucket/engine và khả năng lưu bền khác nhau theo phiên bản. Với một bucket có persistence, các mức durability yêu cầu persist có ý nghĩa khác với bucket không có cùng khả năng lưu xuống đĩa.

Đừng áp dụng `PERSIST_TO_MAJORITY` cho một môi trường mà loại bucket hoặc cấu hình không hỗ trợ mức đó. Khi chọn mức durability, cần kiểm tra **Couchbase Server/Capella, bucket type, storage engine, replica count và SDK version**.

## 5. Synchronous durability: client yêu cầu điều kiện mạnh hơn

Couchbase hỗ trợ **synchronous durability** cho các mutation thích hợp: client gửi yêu cầu cùng durability level; server chỉ xác nhận thành công theo mức đó khi các điều kiện liên quan được đáp ứng.

Khái niệm “synchronous” ở đây không có nghĩa toàn bộ hệ thống dừng xử lý tuần tự từng ghi. Nó có nghĩa **kết quả trả cho thao tác hiện tại phụ thuộc việc mutation đạt mốc durability được yêu cầu**.

### 5.1. Bốn lựa chọn cần phân biệt

| Yêu cầu từ ứng dụng | Đa số bản dữ liệu xác nhận mutation? | Active phải persist? | Đa số bản dữ liệu phải persist? |
|---|---|---|---|
| Không yêu cầu synchronous durability bổ sung | Không đặt điều kiện ở mức này | Không đặt điều kiện ở mức này | Không đặt điều kiện ở mức này |
| `MAJORITY` | Có | Không bắt buộc theo level này | Không bắt buộc theo level này |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Có | Có | Không bắt buộc theo level này |
| `PERSIST_TO_MAJORITY` | Có theo semantics mức này | Điều kiện persistence đa số | Có |

Bảng thể hiện **ngưỡng tối thiểu của mức yêu cầu**, không khẳng định những replica không bắt buộc sẽ không được sao chép hoặc persist. Điều kiện chính xác tùy hỗ trợ của server/bucket/version.

### 5.2. Diễn giải từng mức

**`MAJORITY`**

Server cần mutation đạt xác nhận của **đa số các bản dữ liệu tham gia durability của vBucket** theo cơ chế Couchbase. Mục tiêu chính là xác nhận mutation đã được chấp nhận trên đủ bản, không đặt thêm ràng buộc phải persist trên active hoặc replica.

**`MAJORITY_AND_PERSIST_TO_ACTIVE`**

Ngoài điều kiện majority, mutation phải được lưu bền trên **active**. Đây là mức hữu ích khi cần vừa có majority replication, vừa yêu cầu persistence ở owner đang xử lý ghi. Nó không yêu cầu mọi replica đã persist.

**`PERSIST_TO_MAJORITY`**

Mutation phải đạt yêu cầu persistence trên **đa số** các bản liên quan. Nó có thể tăng khả năng bảo vệ trước những failure scenario cần dữ liệu đã nằm trên storage ở nhiều bản, đổi lại độ trễ ghi có thể tăng theo disk I/O và replication.

### 5.3. Không có “mức mạnh nhất luôn tốt nhất” cho mọi dữ liệu

Độ bền cao hơn thường đi kèm ràng buộc phối hợp/lưu trữ cao hơn. Workload ghi nhiều có thể chịu tác động trên latency p95/p99, timeout và throughput.

Lựa chọn theo nghiệp vụ:

- Cache có thể tái tạo từ nguồn khác: độ bền bổ sung thấp hơn có thể hợp lý.
- Đơn đã xác nhận, ledger nghiệp vụ hoặc state khó khôi phục: cân nhắc durability mạnh hơn.
- Session: tùy mức chấp nhận đăng nhập lại, chi phí và khả năng phục hồi.
- Audit/retention: cần đánh giá durability **cùng** backup/restore và yêu cầu tuân thủ; một mức mutation không giải quyết toàn bộ.

## 6. Majority là bao nhiêu bản?

Khái niệm **majority** là số bản lớn hơn một nửa số bản liên quan đến cấu hình durability/vBucket. Mô hình khái niệm đơn giản:

~~~text
majority = floor(N / 2) + 1

N = số bản dữ liệu tham gia tính majority
    theo topology/replica của vBucket và semantics server
~~~

Ví dụ minh họa khi tất cả thành viên dự kiến đều khả dụng:

| Active + replica | N minh họa | Đa số tối thiểu |
|---|---:|---:|
| 1 active, không replica | 1 | 1 |
| 1 active + 1 replica | 2 | 2 |
| 1 active + 2 replica | 3 | 2 |
| 1 active + 3 replica | 4 | 3 |

**Chỉ là mô hình để hiểu quorum**, không phải thuật toán thay thế cluster configuration/SDK. Việc xác định thành viên đủ điều kiện và trạng thái durable write phụ thuộc server và tình trạng topology thực tế.

### 6.1. “Một replica” không luôn cho phép chịu lỗi khi đang ghi durability

Giả sử active A và replica B, `MAJORITY` cần cả hai theo ví dụ N=2. Nếu B mất kết nối, active có thể vẫn phục vụ một số thao tác khác nhưng **không thể mặc nhiên hoàn tất mutation ở mức majority đã yêu cầu**.

Cùng lúc đó, failover/cluster membership có quy trình quản lý riêng; không tự “giảm quorum” vì một request đang timeout. Đội vận hành cần phục hồi redundancy và capacity.

### 6.2. Hai replica không có nghĩa bảo đảm chịu mất hai node

Với N=3, majority về mặt số học là 2. Nhưng mất node nào, active có còn không, replica đã sao chép/persist tới đâu, failure domain và trạng thái failover là những điều quan trọng.

Không chuyển bảng đa số thành khẩu hiệu “có hai replica thì mọi ghi đều sống qua hai node lỗi”. Yêu cầu chịu lỗi phải được **định nghĩa bằng kịch bản và kiểm thử**.

## 7. Dòng thời gian của một durable write

Một mutation yêu cầu synchronous durability có thể được hiểu ở mức logic bằng các giai đoạn:

1. SDK định tuyến mutation đến active vBucket.
2. Active kiểm tra điều kiện thao tác (ID đã tồn tại, CAS, quyền, trạng thái khả dụng).
3. Hệ thống điều phối mutation qua cơ chế durable write, replica và persistence theo level.
4. Khi các điều kiện cần thiết được thỏa, mutation được hoàn tất/commit theo semantics của server.
5. SDK nhận thành công hoặc lỗi/timeout.

~~~mermaid
sequenceDiagram
    participant App as Spring Data / Java SDK
    participant A as Active vBucket (A)
    participant B as Replica vBucket (B)
    participant DiskA as Storage A
    App->>A: INSERT id + durability=MAJORITY
    A->>B: Truyền trạng thái mutation bền
    B-->>A: Xác nhận theo durability protocol
    Note over A,B: Đủ majority theo cấu hình
    opt Nếu level yêu cầu persistence
        A->>DiskA: Lưu bền theo cơ chế storage
    end
    Note over A,B: Hoàn tất tất cả điều kiện của level được yêu cầu
    A-->>App: Thành công sau khi hoàn tất durable write
~~~

Sơ đồ là **mô hình giáo dục**, không phải mô tả đúng thứ tự từng thông điệp nội bộ: các bước prepare, replicate, persist, commit/abort và response có thể có quy tắc riêng trong Couchbase Server. Trong thực tế, khi level yêu cầu persistence, điều kiện đó phải được đáp ứng **trước khi trả success**, không hiểu khối `opt` là ghi đĩa diễn ra sau success.

### 7.1. Mutation đang chờ durability

Một durable write có thể tạm ở trạng thái chuẩn bị/chờ xác nhận, và có thể không hoàn tất nếu replica không khả dụng, timeout hoặc topology thay đổi. SDK/server có cơ chế báo lỗi tương ứng.

Ứng dụng **không được tự kiểm tra “đã thấy document rồi” để kết luận một durable write trước đó đã commit đạt đủ durability** khi kết quả vẫn ambiguous. Cần xử lý theo API semantics, ID và trạng thái nghiệp vụ; đồng thời ghi lại để điều tra nếu không thể xác minh.

## 8. Java SDK: chỉ định durability trên mutation

Ví dụ Java SDK 3.x cho collection `commerce.sales.orders`:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

// orders là Collection đã kết nối đến commerce.sales.orders.
String id = "tenant::42::order::1001";

JsonObject body = JsonObject.create()
        .put("tenantId", "42")
        .put("status", "NEW")
        .put("total", 1490000);

orders.insert(
        id,
        body,
        insertOptions()
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Ở đây:

- `insert` chỉ tạo document nếu ID chưa tồn tại; phù hợp việc tránh tạo mới đè lên bản đã có.
- `DurabilityLevel.MAJORITY` yêu cầu mức đồng bộ tương ứng.
- Nếu hệ thống không đáp ứng điều kiện, operation có thể thất bại hoặc có kết quả không xác định, thay vì silently downgrade theo mong muốn ứng dụng.

### 8.1. Ghi bền và CAS cùng lúc

Khi chuyển một order từ `NEW` sang `PAID`, ứng dụng cần **tránh lost update** và **đặt mức durability**:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;

var old = orders.get(id);
var next = old.contentAsObject()
        .put("status", "PAID");

var saved = orders.replace(
        id,
        next,
        replaceOptions()
                .cas(old.cas())
                .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);

System.out.println("CAS sau khi ghi: " + saved.cas());
~~~

Trong ví dụ:

- **CAS**: bảo vệ update theo phiên bản đã đọc. Nếu document bị sửa giữa `get` và `replace`, thao tác có thể báo CAS mismatch.
- **Durability**: ràng buộc xác nhận bản mutation được chấp nhận.
- **Business validation**: vẫn phải kiểm tra phép chuyển trạng thái `NEW → PAID`, không để một request cũ hủy đơn đã thanh toán chỉ vì dùng CAS đúng.

Không có một tùy chọn nào trong ba phần tự thay thế hai phần còn lại.

### 8.2. TTL và durability không thay thế nhau

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

sessions.upsert(
        "session::abc123",
        sessionBody,
        upsertOptions()
                .expiry(Duration.ofMinutes(30))
                .durability(DurabilityLevel.MAJORITY)
);
~~~

`expiry` xác định thời hạn sống của document; `durability` xác định điều kiện xác nhận mutation. Một session được ghi bền theo mức majority **vẫn sẽ hết hạn** khi TTL kết thúc. Đừng bật durability để “giữ document không bị xóa”, và đừng dùng TTL thay backup.

## 9. Từ Spring Data Couchbase xuống Java SDK

Spring Data Couchbase giúp ánh xạ entity và thao tác qua `CouchbaseRepository` / `CouchbaseTemplate`. Nó không tự tạo một bảo đảm ghi bền bất biến cho mọi project, bởi hành vi còn phụ thuộc **phiên bản framework, SDK, cấu hình bucket và các tùy chọn mutation**.

### 9.1. Document mapping

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

    private String tenantId;
    private String status;
    private Long total;

    // Constructor, getter/setter được lược bỏ.
}
~~~

### 9.2. Repository

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument result = orderRepository.save(order);
~~~

Lời gọi `save` rất thuận tiện, nhưng cần phân biệt:

- `@Version` thường dùng CAS để chống ghi đè trong optimistic locking.
- `save` trả thành công xác nhận operation theo cấu hình đang áp dụng; **không tự suy ra** đó là `PERSIST_TO_MAJORITY`.
- Nếu tổ chức có **minimum durability level ở bucket** theo phiên bản hỗ trợ, effective behavior có thể bị ràng buộc bởi chính sách server.
- Nếu muốn bắt buộc mức khác nhau cho từng use case, chọn API Spring Data/SDK có hỗ trợ cấu hình durability tường minh theo **phiên bản thực tế**.

### 9.3. Khi cần low-level mutation options

Một service có thể dùng Spring Data cho mapping/query thông thường và dùng **Couchbase Java SDK Collection** cho thao tác write quan trọng cần option cụ thể. Cần giữ nhất quán keyspace, JSON mapping, CAS và kiểm thử, tránh lẫn hai cách lưu với serialization khác nhau.

Ví dụ nghiệp vụ:

~~~text
order-service:
  read by ID             → Spring Data repository
  list paid orders       → Spring Data SQL++ query
  create critical order  → Java SDK insert + durability option
  update order status    → Java SDK replace + CAS + durability option
~~~

Việc dùng SDK trực tiếp là một lựa chọn kiến trúc, **không phải quy tắc bắt buộc**: API Spring Data có thể hỗ trợ cấu hình tương ứng tùy version. Không nên tự đặt một annotation/method name chưa được xác minh và khẳng định nó hoạt động trên mọi phiên bản.

## 10. Per-operation durability và chính sách tối thiểu của bucket

Trong những phiên bản/hình thức deployment hỗ trợ, bucket có thể có cấu hình **minimum durability level**. Điều đó có nghĩa operation không thể tùy tiện chọn mức thấp hơn chính sách bucket đã áp dụng.

| Nơi đặt cấu hình | Người/nhóm thường quyết định | Cần kiểm tra |
|---|---|---|
| **Bucket minimum durability** | DBA/SRE/platform phối hợp nghiệp vụ | Có phù hợp mọi collection/workload dùng chung bucket không? |
| **Mutation options** | Nhóm ứng dụng | Mỗi use case cần mức nào? SDK có truyền đúng không? |
| **Replica count/placement** | DBA/SRE | Level có khả thi khi mất node hay không? |
| **Timeout/deadline** | Ứng dụng và vận hành | Có đủ cho latency mục tiêu mà không treo vô hạn không? |

Một bucket chứa cache tạm và ledger thanh toán có yêu cầu rất khác nhau. Nếu minimum durability quá mạnh cho mọi mutation, latency/availability của cache cũng có thể bị ảnh hưởng. Ngược lại, chỉ dựa trên cấu hình ứng dụng mà bỏ qua bucket policy khiến khó kiểm soát khi có nhiều service sử dụng chung dữ liệu.

**Hợp đồng tốt:** thống nhất durability level theo loại dữ liệu, cấu hình thực tế, khả năng replica và tiêu chí giám sát trước khi triển khai.

## 11. Tương quan durability với số replica và trạng thái cluster

Giả sử bucket có **1 replica** và ba Data node A, B, C. Một vBucket có active ở A, replica ở B; C có thể chứa active/replica của các vBucket khác.

Khi A và B khỏe:

- `MAJORITY` cho vBucket trong ví dụ có thể cần xác nhận từ cả A và B.
- `MAJORITY_AND_PERSIST_TO_ACTIVE` cần thêm điều kiện active persistence.
- `PERSIST_TO_MAJORITY` cần persistence theo majority.

Khi B mất kết nối, ứng dụng có thể không thể hoàn tất mutation yêu cầu mức cao; không nên bỏ durability level ngay trong incident chỉ để làm endpoint trả 200.

### 11.1. Phải lập kế hoạch mất node

Câu hỏi cùng DBA/SRE:

1. Sau một Data node lỗi, mỗi vBucket còn những bản nào đủ điều kiện?
2. Automatic failover có được cấu hình và hoạt động trong tình huống này không?
3. Cluster còn đủ Data/Query/Index Service và capacity N-1 để phục vụ?
4. Những mutation đang pending/ambiguous sẽ được điều tra thế nào?
5. Khi nào rebalance/recovery khôi phục lại mức redundancy mong muốn?
6. Backup và kế hoạch DR có độc lập với replica trong cluster không?

Một cluster đã failover thành công vẫn có thể ở trạng thái **giảm dự phòng**, khiến lỗi tiếp theo nguy hiểm hơn. Không tuyên bố “HA đã phục hồi hoàn toàn” chỉ vì API trả về kết quả trở lại.

### 11.2. Failure domain quan trọng hơn chỉ số node

Replica nằm trên node khác nhưng cùng nguồn điện/rack có thể mất cùng active. Cấu hình failure-domain awareness/server groups khi được hỗ trợ có ý nghĩa quan trọng.

Nhà phát triển cần biết mục tiêu availability và durability; nhóm vận hành chịu trách nhiệm placement thực tế, backup và diễn tập.

## 12. Lỗi, timeout và kết quả ghi không xác định

Phần dễ gây tổn thất dữ liệu/nghiệp vụ nhất là **hiểu nhầm timeout**.

~~~mermaid
sequenceDiagram
    participant App as Client API
    participant SDK as Couchbase Java SDK
    participant Data as Active Data node
    participant Rep as Replica Data node
    App->>SDK: INSERT với durability=MAJORITY
    SDK->>Data: Gửi mutation
    Data->>Rep: Replicate/đợi xác nhận
    Rep-->>Data: Đạt điều kiện
    Note over Data: Mutation có thể đã hoàn tất
    Data--xSDK: Response bị mất do mạng
    SDK-->>App: Timeout / ambiguous outcome
~~~

Từ góc nhìn client, một thao tác có thể:

1. **Chưa đến active**: không có mutation.
2. **Đã hoàn tất nhưng response mất**: dữ liệu có thể đã ở server đúng mức yêu cầu.
3. **Bị gián đoạn khi chờ durability**: kết quả cần được đánh giá theo exception/status và semantics server.
4. **Thất bại xác định** vì vi phạm điều kiện như document ID trùng hoặc CAS mismatch.

Do đó, một timeout không phải chứng cứ “không có document”. Mặt khác, một lỗi durability cũng không nên bị âm thầm chuyển thành success nếu ứng dụng không có đủ thông tin xác nhận.

### 12.1. Phân biệt lỗi khẳng định với lỗi ambiguous

| Loại kết quả | Ví dụ | Hướng xử lý |
|---|---|---|
| Thành công rõ ràng | SDK trả `MutationResult` đúng operation | Tiếp tục workflow theo mức đã yêu cầu |
| Từ chối do ID trùng | `insert` gặp document đã tồn tại | Đọc/đối chiếu request; xử lý duplicate |
| CAS mismatch | `replace` dùng phiên bản cũ | Đọc lại và kiểm tra business rule |
| Durability không thể đáp ứng | Replica/topology/level không phù hợp | Cảnh báo và phối hợp vận hành; không tự hạ level |
| Timeout/kết quả mơ hồ | Phản hồi hoặc commit status không rõ | Kiểm tra bằng ID/idempotency và reconciliation |
| Không tìm thấy khi đọc sau timeout | ID chưa tồn tại hoặc trạng thái chưa thể xác minh | Không suy ra chắc chắn mutation trước chưa xảy ra trong mọi tình huống |

Tên exception cụ thể của SDK có thể gồm các nhóm durability failure/ambiguous, nhưng **khả năng retry an toàn phải dựa trên semantics của lỗi và thao tác**, không chỉ dựa trên việc exception là một subclass của Timeout.

### 12.2. Một ví dụ nguy hiểm

~~~text
POST /orders, request-id = checkout-abc

Lần 1: insert order::random-A → server có thể đã hoàn tất
         client nhận timeout
Lần 2: insert order::random-B → success
Kết quả: có khả năng hai đơn cho một checkout
~~~

Sửa bằng cách định danh nghiệp vụ ổn định:

~~~text
Order ID = tenant::42::checkout::checkout-abc
Lần retry vẫn dùng chính ID này.
~~~

Nếu lần đầu đã tạo document, lần sau `insert` có thể báo trùng; ứng dụng đọc lại, đối chiếu payload/trạng thái và trả kết quả đã có thay vì tạo bản khác.

## 13. Quy trình idempotency cho critical write

Một cách triển khai ứng dụng tạo đơn:

~~~mermaid
flowchart TD
    A["Nhận request + idempotency key"]
    B["Sinh document ID ổn định"]
    C["INSERT + durability phù hợp"]
    D{"Kết quả?"}
    S["Success → ghi nhận order"]
    E["Document exists → đọc/đối chiếu"]
    X["Timeout ambiguous → kiểm tra trạng thái"]
    V{"Có bản ghi khớp request?"}
    Y["Trả kết quả cũ, không tạo trùng"]
    N["Retry có kiểm soát hoặc báo cần đối soát"]
    A --> B --> C --> D
    D -->|"Success"| S
    D -->|"Duplicate"| E
    D -->|"Ambiguous"| X
    E --> V
    X --> V
    V -->|"Có"| Y
    V -->|"Không rõ"| N
~~~

Thiết kế cần thêm:

- **Payload fingerprint** hoặc điều kiện xác minh để cùng idempotency key không bị dùng cho request khác nội dung.
- **Giới hạn retry và deadline**; không tạo retry storm khi cluster đang failover.
- **Trạng thái workflow** cho thanh toán/đơn hàng, tránh kết luận “đã thanh toán” chỉ vì có một document `order`.
- **Giám sát các request chưa xác minh** để có reconciliation và cảnh báo.

Đối với hệ thống thanh toán ngoài Couchbase, cần thêm idempotency ở payment gateway; durability của database **không tự bảo đảm** HTTP charge chỉ được thực hiện một lần.

## 14. CAS, transaction và durability là ba trục độc lập

Một workflow có thể cần cả ba:

| Cơ chế | Bảo vệ điều gì? | Không tự bảo vệ điều gì? |
|---|---|---|
| **CAS / `@Version`** | Phát hiện update dựa trên phiên bản document đã cũ | Lưu bền mutation qua node failure; atomicity nhiều document |
| **Couchbase Transactions** | Một nhóm mutation nhiều document theo semantics transaction | Hệ thống thanh toán/email bên ngoài; backup |
| **Synchronous durability** | Mức xác nhận replication/persistence của mutation | Lost update do thiếu CAS; invariant nghiệp vụ; query index freshness |

Ví dụ tạo đơn và giảm tồn kho cần atomicity nhiều document. Nếu cả hai mutation phải có mức durability cụ thể, cần dùng transaction API/cấu hình phù hợp với phiên bản SDK/server, **không tự giả định thêm durability option cho một mutation ngoài transaction làm cả transaction bền tương đương**.

### 14.1. Transaction không nên chứa side effect bên ngoài

Transaction callback trong SDK có thể được thực thi lại khi retry. Không gọi thanh toán, gửi email hoặc publish event không idempotent trực tiếp trong callback.

Nếu cần bảo đảm phối hợp giữa database và message broker, cân nhắc transactional outbox/saga với idempotent consumers và cơ chế reconciliation; đây là bài toán **phân tán nhiều hệ thống**, vượt khỏi phạm vi một Couchbase durable write.

## 15. Độ mới SQL++ và độ bền ghi: không được đánh đồng

Sau khi mutation đã đạt `MAJORITY` hoặc `PERSIST_TO_MAJORITY`, Query Service vẫn có thể truy vấn qua GSI chưa cập nhật kịp.

~~~text
T0: KV insert order::1001, durability đạt yêu cầu
T1: SQL++ WHERE status="PAID", scan consistency=not_bounded
T2: Index Service chưa cập nhật entry của order mới
T3: Index Service bắt kịp mutation
~~~

Ở T1, query có thể chưa thấy đơn. Đây không nhất thiết là vấn đề durability.

Khi đã biết ID, ưu tiên KV:

~~~java
var order = orders.get("tenant::42::order::1001");
~~~

Khi phải truy vấn theo field, chọn scan consistency phù hợp:

| Query option | Ý nghĩa |
|---|---|
| `not_bounded` | Không đòi index bắt kịp một mốc mutation mới |
| `request_plus` | Chờ GSI theo kịp mutation trước mốc query theo semantics server |
| `consistentWith(MutationState)` | Chờ một/nhiều mutation đã biết từ kết quả SDK |

**Không dùng `request_plus` để “thay thế” durability.** Một query đã thấy dữ liệu cũng không chứng minh những điều kiện replication/persistence mạnh nhất đã được thỏa mãn.

## 16. TTL không phải độ bền ghi

TTL/expiry nói về **lúc nào document hết hạn**. Durability nói về **mutation đã được xác nhận theo mức nào**. Một session có TTL 30 phút vẫn có thể được ghi ở mức `MAJORITY`, nhưng nó sẽ hết hạn theo chính sách TTL.

Một hóa đơn cần lưu lâu có thể không nên đặt TTL ngắn, nhưng chỉ bỏ TTL cũng không tạo backup, replica hoặc mức durability mạnh.

Cần xem cùng lúc:

- TTL của mutation.
- MaxTTL/chính sách retention của bucket hoặc collection theo phiên bản.
- Durability level của mutation.
- Backup/restore và yêu cầu pháp lý.
- Tác động của update tới expiry (có giữ hay đặt lại TTL).

Đừng dùng `expiresAt` trong JSON như bằng chứng rằng server đã áp dụng expiry metadata, hoặc dùng CAS như bằng chứng đã persist.

## 17. Reactive write: kết quả vẫn có thể ambiguous

`ReactiveCouchbaseRepository`, reactive template hoặc reactive SDK giúp thực thi I/O theo `Mono`/`Flux`, nhưng **không thay đổi nguyên tắc Data Service, replica và persistence**.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
Mono<OrderDocument> loaded =
        reactiveOrderRepository.findById("tenant::42::order::1001");
~~~

Đặc biệt chú ý `retryWhen`:

- Một subscription lặp lại có thể **thực thi lại side effect** của publisher mutation.
- Nếu mutation lần đầu thành công nhưng response mất, retry có thể tạo xung đột hoặc ghi trùng nghiệp vụ.
- Backpressure không chứng minh durability; concurrency lớn có thể khiến server chờ nhiều durable write cùng lúc.
- Giới hạn timeout, backoff và số retry; phân loại CAS conflict/duplicate/ambiguous riêng.

Với một luồng tạo đơn critical, thiết kế **ID/idempotency trước**, rồi mới quyết định dùng synchronous hoặc reactive API.

## 18. Chi phí hiệu năng của durability

Durability level cao có thể gia tăng số điều kiện mà server cần chờ, nên **latency phân phối** và **throughput** có thể thay đổi theo workload.

Các yếu tố tác động:

1. **Replica count và placement:** số node liên quan, mạng giữa chúng.
2. **Disk I/O:** nhất là khi yêu cầu persistence trên active hoặc majority.
3. **Node health:** replica không khả dụng, rebalance hoặc failover.
4. **Document size và write rate:** dữ liệu nhiều, có nhiều mutation đồng thời.
5. **Collection/bucket type và storage engine:** tính năng, đường ghi và mức durability hỗ trợ.
6. **Transaction load:** nhiều document/round trip có thể tăng contention.
7. **SDK timeout và retry behavior:** deadline quá ngắn gây nhiều ambiguous; quá dài có thể làm request treo so với SLO.

### 18.1. Không quyết định bằng benchmark “một lần gọi”

Chỉ đo một lệnh insert đơn lẻ trong môi trường rảnh không phản ánh điều kiện production. Cần đo:

| Chỉ số | Tại sao quan trọng? |
|---|---|
| KV write p50/p95/p99 | Nhìn thấy độ trễ đuôi do replication/persistence |
| Throughput ops/s | Kiểm tra khả năng chịu tải theo yêu cầu |
| Durability timeout/error rate | Phát hiện level vượt khả năng hiện tại |
| Ambiguous outcome count | Đánh giá nhu cầu reconciliation |
| Replica/active health | Xác định có đáp ứng số bản cần thiết không |
| Disk I/O và network | Phát hiện nghẽn khi persist/replicate |
| API business latency | Xem tác động đến checkout, đăng nhập, xác nhận đơn |

Kết quả nên đo **cùng một workload, cùng kích thước document, cùng topology** khi so sánh durability level.

### 18.2. Không hạ durability để chữa sự cố mà không đánh giá RPO

Nếu `PERSIST_TO_MAJORITY` khiến p99 tăng, chưa thể kết luận “đổi về mặc định là giải pháp đúng”. Trước hết kiểm tra disk/network/replica health, burst traffic, timeout và tài nguyên.

Chỉ hạ mức sau khi chủ sở hữu nghiệp vụ và vận hành đồng ý **thay đổi rủi ro mất dữ liệu** tương ứng.

## 19. Phân loại lỗi ứng dụng và lỗi hạ tầng

| Triệu chứng | Câu hỏi chẩn đoán | Hướng xử lý ban đầu |
|---|---|---|
| `insert` báo ID đã tồn tại | Client có retry cùng idempotency key? | Đọc/đối chiếu document, không đổi ID mù quáng |
| `replace` báo CAS mismatch | Có writer khác sửa document không? | Kiểm tra trạng thái nghiệp vụ rồi mới retry |
| Durability impossible/unavailable | Replica/bucket/topology có hỗ trợ level không? | Kiểm tra cấu hình và phối hợp DBA/SRE |
| Durability timeout/ambiguous | Server đã hoàn tất mutation hay chưa? | Ghi nhận request ID, xác minh document và workflow |
| Write p99 tăng sau node failure | Replica/active owner có thay đổi? | Quan sát failover, redundancy, disk/network, retry |
| KV thấy document nhưng SQL++ chưa thấy | Index lag hay query sai predicate? | Kiểm tra GSI và scan consistency, không sửa durability |
| Document biến mất sau TTL | Metadata expiry có được đặt không? | Kiểm tra TTL, keyspace và lifecycle; không quy ngay cho mất durability |
| Ghi thành công nhưng business state sai | Validation/CAS/transaction boundary có đúng? | Sửa invariant nghiệp vụ; durability không vá logic sai |
| Sau restore thiếu thao tác gần nhất | RPO backup và lịch chụp là gì? | Phân biệt restore point với durability/replica |
| Reactive retry tạo đôi mutation | Publisher resubscribe? ID có ổn định? | Bổ sung idempotency, giới hạn retry |

Không cần log toàn bộ JSON đơn hàng hay secrets để điều tra. Nên dùng **request/correlation ID, document ID đã giảm nhạy cảm, loại operation, level durability, latency và exception class**.

## 20. Runbook ứng dụng khi ghi quan trọng gặp timeout

Đây là quy trình ở **tầng ứng dụng**, không phải hướng dẫn thao tác cluster production:

1. Ghi nhận `requestId`/idempotency key, operation type, document ID, durability level và trace.
2. Phân loại lỗi: có từ chối chắc chắn (duplicate/CAS) hay outcome ambiguous?
3. Với outcome ambiguous, thử kiểm tra trạng thái qua **KV theo ID** khi hệ thống có thể phục vụ; nếu vẫn không xác minh được, để workflow ở trạng thái cần đối soát.
4. Không phát hành side effect ngoài (charge/email/event) dựa trên giả định “timeout nghĩa là chưa ghi”.
5. Retry có giới hạn theo **cùng idempotency key** và business rule; không dùng ID mới cho cùng một hành động.
6. Nếu nghi hạ tầng, chuyển DBA/SRE kèm timestamp, rate, SDK timeout/error và tác động nghiệp vụ.
7. Sau khi cluster phục hồi, chạy reconciliation cho các request chưa xác nhận rõ ràng.
8. Theo dõi số request còn ambiguous; không đánh dấu incident đã xong khi số này chưa được xử lý.

### Một mẫu log có ích

~~~text
time=2026-11-25T03:10:00Z
service=order-api
operation=KV_INSERT
keyspace=commerce.sales.orders
requestId=checkout-abc
documentIdHash=sha256-prefix-redacted
durability=MAJORITY
outcome=AMBIGUOUS
attempt=1
latencyMs=...
exceptionClass=...
~~~

Đây là định dạng gợi ý, không phải log có sẵn của SDK. Tránh ghi password, session token, nội dung thanh toán hoặc document body nhạy cảm.

## 21. Kiểm thử durability đúng cách

Một số test có thể viết ở tầng integration; các failure test cần **môi trường được phép diễn tập**, không chạy failover trên production để “kiểm chứng một bài học”.

| Bài thử | Hành động | Điều cần xác minh |
|---|---|---|
| Ghi mặc định | `insert` không đặt synchronous durability | Operation thành công, nhưng test không suy diễn persistence majority |
| `MAJORITY` | Ghi với một/two replicas theo test cluster | Kết quả đúng khi quorum khả dụng; latency và lỗi khi mất thành viên |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Ghi khi storage hoạt động bình thường | Latency và outcome theo điều kiện active persistence |
| `PERSIST_TO_MAJORITY` | Ghi trên bucket hỗ trợ | Khả năng đạt mức persistence majority hoặc lỗi rõ ràng |
| CAS + durability | Hai writer đọc một CAS rồi thay | Một writer gặp conflict; chỉ ghi hợp lệ được xác nhận |
| Replica unavailable | Mô phỏng lỗi có kiểm soát | Durability failure/timeout, không silent success ngoài semantics |
| Timeout ambiguous | Làm mất response sau khi ghi trong test | Không tạo hai đơn từ một idempotency key |
| Rebalance/failover | Chạy theo runbook lab | Quan sát availability, outcome và thời gian phục hồi |
| SQL++ sau durable write | Ghi rồi query với GSI | Phân biệt durability với `request_plus`/MutationState |
| Backup/restore | Restore trong môi trường riêng | RPO thực tế, dữ liệu và quyền sau khôi phục |

### 21.1. Bài test nghiệp vụ quan trọng hơn chỉ assert mã 200

Một test tạo đơn cần assert:

- Cùng `Idempotency-Key` không tạo hai đơn.
- Bản ghi tồn tại có payload/tenant hợp lệ.
- Không có chuyển trạng thái bất hợp lệ sau CAS conflict.
- Khi timeout, API trả trạng thái kiểm tra được thay vì khẳng định sai.
- Những mutation được xác nhận durable dùng đúng level cấu hình; không âm thầm hạ mức.
- Có metric ghi nhận latency và ambiguous outcomes.

Không kiểm tra persistence bằng cách ngủ cố định vài mili giây rồi chỉ gọi SQL++: đó là **đo index freshness**, không phải kiểm tra durable write protocol.

## 22. Bài tập thực hành

### Bài tập A — phân biệt ba mốc

Một mutation được active node chấp nhận, nhưng replica chưa nhận và storage chưa persist khi client nhận success mặc định. Giải thích tại sao có thể xảy ra và tại sao không thể kết luận dữ liệu đã được bảo vệ trước lỗi active node ngay lúc đó.

### Bài tập B — tính majority

Xét mô hình một active và hai replica. Có bao nhiêu bản tối thiểu tạo thành majority? Nếu một replica mất liên lạc, liệu mọi durable write đều thất bại không? Phân biệt điều kiện toán học với tình trạng owner, membership và topology thực tế.

### Bài tập C — chọn durability level

So sánh ba mức `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE`, `PERSIST_TO_MAJORITY` theo:
- Điều kiện replica acknowledgement.
- Yêu cầu persistence.
- Tác động dự kiến tới latency.
- Rủi ro và loại bucket cần kiểm tra.

### Bài tập D — CAS và durability

Hai API cùng sửa `order::1001`: A cập nhật `PAID`, B cập nhật `CANCELLED`. Nếu B đã đọc CAS cũ, việc đặt `PERSIST_TO_MAJORITY` cho `replace` có giúp B tránh lost update không? Cần điều kiện gì?

### Bài tập E — SQL++ không thấy ghi

Một đơn được ghi `MAJORITY` thành công. `findById(id)` thấy đơn, nhưng SQL++ lọc `status="PAID"` chưa thấy. Đây có phải lỗi durability? Hãy chỉ ra cách kiểm tra GSI và scan consistency.

### Bài tập F — xử lý ambiguous

Client gửi `insert("order::1001", ...)`, nhận timeout và định đổi sang ID `order::1002` để retry. Tại sao nguy hiểm? Đề xuất idempotency key, đối chiếu document và phản hồi API khi chưa thể xác minh.

### Bài tập G — Spring Data repository

Đoạn code `orderRepository.save(order)` trả về entity. Từ đó có thể khẳng định mutation đã đạt `PERSIST_TO_MAJORITY` không? Nêu các cấu hình cần kiểm tra và lựa chọn API nếu cần yêu cầu durability per-operation.

### Bài tập H — performance under failure

Trong giờ cao điểm, p99 của durable write tăng sau failover một Data node. Hãy nêu nhóm metric từ ứng dụng và cluster cần cung cấp trước khi quyết định thêm node, thay replica hoặc điều chỉnh durability level.

## 23. Checklist thiết kế ghi bền

- [ ] Xác định dữ liệu nào phải chịu mất node, process restart, storage loss hoặc lỗi liên vùng.
- [ ] Phân biệt accepted-on-active, replication và persistence.
- [ ] Chọn mức durability theo RPO và workflow, không suy ra từ “insert success” mặc định.
- [ ] Kiểm tra loại bucket/storage engine, SDK/server version và khả năng hỗ trợ level.
- [ ] Đồng bộ chính sách minimum durability ở bucket và option per-operation.
- [ ] Kiểm tra replica count, placement, failure domain và năng lực N-1.
- [ ] Đo write p95/p99, throughput, durability timeouts và ambiguous outcomes.
- [ ] Chọn `insert` với ID ổn định cho tạo mới cần tránh duplicate; dùng CAS cho cập nhật cạnh tranh.
- [ ] Không dùng CAS thay durability hoặc durability thay transaction.
- [ ] Không dùng `request_plus` thay durability; SQL++ index freshness là mục tiêu khác.
- [ ] Với retry/reactive, tránh resubscribe mutation không idempotent.
- [ ] Xử lý timeout ambiguous bằng xác minh trạng thái và reconciliation.
- [ ] Có backup/restore và diễn tập DR độc lập với data replica.
- [ ] Chuẩn bị runbook escalation tới DBA/SRE trước khi cluster thiếu replica.
- [ ] Viết integration/failure tests trên môi trường được phép để xác nhận RPO/RTO.

## 24. Tổng kết

**Xác nhận ghi trên active, sao chép sang replica và lưu bền xuống storage là những mốc khác nhau.** Với Couchbase, mức durability được yêu cầu quyết định điều kiện phải thỏa trước khi mutation được báo thành công. `MAJORITY` yêu cầu xác nhận majority; `MAJORITY_AND_PERSIST_TO_ACTIVE` bổ sung persistence trên active; `PERSIST_TO_MAJORITY` yêu cầu persistence theo majority trong điều kiện được hỗ trợ.

Trong **Spring Data Couchbase**, repository, `CouchbaseTemplate` và Java SDK đều thao tác trên cùng Data Service nhưng khả năng chỉ định durability tường minh phụ thuộc API và cấu hình. Khi triển khai, cần kết hợp **ID ổn định, CAS, retry/idempotency, health của replica và mức durability phù hợp RPO**. Không nhầm độ bền ghi với độ mới SQL++/GSI, tính nguyên tử transaction hay backup/DR. Thiết kế tốt không chỉ yêu cầu ghi “thành công”, mà chỉ rõ **thành công với điều kiện nào, chịu được lỗi nào và ứng dụng phải làm gì khi kết quả chưa xác định**.
