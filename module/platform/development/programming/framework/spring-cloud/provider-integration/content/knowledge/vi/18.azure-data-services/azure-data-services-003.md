# Truy vấn, phân trang và kiểm soát request units

Một truy vấn Cosmos DB có thể chỉ trả vài item trong một lần gọi, dù container còn hàng nghìn item phù hợp. Dịch vụ có thể chia kết quả thành nhiều trang vì giới hạn thời gian thực thi, kích thước response hoặc lượng Request Units (RU) đang sẵn có. Với Spring Data Cosmos, repository và `Pageable` giúp viết truy vấn quen thuộc, nhưng cách phân trang vẫn dựa trên **continuation token** của Cosmos DB. Muốn kiểm soát chi phí và độ trễ, ứng dụng phải hiểu query được định tuyến tới partition nào, mỗi trang tiêu thụ bao nhiêu RU, SDK đang retry ra sao và index có phục vụ đúng predicate hay không.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào Azure Cosmos DB for NoSQL: viết query bằng Spring Data Cosmos, duyệt kết quả theo continuation, đo RU và tối ưu truy vấn theo tải thực tế.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt point read, query theo một partition và cross-partition query.
- Viết derived query và custom Cosmos SQL bằng `@Query`, tham số được bind và predicate có partition key.
- Sử dụng `CosmosPageRequest`, `Pageable` và `Slice` để duyệt continuation token đúng cách.
- Giải thích vì sao một trang có thể chứa ít item hơn page size yêu cầu, số trang thay đổi hoặc có trang rỗng ở tầng SDK.
- Ước lượng và đo RU của từng request/trang; phân biệt RU charge với RU/s throughput.
- Đọc query metrics/index metrics, điều chỉnh indexing policy và parallelism.
- Xử lý 429/throttling, giới hạn concurrency và thiết kế API cursor ổn định.
- Xây dựng kiểm thử truy vấn và workload test có dữ liệu đại diện.

## 2. Từ repository method đến query execution

Với Spring Data Cosmos, repository method thường được thực thi qua `CosmosTemplate` hoặc `ReactiveCosmosTemplate`, rồi xuống Azure Cosmos DB Java SDK. SDK gửi request tới account; dịch vụ lập kế hoạch query, định tuyến partition, thực thi và trả dữ liệu cùng thông tin request.

~~~mermaid
flowchart LR
    A[Application service] --> R[CosmosRepository]
    R --> T[CosmosTemplate]
    T --> S[Cosmos DB Java SDK]
    S --> Q[Query planner]
    Q --> P1[Partition range A]
    Q --> P2[Partition range B]
    Q --> P3[Partition range C]
    P1 --> M[Merge results / continuation]
    P2 --> M
    P3 --> M
    M --> S
    S --> T
    T --> R
    R --> A
~~~

Nếu query có filter bằng partition key value, SDK thường có thể định tuyến tới partition tương ứng. Nếu không có partition predicate phù hợp, query có thể được thực hiện trên nhiều partition rồi SDK tổng hợp/merge kết quả. Với `ORDER BY` cross-partition, kết quả từ các partition phải được merge theo thứ tự toàn cục.

Một truy vấn được chia thành nhiều lần thực thi; mỗi lần có thể trả một phần kết quả và request charge riêng. Vì vậy, “repository method được gọi một lần” không đồng nghĩa “dịch vụ chỉ nhận một request”. Một query có thể tạo nhiều round trip do số item, page size, RU khả dụng hoặc giới hạn thực thi.

## 3. Chọn đường đọc trước khi tối ưu query

Với một item đã biết, ưu tiên **point read** bằng container, item ID và partition key. Khi cần nhiều item, query theo partition key là bước tiếp theo; query không có partition predicate thường có phạm vi rộng hơn.

| Kiểu truy cập | Thông tin cần | Đặc điểm |
| --- | --- | --- |
| **Point read** | Item ID + partition key value | Thường ít RU và độ trễ thấp nhất cho một item đã biết |
| **Query trong một logical partition** | Predicate có partition key equality | Tránh fan-out tới các partition không liên quan |
| **Query có filter nhưng không biết partition key** | Predicate trên field khác | Có thể phải dò nhiều partition; chi phí tùy index và dữ liệu |
| **Cross-partition query** | Query không giới hạn một partition key value | SDK điều phối nhiều partition và merge kết quả |
| **Scan hoặc truy vấn không tận dụng index** | Query shape/index không phù hợp | Có thể đọc nhiều item hơn số kết quả cuối cùng |

