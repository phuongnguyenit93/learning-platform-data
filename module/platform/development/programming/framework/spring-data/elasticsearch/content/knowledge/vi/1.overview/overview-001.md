# Spring Data Elasticsearch là gì và giải quyết nhu cầu tìm kiếm nào

## 1. Spring Data Elasticsearch là gì?

Spring Data Elasticsearch là một phần của hệ sinh thái Spring Data, cung cấp cách làm việc với Elasticsearch từ ứng dụng Java theo phong cách quen thuộc của Spring. Thư viện hỗ trợ ánh xạ đối tượng Java với tài liệu trong Elasticsearch, thao tác với index, lưu và đọc dữ liệu, xây dựng truy vấn tìm kiếm, phân trang và sắp xếp kết quả.

Elasticsearch là một công cụ tìm kiếm và phân tích dữ liệu phân tán, được xây dựng trên Apache Lucene. Nó tổ chức dữ liệu thành các index và tối ưu cho việc tìm kiếm trên nội dung lớn. Elasticsearch có thể tìm văn bản theo mức độ liên quan, lọc theo nhiều điều kiện, sắp xếp, thống kê và tổng hợp dữ liệu.

Spring Data Elasticsearch đóng vai trò kết nối giữa mô hình lập trình Spring và API của Elasticsearch. Thay vì tự viết nhiều đoạn mã kết nối, chuyển đổi dữ liệu và tạo truy vấn ở mọi nơi, ứng dụng có thể sử dụng các abstraction như:

- `ElasticsearchRepository`: giao diện repository để lưu, tìm và xóa tài liệu bằng các phương thức Java.
- `ElasticsearchOperations`: API cấp cao để thực hiện các thao tác với index, tài liệu và truy vấn tùy biến.
- `ElasticsearchTemplate`: một triển khai của `ElasticsearchOperations`, cung cấp các thao tác làm việc với Elasticsearch.
- Các annotation như `@Document`, `@Id` và `@Field`: mô tả cách một lớp Java được ánh xạ thành tài liệu và trường trong index.

Spring Data Elasticsearch không phải là một công cụ tìm kiếm độc lập. Khả năng phân tích văn bản, tính điểm liên quan, phân tán dữ liệu và tổng hợp kết quả đến từ Elasticsearch. Spring Data cung cấp cách sử dụng những khả năng đó thuận tiện hơn trong ứng dụng Spring.

## 2. Nhu cầu tìm kiếm mà cơ sở dữ liệu thông thường khó đáp ứng

Cơ sở dữ liệu quan hệ rất phù hợp để lưu dữ liệu nghiệp vụ có cấu trúc, duy trì ràng buộc và thực hiện giao dịch. Tuy nhiên, khi sản phẩm cần tìm kiếm trên nhiều trường văn bản hoặc cần xếp hạng kết quả theo mức độ phù hợp, các truy vấn lọc thông thường có thể không đủ tiện lợi hoặc hiệu quả.

Hãy hình dung một cửa hàng trực tuyến có hàng trăm nghìn sản phẩm. Người dùng nhập “tai nghe bluetooth chống ồn”, sau đó muốn lọc theo thương hiệu, khoảng giá, đánh giá và tình trạng còn hàng. Họ kỳ vọng sản phẩm phù hợp nhất xuất hiện trước, dù tên sản phẩm không chứa nguyên vẹn cả cụm từ đã nhập.

Một chức năng tìm kiếm như vậy thường cần kết hợp nhiều khả năng:

### Tìm kiếm toàn văn (full-text search)

Tìm kiếm toàn văn cho phép tìm theo nội dung ngôn ngữ tự nhiên. Elasticsearch phân tích văn bản thành các đơn vị có thể lập chỉ mục, thường là token. Khi truy vấn, hệ thống phân tích cụm từ tìm kiếm rồi tìm các tài liệu có nội dung phù hợp.

Ví dụ, với trường tên sản phẩm được cấu hình là `text`, truy vấn `match` cho cụm “tai nghe bluetooth” có thể tìm các tài liệu chứa những từ liên quan, thay vì yêu cầu trường phải bằng chính xác toàn bộ chuỗi đó.

### Xếp hạng theo mức độ liên quan

Không phải kết quả nào khớp với truy vấn cũng hữu ích như nhau. Elasticsearch tính điểm liên quan cho kết quả dựa trên truy vấn, nội dung tài liệu và cấu hình tìm kiếm. Ứng dụng có thể dùng điểm này để đưa kết quả phù hợp hơn lên đầu danh sách.

