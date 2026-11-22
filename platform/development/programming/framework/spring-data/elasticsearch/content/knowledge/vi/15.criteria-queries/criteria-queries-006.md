# Phân biệt điều kiện truy vấn và điều kiện lọc được sinh

`CriteriaQuery` của Spring Data Elasticsearch cho phép mô tả điều kiện tìm kiếm bằng các object `Criteria` rồi chuyển chúng thành truy vấn Elasticsearch. Khi đọc kết quả được sinh ra, cần phân biệt hai khái niệm:

- **Query context**: Elasticsearch kiểm tra document có khớp hay không và tính relevance score để xếp hạng kết quả.
- **Filter context**: Elasticsearch chỉ kiểm tra document có thỏa điều kiện hay không; điều kiện không đóng góp vào relevance score và có thể được cache khi phù hợp.

Điều kiện lọc theo nghiệp vụ không tự động đồng nghĩa với filter context. Ví dụ, `Criteria.where("status").is("ACTIVE")` trông giống một bộ lọc trạng thái, nhưng API `Criteria` xếp thao tác `is()` vào nhóm query criteria entries. Muốn hiểu đúng request được tạo, phải xem loại operation mà Spring Data sử dụng và cấu trúc Query DSL cuối cùng.

## 1. Query context và filter context trong Elasticsearch

Elasticsearch dùng hai cách đánh giá điều kiện trong Query DSL:

| Context | Mục đích | Relevance score | Ví dụ thường gặp |
| --- | --- | --- | --- |
| Query context | Tìm document phù hợp và đánh giá mức độ phù hợp của document với nội dung truy vấn. | Có thể đóng góp vào `_score`. | `match`, `multi_match`, `match_phrase`, `fuzzy`. |
| Filter context | Giữ hoặc loại document theo điều kiện đúng/sai. | Không tính điểm từ điều kiện đó. | Điều kiện trạng thái, khoảng giá, thời gian, địa lý khi chỉ cần giới hạn tập kết quả. |

Ví dụ người dùng tìm sản phẩm bằng cụm từ `wireless keyboard`, sau đó chỉ muốn xem sản phẩm đang hoạt động có giá trong khoảng 100–500:

- Tên sản phẩm cần được phân tích văn bản và có thể xếp hạng theo mức độ khớp: query context.
- Trạng thái phải bằng `ACTIVE`: filter context là phù hợp nếu điều kiện chỉ dùng để giới hạn kết quả.
- Giá phải nằm trong khoảng: filter context là phù hợp nếu không cần tính điểm liên quan từ giá.

Trong Elasticsearch, `bool` query kết hợp các clause theo vai trò:

| Clause | Hành vi | Context |
| --- | --- | --- |
| `must` | Document phải khớp điều kiện. | Query context; score của clause được tính. |
| `should` | Điều kiện tùy chọn hoặc điều kiện tăng mức phù hợp, tùy `minimum_should_match` và các clause khác. | Query context. |
| `filter` | Document phải thỏa điều kiện. | Filter context; không tính score. |
| `must_not` | Document không được thỏa điều kiện. | Filter context; không tính score. |

Ví dụ Query DSL:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lte": 500
            }
          }
        }
      ]
    }
  }
}
~~~

Kết quả vẫn được xếp hạng dựa trên phần tìm kiếm tên sản phẩm. Hai điều kiện trạng thái và giá chỉ giới hạn document đủ điều kiện.

## 2. `Criteria` lưu hai nhóm entry riêng

Trong Spring Data Elasticsearch, `Criteria` là API fluent để tạo điều kiện. Một `Criteria` có hai tập entry nội bộ:

- `queryCriteriaEntries`: các operation được tạo cho query context.
- `filterCriteriaEntries`: các operation được tạo cho filter context.

Khi `CriteriaQuery` được thực thi, Spring Data chuyển các entry này thành phần query và phần filter của request Elasticsearch. Tài liệu API của `Criteria` mô tả rõ hai tập entry này; không nên chỉ nhìn tên method hoặc ý nghĩa nghiệp vụ của điều kiện để đoán context.

### 2.1. Những operation phổ biến được thêm vào query criteria

