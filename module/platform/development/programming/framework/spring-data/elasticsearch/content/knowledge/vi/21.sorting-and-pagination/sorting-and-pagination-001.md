# Sort, Sort.Order và Pageable trong Spring Data

Trong ứng dụng Spring Data Elasticsearch, tìm kiếm thường cần hai khả năng đi cùng nhau: chọn document phù hợp và quyết định thứ tự hiển thị. Query xác định tập kết quả, còn sort quyết định document nào đứng trước. Pageable kết hợp thông tin phân trang với sort để service hoặc repository có thể lấy một phần kết quả theo thứ tự mong muốn.

Spring Data cung cấp các abstraction quen thuộc:

- Sort biểu diễn một hoặc nhiều điều kiện sắp xếp.
- Sort.Order mô tả một điều kiện sort, gồm field và hướng tăng/giảm.
- Pageable mô tả trang hiện tại, kích thước trang, offset và sort.
- PageRequest là implementation phổ biến để tạo Pageable.

Các abstraction này giúp code repository và service ít phụ thuộc vào chi tiết REST API của Elasticsearch. Tuy nhiên, Elasticsearch chỉ sort hiệu quả trên những field có mapping phù hợp. Đặc biệt, không nên sort trực tiếp trên field text đã được phân tích; thường cần dùng keyword sub-field, numeric field hoặc date field có doc values.

## 1. Vì sao cần sort và phân trang?

Giả sử trang danh sách sản phẩm cần hiển thị 20 sản phẩm mỗi lần, mới cập nhật trước. Nếu chỉ chạy search mà không chỉ định sort, thứ tự kết quả không phải là một cam kết nghiệp vụ ổn định. Ứng dụng nên yêu cầu sắp xếp theo thời gian cập nhật giảm dần.

Ví dụ:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("updatedAt"))
    );

    Page<Product> page = productRepository.findAll(pageable);

Ở đây:

- Trang đầu tiên có chỉ số 0.
- Mỗi trang chứa tối đa 20 sản phẩm.
- updatedAt được sắp xếp giảm dần.
- Repository trả về một Page chứa nội dung và metadata phân trang.

Phân trang giúp giới hạn số document trả về trong một request. Sort giúp kết quả có thứ tự phù hợp với trải nghiệm người dùng. Khi dùng cùng nhau, sort cần đủ ổn định để người dùng chuyển từ trang này sang trang khác mà ít gặp tình trạng kết quả lặp hoặc bị bỏ qua.

## 2. Sort là gì?

Sort là abstraction của Spring Data để mô tả thứ tự sắp xếp. Nó có thể chứa một hoặc nhiều Sort.Order.

Ví dụ sort theo giá tăng dần:

    Sort sort = Sort.by("price").ascending();

Hoặc:

    Sort sort = Sort.by(Sort.Order.asc("price"));

Sort giảm dần:

    Sort sort = Sort.by(Sort.Order.desc("createdAt"));

Sort không chứa một field duy nhất theo bản chất. Nó là một tập có thứ tự các Order. Khi có nhiều Order, Elasticsearch áp dụng chúng theo thứ tự ưu tiên: field đầu tiên được xét trước; nếu hai document bằng nhau ở field đó, field tiếp theo được dùng để phân biệt.

Có thể biểu diễn:

    Sort sort = Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.asc("name")
    );

Kết quả được sắp xếp theo updatedAt giảm dần. Nếu hai document có cùng updatedAt, name tăng dần sẽ quyết định thứ tự giữa chúng.

## 3. Sort.Order và các thuộc tính

Sort.Order mô tả một điều kiện sắp xếp riêng. Những thành phần quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| property | Tên field hoặc thuộc tính dùng để sort |
| direction | ASC hoặc DESC |
| ascending() | Tạo Order tăng dần |
| descending() | Tạo Order giảm dần |
| null handling | Gợi ý cách xử lý giá trị null ở abstraction Spring Data; khả năng chuyển đổi phụ thuộc datastore |
| ignoreCase() | Đánh dấu mong muốn bỏ qua khác biệt chữ hoa/chữ thường nếu datastore hỗ trợ |

Ví dụ:

    Sort.Order priceAscending =
        Sort.Order.asc("price");

    Sort.Order newestFirst =
        Sort.Order.desc("createdAt");

    Sort.Order nameAscending =
        Sort.Order.asc("name");

Có thể tạo Order từ direction:

    Sort.Order order = new Sort.Order(
        Sort.Direction.DESC,
        "createdAt"
    );

Sort.Order chỉ mô tả thứ tự. Nó không xác minh field có tồn tại trong Elasticsearch mapping hay không, cũng không tự chuyển field text thành keyword. Việc chọn field phù hợp vẫn thuộc trách nhiệm của thiết kế mapping và query.

## 4. Tạo Sort với một field