Ví dụ, khi tìm “máy ảnh du lịch”, sản phẩm có tên và mô tả đề cập trực tiếp đến máy ảnh du lịch thường nên được ưu tiên hơn sản phẩm chỉ nhắc đến cụm từ đó ở một phần ít quan trọng.

### Kết hợp tìm kiếm với bộ lọc có cấu trúc

Người dùng thường vừa nhập từ khóa, vừa giới hạn kết quả theo các thuộc tính như danh mục, thương hiệu, giá, ngày xuất bản hoặc trạng thái. Elasticsearch cho phép kết hợp truy vấn toàn văn với các điều kiện lọc chính xác.

Ví dụ: tìm sản phẩm khớp với “tai nghe bluetooth”, chỉ lấy danh mục `audio` và giá không vượt quá một mức nhất định. Phần tìm kiếm văn bản có thể ảnh hưởng đến điểm liên quan; các điều kiện lọc thường được dùng để loại bỏ tài liệu không đáp ứng tiêu chí.

### Phân trang, sắp xếp và thống kê

Một trang kết quả thường cần phân trang và sắp xếp theo điểm liên quan, giá hoặc thời gian. Các trang danh mục còn có thể hiển thị số lượng sản phẩm theo thương hiệu, mức giá hoặc loại sản phẩm. Những thống kê này thường được gọi là aggregation hoặc facet.

Elasticsearch hỗ trợ aggregation để tính toán các nhóm và số liệu trên tập kết quả. Ứng dụng có thể dùng chúng để xây dựng bộ lọc dạng “Thương hiệu A (120 sản phẩm)” hoặc biểu đồ phân bố giá.

### Các trải nghiệm tìm kiếm nâng cao

Tùy cách thiết kế index và truy vấn, Elasticsearch còn hỗ trợ các trường hợp như gợi ý khi nhập, tìm gần đúng, từ đồng nghĩa, tìm theo vị trí địa lý và tìm kiếm đa ngôn ngữ. Những khả năng này cần cấu hình analyzer, mapping và query phù hợp; chỉ thêm Spring Data Elasticsearch vào dự án không tự động tạo ra chúng.

## 3. Spring Data Elasticsearch giúp ứng dụng làm việc như thế nào?

Luồng cơ bản có thể hình dung như sau:

```text
Ứng dụng Spring
      |
      v
Repository hoặc ElasticsearchOperations
      |
      v
Spring Data Elasticsearch
      |
      v
Elasticsearch Java Client
      |
      v
Elasticsearch cluster -> index -> documents
```

Ứng dụng gọi repository hoặc operations. Spring Data chuyển đổi đối tượng Java và mô tả truy vấn sang yêu cầu mà Elasticsearch hiểu, sau đó chuyển kết quả trả về thành đối tượng hoặc cấu trúc kết quả Java.

Trong Elasticsearch, dữ liệu thường được tổ chức theo các khái niệm sau:

- **Cluster** là một hệ thống Elasticsearch gồm một hoặc nhiều node.
- **Node** là một tiến trình Elasticsearch tham gia lưu trữ và xử lý dữ liệu.
- **Index** là nơi chứa các tài liệu có cấu trúc trường tương ứng. Có thể xem index là khái niệm gần với bảng trong cơ sở dữ liệu quan hệ để dễ hình dung, nhưng cách lưu trữ và truy vấn khác nhau.
- **Document** là một đơn vị dữ liệu, thường được biểu diễn dưới dạng JSON.
- **Field** là một thuộc tính trong document, chẳng hạn `name`, `category` hoặc `price`.

Elasticsearch có thể chia index thành shard và phân phối chúng trên nhiều node. Việc phân shard, replica và vận hành cluster thuộc phạm vi cấu hình Elasticsearch; Spring Data không tự quyết định chiến lược hạ tầng thay cho ứng dụng.

## 4. Ánh xạ lớp Java thành document

