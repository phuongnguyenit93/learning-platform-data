# Refresh policy NONE, IMMEDIATE và WAIT_UNTIL

## 1. Refresh trong Elasticsearch là gì?

Elasticsearch là hệ thống tìm kiếm near real-time (NRT). Khi ứng dụng ghi hoặc cập nhật một document, thao tác ghi có thể đã được xác nhận thành công nhưng document chưa xuất hiện ngay trong kết quả của Search API.

Lý do là thao tác ghi và khả năng tìm kiếm có hai mốc thời gian khác nhau:

1. Elasticsearch nhận và xử lý thao tác ghi, cập nhật dữ liệu nội bộ và xác nhận request.
2. Một lần **refresh** làm cho những thay đổi mới có thể được tìm kiếm.

Ví dụ, ứng dụng vừa tạo sản phẩm:

~~~http
PUT /products/_doc/p-100
{
  "name": "Wireless Headphones",
  "category": "audio",
  "price": 1200000
}
~~~

Request có thể trả về thành công. Tuy nhiên, nếu ngay sau đó ứng dụng chạy:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

thì document mới chưa chắc đã xuất hiện trong kết quả. Nó sẽ có thể tìm kiếm được sau lần refresh tiếp theo.

**Refresh policy** quyết định thao tác ghi sẽ xử lý mốc hiển thị trong tìm kiếm như thế nào. Elasticsearch hỗ trợ ba lựa chọn:

- `NONE`: không yêu cầu refresh liên quan đến request.
- `IMMEDIATE`: refresh ngay sau khi thao tác ghi hoàn tất.
- `WAIT_UNTIL`: chờ đến khi một lần refresh làm cho thay đổi của request có thể tìm kiếm được.

Trong REST API, ba lựa chọn tương ứng với `refresh=false`, `refresh=true` và `refresh=wait_for`.

## 2. Phân biệt refresh, refresh interval và flush

Ba khái niệm này liên quan đến vòng đời dữ liệu trong Elasticsearch nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa |
|---|---|
| Refresh | Mở các thay đổi mới để Search API có thể tìm thấy |
| `index.refresh_interval` | Khoảng thời gian cấu hình giữa các lần refresh tự động |
| Flush | Tạo Lucene commit và xử lý translog để hỗ trợ phục hồi sau sự cố |

Refresh tập trung vào khả năng tìm kiếm. Nó không có nghĩa là ứng dụng đã yêu cầu một Lucene commit mới hoặc hoàn tất mọi công việc lưu trữ lâu dài.

Tương tự, `refresh_interval` không phải thời gian chờ cố định mà mọi request phải đợi. Đây là thiết lập điều khiển chu kỳ refresh tự động của shard. Request dùng `WAIT_UNTIL` sẽ chờ một refresh làm cho thay đổi của nó có thể tìm kiếm được.

Mặc định của Elastic Stack hiện hành là `1s`; Elastic Cloud Serverless có mặc định `5s`. Giá trị thực tế phụ thuộc môi trường và cấu hình index. Elasticsearch cũng có thể điều chỉnh hành vi refresh tự động theo hoạt động tìm kiếm của shard.

Một cách hình dung:

~~~text
Ghi document
     |
     v
Request được xác nhận
     |
     v
Document đã được ghi nhưng chưa chắc searchable
     |
     v
Refresh
     |
     v
Search API nhìn thấy document mới
~~~

Refresh không phải thao tác cần thực hiện sau mọi lần ghi. Elasticsearch có cơ chế refresh tự động để cân bằng khả năng tìm kiếm và hiệu năng ghi.

## 3. Ba giá trị của Refresh policy

Ba chính sách có thể so sánh như sau:

| Spring Data | Elasticsearch REST | Hành vi | Chi phí chính |
|---|---|---|---|
| `RefreshPolicy.NONE` | `refresh=false` | Không thực hiện hành động refresh cho request | Thấp nhất |
| `RefreshPolicy.IMMEDIATE` | `refresh=true` | Refresh các shard liên quan ngay sau thao tác | Tăng chi phí ghi, tìm kiếm và merge |
| `RefreshPolicy.WAIT_UNTIL` | `refresh=wait_for` | Chờ refresh tự động hoặc refresh khác làm thay đổi searchable | Tăng thời gian phản hồi, thường tránh refresh riêng cho request |

Lựa chọn phù hợp phụ thuộc vào yêu cầu của luồng nghiệp vụ:

- Nếu ứng dụng có thể chấp nhận độ trễ tìm kiếm ngắn, chọn `NONE`.
- Nếu người dùng cần thấy document ngay trong kết quả tìm kiếm tiếp theo, cân nhắc `WAIT_UNTIL`.
- Nếu thật sự cần refresh ngay sau thao tác và chấp nhận chi phí, chọn `IMMEDIATE`.

`NONE` thường là lựa chọn phù hợp cho luồng ghi thông thường. Chỉ bật chính sách chờ hoặc refresh ngay khi nghiệp vụ cần bảo đảm về khả năng tìm kiếm.

## 4. NONE: không yêu cầu refresh

`RefreshPolicy.NONE` tương ứng với `refresh=false` trong Elasticsearch.

Khi dùng chính sách này:

- Request ghi không yêu cầu Elasticsearch refresh shard.
- Request vẫn có thể trả về thành công sau khi thao tác ghi được xác nhận.
- Document sẽ trở nên searchable khi một lần refresh tự động hoặc một lần refresh khác diễn ra.
- Ứng dụng không được giả định rằng Search API sẽ thấy document ngay sau khi write response trả về.

Ví dụ REST:

~~~http
PUT /products/_doc/p-101?refresh=false
{
  "name": "Bluetooth Speaker",
  "category": "audio",
  "price": 850000
}
~~~

Hoặc bỏ hẳn tham số `refresh`:

~~~http
PUT /products/_doc/p-102
{
  "name": "USB Hub",
  "category": "accessories",
  "price": 350000
}
~~~

Khi không truyền tham số, Elasticsearch mặc định không thực hiện hành động refresh cho request ghi.

### Khi nào nên dùng NONE?

`NONE` phù hợp với:

- Import nhiều document.
- Ghi dữ liệu nền hoặc đồng bộ định kỳ.
- Luồng ghi có tần suất cao.
- Các thao tác mà người dùng không cần tìm kiếm document ngay lập tức.
- Hệ thống có thể chấp nhận dữ liệu xuất hiện trong kết quả sau lần refresh tự động tiếp theo.

Ví dụ, một job import 100.000 sản phẩm không cần làm từng sản phẩm searchable ngay sau mỗi lần ghi. Để Elasticsearch refresh theo lịch thường hiệu quả hơn việc refresh sau mỗi document.

### NONE không có nghĩa là dữ liệu bị mất

`NONE` chỉ nói rằng request không yêu cầu refresh. Nó không có nghĩa Elasticsearch bỏ qua thao tác ghi hoặc document không được lưu.

Cần phân biệt:

- Write response thành công: thao tác ghi được xử lý và xác nhận theo cơ chế của request.
- Search visibility: document đã có thể được truy vấn bằng Search API.
- Durability: khả năng dữ liệu được phục hồi sau sự cố, liên quan đến translog, commit và cấu hình lưu trữ.

Không dùng trạng thái hiển thị trong Search API làm bằng chứng duy nhất cho tính bền vững của dữ liệu.

## 5. IMMEDIATE: refresh ngay lập tức

`RefreshPolicy.IMMEDIATE` tương ứng với `refresh=true`.

Sau khi thao tác ghi hoàn tất, Elasticsearch refresh các primary và replica shard liên quan để thay đổi có thể tìm kiếm ngay.

Ví dụ:

~~~http
PUT /products/_doc/p-103?refresh=true
{
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 1500000
}
~~~

Sau khi request trả về thành công, ứng dụng có thể chạy Search API và tìm thấy document mới mà không cần chờ chu kỳ refresh tự động tiếp theo.

### IMMEDIATE tác động đến những shard nào?

Elasticsearch không refresh toàn bộ index trong mọi trường hợp. Request refresh sẽ tác động đến các shard liên quan đến thao tác ghi, bao gồm primary và các replica tương ứng.

Điều này vẫn có thể gây ra chi phí đáng kể, đặc biệt khi ứng dụng ghi thường xuyên hoặc có nhiều shard.

### Vì sao IMMEDIATE tốn tài nguyên?

Refresh tạo các segment nhỏ có thể tìm kiếm. Nếu ứng dụng liên tục ép refresh:

- Index có thể tạo nhiều segment nhỏ.
- Search phải xử lý nhiều segment hơn.
- Merge phải làm việc nhiều hơn để hợp nhất các segment.
- CPU, I/O và độ trễ có thể tăng.
- Throughput của quá trình index có thể giảm.

