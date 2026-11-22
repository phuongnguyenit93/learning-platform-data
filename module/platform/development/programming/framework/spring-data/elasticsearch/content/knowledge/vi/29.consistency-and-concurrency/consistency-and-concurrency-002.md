# GET theo id và search có đặc điểm nhất quán khác nhau

Elasticsearch cung cấp hai cách đọc document thường gặp: lấy một document theo ID bằng Get API và tìm kiếm theo điều kiện bằng Search API. Hai cách đọc này có đặc điểm nhất quán khác nhau vì chúng sử dụng các cơ chế đọc dữ liệu khác nhau.

**Get API là real-time theo mặc định:** sau khi một thao tác index/update/delete được chấp nhận, ứng dụng có thể đọc trạng thái mới nhất của document theo ID mà không cần chờ refresh.

**Search API là near-real-time:** search chỉ nhìn thấy những thay đổi đã được refresh thành các segment searchable. Một document vừa ghi có thể đọc được ngay bằng GET nhưng chưa xuất hiện trong kết quả search.

Đây là hành vi có chủ đích để Elasticsearch cân bằng giữa tốc độ ghi và khả năng tìm kiếm. Khi thiết kế ứng dụng Spring Data Elasticsearch, cần chọn đúng cách đọc theo nhu cầu: đọc ngay một document theo ID, tìm document theo nội dung/điều kiện, hay yêu cầu read-after-write cho một truy vấn search.

## 1. Hai cách đọc dữ liệu

### Get theo ID

Get API lấy một document cụ thể từ index dựa trên `_id`:

```http
GET /products/_doc/P-100
```

Đây là lựa chọn phù hợp khi ứng dụng đã biết ID và cần đọc một document. Get API là real-time theo mặc định, không phụ thuộc refresh interval của index.

### Search theo điều kiện

Search API tìm một tập document theo query:

```http
GET /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Search API hoạt động theo mô hình near-real-time. Nó tìm trên dữ liệu đã được refresh và có thể chưa thấy thao tác ghi vừa hoàn tất nếu refresh chưa xảy ra.

| Đặc điểm | Get API | Search API |
|---|---|---|
| Cách chọn document | Theo `_id` và tùy chọn routing. | Theo query, filter, sort và aggregation. |
| Visibility mặc định | Real-time. | Near-real-time. |
| Phụ thuộc refresh để thấy write mới | Không, nếu `realtime=true` mặc định. | Có. |
| Có thể đọc một document theo ID | Có, là mục đích chính. | Có thể query theo ID, nhưng không phải cơ chế Get API. |
| Phù hợp | Read-after-write theo ID, chi tiết một entity. | Tìm kiếm, lọc, xếp hạng, aggregation và danh sách. |

Không nên hiểu “real-time GET” là mọi thao tác đọc trên toàn cluster đều có transaction snapshot mạnh. Đây là đặc tính của thao tác lấy document theo ID trên shard tương ứng; search nhiều document và nhiều shard vẫn có semantics riêng.

## 2. Vì sao GET thấy dữ liệu mới trước Search?

Elasticsearch ghi document vào các cấu trúc nội bộ và translog. Get API có thể đọc phiên bản mới nhất của document ngay cả khi document chưa được đưa vào một searcher mới. Search API thì đọc các segment đã được refresh để có thể tìm kiếm.

Quá trình đơn giản hóa:

```text
Client
  |
  | index/update/delete
  v
Elasticsearch shard
  |
  +---- ghi thay đổi và translog
  |          |
  |          +----> Real-time GET có thể thấy phiên bản mới
  |
  +---- chờ refresh
             |
             v
       Mở searcher mới
             |
             +----> Search nhìn thấy thay đổi
