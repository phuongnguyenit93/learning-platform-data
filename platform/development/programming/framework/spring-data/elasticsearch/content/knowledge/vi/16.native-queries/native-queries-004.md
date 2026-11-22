# Thiết lập sort, phân trang và giới hạn kết quả

`NativeQuery` cho phép xây dựng Elasticsearch Query DSL bằng Elasticsearch Java API Client, đồng thời tích hợp các tùy chọn của Spring Data Elasticsearch như sort và pageable. Khi truy vấn trả về nhiều document, ba việc cần thiết là xác định thứ tự kết quả, giới hạn số hit cần lấy và chọn cách đi qua các trang dữ liệu.

Sort quyết định thứ tự hiển thị. Pagination xác định vị trí và kích thước một trang. Result limit kiểm soát số document trả về cho một lần tìm kiếm. Các lựa chọn này ảnh hưởng đến trải nghiệm người dùng, tải cluster, bộ nhớ ứng dụng và tính ổn định của kết quả khi dữ liệu thay đổi.

## 1. Vai trò của sort, pagination và limit

### 1.1. Sort quyết định thứ tự kết quả

Nếu không chỉ định sort, Elasticsearch thường xếp hạng kết quả theo relevance score khi query có tính điểm. Với các query không tính điểm hoặc trong một số ngữ cảnh khác, thứ tự mặc định không nên được xem là thứ tự nghiệp vụ ổn định.

Một màn hình danh sách sản phẩm có thể cần sắp xếp theo giá tăng dần, ngày tạo mới nhất hoặc tên theo thứ tự chữ cái. Những yêu cầu đó cần được khai báo tường minh.

### 1.2. Pagination chia kết quả thành từng trang

Thay vì trả về toàn bộ document phù hợp, ứng dụng yêu cầu một phần kết quả:

- Trang số 0: các kết quả đầu tiên.
- Trang số 1: nhóm kết quả tiếp theo.
- Trang số 2: nhóm kết quả tiếp theo nữa.

Spring Data dùng `Pageable` để biểu diễn số trang, kích thước trang và có thể cả sort. Chỉ số trang bắt đầu từ 0.

### 1.3. Limit giới hạn số hit trong một request

Limit là số document tối đa mà một lần search cần trả về. Trong cách dùng thông thường của Spring Data, giới hạn này được biểu diễn bằng kích thước `Pageable`.

Ví dụ, `PageRequest.of(0, 20)` yêu cầu trang đầu với tối đa 20 hit. Điều này không có nghĩa toàn bộ query chỉ có 20 kết quả; query vẫn có thể phù hợp với hàng nghìn document.

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Sort | Kết quả nào đứng trước? | Giá thấp nhất trước |
| Pagination | Đang lấy phần nào của tập kết quả? | Trang 2 |
| Limit/page size | Một lần lấy tối đa bao nhiêu hit? | 20 hit |
| Total hits | Có bao nhiêu document phù hợp? | 1.250 hit |

## 2. Tạo NativeQuery cơ bản

### 2.1. Khởi tạo query với Query DSL

`NativeQuery` là lựa chọn phù hợp khi cần dùng các query Elasticsearch như match, term, bool, range, nested, function score hoặc các thành phần DSL khác.

Ví dụ tìm sản phẩm theo tên:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .build();
~~~

Query này tìm các document có nội dung phù hợp với cụm từ theo analyzer của field `name`. Đến bước thực thi, truyền query và entity class cho `ElasticsearchOperations`:

~~~java
SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

### 2.2. Tên field trong NativeQuery

Query DSL làm việc với tên field trong Elasticsearch mapping. Nếu entity Java khai báo:

~~~java
@Field(name = "product_name", type = FieldType.Text)
private String name;
~~~

thì trong NativeQuery, field thường phải được ghi là `product_name`:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("product_name")
        .query("wireless keyboard")
    ))
    .build();
~~~

Không mặc định rằng mọi chuỗi truyền vào NativeQuery đều được Spring tự đổi từ tên property Java sang tên field trong mapping. Hãy dùng tên field thực tế và kiểm tra mapping của index.

### 2.3. Tách query condition khỏi tùy chọn hiển thị

Query condition trả lời document nào phù hợp. Sort, page và limit quyết định cách lấy các document phù hợp đó.

