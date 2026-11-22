# Bộ lọc tùy chọn, giá trị null và quy tắc kết hợp điều kiện

Một API tìm kiếm thường có nhiều bộ lọc mà người gọi có thể bỏ qua: trạng thái, danh mục, khoảng giá, thương hiệu, thời gian cập nhật và từ khóa. Thách thức không nằm ở việc thêm từng điều kiện vào Query DSL, mà ở việc xác định chính xác **khi nào một điều kiện được áp dụng, khi nào nó bị bỏ qua và khi nào nó có nghĩa là tìm giá trị thiếu hoặc null**.

Nếu code chỉ kiểm tra truthy/falsy, các giá trị hợp lệ như `false`, `0` hoặc chuỗi rỗng có thể bị xử lý sai. Nếu thêm mọi filter kể cả khi giá trị null, query có thể tìm document thiếu field thay vì bỏ qua điều kiện. Nếu kết hợp các nhánh OR không có ngoặc logic rõ ràng, kết quả có thể rộng hơn hoặc hẹp hơn mong đợi.

Bài học này trình bày cách thiết kế filter tùy chọn trong Spring Data Elasticsearch, chuẩn hóa input, xử lý null/empty, kết hợp AND/OR/NOT bằng bool query và kiểm thử các tổ hợp điều kiện. Nguyên tắc xuyên suốt là: **quy tắc nghiệp vụ quyết định semantics của filter; query builder chỉ chuyển semantics đó thành Query DSL**.

## 1. Bộ lọc tùy chọn là gì?

Giả sử API tìm kiếm sản phẩm cho phép:

~~~http
GET /api/products/search?q=keyboard&category=ACCESSORIES&minPrice=100000&maxPrice=2000000&status=PUBLISHED
~~~

Người gọi có thể chỉ truyền một vài điều kiện:

~~~http
GET /api/products/search?category=ACCESSORIES
~~~

hoặc:

~~~http
GET /api/products/search?q=keyboard
~~~

Một filter là tùy chọn khi việc không truyền giá trị có nghĩa là không áp dụng điều kiện tương ứng. Ví dụ, nếu không có `category`, kết quả có thể thuộc mọi danh mục mà người dùng được phép xem.

Tuy nhiên, “không truyền” không phải lúc nào cũng giống “truyền null”, “chuỗi rỗng”, “danh sách rỗng” hoặc `false`. API cần định nghĩa riêng semantics cho từng loại dữ liệu.

Một request filter nên được hiểu theo hợp đồng:

| Input | Ý nghĩa có thể chọn | Cách xử lý |
|---|---|---|
| Không truyền category | Không lọc theo category | Không thêm clause |
| category = ACCESSORIES | Chỉ lấy category này | Thêm term filter |
| Không truyền minPrice | Không giới hạn giá dưới | Không thêm lower bound |
| minPrice = 0 | Giá phải lớn hơn hoặc bằng 0 | Giữ giá trị 0 |
| active = false | Chỉ lấy document inactive | Thêm term filter false |
| brands không truyền | Không lọc thương hiệu | Không thêm clause |
| brands = [] | Tùy hợp đồng: không lọc, không có kết quả hoặc input không hợp lệ | Phải chọn rõ |
| status = null | Tùy hợp đồng: không lọc hoặc tìm field null/missing | Không tự suy đoán |

Không nên dùng một quy tắc “null/empty thì bỏ qua” cho mọi kiểu input mà không xác định ý nghĩa nghiệp vụ.

## 2. Thiết kế Search Criteria độc lập với HTTP

Controller nên chuyển request thành criteria có kiểu dữ liệu rõ ràng. Criteria không nên chứa raw Query DSL hoặc tên field tùy ý do client gửi.

Ví dụ:

~~~java
public record ProductSearchCriteria(
        String tenantId,
        String text,
        String category,
        List<String> brands,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean active,
        String status,
        Boolean hasDescription
) {
}
~~~

Một criteria riêng có thể được tạo từ request DTO sau khi xác thực và chuẩn hóa:

~~~java
public record ProductSearchRequest(
        String q,
        String category,
        List<String> brands,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean active,
        String status,
        Boolean hasDescription
) {
}
~~~

Tách hai kiểu giúp:

- Request DTO phản ánh hợp đồng HTTP.
- Criteria phản ánh ý định nghiệp vụ.
- Tenant scope có thể được thêm từ principal đã xác thực.
- Giá trị mặc định và quy tắc empty/null được xử lý ở một nơi.
- Query builder không cần biết request được gửi qua query parameter hay JSON body.

Không đưa `tenantId` do client tự chọn vào criteria nội bộ nếu người gọi không có quyền chọn tenant. Service nên lấy tenant từ authentication/authorization provider.

## 3. Phân biệt absent, null, blank và empty

Bốn trạng thái này thường bị gộp sai:

- **Absent**: field không xuất hiện trong request.
- **Null**: field có xuất hiện nhưng giá trị là JSON `null`, hoặc tham số được bind thành null.
- **Blank**: chuỗi có mặt nhưng rỗng hoặc chỉ chứa whitespace.
- **Empty collection**: danh sách có mặt nhưng không chứa phần tử.

Ví dụ JSON:

~~~json
{
  "category": null,
  "status": "",
  "brands": [],
  "active": false,
  "minPrice": 0
}
~~~

Một số framework binding có thể làm mất khác biệt giữa absent và explicit null nếu DTO chỉ dùng field nullable. Nếu API cần phân biệt hai trạng thái, hãy dùng request model có presence marker, wrapper hoặc JSON node phù hợp.

Quy tắc gợi ý cho API search:

| Trạng thái | Chuỗi | Số | Boolean | Collection |
|---|---|---|---|---|
| Absent | Bỏ qua filter | Bỏ qua bound | Bỏ qua filter | Bỏ qua filter |
| Null | Bỏ qua hoặc tìm missing theo hợp đồng | Thường bỏ qua | Thường bỏ qua | Thường bỏ qua |
| Blank/empty | Trim rồi bỏ qua hoặc reject | Không áp dụng | Không áp dụng | Không áp dụng |
| Empty list | Không lọc hoặc match-none theo hợp đồng | Không áp dụng | Không áp dụng | Phải xác định rõ |
| Giá trị hợp lệ | Thêm clause | Thêm range/term | Thêm term kể cả false | Thêm terms |

Đây chỉ là policy mẫu. Một endpoint quản trị có thể cần semantics khác, ví dụ explicit null nghĩa là tìm document chưa có giá trị.

## 4. Không dùng kiểm tra truthy/falsy cho filter

Lỗi thường gặp:

~~~java
if (criteria.minPrice() != null
        && criteria.minPrice().doubleValue() > 0) {
    // Add price filter
}
~~~

Điều kiện trên loại bỏ giá trị 0 dù `minPrice = 0` có thể là input hợp lệ.

Tương tự:

~~~java
if (Boolean.TRUE.equals(criteria.active())) {
    // Add active filter
}
~~~

Đoạn code chỉ áp dụng filter khi active là true; giá trị false bị bỏ qua. Nếu `false` có nghĩa là tìm document inactive, đây là bug.

Hãy kiểm tra presence/null:

~~~java
if (criteria.minPrice() != null) {
    // Add lower bound, including zero.
}

if (criteria.active() != null) {
    // Add active=true or active=false.
}
~~~

Với chuỗi:

~~~java
if (criteria.text() != null && !criteria.text().isBlank()) {
    // Add full-text query.
}
~~~

Với collection:

~~~java
if (criteria.brands() != null && !criteria.brands().isEmpty()) {
    // Add terms filter, subject to the API's empty-list policy.
}
~~~

Không dùng `if (value)` hoặc `if (!value)` cho các giá trị Boolean/Number khi cần phân biệt false và zero.

## 5. Chuẩn hóa input trước khi build query

Query builder nên nhận dữ liệu đã được chuẩn hóa hoặc tự gọi một component normalization thuần Java.

Ví dụ:

~~~java
public final class ProductSearchNormalizer {

    private ProductSearchNormalizer() {
    }

    public static ProductSearchCriteria normalize(
            ProductSearchCriteria criteria
    ) {
        String text = normalizeText(criteria.text());
        String category = normalizeCode(criteria.category());

        List<String> brands = criteria.brands() == null
                ? null
                : criteria.brands().stream()
                        .filter(Objects::nonNull)
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .toList();

        return new ProductSearchCriteria(
                criteria.tenantId(),
                text,
                category,
                brands,
                criteria.minPrice(),
                criteria.maxPrice(),
                criteria.active(),
                normalizeCode(criteria.status()),
                criteria.hasDescription()
        );
    }

    private static String normalizeText(String value) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private static String normalizeCode(String value) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized.toUpperCase(Locale.ROOT);
    }
}
~~~

Ví dụ này chọn policy: blank text/code trở thành absent; collection được loại phần tử null/blank và loại duplicate. Một API khác có thể trả validation error khi nhận blank hoặc empty list. Hãy chọn một hành vi nhất quán và ghi rõ trong API contract.

Không tự lowercase mọi text search. Analyzer và ngôn ngữ quyết định cách xử lý chữ hoa/thường; việc normalize query string nên phù hợp với mapping và semantics.

## 6. Xác thực các quan hệ giữa filter

Một criteria có thể chứa các giá trị riêng lẻ hợp lệ nhưng tổ hợp lại không hợp lệ.

Ví dụ:

- minPrice lớn hơn maxPrice.
- startDate sau endDate.
- Một danh sách status chứa giá trị không được hỗ trợ.
- Một filter yêu cầu text nhưng text bị blank.
- Một endpoint yêu cầu ít nhất một trong SKU hoặc keyword.

Ví dụ validation:

~~~java
public void validate(ProductSearchCriteria criteria) {
    if (criteria.minPrice() != null
            && criteria.maxPrice() != null
            && criteria.minPrice().compareTo(criteria.maxPrice()) > 0) {
        throw new InvalidSearchCriteriaException(
                "minPrice must not exceed maxPrice"
        );
    }

    if (criteria.brands() != null
            && criteria.brands().size() > 50) {
        throw new InvalidSearchCriteriaException(
                "Too many brand filters"
        );
    }
}
~~~

Validation nên chạy trước khi query builder tạo Query DSL. Query builder không nên phải đoán cách xử lý một range ngược hoặc danh sách filter quá lớn.

Không tự hoán đổi min/max để “sửa” request nếu API contract không nói như vậy. Báo lỗi input thường rõ hơn việc âm thầm thay đổi ý định của người gọi.

## 7. Quy tắc AND: tất cả điều kiện phải đúng

Trong tìm kiếm sản phẩm, điều kiện phổ biến là:

- Tenant phải đúng.
- Status phải là PUBLISHED.
- Nếu có category thì category phải khớp.
- Nếu có khoảng giá thì giá phải nằm trong khoảng.
- Nếu có thương hiệu thì thương hiệu phải thuộc danh sách.

Đây là quan hệ AND. Elasticsearch bool query thường dùng `filter` cho các điều kiện ràng buộc không cần relevance score.

~~~text
tenant = tenant-42
    AND status = PUBLISHED
    AND category = ACCESSORIES
    AND price >= 100000
    AND price <= 2000000
    AND brand IN (ACME, CONTOSO)
~~~

Ví dụ Query DSL:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "PUBLISHED" } },
        { "term": { "category": "ACCESSORIES" } },
        { "range": { "price": { "gte": 100000, "lte": 2000000 } } },
        { "terms": { "brand": ["ACME", "CONTOSO"] } }
      ]
    }
  }
}
~~~