Ví dụ: với container partition key path `/tenantId`, truy vấn đơn hàng của một tenant nên có điều kiện `tenantId = @tenantId`. Nếu màn hình báo cáo cần lấy mọi đơn hàng đã thanh toán trên toàn hệ thống, cross-partition query có thể là yêu cầu hợp lệ; cần đo RU, giới hạn phạm vi thời gian và cân nhắc read model riêng cho báo cáo.

## 4. Viết query có tham số trong Spring Data Cosmos

### 4.1. Derived query

Giả sử entity `OrderDocument` có các field `tenantId`, `status` và `createdAt`. Repository có thể khai báo:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;
import java.time.Instant;
import java.util.List;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    List<OrderDocument> findByTenantIdAndCreatedAtAfter(
        String tenantId, Instant from);
}
~~~

Spring Data Cosmos phân tích tên method để tạo query. Các property trong method name phải khớp mapping của entity. Derived query thuận tiện cho điều kiện đơn giản, nhưng cần kiểm tra query được sinh ra và partition routing; đừng giả định mọi từ khóa của Spring Data JPA đều có cùng semantics hoặc được hỗ trợ trong Cosmos.

### 4.2. Custom query bằng `@Query`

Khi cần kiểm soát predicate, projection hoặc thứ tự, khai báo Cosmos SQL query:

~~~java
import com.azure.spring.data.cosmos.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    @Query("""
        SELECT * FROM c
        WHERE c.tenantId = @tenantId
          AND c.status = @status
        ORDER BY c.createdAt DESC, c.id ASC
        """)
    Slice<OrderDocument> findRecentOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status,
        Pageable pageable);
}
~~~

Đây là query language của **Cosmos DB for NoSQL**, không phải JPQL. `@Param` bind giá trị vào query; không nối chuỗi do người dùng nhập trực tiếp vào câu SQL. Predicate `tenantId = @tenantId` giúp giới hạn truy vấn theo partition key. `ORDER BY` nhiều thuộc tính có thể cần **composite index** tương ứng; nếu index chưa phù hợp, dịch vụ có thể trả lỗi yêu cầu index hoặc query tốn tài nguyên hơn dự kiến.

### 4.3. Projection: chỉ đọc dữ liệu cần thiết

Nếu trang danh sách chỉ hiển thị ID, trạng thái, tổng tiền và ngày tạo, không cần tải toàn bộ item có nhiều nested object. Có thể dùng projection/query phù hợp với phiên bản Spring Data Cosmos đang sử dụng.

Ví dụ query chỉ chọn field:

~~~sql
SELECT c.id, c.tenantId, c.status, c.total, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
ORDER BY c.createdAt DESC, c.id ASC
~~~

Kiểu kết quả phải được ánh xạ tương ứng (projection interface/DTO hoặc model riêng theo khả năng thư viện). Không trả persistence entity chứa field nội bộ trực tiếp ra public API. Giảm payload có thể giảm chi phí truyền và xử lý document, nhưng RU thực tế vẫn cần đo theo query plan, index và dữ liệu.

## 5. Phân trang trong Cosmos DB dựa trên continuation token

### 5.1. Page size là giới hạn tối đa, không phải cam kết số item

Cosmos DB có thể chia query result thành nhiều trang vì:

- Không còn đủ RU tại thời điểm thực thi để trả thêm item.
- Response chạm giới hạn kích thước.
- Một lần thực thi chạm giới hạn thời gian.
- Query engine chọn chia nhỏ để xử lý hiệu quả hơn.

Page size/`MaxItemCount` chỉ biểu thị **số item tối đa** cho một lần thực thi. Dịch vụ có thể trả ít hơn. Cùng một query và cùng page size có thể có số trang khác nhau ở những lần chạy khác nhau, ví dụ khi throughput bị throttling hoặc kích thước response thay đổi. Ở tầng SDK, đôi khi có thể nhận một trang rỗng nhưng vẫn còn continuation token; chỉ dừng khi không còn trang tiếp theo.

Do đó, không viết logic:

~~~java
if (page.getContent().size() < requestedPageSize) {
    // Sai: không thể kết luận đã hết dữ liệu chỉ từ số item.
}
~~~

Hãy dùng `Slice.hasNext()`, continuation token hoặc trạng thái iterator của SDK theo đúng abstraction đang sử dụng.

### 5.2. CosmosPageRequest mang continuation token

Spring Data Cosmos hỗ trợ `Pageable`, `Slice` và `Sort`. Với pagination của Cosmos, dùng `CosmosPageRequest` để truyền page size và continuation token:

~~~java
import com.azure.spring.data.cosmos.core.query.CosmosPageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