Ví dụ cùng một điều kiện tìm sản phẩm có thể dùng cho:

- Trang đầu với giá tăng dần.
- Trang đầu với sản phẩm mới nhất.
- Trang tiếp theo với cùng thứ tự.
- Một danh sách gợi ý chỉ cần 5 kết quả.

Tách phần xây điều kiện khỏi phần cấu hình hiển thị giúp tái sử dụng query và tránh các màn hình có điều kiện tìm kiếm vô tình khác nhau.

## 3. Sắp xếp kết quả bằng Sort

### 3.1. Sort tăng dần và giảm dần

Spring Data Elasticsearch hỗ trợ kiểu `Sort` của Spring Data. Có thể đặt sort trực tiếp trong `Pageable`:

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "price");

Pageable pageable = PageRequest.of(0, 20, sort);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(pageable)
    .build();
~~~

Trong ví dụ, kết quả được sắp xếp theo `price` tăng dần. Để lấy giá cao trước:

~~~java
Sort sort = Sort.by(Sort.Direction.DESC, "price");
~~~

Sau đó thực thi bằng `operations.search(query, ProductDocument.class)`.

Có thể đọc nội dung và score từ kết quả:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();
    System.out.println(product.getPrice());
}
~~~

### 3.2. Khai báo nhiều tiêu chí sort

Khi nhiều document có cùng giá, có thể dùng tiêu chí thứ hai để xác định thứ tự:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.asc("name")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Elasticsearch áp dụng thứ tự sort theo danh sách khai báo:

1. So sánh giá tăng dần.
2. Nếu giá bằng nhau, so sánh tên tăng dần.

Với truy vấn có relevance score, nếu cần ưu tiên độ liên quan trước rồi mới dùng một field làm tie-breaker, hãy khai báo thứ tự sort phù hợp với ý định đó. Khi chỉ định field sort tường minh, đừng giả định score vẫn tự động là tiêu chí đầu tiên.

### 3.3. Dùng Sort độc lập trong NativeQuery

Một số phiên bản Spring Data Elasticsearch cho phép đặt sort trực tiếp trong builder của NativeQuery:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withSort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("productId")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Nếu đã truyền sort trong `Pageable`, không cần lặp lại cùng một sort trong builder. Chọn một nơi làm nguồn cấu hình thứ tự để tránh khó đọc hoặc xung đột. Chữ ký builder có thể thay đổi theo phiên bản Spring Data Elasticsearch; hãy kiểm tra dependency đang dùng nếu IDE không nhận overload.

### 3.4. Chọn field phù hợp để sort

Không phải field nào cũng có thể sort hiệu quả.

| Kiểu field | Khả năng sort thường dùng | Lưu ý |
|---|---|---|
| number | Có | Phù hợp cho giá, số lượng, điểm |
| date | Có | Phù hợp cho ngày tạo/cập nhật |
| keyword | Có | Phù hợp cho mã, trạng thái, tên đã chuẩn hóa |
| boolean | Có | Có thể dùng khi nghiệp vụ cần |
| text | Thường không phù hợp mặc định | Field được phân tích; cần keyword subfield hoặc field sort riêng |
| object/nested | Cần cấu hình riêng | Sort có thể cần nested sort path |

Ví dụ entity có multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Field `name` dùng cho full-text search, còn `name.keyword` phù hợp hơn cho exact sort. Khi dùng query DSL trực tiếp, có thể khai báo tên subfield cụ thể trong sort option. Nếu dùng Spring `Sort`, hãy xác nhận cách phiên bản thư viện ánh xạ property path sang field mapping; không mặc định mọi subfield đều được suy ra tự động.

### 3.5. Vì sao text field không nên sort trực tiếp?

Field `text` được analyzer tách thành token. Elasticsearch không lưu doc values cho text field theo cách thường dùng để sort. Bật fielddata trên text có thể tiêu tốn nhiều heap và gây áp lực bộ nhớ.

Với tên hoặc nhãn cần cả tìm kiếm toàn văn lẫn sort, thường dùng multi-field:

- `name` kiểu text cho match query.
- `name.keyword` kiểu keyword cho sort hoặc exact match.

Với dữ liệu cần sort thường xuyên, hãy thiết kế field chuyên dụng ngay từ đầu thay vì bật fielddata chỉ để giải quyết một lỗi sort.

