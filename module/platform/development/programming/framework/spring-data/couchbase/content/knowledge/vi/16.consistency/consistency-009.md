# Kiểm thử độ trễ cập nhật chỉ mục bằng tình huống có kiểm soát

## 1. Tại sao cần một phép thử riêng cho độ trễ chỉ mục?

Trong ứng dụng **Spring Data Couchbase**, lệnh ghi một document có thể được xác nhận thành công trước khi **Global Secondary Index (GSI)** dùng cho truy vấn SQL++ bắt kịp mutation đó. Vì vậy, ngay sau khi lưu một Order:

~~~java
OrderDocument saved = orderRepository.save(newOrder);

// Đường KV theo metadata key.
OrderDocument detail = orderRepository.findById(saved.getId())
        .orElseThrow();

// Đường SQL++ theo field JSON, thường cần index.
List<OrderDocument> history =
        orderRepository.findByCustomerId(saved.getCustomerId());
~~~

`detail` và `history` không được bảo đảm có cùng **thời điểm nhìn thấy thay đổi** nếu SQL++ chưa yêu cầu index đủ mới. Dù vậy, một bài kiểm thử viết kiểu “ghi xong, truy vấn NOT_BOUNDED phải không thấy row” là **sai về logic**: index có thể đã cập nhật rất nhanh; một cơ chế cho phép đọc stale **không bắt buộc** nó phải stale.

Bài học thuộc chương **Tính nhất quán** của module **SPRING_DATA_COUCHBASE**. Kiến thức liên quan trực tiếp đến document mapping, Repository, `CouchbaseTemplate`, SQL++, bucket/scope/collection, index, TTL, CAS, giao dịch, reactive API, hiệu năng và vận hành.

Chúng ta sẽ thiết kế **hai loại phép thử độc lập**:

1. **Correctness test (deterministic theo hợp đồng):** Sau khi write được ACK, query `REQUEST_PLUS` hoặc `consistentWith(MutationState)` thành công phải phản ánh mutation trong phạm vi query/index hỗ trợ, nếu document vẫn thỏa bộ lọc và không có thay đổi cạnh tranh.
2. **Latency observation (phép đo có kiểm soát):** Dưới workload, lấy mẫu SQL++ `NOT_BOUNDED` sau mutation để ước lượng *thời điểm client lần đầu quan sát được thay đổi*, đồng thời thu metric Index/Query Service. Đây **không** phải một phép assert rằng lag phải xảy ra.

**Kết quả học tập:** Bạn sẽ biết dựng môi trường thử, chọn dữ liệu/secondary index, viết Java SDK/JUnit test, thiết kế polling có giới hạn, phân biệt đo quan sát và độ trễ nội bộ thực, đọc biểu đồ p95/p99, tránh nhiễu bởi cache hoặc `LIMIT`, lập báo cáo và đưa kết luận kỹ thuật đúng phạm vi.

## 2. Trước khi đo: phát biểu giả thuyết đúng

Một phép thử có ý nghĩa cần phân biệt **bảo đảm sản phẩm** với **hiện tượng được phép xảy ra**.

| Giả thuyết/câu hỏi | Có thể dùng assert cứng? | Giải thích |
| --- | --- | --- |
| KV get theo key thấy document vừa insert được ACK trên active path | Có, nếu không có delete/update cạnh tranh và cùng keyspace | Không cần secondary index |
| SQL++ `REQUEST_PLUS` sau ACK thấy document phù hợp filter | Có, với index online, query thành công và dữ liệu ổn định | Yêu cầu index đạt mốc request trước scan |
| SQL++ `consistentWith(state)` thấy mutation đã cung cấp | Có, khi có token hợp lệ và query đúng | Yêu cầu index đạt mốc mutation được nêu |
| SQL++ `NOT_BOUNDED` *phải* không thấy document ngay | **Không** | Nó có thể nhìn thấy mutation nếu index đã kịp |
| REQUEST_PLUS *luôn* chậm hơn NOT_BOUNDED X ms | **Không** | Phụ thuộc index lag, query plan, cluster và tải |
| Sau một lần sleep 100 ms thì index chắc chắn đã cập nhật | **Không** | Không có bảo đảm thời gian cố định |
| Kết quả query thiếu row đồng nghĩa index lag | **Không** | Có thể do filter, sort, LIMIT, keyspace, cache, quyền |
| Một bài benchmark cho số liệu chung của mọi cluster | **Không** | Chỉ đại diện cấu hình và workload đã đo |

Đặt mục tiêu bằng hai câu rõ ràng:

- **Hợp đồng về độ mới:** “Khi POST trả thành công, query danh sách ngay sau đó phải nhìn thấy Order nếu Order thỏa WHERE và nằm trong phạm vi kết quả.”
- **Mục tiêu về hiệu năng:** “Theo workload đại diện, API query đạt latency SLO và Index Service không có backlog kéo dài quá ngưỡng vận hành đã thống nhất.”

Tách hai câu giúp đội phát triển không đánh đổi tính đúng đắn lấy một kết quả benchmark đẹp.

## 3. Đường đi mutation và index: nơi có thể xuất hiện khoảng trễ

~~~mermaid
sequenceDiagram
    participant TEST as JUnit / Load Client
    participant DATA as Couchbase Data Service
    participant IDX as Index Service
    participant QUERY as Query Service

    TEST->>DATA: KV insert Order A
    DATA-->>TEST: Mutation ACK
    TEST->>DATA: KV get(A)
    DATA-->>TEST: Order A
    Note over DATA,IDX: Mutation được chuyển và xử lý bởi index
    TEST->>QUERY: SQL++ NOT_BOUNDED theo customerId
    QUERY->>IDX: Scan index hiện có
    IDX-->>QUERY: Rows theo mốc đã index
    QUERY-->>TEST: Có thể thiếu A
    DATA-->>IDX: Mutation A được index phản ánh
    TEST->>QUERY: SQL++ REQUEST_PLUS theo customerId
    QUERY->>IDX: Chờ mốc consistency request
    IDX-->>QUERY: Đủ mới để scan
    QUERY-->>TEST: A nếu filter và dữ liệu vẫn phù hợp
~~~

Sơ đồ minh họa **hai lần query khác thời điểm**. Không nên coi lần NOT_BOUNDED đầu luôn stale. Nếu Index Service đã bắt kịp trước query ấy, cả hai truy vấn có thể cùng trả Order.

### 3.1. Không nhầm ACK write với readiness của index

`Collection.insert(...)` hoặc `Repository.save(...)` thành công nghĩa là client nhận xác nhận mutation theo semantics của thao tác ghi. Nó không mặc định yêu cầu mọi secondary index đã cập nhật, cũng không tự bảo đảm Search index, cache hay bản sao ở cluster khác đủ mới.

### 3.2. KV read và SQL++ scan không kiểm tra cùng thứ

- **KV get:** đọc theo metadata key; thích hợp xác minh document nguồn.
- **SQL++ query theo field:** dùng điều kiện `WHERE customerId = ...`; query plan thường cần secondary index.
- **Query consistency:** xác định index phải đạt mốc nào trước khi quét.
- **Cache:** có thể trả kết quả trước khi SQL++ thực thi; phải loại khỏi phép đo nếu mục tiêu là GSI.

## 4. Định nghĩa chính xác đại lượng muốn đo

Giả sử mutation `m` được client xác nhận ở `t_ack`. Gọi `t_index_visible` là thời điểm mà một query/index path cụ thể có thể quan sát được tác động của mutation.

Ta thường muốn biết:

\[
L_{\mathrm{index}}(m)=t_{\mathrm{index\_visible}}(m)-t_{\mathrm{ack}}(m)
\]

Đây là **định nghĩa khái niệm**. Client không tự nhìn thấy đồng hồ nội bộ của Index Service, không biết chính xác lúc nào mutation được phản ánh vào GSI và thậm chí một mutation có thể được index hóa trước lúc ACK đến client.

