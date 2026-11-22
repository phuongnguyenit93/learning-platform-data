# Đọc Query DSL được sinh và tránh suy diễn từ hành vi JPA

Spring Data Elasticsearch cho phép khai báo truy vấn bằng tên phương thức repository, chẳng hạn findByStatus hoặc findByTitleAndCategory. Cú pháp này quen thuộc với người đã dùng Spring Data JPA, nhưng không có nghĩa Elasticsearch thực thi cùng một truy vấn SQL/JPQL hoặc giữ nguyên mọi ngữ nghĩa của JPA.

Tên phương thức là một mô tả ở mức repository. Spring Data phân tích tên đó, nhận diện thuộc tính và toán tử, rồi chuyển thành truy vấn phù hợp với store đang sử dụng. Với Elasticsearch, kết quả cuối cùng là một truy vấn theo Elasticsearch Query DSL, chịu ảnh hưởng bởi mapping, analyzer, kiểu field và khả năng của Elasticsearch.

Vì vậy, khi đọc một derived query method, cần trả lời ba câu hỏi:

1. Spring Data đã phân tích tên phương thức thành những điều kiện nào?
2. Những điều kiện đó được chuyển thành Query DSL nào trong phiên bản Spring Data Elasticsearch đang chạy?
3. Mapping và analyzer của index khiến Query DSL đó khớp document ra sao?

Không nên suy diễn từ tên method rằng truy vấn sẽ có đúng semantics như một method tương tự trong JPA. Khi hành vi quan trọng với nghiệp vụ, hãy xem Query DSL thực tế và kiểm tra trên Elasticsearch.

## 1. Tên phương thức repository được phân tích như thế nào?

Một derived query method thường có hai phần:

    findByTitleAndStatusOrderByCreatedAtDesc
    |      |                         |
    |      |                         +-- phần sắp xếp
    |      +-- predicate bắt đầu sau By
    +-- subject / mục đích truy vấn

Phần subject cho biết loại thao tác repository, ví dụ tìm kiếm, đếm hoặc kiểm tra tồn tại. Phần predicate sau By mô tả các điều kiện theo tên thuộc tính và các keyword như And, Or, GreaterThan hoặc In. OrderBy có thể mô tả thứ tự sắp xếp.

Ví dụ:

    List<Product> findByCategoryAndActive(
        String category,
        boolean active
    );

Spring Data phân tích điều kiện thành:

- category phải khớp với tham số thứ nhất.
- active phải khớp với tham số thứ hai.
- Hai điều kiện được kết hợp theo AND.

Tên thuộc tính phải khớp với property của entity theo quy tắc phân tích tên của Spring Data. Nếu tên field trong Elasticsearch khác tên property Java, mapping metadata như @Field(name = ...) sẽ quyết định tên field thực tế được sử dụng khi chuyển query.

Ví dụ:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(name = "product_name", type = FieldType.Text)
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;

        @Field(type = FieldType.Boolean)
        private boolean active;
    }

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategoryAndActive(
            String category,
            boolean active
        );
    }

Method sử dụng property category và active. Field category được ánh xạ cùng tên; property name được ánh xạ đến product_name khi framework tạo truy vấn hoặc chuyển đổi document.

Tên method không chứa Query DSL tường minh. Muốn biết chính xác nó tạo term, match, range, wildcard hay cấu trúc bool nào, phải dựa vào quy tắc của phiên bản Spring Data Elasticsearch và kiểu property được ánh xạ.

## 2. Cú pháp giống JPA không có nghĩa semantics giống JPA

Spring Data có một cơ chế chung để phân tích tên phương thức, nhưng từng module dữ liệu có query creator riêng. JPA tạo truy vấn theo mô hình entity quan hệ và chuyển thành JPQL/SQL. Elasticsearch tạo truy vấn theo document, inverted index, mapping và Query DSL.