### 3.6. Sort theo ngày và số

Ví dụ sort sản phẩm mới nhất:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt")
);
~~~

Ví dụ sort giá tăng dần, rồi số lượng tồn kho giảm dần:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.desc("stockQuantity")
);
~~~

Field date phải có mapping date phù hợp. Field số cần mapping numeric thay vì keyword chứa chuỗi số; nếu lưu số dưới dạng chuỗi, thứ tự từ điển có thể khác thứ tự số học, ví dụ `"100"` có thể đứng trước `"20"` khi so sánh chuỗi.

## 4. Sort nâng cao trong Elasticsearch Query DSL

### 4.1. Native sort options

Spring Data `Sort` bao phủ các nhu cầu phổ biến. Khi cần tùy chọn riêng của Elasticsearch như missing value, mode, nested sort hoặc unmapped type, có thể dùng native sort options của Elasticsearch Java API Client thông qua NativeQuery builder.

Ví dụ khái niệm về sort option:

~~~java
SortOptions priceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("price")
        .order(SortOrder.Asc)
        .missing("_last")
    )
);
~~~

Sau đó đưa sort option vào NativeQuery bằng overload `withSort` tương ứng với phiên bản Elasticsearch Java API Client:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withSort(priceSort)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Tên package/import và overload cụ thể phụ thuộc phiên bản client. Ý nghĩa cấu hình cần giữ nhất quán: field `price` tăng dần, document thiếu giá được đặt cuối danh sách.

### 4.2. Xử lý field bị thiếu

Một số document có thể không chứa field được sort. Elasticsearch có tùy chọn missing để đặt các document đó lên đầu hoặc cuối:

- `_first`: đưa giá trị thiếu lên đầu.
- `_last`: đưa giá trị thiếu xuống cuối.
- Giá trị cụ thể: dùng một giá trị thay thế theo query option hỗ trợ.

Nếu sort theo ngày tạo mà dữ liệu cũ thiếu `createdAt`, hãy quyết định vị trí của các document đó thay vì để hành vi mặc định làm thứ tự khó dự đoán.

### 4.3. Nested sort

Nếu sort dựa trên field trong object nested, cần khai báo nested path và quy tắc chọn giá trị từ các phần tử nested. Ví dụ một sản phẩm có nhiều offer và muốn sort theo giá offer nhỏ nhất.

Đây là trường hợp cần native sort options vì chỉ truyền tên property đơn giản thường chưa đủ để mô tả nested sort. Mapping của field phải là `nested`; nếu chỉ là `object`, ngữ nghĩa truy vấn và sort khác nhau.

### 4.4. Sort theo score

Relevance score thường phù hợp khi người dùng tìm nội dung. Nếu cần ưu tiên kết quả có score cao, có thể sắp xếp theo `_score` giảm dần và thêm field ổn định làm tiêu chí phụ.

Không nên dùng giá hoặc tên làm tiêu chí đầu tiên nếu mục tiêu chính là xếp hạng theo độ liên quan. Ngược lại, với màn hình danh mục sản phẩm không có truy vấn full-text, sort theo field nghiệp vụ thường hợp lý hơn.

### 4.5. Sort ổn định bằng tie-breaker

Nếu nhiều document có cùng giá hoặc cùng timestamp, thứ tự giữa chúng có thể thay đổi giữa các request nếu không có tiêu chí phụ duy nhất.

Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.asc("productId")
);
~~~

`productId` nên là field keyword có giá trị duy nhất và hỗ trợ sort. Điều này giúp kết quả có thứ tự xác định hơn khi chuyển trang.

Không mặc định dùng Elasticsearch `_id` làm field sort thông thường. Hãy lưu một field nghiệp vụ duy nhất có doc values nếu cần tie-breaker ổn định.

## 5. Phân trang với Pageable

### 5.1. PageRequest

`PageRequest` là implementation phổ biến của `Pageable`:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Các tham số:

- Tham số thứ nhất là page number, bắt đầu từ 0.
- Tham số thứ hai là page size, số phần tử tối đa trong một trang.

Ví dụ:

~~~java
Pageable firstPage = PageRequest.of(0, 20);
Pageable secondPage = PageRequest.of(1, 20);
Pageable thirdPage = PageRequest.of(2, 20);
~~~