Vì vậy, một phép thử polling tại client đo một đại lượng khác:

\[
L_{\mathrm{first\_observed}} =
 t_{\mathrm{first\_successful\_probe}}-t_{\mathrm{ack}}
\]

Trong đó “successful probe” là **lần query kết thúc và chứa row mong đợi** theo filter đã xác định.

**Điểm cần nhớ:**

- `L_first_observed` bao gồm lịch polling, network, query execution và scheduling của client.
- Nó **không bằng tuyệt đối** độ trễ nội bộ Index Service.
- Nếu query đầu tiên đã thấy Order, không thể suy index lag chính xác bằng 0.
- Nếu chưa thấy ở lần cuối trước deadline, kết quả là **censored/right-censored**: “chưa quan sát được trong cửa sổ thử”, không được tự gán 0 hoặc vô hạn.
- Nếu thấy row sau mutation khác hoặc document bị xóa/đổi filter, phép thử mất ý nghĩa; dữ liệu test cần cô lập.

### 4.1. Dùng đồng hồ đơn điệu cho duration

Trong Java, nên dùng `System.nanoTime()` để đo khoảng thời gian trên **một process**, không dùng chênh lệch `LocalDateTime.now()` dễ ảnh hưởng bởi điều chỉnh đồng hồ hệ thống.

~~~java
long startedNs = System.nanoTime();
QueryResult result = cluster.query(sql, options);
long elapsedNs = System.nanoTime() - startedNs;
double elapsedMs = elapsedNs / 1_000_000.0;
~~~

Nếu đo từ nhiều máy, chỉ so sánh timestamp wall-clock sau khi đã xem xét đồng bộ đồng hồ, time zone và sai số. Đo duration cục bộ bằng monotonic clock thường đáng tin cậy hơn.

## 5. Chuẩn bị dữ liệu và namespace cho bài thử

Bộ dữ liệu xuyên suốt:

~~~text
Bucket:       shop
Scope:        sales
Collection:   orders
Document key: order::it-<UUID>
~~~

Body JSON minh họa:

~~~json
{
  "customerId": "it-customer-5f3d...",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 180000
}
~~~

Mỗi phép thử dùng:

- Một `orderId` mới sinh, tránh đụng document khác.
- Một `customerId` duy nhất, không có traffic nghiệp vụ khác.
- Một filter chỉ dựa vào field chắc chắn đã lưu.
- Một secondary index được xác nhận online.
- Không có ứng dụng khác cập nhật/xóa document test giữa insert và query.

Tính độc lập của dữ liệu test rất quan trọng. Nếu hai worker dùng chung customerId và `LIMIT 20`, một Order không có trong kết quả có thể đơn giản là bị loại bởi sort/limit chứ không phải index lag.

### 5.1. Thiết kế JSON ổn định

Chọn kiểu field nhất quán: `customerId` là string; `status` là một trong các giá trị xác định; `createdAt` là ISO-8601 UTC theo quy ước chung. Nếu mapper chuyển đổi `Instant` hoặc type discriminator, phải xác minh JSON thực tế.

### 5.2. Đừng lấy một field random làm nguyên nhân truy vấn không có index

Index phải phục vụ field được lọc. Không chỉ tạo dữ liệu random rồi cho rằng mọi query đều dùng index đang muốn đo. Cần chuẩn bị query, index và kiểm tra `EXPLAIN`.

## 6. Tạo chỉ mục có thể giải thích được

Một index khởi đầu cho truy vấn theo `customerId`:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Query đo insert visibility:

~~~sql
SELECT META(o).id AS documentId
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId;
~~~

Không dùng `LIMIT` trong phép đo insert một row theo customerId duy nhất; điều này loại bỏ nhiễu “document nằm ngoài trang kết quả”. Ở ứng dụng thật vẫn cần pagination, nhưng phép đo index visibility phải **đơn giản hóa có chủ đích**.

Kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT META(o).id AS documentId
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "it-customer-example";
~~~

**Phải ghi lại index thực sự được chọn.** Nếu query dùng primary index, một index khác hoặc có kế hoạch fetch/sort không dự kiến, phép đo có thể không kiểm tra đúng thứ bạn nghĩ.

### 6.1. Covering hay non-covering?

Ở truy vấn chỉ cần `META(o).id` và filter `customerId`, có thể có khả năng dùng covering index tùy thiết kế/plan. Nếu query fetch document nguồn, stale index membership có thể biểu hiện khác với query được cover.

Do đó:

1. Ghi lại query plan.
2. Giữ nguyên plan giữa các đợt benchmark.
3. Nếu thử riêng tác động covering/non-covering, đặt đó thành **hai nhóm thử nghiệm tách biệt**.
4. Không suy rằng “index cũ” luôn làm body JSON trả nguyên một bản cũ.

## 7. Ba mức consistency cần so sánh

| Chế độ | Yêu cầu đối với index trước scan | Thích hợp trong thử nghiệm |
| --- | --- | --- |
| `NOT_BOUNDED` | Không buộc đợi mốc mutation mới nhất của request | Quan sát độ trễ thấy row dưới tải |
| `REQUEST_PLUS` | Đợi index liên quan bắt kịp mốc consistency của request | Correctness test read-after-write và latency chờ |
| `AT_PLUS` / `consistentWith(MutationState)` | Đợi các mutation token đã biết | Correctness test cho các ghi cụ thể |

**`REQUEST_PLUS` không làm mọi query trở thành snapshot bất biến.** Nếu một worker khác sửa/xóa document sau write, query có thể phản ánh mutation mới hơn. Kiểm thử phải kiểm soát concurrency trên document mục tiêu.

### 7.1. NOT_BOUNDED không có điều kiện “phải cũ”

`NOT_BOUNDED` có thể thấy một Order mới ngay vì Index Service đã theo kịp. Không nên thêm `Thread.sleep(10)` để cố tạo một “khoảng cũ”; chờ thêm thường còn làm index dễ bắt kịp hơn.

### 7.2. REQUEST_PLUS có chi phí thực

Query có thể chờ lâu nếu Index Service còn backlog; khi vượt timeout, kết quả là **lỗi query** chứ không phải “0 rows”. Phải đo latency/error rate cùng nhau; chỉ tính những query thành công có thể tạo sai lệch.

### 7.3. MutationState cần token thật

SDK KV mutation có thể cung cấp `MutationResult.mutationToken()`. Nếu token không có, không tạo token giả từ CAS, ID hoặc clock của client. Với use case cần mốc request và không có token, `REQUEST_PLUS` là một fallback có chủ đích, không phải tương đương trong mọi semantics.

## 8. Hai nhóm thử nghiệm: correctness và characterization

Nên đặt bộ test thành hai nhóm rõ ràng.

| Nhóm | Câu hỏi | Dạng kết quả | Có nên chạy trong CI thông thường? |
| --- | --- | --- | --- |
| **Correctness** | REQUEST_PLUS có thấy insert đã ACK trong keyspace/index hợp lệ không? | PASS/FAIL và lỗi rõ | Có, nếu môi trường Couchbase ổn định |
| **Characterization** | Dưới tải, NOT_BOUNDED mất bao lâu để lần đầu quan sát mutation? | Phân phối, tỷ lệ đã thấy ngay, censored samples | Có thể chạy nightly/performance lab; không ép ngưỡng cứng trong CI thiếu kiểm soát |
| **Capacity/Stress** | Khi tăng ghi/query, backlog và p99 thay đổi ra sao? | Throughput, p95/p99, timeout, index metrics | Chạy riêng, có giới hạn tài nguyên |
| **Failure/Recovery** | Khi index chậm hoặc node phục hồi, API đáp ứng thế nào? | Error handling, retry/backoff, recovery time | Chỉ trên cluster thử nghiệm có quyền kiểm soát |

Không cố gom cả bốn nhóm thành một `@Test` duy nhất với thời gian chờ không giới hạn.

