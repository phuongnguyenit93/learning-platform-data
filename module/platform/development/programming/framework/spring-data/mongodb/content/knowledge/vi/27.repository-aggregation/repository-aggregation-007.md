# Stream hoặc Flux kết quả và đóng cursor

## 1. Bài toán: báo cáo aggregation có rất nhiều kết quả

Hệ thống thương mại điện tử cần xuất báo cáo doanh thu theo từng mã sản phẩm (SKU) cho một cửa hàng. Nếu cửa hàng có hàng chục nghìn SKU, kết quả của pipeline **$group** có thể rất lớn. Việc repository trả toàn bộ báo cáo dưới dạng **List** khiến ứng dụng phải vật hóa nhiều object trước khi bắt đầu xử lý, tăng áp lực bộ nhớ và kéo dài thời gian tạo file xuất.

Spring Data MongoDB cung cấp hai mô hình tiêu thụ tăng dần:

- **Java Stream<T>** trong repository/MongoTemplate **đồng bộ**. Stream thường dựa trên MongoDB cursor; **phải đóng Stream** sau khi dùng để giải phóng tài nguyên.
- **Reactor Flux<T>** trong repository/ReactiveMongoTemplate **reactive**. Flux phát kết quả khi có subscriber, hỗ trợ backpressure/cancellation; resource lifecycle được phối hợp qua reactive driver và subscription.

Điểm cốt lõi: **trả Stream hoặc Flux không làm cho mọi stage aggregation đều có khả năng xử lý từng record mà không cần bộ nhớ**. Những stage như $group, $sort có thể cần xử lý nhiều dữ liệu trên server trước khi phát phần tử đầu tiên. Streaming chủ yếu giúp ứng dụng **không bắt buộc giữ toàn bộ kết quả đầu ra trong RAM**, đồng thời cần quản lý cursor đúng cách.

Bài **Stream hoặc Flux kết quả và đóng cursor** thuộc chương **Aggregation repository** của module **SPRING_DATA_MONGODB**. Module sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua MongoTemplate hoặc repository, đồng thời thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Sau bài học, bạn có thể:

1. Chọn giữa **List**, **Stream**, **Slice**, **Flux** theo nhu cầu.
2. Định nghĩa repository **@Aggregation** trả **Stream<DTO>** hoặc **Flux<DTO>**.
3. Sử dụng **try-with-resources** để đóng cursor đồng bộ, kể cả khi xử lý bị dừng sớm hoặc ném exception.
4. Hiểu việc subscribe, cancel, doFinally và backpressure trong reactive pipeline.
5. Dùng **MongoTemplate.aggregateStream** và **ReactiveMongoTemplate.aggregate** khi cần pipeline động.
6. Giới hạn phạm vi/khối lượng dữ liệu, chọn index và chẩn đoán những stage blocking.
7. Kiểm thử kết quả, quyền tenant, đóng tài nguyên và tình huống client ngắt kết nối.

## 2. Đặt đúng câu hỏi: dữ liệu kết quả được giữ ở đâu?

Giả sử pipeline tổng hợp 5 triệu event thanh toán thành 70.000 dòng SKU. Có ba khối tài nguyên cần phân biệt:

| Thành phần | Vai trò | Rủi ro |
| --- | --- | --- |
| MongoDB Server | Thực thi $match, $group, $sort; duy trì cursor | CPU, RAM/disk tạm, index scan, cursor tồn tại quá lâu |
| MongoDB Driver | Đọc batch từ cursor và chuyển dữ liệu | Kết nối, bộ nhớ buffer, round trips |
| Java Application | Mapping DTO, tính toán/xuất dữ liệu tiếp | Heap, GC, backpressure, response bị ngắt |

**List** thường yêu cầu hoàn thành đọc và giữ các kết quả trước khi người gọi duyệt List. **Stream/Flux** cho phép caller tiêu thụ tăng dần, nhưng không thay đổi toàn bộ chiến lược thực thi phía MongoDB.

~~~mermaid
flowchart LR
    A["Collection sale_events"] --> B["MongoDB $match / $group / $sort"]
    B --> C["Server cursor"]
    C --> D["Driver nhận batch"]
    D --> E["Stream hoặc Flux"]
    E --> F["Export / Web response / xử lý"]
~~~

### 2.1. List, Stream, Flux không đồng nghĩa nhau

| Đặc điểm | List<T> | Stream<T> | Flux<T> |
| --- | --- | --- | --- |
| Kiểu lập trình | Đồng bộ | Đồng bộ, Java Stream | Reactive, Reactor |
| Thời điểm xử lý phần tử | Sau khi lấy kết quả | Khi iterator/terminal operation đọc | Khi có subscription và demand |
| Bộ nhớ ứng dụng | Có thể tăng theo số kết quả | Có thể giới hạn nếu không gom toàn bộ | Có thể giới hạn nếu downstream không gom/đệm vô hạn |
| Cần caller chủ động đóng? | Thông thường không giữ cursor mở sau khi method trả List | **Có**, đóng Stream/try-with-resources | Thông thường resource được driver/framework quản lý qua terminal/cancel |
| Có thể dừng sớm? | Đã lấy kết quả trước khi duyệt | Có, nhưng **vẫn phải close** | Có, qua cancel/take/timeout |
| Backpressure theo Reactive Streams | Không | Không | Có |
| Có tự đảm bảo snapshot? | Không | Không | Không |

**Chú ý:** Flux không tự làm truy vấn nhanh hơn. Nó là mô hình truyền và tiêu thụ dữ liệu không chặn (*non-blocking*) khi dùng đúng reactive driver, chứ không biến stage $group tốn kém thành một phép đọc miễn phí.

## 3. Domain mẫu: sự kiện thanh toán theo SKU

Giả sử collection **sale_events** lưu các sự kiện thanh toán:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  status: "PAID",
  sku: "BOOK-101",
  amountMinor: NumberLong("159000"),
  paidAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Một event khác:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  status: "PAID",
  sku: "PEN-002",
  amountMinor: NumberLong("12000"),
  paidAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

Trong Java:

~~~java
package com.example.sales;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "sale_events")
public record SaleEventDocument(
    @Id ObjectId id,
    String tenantId,
    String status,
    String sku,
    long amountMinor,
    Instant paidAt
) {}
~~~

Entity lưu một event thanh toán. **tenantId** là điều kiện phân quyền bắt buộc trong truy vấn; status = PAID giúp loại các event chưa thanh toán. **amountMinor** là giá trị nguyên theo đơn vị tiền nhỏ nhất. Nếu có nhiều loại tiền, cần thêm currency và group riêng theo currency; không cộng các đồng tiền khác nhau thành một số chung.

### 3.1. DTO kết quả của aggregation

~~~java
package com.example.sales;

public record SkuRevenueRow(
    String sku,
    long orderCount,
    long revenueMinor
) {}
~~~

Mỗi dòng chứa một SKU, số event được tính và tổng amountMinor. Trong bài này **orderCount** là tên metric minh họa; chỉ tương đương số đơn hàng nếu mô hình thực sự có đúng một sale event cho mỗi order/SKU theo quy tắc nghiệp vụ. Nếu một đơn có nhiều event cho cùng SKU, cần đặt tên metric **eventCount** hoặc group distinct orderId thay vì gọi là orderCount.

**Không map kết quả $group vào SaleEventDocument** khi structure đã thay đổi. Sử dụng DTO kết quả để tránh hiểu sai các field entity bị thiếu và tránh đem object partial đi save.

## 4. Pipeline gốc: nhóm doanh thu theo SKU

Trong mongosh:

~~~javascript
db.sale_events.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$sku",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
    }
  },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      orderCount: 1,
      revenueMinor: 1
    }
  },
  { $sort: { sku: 1 } }
]);
~~~

Các stage:

1. **$match** giới hạn tenant và trạng thái trước khi tổng hợp.
2. **$group** tạo một nhóm cho mỗi SKU và tính các accumulator.
3. **$project** đổi khóa nhóm _id thành field sku của DTO.
4. **$sort** định thứ tự đầu ra để xuất báo cáo ổn định.

Đầu ra minh họa:

~~~javascript
[
  { sku: "BOOK-101", orderCount: 2, revenueMinor: NumberLong("350000") },
  { sku: "PEN-002", orderCount: 1, revenueMinor: NumberLong("12000") }
]
~~~

Trong báo cáo thật, nếu số SKU rất lớn thì một List<SkuRevenueRow> có thể chiếm nhiều bộ nhớ ứng dụng. Đó là lý do cân nhắc streaming kết quả từ aggregation.

### 4.1. Streaming kết quả khác streaming dữ liệu nguồn

**$group** phải tổng hợp các event trước khi tạo các nhóm tương ứng, có thể dùng bộ nhớ trên server hoặc disk spill theo cấu hình. Sau khi các nhóm được tạo, cursor mới cung cấp những document kết quả cho driver.

Vì vậy, dù client dùng Stream/Flux, pipeline có thể vẫn có độ trễ lớn trước phần tử đầu tiên. Khi chẩn đoán, phải xem **kế hoạch aggregation, index, number of input documents và blocking stages**, không chỉ số phần tử đã emit.

## 5. @Aggregation trong repository đồng bộ trả Stream

Spring Data MongoDB hỗ trợ method repository được chú thích **@Aggregation** và kết quả **Stream<DTO>** để đọc qua cursor.

~~~java
package com.example.sales;

import java.util.stream.Stream;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SaleEventRepository
        extends MongoRepository<SaleEventDocument, ObjectId> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
        "{ '$group': { '_id': '$sku', "
            + "'orderCount': { '$sum': 1 }, "
            + "'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'sku': '$_id', "
            + "'orderCount': 1, 'revenueMinor': 1 } }",
        "{ '$sort': { 'sku': 1 } }"
    })
    Stream<SkuRevenueRow> streamPaidRevenueByTenant(
        String tenantId
    );
}
~~~

**?0** là tham số đầu tiên của method (tenantId). Framework bind giá trị theo cơ chế của Spring Data, không dùng nối chuỗi JSON từ input. Điều kiện tenant phải được lấy từ ngữ cảnh xác thực đáng tin cậy, không chỉ từ query parameter client tự khai.

Phương thức trên **không trả List**. Caller nhận một Stream có thể nắm giữ MongoDB cursor và phải đảm bảo đóng.

### 5.1. @Aggregation ở tầng repository không phải @Query thông thường

**@Query** xác định truy vấn find/fields; **@Aggregation** xác định các stage pipeline. Pipeline ở repository có thể trả DTO/projection khác kiểu entity nguồn.

Không nhầm Stream<SkuRevenueRow> với Stream<SaleEventDocument>: các document kết quả đã được **$group** và **$project** nên chỉ còn thông tin báo cáo.

### 5.2. Sort và Pageable trong @Aggregation

Theo tài liệu Spring Data MongoDB, method @Aggregation có thể nhận Sort/Pageable để thêm các stage sắp xếp/phân trang sau pipeline, và có thể trả **Slice**. Tuy nhiên, **Page** không được hỗ trợ như return type tự động cho @Aggregation repository method.

Nếu pipeline đã kết thúc bằng **$sort**, hãy kiểm tra việc thêm một Sort từ method có làm thay đổi thứ tự cuối cùng hay không. Trong ví dụ, sort SKU được khai báo ngay trong pipeline để giữ hợp đồng thứ tự cố định.

**Không dùng Pageable chỉ để giả vờ cursor được đóng**. Phân trang và vòng đời cursor là hai vấn đề khác nhau.

## 6. Đóng Stream bằng try-with-resources

Cách sử dụng đúng:

~~~java
import java.util.function.Consumer;
import java.util.stream.Stream;

public class RevenueExportService {

    private final SaleEventRepository repository;

    public RevenueExportService(SaleEventRepository repository) {
        this.repository = repository;
    }

    public void export(
            String authenticatedTenantId,
            Consumer<SkuRevenueRow> sink) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant required");
        }

        try (Stream<SkuRevenueRow> rows =
                repository.streamPaidRevenueByTenant(
                    authenticatedTenantId)) {

            rows.forEach(sink);
        }
    }
}
~~~

Khi thoát khối **try**:

- Stream được đóng sau khi duyệt hết.
- Stream được đóng khi **sink.accept** ném RuntimeException.
- Stream được đóng khi code **return** sớm từ trong khối.

Với Java Stream gắn cursor, **close() là thao tác quản lý tài nguyên thực**, không chỉ một phương thức mang tính hình thức.

### 6.1. Nên đặt try-with-resources tại nơi tiêu thụ

Đừng làm như sau:

~~~java
public Stream<SkuRevenueRow> loadReport(String tenantId) {
    try (Stream<SkuRevenueRow> rows =
            repository.streamPaidRevenueByTenant(tenantId)) {
        return rows;
    }
}
~~~

Ở đây Stream đã bị đóng trước khi caller bắt đầu duyệt, nên phương thức trả một resource không còn sử dụng đúng cách.

Một thiết kế service tốt hơn là **tiêu thụ Stream trong cùng phạm vi sở hữu tài nguyên**, hoặc chuyển sang một callback/consumer được gọi bên trong try.

### 6.2. Dừng sớm vẫn phải đóng

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {

    rows.limit(10).forEach(this::writePreviewRow);
}
~~~

**limit(10)** ở đây giới hạn số phần tử Java tiêu thụ nhưng **không chắc MongoDB chỉ tính 10 nhóm**. Đặc biệt, $group/$sort có thể đã xử lý nhiều dữ liệu. Dù chỉ xem trước 10 dòng, cần đóng cursor sau khi kết thúc terminal operation.

Để server chỉ trả N kết quả, hãy xem xét **$limit trong pipeline** với thứ tự stage đúng cho nghiệp vụ. $limit sau $group có nghĩa giới hạn **N nhóm**, không giới hạn N event đầu vào.

### 6.3. Stream.findFirst không đóng cursor tự động thay caller

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {

    var first = rows.findFirst();
}
~~~

**findFirst()** là terminal operation có thể dừng trước khi cursor hết. Không nên tin rằng terminal operation luôn giải phóng mọi resource. try-with-resources giữ quyền sở hữu tài nguyên rõ ràng.

## 7. Những cách dùng Stream dễ gây rò tài nguyên

### 7.1. Trả Stream thẳng cho controller

~~~java
// Không nên khi không kiểm soát ai đóng stream.
public Stream<SkuRevenueRow> controllerAction() {
    return repository.streamPaidRevenueByTenant(tenantId);
}
~~~

Việc trả một Stream tới tầng serialization không bảo đảm serializer đóng cursor trong mọi đường thành công/hủy/lỗi. Controller nên dùng một cơ chế response streaming có lifecycle được kiểm soát hoặc một service tự tiêu thụ Stream và đóng trong finally.

### 7.2. Giữ Stream trong field singleton

~~~java
// Không nên: Stream gắn cursor không phải cache dữ liệu.
private Stream<SkuRevenueRow> cachedRows;
~~~

Stream dựa trên cursor không phải object để tái sử dụng qua nhiều request, không phù hợp làm field singleton và không dùng như một cache.

### 7.3. Dùng parallel() trên cursor-backed Stream

~~~java
// Không nên giả định cursor sẽ được chia an toàn, có lợi cho parallelism.
rows.parallel().forEach(this::writeRow);
~~~

Driver cursor và mapper không phải một tập dữ liệu bất biến trong memory đã được chia partition. Parallel stream không tự tạo nhiều cursor độc lập hoặc thay thế thiết kế xử lý theo lô. Với workload I/O xuất file, sự phối hợp thứ tự/ghi cũng là vấn đề riêng.

### 7.4. Chỉ đóng khi có exception

~~~java
// Sai: đường thành công không close; đường return sớm dễ bỏ sót.
Stream<SkuRevenueRow> rows =
    repository.streamPaidRevenueByTenant(tenantId);
rows.forEach(this::writeRow);
~~~

Hãy dùng **try-with-resources** là lựa chọn mặc định, kể cả khi cho rằng toàn bộ Stream sẽ được tiêu thụ.

## 8. MongoTemplate.aggregateStream cho pipeline linh hoạt

Khi filter thời gian, grouping hoặc projection được xây theo yêu cầu, MongoTemplate có API **aggregateStream(...)** trả Java Stream:

~~~java
import java.util.stream.Stream;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is("PAID")
    ),
    Aggregation.group("sku")
        .count().as("orderCount")
        .sum("amountMinor").as("revenueMinor"),
    Aggregation.project("orderCount", "revenueMinor")
        .and("_id").as("sku")
        .andExclude("_id"),
    Aggregation.sort(Sort.Direction.ASC, "sku")
);

try (Stream<SkuRevenueRow> rows =
        mongoTemplate.aggregateStream(
            aggregation,
            "sale_events",
            SkuRevenueRow.class)) {

    rows.forEach(this::writeRow);
}
~~~

**aggregateStream** dùng MongoDB aggregation cursor, không trả AggregationResults chứa một danh sách đã vật hóa. Đây là cách kiểm soát rõ pipeline ở service/custom repository fragment.

### 8.1. stream(Query) và aggregateStream khác nhau

~~~java
try (Stream<SaleEventDocument> events =
        mongoTemplate.stream(
            Query.query(Criteria.where("tenantId").is(tenantId)),
            SaleEventDocument.class)) {

    events.forEach(this::handleEvent);
}
~~~

**MongoTemplate.stream(Query, ...)** streaming kết quả **find**; **aggregateStream(Aggregation, ...)** streaming kết quả **pipeline aggregation**. Hai API đều có vòng đời resource cần close, nhưng semantics truy vấn khác nhau.

### 8.2. AggregateStream và explain

Tài liệu MongoOperations chỉ rõ **aggregation streaming không dùng cùng chế độ explain**; bật explain trên một aggregation dùng aggregateStream có thể gây IllegalArgumentException.

Muốn phân tích execution plan, hãy chạy **explain trên pipeline tương đương** riêng bằng mongosh/driver hoặc API explain phù hợp. Đừng cố bật giải thích kế hoạch trên Stream đang chạy để xuất dữ liệu production.

## 9. List so với Stream: chọn từ mục tiêu ứng dụng

| Yêu cầu | Cách phù hợp |
| --- | --- |
| Báo cáo chỉ có 5–20 nhóm cố định | List hoặc Page/Slice nếu phù hợp |
| Xuất hàng chục nghìn nhóm theo thứ tự | Stream + try-with-resources |
| Lấy một phần preview có limit tường minh | $limit / Slice với sort đúng |
| Cần tính thêm metric toàn cục từ toàn bộ nhóm | Có thể đưa phép tổng hợp vào MongoDB thay vì materialize List |
| API trả danh sách nhỏ đã giới hạn | List đơn giản, dễ serialize |
| WebFlux cần đẩy kết quả liên tục | Flux qua reactive repository/template |
| Job chạy nền đồng bộ và ghi file từng dòng | Stream có quản lý vòng đời rõ |

**Đừng dùng Stream chỉ vì một chữ “nhanh”**. Với tập kết quả nhỏ, List đơn giản hơn và tránh việc caller phải sở hữu cursor mở.

### 9.1. Stream không có nghĩa kết quả được cache

Java Stream thông thường chỉ duyệt một lần. Nếu muốn đọc lại, phải gọi repository một lần nữa hoặc lưu dữ liệu theo một cơ chế riêng. Không gọi hai terminal operations trên cùng Stream như thể đó là một Collection.

### 9.2. Tạo List từ Stream làm mất lợi ích về heap

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {

    List<SkuRevenueRow> all = rows.toList();
}
~~~

Code đóng cursor đúng nhưng lại giữ toàn bộ kết quả trong List. Điều này hợp lý nếu có giới hạn chặt; **không phù hợp với mục tiêu xuất báo cáo cực lớn với RAM hạn chế**.

## 10. Reactive repository trả Flux từ @Aggregation

Spring Data MongoDB hỗ trợ repository reactive qua ReactiveMongoRepository. Với @Aggregation, kết quả có thể được biểu diễn bằng **Flux<DTO>**:

~~~java
package com.example.sales;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveSaleEventRepository
        extends ReactiveMongoRepository<SaleEventDocument, ObjectId> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
        "{ '$group': { '_id': '$sku', "
            + "'orderCount': { '$sum': 1 }, "
            + "'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'sku': '$_id', "
            + "'orderCount': 1, 'revenueMinor': 1 } }",
        "{ '$sort': { 'sku': 1 } }"
    })
    Flux<SkuRevenueRow> streamPaidRevenueByTenant(
        String tenantId
    );
}
~~~

Trong service:

~~~java
import reactor.core.publisher.Flux;

public Flux<SkuRevenueRow> getRows(
        String authenticatedTenantId) {

    return reactiveRepository
        .streamPaidRevenueByTenant(authenticatedTenantId)
        .map(this::normalizeRow);
}
~~~

**normalizeRow** là hàm nghiệp vụ minh họa biến đổi từng DTO. Tránh để normalizeRow thực hiện I/O blocking trên event loop.

### 10.1. Flux là publisher, không phải cursor đang được duyệt ngay

~~~java
Flux<SkuRevenueRow> result =
    reactiveRepository.streamPaidRevenueByTenant(tenantId);
~~~

Chỉ tạo một Flux chưa phải bằng chứng MongoDB đã thực thi aggregation. Khi có subscriber, driver bắt đầu truy vấn và phát các phần tử theo nhu cầu tiêu thụ.

### 10.2. Không chuyển Flux thành List vô hạn

~~~java
// Nguy hiểm nếu số nhóm rất lớn.
Mono<List<SkuRevenueRow>> allRows =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .collectList();
~~~

**collectList** gom toàn bộ dữ liệu vào bộ nhớ. Nếu tập nhóm có giới hạn nhỏ và đã được kiểm soát ở MongoDB, collectList có thể hợp lý; còn với báo cáo lớn thì đánh mất một trong các lợi ích của Flux.

## 11. Subscription, cancellation và vòng đời cursor reactive

Với reactive driver, cursor được quản lý theo lifecycle của publisher/subscription. Khi publisher kết thúc thông thường, phát lỗi hoặc subscriber **cancel**, driver/framework sẽ thực hiện quy trình giải phóng resource tương ứng. Ứng dụng thường **không cần gọi MongoCursor.close thủ công** trên Flux do Spring Data tạo ra.

~~~mermaid
flowchart TD
    A["Tạo Flux từ repository"] --> B["Subscriber đăng ký"]
    B --> C["Driver mở aggregation cursor"]
    C --> D["Phát batch dữ liệu theo demand"]
    D --> E{"Tín hiệu kết thúc?"}
    E -->|Complete| F["Giải phóng cursor"]
    E -->|Error| F
    E -->|Cancel| F
~~~

**Lưu ý:** việc giải phóng khi cancel có thể là quy trình phối hợp driver/network, không phải lời hứa rằng server cursor biến mất tức thời trong mọi sự cố kết nối. Hãy đo bằng metrics và integration test nếu quản lý resource là yêu cầu vận hành quan trọng.

### 11.1. take(n) khiến upstream bị hủy sau N phần tử

~~~java
Flux<SkuRevenueRow> preview =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .take(10);
~~~

Khi take đã nhận đủ 10 phần tử, nó có thể cancel upstream. Điều này giúp ngừng đọc thêm kết quả từ cursor. Nhưng giống Stream.limit, **không đảm bảo $group/$sort trên MongoDB chỉ xử lý 10 event**.

Nếu mục tiêu giới hạn số nhóm từ server, hãy thêm **$limit** vào aggregation sau khi xác định đúng $group/$sort, thay vì chỉ dùng take(10) trên Java.

### 11.2. timeout và cancel

~~~java
import java.time.Duration;

Flux<SkuRevenueRow> guarded =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .timeout(Duration.ofSeconds(30));
~~~

Khi timeout, Reactor có thể hủy subscription upstream và phát lỗi timeout downstream. Điều đó không tự xác nhận MongoDB Server đã hủy toàn bộ công việc trong đúng 30 giây, đặc biệt nếu stage server đang xử lý hoặc mạng bị gián đoạn.

Với SLA chặt, cân nhắc **maxTimeMS**/metadata query phù hợp, giới hạn dữ liệu theo thời gian và timeout ở cả tầng database lẫn application.

### 11.3. Không tự subscribe rồi trả Flux