Với page size 20, các trang offset tương ứng là 0, 20 và 40. Spring Data chuyển thông tin pageable thành from/size tương ứng trong request search theo API được sử dụng.

### 5.2. Kết hợp Pageable và Sort

Có thể truyền sort ngay khi tạo PageRequest:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"))
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(pageable)
    .build();
~~~

Đây là cách gọn khi sort và pagination thuộc cùng một yêu cầu hiển thị. Nếu sort phức tạp cần native options, cấu hình sort bằng API Elasticsearch tương ứng và chỉ dùng Pageable để biểu diễn page/size.

### 5.3. Tạo Pageable từ tham số API

Giả sử controller nhận page và size từ request. Không nên truyền trực tiếp giá trị bất kỳ của client vào PageRequest.

~~~java
public Pageable createPageable(int page, int size) {
    int safePage = Math.max(page, 0);
    int safeSize = Math.min(Math.max(size, 1), 100);

    return PageRequest.of(
        safePage,
        safeSize,
        Sort.by(Sort.Order.desc("createdAt"))
    );
}
~~~

Đoạn code đảm bảo page không âm và size nằm trong khoảng 1–100. Giới hạn cụ thể nên dựa trên kích thước document và tải cluster. API tìm kiếm công khai thường cần giới hạn size để một request không yêu cầu hàng nghìn document.

### 5.4. Đọc kết quả phân trang

Thực thi query:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(query, ProductDocument.class);
~~~

Nếu cần cấu trúc trang của Spring Data:

~~~java
SearchPage<ProductDocument> searchPage =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

Có thể lấy các thông tin:

~~~java
List<SearchHit<ProductDocument>> content =
    searchPage.getContent().getSearchHits();

long totalHits = searchPage.getTotalElements();
int pageNumber = searchPage.getNumber();
int pageSize = searchPage.getSize();
int totalPages = searchPage.getTotalPages();
boolean hasNext = searchPage.hasNext();
~~~

Tên method cụ thể trên `SearchPage`/`SearchHits` có thể khác theo phiên bản. Nếu chỉ cần dữ liệu, có thể lấy `searchHits.getSearchHits()` rồi map `SearchHit::getContent`.

### 5.5. Phân biệt Page, SearchHits và SearchPage

| Kiểu | Nội dung |
|---|---|
| `SearchHit<T>` | Một document cùng metadata của hit |
| `SearchHits<T>` | Danh sách hit và metadata tổng thể của response |
| `SearchPage<T>` | SearchHit content kết hợp thông tin phân trang |
| `Page<T>` | Abstraction trang phổ biến của Spring Data |

`SearchHits` hữu ích khi cần score, ID, highlight hoặc sort values. `SearchPage` giữ các metadata đó đồng thời cung cấp page metadata. `Page` thường phù hợp với API ứng dụng chỉ cần content và tổng số.

Không làm mất metadata quá sớm nếu giao diện cần relevance score hoặc highlight.

## 6. Giới hạn kết quả bằng page size

### 6.1. Lấy N kết quả đầu tiên

Nếu chỉ cần 5 gợi ý, tạo trang đầu có size 5:

~~~java
Pageable topFive = PageRequest.of(0, 5);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless")
    ))
    .withPageable(topFive)
    .build();
~~~

Cách này giới hạn số hit trả về cho request. Elasticsearch vẫn đánh giá query trên tập dữ liệu phù hợp để xác định kết quả đứng đầu theo sort/relevance.

### 6.2. Limit không phải total hits

Giả sử query phù hợp với 3.000 document, nhưng page size là 10:

- Response hiện tại chứa tối đa 10 hit.
- Tổng số hit có thể là 3.000 nếu total-hit tracking cung cấp con số đầy đủ.
- Các document còn lại được lấy ở những trang tiếp theo.

Không dùng kích thước danh sách trả về làm tổng số kết quả. Ngược lại, không cần tải hết 3.000 document về chỉ để hiển thị con số tổng.

### 6.3. Chỉ lấy một hit khi cần kiểm tra có kết quả

Nếu chỉ cần biết query có kết quả hay không, không cần tải một trang lớn:

~~~java
Pageable oneResult = PageRequest.of(0, 1);

Query query = NativeQuery.builder()
    .withQuery(q -> q.term(t -> t
        .field("category")
        .value("ACCESSORY")
    ))
    .withPageable(oneResult)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);

