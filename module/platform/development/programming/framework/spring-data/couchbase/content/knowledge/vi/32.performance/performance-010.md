# Phân tích tài liệu lớn, khóa nóng và tải phân bố không đều

## 1. Ba triệu chứng dễ bị gọi chung là “Couchbase chậm”

Một hệ thống bán hàng chạy **Spring Data Couchbase** gặp ba hiện tượng: endpoint xem đơn hàng có p99 tăng khi JSON chứa hàng nghìn sự kiện lịch sử; bộ đếm `counter::global-orders` bị nhiều requests cùng cập nhật và gặp CAS conflict; và một Data node bị quá tải trong khi CPU trung bình toàn cluster chưa cao.

Ba hiện tượng có thể liên quan, nhưng **không cùng nguyên nhân**:

- **Tài liệu lớn (large document):** nhiều byte phải truyền, decode, map, serialize hoặc ghi lại trong mỗi operation.
- **Khóa nóng (hot key):** một document ID nhận quá nhiều lượt đọc hoặc cập nhật, đặc biệt khi nhiều writers cạnh tranh cùng một phiên bản.
- **Tải phân bố không đều (skewed workload):** requests dồn vào một nhóm key, partition/vBucket, node, tenant hoặc query shape; average toàn hệ thống che nút nghẽn cục bộ.

Bài **“Phân tích tài liệu lớn, khóa nóng và tải phân bố không đều”** thuộc chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Module tập trung vào tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để cân bằng hiệu năng, tính nhất quán và khả năng vận hành.

**Sau bài học, bạn có thể:**

1. Phân tích distribution kích thước document và kết nối với latency, bytes, GC.
2. Phân biệt read-hot, write-hot, CAS-hot và query-hot workloads.
3. Giải thích cơ chế vBucket/key placement mà không nhầm prefix với cùng node.
4. Chọn `findById`/`get`, `lookupIn`, `mutateIn`, SQL++ projection phù hợp.
5. Thiết kế bounded document, tách summary/detail/events, hoặc shard counters khi cần.
6. Hiểu các đánh đổi về CAS, idempotency, TTL, transaction và read aggregation.
7. Kiểm soát reactive concurrency, cache stampede, N+1 fan-out và noisy tenants.
8. Đo p50/p95/p99, goodput, body/wire bytes, per-node saturation và conflict rate.
9. Tạo benchmark đa chiều về document size, key skew và read/write mix.

Ví dụ theo Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x tương thích. Tên metric/cấu hình theo Couchbase Server version khác nhau; kiểm tra trên cluster thực tế trước khi kết luận.

## 2. Mô hình dữ liệu xuyên suốt

~~~text
Bucket: commerce

Scope: sales
  Collection: orders
    order::O-2026-001
    order::O-2026-002
  Collection: order_details
    order-detail::O-2026-001
  Collection: order_events
    order-event::O-2026-001::e-001

Scope: metrics
  Collection: counters
    counter::daily-orders::2026-11-25
    views::2026-11-25::shard-00

Scope: checkout
  Collection: carts
    cart::u-42
~~~

Document order ban đầu:

~~~json
{
  "docType": "order",
  "tenantId": "tenant-a",
  "customerId": "u-42",
  "status": "PAID",
  "createdAtEpochMs": 1795582800000,
  "total": 150000,
  "currency": "VND",
  "items": [
    {"sku": "SKU-A", "quantity": 2},
    {"sku": "SKU-B", "quantity": 1}
  ],
  "statusHistory": [
    {"eventId": "e-001", "status": "CREATED"},
    {"eventId": "e-002", "status": "PAID"}
  ],
  "metrics": {"viewCount": 41}
}
~~~

Nếu `statusHistory` và `items` tăng không giới hạn, document ngày càng rộng. Nếu `metrics.viewCount` bị cập nhật trên mỗi GET, document còn trở thành write-hot. Nếu một tenant tạo phần lớn traffic, cluster có thể bị skew ngay cả khi có hàng triệu keys.

## 3. Sơ đồ chẩn đoán tổng quan

~~~mermaid
flowchart TD
    A["Latency p99 hoặc throughput xấu"] --> B{"Body bytes lớn?"}
    B -- "Có" --> C["Full GET/mapping/SELECT *?"]
    C --> D["Projection / lookupIn / tách document"]
    B -- "Không hoặc đã tối ưu" --> E{"Request dồn vào ít key?"}
    E -- "Nhiều reads" --> F["Cache/single-flight đúng freshness"]
    E -- "Nhiều writes" --> G["CAS, retry, atomic counter, sharding"]
    E -- "Không rõ" --> H["Per-node metrics, Query/Index, GC/network"]
    D --> I["Benchmark + correctness test"]
    F --> I
    G --> I
    H --> I
~~~

Các nhánh không loại trừ nhau. Một document có thể vừa lớn vừa có nhiều writers. Một query có thể chậm vì index scan rộng dù response chỉ có hai field.

## 4. “Document lớn” phụ thuộc access pattern

Một JSON 100 KiB có thể nhỏ đối với batch export, nhưng rất rộng với một API chỉ cần `status` ở 5.000 GET/s. Ngược lại, document 2 KiB bị cập nhật hàng nghìn lần/giây vẫn là hot key.

| Thuộc tính | Câu hỏi |
| --- | --- |
| Serialized JSON size | Body bao nhiêu bytes, p95/p99 size? |
| Read projection | Đọc toàn entity hay vài fields? |
| Write pattern | Thay toàn JSON hay một vài paths? |
| Operations per key | Read/write QPS trên nhóm hot keys? |
| Array growth | Data có tăng vô hạn? |
| CAS conflict | Bao nhiêu writers dùng phiên bản cũ? |
| TTL | Có deadline/expiry hoặc maxTTL? |
| Index fields | Field thay đổi có được index không? |
| Mapping | Spring Data converter cấp phát bao nhiêu objects? |
| Tail latency | Document lớn có tương quan p99 và GC? |

Đừng dùng ngưỡng kích thước cứng như “trên 10 KiB là xấu” khi chưa biết workload. Giới hạn kích thước tối đa cũng phụ thuộc phiên bản server; không thiết kế sát giới hạn.

## 5. Vì sao document lớn làm chậm đường đọc?

~~~mermaid
flowchart LR
    A["Data service"] --> B["KV response bytes"]
    B --> C["SDK decode"]
    C --> D["Spring Data converter"]
    D --> E["Domain entity + collections"]
    E --> F["DTO / HTTP JSON"]
    F --> G["Caller"]
~~~

Đường `repository.findById` có thể phải chịu:

- Network payload, TLS và compression.
- SDK buffers và JSON decoding.
- Java allocations cho nested objects/arrays.
- Spring Data converters và type mapping.
- Garbage collection khi nhiều requests concurrent.
- Serialization DTO/HTTP nếu vẫn trả gần toàn entity.
- Application cache memory nếu giữ document đầy đủ.

Nếu API chỉ cần vài field, nhiều phần của đường này là công việc dư thừa.

### 5.1. Logical bytes không phải wire bytes

`contentAsBytes().length` đo bytes body trả về tại SDK theo API; nó không tự bao gồm protocol framing, TLS, retries và byte truyền thực trên mạng.

Báo cáo nên tách logical JSON bytes, HTTP response bytes và network ingress/egress. Java `String.length()` cũng không phải số byte UTF-8 của JSON.