| Khía cạnh | Spring Data JPA | Spring Data Elasticsearch |
|---|---|---|
| Mô hình dữ liệu | Entity và quan hệ trong database quan hệ | Document và field trong index |
| Ngôn ngữ truy vấn bên dưới | JPQL/SQL | Elasticsearch Query DSL |
| So khớp văn bản | SQL predicate, LIKE, collation hoặc full-text tùy database | Analyzer, term, match, phrase, wildcard và các query khác |
| Quan hệ | Join, foreign key, fetch strategy | Document lồng nhau, nested query, denormalization hoặc truy vấn nhiều bước |
| NULL / thiếu field | SQL NULL và ba giá trị logic | Field có thể thiếu, có null, hoặc được xử lý qua null_value mapping |
| Transaction | Có thể tham gia transaction ACID của database | Không có transaction nhiều document tương đương JPA |
| Sắp xếp | Theo cột SQL | Theo field có khả năng sort, thường cần keyword/numeric/date hoặc doc values |

Một method như findByNameContaining có thể gợi nhớ đến LIKE '%value%' của SQL. Tuy nhiên, không được mặc định nó có cùng hành vi trên Elasticsearch. Cách tạo query phụ thuộc keyword được hỗ trợ, kiểu field và implementation của module. Một truy vấn wildcard trên chuỗi đã phân tích khác với một SQL LIKE trên giá trị cột.

Tương tự, IgnoreCase không tự bảo đảm mọi kiểu field đều được so khớp không phân biệt hoa thường. Trên Elasticsearch, kết quả còn phụ thuộc analyzer, normalizer hoặc khả năng case-insensitive của query được tạo.

Quy tắc an toàn là coi tên method là cú pháp khai báo của Spring Data, còn Query DSL và mapping mới quyết định hành vi tìm kiếm thực tế.

## 3. Những keyword phổ biến và cách suy nghĩ về chúng

Spring Data Elasticsearch hỗ trợ một tập keyword cho derived query methods. Tập hỗ trợ và cách ánh xạ có thể thay đổi theo phiên bản; cần kiểm tra tài liệu của dependency đang dùng trước khi dựa vào một keyword cụ thể.

Một số nhóm cú pháp thường gặp:

| Nhóm | Ví dụ tên method | Ý nghĩa ở mức repository |
|---|---|---|
| So khớp thuộc tính | findByStatus | Tìm theo status |
| Kết hợp điều kiện | findByStatusAndCategory | Cả hai điều kiện phải thỏa |
| Lựa chọn điều kiện | findByStatusOrCategory | Một trong các điều kiện thỏa theo query được sinh |
| So sánh số/ngày | findByPriceGreaterThan | So sánh lớn hơn |
| Khoảng giá trị | findByCreatedAtBetween | Tìm trong một khoảng |
| Tập giá trị | findByCategoryIn | Giá trị thuộc một tập |
| Giá trị đúng/sai | findByActiveTrue | Field có giá trị true |
| Kiểm tra rỗng | findByDescriptionIsNull | Điều kiện liên quan đến field không có giá trị |
| Giới hạn kết quả | findTop10ByStatus | Giới hạn số kết quả |
| Sắp xếp | findByStatusOrderByCreatedAtDesc | Sắp xếp theo field |

Đây là mô tả ý định của method. Không nên coi bảng này là bảng ánh xạ cố định từ keyword sang một loại Query DSL duy nhất cho mọi phiên bản.

### And và Or

Ví dụ:

    List<Product> findByCategoryAndActive(
        String category,
        boolean active
    );

Ý định là cả category và active phải thỏa. Trong Query DSL, điều kiện AND thường được biểu diễn bằng bool query với các clause bắt buộc, chẳng hạn must hoặc filter, tùy loại query được tạo.

Method OR:

    List<Product> findByCategoryOrBrand(
        String category,
        String brand
    );

Ý định là category hoặc brand khớp. Trong Query DSL, OR thường được biểu diễn bằng bool should và minimum_should_match phù hợp. Cần kiểm tra query thực tế nếu điều kiện OR lồng với AND hoặc có nhiều nhóm điều kiện, vì cách nhóm biểu thức ảnh hưởng kết quả.