```

Vì vậy, ngay sau khi index một document:

- `GET /products/_doc/P-100` có thể trả document mới.
- Một search query khớp document đó có thể chưa trả kết quả.
- Sau refresh, search sẽ nhìn thấy document mới.

Đây không phải lỗi dữ liệu hay cache bug. Đây là khác biệt giữa real-time document retrieval và near-real-time search visibility.

## 3. Ví dụ: index xong, GET thấy nhưng Search chưa thấy

Giả sử index `products` đã tồn tại và ứng dụng tạo sản phẩm:

```http
PUT /products/_doc/P-100
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "status": "ACTIVE",
  "price": 2500000
}
```

Sau khi request ghi trả về thành công, đọc theo ID:

```http
GET /products/_doc/P-100
```

Get API có thể trả về document vừa tạo ngay lập tức.

Nhưng search theo trạng thái:

```http
GET /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

có thể chưa chứa `P-100` nếu shard chưa refresh kể từ lúc ghi.

Sau khi refresh index:

```http
POST /products/_refresh
```

chạy lại Search API sẽ nhìn thấy document.

Điểm cần nhớ: response thành công của thao tác index có nghĩa Elasticsearch đã chấp nhận/xử lý thao tác ghi theo semantics của API. Nó không mặc nhiên có nghĩa document đã searchable ngay trong Search API.

## 4. GET có thể chuyển sang chế độ không realtime

Get API có tham số `realtime`. Mặc định là `true`:

```http
GET /products/_doc/P-100?realtime=true
```

Khi `realtime=true`, GET có thể đọc phiên bản mới nhất chưa refresh.

Nếu đặt `realtime=false`:

```http
GET /products/_doc/P-100?realtime=false
```

GET chỉ đọc từ góc nhìn searchable đã refresh. Khi đó nó có thể chưa thấy thay đổi mới nhất, tương tự vấn đề visibility của search.

`realtime=false` hữu ích khi muốn kiểm tra trạng thái đã searchable thay vì trạng thái mới nhất của document theo ID. Trong ứng dụng thông thường, không cần tắt realtime nếu không có yêu cầu rõ ràng.

## 5. Refresh là gì?

Refresh làm cho các thay đổi đã được index trở nên searchable bằng cách mở một searcher mới trên các segment phù hợp. Đây là bước tạo khả năng nhìn thấy dữ liệu qua Search API.

Refresh khác với flush và khác với việc ghi bền vững:

| Cơ chế | Vai trò |
|---|---|
| Index/update/delete | Ghi thay đổi của document. |
| Translog | Ghi nhận thao tác để hỗ trợ recovery/durability theo cấu hình. |
| Refresh | Làm thay đổi trở nên nhìn thấy qua Search API. |
| Flush | Tạo Lucene commit và xử lý translog; là cơ chế khác với refresh. |

Không gọi refresh là “commit transaction”. Refresh chủ yếu giải quyết search visibility. Durability và recovery có cơ chế riêng, trong đó translog và flush đóng vai trò khác.

### 5.1. Refresh interval

Elasticsearch tự refresh index theo refresh interval. Giá trị mặc định thường khoảng một giây đối với index đang hoạt động tìm kiếm, nhưng có thể thay đổi theo setting, phiên bản và trạng thái hoạt động của index.

Ứng dụng không nên dựa vào một khoảng thời gian cố định như “đợi đúng một giây là chắc chắn search thấy”. Nếu cần bảo đảm visibility cho một thao tác ghi cụ thể, dùng refresh policy phù hợp thay vì `Thread.sleep`.

### 5.2. Refresh có chi phí

Refresh thường nhẹ hơn một flush nhưng không miễn phí. Refresh quá thường xuyên có thể tạo nhiều segment nhỏ, tăng chi phí merge và làm giảm throughput indexing.

Vì vậy:

- Không refresh sau mỗi document nếu không cần thiết.
- Không gọi refresh trong mọi request ghi chỉ để giải quyết một lỗi đọc sau ghi ở tầng ứng dụng.
- Với import/bulk lớn, thường ghi theo batch rồi refresh khi cần công bố dữ liệu.
- Chọn refresh interval dựa trên yêu cầu freshness và workload thực tế.

