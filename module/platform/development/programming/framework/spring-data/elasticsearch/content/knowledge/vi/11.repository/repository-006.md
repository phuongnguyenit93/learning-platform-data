# Phân biệt phương thức CRUD và phương thức truy vấn tự khai báo

## 1. Repository trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp abstraction Repository để tầng service thao tác với document thông qua các phương thức Java. Thay vì tự tạo request HTTP cho mỗi thao tác, ứng dụng khai báo một interface repository kế thừa interface nền tảng của Spring Data.

Ví dụ entity sản phẩm:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters và setters
}
~~~

Repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

`ElasticsearchRepository<Product, String>` cho biết repository quản lý entity `Product` và kiểu định danh của entity là `String`. Repository kế thừa các thao tác nền tảng như lưu, tìm theo ID, đếm và xóa.

Khi ứng dụng cần truy vấn theo tiêu chí nghiệp vụ, có thể khai báo thêm các phương thức ngay trong interface. Spring Data hỗ trợ hai cách phổ biến:

- **Derived query:** Spring Data phân tích tên phương thức và tạo truy vấn từ tên đó.
- **Declared query:** lập trình viên khai báo nội dung truy vấn rõ ràng, thường bằng annotation `@Query` chứa Elasticsearch Query DSL.

Ngoài ra, có thể mở rộng repository bằng custom implementation khi cần xây dựng truy vấn động hoặc xử lý tìm kiếm phức tạp.

## 2. Phương thức CRUD là gì?

CRUD là viết tắt của Create, Read, Update và Delete. Đây là các thao tác cơ bản để quản lý document.

Các phương thức CRUD được kế thừa từ các interface repository của Spring Data. Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Không cần khai báo lại các phương thức cơ bản. Có thể sử dụng trực tiếp:

~~~java
productRepository.save(product);
productRepository.findById("p-100");
productRepository.findAll();
productRepository.existsById("p-100");
productRepository.count();
productRepository.deleteById("p-100");
productRepository.delete(product);
~~~

Một số phương thức thường gặp:

| Phương thức | Ý nghĩa |
|---|---|
| `save(entity)` | Lưu document; nếu ID đã tồn tại thì document tương ứng có thể được ghi đè bằng dữ liệu mới |
| `saveAll(entities)` | Lưu nhiều entity |
| `findById(id)` | Tìm một document theo định danh |
| `findAll()` | Lấy tất cả document |
| `findAll(Pageable)` | Lấy document theo phân trang |
| `findAll(Sort)` | Lấy document theo thứ tự sắp xếp |
| `existsById(id)` | Kiểm tra document có ID đó hay không |
| `count()` | Đếm document |
| `deleteById(id)` | Xóa document theo ID |
| `delete(entity)` | Xóa document tương ứng với entity |
| `deleteAll()` | Xóa toàn bộ document theo phạm vi repository |

CRUD tập trung vào thao tác với document theo định danh hoặc trên toàn bộ tập dữ liệu. Các phương thức này không mô tả điều kiện tìm kiếm tùy chỉnh như tên sản phẩm, danh mục, khoảng giá hoặc trạng thái.

### CRUD không đồng nghĩa với truy vấn nghiệp vụ

Giả sử yêu cầu là tìm tất cả sản phẩm thuộc danh mục `audio` và có giá nhỏ hơn hoặc bằng 2.000.000. CRUD không có sẵn một phương thức mang điều kiện đó. Ta cần khai báo phương thức truy vấn:

~~~java
List<Product> findByCategoryAndPriceLessThanEqual(
    String category,
    Double maxPrice
);
~~~

Sự khác biệt nằm ở nguồn gốc và mục đích của phương thức:

- CRUD được kế thừa từ repository nền tảng.
- Phương thức truy vấn tự khai báo được thêm theo yêu cầu của ứng dụng và có điều kiện cụ thể.

## 3. Phương thức truy vấn tự khai báo là gì?

Phương thức truy vấn tự khai báo là phương thức do lập trình viên đặt tên trong repository để biểu diễn một điều kiện tìm kiếm. Spring Data đọc tên phương thức, phân tích các phần như `find`, `By`, tên thuộc tính và toán tử, sau đó tạo truy vấn tương ứng.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndActiveTrue(String category);

    List<Product> findByPriceLessThan(Double maxPrice);

    List<Product> findByCategoryAndPriceLessThanEqual(
        String category,
        Double maxPrice
    );
}
~~~