## 9. Chuẩn bị môi trường: giữ những biến số quan trọng cố định

Trước khi chạy, ghi lại:

1. Phiên bản Couchbase Server, Java SDK, Spring Boot và Spring Data Couchbase.
2. Topology: Data, Query và Index Service chạy trên node nào, tài nguyên phân bổ ra sao.
3. Bucket/scope/collection, index definition và index state.
4. Dataset size, document size, phân phối `customerId`/`status`.
5. Có background workloads khác không; nếu có phải ghi rõ.
6. Write durability, timeout và SDK retry configuration.
7. Query SQL++, plan, scan consistency và projection.
8. Có cache ứng dụng/HTTP/Redis/Browser hay không; phép đo index cần bypass.
9. Network path client tới cluster, số kết nối và mức concurrent requests.
10. Thời điểm test có đang index build, rebalance, backup hoặc recovery không.

Không thử gây tải nặng lên production. Tạo một môi trường test có tài nguyên giới hạn và quyền quản trị/index rõ, chủ động tách khỏi hệ thống khách hàng thật.

### 9.1. Mục tiêu “có kiểm soát” không có nghĩa mọi yếu tố đều cố định hoàn toàn

Couchbase là hệ thống phân tán; scheduler, network, rebalance, garbage collection, I/O và background maintenance gây biến thiên. “Có kiểm soát” nghĩa là **ghi nhận và giới hạn những biến số chính**, lặp thí nghiệm đủ lần và diễn giải kết quả đúng phạm vi.

## 10. Một mẫu cấu hình Spring Boot cho môi trường test

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cấu hình minh họa:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: YOUR_TEST_USERNAME
    password: YOUR_TEST_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Đừng hard-code credential thật trong source control; lấy từ secret/environment. Cần đảm bảo account có quyền KV và Query phù hợp. Việc create index cần quyền riêng, không nên cho ứng dụng production quyền quản trị index nếu không cần.

Tài khoản và đường kết nối trong snippet là **ví dụ**, phải thay bằng cluster test thực tế. `@SpringBootTest` được dùng để lấy bean `Cluster` nếu cấu hình Spring Data Couchbase/SDK phiên bản đang chạy phơi bày bean tương ứng.

## 11. Correctness test: REQUEST_PLUS thấy insert đã xác nhận

Bài kiểm thử đầu tiên kiểm tra một bảo đảm rõ ràng, không cố tạo lag.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class RequestPlusReadAfterWriteIT {

    @Autowired
    private Cluster cluster;

    @Test
    void querySeesPreviouslyAcknowledgedInsert() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String documentId = "order::it-" + UUID.randomUUID();
        String customerId = "it-customer-" + UUID.randomUUID();
        boolean insertAcknowledged = false;

        try {
            orders.insert(documentId, JsonObject.create()
                    .put("customerId", customerId)
                    .put("status", "CREATED"));
            insertAcknowledged = true;

            assertEquals(customerId,
                    orders.get(documentId)
                            .contentAsObject()
                            .getString("customerId"));

            String sql = """
                SELECT META(o).id AS documentId
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                """;

            QueryResult result = cluster.query(
                    sql,
                    queryOptions()
                            .parameters(JsonObject.create()
                                    .put("customerId", customerId))
                            .scanConsistency(
                                    QueryScanConsistency.REQUEST_PLUS));

            assertTrue(result.rowsAsObject().stream()
                    .anyMatch(row -> documentId.equals(
                            row.getString("documentId"))));
        } finally {
            if (insertAcknowledged) {
                orders.remove(documentId);
            }
        }
    }
}
~~~

**Điều kiện trước khi chạy:**

- `shop.sales.orders` tồn tại, có index phù hợp và đã online.
- Không có mutation cạnh tranh trên document test.
- Query filter không có `LIMIT`/tenant/type discriminator bất ngờ loại row.
- `orders.get` kiểm tra đường KV, còn `cluster.query` kiểm tra SQL++.
- SDK raw JSON không tự thêm type discriminator của Spring Data; test Repository/entity mapping phải chuẩn bị fixture tương ứng.

Đây là mẫu **integration test với fixture**, không nên chạy trên production. Nếu insert đã được server xử lý nhưng client không nhận ACK, cờ `insertAcknowledged` có thể false và cleanup trong `finally` không đủ; suite hoàn chỉnh cần dọn fixture theo key/prefix sau các write ambiguous.

### 11.1. Query thành công nhưng thiếu row là lỗi cần điều tra

Nếu query REQUEST_PLUS trả thành công mà không có row vừa ghi, trước khi kết luận cơ chế consistency sai cần kiểm tra keyspace, index đang dùng, `WHERE`, body JSON, concurrent delete/update, query error và metadata. Nếu query timeout, test nên fail với exception/diagnostics, **không** trả về empty list giả.

### 11.2. Khi nào bài test này vẫn có thể flaky?

Môi trường không ổn định, index mới đang build hoặc cluster thiếu capacity có thể khiến REQUEST_PLUS timeout. Đây có thể là vấn đề **environment/SLO** cần phân biệt với bug logic. Vì thế correctness test phải có timeout hợp lý, log đủ context và không lạm dụng retry không giới hạn.

## 12. Một helper query dùng chung cho các phép đo

Để so sánh hai chế độ, cần giữ **SQL++ và dữ liệu query giống nhau**, chỉ đổi mode. Có thể xây utility đơn giản:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public final class IndexVisibilityProbe {
    private static final String SQL = """
        SELECT META(o).id AS documentId
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.customerId = $customerId
        """;

    private final Cluster cluster;

    public IndexVisibilityProbe(Cluster cluster) {
        this.cluster = cluster;
    }

    public boolean contains(String customerId,
                            String documentId,
                            QueryScanConsistency consistency) {
        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(consistency);

        QueryResult result = cluster.query(SQL, options);
        return result.rowsAsObject().stream()
                .anyMatch(row -> documentId.equals(
                        row.getString("documentId")));
    }
}
~~~

Có thể dùng:

~~~java
IndexVisibilityProbe probe = new IndexVisibilityProbe(cluster);

boolean seenWithDefaultLikeMode = probe.contains(
        customerId, documentId, QueryScanConsistency.NOT_BOUNDED);

boolean seenWithRequestPlus = probe.contains(
        customerId, documentId, QueryScanConsistency.REQUEST_PLUS);
~~~

Đừng đọc hai boolean này như một phép so sánh “cùng thời điểm”: query thứ hai chạy **sau** query thứ nhất, nên có thêm thời gian cho index bắt kịp. Khi đo latency so sánh, cần dùng nhiều lần thử và cân bằng thứ tự/điều kiện.

## 13. Observation test: polling NOT_BOUNDED có giới hạn

Mục tiêu là **quan sát**, không ép GSI trễ. Một phép thử sau khi insert:

1. Ghi Order mới bằng KV và ghi lại mốc ACK cục bộ.
2. Gọi `NOT_BOUNDED` với filter customerId duy nhất.
3. Nếu đã thấy document ở query đầu: ghi nhận **first-probe hit**.
4. Nếu chưa: lấy mẫu thêm với khoảng nghỉ nhỏ, **có giới hạn số lần và thời gian tổng**.
5. Nếu nhìn thấy ở lần sau: ghi lại “đã quan sát thành công trong cửa sổ”, thời điểm quan sát và số probe.
6. Nếu hết deadline: ghi lại **censored sample**; không chuyển thành false correctness assertion cho NOT_BOUNDED.
7. Dọn dữ liệu và thu metric bên cluster.

Mã minh họa:

~~~java
import java.time.Duration;

import com.couchbase.client.java.query.QueryScanConsistency;

public class ControlledLagSampler {

    public record Observation(
            boolean firstProbeHit,
            boolean visibleWithinWindow,
            int queriesExecuted,
            long firstVisibleAfterAckMillis) {
    }

    private final IndexVisibilityProbe probe;

