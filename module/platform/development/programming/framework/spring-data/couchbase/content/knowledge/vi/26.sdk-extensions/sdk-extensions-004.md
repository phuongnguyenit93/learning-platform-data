# Đọc từ bản sao và đánh đổi về độ mới dữ liệu

Trong **Spring Data Couchbase**, thao tác tìm entity theo document key thông thường ưu tiên truy cập bản **active** của document. Couchbase còn có thể lưu các bản **replica** để tăng khả năng chịu lỗi và phục vụ một số kiểu đọc khi cần ưu tiên tính khả dụng hoặc độ trễ. Couchbase Java SDK cung cấp các lệnh như `getAnyReplica(...)` và `getAllReplicas(...)` để truy cập dữ liệu theo hướng đó.

Lợi ích có thể rất rõ khi active node phản hồi chậm hoặc có vấn đề. Nhưng **bản trả về nhanh nhất không nhất thiết là bản mới nhất**. Replica có thể đang trễ so với active; hai lần đọc cùng một key có thể nhận những phiên bản khác nhau; một bản đã xóa hoặc vừa được sửa cũng có thể xuất hiện khác nhau tùy thời điểm truyền mutation.

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: phát triển tầng truy cập bằng document mapping, Repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để đạt hiệu năng, tính nhất quán và khả năng vận hành.

Mục tiêu là biết **khi nào có thể đánh đổi độ mới để lấy tính khả dụng/độ trễ**, cách triển khai SDK adapter rõ ràng, và trường hợp nào **không nên** dùng replica read.

## 1. Sau bài học, bạn làm được gì?

1. Phân biệt active vBucket, replica vBucket, KV read và query qua Index/Query Service.
2. Gọi `Collection.get(...)`, `getAnyReplica(...)` và `getAllReplicas(...)` với hợp đồng đúng.
3. Hiểu `getAnyReplica` trả **active hoặc replica**, không hứa luôn truy cập replica và không hứa mới nhất.
4. Đọc `GetReplicaResult.isReplica()`, `cas()`, nội dung JSON để phân tích độ trễ sao chép.
5. Nhận ra `getAllReplicas` là best-effort, các lỗi riêng lẻ có thể bị bỏ qua và kết quả không mặc nhiên đủ một quorum.
6. Đánh giá read-after-write, delete/TTL, cập nhật quyền, giá, tồn kho và dữ liệu nhạy cảm.
7. Phân biệt **durability khi ghi** với **freshness/consistency khi đọc**.
8. Không đánh đồng `REQUEST_PLUS` của SQL++ với lựa chọn đọc bản sao của KV.
9. Dùng Spring-managed `Cluster` và `Collection` cho SDK sync/reactive; giới hạn SDK trong adapter.
10. Viết integration tests và đo `stale read rate`, latency, availability theo workload và topology.

> **Nguyên tắc:** Dùng `get(...)` vào active khi nghiệp vụ cần đọc trạng thái hiện hành. Cân nhắc `getAnyReplica(...)` khi dữ liệu **chấp nhận cũ** và tăng khả dụng là quan trọng. Dùng `getAllReplicas(...)` khi **cần quan sát các bản sao** hoặc có thuật toán đối chiếu rõ, không coi nó là phép “chọn đúng dữ liệu” tự động.

## 2. Bức tranh phân mảnh và bản sao

Couchbase phân phối document vào các **vBucket** dựa trên document key. Với mỗi vBucket, có một bản **active** và có thể có một số bản **replica** theo cấu hình bucket.

~~~text
Cluster Couchbase
  |
  +-- Node A: active vBucket cho customer::42
  |       body: { "displayName": "Minh mới", "revision": 12 }
  |
  +-- Node B: replica cùng vBucket
  |       body: { "displayName": "Minh", "revision": 11 }
  |
  +-- Node C: replica cùng vBucket
          body: { "displayName": "Minh mới", "revision": 12 }
~~~

Ví dụ trên minh họa **trạng thái trễ tạm thời**, không phải một cấu hình bắt buộc. Giá trị `revision` là field nghiệp vụ tự đặt để quan sát; Couchbase không tự tạo field JSON có tên đó.

Những điểm cần ghi nhớ:

- Active là nơi xử lý đường ghi thông thường cho vBucket đang sở hữu key.
- Replica nhận các mutation theo cơ chế sao chép của Data Service.
- Replica không phải một collection khác với key riêng do application tự chọn.
- Số replica, vị trí node, server groups, rebalancing và failover là **cấu hình/topology của cluster**, không phải thuộc tính của `@Document`.
- Replica trong cùng Couchbase cluster khác với **XDCR giữa các datacenter/clusters**.
- Index replicas của Index Service cũng không đồng nghĩa với KV replicas của Data Service.

Document `customer::42` vẫn được định danh bởi bộ `bucket/scope/collection + document key`. SDK lựa chọn nguồn đọc dựa trên định tuyến và API đọc.

## 3. Khi đọc một key, có những lựa chọn nào?

| API Java SDK | Phạm vi bản đọc | Kiểu kết quả sync | Tư duy sử dụng |
| --- | --- | --- | --- |
| `collection.get(id)` | Active của key | `GetResult` | Mặc định khi cần dữ liệu hiện hành hơn |
| `collection.getAnyReplica(id)` | Active và các replica khả dụng, nhận bản thành công đầu tiên | `GetReplicaResult` | Đọc ưu tiên khả dụng/độ trễ; có thể cũ |
| `collection.getAllReplicas(id)` | Yêu cầu các bản khả dụng gồm active, replica | `Stream<GetReplicaResult>` | Quan sát/đối chiếu; best-effort |
| `collection.reactive().getAnyReplica(id)` | Cùng mô hình nhưng non-blocking | `Mono<GetReplicaResult>` | WebFlux/reactive |
| `collection.reactive().getAllReplicas(id)` | Cùng mô hình nhưng non-blocking | `Flux<GetReplicaResult>` | Theo dõi nhiều kết quả |

Các chữ ký ở đây theo hướng **Couchbase Java SDK 3.x**. Kiểm tra API thực tế theo dependency được khóa trong dự án.

Một sai lầm phổ biến là hiểu tên `getAnyReplica` thành “luôn đọc từ replica để giảm tải active”. Theo SDK, phương thức này có thể trả **active hoặc replica**: bản nào trả thành công trước có thể thắng.

## 4. Ví dụ dữ liệu: read-after-write có thể đọc bản cũ

Giả sử ứng dụng quản lý hồ sơ khách hàng:

~~~json
{
  "tenantId": "tenant-01",
  "display_name": "Minh",
  "revision": 11,
  "updatedAt": "2026-11-25T02:00:00.000Z"
}
~~~

Tại T1, Spring Data Repository hoặc SDK cập nhật tên thành `Minh mới`, revision thành 12.