Các cách viết thường dùng:

    Sort byPrice = Sort.by("price");

    Sort priceDescending =
        Sort.by(Sort.Direction.DESC, "price");

    Sort newestFirst =
        Sort.by(Sort.Order.desc("createdAt"));

    Sort alphabetical =
        Sort.by(Sort.Order.asc("name"));

Sort.by("price") mặc định tạo thứ tự tăng dần. Để code dễ đọc trong nghiệp vụ, nên chỉ rõ hướng nếu thứ tự có ý nghĩa quan trọng:

    Sort sort = Sort.by(
        Sort.Order.desc("rating")
    );

Với giá trị số, ASC thường là từ nhỏ đến lớn; DESC là từ lớn đến nhỏ. Với ngày, DESC thường đưa thời điểm mới nhất lên trước. Với keyword, ASC/DESC dựa trên thứ tự term theo semantics của Elasticsearch, không phải thứ tự ngôn ngữ tự nhiên.

## 5. Kết hợp nhiều Sort.Order

Sort có thể chứa nhiều điều kiện:

    Sort sort = Sort.by(
        Sort.Order.desc("rating"),
        Sort.Order.desc("purchaseCount"),
        Sort.Order.asc("name")
    );

Elasticsearch sẽ:

1. Sắp xếp rating giảm dần.
2. Nếu rating bằng nhau, sắp xếp purchaseCount giảm dần.
3. Nếu cả hai field đều bằng nhau, sắp xếp name tăng dần.

Đây là sort đa tiêu chí. Thứ tự Order trong Sort rất quan trọng. Đổi thứ tự các Order sẽ đổi thứ tự ưu tiên.

Một ví dụ khác cho trang đơn hàng:

    Sort orderSort = Sort.by(
        Sort.Order.asc("deliveryDate"),
        Sort.Order.desc("priority"),
        Sort.Order.asc("orderNumber")
    );

Các đơn được sắp theo ngày giao gần trước; trong cùng ngày, đơn ưu tiên cao trước; nếu vẫn bằng nhau, orderNumber tăng dần.

### Dùng Sort.and

Có thể ghép các Sort:

    Sort primary = Sort.by(
        Sort.Order.desc("updatedAt")
    );

    Sort tieBreaker = Sort.by(
        Sort.Order.asc("productId")
    );

    Sort combined = primary.and(tieBreaker);

Cách này hữu ích khi một sort chính được tái sử dụng và mỗi use case thêm một điều kiện phân biệt riêng.

## 6. Sort.unsorted và Pageable

Nếu không cần sắp xếp, có thể dùng:

    Sort sort = Sort.unsorted();

Với Pageable:

    Pageable pageable = PageRequest.of(0, 20);

PageRequest không có Sort sẽ biểu diễn trang và kích thước trang mà không yêu cầu sort cụ thể.

Không nên dựa vào thứ tự ngẫu nhiên hoặc thứ tự nội bộ của shard nếu giao diện cần một thứ tự có ý nghĩa. Khi người dùng chuyển trang, sort ổn định đặc biệt quan trọng.

## 7. Pageable là gì?

Pageable là interface mô tả yêu cầu phân trang. Nó chứa:

- page number: số trang, bắt đầu từ 0.
- page size: số phần tử tối đa trong một trang.
- offset: vị trí bắt đầu trong tập kết quả.
- sort: thứ tự sắp xếp.

PageRequest là implementation thường dùng:

    Pageable pageable = PageRequest.of(0, 20);

    Pageable secondPage = PageRequest.of(1, 20);

    Pageable thirdPage = PageRequest.of(2, 20);

Với page size bằng 20:

| Page number | Offset | Phần kết quả |
|---:|---:|---|
| 0 | 0 | Document 1 đến 20 |
| 1 | 20 | Document 21 đến 40 |
| 2 | 40 | Document 41 đến 60 |

Offset được tính bằng page number nhân page size. Page number bắt đầu từ 0, không phải 1. Nếu API bên ngoài nhận số trang bắt đầu từ 1, service hoặc controller cần chuyển đổi trước khi tạo PageRequest.

### Tạo Pageable có Sort

Có thể truyền Sort trực tiếp:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("name")
        )
    );

Hoặc tạo Pageable trước rồi thay Sort:

    Pageable pageable = PageRequest.of(0, 20)
        .withSort(Sort.by(Sort.Order.desc("createdAt")));

Khi sort là một phần của API, nên tạo Pageable tại tầng nhận yêu cầu và truyền nó qua service đến repository hoặc ElasticsearchOperations.

### Kiểm tra tham số phân trang

PageRequest yêu cầu page number không âm và page size lớn hơn 0. Không nên truyền trực tiếp page/size do client gửi mà không giới hạn:

    int page = Math.max(requestedPage, 0);
    int size = Math.min(Math.max(requestedSize, 1), 100);

    Pageable pageable = PageRequest.of(page, size);