Spring Data Elasticsearch dùng annotation để mô tả cách lưu một đối tượng. Ví dụ dưới đây mô tả một sản phẩm:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructors, getters và setters
}
```

Các annotation quan trọng trong ví dụ:

- `@Document(indexName = "products")` chỉ định index mà các đối tượng `Product` được lưu vào.
- `@Id` đánh dấu thuộc tính dùng làm định danh tài liệu.
- `@Field` khai báo kiểu dữ liệu và các thiết lập ánh xạ của một trường.
- `FieldType.Text` phù hợp với nội dung cần phân tích để tìm kiếm toàn văn.
- `FieldType.Keyword` phù hợp với giá trị cần so khớp chính xác, lọc hoặc gom nhóm, chẳng hạn mã danh mục.
- `FieldType.Double` biểu diễn dữ liệu số có phần thập phân.

Việc chọn kiểu trường có ảnh hưởng trực tiếp đến kết quả tìm kiếm. Nếu một trường tên được ánh xạ thành `keyword`, Elasticsearch xem cả giá trị là một đơn vị để so khớp chính xác. Nếu ánh xạ thành `text`, analyzer có thể tách và chuẩn hóa nội dung để phục vụ full-text search.

Trong thực tế, cùng một thuộc tính đôi khi cần cả hai cách sử dụng. Ví dụ tên sản phẩm cần tìm toàn văn nhưng cũng cần sắp xếp hoặc gom nhóm theo toàn bộ giá trị. Elasticsearch hỗ trợ multi-fields để một giá trị được lập chỉ mục dưới nhiều kiểu trường. Khi cần, có thể khai báo `@MultiField` và `@InnerField` trong Spring Data Elasticsearch.

Mapping nên được thiết kế trước khi nạp dữ liệu. Thay đổi kiểu của một field đã có dữ liệu thường cần tạo index mới và nạp lại dữ liệu, thay vì chỉ đổi annotation trong mã nguồn.

## 5. Lưu và truy vấn bằng Repository

Với các thao tác thông dụng, có thể khai báo repository bằng cách mở rộng `ElasticsearchRepository`:

```java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

Ứng dụng có thể tiêm `ProductRepository` vào service rồi gọi các phương thức do Spring Data cung cấp, chẳng hạn lưu một sản phẩm hoặc tìm theo định danh. Phương thức `findByCategory` là một derived query: Spring Data phân tích tên phương thức và tạo truy vấn tương ứng dựa trên thuộc tính của entity.

Ví dụ sử dụng trong service:

```java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository productRepository;

    public ProductSearchService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public List<Product> findByCategory(String category) {
        return productRepository.findByCategory(category);
    }
}
```

Repository phù hợp với các thao tác có cấu trúc rõ ràng và có thể diễn đạt bằng phương thức. Khi cần truy vấn toàn văn cụ thể hoặc kết hợp nhiều điều kiện phức tạp, có thể khai báo truy vấn bằng `@Query` hoặc dùng `ElasticsearchOperations`.

Ví dụ một phương thức tìm tên sản phẩm bằng truy vấn `match`:

```java
import java.util.List;
import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<Product> searchByName(String text);
}
```

Trong ví dụ, `?0` là tham số đầu tiên của phương thức. Truy vấn `match` yêu cầu Elasticsearch phân tích nội dung tìm kiếm theo mapping của trường `name`. Cú pháp truy vấn và các kiểu kết quả cụ thể có thể khác đôi chút giữa các phiên bản Spring Data Elasticsearch.

## 6. Kết hợp full-text search và filter

Một yêu cầu thực tế thường không dừng ở việc tìm một từ khóa. Ví dụ, trang tìm kiếm sản phẩm có thể cần:

1. Tìm sản phẩm có tên phù hợp với cụm “tai nghe bluetooth”.
2. Chỉ lấy sản phẩm thuộc danh mục `audio`.
3. Giới hạn giá tối đa.
4. Sắp xếp kết quả theo mức độ liên quan hoặc giá.
5. Trả về một trang kết quả và số lượng theo từng thương hiệu.