## 6. Instrument body size và KV latency

Ví dụ custom Micrometer metrics:

~~~java
import com.couchbase.client.java.Collection;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderReadProbe {
    private final Collection orders;
    private final DistributionSummary bytes;
    private final Timer timer;

    public OrderReadProbe(Collection orders, MeterRegistry registry) {
        this.orders = orders;
        this.bytes = DistributionSummary.builder(
                    "app.order.kv.response.body.bytes")
                .baseUnit("bytes")
                .tag("collection", "orders")
                .register(registry);
        this.timer = Timer.builder("app.order.kv.get.duration")
                .tag("collection", "orders")
                .register(registry);
    }

    public byte[] getRaw(String id) {
        return timer.record(() -> {
            byte[] data = orders.get(id).contentAsBytes();
            bytes.record(data.length);
            return data;
        });
    }
}
~~~

Đây là **custom app metrics**, không phải metric tự có của mọi SDK. Để vận hành, bổ sung outcome success/not-found/timeout với nhãn cardinality thấp. Không tag document ID hoặc user ID lên từng time series.

### 6.1. Histogram size quan trọng hơn average

Một dataset có 99% document 2 KiB và 1% document 500 KiB có thể gây tail latency và GC cao dù average body không lớn. Đo distribution p50/p95/p99 body size và đối chiếu với p50/p95/p99 latency theo endpoint.

Không lấy trung bình p99 của nhiều JVM instances rồi gọi đó là p99 toàn fleet.

## 7. DTO nhỏ không tự làm KV GET đọc ít byte

~~~java
OrderDocument order = repository.findById(id)
        .orElseThrow();

return new OrderStatusResponse(
        order.getId(), order.getStatus());
~~~

Đoạn này trả HTTP DTO nhỏ nhưng `repository.findById` có thể đã tải/mapping toàn entity. Vì vậy chỉ tạo DTO **sau khi đọc** chưa chắc giảm traffic Couchbase → JVM.

Nếu đã biết exact document key và chỉ cần vài fields, xem SDK `lookupIn`. Nếu tìm theo predicate, xem SQL++ `SELECT` projection và covering index.

## 8. `lookupIn`: một vài path trong document lớn

~~~java
import java.util.List;
import com.couchbase.client.java.kv.LookupInSpec;
import com.couchbase.client.java.kv.LookupInResult;

LookupInResult read = orders.lookupIn(
    "order::O-2026-001",
    List.of(
        LookupInSpec.get("status"),
        LookupInSpec.get("total")
    )
);

String status = read.contentAs(0, String.class);
Long total = read.contentAs(1, Long.class);
~~~

`lookupIn` là KV sub-document operation theo key, không cần Query service/GSI. Nó có thể giảm response bytes khi chỉ cần một số path của JSON lớn.

**Giới hạn:** không hứa server chỉ đọc vài byte từ disk hay `lookupIn` luôn nhanh hơn. Chi phí nội bộ phụ thuộc engine, cache và workload. Kiểm tra missing path/type lỗi; không gộp `PathNotFoundException` với document missing hoặc timeout.

## 9. `mutateIn`: tránh gửi lại toàn JSON khi cập nhật vài fields

~~~java
import java.time.Instant;
import java.util.List;
import com.couchbase.client.java.kv.MutateInSpec;
import com.couchbase.client.java.kv.MutateInOptions;
import com.couchbase.client.java.kv.StoreSemantics;

orders.mutateIn(
    "order::O-2026-001",
    List.of(
        MutateInSpec.replace("status", "PACKED"),
        MutateInSpec.upsert(
            "updatedAtEpochMs", Instant.now().toEpochMilli())
    ),
    MutateInOptions.mutateInOptions()
        .storeSemantics(StoreSemantics.REPLACE)
        .preserveExpiry(true)
);
~~~

Những paths trong cùng một `mutateIn` được xử lý nguyên tử trên **một document**. Nhưng lưu ý:

- `StoreSemantics.REPLACE` yêu cầu document gốc tồn tại, tránh vô ý hồi sinh dữ liệu đã expired.
- `preserveExpiry(true)` giữ TTL theo API/server version hỗ trợ.
- SDK trực tiếp không tự chạy Spring Data auditing, custom converters, `@Version` hoặc Bean Validation.
- Update field thuộc index vẫn có thể cần index maintenance.
- Logical patch bytes giảm không đồng nghĩa physical disk writes giảm đúng tỷ lệ.

Nếu status transition chỉ hợp lệ từ PAID, blind `replace("status","PACKED")` **chưa đủ**; cần đọc state và CAS.

## 10. CAS conflict là dấu hiệu writers tranh chấp

~~~text
A: GET order status=PAID, CAS=c1
B: GET order status=PAID, CAS=c1
A: REPLACE CAS=c1 -> PACKED, new CAS=c2
B: REPLACE CAS=c1 -> CANCELLED -> CAS mismatch
~~~

CAS/`@Version` ngăn overwrite dữ liệu dựa trên phiên bản cũ. Một hot document có nhiều writers có thể khiến CAS conflicts, retries và p99 tăng.

Vòng retry đúng:

1. Đọc lại state/CAS.
2. Kiểm tra lại authorization và business invariant.
3. Nếu còn hợp lệ, gửi mutation có CAS mới.
4. Giới hạn retries, backoff theo latency budget.
5. Nếu không hợp lệ, trả conflict/business rejection tương ứng.

Không “tối ưu” bằng cách bỏ CAS nếu ứng dụng cần tránh lost update.

### 10.1. CAS conflict khác timeout

CAS mismatch báo phiên bản đã đổi; timeout có thể để lại outcome mơ hồ. Một retry increment/array append sau timeout mơ hồ có thể tạo thao tác hai lần. Phân loại lỗi theo SDK version và bảo đảm idempotency.

## 11. VBucket placement và document keys

Couchbase phân phối KV documents qua **vBuckets** theo cơ chế hash/phân vùng của server. Mỗi vBucket có vị trí active và replica tùy topology. Một document key cụ thể được phục vụ bởi partition active tại thời điểm đó, không tự phân tán một update trên key đó qua mọi Data nodes.

~~~mermaid
flowchart TD
    A["Document IDs khác nhau"] --> B["Hash/partition routing"]
    B --> C["vBucket active ở node 1"]
    B --> D["vBucket active ở node 2"]
    B --> E["vBucket active ở node 3"]
    C --> F["Replica placement theo bucket config"]
    D --> F
    E --> F
~~~

Những hệ quả quan trọng:

- Nhiều keys khác nhau có cơ hội phân bố qua nhiều vBuckets/nodes.
- **Một hot key** vẫn có một đường active cho thao tác ghi tại một thời điểm; tăng node không tự nhân khả năng ghi độc lập vào đúng key.
- Prefix `order::` giống nhau **không** mặc định khiến mọi order chung một node.
- Nếu chỉ một nhóm key nhỏ nhận phần lớn traffic, tải vẫn có thể lệch dù keyspace rất lớn.
- Rebalance/failover có thể thay đổi placement; không pin logic nghiệp vụ vào node sở hữu key.

Phân tích hot partitions phải dựa trên metrics/topology thực tế, không đoán từ tên key.

## 12. Phân loại hot keys