Các phương thức trên không cần phần thân. Spring Data tạo implementation khi khởi tạo repository.

Ví dụ lời gọi:

~~~java
List<Product> products =
    productRepository.findByCategoryAndPriceLessThanEqual(
        "audio",
        2_000_000.0
    );
~~~

Spring Data phân tích tên phương thức:

- `findBy`: tìm document theo điều kiện.
- `Category`: thuộc tính `category` của entity.
- `And`: kết hợp hai điều kiện.
- `Price`: thuộc tính `price`.
- `LessThanEqual`: toán tử nhỏ hơn hoặc bằng.

Về mặt ý tưởng, truy vấn có thể tương đương:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "audio"
          }
        },
        {
          "range": {
            "price": {
              "lte": 2000000
            }
          }
        }
      ]
    }
  }
}
~~~

Đây là minh họa cho điều kiện tìm kiếm. Query DSL thực tế được tạo ra phụ thuộc vào phiên bản Spring Data Elasticsearch và kiểu mapping của từng field.

## 4. Cấu trúc tên phương thức derived query

Tên phương thức thường gồm phần giới thiệu thao tác, phần phân tách `By`, các thuộc tính và toán tử.

~~~text
findBy + Category + And + Price + LessThanEqual
  |        |                  |        |
  |        |                  |        +-- Toán tử so sánh
  |        |                  +----------- Thuộc tính thứ hai
  |        +------------------------------ Thuộc tính thứ nhất
  +--------------------------------------- Loại thao tác
~~~

Một số tiền tố thường gặp:

| Tiền tố | Mục đích |
|---|---|
| `findBy...` | Tìm document theo điều kiện |
| `readBy...` | Đọc document theo điều kiện |
| `getBy...` | Lấy document theo điều kiện |
| `queryBy...` | Truy vấn document theo điều kiện |
| `countBy...` | Đếm document thỏa điều kiện |
| `existsBy...` | Kiểm tra có document thỏa điều kiện |
| `findFirstBy...` | Lấy kết quả đầu tiên theo điều kiện |
| `findTopBy...` | Lấy kết quả đầu tiên theo giới hạn |

Các từ khóa và tổ hợp toán tử được hỗ trợ phụ thuộc vào module Spring Data và phiên bản. Không nên giả định mọi từ khóa dùng được trong JPA đều được hỗ trợ trong Spring Data Elasticsearch.

Tên thuộc tính phải tương ứng với property trong entity Java. Ví dụ entity có thuộc tính `category`, phương thức nên dùng `findByCategory`, kể cả khi mapping Elasticsearch dùng một tên field khác thông qua `@Field(name = "...")`. Spring Data dùng metadata ánh xạ để liên hệ property Java với field lưu trữ.

## 5. Các toán tử truy vấn thường dùng

Một số toán tử phổ biến có thể diễn đạt bằng tên phương thức:

| Toán tử | Ví dụ tên phương thức | Ý nghĩa |
|---|---|---|
| Bằng | `findByCategory` hoặc `findByCategoryEquals` | Khớp giá trị category |
| Khác | `findByCategoryNot` | Không bằng giá trị chỉ định |
| Nhỏ hơn | `findByPriceLessThan` | Giá nhỏ hơn giá trị truyền vào |
| Nhỏ hơn hoặc bằng | `findByPriceLessThanEqual` | Giá không vượt quá giá trị |
| Lớn hơn | `findByPriceGreaterThan` | Giá lớn hơn giá trị |
| Lớn hơn hoặc bằng | `findByPriceGreaterThanEqual` | Giá ít nhất bằng giá trị |
| Trong khoảng | `findByPriceBetween` | Giá nằm trong khoảng |
| Thuộc danh sách | `findByCategoryIn` | Khớp một trong các giá trị |
| Không thuộc danh sách | `findByCategoryNotIn` | Không thuộc danh sách |
| Có giá trị | `findByNameIsNotNull` | Field có giá trị khác null |
| Không có giá trị | `findByNameIsNull` | Field null hoặc không có giá trị được lập chỉ mục theo semantics của Elasticsearch |
| Boolean đúng | `findByActiveTrue` | Field active là true |
| Boolean sai | `findByActiveFalse` | Field active là false |