## 6. Các lựa chọn refresh khi ghi

Các API ghi Elasticsearch hỗ trợ tham số `refresh` với ba lựa chọn thường dùng:

| Giá trị | Ý nghĩa | Hệ quả |
|---|---|---|
| `false` | Không yêu cầu refresh bổ sung. Đây là mặc định phổ biến. | Search nhìn thấy dữ liệu sau lần refresh tiếp theo. |
| `true` | Yêu cầu refresh ngay các shard liên quan trước khi response hoàn tất. | Read-after-write qua search nhanh hơn, nhưng có thể giảm throughput. |
| `wait_for` | Chờ lần refresh tiếp theo làm thay đổi searchable. | Tránh ép refresh riêng ngay lập tức, nhưng response có thể phải chờ. |

### 6.1. `refresh=true`

Ví dụ:

```http
PUT /products/_doc/P-101?refresh=true
Content-Type: application/json

{
  "name": "Wireless Mouse",
  "status": "ACTIVE",
  "price": 450000
}
```

Khi request hoàn tất, thao tác ghi đã được refresh trên các shard liên quan và search có thể nhìn thấy thay đổi.

Đây là cách mạnh tay để có search visibility ngay sau write, nhưng dùng thường xuyên có thể gây nhiều refresh không cần thiết. Chỉ dùng khi latency/visibility requirement thực sự cần và đã đánh giá ảnh hưởng.

### 6.2. `refresh=wait_for`

Ví dụ:

```http
PUT /products/_doc/P-102?refresh=wait_for
Content-Type: application/json

{
  "name": "USB-C Hub",
  "status": "ACTIVE",
  "price": 850000
}
```

Elasticsearch chờ lần refresh tiếp theo làm document searchable rồi mới hoàn tất response. `wait_for` thường phù hợp hơn `true` cho read-after-write qua search khi ứng dụng chấp nhận chờ một khoảng refresh.

Nếu refresh tự động bị tắt, ví dụ `refresh_interval=-1`, request `wait_for` có thể chờ đến khi một thao tác refresh khác xảy ra hoặc hết timeout. Khi dùng chế độ này, phải hiểu cấu hình refresh của index.

### 6.3. `refresh=false`

Ví dụ:

```http
PUT /products/_doc/P-103?refresh=false
Content-Type: application/json

{
  "name": "Monitor Stand",
  "status": "ACTIVE",
  "price": 650000
}
```

Request không yêu cầu refresh. Đây là lựa chọn phù hợp cho throughput ghi thông thường khi search visibility có thể chờ chu kỳ refresh tự nhiên.

## 7. Đọc sau khi ghi: chọn chiến lược theo yêu cầu

Không có một cách đọc duy nhất phù hợp cho mọi trường hợp. Hãy xem ứng dụng cần đọc theo ID hay cần tìm theo điều kiện.

| Nhu cầu | Cách tiếp cận |
|---|---|
| Lưu xong cần hiển thị chính entity vừa lưu theo ID | Dùng real-time GET theo ID. |
| Lưu xong cần tìm entity bằng query/search | Ghi với `refresh=wait_for` hoặc refresh phù hợp trước search. |
| Ghi nhiều document rồi mới hiển thị danh sách | Bulk write, sau đó refresh một lần khi hoàn tất nếu cần. |
| Không cần search thấy ngay | Giữ mặc định `refresh=false`, chấp nhận near-real-time. |
| Cần kiểm tra dữ liệu đã searchable | Dùng search sau refresh hoặc GET với `realtime=false` cho document đã biết ID. |
| Cần đọc trạng thái mới nhất của một document trong luồng cập nhật | GET real-time theo ID và xử lý concurrency/version. |

### 7.1. Không dùng search để thay GET nếu đã biết ID

