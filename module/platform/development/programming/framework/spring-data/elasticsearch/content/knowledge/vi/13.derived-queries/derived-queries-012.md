# Khi tên phương thức quá dài hoặc không còn rõ nghĩa

Spring Data Elasticsearch hỗ trợ query derivation: chỉ cần đặt tên phương thức repository theo quy ước, Spring Data phân tích tên và tạo truy vấn Elasticsearch. Cách này rất tiện với điều kiện đơn giản như tìm theo mã, trạng thái, khoảng giá hoặc kết hợp vài thuộc tính.

Tuy nhiên, khi tên phương thức kéo dài với nhiều điều kiện `And`/`Or`, nhiều nhánh logic, lọc tùy chọn hoặc yêu cầu về scoring, nested query và aggregation, tên method có thể trở nên khó đọc và khó thay đổi. Đây là lúc nên chuyển sang `@Query`, `ElasticsearchOperations` hoặc custom repository fragment. Mục tiêu là để tên method thể hiện ý định nghiệp vụ, còn cấu trúc truy vấn được đặt ở nơi phù hợp với độ phức tạp của nó.

## 1. Query derivation phù hợp với truy vấn đơn giản

Một phương thức dẫn xuất thường có dạng `findBy<Property><Operator>`. Spring Data đọc tên property và keyword để xây dựng query.

Ví dụ document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    // Constructors, getters and setters
}
```

Với các điều kiện phổ biến, tên phương thức ngắn và rõ:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    List<ProductDocument> findByStatusAndAvailableTrue(String status);

    List<ProductDocument> findByCategoryIdAndPriceMinorUnitsBetween(
            String categoryId,
            Long minPrice,
            Long maxPrice);
}
```

Những method này dễ đọc vì mỗi method diễn đạt một mục đích cụ thể và có ít điều kiện. Query derivation phù hợp khi:

- Điều kiện chủ yếu là so khớp, range, tồn tại, Boolean hoặc các keyword được Spring Data hỗ trợ.
- Số lượng điều kiện ít và có thể hiểu trực tiếp từ tên method.
- Logic kết hợp AND/OR không cần nhóm ngoặc phức tạp.
- Truy vấn không cần nhiều nhánh động, scoring tùy chỉnh hoặc cấu trúc Query DSL đặc biệt.

Tên method dài tự nó không làm Elasticsearch chạy chậm hơn. Vấn đề chính là khả năng đọc, kiểm tra logic, sửa đổi và kiểm thử của mã nguồn. Hiệu năng thực tế phụ thuộc query được gửi, mapping, dữ liệu, shard và cách Elasticsearch thực thi.

## 2. Dấu hiệu cho thấy tên phương thức đã quá dài

Ví dụ một method có thể bắt đầu như sau:

```java
List<ProductDocument>
findByStatusAndCategoryIdAndAvailableTrueAndPriceMinorUnitsBetweenAndCreatedAtAfterAndBrandIdIn(
        String status,
        String categoryId,
        Long minPrice,
        Long maxPrice,
        Instant createdAfter,
        Collection<String> brandIds);
```

Tên method này mô tả rất nhiều chi tiết kỹ thuật. Người đọc phải lần lượt giải mã từng property và toán tử để hiểu mục đích nghiệp vụ. Nếu sau đó thêm `Or`, phủ định hoặc một điều kiện tùy chọn, method còn khó đọc hơn.

Một số dấu hiệu nên cân nhắc cách viết khác:

1. Tên method chiếm nhiều dòng và khó đọc ngay cả khi format xuống dòng.
2. Method chứa nhiều nhóm `And` và `Or`, người đọc phải tự đặt ngoặc để hiểu logic.
3. Một số tham số chỉ được dùng khi có giá trị, khiến nhiều method gần giống nhau xuất hiện.
4. Truy vấn cần `bool`, `nested`, `minimum_should_match`, boost hoặc sort tùy chỉnh.
5. Tên method mô tả chi tiết Query DSL hơn là mục đích nghiệp vụ.
6. Mỗi thay đổi bộ lọc nhỏ lại buộc phải sửa một method có tên rất dài hoặc thêm nhiều overload.
7. Truy vấn cần aggregation, highlight, source filtering hoặc thông tin score.