| Hotness | Triệu chứng | Nguyên nhân/đánh đổi |
| --- | --- | --- |
| Read-hot | GET dồn lên key ít thay đổi | Network/CPU/cache |
| Write-hot | Rất nhiều mutations | Replication, durability, index |
| CAS-hot | Nhiều read-modify-write trên một doc | Conflicts/retries |
| Large-read-hot | GET JSON rất lớn liên tục | Bytes/GC/p99 |
| Large-write-hot | Replace JSON lớn liên tục | CPU, disk, network |
| TTL-churn | Tạo/hết hạn và refresh thường xuyên | Expiry/cache invalidation |
| Query-hot | SQL++ cùng shape scan rộng | Query/Index bottleneck |

Một cache read-only không xử lý write-hot. `mutateIn` giảm patch bytes nhưng không tự xóa cạnh tranh trên same-key.

## 13. Tải phân bố lệch: top 1% keys có thể chiếm 80% requests

Ví dụ hai nhóm:

| Nhóm | % số keys | % GET/PUT |
| --- | ---: | ---: |
| Hot set | 1% | 80% |
| Long tail | 99% | 20% |

Đây là **phân bố giả định minh họa**, không phải số đo một cluster. Production có thể gần Zipf-like, chịu ảnh hưởng tenant, flash sale, thời điểm trong ngày, hot SKU hoặc những campaign ngắn hạn.

Dù tổng requests/s bằng nhau, uniform và skewed loads có thể cho p99/per-node resource rất khác.

### 13.1. Vì sao cluster CPU trung bình có thể đánh lừa?

Nếu ba Data nodes có CPU 90%, 30%, 25%, average khoảng 48%. Con số này che việc node đầu đang sát ngưỡng. Đọc CPU/disk/network và KV latency **theo từng node** cùng phân bố key/vBucket trước khi tăng số node hoặc tune concurrency.

## 14. Quan sát hotness mà không làm nổ cardinality

Không gắn `documentId`, `userId` hoặc session token vào mỗi time series metric: số label values quá lớn gây mất ổn định hệ giám sát và rò thông tin.

Nên:

- Timer/histogram theo operation, collection, outcome, instance.
- Sampling logs/traces có masking/hash theo chính sách để phân tích hot cohorts.
- Aggregation frequency ngoài metrics labels (heavy hitter analysis).
- Dùng nhãn cohort hữu hạn như `hot_cohort=yes/no` nếu đã phân loại hợp lệ.
- Xem metrics/node topology qua Couchbase UI/API theo phiên bản.
- Ghi keyspace cụ thể, không lưu raw document body/OTP/secrets.

Không khẳng định Server luôn có metric per-key để truy vấn trực tiếp; có thể cần sampling ở ứng dụng và công cụ quan sát phù hợp.

## 15. Node nóng chưa chắc chỉ do một key

Một Data node quá tải có thể do:

1. Một hot key ở active partition.
2. Nhiều hot keys cùng placement.
3. Disk/network/CPU của node đó yếu hoặc lỗi.
4. Data migration/rebalance/failover tạm thời.
5. Payload lớn hoặc hot document churn.
6. Workload của tenant/noisy neighbor.
7. Query/Index fetch work ảnh hưởng Data nodes.

Chẩn đoán phải phối hợp per-node resource metrics, KV op rates, partition placement, retry/timeout, application GC và query plan. **Thêm node có thể giúp tải toàn cụm**, nhưng không chắc chữa single-key contention.

## 16. Tỷ lệ CAS conflict và retry amplification

~~~text
CAS conflict ratio =
  CAS mismatch attempts / total CAS-guarded write attempts

Business goodput =
  successful business writes / measurement seconds

SDK attempt rate =
  all write attempts including retries / seconds
~~~

Một business write phải thử ba lần là **một** request thành công và **ba** SDK attempts, không phải ba đơn hàng được xử lý.

Đo đồng thời latency p50/p95/p99, offered rate, completed goodput, CAS mismatch, timeout/ambiguous outcomes, total retries và Data service saturation. Nếu retries tăng nhưng goodput không tăng, đang có amplification do contention.

## 17. Giảm tần suất ghi khi nghiệp vụ cho phép

Trước khi triển khai sharded counters, hỏi có cần update trên mọi event không.

Ví dụ:

- `lastViewedAt` có thể chỉ ghi một lần mỗi phút nếu product contract cho phép.
- Analytics events có thể được đưa qua pipeline aggregate theo time window.
- Nhiều field edits của một document có thể gom một `mutateIn`.
- Đừng gia hạn TTL trên mỗi GET nếu session semantics không yêu cầu.
- Dùng debounce/coalescing khi có yêu cầu hợp lệ, không làm mất sự kiện cần ghi nhận.

Không drop/batch tùy tiện payment, billing hoặc audit events. Giảm work phải tuân thủ rủi ro và retention đã định.

## 18. Atomic increment giảm lost update, không xóa hot key

~~~java
import java.util.List;
import com.couchbase.client.java.kv.MutateInSpec;
import com.couchbase.client.java.kv.MutateInOptions;
import com.couchbase.client.java.kv.StoreSemantics;

counters.mutateIn(
    "counter::daily-orders::2026-11-25",
    List.of(MutateInSpec.increment("value", 1)),
    MutateInOptions.mutateInOptions()
        .storeSemantics(StoreSemantics.REPLACE)
        .preserveExpiry(true)
);
~~~

`increment` tránh mẫu GET→tính→REPLACE bị lost update khi không có CAS. Tuy nhiên mọi increments vẫn hướng tới **cùng document**; vẫn có work cho replication, durability, TTL/index tùy cấu hình.

Với ambiguous timeout, **blind retry increment có thể đếm trùng**. Exactly-once counting cần event ID/idempotency/deduplication theo thiết kế nghiệp vụ.

## 19. Sharded counter: chia một hot key thành nhiều keys

~~~text
Trước:
counter::pageviews::2026-11-25

Sau:
pageviews::2026-11-25::shard-00
pageviews::2026-11-25::shard-01
...
pageviews::2026-11-25::shard-31
~~~

Các event được định tuyến vào shard dựa trên ID ổn định hoặc cách phân phối có thể kiểm tra. Khi các shard keys phân bố hợp lý, write rate trên một document giảm.

~~~mermaid
flowchart LR
    A["Event có eventId"] --> B["Hash(eventId) mod N"]
    B --> C["Shard 0"]
    B --> D["Shard 1"]
    B --> E["Shard ..."]
    B --> F["Shard 31"]
    C --> G["Read + Sum"]
    D --> G
    E --> G
    F --> G
~~~

**Đánh đổi:**

- Đọc tổng cần N reads hoặc materialized summary.
- Các reads không tự là một snapshot nguyên tử khi values thay đổi.
- Retry cùng event cần idempotency; hash chỉ chọn vị trí, không ngăn double count.
- Resize shard count cần migration/routing version.
- TTL/retention phải được thiết kế per shard.
- Một hash không phù hợp vẫn có thể tạo skew.

Đừng dùng sharding counters kiểu này cho quota/billing yêu cầu exact atomic total nếu chưa có thiết kế consistency riêng.

## 20. Chọn shard ổn định theo event ID

~~~java
public final class ShardKeys {
    private static final int SHARDS = 32;

    private ShardKeys() {}

    public static String forEvent(
            String day, String stableEventId) {
        if (day == null || day.isBlank()
                || stableEventId == null
                || stableEventId.isBlank()) {
            throw new IllegalArgumentException("Invalid input");
        }

        int shard = Math.floorMod(
            stableEventId.hashCode(), SHARDS);

        return "pageviews::" + day
                + "::shard-" + String.format("%02d", shard);
    }
}
~~~