~~~java
// Sai: có thể tạo hai subscription/truy vấn.
Flux<SkuRevenueRow> rows =
    reactiveRepository.streamPaidRevenueByTenant(tenantId);

rows.subscribe(this::logRow);
return rows;
~~~

Khi controller/framework subscribe lần nữa, pipeline có thể chạy lại. Hai lần aggregation có thể tạo thêm tải, kéo dài thời gian giữ cursor và nhận dữ liệu khác nhau nếu database thay đổi giữa hai lần.

Hãy **return một pipeline** rồi để caller điều khiển subscription.

## 12. DoFinally, onCancel và xử lý lỗi reactive

Reactor cung cấp các hook giúp quan sát lifecycle:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

Flux<SkuRevenueRow> rows =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .doOnSubscribe(subscription ->
            log.info("Revenue export subscribed"))
        .doOnNext(row ->
            metrics.incrementRowsEmitted())
        .doOnCancel(() ->
            metrics.incrementExportsCancelled())
        .doOnError(error ->
            log.error("Revenue aggregation failed", error))
        .doFinally(signal ->
            log.info("Revenue stream finished: {}", signal));
~~~

Đây là ví dụ dùng các dependency **log** và **metrics** giả định. **doFinally** được gọi khi pipeline downstream kết thúc, lỗi hoặc hủy, với SignalType tương ứng. Nó hữu ích để đo thời gian, số row và số lần cancel.

**Không gọi tự ý close() trên MongoCursor từ trong doFinally** khi cursor thuộc quyền quản lý của reactive driver. Hook chỉ nên thu thập telemetry hoặc giải phóng các resource **do ứng dụng tự sở hữu**.

### 12.1. doOnComplete và doFinally khác nhau

| Hook | Khi nào được gọi |
| --- | --- |
| doOnComplete | Upstream hoàn thành bình thường |
| doOnError | Upstream phát lỗi |
| doOnCancel | Downstream hủy subscription |
| doFinally | Khi pipeline kết thúc bằng complete/error/cancel |

Nếu dùng **doOnComplete** để “luôn giải phóng writer”, writer có thể không được giải phóng khi client ngắt kết nối hoặc exception xảy ra. Với tài nguyên ứng dụng tự quản lý, hãy thiết kế close trong **finally/doFinally**, hoặc dùng các cơ chế **using/usingWhen** với resource lifecycle rõ ràng.

### 12.2. Lỗi giữa chừng không có nghĩa dữ liệu đã phát bị thu hồi

Một Flux có thể đã emit 2.000 hàng trước khi database/driver báo lỗi ở batch kế tiếp. Nếu client đã ghi ra file/HTTP response, những dòng đó **không tự rollback**.

Đối với quy trình xuất dữ liệu quan trọng, một chiến lược thực tế là:

1. Ghi sang file tạm/bản xuất chưa công bố.
2. Kiểm tra luồng **complete** thành công.
3. Công bố/đổi tên file đầu ra khi hoàn tất.
4. Nếu bị cancel/error, xóa hoặc đánh dấu bản xuất là chưa hoàn tất.

Nếu response HTTP đã gửi một phần dữ liệu, thường không thể chuyển nó thành một JSON error bình thường ở cuối; cần giao thức stream có định nghĩa về partial output và cách client phát hiện kết thúc.

## 13. Backpressure: có ích nhưng không phải bộ nhớ vô hạn

Reactive Streams cho phép downstream yêu cầu số phần tử (*demand*), giúp upstream không phát không giới hạn vào một consumer chậm. Reactive MongoDB driver phối hợp cung cấp dữ liệu từ cursor qua batch/demand theo cơ chế của mình.

~~~java
Flux<SkuRevenueRow> throttled =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .limitRate(64);
~~~

**limitRate** là chiến lược điều chỉnh số phần tử Reactor yêu cầu upstream; nó không phải cú pháp thiết lập trực tiếp **batchSize=64 trên MongoDB cursor**. Driver có thể prefetch, giữ batch riêng và thực hiện getMore theo cách phù hợp.

### 13.1. Những phép toán có thể phá lợi ích streaming

~~~java
// Có thể tích lũy toàn bộ kết quả vào bộ nhớ.
Flux<SkuRevenueRow> sortedInJava =
    rows.sort((a, b) -> a.sku().compareTo(b.sku()));
~~~

**Flux.sort(...)** cần thu thập phần tử để sắp xếp, không phải thao tác sort streaming trên MongoDB. Với danh sách rất lớn, ưu tiên **$sort trong aggregation** nếu yêu cầu thứ tự thuộc hợp đồng của dữ liệu.

~~~java
// Tương tự: collectList sẽ gom tất cả kết quả.
Mono<List<SkuRevenueRow>> list = rows.collectList();
~~~

**buffer**, **groupBy**, **collectMap**, **reduce** hoặc các toán tử khác cũng có thể giữ trạng thái trong bộ nhớ. Mỗi toán tử cần được đánh giá theo số phần tử và mẫu tiêu thụ, không chỉ dựa vào việc chain bắt đầu bằng Flux.

### 13.2. onBackpressureBuffer không giải quyết consumer chậm một cách mặc định

~~~java
// Không nên tạo buffer không giới hạn chỉ để tránh tắc nghẽn.
Flux<SkuRevenueRow> unsafe =
    rows.onBackpressureBuffer();
~~~

Một buffer không giới hạn có thể làm heap tăng mạnh. Nếu cần buffer, hãy dùng **giới hạn rõ ràng** và chính sách overflow phù hợp, đồng thời đo tác động lên latency và tài nguyên.

### 13.3. Đừng nhầm batchSize với limit

| Tham số/khái niệm | Tác dụng |
| --- | --- |
| cursor batchSize | Số document driver/server trao đổi trong một batch, theo cơ chế cursor |
| $limit trong pipeline | Giới hạn tối đa số document đầu ra ở vị trí stage đó |
| Pageable / $skip | Bỏ qua kết quả theo thứ tự phù hợp |
| Reactor limitRate | Điều chỉnh demand trong pipeline reactive |
| take(n) | Dừng tiêu thụ sau n phần tử và có thể cancel upstream |

**Batch size không phải tổng số document mà truy vấn được phép trả.** Một cursor với batchSize nhỏ vẫn có thể trả hàng triệu document qua nhiều lần getMore.

## 14. ReactiveMongoTemplate.aggregate: khi cần pipeline động

Repository @Aggregation gọn với pipeline cố định. Nếu report có thời gian, tenant, status hoặc group unit động, dùng **ReactiveMongoTemplate**:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import reactor.core.publisher.Flux;

public Flux<SkuRevenueRow> aggregateReactive(
        ReactiveMongoTemplate template, String tenantId) {

    Aggregation pipeline = Aggregation.newAggregation(
        Aggregation.match(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is("PAID")
        ),
        Aggregation.group("sku")
            .count().as("orderCount")
            .sum("amountMinor").as("revenueMinor"),
        Aggregation.project("orderCount", "revenueMinor")
            .and("_id").as("sku")
            .andExclude("_id"),
        Aggregation.sort(Sort.Direction.ASC, "sku")
    );

    return template.aggregate(
        pipeline, "sale_events", SkuRevenueRow.class
    );
}
~~~

Khác với **MongoTemplate.aggregate(...)** đồng bộ trả **AggregationResults**, **ReactiveMongoTemplate.aggregate(...)** trả Flux các kết quả của aggregation. Reactive driver/framework chịu trách nhiệm phối hợp cursor với subscription lifecycle.

### 14.1. DTO Mapping

Kết quả pipeline có:

~~~javascript
{
  sku: "BOOK-101",
  orderCount: 2,
  revenueMinor: NumberLong("350000")
}
~~~

Record SkuRevenueRow có property tương ứng, nên Spring Data có thể ánh xạ dữ liệu. Với projection đổi tên trường hoặc accumulator ra kiểu số khác, phải kiểm tra DTO constructor/property mapping và kiểu BSON thực tế trong integration test.

### 14.2. Query động không có nghĩa nối JSON từ HTTP input

Đừng nối một chuỗi JSON tự tạo để truyền stage:

~~~java
// Không nên: chuỗi field/operator do client tùy ý kiểm soát.
String pipeline = "{ '$match': " + clientJson + " }";
~~~

