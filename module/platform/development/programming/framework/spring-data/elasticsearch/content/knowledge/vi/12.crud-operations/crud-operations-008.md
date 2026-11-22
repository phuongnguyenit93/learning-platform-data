# Xóa theo điều kiện và khác biệt với xóa từng id

Spring Data Elasticsearch hỗ trợ xóa tài liệu theo nhiều cách. Khi biết chính xác định danh của tài liệu, ứng dụng có thể gọi **deleteById(id)** hoặc **ElasticsearchOperations.delete(id, ...)**. Khi cần xóa mọi tài liệu thỏa một điều kiện nghiệp vụ, có thể dùng truy vấn xóa theo điều kiện thông qua **ElasticsearchOperations.delete(Query, ...)**.

Hai cách xóa này khác nhau về phạm vi, cách Elasticsearch tìm tài liệu và mức độ kiểm soát. Xóa theo ID nhắm đến một tài liệu cụ thể. Xóa theo điều kiện thực hiện một truy vấn trên index rồi xóa những tài liệu phù hợp. Nếu điều kiện quá rộng hoặc mapping không đúng, thao tác xóa theo query có thể ảnh hưởng đến rất nhiều tài liệu.

Bài này dùng ví dụ index **products**, trong đó mỗi tài liệu có ID, SKU, danh mục, trạng thái, giá và thời điểm tạo. Ta sẽ tìm hiểu xóa theo ID, xóa nhiều ID, xóa theo điều kiện bằng CriteriaQuery, kiểm tra phạm vi trước khi xóa và xử lý các tình huống có cập nhật đồng thời.

## 1. Hai cách xóa giải quyết hai nhu cầu khác nhau

Giả sử index **products** có các tài liệu:

~~~json
[
  {
    "id": "p-1001",
    "sku": "KB-1001",
    "category": "accessories",
    "status": "ACTIVE",
    "price": 89.5
  },
  {
    "id": "p-1002",
    "sku": "MS-1002",
    "category": "accessories",
    "status": "DISCONTINUED",
    "price": 29.0
  },
  {
    "id": "p-1003",
    "sku": "HD-1003",
    "category": "storage",
    "status": "DISCONTINUED",
    "price": 59.0
  }
]
~~~

Nếu cần xóa sản phẩm có ID **p-1002**, dùng xóa theo ID. Nếu cần xóa tất cả sản phẩm có trạng thái **DISCONTINUED**, dùng xóa theo điều kiện.

| Tiêu chí | Xóa theo ID | Xóa theo điều kiện |
|---|---|---|
| Đầu vào | Một ID hoặc tập ID | Một query mô tả điều kiện |
| Phạm vi | Tài liệu có ID được chỉ định | Tất cả tài liệu khớp query |
| Cách xác định tài liệu | Định danh trực tiếp | Elasticsearch thực hiện tìm kiếm theo điều kiện |
| Trường hợp phù hợp | Xóa một tài liệu đã xác định | Dọn dữ liệu theo trạng thái, thời gian, danh mục hoặc tiêu chí nghiệp vụ |
| Rủi ro thường gặp | Truyền nhầm ID | Điều kiện quá rộng hoặc query sai |
| API thường dùng | **deleteById**, **deleteAllById**, **delete(id, ...)** | **delete(Query, ...)** hoặc query method được phiên bản hỗ trợ |

Không nên dùng truy vấn xóa theo điều kiện chỉ để xóa một tài liệu đã biết ID. Ngược lại, không nên lấy toàn bộ tài liệu phù hợp về ứng dụng rồi lặp từng ID để xóa nếu Elasticsearch có thể thực hiện delete-by-query trực tiếp và nghiệp vụ cho phép.

## 2. Xóa một tài liệu theo ID bằng repository

Khi biết ID, cách đơn giản nhất là dùng **deleteById**:

~~~java
productRepository.deleteById("p-1002");
~~~

Phương thức này xóa tài liệu có ID tương ứng trong index mà repository quản lý. Nó không cần tạo query theo trường nghiệp vụ như category hay status.

Có thể kiểm tra sự tồn tại trước khi xóa:

~~~java
String productId = "p-1002";

