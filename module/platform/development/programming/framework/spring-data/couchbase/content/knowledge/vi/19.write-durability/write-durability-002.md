# DurabilityLevel và các mức xác nhận được hỗ trợ trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập dữ liệu bằng Spring Data Couchbase, document mapping, repository, `CouchbaseTemplate` và SQL++; phối hợp durability với CAS, TTL, transaction, index và API reactive để đáp ứng yêu cầu hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **`DurabilityLevel`** là yêu cầu của một mutation đối với **điều kiện xác nhận ghi**, không phải chế độ đọc hay bảo đảm backup.
2. Phân biệt đúng bốn lựa chọn phổ biến trong Couchbase Java SDK: **`NONE`**, **`MAJORITY`**, **`MAJORITY_AND_PERSIST_TO_ACTIVE`** và **`PERSIST_TO_MAJORITY`**.
3. Nêu khác biệt giữa **nhận mutation trên active**, **xác nhận từ replica** và **persistence xuống storage**.
4. Tính majority trong mô hình active/replica đơn giản, đồng thời nhận biết giới hạn của phép tính khi cluster suy giảm.
5. Áp dụng `DurabilityLevel` trong `insert`, `upsert`, `replace` và những mutation API hỗ trợ, không nhầm với `@Version`/CAS.
6. Xử lý đúng lỗi **durability impossible/not available**, timeout và **durability ambiguous** bằng idempotency/reconciliation.
7. Quyết định mức yêu cầu theo **RPO, SLO latency, giá trị nghiệp vụ, loại bucket và topology**, thay vì chọn “mạnh nhất” cho mọi thao tác.
8. Xác định những việc cần kiểm tra tại tầng Spring Data Couchbase, Java SDK và Couchbase Server/Capella trước khi đưa vào production.

## 2. DurabilityLevel trả lời câu hỏi gì?

Giả sử người dùng nhấn **Thanh toán** và ứng dụng ghi document:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
ID: tenant::42::order::1001

JSON:
{
  "tenantId": "42",
  "status": "PAID",
  "total": 1490000
}
~~~

Ngay khi SDK nhận kết quả thành công từ Data Service, ta muốn biết: **mutation này đã được xác nhận ở bao nhiêu bản dữ liệu và đã được lưu bền ở đâu?**

`DurabilityLevel` diễn tả **mức xác nhận** mà một thao tác ghi yêu cầu. Couchbase sử dụng cơ chế **synchronous durability** (*Sync Writes*, khi được hỗ trợ) để điều phối mutation sao cho những điều kiện của mức đã chọn được đáp ứng trước khi hoàn tất thao tác thành công.

Điều quan trọng: “server ghi thành công” có thể mang nhiều ý nghĩa nếu client **không** hoặc **có** yêu cầu durability đồng bộ. Không được suy ra độ bền của một ghi chỉ từ việc nhận HTTP 200 ở API ứng dụng.

### Ba mốc tách biệt

~~~mermaid
flowchart LR
    App["Spring Data / Java SDK"]
    Active["Active vBucket trên Data node A"]
    Replica["Replica vBucket trên Data node B"]
    DiskA[("Storage node A")]
    DiskB[("Storage node B")]
    App -->|"KV mutation"| Active
    Active -->|"Sao chép"| Replica
    Active -->|"Persist"| DiskA
    Replica -->|"Persist"| DiskB
    Active -.->|"Thành công khi đạt level đã yêu cầu"| App
~~~

- **Active accepted / acknowledged:** Data node đang giữ active vBucket đã tiếp nhận/xử lý mutation theo giao thức.
- **Replicated / acknowledged:** các bản sao liên quan đã nhận và xác nhận mutation đến mốc yêu cầu.
- **Persisted:** dữ liệu được ghi bền theo cơ chế storage engine/bucket của môi trường.

Các công việc có thể tiến triển đồng thời, không phải một chuỗi cứng “ghi RAM → replica → disk”. Durability level quy định **những điều kiện nào phải đạt**, không cung cấp đồng hồ thời gian hay bản sao lưu độc lập.

## 3. Active vBucket không phải “master node” của toàn cluster

Couchbase phân phối document dựa trên document ID vào các **vBucket**. Mỗi vBucket có một **active** và có thể có các **replica**, phân bố trên Data node khác theo topology.

~~~text
Ví dụ minh họa (không phải phép băm vBucket thật):

              Node A        Node B        Node C
vBucket V7    active        replica       replica
vBucket V9    replica       active        replica
vBucket V21   replica       replica       active
~~~

Vì vậy, “ghi vào active” nghĩa là ghi tới **active của vBucket chứa ID cụ thể**, không phải mọi thao tác ghi trong cluster đều phải qua một máy chủ chính duy nhất.

SDK Couchbase định tuyến thao tác KV bằng cluster/vBucket map. Lập trình viên Spring Data **không** tự xác định node đích từ tên tenant hoặc tiền tố ID.

### Liên quan tới durability

Yêu cầu `MAJORITY` hoặc `PERSIST_TO_MAJORITY` được đánh giá đối với những bản dữ liệu tham gia durable write cho **vBucket liên quan**. Nút tham gia và khả năng đáp ứng có thể khác khi node failover, replica không khả dụng hoặc cluster đang rebalance.

Do vậy, số Data node toàn cluster không phải cứ càng nhiều thì riêng một document có càng nhiều bản. Điều quan trọng là **replica configuration và trạng thái các bản dành cho vBucket đó**.

## 4. Bốn giá trị DurabilityLevel cần nắm

Trong Java SDK hiện đại, các lựa chọn thường gặp là:

| Giá trị | Điều kiện cốt lõi | Điều **không** được mặc nhiên bảo đảm |
|---|---|---|
| **`NONE`** | Không yêu cầu thêm điều kiện synchronous durability của các mức bên dưới | Không suy ra đa số replica đã xác nhận hoặc majority đã persist |
| **`MAJORITY`** | Mutation đạt xác nhận từ **đa số** bản dữ liệu liên quan | Không yêu cầu riêng persistence của active/đa số theo level này |
| **`MAJORITY_AND_PERSIST_TO_ACTIVE`** | Đạt majority **và** active persist mutation | Không yêu cầu mọi replica đều persist |
| **`PERSIST_TO_MAJORITY`** | Mutation đạt persistence ở **đa số** bản liên quan | Không có nghĩa mọi bản, mọi vùng hay backup độc lập đều đã cập nhật |

**Lưu ý:** Bảng mô tả cam kết tối thiểu. Hệ thống có thể sao chép hoặc persist **nhiều hơn** điều kiện level yêu cầu. Không diễn giải “không bắt buộc” thành “không xảy ra”.

### 4.1. `NONE`

`NONE` không yêu cầu các điều kiện synchronous durability bổ sung. Điều đó **không có nghĩa** database tắt replication hay không bao giờ ghi xuống đĩa. Nó chỉ nói operation không đòi chờ những mốc đồng bộ mạnh hơn trước khi trả kết quả thành công, trừ các chính sách hiệu lực khác của bucket/server.