Ví dụ kết hợp:

~~~java
List<Product> findByPriceBetween(Double min, Double max);

List<Product> findByCategoryIn(Collection<String> categories);

List<Product> findByActiveTrueAndPriceGreaterThan(Double minPrice);

long countByCategory(String category);

boolean existsByCategoryAndActiveTrue(String category);
~~~

Các phương thức trả về `count` hoặc `exists` phù hợp khi ứng dụng chỉ cần số lượng hoặc sự tồn tại, thay vì tải toàn bộ document về bộ nhớ.

Với điều kiện văn bản, cần phân biệt kiểu field:

- `keyword` thường dùng cho so khớp chính xác, lọc và aggregation.
- `text` được phân tích bởi analyzer và phù hợp với full-text search.
- Tên phương thức có thể biểu diễn điều kiện cơ bản, nhưng hành vi tìm kiếm văn bản còn phụ thuộc analyzer và query mà Spring Data tạo ra.

Hãy xem tài liệu đúng phiên bản để xác nhận toán tử cụ thể, đặc biệt với wildcard, fuzzy, phrase và truy vấn địa lý.

## 6. Kết hợp điều kiện AND, OR và sắp xếp

Có thể kết hợp nhiều điều kiện bằng `And` và `Or`:

~~~java
List<Product> findByCategoryAndActiveTrue(String category);

List<Product> findByCategoryOrActiveTrue(String category);
~~~

`And` yêu cầu các điều kiện kết hợp cùng thỏa mãn. `Or` cho phép kết quả thỏa mãn một trong các nhánh. Khi biểu thức có nhiều toán tử logic, cần đọc kỹ cách Spring Data phân tích tên phương thức và ưu tiên nhóm điều kiện.

Có thể khai báo thứ tự sắp xếp ngay trong tên:

~~~java
List<Product> findByCategoryOrderByPriceAsc(String category);

List<Product> findByActiveTrueOrderByPriceDesc();
~~~

Có thể truyền `Sort` khi muốn quyết định thứ tự ở thời điểm gọi:

~~~java
List<Product> findByCategory(
    String category,
    Sort sort
);
~~~

Ví dụ:

~~~java
List<Product> products = productRepository.findByCategory(
    "audio",
    Sort.by(Sort.Direction.ASC, "price")
);
~~~

Tên property dùng trong `Sort` thường là tên thuộc tính Java của entity. Hãy xác nhận cách ánh xạ field và hỗ trợ sort của kiểu dữ liệu trong phiên bản đang dùng.

## 7. Phân trang và kiểu kết quả

Phương thức truy vấn có thể nhận `Pageable` để giới hạn kết quả và yêu cầu phân trang:

~~~java
Page<Product> findByCategory(String category, Pageable pageable);
~~~

Cách gọi:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "price")
);

Page<Product> page =
    productRepository.findByCategory("audio", pageable);
~~~

Một số kiểu kết quả thường gặp:

| Kiểu trả về | Khi nào dùng |
|---|---|
| `Product` | Kỳ vọng tối đa một kết quả |
| `Optional<Product>` | Có thể có hoặc không có một kết quả |
| `List<Product>` | Cần danh sách kết quả |
| `Page<Product>` | Cần dữ liệu trang hiện tại và thông tin tổng số trang/kết quả |
| `Slice<Product>` | Cần biết còn trang tiếp theo hay không, nếu kiểu này được hỗ trợ cho phương thức và phiên bản đang dùng |
| `SearchHits<Product>` | Cần metadata tìm kiếm như score, highlights hoặc thông tin hit |
| `SearchPage<Product>` | Cần kết quả tìm kiếm cùng thông tin phân trang |

Với `Page`, thông tin tổng số kết quả có thể khiến Elasticsearch phải thực hiện thêm công việc đếm hoặc lấy total hits. Với tập dữ liệu lớn, hãy cân nhắc có thật sự cần tổng số trang hay chỉ cần lấy tiếp trang sau.

`findAll()` không phân trang có thể tải lượng dữ liệu rất lớn. Trong ứng dụng thực tế, nên dùng `Pageable`, giới hạn kết quả hoặc cơ chế cuộn/phân trang tìm kiếm phù hợp với yêu cầu và phiên bản Elasticsearch.