### GreaterThan, LessThan và Between

Các keyword so sánh thường được dùng cho field số hoặc ngày:

    List<Product> findByPriceGreaterThan(double price);

    List<Product> findByCreatedAtBetween(
        Instant from,
        Instant to
    );

Ở Elasticsearch, truy vấn khoảng thường được biểu diễn bằng range query. Kiểu mapping của field cần phù hợp với phép so sánh. Nếu price bị mapping thành keyword, query số không thể hoạt động như mong muốn.

### In

Method:

    List<Product> findByCategoryIn(Collection<String> categories);

diễn đạt việc category nằm trong một tập giá trị. Query DSL có thể sử dụng truy vấn kiểu terms cho field phù hợp. Field category thường được mapping keyword để so khớp các giá trị phân loại chính xác.

### Top và First

Method:

    List<Product> findTop5ByActiveTrueOrderByCreatedAtDesc();

diễn đạt việc giới hạn số lượng kết quả và sắp xếp theo thời gian giảm dần. Đây là giới hạn kết quả ở tầng truy vấn; không nên nhầm nó với việc Elasticsearch chỉ đọc đúng năm document trong mọi giai đoạn thực thi.

## 4. Mapping quyết định ý nghĩa của truy vấn

Elasticsearch không lưu mọi chuỗi theo cùng một cách. Một field text thường được phân tích thành token; field keyword giữ giá trị phù hợp cho so khớp chính xác, sort và aggregation.

Ví dụ mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "raw": {
                "type": "keyword"
              }
            }
          },
          "category": {
            "type": "keyword"
          },
          "price": {
            "type": "double"
          },
          "active": {
            "type": "boolean"
          }
        }
      }
    }

Với mapping này:

- name phục vụ tìm kiếm văn bản đã phân tích.
- name.raw phục vụ so khớp chính xác, sort hoặc aggregation theo toàn bộ tên.
- category phù hợp với filter theo giá trị chính xác.
- price phù hợp với range query.
- active phù hợp với điều kiện boolean.

Nếu method findByName("Spring Data") được chuyển thành term query trên field name, kết quả có thể khác với match query. Field text được analyzer tách thành các term như spring và data; term query không tự phân tích chuỗi đầu vào như match query.

Đó là lý do không thể chỉ nhìn method name rồi kết luận rằng nó là tìm kiếm toàn văn.

## 5. Term query và match query không giống nhau

Đây là một trong những điểm quan trọng nhất khi đọc Query DSL.

### Term query

Term query tìm một term chính xác trong inverted index. Nó không chạy analyzer trên chuỗi query như match query.

Ví dụ:

    GET products/_search
    {
      "query": {
        "term": {
          "category": "keyboard"
        }
      }
    }

Đây là cách phù hợp với field keyword có giá trị keyboard.

Nếu dùng term query trên field text, cần biết analyzer đã biến đổi nội dung như thế nào. Ví dụ document chứa Spring Data có thể được index thành các token spring và data. Term query với chuỗi nguyên văn Spring Data không nhất thiết khớp.

### Match query

Match query phân tích chuỗi truy vấn bằng search analyzer của field, sau đó tìm các term phù hợp:

    GET products/_search
    {
      "query": {
        "match": {
          "name": "Spring Data"
        }
      }
    }

Đây thường là lựa chọn tự nhiên cho tìm kiếm toàn văn trên field text.

### Không suy diễn match chỉ từ tên findBy

Method:

    List<Product> findByName(String name);

không tự nói cho người đọc biết chắc nó sẽ tạo match query. Nếu nghiệp vụ yêu cầu full-text search, hãy dùng một API có ngữ nghĩa match rõ ràng, chẳng hạn @Query với Query DSL, NativeQuery qua ElasticsearchOperations hoặc Java API Client trực tiếp.

Ví dụ @Query:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
        List<Product> searchName(String text);
    }