Nếu giao diện vừa tạo một sản phẩm và cần chuyển sang trang chi tiết, không nhất thiết phải search bằng `term` trên ID. Dùng GET theo ID là tự nhiên và có thể đọc ngay phiên bản vừa ghi.

Ngược lại, nếu giao diện cần cập nhật danh sách “tất cả sản phẩm active dưới 1 triệu”, đó là một truy vấn search. Real-time GET của một document không làm cho truy vấn danh sách tự nhìn thấy thay đổi.

## 8. GET và Search sau Update

Khác biệt không chỉ xuất hiện khi tạo mới. Với update, GET có thể thấy nội dung mới trong khi Search vẫn trả nội dung cũ cho đến refresh.

Ví dụ document ban đầu:

```json
{
  "name": "Mechanical Keyboard",
  "status": "ACTIVE",
  "price": 2500000
}
```

Cập nhật giá:

```http
POST /products/_update/P-100
Content-Type: application/json

{
  "doc": {
    "price": 2300000
  }
}
```

Ngay sau khi update thành công:

- GET theo ID có thể trả `price = 2300000`.
- Search query có thể vẫn trả phiên bản searchable trước đó với `price = 2500000` hoặc vẫn đánh giá document theo dữ liệu cũ.
- Sau refresh, search nhìn thấy phiên bản mới.

Nếu query phụ thuộc field vừa cập nhật, ví dụ `price <= 2400000`, document có thể chưa xuất hiện trong kết quả mới ngay cả khi GET đã cho thấy giá mới.

## 9. GET và Search sau Delete

Delete cũng thể hiện rõ khác biệt visibility.

Xóa document:

```http
DELETE /products/_doc/P-100
```

Sau khi delete được chấp nhận:

- GET realtime theo ID có thể trả 404 ngay.
- Search có thể vẫn trả document cũ cho đến khi delete được refresh và trở nên searchable.

Điều này có thể làm một màn hình danh sách tạm thời hiển thị document vừa bị xóa, trong khi trang chi tiết theo ID đã báo không tìm thấy.

Nếu nghiệp vụ cần danh sách search phản ánh delete ngay sau thao tác, dùng refresh policy phù hợp. Nếu giao diện chấp nhận near-real-time, có thể cập nhật UI lạc quan hoặc chờ refresh tự nhiên.

## 10. Spring Data Elasticsearch: `get` và `search`

Spring Data Elasticsearch cung cấp hai đường API tương ứng:

- `ElasticsearchOperations.get(id, Entity.class)` lấy một entity theo ID.
- `ElasticsearchOperations.search(query, Entity.class)` thực hiện search và trả `SearchHits<Entity>`.

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private double price;

    // constructors, getters, setters
}
```

Lưu rồi đọc theo ID:

```java
ProductDocument saved = operations.save(product);

ProductDocument loaded = operations.get(
        saved.getId(),
        ProductDocument.class
);
```

`get` dùng thao tác lấy document theo ID và mặc định có semantics real-time của Elasticsearch.

Search theo điều kiện:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query activeQuery = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(activeQuery)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

`search` dùng Search API nên chỉ nhìn thấy dữ liệu đã refresh. Nếu vừa gọi `save` rồi search ngay, kết quả có thể chưa chứa entity vừa lưu.

### 10.1. Repository cũng có khác biệt tương tự

Với Spring Data repository:

```java
Optional<ProductDocument> byId = productRepository.findById("P-100");
```

`findById` là thao tác đọc theo ID. Các method truy vấn như:

```java
List<ProductDocument> activeProducts =
        productRepository.findByStatus("ACTIVE");
```

được thực hiện như search query. Vì vậy, hai method có thể tạm thời cho kết quả khác nhau ngay sau write.

Khi thiết kế service, không nên giả định tất cả method của repository đều có cùng freshness semantics. Hãy xác định method nào đi qua Get API và method nào tạo Search API.

## 11. Refresh bằng Spring Data Elasticsearch

Nếu cần làm dữ liệu searchable trước khi chạy search, có thể gọi refresh qua `IndexOperations`:

```java
operations.save(product);