Dùng **Criteria**, **AggregationOperation**, validation và danh sách field/operator được phép. Điều kiện **tenantId** phải do service áp đặt, không cho client xây một $or làm vượt filter quyền.

## 15. Stream/Flux trong Web API

### 15.1. WebFlux với NDJSON

Với một API muốn phát mỗi dòng kết quả thành một JSON object riêng, có thể chọn **NDJSON**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class RevenueStreamController {

    private final ReactiveSaleEventRepository repository;

    public RevenueStreamController(
            ReactiveSaleEventRepository repository) {
        this.repository = repository;
    }

    @GetMapping(
        path = "/reports/revenue/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<SkuRevenueRow> exportRevenue() {

        String tenantId = authenticatedTenantId();

        return repository.streamPaidRevenueByTenant(tenantId);
    }

    private String authenticatedTenantId() {
        // Minh họa: lấy từ cơ chế authorization đáng tin cậy.
        throw new UnsupportedOperationException("Wire security context");
    }
}
~~~

Method authenticatedTenantId là **chỗ nối với hệ thống bảo mật thực tế**. Không gọi controller minh họa khi chưa tích hợp principal/tenant resolution. Trên production, cần lấy tenantId theo cơ chế xác thực reactive phù hợp, không truy cập bừa ThreadLocal của stack đồng bộ trên WebFlux.

NDJSON cho phép client đọc từng JSON line mà không cần chờ cả một mảng JSON đóng. Tuy nhiên, hỗ trợ flush từng phần, buffering của HTTP server, proxy và client là những yếu tố vận hành phải kiểm thử.

### 15.2. Client hủy response

Khi client ngắt kết nối, WebFlux sẽ thực hiện cơ chế cancel subscription tương ứng theo runtime. Driver/framework sau đó xử lý giải phóng cursor. Ứng dụng vẫn nên:

- Giới hạn thời gian truy vấn.
- Giám sát số stream mở và thời gian tồn tại.
- Theo dõi cancellation/timeout.
- Tránh bắt lỗi rồi tiếp tục truy vấn nền không cần thiết.

**Không kết luận cursor đã giải phóng ngay lập tức** chỉ vì browser đóng tab; hãy kiểm tra metrics và hành vi thực tế khi có sự cố mạng.

### 15.3. Streaming đồng bộ qua HTTP

Với Spring MVC, một export có thể dùng StreamingResponseBody hoặc cơ chế response streaming phù hợp. Phải đặt **try-with-resources bao quanh toàn bộ vòng lặp xuất dữ liệu** bên trong callback thực sự ghi response, không mở Stream ở controller rồi trả ra ngoài cho thread khác xử lý.

Đừng truyền Java Stream gắn MongoDB cursor qua boundary mà không xác định người sở hữu và thời điểm đóng.

## 16. Cursor: từ firstBatch đến getMore và close

Một aggregation không nhất thiết gửi toàn bộ kết quả trong một response MongoDB. MongoDB có thể tạo **cursor** chứa trạng thái cần thiết để trả từng batch.

~~~mermaid
sequenceDiagram
    participant C as Application
    participant D as MongoDB Driver
    participant M as MongoDB Server
    C->>D: Chạy @Aggregation / aggregateStream
    D->>M: aggregate với cursor
    M-->>D: firstBatch và cursorId (nếu còn)
    D-->>C: Phần tử kết quả
    C->>D: Tiếp tục tiêu thụ
    D->>M: getMore khi cần
    M-->>D: batch tiếp theo
    C->>D: close Stream hoặc cancel Flux
    D->>M: Quy trình giải phóng/killCursors khi thích hợp
~~~

**Cursor server** và **Java Stream/Flux publisher** là hai đối tượng ở các tầng khác nhau. Stream chỉ là cách Java truy cập kết quả, còn cursor liên quan tài nguyên driver/server. Đây là lý do try-with-resources phải đóng Stream dù vòng lặp Java dừng sớm.

### 16.1. Cursor có thể hết tự nhiên

Khi truy vấn được tiêu thụ hết, server/driver thường giải phóng cursor theo lifecycle bình thường. Tuy nhiên, trong ứng dụng đồng bộ, việc **close() vẫn là trách nhiệm caller** vì có thể dừng sớm hoặc lỗi giữa vòng lặp.

### 16.2. Cursor tồn tại quá lâu

Một Stream được mở nhưng không được duyệt hoặc không đóng có thể giữ kết nối và cursor/resource liên quan lâu hơn cần thiết. Dưới tải cao, nhiều cursor bỏ quên có thể gây:

- Tăng áp lực kết nối và số cursor server.
- Tăng thời gian giữ tài nguyên cho một request.
- Khó xác định vì sao một job không hoàn tất.
- Rủi ro timeout/invalidation của cursor khi idle.

Không dựa vào garbage collection hay thời gian timeout của server để giải phóng tài nguyên đúng hạn. **Sở hữu tài nguyên phải được biểu diễn trong code.**

## 17. $group và $sort vẫn có thể là blocking stages

Streaming giảm nhu cầu giữ toàn bộ **kết quả đầu ra** trong Java, nhưng MongoDB Server có thể phải xử lý nhiều dữ liệu trước khi phát kết quả.

### 17.1. $group

~~~javascript
{
  $group: {
    _id: "$sku",
    revenueMinor: { $sum: "$amountMinor" }
  }
}
~~~

$group thường phải tích lũy trạng thái theo từng key trong quá trình xử lý. Nếu số nhóm lớn hoặc dữ liệu đầu vào khổng lồ, memory consumption có thể tăng. Tùy server version và cấu hình, aggregation có thể cần sử dụng disk cho những stage đủ điều kiện.

### 17.2. $sort

~~~javascript
{ $sort: { revenueMinor: -1 } }
~~~

Nếu sort theo một field **được tạo sau $group**, index trên field gốc trong collection không tự biến sort thành thao tác miễn phí. MongoDB có thể phải sắp xếp những nhóm đã tổng hợp.

### 17.3. $match và index

Một index cân nhắc cho workload:

~~~javascript
db.sale_events.createIndex({
  tenantId: 1,
  status: 1,
  paidAt: 1
});
~~~

Với báo cáo theo tenant/status và **khoảng paidAt**, index này có thể giúp $match giảm số event phải xử lý. Nếu pipeline không có filter paidAt, thiết kế index cần đánh giá lại theo mẫu truy vấn thật.

**Không thêm $limit lên trước $group để giảm tải mà không thay đổi yêu cầu**, vì điều đó biến tổng doanh thu toàn tập thành tổng doanh thu của một tập con.

## 18. @Meta và các giới hạn tài nguyên cho aggregation

Spring Data MongoDB hỗ trợ **@Meta** cho repository aggregation để thiết lập một số tùy chọn như allowDiskUse, maxExecutionTimeMs và comment.

~~~java
import java.util.stream.Stream;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.Meta;

public interface SaleEventReportRepository
        extends MongoRepository<SaleEventDocument, ObjectId> {

    @Meta(allowDiskUse = "true", maxExecutionTimeMs = 30000)
    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
        "{ '$group': { '_id': '$sku', "
            + "'orderCount': { '$sum': 1 }, "
            + "'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'sku': '$_id', "
            + "'orderCount': 1, 'revenueMinor': 1 } }",
        "{ '$sort': { 'sku': 1 } }"
    })
    Stream<SkuRevenueRow> streamByTenantWithOptions(String tenantId);
}
~~~

**allowDiskUse không có nghĩa query chắc chắn spill ra disk**, cũng không bảo đảm dùng ít thời gian hay ít tài nguyên. Nó cho phép các stage thích hợp dùng disk khi cần theo semantics MongoDB Server/version.

**maxExecutionTimeMs** đặt giới hạn thời gian thực thi ở tầng database theo ngữ nghĩa của MongoDB; nó không thay thế timeout mạng/HTTP, không đảm bảo mọi loại tác vụ sẽ bị dừng đúng tức thời khi client cancel và không tự đóng resource do Java sở hữu.

### 18.1. Tại sao @Meta không thay close?

Ngay cả khi giới hạn 30 giây, Stream đồng bộ **vẫn cần try-with-resources**:

~~~java
try (Stream<SkuRevenueRow> stream =
        repository.streamByTenantWithOptions(tenantId)) {
    stream.forEach(this::handleRow);
}
~~~

Tùy chọn server và trách nhiệm close ở client là hai lớp bảo vệ khác nhau.

## 19. Transactions, sessions và phạm vi sống của Stream

Streaming query có thể liên quan tới session/transaction do Spring quản lý. **Không được trả một Stream chưa được duyệt ra khỏi phạm vi transaction rồi kỳ vọng cursor/session vẫn hợp lệ**.

Ví dụ có nguy cơ:

~~~java
// Không nên trả Stream ra khỏi transactional method.
@Transactional(readOnly = true)
public Stream<SkuRevenueRow> openInTransaction(String tenantId) {
    return repository.streamPaidRevenueByTenant(tenantId);
}
~~~

Khi method kết thúc, transaction interceptor có thể kết thúc transaction trước khi caller duyệt Stream, làm lifecycle không khớp.

### 19.1. Tiêu thụ trong phạm vi sở hữu

~~~java
@Transactional(readOnly = true)
public void exportWithinTransaction(
        String tenantId,
        Consumer<SkuRevenueRow> sink) {

    try (Stream<SkuRevenueRow> rows =
            repository.streamPaidRevenueByTenant(tenantId)) {
        rows.forEach(sink);
    }
}
~~~

Code này chỉ minh họa **đặt vòng đời Stream bên trong phương thức**. MongoDB transaction thực sự cần MongoTransactionManager và deployment hỗ trợ; annotation @Transactional không tự bảo đảm tất cả hoạt động tham gia transaction.

**Không mở transaction chỉ để có thể gọi aggregateStream**. Một transaction dài giữ cursor mở trong suốt export lớn có thể tốn tài nguyên và chịu giới hạn thời gian transaction. Chỉ dùng transaction khi cần consistency/atomicity theo nghiệp vụ và đã đánh giá chi phí.

### 19.2. Tính nhất quán của báo cáo

Nếu collection bị thêm/sửa/xóa trong khi aggregation chạy, kết quả có thể phụ thuộc read concern, snapshot và cơ chế thực thi. **Stream/Flux không tạo snapshot nhất quán chỉ bằng cách đổi return type**.

Nếu báo cáo kế toán cần số liệu được chốt, có thể dùng:

- Snapshot/transaction với phạm vi phù hợp khi có hỗ trợ.
- Version/cutoff của dữ liệu.
- Quy trình materialize báo cáo tại một mốc đối soát.
- Quy tắc điều chỉnh cho event đến trễ và hoàn tiền.

Tính chính xác nghiệp vụ nên được thiết kế độc lập với cách tiêu thụ cursor.

## 20. Khi nào nên chia batch thay vì giữ một cursor rất lâu?

Một export dữ liệu lớn kéo dài hàng giờ có thể phải xử lý lỗi mạng, retry và checkpoint. Một Stream dài có thể đơn giản nhưng khó tiếp tục chính xác từ giữa khi đứt kết nối.

### 20.1. Chiến lược theo lô

1. Chọn khoảng paidAt, tenant và sort key ổn định.
2. Xử lý một nhóm ID hoặc khoảng dữ liệu hữu hạn.
3. Ghi checkpoint cho lô đã hoàn tất.
4. Khi lỗi, đối soát rồi tiếp tục từ checkpoint.
5. Kết hợp idempotency nếu xuất dữ liệu sang hệ thống ngoài.

Với dữ liệu thô có khóa tăng/unique phù hợp, **keyset pagination** có thể tốt hơn skip sâu. Với aggregation đã group theo SKU, checkpoint theo **group key** cần được thiết kế cẩn thận; không tự suy từ việc đã xuất một phần kết quả rằng có thể resume mà không thay đổi số liệu khi event nguồn vẫn cập nhật.

### 20.2. Khi nên materialize trước

Nếu báo cáo cần khớp một phiên bản dữ liệu cố định, có thể tạo materialized report/batch result với **reportId** và timestamp. Sau đó Stream/Flux tiêu thụ chính các dòng báo cáo đã chốt. Điều này tách bài toán **tính kết quả nhất quán** khỏi bài toán **phát kết quả tăng dần cho client**.

### 20.3. Không nhầm MongoDB cursor với Change Stream

**Aggregation cursor** ở bài này trả kết quả của một pipeline truy vấn. **MongoDB Change Streams** dùng pipeline đặc biệt để theo dõi thay đổi liên tục và có lifecycle/semantics khác. Không dùng một cursor aggregation bình thường như thể đó là kênh sự kiện chạy mãi.

## 21. Đọc kết quả trực tiếp không thay thế giới hạn dữ liệu

Một số API cần preview 10 dòng, số khác cần export toàn bộ 50.000 dòng. Nên tách mục tiêu ngay trong hợp đồng:

~~~text
GET /reports/revenue/preview?limit=10
GET /reports/revenue/exports/{jobId}
GET /reports/revenue/stream
~~~

Ở preview, nên đưa **$sort/$limit vào pipeline** đúng vị trí. Ở export, cần scope tenant, thời gian, quyền, thời lượng, resource budget và cách xử lý nếu client hủy giữa chừng.

### 21.1. Giới hạn ngữ nghĩa ở đâu?

| Pipeline | Ý nghĩa |
| --- | --- |
| $match → $limit(10) → $group | Tổng hợp từ 10 event đầu tiên; thường sai cho báo cáo doanh thu toàn tập |
| $match → $group → $sort → $limit(10) | Lấy 10 nhóm đầu theo thứ tự sort |
| $match → $group → $limit(10) → $sort | Sắp xếp chỉ 10 nhóm được chọn trước đó; có thể sai mục tiêu top 10 |
| $match → $group → $sort → Stream | Xuất dần tất cả nhóm sau khi server xử lý pipeline |

**Thứ tự stage là một phần của kết quả nghiệp vụ**, không chỉ một lựa chọn tối ưu.

### 21.2. Top-N và sort ở repository

Nếu thêm Sort/Pageable ở chữ ký @Aggregation, các stage phụ có thể được áp dụng sau pipeline đã khai báo. Với top-N, kiểm tra vị trí $sort/$limit cuối cùng và mapping tên field của **DTO trả về**; không mặc định sort theo property của entity nguồn khi kết quả đã đổi cấu trúc sau $group.

## 22. Kiểm thử tích hợp Stream từ @Aggregation

Unit test chỉ mock repository không chứng minh được framework dùng MongoDB cursor hoặc pipeline thực sự group đúng. Nên có integration test với MongoDB test instance riêng, ví dụ Testcontainers hoặc môi trường MongoDB dành cho kiểm thử.

### 22.1. Dữ liệu test và kết quả kỳ vọng

Giả sử:

| Tenant | Status | SKU | amountMinor |
| --- | --- | --- | --- |
| test-a | PAID | BOOK-101 | 10000 |
| test-a | PAID | BOOK-101 | 25000 |
| test-a | PAID | PEN-002 | 5000 |
| test-a | PENDING | BOOK-101 | 90000 |
| test-b | PAID | BOOK-101 | 70000 |

Expected với tenant=test-a:

~~~javascript
[
  { sku: "BOOK-101", orderCount: 2, revenueMinor: 35000 },
  { sku: "PEN-002", orderCount: 1, revenueMinor: 5000 }
]
~~~

### 22.2. Ví dụ JUnit