if (productRepository.existsById(productId)) {
    productRepository.deleteById(productId);
}
~~~

Kiểm tra trước chỉ hữu ích khi nghiệp vụ cần phân biệt trường hợp tài liệu đã tồn tại. Nó tạo thêm một lần truy vấn và không bảo đảm tài liệu vẫn tồn tại tại thời điểm lệnh xóa được thực hiện. Một tiến trình khác có thể xóa tài liệu sau khi kiểm tra.

Nếu không cần thông báo riêng cho trường hợp không tồn tại, gọi trực tiếp **deleteById** thường gọn hơn.

### Xóa entity đã đọc

Có thể xóa một đối tượng đã lấy từ repository:

~~~java
Product product = productRepository.findById("p-1002")
        .orElseThrow(() -> new ProductNotFoundException("p-1002"));

productRepository.delete(product);
~~~

Repository dùng định danh của entity để xác định tài liệu cần xóa. Nếu chỉ có ID, không cần đọc toàn bộ entity trước khi xóa.

## 3. Xóa nhiều tài liệu theo danh sách ID

Nếu đã có danh sách ID cần xóa, dùng **deleteAllById**:

~~~java
List<String> ids = List.of("p-1002", "p-1003", "p-1010");

productRepository.deleteAllById(ids);
~~~

Đây là cách phù hợp khi danh sách ID đến từ một thao tác nghiệp vụ khác, ví dụ người quản trị chọn một số sản phẩm trong giao diện rồi yêu cầu xóa.

Có thể dùng **deleteAll(Iterable<T>)** nếu đã có các entity:

~~~java
List<Product> products = loadProductsSelectedForDeletion();

productRepository.deleteAll(products);
~~~

Không nên tải entity đầy đủ chỉ để xóa nếu ứng dụng đã có ID. Danh sách ID thường đủ để xác định tài liệu cần xóa.

Cũng cần phân biệt:

- **deleteAllById(ids)** xóa các tài liệu có ID nằm trong danh sách.
- **deleteAll(entities)** xóa các entity được truyền vào, dựa trên định danh.
- **deleteAll()** xóa toàn bộ tài liệu trong phạm vi repository.

**deleteAll()** không phải phương thức xóa theo điều kiện. Chỉ dùng khi nghiệp vụ thực sự yêu cầu làm rỗng index hoặc tập dữ liệu mà repository quản lý.

## 4. Xóa theo điều kiện bằng ElasticsearchOperations

Khi điều kiện xóa dựa trên giá trị trường, có thể tạo một Query rồi truyền cho **ElasticsearchOperations.delete(...)**.

Ví dụ cần xóa sản phẩm có trạng thái **DISCONTINUED**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCleanupService {

    private final ElasticsearchOperations operations;

    public ProductCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void deleteDiscontinuedProducts() {
        Criteria criteria = new Criteria("status").is("DISCONTINUED");
        Query query = new CriteriaQuery(criteria);

        IndexCoordinates index = IndexCoordinates.of("products");

        var response = operations.delete(query, Product.class, index);
    }
}
~~~

Trong ví dụ:

1. **Criteria** mô tả điều kiện trên trường **status**.
2. **CriteriaQuery** chuyển điều kiện thành một truy vấn mà Spring Data Elasticsearch có thể thực thi.
3. **IndexCoordinates.of("products")** xác định index đích.
4. **operations.delete(query, Product.class, index)** thực hiện xóa tài liệu khớp điều kiện.
5. Giá trị trả về là phản hồi của thao tác delete-by-query; cấu trúc chi tiết và accessor phụ thuộc phiên bản Spring Data Elasticsearch.

Đây là thao tác xóa theo query ở phía Elasticsearch. Ứng dụng không cần tải từng Product về rồi gọi **delete(product)** cho từng phần tử.

### Chọn đúng index đích

Nếu lớp tài liệu khai báo **@Document(indexName = "products")**, một số overload cho phép dùng metadata của entity để xác định index:

~~~java
var response = operations.delete(query, Product.class);
~~~

Khi ứng dụng dùng alias hoặc index theo phiên bản, truyền **IndexCoordinates** tường minh để kiểm soát phạm vi:

~~~java
IndexCoordinates index = IndexCoordinates.of("products-current");
var response = operations.delete(query, Product.class, index);
~~~

Trước khi dùng overload, kiểm tra chữ ký của **ElasticsearchOperations** trong phiên bản thư viện của dự án. Các API có thể khác nhau giữa các thế hệ Spring Data Elasticsearch.

## 5. Kết hợp nhiều điều kiện xóa

Điều kiện xóa có thể dựa trên một hoặc nhiều trường. Ví dụ chỉ xóa sản phẩm đã ngừng kinh doanh trong danh mục clearance.

~~~java
Criteria criteria = new Criteria("status").is("DISCONTINUED")
        .and("category").is("clearance");

Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Điều kiện kết hợp giúp giới hạn phạm vi xóa. Cần xác định rõ các điều kiện được kết hợp theo logic AND hay OR, vì thay đổi logic có thể làm tăng đáng kể số tài liệu khớp.

Ví dụ, với logic AND:

~~~text
status = DISCONTINUED
        AND
category = clearance
~~~

Chỉ tài liệu thỏa cả hai điều kiện mới được chọn.

Với logic OR:

~~~text
status = DISCONTINUED
        OR
category = clearance
~~~

Tài liệu thỏa một trong hai điều kiện đều có thể bị xóa. Khi dùng OR, phạm vi thường rộng hơn; hãy kiểm tra kỹ query được tạo ra.

Criteria API cung cấp các toán tử như **is**, **isNot**, **greaterThan**, **lessThan**, **between**, **in** và các cách kết hợp điều kiện. Tên và khả năng hỗ trợ cụ thể phụ thuộc phiên bản. Với truy vấn phức tạp, có thể dùng **NativeQuery** để biểu đạt trực tiếp Elasticsearch Query DSL.

## 6. Xóa theo khoảng thời gian

Một tình huống phổ biến là dọn tài liệu cũ hơn một mốc thời gian, ví dụ xóa các sản phẩm tạm thời đã hết hạn hoặc các tài liệu log quá thời hạn lưu giữ.

Giả sử lớp tài liệu có trường **expiresAt** kiểu date. Có thể xây dựng query:

~~~java
import java.time.Instant;

Instant cutoff = Instant.now();

Criteria criteria = new Criteria("expiresAt").lessThan(cutoff);
Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Query chọn các tài liệu có **expiresAt** nhỏ hơn thời điểm hiện tại.

Khi xóa theo thời gian, cần lưu ý:

- Trường phải được mapping thành **date**, không phải text tùy ý.
- Mốc thời gian cần dùng cùng quy ước timezone, thường là UTC.
- Cần xác định có xóa tài liệu đúng tại mốc cutoff hay chỉ xóa tài liệu nhỏ hơn mốc.
- Nếu dữ liệu có trường thời gian null hoặc thiếu, cần xác định rõ chúng có thuộc phạm vi dọn dẹp hay không.
- Không dùng thời gian của máy chạy ứng dụng nếu hệ thống cần một nguồn thời gian thống nhất và có kiểm soát.

## 7. Xóa theo khoảng giá hoặc giá trị số

Query cũng có thể dùng điều kiện số. Ví dụ xóa sản phẩm thử nghiệm có giá bằng 0:

~~~java
Criteria criteria = new Criteria("price").is(0.0);
Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Hoặc xóa các bản ghi có giá âm do dữ liệu lỗi:

~~~java
Criteria criteria = new Criteria("price").lessThan(0.0);
Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Điều kiện range chỉ hoạt động đúng khi trường được mapping thành kiểu số phù hợp. Nếu trường giá được lưu dưới dạng text, so sánh có thể không có ý nghĩa số học như mong đợi.

Trong môi trường thực tế, xóa dữ liệu lỗi thường nên đi kèm lưu vết hoặc xuất dữ liệu cần điều tra trước khi xóa. Đặc biệt với dữ liệu tài chính, kiểm toán hoặc dữ liệu nghiệp vụ quan trọng, chính sách lưu trữ có thể yêu cầu đánh dấu trạng thái thay vì xóa vật lý.