~~~text
T0    Active = revision 11       Replica = revision 11
T1    Active nhận mutation 12    Replica vẫn có revision 11
T2    Ghi được xác nhận theo durability của thao tác
T3    getAnyReplica(id) có thể nhận kết quả từ Replica 11
T4    Replica bắt kịp revision 12
~~~

Từng thời điểm phụ thuộc cấu hình durability, số replica và đường mạng; sơ đồ chỉ diễn tả khả năng replica lag khi không có ràng buộc đồng bộ phù hợp.

Nếu người dùng vừa bấm “Đổi tên” rồi reload hồ sơ bằng replica read, UI **có thể hiện tên cũ**, khiến họ nghĩ thao tác lưu thất bại. Đây là lỗi **hợp đồng trải nghiệm đọc sau ghi**, không phải nhất thiết do write bị mất.

### Điều quan trọng hơn độ trễ trung bình

Một số use case có thể chịu được dữ liệu cũ khoảng vài trăm mili-giây, nhưng không chịu được trường hợp:

- Vừa **thu hồi quyền**, replica vẫn trả bản `permission=true`.
- Vừa cập nhật **giá/tồn kho**, replica trả giá trước đó.
- Vừa khóa tài khoản, replica vẫn báo `active=true`.
- Vừa hết hạn credential, một trạng thái cũ tiếp tục được dùng để cho phép thao tác.

Với những dữ liệu **được dùng để ra quyết định có tác động**, hãy ưu tiên nguồn đọc/mức nhất quán thích hợp, không chọn bản trả nhanh nhất chỉ vì p50 latency đẹp.

## 5. Đọc active bằng `get(...)`

Đây là đường KV đọc thường dùng:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;

public String readDisplayNameFromActive(
        Collection customers, String id) {

    GetResult result = customers.get(id);
    return result.contentAsObject()
            .getString("display_name");
}
~~~

`Collection.get` đọc theo document key, không cần secondary index như một SQL++ query theo `WHERE`.

Ưu điểm:

- Thường phản ánh trạng thái active hơn replica đang trễ.
- Là lựa chọn khởi đầu cho read-after-write, đọc trước ghi có CAS, trạng thái quyền và dữ liệu cần quyết định.
- Có `GetResult.cas()` để dùng làm expected CAS nếu thực hiện một mutation có điều kiện sau đó.

Nhưng không nên nói `get` tự tạo **snapshot xuyên nhiều document** hoặc mọi request: hai `get` liên tiếp vẫn có thể đọc các phiên bản khác nhau nếu writer khác cập nhật giữa chúng. Active read cũng có thể timeout hay lỗi khi node/topology gặp vấn đề.

## 6. `getAnyReplica(...)` trả bản thành công đầu tiên

Đọc dữ liệu chấp nhận cũ:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetReplicaResult;

public record CustomerPreview(
        String displayName,
        boolean fromReplica) {}

public CustomerPreview readPreview(
        Collection customers, String id) {

    GetReplicaResult result =
            customers.getAnyReplica(id);

    return new CustomerPreview(
            result.contentAsObject().getString("display_name"),
            result.isReplica());
}
~~~

`GetReplicaResult` là một lớp kết quả có các thao tác đọc nội dung tương tự `GetResult`, cộng thêm:

- `isReplica()`: kết quả đến từ replica hay active.
- `cas()`: CAS của **phiên bản được đọc**.
- `contentAsObject()` hoặc bộ transcoder thích hợp cho body.

### Điều `getAnyReplica` không hứa

- Không bảo đảm đọc replica; active cũng có thể thắng cuộc đua.
- Không bảo đảm body mới nhất ở active.
- Không bảo đảm sẽ nhanh hơn `get` ở mọi tải/topology.
- Không làm request mới tự ưu tiên đúng replica được đọc ở lần trước.
- Không bảo đảm có kết quả nếu mọi bản đều lỗi hoặc key không tìm được.
- Không chọn bản có CAS “lớn nhất”.

Trong đường blocking, khi không có bản thành công để trả, API có thể ném `DocumentUnretrievableException`, thay vì giả định mọi thất bại đều là `DocumentNotFoundException`. Phải phân biệt **không tìm được bản có thể đọc**, **key thực sự không tồn tại** và **mạng/cluster có vấn đề** theo ngữ nghĩa lỗi cụ thể.

## 7. `getAllReplicas(...)` để quan sát nhiều bản

Khi cần xem những phiên bản mà SDK lấy được:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetReplicaResult;
import java.util.List;
import java.util.stream.Stream;

public record ReplicaObservation(
        boolean fromReplica,
        long cas,
        Long revision,
        String displayName) {}

public List<ReplicaObservation> inspectCopies(
        Collection customers, String id) {

    try (Stream<GetReplicaResult> results =
                 customers.getAllReplicas(id)) {

        return results
                .map(result -> new ReplicaObservation(
                        result.isReplica(),
                        result.cas(),
                        result.contentAsObject().getLong("revision"),
                        result.contentAsObject().getString("display_name")))
                .toList();
    }
}
~~~

Ý nghĩa:

- `getAllReplicas` có thể phát nhiều kết quả từ **active và các replica khả dụng**.
- `isReplica()` giúp phân loại nguồn.
- `revision` là **field nghiệp vụ để minh họa**, không phải thứ tự do SDK tự cấp.
- `cas()` là token phiên bản để phát hiện thay đổi trong thao tác ghi có điều kiện, **không phải đồng hồ toàn cục hoặc chỉ số thứ tự để tự chọn bản mới nhất**.

### “All” vẫn là best-effort

SDK ghi rõ các lỗi riêng lẻ có thể bị bỏ qua. Vì vậy:

1. Danh sách trả về **có thể thiếu** một số bản khi lỗi/mạng/timeout.
2. Kết quả rỗng hoặc thiếu bản **không chứng minh document đã bị xóa**.
3. Số phần tử có thể nhỏ hơn số bản active+replica dự kiến.
4. Thứ tự phát các kết quả **không phải thứ tự mới → cũ**.
5. Không dùng “đa số các bản trả về giống nhau” như một quorum-read protocol tự xây.
6. Đọc tất cả có thể tốn thêm network requests, payload và CPU decode.

Phù hợp cho **diagnostics, quan sát sự lệch tạm thời, một số mô hình đọc ưu tiên availability**. Nếu mục tiêu chỉ là trả một preview, `getAnyReplica` thường ít phức tạp hơn.

## 8. `isReplica()` và CAS không tạo freshness guarantee

Giả sử kết quả:

| Nguồn | `isReplica()` | `revision` nghiệp vụ | `cas()` |
| --- | --- | ---: | --- |
| Active | false | 12 | opaque-token-A |
| Replica 1 | true | 11 | opaque-token-B |
| Replica 2 | true | 12 | opaque-token-C |

Bảng này cố ý ghi CAS bằng chuỗi tượng trưng. Trong Java, `cas()` là `long`; ý nghĩa của nó là **opaque version token**, không phải số đếm tăng đều theo thứ tự thời gian.

Đừng viết:

~~~java
// KHÔNG DÙNG: CAS không được định nghĩa là timestamp/sequence để sắp.
GetReplicaResult newest = results.stream()
        .max(Comparator.comparingLong(GetReplicaResult::cas))
        .orElseThrow();
~~~

Nếu ứng dụng duy trì một `revision` đáng tin cậy, có thể **quan sát độ lệch** theo revision. Nhưng ngay cả khi các bản đều có revision 12:

- Chúng có thể được đọc **ở các thời điểm khác nhau**.
- Không tự tạo snapshot nhiều document.
- Không nói gì về các mutation **đang diễn ra** sau thời điểm lấy từng bản.
- Revision do writer quản lý phải tăng đúng; nếu một writer bỏ qua nó, logic so sánh mất ý nghĩa.

### CAS của replica để ghi tiếp?

CAS lấy từ một replica có thể đã cũ. Nếu dùng nó làm expected CAS cho replace trên active, mutation có thể bị từ chối do CAS mismatch. Để tạo luồng optimistic locking đáng tin cậy, nên **đọc active** rồi ghi kèm CAS mới, xử lý conflict theo nghiệp vụ.

## 9. Chính sách chọn đường đọc theo từng use case

| Nhu cầu | Chọn ban đầu | Vì sao |
| --- | --- | --- |
| Xem preview tên hiển thị có thể cũ ít lâu | `getAnyReplica` có thể phù hợp | Ưu tiên có kết quả khi một bản chậm |
| Feed thông tin sản phẩm chỉ để tham khảo | Có thể cân nhắc replica read | Phải gắn nhãn/chính sách stale được chấp nhận |
| Đọc hồ sơ ngay sau khi vừa cập nhật | `get` active | Tránh “đọc lại tên cũ” |
| Kiểm tra quyền/thu hồi quyền | Nguồn có chính sách consistency chặt | Stale authorization không an toàn |
| Giá tiền tại bước thanh toán | Active + kiểm tra giá tại điểm commit | Không dùng preview stale làm giá cuối |
| Kiểm tra tồn kho trước trừ hàng | Conditional mutation/transaction | Replica read không giữ bất biến |
| Quyết định cấp quota | CAS/transaction/invariant design | Get replica là read-only và có thể cũ |
| Dashboard đếm gần realtime | Aggregate/materialized view phù hợp | Không coi replica read của một key là snapshot |
| Kiểm tra active/replica lệch nhau | `getAllReplicas` | Quan sát, không tự suy ra quorum |
| Xuất báo cáo theo trạng thái T0 | Snapshot/versioned export riêng | Một loạt replica reads không tạo snapshot |

**Freshness là yêu cầu nghiệp vụ**, không phải một cờ tối ưu hiệu năng dùng đại trà. Một ứng dụng có thể dùng active cho checkout và replica cho preview trên **cùng collection**.

## 10. Spring-managed Cluster, Bucket và Collection

Bài thuộc phần **Mở rộng bằng SDK**, nên adapter phải dùng cùng hạ tầng với Spring Data:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import org.springframework.stereotype.Component;

@Component
public final class CustomerReplicaReader {

    private final Collection customers;

    public CustomerReplicaReader(Cluster cluster) {
        this.customers = cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
    }

    public CustomerPreview preview(String id) {
        var result = customers.getAnyReplica(id);
        return new CustomerPreview(
                result.contentAsObject().getString("display_name"),
                result.isReplica());
    }
}
~~~

`Cluster` do Spring Boot/Spring Data hoặc cấu hình dự án quản lý. Đừng tạo `Cluster.connect(...)` mỗi request và đừng gọi `cluster.disconnect()` trong adapter. Những handle `Bucket`/`Scope`/`Collection` có thể được giữ lâu dài.

**Cùng Cluster chưa đủ.** Phải chọn đúng cả `bucket/scope/collection`. Entity có thể gắn `@Scope("crm")` và `@Collection("customers")`, trong khi SDK `bucket.defaultCollection()` lại trỏ tới một keyspace khác.

### Không mất quy ước mapping

Nếu entity Spring Data có:

~~~java
@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;
}
~~~

thì SDK raw `contentAsObject().getString("display_name")` đọc tên field **đã lưu**. Nó không tự chạy `CouchbaseConverter` hoặc xử lý `@Field` cho property `displayName`.

Hãy trả **DTO/read model** từ replica adapter, không đưa raw partial body vào `repository.save(...)` như một entity đầy đủ.

## 11. Ranh giới giữa Repository, Template và SDK

Trong ứng dụng Spring Data Couchbase:

- `CouchbaseRepository.findById(id)` phục vụ truy cập entity thông thường theo hợp đồng Repository.
- `CouchbaseTemplate` cho thêm khả năng kiểm soát thao tác và mapping khi cần.
- SDK `Collection.get(...)` đọc KV active tường minh.
- SDK `Collection.getAnyReplica(...)` và `getAllReplicas(...)` là các API replica-aware rõ ràng.

Không nên khẳng định “Repository tuyệt đối không thể làm việc với replica” cho mọi phiên bản hoặc mọi extension. Tuy nhiên, nếu tầng abstraction hiện tại **không cung cấp replica reads với hợp đồng rõ**, viết một SDK adapter là phương án minh bạch.

Đừng tự gọi `getAnyReplica` từ mọi Repository method chỉ để có vẻ “tăng HA”. Điều đó thay đổi **semantics đọc**, cần quyết định từ yêu cầu sản phẩm.

### Port thể hiện intent

~~~java
public interface CustomerReadPort {

    CustomerPreview readPossiblyStalePreview(String id);

    CustomerSnapshot readAuthoritative(String id);
}
~~~

Ví dụ:

~~~java
public record CustomerSnapshot(
        String displayName,
        long cas) {}

public CustomerSnapshot readAuthoritative(String id) {
    var result = customers.get(id);
    return new CustomerSnapshot(
            result.contentAsObject().getString("display_name"),
            result.cas());
}
~~~

Tên method như `readPossiblyStalePreview` giúp người gọi **không nhầm** đây là bản mới nhất. Nếu không cần CAS ở consumer, đừng đưa token này vào API công khai chỉ để “có thêm metadata”.

## 12. Phân biệt replica read với replica index và SQL++

Một SQL++ query ví dụ:

~~~sql
SELECT META(c).id AS id,
       c.display_name AS displayName
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
ORDER BY c.display_name ASC, META(c).id ASC
LIMIT $limit;
~~~

Truy vấn này **không phải** `getAnyReplica`. Nó đi qua Query Service và thường dùng index phù hợp để lọc/sắp xếp row, thay vì KV read theo một key biết trước.

**Đừng đánh đồng** các khái niệm:

| Khái niệm | Phục vụ việc gì? |
| --- | --- |
| KV active/replica | Chọn bản document theo key ở Data Service |
| Secondary index | Tìm document/row theo predicate SQL++ |
| Index replica | Tăng khả dụng của hệ thống index theo cấu hình |
| SQL++ scan consistency | Kiểm soát mức mới của index mà query chờ/nhìn |
| XDCR | Sao chép giữa deployments/datacenters |
| Transaction | Giữ bất biến nhiều thao tác theo phạm vi hỗ trợ |