int pageSize = 50;
Pageable request = new CosmosPageRequest(0, pageSize, null);

Slice<OrderDocument> slice =
    repository.findRecentOrders("tenant-42", "PAID", request);

while (true) {
    process(slice.getContent());

    if (!slice.hasNext()) {
        break;
    }

    Pageable nextRequest = slice.nextPageable();
    slice = repository.findRecentOrders(
        "tenant-42", "PAID", nextRequest);
}
~~~

Trang đầu dùng continuation token `null`. Khi gọi `nextPageable()`, Spring Data Cosmos tạo request tiếp theo chứa token cần thiết để tiếp tục query. **Dùng pageable trả về từ slice trước**, không tự tính `PageRequest.of(pageNumber, pageSize)` rồi giả định Cosmos sẽ nhảy tới offset tương ứng.

Ví dụ trên xử lý từng trang rồi giải phóng dữ liệu sau khi xử lý, thay vì tích lũy toàn bộ kết quả vào một `List` lớn. Nếu cần trả dữ liệu ra API, hãy chuyển từng trang thành response DTO và chỉ giữ cursor cho lần gọi tiếp theo.

### 5.3. Slice hay Page?

Spring Data Cosmos hỗ trợ cả `Page` và `Slice` với pageable query. Chọn theo nhu cầu giao diện:

| Kiểu | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| **Slice<T>** | Chỉ cần biết còn trang tiếp theo hay không | Thường phù hợp với API cursor/infinite scroll; không yêu cầu tổng số item để hiển thị |
| **Page<T>** | Giao diện thực sự cần thông tin page abstraction của Spring Data | Số item mỗi lần trả về vẫn có thể nhỏ hơn requested size; không suy ra tổng dữ liệu từ page index × size |
| **Iterator/Feed API của SDK** | Cần điều khiển continuation, request options hoặc diagnostics ở mức thấp | Adapter phải quản lý vòng lặp, cancellation và lifecycle của response |

Tài liệu Spring Data Cosmos lưu ý số item trả về có thể nhỏ hơn kích thước yêu cầu theo lượng RU khả dụng; vì vậy không nên dựa vào tổng page size để kết luận đã đọc hết. Nếu giao diện cần **tổng số kết quả chính xác**, phải thiết kế một count query riêng và tính cả RU/latency của nó; không mặc định count miễn phí hoặc luôn được gộp với truy vấn danh sách.

### 5.4. Continuation token là cursor opaque

Continuation token là bookmark do Cosmos DB/SDK tạo để tiếp tục query. Ứng dụng không nên phân tích hoặc tự sửa nội dung token. Với Java SDK, token có thể được lưu và dùng lại để tiếp tục query; tài liệu dịch vụ nêu token có thể dùng lại khi tiếp tục bằng cùng SDK version.

Nếu public API trả cursor:

1. Đóng gói token cùng query/filter/sort version và tenant scope đã xác thực.
2. Ký hoặc bảo vệ cursor để caller không sửa token/context.
3. Kiểm tra cursor thuộc đúng tenant và đúng truy vấn hiện tại.
4. Không cho caller tự gửi partition key hoặc query text tùy ý để sử dụng token.
5. Xử lý token không hợp lệ hoặc không còn tương thích bằng lỗi cursor rõ ràng và hướng dẫn bắt đầu lại.

Cursor không phải ID nghiệp vụ, không phải quyền truy cập dữ liệu và cũng không đảm bảo một snapshot bất biến nếu item thay đổi trong lúc client duyệt nhiều trang. Nếu dữ liệu có thể cập nhật liên tục, hãy xác định semantics của danh sách (best-effort, theo thời điểm, theo revision) và dùng sort ổn định với tie-breaker duy nhất khi phù hợp.

### 5.5. Không dùng offset sâu như phân trang quan hệ

`OFFSET LIMIT` có thể hữu ích cho một số query, nhưng phân trang sâu bằng offset thường buộc query phải xử lý/loại bỏ các item đứng trước vị trí cần lấy. Với danh sách dài hoặc cross-partition, chi phí và latency có thể tăng. Dùng continuation token để đi tuần tự qua kết quả thường phù hợp hơn.

Không phải mọi query shape đều hỗ trợ continuation giống nhau. Các truy vấn `GROUP BY` và `DISTINCT` có giới hạn continuation; Cosmos DB cho phép trường hợp `DISTINCT` kết hợp `ORDER BY` theo hướng dẫn dịch vụ. Với aggregate, grouping hoặc báo cáo phức tạp, kiểm tra khả năng paging của query cụ thể trước khi thiết kế public cursor.