`hashCode()` là ví dụ hash deterministic để mô phỏng, không dùng như cơ chế cryptographic security. Phải đo phân bố: nếu event IDs tương quan hoặc do attacker điều khiển, hash/salt phù hợp có thể cần thiết.

- Hash theo event ID: các events khác nhau có cơ hội sang shard khác.
- Hash theo user ID: một user cực nóng có thể đổ hết vào một shard.
- Random shard cho mỗi attempt: dễ tạo split khi retry cùng event, không tự giải quyết duplicate.
- Nhiều instances phải đồng ý cùng shard count/routing policy.

## 21. Đọc tổng và hiểu chi phí mới của sharding

Một vòng GET blocking:

~~~java
long sum = 0L;
for (int shard = 0; shard < 32; shard++) {
    String key = "pageviews::2026-11-25::shard-"
            + String.format("%02d", shard);
    try {
        var row = counters.get(key);
        sum += row.contentAsObject().getLong("value");
    } catch (com.couchbase.client.core.error
            .DocumentNotFoundException ignored) {
        // Chỉ hợp lệ nếu absent shard được định nghĩa là 0.
    }
}
~~~

Đây là **32 GETs tuần tự**; latency đọc tổng có thể cao. Có thể sử dụng bounded fan-out hoặc summary định kỳ khi contract cho phép.

Không coi missing shard là 0 nếu schema yêu cầu mọi shard phải tồn tại. Và tổng của 32 GETs khi concurrent writes vẫn diễn ra **không đảm bảo snapshot nhất quán tức thời**. Nếu cần một con số tuyệt đối chính xác để ra quyết định thanh toán, phải có cơ chế khác.

## 22. Time-bucket shards và dữ liệu đến muộn

Ví dụ:

~~~text
views::2026-11-25::09::shard-00
views::2026-11-25::09::shard-01
views::2026-11-25::10::shard-00
...
~~~

Time buckets có thể:

- Giảm thời gian mỗi key bị update liên tục.
- Đặt TTL/retention theo cửa sổ.
- Hỗ trợ báo cáo per hour/day.
- Hạn chế một document tích lũy không giới hạn.

Cần giải quyết: UTC/timezone, ranh giới ngày, late events, replay, shard creation, TTL fixed deadline, số document và index entries tăng.

Không dùng cùng TTL cho order detail, session và view aggregates: lifecycle khác nhau.

## 23. Sharding khác replication và durability

Sharding tạo **nhiều logical keys** để phân phối operations. Replication tạo **bản sao dữ liệu** nhằm chịu lỗi/khả năng đọc theo API. Thêm replicas không tạo 32 counters có thể ghi độc lập trên cùng business total.

Với mỗi shard, durability level vẫn cần được chọn theo failure contract. `MAJORITY` có thể tăng chi phí mỗi write; không hạ durability chỉ để benchmark hot counter nhanh hơn nếu dữ liệu không cho phép mất.

## 24. Hot reads: cache và single-flight khi freshness cho phép

Một product profile được GET nhiều nhưng thay đổi ít có thể được cache:

~~~text
HTTP -> Authorization -> cache lookup
                         |
                hit      |      miss
                |        |        |
              DTO       KV GET -> cache -> DTO
~~~

Cần xác định:

- Cache key gồm tenant/locale/permission context khi response phụ thuộc.
- TTL/invalidation trên mutation/revocation.
- Giới hạn stale age có được phép không.
- Cache memory/eviction.
- Stampede khi cùng key expire.
- Error behavior khi Couchbase timeout.

**Cache hit không phải KV GET nhanh hơn**; benchmark cần tách cache hit/miss và total Couchbase operation rate.

### 24.1. Cache stampede tạo hot read burst

Nếu cache của một key hết hạn, hàng nghìn requests cùng miss rồi cùng GET Couchbase, QPS có thể tăng vọt. Single-flight/request coalescing, TTL jitter và bounded refresh có thể giúp, nhưng phải đo và xử lý lỗi.

Không cache session/OTP đã hết hạn hoặc bị revoke lâu hơn deadline; hiệu năng không thay thế security contract.

## 25. Full-document replacement và hot writes

Một service đọc toàn document rồi chỉ đổi `status`:

~~~java
import com.couchbase.client.java.kv.ReplaceOptions;

var previous = orders.get(orderId);
var json = previous.contentAsObject();
json.put("status", "PACKED");

orders.replace(
    orderId,
    json,
    ReplaceOptions.replaceOptions()
        .cas(previous.cas())
        .preserveExpiry(true)
);
~~~

Điều này có thể hợp lý khi phải validate toàn bộ aggregate, thay nhiều fields hoặc giữ converter/domain lifecycle. Nhưng với body 200 KiB chỉ để đổi chuỗi ngắn, GET + full REPLACE có thể tạo bytes, mappings và allocations không cần.

Benchmark nên so với `lookupIn` để đọc đúng state + `mutateIn` có CAS, cùng authorization, durability và TTL. Không so một full replace có CAS với subdocument blind write bỏ CAS rồi kết luận chỉ do payload.

### 25.1. Một document vẫn có thể cần giữ nguyên

Nếu các fields phải luôn thỏa một invariant nguyên tử và thường được đọc/ghi cùng nhau, gom chúng vào **một document** có thể hợp lý hơn tách thành nhiều keys. Giảm kích thước không phải mục tiêu duy nhất; còn cần đúng business semantics và chi phí transaction sau khi split.

## 26. Unbounded arrays: vấn đề tăng theo thời gian

Một order chứa lịch sử trạng thái dài:

~~~json
{
  "status": "PAID",
  "statusHistory": [
    {"eventId": "e-1", "status": "CREATED"},
    {"eventId": "e-2", "status": "PAID"},
    {"eventId": "e-3", "status": "PACKED"}
  ]
}
~~~

Nếu mỗi lần chuyển trạng thái dùng `MutateInSpec.arrayAppend`, request body có thể nhỏ, nhưng array/document vẫn tăng dần. Tới một mức, full GET, conversion, index maintenance và backup/replication trở nên nặng.

Thiết kế thay thế:

~~~text
orders:
  order::O-2026-001
    status, total, recentEventIds, timestamps

order_events:
  event::O-2026-001::e-001
  event::O-2026-001::e-002
  event::O-2026-001::e-003
~~~

Order summary gọn, events immutable riêng. Có thể query lịch sử theo `orderId` và `eventAt` qua index phù hợp.

**Không bỏ audit history chỉ để tăng throughput.** Retention/compliance cần được bảo toàn; sau split có thể cần transaction/outbox nếu trạng thái order và event phải commit cùng nhau.

## 27. Split document theo cách truy cập thực

| Logical entity | Nội dung | Access pattern |
| --- | --- | --- |
| Order summary | ID, customer, status, totals, timestamps | KV GET, SQL++ list |
| Order detail | Address, items, discounts | KV GET khi xem chi tiết |
| Order events | Audit/event records | SQL++ theo orderId/time |
| View counter shards | Number/counter state | KV increment và sum |
| Cart/session | State, expiry/deadline | KV CAS, TTL theo policy |
| Inventory reservation | Số lượng và reservation IDs | KV/transaction theo invariant |