Không có giới hạn ký tự cố định mà cứ vượt qua là phải chuyển khỏi query derivation. Hãy dùng khả năng đọc và độ ổn định của logic làm tiêu chí. Một method có tên tương đối dài nhưng vẫn diễn đạt một điều kiện rõ ràng có thể chấp nhận được; một method ngắn nhưng nhóm OR khó hiểu thì vẫn nên thay thế.

## 3. Tên dài có thể che giấu lỗi logic AND/OR

Khi kết hợp `And` và `Or`, cách parser nhóm các phần có ảnh hưởng trực tiếp tới kết quả. Ví dụ:

```java
findByStatusAndCategoryIdOrAvailableTrue(...)
```

Thường được hiểu theo nhóm:

```text
(status = ?0 AND categoryId = ?1)
OR available = true
```

Nó không có nghĩa:

```text
status = ?0
AND (categoryId = ?1 OR available = true)
```

Nếu ý định nghiệp vụ là `status = PUBLISHED AND (categoryId = coffee OR categoryId = tea)`, một method dài có thể không biểu đạt nhóm ngoặc theo cách người đọc mong đợi. Truy vấn tường minh giúp nhìn thấy cấu trúc bool và `minimum_should_match` ngay tại nơi định nghĩa.

Trước khi chuyển đổi một method, hãy viết biểu thức logic của nó bằng ngoặc. Đây là cách giữ nguyên hành vi khi chuyển từ derived query sang `@Query` hoặc custom repository.

## 4. Cách thứ nhất: đặt tên method theo mục đích nghiệp vụ

Đôi khi có thể làm tên method dễ hiểu hơn mà chưa cần chuyển sang query tùy chỉnh. Thay vì để method chỉ liệt kê mọi thuộc tính, hãy đặt tên theo mục đích của truy vấn khi điều đó vẫn phù hợp với quy ước repository.

Ví dụ:

```java
List<ProductDocument> findPublishedProductsByCategoryId(String categoryId);

List<ProductDocument> findAvailableProductsByCategoryId(String categoryId);
```

Phần mô tả trước `By` có thể giúp method dễ hiểu hơn, nhưng các điều kiện sau `By` vẫn phải tuân theo query derivation. Không thể tùy ý viết một câu mô tả nghiệp vụ ở đầu tên method rồi mong Spring Data suy luận mọi logic còn lại.

Nếu hai method có cùng một bộ lọc cơ bản, có thể tách phần dùng chung thành method service hoặc repository helper. Tuy nhiên, không nên tạo nhiều lớp wrapper chỉ để che một query quá phức tạp; khi logic đã nhiều nhánh, hãy biểu diễn nó rõ ràng bằng query tùy chỉnh.

## 5. Cách thứ hai: dùng `@Query` cho truy vấn tĩnh

`@Query` cho phép khai báo trực tiếp Elasticsearch Query DSL trên phương thức repository. Cách này phù hợp khi:

- Cấu trúc query tương đối cố định.
- Điều kiện có nhóm ngoặc rõ ràng mà tên method khó biểu đạt.
- Cần dùng `bool`, `nested`, `minimum_should_match`, boost hoặc các tùy chọn Query DSL.
- Query đủ ngắn để JSON có thể đọc và bảo trì ngay trong annotation.