Ví dụ trên giới hạn page size tối đa 100 để tránh request trả về lượng dữ liệu quá lớn. Mức giới hạn thực tế cần phù hợp với API và kích thước document.

## 8. Dùng Pageable trong ElasticsearchRepository

Spring Data Elasticsearch repository hỗ trợ các phương thức nhận Pageable.

Ví dụ:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        Page<Product> findByCategory(
            String category,
            Pageable pageable
        );
    }

Service:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public Page<Product> findCategory(
                String category,
                int page,
                int size) {

            Pageable pageable = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Order.desc("createdAt"))
            );

            return repository.findByCategory(category, pageable);
        }
    }

Repository method sẽ tìm các sản phẩm thuộc category và áp dụng phân trang cùng sort được truyền vào.

Có thể dùng Pageable với findAll:

    Page<Product> products =
        productRepository.findAll(
            PageRequest.of(
                0,
                20,
                Sort.by(Sort.Order.asc("name"))
            )
        );

Các method derived query vẫn có thể nhận Pageable:

    Page<Product> findByStatus(
        ProductStatus status,
        Pageable pageable
    );

Tên field trong method và sort cần phù hợp với metadata entity và mapping thực tế.

## 9. Đọc Page và metadata phân trang

Page<T> chứa nội dung trang cùng thông tin tổng quan:

    Page<Product> page =
        productRepository.findAll(pageable);

    List<Product> products = page.getContent();
    int currentPage = page.getNumber();
    int pageSize = page.getSize();
    long totalElements = page.getTotalElements();
    int totalPages = page.getTotalPages();
    boolean hasNext = page.hasNext();
    boolean hasPrevious = page.hasPrevious();

Các thông tin thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| getContent() | Danh sách phần tử trong trang |
| getNumber() | Chỉ số trang hiện tại |
| getSize() | Kích thước trang được yêu cầu |
| getNumberOfElements() | Số phần tử thực tế trong trang |
| getTotalElements() | Tổng số phần tử theo metadata truy vấn |
| getTotalPages() | Tổng số trang |
| hasNext() | Có trang tiếp theo hay không |
| hasPrevious() | Có trang trước hay không |
| isFirst() / isLast() | Trang hiện tại có phải đầu/cuối hay không |

Page phù hợp khi giao diện cần hiển thị tổng số kết quả hoặc tổng số trang. Tuy nhiên, việc lấy total hits chính xác có thể tốn thêm tài nguyên tùy truy vấn và cấu hình Elasticsearch.

Nếu giao diện chỉ cần biết còn dữ liệu để tải tiếp hay không, có thể cân nhắc Slice hoặc một response nhẹ hơn nếu repository/API đang dùng hỗ trợ phù hợp. Không nên tính tổng số trang nếu giao diện không cần.

## 10. Sort trên field nào trong Elasticsearch?

Không phải field nào cũng phù hợp để sort. Elasticsearch cần một cách lưu trữ cho phép đọc giá trị field hiệu quả khi sắp xếp.

Các kiểu field thường dùng:

| Mapping type | Dùng để sort? | Ghi chú |
|---|---|---|
| keyword | Có | Thường dùng cho tên chuẩn hóa, mã, trạng thái |
| long, integer, double, float | Có | Phù hợp cho giá, số lượng, điểm |
| date, date_nanos | Có | Phù hợp cho thời gian |
| boolean | Có | Có thể sort theo giá trị boolean |
| text | Thường không | Field text mặc định không có doc values; sort trực tiếp thường bị từ chối |
| geo_point | Có theo kiểu geo-distance sort | Cần cấu hình sort địa lý phù hợp |

Elasticsearch thường dùng doc values để hỗ trợ sort, aggregation và truy cập giá trị field theo document. Keyword và các kiểu scalar phổ biến thường bật doc_values mặc định. Field text thường không bật doc_values vì được tối ưu cho full-text search.

### Không sort trực tiếp trên text field

Mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "price": {
            "type": "double"
          },
          "createdAt": {
            "type": "date"
          }
        }
      }
    }

Nếu sort trực tiếp trên name, Elasticsearch có thể trả lỗi vì field text không hỗ trợ sort theo cách thông thường. Field text được phân tích thành token và không phù hợp cho thứ tự chuỗi nguyên vẹn.

Nên khai báo multi-field:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Sau đó dùng name.keyword để sort:

    Sort sort = Sort.by(
        Sort.Order.asc("name.keyword")
    );

Với entity Spring Data, tên property và tên field thực tế có thể được ánh xạ qua metadata. Nếu dùng field path thô trong native sort, hãy chỉ định đúng tên mapping thực tế.

### Keyword normalizer cho sort không phân biệt hoa thường

