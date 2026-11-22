# Xử lý điều kiện tùy chọn khi xây dựng biểu mẫu lọc

Biểu mẫu tìm kiếm thường có nhiều điều kiện mà người dùng không bắt buộc phải nhập hết: từ khóa, trạng thái, danh mục, khoảng giá, khoảng ngày hoặc người tạo. Khi gửi biểu mẫu, ứng dụng cần chỉ đưa những điều kiện thực sự được cung cấp vào truy vấn Elasticsearch.

Spring Data Elasticsearch cung cấp `Criteria` và `CriteriaQuery` để xây dựng truy vấn theo từng điều kiện. Ta có thể thêm tiêu chí khi giá trị có mặt, kết hợp chúng bằng AND/OR, rồi thực thi bằng `ElasticsearchOperations.search(...)`.

Điểm quan trọng là phân biệt **không cung cấp điều kiện** với **cung cấp một giá trị cần tìm**. Ví dụ, `minPrice = 0` là một điều kiện hợp lệ; chuỗi rỗng thường có nghĩa người dùng không nhập từ khóa; danh sách danh mục rỗng thường có nghĩa không lọc theo danh mục.

## 1. Từ biểu mẫu đến CriteriaQuery

Giả sử màn hình tìm kiếm sản phẩm có các trường:

- Từ khóa trong tên sản phẩm.
- Trạng thái xuất bản.
- Danh mục.
- Giá thấp nhất và cao nhất.
- Ngày tạo từ và đến.

Người dùng có thể chỉ nhập từ khóa, hoặc chỉ chọn trạng thái, hoặc kết hợp nhiều trường. Nếu tạo query cố định với mọi điều kiện, các giá trị null/rỗng có thể gây truy vấn sai hoặc khiến kết quả bị thu hẹp ngoài ý muốn.

Luồng xử lý nên có dạng:

~~~mermaid
flowchart TD
    A["Form filter từ người dùng"] --> B["Validate và chuẩn hóa input"]
    B --> C["Tạo Criteria cho điều kiện có giá trị"]
    C --> D["Kết hợp AND / OR"]
    D --> E["Tạo CriteriaQuery"]
    E --> F["Thêm pageable và sort"]
    F --> G["ElasticsearchOperations.search"]
    G --> H["SearchHits trả về"]
~~~

Ví dụ, nếu người dùng chỉ chọn trạng thái `PUBLISHED` và giá tối thiểu `100000`, truy vấn chỉ cần hai điều kiện đó. Không nên thêm điều kiện tên sản phẩm với chuỗi rỗng hoặc khoảng giá tối đa bằng null.

## 2. Criteria và CriteriaQuery là gì?

`Criteria` mô tả một điều kiện trên field Elasticsearch. Một số phép toán thường dùng:

| Phép toán | Ý nghĩa |
|---|---|
| `is(value)` | So khớp giá trị |
| `isNot(value)` | Không bằng giá trị |
| `greaterThan(value)` | Lớn hơn |
| `greaterThanEqual(value)` | Lớn hơn hoặc bằng |
| `lessThan(value)` | Nhỏ hơn |
| `lessThanEqual(value)` | Nhỏ hơn hoặc bằng |
| `between(from, to)` | Trong khoảng |
| `in(values)` | Thuộc một tập giá trị |
| `matches(text)` | Tìm kiếm văn bản theo cơ chế match |
| `contains(text)` | Tìm theo chuỗi con với semantics của Criteria |
| `exists()` | Field tồn tại |
| `isNull()` | Field không có giá trị được lập chỉ mục theo semantics của Elasticsearch |

`CriteriaQuery` đóng gói các Criteria thành một query mà Spring Data Elasticsearch có thể thực thi.

Ví dụ đơn giản:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("status").is("PUBLISHED")
        .and("price").greaterThanEqual(100000);

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

Ở đây, cả hai điều kiện được kết hợp bằng AND: sản phẩm phải có trạng thái `PUBLISHED` và giá lớn hơn hoặc bằng `100000`.