    public ControlledLagSampler(IndexVisibilityProbe probe) {
        this.probe = probe;
    }

    public Observation sampleAfterAcknowledgement(
            String customerId,
            String documentId,
            long acknowledgedAtNs) throws InterruptedException {

        final int maxQueries = 8;
        final Duration pause = Duration.ofMillis(40);

        boolean firstProbeHit = false;
        for (int i = 1; i <= maxQueries; i++) {
            boolean visible = probe.contains(
                    customerId,
                    documentId,
                    QueryScanConsistency.NOT_BOUNDED);

            long observedAtNs = System.nanoTime();

            if (i == 1) {
                firstProbeHit = visible;
            }
            if (visible) {
                long ms = Duration.ofNanos(
                        observedAtNs - acknowledgedAtNs).toMillis();
                return new Observation(
                        firstProbeHit, true, i, ms);
            }

            if (i < maxQueries) {
                Thread.sleep(pause.toMillis());
            }
        }

        // -1 có nghĩa là chưa quan sát được trước giới hạn,
        // KHÔNG có nghĩa index lag = -1 ms.
        return new Observation(false, false, maxQueries, -1L);
    }
}
~~~

Cách gọi bên trong thử nghiệm:

~~~java
Collection orders = cluster.bucket("shop")
        .scope("sales")
        .collection("orders");

long acknowledgedNs;
orders.insert(id, body);
acknowledgedNs = System.nanoTime();

IndexVisibilityProbe probe = new IndexVisibilityProbe(cluster);
Observation observation = new ControlledLagSampler(probe)
        .sampleAfterAcknowledgement(
                customerId, id, acknowledgedNs);

// Lưu observation vào dữ liệu phân tích.
// Không assert visibleWithinWindow buộc phải true cho NOT_BOUNDED.
~~~

Trong snippet cuối, `id`, `body`, `customerId` và kiểu `Observation` phải được khai báo theo fixture; dùng tên đủ `ControlledLagSampler.Observation` nếu code ở ngoài lớp. Không dùng `Thread.sleep` này như logic production để “bảo đảm index mới”; nó chỉ tạo **nhịp lấy mẫu có giới hạn trong thí nghiệm**.

### 13.1. Giới hạn test để tránh tự gây quá tải

Ví dụ `8 query` và `40 ms` chỉ để minh họa một phép lấy mẫu nhỏ, không phải mức khuyến nghị cho production. Nếu thử hàng nghìn mutations đồng thời và mỗi mutation gửi tám SQL++ queries, **chính phép đo có thể tạo tải lớn** lên Query/Index Service. Cần giới hạn concurrency, tổng QPS và thời gian chạy.

### 13.2. Xử lý lỗi query trong mẫu

Nếu bất kỳ query NOT_BOUNDED nào timeout hoặc trả lỗi, đó là **error sample**, không phải “row chưa visible”. Mã `contains` ở trên để exception nổi lên; runner benchmark phải ghi nhận lỗi riêng và quyết định dừng/retry có giới hạn.

## 14. Tính toán thống kê mà không tự bịa mốc index

Sau N mutation độc lập, thu:

- Tổng số lần thử.
- Tỷ lệ query đầu tiên đã thấy row.
- Tỷ lệ nhìn thấy row trong cửa sổ thử.
- Số lượng **censored samples**.
- Tỷ lệ timeout/error (tách riêng).
- Thời gian từ ACK tới lần query thành công đầu tiên của những mẫu quan sát được.
- Query latency và chỉ số Index Service tương ứng.

Một báo cáo ví dụ ở dạng **mẫu điền số liệu**, chưa có kết quả thật:

| Chỉ số | Kết quả |
| --- | --- |
| Tổng mutation đã ACK | Điền sau thử |
| First-probe hit rate | Điền sau thử |
| Visible within 8 probes | Điền sau thử |
| Censored within probe window | Điền sau thử |
| Query error/timeout count | Điền sau thử |
| p50 first-observed time | Điền sau thử, nêu rõ chỉ trên mẫu observed |
| p95 first-observed time | Điền sau thử, nêu rõ censored samples |
| Index backlog/lag metric | Điền từ cluster |

### 14.1. Thiên lệch do bỏ mẫu censored

Nếu chỉ tính trung bình/p95 trên những mutation đã được nhìn thấy trong cửa sổ và **bỏ các mẫu chưa thấy**, kết quả có thể trông tốt bất thường. Càng nhiều censored samples, kết luận percentile của thời gian “đến khi visible” càng không chắc chắn.

Nên công bố tỷ lệ censored và deadline, hoặc dùng phương pháp phân tích dữ liệu bị kiểm duyệt (survival-analysis) khi mức độ nghiêm túc yêu cầu. Đừng tự thay mẫu chưa thấy thành 0 ms.

### 14.2. Biên trên quan sát không phải latency nội bộ

Giữa hai query cách nhau 40 ms, mutation có thể đã visible ngay sau query trước, nhưng chỉ được phát hiện ở query sau. Khoảng chờ lịch polling và network làm phép đo client **kém chính xác hơn** timestamp nội bộ Index Service. Nếu cần chẩn đoán capacity, phải kết hợp metric index update backlog/lag do Couchbase cung cấp.

## 15. So sánh NOT_BOUNDED và REQUEST_PLUS đúng cách

Một lỗi benchmark thường gặp:

~~~text
insert Order
query NOT_BOUNDED   -> chạy trước
query REQUEST_PLUS  -> chạy sau
kết luận REQUEST_PLUS "nhìn thấy mới hơn vì policy"
~~~

Kết luận chưa chặt vì **thời điểm query khác nhau**. REQUEST_PLUS có bảo đảm freshness riêng, nhưng một thử nghiệm như vậy không chứng minh sự khác biệt do policy chứ không phải index tự bắt kịp trong khoảng giữa hai query.

### 15.1. Thiết kế so sánh tốt hơn

- Chạy nhiều mutation ID ngẫu nhiên, độc lập.
- Với các vòng thử khác nhau, đảo thứ tự/nhóm mode nếu mục tiêu là đo latency.
- Giữ query, index, dataset, mạng và concurrency tương đồng.
- Ghi index lag/backlog tại từng khoảng thời gian.
- Đo latency của mode và tính đúng đắn của row như **hai cột riêng**.
- Không buộc hai mode nhìn cùng một snapshot nếu có mutation đồng thời.
- Công bố confidence interval hoặc phân phối khi dữ liệu đủ lớn; tránh kết luận từ hai lần chạy.

### 15.2. Có cần chạy hai query thực sự đồng thời?

Có thể, nếu mục tiêu là mô phỏng cạnh tranh, nhưng khi đó thời điểm bắt đầu và scheduling phải được ghi rõ; hai query đồng thời có thể tạo thêm tải và không dễ tách nguyên nhân. Với bài thực hành cơ bản, nên ưu tiên hai nhóm thử có thứ tự được kiểm soát và số lần lặp đủ thay vì cố tạo “cùng mili giây”.

### 15.3. Tỷ lệ timeout cũng là một kết quả

Nếu REQUEST_PLUS có p99 của **các truy vấn thành công** thấp nhưng 15% query timeout, không được tuyên bố nó đáp ứng SLO. Phải báo cáo cả lỗi, retry và ngân sách timeout.

## 16. Tạo tải ghi có kiểm soát để quan sát index backlog

Độ trễ index có thể gần như không quan sát được trên cluster nhàn. Muốn đánh giá dưới tải, tăng mutation rate **có kế hoạch** trong môi trường test:

1. Đo baseline ở tốc độ ghi thấp.
2. Tăng write rate theo từng bậc có giới hạn.
3. Ở mỗi bậc, giữ query rate và các setting chính ổn định.
4. Ghi mutation backlog/Index Service CPU/memory/disk I/O.
5. Chạy probe NOT_BOUNDED và correctness REQUEST_PLUS ở dữ liệu test độc lập.
6. Giảm tải để quan sát recovery.
7. Dừng khi gần ngưỡng tài nguyên/timeouts đã định trước.