Các method sau tạo query criteria entry trong API Spring Data Elasticsearch:

| `Criteria` method | Ý nghĩa | Query thường được tạo |
| --- | --- | --- |
| `is(value)` | So khớp bằng giá trị. | `term` query. |
| `in(values)` | Khớp một trong các giá trị. | `terms` query. |
| `notIn(values)` | Không khớp các giá trị đã liệt kê. | Dạng phủ định tương ứng. |
| `matches(text)` | Tìm nội dung văn bản, các token được kết hợp OR. | `match` query với OR operator. |
| `matchesAll(text)` | Tìm nội dung văn bản, các token được kết hợp AND. | `match` query với AND operator. |
| `between(a, b)` | Nằm trong khoảng. | `range` query. |
| `greaterThan(value)` / `lessThan(value)` | So sánh lớn hơn/nhỏ hơn. | `range` query. |
| `exists()` | Field có tồn tại. | `exists` query. |
| `startsWith(value)` | Bắt đầu bằng chuỗi. | `prefix` query. |
| `contains(value)` / `endsWith(value)` | Chứa hoặc kết thúc bằng chuỗi. | Thường tạo wildcard query. |
| `fuzzy(value)` | Tìm gần đúng. | `fuzzy` query. |

Điểm quan trọng: `is("ACTIVE")`, `in("ACTIVE", "PENDING")` và `between(100, 500)` là những điều kiện lọc quen thuộc trong nghiệp vụ, nhưng theo API `Criteria` chúng vẫn được thêm vào `queryCriteriaEntries`. Nếu chúng được đưa vào query context, chúng có thể tham gia tính `_score` cùng các query clause khác.

Với chuỗi cần so khớp chính xác, hãy dùng field mapping `keyword`. `in()` tạo terms query; tài liệu API khuyến cáo không dùng thao tác này trên field `text` đã được analyzer biến đổi.

### 2.2. Những operation tạo filter criteria entry

Một số operation đặc thù tạo filter criteria entry thay vì query criteria entry, nổi bật là các điều kiện địa lý và quan hệ parent/child:

| `Criteria` method | Ý nghĩa |
| --- | --- |
| `within(GeoPoint, distance)` | Điểm nằm trong bán kính địa lý quanh một tọa độ. |
| `within(GeoJson)` | Hình học nằm trong vùng được chỉ định. |
| `boundedBy(...)` | Điểm nằm trong bounding box. |
| `intersects(GeoJson)` | Hình học giao với vùng được chỉ định. |
| `contains(GeoJson)` | Hình học chứa vùng được chỉ định. |
| `isDisjoint(GeoJson)` | Hình học không giao với vùng được chỉ định. |
| `hasChild(query)` | Điều kiện quan hệ child document. |
| `hasParent(query)` | Điều kiện quan hệ parent document. |

Các method có overload khác nhau theo kiểu tọa độ và hình học. Hãy chọn đúng kiểu dữ liệu tương ứng với field mapping, chẳng hạn `geo_point` hoặc `geo_shape`.

Không phải mọi method có tên giống nhau đều cùng context. Ví dụ `contains(String)` tạo query criteria entry dạng tìm chuỗi, còn `contains(GeoJson)` tạo filter criteria entry dạng địa lý.

## 3. Phân biệt AND/OR với query/filter context

Đây là hai khái niệm độc lập và rất dễ nhầm:

- `and()` và `or()` xác định các điều kiện được kết hợp theo logic nào.
- Query context và filter context xác định Elasticsearch đánh giá từng điều kiện theo cách nào.

Trong `CriteriaQuery`, `AND` được chuyển thành quan hệ `must`, còn `OR` được chuyển thành quan hệ `should`. Ví dụ:

~~~java
Criteria criteria = Criteria.where("lastName").is("Miller")
        .and("firstName").is("James");

Query query = new CriteriaQuery(criteria);
~~~

Đây là hai điều kiện được kết hợp AND. Vì `is()` tạo query criteria entry, các điều kiện này thuộc query context theo API `Criteria`.

Ví dụ OR:

~~~java
Criteria firstName = Criteria.where("firstName").is("John")
        .or("firstName").is("Jack");

Query query = new CriteriaQuery(firstName);
~~~

Các điều kiện tên là John hoặc Jack được kết hợp theo `should`. Việc dùng OR không tự biến chúng thành filter context.

Có thể tạo subcriteria để nhóm logic phức tạp hơn:

~~~java
Criteria firstNameIsJohnOrJack = new Criteria()
        .or("firstName").is("John")
        .or("firstName").is("Jack");

Criteria criteria = Criteria.where("lastName").is("Miller")
        .subCriteria(firstNameIsJohnOrJack);

Query query = new CriteriaQuery(criteria);
~~~

Ý nghĩa logic là `lastName = Miller AND (firstName = John OR firstName = Jack)`. Subcriteria điều khiển cách nhóm điều kiện; nó không phải một thao tác chuyển query entry thành filter entry.

## 4. Ví dụ CriteriaQuery tạo cả query và filter entries

Giả sử document sản phẩm có các field:

| Field | Mapping | Mục đích |
| --- | --- | --- |
| `name` | `text` | Tìm kiếm toàn văn. |
| `status` | `keyword` | Trạng thái sản phẩm. |
| `price` | `long` | Khoảng giá. |
| `location` | `geo_point` | Vị trí kho hoặc cửa hàng. |

Entity minh họa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // Constructor, getters và setters
}
~~~

Tạo Criteria:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.Criteria;

Criteria criteria = Criteria.where("name").matches("wireless keyboard")
        .and("status").is("ACTIVE")
        .and("price").between(100, 500)
        .and(new Criteria("location")
                .within(new GeoPoint(10.7769, 106.7009), "5km"));

Query query = new CriteriaQuery(criteria);
~~~

Trong ví dụ:

- `matches("wireless keyboard")` là query criteria entry để tìm nội dung.
- `is("ACTIVE")` là query criteria entry theo API `Criteria`, dù về nghiệp vụ nó là điều kiện lọc trạng thái.
- `between(100, 500)` là query criteria entry theo API `Criteria`.
- `within(GeoPoint, "5km")` là filter criteria entry.

Spring Data kết hợp các điều kiện theo logic AND, đồng thời giữ sự phân biệt giữa query entries và filter entries. Phần query có thể tạo relevance score; phần filter chỉ giới hạn document thỏa điều kiện địa lý.