operations.indexOps(ProductDocument.class).refresh();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Refresh làm các thay đổi đã được index trên index tương ứng trở nên nhìn thấy qua Search API. Chỉ gọi khi có yêu cầu rõ ràng; nếu dùng trong mỗi request ghi, có thể giảm throughput.

### 11.1. Refresh sau bulk import

Với import nhiều batch:

```java
for (List<IndexQuery> batch : batches) {
    operations.bulkIndex(batch, ProductDocument.class);
}

operations.indexOps(ProductDocument.class).refresh();
```

Mẫu này tránh refresh sau từng batch và chỉ làm dữ liệu searchable sau khi toàn bộ import hoàn tất. Trong ứng dụng production, nên đảm bảo mọi bulk item đã được xử lý và lỗi đã được giải quyết trước khi refresh/công bố.

### 11.2. Refresh policy cho Bulk API

Spring Data Elasticsearch có `BulkOptions` để cấu hình refresh policy cho bulk operation ở các phiên bản hỗ trợ:

```java
import org.springframework.data.elasticsearch.core.BulkOptions;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        ProductDocument.class
);
```

`WAIT_UNTIL` yêu cầu chờ refresh tiếp theo làm các thay đổi searchable. Có thể chọn `IMMEDIATE` hoặc `NONE` theo nhu cầu và API version. Với bulk lớn, `NONE` rồi refresh một lần sau khi hoàn tất thường giảm số lần refresh cưỡng bức.

Tên enum, package và overload của `BulkOptions` có thể khác giữa các phiên bản Spring Data Elasticsearch; cần dùng API tương thích với dependency của dự án.

## 12. GET có custom routing

Nếu document được index với custom routing, Get API phải nhận cùng routing value. Ví dụ:

```http
PUT /orders/_doc/O-100?routing=customer-42
{
  "customer_id": "customer-42",
  "status": "PAID"
}
```

Đọc theo ID cần routing:

```http
GET /orders/_doc/O-100?routing=customer-42
```

Nếu bỏ routing, request có thể tìm sai shard và trả 404. Điều này không phải vấn đề refresh; document có thể đã tồn tại nhưng được định tuyến đến shard khác.

Trong Spring Data, có thể cấu hình routing cho thao tác get theo ID:

```java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;

OrderDocument order = operations
        .withRouting(RoutingResolver.just("customer-42"))
        .get("O-100", OrderDocument.class);
```

Hãy phân biệt hai nguyên nhân:

- GET không tìm thấy do sai/mất routing.
- Search chưa thấy do dữ liệu chưa refresh.

Chờ refresh không sửa được lỗi routing.

## 13. Search consistency trong môi trường nhiều shard

Một search request có thể được phân phối đến nhiều shard. Mỗi shard có searcher/refresh state của riêng nó. Elasticsearch không cung cấp transaction snapshot toàn cluster cho mọi Search API request thông thường.

Một số hệ quả:

- Thay đổi trên các shard khác nhau có thể trở nên searchable ở các thời điểm khác nhau.
- Một search trên nhiều shard có thể quan sát trạng thái refresh không hoàn toàn đồng thời giữa các shard.
- Search request tiếp theo có thể nhìn thấy thêm document sau khi một shard được refresh.
- Replica selection và trạng thái shard copy có thể ảnh hưởng đến shard copy phục vụ search.

Vì vậy, không nên mô tả Search API là một snapshot giao dịch nhất quán trên tất cả document và shard. Nó là một truy vấn trên các searcher đang khả dụng ở thời điểm request chạy.

Nếu cần duyệt một tập kết quả ổn định qua nhiều request, có thể dùng Point in Time (PIT) kết hợp `search_after`. PIT giữ góc nhìn search ổn định cho các trang tiếp theo, nhưng không đưa các write mới sau thời điểm mở PIT vào snapshot đó.