Elasticsearch Query DSL cho phép kết hợp các điều kiện bằng `bool`. Ví dụ minh họa:

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "tai nghe bluetooth" } }
      ],
      "filter": [
        { "term": { "category": "audio" } },
        { "range": { "price": { "lte": 2000000 } } }
      ]
    }
  }
}
```

Ở đây:

- `must` chứa điều kiện truy vấn cần thỏa mãn và có thể ảnh hưởng đến điểm liên quan.
- `match` thực hiện tìm kiếm toàn văn trên trường `name`.
- `filter` giới hạn tập tài liệu theo điều kiện mà không dùng điểm liên quan để xếp hạng.
- `term` phù hợp với so khớp chính xác trên trường như `keyword`.
- `range` lọc theo khoảng giá trị, ví dụ giá nhỏ hơn hoặc bằng giới hạn đã chọn.

Có thể tạo truy vấn tương tự bằng API truy vấn của Spring Data Elasticsearch thông qua `ElasticsearchOperations` và các lớp query tương ứng. Cách này linh hoạt hơn khi điều kiện tìm kiếm được lắp ghép theo đầu vào của người dùng. `ElasticsearchOperations` cũng cung cấp kết quả tìm kiếm có thể chứa thông tin như điểm liên quan và metadata của từng hit.

## 7. Những loại chức năng tìm kiếm thường được xây dựng

| Nhu cầu của sản phẩm | Khả năng Elasticsearch thường dùng | Vai trò của Spring Data Elasticsearch |
|---|---|---|
| Tìm bài viết hoặc sản phẩm theo nội dung | `text`, analyzer, `match` query | Ánh xạ entity và gửi truy vấn từ Java |
| Lọc theo mã, danh mục hoặc trạng thái | `keyword`, `term`, `bool.filter` | Tạo truy vấn bằng repository hoặc operations |
| Lọc theo khoảng giá hoặc thời gian | Trường số/ngày và `range` query | Chuyển điều kiện của ứng dụng thành truy vấn |
| Xếp hạng kết quả | Relevance score và các query phù hợp | Đọc và sử dụng kết quả tìm kiếm có điểm số |
| Bộ lọc có số lượng theo nhóm | Aggregations | Gửi truy vấn aggregation và đọc kết quả |
| Gợi ý khi người dùng nhập | Completion suggester hoặc query phù hợp | Gọi API Elasticsearch và chuyển kết quả về ứng dụng |
| Tìm gần đúng hoặc xử lý từ đồng nghĩa | Fuzzy query, analyzer và synonym configuration | Khai báo và thực thi truy vấn từ Spring |
| Tìm theo vị trí | Kiểu dữ liệu địa lý và geo query | Ánh xạ dữ liệu, xây dựng truy vấn địa lý |

Các chức năng trong bảng phụ thuộc vào thiết kế index và query. Spring Data Elasticsearch giúp ứng dụng gọi những chức năng đó; nó không tự quyết định từ đồng nghĩa, ngôn ngữ, mức độ gần đúng hay cách xếp hạng phù hợp với nghiệp vụ.

## 8. Spring Data Elasticsearch thường được dùng trong kiến trúc nào?

Trong nhiều hệ thống nghiệp vụ, cơ sở dữ liệu quan hệ vẫn là nơi lưu dữ liệu gốc. Elasticsearch được dùng như một kho dữ liệu phục vụ tìm kiếm, chứa bản sao đã được chuẩn bị theo cấu trúc phù hợp với truy vấn.

Ví dụ với cửa hàng trực tuyến:

```text
                 Ghi và cập nhật dữ liệu
Người dùng -> Ứng dụng --------------------> Cơ sở dữ liệu chính
                 |                                  |
                 |                                  | Sự kiện đồng bộ
                 |                                  v
                 |                           Tiến trình lập chỉ mục
                 |                                  |
                 |                                  v
                 |                           Elasticsearch
                 |                                  ^
                 | Tìm kiếm                         |
                 +----------------------------------+