## 6. RU là chi phí của từng request, không phải kích thước trang

**Request Unit (RU)** chuẩn hóa tài nguyên xử lý như CPU, I/O và bộ nhớ mà một thao tác Cosmos DB sử dụng. RU là chi phí của request; **RU/s** là throughput khả dụng/cấp phát theo thời gian. Không thể suy ra RU chỉ từ số item trả về.

Chi phí query phụ thuộc:

- Kích thước dữ liệu nguồn và số item được đọc.
- Kích thước và số lượng item trả về.
- Số predicate, loại predicate và khả năng sử dụng index.
- Số lookup/scan trên index, document loading và parsing.
- Projection, user-defined function và sort/aggregation.
- Page size, số page/round trip và việc query có phải fan-out qua partition hay không.
- Consistency level, số region và tải đồng thời của account/container.

Một query trả 20 item có thể tốn nhiều RU hơn query khác trả 100 item nếu query đầu phải scan nhiều dữ liệu, dùng predicate không hiệu quả hoặc truy cập nhiều partition. Ngược lại, page nhỏ hơn không nhất thiết làm tổng RU thấp hơn; nó có thể tạo thêm round trip và tổng chi phí vẫn tương tự hoặc tăng.

### 6.1. Tính tổng RU qua các trang

Mỗi lần thực thi query trả request charge của lần đó. Nếu một query được chia thành 4 trang, tổng RU của lần duyệt là:

[
RU_{total} = RU_1 + RU_2 + RU_3 + RU_4
]

Ví dụ minh họa:

| Trang | Item trả về | RU charge |
| --- | ---: | ---: |
| 1 | 50 | 8.2 |
| 2 | 38 | 7.1 |
| 3 | 50 | 8.4 |
| 4 | 12 | 3.5 |
| **Tổng** | **150** | **27.2 RU** |

Đây chỉ là số giả định để minh họa cách cộng. Khi đo thật, lấy request charge từ response/diagnostics của SDK hoặc Spring Data integration phù hợp. Không lấy `pageSize × một RU cố định` làm công thức dự toán.

### 6.2. Page size ảnh hưởng điều gì?

| Page size nhỏ | Page size lớn |
| --- | --- |
| Response nhỏ hơn và ít item cần giữ trong bộ nhớ mỗi lần | Có thể giảm số lần round trip khi throughput và response limit cho phép |
| Có thể tăng số trang, số lần request và tổng latency do nhiều round trip | Response lớn hơn, tăng memory/buffer và thời gian xử lý một trang |
| Hữu ích cho API tương tác cần trả nhanh một phần kết quả | Hữu ích cho batch/worker xử lý theo lô nếu đã giới hạn concurrency |
| Không bảo đảm tổng RU thấp hơn | Không bảo đảm chỉ có một request hoặc luôn trả đủ page size |

Hãy chọn page size dựa trên latency mục tiêu, kích thước item, concurrency, bộ nhớ và RU khả dụng. Đo nhiều giá trị page size với workload đại diện thay vì chọn số lớn nhất.

## 7. Indexing và hình dạng query

Cosmos DB for NoSQL mặc định có indexing policy tự động trên nhiều property. Index giúp query lọc và sắp xếp hiệu quả, nhưng mỗi property được index có thể làm tăng RU của write/update và dung lượng index.

### 7.1. Predicate có thể dùng index

Ví dụ query:

~~~sql
SELECT c.id, c.status, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
  AND c.createdAt >= @from
ORDER BY c.createdAt DESC
~~~

Kiểm tra:

- `tenantId` có phải partition key và có predicate equality không?
- Các field filter/sort có nằm trong indexing policy phù hợp không?
- Có thể giảm projection thay vì `SELECT *` không?
- Query có gọi UDF hoặc expression làm giảm khả năng tận dụng index không?
- Thứ tự sort có ổn định và có index cần thiết không?

### 7.2. Composite index cho nhiều trường ORDER BY

Query `ORDER BY c.createdAt DESC, c.id ASC` có thể yêu cầu composite index theo thứ tự và hướng sort tương ứng. Nếu thiếu index, Cosmos DB có thể trả lỗi yêu cầu tạo composite index. Hãy thêm index bằng IaC/deployment quản lý container và chờ index transformation hoàn tất trước khi phụ thuộc vào query mới.

### 7.3. Giảm chi phí write bằng indexing có chủ đích

Nếu container write-heavy và có nhiều field không bao giờ được lọc/sort, có thể xem xét exclude các path đó khỏi indexing policy. Đổi lại, query dựa vào path bị exclude có thể cần scan hoặc không chạy nếu scan không được cho phép. Không loại bỏ index chỉ dựa vào cảm giác; lập ma trận query thực tế trước khi sửa.