## 14. Preference và refresh không giải quyết cùng một vấn đề

Search API có tham số `preference` để kiểm soát shard copy hoặc tính ổn định của việc chọn shard trong một số trường hợp. Ví dụ `_primary` yêu cầu search trên primary shard copy.

Tuy nhiên, `preference=_primary` không thay thế refresh. Nếu primary shard chưa refresh, search trên primary vẫn có thể chưa thấy thay đổi mới.

Tương tự, chỉ chọn cùng một replica không đảm bảo dữ liệu mới đã searchable. Muốn thay đổi xuất hiện trong search, cần refresh visibility phù hợp.

## 15. GET real-time không thay thế optimistic concurrency control

GET theo ID có thể trả phiên bản mới nhất hiện có của document, nhưng nếu nhiều client cùng đọc rồi cập nhật, vẫn có nguy cơ lost update.

Ví dụ:

1. Client A đọc số lượng tồn kho là 10.
2. Client B cũng đọc số lượng tồn kho là 10.
3. A cập nhật thành 9.
4. B cập nhật dựa trên giá trị cũ thành 8.

Nếu không kiểm soát concurrency, một cập nhật có thể ghi đè cập nhật khác.

Elasticsearch hỗ trợ optimistic concurrency control bằng `_seq_no` và `_primary_term`.

Đọc document kèm metadata:

```http
GET /products/_doc/P-100?seq_no_primary_term=true
```

Response chứa `_seq_no` và `_primary_term`. Khi ghi cập nhật, gửi lại hai giá trị:

```http
PUT /products/_doc/P-100?if_seq_no=7&if_primary_term=3
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "status": "ACTIVE",
  "price": 2300000
}
```

Elasticsearch chỉ chấp nhận update nếu document vẫn có sequence number và primary term tương ứng. Nếu một client khác đã cập nhật trước, request có thể trả `409 version conflict`.

Ứng dụng cần đọc lại document, áp dụng lại thay đổi nghiệp vụ hoặc báo conflict cho người dùng. Không retry cùng payload cũ vô hạn.

### 15.1. Phân biệt refresh consistency và write concurrency

Hai vấn đề thường bị nhầm:

| Vấn đề | Câu hỏi | Cơ chế |
|---|---|---|
| Search visibility | Search đã nhìn thấy write mới chưa? | Refresh, `refresh=wait_for`, refresh interval. |
| Lost update | Một client có ghi đè thay đổi của client khác không? | Optimistic concurrency control, `_seq_no`, `_primary_term`, versioning. |
| Snapshot qua nhiều trang | Các trang có nhìn cùng một tập dữ liệu không? | PIT + `search_after` hoặc Scroll. |
| Tìm đúng shard | GET có đến shard chứa document không? | Routing value nhất quán. |

Refresh không ngăn lost update. OCC không làm document searchable ngay. PIT không làm write mới xuất hiện trong snapshot. Routing không thay thế các cơ chế còn lại.

## 16. Tình huống thực tế và lựa chọn phù hợp

### 16.1. Tạo đơn hàng rồi mở trang chi tiết

Sau khi lưu đơn hàng, ứng dụng đã biết ID được trả về. Dùng GET theo ID để đọc trang chi tiết. Không cần refresh chỉ để GET thấy document.

### 16.2. Tạo sản phẩm rồi cập nhật danh sách tìm kiếm

Nếu UI ngay lập tức gọi search để tìm sản phẩm mới theo tên hoặc category, cần `refresh=wait_for` ở thao tác ghi hoặc một refresh phù hợp trước search. Nếu không, sản phẩm có thể chưa xuất hiện trong danh sách trong một khoảng ngắn.

### 16.3. Cập nhật trạng thái rồi lọc danh sách

Ví dụ chuyển order từ `PENDING` sang `PAID`. GET theo ID có thể trả `PAID` ngay, nhưng search filter `status=PENDING` có thể vẫn trả order cho đến refresh. Nếu UI cần danh sách phản ánh thay đổi ngay, chọn chính sách visibility phù hợp.