Một SDK query `Cluster.query(...)` không tự chạy trên KV replica chỉ vì cùng `Cluster` với `Collection.getAnyReplica(...)`.

## 13. `REQUEST_PLUS` không phải replica freshness switch

Trong SDK Java, có thể yêu cầu SQL++ chờ index:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

var options = queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
~~~

`REQUEST_PLUS` chủ yếu liên quan **index scan consistency** của một query SQL++: Query Service đợi các index đáp ứng trạng thái mutation theo semantics của lựa chọn đó, có thể tăng độ trễ.

Nó **không**:

- Biến `getAnyReplica(...)` thành một active read.
- Bắt tất cả KV replicas đồng bộ tại thời điểm một HTTP request.
- Cấp snapshot chung xuyên nhiều request phân trang.
- Tạo transaction hoặc ngăn writer sửa dữ liệu sau đó.

`NOT_BOUNDED` cũng là lựa chọn cho SQL++ về việc không chờ index bắt kịp. Đừng dùng các tên consistency của query như một giải pháp cho replica KV lag; đó là hai đường khác nhau.

## 14. Durability lúc ghi ảnh hưởng cửa sổ stale thế nào?

Mutation thông thường được xử lý trên active rồi sao chép tới các replica. Couchbase hỗ trợ **durable writes** với các mức:

- `DurabilityLevel.MAJORITY`.
- `DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE`.
- `DurabilityLevel.PERSIST_TO_MAJORITY`.

Ví dụ SDK:

~~~java
import com.couchbase.client.java.durability.DurabilityLevel;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

customers.upsert(
        "customer::42",
        body,
        upsertOptions().durability(DurabilityLevel.MAJORITY));
~~~

Durability xác định **mức xác nhận replication/persistence mà một mutation phải đạt** trước khi báo thành công, tùy topology và ngữ nghĩa Server. Nó có thể làm giảm một số tình huống replica trễ tại thời điểm ghi hoàn tất, nhưng:

1. Không mặc nhiên buộc **mọi** replica có phiên bản mới nhất.
2. Với nhiều replica, một mức majority có thể chưa bao gồm replica mà `getAnyReplica` đọc.
3. Ngay sau lần ghi đó có thể xuất hiện **mutation mới**, nên bản trả về vẫn có thể kém mới.
4. Không áp dụng một mức durability trên request ghi rồi suy ra tất cả các đường đọc ở bất kỳ thời điểm nào đều linearizable.
5. Durability tăng chi phí latency/throughput, cần đo theo workload.

Couchbase có hướng dẫn riêng về mức durability và trường hợp đọc replica theo preferred server group. Những bảo đảm theo số replica và topology phải được kiểm chứng **cho đúng Server/SDK và cấu hình bucket**, không khái quát từ một mức `MAJORITY` đơn lẻ.

## 15. Replica read, tính khả dụng và failover

Khi active node chậm hoặc mất kết nối, việc có replica có thể hỗ trợ **đọc được một bản** nhanh hơn thay vì chờ active.

~~~text
Client ── get(id) ──────> Active chậm / không phản hồi
Client ── getAnyReplica(id) ──> Active + các replica
                                    |
                                    +-- một bản thành công đầu tiên
~~~

Nhưng lưu ý:

- `getAnyReplica` không phải cơ chế **failover promotion**; SDK/cluster xử lý topology và failover theo quy trình riêng.
- Không hứa mọi lỗi active đều được replica cứu, vì bản sao cũng có thể lỗi, không có bản tồn tại hoặc topology chưa ổn định.
- Nếu bucket cấu hình **0 replica**, không có các bản sao phụ để tăng lựa chọn đọc.
- Rebalance, failover và topology update làm vị trí active/replica thay đổi; `isReplica()` mô tả nguồn **của lần đọc đó**.
- Read availability tăng có thể đi kèm freshness giảm. Đó là sự đánh đổi thiết kế, không phải lỗi SDK.

Khi failover vừa xảy ra, cần kiểm thử cả việc client định tuyến lại, dữ liệu được xác nhận theo durability, và thời gian service trở về trạng thái có thể phục vụ.

## 16. Delete và TTL: bản đã biến mất vẫn có thể gây nhầm

Hai kịch bản cần thận trọng:

### Vừa xóa document

~~~text
T0 Active và Replica đều có customer::42
T1 Active xử lý delete customer::42
T2 Một replica có thể chưa phản ánh delete
T3 Replica read có khả năng thấy bản cũ
~~~

Nếu UI chỉ hiển thị preview, lỗi này có thể chấp nhận trong một cửa sổ ngắn. Nhưng nếu user vừa xóa token truy cập/quyền truy cập, đọc replica cũ để xác thực lại là không an toàn.

### Document có TTL

TTL làm document hết hạn theo chính sách của Couchbase. Các bản sao và việc quan sát expiry/delete có thể không xuất hiện hoàn toàn đồng thời trong mọi tình huống. Không coi một replica read trả body là bằng chứng token/session vẫn còn hiệu lực theo chính sách hiện hành.

Hãy thực hiện kiểm tra authorization, expiry và invariant ở đường **được thiết kế cho tính đúng**, thay vì dùng replica preview làm nguồn quyết định.

**Không mặc định:** “Replica còn document” nghĩa là “document vẫn còn hợp lệ”, hoặc “một replica báo not found” nghĩa là “mọi bản đều đã xóa”.

## 17. Đọc nhiều bản không tạo consensus đúng nghĩa

Một người có thể muốn:

~~~text
Đọc active + 2 replicas
Nếu 2 trên 3 bản trả tên "Minh" thì trả "Minh"
~~~

Cách này có một số lỗ hổng:

1. `getAllReplicas` là **best-effort**; không đảm bảo tất cả bản trả kết quả.
2. Các bản được đọc **khác thời điểm**, không phải atomic snapshot.
3. Một bản thiếu có thể do lỗi đọc, không phải vote “document không có”.
4. Các mutation mới có thể đến ngay sau khi một bản được đọc.
5. CAS là opaque; “CAS lớn hơn” không phải tiêu chí mới hơn.
6. Một majority theo các bản đã phản hồi không tương đương quorum protocol được Server bảo đảm.
7. Đọc từ nhiều bản tăng network/CPU, có thể làm tải tăng lúc cluster đang suy giảm.

Nếu ứng dụng yêu cầu một read protocol mạnh hơn, cần một thiết kế được Couchbase Server/SDK hỗ trợ chính thức hoặc một transaction/invariant ở tầng thích hợp; không tự xây consensus bằng Java stream.

## 18. Đường đọc ưu tiên bản sao theo Server Group