`filter` không ảnh hưởng relevance score và phù hợp với điều kiện chính xác, khoảng số/ngày và tenant scope.

Khi một filter tùy chọn không có giá trị, không thêm clause tương ứng. Các filter còn lại vẫn kết hợp AND.

## 8. Quy tắc OR: chỉ cần một nhánh đúng

Giả sử tìm sản phẩm nếu:

- Tên chứa từ khóa; hoặc
- SKU khớp chính xác; hoặc
- Barcode khớp chính xác.

Đây là nhóm OR. Có thể dùng `should` và chỉ rõ `minimum_should_match`:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "PUBLISHED" } }
      ],
      "should": [
        { "match": { "name": "keyboard" } },
        { "term": { "sku": "keyboard" } },
        { "term": { "barcode": "keyboard" } }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Điều kiện tenant/status vẫn là AND với toàn bộ nhóm OR. Tức là:

~~~text
tenant đúng
AND status là PUBLISHED
AND (name khớp OR sku khớp OR barcode khớp)
~~~

Nếu bool query có `must` hoặc `filter`, mặc định `should` có thể chỉ đóng vai trò tăng score và không bắt buộc phải match. Vì vậy, nếu nghiệp vụ yêu cầu ít nhất một nhánh OR, hãy đặt `minimum_should_match: 1` tường minh.

## 9. Quy tắc NOT: loại trừ điều kiện

`must_not` dùng để loại document thỏa một điều kiện.

Ví dụ loại sản phẩm đã ngừng bán:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } }
      ],
      "must_not": [
        { "term": { "status": "DISCONTINUED" } }
      ]
    }
  }
}
~~~

Ý nghĩa:

~~~text
tenant đúng
AND NOT(status = DISCONTINUED)
~~~

Cần phân biệt “không phải DISCONTINUED” với “status phải tồn tại và khác DISCONTINUED”. Một document thiếu status có thể vẫn thỏa `must_not term(status = DISCONTINUED)`.

Nếu yêu cầu field phải tồn tại, kết hợp `exists` trong filter:

~~~json
{
  "bool": {
    "filter": [
      { "exists": { "field": "status" } }
    ],
    "must_not": [
      { "term": { "status": "DISCONTINUED" } }
    ]
  }
}
~~~

Hãy diễn đạt đúng semantics trong nghiệp vụ: “khác giá trị X” và “có giá trị, nhưng khác X” không giống nhau khi document có thể thiếu field.

## 10. Kết hợp nhóm điều kiện bằng ngoặc logic

Khi query có AND và OR, hãy viết biểu thức nghiệp vụ trước rồi mới chuyển thành bool query.

Ví dụ:

~~~text
tenant đúng
AND status = PUBLISHED
AND (
      category = ACCESSORIES
      OR brand = ACME
    )
AND (
      price < 500000
      OR price > 5000000
    )
~~~

Mỗi nhóm OR nên là một bool query lồng nhau:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "PUBLISHED" } },
        {
          "bool": {
            "should": [
              { "term": { "category": "ACCESSORIES" } },
              { "term": { "brand": "ACME" } }
            ],
            "minimum_should_match": 1
          }
        },
        {
          "bool": {
            "should": [
              { "range": { "price": { "lt": 500000 } } },
              { "range": { "price": { "gt": 5000000 } } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
~~~

Không đặt tất cả clause vào một danh sách `should` nếu chúng thuộc các nhóm OR khác nhau. Query builder cần giữ cấu trúc ngoặc logic của biểu thức nghiệp vụ.

Một cách tốt là đặt tên cho từng nhóm điều kiện trong code, ví dụ `availabilityFilter`, `priceBandFilter`, `textMatchQuery`. Tên có ý nghĩa giúp reviewer hiểu logic mà không phải tự phân tích một biểu thức bool dài.

## 11. Null trong Elasticsearch không giống SQL NULL

Elasticsearch không dùng SQL semantics. Với trường `_source` có giá trị JSON null, field thường không tạo indexed value và không match `exists`. Tuy nhiên, source có thể vẫn lưu key với giá trị null nếu `_source` được bật.

Ví dụ:

~~~json
{
  "productId": "P-1001",
  "description": null
}
~~~

Thông thường query:

~~~json
{
  "query": {
    "exists": {
      "field": "description"
    }
  }
}
~~~

không match document trên.

Cần nhớ:

- Field không có trong source: thường không có indexed value.
- Field có giá trị null: thường không có indexed value.
- Field có mảng rỗng: không có giá trị để index.
- Field có `null_value` trong mapping: explicit null có thể được index như giá trị thay thế.
- Field bị bỏ qua do `ignore_above` hoặc `ignore_malformed`: có thể không có indexed value dù source chứa giá trị.

Vì vậy, `exists` kiểm tra giá trị có được index hay không, không phải phép kiểm tra chính xác xem JSON key có tồn tại trong `_source` hay không.

## 12. Tìm document thiếu field hoặc có null

Để tìm document không có indexed value cho `description`, dùng `must_not exists`:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

Điều này có thể bao gồm document không có key, document có explicit null, mảng rỗng và các trường hợp không tạo indexed value khác.

Nếu mapping dùng `null_value`, explicit null được index bằng sentinel và có thể match `exists`. Khi đó semantics thay đổi.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "keyword",
        "null_value": "__NULL__"
      }
    }
  }
}
~~~

Document có `"description": null` có thể được index với giá trị sentinel `__NULL__`. Query tìm explicit null theo sentinel:

~~~json
{
  "query": {
    "term": {
      "description": "__NULL__"
    }
  }
}
~~~

`null_value` không thay đổi nội dung `_source`; nó chỉ thay giá trị được index cho mục đích query. Chọn sentinel không thể xuất hiện như dữ liệu hợp lệ và bảo đảm mọi writer tuân thủ cùng mapping.