Ví dụ ma trận **không gắn con số benchmark tự tạo**:

| Giai đoạn | Tải mutation | Tải query | Điều cần quan sát |
| --- | --- | --- | --- |
| Baseline | Thấp | Thấp | Query latency và first-probe hit |
| Write-step A | Trung bình | Giữ nguyên | Backlog và tốc độ catch-up |
| Write-step B | Cao có giới hạn | Giữ nguyên | Tail latency và timeout |
| Read-heavy | Cố định | Tăng có giới hạn | Query Service, scan/fetch pressure |
| Recovery | Giảm dần | Vẫn đo | Thời gian backlog trở về |
| Repeat | Như baseline | Như baseline | Hệ thống có phục hồi tương đương không |

**Không điều chỉnh tải bằng cách bỏ qua mọi lỗi và retry vô hạn.** Khi Index Service hoặc Query Service đã quá tải, một load generator thiếu giới hạn có thể làm thí nghiệm không còn đại diện và gây hại cho cluster test.

### 16.1. Không cố tình tắt Index Service trên production

Việc tạm dừng index, network partition hoặc failover để “bắt buộc thấy stale data” là fault injection ảnh hưởng khả năng sẵn sàng, không phải điều kiện bắt buộc để chứng minh NOT_BOUNDED semantics. Chỉ tiến hành trên **cluster lab cô lập**, có runbook phục hồi và quyền vận hành rõ ràng. Bài học này không yêu cầu can thiệp dịch vụ hệ thống.

## 17. Kiểm thử update: membership index cũ và mới

Insert là trường hợp dễ quan sát nhất. Update có điểm tinh tế hơn: một index theo `status` có thể phải loại entry cũ và thêm/update entry mới.

Ví dụ:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED"
}
~~~

Sau update:

~~~json
{
  "customerId": "c-1001",
  "status": "PAID"
}
~~~

Có thể kiểm tra hai câu SQL++:

~~~sql
SELECT META(o).id AS documentId
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = "PAID";
~~~

~~~sql
SELECT META(o).id AS documentId
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = "CREATED";
~~~

Để có đường index rõ ràng:

~~~sql
CREATE INDEX ix_orders_customer_status
ON `shop`.`sales`.`orders`(customerId, status);
~~~

**Correctness test:** Sau khi update được ACK và query REQUEST_PLUS thành công, khi không có mutation cạnh tranh, query `status = PAID` phải có Order, còn `status = CREATED` phải phản ánh điều kiện không còn match. Kiểm tra index/query plan và JSON thực tế.

**Observation test:** Đo thời điểm query NOT_BOUNDED đầu tiên phát hiện membership mới, nhưng không assert phải thấy trạng thái cũ trước đó. Với query phải fetch document nguồn, biểu hiện trong thời gian index lag còn phụ thuộc cơ chế xử lý row và query plan.

### 17.1. Đừng gọi tên “dữ liệu cũ” quá chung

Một query `status = CREATED` có thể vẫn dùng entry index cũ nhưng khi fetch body mới, kết quả thực tế khác. Một covering query có thể thể hiện trạng thái index rõ hơn. Ghi lại query plan; không kết luận mọi row đều chứa body JSON cũ chỉ từ việc index update trễ.

## 18. Kiểm thử delete: đừng đồng nhất index entry với document còn tồn tại

Sau lệnh `Collection.remove(id)` được ACK:

- KV get theo ID trên active path nên phản ánh document đã bị xóa.
- Secondary index có thể còn entry trong khoảng chưa xử lý removal.
- Một SQL++ query có thể thấy/hay không thấy row tùy index scan và việc fetch body nguồn.

Một phép thử tốt:

1. Seed Order, dùng REQUEST_PLUS xác nhận index đã nhìn thấy insert.
2. Xóa Order bằng KV, xác nhận thao tác.
3. Query REQUEST_PLUS theo field; không có mutation cạnh tranh, query hoàn thành phải phản ánh removal khi điều kiện/keyspace phù hợp.
4. Lấy mẫu NOT_BOUNDED để quan sát **nếu** còn entry, nhưng không bắt nó stale.
5. Cleanup idempotent và ghi lỗi riêng.

Nếu dùng Search/FTS, phải kiểm thử consistency của **Search Service** riêng. SQL++ `QueryScanConsistency.REQUEST_PLUS` không tự mang cùng semantics sang mọi Search index.

## 19. TTL và expiry: một nguồn biến thiên phải cô lập

Nếu document có TTL và tự hết hạn trong cửa sổ thử, query có thể thiếu row vì expiry chứ không phải index lag do insert. Để phép đo insert/update đơn giản, **không đặt TTL quá ngắn** cho fixture.

Các khái niệm tách biệt:

- **Couchbase expiry:** metadata vòng đời document.
- **Business field `expiresAt`:** JSON do ứng dụng quản lý, không tự kích hoạt TTL.
- **Cache TTL:** thời gian Redis/Caffeine/HTTP giữ kết quả.
- **Index visibility:** thời điểm GSI phản ánh mutation/expiry.

Một bài test TTL cần được thiết kế riêng với thời gian hết hạn, KV check và SQL++ query phù hợp; không trộn vào bài đo insert latency cơ bản.

## 20. Không để cache làm sai phép đo

Nếu query được gọi qua một service có `@Cacheable`, client có thể nhận lại danh sách cũ mà **không gửi SQL++ tới Couchbase**. Khi đó, “lag đo được” có thể là TTL/invalidation của cache, không phải Index Service.

Ví dụ:

~~~java
@Cacheable(cacheNames = "order-history", key = "#customerId")
public List<OrderDocument> history(String customerId) {
    return orderRepository.findByCustomerId(customerId);
}
~~~

Ở lần cache hit, Repository không được gọi. Dù method dưới đã gắn REQUEST_PLUS, query consistency cũng không được thực thi.

**Đối với thí nghiệm GSI:**

- Gọi SDK `cluster.query(...)` trực tiếp hoặc một DAO chắc chắn bypass cache.
- Không cache rows giữa các probes.
- Không dùng HTTP/CDN/browser để đo thời gian index.
- Ghi query execution count để chứng minh mỗi probe đã chạy.
- Nếu muốn đánh giá **độ mới cuối-đầu của sản phẩm**, làm bài test thứ hai có chủ đích bao gồm cache.

### 20.1. Prepared query plan không phải result cache

Việc Query Service dùng prepared plan có thể giảm overhead lập kế hoạch, nhưng không đồng nghĩa tự cache toàn bộ kết quả SQL++. Không viện “plan cache” làm lời giải thích cho row stale nếu chưa có bằng chứng.

## 21. Đo REQUEST_PLUS bằng latency và timeout

Correctness test ở phần 11 assert row tồn tại khi query thành công. Để đo chi phí consistency, ghi thời gian thực thi quanh SDK call:

~~~java
long before = System.nanoTime();
try {
    QueryResult result = cluster.query(
            sql,
            QueryOptions.queryOptions()
                    .parameters(params)
                    .scanConsistency(
                            QueryScanConsistency.REQUEST_PLUS));

    long after = System.nanoTime();
    recorder.recordSuccess(
            (after - before) / 1_000_000.0,
            result.rowsAsObject().size());
} catch (RuntimeException error) {
    long after = System.nanoTime();
    recorder.recordFailure(
            (after - before) / 1_000_000.0,
            error.getClass().getSimpleName());
    throw error;
}
~~~

`sql`, `params` và `recorder` ở snippet là biến/phụ thuộc do benchmark định nghĩa. Code chỉ minh họa cách lưu **cả success lẫn failure**. Nên thêm query metrics/tracing khi API hỗ trợ, nhưng không log toàn bộ dữ liệu nhạy cảm.

### 21.1. Đo p50/p95/p99 không chỉ trung bình