### 16.4. Xóa document rồi kiểm tra bằng ID

GET theo ID có thể trả 404 ngay sau delete. Search có thể còn trả document cũ cho đến refresh. Nếu quy trình xóa cần xác nhận document không còn xuất hiện trong query search, phải đợi refresh visibility.

### 16.5. Bulk import rồi mở dashboard

Không nên refresh từng document hoặc từng batch nếu dashboard chỉ cần dữ liệu sau khi import hoàn tất. Import xong, kiểm tra lỗi item, refresh index một lần và sau đó mở dashboard.

## 17. Kiểm thử sự khác nhau giữa GET và Search

Nên có integration test với Elasticsearch thật hoặc Testcontainers. Mock `ElasticsearchOperations` không thể xác nhận refresh behavior và real-time GET.

### 17.1. Kiểm thử index mới

1. Tạo index test.
2. Index document `P-100` mà không yêu cầu refresh.
3. Gọi Get API theo ID và xác nhận document tồn tại.
4. Gọi Search API với query khớp document và kiểm tra có thể chưa thấy document.
5. Gọi refresh index.
6. Chạy lại Search API và xác nhận document xuất hiện.

Để test xác định được, có thể tắt refresh tự động trong index test bằng `refresh_interval=-1`, sau đó chủ động refresh ở bước 5. Điều này giúp loại bỏ race với refresh nền.

### 17.2. Kiểm thử update

1. Index document ban đầu và refresh.
2. Update một field.
3. GET theo ID và xác nhận giá trị mới.
4. Search theo giá trị mới trước refresh và xác nhận chưa thấy theo snapshot searchable cũ.
5. Refresh rồi search lại và xác nhận giá trị mới.

### 17.3. Kiểm thử delete

1. Index document và refresh.
2. Delete document.
3. GET theo ID và xác nhận 404.
4. Search trước refresh có thể vẫn thấy document cũ.
5. Refresh rồi search lại và xác nhận document biến mất.

### 17.4. Kiểm thử `realtime=false`

Sau khi index document mà chưa refresh:

- GET mặc định có thể thấy document.
- GET với `realtime=false` có thể chưa thấy document.
- Sau refresh, cả GET non-realtime và Search có thể thấy trạng thái mới.

### 17.5. Tránh kiểm thử bằng `Thread.sleep`

Không nên viết test:

```java
Thread.sleep(1000);
assertThat(search(...)).isNotEmpty();
```

Test có thể chập chờn vì refresh interval, tải máy và timing. Hãy gọi refresh API hoặc dùng `refresh=wait_for` để đồng bộ theo cơ chế thực tế.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Save thành công nhưng search không thấy document | Document chưa được refresh. | Dùng `refresh=wait_for` hoặc refresh khi thật sự cần. |
| GET thấy document nhưng danh sách search chưa có | GET real-time, Search near-real-time. | Đây là semantics bình thường; đồng bộ search visibility. |
| GET trả 404 nhưng document có trong index | Custom routing không được truyền hoặc ID/index sai. | Kiểm tra index, ID và routing. |
| GET trả dữ liệu mới nhưng search vẫn trả field cũ | Update chưa refresh. | Chờ refresh hoặc dùng refresh policy. |
| Delete trả thành công nhưng search vẫn thấy document | Delete chưa searchable do chưa refresh. | Refresh trước khi xác nhận bằng search. |
| Dùng `realtime=false` nhưng vẫn thấy trạng thái cũ | Searcher chưa được refresh. | Refresh index hoặc chờ refresh tự nhiên. |
| Gọi `refresh=true` mọi request làm indexing chậm | Refresh quá thường xuyên tạo overhead. | Dùng `wait_for`, refresh theo batch hoặc chấp nhận NRT. |
| `Thread.sleep` làm test lúc pass lúc fail | Timing refresh không được đồng bộ. | Dùng refresh API hoặc `refresh=wait_for`. |
| Search trên primary vẫn chưa thấy write | `preference=_primary` không ép refresh. | Giải quyết refresh visibility. |
| Client ghi đè cập nhật của client khác | Thiếu optimistic concurrency control. | Dùng `_seq_no`/`_primary_term` hoặc versioning. |
| PIT không thấy document mới vừa ghi | PIT giữ snapshot tại thời điểm mở. | Mở PIT mới nếu cần thấy dữ liệu mới. |
| Đọc sau ghi chỉ sai trên một số tenant | Routing value không nhất quán. | Dùng cùng routing khi index và get. |