Query DSL trong annotation thể hiện rõ loại query. Cú pháp placeholder và cách serialize tham số cần theo phiên bản Spring Data Elasticsearch đang dùng.

## 6. Contains, StartingWith và Like không phải SQL LIKE một cách tự động

Các keyword như Containing, StartingWith và Like dễ khiến người dùng liên tưởng đến SQL LIKE. Trên Elasticsearch, chúng có thể được ánh xạ thành các truy vấn phù hợp với khả năng của module, chẳng hạn wildcard/prefix hoặc một dạng truy vấn khác theo phiên bản.

Điều cần chú ý:

- Wildcard query trên keyword field tìm theo mẫu của giá trị đã index.
- Prefix query tìm các term bắt đầu bằng một chuỗi.
- Match query tìm theo token đã phân tích, không tương đương substring.
- N-gram hoặc edge n-gram có thể tạo khả năng tìm một phần chuỗi, nhưng cần analyzer được cấu hình từ lúc index.

Ví dụ prefix query:

    GET products/_search
    {
      "query": {
        "prefix": {
          "name.raw": "key"
        }
      }
    }

Ví dụ wildcard query:

    GET products/_search
    {
      "query": {
        "wildcard": {
          "name.raw": {
            "value": "*board*"
          }
        }
      }
    }

Wildcard có ký tự * ở đầu thường tốn kém hơn vì có thể phải xem xét nhiều term. Không nên dùng một method chứa từ Containing rồi giả định nó luôn là cách hiệu quả để làm substring search trên dữ liệu lớn.

Nếu chức năng cần autocomplete, hãy cân nhắc edge n-gram hoặc search_as_you_type. Nếu cần substring search, cân nhắc n-gram và đánh giá kích thước index. Hãy chọn mapping và query theo yêu cầu thực tế thay vì dựa vào tên method giống SQL.

## 7. Null, field thiếu và IsNull

Trong JPA, SQL NULL có ngữ nghĩa quen thuộc với người dùng database quan hệ. Trong Elasticsearch, cần phân biệt:

- Document không có field.
- Document có field với giá trị null.
- Document có field chứa giá trị rỗng như chuỗi "".
- Mapping có khai báo null_value cho một số kiểu field.

Elasticsearch exists query kiểm tra field có giá trị được index hay không:

    GET products/_search
    {
      "query": {
        "exists": {
          "field": "description"
        }
      }
    }

Document không có giá trị được index cho field description sẽ không khớp exists. Giá trị null thông thường cũng không được xem là giá trị tồn tại, trừ khi mapping dùng null_value theo cách phù hợp.

Vì vậy, không nên chuyển suy nghĩ SQL IS NULL sang Elasticsearch mà không xem mapping. Method IsNull hoặc IsNotNull, nếu được phiên bản hỗ trợ, cần được kiểm tra xem nó tạo exists/negation hay một dạng query nào khác.

Chuỗi rỗng không đồng nghĩa với null. Nếu ứng dụng cần phân biệt chưa nhập mô tả và mô tả là chuỗi rỗng, hãy định nghĩa rõ cách lưu và query.

## 8. Quan hệ entity JPA không chuyển nguyên vẹn sang document Elasticsearch

Trong JPA, một method truy vấn có thể đi qua quan hệ entity hoặc tạo join dựa trên mapping quan hệ:

    findByCustomer_Address_City(...)

Không nên mặc định rằng một đường dẫn property tương tự trong Spring Data Elasticsearch sẽ tạo SQL join tương đương.

Elasticsearch lưu document theo cấu trúc JSON. Dữ liệu liên quan có thể được:

- Denormalize và sao chép vào cùng document.
- Lưu trong object field.
- Lưu trong nested field khi cần bảo toàn mối quan hệ giữa các phần tử trong mảng object.
- Lưu ở document riêng và truy vấn theo nhiều bước ở tầng ứng dụng.

### Object và nested khác nhau