Đọc list không cần tải detail/events. Nhưng endpoint detail có thể cần 2–3 GETs và thêm mapping. **Đo request graph end-to-end**, đừng chỉ nhìn thời gian đọc summary.

### 27.1. Đừng cực đoan tách mỗi field thành document

Mỗi document riêng có overhead metadata, key management, index/TTL, network calls và transaction nếu nhiều field phải đồng bộ. Split chỉ có lợi khi giảm work hơn chi phí mới.

## 28. Tách document làm thay đổi atomicity

Trước khi split, một `mutateIn` có thể cập nhật `status` và `updatedAt` nguyên tử **trong một document**.

Sau khi split:

~~~text
order::O-1
event::O-1::e-42
~~~

hai KV mutations độc lập không tự cùng commit. Nếu contract là “mỗi thay đổi trạng thái phải đi cùng một audit event”, xem Couchbase Transactions hoặc outbox/saga để bảo đảm consistency theo kiến trúc.

CAS/`@Version` bảo vệ phiên bản **một document**, không tạo một transaction nhiều keys. Transaction có staging, commit, metadata/retry costs; cần cân bằng trên invariant thực, không bỏ transaction để có p99 đẹp.

## 29. SQL++ projection giảm width; index tốt giảm scan/fetch

Query trả full entity:

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Projection hẹp:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.total,
       o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

`SELECT` ít fields giúp giảm serialized JSON/DTO bytes. Nhưng nếu Query vẫn Fetch 50.000 documents và sort trước LIMIT, response hẹp **không đủ**. Cần index theo predicate/order và xem `EXPLAIN`.

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_customer_recent
ON `commerce`.`sales`.`orders` (
    customerId,
    createdAtEpochMs DESC,
    status,
    total
);
~~~

Nếu optimizer có thể dùng index để lọc/order/cover projection, sẽ có cơ hội tránh Fetch và sort dư. Tuy nhiên syntax, sargability, missing fields và query plan thực phụ thuộc Couchbase Server release; **không khẳng định index này chắc chắn covering/pushdown** khi chưa EXPLAIN.

### 29.1. Chi phí của index rộng

Index chứa nhiều fields có thể tăng disk/memory và write amplification. Một document lớn có nhiều indexed fields được update thường xuyên có thể làm Index service bận dù endpoint KV GET vẫn nhanh. Cần đo read/write chung.

## 30. Tránh N+1 sau split

Anti-pattern:

~~~text
SQL++ lấy 1.000 summaries
   -> 1.000 KV GET detail
   -> filter trong Java còn 20
   -> HTTP trả 20
~~~

Các bước sửa:

1. Đưa predicate, ORDER BY, LIMIT vào SQL++ trước khi trả kết quả.
2. Nếu list đủ field, trả projection/covering index mà không GET detail.
3. Chỉ GET detail cho subset cuối cùng cần hiển thị.
4. Dùng bounded concurrency và timeout budget cho KV fan-out.
5. Cache detail có kiểm soát nếu business cho phép.
6. Không nuốt missing detail nếu đó là lỗi integrity.

Giảm bytes của một document nhưng tạo 1.000 round trips mới **không phải tối ưu tốt**.

## 31. Reactive fan-out có giới hạn

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<JsonObject> details =
    Flux.fromIterable(detailIds)
        .flatMap(
            id -> orderDetails.reactive()
                .get(id)
                .map(r -> r.contentAsObject())
                .onErrorResume(
                    DocumentNotFoundException.class,
                    e -> Mono.empty()
                ),
            12
        );
~~~

Giả định `detailIds` là danh sách bounded và `orderDetails` là SDK Collection đã tạo. Chỉ bỏ qua not-found nếu business contract cho phép, nếu không để lỗi đi qua.

- `flatMap` concurrency 12 là ví dụ, không phải mức tối ưu cố định.
- Tổng concurrency = requests × fan-out × instances; nhiều pipelines nhỏ vẫn có thể flood Data service.
- `flatMap` không bảo đảm result order; dùng `flatMapSequential` hoặc gắn ID nếu cần.
- Không `block()` trên WebFlux event loop.
- Backpressure không tự tăng capacity của Data/Query service.
- `collectList()` trên stream triệu rows vẫn có thể OOM.

### 31.1. Bounded requests ở cấp hệ thống

Ngoài cap của một pipeline, có thể cần admission control, rate limiting và bulkhead theo tenant/workload để tránh một hot endpoint làm chậm cả service. Monitor số operations in-flight trên toàn fleet, không chỉ một request.

## 32. Mapping Spring Data và thay đổi data model

