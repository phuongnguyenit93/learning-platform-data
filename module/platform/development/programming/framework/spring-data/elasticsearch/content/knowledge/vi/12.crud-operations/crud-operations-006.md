# existsById, count và chi phí thao tác

Spring Data Elasticsearch cung cấp các thao tác kiểm tra document có tồn tại hay không và đếm số document. Hai nhu cầu này nghe có vẻ gần nhau, nhưng có chi phí và mục đích khác nhau:

- existsById(id) trả lời một câu hỏi boolean: document có ID đó có tồn tại trong index hay không.
- count() trả về số document trong phạm vi repository.
- Các method như existsBySku(...) hoặc countByActiveTrue() kiểm tra/đếm theo điều kiện, thường cần thực hiện truy vấn trên field thay vì tra cứu trực tiếp theo document ID.

Chọn đúng thao tác giúp giảm request không cần thiết, tránh quét dữ liệu lớn và hạn chế tải lên Elasticsearch. Bài này giải thích semantics của từng method, cách chúng liên hệ với REST API, các yếu tố quyết định chi phí và cách dùng an toàn trong luồng CRUD.

## 1. existsById dùng để làm gì?

Repository kế thừa ElasticsearchRepository có sẵn method existsById:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Sử dụng:

~~~java
boolean exists = productRepository.existsById("P-1001");

if (exists) {
    // Document có ID P-1001 đang tồn tại.
}
~~~

Kết quả là boolean:

- true: document được tìm thấy trong index tương ứng.
- false: document không tồn tại trong phạm vi index/alias mà repository sử dụng.

Method này phù hợp khi ứng dụng chỉ cần xác nhận một document theo ID, chẳng hạn kiểm tra tài nguyên trước khi hiển thị, kiểm tra trạng thái một thao tác hoặc xác nhận một ID đã được tạo.

Về mặt Elasticsearch, kiểm tra sự tồn tại theo ID thường được thực hiện bằng Exists API, tương ứng với một HTTP HEAD request:

~~~http
HEAD /products/_doc/P-1001
~~~

Nếu document tồn tại, Elasticsearch trả HTTP 200. Nếu không tồn tại, response thường là HTTP 404. HEAD response không tải toàn bộ nội dung _source về ứng dụng.

Spring Data có thể thay đổi chi tiết triển khai giữa các phiên bản. Khi cần biết chính xác request được phát ra trong một project, hãy xem API/implementation của phiên bản đang dùng hoặc bật log HTTP client ở môi trường test. Ý nghĩa của repository method vẫn là kiểm tra tồn tại theo ID.

### 1.1. existsById không phải count

Không cần gọi count() để trả lời một câu hỏi tồn tại theo ID:

~~~java
// Chỉ cần biết document có tồn tại hay không:
boolean exists = productRepository.existsById(id);

// Không cần đếm toàn bộ document để suy ra điều đó:
boolean existsByCounting = productRepository.count() > 0;
~~~

Hai biểu thức cuối có ý nghĩa khác nhau. count() > 0 chỉ cho biết index có ít nhất một document, không cho biết document có ID cụ thể có tồn tại hay không. Ngoài ra, count() có thể phải xử lý tất cả document trong phạm vi truy vấn.

## 2. count dùng để làm gì?

Repository kế thừa CrudRepository cung cấp method count() trả về kiểu long:

~~~java
long total = productRepository.count();
~~~

Method này đếm số document trong phạm vi repository. Nếu repository được ánh xạ tới index products, kết quả là số document được đếm trong index đó. Nếu cấu hình dùng alias hoặc phạm vi index khác, kết quả phụ thuộc index/alias thực tế mà repository truy cập.

Ở tầng Elasticsearch, Count API có thể được gọi trực tiếp:

~~~http
GET /products/_count
~~~

Response minh họa:

~~~json
{
  "count": 1250,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
~~~

Trường count là số document khớp điều kiện. _shards mô tả kết quả thực thi trên các shard được chọn.

Count API không trả về toàn bộ document. Nó trả về con số và metadata thực thi, nên phù hợp hơn Search API khi mục tiêu chỉ là lấy số lượng chính xác.

### 2.1. Đếm theo điều kiện

Có thể gửi query vào Count API:

~~~http
POST /products/_count
{
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

Request trên đếm số sản phẩm có active = true.

Trong repository, có thể khai báo derived query nếu phiên bản Spring Data Elasticsearch của dự án hỗ trợ keyword tương ứng:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    long countByActiveTrue();

    long countBySku(String sku);
}
~~~

Sử dụng:

~~~java
long activeProducts = productRepository.countByActiveTrue();
long productsWithSku = productRepository.countBySku("SKU-1001");
~~~

Các method derived query được Spring Data phân tích từ tên method. Hãy kiểm tra cú pháp và khả năng hỗ trợ của phiên bản Spring Data Elasticsearch trong dự án, nhất là khi method có nhiều điều kiện hoặc kiểu field đặc biệt.

Nếu cần query phức tạp, có thể dùng ElasticsearchOperations với Query và Count API thay vì ép mọi điều kiện vào tên method.

## 3. existsById và existsBy<Property> là hai trường hợp khác nhau

Spring Data repository có thể cung cấp cả method tồn tại theo ID và method tồn tại theo một thuộc tính domain.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    boolean existsById(String id);

    boolean existsBySku(String sku);

    boolean existsByActiveTrue();
}
~~~

Phân biệt:

| Method | Ý nghĩa |
|---|---|
| existsById(id) | Kiểm tra document theo ID Elasticsearch. |
| existsBySku(sku) | Kiểm tra có document nào thỏa điều kiện SKU hay không. |
| existsByActiveTrue() | Kiểm tra có document nào có active = true hay không. |
| count() | Đếm toàn bộ document trong phạm vi repository. |
| countBySku(sku) | Đếm số document thỏa điều kiện SKU. |

existsById có thể tận dụng tra cứu trực tiếp theo document ID. existsBySku và các method tương tự cần xử lý điều kiện trên field. Cơ chế query cụ thể phụ thuộc cách Spring Data tạo query và phiên bản đang sử dụng.

Không nên mặc định mọi method bắt đầu bằng exists đều có cùng chi phí. Kiểm tra theo ID thường có đường đi đơn giản hơn kiểm tra một thuộc tính không phải ID.

## 4. Dùng ElasticsearchOperations khi cần chỉ định index hoặc query

Ngoài repository, Spring Data Elasticsearch cung cấp ElasticsearchOperations để thực hiện thao tác trực tiếp.