Nếu nghiệp vụ cần phân biệt ba trạng thái: absent, explicit null và giá trị bình thường, cách rõ ràng hơn thường là lưu thêm field trạng thái như `descriptionState` với các giá trị `MISSING`, `NULL`, `PRESENT`. Query `exists` đơn thuần không thể phân biệt absent và explicit null trong trường hợp mặc định.

## 13. Filter null/missing bằng exists và must_not

Có thể tạo các semantics riêng:

| Nhu cầu | Query |
|---|---|
| Field có indexed value | `exists(field)` |
| Field không có indexed value | `must_not exists(field)` |
| Field bằng giá trị cụ thể | `term(field, value)` |
| Field là explicit null với null_value mapping | `term(field, sentinel)` |
| Field khác giá trị X và phải tồn tại | `exists(field) AND must_not term(field, X)` |

Không dùng `term field = null` để tìm null như cách viết SQL. Term query yêu cầu một indexed term/value phù hợp; null không phải một term thông thường.

Nếu API có filter `descriptionState`, nên biểu diễn bằng enum:

~~~java
public enum NullFilter {
    ANY,
    PRESENT,
    MISSING,
    EXPLICIT_NULL
}
~~~

Sau đó builder chuyển từng giá trị enum thành query tương ứng. `ANY` nghĩa là không thêm điều kiện; `PRESENT` dùng exists; `MISSING` dùng must_not exists; `EXPLICIT_NULL` cần mapping/presence marker được thiết kế hỗ trợ.

## 14. Chuỗi rỗng và whitespace

Chuỗi `""`, `"   "` và field không tồn tại là các trạng thái khác nhau trong source. Với keyword field, chuỗi rỗng có thể là một giá trị được index; với field text, analyzer có thể tạo ra zero token từ chuỗi rỗng/whitespace.

Nếu API search không muốn coi chuỗi rỗng là một điều kiện, trim và bỏ qua trước khi tạo query:

~~~java
String text = criteria.text();

if (text != null && !text.isBlank()) {
    // Add match or multi_match query.
}
~~~

Nếu API cần tìm document có chuỗi rỗng, phải có mapping và semantics rõ ràng. Không thể dùng `isBlank()` để biểu diễn yêu cầu đó vì nó cố ý gộp chuỗi rỗng và whitespace thành trạng thái absent.

Không tự động trim mọi giá trị keyword. Với mã định danh, việc trim có thể đúng; với token/code có ý nghĩa khoảng trắng, cần policy riêng.

## 15. Empty list và terms query

`terms` query dùng để match một trong các giá trị được cung cấp:

~~~json
{
  "query": {
    "terms": {
      "brand": ["ACME", "CONTOSO"]
    }
  }
}
~~~

Nếu danh sách rỗng, đừng dựa vào behavior ngầm hoặc để query builder tạo một clause không rõ nghĩa. Chọn một trong ba policy:

1. **Empty means no filter**: bỏ qua điều kiện khi danh sách rỗng.
2. **Empty means no matches**: tạo match-none hoặc trả kết quả rỗng theo use case.
3. **Empty is invalid**: trả lỗi validation.

Ví dụ helper với policy empty means no filter:

~~~java
if (criteria.brands() != null && !criteria.brands().isEmpty()) {
    filters.add(termsQuery("brand", criteria.brands()));
}
~~~

Nếu endpoint có semantics “người dùng chọn một danh sách rỗng nghĩa là không được xem sản phẩm nào”, việc bỏ filter là lỗi bảo mật/nghiệp vụ nghiêm trọng. Hãy thể hiện policy này bằng enum/command riêng thay vì suy luận chỉ từ collection rỗng.

Cũng cần phân biệt absent list với empty list nếu API muốn hỗ trợ cả hai trạng thái. Một DTO thông thường có thể cần presence marker để giữ khác biệt.

## 16. Boolean false và số 0 là giá trị hợp lệ

Các filter Boolean thường có ba trạng thái:

- `true`: chỉ lấy active.
- `false`: chỉ lấy inactive.
- `null`: không lọc theo active, nếu API chọn semantics đó.

Query:

~~~json
{
  "query": {
    "term": {
      "active": false
    }
  }
}
~~~

Tương tự, range `price >= 0` phải giữ lower bound bằng 0:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 0
      }
    }
  }
}
~~~

Không dùng `if (active)` hoặc `if (minPrice.doubleValue() > 0)`. Hãy kiểm tra `!= null`.

## 17. Khoảng giá: inclusive, exclusive và range ngược

Elasticsearch range query hỗ trợ các toán tử:

| Toán tử | Ý nghĩa |
|---|---|
| `gt` | Lớn hơn |
| `gte` | Lớn hơn hoặc bằng |
| `lt` | Nhỏ hơn |
| `lte` | Nhỏ hơn hoặc bằng |

Nếu API định nghĩa khoảng giá đóng hai đầu, dùng `gte` và `lte`. Nếu yêu cầu “trên 100.000” thì dùng `gt`.

Khi chỉ có min:

~~~json
{
  "range": {
    "price": {
      "gte": 100000
    }
  }
}
~~~

Khi chỉ có max:

~~~json
{
  "range": {
    "price": {
      "lte": 2000000
    }
  }
}
~~~

Khi cả hai có mặt:

~~~json
{
  "range": {
    "price": {
      "gte": 100000,
      "lte": 2000000
    }
  }
}
~~~

Nếu min lớn hơn max, trả validation error. Không gửi range ngược rồi mong Elasticsearch tự hiểu.

Với tiền tệ, cần thống nhất đơn vị và kiểu lưu trữ. Có thể lưu đơn vị nhỏ nhất bằng integer/long để tránh sai số floating point; nếu mapping dùng double thì cần hiểu sai số và cách chuyển `BigDecimal` sang giá trị query.

## 18. Date filter và timezone

Date filter thường có start/end tùy chọn:

~~~java
public record DateRangeCriteria(
        Instant from,
        Instant to
) {
}
~~~

Nếu dùng `Instant`, dữ liệu đã biểu diễn một thời điểm UTC. Nếu API nhận local date/time, phải xác định timezone trước khi chuyển sang Instant.

Ví dụ range:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2026-02-01T00:00:00Z"
    }
  }
}
~~~

Khoảng thời gian thường dễ định nghĩa bằng đầu mốc inclusive và cuối mốc exclusive: `[from, to)`. Cách này tránh phải tạo “23:59:59.999...” cho cuối ngày.

Nếu `from` hoặc `to` null, chỉ thêm bound tương ứng. Kiểm tra `from <= to`. Đừng để timezone mặc định của máy CI quyết định ý nghĩa ngày tìm kiếm.

## 19. Dựng bool query động bằng Spring Data Elasticsearch

Với Spring Data Elasticsearch hiện đại, có thể tạo Query bằng Elasticsearch Java API Client và gắn vào `NativeQuery`. Ví dụ dưới đây minh họa một builder chỉ thêm clause khi criteria có giá trị.

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query as SpringQuery;
~~~

Trong Java không hỗ trợ cú pháp alias import như `Query as SpringQuery`. Vì vậy, khi code thật, hãy dùng tên đầy đủ cho một trong hai kiểu hoặc tránh import trùng tên. Ví dụ builder sau dùng kiểu Elasticsearch Java Client `Query` và trả về `NativeQuery`:

~~~java
public NativeQuery build(ProductSearchCriteria criteria) {
    List<co.elastic.clients.elasticsearch._types.query_dsl.Query> filters =
            new ArrayList<>();

    filters.add(term("tenantId", criteria.tenantId()));
    filters.add(term("status", "PUBLISHED"));

    if (criteria.category() != null) {
        filters.add(term("category", criteria.category()));
    }

    if (criteria.active() != null) {
        filters.add(term("active", criteria.active()));
    }

    if (criteria.minPrice() != null || criteria.maxPrice() != null) {
        filters.add(priceRange(
                criteria.minPrice(),
                criteria.maxPrice()
        ));
    }

    if (criteria.brands() != null && !criteria.brands().isEmpty()) {
        filters.add(terms("brand", criteria.brands()));
    }

    List<co.elastic.clients.elasticsearch._types.query_dsl.Query> must =
            new ArrayList<>();

    if (criteria.text() != null && !criteria.text().isBlank()) {
        must.add(multiMatch(criteria.text()));
    }

    co.elastic.clients.elasticsearch._types.query_dsl.Query boolQuery =
            co.elastic.clients.elasticsearch._types.query_dsl.Query.of(q ->
                    q.bool(b -> {
                        b.filter(filters);
                        if (!must.isEmpty()) {
                            b.must(must);
                        }
                        return b;
                    })
            );

    return NativeQuery.builder()
            .withQuery(boolQuery)
            .build();
}
~~~

Các helper `term`, `terms`, `priceRange` và `multiMatch` sẽ đóng gói cách gọi Java API Client. Ví dụ helper term:

~~~java
private Query term(String field, String value) {
    return Query.of(q -> q.term(t -> t
            .field(field)
            .value(FieldValue.of(value))
    ));
}

private Query term(String field, boolean value) {
    return Query.of(q -> q.term(t -> t
            .field(field)
            .value(FieldValue.of(value))
    ));
}
~~~

`tenantId` và `status` là điều kiện bắt buộc. Category, active, price và brands là tùy chọn. Giá trị false không bị bỏ qua vì builder kiểm tra null, không kiểm tra true.

Các import và helper cụ thể cần khớp phiên bản Elasticsearch Java API Client/Spring Data trong dự án. Không trộn `org.springframework.data.elasticsearch.core.query.Query` với `co.elastic.clients.elasticsearch._types.query_dsl.Query` mà không phân biệt rõ tên.

## 20. Helper cho range và terms

Helper range có thể xây dựng một numeric range với một hoặc hai bound:

~~~java
private Query priceRange(BigDecimal min, BigDecimal max) {
    return Query.of(q -> q.range(r -> r.number(n -> {
        n.field("price");

        if (min != null) {
            n.gte(min.doubleValue());
        }

        if (max != null) {
            n.lte(max.doubleValue());
        }

        return n;
    })));
}
~~~

Helper terms:

~~~java
private Query terms(String field, List<String> values) {
    List<FieldValue> terms = values.stream()
            .map(FieldValue::of)
            .toList();

    return Query.of(q -> q.terms(t -> t
            .field(field)
            .terms(v -> v.value(terms))
    ));
}
~~~

Chỉ gọi helper terms khi list có phần tử theo policy đã chọn. Không truyền list null hoặc empty vào builder rồi để behavior phụ thuộc client version.

Nếu dùng `BigDecimal` cho tiền, kiểm tra mapping và đơn vị lưu. Ví dụ chuyển sang `doubleValue()` chỉ minh họa cho mapping double; ứng dụng dùng minor-unit long nên chuyển đổi sang long theo currency scale đã định nghĩa.

## 21. Nhóm OR bằng bool query lồng nhau

Ví dụ muốn tìm theo tên hoặc SKU khi cả hai cùng là filter tùy chọn:

~~~java
private Query textOrSku(String text) {
    Query byName = Query.of(q -> q.match(m -> m
            .field("name")
            .query(text)
    ));

    Query bySku = Query.of(q -> q.term(t -> t
            .field("sku")
            .value(FieldValue.of(text))
    ));

    return Query.of(q -> q.bool(b -> b
            .should(byName)
            .should(bySku)
            .minimumShouldMatch("1")
    ));
}
~~~

Khi có từ khóa, builder thêm nhóm OR này vào `must` hoặc `filter` tùy scoring requirement. Nếu không có từ khóa, không thêm nhóm OR.