## 19. Quy trình lựa chọn read-after-write

Khi thiết kế một luồng ghi rồi đọc, hãy đi theo các bước:

1. **Xác định loại đọc:** đọc một document theo ID hay tìm kiếm theo query?
2. **Nếu đã biết ID:** dùng Get API/Spring Data `get` để tận dụng real-time GET.
3. **Nếu cần search:** xác định có yêu cầu nhìn thấy ngay hay chấp nhận near-real-time.
4. **Nếu cần search ngay:** chọn `refresh=wait_for` hoặc refresh có kiểm soát.
5. **Nếu ghi nhiều item:** gom batch và refresh một lần sau khi hoàn tất nếu phù hợp.
6. **Nếu có nhiều writer:** dùng OCC/versioning để tránh lost update.
7. **Nếu phân trang qua nhiều request:** cân nhắc PIT + `search_after` khi cần snapshot ổn định.
8. **Nếu custom routing:** truyền đúng routing cho Get API theo ID.
9. **Kiểm thử:** xác minh GET, Search, update, delete và refresh bằng integration test.

## 20. Những điểm cần nhớ

- Get API theo ID là real-time theo mặc định và không cần refresh để thấy write mới.
- Search API là near-real-time; chỉ nhìn thấy thay đổi sau khi shard được refresh.
- Vì vậy, GET có thể thấy document mới trong khi Search chưa thấy, hoặc GET đã trả 404 sau delete trong khi Search còn thấy document cũ.
- `realtime=false` làm GET chỉ đọc trạng thái searchable đã refresh.
- Refresh làm thay đổi searchable; nó khác với flush và không phải transaction commit.
- `refresh=true` ép refresh ngay và có thể giảm throughput; `refresh=wait_for` chờ lần refresh tiếp theo; `false` không yêu cầu refresh.
- Spring Data `ElasticsearchOperations.get` đọc theo ID; `search` thực hiện Search API.
- `operations.indexOps(Entity.class).refresh()` có thể dùng để refresh index khi cần.
- Không dùng `Thread.sleep` để chờ search visibility; đồng bộ bằng refresh API hoặc `wait_for`.
- `preference=_primary` không thay thế refresh.
- Real-time GET không ngăn lost update; dùng `_seq_no` và `_primary_term` hoặc versioning.
- PIT giữ góc nhìn search ổn định qua nhiều request nhưng không bao gồm write phát sinh sau khi mở PIT.
- Nếu dùng custom routing, GET theo ID cần cùng routing đã dùng khi index.

GET và Search có hai mục tiêu khác nhau nên có semantics nhất quán khác nhau. Dùng GET khi đã biết ID và cần trạng thái mới nhất của một document; dùng Search cho truy vấn trên tập dữ liệu và chấp nhận near-real-time hoặc chủ động đồng bộ bằng refresh policy khi cần read-after-write. Khi hiểu rõ ranh giới này, ứng dụng Spring Data Elasticsearch có thể tránh các lỗi “ghi thành công nhưng tìm chưa thấy” và vẫn giữ được throughput phù hợp.

## Tài liệu tham khảo

- [Elasticsearch — Get API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-get.html)
- [Elasticsearch — Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html)
- [Elasticsearch — Refresh API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)
- [Elasticsearch — Index API refresh parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