~~~java
package com.example.sales;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.stream.Stream;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class SaleEventAggregationStreamTest {

    @Autowired SaleEventRepository repository;
    @Autowired MongoTemplate template;

    private SaleEventDocument event(
            String tenant, String status, String sku, long amount) {
        return new SaleEventDocument(
            new ObjectId(),
            tenant,
            status,
            sku,
            amount,
            Instant.parse("2025-06-01T09:00:00Z")
        );
    }

    @Test
    void streamsGroupedRevenueAndClosesStream() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "OTHER-" + UUID.randomUUID();

        List<SaleEventDocument> inserted = repository.saveAll(List.of(
            event(tenant, "PAID", "BOOK-101", 10_000),
            event(tenant, "PAID", "BOOK-101", 25_000),
            event(tenant, "PAID", "PEN-002", 5_000),
            event(tenant, "PENDING", "BOOK-101", 90_000),
            event(otherTenant, "PAID", "BOOK-101", 70_000)
        ));

        try {
            List<SkuRevenueRow> rows;

            try (Stream<SkuRevenueRow> stream =
                    repository.streamPaidRevenueByTenant(tenant)) {
                rows = stream.toList();
            }

            assertThat(rows).hasSize(2);
            assertThat(rows.get(0).sku()).isEqualTo("BOOK-101");
            assertThat(rows.get(0).orderCount()).isEqualTo(2L);
            assertThat(rows.get(0).revenueMinor()).isEqualTo(35_000L);
            assertThat(rows.get(1).sku()).isEqualTo("PEN-002");
            assertThat(rows.get(1).revenueMinor()).isEqualTo(5_000L);
        } finally {
            repository.deleteAllById(
                inserted.stream().map(SaleEventDocument::id).toList()
            );
        }
    }
}
~~~

Test trên **đọc và đóng Stream đúng cách** và xác minh filter, group, sort và DTO mapping. Nhưng việc dùng try-with-resources **không tự chứng minh server cursor thực sự đã nhận killCursors** trong trường hợp dừng sớm. Muốn test đóng cursor chi tiết, cần instrument MongoDB command monitoring/driver metrics hoặc kiểm tra cursor lifecycle phù hợp với môi trường test.

**Không chạy test lên collection production.** Để tránh va chạm với dữ liệu khác, fixture dùng tenant ID riêng và dọn theo ID đã tạo.

### 22.3. Test exception vẫn đóng Stream

Với một stream resource giả có close hook, có thể unit test rằng một service dùng try-with-resources sẽ gọi close khi Consumer ném lỗi. Integration test tương ứng có thể cố tình ném exception ở phần tử đầu trong vòng lặp, rồi đo metrics cursor/command khi driver đóng.

Đừng chỉ assert ném RuntimeException rồi kết luận **mọi tài nguyên network đã được giải phóng đúng thời điểm** mà không có instrumentation.

## 23. Kiểm thử Flux và cancellation

Với repository reactive, sử dụng **StepVerifier** để xác minh dữ liệu:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .map(SkuRevenueRow::sku)
)
.expectNext("BOOK-101")
.expectNext("PEN-002")
.verifyComplete();
~~~

Đoạn mã giả định **reactiveRepository** đã được inject và dữ liệu test giống phần 22. Bộ test cần dependency **reactor-test**.

### 23.1. Hủy sớm

~~~java
StepVerifier.create(
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .take(1)
)
.expectNextCount(1)
.verifyComplete();
~~~

**take(1)** hoàn thành downstream sau một phần tử và hủy upstream khi còn dữ liệu. Điều này kiểm tra flow ở mức Reactor, nhưng **chưa đủ để khẳng định cursor server đã đóng**. Nếu tài nguyên là một yêu cầu kiểm soát quan trọng, bổ sung metrics/command monitoring, theo dõi số cursor mở và thử lỗi mạng.

### 23.2. Tín hiệu lỗi và cancel

Một test có thể thêm:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.publisher.SignalType;

AtomicReference<SignalType> terminal =
    new AtomicReference<>();

StepVerifier.create(
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .doFinally(terminal::set)
        .take(1)
)
.expectNextCount(1)
.verifyComplete();
~~~

**Không dùng assert về thời điểm doFinally gọi ngay lập tức nếu test có race bất đồng bộ**. Nếu cần chứng minh tín hiệu, sử dụng cơ chế đồng bộ hóa test phù hợp hoặc đặt hook ở vị trí và mô hình scheduling được kiểm soát.

### 23.3. Test nhiều tenant

Cần seed ít nhất một event có cùng SKU thuộc tenant khác rồi xác minh event đó không góp vào count/doanh thu. Việc lọc đúng tenant là yêu cầu bảo mật quan trọng hơn một thay đổi nhỏ về hiệu năng streaming.

## 24. Chẩn đoán lỗi và rò cursor

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| RAM tăng khi export | Dùng List/collectList hoặc buffer không giới hạn | Stream/Flux và xử lý từng dòng; giới hạn đầu ra |
| Cursor tồn tại lâu | Stream không close, consumer quá chậm | try-with-resources, timeout, metrics |
| Controller trả Stream rồi lỗi sau đó | Resource sống vượt phạm vi owner | Tiêu thụ trong callback có lifecycle rõ |
| findFirst/limit(10) xong vẫn còn cursor | Terminal operation không thay trách nhiệm close | try-with-resources |
| Không có kết quả reactive | Chưa có subscription | Trả Flux cho WebFlux/caller phù hợp |
| Aggregation chạy hai lần | subscribe hai lần hoặc retry/repeat | Đảm bảo một subscription theo request |
| Client ngắt mà server vẫn xử lý | Cleanup/cancel bất đồng bộ hoặc blocking server stage | Đo metrics, maxTimeMS, filter sớm |
| First row rất chậm | $group/$sort cần tính toán nhiều dữ liệu | Đánh giá pipeline và index |
| Stream đã đóng trước khi duyệt | Trả Stream ra khỏi try hoặc transaction | Tiêu thụ trong scope sở hữu |
| Error ở row 1000 và file nửa chừng | Streaming không rollback output | File tạm, publish khi complete |
| Reactive stream tăng heap | collectList/sort/buffer/groupBy giữ nhiều phần tử | Đánh giá từng operator, giới hạn |
| Query chậm dù có $limit cuối | $group phải xử lý đầu vào lớn | $match sớm và index đúng |
| Cursor timeout/invalid | Stream giữ quá lâu, session/transaction kết thúc | Giảm thời gian giữ cursor, chia batch |
| Mapping DTO sai | $project tên field/kiểu số không khớp | Test raw BSON và constructor |
| Sort lệch sau @Aggregation | Sort parameter append sau pipeline | Kiểm tra thứ tự stage thực |
| Aggregation không hỗ trợ Page | @Aggregation repository không tự trả Page | Dùng Slice/thiết kế count riêng |
| Error khi aggregateStream + explain | Streaming aggregation không hỗ trợ explain mode | Chạy explain riêng |
| Export lộ tenant khác | Không ràng buộc tenant vào $match | Auth tenant + kiểm thử cross-tenant |

### 24.1. Quy trình điều tra

1. Xác định đang dùng **List**, **Stream** hay **Flux**.
2. Xác minh pipeline có filter tenant/status và thời gian đúng không.
3. Kiểm tra stage nào có thể chặn phát kết quả: $group, $sort, $lookup.
4. Đọc execution plan/metrics để xác định có COLLSCAN hoặc spill không.
5. Đo số kết quả thật và số tài nguyên cursor đang mở.
6. Với Stream, xem caller có try-with-resources ở **mọi đường đi** không.
7. Với Flux, xem subscription, cancellation, timeout và operator giữ bộ nhớ.
8. Kiểm tra transaction/session không kết thúc trước khi consume dữ liệu.
9. Tái hiện bằng test dừng sớm, lỗi mid-stream và client hủy.
10. Chỉ sau đó tối ưu batch size, index, pipeline và cơ chế xuất file.

## 25. Bài tập thực hành

### Bài tập 1: Stream hay List?

Một báo cáo có 200.000 dòng SKU và service cần ghi tuần tự từng dòng vào file, không cần giữ tất cả trong RAM. Nên cân nhắc kiểu nào?

**Đáp án:** **Stream<SkuRevenueRow>** với try-with-resources trong stack đồng bộ, hoặc **Flux<SkuRevenueRow>** trong reactive stack. Cả hai vẫn cần pipeline/index phù hợp.

### Bài tập 2: đóng cursor

Viết code Java duyệt repository Stream và đóng trong mọi đường:

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {
    rows.forEach(this::writeRow);
}
~~~

**Giải thích:** try-with-resources đóng Stream kể cả khi writeRow ném lỗi.

### Bài tập 3: lỗi khi return Stream

Method return Stream từ bên trong try-with-resources có an toàn không?

**Đáp án:** Không. Stream sẽ bị đóng khi thoát khối try, trước khi caller tiêu thụ. Cần chuyển quyền sở hữu có hợp đồng rõ hoặc xử lý trong cùng scope.