`CriteriaQuery` là một cách xây dựng query ở mức abstraction của Spring Data. Nó không phải JPA Criteria API và cũng không phải SQL string.

## 3. Thiết kế DTO nhận điều kiện lọc

Không nên nhận trực tiếp các tham số rời rạc rồi xây dựng query ở nhiều nơi. Có thể gom chúng vào một filter DTO:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record ProductFilter(
        String keyword,
        String status,
        List<String> categories,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Instant createdFrom,
        Instant createdTo
) {
}
~~~

DTO thể hiện các điều kiện tùy chọn. Giá trị `null` nghĩa là người dùng không cung cấp điều kiện tương ứng.

Trước khi xây dựng query, nên chuẩn hóa input:

- Trim khoảng trắng đầu/cuối của từ khóa.
- Chuyển chuỗi rỗng thành không có điều kiện.
- Loại bỏ giá trị trùng trong danh sách.
- Kiểm tra trạng thái và danh mục có nằm trong tập giá trị hợp lệ.
- Kiểm tra giá tối thiểu không lớn hơn giá tối đa.
- Kiểm tra ngày bắt đầu không nằm sau ngày kết thúc.

Không nên dùng một điều kiện kiểu `if (minPrice > 0)` để xác định giá có được nhập hay không. Giá trị `0` vẫn có thể là điều kiện hợp lệ. Hãy kiểm tra `minPrice != null`.

## 4. Thêm Criteria chỉ khi có giá trị

Giả sử `tenantId` là điều kiện bắt buộc của mọi truy vấn. Ta có thể dùng nó làm Criteria gốc rồi bổ sung các điều kiện tùy chọn.

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.util.StringUtils;

public CriteriaQuery buildQuery(
        String tenantId,
        ProductFilter filter
) {
    // tenantId là điều kiện bắt buộc, không được bỏ qua.
    Criteria criteria = new Criteria("tenantId").is(tenantId);

    if (StringUtils.hasText(filter.keyword())) {
        criteria = criteria.and("name").matches(
                filter.keyword().trim()
        );
    }

    if (StringUtils.hasText(filter.status())) {
        criteria = criteria.and("status").is(
                filter.status().trim()
        );
    }

    if (filter.categories() != null
            && !filter.categories().isEmpty()) {
        criteria = criteria.and("category").in(
                filter.categories()
        );
    }

    if (filter.minPrice() != null) {
        criteria = criteria.and("price").greaterThanEqual(
                filter.minPrice()
        );
    }

    if (filter.maxPrice() != null) {
        criteria = criteria.and("price").lessThanEqual(
                filter.maxPrice()
        );
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("createdAt").greaterThanEqual(
                filter.createdFrom()
        );
    }

    if (filter.createdTo() != null) {
        criteria = criteria.and("createdAt").lessThanEqual(
                filter.createdTo()
        );
    }

    return new CriteriaQuery(criteria);
}
~~~

Trong ví dụ:

- `tenantId` luôn được áp dụng để giới hạn dữ liệu theo tenant.
- `keyword` chỉ được thêm khi có nội dung.
- `status` chỉ được thêm khi người dùng chọn trạng thái.
- `categories` chỉ được thêm khi danh sách không rỗng.
- Mỗi biên giá và ngày được thêm độc lập, nên người dùng có thể chỉ nhập giá tối thiểu hoặc chỉ nhập giá tối đa.

`criteria = criteria.and(...)` giúp nối điều kiện mới vào Criteria chain hiện tại. Tất cả điều kiện trong ví dụ được kết hợp theo AND.

Lưu ý: tên field trong Criteria phải là tên field Elasticsearch, tương ứng với mapping của entity. Nếu Java property dùng tên khác với tên field trong index do cấu hình mapping, hãy dùng đúng tên mà Spring Data ánh xạ.

## 5. Trường hợp không có bất kỳ điều kiện tùy chọn nào

Có biểu mẫu cho phép người dùng bấm tìm kiếm mà không nhập bộ lọc. Cần xác định rõ hành vi mong muốn.