Chi phí của refresh ngay không chỉ xuất hiện ở thời điểm ghi. Nó còn có thể ảnh hưởng đến truy vấn và các lần merge tiếp theo.

### Khi nào nên dùng IMMEDIATE?

Chỉ dùng khi luồng nghiệp vụ thực sự cần kết quả tìm kiếm ngay sau khi request ghi hoàn tất và việc ép refresh là yêu cầu có chủ đích.

Ví dụ có thể là một thao tác quản trị rất ít xảy ra, cần cập nhật một cấu hình rồi ngay lập tức kiểm tra nó bằng Search API.

Không nên đặt `IMMEDIATE` cho mọi thao tác ghi chỉ để tránh độ trễ near real-time vốn là đặc tính bình thường của Elasticsearch.

## 6. WAIT_UNTIL: chờ đến lần refresh tiếp theo

`RefreshPolicy.WAIT_UNTIL` tương ứng với `refresh=wait_for`.

Khi dùng chính sách này, Elasticsearch không chủ động ép một lần refresh ngay lập tức. Request được giữ lại cho đến khi một lần refresh làm cho thay đổi của nó có thể tìm kiếm được.

Ví dụ:

~~~http
PUT /products/_doc/p-104?refresh=wait_for
{
  "name": "Office Chair",
  "category": "furniture",
  "price": 2400000
}
~~~

Khi request trả về, document đã searchable. Ứng dụng có thể thực hiện truy vấn tìm kiếm tiếp theo mà không cần tự chèn một khoảng sleep.

### WAIT_UNTIL hoạt động như thế nào?

Giả sử `index.refresh_interval` là `1s`:

~~~text
T0: Ứng dụng gửi write request với refresh=wait_for
 |
 v
T1: Elasticsearch ghi document và xác nhận phần xử lý ghi
 |
 v
   Request chờ refresh
 |
 v
T2: Refresh tự động xảy ra
 |
 v
T3: Document trở nên searchable
 |
 v
T4: Write request trả response cho ứng dụng
~~~

Thời gian chờ phụ thuộc thời điểm lần refresh kế tiếp xảy ra. Nếu request đến ngay trước lần refresh, thời gian chờ có thể rất ngắn. Nếu vừa lỡ một lần refresh, request có thể phải chờ gần hết chu kỳ tiếp theo.

Đây không phải một cam kết rằng request luôn hoàn tất trong đúng một giây. Độ trễ còn phụ thuộc tải cluster, lịch refresh, số shard và các request đang chờ.

### Khi nào nên dùng WAIT_UNTIL?

`WAIT_UNTIL` phù hợp với luồng:

1. Người dùng tạo hoặc cập nhật một document.
2. Backend cần đợi cho document có thể tìm kiếm.
3. Backend thực hiện truy vấn tiếp theo dựa trên dữ liệu vừa ghi.
4. Backend trả kết quả cho người dùng.

Ví dụ sau khi tạo một sản phẩm, màn hình cần chuyển sang trang tìm kiếm và hiển thị sản phẩm đó ngay trong danh sách. `WAIT_UNTIL` giúp bảo đảm mốc searchable trước khi write request hoàn tất.

So với `IMMEDIATE`, `WAIT_UNTIL` thường tận dụng lần refresh tự động sắp tới hoặc lần refresh khác đang diễn ra, do đó tránh ép một lần refresh riêng cho từng request.

## 7. WAIT_UNTIL và index.refresh_interval = -1

Có thể tắt refresh tự động bằng cấu hình:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Khi automatic refresh bị tắt:

- `NONE` tiếp tục không yêu cầu refresh.
- `IMMEDIATE` vẫn có thể chủ động refresh ngay.
- `WAIT_UNTIL` có thể chờ vô thời hạn nếu không có thao tác nào khác tạo refresh.

Một lần refresh thủ công hoặc request khác dùng `refresh=true` có thể làm các request đang chờ `WAIT_UNTIL` hoàn tất.

Đây là điểm cần chú ý trong các quy trình bulk indexing. Nếu job tắt refresh tự động để tăng tốc ingest nhưng lại gửi request `WAIT_UNTIL` và chờ response trước khi có bất kỳ lần refresh nào, job có thể bị treo ở bước đó.

Sau khi hoàn thành quá trình bulk indexing, ứng dụng có thể bật lại refresh interval và thực hiện một lần refresh có chủ đích nếu cần tìm kiếm ngay.

## 8. WAIT_UNTIL có thể buộc refresh trong trường hợp đặc biệt