Một query `REQUEST_PLUS` có thể nhanh ở phần lớn request nhưng chậm đáng kể khi backlog tăng. Giá trị trung bình che giấu tail latency. Công bố p95, p99, timeout và retry count theo từng giai đoạn tải.

### 21.2. Cẩn thận với timeout của từng tầng

Query SDK timeout, HTTP server timeout và test runner deadline phải tương thích. Nếu HTTP timeout trước nhưng query phía server vẫn xử lý, concurrency/tải có thể kéo dài hơn điều client quan sát. Cần định nghĩa giới hạn cho từng tầng.

## 22. Đo index backlog và trạng thái dịch vụ

Client polling chỉ cho thấy kết quả cuối cùng từ góc nhìn query. Để đánh giá nguyên nhân, ghép metric của Couchbase Server tương ứng phiên bản:

| Nhóm metric | Câu hỏi |
| --- | --- |
| Index mutation backlog/lag | GSI có đang theo kịp tốc độ mutation không? |
| Index state/build progress | Index có online/hợp lệ khi thử không? |
| Data Service mutation rate | Tải ghi thực tế là bao nhiêu? |
| Query Service latency, timeout/error | Query đang chờ index hay tốn scan/fetch? |
| Query plan / index scan rows | Query có dùng đúng index không? |
| Index/Query CPU, memory, disk I/O | Có nút thắt tài nguyên rõ ràng không? |
| Network/SDK metrics | Client/network có gây trễ không? |
| Retry/cancellation count | Load generator hoặc app có khuếch đại sự cố không? |

Tên metric chính xác, đơn vị, phương thức thu thập và vị trí trong UI/Prometheus có thể thay đổi theo phiên bản Couchbase. Không tự đặt một tên metric rồi coi đó là giao diện chuẩn; phải đối chiếu tài liệu và dashboard của cluster đang chạy.

### 22.1. Liên hệ metric với mốc thí nghiệm

Ghi timestamp giai đoạn baseline, write-heavy, recovery, đồng thời lưu query correlation/request ID. Nếu biểu đồ Index Service tăng backlog ở đúng giai đoạn REQUEST_PLUS p99 tăng, đây là bằng chứng hỗ trợ giả thuyết; vẫn cần xem query plan, network và CPU để tránh quy nguyên nhân đơn giản hóa.

## 23. Spring Data Repository: kiểm chứng đường query phát sinh

Một entity cho thử nghiệm mapping:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    @Field
    private String customerId;

    @Field
    private String status;

    @Field
    private String createdAt;

    @Version
    private Long version;

    public OrderDocument() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String v) { this.customerId = v; }
    public String getStatus() { return status; }
    public void setStatus(String v) { this.status = v; }
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String v) { this.createdAt = v; }
    public Long getVersion() { return version; }
    public void setVersion(Long v) { this.version = v; }
}
~~~

Repository:

~~~java
import java.util.List;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Dùng một test mapping riêng để kiểm tra:

- `findById` theo metadata key thường dùng KV.
- Derived query theo `customerId` chạy SQL++ với index phù hợp.
- `@ScanConsistency` ở method đã được áp dụng tới query options trên version thực.
- Generated SQL++ có thể thêm type discriminator, khác SQL++ SDK raw dùng trong các thí nghiệm trước.
- `@Version` phục vụ CAS, **không** phải mutation token hay freshness metric.

Nếu SDK trực tiếp insert JSON không có trường phân biệt type của Spring Data, Repository có thể không trả document đó dù index đã đủ mới. **Không báo lỗi index lag khi vấn đề là mapping/type filter.**

## 24. CouchbaseTemplate: cấu hình mode trong bài thử

Với `CouchbaseTemplate`, những phiên bản hỗ trợ fluent query cho phép đặt consistency riêng từng lần gọi:

~~~java
import static org.springframework.data.couchbase.core.query.Query.query;
import static org.springframework.data.couchbase.core.query.QueryCriteria.where;

import java.util.List;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;

public class OrderQueryDao {
    private final CouchbaseTemplate template;

    public OrderQueryDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> byCustomer(
            String customerId,
            QueryScanConsistency consistency) {

        Query q = query(where("customerId").is(customerId));

        return template.findByQuery(OrderDocument.class)
                .withConsistency(consistency)
                .matching(q)
                .all();
    }
}
~~~

Có thể dùng:

~~~java
List<OrderDocument> defaultLike = dao.byCustomer(
        customerId, QueryScanConsistency.NOT_BOUNDED);

List<OrderDocument> fresh = dao.byCustomer(
        customerId, QueryScanConsistency.REQUEST_PLUS);
~~~

Mỗi `Query` nên được tạo mới cho từng invocation. Đừng chia sẻ Query mutable rồi để hai worker thay đổi consistency. Với các API version hỗ trợ, `Query.scanConsistency(...)` là lựa chọn khác, nhưng không nên cùng lúc cấu hình hai mức mâu thuẫn và dựa vào precedence không được kiểm chứng.

**Về phạm vi phép đo:** Template phải thực sự phát sinh SQL++ query và không bị cache bọc ngoài. Nếu cần so sánh SDK với Template, hãy ghi rõ **khác biệt về converter, generated SQL++ và overhead mapping** để không gán mọi chênh lệch latency cho index.

## 25. MutationState: correctness test theo những ghi đã biết

Bên cạnh REQUEST_PLUS, Java SDK có thể nhận mutation token từ một KV mutation và tạo `MutationState`:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryResult;

// orders, cluster, id, customerId đã được chuẩn bị.
MutationResult mutation = orders.insert(
        id, JsonObject.create()
                .put("customerId", customerId)
                .put("status", "CREATED"));

if (mutation.mutationToken().isEmpty()) {
    throw new IllegalStateException(
            "Test requires a mutation token");
}

MutationState state = MutationState.from(mutation);

String sql = """
    SELECT META(o).id AS documentId
    FROM `shop`.`sales`.`orders` AS o
    WHERE o.customerId = $customerId
    """;

QueryResult result = cluster.query(
        sql,
        queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .consistentWith(state));
~~~

Trong production, nếu token không có, ứng dụng phải có fallback theo SLO như `REQUEST_PLUS` hoặc chuyển sang KV theo ID; **không tự tạo token từ CAS hay timestamp client**.

### 25.1. Nhiều mutation cần nhiều dấu mốc phù hợp

Nếu request insert hai Order A và B, state chỉ chứa token A không mặc định chứng minh index đã bắt kịp B. Dùng API SDK ghép các mutation result/token cần thiết trong cùng ngữ cảnh keyspace được hỗ trợ và kiểm thử bằng dữ liệu độc lập.

### 25.2. AT_PLUS không tạo snapshot lịch sử

Một Order vừa được ghi rồi bị worker khác đổi status có thể trả giá trị mới hơn khi query consistentWith đã đủ mốc cũ. Consistency theo mutation là **ràng buộc độ tiến index**, không khóa thời điểm của toàn bộ database.

## 26. Kiểm thử reactive: thứ tự completion không thay consistency

Với Spring WebFlux, một lưu đồ reactive có thể nối write rồi query:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Service minh họa:

~~~java
import reactor.core.publisher.Flux;

public Flux<OrderDocument> saveThenQuery(
        OrderDocument newOrder) {

    return reactiveOrders.save(newOrder)
            .flatMapMany(saved ->
                    reactiveOrders.findByCustomerIdAndStatus(
                            saved.getCustomerId(), "CREATED"));
}
~~~

`flatMapMany` đảm bảo Publisher query được subscribe sau khi save phát tín hiệu thành công. Nhưng **Reactive không làm GSI cập nhật ngay**, không giảm mặc định thời gian chờ REQUEST_PLUS và không tạo transaction.

Với integration test reactive, có thể dùng `StepVerifier` ở tầng test để chờ tín hiệu và xác minh row khi query thành công; vẫn phải chuẩn bị index, fixture, cleanup và timeout. Không gọi `block()` trong WebFlux event loop hoặc `subscribe()` fire-and-forget trong service rồi kỳ vọng read-after-write có thứ tự.