Keyword thường giữ nguyên chuỗi. Nếu cần thứ tự không phân biệt chữ hoa/chữ thường, có thể khai báo normalizer cho keyword field:

    PUT products
    {
      "settings": {
        "analysis": {
          "normalizer": {
            "lowercase_normalizer": {
              "type": "custom",
              "filter": [ "lowercase" ]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "sort": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer"
              }
            }
          }
        }
      }
    }

Sau đó sort theo name.sort. Normalizer được áp dụng khi index giá trị keyword và tạo thứ tự nhất quán hơn cho chuỗi khác nhau về chữ hoa/chữ thường.

Không nên giả định Sort.Order.ignoreCase() tự động thay thế việc thiết kế mapping. Với Elasticsearch, normalizer trên keyword field là cách rõ ràng để xác định semantics của sort.

## 11. Sort theo field được ánh xạ bằng @Field

Entity Java có thể dùng tên property khác tên field trong Elasticsearch:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(name = "created_at", type = FieldType.Date)
        private Instant createdAt;

        @Field(type = FieldType.Double)
        private Double price;
    }

Trong code Spring Data, thường nên dùng tên property của entity trong Sort:

    Sort sort = Sort.by(
        Sort.Order.desc("createdAt")
    );

Mapping metadata của Spring Data có thể chuyển property name thành tên field Elasticsearch tương ứng khi xử lý query. Với native sort hoặc request được xây dựng trực tiếp bằng Java API Client, cần dùng đúng field name ở Elasticsearch, trong ví dụ là created_at.

Điểm này cần được phân biệt khi dùng:

- Sort của Spring Data gắn với metadata entity.
- Sort option native của Elasticsearch Java API Client tham chiếu field trong mapping Elasticsearch.

Nếu sort không hoạt động như mong đợi, hãy kiểm tra request DSL cuối cùng và mapping thực tế thay vì chỉ nhìn tên property Java.

## 12. Sort theo score tìm kiếm

Với full-text search, Elasticsearch thường xếp hạng theo _score giảm dần khi không có sort khác. Nếu muốn thể hiện rõ relevance trong danh sách sort, có thể dùng field _score:

    Sort sort = Sort.by(
        Sort.Order.desc("_score")
    );

Nếu cần tie-breaker khi score bằng nhau:

    Sort sort = Sort.by(
        Sort.Order.desc("_score"),
        Sort.Order.asc("productId")
    );

productId ở đây nên là field keyword có doc values và giá trị duy nhất hoặc gần như duy nhất trong tập dữ liệu.

Sort theo field khác như price hoặc createdAt có thể thay đổi vai trò của relevance. Ví dụ sort giá tăng dần sẽ ưu tiên giá thấp dù document có score văn bản thấp hơn. Hãy quyết định rõ API đang cần:

- Relevance trước, field phụ chỉ dùng khi score bằng nhau.
- Field nghiệp vụ là thứ tự chính.
- Kết hợp score và field theo thứ tự cụ thể.

## 13. Missing values và giá trị null khi sort

Document có thể thiếu field dùng để sort. Elasticsearch cho phép cấu hình missing value trong sort option, ví dụ đặt giá trị thiếu ở đầu hoặc cuối danh sách.

REST API:

    GET products/_search
    {
      "sort": [
        {
          "price": {
            "order": "asc",
            "missing": "_last"
          }
        }
      ]
    }

Với cấu hình này, sản phẩm không có price được đặt cuối khi sắp xếp tăng dần.

Spring Data Sort.Order có metadata về null handling, nhưng cách chuyển đổi sang backend phụ thuộc implementation và phiên bản. Nếu yêu cầu missing phải chính xác, hãy kiểm tra hỗ trợ của Spring Data Elasticsearch hoặc sử dụng native SortOptions để khai báo missing rõ ràng.

Không nên coi giá trị thiếu là 0 nếu 0 mang ý nghĩa nghiệp vụ thực sự. Ví dụ sản phẩm thiếu giá không nên tự động đứng đầu khi sort giá tăng dần chỉ vì ứng dụng gán mặc định 0.

## 14. Sort theo nhiều giá trị trong một document

Một field có thể chứa nhiều giá trị, ví dụ:

    {
      "name": "Keyboard",
      "offers": [ 40.0, 45.0, 50.0 ]
    }

Khi sort trên field đa trị, Elasticsearch cần quy tắc chọn giá trị đại diện. Các mode phổ biến:

| Mode | Ý nghĩa |
|---|---|
| min | Dùng giá trị nhỏ nhất |
| max | Dùng giá trị lớn nhất |
| sum | Cộng các giá trị |
| avg | Lấy trung bình |
| median | Lấy trung vị |

Ví dụ sort theo giá offer thấp nhất:

    GET products/_search
    {
      "sort": [
        {
          "offers": {
            "order": "asc",
            "mode": "min"
          }
        }
      ]
    }

Với sort giảm dần, mode mặc định thường phụ thuộc hướng sort; nếu yêu cầu nghiệp vụ cụ thể, nên khai báo mode tường minh.