Những tình huống có thể cân nhắc: cache có thể tái tạo, dữ liệu tạm hoặc thao tác có thể chịu mất mát gần thời điểm sự cố theo RPO đã thống nhất.

Không chọn `NONE` chỉ vì muốn API nhanh hơn nếu việc mất một mutation gây thiệt hại lớn và khó hòa giải.

### 4.2. `MAJORITY`

Mutation cần đạt xác nhận từ đa số các bản dữ liệu liên quan. Mức này hướng tới sự hiện diện của mutation trên đủ bản theo giao thức, nhưng **không** bắt buộc ghi bền xuống storage của active hay các replica theo level này.

Nếu một Data node lỗi trước khi số bản xác nhận đủ, operation có thể không hoàn tất mức yêu cầu. Không coi việc active đã nhận request là thành công durable.

### 4.3. `MAJORITY_AND_PERSIST_TO_ACTIVE`

Mutation cần thỏa hai điều kiện:

1. Đã đạt xác nhận **majority**.
2. Đã **persist trên active** theo semantics của server.

Đây là lựa chọn khác với `MAJORITY` vì có yêu cầu lưu bền cụ thể tại active. Tuy nhiên không tự kết luận các replica đều đã persist.

### 4.4. `PERSIST_TO_MAJORITY`

Mutation phải đạt **persistence tại đa số** bản dữ liệu theo cơ chế được hỗ trợ. Như vậy có thêm ràng buộc lưu bền trên nhiều bản so với chỉ đợi bản sao xác nhận.

Ở một môi trường disk I/O chậm, mức này có thể làm write latency tăng rõ rệt. Dù vậy nó không bảo đảm mọi node, mọi failure domain, mọi vùng địa lý hoặc mọi backup đã có dữ liệu.

### 4.5. Tránh xếp hạng quá đơn giản

Có thể nói mức có điều kiện persistence **thường đắt hơn** mức chỉ yêu cầu majority acknowledgement, nhưng không nên suy diễn rằng mọi mức luôn tạo cùng một thứ tự latency trong tất cả workload, hoặc `PERSIST_TO_MAJORITY` đồng nghĩa “persist trên mọi node”.

Cần đọc **điều kiện cụ thể** chứ không chỉ ghi nhớ danh sách enum theo một trật tự mạnh/yếu.

## 5. “Majority” được tính như thế nào?

Để học khái niệm quorum, giả sử một vBucket có `N` bản dữ liệu tham gia:

~~~text
majority(N) = floor(N / 2) + 1
~~~

Ví dụ trong điều kiện mọi thành viên dự kiến đều khả dụng:

| Cấu hình minh họa | Tổng số bản N | Ngưỡng majority |
|---|---:|---:|
| 1 active + 1 replica | 2 | 2 |
| 1 active + 2 replica | 3 | 2 |
| 1 active + 3 replica | 4 | 3 |

Ví dụ `1 active + 2 replica` có majority là **2 bản**. Không cần cả ba bản cùng đáp ứng nếu mức đang yêu cầu chỉ đặt điều kiện majority tương ứng.

Tuy nhiên, đây là **mô hình toán học giải thích**, không phải cách lập trình viên tự tính server đã hoàn tất durable write. Trong thực tế phải xét phiên bản Couchbase, replica configuration, membership, trạng thái vBucket và failure/recovery protocol.

### 5.1. Một replica không đủ để “thoải mái mất một node” trong mọi trường hợp

Với `1 active + 1 replica`, majority theo bảng là **2**. Nếu replica không liên lạc được, một durable write yêu cầu majority có thể không đạt mức mong muốn trong khi lỗi chưa được xử lý.

Chỉ vì application vẫn kết nối được active không có nghĩa một request với `MAJORITY` luôn phải được ack.

### 5.2. Hai replica không có nghĩa tất cả lỗi đều an toàn

Với N=3, majority=2 là ngưỡng toán học, nhưng mức bảo vệ thực tế phụ thuộc:

- Node nào bị lỗi và active còn khả dụng hay không.
- Replica nào đã nhận/persist mutation.
- Cách các bản phân bố theo failure domain.
- Trạng thái failover và membership sau sự cố.
- Điều kiện timeout hoặc durable write chưa commit.

Không chuyển “majority 2/3” thành câu hứa “mọi ghi an toàn sau mọi kiểu hai node lỗi”.

## 6. Bảng lựa chọn theo điều kiện xác nhận

Để tránh nhầm giữa **replication acknowledgement** và **persistence**, có thể tóm tắt như sau:

| DurabilityLevel | Majority acknowledgement | Persistence trên active | Persistence theo majority |
|---|---|---|---|
| `NONE` | Không bắt buộc bởi level | Không bắt buộc bởi level | Không bắt buộc bởi level |
| `MAJORITY` | Bắt buộc | Không bắt buộc bởi level | Không bắt buộc bởi level |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Bắt buộc | Bắt buộc | Không bắt buộc bởi level |
| `PERSIST_TO_MAJORITY` | Theo yêu cầu persistence majority | Không nên tự tách thành giả định ngoài semantics cụ thể | Bắt buộc |

Bảng trình bày sự khác biệt **logic**; không phải hướng dẫn giám sát trực tiếp từng replica bằng cách tự đọc số ack. Khi SDK trả một `MutationResult` thành công, ứng dụng nên tin vào API contract của level **đã được áp dụng**; nếu nhận timeout hoặc lỗi, không được tự chuyển trạng thái sang thành công.

### Ví dụ chọn mức

- Một lần cập nhật cache tạm có nguồn dữ liệu khác để dựng lại: có thể không cần synchronous durability bổ sung.
- Tạo đơn cần tồn tại khi một Data node hỏng: xem xét replica, `MAJORITY` và kịch bản lỗi đã định nghĩa.
- Mutation quan trọng cần persistence trên active: cân nhắc `MAJORITY_AND_PERSIST_TO_ACTIVE`.
- Trường hợp yêu cầu storage persistence ở đa số bản: đánh giá `PERSIST_TO_MAJORITY` với chi phí latency.

Không thể xác định mức đúng chỉ từ tên “order” hoặc “payment”. **RPO, SLO và quy trình khôi phục** mới là đầu vào quyết định.

## 7. Giao thức durable write nhìn từ phía ứng dụng

Với synchronous durability, Couchbase có cơ chế điều phối mutation tới các bản liên quan và hoàn tất khi đủ điều kiện. Chi tiết nội bộ có thể gồm giai đoạn prepare, replication, persistence và commit/abort theo phiên bản server.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant SDK as Couchbase Java SDK
    participant A as Active vBucket
    participant B as Replica vBucket
    App->>SDK: INSERT + DurabilityLevel.MAJORITY
    SDK->>A: Mutation và yêu cầu durability
    A->>B: Điều phối mutation theo durable write protocol
    B-->>A: Xác nhận tiến độ
    Note over A,B: Chỉ hoàn tất khi điều kiện majority đạt
    A-->>SDK: Thành công hoặc lỗi theo semantics
    SDK-->>App: MutationResult hoặc exception