Nếu cần điều kiện OR giữa nhiều filter chính xác, dùng `filter` chứa nested bool query. Nếu muốn relevance score từ tên và mô tả, đặt nested bool trong `must` hoặc `should` theo semantics.

Đừng thêm các nhánh OR bằng nhiều `filter` riêng lẻ: nhiều filter riêng trong bool query thường kết hợp AND, không phải OR.

## 22. Kết hợp null filter với các filter khác

Giả sử API hỗ trợ `descriptionState`:

- ANY: không lọc.
- PRESENT: description có indexed value.
- MISSING: description không có indexed value.
- EXPLICIT_NULL: chỉ có thể hỗ trợ nếu mapping/presence marker phân biệt được trạng thái này.

Ví dụ builder:

~~~java
private Query descriptionStateFilter(NullFilter state) {
    return switch (state) {
        case ANY -> null;
        case PRESENT -> Query.of(q -> q.exists(e ->
                e.field("description")
        ));
        case MISSING -> Query.of(q -> q.bool(b -> b
                .mustNot(m -> m.exists(e ->
                        e.field("description")
                ))
        ));
        case EXPLICIT_NULL -> Query.of(q -> q.term(t -> t
                .field("descriptionState")
                .value(FieldValue.of("NULL"))
        ));
    };
}
~~~

Trong ví dụ, `descriptionState` là field presence marker do ứng dụng duy trì. Nếu không có marker hoặc `null_value` phù hợp, không thể phân biệt explicit null với missing chỉ bằng `exists` mặc định.

Không thêm `null` vào danh sách filter. `ANY` là một trạng thái rõ ràng để builder biết bỏ qua điều kiện.

## 23. Query builder đầy đủ với filter tùy chọn

Một builder có thể được tổ chức theo nhóm:

~~~java
@Component
public class ProductSearchQueryBuilder {

    public NativeQuery build(ProductSearchCriteria criteria) {
        List<Query> filters = new ArrayList<>();
        List<Query> must = new ArrayList<>();

        // Mandatory scope and business visibility.
        filters.add(term("tenantId", criteria.tenantId()));
        filters.add(term("status", "PUBLISHED"));

        addCategoryFilter(criteria, filters);
        addActiveFilter(criteria, filters);
        addPriceFilter(criteria, filters);
        addBrandFilter(criteria, filters);
        addDescriptionFilter(criteria, filters);

        if (hasText(criteria.text())) {
            must.add(textOrSku(criteria.text().trim()));
        }

        Query query = Query.of(q -> q.bool(b -> {
            b.filter(filters);
            if (!must.isEmpty()) {
                b.must(must);
            }
            return b;
        }));

        return NativeQuery.builder()
                .withQuery(query)
                .build();
    }

    private void addCategoryFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (hasText(criteria.category())) {
            filters.add(term(
                    "category",
                    criteria.category().trim()
            ));
        }
    }

    private void addActiveFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (criteria.active() != null) {
            filters.add(term("active", criteria.active()));
        }
    }

    private void addPriceFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (criteria.minPrice() != null
                || criteria.maxPrice() != null) {
            filters.add(priceRange(
                    criteria.minPrice(),
                    criteria.maxPrice()
            ));
        }
    }

    private void addBrandFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (criteria.brands() != null
                && !criteria.brands().isEmpty()) {
            filters.add(terms("brand", criteria.brands()));
        }
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

Đây là cấu trúc minh họa; các helper và kiểu `Query` phải dùng thống nhất Elasticsearch Java API Client của phiên bản dự án. Có thể tách helper thành component riêng nếu nhiều use case cùng dùng.

Các điểm đáng chú ý:

- Filter tenant/status luôn được thêm.
- Filter category chỉ thêm khi có text.
- Filter active được thêm cả khi giá trị là false.
- Price range giữ min bằng 0.
- Brand list rỗng được bỏ qua theo policy đã chọn.
- Full-text/sku được nhóm OR và chỉ thêm khi có từ khóa.
- Query builder không gọi Elasticsearch.

## 24. Filter bắt buộc và filter tùy chọn phải tách rõ

Một lỗi nghiêm trọng là để mọi filter cùng một danh sách tùy chọn. Một số điều kiện không bao giờ được bỏ qua:

- Tenant scope.
- Quyền visibility.
- Soft-delete condition.
- Trạng thái chỉ được phép hiển thị.
- Region/organization boundary.

Ví dụ:

~~~java
filters.add(term("tenantId", authenticatedTenantId));
filters.add(term("deleted", false));
~~~

Các filter người dùng tùy chọn được thêm sau:

~~~java
if (criteria.category() != null) {
    filters.add(term("category", criteria.category()));
}
~~~

Không cho phép `tenantId == null` dẫn đến bỏ qua tenant filter. Nếu tenant là bắt buộc, service phải từ chối request khi không có tenant đã xác thực.

Với use case quản trị đa tenant, tạo service method/permission riêng có tên và authorization rõ ràng. Không dùng null để biểu diễn “admin được tìm tất cả”.

## 25. Field có thể thiếu và filter phủ định

Cần hiểu behavior của `must_not` với document thiếu field.

Ví dụ yêu cầu “không phải discontinued”:

~~~json
{
  "bool": {
    "must_not": [
      {
        "term": {
          "status": "DISCONTINUED"
        }
      }
    ]
  }
}
~~~

Document không có status có thể được trả vì nó không match term bị loại trừ.

Nếu yêu cầu “status tồn tại và khác discontinued”:

~~~json
{
  "bool": {
    "filter": [
      {
        "exists": {
          "field": "status"
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "status": "DISCONTINUED"
        }
      }
    ]
  }
}
~~~

Đây là khác biệt quan trọng trong index có document cũ, dữ liệu migration hoặc field chỉ được thêm từ một phiên bản ứng dụng mới.