```

Khi người quản trị cập nhật sản phẩm, dữ liệu chính được lưu trong cơ sở dữ liệu nghiệp vụ. Một tiến trình đồng bộ cập nhật document tương ứng trong Elasticsearch. Khi khách hàng tìm sản phẩm, ứng dụng truy vấn Elasticsearch để lấy danh sách kết quả phù hợp.

Thiết kế này giúp mỗi hệ thống làm tốt nhiệm vụ của mình:

- Cơ sở dữ liệu chính quản lý dữ liệu nghiệp vụ, ràng buộc và giao dịch.
- Elasticsearch phục vụ tìm kiếm toàn văn, lọc, xếp hạng và tổng hợp.
- Spring Data Elasticsearch cung cấp lớp tích hợp để ứng dụng Spring làm việc với index tìm kiếm.

Việc đồng bộ cần được thiết kế cẩn thận. Cập nhật cơ sở dữ liệu và Elasticsearch không mặc nhiên nằm trong cùng một giao dịch nguyên tử. Nếu ứng dụng ghi trực tiếp vào cả hai nơi, một thao tác có thể thành công ở cơ sở dữ liệu nhưng thất bại ở Elasticsearch. Các hệ thống cần độ tin cậy cao thường dùng transactional outbox, change data capture hoặc hàng đợi sự kiện để đồng bộ có thể thử lại và phục hồi.

Elasticsearch cũng có đặc tính near-real-time: một thay đổi được ghi vào index có thể cần chờ lần refresh trước khi xuất hiện trong kết quả tìm kiếm. Vì vậy, kết quả tìm kiếm có thể chậm hơn dữ liệu gốc một khoảng ngắn. Ứng dụng cần xác định mức độ trễ này có phù hợp với nghiệp vụ hay không.

## 9. Khi nào nên dùng Spring Data Elasticsearch?

Spring Data Elasticsearch phù hợp khi ứng dụng Spring cần một hoặc nhiều khả năng sau:

- Tìm kiếm toàn văn trên lượng lớn nội dung.
- Xếp hạng kết quả theo mức độ liên quan.
- Kết hợp từ khóa với nhiều bộ lọc và điều kiện sắp xếp.
- Tạo bộ lọc theo nhóm, thống kê và aggregation.
- Xây dựng gợi ý, tìm gần đúng hoặc tìm kiếm đa ngôn ngữ.
- Mở rộng khả năng tìm kiếm bằng index phân tán khi quy mô dữ liệu và tải truy vấn tăng.

Không phải ứng dụng nào cũng cần Elasticsearch. Nếu nhu cầu chỉ là tìm một bản ghi theo ID, lọc vài trường trong một bảng nhỏ hoặc thực hiện giao dịch nhiều bảng, cơ sở dữ liệu quan hệ có thể đáp ứng đơn giản hơn. Việc thêm Elasticsearch cũng kéo theo chi phí vận hành cluster, thiết kế mapping, đồng bộ dữ liệu, giám sát và xử lý sai lệch giữa dữ liệu gốc với index tìm kiếm.

Một nguyên tắc thực tế là chọn Elasticsearch khi trải nghiệm tìm kiếm là một yêu cầu quan trọng của sản phẩm. Hãy giữ dữ liệu nghiệp vụ ở hệ thống phù hợp với giao dịch và dùng Elasticsearch cho mô hình đọc được tối ưu theo cách người dùng tìm kiếm.

## 10. Những điểm cần lưu ý khi triển khai

**Tương thích phiên bản.** Cần chọn phiên bản Spring Boot, Spring Data Elasticsearch, Elasticsearch và Java Client tương thích với nhau. Cấu hình kết nối, API truy vấn và một số kiểu dữ liệu có thể thay đổi giữa các thế hệ phiên bản.

**Mapping và analyzer.** Chọn đúng kiểu `text`, `keyword`, số, ngày hoặc boolean. Analyzer quyết định cách văn bản được tách và chuẩn hóa. Một mapping không phù hợp có thể khiến truy vấn chính xác không hoạt động như mong đợi hoặc làm bộ lọc và aggregation cho kết quả sai.

**Vòng đời index.** Khi cấu trúc dữ liệu thay đổi, cần có kế hoạch tạo index mới, nạp lại dữ liệu và chuyển alias nếu hệ thống yêu cầu cập nhật liên tục. Không nên giả định rằng thay đổi annotation trong entity sẽ tự sửa mọi dữ liệu đã được lập chỉ mục.

**Đồng bộ và tính nhất quán.** Xác định hệ thống nào là nguồn dữ liệu chính, cách phát hiện thay đổi, xử lý xóa, thử lại và khôi phục khi đồng bộ thất bại. Tránh để dữ liệu tìm kiếm trở thành một bản sao không thể tái tạo.

**Bảo mật và vận hành.** Cấu hình xác thực, TLS, quyền truy cập index, giới hạn tài nguyên và giám sát cluster. Thông tin đăng nhập nên được quản lý bằng cấu hình bảo mật hoặc biến môi trường phù hợp, không ghi trực tiếp vào mã nguồn.

**Hiểu Query DSL.** Repository giúp giảm mã lặp cho thao tác phổ biến, nhưng truy vấn tìm kiếm thực tế vẫn cần hiểu các khái niệm như analyzer, `match`, `term`, `bool`, filter, score và aggregation. Khi truy vấn phức tạp, dùng `ElasticsearchOperations` hoặc API query phù hợp sẽ rõ ràng hơn việc cố diễn đạt mọi thứ bằng tên phương thức repository.

## Kết luận

Spring Data Elasticsearch là lớp tích hợp giúp ứng dụng Spring làm việc với Elasticsearch thông qua repository, annotation ánh xạ và API thao tác truy vấn. Nó giải quyết phần kết nối và chuyển đổi giữa mô hình Java với tài liệu trong index, để ứng dụng có thể xây dựng các chức năng tìm kiếm toàn văn, xếp hạng, lọc, phân trang và thống kê.

Giá trị của nó thể hiện rõ nhất khi sản phẩm cần trải nghiệm tìm kiếm phong phú trên nhiều trường dữ liệu. Để triển khai hiệu quả, nhóm phát triển vẫn cần thiết kế mapping và analyzer, hiểu cách Elasticsearch xử lý truy vấn, đồng thời xây dựng cơ chế đồng bộ phù hợp với hệ thống lưu trữ dữ liệu nghiệp vụ.