Sort mode cho multi-valued field không phải là cách tính tổng hợp nghiệp vụ tùy ý. Nếu giá trị đại diện cần có ý nghĩa khác, hãy lưu một field numeric đã được tính trước hoặc sử dụng script sort khi thực sự cần.

## 15. Nested sort

Khi dữ liệu dùng mapping nested, sort trên field bên trong nested object cần chỉ định nested path và có thể cần filter.

Ví dụ mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "offers": {
            "type": "nested",
            "properties": {
              "seller": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              }
            }
          }
        }
      }
    }

Sort theo giá thấp nhất trong offers:

    GET products/_search
    {
      "sort": [
        {
          "offers.price": {
            "order": "asc",
            "mode": "min",
            "nested": {
              "path": "offers"
            }
          }
        }
      ]
    }

Nếu chỉ muốn sort theo offer của một seller cụ thể, nested sort có thể có filter để chỉ lấy nested document thỏa điều kiện. Khi đó query sort phải khai báo đúng nested path và filter.

Spring Data Sort thông thường không biểu diễn đầy đủ mọi tùy chọn nested sort. Với nested sort, thường cần NativeQuery và SortOptions của Elasticsearch Java API Client hoặc API chuyên biệt mà phiên bản Spring Data cung cấp.

## 16. Dùng Pageable với ElasticsearchOperations

Không chỉ repository mới dùng Pageable. Khi service xây dựng NativeQuery, có thể gắn Pageable bằng withPageable:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("name")
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .withPageable(pageable)
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

withPageable truyền offset, size và sort của Pageable vào query. ElasticsearchOperations thực thi truy vấn và trả về SearchHits.

SearchHits chứa các hit và metadata như score, id và tổng số hit. Có thể lấy nội dung:

    List<Product> products = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

Nếu cần Page abstraction, Spring Data cung cấp các tiện ích chuyển SearchHits thành SearchPage trong những API phù hợp. Cần dùng đúng tiện ích và kiểu kết quả của phiên bản đang cài đặt; SearchHits không tự đồng nghĩa với Page.

## 17. Sort trong NativeQuery bằng Elasticsearch SortOptions

Spring Data Sort đủ cho phần lớn sort đơn giản. Khi cần các tùy chọn đặc thù như missing, nested path, mode, unmapped_type hoặc geo distance, có thể xây dựng native sort option bằng Elasticsearch Java API Client.

Ví dụ sort theo price và đặt field thiếu ở cuối:

    import co.elastic.clients.elasticsearch._types.SortOptions;
    import co.elastic.clients.elasticsearch._types.SortOrder;

    SortOptions priceSort = SortOptions.of(s -> s
        .field(f -> f
            .field("price")
            .order(SortOrder.Asc)
            .missing("_last")
        )
    );

Sau đó gắn vào NativeQuery bằng API sort tương ứng:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .withSort(priceSort)
        .withPageable(PageRequest.of(0, 20))
        .build();

Tên phương thức builder và overload có thể thay đổi theo phiên bản Spring Data Elasticsearch/Java API Client. Hãy xác nhận chữ ký trong dependency thực tế. Khi dùng native SortOptions, field name phải khớp với mapping Elasticsearch; không mặc định nó sẽ được chuyển từ property name qua metadata entity như Spring Data Sort.

Nếu vừa đặt sort trong Pageable vừa đặt native sort riêng, cần xác định thứ tự ưu tiên và hành vi của phiên bản API đang dùng. Tránh cấu hình hai danh sách sort khác nhau nếu không có chủ đích rõ ràng.

## 18. Sort và giới hạn phân trang sâu

Elasticsearch thường dùng from/size cho phân trang thông thường. Ví dụ:

    GET products/_search
    {
      "from": 100,
      "size": 20,
      "sort": [
        { "created_at": "desc" }
      ]
    }

from là số document bỏ qua, size là số document lấy về. Với PageRequest, Spring Data tính offset từ page number và page size rồi chuyển thành from/size.

Mặc định Elasticsearch giới hạn tổng cửa sổ kết quả có thể truy cập bằng from/size thông qua index.max_result_window, thường là 10.000. Nếu người dùng yêu cầu trang rất sâu, tăng page number có thể chạm giới hạn và gây chi phí bộ nhớ, CPU lớn.

Ví dụ:

    PageRequest.of(500, 20)

có offset 10.000. Đây là ranh giới mặc định thường gặp của result window.

Không nên tăng max_result_window vô hạn để giải quyết phân trang sâu. Elasticsearch cần giữ và xử lý các kết quả bị bỏ qua trên mỗi shard, nên chi phí tăng khi offset lớn.

### search_after cho phân trang sâu

search_after dùng giá trị sort của hit cuối cùng ở trang trước để lấy trang tiếp theo. Thay vì bỏ qua hàng nghìn document, request tiếp theo tiếp tục sau vị trí sort đã biết.