## 8. Phương thức CRUD và derived query: ví dụ đối chiếu

Cùng xét repository sản phẩm:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    // CRUD kế thừa: không cần tự khai báo
    // save(Product)
    // findById(String)
    // findAll()
    // deleteById(String)

    // Derived query: điều kiện được suy ra từ tên phương thức
    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndActiveTrue(String category);

    List<Product> findByCategoryAndPriceLessThanEqual(
        String category,
        Double maxPrice
    );

    Optional<Product> findFirstByName(String name);

    Page<Product> findByActiveTrue(Pageable pageable);
}
~~~

Bảng đối chiếu:

| Nhu cầu | Cách gọi | Loại phương thức |
|---|---|---|
| Lưu một sản phẩm | `save(product)` | CRUD kế thừa |
| Tìm sản phẩm theo ID | `findById(id)` | CRUD kế thừa |
| Xóa theo ID | `deleteById(id)` | CRUD kế thừa |
| Tìm theo danh mục | `findByCategory(category)` | Derived query |
| Tìm sản phẩm đang hoạt động | `findByActiveTrue()` | Derived query |
| Tìm theo danh mục và giá tối đa | `findByCategoryAndPriceLessThanEqual(...)` | Derived query |
| Tìm một kết quả đầu tiên theo tên | `findFirstByName(name)` | Derived query |
| Lấy sản phẩm active theo trang | `findByActiveTrue(pageable)` | Derived query |

Điểm cần nhớ: phương thức CRUD được cung cấp bởi interface cha, còn derived query được khai báo thêm theo thuộc tính và điều kiện của domain model.

## 9. Declared query bằng @Query

Tên phương thức có thể trở nên dài hoặc khó diễn đạt khi truy vấn có nhiều điều kiện. Khi đó, có thể dùng `@Query` để khai báo trực tiếp Elasticsearch Query DSL.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<Product> searchByName(String keyword);
}
~~~

`@Query` nhận một chuỗi JSON biểu diễn query. Placeholder `?0` là tham số đầu tiên của phương thức. Tham số thứ hai có thể được tham chiếu bằng `?1`, tham số thứ ba bằng `?2`, v.v.

Ví dụ kết hợp full-text search và filter:

~~~java
@Query("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "?0"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "?1"
        }
      },
      {
        "range": {
          "price": {
            "lte": "?2"
          }
        }
      }
    ]
  }
}
""")
List<Product> searchProducts(
    String keyword,
    String category,
    Double maxPrice
);
~~~

Đoạn trên dùng Java text block để dễ đọc. Nếu dự án dùng phiên bản Java không hỗ trợ text block, cần viết chuỗi theo cách nối hoặc escape dấu nháy.

Ý nghĩa truy vấn:

- `match` tìm kiếm toàn văn trên `name`.
- `must` chứa điều kiện truy vấn cần thỏa mãn và có thể ảnh hưởng điểm liên quan.
- `filter` giới hạn theo danh mục và khoảng giá mà không dùng điều kiện lọc để tính điểm liên quan.
- `term` phù hợp với `category` kiểu keyword.
- `range` giới hạn giá không vượt quá tham số truyền vào.

`@Query` vẫn là một phương thức truy vấn tự khai báo, nhưng nội dung query do lập trình viên viết rõ ràng thay vì được suy ra từ tên phương thức.

## 10. Khi nào dùng derived query và khi nào dùng @Query?

Hai cách đều tạo ra phương thức truy vấn trong repository, nhưng phù hợp với độ phức tạp khác nhau.

| Tiêu chí | Derived query | `@Query` |
|---|---|---|
| Nguồn truy vấn | Tên phương thức | Chuỗi Query DSL |
| Độ dài mã | Ngắn với điều kiện đơn giản | Có thể dài hơn |
| Khả năng đọc | Dễ đọc khi ít điều kiện | Thể hiện trực tiếp cấu trúc query |
| Toán tử và điều kiện | Phụ thuộc parser và từ khóa được hỗ trợ | Có thể dùng nhiều khả năng Query DSL |
| Thay đổi điều kiện | Thay tên phương thức hoặc tham số | Sửa JSON query và placeholder |
| Truy vấn động | Hạn chế khi cấu trúc query thay đổi nhiều | Phù hợp với query có cấu trúc tương đối cố định; query động phức tạp nên dùng custom implementation |
| Phù hợp | Lọc theo thuộc tính, so sánh, sắp xếp cơ bản | Full-text, bool query, range, nested hoặc cấu trúc DSL cần kiểm soát |

Nên chọn derived query khi tên phương thức vẫn ngắn, thể hiện rõ nghiệp vụ và các toán tử cần dùng được Spring Data hỗ trợ.

Nên chọn `@Query` khi cần kiểm soát cấu trúc Query DSL, ví dụ kết hợp `match`, `bool`, `filter`, `range`, `nested` hoặc các toán tử mà derived query không diễn đạt thuận tiện.

Không nên biến tên phương thức thành một câu dài chứa quá nhiều `And`, `Or` và điều kiện. Một phương thức dài khó đọc, khó thay đổi và khó xác định chính xác cấu trúc logic.

## 11. Custom repository implementation cho truy vấn phức tạp

Có những yêu cầu mà cả tên phương thức lẫn một chuỗi `@Query` cố định đều không thuận tiện, ví dụ:

- Người dùng chọn tùy ý nhiều bộ lọc trên giao diện.
- Chỉ thêm điều kiện khi tham số được cung cấp.
- Kết hợp nhiều nhánh truy vấn theo quyền hoặc ngữ cảnh.
- Cần aggregation, highlight, suggest hoặc metadata kết quả đặc biệt.
- Cần xây dựng Query DSL theo cấu trúc động.

Có thể mở rộng repository bằng custom fragment:

~~~java
import java.util.List;

public interface ProductSearchExtension {

    List<Product> search(ProductSearchCriteria criteria);
}
~~~

Kế thừa cả repository nền tảng và fragment:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchExtension {
}
~~~

Một lớp triển khai fragment có thể tiêm `ElasticsearchOperations` để tạo truy vấn:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchExtensionImpl
        implements ProductSearchExtension {

    private final ElasticsearchOperations operations;

    public ProductSearchExtensionImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> search(ProductSearchCriteria criteria) {
        // Xây dựng Query hoặc NativeQuery từ các tiêu chí có mặt.
        // Gọi operations.search(query, Product.class).
        // Chuyển SearchHits<Product> thành danh sách Product.
        throw new UnsupportedOperationException(
            "Implement query construction for the application's criteria"
        );
    }
}
~~~

Đây là khung tổ chức custom fragment. Phần xây dựng query cần được triển khai theo các trường và điều kiện thực tế của ứng dụng, sử dụng API query tương ứng với phiên bản Spring Data Elasticsearch đang dùng.

Ưu điểm của cách này là logic tìm kiếm động được tách thành một thành phần riêng. Repository vẫn giữ các phương thức CRUD và derived query đơn giản, trong khi phần tìm kiếm phức tạp có thể được tổ chức, kiểm thử và thay đổi độc lập.

Không nên đưa mọi truy vấn vào custom implementation. Nếu chỉ cần `findByCategory`, derived query ngắn và dễ hiểu hơn.

## 12. Những điểm cần chú ý khi viết tên phương thức

**Tên property phải khớp với entity.** Spring Data phân tích property Java, không đơn giản là đoán tên field trong JSON. Nếu entity có `productCategory`, phương thức nên dùng `findByProductCategory`, kể cả khi mapping đổi tên field ở Elasticsearch.

**Kiểm tra toán tử được hỗ trợ.** Không phải mọi từ khóa của Spring Data JPA đều áp dụng cho Elasticsearch. Hãy đối chiếu danh sách keyword của phiên bản đang dùng.

**Phân biệt text và keyword.** Truy vấn bằng nhau trên field keyword có semantics khác tìm kiếm toàn văn trên field text. Chọn mapping phù hợp với mục đích tìm kiếm.

**Cẩn thận với nested object.** Nếu điều kiện phải khớp trên cùng một phần tử của collection nested, cần truy vấn trong đúng nested scope. Đừng giả định mọi derived query trên property lồng nhau tự tạo nested query như nghiệp vụ mong muốn; dùng `@Query` hoặc `ElasticsearchOperations` nếu cần kiểm soát nested DSL.

**Tránh kết quả vượt quá kỳ vọng.** Phương thức trả về một entity hoặc `Optional` cần có điều kiện bảo đảm tối đa một kết quả. Nếu có thể trả nhiều document, dùng `List` hoặc kiểu phân trang phù hợp.

**Chú ý phương thức xóa theo điều kiện.** Các derived delete method có thể xóa nhiều document. Hãy xác định rõ điều kiện và phạm vi trước khi gọi.

**Không tải toàn bộ index.** `findAll()` trên index lớn có thể tạo tải đáng kể. Dùng điều kiện, phân trang hoặc cơ chế tìm kiếm theo luồng phù hợp.

**Giữ tên phương thức phản ánh nghiệp vụ.** Một phương thức tên `findActiveProductsUnderPrice` có thể dễ hiểu hơn một chuỗi dài các thuộc tính kỹ thuật, nhưng phần tên vẫn phải tuân theo cú pháp derived query mà Spring Data phân tích được. Khi tên bắt đầu khó đọc, cân nhắc `@Query` hoặc custom fragment.

## 13. Kiểm tra và sử dụng repository trong service

Service nên gọi repository theo ý nghĩa nghiệp vụ thay vì tự xây dựng request Elasticsearch ở mọi nơi.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Product save(Product product) {
        return productRepository.save(product);
    }

    public List<Product> findActiveProducts(String category) {
        return productRepository.findByCategoryAndActiveTrue(category);
    }

    public List<Product> findProductsUnderPrice(
            String category,
            Double maxPrice) {
        return productRepository.findByCategoryAndPriceLessThanEqual(
            category,
            maxPrice
        );
    }
}
~~~

Khi kiểm tra repository, nên dùng integration test với Elasticsearch tương thích phiên bản ứng dụng. Kiểm tra ít nhất:

1. CRUD: lưu, tìm theo ID, cập nhật và xóa document.
2. Derived query: xác nhận điều kiện `And`, `Or`, range và sort tạo ra kết quả đúng.
3. Declared query: xác nhận placeholder truyền đúng tham số và Query DSL thực hiện đúng điều kiện.
4. Phân trang: kiểm tra trang, thứ tự và tổng số kết quả khi dùng `Page`.
5. Mapping: xác nhận field text/keyword và nested được truy vấn theo đúng semantics.
6. Trường hợp không có kết quả, null hoặc dữ liệu thiếu theo hợp đồng của ứng dụng.

Không nên chỉ mock repository rồi kết luận truy vấn Elasticsearch hoạt động chính xác. Mock có thể kiểm tra service gọi đúng phương thức, nhưng không xác nhận Query DSL, mapping và analyzer thực sự cho ra kết quả mong muốn.

## 14. Quy tắc lựa chọn phương thức

Có thể dùng các nguyên tắc sau khi thiết kế repository:

- Dùng CRUD kế thừa cho lưu, cập nhật, tìm theo ID, đếm và xóa cơ bản.
- Dùng derived query cho điều kiện đơn giản, ổn định và dễ diễn đạt bằng tên phương thức.
- Dùng `@Query` khi cần viết rõ Elasticsearch Query DSL nhưng cấu trúc truy vấn vẫn tương đối cố định.
- Dùng custom repository fragment với `ElasticsearchOperations` khi cần tạo truy vấn động, nhiều nhánh điều kiện hoặc kết quả tìm kiếm nâng cao.
- Dùng `Pageable` hoặc cơ chế phân trang phù hợp thay vì lấy toàn bộ dữ liệu.
- Kiểm tra phiên bản Spring Data Elasticsearch vì khả năng parser, kiểu trả về và API query có thể thay đổi.

## Kết luận

Phương thức CRUD là các thao tác nền tảng được kế thừa từ repository, phục vụ lưu, đọc, cập nhật và xóa document. Phương thức truy vấn tự khai báo bổ sung điều kiện nghiệp vụ và có thể được triển khai bằng derived query, `@Query` hoặc custom repository fragment.

Derived query phù hợp với điều kiện đơn giản, dễ đọc. `@Query` cho phép kiểm soát trực tiếp Elasticsearch Query DSL. Custom implementation phù hợp với tìm kiếm động hoặc phức tạp. Chọn đúng loại phương thức giúp repository giữ được giao diện rõ ràng, service dễ sử dụng và truy vấn Elasticsearch dễ bảo trì hơn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch — Query Methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
- [Spring Data Elasticsearch — Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html)