Elasticsearch giới hạn số request đang chờ refresh trên mỗi shard bằng setting `index.max_refresh_listeners`. Giá trị mặc định là 1.000.

Nếu số request chờ trên shard đã đạt giới hạn này, một request mới dùng `refresh=wait_for` có thể hoạt động như `refresh=true` và buộc refresh để tránh giữ vô hạn các request đang chờ.

Trong trường hợp đó, response có thể có:

~~~json
{
  "forced_refresh": true
}
~~~

Điều này có nghĩa request đã buộc refresh thay vì chỉ chờ lần refresh kế tiếp.

Đối với Bulk API, một request bulk chỉ chiếm một refresh listener trên mỗi shard mà nó tác động, bất kể có bao nhiêu thao tác ghi vào shard đó. Vì vậy, gom nhiều thao tác vào một bulk request thường phù hợp hơn việc gửi hàng loạt request `WAIT_UNTIL` riêng lẻ.

## 9. Refresh policy trong Index, Update, Delete và Bulk API

Elasticsearch hỗ trợ tham số `refresh` cho các API ghi chính như Index, Update, Delete và Bulk.

### Index API

~~~http
PUT /products/_doc/p-105?refresh=wait_for
{
  "name": "Standing Desk",
  "category": "furniture",
  "price": 5200000
}
~~~

### Update API

~~~http
POST /products/_update/p-105?refresh=wait_for
{
  "doc": {
    "price": 5400000
  }
}
~~~

### Delete API

~~~http
DELETE /products/_doc/p-105?refresh=true
~~~

### Bulk API

~~~http
POST /products/_bulk?refresh=wait_for
{"index":{"_index":"products","_id":"p-106"}}
{"name":"Monitor Stand","category":"accessories","price":700000}
{"index":{"_index":"products","_id":"p-107"}}
{"name":"Desk Lamp","category":"furniture","price":450000}
~~~

Tham số `refresh` đặt ở cấp Bulk request và áp dụng cho các thao tác trong request đó.

Không cần gọi refresh riêng cho từng action trong bulk. Khi cần tất cả thay đổi của batch searchable trước khi xử lý tiếp, dùng một bulk request với `refresh=wait_for`.

## 10. Refresh policy không phải tham số của Search API

Refresh policy điều khiển hành vi sau thao tác ghi. Nó không phải tùy chọn để làm Search API refresh index.

Ví dụ, request sau không có ý nghĩa như một cơ chế chờ refresh:

~~~http
GET /products/_search?refresh=wait_for
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Để thay đổi thời điểm dữ liệu có thể tìm kiếm, hãy đặt policy trên write request. Search API chỉ đọc trạng thái đã searchable tại thời điểm nó thực thi.

Nếu ứng dụng cần tìm kiếm document vừa ghi:

1. Gửi write request với `WAIT_UNTIL`.
2. Chờ write response hoàn tất.
3. Gửi Search API bình thường.

Không cần truyền refresh policy vào request tìm kiếm sau đó.

## 11. Refresh thủ công bằng Refresh API

Elasticsearch cung cấp Refresh API:

~~~http
POST /products/_refresh
~~~

API này yêu cầu refresh các shard của index được chỉ định. Có thể dùng khi:

- Kiểm tra dữ liệu trong môi trường phát triển.
- Kết thúc một batch ingest và cần làm cho dữ liệu searchable.
- Thực hiện thao tác quản trị có chủ đích.

Không nên gọi Refresh API sau từng document hoặc sau mỗi request của người dùng. Điều đó có thể tạo cùng loại chi phí như sử dụng `IMMEDIATE` quá thường xuyên.

Trong kiểm thử, có thể dùng một lần refresh có chủ đích sau khi chuẩn bị dữ liệu. Tuy nhiên, nếu muốn kiểm tra semantics của refresh policy, nên kiểm tra cả ba chế độ thay vì luôn refresh thủ công để che đi độ trễ.

## 12. Cấu hình RefreshPolicy trong Spring Data Elasticsearch

Spring Data Elasticsearch định nghĩa enum:

`org.springframework.data.elasticsearch.core.RefreshPolicy`

Ba giá trị:

~~~java
public enum RefreshPolicy {
    NONE,
    IMMEDIATE,
    WAIT_UNTIL
}
~~~

Ánh xạ sang Elasticsearch:

| Spring Data | REST API |
|---|---|
| `RefreshPolicy.NONE` | `refresh=false` |
| `RefreshPolicy.IMMEDIATE` | `refresh=true` |
| `RefreshPolicy.WAIT_UNTIL` | `refresh=wait_for` |