Entity summary:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderSummaryDocument {
    @Id
    private String id;

    @Version
    private Long version;

    private String customerId;
    private String status;
    private Long total;
    private Long createdAtEpochMs;

    protected OrderSummaryDocument() {}

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Long getTotal() { return total; }
    public Long getCreatedAtEpochMs() { return createdAtEpochMs; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderSummaryRepository
    extends CouchbaseRepository<OrderSummaryDocument, String> {
}
~~~

`findById` có thể dùng KV key lookup. Derived methods theo customer/status thường tạo SQL++/index queries; xem SQL++ thực tế của framework trước khi thiết kế index.

### 32.1. SDK patch không tự chạy Spring Data callbacks

Khi dùng SDK `mutateIn`:

- JSON path phải khớp persisted names, có thể khác Java property bởi `@Field`.
- Auditing/lifecycle callbacks của repository không tự thực thi.
- CAS document thay đổi dù chỉ sửa một field.
- Không làm hỏng type metadata/converter expectations.
- `@Document(expiry)` không tự điều khiển SDK options.
- Kiểm tra repository đọc được entity sau SDK mutation và ngược lại.

Không refactor hàng loạt `repository.save` sang SDK raw JSON khi chưa kiểm tra mapping, concurrency và TTL.

## 33. Index maintenance không biến mất với subdocument

Một giả định sai:

> “Thay một JSON path nên server và Index service chỉ làm việc với vài byte.”

`mutateIn` giảm request payload ở client, nhưng Data service vẫn duy trì document, replication/durability và các index liên quan. Nếu `status` nằm trong GSI, update status có thể gây index maintenance.

Đo KV latency, bytes, Data CPU/disk/network, Index CPU/index size, Query scans, error rate và write throughput. Không suy physical I/O từ `S_patch / S_full` mà thiếu đo lường.

## 34. TTL và split documents

Sau split có thể có các deadline riêng:

- Order summary sống dài hơn cart/session.
- Order detail giữ theo retention của đơn hàng.
- Audit events giữ theo legal policy.
- Counter shards hết hạn sau cửa sổ.
- Bucket/collection `maxTTL` có thể áp mặc định/giới hạn.

Với patch trên key sống có fixed deadline:

~~~java
var changed = counters.mutateIn(
    shardKey,
    java.util.List.of(
        MutateInSpec.increment("value", 1)
    ),
    MutateInOptions.mutateInOptions()
        .storeSemantics(StoreSemantics.REPLACE)
        .preserveExpiry(true)
);
~~~

Ở đây `counters`, `shardKey` và SDK imports như ví dụ trước. `preserveExpiry(true)` cần server/API hỗ trợ; kiểm tra expiry metadata trước/sau với integration test. Không để mỗi increment vô ý renew TTL nếu retention phải cố định.

### 34.1. Missing shard là zero hay lỗi?

Nếu shard chưa tạo theo policy, missing có thể coi là 0. Nhưng nếu shard lẽ ra phải tồn tại và bị TTL xóa trước khi tổng hợp, trả 0 sẽ làm báo cáo sai. Cần định nghĩa lifecycle, late events, backfill và monitoring.

## 35. Multi-tenant skew và noisy neighbor

Một tenant có thể chiếm 70% Query/Index hoặc KV traffic, khiến tenants khác bị ảnh hưởng dù mỗi tenant có nhiều keys.

Đánh giá:

- Metrics theo tenant cohorts có giới hạn, không tag user IDs tự do.
- Rate limiting/admission control theo workload.
- Composite index theo `tenantId` và điều kiện nghiệp vụ.
- Phân tách reporting/batch khỏi latency-sensitive traffic.
- Cân nhắc namespace/isolation hoặc cluster riêng cho workloads rất lớn.
- Benchmark fairness và p99 của tenants còn lại dưới noisy-tenant load.

Không tạo bucket/collection cho từng tenant mà chưa đánh giá overhead index/cấu hình/quyền và migration.

## 36. Query-hot workloads không nhất thiết có hot KV key

Ví dụ báo cáo:

~~~sql
SELECT o.status, COUNT(1) AS orderCount
FROM `commerce`.`sales`.`orders` AS o
WHERE o.createdAtEpochMs >= $fromEpochMs
GROUP BY o.status;
~~~

Nếu gọi liên tục, query có thể scan nhiều index entries, aggregate và consume Query/Index resources mà không có một document ID quá nóng.

Các hướng:

- Index phù hợp predicate và projection.
- `EXPLAIN`, query profiles, scanned/fetched rows.
- Pre-aggregation/materialized counters nếu consistency cho phép.
- Cache report theo time window; bounded request rate.
- Reporting service isolation, scheduling batch loads.

Đừng áp sharded KV counter để chữa mọi SQL++ bottleneck.

## 37. Replica reads và tính nhất quán

Một số SDK APIs hỗ trợ đọc replicas, nhưng visibility/staleness có thể khác active-key read theo API/server version.

Với read-hot keys:

1. Xác định có chấp nhận stale result không.
2. Kiểm tra SDK, active/replica topology và tính năng hỗ trợ.
3. Đo tail latency/error rate/bytes thực tế.
4. Test mutation visibility, TTL và failover.
5. Không hạ consistency nếu endpoint cần read-your-writes.

Replication tăng khả năng chịu lỗi và hỗ trợ các đường đọc được phép, nhưng không tự biến một hot document thành nhiều bản ghi cập nhật độc lập.

## 38. Durability làm hot writes có thêm chi phí

`DurabilityLevel.MAJORITY` hoặc persistence levels có thể thêm điều kiện replica/disk acknowledgement. Một key nóng liên tục update sẽ lộ tail latency của mạng, disk và server queues.

Cần kiểm tra:

- Replica count/topology và server version.
- Data service CPU/disk latency.
- Ambiguous mutation outcomes.
- Retry storm và idempotency.
- Index maintenance trên indexed fields.
- Goodput và p99 ở workload skew.

Không hạ durability chỉ để giảm p99 khi business cần chịu lỗi node. **Timeout sau increment không chứng minh increment chưa được áp**; không retry mù quáng.

## 39. Transaction và giới hạn của một aggregate

Nếu split tạo:

~~~text
order::O-1
order-detail::O-1
order-event::O-1::e-42
~~~

và business yêu cầu nhiều document commit cùng nhau, dùng Couchbase Transactions hoặc outbox/saga phù hợp.

Một hot inventory key trong transaction có thể gây conflicts/retries. Tăng concurrency có thể làm throughput tệ hơn. Khi tối ưu, cân nhắc reservation records, aggregate boundaries và idempotency.

**CAS không tự là transaction nhiều documents.** Một update status và một update inventory ở hai keys có thể một thành công, một thất bại khi thực hiện độc lập.

## 40. Ma trận benchmark: size × skew × read/write ratio

Thử các trục độc lập:

| Biến | Mức ví dụ | Mục tiêu |
| --- | --- | --- |
| Document size | 2, 64, 512 KiB | Bytes/mapper/GC |
| Key distribution | Uniform; top 1% nhận 80% requests | Hotness/skew |
| Read/write ratio | 95/5, 80/20, 20/80 | Tách bottleneck |
| Concurrency | 1, 8, 32, 128 | Queue/saturation |
| Access method | GET, lookupIn, mutateIn, replace | Hiệu quả thực |
| Index coverage | Indexed/unindexed updated field | Maintenance |
| Durability | Mức đúng business | Replica/disk cost |
| Cache | Cold/warm, hit ratio rõ | Cache effects |
| TTL | Không TTL; fixed deadline | Expiry correctness |
| Node topology | Size/node count/placement | Per-node skew |

Các mức là **ví dụ kế hoạch**, không phải benchmark đã đo. Tránh làm tải sản xuất không kiểm soát.

### 40.1. Thí nghiệm tách size khỏi skew

Ít nhất bốn nhóm:

~~~text
A: uniform keys, small JSON
B: uniform keys, large JSON
C: skewed keys, small JSON
D: skewed keys, large JSON
~~~

Nếu chỉ so A và D, không thể biết phần nào do body size, phần nào do skew. Cần cùng hardware/SDK/config/consistency và arrival model.

### 40.2. So update đúng business contract

~~~text
Full write:
  GET -> validate state -> REPLACE CAS -> preserveExpiry

Subdocument:
  lookupIn -> validate state -> mutateIn CAS -> preserveExpiry
~~~

Không bỏ validation/CAS ở phương án thứ hai rồi ghi “subdoc nhanh hơn X%” như thể tương đương.

## 41. Sinh workload skew an toàn bằng dữ liệu giả lập

~~~java
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

public record SkewedKeys(
        List<String> hot,
        List<String> cold,
        double hotProbability) {

    public SkewedKeys {
        if (hot == null || hot.isEmpty()
                || cold == null || cold.isEmpty()
                || hotProbability < 0 || hotProbability > 1) {
            throw new IllegalArgumentException(
                "Invalid distribution");
        }
    }

    public String next() {
        var r = ThreadLocalRandom.current();
        var candidates = r.nextDouble() < hotProbability
                ? hot : cold;
        return candidates.get(r.nextInt(candidates.size()));
    }
}
~~~

Nếu hot set là 1% keys và `hotProbability=0.8`, khoảng 80% requests chọn nhóm hot trong giả lập hai-cohort này. Đây **không phải phân bố Zipf chính xác**; với production skew phức tạp cần calibrate theo observed key frequencies.

Dùng synthetic IDs thay raw production IDs/PII/token, giữ kích thước/pattern cần thiết mà không mang dữ liệu nhạy cảm vào bài test.

## 42. Open-loop và coordinated omission

**Closed-loop** gửi request mới sau khi request cũ hoàn tất; hệ thống chậm có thể làm offered rate giảm. **Open-loop** cố duy trì arrival rate, hữu ích để quan sát p99 và saturation khi tải tăng.

Khi benchmark:

- Ghi offered requests/s và completed goodput/s riêng.
- Ghi in-flight/queued/cancelled requests.
- Không loại timeout khỏi kết luận.
- Kiểm tra load generator CPU/network/socket budget.
- Hiểu công cụ xử lý coordinated omission như thế nào.
- Tách warm-up khỏi steady-state và ghi run ID.

Thử nghiệm chỉ có vài chục requests không đủ căn cứ đánh giá p99.

## 43. Metrics nên thu theo đúng tầng

| Metric | Cách phân nhóm hữu ích |
| --- | --- |
| HTTP p50/p95/p99 | Endpoint, outcome, size cohort |
| KV p50/p95/p99 | GET, lookupIn, mutateIn, replace |
| Business goodput | Successful requests/s |
| SDK attempt rate | Bao gồm retries |
| CAS conflicts | Rate/tỷ lệ attempts |
| Logical body bytes | Histogram per collection/operation |
| HTTP/network bytes | Egress/ingress tại tầng đo rõ |
| Data service CPU/disk/network | Per-node, không chỉ average |
| Query/Index service | Plan, scanned entries, Fetch, CPU |
| App JVM heap/GC | Allocation và pauses |
| Hot cohort share | Bounded cohorts, không raw IDs |
| Cache hit/miss | Miss storms và evictions |
| Timeout/ambiguous outcomes | Không ẩn trong success average |

Nếu SDK/server không expose tên metric giả định, sử dụng telemetry thực hỗ trợ theo release và nêu giới hạn quan sát.

## 44. Số liệu minh họa và cách tránh kết luận sai

| Chỉ số | Uniform 2 KiB GET | Skewed 512 KiB GET |
| --- | ---: | ---: |
| Average | 8 ms | 35 ms |
| p95 | 18 ms | 110 ms |
| p99 | 40 ms | 240 ms |
| Logical bytes/s tại 400 GET/s | ~800 KiB/s | ~200 MiB/s |
| Highest Data node CPU | 40% | 90% |
| App GC pressure | Thấp | Cao |

**Các con số hoàn toàn giả định**, không phải đo Couchbase thật. Chúng thay đổi cả size **lẫn** skew nên không thể quy tất cả tác động cho hot key. Hãy chạy thêm uniform-large và skew-small.

### 44.1. Đơn vị

`KiB` = 1.024 bytes; `MiB` = 1.048.576 bytes; `Mbps` thường là triệu bit/giây. Logical JSON payload không đồng nghĩa physical network wire bytes do compression/TLS/retries.

## 45. SLO của hot endpoint phải nhìn tail latency

Nếu `GET /orders/{id}` có p50=12 ms nhưng p99=600 ms dưới flash sale, người dùng ở tail vẫn gặp timeout. Xem p95/p99 theo body size, hot cohort, instance/node, cache hit/miss, Query plan, retries và time window.

Không trung bình p99 của từng node để ra fleet p99. Sử dụng histogram/distribution có thể aggregate đúng.

## 46. Bảng chẩn đoán nhanh

| Triệu chứng | Giả thuyết | Cách kiểm tra |
| --- | --- | --- |
| Mọi key chậm trên một node | Disk/network/CPU health | Per-node metrics |
| Vài keys rất chậm | Hot key/CAS contention | Hot cohort sampling |
| Chỉ large documents chậm | Bytes/mapping/GC | Size vs latency histogram |
| CAS mismatches tăng | Nhiều writers một doc | Retry attempts, write rate |
| KV nhanh, SQL++ chậm | Query/Index plan | EXPLAIN/profiles |
| SDK nhanh, HTTP chậm | DTO/GC/other downstream | Trace end-to-end |
| Burst đọc sau cache TTL | Stampede | Hit/miss/concurrency |
| Sau split số GET tăng mạnh | N+1 | Bounded fan-out |
| Counter tăng trùng | Retry increment | Event idempotency |
| Shards phân bố lệch | Routing hash/input skew | Per-shard stats |
| Replica read cũ | Staleness | Consistency contract |
| Shard biến mất | TTL/retention sai | Expiry metadata |
| Rebalance rồi skew đổi | Active placement | Cluster topology |

Đừng chữa một bottleneck Query service bằng cách chỉ tăng KV timeout, hoặc chữa mapping cost bằng cách tạo thêm Index nodes.

## 47. Integration test sau document split

Các bài kiểm thử:

1. Tạo summary/detail/event test documents có IDs duy nhất.
2. Repository `findById` đọc summary đúng bucket/scope/collection.
3. API detail kết hợp dữ liệu đúng response contract.
4. List API không tải detail khi không cần.
5. Không lộ data cross-tenant qua detail/event lookups.
6. JSON fields khớp `@Field`/converters.
7. CAS/`@Version` ngăn lost updates.
8. TTL/expiry của từng document đúng policy.
9. Transaction/outbox giữ invariant order+event nếu business cần.
10. Missing detail/expired event có outcome rõ, không âm thầm sai dữ liệu.

Không dùng một HTTP 200 response làm bằng chứng toàn bộ consistency được giữ.

## 48. Test contention và idempotency của counter

~~~text
Arrange:
  Counter shards value=0
  50 events có IDs ổn định

Act:
  Chạy increments đồng thời trong test cluster
  Inject ambiguous timeout có kiểm soát
  Đọc toàn bộ shard values

Assert:
  Nếu contract exactly-once effect:
    sum = số event IDs unique
    Dedupe phải có cơ chế rõ
  Nếu at-least-once:
    assert theo contract tương ứng
  Shards không mất trái TTL
  Retries không bị che khỏi metrics
~~~

Increment atomic **không** tự bảo đảm exactly-once effect dưới timeout/retry. Test phải xác minh lớp idempotency, không chỉ khả năng cộng số của SDK.

### 48.1. Test hot CAS ổn định

Hai writers đọc cùng CAS c1; A ghi thành công, B ghi bằng CAS c1 phải báo mismatch. Khi retry, B đọc lại và xác minh business invariant. Tránh dựa vào `Thread.sleep(5)` để hy vọng tạo race.

## 49. Kiểm thử TTL của shards và dữ liệu đến muộn

Một test retention tốt:

- Tạo shard với expiry/hard deadline.
- Increment nhiều lần với `preserveExpiry(true)`.
- Đọc metadata expiry trước/sau.
- Assert deadline không tự kéo dài ngoài policy.
- Sau expiry, kiểm tra handling missing shard.
- Gửi event trễ qua ranh giới giờ/ngày và kiểm tra routing.
- Xác minh data cần archive được giữ đúng retention.

Không gộp TTL counter, session và order history vào một policy nếu vòng đời khác nhau.

## 50. Rollout từ một hot counter sang shards

Quy trình đề xuất:

1. **Baseline:** đo per-key write rate, p99, CAS/errors và correctness.
2. **Thiết kế:** chọn N shards, hash/routing, retention và summary reads.
3. **Test:** phân bố uniform/skew, idempotency, read amplification, TTL.
4. **Compatibility:** tính toán dual-write/backfill nếu phải giữ dữ liệu cũ.
5. **Đối soát:** so old/new totals trong cửa sổ có kiểm soát.
6. **Cutover:** chuyển đường đọc, có feature flag/rollback.
7. **Quan sát:** write goodput, per-shard skew và p99 của summary read.
8. **Thu hồi:** chỉ bỏ old key khi không còn phụ thuộc và retention hợp lệ.

Dual-write hai documents **không tự atomic**; nếu cần một lần cập nhật logic chỉ được tính một lần, phải thiết kế reconciliation/idempotency.

## 51. Ma trận quyết định thực dụng

| Vấn đề | Tối ưu xem xét | Đánh đổi |
| --- | --- | --- |
| GET JSON lớn chỉ cần status | `lookupIn`, tách summary | Path schema, nhiều docs |
| SQL++ list `SELECT *` | Projection/covering index | Index footprint |
| Array audit dài vô hạn | Event documents/time buckets | Query, retention, atomicity |
| Hot counter | Atomic increment/shards | Idempotency, sum reads |
| Read-hot product | Cache/single-flight | Staleness/auth/memory |
| Write-hot order | Giảm writes, CAS/backoff, split state hợp lý | Business invariants |
| Một Data node quá tải | Kiểm tra placement/skew/health | Capacity/rebalance |
| Tenant noisy neighbor | Rate limits/resource isolation | Fairness, vận hành |
| Fan-out sau split | LIMIT/projection, concurrency cap | Error semantics |
| SQL++ report nặng | Index/pre-aggregate/cache | Freshness |
| Transaction hot inventory | Reservation/data-model redesign | Atomicity |
| Stale replica read | Đúng consistency API | Latency/availability |

Không có một “nút tăng hiệu năng” chung. Bắt đầu từ **bottleneck được đo**.

## 52. Bài tập tình huống

Ứng dụng thương mại điện tử có:

~~~text
commerce.sales.orders            # document lớn dần
commerce.sales.order_events      # audit records
commerce.metrics.counters        # daily totals
commerce.checkout.carts          # TTL
commerce.inventory.stock         # hot SKU
~~~

**Câu hỏi:**

1. API list chỉ cần `status`/`total`, nhưng entity chứa 500 items. Vì sao DTO sau `findById` chưa đủ để giảm KV payload?
2. Khi nào chọn `lookupIn`, khi nào SQL++ projection?
3. Vì sao tiền tố `order::` không tự khiến mọi orders cùng vBucket?
4. Một key nhận 5.000 writes/s; thêm Data nodes có chắc tăng capacity cho đúng key đó?
5. Phân biệt read-hot và CAS-hot bằng metrics nào?
6. Tại sao `MutateInSpec.increment` giảm lost update nhưng chưa chữa hot counter?
7. Thiết kế 32 shards cho pageviews và giải thích chi phí đọc tổng.
8. Vì sao hash theo userId vẫn skew nếu một user tạo phần lớn traffic?
9. Nếu increment timeout sau khi server đã ghi, retry ngay gây rủi ro gì?
10. Split order summary/event thay đổi atomicity ra sao?
11. Thiết kế TTL cố định cho time-bucket shards.
12. SQL++ report chậm nhưng body nhỏ: xem operator/metrics nào?
13. Vì sao cache stampede tạo hot read burst?
14. WebFlux đọc 20 detail IDs: giới hạn concurrency ở đâu?
15. Một tenant chiếm 70% Query CPU: thiết kế isolation và đo thế nào?
16. Vì sao `collectList()` trên Flux nhiều rows vẫn có thể OOM?
17. Khi nào giữ nguyên một large document để bảo vệ invariant?
18. Per-node p99 cao nhưng average cluster CPU thấp, cần kiểm tra gì?
19. Thiết kế bốn benchmark để tách size khỏi skew.
20. Nếu sharding giảm write p99 nhưng mất strong total snapshot, đây có phải tối ưu hợp lệ không?

**Định hướng:** phân loại document size, key popularity và node skew; chọn projection, subdocument, split, cache, shards hoặc topology tuning; test CAS/TTL/idempotency/authorization và so goodput, p99, bytes, resource costs.

## 53. Checklist production

- [ ] Đã đo phân bố document sizes, không chỉ average.
- [ ] Có HTTP/SDK/Query p50/p95/p99 theo workload và outcome.
- [ ] Có goodput, error/timeout, CAS conflict và retry rates.
- [ ] Phân biệt logical JSON, HTTP và wire bytes.
- [ ] Đã tách large document, hot key và cluster/node skew trong chẩn đoán.
- [ ] Đúng bucket/scope/collection và document ID.
- [ ] Không suy prefix giống nhau đồng nghĩa chung vBucket.
- [ ] Không coi thêm node là giải pháp chắc chắn cho single-key bottleneck.
- [ ] Không đưa document ID/user ID/PII vào high-cardinality metric tags.
- [ ] Có per-node Data metrics và Query/Index resource monitoring.
- [ ] Không tải full entity nếu endpoint chỉ cần một vài fields mà không có lý do.
- [ ] `lookupIn` được test path/type và benchmark với GET.
- [ ] `mutateIn` giữ CAS/TTL/validation theo business contract.
- [ ] SDK raw patch không phá Spring Data `@Field`/converter/`@Version`.
- [ ] Unbounded arrays/audit events được đánh giá để split/retention.
- [ ] Sau split, N+1 fan-out và request graph được đo.
- [ ] Transaction/outbox được thêm khi split phá atomic invariant.
- [ ] Counter increment có retry/idempotency policy rõ.
- [ ] Shard hash input phân bố được đo, không giả định.
- [ ] Counter aggregation có freshness/snapshot contract.
- [ ] Resize shard/time-bucket có migration/late-event policy.
- [ ] Cache hit/miss, stampede, TTL/invalidation và auth được kiểm soát.
- [ ] Session/OTP cache không vượt deadline/revocation.
- [ ] Noisy tenants có fairness/resource controls.
- [ ] SQL++ có EXPLAIN/index/projection phù hợp.
- [ ] Reactive concurrency có cap per-request và toàn fleet.
- [ ] Không block WebFlux event loop hay materialize stream vô hạn.
- [ ] Durability/replica semantics phù hợp failure model.
- [ ] TTL/maxTTL/expiry metadata được test sau mutation/migration.
- [ ] Driver đủ capacity và load model không che coordinated omission.
- [ ] Benchmark ma trận size × skew × read/write mix, nhiều load steps.
- [ ] Có uniform-large và skew-small để phân rã nguyên nhân.
- [ ] Rebalance/failover test ở môi trường riêng an toàn.
- [ ] Migration/sharding rollout có đối soát và rollback.
- [ ] Không tối ưu bằng cách bỏ tenant checks, CAS hoặc transaction.
- [ ] Kết luận dựa trên correctness + p99 + goodput + tài nguyên.

## 54. Tổng kết

Hệ thống **Spring Data Couchbase** có thể chậm vì **document quá rộng**, vì **một số key nhận tần suất đọc/ghi rất cao**, hoặc vì **traffic lệch trên một nhóm vBuckets/nodes**. Ba vấn đề có thể đi cùng nhau, nhưng cần đo và xử lý riêng.

Với document lớn, kiểm tra full entity mapping và chuyển sang `lookupIn`, SQL++ projection, bounded summary/detail/event documents khi phù hợp. Với hot writes, xem CAS conflicts, retries, `mutateIn`, atomic counters, sharding và time buckets; với read-hot keys, cân nhắc cache/single-flight chỉ khi freshness cho phép. Khi node load lệch, xem key popularity, placement, noisy neighbors và hạ tầng trước khi chỉ tăng node count.

**Tối ưu đáng tin phải chứng minh bằng p50/p95/p99, goodput, bytes, GC, per-node metrics, CAS conflicts và correctness tests.** Không đánh đổi tenant authorization, TTL, durability hoặc transaction để đạt một con số đẹp. Mục tiêu là giảm công việc thừa và phân tán tải hợp lý **mà vẫn giữ đúng hợp đồng nghiệp vụ**.