Ví dụ trên có `tenantId` bắt buộc, vì vậy dù người dùng không nhập filter nào thì query vẫn giới hạn trong tenant. Điều này khác với việc tìm toàn bộ dữ liệu trên index.

Nếu không có điều kiện bắt buộc và danh sách filter rỗng, ứng dụng nên quyết định rõ một trong các cách:

- Trả về lỗi validation yêu cầu ít nhất một điều kiện.
- Trả về danh sách rỗng nếu tìm kiếm không có filter bị cấm.
- Cho phép truy vấn rộng một cách có chủ đích, nhưng luôn giới hạn page size và áp dụng quyền truy cập.

Không nên vô tình tạo query rỗng rồi để hành vi mặc định quyết định phạm vi dữ liệu. Với hệ thống multi-tenant hoặc dữ liệu nhạy cảm, tenant/permission filter phải được bổ sung từ context đã xác thực, không lấy tùy ý từ form.

## 6. Phân biệt null, chuỗi rỗng, số 0 và danh sách rỗng

Một lỗi phổ biến khi xử lý form là coi mọi giá trị “trông có vẻ rỗng” đều giống nhau.

| Input | Cách hiểu thường gặp | Cách xử lý |
|---|---|---|
| `keyword = null` | Không nhập từ khóa | Bỏ qua điều kiện |
| `keyword = ""` | Chuỗi rỗng | Trim, rồi bỏ qua |
| `minPrice = null` | Không đặt giá tối thiểu | Bỏ qua cận dưới |
| `minPrice = 0` | Giá tối thiểu bằng 0 | Thêm điều kiện range |
| `categories = null` | Không gửi danh sách | Bỏ qua điều kiện |
| `categories = []` | Không chọn danh mục | Thường bỏ qua điều kiện |
| `status = "PUBLISHED"` | Chọn một trạng thái | Thêm điều kiện chính xác |
| `includeArchived = false` | Người dùng chọn false | Vẫn phải xử lý như một giá trị được cung cấp nếu filter có ý nghĩa |

Đối với checkbox boolean, nếu cần phân biệt “không chọn” với “chọn false”, dùng `Boolean` nullable hoặc một kiểu biểu diễn có trạng thái rõ ràng. Kiểu primitive `boolean` không phân biệt được hai trường hợp này.

### Khi người dùng muốn tìm document thiếu field

Đừng nhầm `null` trong DTO với yêu cầu tìm document không có giá trị. `null` trong filter thường có nghĩa bỏ qua điều kiện; còn nếu người dùng chủ động chọn “chưa có trạng thái”, cần thêm một điều kiện truy vấn tương ứng, ví dụ `exists` hoặc `isNull` theo mapping và semantics của field.

Trong Elasticsearch, field có giá trị JSON `null` thường không được lập chỉ mục như một term. Nếu mapping dùng `null_value`, cách biểu diễn và truy vấn sẽ khác. Hãy kiểm tra mapping thực tế trước khi thiết kế bộ lọc cho null/missing.

## 7. Xây dựng khoảng giá và khoảng ngày

Khoảng giá thường có hai cận độc lập. Không yêu cầu người dùng phải nhập cả hai.

Ví dụ:

~~~java
if (filter.minPrice() != null) {
    criteria = criteria.and("price")
            .greaterThanEqual(filter.minPrice());
}

if (filter.maxPrice() != null) {
    criteria = criteria.and("price")
            .lessThanEqual(filter.maxPrice());
}
~~~

Nếu có cả hai cận, điều kiện tương đương:

~~~json
{
  "range": {
    "price": {
      "gte": 100000,
      "lte": 500000
    }
  }
}
~~~

Dùng `greaterThanEqual` và `lessThanEqual` khi muốn bao gồm cả hai đầu mút. Nếu nghiệp vụ yêu cầu khoảng nửa mở, chọn `greaterThan` hoặc `lessThan` tương ứng.