Ví dụ request đầu:

    GET products/_search
    {
      "size": 20,
      "sort": [
        { "created_at": "desc" },
        { "product_id": "asc" }
      ],
      "query": {
        "match": {
          "name": "keyboard"
        }
      }
    }

Giả sử hit cuối có sort values:

    "sort": [
      1794564000000,
      "p-1020"
    ]

Request tiếp theo truyền đúng các giá trị đó:

    GET products/_search
    {
      "size": 20,
      "sort": [
        { "created_at": "desc" },
        { "product_id": "asc" }
      ],
      "search_after": [
        1794564000000,
        "p-1020"
      ],
      "query": {
        "match": {
          "name": "keyboard"
        }
      }
    }

Giá trị trong search_after phải lấy từ mảng sort của hit cuối trang trước và giữ nguyên kiểu, thứ tự. Sort cần có tie-breaker ổn định để hai document không có cùng toàn bộ sort values.

### PIT kết hợp search_after

Nếu dữ liệu thay đổi trong khi người dùng duyệt nhiều trang, kết quả của trang sau có thể bị ảnh hưởng bởi insert/update/delete. Point in Time (PIT) giữ một góc nhìn nhất quán trong một khoảng thời gian và thường được kết hợp với search_after cho deep pagination.

Luồng khái quát:

1. Mở PIT trên index hoặc alias.
2. Gửi search đầu tiên với PIT, query và sort ổn định.
3. Lưu sort values của hit cuối.
4. Gửi request tiếp theo với cùng PIT và search_after.
5. Tiếp tục đến khi hết dữ liệu hoặc đóng PIT.

PIT giữ tài nguyên của cluster trong thời gian mở, vì vậy cần đặt keep_alive hợp lý và đóng PIT khi hoàn tất nếu API/client yêu cầu.

Pageable tiêu chuẩn chủ yếu mô tả offset và size. Nó không tự biểu diễn toàn bộ trạng thái cursor của search_after/PIT. Với phân trang sâu, cần dùng API Elasticsearch phù hợp hoặc thiết kế cursor riêng thay vì cố nhồi search_after vào page number.

## 19. Thứ tự ổn định và tie-breaker

Nếu nhiều document có cùng giá trị sort, Elasticsearch có thể trả chúng theo thứ tự nội bộ không được bảo đảm ổn định giữa các request. Điều này dễ tạo ra:

- Một document xuất hiện ở hai trang.
- Một document bị bỏ qua khi dữ liệu thay đổi.
- Thứ tự trang thay đổi giữa các lần gọi.

Giải pháp là thêm một field tie-breaker có giá trị duy nhất hoặc đủ phân biệt:

    Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("productId")
    );

productId cần có mapping keyword và doc values để sort hiệu quả. Không nên mặc định sort trực tiếp trên _id là lựa chọn tốt; field _id có các giới hạn riêng và không được thiết kế cho sort thông thường. Có thể lưu một bản sao định danh vào field keyword chuyên dùng cho sort.

Với search_after, tie-breaker càng quan trọng vì nó xác định chính xác vị trí tiếp tục.

## 20. Sort theo nhiều loại dữ liệu

### Giá và số lượng

Numeric field phù hợp với thứ tự số:

    Sort priceAscending =
        Sort.by(Sort.Order.asc("price"));

Đảm bảo mapping là integer, long, float, double hoặc kiểu số phù hợp. Nếu giá được lưu dưới dạng keyword, sort sẽ theo thứ tự chuỗi, ví dụ "100" có thể đứng trước "20", không phải thứ tự số.

### Ngày giờ

Date field hỗ trợ sắp xếp theo thời gian:

    Sort newestFirst =
        Sort.by(Sort.Order.desc("createdAt"));

Hãy lưu thời gian theo kiểu date và chuẩn hóa timezone. Nếu một index dùng date còn index khác dùng kiểu không tương thích, sort trên alias hoặc nhiều index có thể lỗi.

### Keyword

Keyword thích hợp cho mã, trạng thái hoặc tên đã chuẩn hóa:

    Sort alphabetical =
        Sort.by(Sort.Order.asc("name.keyword"));

Thứ tự chuỗi dựa trên giá trị keyword và quy tắc chuẩn hóa, không nhất thiết là thứ tự từ điển theo ngôn ngữ tự nhiên.

### Boolean

Boolean có thể dùng cho cờ như featured hoặc active. Tuy nhiên, nếu yêu cầu nghiệp vụ là nhóm true trước rồi sort theo field khác, hãy kiểm tra rõ thứ tự boolean và thêm các Order tiếp theo.

## 21. Kết hợp filter, query và sort

Sort chỉ quyết định thứ tự của document đã được query chọn. Nó không thay thế filter.