Gọi truy vấn qua `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<ProductDocument> searchNearbyProducts(
        ElasticsearchOperations operations) {

    Criteria criteria = Criteria.where("name").matches("wireless keyboard")
            .and("status").is("ACTIVE")
            .and("price").between(100, 500)
            .and(new Criteria("location")
                    .within(new GeoPoint(10.7769, 106.7009), "5km"));

    Query query = new CriteriaQuery(criteria);
    return operations.search(query, ProductDocument.class);
}
~~~

Kết quả trả về là các sản phẩm khớp tên, trạng thái, khoảng giá và vị trí. Nếu muốn status và price được xử lý hoàn toàn trong filter context, cần chọn API/query DSL cho phép chỉ định filter rõ ràng thay vì giả định mọi điều kiện nghiệp vụ trong Criteria đều tự trở thành filter.

## 5. Khi nào nên dùng CriteriaQuery?

`CriteriaQuery` phù hợp khi muốn xây dựng truy vấn theo từng bước bằng Java mà không cần viết trực tiếp toàn bộ Elasticsearch Query DSL.

Ví dụ các trường hợp phù hợp:

- Bộ lọc tìm kiếm được ghép từ những lựa chọn của form.
- Điều kiện tìm kiếm đơn giản hoặc trung bình, có thể biểu diễn bằng các operation có sẵn trong `Criteria`.
- Truy vấn có nhiều điều kiện AND/OR và một số tiêu chí địa lý được hỗ trợ.

Ưu điểm:

- Dễ tạo điều kiện có điều kiện bằng code Java.
- Có thể ghép Criteria theo từng bước.
- Dùng mapping metadata của domain type trong quá trình chuyển đổi.
- Không cần tự tạo JSON Query DSL cho các operation phổ biến.

Giới hạn:

- Không phải mọi Query DSL feature đều có operation tương ứng trong `Criteria`.
- Không nên giả định các điều kiện `is`, `in`, `between` được sinh thành filter context.
- Những truy vấn phức tạp về `bool`, nested, aggregation, script, scoring hoặc filter composition có thể cần `NativeQuery`.

## 6. Đặt điều kiện nghiệp vụ vào filter context bằng NativeQuery

Khi muốn điều kiện văn bản tham gia tính điểm còn điều kiện trạng thái và khoảng giá chỉ giới hạn tập kết quả, hãy biểu diễn trực tiếp bằng `bool.must` và `bool.filter` trong `NativeQuery`.

Ví dụ với Spring Data Elasticsearch 5.x/6.x và Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query("wireless keyboard")))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))))
                .filter(f -> f.range(r -> r.number(n -> n
                        .field("price")
                        .gte(100.0)
                        .lte(500.0))))
        ))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
~~~

Trong Query DSL tương ứng, cấu trúc chính có dạng:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lte": 500
            }
          }
        }
      ]
    }
  }
}
~~~

Đây là cách thể hiện rõ ý định:

- `must` tìm nội dung và tham gia tính relevance score.
- `filter` kiểm tra status và price nhưng không đóng góp vào score.

`NativeQuery` cho phép dùng các query builder của Elasticsearch Java API Client, phù hợp khi Criteria API không biểu đạt đủ cấu trúc cần thiết. API builder cụ thể có thể khác theo phiên bản client; hãy dùng dependency tương thích với phiên bản Spring Data Elasticsearch của dự án.

## 7. Phân biệt `bool.filter` và `post_filter`

Ngoài `bool.filter`, Elasticsearch còn có `post_filter` ở cấp search request. Hai cơ chế đều lọc kết quả trả về nhưng có khác biệt quan trọng khi dùng aggregation.

| Cơ chế | Ảnh hưởng document trả về | Ảnh hưởng aggregation |
| --- | --- | --- |
| `bool.filter` bên trong `query` | Có. | Có; aggregation được tính trên tập document đã qua query/filter. |
| `post_filter` ở cấp search request | Có. | Không; aggregation được tính trước post-filter. |

Ví dụ một trang thương mại điện tử hiển thị bộ lọc màu cùng số lượng sản phẩm theo từng màu:

- Nếu màu đang chọn nằm trong `bool.filter`, aggregation màu chỉ tính trên tập kết quả đã bị giới hạn bởi màu đó.
- Nếu màu đang chọn nằm trong `post_filter`, danh sách hit bị lọc theo màu nhưng aggregation vẫn có thể hiển thị số lượng của các màu khác trong tập kết quả ban đầu.

Vì vậy, `post_filter` hữu ích cho một số giao diện faceted search muốn giữ aggregation độc lập với bộ lọc đang chọn. Nếu mong aggregation cũng chịu cùng điều kiện, hãy đưa điều kiện vào `bool.filter` trong query.

Spring Data có API filter riêng trong một số kiểu Query/NativeQuery và cách ánh xạ cụ thể phụ thuộc phiên bản. Đừng chỉ nhìn tên `withFilter` rồi giả định nó tương đương với `bool.filter`. Khi aggregation quan trọng, hãy xác định rõ điều kiện nằm trong `query.bool.filter` hay `post_filter` của request thực tế.

## 8. Tác động của filter context tới score và hiệu năng

### 8.1. Score

Query context có thể thay đổi `_score`. Khi nhiều clause nằm trong `bool.must` hoặc `bool.should`, score của chúng được kết hợp theo quy tắc scoring của Elasticsearch.

Filter context không đóng góp score. Document thỏa filter có thể vẫn có score đến từ phần query context; nếu truy vấn chỉ có filter mà không có query scoring, Elasticsearch có thể dùng score mặc định giống nhau cho các document phù hợp.

Điều này có ý nghĩa khi sắp xếp theo `_score`: hãy giữ các điều kiện tìm kiếm nội dung ở query context và chuyển các ràng buộc không liên quan đến độ phù hợp sang filter context.

### 8.2. Cache và chi phí xử lý

Filter context tránh tính relevance score cho điều kiện đó. Elasticsearch có thể cache kết quả filter phù hợp, đặc biệt với các điều kiện được lặp lại và có tính ổn định. Không phải mọi filter đều được cache tự động trong mọi tình huống; cache phụ thuộc loại query, dữ liệu, cấu hình và quyết định nội bộ của Elasticsearch.

Không nên đưa mọi điều kiện vào filter chỉ vì nghĩ rằng filter luôn nhanh hơn. Hãy chọn context theo ý nghĩa của điều kiện:

- Điều kiện cần đánh giá mức độ liên quan: query context.
- Điều kiện chỉ cần đúng/sai để giới hạn kết quả: filter context.
- Điều kiện cần ảnh hưởng tới aggregation hay không: quyết định giữa `bool.filter` và `post_filter`.

## 9. Mapping ảnh hưởng cách Criteria tạo query

Criteria operation được chuyển thành Query DSL, nhưng kết quả có đúng hay không còn phụ thuộc mapping của field.

| Field cần truy vấn | Mapping nên dùng | Operation phù hợp |
| --- | --- | --- |
| Tên, mô tả cần tìm theo từ | `text` | `matches`, `matchesAll` hoặc các truy vấn full-text tương ứng. |
| Trạng thái, mã, loại sản phẩm cần khớp chính xác | `keyword` | `is`, `in`. |
| Giá, số lượng, điểm | `integer`, `long`, `float`, `double` | `between`, `greaterThan`, `lessThan`. |
| Ngày tạo, ngày cập nhật | `date` | `between`, `greaterThan`, `lessThan`. |
| Tọa độ | `geo_point` | `within`, `boundedBy`. |
| Vùng hình học | `geo_shape` | `within`, `intersects`, `contains`, `isDisjoint` tùy mapping và operation. |

Ví dụ, `in("ACTIVE", "PENDING")` tạo terms query. Nếu field là `text`, analyzer có thể biến đổi token và làm kết quả khác với mong muốn so khớp chính xác. Với trạng thái, nên dùng `keyword`.

`matches("wireless keyboard")` phù hợp với field `text`, vì Elasticsearch phân tích nội dung theo analyzer. Dùng `matches` trên field `keyword` thường không tạo hành vi tìm kiếm toàn văn mà người viết truy vấn mong đợi.

## 10. Cách xem điều kiện thực tế được sinh

Không nên suy luận toàn bộ Query DSL chỉ từ đoạn Java. Khi cần xác nhận query/filter context, hãy xem request được gửi tới Elasticsearch.

Các bước kiểm tra:

1. Bật logging phù hợp cho client/transport của phiên bản đang dùng trong môi trường phát triển.
2. Chạy một CriteriaQuery với dữ liệu mẫu có kết quả dễ nhận biết.
3. Ghi nhận phần `query`, `bool.must`, `bool.should`, `bool.filter` và `post_filter` nếu xuất hiện.
4. So sánh `_score` của kết quả khi điều kiện nằm trong query context và filter context.
5. Nếu có aggregation, kiểm tra aggregation có bị giới hạn bởi filter hay không.
6. Tắt logging request chi tiết sau khi hoàn tất kiểm tra, đặc biệt nếu query chứa dữ liệu người dùng hoặc thông tin nhạy cảm.

Có thể dùng Elasticsearch Profile API để phân tích chi phí từng query khi cần tối ưu sâu. Profile có overhead và nên dùng trong môi trường kiểm thử, không bật mặc định cho mọi request production.

## 11. Những lỗi dễ gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Điều kiện status làm thay đổi `_score` | `Criteria.is()` được tạo thành query criteria entry. | Dùng NativeQuery với `bool.filter` nếu status chỉ cần giới hạn kết quả. |
| Dùng `in()` nhưng chuỗi không khớp | Field là `text` và analyzer đã biến đổi giá trị. | Dùng mapping `keyword` cho mã/trạng thái cần exact match. |
| Điều kiện địa lý không xuất hiện trong query phần chính | Operation địa lý tạo filter criteria entry riêng. | Kiểm tra phần filter của request được sinh và mapping geo field. |
| OR trả về quá nhiều document | `should` có thể là điều kiện tùy chọn khi đi cùng `must`/`filter`, tùy `minimum_should_match`. | Xác định rõ nhóm OR và cấu hình `minimum_should_match` nếu cần bắt buộc khớp ít nhất một nhánh. |
| Aggregation không chịu điều kiện đang chọn | Điều kiện được đặt ở `post_filter`. | Đưa điều kiện vào `bool.filter` nếu aggregation cũng phải bị giới hạn. |
| Filter không làm kết quả nhanh hơn rõ rệt | Filter cache không được bảo đảm và hiệu năng còn phụ thuộc query, dữ liệu, shard và cache. | Đo bằng dữ liệu thực, tránh giả định mọi filter đều được cache. |
| Criteria API không biểu diễn được query cần thiết | Operation hoặc cấu trúc Query DSL chưa được hỗ trợ trực tiếp. | Dùng NativeQuery hoặc StringQuery cho phần truy vấn phức tạp. |

## 12. Chọn CriteriaQuery hay NativeQuery?

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Điều kiện đơn giản, fluent API, AND/OR rõ ràng | `CriteriaQuery`. |
| Full-text search kết hợp các tiêu chí Criteria có sẵn | `CriteriaQuery`, kiểm tra query/filter entries được tạo. |
| Điều kiện status/range cần chắc chắn nằm trong `bool.filter` | `NativeQuery` với `bool.filter`. |
| Query phức tạp có nested bool, script, function score hoặc nhiều tầng query | `NativeQuery`. |
| Cần aggregation và kiểm soát filter ảnh hưởng aggregation | `NativeQuery` với cấu trúc query/filter được thiết kế rõ ràng. |
| Đã có sẵn JSON Query DSL | `StringQuery` hoặc `NativeQuery`. |

Có thể kết hợp Spring Data `ElasticsearchOperations` với cả ba loại Query: `CriteriaQuery`, `StringQuery` và `NativeQuery`. Hãy chọn API giúp thể hiện rõ ý định và dễ kiểm tra request cuối cùng.

## 13. Quy trình thiết kế điều kiện truy vấn

Khi xây dựng truy vấn, hãy đi theo thứ tự:

1. Xác định điều kiện nào cần ảnh hưởng relevance score, chẳng hạn tìm tên hoặc mô tả theo nội dung.
2. Xác định điều kiện nào chỉ cần giới hạn document, chẳng hạn trạng thái, tenant, khoảng thời gian hoặc khoảng giá.
3. Kiểm tra mapping: `text` cho full-text, `keyword` cho exact match, kiểu số/ngày cho range và geo type cho vị trí.
4. Nếu dùng CriteriaQuery, kiểm tra operation được thêm vào `queryCriteriaEntries` hay `filterCriteriaEntries`.
5. Nhớ rằng `and()`/`or()` chỉ quyết định cách kết hợp logic; chúng không tự chuyển một query entry thành filter entry.
6. Nếu cần kiểm soát filter cho field nghiệp vụ thông thường, dùng NativeQuery với `bool.filter`.
7. Nếu có aggregation, quyết định filter phải ảnh hưởng aggregation hay chỉ lọc hits qua `post_filter`.
8. Quan sát request thực tế và thử trên dữ liệu mẫu trước khi tối ưu.

`CriteriaQuery` cung cấp cách xây dựng điều kiện bằng Java, nhưng query context và filter context là hai khái niệm riêng trong Elasticsearch. Các operation phổ biến như `is`, `in`, `between` và `matches` được API Criteria ghi vào query entries; một số operation địa lý và parent/child tạo filter entries. Khi cần business predicates như status hoặc price chắc chắn không tính score, hãy biểu diễn chúng trong `bool.filter` bằng NativeQuery và kiểm tra cách filter tương tác với aggregation.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Elasticsearch Operations và CriteriaQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Criteria API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Criteria.html)
- [Spring Data Elasticsearch — NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Elasticsearch — Query and filter context](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html)
- [Elasticsearch — Bool query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