Với ngày giờ, nên dùng `Instant` hoặc một kiểu ngày giờ có timezone/offset rõ ràng. Ví dụ, nếu form chọn ngày theo múi giờ địa phương, hãy chuyển ranh giới ngày sang instant theo timezone nghiệp vụ trước khi tạo query. Điều này tránh sai lệch khi server và người dùng ở các múi giờ khác nhau.

Trước khi tạo query, validate:

~~~java
if (filter.minPrice() != null
        && filter.maxPrice() != null
        && filter.minPrice().compareTo(filter.maxPrice()) > 0) {
    throw new IllegalArgumentException(
            "minPrice must be less than or equal to maxPrice"
    );
}
~~~

Không nên âm thầm đổi chỗ hai cận nếu người dùng nhập ngược. Báo lỗi rõ ràng giúp form hiển thị đúng nguyên nhân.

## 8. Tìm kiếm văn bản và điều kiện lọc chính xác

Một biểu mẫu thường kết hợp tìm kiếm toàn văn với các filter chính xác.

Ví dụ:

- Từ khóa `wireless keyboard`: tìm trên field `name`.
- Trạng thái `PUBLISHED`: lọc chính xác trên `status`.
- Danh mục `ACCESSORIES`: lọc chính xác trên `category`.

Trong Criteria API:

~~~java
Criteria criteria = new Criteria("name").matches("wireless keyboard")
        .and("status").is("PUBLISHED")
        .and("category").is("ACCESSORIES");

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

`matches(...)` được dùng cho tìm kiếm văn bản; `is(...)` thường phù hợp với field keyword và điều kiện so khớp giá trị.

Mapping cần tương ứng:

~~~java
@Field(type = FieldType.Text)
private String name;

@Field(type = FieldType.Keyword)
private String status;

@Field(type = FieldType.Keyword)
private String category;
~~~

Không nên dùng cùng một kiểu field cho mọi nhu cầu. Nếu status được mapping thành `text`, analyzer có thể làm thay đổi token; nếu tên sản phẩm chỉ là keyword, tìm kiếm theo từ có thể không hoạt động như mong đợi.

Nếu tên sản phẩm có multi-field, hãy dùng trường chính `name` cho full-text và field con như `name.keyword` cho so khớp chính xác hoặc sort.

## 9. Kết hợp AND và OR

Thông thường, các filter độc lập trong form được kết hợp bằng AND: trạng thái phải đúng, danh mục phải phù hợp, giá phải nằm trong khoảng.

Ví dụ:

~~~text
status = PUBLISHED
AND category = ACCESSORIES
AND price >= 100000
AND price <= 500000
~~~

Một số form có nhiều lựa chọn cùng nhóm và muốn match một trong các giá trị. Với cùng một field, `in(...)` thường rõ ràng hơn nhiều điều kiện OR:

~~~java
Criteria criteria = new Criteria("category")
        .in(List.of("ACCESSORIES", "KEYBOARD"));
~~~

Điều này tương đương điều kiện category thuộc một trong hai giá trị.

Với logic OR giữa các field khác nhau, cần biểu diễn nhóm điều kiện rõ ràng. Ví dụ nghiệp vụ muốn sản phẩm có trạng thái `FEATURED` hoặc có nhãn `PROMOTED`. Có thể dùng Criteria OR chain hoặc chuyển sang query builder có hỗ trợ bool query rõ ràng:

~~~java
Query query = Query.of(q -> q
        .bool(b -> b
                .should(s -> s
                        .term(t -> t
                                .field("status")
                                .value("FEATURED")
                        )
                )
                .should(s -> s
                        .term(t -> t
                                .field("label")
                                .value("PROMOTED")
                        )
                )
                .minimumShouldMatch("1")
        )
);
~~~

Ví dụ này dùng Elasticsearch Java API Client để thể hiện OR trong một nhóm bool. Nếu query có nhiều nhóm AND/OR lồng nhau, `NativeQuery` hoặc `BoolQueryBuilder` phù hợp hơn khi cần kiểm soát chính xác cấu trúc DSL. Không nên nối các Criteria rời rạc theo cách khiến thứ tự ưu tiên AND/OR khó đọc.