### Bài tập 4: findFirst

Một method gọi **stream.findFirst()** rồi return kết quả. Có cần close Stream không?

**Đáp án:** Có. Terminal operation có thể ngừng trước khi cursor hết và không thay trách nhiệm đóng tài nguyên.

### Bài tập 5: Flux và subscribe

Tạo một Flux từ reactive repository rồi không subscribe. MongoDB đã chắc chắn chạy aggregation chưa?

**Đáp án:** Chưa. Publisher lazy và thường chỉ thực thi khi có subscription.

### Bài tập 6: take(10)

Vì sao **Flux.take(10)** không đồng nghĩa MongoDB chỉ xử lý 10 sale event?

**Đáp án:** $group/$sort có thể cần xử lý nhiều input để tạo kết quả; take(10) chỉ giới hạn phần tử downstream nhận và cancel upstream sau khi đủ.

### Bài tập 7: collectList

Làm thế nào một Flux từ MongoDB có thể gây tràn heap dù driver hỗ trợ backpressure?

**Đáp án:** Downstream dùng collectList, sort, buffer không giới hạn hoặc giữ mọi row; backpressure không giải quyết việc ứng dụng cố tình tích lũy toàn bộ dữ liệu.

### Bài tập 8: export lỗi giữa chừng

Đã ghi 1.000 dòng ra file thì driver ném lỗi. File đó có tự rollback thành rỗng không?

**Đáp án:** Không. Cần ghi ra file tạm, chỉ công bố sau khi onComplete hoặc vòng đọc thành công; đánh dấu output incomplete khi lỗi.

### Bài tập 9: cursor và transaction

Bạn return Stream từ một @Transactional method và để caller duyệt sau. Rủi ro?

**Đáp án:** Transaction/session có thể đã kết thúc trước khi Stream được consume, gây lỗi/lifecycle không phù hợp. Duyệt và close trong scope sở hữu đúng.

### Bài tập 10: @Aggregation và Page

Repository @Aggregation trả Page<DTO> để tự đếm total có phải hợp đồng được hỗ trợ không?

**Đáp án:** Không. Tài liệu Spring Data MongoDB không hỗ trợ Page return cho @Aggregation repository; dùng Slice với Pageable hoặc thiết kế count riêng nếu cần total.

### Bài tập 11: $limit vị trí nào?

Muốn 10 SKU doanh thu cao nhất, nên đặt $limit trước hay sau $group/$sort?

**Đáp án:** $match → $group → $sort theo revenueMinor DESC → $limit(10). Đặt limit trước group sẽ chỉ tính trên một tập event nhỏ.

### Bài tập 12: Mono hay Flux?

Một pipeline trả nhiều SKU và dùng ReactiveMongoRepository. Nên trả Mono<SkuRevenueRow> hay Flux<SkuRevenueRow>?

**Đáp án:** Flux<SkuRevenueRow>. Mono phù hợp tối đa một giá trị, chẳng hạn một tổng doanh thu duy nhất.

### Bài tập 13: batch size

Cursor có batchSize=100 thì MongoDB chỉ trả tối đa 100 kết quả trong suốt truy vấn đúng không?

**Đáp án:** Không. Batch size kiểm soát cách trao đổi dữ liệu theo lô; tổng kết quả có thể lớn hơn và được trả qua nhiều batch/getMore.

### Bài tập 14: callback onComplete

Chỉ dùng doOnComplete để đóng một file writer có an toàn nếu client cancel không?

**Đáp án:** Không. doOnComplete không chạy cho mọi trường hợp error/cancel. Dùng quản lý resource rõ ràng như usingWhen hoặc finally/doFinally phù hợp.

### Bài tập 15: hiệu năng

Một Flux phát phần tử đầu tiên sau 45 giây dù client nhanh. Nguyên nhân có thể là gì?

**Đáp án:** $group/$sort, thiếu index ở $match, scan nhiều event hoặc server spill. Phải xem explain/profiler và tối ưu pipeline, không chỉ chỉnh Reactor backpressure.

## 26. Checklist trước khi triển khai

- **Kết quả:** report có đủ lớn để cần Stream/Flux không?
- **Kiểu API:** repository đồng bộ dùng Stream; reactive dùng Flux đúng không?
- **Cursor owner:** có try-with-resources cho mọi Stream đồng bộ không?
- **Scope:** không trả Stream đã đóng hoặc ra khỏi transaction/session scope chứ?
- **Cancellation:** client hủy/timeout có được quan sát không?
- **Error:** đã có phương án cho dữ liệu/file/HTTP response ghi được một phần chưa?
- **Backpressure:** có toán tử nào collect/buffer/sort toàn bộ dữ liệu trong Java không?
- **Batch:** có hiểu batchSize khác $limit và limitRate không?
- **Filter:** $match có tenant và điều kiện phân quyền bắt buộc chưa?
- **Sort:** thứ tự nhóm và vị trí $sort/$limit đúng nghiệp vụ chưa?
- **Index:** đã đo keys/docs examined và query plan chưa?
- **Blocking stage:** đã đánh giá chi phí $group/$sort/$lookup chưa?
- **Disk/time:** allowDiskUse và maxTimeMS có phù hợp workload không?
- **Response:** có format streaming và giao thức phát hiện partial output không?
- **Transaction:** không giữ transaction dài chỉ vì cần export chứ?
- **Consistency:** báo cáo có yêu cầu snapshot/cutoff đã được thiết kế chưa?
- **Testing:** đã test đủ dữ liệu, multi-tenant, error, cancel và close chưa?
- **Metrics:** có đo duration, emitted rows, cancellation, cursor lifetime không?

## 27. Tổng kết

1. **@Aggregation repository có thể trả Stream hoặc Flux**, không phải lúc nào cũng phải trả List.
2. **Stream<T> đồng bộ thường bao bọc MongoDB cursor**. Caller phải close, tốt nhất bằng try-with-resources.
3. **Flux<T> reactive thực thi theo subscription/demand**; terminal/error/cancel phối hợp giải phóng cursor qua driver/framework.
4. **Đóng Stream vẫn cần thiết khi findFirst, limit, exception hoặc return sớm**, không chỉ khi duyệt hết.
5. **Reactive backpressure không có nghĩa mọi operator đều streaming**; collectList/sort/buffer có thể tích lũy lớn.
6. **$group/$sort vẫn có thể giữ nhiều trạng thái trên server**, nên trả Flux không làm pipeline nặng trở thành miễn phí.
7. **MongoTemplate.aggregateStream** dành cho synchronous aggregation và **ReactiveMongoTemplate.aggregate** dành cho reactive pipeline.
8. **$match, index, $limit đúng vị trí, maxTimeMS và quan sát resource** giúp giảm tải hơn việc chỉ chọn return type.
9. **@Aggregation không tự trả Page có total**, cần Slice hoặc thiết kế count theo yêu cầu.
10. **Transaction/session scope và cursor scope phải phù hợp**; không để Stream thoát ra ngoài khi context đã kết thúc.
11. **Streaming output có thể dở dang khi lỗi/cancel**, cần phương án publish/rollback ở tầng xuất file hoặc giao thức ứng dụng.
12. **Kiểm thử MongoDB thật và metrics cursor** là cách kiểm chứng cả tính đúng đắn và vòng đời tài nguyên.

Nắm vững cách sử dụng **Stream hoặc Flux kết quả và đóng cursor** giúp dịch vụ **SPRING_DATA_MONGODB** xây dựng các báo cáo aggregation có thể mở rộng, tránh giữ toàn bộ kết quả trong bộ nhớ, chủ động quản lý tài nguyên đồng bộ và khai thác đúng cancellation/backpressure của reactive access.

### Tài liệu tham khảo

- [Spring Data MongoDB — MongoDB-specific Query Methods / Aggregation Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — @Aggregation, return type Stream, Slice, @Meta và giới hạn Page.
- [Spring Data — Defining Query Methods / Streaming Query Results](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html) — quy tắc close Stream, List so với Stream/Flux.
- [Spring Data MongoDB — MongoOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html) — aggregateStream, lifecycle và giới hạn với aggregation explain.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — Aggregation, group, project, sort và aggregation execution.