~~~

Trong mức yêu cầu persistence, điều kiện persistence tương ứng phải đạt **trước khi SDK nhận kết quả thành công**. Không diễn giải sơ đồ thành thứ tự gói tin bắt buộc cho mọi phiên bản hoặc mọi topology.

### 7.1. Điều gì xảy ra khi level không thể đạt?

Ví dụ replica offline, đĩa thiếu khả năng phục vụ hoặc cluster đang thay đổi topology. Operation có thể gặp lỗi **durability impossible/not available**, timeout hoặc kết quả ambiguous tùy tình huống.

Điểm cần nhớ: client yêu cầu một level thì không nên kỳ vọng server âm thầm báo thành công ở level yếu hơn chỉ vì có sự cố. Thực tế cần kiểm tra mức hiệu lực tại bucket và loại lỗi SDK.

### 7.2. Vì sao không dùng code ứng dụng tự “chờ replica”?

Tự thêm `Thread.sleep(200)` sau mutation không chứng minh replica đã nhận hoặc dữ liệu đã persist. Dùng durability level chính thức để nêu **điều kiện cần đạt**; khi không đáp ứng, nhận lỗi rõ ràng hoặc trạng thái ambiguous cần xử lý, thay vì chờ theo thời gian cảm tính.

## 8. Java SDK: package, enum và các thao tác ghi

Với Couchbase Java SDK 3.x, `DurabilityLevel` được sử dụng từ package:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
~~~

Tên các enum value:

~~~java
DurabilityLevel.NONE
DurabilityLevel.MAJORITY
DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE
DurabilityLevel.PERSIST_TO_MAJORITY
~~~

Đây là **enum option**, không phải Java annotation dùng để tự động bảo vệ tất cả entity. Mỗi operation hoặc một chính sách cấu hình phù hợp cần nêu rõ mức durability được áp dụng.

### 8.1. Chuẩn bị một Collection

~~~java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;

// Giả định Cluster đã cấu hình credentials, TLS và timeout đúng môi trường.
Bucket bucket = cluster.bucket("commerce");
Collection orders = bucket.scope("sales").collection("orders");
~~~

Đoạn này giả định đã có biến `cluster` là `Cluster` được kết nối và keyspace tồn tại. Không tạo `Cluster.connect` mới cho mỗi HTTP request; nên tái sử dụng lifecycle của SDK/Spring.

### 8.2. `insert` với `MAJORITY`

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;

String orderId = "tenant::42::order::1001";

JsonObject body = JsonObject.create()
        .put("tenantId", "42")
        .put("status", "NEW")
        .put("total", 1490000);

MutationResult inserted = orders.insert(
        orderId,
        body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);

System.out.println("CAS = " + inserted.cas());
~~~

`insert` có lợi thế cho workflow tạo mới: nếu ID đã tồn tại, thao tác không tùy tiện ghi đè document. Kết hợp ID ổn định với `MAJORITY` giúp vừa kiểm soát duplicate vừa yêu cầu mức xác nhận ghi. **Hai cơ chế giải quyết hai vấn đề khác nhau.**

### 8.3. `replace` với CAS và `MAJORITY_AND_PERSIST_TO_ACTIVE`

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.kv.GetResult;

GetResult old = orders.get(orderId);
var updated = old.contentAsObject()
        .put("status", "PAID");

var result = orders.replace(
        orderId,
        updated,
        replaceOptions()
                .cas(old.cas())
                .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);

System.out.println(result.cas());
~~~

- **CAS** yêu cầu document vẫn đúng phiên bản đã đọc.
- **Durability** yêu cầu mutation được chấp nhận phải đạt majority và active persistence.
- **Business validation** vẫn phải kiểm tra phép chuyển trạng thái trước ghi.

Nếu `replace` thất bại vì CAS mismatch, đó là xung đột cập nhật **chứ không phải** bằng chứng cluster không đạt mức durability.

### 8.4. `upsert` với `PERSIST_TO_MAJORITY`

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;

var settings = JsonObject.create()
        .put("tenantId", "42")
        .put("type", "CHECKPOINT")
        .put("state", "COMPLETED");

checkpoints.upsert(
        "checkpoint::task-1001",
        settings,
        upsertOptions().durability(DurabilityLevel.PERSIST_TO_MAJORITY)
);
~~~

Ví dụ giả định `checkpoints` là collection đã cấu hình. `upsert` tạo mới hoặc thay body của ID hiện có; nếu dùng cho nghiệp vụ cần ngăn ghi đè, cần CAS/phiên bản hoặc một lệnh phù hợp hơn. Durability cao **không tự biến upsert thành insert-only**.

### 8.5. `NONE`: không yêu cầu durability đồng bộ bổ sung

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;

cache.upsert(
        "cache::product::A1",
        cachedBody,
        upsertOptions().durability(DurabilityLevel.NONE)
);
~~~

Thí dụ này giải thích giá trị `NONE`, không khuyến khích lạm dụng để hạ yêu cầu của hệ thống. Nếu bucket có minimum durability level, cần kiểm tra **semantics hiệu lực**; việc truyền `NONE` không được hiểu là có thể vượt qua chính sách tối thiểu của server.

### 8.6. API mutation khác

Những API như `remove`, `mutateIn` hoặc asynchronous/reactive variants có thể hỗ trợ durability options theo phiên bản SDK. Không gán mặc định rằng một method/overload luôn có option giống nhau: xem documentation theo **SDK 3.x minor version**, loại thao tác và server compatibility.

## 9. DurabilityLevel và chính sách minimum durability của bucket

Bên cạnh mức đặt từ operation, một số Couchbase Server/Capella version cho phép thiết lập **minimum durability level** ở bucket. Khi đó lựa chọn hiệu lực có thể bị ràng buộc bởi chính sách tối thiểu.

~~~text
Ví dụ chính sách thiết kế:

Bucket commerce:
  minimum durability = MAJORITY (giả định)
Order service:
  insert order   -> yêu cầu MAJORITY
Cache service:
  upsert cache   -> gửi NONE
~~~

Nếu hai workload có yêu cầu khác nhau nhưng cùng bucket, cần kiểm tra liệu minimum durability có khiến workload cache bị áp mức mạnh hơn hay thao tác có cấu hình không phù hợp. Hành vi xử lý mức không đạt policy phải xác minh theo server/SDK thực tế.

Không suy đoán rằng mọi request sẽ được “nâng tự động”, hoặc “bị lỗi ngay” trong tất cả version. Điều đúng là: **app code và bucket policy phải được kiểm tra cùng nhau**, không đọc chỉ một bên.