## 10. Thêm phân trang và sắp xếp

Một biểu mẫu lọc thường cần page và sort. `CriteriaQuery` có thể nhận pageable:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

CriteriaQuery query = new CriteriaQuery(criteria);

query.setPageable(
        PageRequest.of(
                0,
                20,
                Sort.by(Sort.Direction.DESC, "createdAt")
        )
);
~~~

Sau đó thực thi:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
~~~

Lưu ý:

- Page index bắt đầu từ `0`.
- Page size cần giới hạn ở mức hợp lý.
- Field sort phải có mapping phù hợp, thường là keyword hoặc numeric/date.
- Không sort trực tiếp trên text field theo mặc định.
- Với tập kết quả lớn, cân nhắc search_after thay cho phân trang sâu bằng from/size.

Nếu người dùng được phép chọn cột sort, hãy ánh xạ lựa chọn từ form sang danh sách field cho phép. Không dùng trực tiếp tên field tùy ý do client gửi vào query.

## 11. Service hoàn chỉnh cho biểu mẫu lọc

Một service có thể gom validation, xây Criteria và thực thi search:

~~~java
import java.util.Optional;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            String tenantId,
            ProductFilter filter,
            int page,
            int size
    ) {
        validate(filter);

        Criteria criteria = new Criteria("tenantId").is(tenantId);

        if (StringUtils.hasText(filter.keyword())) {
            criteria = criteria.and("name")
                    .matches(filter.keyword().trim());
        }

        if (StringUtils.hasText(filter.status())) {
            criteria = criteria.and("status")
                    .is(filter.status().trim());
        }

        if (filter.categories() != null
                && !filter.categories().isEmpty()) {
            criteria = criteria.and("category")
                    .in(filter.categories());
        }

        if (filter.minPrice() != null) {
            criteria = criteria.and("price")
                    .greaterThanEqual(filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            criteria = criteria.and("price")
                    .lessThanEqual(filter.maxPrice());
        }

        if (filter.createdFrom() != null) {
            criteria = criteria.and("createdAt")
                    .greaterThanEqual(filter.createdFrom());
        }

        if (filter.createdTo() != null) {
            criteria = criteria.and("createdAt")
                    .lessThanEqual(filter.createdTo());
        }

        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(
                PageRequest.of(
                        page,
                        size,
                        Sort.by(Sort.Direction.DESC, "createdAt")
                )
        );

        return operations.search(query, ProductDocument.class);
    }

    private void validate(ProductFilter filter) {
        if (filter.minPrice() != null
                && filter.maxPrice() != null
                && filter.minPrice().compareTo(filter.maxPrice()) > 0) {
            throw new IllegalArgumentException(
                    "minPrice must be less than or equal to maxPrice"
            );
        }

        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && filter.createdFrom().isAfter(filter.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must not be after createdTo"
            );
        }
    }
}
~~~

Đây là ví dụ minh họa cấu trúc service. Trong ứng dụng thật, cần kiểm tra page/size không âm, giới hạn kích thước trang, chuẩn hóa danh sách category, xác thực tenant từ security context và đảm bảo các field được mapping đúng kiểu.

`SearchHits` chứa metadata và kết quả. Nếu cần chuyển sang DTO cho API, có thể map `hits.getSearchHits()` sang response model thay vì trả trực tiếp cấu trúc Spring Data ra ngoài.

## 12. Khi nào nên chuyển từ CriteriaQuery sang NativeQuery?

`CriteriaQuery` phù hợp với các form lọc có cấu trúc tương đối đơn giản:

- AND/OR cơ bản.
- So khớp chính xác.
- Range query.
- Tập giá trị.
- Tìm kiếm văn bản thông thường.
- Phân trang và sort.

`NativeQuery` phù hợp khi cần biểu diễn DSL nâng cao hoặc kiểm soát chi tiết hơn:

- Bool query nhiều nhóm lồng nhau.
- Nested query.
- Function score.
- Script query.
- Aggregation phức tạp.
- Các tính năng query DSL chưa được Criteria abstraction thể hiện thuận tiện.