Ví dụ kiểm tra theo ID và đếm document:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean exists(String id) {
        return operations.exists(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );
    }

    public long countAll() {
        return operations.count(
            Query.findAll(),
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

Ví dụ trên chỉ định index bằng IndexCoordinates. Cách này hữu ích khi service cần chọn index hoặc alias ở runtime, trong khi repository thông thường sử dụng index được xác định từ metadata entity.

Tên method và overload có thể khác giữa các phiên bản Spring Data Elasticsearch. Hãy đối chiếu API của dependency trong dự án. Nếu dùng repository với index cố định, các method existsById() và count() thường đơn giản hơn.

## 5. Chi phí của existsById

Kiểm tra tồn tại theo ID thường có chi phí thấp hơn việc đếm một tập document lớn vì Elasticsearch có thể định tuyến thao tác theo ID tới shard chứa document.

Một số yếu tố ảnh hưởng:

- **Số request mạng:** mỗi lần gọi repository thường tạo một request tới Elasticsearch.
- **Định tuyến shard:** Elasticsearch phải xác định shard phù hợp với document ID và routing key nếu được sử dụng.
- **Độ trễ mạng:** ứng dụng và cluster ở xa nhau có thể làm request đơn giản vẫn mất thời gian đáng kể.
- **Tải cluster:** node đang chịu nhiều request hoặc I/O có thể phản hồi chậm.
- **Routing tùy chỉnh:** nếu document được ghi với routing riêng, thao tác kiểm tra phải sử dụng cùng routing để tìm đúng shard.

Tra cứu theo ID không đồng nghĩa chi phí bằng 0. Một request đơn giản vẫn cần network round trip, xác thực, xử lý ở node và response. Nếu gọi hàng nghìn lần tuần tự, tổng độ trễ có thể lớn dù mỗi request riêng lẻ khá nhanh.

### 5.1. Routing ảnh hưởng tới existsById

Nếu ứng dụng dùng custom routing khi index document, Elasticsearch dùng routing value để xác định shard. Khi đọc hoặc kiểm tra tồn tại, cần cung cấp routing tương ứng.

Ví dụ REST API:

~~~http
HEAD /products/_doc/P-1001?routing=tenant-a
~~~

Nếu bỏ routing trong khi document được lưu với routing tùy chỉnh, thao tác có thể tìm ở shard khác và trả về không tồn tại.

Với repository method existsById(id) tiêu chuẩn, không phải lúc nào cũng có tham số routing cho từng lời gọi. Nếu ứng dụng phụ thuộc routing động theo tenant, cần thiết kế service/API sử dụng thao tác có hỗ trợ routing tương ứng với phiên bản Spring Data/Elasticsearch client đang dùng.

Không nên dùng existsById như một phép kiểm tra độc lập với routing trong hệ thống multi-tenant nếu cùng ID có thể nằm ở shard khác nhau theo tenant.

## 6. Chi phí của count

Count thường tốn công hơn kiểm tra một ID vì Elasticsearch phải thực thi query trên các shard thuộc index hoặc alias được chọn, rồi tổng hợp số đếm.

Chi phí phụ thuộc vào:

1. **Số shard cần truy vấn:** alias hoặc wildcard trỏ tới nhiều index có thể làm request fan out tới nhiều shard.
2. **Loại query:** match_all đơn giản thường nhẹ hơn query có nhiều điều kiện, nested query hoặc điều kiện phân tích phức tạp.
3. **Số document và cấu trúc dữ liệu:** index lớn hoặc dữ liệu phân bố phức tạp có thể làm thao tác tốn tài nguyên hơn.
4. **Tình trạng cluster:** CPU, I/O, heap, concurrency và các tác vụ khác ảnh hưởng latency.
5. **Tần suất gọi:** một count có thể chấp nhận được, nhưng count lặp lại trên mỗi request hoặc trong vòng lặp có thể tạo tải đáng kể.
6. **Phạm vi index:** đếm trên một index khác với đếm trên alias bao phủ nhiều index.

Count API không tải toàn bộ _source về ứng dụng và không cần tính điểm liên quan như tìm kiếm toàn văn. Tuy nhiên, điều đó không có nghĩa count luôn miễn phí hoặc luôn tức thời. Elasticsearch vẫn phải thực thi điều kiện và tổng hợp kết quả trên các shard liên quan.

### 6.1. Đếm toàn bộ và đếm có điều kiện

Đếm toàn bộ:

~~~http
GET /products/_count
~~~

Đếm có điều kiện:

~~~http
POST /products/_count
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "priceInCents": {
              "gte": 100000
            }
          }
        }
      ]
    }
  }
}
~~~

Query có điều kiện phải được đánh giá trên các shard liên quan. Filter có thể tận dụng query cache trong một số trường hợp, nhưng khả năng cache phụ thuộc loại query, dữ liệu và trạng thái cluster. Không nên dựa vào cache để giả định mọi count đều có chi phí cố định.

### 6.2. Đếm trên nhiều index hoặc alias

Ví dụ:

~~~http
GET /orders-2026-*/_count
~~~

Request có thể bao phủ nhiều index theo pattern. Số shard cần truy vấn tăng theo phạm vi index được phân giải.

Nếu một alias trỏ tới nhiều index:

~~~http
GET /orders-read/_count
~~~

kết quả là số document trong phạm vi alias. Điều này hữu ích cho dữ liệu phân vùng theo thời gian, nhưng cần nhớ alias có thể thay đổi các index mà nó trỏ tới.

Nếu count được dùng trong nghiệp vụ quan trọng, hãy xác định rõ alias/index và kiểm tra cấu hình alias trong quá trình triển khai.

## 7. count() khác hits.total của Search API như thế nào?

Search API cũng có thể trả số lượng kết quả trong hits.total:

~~~http
GET /products/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

Response có thể chứa:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    },
    "hits": []
  }
}
~~~

Trường relation có hai giá trị thường gặp:

- eq: value là tổng số chính xác.
- gte: value là cận dưới, nghĩa là có ít nhất số document đó khớp.

Elasticsearch mặc định giới hạn việc theo dõi tổng số hit chính xác ở một ngưỡng nhất định (thông thường là 10.000). Với tập kết quả lớn, Search API có thể chỉ báo một cận dưới để giảm chi phí đếm.

Nếu cần tổng chính xác trong Search API, có thể bật:

~~~http
GET /products/_search
{
  "track_total_hits": true,
  "size": 0,
  "query": {
    "match_all": {}
  }
}
~~~

So sánh:

| Nhu cầu | API phù hợp |
|---|---|
| Chỉ cần số lượng chính xác | Count API hoặc repository count() |
| Cần document và tổng số hit | Search API |
| Chỉ cần một số document đầu tiên, không cần tổng chính xác | Search API với size giới hạn và không yêu cầu track_total_hits chính xác |
| Cần kiểm tra một ID có tồn tại | Exists API / existsById |
| Cần kiểm tra có document nào thỏa điều kiện | Search giới hạn một hit hoặc derived exists query phù hợp |

Nếu mục tiêu duy nhất là đếm, Count API thường thể hiện ý định rõ hơn. Nếu đã chạy Search API để lấy danh sách document, cân nhắc có thật sự cần tổng chính xác hay không trước khi bật track_total_hits.

## 8. Khi chỉ cần biết có kết quả theo điều kiện hay không

Giả sử cần biết có sản phẩm đang hoạt động hay không. Không nhất thiết phải đếm tất cả sản phẩm đang hoạt động:

~~~java
long activeCount = productRepository.countByActiveTrue();
boolean hasActive = activeCount > 0;
~~~

Nếu chỉ cần boolean, một query tìm kiếm giới hạn một kết quả có thể phù hợp hơn:

~~~http
POST /products/_search
{
  "size": 1,
  "track_total_hits": false,
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

Ứng dụng kiểm tra hits.hits có phần tử hay không. Search vẫn phải thực thi query trên các shard liên quan, nhưng không yêu cầu tính tổng chính xác của mọi hit và chỉ trả tối đa một document.

Nếu phiên bản Spring Data hỗ trợ derived existsByActiveTrue(), có thể dùng method đó để biểu đạt ý định. Hãy xem request thực tế hoặc tài liệu phiên bản khi tối ưu hiệu năng; đừng mặc định nó luôn tương đương chính xác với một request cụ thể.

## 9. Không dùng count() để kiểm tra index rỗng trong mọi tình huống

Một số code viết:

~~~java
if (productRepository.count() == 0) {
    // Initialize default products
}
~~~

Điều này có thể đúng về logic, nhưng cần xem xét chi phí và concurrency:

- count() có thể phải truy vấn nhiều shard.
- Hai instance ứng dụng có thể cùng nhận kết quả 0 và cùng khởi tạo dữ liệu.
- Dữ liệu mới ghi có thể chưa xuất hiện trong Count/Search API ngay lập tức do refresh.
- Việc khởi tạo dữ liệu có thể cần tính idempotent và cơ chế đồng bộ.

Nếu chỉ cần kiểm tra một document cụ thể, dùng existsById. Nếu cần khởi tạo một tập dữ liệu mặc định, nên thiết kế thao tác khởi tạo có ID xác định, có thể chạy lặp lại an toàn và có cơ chế tránh chạy đồng thời ngoài ý muốn.

Không nên dùng count() như một khóa đồng bộ hoặc cơ chế đảm bảo chỉ một instance thực hiện một tác vụ.

## 10. Tránh check-then-write race condition

Một mẫu code dễ gặp:

~~~java
if (!productRepository.existsById(product.getId())) {
    productRepository.save(product);
}
~~~

Đoạn code có hai request riêng:

1. Kiểm tra ID chưa tồn tại.
2. Ghi document.

Giữa hai bước, một request khác có thể ghi cùng ID. Vì vậy cả hai request đều có thể thấy false rồi cùng ghi. Đây là race condition.

Nếu save dùng semantics index/upsert theo ID, thao tác ghi sau có thể ghi đè document trước. Điều đó có thể chấp nhận hoặc không tùy nghiệp vụ.

Nếu yêu cầu là chỉ tạo mới khi chưa tồn tại, hãy dùng thao tác ghi có điều kiện tạo mới (create-only/op_type=create) hoặc cơ chế optimistic concurrency phù hợp, rồi xử lý conflict khi document đã tồn tại. Không dựa vào một lần existsById trước khi ghi để đảm bảo tính duy nhất.

Nếu ID được tạo xác định từ một khóa nghiệp vụ, có thể thiết kế ID đó sao cho cùng một thực thể luôn ánh xạ tới cùng document ID. Với khóa nghiệp vụ không phải ID, cần một chiến lược duy nhất và concurrency riêng.

## 11. Tối ưu khi gọi exists và count nhiều lần

### 11.1. Tránh gọi trong vòng lặp

Không nên kiểm tra từng ID bằng một request tuần tự nếu có thể xử lý theo batch:

~~~java
for (String id : ids) {
    if (productRepository.existsById(id)) {
        // ...
    }
}
~~~

Với danh sách hàng nghìn ID, cách này có thể tạo hàng nghìn round trip mạng. Cân nhắc Multi Get API hoặc một truy vấn terms phù hợp với yêu cầu, sau đó đối chiếu các ID đã trả về.

Ví dụ truy vấn nhiều ID:

~~~http
POST /products/_search
{
  "size": 1000,
  "query": {
    "ids": {
      "values": [
        "P-1001",
        "P-1002",
        "P-1003"
      ]
    }
  }
}
~~~

Nếu cần đọc document đầy đủ theo ID, Multi Get API có thể phù hợp hơn. Nếu chỉ cần xác định tập ID tồn tại, có thể dùng truy vấn IDs và so sánh tập kết quả. Hãy cân nhắc giới hạn batch size, response size và số shard.

### 11.2. Tránh count lặp lại cho mỗi request UI

Một trang danh sách có thể gọi:

- Search để lấy 20 sản phẩm.
- Count để lấy tổng số sản phẩm.
- Một số existsById cho từng item.

Nếu tổng số chính xác không thực sự cần, hãy tránh request count riêng. Nếu Search API đã trả hits.total với độ chính xác cần thiết, có thể dùng kết quả đó. Nếu chỉ cần hiển thị "còn kết quả khác", không cần đếm toàn bộ.

Nếu count thay đổi chậm và nghiệp vụ cho phép, có thể cache kết quả trong thời gian ngắn hoặc duy trì số liệu tổng hợp riêng. Cache cần có chiến lược invalidation khi document được tạo, cập nhật hoặc xóa; nếu không, con số có thể cũ.

### 11.3. Đặt giới hạn phạm vi query

Khi đếm theo điều kiện, hãy:

- Dùng đúng index hoặc alias.
- Chỉ truy vấn field cần thiết.
- Dùng keyword cho giá trị exact filter.
- Dùng range phù hợp với kiểu số/ngày.
- Tránh wildcard index quá rộng nếu không cần.
- Tránh query phức tạp khi một field lọc đơn giản là đủ.

Query có cấu trúc tốt giúp giảm công việc của Elasticsearch và dễ quan sát hơn khi debug.

## 12. Tác động của refresh và tính nhất quán

Elasticsearch có hành vi near-real-time cho Search và Count. Document vừa được index có thể chưa xuất hiện ngay trong kết quả truy vấn cho tới lần refresh tiếp theo.

Cần phân biệt:

| Thao tác | Hành vi quan sát dữ liệu mới |
|---|---|
| Get document theo ID | Realtime theo semantics của Get API |
| Exists theo ID | Theo đường tra cứu document ID; thông thường thấy document đã ghi thành công ngay |
| Search | Near-real-time, phụ thuộc refresh |
| Count API | Dựa trên cơ chế truy vấn/search và có thể chưa thấy document mới trước refresh |

Ví dụ, vừa ghi document rồi gọi count() hoặc countBy... ngay lập tức có thể chưa thấy document đó nếu refresh chưa diễn ra.

Trong test cần xác nhận kết quả Search/Count ngay sau khi ghi, có thể refresh index tường minh. Trong production, không nên refresh sau mọi lần ghi vì refresh thường xuyên làm giảm hiệu năng indexing.

Nếu ứng dụng cần read-after-write qua search, hãy chọn refresh policy phù hợp với yêu cầu nghiệp vụ và tải. Không nhầm sự khác biệt refresh với lỗi ghi dữ liệu.

## 13. Đo chi phí thay vì phỏng đoán

Không có một con số cố định cho chi phí existsById hoặc count. Đo đạc trên môi trường gần với production sẽ đáng tin cậy hơn.

Các chỉ số hữu ích:

- Request rate của exists/count.
- Latency p50, p95 và p99.
- Tỷ lệ timeout và lỗi.
- Số shard được truy vấn.
- CPU, heap, I/O và tải search thread pool của Elasticsearch.
- Kích thước response và lượng dữ liệu truyền qua mạng.
- Số lần gọi lặp theo mỗi request nghiệp vụ.

Có thể bật log HTTP client ở môi trường test để xem Spring Data phát request nào. Không bật logging chứa dữ liệu nhạy cảm hoặc thông tin xác thực trong production.

Khi so sánh hai cách làm, dùng cùng một dataset, cùng index, cùng query và cùng mức concurrency. Đo nhiều lần để tránh kết luận từ một request đơn lẻ bị ảnh hưởng bởi cache hoặc tải tạm thời.

## 14. Ví dụ chọn API theo nghiệp vụ

| Yêu cầu | Cách nên dùng | Lý do |
|---|---|---|
| Kiểm tra sản phẩm ID P-1001 có tồn tại | existsById("P-1001") | Tra cứu trực tiếp theo ID |
| Đếm toàn bộ sản phẩm | count() | Trả về số lượng chính xác trong phạm vi repository |
| Đếm sản phẩm đang hoạt động | countByActiveTrue() hoặc Count API có filter | Đếm theo điều kiện |
| Kiểm tra có SKU cụ thể | existsBySku(sku), nếu được hỗ trợ | Boolean theo thuộc tính |
| Chỉ cần biết có ít nhất một sản phẩm active | exists query hoặc Search size 1 | Không cần tổng chính xác |
| Lấy danh sách và tổng số | Search API; dùng hits.total khi đủ chính xác | Một request có thể trả cả hits và total |
| Kiểm tra hàng loạt ID | Multi Get hoặc IDs query | Giảm số round trip |
| Tạo document chỉ khi chưa tồn tại | Create-only write / concurrency control | Tránh race condition check-then-write |

## 15. Checklist khi sử dụng existsById và count

Trước khi thêm một thao tác kiểm tra hoặc đếm vào service, hãy xác định:

- Chỉ cần boolean hay cần số lượng chính xác?
- Kiểm tra theo document ID hay theo một thuộc tính?
- Repository đang trỏ tới index, alias hay nhiều index?
- Document có dùng custom routing không?
- Có thể lấy thông tin từ kết quả Search hiện có không?
- Thao tác có bị gọi lặp trong vòng lặp hoặc trên từng request UI không?
- Count có cần chính xác tức thì sau khi ghi hay chấp nhận refresh delay?
- Có nguy cơ race condition giữa kiểm tra và ghi không?
- Có thể batch nhiều ID hoặc cache số liệu nếu nghiệp vụ cho phép không?
- Đã đo latency và tải cluster trong điều kiện thực tế chưa?

existsById và count là hai thao tác CRUD đơn giản nhưng phục vụ mục đích khác nhau. Dùng existsById khi cần xác nhận một document theo ID; dùng count khi thực sự cần số lượng; dùng exists query hoặc Search giới hạn một hit khi chỉ cần biết có document thỏa điều kiện. Hãy tính đến số request, shard fan-out, routing, refresh và concurrency để tránh các lần kiểm tra lặp lại làm tăng tải Elasticsearch.