### 9.1. Trách nhiệm giữa ứng dụng và vận hành

| Quyết định | Thường do ai dẫn dắt? | Cần đối chiếu |
|---|---|---|
| Mutation nào quan trọng? | Nhóm ứng dụng/product | RPO và chi phí mất dữ liệu |
| Durability level per-operation | Nhóm ứng dụng | SDK API, bucket policy, latency |
| Bucket minimum durability | DBA/SRE/platform + ứng dụng | Workload dùng chung, support matrix |
| Replica count/placement | DBA/SRE | Khả năng hoàn tất majority khi node lỗi |
| Timeout/alerting | Phối hợp | SLO endpoint, failure scenarios |

Một quyết định per-operation có thể không đủ nếu bucket thiếu replica hoặc môi trường không hỗ trợ persistence mode.

## 10. Những giới hạn hỗ trợ phải kiểm tra

`DurabilityLevel` là enum ở SDK nhưng **không đồng nghĩa mọi deployment đều thực hiện được mọi mức**.

Các điều kiện cần kiểm tra:

1. **Couchbase Server version:** tính năng synchronous durability có trong phiên bản đang dùng không?
2. **Java SDK version:** method và overload hiện tại có nhận durability option không?
3. **Bucket type:** Couchbase bucket có persistence, Ephemeral bucket hoặc loại bucket khác có các khả năng khác nhau.
4. **Storage engine:** mức persistence yêu cầu phải tương thích với loại storage.
5. **Replica configuration:** có đủ thành viên theo semantics majority và failure tolerance mục tiêu không?
6. **Trạng thái cluster:** replica offline, rebalance, disk pressure, network split ảnh hưởng khả năng hoàn tất.
7. **Tầng framework:** Spring Data/CouchbaseTemplate có truyền durability option hay chỉ dùng default/configured policy?
8. **Managed deployment:** Capella có những giới hạn/tùy chọn riêng theo loại cluster, cloud, tier và version.

### 10.1. Bucket không có persistence thông thường

Không nên đặt một level có yêu cầu persist lên một bucket/engine **không hỗ trợ mốc persistence đó**. Một mức không được hỗ trợ cần được coi là lỗi thiết kế/cấu hình, không cố retry vô hạn.

Không khẳng định mọi bucket không persist đều từ chối tất cả synchronous durability: từng mức có điều kiện khác nhau. Hãy xác minh support matrix trên môi trường thật.

### 10.2. Replica thiếu hoặc chưa sẵn sàng

Nếu majority chưa thể đạt, mutation yêu cầu level liên quan có thể gặp timeout hoặc lỗi không thể đáp ứng. Đừng âm thầm chuyển sang `NONE` ngay trong incident mà không chấp nhận thay đổi rủi ro mất dữ liệu.

### 10.3. Nâng cấp hoặc di chuyển môi trường

Khi chuyển từ Couchbase Server tự quản lý sang Capella hoặc nâng cấp server, cần kiểm thử lại những thao tác write quan trọng với **đúng level hiệu lực**, timeouts, replica status và readback.

Chỉ đổi connection string không chứng minh minimum bucket durability, số replica và tính năng storage đã tương đương môi trường cũ.

## 11. Chi phí: durability mạnh hơn làm thay đổi đường ghi

Synchronous durability có thể khiến mutation chờ nhiều điều kiện hơn trước khi phản hồi. Vì vậy cần đánh giá tác động lên:

- **Write latency p50/p95/p99**, nhất là khi replica/disk/network chậm.
- **Throughput** khi có nhiều mutation đồng thời.
- **Availability của thao tác ghi** khi một thành viên quan trọng không sẵn sàng.
- **Timeout và retry rate** khi ứng dụng có deadline ngắn hơn thời gian server có thể hoàn tất.
- **Tải disk/network** với level có persistence ở active hoặc majority.
- **Tail latency của endpoint** nếu một HTTP request thực hiện nhiều mutation nối tiếp.

~~~mermaid
flowchart LR
    W["Yêu cầu KV mutation"]
    D["DurabilityLevel được áp dụng"]
    N["Replica / network health"]
    P["Persistence / disk I/O"]
    L["Latency + timeout"]
    R["RPO / khả năng chịu lỗi"]
    W --> D
    D --> N --> L
    D --> P --> L
    D --> R
~~~

Đây là **quan hệ phụ thuộc**, không phải biểu đồ định lượng. Không thể kết luận một level cụ thể luôn chậm gấp bao nhiêu lần mà không đo workload thật.

### 11.1. Cách benchmark hợp lý

Cần giữ các yếu tố tương đương:

| Biến | Ví dụ cần cố định |
|---|---|
| Keyspace | Cùng bucket/scope/collection, cùng chính sách |
| Document | Kích thước trung bình và phân bố kích thước |
| Workload | Tỷ lệ insert/upsert/replace/remove, hot key |
| Topology | Node, replica, failure domain |
| Tải đồng thời | Request/s và số request in-flight |
| Network | Ứng dụng cùng vùng và cấu hình |
| SDK | Version, connection reuse, retry policy |
| SLO | p95/p99 latency, timeout rate, throughput |

Đo `NONE`, `MAJORITY` và persistence levels bằng cùng benchmark rồi **kết hợp kết quả với yêu cầu mất dữ liệu**, không chỉ chọn level có thời gian thấp nhất.

### 11.2. Khi p99 tăng đột biến

Trước khi thay level:

1. Kiểm tra có node failure/rebalance hoặc replica backlog không.
2. Đo disk I/O, saturation, CPU/memory, network.
3. Xác định tăng latency ở mutation có persistence hay mọi operation.
4. Kiểm tra timeouts/deadlines có quá ngắn.
5. Kiểm tra concurrency/retry storm của ứng dụng.
6. Nếu cần đổi level, cùng nghiệp vụ đánh giá RPO/availability mới.

## 12. Lỗi xác định và kết quả ambiguous

Một trong những nguyên nhân duplicate nghiệp vụ nghiêm trọng là suy diễn:

> “Client bị timeout, vậy mutation chắc chắn chưa ghi.”

Điều này sai trong hệ thống phân tán. Server có thể hoàn tất durable write nhưng response bị mất do mạng hoặc deadline của client.

~~~mermaid
sequenceDiagram
    participant App as order-api
    participant SDK as Java SDK
    participant A as Active Data node
    participant R as Replica
    App->>SDK: insert(orderId, body, MAJORITY)
    SDK->>A: Mutation KV
    A->>R: Replicate/confirm
    R-->>A: Đạt điều kiện
    Note over A,R: Durable write có thể đã hoàn tất
    A--xSDK: Response mất do sự cố mạng
    SDK-->>App: Timeout / ambiguous outcome
~~~

### 12.1. Những nhóm kết quả khác nhau