## 27. Failure injection và recovery: chỉ trong phòng thử nghiệm

Nếu cần hiểu hệ thống khi Index Service mất khả năng bắt kịp mutation, có thể xây một kịch bản recovery có kiểm soát trong **cluster cô lập**, nhưng không bắt buộc cho correctness test:

- Tạo baseline query/index metrics.
- Áp tải ghi có mức tăng đã định.
- Quan sát backlog, timeout và mức phục hồi.
- Nếu thử node failure/rebalance, có runbook khôi phục, quyền vận hành và giới hạn thời gian.
- Không tác động cluster đang phục vụ khách hàng, và không thực hiện failover chỉ để chứng minh NOT_BOUNDED có thể stale.
- Không coi một node bị lỗi là đại diện cho độ trễ bình thường khi production hoạt động ổn định.

**Mục tiêu tách bạch:** correctness test xác nhận bảo đảm query; stress/failure test xem hệ thống ứng xử thế nào dưới sự cố. Không đổi định nghĩa hợp đồng ở giữa hai nhóm thử.

## 28. Phân biệt kết quả cũ do GSI với cache, replica và Search

| Hiện tượng | Đường điều tra |
| --- | --- |
| KV active path thấy Order, SQL++ NOT_BOUNDED chưa thấy | GSI freshness, `WHERE`, index plan |
| KV thấy Order, SQL++ REQUEST_PLUS thấy, service vẫn trả cũ | Application/HTTP cache, code path |
| SDK direct query đúng, Repository query sai | Type discriminator, converter, keyspace, mapping |
| Hai instance web trả khác | Local caches, route/deployment, topology |
| Replica read trả cũ | Replica lag/semantics riêng của KV replica |
| Search index chưa thấy từ khóa mới | Search/FTS consistency khác SQL++ GSI |
| Ghi bị timeout, không rõ document có tồn tại | Ambiguous mutation, idempotency, KV lookup |
| Query trả 0 rows sau khi bị timeout | Lỗi ứng dụng nuốt exception; không phải “không có Order” |

Đừng dựa vào một client HTTP qua CDN để đo độ trễ Index Service nếu response đang được cache. Bypass mọi result cache trong phép thử GSI; cache freshness cần thí nghiệm riêng.

## 29. Sai lầm thường gặp khi viết benchmark index lag

1. **Chạy một lần và công bố con số chuẩn:** một lần chạy không mô tả phân phối.
2. **Assert NOT_BOUNDED phải stale:** cơ chế không có bảo đảm này.
3. **Dùng `Thread.sleep(100)` làm giải pháp nhất quán:** không có chứng cứ index đã kịp.
4. **Không lưu query plan:** có thể đang đo một index khác.
5. **Để `LIMIT 20` trên dữ liệu nhiều ID:** row thiếu có thể do pagination.
6. **Không phân biệt cache hit:** request có thể chưa tới Couchbase.
7. **Chỉ tính mẫu observed, bỏ censored:** làm đẹp giả tạo thống kê.
8. **Gộp query timeout thành “chưa thấy”:** lẫn lỗi hệ thống với index freshness.
9. **Không dọn fixture:** dữ liệu rác làm méo phân phối và tăng tải.
10. **Dùng customerId chung:** mutation khác thay đổi tập kết quả.
11. **Không ghi write ACK timestamp:** đo cả thời gian insert mà gọi là index lag.
12. **Trộn SDK raw JSON và Repository mapper:** query có thể lọc theo discriminator.
13. **Không theo dõi Index Service:** không biết tình trạng backlog thực.
14. **Benchmark trên production:** rủi ro ảnh hưởng khách hàng/availability.
15. **Tự tạo load vô hạn:** phép đo biến thành sự cố.
16. **Công bố REQUEST_PLUS luôn nhanh/chậm hơn một hằng số:** thiếu căn cứ tải và topology.

Một báo cáo tốt mô tả cả **điều thí nghiệm không thể kết luận**.

## 30. Vận hành và runbook khi kết quả đo bất thường

~~~mermaid
flowchart TD
    A["Probe ghi ACK nhưng query không thấy Order"] --> B{"KV get đúng ID thấy source?"}
    B -->|Không| C["Kiểm tra write ACK, keyspace, TTL, transaction, replica"]
    B -->|Có| D["Bỏ cache, chạy SQL++ trực tiếp"]
    D --> E{"WHERE/filter/index plan hợp lệ?"}
    E -->|Không| F["Sửa query, index, mapping, LIMIT"]
    E -->|Có| G{"Mode REQUEST_PLUS thành công?"}
    G -->|Không, timeout/error| H["Đo index backlog, query timeout, service health"]
    G -->|Có| I["Quan sát NOT_BOUNDED và metrics dưới tải"]
    I --> J["Tổng hợp first-probe hit, censored, p95/p99"]
~~~

Khi kết quả không như dự kiến:

1. Xác minh exact write ACK và keyspace.
2. Đọc active KV source; đừng bắt đầu bằng SQL++ nếu source chưa có.
3. Xác minh SQL++, index state, `EXPLAIN` và filter.
4. Bypass result cache và đảm bảo mỗi probe thực sự gửi query.
5. Kiểm tra REQUEST_PLUS lỗi/timeout trước khi đánh giá lag.
6. Kiểm tra Index Service backlog, node health, CPU/memory/disk.
7. Đối chiếu metric với timeline tải ghi/query.
8. Nếu query chậm do scan/sort/network, đừng quy cho wait-index.
9. So sánh workload với baseline cùng cấu hình.
10. Tạo ticket/cải tiến có bằng chứng, không dùng cảm giác “index hơi chậm”.

## 31. Mẫu báo cáo kết quả chuẩn

Một báo cáo nội bộ nên gồm:

**A. Mục tiêu**

- Correctness: Query REQUEST_PLUS đọc được các write ACK trước mốc query.
- Characterization: Phân phối first-observed time của NOT_BOUNDED.
- Performance: Query p95/p99 và timeout dưới các mức mutation rate.

**B. Môi trường**

~~~text
Server version   : ...
Java SDK version : ...
Spring Data      : ...
Topology         : ...
Keyspace         : shop.sales.orders (test)
Index definition : ...
Query SQL++      : ...
Concurrency      : ...
Write rate       : ...
Query rate       : ...
Timeout          : ...
Cache path       : bypassed
~~~

**C. Kết quả**

| Nhóm | Metric | Giá trị |
| --- | --- | --- |
| Correctness | REQUEST_PLUS pass/fail | Điền sau thử |
| Correctness | MutationState pass/fail khi có token | Điền sau thử |
| Observability | First-probe hit rate | Điền sau thử |
| Observability | Visible within bounded window | Điền sau thử |
| Observability | Censored samples | Điền sau thử |
| Performance | NOT_BOUNDED p95/p99 latency | Điền sau thử |
| Performance | REQUEST_PLUS p95/p99 latency | Điền sau thử |
| Performance | Query timeout/error rate | Điền sau thử |
| Index | Mutation backlog/lag theo giai đoạn | Điền sau thử |
| Capacity | CPU/memory/disk/throughput | Điền sau thử |

**D. Giới hạn kết luận**

- Bounded polling không cung cấp timestamp index update chính xác.
- Kết quả chỉ đại diện workload và topology đã dùng.
- Query thứ hai có thể thấy mutation vì index đã bắt kịp trong khoảng trễ tự nhiên.
- Type discriminator/covering index cần được ghi lại khi so nhiều đường API.
- Nếu có nhiều censored samples, percentile observed time chưa mô tả toàn bộ population.

**E. Hành động**