## 8. Đọc query metrics và index metrics

Khi query chậm hoặc RU cao, bật metrics để phân biệt thời gian xử lý ở query engine, đọc document, index lookup và truyền dữ liệu. Azure Spring Data Cosmos hỗ trợ cấu hình **query metrics**, **index metrics**, response diagnostics, degree of parallelism và số item được buffer thông qua `CosmosConfig` ở các phiên bản hỗ trợ.

Ví dụ phần cấu hình trong lớp kế thừa `AbstractCosmosConfiguration` khi ứng dụng **tự sở hữu cấu hình Cosmos**:

~~~java
import com.azure.spring.data.cosmos.config.CosmosConfig;

@Override
public CosmosConfig cosmosConfig() {
    return CosmosConfig.builder()
        .enableQueryMetrics(true)
        .enableIndexMetrics(true)
        .maxDegreeOfParallelism(-1)
        .maxBufferedItemCount(-1)
        .build();
}
~~~

Đây là đoạn cấu hình cho custom `AbstractCosmosConfiguration`, không phải YAML property tự động áp dụng cho mọi Spring Cloud Azure starter version. Nếu starter đang auto-configure client/template, dùng các property được tài liệu **đúng version** hỗ trợ hoặc custom bean/config có chủ đích; tránh tạo hai bộ client/template cạnh tranh.

### 8.1. Query metrics cần đọc gì?

Các chỉ số query execution có thể bao gồm:

| Metric | Cách diễn giải |
| --- | --- |
| **TotalTime** | Tổng thời gian xử lý query ở các phase được đo |
| **QueryPreparationTime** | Thời gian chuẩn bị/biên dịch query |
| **IndexLookupTime** | Thời gian ở lớp index |
| **DocumentLoadTime** | Thời gian tải document |
| **RuntimeExecutionTime / VMExecutionTime** | Thời gian thực thi phần query runtime |
| **RetrievedDocumentCount** | Số document được lấy để xử lý |
| **OutputDocumentCount** | Số document cuối cùng trả ra |
| **RetrievedDocumentSize / OutputDocumentSize** | Dung lượng dữ liệu được đọc và trả về |
| **IndexHitRatio** | Tỷ lệ index hit theo metric được SDK cung cấp |

Nếu **RetrievedDocumentCount** lớn hơn nhiều **OutputDocumentCount**, query có thể đang đọc nhiều item hơn cần thiết; kiểm tra predicate, index và partition scope. Nếu thời gian network lớn nhưng server query time thấp, tối ưu query engine chưa chắc giải quyết latency; xem region, connectivity và số round trip.

### 8.2. Index metrics

Index metrics giúp xác định index hiện tại được sử dụng ra sao và có path nào có thể cần index bổ sung. Bật trong môi trường điều tra vì việc thu thập metrics có overhead; không nhất thiết bật liên tục cho mọi request production. Dùng kết quả để đề xuất index, sau đó đo lại cả RU của query và chi phí write sau khi thay indexing policy.

### 8.3. Response diagnostics

Spring Data Cosmos hỗ trợ `ResponseDiagnosticsProcessor` để xử lý diagnostics từ response. Có thể dùng callback này để ghi nhận thông tin an toàn như operation, duration, request charge, activity ID và retry context. Không log toàn bộ item hoặc dữ liệu nhạy cảm. Nếu log diagnostics chi tiết trên mọi request, log volume và chi phí quan sát có thể tăng đáng kể.

## 9. Parallel query và giới hạn tài nguyên client

Với cross-partition query, SDK có thể thực thi song song trên nhiều partition. Spring Data Cosmos cho phép cấu hình:

- **maxDegreeOfParallelism:** số operation đồng thời trong quá trình query; giá trị âm như `-1` cho phép SDK tự chọn mức phù hợp.
- **maxBufferedItemCount:** số item tối đa được buffer phía client trong parallel query; giá trị âm cho SDK tự quyết định.
- **responseContinuationTokenLimitInKb:** giới hạn kích thước continuation token trong cấu hình hỗ trợ; giới hạn nhỏ hơn có thể làm query tốn thêm round trip/RU.

Tăng parallelism có thể giảm wall-clock latency cho query fan-out, nhưng không tự giảm tổng RU. Nó có thể tăng số request đồng thời, memory, buffer và áp lực lên throughput. Đặt buffer quá lớn có nguy cơ tăng heap; parallelism quá cao có thể làm workload khác bị throttling.

Chọn theo workload:

| Workload | Cách bắt đầu |
| --- | --- |
| API point read hoặc query một partition | Giữ parallelism mặc định; tối ưu query trước |
| Báo cáo cross-partition chạy nền | Thử parallelism có giới hạn và đo throughput/latency |
| Nhiều request người dùng đồng thời | Giới hạn concurrency ở application/service, tránh mỗi request mở một fan-out lớn |
| Batch export lớn | Duyệt continuation từng trang, stream kết quả ra file/sink, giới hạn buffer |

Không chạy `findAll()` trên container lớn trong HTTP request chỉ để export toàn bộ dữ liệu. Dùng background job, checkpoint và giới hạn throughput/concurrency.

## 10. 429 và kiểm soát request rate

Cosmos DB trả **429 Too Many Requests** khi request vượt throughput khả dụng hoặc một partition/range bị quá tải. Java SDK có retry/backoff theo service retry-after cho các lỗi throttling phù hợp; vì vậy một số 429 có thể xuất hiện trong Azure Monitor nhưng không được ném trực tiếp lên application nếu retry thành công.

Một tỷ lệ 429 nhỏ có thể là dấu hiệu throughput đang được sử dụng hiệu quả nếu end-to-end latency vẫn đạt SLA và tải phân phối đều. Tuy nhiên, tổng tỷ lệ thấp không loại trừ một hot partition: phải xem metrics theo partition key range và latency thực tế.

Khi gặp 429:

1. Xem tổng request, tỷ lệ 429 và normalized RU consumption trên Azure Monitor.
2. Phân tích theo database, container, operation type, region và partition key range.
3. Xác định query/operation nào tiêu thụ nhiều RU, không chỉ nhìn tổng RU/s.
4. Giảm fan-out, tối ưu predicate/index/projection và giới hạn concurrency.
5. Điều chỉnh provisioned throughput/autoscale khi workload thực sự cần thêm capacity.
6. Kiểm tra retry ở SDK, application và message worker để tránh retry chồng.

**Không retry vô hạn ở repository/service** hoặc bỏ qua retry-after. Nếu SDK đã tự retry, thêm một tầng retry lớn có thể nhân số lần request và kéo dài latency. Lỗi permission/configuration không được sửa bằng cách tăng RU.

## 11. Đưa RU và cursor vào API ứng dụng

Application service không nên để controller phụ thuộc trực tiếp vào `CosmosPageRequest` hoặc SDK response. Có thể tạo response model của ứng dụng:

~~~java
import java.util.List;

public record CursorPage<T>(
    List<T> items,
    String nextCursor
) {}
~~~

Ở adapter/persistence boundary:

1. Nhận cursor đã được application kiểm tra chữ ký và tenant context.
2. Giải mã continuation token và tạo `CosmosPageRequest`.
3. Thực hiện repository query với cùng filter, sort và partition scope.
4. Nếu `Slice.hasNext()`, lấy `nextPageable()` và continuation token để tạo cursor tiếp theo.
5. Chuyển entity thành DTO, trả `CursorPage` cho application/controller.

Cursor public nên là opaque token do ứng dụng quản lý. Có thể đóng gói version của query, hash filter/sort, tenant scope và continuation token rồi ký HMAC hoặc mã hóa. Không cho caller thay đổi tenant/filter mà vẫn tái sử dụng continuation của truy vấn trước. Không ghi continuation token vào log công khai.

### 11.1. Khi nào cần tổng số item?

Một số UI muốn hiển thị “1–50 trên tổng 2.000”. Cosmos DB có thể chạy count query, nhưng count trên nhiều partition có thể tốn RU và latency. Nếu tổng số chính xác không thực sự cần, dùng cursor/Slice với nút “Tải thêm” hoặc infinite scroll.

Nếu cần tổng số:

- Chạy count query có phạm vi filter/partition rõ ràng.
- Đo RU riêng của count và tính vào ngân sách.
- Cache hoặc duy trì aggregate/counter nếu nghiệp vụ chấp nhận eventual consistency.
- Không chạy count lại cho mỗi lần tải trang nếu có thể dùng giá trị đã tính.

## 12. Chiến lược kiểm thử query và RU

### 12.1. Unit test

Mock repository để kiểm tra application service truyền đúng tenant, filter, sort và page/cursor. Unit test không đo RU thật và không chứng minh query được định tuyến đúng trong Cosmos DB.

### 12.2. Integration test với Emulator

Cosmos DB Emulator phù hợp để kiểm tra mapping, query syntax, repository method, continuation flow cơ bản và kết quả dữ liệu. Dữ liệu test nên bao gồm nhiều partition key value, nhiều trạng thái, thời gian và item size khác nhau.