Ví dụ tìm sản phẩm đang hoạt động, thuộc category accessories, sắp xếp sản phẩm mới cập nhật trước:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query(keyword)
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("accessories"))
                    )
                )
            )
        )
        .withPageable(PageRequest.of(
            0,
            20,
            Sort.by(
                Sort.Order.desc("updatedAt"),
                Sort.Order.asc("productId")
            )
        ))
        .build();

Trong ví dụ:

- must tìm theo nội dung tên sản phẩm.
- filter giới hạn status và category.
- Sort ưu tiên updatedAt mới nhất.
- productId là tie-breaker.
- Pageable giới hạn 20 kết quả đầu tiên.

Nếu muốn relevance là tiêu chí chính, có thể sort theo _score giảm dần rồi mới đến updatedAt hoặc productId. Nếu sort updatedAt trước, document mới nhất có thể đứng trước document có score nội dung cao hơn.

## 22. Pageable trong API REST

Một API REST thường nhận page, size và sort từ query parameters:

    GET /api/products?page=0&size=20&sort=createdAt,desc

Spring MVC có thể tự bind Pageable nếu cấu hình Spring Data web support phù hợp. Tuy nhiên, với Elasticsearch, ứng dụng vẫn nên giới hạn page size và whitelist các field được phép sort.

Không nên cho client gửi bất kỳ tên field nào để sort:

    GET /api/products?sort=internal_score,desc

Nếu field không được phép công khai, việc cho client sort trên field đó có thể làm lộ tín hiệu nội bộ hoặc tạo truy vấn tốn kém. Hãy ánh xạ các lựa chọn sort công khai:

    switch (sortBy) {
        case "newest" ->
            Sort.by(Sort.Order.desc("createdAt"));
        case "price-low" ->
            Sort.by(Sort.Order.asc("price"));
        case "price-high" ->
            Sort.by(Sort.Order.desc("price"));
        case "name" ->
            Sort.by(Sort.Order.asc("name.keyword"));
        default ->
            Sort.by(Sort.Order.desc("createdAt"));
    }

Ví dụ là cách ánh xạ lựa chọn nghiệp vụ sang Sort. Tên field cần tương ứng mapping thực tế và các lựa chọn cần được kiểm soát.

## 23. Sort và phân trang khi dùng Page, Slice hoặc List

Các kiểu kết quả khác nhau cung cấp lượng metadata khác nhau:

| Kiểu trả về | Nội dung | Metadata tổng |
|---|---|---|
| Page<T> | Nội dung trang hiện tại | Có total elements/pages |
| Slice<T> | Nội dung và thông tin có trang tiếp | Không cần tổng số trang |
| List<T> | Danh sách kết quả giới hạn | Không có metadata trang |
| SearchHits<T> | Hit cùng score và metadata Elasticsearch | Có total hits theo response |

Page hữu ích khi giao diện cần tổng số trang. Slice phù hợp với nút Next/Load more khi không cần đếm toàn bộ kết quả. List phù hợp với một phần dữ liệu có giới hạn. SearchHits phù hợp khi cần score, highlight hoặc metadata chuyên biệt.

Khả năng hỗ trợ từng kiểu trả về tùy repository abstraction và phiên bản Spring Data Elasticsearch. Hãy chọn chữ ký method mà framework đang hỗ trợ, không giả định mọi kiểu của Spring Data JPA đều có semantics giống hệt trên Elasticsearch.

## 24. Hiệu năng và giới hạn của sort

Sort có chi phí vì Elasticsearch cần đọc giá trị field từ các document ứng viên và sắp xếp chúng. Một số nguyên tắc:

- Sort trên keyword/numeric/date có doc values thường phù hợp.
- Tránh sort trên field text đã phân tích.
- Giới hạn số lượng field sort.
- Tránh script sort nếu có thể lưu trước giá trị cần sort.
- Thu hẹp tập ứng viên bằng query/filter phù hợp.
- Dùng page size vừa phải.
- Tránh offset quá sâu.
- Dùng search_after/PIT khi cần duyệt tập dữ liệu lớn.
- Đảm bảo các index trong alias có mapping tương thích cho field sort.

Nếu một field chỉ dùng để sort, có thể cân nhắc mapping phù hợp và doc_values. Không tắt doc_values cho field cần sort hoặc aggregation.

### Sort trên field không tồn tại ở một số index

Nếu query qua alias trỏ đến nhiều index và field sort không tồn tại hoặc có kiểu khác nhau giữa các index, Elasticsearch có thể báo lỗi hoặc tạo kết quả không nhất quán.

Khi dùng nhiều index:

- Giữ mapping của field sort đồng nhất.
- Nếu cần, cấu hình unmapped_type trong native sort để xử lý index thiếu field.
- Kiểm tra field type giữa tất cả backing index.
- Tránh sort trên field có semantics khác nhau giữa các phiên bản index.

## 25. Kiểm thử sort và Pageable