## 8. Xóa theo query và deleteById khác nhau ở tầng Elasticsearch

Khi gọi **deleteById**, Elasticsearch nhận yêu cầu xóa tài liệu theo định danh. Ứng dụng đã biết chính xác tài liệu đích.

Khi gọi delete-by-query, Elasticsearch thực hiện truy vấn trên index để tìm các tài liệu phù hợp, sau đó gửi các thao tác xóa cho tập kết quả. Cơ chế này phù hợp khi ứng dụng không có sẵn ID của từng tài liệu.

| Khía cạnh | Xóa theo ID | Delete-by-query |
|---|---|---|
| Cách tìm tài liệu | Theo **_id** | Thực thi query trên index |
| Số tài liệu | Thường một tài liệu mỗi ID; có thể gọi nhiều ID | Có thể xóa nhiều tài liệu khớp điều kiện |
| Công việc tìm kiếm | Không cần truy vấn theo trường nghiệp vụ | Cần tìm các tài liệu khớp query |
| Phạm vi ảnh hưởng | Được giới hạn bởi ID đầu vào | Phụ thuộc hoàn toàn vào điều kiện query |
| Dữ liệu đầu vào | ID | Criteria, Query DSL hoặc Query |
| Trường hợp điển hình | Người dùng xóa một sản phẩm cụ thể | Dọn sản phẩm theo trạng thái hoặc thời gian |
| Rủi ro chính | Nhầm ID hoặc xóa sai tài liệu cụ thể | Query thiếu điều kiện, sai mapping hoặc khớp quá nhiều tài liệu |

Delete-by-query không xóa index. Nó chỉ xóa các document khớp truy vấn trong index được chỉ định. Mapping, settings, alias và các document không khớp vẫn còn nguyên.

## 9. Kiểm tra số lượng trước khi xóa

Với thao tác xóa theo điều kiện, nên có bước xem trước phạm vi. Có thể dùng **ElasticsearchOperations.count(...)** với cùng query:

~~~java
Criteria criteria = new Criteria("status").is("DISCONTINUED");
Query query = new CriteriaQuery(criteria);
IndexCoordinates index = IndexCoordinates.of("products");

long matchedCount = operations.count(query, Product.class, index);

if (matchedCount > 0) {
    var response = operations.delete(query, Product.class, index);
}
~~~

Cách này giúp biết có bao nhiêu tài liệu đang khớp điều kiện trước khi xóa. Có thể đưa số lượng này vào log hoặc màn hình xác nhận của người quản trị.

Tuy nhiên, count và delete là hai thao tác riêng biệt. Dữ liệu có thể thay đổi giữa lúc đếm và lúc xóa. Vì vậy, số lượng xem trước không phải khóa giao dịch và không bảo đảm số tài liệu bị xóa sẽ bằng đúng số đã đếm.

Nếu nghiệp vụ yêu cầu xác nhận trước khi xóa, hãy hiển thị rõ:

- Index hoặc alias đích.
- Điều kiện query đầy đủ.
- Số lượng tài liệu dự kiến bị ảnh hưởng.
- Người thực hiện và thời điểm thao tác.
- Chính sách lưu trữ hoặc khả năng khôi phục.

Không nên thực hiện delete-by-query nếu điều kiện đầu vào rỗng hoặc không được xác thực. Một query không có điều kiện có thể tương đương xóa toàn bộ tài liệu trong phạm vi index.

## 10. Kiểm tra mapping trước khi tạo điều kiện

Query cần phù hợp với kiểu mapping của trường. Ví dụ:

~~~json
{
  "properties": {
    "status": {
      "type": "keyword"
    },
    "category": {
      "type": "keyword"
    },
    "name": {
      "type": "text"
    },
    "price": {
      "type": "double"
    },
    "expiresAt": {
      "type": "date"
    }
  }
}
~~~

Các lưu ý:

- **status** và **category** là keyword, phù hợp với điều kiện so khớp chính xác.
- **name** là text, phù hợp với truy vấn toàn văn. Khi xóa theo nội dung tên, hãy xác định có cần match query hay truy vấn chính xác trên multi-field keyword.
- **price** là double, phù hợp với điều kiện range số.
- **expiresAt** là date, phù hợp với điều kiện trước hoặc sau một mốc thời gian.