| Kết quả | Điều suy ra được | Hành động ứng dụng |
|---|---|---|
| `MutationResult` success | Operation hoàn tất theo contract và mức hiệu lực | Ghi nhận, tiếp tục workflow |
| Duplicate ID khi `insert` | Có document cùng ID | Đối chiếu payload/idempotency, không thay ID bừa |
| CAS mismatch khi `replace` | Phiên bản document đã đổi | Đọc lại và kiểm tra business rule |
| Durability impossible/unavailable | Level không thể đáp ứng trong tình trạng cụ thể | Ghi nhận, phân tích bucket/replica, phối hợp vận hành |
| Timeout / durability ambiguous | Không chắc request đã commit hay chưa | Kiểm tra theo ID, reconciliation, retry có điều kiện |
| Query SQL++ chưa thấy document | Có thể index lag, query/filter sai | Kiểm tra KV và scan consistency, không quy ngay cho durability |

Tên exception cụ thể ở SDK có thể gồm các nhóm như `DurabilityAmbiguousException`, `DurabilityImpossibleException` hoặc lỗi không hỗ trợ level, tùy phiên bản. **Không viết một catch cho tất cả exception rồi retry vô hạn.**

### 12.2. Một retry không idempotent nguy hiểm

~~~text
POST /checkout (requestId=checkout-abc)

Lần 1:
  insert("order::random-001") -> server hoàn tất,
  response bị mất -> client timeout

Lần 2:
  insert("order::random-002") -> success

Kết quả có thể có hai đơn cho cùng một checkout.
~~~

Việc đặt `PERSIST_TO_MAJORITY` **không** ngăn duplicate ở ví dụ trên. Cần ID/idempotency ổn định.

## 13. Idempotency khi ghi với DurabilityLevel

Một thiết kế cơ bản:

~~~text
idempotencyKey = tenantId + "::" + checkoutId
orderId = "order::" + idempotencyKey

Mọi retry của cùng checkout đều sử dụng orderId đó.
~~~

~~~mermaid
flowchart TD
    A["Nhận request + Idempotency-Key"]
    B["Tính document ID ổn định"]
    C["INSERT với DurabilityLevel phù hợp"]
    D{"Outcome"}
    E["Success → trả kết quả"]
    F["Duplicate → đọc/đối chiếu"]
    G["Ambiguous → kiểm tra trạng thái"]
    H{"Document khớp request?"}
    I["Trả kết quả đã tồn tại"]
    J["Retry có kiểm soát hoặc chờ reconciliation"]
    A --> B --> C --> D
    D -->|"Success"| E
    D -->|"Duplicate"| F
    D -->|"Ambiguous"| G
    F --> H
    G --> H
    H -->|"Có"| I
    H -->|"Không/chưa rõ"| J
~~~

Một ID ổn định là điều kiện quan trọng nhưng chưa đủ cho mọi hệ thống. Cần thêm:

- So sánh **request fingerprint**: cùng key phải ứng với cùng dữ liệu nghiệp vụ.
- Không tạo ID mới khi xử lý retry cùng một checkout.
- Không coi một document tồn tại là bằng chứng thanh toán bên ngoài đã hoàn tất.
- Lưu trạng thái `PENDING/CONFIRMED/FAILED` hoặc workflow tương đương để đối soát nếu cần.
- Giới hạn retry và có dead-letter/reconciliation cho những request kết quả không xác định.

### 13.1. Khi retry `replace` với CAS

Không thể chỉ lấy CAS mới rồi ghi lại nội dung đã tính từ bản cũ. Cần **đọc lại và tính toán business rule từ trạng thái mới**. Nếu trạng thái đã là `PAID`, có thể trả idempotent success sau khi đối chiếu; nếu trạng thái bất hợp lệ, phải từ chối.

### 13.2. Durability failure có nên tự hạ level?

Không nên mặc định. Hạ từ `PERSIST_TO_MAJORITY` về `NONE` là một quyết định thay đổi RPO/điều kiện bảo vệ dữ liệu. Chỉ thực hiện khi policy nghiệp vụ và quy trình vận hành cho phép, có metric/ghi nhận rõ ràng.

## 14. Synchronous durability và CAS: hai bảo đảm độc lập

`CAS` giúp kiểm tra document còn đúng phiên bản mà ứng dụng đã đọc hay không. Durability level giúp kiểm tra mutation **được chấp nhận** có đạt điều kiện replication/persistence hay không.

| Tình huống | CAS | Durability |
|---|---|---|
| Hai request cùng sửa một order | Phát hiện bản đọc cũ | Không quyết định ai được phép sửa |
| Active node lỗi ngay sau write | Không bảo vệ dữ liệu tự thân | Level và replica/persistence ảnh hưởng khả năng tồn tại |
| Cùng ID insert lại sau timeout | `insert`/ID ổn định, đối chiếu | Không giải quyết duplicate bằng durability riêng |
| Query theo field chưa thấy document | CAS không ép GSI mới ngay | Durability cũng không ép GSI mới ngay |

Một hệ thống thanh toán có thể cần **cả CAS và durability** vì phải bảo vệ trạng thái nghiệp vụ lẫn trạng thái dữ liệu sau node failure.

## 15. Synchronous durability và transaction nhiều document

Một KV mutation trên một document có ranh giới nguyên tử của chính nó. Nếu nghiệp vụ phải cập nhật **orders** và **inventory** như một đơn vị, cần cân nhắc **Couchbase Transactions**.

~~~text
Workflow tạo đơn:
  - insert order::1001
  - replace inventory::sku-A1
  - insert payment-record::1001
~~~

Ba mutation riêng biệt, dù tất cả có level `PERSIST_TO_MAJORITY`, **không tạo thành transaction đa document**. Nếu mutation thứ hai lỗi sau mutation thứ nhất thành công, có thể vẫn tồn tại trạng thái một phần.

### 15.1. Transaction có cấu hình durability riêng

API transaction trong Couchbase SDK có cách cấu hình/tính toán durability và retry theo phiên bản. Không tự thêm operation-level option ngoài transaction rồi suy rằng toàn bộ transaction có cùng contract.

Cần kiểm tra:

1. Transaction manager/API nào đang được dùng trong Spring Data hoặc Java SDK?
2. Mức durability hiệu lực của transaction là gì?
3. Server/bucket có hỗ trợ không?
4. Callback retry có thể chạy lại bao nhiêu lần, side effects được xử lý thế nào?
5. Timeout/conflict được chuyển thành trạng thái API nào?

### 15.2. Không gọi hệ thống ngoài trong transaction callback

Giao dịch Couchbase không tự bao gồm email, Kafka hay payment gateway. Callback có thể được thử lại theo SDK. Hãy dùng idempotency/saga/outbox cho side effect ngoài theo yêu cầu hệ thống.

**Durability không thay thế atomicity đa document, và transaction không tự tạo backup/DR.**

## 16. Durability và độ mới của SQL++/GSI

Ví dụ:

~~~text
T0: insert order::1001 với PERSIST_TO_MAJORITY → success
T1: SQL++ WHERE status = "PAID" → chưa có order
T2: Index Service cập nhật GSI
T3: SQL++ sau đó thấy order
~~~

Điều này có thể do **GSI cập nhật bất đồng bộ**, không phải durability thất bại. Đọc KV theo ID qua Data Service không phụ thuộc Index Service để tìm document.

### Ba lựa chọn query scan consistency

| Mức query | Khi phù hợp | Liên quan gì tới durability? |
|---|---|---|
| `not_bounded` | Danh sách chấp nhận cập nhật trễ | Không thay đổi điều kiện durable write |
| `request_plus` | Cần index theo kịp những mutation trước request | Chờ index, **không** tăng durability |
| `consistentWith(MutationState)` | Cần thấy mutation cụ thể đã biết | Chờ index đạt token, **không** thay sync-write level |

Vì vậy đừng dùng `request_plus` để bù cho write yếu, hoặc bật durability mạnh chỉ để “fix” một query chưa thấy document vừa ghi.

## 17. Durability và TTL: dữ liệu bền vẫn có thể hết hạn

`TTL/expiry` là **chính sách vòng đời**. Một session được ghi với `MAJORITY` và TTL 30 phút vẫn sẽ hết hạn theo TTL. Level mạnh không biến session thành dữ liệu vĩnh viễn.

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;
import java.time.Duration;