Ví dụ một đơn hàng có nhiều dòng hàng:

    {
      "order_id": "o-101",
      "items": [
        { "sku": "A", "color": "red" },
        { "sku": "B", "color": "blue" }
      ]
    }

Nếu items được mapping là object thông thường, Elasticsearch có thể làm phẳng các giá trị của mảng object. Một query tìm sku=A và color=blue có thể khớp theo các giá trị thuộc những phần tử khác nhau nếu không dùng nested semantics.

Nếu cần giữ quan hệ giữa sku và color trong cùng một phần tử, field items cần mapping nested và truy vấn phải dùng nested query:

    GET orders/_search
    {
      "query": {
        "nested": {
          "path": "items",
          "query": {
            "bool": {
              "must": [
                { "term": { "items.sku": "A" } },
                { "term": { "items.color": "red" } }
              ]
            }
          }
        }
      }
    }

Không phải mọi derived query method đều diễn đạt được nested query phức tạp này. Khi truy vấn phụ thuộc nested semantics, hãy dùng API truy vấn tường minh và kiểm tra mapping nested.

## 9. Pageable, Sort và thứ tự kết quả

Spring Data repository có thể nhận Pageable hoặc Sort:

    Page<Product> findByCategory(
        String category,
        Pageable pageable
    );

Ví dụ gọi:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "price")
    );

    Page<Product> page =
        productRepository.findByCategory("keyboard", pageable);

Spring Data chuyển yêu cầu phân trang và sắp xếp thành các tùy chọn truy vấn Elasticsearch. Tuy nhiên, field được dùng sort phải có mapping phù hợp.

Text field thường không phù hợp để sort trực tiếp vì fielddata thường tắt mặc định. Với tên sản phẩm, có thể sort qua sub-field keyword:

    Sort.by(Sort.Direction.ASC, "name.raw")

Field numeric, date và keyword thường phù hợp cho sort. Hãy kiểm tra tên field thực tế sau khi áp dụng mapping metadata.

### Page và tổng số kết quả

Page thường cần thông tin tổng số kết quả, trong khi Slice hoặc một cấu trúc chỉ chứa nội dung trang có thể cần ít thông tin hơn. Elasticsearch có giới hạn và cơ chế riêng về total hits; việc đếm chính xác mọi kết quả có thể có chi phí.

Không nên giả định Page trong Spring Data Elasticsearch có cùng chi phí và semantics với một câu lệnh SQL count(*) trên database quan hệ. Kiểm tra query request, total hits tracking và cách framework lấy số lượng kết quả trong phiên bản đang sử dụng.

Với tập dữ liệu lớn và phân trang sâu, from/size có thể trở nên tốn kém. Hãy xem xét search_after cùng sort ổn định hoặc chiến lược pagination phù hợp.

## 10. Đọc Query DSL thực tế được sinh ra

Khi một method có kết quả bất ngờ, cách đáng tin cậy là kiểm tra request thực tế gửi đến Elasticsearch.

Ví dụ method:

    List<Product> findByCategoryAndActive(
        String category,
        boolean active
    );

Một Query DSL tương đương về ý định có thể là:

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "category": "keyboard"
              }
            },
            {
              "term": {
                "active": true
              }
            }
          ]
        }
      }
    }

Đây là ví dụ minh họa cách một truy vấn filter có thể được biểu diễn, không phải lời khẳng định rằng mọi phiên bản Spring Data sẽ sinh chính xác JSON này cho method trên. Query creator, kiểu property và API được gọi có thể dẫn đến cấu trúc khác.

Để đọc request:

1. Xác định repository method và tham số thực tế.
2. Xác định entity property tương ứng và tên field sau mapping.
3. Kiểm tra mapping của field trong index.
4. Bật logging hoặc tracing request ở mức phù hợp với phiên bản Spring Data/client.
5. Lấy Query DSL thực tế và đọc từng clause.
6. Dùng Analyze API nếu truy vấn liên quan đến text analyzer.
7. Dùng Explain API để hiểu vì sao một document khớp hoặc được xếp hạng.