- Giữ/đổi consistency theo SLO từng endpoint.
- Tối ưu index/query/pagination nếu scan quá tốn tài nguyên.
- Thay query theo field bằng KV khi đã biết ID.
- Điều chỉnh capacity/backpressure/timeout khi có bằng chứng.
- Bổ sung monitoring và test regression cho các luồng yêu cầu freshness.

## 32. Câu hỏi tự kiểm tra

**1. Vì sao một test đòi NOT_BOUNDED phải stale là flaky?** Vì GSI có thể kịp cập nhật; NOT_BOUNDED chỉ không buộc đợi mốc mới.

**2. Correctness test với REQUEST_PLUS cần điều kiện gì?** Write đã ACK, query đúng keyspace/index/filter, không có mutation cạnh tranh, query hoàn tất thành công.

**3. Nếu query REQUEST_PLUS timeout thì assert “không có Order” đúng không?** Không. Timeout là lỗi query; không đồng nghĩa kết quả rỗng.

**4. Polling lần đầu thấy ở 80 ms có nghĩa index lag đúng 80 ms?** Không. Mốc đó gồm độ trễ polling/network/query và chỉ cho một quan sát giới hạn.

**5. Vì sao không đưa LIMIT 20 vào probe có nhiều Order?** Row có thể nằm ngoài trang, làm sai kết luận index chưa thấy.

**6. Khi nào dùng MutationState?** Khi có mutation token hợp lệ và cần query đợi các ghi cụ thể.

**7. Có thể dùng CAS thay mutation token?** Không. CAS bảo vệ ghi cạnh tranh, token mô tả tiến độ mutation cho index consistency.

**8. Tại sao phải lưu EXPLAIN?** Để biết query thật sự dùng index/plan nào trong phép đo.

**9. Cache ảnh hưởng phép đo ra sao?** Cache hit có thể trả row cũ mà không hề thực thi SQL++ mới.

**10. Reactive có làm index update nhanh hơn không?** Không. Nó thay cách điều phối I/O, không thay thời điểm GSI xử lý mutation.

**11. Censored sample là gì?** Một mutation chưa được quan sát trong cửa sổ lấy mẫu đã định; không biết chính xác thời gian nhìn thấy cuối.

**12. Có nên benchmark trên cluster production không?** Không nên; cần môi trường cô lập và giới hạn tải.

## 33. Bài tập thực hành có hướng dẫn

### Bài A — Viết kiểm thử đúng

Từ `RequestPlusReadAfterWriteIT` ở mục 11, bổ sung assert KV get theo ID và kiểm tra SQL++ query parameter. Chạy trên collection test có index online.

**Tiêu chí đạt:** Request_plus query thành công chứa Order, không phụ thuộc việc NOT_BOUNDED có stale hay không.

### Bài B — Lấy mẫu có giới hạn

Chạy `ControlledLagSampler` nhiều vòng với ID/customerId riêng và một deadline cho toàn job. Thu first-probe hit, censored count và phân phối first-observed latency.

**Tiêu chí đạt:** Không còn assertion bắt buộc lag; timeout/error lưu riêng, không ẩn thành “chưa thấy”.

### Bài C — Tăng tải ghi

Trên cluster lab, tạo ba mức mutation rate có kiểm soát. Đo query latency p95/p99, backlog và tỷ lệ first-probe hit.

**Câu hỏi:** Index lag có tăng cùng mutation rate không? Có yếu tố query plan hoặc tài nguyên nào gây nhiễu?

### Bài D — Kiểm thử update

Đổi status `CREATED → PAID`, dùng query theo `status` với index phù hợp. Xác minh REQUEST_PLUS phản ánh membership mới khi không có update cạnh tranh; dùng NOT_BOUNDED chỉ để quan sát thời điểm phát hiện.

### Bài E — Phân biệt cache

Bật Spring Cache cho service list, lấy dữ liệu trước insert và không invalidation, sau đó so:

- SDK direct SQL++ REQUEST_PLUS.
- Service `@Cacheable`.
- Service sau eviction.

**Câu hỏi:** Trường hợp nào là index lag, trường hợp nào là cache stale?

### Bài F — Phân tích dữ liệu bị kiểm duyệt

Trong 500 mutation mẫu (số lượng chỉ là ví dụ yêu cầu bài tập), có một tỷ lệ chưa thấy row trong deadline. Hãy giải thích vì sao percentile chỉ từ các sample observed có thể đánh giá quá tốt tốc độ nhìn thấy index.

### Bài G — Chọn API production

Người dùng cần xem chính Order vừa tạo theo ID, không cần toàn lịch sử. So sánh một lần `findById` với query REQUEST_PLUS theo customerId có index.

**Đáp án định hướng:** Dùng saved representation hoặc KV theo ID; không tự thêm chi phí index chờ cho một key đã biết.

## 34. Checklist trước khi chốt kết quả thí nghiệm

- [ ] Đã định nghĩa rõ correctness test và latency observation là **hai phép thử khác nhau**?
- [ ] Query theo field dùng đúng bucket/scope/collection?
- [ ] Index online, `EXPLAIN` và SQL++ được lưu lại?
- [ ] Fixture có document ID/customerId duy nhất cho từng vòng?
- [ ] Không có mutation cạnh tranh làm thay đổi kết quả?
- [ ] Probe bỏ `LIMIT`/sort gây sai lệch hoặc kiểm soát chúng rõ?
- [ ] KV source check có mặt để phân biệt write với index?
- [ ] Không có cache ứng dụng/HTTP trong đường probe GSI?
- [ ] NOT_BOUNDED **không** bị assert phải stale?
- [ ] REQUEST_PLUS/MutationState được kiểm tra với đúng điều kiện bảo đảm?
- [ ] Lấy mẫu có max probes, deadline, QPS và concurrency giới hạn?
- [ ] Error/timeout được tách khỏi “row not visible”?
- [ ] Đồng hồ đo duration là monotonic, không nhầm wall-clock?
- [ ] First-observed time được gọi đúng tên, không tự đồng nhất index internals?
- [ ] Có công bố censored samples, sampling interval và confidence/giới hạn?
- [ ] Mutation rate, query rate và cluster topology được lưu?
- [ ] Có metric Index backlog/lag, Query p95/p99 và tài nguyên?
- [ ] Đã đo recovery sau khi hạ tải?
- [ ] Không tự tạo benchmark số liệu hoặc suy rộng sang production?
- [ ] Cleanup fixture xử lý cả kết quả write ambiguous?
- [ ] CAS, TTL, transaction, durability và Search được phân biệt riêng?
- [ ] Có runbook khi REQUEST_PLUS timeout hoặc Index Service quá tải?
- [ ] Không làm thí nghiệm gây hại trên production?
- [ ] Báo cáo có kết luận, giới hạn và đề xuất theo SLO?

## 35. Kết luận

**Kiểm thử độ trễ cập nhật chỉ mục bằng tình huống có kiểm soát không đồng nghĩa cố tình buộc SQL++ trả dữ liệu cũ.** Với Couchbase, `NOT_BOUNDED` cho phép index chưa mới nhưng không bắt buộc stale; vì thế hãy dùng nó để **quan sát** trong một cửa sổ lấy mẫu có giới hạn, không dùng assertion buộc phải bỏ sót document. Để kiểm tra **bảo đảm đọc sau ghi**, dùng `REQUEST_PLUS` hoặc `MutationState/consistentWith` với mutation đã ACK, query/index đúng và dữ liệu thử nghiệm không bị thay đổi cạnh tranh.

Trong **Spring Data Couchbase**, cần tách rõ KV theo key, SQL++ qua secondary index, cache và các cơ chế CAS/TTL/transaction. Một kết luận kỹ thuật đáng tin phải có **query plan, fixture, sampling method, dữ liệu censored, timeout/error rate và metric Index Service**, đồng thời chỉ suy rộng trong phạm vi workload đã thử. Làm đúng hai loại phép thử này sẽ giúp nhóm phát triển lựa chọn độ mới theo SLO mà không đánh đổi khả năng vận hành bằng những giả định sai.