Emulator không phải môi trường capacity benchmark production. RU, throttling, multi-region, account throughput và partition distribution có thể khác cloud thật; không dùng số RU từ emulator để chốt ngân sách production.

### 12.3. Cloud performance test

Chạy workload trên Azure test account với:

- Dataset có số lượng, kích thước item và skew gần production.
- Tỷ lệ point read/query/write và concurrency thực tế.
- Query có/không có partition predicate.
- Page size nhỏ/vừa/lớn và số trang tương ứng.
- Indexing policy đại diện cho deployment.
- Provisioned throughput/autoscale/serverless tương ứng mục tiêu.

Đo các giá trị:

| Chỉ số | Mục đích |
| --- | --- |
| RU/query và RU/page | Chi phí thao tác |
| Tổng RU của một lượt duyệt | Ngân sách của use case |
| p50/p95/p99 latency | Trải nghiệm người dùng |
| Số trang và item/page thực tế | Hiệu quả pagination |
| 429 count/ratio và retry count | Mức bão hòa throughput |
| Normalized RU theo partition range | Phát hiện hot partition |
| Retrieved/output document count | Phát hiện query đọc thừa |
| Heap/buffer và số request đồng thời | Giới hạn tài nguyên client |

Sau mỗi thay đổi query hoặc index, chạy lại cùng workload và so sánh trước/sau. Một query giảm latency nhưng tăng RU hoặc memory có thể không phải lựa chọn tốt cho production.

## 13. Quy trình tối ưu một query chậm

~~~mermaid
flowchart TD
    A[Chọn query chậm / RU cao] --> B[Đo RU, latency và page count]
    B --> C{Point read có thể thay query?}
    C -->|Có| D[Đổi sang ID + partition key]
    C -->|Không| E[Kiểm tra partition predicate]
    E --> F{Có fan-out không cần thiết?}
    F -->|Có| G[Thu hẹp partition scope / read model]
    F -->|Không| H[Kiểm tra index metrics và query metrics]
    G --> H
    H --> I[Giảm projection, tối ưu filter/order/index]
    I --> J[Điều chỉnh page size và concurrency]
    J --> K[Load test và so sánh RU/p95/429]
    K --> L{Đạt ngân sách và SLA?}
    L -->|Không| H
    L -->|Có| M[Ghi nhận baseline và alert]
~~~

Thứ tự điều tra giúp tránh tăng throughput trước khi biết query đang đọc gì. Nếu query scan nhiều item do thiếu index, tăng RU có thể làm nó chạy nhanh hơn nhưng vẫn trả chi phí cao. Nếu query đã tối ưu mà traffic vượt năng lực được cấp, lúc đó mới xem xét tăng throughput hoặc autoscale.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dừng khi page có ít item hơn page size | Bỏ sót dữ liệu còn ở continuation tiếp theo | Dựa vào `Slice.hasNext()` hoặc continuation token |
| Dùng `PageRequest.of(pageNumber, size)` để nhảy sâu | Không có continuation tương ứng; semantics offset không giống database quan hệ | Dùng `CosmosPageRequest` và pageable trả về từ trang trước |
| Query không có partition predicate | Fan-out, tăng RU và latency | Đưa partition value vào filter nếu access pattern cho phép |
| `SELECT *` cho màn hình chỉ cần vài field | Tăng payload/document processing | Dùng projection phù hợp |
| Tăng page size để giảm RU | Có thể tăng response, memory và latency; RU tổng không chắc giảm | Đo nhiều page size và tổng RU |
| Tăng parallelism không giới hạn | Tăng buffer/concurrency, dễ throttling | Đặt giới hạn và đo tải |
| Chạy count query mỗi lần tải trang | RU và latency tăng | Dùng Slice/cursor; count riêng khi thật sự cần |
| Bật index cho mọi field mà không kiểm tra | Write RU và index storage tăng | Index theo query pattern |
| Tắt index để giảm write mà không kiểm thử query | Query scan hoặc không thực thi như mong đợi | Dùng index metrics và workload test |
| Retry 429 ở nhiều tầng | Tăng request volume và latency | Tôn trọng retry-after, đặt retry budget |
| Dùng emulator để chốt RU production | Dự toán sai do môi trường khác | Cloud performance test với dữ liệu đại diện |

## 15. Bài tập thực hành

**Bài tập 1 — So sánh query shape.** Container `orders` dùng partition key `/tenantId`. So sánh RU/latency kỳ vọng của point read theo ID + tenant, query theo tenant/status và query chỉ theo status. Giải thích vì sao query thứ ba có thể fan-out.