Một test hữu ích nên xác minh cả thứ tự và phân trang, không chỉ xác minh có kết quả.

Ví dụ dữ liệu:

| ID | Price | CreatedAt |
|---|---:|---|
| p-1 | 100 | 2026-11-01 |
| p-2 | 50 | 2026-11-03 |
| p-3 | 75 | 2026-11-02 |

Sort price tăng dần phải cho thứ tự p-2, p-3, p-1.

Với page size 2:

- Trang 0 có p-2 và p-3.
- Trang 1 có p-1.

Test nên kiểm tra:

- Hướng ASC/DESC.
- Thứ tự ưu tiên khi có nhiều Order.
- Tie-breaker khi giá trị sort bằng nhau.
- Document thiếu field sort.
- Field mapping text/keyword đúng.
- Page number và size.
- Total elements/pages nếu dùng Page.
- Hành vi khi page vượt quá trang cuối.

Integration test với Elasticsearch thực tế giúp phát hiện lỗi mapping và lỗi sort DSL mà unit test mock repository không thể phát hiện.

## 26. Những lỗi thường gặp

### Sort trực tiếp trên field text

Field text được phân tích và thường không có doc values. Dùng keyword sub-field như name.keyword để sort chuỗi.

### Nhầm property Java với field mapping trong native sort

Spring Data Sort có thể dùng mapping metadata để chuyển property thành tên field. Native SortOptions tham chiếu tên field Elasticsearch trực tiếp. Kiểm tra mapping và request thực tế.

### Quên hướng sort

Sort.by("price") mặc định tăng dần. Nếu nghiệp vụ cần giá cao trước, phải chỉ định DESC.

### Đặt sai thứ tự nhiều Order

Order đầu tiên có ưu tiên cao nhất. Hãy sắp xếp các điều kiện theo thứ tự nghiệp vụ.

### Không thêm tie-breaker

Nhiều document có cùng giá trị sort có thể thay đổi thứ tự giữa các request. Thêm field duy nhất, ổn định và có thể sort.

### Dùng _id làm tie-breaker mặc định

_id có giới hạn riêng và không phải field sort thông thường được tối ưu cho use case này. Lưu thêm một field keyword có doc values để sort.

### Dùng Pageable cho deep pagination

PageRequest dùng offset/size và có thể chạm max_result_window. Dùng search_after cùng PIT cho việc duyệt sâu và cần tính nhất quán.

### Cho client sort tùy ý

Client có thể yêu cầu sort trên field nội bộ hoặc field tốn kém. Whitelist các sort option được API công khai.

### Nghĩ Sort thay thế filter

Sort chỉ đổi thứ tự. Document không đủ điều kiện phải được loại bằng query/filter hoặc authorization.

### Không đồng nhất mapping giữa các index

Alias nhiều index cần field sort có kiểu và semantics tương thích. Nếu mapping lệch, query có thể lỗi hoặc kết quả sai.

## 27. Quy trình chọn Sort và Pageable

Khi thiết kế endpoint tìm kiếm, có thể làm theo trình tự:

1. Xác định query và filter nào chọn tập document hợp lệ.
2. Xác định thứ tự nghiệp vụ: relevance, mới nhất, giá, tên hay mức ưu tiên.
3. Chọn field có mapping hỗ trợ sort.
4. Nếu cần sort chuỗi, dùng keyword hoặc keyword sub-field.
5. Tạo Sort với một hoặc nhiều Sort.Order theo đúng thứ tự ưu tiên.
6. Thêm tie-breaker ổn định nếu người dùng chuyển trang.
7. Tạo Pageable với page number và page size được giới hạn.
8. Truyền Pageable vào repository hoặc NativeQuery.
9. Chọn Page, Slice, List hoặc SearchHits theo metadata cần thiết.
10. Nếu offset sâu, chuyển sang search_after/PIT.
11. Kiểm tra request và mapping thực tế bằng integration test.

## Kết luận

Sort và Sort.Order mô tả thứ tự sắp xếp; Pageable kết hợp page number, page size, offset và sort. Trong Spring Data Elasticsearch, có thể truyền Pageable vào repository method hoặc gắn vào NativeQuery bằng withPageable. Sort nhiều field được áp dụng theo thứ tự Order, vì vậy field đầu tiên là tiêu chí ưu tiên chính.

Elasticsearch cần field mapping phù hợp để sort: keyword cho chuỗi, numeric cho số và date cho thời gian. Với field text, hãy dùng keyword sub-field; với nested sort hoặc missing-value rules đặc biệt, cân nhắc native SortOptions. Thêm tie-breaker ổn định để phân trang ít bị lặp hoặc bỏ sót, giới hạn page size và tránh offset sâu vượt max_result_window. Khi cần duyệt lượng dữ liệu lớn, search_after kết hợp PIT là lựa chọn phù hợp hơn Pageable offset thông thường.