Enum này được Spring Data Elasticsearch cung cấp từ phiên bản 4.2. Từ phiên bản 4.2, package sử dụng là `org.springframework.data.elasticsearch.core.RefreshPolicy` thay cho enum refresh policy thuộc Elasticsearch Java client cũ.

Khi dùng Spring Data Elasticsearch hiện hành, import:

~~~java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
~~~

Không nhầm với:

~~~java
import org.elasticsearch.action.support.WriteRequest.RefreshPolicy;
~~~

Import thứ hai thuộc API client cũ và không phải kiểu enum mà Spring Data hiện hành yêu cầu.

## 13. Đặt policy cho một thao tác bằng ElasticsearchOperations

`ElasticsearchOperations` cung cấp `withRefreshPolicy` để tạo một instance có cùng cấu hình nhưng dùng refresh policy khác.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Product saveAndWaitUntilSearchable(Product product) {

        return operations
            .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
            .save(product);
    }
}
~~~

Trong ví dụ:

- `withRefreshPolicy` trả về một bản sao của operations với policy mới.
- `save` thực hiện thao tác ghi bằng policy đó.
- Khi phương thức trả về thành công, thay đổi đã searchable theo semantics của WAIT_UNTIL.

Có thể dùng các policy khác:

~~~java
operations.withRefreshPolicy(RefreshPolicy.NONE).save(product);

operations.withRefreshPolicy(RefreshPolicy.IMMEDIATE).save(product);

operations.withRefreshPolicy(RefreshPolicy.WAIT_UNTIL).save(product);
~~~

`withRefreshPolicy` có từ Spring Data Elasticsearch 5.2. Đây là cách hữu ích khi chỉ một số thao tác cần chính sách riêng mà không muốn thay đổi cấu hình chung của toàn bộ template.

Cũng có thể áp dụng cho thao tác xóa hoặc ghi nhiều document thông qua các phương thức tương ứng của `ElasticsearchOperations`.

## 14. Đặt policy trực tiếp trên ElasticsearchRepository

`ElasticsearchRepository` có các overload nhận `RefreshPolicy` cho một số thao tác ghi.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Service:

~~~java
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product saveAndWait(Product product) {
        return repository.save(product, RefreshPolicy.WAIT_UNTIL);
    }

    public Iterable<Product> saveBatch(Iterable<Product> products) {
        return repository.saveAll(products, RefreshPolicy.NONE);
    }

    public void deleteAndRefresh(String id) {
        repository.deleteById(id, RefreshPolicy.IMMEDIATE);
    }
}
~~~

Các overload có thể dùng cho:

- `save(entity, refreshPolicy)`.
- `saveAll(entities, refreshPolicy)`.
- `delete(entity, refreshPolicy)`.
- `deleteById(id, refreshPolicy)`.
- `deleteAll(...)` với policy tương ứng.

Các overload nhận refresh policy được cung cấp từ Spring Data Elasticsearch 5.2.

Điểm thuận tiện là policy được chọn ngay tại nơi gọi repository. Điều này giúp thể hiện rõ yêu cầu của từng luồng nghiệp vụ: batch import dùng NONE, thao tác cần tìm kiếm ngay dùng WAIT_UNTIL.

## 15. Cấu hình policy mặc định và lưu ý về null

Spring Data có thể sử dụng refresh policy ở cấp template/operations. Tuy nhiên, cần phân biệt hai trạng thái:

- `null`: không đặt refresh policy tường minh, để hành vi mặc định của tầng tích hợp hoặc cluster quyết định.
- `RefreshPolicy.NONE`: chủ động yêu cầu không thực hiện hành động refresh cho write request.

Hai trạng thái này không nhất thiết tương đương trong mọi đường gọi của Spring Data.

Từ thay đổi trong Spring Data Elasticsearch 4.2:

- `ElasticsearchOperations` và `ReactiveElasticsearchOperations` dùng policy được cấu hình trên template nếu policy khác null. Nếu policy null, template không đặt hành động refresh tường minh và để cluster defaults áp dụng.
- Các implementation repository có sẵn của Spring Data thực hiện refresh tường minh khi policy null. Nếu truyền một policy cụ thể, repository sử dụng policy đó.

Vì vậy, không nên suy luận rằng `repository.save(entity)` và `operations.save(entity)` luôn có cùng hành vi refresh mặc định chỉ vì cả hai đều ghi một entity.