Tên logger và cách bật wire logging phụ thuộc phiên bản client và transport. Hãy tham khảo cấu hình logging của đúng dependency thay vì sao chép tên logger từ một phiên bản cũ. Wire logging có thể ghi cả query body và dữ liệu nhạy cảm; chỉ bật trong môi trường kiểm thử hoặc trong khoảng thời gian được kiểm soát.

### Validate và explain query

Có thể kiểm tra query bằng Validate API:

    GET products/_validate/query?explain=true
    {
      "query": {
        "match": {
          "name": "Spring Data"
        }
      }
    }

Explain API cho một document cụ thể:

    GET products/_explain/p-101
    {
      "query": {
        "match": {
          "name": "Spring Data"
        }
      }
    }

Profile API có thể giúp phân tích chi phí thực thi query, nhưng tạo thêm overhead. Chỉ bật khi điều tra hiệu năng.

## 11. Khi nào nên dùng @Query hoặc NativeQuery?

Derived query phù hợp khi điều kiện đơn giản, tên method dễ đọc và query được sinh ra đúng với ý định.

Khi truy vấn cần thể hiện rõ Elasticsearch semantics, hãy cân nhắc:

- @Query với JSON Query DSL cho một truy vấn repository cố định.
- NativeQuery qua ElasticsearchOperations khi cần xây dựng query linh hoạt bằng Java API Client query types.
- Elasticsearch Java Client trực tiếp khi cần kiểm soát request/response hoặc dùng API chưa được abstraction Spring Data cung cấp thuận tiện.

Ví dụ @Query cho full-text search:

    @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
    List<Product> searchByNameText(String text);

Ví dụ NativeQuery:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("Spring Data")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("keyboard"))
                    )
                )
            )
        )
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

Truy vấn này thể hiện rõ:

- name dùng match query trong query context để tìm văn bản.
- category dùng term trong filter context để giới hạn danh mục.
- SearchHits giữ thông tin kết quả tìm kiếm cùng metadata của hit.

NativeQuery phù hợp khi cần kết hợp nhiều query clause, nested query, aggregation, highlighting hoặc các tùy chọn Elasticsearch khác mà derived method khó biểu diễn.

## 12. Ví dụ từ yêu cầu nghiệp vụ đến Query DSL

Giả sử trang danh sách sản phẩm cần:

- Chỉ lấy sản phẩm đang hoạt động.
- Chỉ lấy danh mục keyboard.
- Tìm nội dung tên phù hợp với từ khóa spring.
- Sản phẩm có giá từ 20 đến 200.
- Ưu tiên sản phẩm có tên khớp tốt hơn.
- Sắp xếp kết quả theo điểm liên quan.

Một derived method có thể diễn đạt phần điều kiện đơn giản:

    findByCategoryAndActiveAndPriceBetween(...)

Nhưng method này không nói rõ rằng name cần match query toàn văn và xếp hạng theo relevance score. Có thể tách truy vấn sang NativeQuery:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("spring")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("keyboard"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("active")
                        .value(FieldValue.of(true))
                    )
                )
                .filter(f -> f
                    .range(r -> r
                        .number(n -> n
                            .field("price")
                            .gte(20.0)
                            .lte(200.0)
                        )
                    )
                )
            )
        )
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

Ở đây, các điều kiện nghiệp vụ được chia theo vai trò:

- match name tìm nội dung và có thể đóng góp điểm liên quan.
- term category kiểm tra giá trị phân loại chính xác.
- term active kiểm tra trạng thái boolean.
- range price giới hạn khoảng giá.

Query DSL cho thấy rõ field nào cần analyzer và field nào cần mapping keyword/numeric/boolean. Điều này giúp tránh kỳ vọng rằng một tên method tự động hiểu được ý nghĩa tìm kiếm của nghiệp vụ.

## 13. Kiểm thử derived query đúng cách