boolean hasAny = !hits.getSearchHits().isEmpty();
~~~

Nếu chỉ cần số lượng chính xác hoặc kiểm tra tồn tại theo điều kiện, có thể dùng API count thay vì search; điều này tránh tải source document.

### 6.4. Không dùng unbounded result cho màn hình thông thường

`Pageable.unpaged()` hoặc query không giới hạn page size có thể khiến ứng dụng lấy quá nhiều dữ liệu. Với index lớn, điều này gây tăng bộ nhớ, thời gian serialization và tải mạng.

Hãy đặt page size mặc định và tối đa tại tầng service. Với tác vụ export toàn bộ dữ liệu, dùng cơ chế duyệt batch chuyên biệt thay vì bỏ giới hạn trong một request search.

## 7. Giới hạn from/size và deep pagination

### 7.1. Cơ chế from/size

Phân trang truyền thống của Elasticsearch sử dụng hai giá trị:

- `from`: số hit bỏ qua trước khi bắt đầu lấy kết quả.
- `size`: số hit tối đa cần trả về.

Ví dụ trang 3 với size 20 có offset 60 và size 20. Mỗi shard có thể cần giữ và xử lý các kết quả trung gian để coordinator tổng hợp thứ tự toàn cục.

Khi offset tăng lớn, chi phí bộ nhớ và xử lý tăng theo. Vì vậy Elasticsearch đặt giới hạn result window; giá trị mặc định phổ biến là 10.000 hit cho `from + size`.

### 7.2. Không tăng max_result_window tùy tiện

Có thể thay đổi `index.max_result_window` ở cấp index, nhưng tăng giới hạn không làm deep pagination trở nên rẻ. Nó có thể khiến mỗi request tiêu thụ nhiều tài nguyên hơn và gây áp lực lên heap/cluster.

Trước khi tăng giới hạn, hãy xác định:

- Người dùng có thật sự cần đi tới trang rất sâu không?
- Có thể lọc hẹp hơn không?
- Có thể sắp xếp theo tiêu chí ổn định và dùng search_after không?
- Có thể dùng export/batch API thay cho phân trang giao diện không?

Với màn hình người dùng, thường nên giới hạn số trang hoặc khuyến khích lọc cụ thể hơn.

### 7.3. Dùng search_after cho tập dữ liệu lớn

`search_after` cho phép tiếp tục tìm kiếm sau sort values của hit cuối trang trước. Cách này tránh offset lớn và phù hợp với luồng duyệt tuần tự.

Ví dụ request Elasticsearch:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 100,
  "sort": [
    { "createdAt": "asc" },
    { "productId": "asc" }
  ],
  "query": {
    "match_all": {}
  },
  "search_after": [
    "2026-01-15T10:00:00Z",
    "P1001"
  ]
}
~~~

Giá trị trong `search_after` phải lấy từ sort values của hit cuối cùng ở trang trước, theo đúng thứ tự các field sort. Không tự tính hoặc đoán cursor từ dữ liệu ứng dụng.

Sort phải xác định thứ tự ổn định. Nếu hai document có cùng giá trị sort và không có tie-breaker duy nhất, có thể bỏ sót hoặc lặp kết quả giữa các trang.

### 7.4. Point-in-time để giữ góc nhìn ổn định

Nếu dữ liệu thay đổi trong khi ứng dụng duyệt nhiều trang, tập kết quả có thể thay đổi giữa các request. Point-in-time (PIT) giúp giữ một góc nhìn nhất quán trong một khoảng thời gian.

Quy trình khái niệm:

1. Mở PIT cho index/alias cần tìm.
2. Gửi search đầu tiên với PIT và sort ổn định.
3. Lấy sort values từ hit cuối cùng.
4. Gửi trang tiếp theo với cùng PIT và search_after.
5. Tiếp tục đến khi hết kết quả.
6. Đóng PIT khi hoàn thành hoặc để hết thời hạn giữ theo chính sách.

PIT tiêu tốn tài nguyên và cần keep-alive hợp lý. Không mở PIT rồi giữ vô thời hạn. Hãy xử lý trường hợp PIT hết hạn và tạo lại phiên tìm kiếm theo chiến lược ứng dụng.

### 7.5. Search after và NativeQuery