Nếu cần hành vi rõ ràng và nhất quán, hãy truyền policy tường minh hoặc dùng `withRefreshPolicy`.

Ví dụ đặt policy cho một thao tác:

~~~java
Product saved = repository.save(
    product,
    RefreshPolicy.NONE
);
~~~

Ví dụ đặt policy trên operations:

~~~java
ElasticsearchOperations noRefreshOperations =
    operations.withRefreshPolicy(RefreshPolicy.NONE);

Product saved = noRefreshOperations.save(product);
~~~

Khi đọc code cũ, hãy kiểm tra phiên bản Spring Data Elasticsearch và đường gọi đang dùng. Quy tắc mặc định đã thay đổi trong lịch sử framework, đặc biệt ở các phiên bản 4.2 trở lên.

## 16. Reactive Elasticsearch và refresh policy

Spring Data Elasticsearch cũng cung cấp API reactive với enum `RefreshPolicy` giống API đồng bộ.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import reactor.core.publisher.Mono;

public Mono<Product> saveAndWait(Product product) {
    return reactiveOperations
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .save(product);
}
~~~

Repository reactive cũng có overload nhận policy:

~~~java
Mono<Product> saved =
    reactiveProductRepository.save(
        product,
        RefreshPolicy.WAIT_UNTIL
    );
~~~

Trong reactive flow, request vẫn chờ cho đến khi Elasticsearch đáp ứng policy. Việc dùng `Mono` không làm cho refresh trở nên tức thời hoặc loại bỏ thời gian chờ. Nó chỉ biểu diễn thao tác bất đồng bộ theo mô hình reactive.

Nếu có nhiều thao tác ghi, hãy cân nhắc gom thành một batch và chọn policy ở cấp batch để giảm số request phải chờ.

## 17. WAIT_UNTIL trong kiểm thử tích hợp

Một tình huống phổ biến trong integration test:

1. Lưu document.
2. Tìm kiếm document vừa lưu.
3. Kiểm tra kết quả.

Nếu dùng NONE, bước tìm kiếm có thể chạy trước lần refresh tự động và không thấy document. Test sẽ phụ thuộc vào thời điểm thực thi, gây ra lỗi không ổn định.

Không nên giải quyết bằng cách thêm `Thread.sleep(...)`:

~~~java
repository.save(product);
Thread.sleep(1000);
List<Product> results = searchProducts();
~~~

Cách này có nhiều hạn chế:

- Không bảo đảm lần refresh đã xảy ra sau đúng một giây.
- Làm test chậm.
- Có thể vẫn thất bại khi môi trường tải cao.
- Không thể hiện rõ yêu cầu về khả năng tìm kiếm.

Có thể dùng WAIT_UNTIL:

~~~java
repository.save(product, RefreshPolicy.WAIT_UNTIL);

List<Product> results = searchProducts();

assertThat(results)
    .extracting(Product::getId)
    .contains(product.getId());
~~~

Khi write response trả về, document đã searchable. Test không cần đoán thời điểm refresh.

Nếu test chuẩn bị hàng trăm document, hãy dùng `saveAll` hoặc Bulk API với WAIT_UNTIL một lần thay vì gọi WAIT_UNTIL cho từng document riêng lẻ.

## 18. Batch indexing và lựa chọn policy

Giả sử một hệ thống nhập 50.000 sản phẩm.

Cách ghi từng document với IMMEDIATE:

~~~text
Index product 1  -> refresh
Index product 2  -> refresh
Index product 3  -> refresh
...
Index product 50,000 -> refresh
~~~

Cách này có thể tạo rất nhiều lần refresh, làm giảm throughput và tăng số segment nhỏ.

Một hướng phù hợp hơn:

~~~text
Batch 1: ghi 5,000 document
Batch 2: ghi 5,000 document
Batch 3: ghi 5,000 document
...
Batch 10: ghi 5,000 document
             |
             v
Bulk request với NONE
             |
             v
Để refresh tự động
             |
             v
Nếu cần searchable ngay:
Bulk request cuối với WAIT_UNTIL
~~~

Nếu ứng dụng cần kiểm soát hoàn toàn chu kỳ refresh trong lúc bulk import, có thể:

1. Tạm tắt refresh tự động bằng `index.refresh_interval = -1`.
2. Thực hiện bulk indexing với NONE.
3. Khôi phục refresh interval.
4. Gọi một lần refresh thủ công hoặc gửi thao tác cần chờ refresh.
5. Tiếp tục luồng tìm kiếm.