Unit test chỉ kiểm tra tên method hoặc mock repository không chứng minh Query DSL hoạt động đúng với mapping thật. Các lỗi liên quan analyzer, field type, nested mapping hoặc sort thường chỉ xuất hiện khi truy vấn Elasticsearch thực tế.

Một integration test nên:

1. Khởi tạo Elasticsearch test instance có phiên bản tương thích với dependency của ứng dụng.
2. Tạo index và mapping giống cấu hình môi trường.
3. Index dữ liệu có cả trường hợp khớp và không khớp.
4. Gọi repository method.
5. Kiểm tra tập document trả về, thứ tự và số lượng.
6. Nếu cần, kiểm tra query DSL được sinh hoặc dùng Explain API để hiểu kết quả.

Ví dụ dữ liệu test:

| ID | name | category | active | price |
|---|---|---|---|---:|
| p1 | Spring Keyboard | keyboard | true | 80 |
| p2 | Spring Mouse | mouse | true | 25 |
| p3 | Mechanical Keyboard | keyboard | false | 100 |

Với method findByCategoryAndActive("keyboard", true), kết quả mong đợi chỉ có p1. Nhưng để bảo đảm test có ý nghĩa, mapping category phải là keyword và active phải là boolean như trong môi trường thật.

Với full-text search trên name, hãy kiểm tra analyzer. Ví dụ match query cho spring có thể khớp Spring Keyboard; term query trên chuỗi nguyên văn spring không có cùng semantics.

## 14. Những suy diễn JPA thường gây lỗi trong Elasticsearch

### Nghĩ Containing luôn tương đương LIKE '%value%'

SQL LIKE và query trên inverted index là hai cơ chế khác nhau. Kiểm tra Query DSL thực tế và cân nhắc wildcard hoặc n-gram tùy yêu cầu.

### Nghĩ findByName luôn là full-text search

Method name không đủ để kết luận query là match. Kiểm tra loại query được sinh và mapping của name. Nếu cần full-text, thể hiện match rõ ràng.

### Nghĩ IgnoreCase luôn xử lý được mọi kiểu field

Case sensitivity phụ thuộc analyzer, normalizer hoặc query option. Keyword field không tự động giống collation không phân biệt hoa thường trong database quan hệ.

### Nghĩ property traversal luôn tạo join

Elasticsearch không có join SQL tổng quát như JPA. Cần hiểu object/nested mapping hoặc denormalize dữ liệu.

### Nghĩ IsNull giống SQL NULL

Field thiếu, null, chuỗi rỗng và null_value có semantics khác nhau. Dùng exists query và kiểm tra mapping.

### Nghĩ Sort theo text luôn hoạt động

Text field thường không dùng trực tiếp cho sort. Dùng keyword sub-field hoặc kiểu dữ liệu có doc values phù hợp.

### Nghĩ Page có chi phí như SQL pagination

Elasticsearch có giới hạn from/size và chi phí total hits riêng. Phân trang sâu có thể cần search_after.

### Nghĩ @Transactional rollback được nhiều document

Elasticsearch không cung cấp transaction nhiều document giống JPA. Bulk request có thể partial success và cần xử lý item-level.

## Kết luận

Derived query method của Spring Data Elasticsearch giúp khai báo truy vấn ngắn gọn, nhưng tên method chỉ là đầu vào cho query creator của module. Query DSL thực tế, mapping và analyzer của index mới quyết định document nào khớp, cách so sánh giá trị và thứ tự kết quả.

Đừng suy diễn rằng findByName tương đương full-text match, Containing luôn tương đương SQL LIKE, IgnoreCase luôn bỏ qua hoa thường hoặc property traversal sẽ tạo join như JPA. Với điều kiện đơn giản, derived query có thể đủ. Với full-text, nested, wildcard, scoring hoặc aggregation, hãy dùng @Query, NativeQuery hoặc Elasticsearch Java Client để thể hiện Query DSL rõ ràng. Khi hành vi quan trọng, hãy đọc request thực tế và kiểm thử trên mapping Elasticsearch thật.