sessions.upsert(
        "session::abc123",
        sessionBody,
        upsertOptions()
                .expiry(Duration.ofMinutes(30))
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Các điều kiện khác nhau:

- `expiry`: document sống bao lâu.
- `durability`: ghi được xác nhận theo mức nào.
- `preserveExpiry`/`touch` (khi API hỗ trợ): thay đổi hoặc giữ hạn hết hạn.
- `CAS`: tránh ghi từ phiên bản đã cũ.
- Backup/restore: khôi phục dữ liệu độc lập khi có sự cố ngoài phạm vi replica.

Không dùng durability level thay backup, cũng không dùng trường JSON `expiresAt` thay metadata expiry của Couchbase.

## 18. Spring Data Couchbase: repository có tự đặt DurabilityLevel không?

Spring Data cung cấp abstraction entity/repository:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

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

    // Constructors và accessors được lược bỏ.
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

1. `@Id` phục vụ định danh document.
2. `@Version` thường được Spring Data Couchbase ánh xạ tới **CAS/optimistic locking**, **không phải durability level**.
3. `repository.save` không tự cho biết “level đã dùng là `PERSIST_TO_MAJORITY`” chỉ vì trả một entity.
4. Cấu hình bucket minimum durability, phiên bản Spring Data/SDK và options hiện tại quyết định **mức hiệu lực**.
5. Nếu cần mức riêng cho một operation, xác định phương thức Spring Data/`CouchbaseTemplate` hoặc Java SDK có hỗ trợ truyền durability option.

### 18.1. Dùng Java SDK cho đường ghi cần option cụ thể

Một kiến trúc thực dụng:

~~~text
OrderRepository / CouchbaseTemplate:
  - CRUD entity và tìm theo ID
  - Derived queries / SQL++

Java SDK Collection (khi cần):
  - insert order với DurabilityLevel.MAJORITY
  - replace order với CAS + MAJORITY_AND_PERSIST_TO_ACTIVE
  - write checkpoint với PERSIST_TO_MAJORITY
~~~

Không bắt buộc mọi project dùng SDK trực tiếp; có thể có API/cấu hình Spring Data tương ứng theo phiên bản. Quan trọng là **không tự suy diễn một annotation hoặc property chưa kiểm chứng**.

### 18.2. Cẩn thận khi trộn entity mapping và JSON SDK

Nếu repository lưu field loại entity hoặc mapping conventions đặc biệt, trực tiếp `upsert` một `JsonObject` không tương đương tuyệt đối với `repository.save`. Hãy kiểm thử:

- Document keyspace/id.
- Trường `_class` hoặc discriminator do framework quản lý khi có.
- Field conversion, naming, date/time và schemaVersion.
- CAS và expiry.
- Truy vấn SQL++ sinh từ repository.

Mục tiêu là dùng được durability options mà vẫn giữ **hợp đồng dữ liệu** thống nhất.

## 19. Reactive SDK và DurabilityLevel

Reactive programming giúp quản lý I/O đồng thời bằng `Mono`/`Flux`, nhưng server vẫn phải thực hiện các điều kiện durability giống nhau.

Ví dụ định hướng với reactive Java SDK:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> write =
        orders.reactive().insert(
                orderId,
                body,
                insertOptions().durability(DurabilityLevel.MAJORITY)
        );
~~~

Lệnh chỉ thực hiện khi publisher được subscribe theo cơ chế Reactor. Đoạn ví dụ giả định `orders`, `orderId` và `body` đã được tạo ở phần trước và API tương thích phiên bản SDK.

### 19.1. Resubscription là một mutation mới có thể xảy ra

Nếu một subscriber timeout và pipeline có `retryWhen(...)`, publisher có side effect có thể được subscribe lại. Nếu mutation trước đã commit nhưng response mất, lần thử lại không được tự nhận định “chưa có order”.

Chiến lược:

- Dùng ID ổn định và `insert` cho create-once.
- Phân loại lỗi duplicate, CAS và ambiguous.
- Hạn chế retry/backoff, có deadline rõ ràng.
- Đối soát document và trạng thái nghiệp vụ khi cần.
- Giới hạn concurrency để tránh quá nhiều durable writes đang chờ.

**Reactive không làm durability mạnh hơn và cũng không khiến write hoàn tất trước khi điều kiện được đáp ứng.**

## 20. DurabilityLevel và các mức timeout

Một thao tác durable write có thể chịu nhiều nguồn deadline:

- **Timeout phía SDK/operation**.
- **Thời gian tối đa mà server cho phép để đáp ứng durable write** theo protocol/configuration.
- **HTTP/API deadline** ở tầng service.
- **Timeout mạng, proxy và các cơ chế retry**.
- **Transaction timeout** nếu mutation thuộc transaction.

Không nên đặt HTTP deadline ngắn hơn một cách tùy tiện rồi nghĩ rằng server đã hủy mutation ngay khi caller bỏ chờ. Client có thể mất khả năng biết trạng thái cuối.

### Ví dụ ngân sách độ trễ

~~~text
API POST /checkout: SLO p99 < 800 ms (ví dụ minh họa)
  validate request:      ~20 ms
  business checks:       ~60 ms
  durable KV mutation:   cần đo p99 thật
  serialize response:    ~10 ms
  network + headroom:    phần còn lại
~~~

Đây chỉ là mô hình phân bổ, không phải thông số Couchbase. Cần quan sát request thật, tránh đặt durability timeout giống nhau cho mọi endpoint mà không tính số mutation nối tiếp.

### Khi có lỗi timeout

1. Ghi nhận operation, level, requestId và latency.
2. Phân biệt lỗi chắc chắn với ambiguous.
3. Không tự tạo record mới trước khi xác minh idempotency key.
4. Nếu cluster đang thiếu replica hoặc disk quá tải, chuyển nhóm vận hành với bằng chứng.
5. Theo dõi reconciliation sau khi hệ thống phục hồi.

## 21. Quan sát và cảnh báo ở tầng ứng dụng và cluster

### 21.1. Metrics phía ứng dụng

- Số mutation theo `DurabilityLevel` và keyspace.
- Write p50/p95/p99, timeout/ambiguous outcome rate.
- CAS mismatch, duplicate ID và retry count.
- Deadline budget còn lại khi caller kết thúc.
- Số checkout/order chưa xác minh được kết quả sau timeout.
- Business metrics: đơn trùng, trạng thái không hợp lệ, double charge.

### 21.2. Metrics phía cluster

- Data Service health, active/replica vBucket availability.
- Replica replication health và những tình trạng thiếu redundancy.
- Disk write latency/IOPS, CPU, memory và network.
- Failover, recovery, rebalance, node replacement.
- Durability-related errors/timeouts khi có telemetry.
- Backup/restore và DR readiness.

Tên metric, API và nguồn telemetry thực tế tùy Couchbase Server/Capella version. Không suy ra rằng chỉ một metric “cluster healthy” là đủ chứng minh mọi request đã đạt mức durability đã yêu cầu.

### 21.3. Mẫu structured log

~~~text
timestamp=2026-11-25T03:10:00Z
service=order-api
operation=KV_INSERT
keyspace=commerce.sales.orders
requestId=checkout-abc
documentIdHash=redacted
requestedDurability=MAJORITY
result=AMBIGUOUS
attempt=1
elapsedMs=...
sdkException=...
~~~

Không ghi password, session token, payment credentials hoặc document body nhạy cảm. Nếu cần correlation với server, sử dụng context/trace hợp lệ theo SDK và hệ thống log của tổ chức.

## 22. Triage: chọn lỗi nào cần sửa ở code, lỗi nào chuyển vận hành

| Dấu hiệu | Hướng kiểm tra tại app | Khi cần DBA/SRE |
|---|---|---|
| `insert` duplicate | ID/idempotency, payload mismatch | Khi nhiều duplicate không giải thích được bởi business traffic |
| CAS conflict | Concurrent writers, business transition | Nếu contention/hot key gây bão retry |
| Durability impossible | Level, bucket type, replica constraints | Xác minh topology/replica và khả năng phục vụ |
| Durability ambiguous | Timeout budget, network, reconciliation | Có sự cố node/network hoặc pending writes lớn |
| Write p99 tăng khi bật persist | Workload, concurrency, client timeout | Disk/network saturation hoặc replica backlog |
| KV ghi success, SQL++ chưa thấy | GSI/index lag và scan consistency | Nếu index backlog hoặc node lỗi |
| Dữ liệu đã hết TTL | Expiry metadata, update làm reset TTL? | Bucket/collection policy bất thường |
| Dữ liệu không có sau restore | Restore point, RPO | Backup/DR runbook và phạm vi sự cố |

**Không xử lý bằng cách tăng timeout vô hạn**, cũng không giảm durability mà không xem lại RPO. Chỉ tăng tài nguyên khi đã biết bottleneck ở Data/replica/storage/network.

## 23. Kiểm thử DurabilityLevel

Các test cần chạy trong môi trường **được phép mô phỏng lỗi**, không thực hiện hard failover production chỉ để hoàn thành bài tập.

| Test | Thiết lập | Kỳ vọng đúng |
|---|---|---|
| `NONE` | Ghi vào bucket hợp lệ | Operation theo semantics mặc định; không khẳng định majority persist |
| `MAJORITY` | Replica/topology lành mạnh | Có thể hoàn tất khi đạt majority; đo latency |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Có persistence được hỗ trợ | Xác minh thành công theo level hoặc lỗi có phân loại |
| `PERSIST_TO_MAJORITY` | Bucket/engine hỗ trợ và đủ bản | Thành công/timeout theo policy; đo disk I/O |
| Bucket không hỗ trợ level | Cấu hình test không tương thích | Fail rõ ràng, không silent downgrade |
| Replica tạm không sẵn sàng | Thử trên test cluster có kế hoạch | Lỗi/delay phù hợp; không suy ra success sai |
| CAS + durability | Hai writer cùng đọc CAS cũ | Xung đột được phát hiện, không ghi đè dữ liệu mới |
| Timeout ambiguous | Giả lập mất response sau commit | Một idempotency key không tạo hai đơn |
| SQL++ sau durable write | Query mặc định và request_plus | Phân biệt index freshness với persistence |
| Reactive retry | Resubscribe pipeline mutation | Không tạo duplicate nhờ ID ổn định |
| Backup/restore | Khôi phục vào môi trường tách biệt | Đo RPO/RTO, không coi replica là backup |

### 23.1. Đừng dùng sleep để chứng minh durability

Một test kiểu “insert → sleep(500 ms) → query SQL++ → có row” **không chứng minh** đã persist trên đa số node. Nó còn có thể pass/fail do GSI cập nhật bất đồng bộ.

Durability được xác minh trước hết qua **operation contract/result**, hỗ trợ của môi trường và failure testing có kiểm soát.

## 24. Tình huống thực tế 1 — tạo đơn nhưng mất replica

**Bối cảnh:** bucket có một active và một replica cho vBucket của order. API tạo đơn với `MAJORITY`. Một replica không liên lạc được.

Cần hỏi:

1. Điều kiện majority có đạt được khi chỉ active còn phản hồi không?
2. Nếu SDK nhận lỗi durability, ứng dụng có được trả HTTP 201 không?
3. Có nên chuyển ngay sang `NONE` để giữ throughput?
4. Khi cluster phục hồi, những request ambiguous được xử lý thế nào?

**Hướng phân tích:** Khi điều kiện yêu cầu không thể đáp ứng, trả success là sai contract. App cần ghi nhận lỗi, đối soát ID và bảo vệ idempotency. Vận hành cần khôi phục replica/capacity. Hạ level là **thay đổi yêu cầu nghiệp vụ**, không phải biện pháp retry mặc định.

## 25. Tình huống thực tế 2 — ghi bền nhưng danh sách không thấy

**Bối cảnh:** order được ghi `PERSIST_TO_MAJORITY` thành công. Trang danh sách lọc `status="PAID"` qua SQL++ không thấy document mới, nhưng KV `get(id)` thấy.

Đây có thể là **index lag**: GSI cập nhật bất đồng bộ so với Data Service. Chẩn đoán bằng:

1. Kiểm tra document ID/keyspace và body qua KV.
2. Kiểm tra SQL++ predicate, quyền và GSI.
3. Thử query với `request_plus` hoặc `consistentWith(MutationState)` khi hỗ trợ.
4. Đo Query/Index Service latency, không sửa `DurabilityLevel` chỉ để “làm mới query”.

**Kết luận:** durability và SQL++ freshness là hai trục khác nhau.

## 26. Tình huống thực tế 3 — thanh toán gọi hai lần

**Bối cảnh:** API thanh toán gửi mutation `PERSIST_TO_MAJORITY`, nhận timeout, sau đó gọi lại payment gateway và insert order mới dưới ID khác.

Nguy cơ **double charge** không được giải quyết bởi durability mạnh:

- Mutation đầu có thể đã hoàn tất nhưng response thất lạc.
- Lần retry với ID khác tạo document thứ hai.
- External payment API không nằm trong transaction Couchbase.

Thiết kế lại:

1. Dùng idempotency key cố định ở cả order service và payment gateway theo khả năng gateway.
2. Tách trạng thái order/payment workflow để xác minh.
3. Dùng ID ổn định, `insert` và đối chiếu duplicate.
4. Khi kết quả ambiguous, đưa workflow vào reconciliation.
5. Không phát payment side effect thêm cho tới khi đã có quy tắc retry xác định.

## 27. Bài tập thực hành

### Bài tập A — đọc bảng mức xác nhận

Một mutation `MAJORITY` đã thành công. Có thể kết luận active đã persist không? Nếu mutation `MAJORITY_AND_PERSIST_TO_ACTIVE` thành công, có thể kết luận mọi replica đã persist không? Giải thích.

### Bài tập B — tính quorum

Một vBucket có 1 active và 2 replica. Majority trong mô hình đơn giản là mấy bản? Khi một replica không khả dụng, còn có thể thỏa majority về mặt toán học không? Vì sao vẫn phải kiểm tra trạng thái cluster thực tế?

### Bài tập C — code Java SDK

Viết `orders.insert(...)` với `DurabilityLevel.MAJORITY` và `orders.replace(...)` có cả CAS + `MAJORITY_AND_PERSIST_TO_ACTIVE`. Giải thích hai tham số bảo vệ hai điều gì khác nhau.

### Bài tập D — chọn level theo dữ liệu

Hãy phân tích lựa chọn cho cache giá sản phẩm, session đăng nhập, order confirmed, ledger nghiệp vụ và audit event. Với mỗi loại, nêu RPO, khả năng tái tạo, latency SLO và backup/retention; không chọn chỉ dựa trên tên loại document.

### Bài tập E — sai lầm trong retry

Một service gặp timeout, đổi ID rồi `upsert` lần hai. Vì sao có thể tạo hai record? Đề xuất một idempotency key và quy trình đối soát.

### Bài tập F — Spring Data repository

Lệnh `orderRepository.save(order)` trả về entity. Có đủ cơ sở kết luận `PERSIST_TO_MAJORITY` được áp dụng không? Nêu những điểm cần kiểm tra ở Spring Data version, SDK và bucket policy.

### Bài tập G — môi trường không tương thích

Application yêu cầu `PERSIST_TO_MAJORITY` trên bucket không hỗ trợ persistence tương ứng. Nêu kết quả cần mong đợi và cách xử lý đúng, thay vì retry vô hạn hoặc tự hạ level.

### Bài tập H — reactive retry

Vì sao `retryWhen` có thể thực thi lại một mutation có side effect? Làm thế nào phân biệt duplicate, CAS conflict và timeout ambiguous trong một workflow checkout?

### Bài tập I — durability vs query consistency

Một order ghi bền thành công nhưng SQL++ mặc định chưa thấy. Hãy đề xuất đường KV theo ID, `request_plus` hoặc MutationState theo từng nhu cầu UI mà không đổi durability level.

### Bài tập J — failure drill

Thiết kế một test trên cluster thử nghiệm có thể cô lập một replica và đo write p99, timeout, ambiguous outcomes với `MAJORITY`. Nêu điều kiện an toàn, rollback và metric cần quan sát.

## 28. Checklist triển khai

- [ ] Phân biệt `NONE`, `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` bằng điều kiện thực tế.
- [ ] Xác định nghiệp vụ nào cần durability cao dựa trên RPO và chi phí mất dữ liệu.
- [ ] Kiểm tra SDK/Server/bucket type/storage engine có hỗ trợ level mong muốn.
- [ ] Đối chiếu minimum durability level ở bucket và option của từng mutation.
- [ ] Xác nhận số replica, placement, failure domain và khả năng chịu lỗi.
- [ ] Dùng `insert` + ID ổn định cho nghiệp vụ create-once; không dùng upsert vô điều kiện để che duplicate.
- [ ] Dùng CAS/`@Version` cho update có cạnh tranh; không xem durability là cách chống lost update.
- [ ] Dùng transaction khi cần nguyên tử nhiều document; không gọi side effect ngoài transaction callback.
- [ ] Với timeout ambiguous, có idempotency và reconciliation, không tự giả định write thất bại.
- [ ] Với reactive, kiểm soát subscribe/retry, concurrency và deadline.
- [ ] Đo p50/p95/p99, throughput, durability errors, replica/storage health.
- [ ] Không dùng `Thread.sleep` hay SQL++ query để “chứng minh” mutation đã persist.
- [ ] Phân biệt durability với TTL, scan consistency và backup/restore.
- [ ] Không tự hạ durability khi replica lỗi nếu chưa được chấp nhận thay đổi RPO.
- [ ] Có quy trình kiểm thử failover/recovery trên môi trường được phép và phối hợp DBA/SRE.

## 29. Tổng kết

`DurabilityLevel` diễn đạt **điều kiện xác nhận mà một mutation Couchbase yêu cầu**. `NONE` không yêu cầu synchronous durability bổ sung; `MAJORITY` yêu cầu majority acknowledgement; `MAJORITY_AND_PERSIST_TO_ACTIVE` cần thêm active persistence; còn `PERSIST_TO_MAJORITY` yêu cầu persistence theo majority. Khả năng sử dụng và mức hiệu lực phụ thuộc Couchbase Server/Capella, bucket type, storage engine, replica topology, SDK và bucket policy.

Trong **Spring Data Couchbase**, hãy phân biệt `@Version`/CAS với durability, kiểm tra cấu hình thực tế của repository/`CouchbaseTemplate` và dùng Java SDK option khi cần mức per-operation được hỗ trợ. Một write có durability mạnh vẫn có thể gặp timeout ambiguous; vì vậy **ID ổn định, idempotency, reconciliation, retry đúng loại lỗi và giám sát** là phần không thể thiếu.

**Chọn DurabilityLevel đúng nghĩa là biết mình đang đợi xác nhận ở đâu, sẵn sàng trả giá latency nào và muốn bảo vệ dữ liệu trước loại lỗi nào** — không phải chỉ thêm một enum vào thao tác ghi rồi coi mọi vấn đề nhất quán, giao dịch và khôi phục đã được giải quyết.