Nếu dùng **term** trên trường text, kết quả có thể không như mong đợi do nội dung đã được analyzer xử lý. Nếu cần so khớp nguyên vẹn, hãy dùng trường keyword hoặc multi-field keyword.

## 11. Delete-by-query xử lý cập nhật đồng thời như thế nào?

Elasticsearch delete-by-query thực hiện tìm kiếm trên một snapshot của index rồi xóa các tài liệu được tìm thấy. Trong lúc thao tác đang chạy, tài liệu có thể bị một tiến trình khác cập nhật hoặc xóa.

Do đó, kết quả có thể phát sinh version conflict. Ví dụ:

1. Delete-by-query tìm thấy một sản phẩm có trạng thái DISCONTINUED.
2. Một tiến trình khác cập nhật sản phẩm đó thành ACTIVE.
3. Delete-by-query cố xóa phiên bản tài liệu đã tìm thấy.
4. Elasticsearch phát hiện tài liệu đã thay đổi và có thể báo version conflict.

Delete-by-query không phải transaction bao trùm toàn bộ index. Không có cơ chế rollback tự động để khôi phục mọi tài liệu đã xóa nếu một phần thao tác gặp lỗi.

Với các thao tác quản trị lớn, cần xác định cách xử lý conflict:

- Dừng thao tác và điều tra nếu xung đột cho thấy dữ liệu thay đổi ngoài dự kiến.
- Cho phép tiếp tục qua conflict nếu nghiệp vụ chấp nhận bỏ qua các tài liệu đã thay đổi, đồng thời ghi nhận số conflict.
- Tạm dừng hoặc điều phối các luồng ghi liên quan trong thời gian dọn dữ liệu nếu cần tính nhất quán cao.

Elasticsearch Delete By Query API có các tùy chọn như **conflicts**, **requests_per_second**, **slices** và chạy bất đồng bộ bằng task tùy phiên bản. Spring Data Elasticsearch không nhất thiết phơi bày tất cả tùy chọn này qua cùng một overload. Nếu cần kiểm soát sâu, hãy dùng Elasticsearch Java API Client tương thích với phiên bản cluster.

## 12. Kết quả trả về và lỗi khi delete-by-query

Khác với **deleteById**, thao tác delete-by-query có thể trả về phản hồi chứa thông tin về số tài liệu đã xóa, số batch, version conflict và các lỗi phát sinh.

Ví dụ:

~~~java
var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Không nên giả định gọi phương thức không ném exception đồng nghĩa mọi tài liệu đều đã được xóa thành công. Hãy đọc cấu trúc phản hồi và log theo API của phiên bản đang dùng. Một số thao tác có thể hoàn tất một phần và vẫn trả về thông tin lỗi.

Khi xử lý phản hồi, cần quan tâm:

- Số tài liệu đã xóa.
- Số version conflict.
- Danh sách lỗi theo batch hoặc tài liệu.
- Trạng thái task nếu thao tác được chạy bất đồng bộ.
- Thời gian thực hiện và tốc độ xử lý.

Nếu client bị ngắt kết nối sau khi gửi request, không nên gửi lại ngay mà không kiểm tra trạng thái. Request đầu tiên có thể đã thực hiện một phần hoặc hoàn tất dù client không nhận được phản hồi. Hãy kiểm tra index, task hoặc log trước khi quyết định chạy lại.

## 13. Xóa theo điều kiện không làm dữ liệu biến mất khỏi tìm kiếm ngay lập tức

Elasticsearch là hệ thống near real-time. Sau khi xóa, thay đổi có thể chưa xuất hiện ngay trong kết quả tìm kiếm cho đến khi index được refresh.

Nếu luồng nghiệp vụ cần xác nhận kết quả tìm kiếm ngay sau thao tác xóa, có thể dùng cơ chế refresh phù hợp với API phiên bản đang chạy hoặc gọi refresh có chủ đích:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
~~~