**Bài tập 2 — Viết repository query.** Viết method `Slice<OrderDocument>` với `@Query`, filter tenant/status và `ORDER BY createdAt DESC, id ASC`. Nêu composite index cần kiểm tra và cách bind tham số an toàn.

**Bài tập 3 — Duyệt continuation.** Viết vòng lặp với `CosmosPageRequest` bắt đầu bằng token null, xử lý từng `Slice` và lấy `nextPageable()`. Giải thích vì sao không thể dừng chỉ vì page hiện tại có 17 item trong khi size yêu cầu là 50.

**Bài tập 4 — Thiết kế API cursor.** Tạo response `CursorPage<T>` và cursor opaque gồm continuation token, tenant, query version và sort. Đề xuất cách ký/bảo vệ cursor và kiểm tra tenant ở request tiếp theo.

**Bài tập 5 — RU budget.** Một màn hình cần 5 trang, RU lần lượt là 7, 8, 6, 9 và 4. Tính tổng RU của một lượt duyệt; nếu 1.000 lượt/giờ thì ước lượng RU/giờ trước khi cộng các thao tác khác. Giải thích vì sao page size không thể dùng làm công thức tính RU.

**Bài tập 6 — Chẩn đoán query chậm.** Query trả 30 item nhưng metrics cho thấy RetrievedDocumentCount là 12.000, IndexHitRatio thấp và p95 tăng. Hãy kiểm tra predicate, index, cross-partition scope, projection và dữ liệu thực tế; đề xuất thứ tự thay đổi.

**Bài tập 7 — 429 và parallelism.** Một query báo cáo cross-partition bị 429 khi chạy song song. Thiết kế thử nghiệm với maxDegreeOfParallelism và maxBufferedItemCount khác nhau; đo RU tổng, p95, heap, 429 ratio và normalized RU theo partition range.

**Bài tập 8 — Count và pagination.** Product owner yêu cầu tổng số đơn hàng chính xác trên mỗi trang. Hãy phân tích chi phí count query, độ mới dữ liệu và phương án thay thế bằng Slice/cursor hoặc aggregate projection.

## 16. Ghi nhớ

- **Query có partition predicate** thường giảm fan-out; point read bằng ID + partition key là lựa chọn ưu tiên khi đã biết một item.
- `CosmosPageRequest` dùng **continuation token**. Hãy dùng `nextPageable()` từ kết quả trước; không coi page number/offset là cách nhảy trang tùy ý.
- Page size là **số item tối đa**, không phải số item được bảo đảm. Dịch vụ có thể trả ít hơn hoặc chia nhiều trang; tiếp tục cho tới khi hết continuation.
- **RU được tính theo request/page và query execution**, không theo số item đơn thuần. Tổng RU của một lượt duyệt là tổng charge các trang.
- Query metrics và index metrics giúp phân biệt scan, index lookup, document load, network và chi phí trả kết quả. Bật metrics có chọn lọc và bảo vệ diagnostics.
- Page size, parallelism và buffer là các nút điều khiển latency/concurrency/memory; tăng chúng không tự giảm tổng RU.
- SDK tự retry một số 429 theo retry-after; theo dõi tỷ lệ throttling, normalized RU theo partition và end-to-end latency, tránh retry chồng nhiều tầng.
- Kiểm thử query bằng Emulator cho tính đúng đắn; dùng Azure test account với dữ liệu/tải đại diện để đo RU, quota, 429 và p95 trước khi chốt cấu hình production.

## 17. Tài liệu tham khảo

- [Azure Spring Data Cosmos — repository, Pageable, Slice, CosmosPageRequest và query metrics](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [CosmosPageRequest API](https://learn.microsoft.com/en-us/java/api/com.azure.spring.data.cosmos.core.query.cosmospagerequest?view=azure-java-stable)
- [Pagination in Azure Cosmos DB](https://learn.microsoft.com/en-us/cosmos-db/query/pagination)
- [Tuning query performance and reading query metrics](https://learn.microsoft.com/en-us/azure/cosmos-db/query-metrics)
- [Request Units as a throughput and performance currency](https://learn.microsoft.com/en-us/azure/cosmos-db/request-units)
- [Understanding Request Units Consumption](https://learn.microsoft.com/en-us/azure/cosmos-db/understand-request-unit-consumption)
- [Troubleshoot request rate too large (429)](https://learn.microsoft.com/en-us/azure/cosmos-db/troubleshoot-request-rate-too-large)
- [Monitor request unit usage](https://learn.microsoft.com/en-us/azure/cosmos-db/monitor-request-unit-usage)