Đây là quy trình cần được kiểm soát cẩn thận vì việc tắt refresh ảnh hưởng mọi client đang tìm kiếm trên index đó. Không áp dụng trên index production đang phục vụ truy vấn trực tiếp nếu chưa đánh giá tác động.

## 19. Refresh policy không giải quyết concurrency hoặc optimistic locking

Refresh policy chỉ điều khiển khả năng tìm kiếm của thay đổi. Nó không giải quyết các vấn đề đồng thời khi nhiều client cập nhật cùng một document.

Ví dụ:

- Client A đọc document phiên bản cũ.
- Client B cập nhật document.
- Client A gửi update dựa trên dữ liệu cũ.

Dùng `WAIT_UNTIL` hoặc `IMMEDIATE` không ngăn Client A ghi đè thay đổi của Client B.

Để xử lý xung đột ghi, hãy xem xét optimistic concurrency control với `if_seq_no` và `if_primary_term` hoặc cơ chế versioning phù hợp.

Tương tự, refresh không thay thế cơ chế replication, acknowledgement hoặc durability. Nó chỉ xác định khi nào dữ liệu có thể được tìm kiếm.

## 20. Quan hệ giữa realtime GET và near real-time Search

Một điểm dễ gây nhầm là sau khi write thành công, thao tác GET theo ID có thể nhìn thấy document trước khi Search API nhìn thấy.

Ví dụ:

~~~http
PUT /products/_doc/p-108
{
  "name": "Desk Lamp",
  "category": "furniture"
}
~~~

Ngay sau đó, GET theo ID:

~~~http
GET /products/_doc/p-108
~~~

Get API mặc định hoạt động theo cơ chế real-time và có thể trả document vừa ghi mà không cần chờ refresh.

Trong khi đó, Search API:

~~~http
GET /products/_search
{
  "query": {
    "ids": {
      "values": ["p-108"]
    }
  }
}
~~~

vẫn có thể chưa tìm thấy document cho đến lần refresh tiếp theo.

Đây không phải mâu thuẫn. GET theo ID và Search API sử dụng các đường đọc khác nhau.

Nếu nghiệp vụ chỉ cần xác nhận document đã được lưu và đọc lại theo ID, không nhất thiết phải ép refresh. Nếu nghiệp vụ cần tìm kiếm theo field, filter hoặc full-text ngay sau khi ghi, hãy cân nhắc WAIT_UNTIL.

## 21. Điều chỉnh refresh_interval của index

`index.refresh_interval` là index setting điều khiển chu kỳ refresh tự động.

Có thể kiểm tra:

~~~http
GET /products/_settings?include_defaults=true
~~~

Thay đổi refresh interval:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "5s"
  }
}
~~~

Có thể tắt refresh tự động:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Bật lại:

~~~http
PUT /products/_settings
{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

Setting này có thể thay đổi động trên index. Tuy nhiên, không nên giảm interval quá thấp chỉ để mọi request WAIT_UNTIL phản hồi nhanh hơn. Refresh quá thường xuyên làm tăng chi phí tạo segment và merge.

Thời gian refresh interval nên được lựa chọn dựa trên:

- Tần suất ghi.
- Tần suất tìm kiếm.
- Yêu cầu độ trễ hiển thị dữ liệu mới.
- Số shard và kích thước segment.
- CPU, I/O và tải của cluster.

Refresh interval và refresh policy là hai tầng cấu hình khác nhau: một bên điều khiển lịch refresh tự động, bên kia điều khiển cách từng write request tương tác với refresh.

## 22. Những lỗi thường gặp

**Cho rằng write thành công đồng nghĩa Search API nhìn thấy ngay.** Write acknowledgement và search visibility là hai mốc khác nhau. Dùng WAIT_UNTIL nếu cần bảo đảm searchable trước khi response trả về.

**Dùng IMMEDIATE cho mọi thao tác ghi.** Refresh thường xuyên tạo nhiều segment nhỏ và làm tăng chi phí indexing, search và merge. Chỉ dùng khi thật sự cần.

**Dùng WAIT_UNTIL nhưng đã tắt refresh tự động.** Khi `refresh_interval` là `-1`, request có thể chờ vô thời hạn nếu không có thao tác khác tạo refresh.

**Gửi nhiều WAIT_UNTIL request tuần tự.** Mỗi request phải chờ refresh. Gom các thao tác vào một bulk request với WAIT_UNTIL sẽ hiệu quả hơn.

**Dùng Thread.sleep để chờ refresh.** Sleep không bảo đảm refresh đã hoàn tất. Dùng policy WAIT_UNTIL để đồng bộ theo sự kiện refresh thực tế.

**Nhầm null với RefreshPolicy.NONE trong Spring Data.** Null có thể kích hoạt hành vi mặc định khác nhau giữa operations và repository. Truyền policy tường minh khi cần kiểm soát.

**Cho rằng Refresh API là một thao tác ghi document.** Refresh API chỉ làm cho các thay đổi đã được ghi trở nên searchable; nó không thay thế Index, Update hoặc Delete API.

**Nhầm refresh với flush.** Refresh làm thay đổi searchable; flush tạo Lucene commit và xử lý translog. Hai thao tác phục vụ mục đích khác nhau.

**Đặt refresh policy trên Search API.** Refresh policy thuộc write request. Search API đọc dữ liệu đã searchable và không dùng `refresh=wait_for` để chờ write khác.

**Cho rằng WAIT_UNTIL luôn không ép refresh.** Nếu refresh listener của shard đã đầy, Elasticsearch có thể buộc refresh và trả `forced_refresh: true`.

**Nhầm realtime GET với Search API.** GET theo ID có thể nhìn thấy thay đổi trước khi Search API thấy nó. Điều này là hành vi bình thường của near real-time search.

**Nghĩ rằng refresh giải quyết xung đột ghi.** Refresh không thay thế optimistic concurrency control hoặc versioning.

## 23. Quy trình chọn refresh policy trong ứng dụng

Có thể chọn policy theo quy trình:

1. Xác định thao tác tiếp theo có cần tìm kiếm document vừa ghi hay không.
2. Nếu không cần searchable ngay, dùng `NONE`.
3. Nếu cần searchable trước khi write request trả về, ưu tiên xem xét `WAIT_UNTIL`.
4. Chỉ dùng `IMMEDIATE` khi có lý do cụ thể cần refresh ngay.
5. Với nhiều thao tác ghi, gom thành Bulk API hoặc `saveAll`.
6. Nếu dùng Spring Data, chọn policy tường minh qua repository overload hoặc `ElasticsearchOperations.withRefreshPolicy`.
7. Kiểm tra `index.refresh_interval`, đặc biệt nếu nó đang là `-1`.
8. Không dùng sleep hoặc refresh thủ công sau từng document.
9. Theo dõi độ trễ ghi, độ trễ search visibility và số segment.
10. Kiểm tra hành vi mặc định của phiên bản Spring Data Elasticsearch đang dùng nếu policy là null.

## Kết luận

Refresh policy điều khiển thời điểm thay đổi được ghi trở nên có thể tìm kiếm qua Search API. `NONE` không yêu cầu refresh và thường phù hợp cho luồng ghi thông thường. `IMMEDIATE` refresh các shard liên quan ngay sau thao tác nhưng có thể làm tăng chi phí indexing, search và merge. `WAIT_UNTIL` chờ một lần refresh làm cho thay đổi searchable trước khi write request trả về, thường là lựa chọn phù hợp khi cần đọc ngay sau ghi.

Trong Spring Data Elasticsearch, enum `RefreshPolicy` nằm trong package `org.springframework.data.elasticsearch.core` và có ba giá trị tương ứng với Elasticsearch REST API. Có thể đặt policy cho một thao tác bằng `ElasticsearchOperations.withRefreshPolicy` hoặc truyền trực tiếp vào các overload của `ElasticsearchRepository`. Cần phân biệt policy `null` với `NONE` vì hành vi mặc định của operations và repository có thể khác nhau.

Khi thiết kế luồng ghi, hãy ưu tiên NONE nếu không cần tìm kiếm ngay, dùng WAIT_UNTIL khi cần đồng bộ search visibility và chỉ dùng IMMEDIATE khi thật sự cần ép refresh. Kết hợp bulk write, refresh interval hợp lý và kiểm thử theo mốc searchable sẽ giúp ứng dụng cân bằng độ trễ với throughput.

## Tài liệu tham khảo

- [Elasticsearch — The refresh parameter](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/refresh-parameter)
- [Elasticsearch — Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
- [Elasticsearch — Index settings: refresh interval](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index)
- [Spring Data Elasticsearch — RefreshPolicy API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/RefreshPolicy.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch — ElasticsearchRepository API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/repository/ElasticsearchRepository.html)
- [Spring Data Elasticsearch — RefreshPolicy migration notes](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-4.1-4.2.html)