Các phiên bản Spring Data Elasticsearch hỗ trợ query cursor có thể cung cấp API để gắn search-after values vào NativeQuery. Tên method và kiểu giá trị phụ thuộc phiên bản. Khi dùng, cần:

- Giữ sort options giống nhau giữa các trang.
- Truyền chính xác sort values từ hit cuối trang trước.
- Giữ cùng điều kiện query.
- Dùng PIT khi cần snapshot ổn định.
- Không trộn offset pagination với cursor pagination trong cùng luồng nếu không có thiết kế rõ ràng.

Nếu abstraction của phiên bản dự án chưa hỗ trợ PIT/search_after đầy đủ, có thể dùng Elasticsearch Java API Client trực tiếp cho phần duyệt dữ liệu sâu.

## 8. Relevance score và sort nghiệp vụ

### 8.1. Sort mặc định theo relevance

Với match query, Elasticsearch thường dùng relevance score để xếp hạng kết quả. Tài liệu phù hợp hơn thường có score cao hơn, tùy thuật toán và cấu hình.

Nếu thêm sort theo giá, thứ tự có thể chuyển thành giá trước, thay vì relevance. Đây là thay đổi về ý nghĩa sản phẩm, không chỉ là tối ưu kỹ thuật.

### 8.2. Kết hợp score với field

Nếu muốn ưu tiên relevance rồi dùng giá làm tie-breaker, cấu hình thứ tự sort tương ứng. Với native sort options, có thể sort theo `_score` giảm dần rồi theo field nghiệp vụ.

Ví dụ DSL:

~~~json
{
  "sort": [
    { "_score": "desc" },
    { "price": "asc" },
    { "productId": "asc" }
  ]
}
~~~

Nếu yêu cầu là sản phẩm rẻ nhất trước bất kể độ liên quan, hãy sort theo giá. Nếu yêu cầu là kết quả phù hợp nhất trước, hãy giữ score ở vị trí ưu tiên. Hãy thống nhất hành vi này với UX và kiểm thử bằng truy vấn đại diện.

### 8.3. Sort theo giá trị tính toán

Một số ứng dụng cần sort theo giá trị script hoặc công thức kết hợp nhiều field. Elasticsearch hỗ trợ script sort, nhưng loại này có thể tốn kém và cần kiểm soát script.

Trước khi dùng script sort, xem xét có thể tính trước field trong lúc ghi document hay không. Một field được lưu sẵn thường dễ sort và tối ưu hơn việc tính lại trên từng hit.

## 9. Sort, pagination và multi-index

### 9.1. Sort trên nhiều index

Khi search qua alias hoặc nhiều index, các field sort cần có mapping tương thích. Nếu index cũ khai báo `price` là keyword nhưng index mới khai báo numeric, sort có thể lỗi hoặc cho thứ tự không mong đợi.

Với migration theo phiên bản, cần thống nhất field type hoặc cấu hình unmapped type phù hợp nếu có field thiếu ở một index. Đừng giả định chỉ vì tên field giống nhau thì mapping cũng giống nhau.

### 9.2. Field không tồn tại trong một số index

Một alias có thể trỏ đến nhiều index với schema khác nhau. Nếu sort field không tồn tại ở một index, cần quyết định cách xử lý field thiếu/unmapped theo query option phù hợp.

Giải pháp bền vững là giữ mapping tương thích giữa các index mà cùng một query nhắm tới. Unmapped type chỉ nên dùng khi hiểu rõ dữ liệu và kiểu sort.

### 9.3. Sort và refresh

Khi document mới được index hoặc field sort được cập nhật, kết quả search có thể phản ánh thay đổi sau refresh. Nếu người dùng chuyển trang trong lúc dữ liệu thay đổi, thứ tự và vị trí có thể dịch chuyển.

Với giao diện thông thường, điều này thường chấp nhận được. Với export hoặc xử lý tuần tự cần tính nhất quán, dùng PIT cùng search_after phù hợp hơn.

## 10. Ví dụ hoàn chỉnh trong Service