Không nên refresh sau mọi thao tác xóa trong môi trường có tải cao. Refresh thường xuyên có thể làm giảm hiệu năng. Trong ứng dụng bình thường, nên dựa vào chu kỳ refresh mặc định và chỉ yêu cầu refresh khi có yêu cầu nghiệp vụ rõ ràng.

Cũng cần phân biệt thao tác xóa tài liệu với xóa index:

- **deleteById** xóa một tài liệu theo ID.
- **delete(Query, ...)** xóa các tài liệu khớp query.
- **IndexOperations.delete()** xóa toàn bộ index vật lý, bao gồm tài liệu, mapping và settings.

Ba thao tác có phạm vi ảnh hưởng rất khác nhau.

## 14. Đóng gói xóa theo điều kiện trong service

Nên đặt logic xóa theo điều kiện trong service để tập trung quy tắc nghiệp vụ, xác định index đích và kiểm tra điều kiện trước khi gọi Elasticsearch.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCleanupService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public long countDiscontinuedProducts() {
        Query query = discontinuedProductsQuery();
        return operations.count(query, Product.class, PRODUCTS);
    }

    public void deleteDiscontinuedProducts() {
        Query query = discontinuedProductsQuery();

        long count = operations.count(query, Product.class, PRODUCTS);
        if (count == 0) {
            return;
        }

        var response = operations.delete(query, Product.class, PRODUCTS);

        // Ghi log phản hồi theo API của phiên bản đang sử dụng.
    }

    private Query discontinuedProductsQuery() {
        Criteria criteria = new Criteria("status").is("DISCONTINUED");
        return new CriteriaQuery(criteria);
    }
}
~~~

Service dùng một phương thức để tạo query, giúp điều kiện xem trước và điều kiện xóa nhất quán về mặt mã nguồn. Tuy nhiên, count và delete vẫn là hai request riêng biệt nên dữ liệu có thể thay đổi giữa hai bước.

Trong hệ thống thực tế, có thể bổ sung tham số danh mục, mốc thời gian hoặc trạng thái, nhưng phải xác thực chúng trước khi tạo query. Không cho phép caller truyền một query rỗng hoặc điều kiện xóa toàn index nếu nghiệp vụ không cho phép.

## 15. Có nên dùng derived delete query trong repository?

Spring Data có cơ chế query derivation dựa trên tên phương thức. Một số phiên bản và loại repository hỗ trợ các phương thức xóa theo thuộc tính, ví dụ dạng **deleteByStatus(...)**. Tuy nhiên, khả năng hỗ trợ và kiểu trả về cụ thể cần được xác nhận theo phiên bản Spring Data Elasticsearch đang sử dụng.

Nếu dự án có dùng derived delete query:

~~~java
void deleteByStatus(String status);
~~~

Hãy kiểm tra tài liệu phiên bản và hành vi thực tế của query method, đặc biệt khi cần biết số tài liệu bị xóa hoặc cần xử lý lỗi từng phần.

Khi cần thể hiện rõ query, index đích, số lượng xem trước hoặc metadata phản hồi, dùng **ElasticsearchOperations.delete(Query, ...)** thường dễ kiểm soát hơn.

Không nên chọn derived delete method chỉ vì tên ngắn. Điều kiện xóa là thao tác có tác động dữ liệu lớn, vì vậy cần để người đọc mã hiểu được phạm vi tài liệu bị ảnh hưởng.

## 16. Xóa vật lý hay đánh dấu trạng thái?

Không phải lúc nào tài liệu cũng nên bị xóa vật lý. Với dữ liệu nghiệp vụ, có thể cần giữ lịch sử để kiểm toán, khôi phục hoặc báo cáo.

Một lựa chọn là cập nhật trạng thái thay vì xóa:

~~~java
Product product = productRepository.findById(productId)
        .orElseThrow(() -> new ProductNotFoundException(productId));

product.setStatus("ARCHIVED");
productRepository.save(product);
~~~

Sau đó, các truy vấn thông thường lọc bỏ trạng thái ARCHIVED. Dữ liệu vẫn tồn tại trong index và có thể được tìm kiếm bởi tác vụ quản trị.

Có thể chọn giữa xóa vật lý và đánh dấu trạng thái dựa trên:

- Chính sách lưu giữ dữ liệu.
- Yêu cầu kiểm toán.
- Khả năng khôi phục.
- Chi phí lưu trữ.
- Quyền riêng tư và yêu cầu xóa dữ liệu.
- Mức độ ảnh hưởng đến báo cáo và các hệ thống tích hợp.

Nếu nghiệp vụ bắt buộc xóa vật lý, hãy bảo đảm mọi bản sao hoặc luồng đồng bộ liên quan cũng được xử lý theo chính sách dữ liệu của hệ thống.

## 17. Lỗi thường gặp khi xóa theo điều kiện

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Xóa nhiều tài liệu hơn dự kiến | Query thiếu điều kiện hoặc dùng OR ngoài ý muốn | Kiểm tra query và đếm số tài liệu khớp trước khi xóa |
| Không xóa được tài liệu | Sai tên trường, kiểu mapping hoặc điều kiện | Đọc mapping và thử query bằng API search |
| Xóa theo ID không tìm thấy | ID sai hoặc tài liệu đã bị xóa | Kiểm tra ID và xác định hợp đồng khi không tồn tại |
| Delete-by-query báo version conflict | Tài liệu bị cập nhật trong lúc thao tác | Xác định chính sách conflict và đồng bộ luồng ghi |
| Một phần tài liệu chưa bị xóa | Batch có lỗi hoặc thao tác bị gián đoạn | Đọc phản hồi, failures và kiểm tra lại các tài liệu còn lại |
| Xóa thành công nhưng tìm kiếm vẫn thấy tài liệu | Index chưa refresh | Chờ refresh hoặc refresh có chủ đích khi cần |
| Client timeout | Tác vụ kéo dài hoặc phản hồi bị mất | Kiểm tra trạng thái thực tế trước khi gửi lại |
| Dữ liệu cần khôi phục đã bị xóa | Không có bản sao hoặc event log | Xác định chính sách backup, snapshot và lưu trữ trước thao tác |
| Xóa nhầm toàn bộ index | Dùng nhầm **deleteAll()** hoặc **IndexOperations.delete()** | Phân biệt rõ xóa document và xóa index; giới hạn quyền quản trị |

## 18. Nguyên tắc lựa chọn API xóa

Có thể dựa trên các nguyên tắc sau:

1. Dùng **deleteById(id)** khi biết chính xác một tài liệu cần xóa.
2. Dùng **deleteAllById(ids)** khi có danh sách ID cụ thể.
3. Dùng **delete(entity)** hoặc **deleteAll(entities)** khi đã có các entity cần xóa.
4. Dùng **ElasticsearchOperations.delete(Query, ...)** khi cần xóa mọi tài liệu thỏa điều kiện.
5. Dùng **count(query, ...)** để xem trước phạm vi khi thao tác có ảnh hưởng lớn, đồng thời hiểu rằng count không khóa dữ liệu.
6. Xác định đúng index hoặc alias đích trước khi thực hiện.
7. Kiểm tra kiểu mapping và loại query để điều kiện khớp đúng dữ liệu.
8. Đọc phản hồi delete-by-query, bao gồm deleted count, conflicts và failures theo API phiên bản.
9. Xác định cách xử lý cập nhật đồng thời và dữ liệu phát sinh trong lúc xóa.
10. Chỉ dùng **deleteAll()** hoặc xóa index khi nghiệp vụ thực sự yêu cầu phạm vi đó.

Xóa theo ID phù hợp khi định danh tài liệu đã biết và phạm vi xóa nhỏ, rõ ràng. Xóa theo điều kiện phù hợp với các tác vụ dọn dữ liệu theo trạng thái, danh mục, thời gian hoặc quy tắc nghiệp vụ. Trong Spring Data Elasticsearch, repository giúp thao tác theo ID đơn giản, còn **ElasticsearchOperations.delete(Query, ...)** cho phép gửi điều kiện đến Elasticsearch để xóa hàng loạt. Trước một thao tác xóa theo query, cần xác định index, kiểm tra mapping, xem trước phạm vi và có cách xử lý lỗi hoặc cập nhật đồng thời.