Khi schema có thể thay đổi, hãy quyết định rõ cách xử lý document thiếu field: được xem là default, không hợp lệ, hay thuộc nhóm riêng.

## 26. Empty list: no filter, match-none hay validation error?

Một ví dụ cụ thể: API có filter `allowedCategories` được lấy từ quyền người dùng.

Nếu danh sách rỗng vì người dùng không được phép xem danh mục nào, bỏ qua filter sẽ trả tất cả danh mục — một lỗi authorization.

Ngược lại, nếu client gửi `brands=[]` để biểu thị “không chọn filter thương hiệu”, bỏ qua filter có thể đúng.

Vì vậy, empty-list semantics phụ thuộc nguồn dữ liệu và ý nghĩa:

| Nguồn danh sách | Empty có thể có nghĩa | Hành vi |
|---|---|---|
| Optional user filter | Người dùng không chọn | Bỏ qua filter |
| Authorization allowlist | Không được phép xem mục nào | Match-none hoặc deny |
| Required command input | Thiếu input bắt buộc | Validation error |
| Internal batch selection | Không có item cần xử lý | Không gửi request hoặc hoàn tất rỗng |

Không dùng cùng một helper `addTermsIfPresent` cho filter người dùng và authorization allowlist nếu semantics khác nhau.

## 27. Filter có điều kiện phụ thuộc nhau

Một số filter chỉ hợp lệ khi filter khác có mặt.

Ví dụ:

- Nếu `includeOutOfStock=true`, user cần authority tương ứng.
- Nếu có `supplierId`, chỉ role quản trị mới được lọc theo supplier nội bộ.
- Nếu chọn mode `ADVANCED`, phải có ít nhất một điều kiện nâng cao.
- Nếu chọn `dateField=UPDATED_AT`, range phải được diễn giải theo updatedAt.

Đặt các rule này ở validation/policy layer:

~~~java
if (criteria.includeOutOfStock()
        && !authorization.canViewOutOfStock()) {
    throw new AccessDeniedException(
            "Not allowed to include out-of-stock products"
    );
}
~~~

Query builder chỉ nhận criteria đã được cấp phép. Không nên để builder quyết định quyền chỉ bằng việc kiểm tra một Boolean trong request.

## 28. Tránh tạo query rỗng hoặc match-all ngoài ý muốn

Nếu mọi filter tùy chọn đều absent, query có thể chỉ còn các filter bắt buộc. Điều này có thể hợp lệ hoặc nguy hiểm tùy endpoint.

Ví dụ search toàn bộ sản phẩm đã xuất bản của tenant có thể là use case hợp lệ. Nhưng một endpoint bắt buộc có từ khóa không nên âm thầm chạy match_all khi text blank.

Service có thể yêu cầu ít nhất một điều kiện:

~~~java
if (!hasText(criteria.text())
        && !hasText(criteria.category())
        && criteria.minPrice() == null
        && criteria.maxPrice() == null
        && (criteria.brands() == null || criteria.brands().isEmpty())) {
    throw new InvalidSearchCriteriaException(
            "At least one search filter is required"
    );
}
~~~

Nếu endpoint cho phép browse toàn bộ trong tenant, không cần reject. Nhưng page size phải giới hạn và tenant/visibility filter vẫn bắt buộc.

Không dựa vào builder tự tạo `match_all` khi danh sách filter rỗng mà không xem xét policy của endpoint.

## 29. Sort và pagination không phải filter

Query conditions xác định document nào khớp. Sort và pagination xác định thứ tự và phần kết quả được trả.

Có thể thiết lập riêng:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(boolQuery)
        .withPageable(PageRequest.of(
                criteria.page(),
                criteria.size(),
                allowedSort(criteria.sort())
        ))
        .build();
~~~

Không để page size hoặc sort field do client truyền vào không giới hạn. Dùng allowlist sort field, page size max và tie-breaker ổn định.

Khi dùng `from/size`, giới hạn độ sâu. Với phân trang sâu, dùng `search_after` cùng sort ổn định và PIT khi cần snapshot.

Thay đổi page/sort không nên làm thay đổi semantics của filter. Tách các component này giúp test từng phần độc lập.

## 30. Kiểm thử tổ hợp filter

Query builder có nhiều nhánh nên cần kiểm thử theo bảng tổ hợp. Unit test nên xác nhận cấu trúc query hoặc serialize thành Query DSL để so sánh semantics.

Ma trận ví dụ:

| Criteria | Clause mong đợi |
|---|---|
| category null | Không có category term |
| category blank | Bỏ qua hoặc validation theo policy |
| category = ACCESSORIES | Có category term |
| active = true | Có active term true |
| active = false | Có active term false |
| active = null | Không có active term |
| minPrice = 0 | Có gte 0 |
| maxPrice = 0 | Có lte 0 |
| minPrice > maxPrice | Validation error |
| brands null | Không có terms |
| brands empty | Theo policy empty-list |
| brands có 2 phần tử | Terms chứa cả 2 giá trị |
| text blank | Không có full-text clause |
| text có giá trị | Có nhóm text/SKU OR |
| tenant null | Từ chối trước khi build query |

Một unit test cần xác nhận cả trường hợp “không có clause” lẫn “có clause với false/zero”. Chỉ test happy path với giá trị truthy sẽ bỏ sót bug phổ biến.

## 31. Kiểm thử null/missing trên Elasticsearch thật

Một unit test query object không chứng minh behavior của mapping và `exists`. Cần integration test với Elasticsearch để xác nhận:

- Field không có trong source.
- Field explicit null.
- Field có empty string.
- Field có mảng rỗng.
- Field có `null_value`.
- Field bị ignore do `ignore_above` hoặc `ignore_malformed` nếu ứng dụng dùng.
- Field nested/object.
- Mapping của index version cũ và mới.

Ví dụ test data:

~~~json
{"productId":"P-1"}
{"productId":"P-2","description":null}
{"productId":"P-3","description":""}
{"productId":"P-4","description":[]}
{"productId":"P-5","description":"Keyboard"}
~~~

Sau đó chạy `exists(description)` và `must_not exists(description)`, kiểm tra kết quả thực tế theo mapping. Nếu dùng `null_value`, thêm test cho sentinel.

Đừng giả định kết quả của Elasticsearch giống database relational `IS NULL`.

## 32. Kiểm thử AND/OR/NOT theo truth table

Với query phức tạp, viết bảng truth table trước:

| Tenant đúng | Status published | Name match | SKU match | Kết quả |
|---|---|---|---|---|
| Không | Có | Có | Có | Không |
| Có | Không | Có | Có | Không |
| Có | Có | Có | Không | Có |
| Có | Có | Không | Có | Có |
| Có | Có | Không | Không | Không |

Biểu thức tương ứng:

~~~text
tenantCorrect
AND statusPublished
AND (nameMatch OR skuMatch)
~~~

Test nên tạo document đại diện cho từng hàng của bảng và chạy integration query. Điều này phát hiện lỗi bool default `should` hoặc thiếu tenant filter tốt hơn một assertion chỉ kiểm tra query JSON có chứa một vài field.

## 33. Những lỗi thường gặp

### Dùng if truthy cho Boolean

`false` bị coi là absent. Kiểm tra `value != null`.

### Dùng điều kiện lớn hơn 0 cho số

Min price bằng 0 bị bỏ qua. Kiểm tra null, không kiểm tra truthiness.

### Gộp absent và explicit null

API có thể cần phân biệt bỏ qua filter với tìm field null. Dùng presence-aware request model hoặc enum semantics.

### Gửi term null

Elasticsearch không xử lý null như SQL term. Dùng exists/must_not exists hoặc presence marker.

### Cho rằng exists kiểm tra key trong _source

`exists` kiểm tra indexed value. Explicit null, empty array và field bị ignore có thể không match.

### Bỏ qua empty-list policy

Danh sách rỗng có thể vô tình bỏ authorization filter hoặc tạo kết quả quá rộng. Xác định no-filter, match-none hay invalid.

### Quên minimum_should_match

Bool có filter/must có thể làm should trở thành optional theo default. Đặt minimum_should_match khi OR phải có ít nhất một nhánh khớp.

### Đưa mọi điều kiện vào should

Các điều kiện AND bị biến thành OR. Nhóm filter bắt buộc trong filter; nhóm lựa chọn trong bool lồng nhau.

### Dùng must_not mà không kiểm tra exists

Document thiếu field cũng có thể được trả. Nếu cần field tồn tại, thêm exists.

### Cho tenant filter là tùy chọn

Tenant null có thể mở tìm kiếm toàn index. Tenant scope phải bắt buộc ở service/policy.

### Dùng cùng một helper cho user filter và authorization filter

Empty user filter có thể nghĩa là no-filter, nhưng empty authorization allowlist phải nghĩa là deny/match-none. Tách semantics.

### Query builder tự đọc SecurityContext

Dependency ẩn làm unit test khó và có thể khiến background job thiếu tenant. Truyền scope đã xác thực qua criteria.

### Tạo match-all khi input rỗng mà không kiểm tra use case

Có thể vô tình tạo query rộng. Quyết định endpoint có cho browse toàn bộ trong scope hay cần ít nhất một filter.

## 34. Quy trình thiết kế filter tùy chọn

Khi thêm một filter vào search API:

1. Định nghĩa absent, explicit null, blank và empty có nghĩa gì.
2. Xác định filter là bắt buộc, tùy chọn hay phụ thuộc quyền.
3. Chuẩn hóa chuỗi, mã, collection và timezone trước khi build query.
4. Giữ giá trị Boolean false và numeric zero.
5. Validate các quan hệ như min/max và from/to.
6. Xác định empty list là no-filter, match-none hay invalid.
7. Dùng filter cho điều kiện AND không cần scoring.
8. Dùng nested bool/should cho nhóm OR và đặt minimum_should_match rõ ràng.
9. Dùng must_not cho điều kiện phủ định; thêm exists nếu field phải có giá trị.
10. Dùng exists/must_not exists cho indexed presence, không giả định SQL NULL semantics.
11. Nếu phải phân biệt absent với explicit null, thiết kế presence marker hoặc null_value phù hợp.
12. Giữ tenant/visibility/soft-delete scope ở nhóm điều kiện bắt buộc.
13. Dùng field name và sort field do server kiểm soát.
14. Giới hạn page size và độ sâu phân trang.
15. Unit test ma trận null/empty/false/zero và tổ hợp AND/OR/NOT.
16. Integration test exists/null_value/mapping và kết quả query thực tế.
17. Theo dõi query latency và không log raw criteria chứa dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Elasticsearch — Boolean query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
- [Elasticsearch — Exists query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-exists-query.html)
- [Elasticsearch — Term query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html)
- [Elasticsearch — Terms query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-terms-query.html)
- [Elasticsearch — Range query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html)
- [Elasticsearch — Null value mapping parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/null-value.html)
- [Elasticsearch — Mapping source field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

## Kết luận

Filter tùy chọn cần có semantics rõ ràng cho absent, null, blank và empty trước khi được chuyển thành Query DSL. Dùng kiểm tra null thay cho truthy/falsy để giữ Boolean false và numeric zero; xác thực các range và collection; dùng filter cho AND, nested bool/should cho OR và must_not cho NOT. Trong Elasticsearch, exists kiểm tra indexed value chứ không tương đương SQL IS NULL; explicit null mặc định thường không có indexed value, còn null_value hoặc presence marker có thể tạo semantics riêng. Tenant và visibility scope phải luôn bắt buộc. Unit test ma trận tổ hợp và integration test trên mapping thật giúp bảo đảm query phản ánh đúng quy tắc nghiệp vụ.