### 10.1. Xây dựng query có sort và pagination

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchPage<ProductDocument> search(
            String keyword,
            int requestedPage,
            int requestedSize) {

        int page = Math.max(requestedPage, 0);
        int size = Math.min(Math.max(requestedSize, 1), 50);

        Sort sort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("productId")
        );

        Pageable pageable = PageRequest.of(page, size, sort);

        Query query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                    .field("name")
                    .query(keyword)
                ))
                .filter(f -> f.term(t -> t
                    .field("available")
                    .value(true)
                ))
            ))
            .withPageable(pageable)
            .build();

        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        return SearchHitSupport.searchPageFor(hits, pageable);
    }
}
~~~

Ví dụ minh họa quy trình chung. Entity cần có field `createdAt` và `productId` được mapping theo kiểu hỗ trợ sort. Nếu dùng tên field khác trong Elasticsearch, hãy điều chỉnh sort field theo mapping thực tế và API converter của phiên bản.

### 10.2. Chuyển kết quả sang DTO

~~~java
public record ProductResult(
    String id,
    String name,
    float score
) {
}

public record ProductPageResponse(
    List<ProductResult> items,
    long totalHits,
    int page,
    int size,
    int totalPages
) {
}
~~~

Chuyển đổi:

~~~java
public ProductPageResponse toResponse(
        SearchPage<ProductDocument> searchPage) {

    List<ProductResult> items = searchPage.getContent()
        .getSearchHits()
        .stream()
        .map(hit -> new ProductResult(
            hit.getId(),
            hit.getContent().getName(),
            hit.getScore()
        ))
        .toList();

    return new ProductPageResponse(
        items,
        searchPage.getTotalElements(),
        searchPage.getNumber(),
        searchPage.getSize(),
        searchPage.getTotalPages()
    );
}
~~~

DTO giúp controller không phụ thuộc trực tiếp vào các kiểu kết quả nội bộ của Spring Data. Nếu chỉ cần content, có thể bỏ score khỏi DTO.

### 10.3. Endpoint cần giới hạn page size

Khi nhận tham số từ client, service nên áp dụng giới hạn tối đa như ví dụ trên. Controller cũng có thể validate input để trả lỗi 400 khi page/size không hợp lệ, thay vì âm thầm sửa mọi giá trị. Quyết định này phụ thuộc hợp đồng API; điều quan trọng là không cho phép client yêu cầu một lượng kết quả tùy ý.

## 11. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Sort theo tên báo lỗi hoặc tốn heap | Field là text, không có doc values phù hợp | Dùng keyword subfield hoặc field sort riêng |
| Sort theo số cho thứ tự sai | Giá trị được lưu dưới dạng keyword/string | Sửa mapping thành numeric và lập chỉ mục lại khi cần |
| Trang sau lặp hoặc thiếu document | Thứ tự sort không ổn định khi có giá trị trùng | Thêm tie-breaker duy nhất |
| Không lấy được trang sâu | Vượt index.max_result_window | Dùng search_after/PIT hoặc giới hạn trang |
| Page size quá lớn gây chậm | Request tải nhiều document/source | Giảm limit, dùng source filtering hoặc batch |
| Tổng hit khác số hit trong trang | Total hits là tổng phù hợp; danh sách chỉ là một trang | Dùng đúng metadata total và page content |
| Kết quả đổi thứ tự giữa các trang | Dữ liệu thay đổi hoặc sort thiếu ổn định | Thêm tie-breaker; dùng PIT nếu cần snapshot |
| Sort theo nested field không đúng | Thiếu nested path hoặc nested sort mode | Dùng native sort options và mapping nested |
| Alias nhiều index gây sort lỗi | Mapping field không tương thích | Đồng bộ schema hoặc xử lý unmapped type có chủ đích |
| Score không còn là ưu tiên | Đã thêm sort nghiệp vụ lên trước _score | Xem lại thứ tự sort theo yêu cầu relevance |
| Search bị từ chối vì query nặng | Script sort hoặc query tốn kém bị cluster policy chặn | Đo tải và cân nhắc tính trước field sort |

Khi debug, hãy kiểm tra request DSL cuối cùng và mapping thực tế trên cluster. Đừng chỉ nhìn object Pageable trong Java rồi kết luận Elasticsearch đã nhận đúng sort/offset/size.

## 12. Kiểm thử sort, pagination và limit

### 12.1. Tạo dữ liệu có giá trị trùng

Để kiểm tra sort, nên có nhiều document cùng giá hoặc cùng timestamp. Nếu mọi dữ liệu mẫu có giá trị khác nhau, test sẽ không phát hiện được vấn đề tie-breaker.