Ở các phiên bản hỗ trợ, Couchbase cho phép cấu hình **server groups** và chọn `ReadPreference.PREFERRED_SERVER_GROUP` nhằm ưu tiên đọc từ nhóm máy chủ mong muốn, ví dụ node cùng availability zone để giảm chi phí mạng.

Điều kiện version cần đối chiếu:

- Java SDK **3.7.4 trở lên** cùng Couchbase Server **7.6.2 trở lên** theo tài liệu tính năng này.
- Cluster environment được cấu hình **preferred server group**.
- Server group và replica placement phải phù hợp; rebalance có thể cần thiết sau khi thay đổi bố trí.
- Read preference giúp **định tuyến ưu tiên**, không biến replica thành bản mới nhất.

Một ví dụ về hình dạng API:

~~~java
import com.couchbase.client.java.kv.ReadPreference;

import static com.couchbase.client.java.kv.GetAnyReplicaOptions
        .getAnyReplicaOptions;

var result = customers.getAnyReplica(
        "customer::42",
        getAnyReplicaOptions()
                .readPreference(ReadPreference.PREFERRED_SERVER_GROUP));
~~~

**Tiền đề:** preferred server group đã được cấu hình trong SDK environment. Nếu không có configuration phù hợp hoặc phiên bản Server/SDK chưa hỗ trợ, không sao chép ví dụ vào production rồi cho rằng sẽ tự đọc local zone.

Đặc biệt với dữ liệu nhất quán nhạy cảm, Couchbase lưu ý cần cân nhắc rất kỹ việc ưu tiên replica. Đừng dùng tối ưu cross-AZ cost làm lý do bỏ qua hợp đồng read-after-write.

## 19. Reactive `getAnyReplica`: không block event loop

Với Spring WebFlux, có thể lấy reactive collection từ `Collection` SDK do Spring-managed `Cluster` cung cấp:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetReplicaResult;
import reactor.core.publisher.Mono;

public Mono<CustomerPreview> previewReactive(
        Collection customers, String id) {

    return customers.reactive()
            .getAnyReplica(id)
            .map(result -> new CustomerPreview(
                    result.contentAsObject().getString("display_name"),
                    result.isReplica()))
            .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                            "No readable copy returned")));
}
~~~

Với Java SDK reactive, `getAnyReplica` có thể hoàn tất rỗng nếu các read requests không có kết quả thành công theo semantics SDK. Vì vậy **Mono.empty không tự đồng nghĩa document thực sự không tồn tại trên active**.

Không làm:

~~~java
// SAI: thao tác getAnyReplica blocking thực thi ngay.
Mono<CustomerPreview> bad = Mono.just(
        previewBlocking(customers, id));
~~~

hoặc:

~~~java
// SAI ở WebFlux event-loop: block() đổi reactive thành blocking.
CustomerPreview bad = previewReactive(customers, id).block();
~~~

Một ứng dụng non-blocking phải trả `Mono<CustomerPreview>` cho controller hoặc ghép với operator Reactor khác mà không `block()` ở event-loop.

## 20. Reactive `getAllReplicas` và giới hạn của `collectList()`

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetReplicaResult;
import reactor.core.publisher.Mono;

import java.util.List;

public Mono<List<ReplicaObservation>> inspectCopiesReactive(
        Collection customers, String id) {

    return customers.reactive()
            .getAllReplicas(id)
            .map(result -> new ReplicaObservation(
                    result.isReplica(),
                    result.cas(),
                    result.contentAsObject().getLong("revision"),
                    result.contentAsObject().getString("display_name")))
            .collectList();
}
~~~

Khác SQL++ query trả hàng triệu row, luồng `getAllReplicas` của **một key** thông thường được giới hạn bởi số bản active/replica theo topology. Vì vậy `collectList()` có quy mô nhỏ trong mô hình này.

Tuy nhiên:

- Không dùng `collectList()` như bằng chứng **tất cả replica đã phản hồi**.
- Nếu có nhiều key, `flatMap(id -> getAllReplicas(id))` có thể tạo nhiều thao tác đồng thời; cần giới hạn concurrency.
- Kết quả các bản có thể đến không theo thứ tự.
- Cần timeout, cancel behavior, metric và error handling rõ.
- Không thay một phép đọc active cần độ đúng bằng việc lấy tất cả rồi chọn ngẫu nhiên.

Với một trường hợp read availability, `getAnyReplica` thường phù hợp hơn `getAllReplicas` vì tránh tầng logic chọn bản phức tạp.

## 21. SDK read từ bản sao không tự dùng Spring converter

Một entity Spring Data:

~~~java
@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;

    private String tenantId;
}
~~~

SDK raw replica read:

~~~java
GetReplicaResult result = customers.getAnyReplica(id);

String rawName = result.contentAsObject()
        .getString("display_name");
~~~

Lệnh SDK **không tự áp dụng** converter của Repository hoặc `CouchbaseTemplate`. Nó đọc body JSON trên bản đã trả.

Hệ quả:

- `@Field("display_name")` phải được phản ánh trong JSON path.
- `@Version`/CAS của entity không biến raw JSON thành entity hoàn chỉnh.
- Custom converter cho `Instant`, enum, value object có thể cần mapper riêng.
- Type discriminator do Spring Data lưu có thể cần lọc/kiểm tra khi collection dùng chung nhiều entity.
- Nếu DTO thiếu trường, không dùng nó để `repository.save(...)` nhằm cập nhật full document.

**Replica read nên là read-only path**. Khi cần sửa sau đọc, đọc active với CAS và thực hiện write có điều kiện, không coi dữ liệu replica cũ là bản được phép overwrite.

## 22. Multi-tenancy và authorization: đừng lấy quyết định từ dữ liệu cũ

Đây là lỗi thiết kế có hậu quả nghiêm trọng hơn việc hiện tên cũ.

Giả sử document:

~~~json
{
  "tenantId": "tenant-01",
  "canDownloadInvoice": true,
  "updatedAt": "2026-11-25T02:00:00Z"
}
~~~

Admin vừa thu hồi quyền tải hóa đơn, nhưng replica vẫn có `canDownloadInvoice=true`. Nếu service tin replica và phát hóa đơn, hệ thống có thể **vượt qua quyết định quyền mới nhất**.

Nguyên tắc:

1. Lấy tenant từ **principal/context xác thực**, không tin chỉ một field do client cung cấp.
2. Dùng nguồn authorization được thiết kế **phù hợp với mức consistency yêu cầu**.
3. Không dùng replica read cho quyết định thu hồi quyền, khóa tài khoản, giá cuối hoặc chuyển tiền nếu nghiệp vụ không chấp nhận stale.
4. KV read theo document key vẫn phải kiểm tra authorization; biết key không đồng nghĩa có quyền.
5. Server credentials/RBAC có thể đọc nhiều tenant; business layer phải lọc phạm vi.
6. Không log nguyên body, token hoặc PII vào hệ thống metrics khi đo replica lag.

**Một API nhanh hơn nhưng trả quyết định quyền cũ không phải tối ưu thành công.**