Không cần chuyển sang NativeQuery chỉ vì form có nhiều trường tùy chọn. Có thể tiếp tục tạo Criteria có điều kiện. Chỉ đổi abstraction khi cấu trúc query hoặc tính năng cần dùng vượt quá khả năng biểu đạt rõ ràng của Criteria API.

## 13. Những lỗi thường gặp khi xử lý filter tùy chọn

### Thêm điều kiện với null

Gọi `is(null)` khi người dùng không nhập giá trị không tương đương với bỏ qua filter. Hãy kiểm tra null trước khi thêm Criteria.

### Không trim chuỗi

Chuỗi `"   "` có thể vượt qua kiểm tra `!= null` nhưng không chứa nội dung tìm kiếm hữu ích. Dùng `StringUtils.hasText(...)` hoặc chuẩn hóa tương đương.

### Coi số 0 là không có giá trị

`minPrice = 0` có thể là điều kiện hợp lệ. Dùng kiểm tra null thay vì kiểm tra lớn hơn 0.

### Truy vấn terms với danh sách rỗng

Danh sách rỗng thường có nghĩa người dùng chưa chọn filter. Bỏ qua điều kiện thay vì tạo `in(emptyList)`, vì semantics hoặc query được sinh ra có thể không như mong đợi.

### Ghép mọi điều kiện bằng OR

Nếu status, category và price là các filter bắt buộc đồng thời, dùng OR sẽ trả về các document chỉ cần thỏa một điều kiện. Xác định logic nghiệp vụ trước khi xây query.

### Dùng sai kiểu field

`term` trên field text có analyzer có thể không khớp giá trị gốc. Dùng keyword cho trạng thái/mã và text cho nội dung cần tìm toàn văn.

### Không giới hạn page size

Người dùng có thể gửi page size rất lớn khiến request tốn bộ nhớ và tài nguyên. Đặt giới hạn server-side, không tin giá trị từ form.

### Cho phép client chọn field tùy ý

Field name trong Criteria là metadata truy vấn. Chỉ cho phép các field đã được ứng dụng định nghĩa, đặc biệt với sort và filter động.

### Bỏ qua filter quyền truy cập

Filter tenant, owner hoặc phạm vi dữ liệu cần được thêm từ security context. Không để người dùng có thể bỏ qua bằng cách gửi null hoặc sửa request.

## 14. Quy trình xây dựng biểu mẫu lọc

Khi triển khai một form tìm kiếm với CriteriaQuery:

1. Thiết kế DTO có kiểu dữ liệu rõ ràng cho từng điều kiện.
2. Phân biệt giá trị không nhập với giá trị hợp lệ như số 0 hoặc boolean false.
3. Chuẩn hóa chuỗi và danh sách trước khi tạo query.
4. Validate khoảng giá, ngày tháng và danh sách giá trị.
5. Tạo Criteria chỉ cho điều kiện có mặt.
6. Luôn thêm filter bắt buộc về tenant/quyền truy cập từ nguồn đáng tin cậy.
7. Kết hợp các điều kiện theo AND/OR đúng yêu cầu nghiệp vụ.
8. Tạo CriteriaQuery và thêm pageable/sort có giới hạn.
9. Thực thi bằng ElasticsearchOperations.search.
10. Khi cần DSL phức tạp, cân nhắc NativeQuery.
11. Kiểm tra mapping field và query thực tế với các tổ hợp filter khác nhau.

## Kết luận

Xử lý điều kiện tùy chọn bằng CriteriaQuery là quá trình chuyển các giá trị form đã được chuẩn hóa thành những Criteria chỉ xuất hiện khi người dùng thực sự cung cấp chúng. Dùng AND cho các filter phải đồng thời thỏa mãn, dùng OR hoặc tập `in` cho các lựa chọn thay thế, và luôn giữ các điều kiện phân quyền bắt buộc. Sau đó tạo `CriteriaQuery`, thêm phân trang/sắp xếp và thực thi qua `ElasticsearchOperations.search(...)`.