Ví dụ:

| ID | Giá | Ngày tạo |
|---|---:|---|
| P1001 | 49.90 | 2026-01-10 |
| P1002 | 49.90 | 2026-01-10 |
| P1003 | 29.90 | 2026-01-12 |
| P1004 | 79.90 | 2026-01-09 |

Kiểm tra giá tăng dần và productId tăng dần khi giá bằng nhau.

### 12.2. Kiểm tra giới hạn kết quả

Với page size 2, xác nhận:

- Trang đầu có tối đa 2 hit.
- Trang tiếp theo có các ID tiếp theo theo cùng sort.
- Không có ID bị lặp giữa các trang trong một tập dữ liệu không thay đổi.
- Tổng hit không bị nhầm với số phần tử hiện tại.

### 12.3. Kiểm tra field sort

Thử sort trên:

- Numeric field.
- Date field.
- Keyword field.
- Text field và keyword subfield tương ứng.
- Field bị thiếu.
- Nested field nếu ứng dụng sử dụng.

Test cần chạy với Elasticsearch tương thích để xác minh mapping và query thực tế. Mock ElasticsearchOperations chỉ kiểm tra cách service gọi API, không chứng minh sort hoạt động đúng trên cluster.

### 12.4. Kiểm tra deep pagination

Nếu ứng dụng dùng search_after, kiểm tra:

1. Trang đầu lấy sort values từ hit cuối.
2. Trang tiếp theo dùng đúng sort values đó.
3. Không thay đổi query/sort giữa các trang.
4. Cursor hết hạn được xử lý.
5. PIT được đóng hoặc hết hạn theo kế hoạch.
6. Không lặp hoặc bỏ sót document trong tập dữ liệu ổn định.

## 13. Quy trình chọn cách phân trang

Có thể chọn chiến lược theo quy mô và trải nghiệm cần cung cấp:

| Tình huống | Cách tiếp cận |
|---|---|
| Danh sách ngắn, vài trang | Pageable với from/size |
| Trang đầu/autocomplete | Page size nhỏ, sort phù hợp |
| Người dùng cần tổng số trang | SearchPage/Page hoặc total hits được theo dõi |
| Không cần tổng chính xác | Chỉ lấy content và thông tin có trang tiếp theo nếu API hỗ trợ |
| Duyệt dữ liệu rất lớn | search_after và sort ổn định |
| Export cần góc nhìn ổn định | PIT kết hợp search_after |
| Cần sort đặc biệt | Native sort options |
| Tìm nội dung cần relevance | Giữ sort theo score hoặc kết hợp score với tie-breaker |

Không nên dùng một cơ chế cho mọi trường hợp. Pageable đơn giản và dễ tích hợp với UI, còn search_after phù hợp hơn với việc duyệt tuần tự qua tập dữ liệu lớn.

## 14. Những điểm cần ghi nhớ

- `NativeQuery` cho phép kết hợp Query DSL với các tùy chọn sort và pagination của Spring Data.
- `Sort` mô tả thứ tự một hoặc nhiều field; thứ tự các tiêu chí quyết định ưu tiên.
- Field sort cần mapping phù hợp: numeric, date và keyword thường phù hợp; text thường cần keyword subfield.
- `Pageable` biểu diễn page number, page size và có thể cả sort.
- Page index bắt đầu từ 0; page size là số hit tối đa cho trang hiện tại.
- Limit không phải tổng số document phù hợp với query.
- Sort cần tie-breaker ổn định khi giá trị chính có thể trùng.
- from/size phù hợp với phân trang nông; deep pagination nên cân nhắc search_after và PIT.
- Không tăng max_result_window hoặc page size tùy tiện để xử lý dữ liệu lớn.
- Luôn kiểm tra query DSL, mapping và hành vi trên Elasticsearch thật hoặc test container.
- Chữ ký builder/native sort có thể thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client; hãy kiểm tra dependency dự án trước khi áp dụng.

Khi cấu hình đúng sort, pagination và limit, ứng dụng có thể trả kết quả theo thứ tự nghiệp vụ, giữ kích thước response trong giới hạn và duyệt dữ liệu lớn theo cách phù hợp với khả năng của Elasticsearch.