Ví dụ cần tìm sản phẩm đang hiển thị và thuộc một trong hai trạng thái, đồng thời phải có danh mục được yêu cầu:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
    {
      "bool": {
        "filter": [
          { "term": { "categoryId": "?0" } },
          { "term": { "available": true } },
          {
            "bool": {
              "should": [
                { "term": { "status": "?1" } },
                { "term": { "status": "?2" } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }
    """)
    List<ProductDocument> findVisibleProducts(
            String categoryId,
            String firstStatus,
            String secondStatus);
}
```

Query thể hiện rõ biểu thức:

```text
categoryId = ?0
AND available = true
AND (status = ?1 OR status = ?2)
```

`filter` dùng cho điều kiện lọc không cần tính điểm relevance. Nhánh `should` được đặt trong một bool query con với `minimum_should_match: 1`, vì vậy ít nhất một trạng thái phải khớp.

Ví dụ dùng Java text block, yêu cầu Java 15 trở lên. Với Java thấp hơn, thay cách viết chuỗi nhưng giữ nguyên JSON. Cú pháp placeholder và cách bind tham số cần khớp phiên bản Spring Data Elasticsearch của dự án; kiểm tra tài liệu phiên bản đang dùng nếu query có kiểu dữ liệu hoặc cấu trúc đặc biệt.

### Ưu điểm và giới hạn của `@Query`

Ưu điểm là cấu trúc query nằm ngay cạnh method, dễ đọc hơn một tên method rất dài và không cần tạo lớp implementation riêng. Giới hạn là JSON được viết dưới dạng chuỗi, tên field phải khớp mapping và query khó xây dựng khi số lượng điều kiện thay đổi theo request.

Nếu truy vấn có nhiều filter tùy chọn, không nên tạo một annotation JSON lớn với nhiều placeholder hoặc cố gửi null cho mọi điều kiện. Hãy dùng custom repository để chỉ thêm những điều kiện thực sự được yêu cầu.

## 6. Cách thứ ba: dùng custom repository fragment cho truy vấn động

Khi query được xây dựng từ nhiều tiêu chí tùy chọn, custom repository fragment giúp tách logic tìm kiếm khỏi interface repository chính.

Ví dụ, người dùng có thể lọc sản phẩm theo một hoặc nhiều tiêu chí:

```java
public record ProductSearchCriteria(
        String categoryId,
        String status,
        Boolean available,
        Long minPrice,
        Long maxPrice,
        String keyword) {
}
```

Định nghĩa fragment interface:

```java
import java.util.List;

public interface ProductSearchOperations {
    List<ProductDocument> search(ProductSearchCriteria criteria);
}
```

Repository chính kế thừa fragment:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchOperations {
}
```

Implementation fragment có thể dùng `ElasticsearchOperations` và `NativeQuery` để xây dựng Query DSL. Ví dụ dưới đây minh họa một query với một số điều kiện; API builder có thể khác theo major version Spring Data Elasticsearch/client:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchOperationsImpl implements ProductSearchOperations {

    private final ElasticsearchOperations operations;

    public ProductSearchOperationsImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<ProductDocument> search(ProductSearchCriteria criteria) {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> {
                if (criteria.categoryId() != null) {
                    b.filter(f -> f.term(t -> t
                        .field("categoryId")
                        .value(criteria.categoryId())
                    ));
                }
                if (criteria.status() != null) {
                    b.filter(f -> f.term(t -> t
                        .field("status")
                        .value(criteria.status())
                    ));
                }
                if (criteria.available() != null) {
                    b.filter(f -> f.term(t -> t
                        .field("available")
                        .value(criteria.available())
                    ));
                }
                if (criteria.minPrice() != null || criteria.maxPrice() != null) {
                    b.filter(f -> f.range(r -> {
                        r.field("priceMinorUnits");
                        if (criteria.minPrice() != null) {
                            r.gte(co.elastic.clients.json.JsonData.of(criteria.minPrice()));
                        }
                        if (criteria.maxPrice() != null) {
                            r.lte(co.elastic.clients.json.JsonData.of(criteria.maxPrice()));
                        }
                        return r;
                    }));
                }
                return b;
            }))
            .build();

        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
            .map(hit -> hit.getContent())
            .toList();
    }
}
```

Đoạn code minh họa cách chỉ thêm filter khi tiêu chí tương ứng có giá trị. API lambda của Elasticsearch Java client, đặc biệt builder `range`, có thể thay đổi theo version; hãy điều chỉnh theo dependency đã resolve trong dự án. Phần thiết kế quan trọng là interface nhận một đối tượng criteria, implementation dựng query và service không phải tự biết chi tiết Query DSL.

Nếu dùng Java thấp hơn 16, thay `record` bằng class DTO thông thường. Nếu cần phân trang, sort, highlight hoặc trả về score, hãy thiết kế kiểu kết quả phù hợp (`SearchHits`, `Page` hoặc DTO kết quả) thay vì luôn chuyển mọi kết quả thành `List`.

### Vì sao criteria object hữu ích?

Một đối tượng `ProductSearchCriteria` gom các bộ lọc tùy chọn vào một cấu trúc có tên. Thay vì một method có 8 tham số rời rạc, service truyền một object thể hiện yêu cầu tìm kiếm. Khi bổ sung bộ lọc mới, có thể mở rộng criteria và implementation mà không phải tạo hàng loạt method gần giống nhau.

Criteria object cũng là nơi phù hợp để xác thực khoảng giá, giới hạn số lượng filter, chuẩn hóa từ khóa và đặt giá trị mặc định cho phân trang. Tuy nhiên, validation nghiệp vụ vẫn nên được thực hiện rõ ràng ở tầng phù hợp.

## 7. Dùng `CriteriaQuery` cho điều kiện động đơn giản

Nếu truy vấn chủ yếu là kết hợp điều kiện bằng/range mà không cần toàn bộ sức mạnh Query DSL, `CriteriaQuery` là một lựa chọn khác trong Spring Data Elasticsearch.

Ví dụ minh họa:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public SearchHits<ProductDocument> searchByCategoryAndStatus(
        String categoryId,
        String status) {

    Criteria criteria = new Criteria("categoryId").is(categoryId)
        .and(new Criteria("status").is(status));

    Query query = new CriteriaQuery(criteria);

    return operations.search(
        query,
        ProductDocument.class,
        IndexCoordinates.of("products")
    );
}
```

`CriteriaQuery` có thể phù hợp khi bộ lọc được ghép dần theo điều kiện. Cú pháp liên kết và các toán tử được hỗ trợ cần được xác nhận theo phiên bản Spring Data Elasticsearch. Với logic OR lồng sâu, nested query hoặc scoring phức tạp, `NativeQuery` thường thể hiện rõ hơn cấu trúc Query DSL.

## 8. Phân chia trách nhiệm giữa service và repository

Không nên để service nghiệp vụ chứa một khối JSON Query DSL lớn. Cũng không nên đưa mọi quyết định nghiệp vụ vào một method repository không có tên gọi rõ ràng.

Một cách tổ chức dễ bảo trì:

```text
ProductController
    |
    v
ProductSearchService
    |-- kiểm tra criteria và quyền truy cập
    |-- áp dụng giá trị mặc định cho paging/sort
    |
    v
ProductRepository
    |-- ElasticsearchRepository CRUD cơ bản
    |-- ProductSearchOperations fragment
            |-- dựng NativeQuery / CriteriaQuery
            |-- gọi ElasticsearchOperations
```

Service chịu trách nhiệm về ý nghĩa nghiệp vụ: người dùng được lọc những trường nào, giá trị mặc định là gì và có được phép truy cập dữ liệu đó hay không. Repository chịu trách nhiệm chuyển tiêu chí thành truy vấn Elasticsearch.

Với truy vấn tĩnh, `@Query` ngay trên repository thường đủ. Với truy vấn động, nhiều tiêu chí tùy chọn hoặc cần tái sử dụng, fragment là nơi phù hợp để tổ chức implementation.

## 9. Chọn công cụ theo độ phức tạp

| Tình huống | Cách viết nên cân nhắc | Lý do |
|---|---|---|
| Tìm theo một ID, SKU hoặc trạng thái | Derived query | Ngắn và dễ hiểu |
| Hai hoặc ba điều kiện AND đơn giản | Derived query | Tên method vẫn thể hiện rõ logic |
| Một truy vấn có nhóm OR/AND cố định | `@Query` | Nhìn thấy ngoặc và `minimum_should_match` |
| Query DSL cố định có nested/boost | `@Query` hoặc custom repository | Có thể biểu diễn trực tiếp cấu trúc Elasticsearch |
| Bộ lọc thay đổi theo request | Custom repository + criteria DTO | Chỉ thêm các điều kiện có giá trị |
| Nhiều truy vấn dùng chung logic filter | Custom repository/service helper | Tránh lặp lại và tập trung logic |
| Aggregation, highlight, score hoặc kết quả tùy biến | `ElasticsearchOperations` | Kiểm soát query và kiểu kết quả chi tiết |

Không cần chuyển tất cả derived query sang custom repository. Derived query vẫn là lựa chọn tốt cho các method đơn giản, rõ nghĩa và ổn định.

## 10. Cách chuyển một method dài mà không đổi hành vi

Khi refactor một method dẫn xuất, đừng bắt đầu bằng việc viết lại JSON theo cảm tính. Hãy xác định chính xác logic cũ trước.

Giả sử method cũ:

```java
List<ProductDocument> findByStatusAndCategoryIdAndAvailableTrueOrFeaturedTrue(
        String status,
        String categoryId);
```

Trước khi thay đổi, cần xác nhận cách parser nhóm điều kiện. Theo cấu trúc PartTree thông thường, biểu thức tương ứng có dạng:

```text
(status = ?0 AND categoryId = ?1 AND available = true)
OR featured = true
```

Nếu mục tiêu nghiệp vụ thực sự là:

```text
status = ?0
AND categoryId = ?1
AND (available = true OR featured = true)
```

thì method cũ có thể đã không diễn đạt đúng ý định. Refactor là thời điểm để xác nhận hành vi mong muốn với người sở hữu nghiệp vụ và bộ dữ liệu mẫu. Không được âm thầm đổi logic chỉ vì query mới trông hợp lý hơn.

Các bước chuyển đổi:

1. Ghi lại biểu thức logic của method cũ với ngoặc rõ ràng.
2. Xác định kiểu mapping của từng field và cách xử lý null/field thiếu.
3. Tạo test dữ liệu bao phủ từng nhánh AND/OR.
4. Viết query mới bằng `@Query`, `CriteriaQuery` hoặc `NativeQuery`.
5. So sánh tập ID kết quả của query cũ và query mới trên cùng dữ liệu.
6. Kiểm tra phân trang, sort, score và các tham số biên.
7. Sau khi kết quả khớp yêu cầu, thay caller sang method mới và xóa method cũ nếu không còn dùng.

Nếu mục tiêu là sửa lỗi logic đã tồn tại, ghi nhận thay đổi hành vi trong test và tài liệu thay vì ép query mới phải giống kết quả sai của query cũ.

## 11. Kiểm thử truy vấn và kiểm tra mapping

Một tên method ngắn hay một JSON query đẹp không đảm bảo kết quả đúng. Hãy kiểm tra query với mapping và document thực tế.

Mapping:

```http
GET /products/_mapping
```

Truy vấn kiểm tra:

```http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "categoryId": "coffee" } },
        { "term": { "available": true } },
        {
          "bool": {
            "should": [
              { "term": { "status": "PUBLISHED" } },
              { "term": { "status": "FEATURED" } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
```

Nên có dữ liệu kiểm thử đại diện:

- Document chỉ khớp điều kiện status thứ nhất.
- Document chỉ khớp điều kiện status thứ hai.
- Document khớp cả hai nhánh.
- Document thiếu field được lọc.
- Document có field null hoặc giá trị rỗng nếu dữ liệu nguồn cho phép.
- Document có giá trị biên như giá tối thiểu/tối đa.
- Document không khớp bất kỳ nhánh nào.

Với truy vấn phân trang, kiểm tra tổng số kết quả, trang đầu, trang cuối và thứ tự sort. Với query có scoring, kiểm tra `_score` và thứ tự kết quả; với filter-only query, đừng kỳ vọng relevance score mang ý nghĩa xếp hạng.

## 12. Những lỗi thường gặp khi tên method quá dài

### Thêm một điều kiện làm thay đổi nhóm logic

Thêm `Or` vào cuối tên method có thể mở rộng kết quả theo một nhánh độc lập. Hãy viết lại biểu thức có ngoặc và xác nhận kết quả mong muốn trước khi sửa tên method.

### Tạo nhiều method gần giống nhau cho filter tùy chọn

Nếu có 5 filter tùy chọn, việc tạo nhiều tổ hợp method sẽ nhanh chóng làm repository phình to. Dùng criteria DTO và custom repository để dựng query theo những filter thực sự có mặt.

### Dùng `@Query` cho một truy vấn quá động

Annotation phù hợp với JSON tĩnh. Khi phải thêm/bỏ nhiều nhánh tùy tham số, một chuỗi JSON lớn với nhiều placeholder khó bảo trì và dễ sai. Chuyển phần dựng query sang implementation.

### Dồn toàn bộ logic truy vấn vào service

Service nên điều phối use case, xác thực criteria và gọi repository. Giữ Query DSL trong repository/custom fragment để logic truy cập dữ liệu có một nơi quản lý.

### Không kiểm tra field mapping

`term` trên field `text` có thể không có hành vi mong đợi. Kiểm tra `keyword`, analyzer và tên field trước khi kết luận query derivation hoặc Query DSL bị lỗi.

### Không kiểm tra null và field thiếu

Các nhánh phủ định hoặc filter tùy chọn có thể xử lý field thiếu khác với SQL. Xác định rõ điều kiện `exists`, `must_not` và `null_value` khi nghiệp vụ phụ thuộc vào chúng.

## 13. Quy trình quyết định

Khi bắt đầu viết một truy vấn repository, hãy đi theo trình tự:

1. Viết mục tiêu tìm kiếm bằng ngôn ngữ nghiệp vụ.
2. Liệt kê field và kiểu mapping cần dùng.
3. Viết biểu thức AND/OR có ngoặc trước khi chọn cách triển khai.
4. Nếu chỉ có vài điều kiện đơn giản, dùng derived query.
5. Nếu query tĩnh nhưng cấu trúc bool/nested phức tạp, dùng `@Query`.
6. Nếu filter tùy chọn hoặc query được dựng theo request, dùng custom fragment với `ElasticsearchOperations`.
7. Đặt tên method theo mục đích nghiệp vụ, không biến tên method thành bản sao của Query DSL.
8. Kiểm thử kết quả với document có thể khớp từng nhánh và các trường hợp thiếu dữ liệu.
9. Kiểm tra paging, sort, scoring và mapping khi truy vấn có các yêu cầu đó.

## 14. Kết luận

Query derivation giúp repository ngắn gọn khi truy vấn đơn giản. Khi tên method quá dài, chứa nhiều nhóm AND/OR, có filter tùy chọn hoặc cần Query DSL chuyên biệt, nên chuyển sang `@Query` hoặc custom repository. `@Query` phù hợp với cấu trúc tĩnh; custom fragment kết hợp `ElasticsearchOperations` phù hợp với truy vấn động và logic có thể tái sử dụng.

Khi refactor, hãy viết biểu thức logic có ngoặc, kiểm tra mapping và so sánh kết quả bằng dữ liệu đại diện. Giữ tên method tập trung vào mục đích nghiệp vụ, để phần truy vấn phức tạp nằm trong một implementation có cấu trúc rõ ràng. Như vậy repository dễ đọc hơn và việc thay đổi bộ lọc ít có nguy cơ làm sai hành vi tìm kiếm.