## 23. Fallback có điều kiện: preview stale khác authoritative read

Một chiến lược rõ ràng có thể tách hai method:

~~~java
public interface CustomerReader {

    CustomerPreview previewPossiblyStale(String id);

    CustomerSnapshot currentForUpdate(String id);
}
~~~

Implementation:

~~~java
@Override
public CustomerPreview previewPossiblyStale(String id) {
    GetReplicaResult r = customers.getAnyReplica(id);
    return new CustomerPreview(
            r.contentAsObject().getString("display_name"),
            r.isReplica());
}

@Override
public CustomerSnapshot currentForUpdate(String id) {
    GetResult r = customers.get(id);
    return new CustomerSnapshot(
            r.contentAsObject().getString("display_name"),
            r.cas());
}
~~~

Một cách khác là trước tiên thử `get(id)` rồi **fallback sang `getAnyReplica(id)` nếu lỗi loại cho phép**. Nhưng:

- Chỉ làm nếu sản phẩm **chấp nhận dữ liệu cũ**.
- Không fallback trên lỗi auth/RBAC hoặc validation.
- Không chuyển mọi `DocumentNotFoundException` thành replica read mà vô tình “hồi sinh” document đã xóa.
- Fallback làm request có thêm một lần đọc, có thể tăng latency khi cluster đang lỗi.
- Cần timeout budget và circuit breaker/failure policy phù hợp.

### Lỗi không thể đọc khác dữ liệu không tồn tại

Ví dụ active timeout nhưng replica còn bản cũ là tình huống khác với “không tìm thấy document trên hệ thống”. Phân biệt response:

- `200 OK` cho preview nếu stale được phép theo hợp đồng.
- `404 Not Found` chỉ khi ứng dụng có bằng chứng phù hợp key thực sự không tồn tại, theo chính sách.
- `503 Service Unavailable` hoặc lỗi tạm thời nếu không có nguồn đủ tin cậy để khẳng định trạng thái.

Không gán mọi `DocumentUnretrievableException` thành `404` chỉ vì tên chứa “document”.

## 24. Nên hiển thị trạng thái “stale” cho client không?

`GetReplicaResult.isReplica()` chỉ cho biết **nguồn đọc**, không xác nhận dữ liệu đã stale. Một replica có thể hoàn toàn bắt kịp active. Ngược lại active read cũng có thể cũ ngay sau đó khi writer mới cập nhật.

Vì vậy một response có thể đặt:

~~~json
{
  "customer": {
    "displayName": "Minh"
  },
  "readSource": "REPLICA",
  "freshnessGuarantee": "BEST_EFFORT"
}
~~~

Nhưng không nên đặt `stale=true` chỉ từ `isReplica()==true` rồi hiểu đó là một phép đo lag chính xác. Nếu muốn báo “as of” cần một timestamp/revision **được quản lý đúng bởi producer**, và quy định nó phản ánh mốc nào.

Một API có thể đơn giản hơn: document trong endpoint preview **có thể cũ**, còn endpoint edit/checkout luôn đọc trạng thái hiện hành trước commit. Bảo đảm về freshness phải được ghi trong hợp đồng service, không chỉ cất trong dashboard.

## 25. Cách đo replica lag không mắc bẫy CAS

Một cách thí nghiệm:

1. Ghi document revision=1 vào active.
2. Ghi revision=2,3,... tuần tự.
3. Sau mỗi mutation, đọc active bằng `get` và quan sát `getAnyReplica`/`getAllReplicas`.
4. Ghi `revision` của từng kết quả và `isReplica()`.
5. Đo thời gian cho đến khi mọi replica **quan sát được** revision mục tiêu trong một cửa sổ kiểm thử.
6. Lặp trên nhiều key/vBucket và cả lúc cluster chịu tải.

Quan trọng:

- `revision` phải được producer tăng nhất quán (đây là **field ứng dụng**).
- `cas()` là opaque, không dùng `max(cas)` để suy ra độ mới.
- `getAllReplicas` có thể thiếu bản vì best-effort; thiếu quan sát không đồng nghĩa lag vô hạn.
- Mutation mới có thể xen vào khiến kết luận “các bản bằng nhau” chỉ là điểm đo nhất thời.
- Nếu cần độ mới tối đa `N` giây, phải kiểm tra SLA bằng cách đo phân phối lag theo cấu hình và chấp nhận cơ chế fallback/refresh.

Đối với production metrics, hạn chế log PII; dùng key ID đã ẩn danh và revision/timestamp phù hợp.

## 26. Bảng thử nghiệm với write và read xen kẽ

Giả sử doc có `revision` và trạng thái:

| Thời điểm | Hành động | Active | Một replica | Khả năng `getAnyReplica` |
| --- | --- | --- | --- | --- |
| T0 | Đã đồng bộ | v1 | v1 | v1 |
| T1 | Ghi v2 không chờ mọi replica | v2 | v1 | v1 **hoặc** v2 |
| T2 | Replica bắt kịp | v2 | v2 | v2 |
| T3 | Ghi v3 | v3 | v2 | v2 **hoặc** v3 |
| T4 | Delete doc | Không còn | Có thể tạm còn v3 | Có thể khác tùy bản |
| T5 | Các bản phản ánh delete | Không còn | Không còn | Không lấy được bản body |

Bảng không phải cam kết thời gian/ordering của một cluster cụ thể. Nó chỉ giúp người học hình dung vì sao chọn kết quả đầu tiên có thể đổi trải nghiệm đọc.

### Điều kiện về durability

Nếu mutation yêu cầu mức durability cao, một số trạng thái trung gian có thể bị thay đổi hoặc không được quan sát theo cùng cách. Không áp bảng mô phỏng cho mọi cấu hình như thể nó là lịch trình xác định của Couchbase.

## 27. Hiệu năng: có thể nhanh hơn, cũng có thể tốn hơn

Replica read đôi khi giúp khi active chậm hoặc replica gần client hơn. Tuy nhiên số lượng request, xử lý và topology khác nhau.

Đo riêng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50/p95/p99 của `get` | Baseline active KV |
| p50/p95/p99 của `getAnyReplica` | Lợi ích/chi phí của race nhiều bản |
| p50/p95/p99 của `getAllReplicas` | Chi phí lấy nhiều bản |
| `isReplica()` ratio | Tỷ lệ bản replica thắng cuộc đua |
| Stale observation rate | Tỷ lệ revision trả thấp hơn mốc đối chứng theo thiết kế |
| Availability/error rate | Có bao nhiêu request nhận được bản khi active chậm |
| Bytes và SDK resource | Payload/network/CPU tăng khi đọc nhiều bản |
| Retry/timeout | Tác động khi một số node lỗi |
| Server-group/zone egress | Chi phí đọc xuyên vùng |
| Topology/failover recovery time | Thời gian dịch vụ ổn định lại |

Không khẳng định `getAnyReplica` luôn nhanh hơn `get` do nó có thể gửi nhiều yêu cầu và chịu contention/network khác nhau. `getAllReplicas` thường có tổng công việc nhiều hơn, không phải giải pháp mặc định để tối ưu endpoint.

### Không tối ưu bằng cách đổi sai ngữ nghĩa

Nếu endpoint phải đưa ra quyết định “có được chi tiền hay không”, một benchmark chỉ đo latency mà bỏ qua **stale decision rate** là thiếu. Hãy đưa yêu cầu đúng/sai vào tiêu chí chấp nhận, không đổi correctness lấy vài mili-giây mà không có phê duyệt nghiệp vụ.

## 28. Lỗi thường gặp và cách xử lý

| Nhầm lẫn | Vì sao sai? | Hướng đúng |
| --- | --- | --- |
| “`getAnyReplica` luôn đọc replica” | Active cũng có thể thắng | Xem `isReplica()` |
| “Bản trả đầu tiên mới nhất” | Replica có thể lag | Đánh đổi freshness rõ ràng |
| “`getAllReplicas` trả đủ mọi bản” | Best-effort, có thể bỏ qua lỗi từng bản | Dùng để quan sát, không suy ra quorum |
| “Chọn CAS lớn nhất là mới nhất” | CAS là opaque | Đừng dùng CAS làm timestamp |
| “Có `MAJORITY` thì mọi replica đều mới” | Majority không phải tất cả | Hiểu số replica/topology |
| “`REQUEST_PLUS` làm KV replica mới” | Nó là SQL++ scan consistency | Phân biệt Data/Index Service |
| “Replica read luôn tăng availability” | Có thể không có replica/đều lỗi | Test topology và failure modes |
| “Replica còn token nghĩa token hợp lệ” | Delete/TTL có thể chưa được nhìn thấy | Dùng nguồn authorization phù hợp |
| “Retry đến khi replica trả body” | Có thể đọc bản bị xóa | Phân loại lỗi và policy |
| “Repository dùng cùng Cluster nên tự map SDK raw” | SDK không chạy converter | Map DTO rõ, giữ field names |
| “`getAllReplicas` nhất quán như snapshot” | Bản được đọc khác thời điểm | Snapshot/transaction riêng |
| “Một replica chưa thấy update là write thất bại” | Có thể replication lag | Kiểm tra mutation acknowledgement và durability |
| “`isReplica` là chỉ số stale” | Source không phải độ mới | Đo revision/freshness riêng |
| “Server group preference là stronger consistency” | Là ưu tiên định tuyến | Chọn theo latency/zone và stale tolerance |
| “XDCR giống KV replica” | Khác lớp replication | Xác định đúng cluster boundary |

## 29. Integration test: trường hợp thành công

Một bộ test có chủ đích:

1. Seed một document vào `shop.crm.customers` với `revision=1`.
2. Xác nhận `customers.get(id)` đọc body và CAS.
3. Gọi `customers.getAnyReplica(id)`, xác minh `GetReplicaResult` có body hợp lệ, `isReplica()` là boolean nguồn.
4. Gọi `customers.getAllReplicas(id)`, ghi lại số bản đọc được; không khẳng định luôn bằng số cấu hình khi môi trường có lỗi.
5. Mutation lên revision=2, đo trong một cửa sổ có thể thấy bản revision=1.
6. Đợi hệ thống bắt kịp theo cách kiểm thử phù hợp, kiểm tra bản sao dần chuyển sang revision=2.
7. Thử đồng thời trên nhiều key nằm ở các vBuckets khác nhau.
8. Cần account cho số replica = 0, 1, 2... và topology thực tế; không viết test cứng chỉ chạy với đúng 2 replica.
9. Nếu dùng `@Field("display_name")`, xác nhận SDK đọc raw field đúng và Repository đọc lại entity đúng.
10. Test cả sync và reactive paths trên SDK/Spring Data versions đang dùng.

### Không tạo assertion phụ thuộc timing ngẫu nhiên

**Không nên** assert: “Ngay sau khi ghi, `getAnyReplica` chắc chắn trả v1.” Nó có thể trả active v2 hoặc replica đã bắt kịp.

Thay vào đó:

- Kiểm tra **bất biến được đảm bảo** của API.
- Ghi nhận stale occurrences như phép đo xác suất/độ trễ.
- Dùng cấu hình/network fault injection có kiểm soát khi test failover.
- Tránh ngủ cố định vài mili-giây rồi coi đó là chứng minh consistency.

## 30. Integration test: lỗi và bảo mật

### A. Active chậm / replica còn phản hồi

Thí nghiệm với môi trường có thể kiểm soát fault:

~~~text
Given active path bị chậm theo kịch bản test
When  get(id) và getAnyReplica(id)
Then  so latency/error rate
And   kiểm tra nguồn bản trả qua isReplica()
~~~

Không nhất thiết `getAnyReplica` luôn thành công; mục tiêu là **đo** mức khả dụng theo topology.

### B. Xóa và TTL

~~~text
Given document có TTL hoặc chuẩn bị bị xóa
When  đọc bằng getAnyReplica ngay trước/sau mutation
Then  theo dõi khác biệt quan sát
And   endpoint bảo mật không dùng kết quả stale làm quyết định
~~~

### C. Thay quyền

1. Tạo quyền `allowed=true`.
2. Thu hồi quyền bằng authoritative mutation.
3. Kiểm tra endpoint kiểm soát quyền **không** dựa vào replica preview.
4. Không cần ép SDK trả dữ liệu cũ để chứng minh policy; kiểm tra đường service được cấu hình đúng.

### D. Lỗi tất cả bản

- Mô phỏng không có bản thành công, phân loại `DocumentUnretrievableException` và timeout khi blocking.
- Với reactive, kiểm tra kết quả rỗng/lỗi theo SDK contract, không tự đổi thành 404.
- Kiểm tra không có log PII/body/token.
- Xác minh fallback không vượt tenant authorization.

### E. Hai collection cùng key

Ghi `customer::42` ở `shop.crm.customers` và một document khác ở `shop._default._default`. Test phải chứng minh adapter đọc đúng **keyspace**, không chỉ đúng chuỗi document ID.

## 31. Kiến trúc ứng dụng và checklist review

### Chọn ngữ nghĩa trước

- [ ] Endpoint xác định rõ có chấp nhận stale không.
- [ ] Dữ liệu được dùng ra quyết định quyền/giá/quota/tồn kho không đọc replica bừa.
- [ ] Read-after-write có đường active/consistency phù hợp.
- [ ] Không biến `getAllReplicas` thành quorum protocol tự chế.
- [ ] Định nghĩa khi nào trả 404, 503, hoặc dữ liệu best-effort.
- [ ] Nếu cần snapshot “as of T0”, không dùng replica read làm thay thế.

### Kết nối và dữ liệu

- [ ] Inject `Cluster` do Spring quản lý.
- [ ] Chọn đúng bucket/scope/collection.
- [ ] SDK raw mapping theo JSON field thực, không dựa vào `@Field` tự động.
- [ ] Đảm bảo tenant authorization, discriminator và read model DTO.
- [ ] Không dùng CAS từ replica như chứng nhận dữ liệu đang hiện hành.
- [ ] Không dùng replica read làm bước tiền đề duy nhất cho write có ràng buộc.

### Vận hành

- [ ] Kiểm tra bucket có số replica và placement phù hợp.
- [ ] Đo latency, stale observation và availability cùng nhau.
- [ ] Thử failover/rebalance/network faults trong môi trường kiểm soát.
- [ ] Cấu hình timeout và retry có chủ đích.
- [ ] Khi có read preference server group, xác minh SDK/Server versions và topology.
- [ ] Reactive không `block()` trên event-loop.
- [ ] Metrics không chứa PII hoặc secret.
- [ ] Kiểm tra chi phí mạng khi đọc nhiều bản.
- [ ] Tài liệu API công khai mức freshness mà client có thể kỳ vọng.

## 32. Bài tập thực hành

Thiết kế hai endpoint cho một customer:

**Endpoint A — preview có thể cũ**

~~~http
GET /customers/{id}/preview
~~~

Yêu cầu:

1. Dùng Spring-managed `Cluster`.
2. SDK adapter truy cập `shop.crm.customers` và gọi `getAnyReplica(id)`.
3. Trả DTO nhỏ gồm tên hiển thị và metadata `readSource` nếu có ích.
4. Phân quyền tenant bằng context đáng tin cậy; không chỉ tin một field stale của document.
5. Khi không có bản thành công, xử lý lỗi đúng semantics; không tự gán 404.
6. Đo p95 latency và tỉ lệ `isReplica()`.

**Endpoint B — đọc để cập nhật**

~~~http
GET /customers/{id}/edit
~~~

Yêu cầu:

1. Dùng `Collection.get(id)` active hoặc đường Repository/Template phù hợp.
2. Trả dữ liệu đầy đủ cần thiết và CAS/version token nếu UI sử dụng optimistic locking.
3. Khi submit sửa, kiểm tra expected CAS và quyền cập nhật ở thời điểm phù hợp.
4. Không lấy một body replica đã cũ rồi replace full document vô điều kiện.
5. Thử concurrent writer, CAS mismatch và TTL/delete giữa đọc và ghi.

**Phần mở rộng — diagnostics**

1. Gọi `getAllReplicas(id)` trong test tool chỉ dành cho người vận hành.
2. Ghi `isReplica`, `cas`, `revision` và độ trễ từng kết quả, không ghi PII.
3. Chứng minh không có thứ tự kết quả đảm bảo.
4. Thử tăng durability của mutation và đo ảnh hưởng cả write latency lẫn stale observations.
5. Nếu hạ tầng hỗ trợ, bật `ReadPreference.PREFERRED_SERVER_GROUP`, so cross-zone latency/egress và sự khác biệt độ mới.
6. Chạy fault injection để test active chậm mà không làm hỏng production cluster.

### Câu hỏi tự kiểm tra

1. Replica vBucket khác XDCR giữa clusters như thế nào?
2. Vì sao `getAnyReplica` có thể trả kết quả từ active?
3. `getAllReplicas` có đảm bảo trả mọi bản không?
4. `isReplica()` có đồng nghĩa dữ liệu stale không?
5. Vì sao không được dùng `max(cas)` để chọn bản mới nhất?
6. Lỗi `DocumentUnretrievableException` có luôn nghĩa document đã bị xóa không?
7. Read-after-write có thể bị ảnh hưởng ra sao khi dùng replica?
8. Vì sao quyền, giá, tồn kho và quota không nên dựa vào stale replica?
9. Durability `MAJORITY` có bắt buộc tất cả replica đã cập nhật không?
10. `REQUEST_PLUS` có làm `getAnyReplica` trả bản mới nhất không?
11. `getAllReplicas` có thể được dùng làm quorum tự xây không? Vì sao?
12. Khi nào một SDK adapter replica-aware phù hợp hơn Repository query mặc định?
13. Đường reactive khác đường blocking ở phương diện nào, có thay consistency không?
14. Vì sao preferred server group có thể giảm egress nhưng làm tăng nguy cơ thấy replica trễ?
15. Khi nào cần snapshot/versioned export thay vì replica reads?

## 33. Tài liệu chính thức và lưu ý theo phiên bản

- [Couchbase Java SDK — Data Modelling, Durability, and Consistency](https://docs.couchbase.com/java-sdk/current/concept-docs/data-durability-acid-transactions.html): active/replica reads, durable writes và preferred server group.
- [Couchbase Java SDK — KV Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): KV get, expiry, CAS và durability.
- [Java SDK API — Collection](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/Collection.html): `get`, `getAnyReplica`, `getAllReplicas`.
- [Java SDK API — GetReplicaResult](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/GetReplicaResult.html): `isReplica()`, `cas()` và body decoding.
- [Java SDK API — GetAnyReplicaOptions](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/GetAnyReplicaOptions.html): timeout, transcoder, read preference.
- [Java SDK API — ReadPreference](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/ReadPreference.html): `PREFERRED_SERVER_GROUP` và `NO_PREFERENCE`.
- [Java SDK API — ReactiveCollection](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/ReactiveCollection.html): `Mono<GetReplicaResult>`, `Flux<GetReplicaResult>` và semantics kết quả rỗng.
- [Couchbase Java SDK — Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): non-blocking, publisher và lifecycle.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): entity reads, converters và repository.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): mức kiểm soát khi dùng Template và SDK.
- [Couchbase Server — SQL++ Query Scan Consistency](https://docs.couchbase.com/server/current/learn/services-and-indexes/indexes/index-scans.html): index scan consistency, khác KV replica reads.

**Chú ý tương thích:** Ví dụ áp dụng các API phổ biến của **Couchbase Java SDK 3.x**. Đặc biệt, replica sub-document methods và preferred server group có điều kiện phiên bản Couchbase Server/SDK; không sử dụng nếu deployment chưa hỗ trợ. Các chi tiết đọc, error/result semantics, topology và mapping cần kiểm tra với **Spring Data Couchbase, Java SDK và Couchbase Server** đã khóa. Vòng Content QA chuyên môn/biên dịch được thực hiện ở giai đoạn kiểm thử sau STEP 4.

> **Ghi nhớ:** `getAnyReplica` là một **lựa chọn đọc ưu tiên khả dụng** có thể trả active hoặc replica; `getAllReplicas` là **best-effort observation**, không phải consensus hoặc snapshot. Dùng chúng khi nghiệp vụ chấp nhận dữ liệu có thể cũ, đo stale observation và có fallback hợp lý. Với read-after-write, quyền, giá, tồn kho và cập nhật có CAS, hãy dùng đường đọc/mutation có consistency đúng yêu cầu; **durability khi ghi và scan consistency của SQL++ không xóa bỏ mọi đánh đổi của KV replica reads**.
