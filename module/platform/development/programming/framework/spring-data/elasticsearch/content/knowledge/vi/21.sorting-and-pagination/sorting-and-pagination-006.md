# Chỉ số trang, kích thước trang và ánh xạ from, size

Phân trang chia một tập kết quả lớn thành các phần nhỏ để API hoặc giao diện chỉ tải số document cần hiển thị. Trong Spring Data Elasticsearch, ứng dụng thường biểu diễn yêu cầu phân trang bằng Pageable, chẳng hạn PageRequest. Elasticsearch nhận hai giá trị tương ứng là from và size: from là vị trí bắt đầu trong tập kết quả đã sắp xếp, còn size là số hit tối đa cần trả về.

Chỉ số trang của Spring Data bắt đầu từ 0. Vì vậy trang đầu tiên có page = 0, trang thứ hai có page = 1. Với kích thước trang cố định, công thức ánh xạ là from = pageNumber × pageSize và size = pageSize. Ví dụ page 3 với size 20 tương ứng from = 60, size = 20.

Phân trang from/size phù hợp cho các trang kết quả nông, nơi người dùng cần chuyển qua lại một số trang đầu. Elasticsearch giới hạn tổng cửa sổ kết quả mặc định ở 10.000 document thông qua index.max_result_window. Với dữ liệu lớn hoặc cần duyệt sâu, nên dùng search_after, thường kết hợp Point In Time (PIT), thay vì tăng from vô hạn.

## 1. Vì sao cần phân trang?

Giả sử index products có 50.000 document. Nếu API trả toàn bộ kết quả trong một response, ứng dụng phải:

- Đọc và chuyển đổi nhiều document hơn nhu cầu của màn hình.
- Dùng nhiều bộ nhớ ở Elasticsearch, server ứng dụng và client.
- Truyền response lớn qua mạng.
- Làm thời gian phản hồi tăng.
- Tăng tải cho các shard và coordinating node.

Phân trang giới hạn số hit trong một response:

~~~text
Tập kết quả đã sắp xếp:  [ 1 ... 1000 ... 50000 ]

Trang 0, size 20:         [ 1 ............... 20 ]
Trang 1, size 20:         [ 21 .............. 40 ]
Trang 2, size 20:         [ 41 .............. 60 ]
...
~~~

API thường nhận page và size từ query parameter:

~~~http
GET /products?page=0&size=20
GET /products?page=1&size=20
GET /products?page=2&size=20
~~~

Mỗi request chỉ trả một phần kết quả. API có thể cung cấp thêm metadata như page number, page size, total elements, total pages, hasNext và hasPrevious.

## 2. Phân biệt page number, offset và size

Ba khái niệm cần tách biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---:|
| pageNumber | Chỉ số trang trong Spring Data, bắt đầu từ 0 | 3 |
| pageSize | Số phần tử tối đa trong một trang | 20 |
| offset | Số phần tử bỏ qua trước khi lấy trang hiện tại | 60 |

Với phân trang từ đầu tập kết quả:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Elasticsearch dùng tên tham số from thay cho offset:

\[
\text{from} = \text{offset}, \qquad \text{size} = \text{pageSize}
\]

Ví dụ:

| Spring Data page | Spring Data size | Elasticsearch from | Elasticsearch size |
|---:|---:|---:|---:|
| 0 | 20 | 0 | 20 |
| 1 | 20 | 20 | 20 |
| 2 | 20 | 40 | 20 |
| 3 | 20 | 60 | 20 |
| 4 | 20 | 80 | 20 |

Page number không phải offset. Nếu API nhận page = 3, size = 20 thì from là 60, không phải 3.

## 3. Chỉ số trang của Spring Data bắt đầu từ 0

Spring Data dùng chỉ số trang zero-based:

- Trang đầu tiên: pageNumber = 0.
- Trang thứ hai: pageNumber = 1.
- Trang thứ ba: pageNumber = 2.

PageRequest tạo Pageable:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Đây là trang đầu tiên với tối đa 20 kết quả.

~~~java
Pageable pageable = PageRequest.of(2, 20);
~~~

Đây là trang thứ ba. Offset được tính là 2 × 20 = 40.

Nếu giao diện đánh số trang từ 1, cần chuyển đổi ở biên API:

~~~java
int springPage = requestedPage - 1;
Pageable pageable = PageRequest.of(springPage, pageSize);
~~~

Chỉ thực hiện phép trừ khi hợp đồng API thực sự nhận page bắt đầu từ 1. Không trộn lẫn quy ước page zero-based của Spring với page one-based của giao diện.

## 4. Kích thước trang và giới hạn đầu vào

Page size là số document tối đa ứng dụng muốn nhận trong một response. Giá trị quá lớn làm response nặng và tăng công việc của Elasticsearch; giá trị quá nhỏ làm client phải gửi nhiều request.

API nên đặt giới hạn:

- page không được âm.
- size phải lớn hơn 0.
- size có giới hạn tối đa do ứng dụng quy định.
- Không chấp nhận page/size vượt phạm vi kiểu dữ liệu hoặc gây overflow khi tính offset.

Ví dụ validation ở controller:

~~~java
@GetMapping
public Page<Product> findProducts(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    if (page < 0) {
        throw new IllegalArgumentException("page must be zero or greater");
    }

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size must be between 1 and 100");
    }

    return productService.findProducts(PageRequest.of(page, size));
}
~~~

Giới hạn 100 chỉ là ví dụ chính sách API. Hệ thống thực tế cần chọn theo kích thước document, latency mục tiêu, số shard và tải cluster.

### 4.1. Tại sao không cho client yêu cầu size tùy ý?

Nếu client gửi size = 100000, ứng dụng có thể tạo response lớn, tăng heap và làm cluster chịu tải cao. Một client lỗi hoặc cố ý lạm dụng có thể tạo nhiều request tốn tài nguyên.

Đặt default và max size ở server. Không dựa vào giao diện để bảo đảm giới hạn vì API có thể được gọi trực tiếp.

### 4.2. Kiểm tra offset an toàn

PageRequest lưu offset dưới dạng long. Tuy nhiên, Elasticsearch from/size có giới hạn thực tế và bị ràng buộc bởi max_result_window. Không nên để phép tính page × size tràn số hoặc tạo offset quá lớn:

~~~java
long offset = (long) page * size;

if (offset + size > MAX_ALLOWED_WINDOW) {
    throw new IllegalArgumentException(
            "Requested page exceeds the supported result window");
}
~~~

Đây là validation theo chính sách ứng dụng. MAX_ALLOWED_WINDOW nên phù hợp với cấu hình index và chiến lược pagination; không nên chỉ kiểm tra kiểu số rồi cho phép mọi offset.

## 5. Ánh xạ Pageable sang Elasticsearch from và size

Spring Data Elasticsearch dùng Pageable trên Query để truyền thông tin phân trang xuống Elasticsearch. Từ Pageable, framework có thể suy ra:

- Offset để đặt from.
- Page size để đặt size.
- Sort để xây phần sort của search request.

Ví dụ trực tiếp với Query:

~~~java
Pageable pageable = PageRequest.of(2, 20);

CriteriaQuery query = new CriteriaQuery(
        Criteria.where("category").is("accessories"));
query.setPageable(pageable);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

Với page = 2 và size = 20, request search tương ứng lấy từ vị trí 40 và tối đa 20 hit. Spring Data xử lý việc chuyển Pageable thành tham số search request.

### 5.1. NativeQuery với Pageable

Nếu dùng NativeQuery để viết Query DSL:

~~~java
Pageable pageable = PageRequest.of(1, 10);

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .term(t -> t
                        .field("category")
                        .value("accessories")))
        .withPageable(pageable)
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

Pageable được gắn vào query. Không cần tự viết from và size trong raw JSON nếu đã dùng withPageable.

### 5.2. Không đặt Pageable hai lần

Tránh vừa gọi query.setPageable(pageable), vừa cấu hình một from/size khác trong native query. Hai nguồn pagination có thể xung đột hoặc làm người đọc khó xác định giá trị thực tế được gửi.

Chọn một cách nhất quán: dùng Pageable của Spring Data, hoặc dùng low-level request với from/size khi thật sự cần kiểm soát trực tiếp.

## 6. Dùng Pageable trong Repository

Repository query method có thể nhận Pageable để phân trang:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Page<Product> findByCategory(String category, Pageable pageable);
}
~~~

Service:

~~~java
public Page<Product> findByCategory(
        String category,
        int page,
        int size) {

    Pageable pageable = PageRequest.of(page, size);
    return repository.findByCategory(category, pageable);
}
~~~

Spring Data tạo query theo tên method, gắn pagination từ Pageable và chuyển kết quả về kiểu Page.

### 6.1. Sort trong Pageable

PageRequest có thể nhận Sort:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("category"),
                Sort.Order.desc("price")));
~~~

Elasticsearch nhận sort theo thứ tự field đã khai báo. Kết quả trang được xác định sau khi áp dụng sort, vì vậy sort phải nhất quán giữa các request trang.

### 6.2. Service không nên tự tạo PageRequest từ tham số chưa validate

Nếu nhiều controller dùng chung service, hãy validate page và size ở một nơi thống nhất, ví dụ request DTO, argument resolver hoặc service boundary. Không để mỗi endpoint có một max size khác nhau ngoài ý muốn.

## 7. Dùng Page, List và SearchHits

Các kiểu kết quả khác nhau cung cấp mức metadata khác nhau:

| Kiểu trả về | Nội dung | Metadata phân trang |
|---|---|---|
| List<T> | Các entity trong trang | Không chứa total/page metadata |
| Page<T> | Content và metadata trang | Page number, size, total elements, total pages |
| SearchHits<T> | SearchHit gồm content và metadata hit | Có total hits, score và thông tin search |
| SearchPage<T> | SearchHits kết hợp Pageable | Có search metadata và page metadata |

Nếu API chỉ cần trả danh sách, List có thể đủ. Nếu UI cần tổng số trang hoặc nút next/previous dựa trên tổng phần tử, Page phù hợp hơn.

Nếu cần score, highlight hoặc sort values của từng hit, dùng SearchHits/SearchPage để giữ metadata Elasticsearch.

### 7.1. Page không chỉ là List

Page chứa:

- getContent(): các phần tử hiện tại.
- getNumber(): chỉ số trang zero-based.
- getSize(): kích thước trang.
- getNumberOfElements(): số phần tử thực tế trong trang hiện tại.
- getTotalElements(): tổng số phần tử.
- getTotalPages(): tổng số trang.
- hasNext(): còn trang tiếp theo hay không.
- hasPrevious(): có trang trước hay không.
- isFirst()/isLast(): vị trí trang.

Trang cuối thường có ít phần tử hơn page size. Ví dụ tổng cộng 43 document, size = 20 thì các trang có lần lượt 20, 20 và 3 phần tử.

### 7.2. Tạo Page từ SearchHits khi cần

Khi dùng ElasticsearchOperations trực tiếp, có thể lấy SearchHits rồi tạo PageImpl:

~~~java
public Page<Product> search(
        Query query,
        Pageable pageable) {

    SearchHits<Product> searchHits = operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));

    List<Product> content = searchHits.getSearchHits().stream()
            .map(SearchHit::getContent)
            .toList();

    return new PageImpl<>(
            content,
            pageable,
            searchHits.getTotalHits());
}
~~~

Query cần được cấu hình Pageable trước khi gọi operations:

~~~java
query.setPageable(pageable);
~~~

PageImpl nhận tổng số phần tử từ SearchHits. Tuy nhiên, độ chính xác của total hits phụ thuộc cấu hình track_total_hits và phản hồi Elasticsearch. Không nên mặc định total hits luôn là con số chính xác không giới hạn.

## 8. Tính tổng trang và trang cuối

Nếu totalElements = 43 và pageSize = 20:

\[
\text{totalPages} =
\left\lceil \frac{\text{totalElements}}{\text{pageSize}} \right\rceil
= 3
\]

Các trang:

| Page | From | Size | Kết quả |
|---:|---:|---:|---|
| 0 | 0 | 20 | 20 phần tử |
| 1 | 20 | 20 | 20 phần tử |
| 2 | 40 | 20 | 3 phần tử |

Nếu totalElements = 40 và size = 20 thì totalPages = 2, trang hợp lệ là 0 và 1. Không tồn tại trang 2 có content rỗng trong phạm vi kết quả hiện tại.

Nếu totalElements = 0, totalPages = 0. Page number yêu cầu vẫn có thể là 0 nhưng không có content.

### 8.1. Công thức tổng quát

Với totalElements = N và pageSize = S, nếu S > 0:

\[
\text{totalPages} = \left\lceil \frac{N}{S} \right\rceil
\]

Spring Data Page cung cấp getTotalPages() để không cần tự tính ở service.

### 8.2. Page cuối có thể không đầy

Không giả định số phần tử trong content luôn bằng pageSize. Chỉ getSize() biểu diễn kích thước trang được yêu cầu; getNumberOfElements() là số phần tử thực tế trong response.

## 9. Tính next và previous

API có thể trả metadata:

~~~json
{
  "page": 1,
  "size": 20,
  "numberOfElements": 20,
  "totalElements": 43,
  "totalPages": 3,
  "first": false,
  "last": false,
  "hasNext": true,
  "hasPrevious": true
}
~~~

Đây là ví dụ DTO; nội dung content có thể được đặt ở field riêng.

Giao diện có thể dùng:

- hasPrevious để bật/tắt nút Previous.
- hasNext để bật/tắt nút Next.
- totalPages để hiển thị tổng số trang nếu total chính xác.
- number để xác định trang hiện tại.

Không tự tính hasNext bằng cách so page với một giá trị hard-code. Dùng metadata Page hoặc cursor response phù hợp.

## 10. Sort ổn định giữa các trang

Phân trang from/size phải có thứ tự kết quả xác định. Nếu sort theo field không duy nhất, nhiều document có thể có cùng giá trị sort. Elasticsearch có thể trả các document đồng hạng theo thứ tự không ổn định giữa các request.

Ví dụ chỉ sort theo category:

~~~java
Sort sort = Sort.by(Sort.Order.asc("category"));
~~~

Nhiều sản phẩm có thể cùng category. Khi dữ liệu thay đổi hoặc shard trả kết quả theo thứ tự khác, document có thể xuất hiện ở hai trang hoặc bị bỏ sót.

Nên thêm một field sort có tính duy nhất để làm tie-breaker:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("category"),
        Sort.Order.asc("sku"));
~~~

Ở đây sku cần được mapping thành keyword và bảo đảm duy nhất trong tập kết quả. Không nên mặc định sort trực tiếp trên Elasticsearch _id; field _id không được thiết kế như một field sort thông thường. Nếu cần tie-breaker, lưu một field keyword phù hợp trong _source.

### 10.1. Field nào có thể sort?

Các field thường phù hợp:

- keyword.
- numeric như integer, long, double.
- date.
- boolean.

Field text thường được phân tích thành token và không phù hợp để sort trực tiếp. Nếu cần vừa full-text search vừa sort, mapping có thể dùng multi-field:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

Sort theo name.keyword thay vì name text:

~~~java
Sort sort = Sort.by(Sort.Order.asc("name.keyword"));
~~~

Tên field phải khớp mapping thực tế. Spring Data field name và Elasticsearch field name có thể khác nếu entity dùng @Field(name = "...").

### 10.2. Tie-breaker không loại bỏ mọi pagination drift

Sort ổn định giúp kết quả có thứ tự xác định khi dữ liệu không đổi. Nếu document được thêm, xóa hoặc thay đổi sort field giữa hai request trang, vị trí kết quả vẫn có thể dịch chuyển. Để duyệt một snapshot ổn định trên tập dữ liệu lớn, dùng PIT kết hợp search_after.

## 11. Ánh xạ from và size trong Elasticsearch DSL

Một search request tương đương với page = 2, size = 10:

~~~http
GET products/_search
{
  "from": 20,
  "size": 10,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "sku": "asc"
    }
  ]
}
~~~

Ý nghĩa:

- Elasticsearch bỏ qua 20 hit đầu theo thứ tự sort.
- Trả tối đa 10 hit tiếp theo.
- Sort được áp dụng trước khi lấy cửa sổ from/size.

Nếu bỏ sort, Elasticsearch vẫn trả kết quả nhưng thứ tự không nên được coi là hợp đồng ổn định cho phân trang.

### 11.1. from không phải số document được tải từ mỗi shard

Elasticsearch phân phối search tới các shard. Mỗi shard có thể cần tìm và giữ các candidate tương ứng với from + size trước khi coordinating node hợp nhất kết quả. Vì vậy chi phí tăng khi from lớn, ngay cả khi response chỉ trả size hit.

Ví dụ from = 9000, size = 20 có thể yêu cầu xử lý một cửa sổ 9020 hit trên mỗi shard liên quan, rồi coordinator chọn phần kết quả đúng.

Đây là lý do deep offset pagination đắt hơn việc chỉ nhìn vào số hit trả về.

## 12. Giới hạn max_result_window

Elasticsearch đặt index.max_result_window mặc định là 10.000. Điều kiện thường được hiểu là from + size không được vượt quá cửa sổ cho phép.

Ví dụ với size = 20:

| Page | From | From + size | Mặc định |
|---:|---:|---:|---|
| 0 | 0 | 20 | Hợp lệ |
| 100 | 2000 | 2020 | Hợp lệ |
| 400 | 8000 | 8020 | Hợp lệ |
| 499 | 9980 | 10000 | Vừa giới hạn |
| 500 | 10000 | 10020 | Vượt giới hạn |

Request vượt giới hạn thường trả lỗi kết quả cửa sổ quá lớn (result window is too large).

Kiểm tra setting:

~~~http
GET products/_settings?filter_path=*.settings.index.max_result_window
~~~

Có thể tăng setting:

~~~http
PUT products/_settings
{
  "index": {
    "max_result_window": 20000
  }
}
~~~

Nhưng tăng giới hạn không làm deep pagination trở nên miễn phí. Nó cho phép request tốn tài nguyên hơn và có thể làm tăng memory pressure trên shard/coordinator. Chỉ tăng khi đã đo tải và có giới hạn API phù hợp.

### 12.1. Không giải quyết deep pagination bằng cách chỉ tăng setting

Nếu sản phẩm cần người dùng chuyển đến trang thứ 50.000, from/size không phải chiến lược phù hợp. Chọn:

- search_after cho duyệt tuần tự.
- PIT + search_after khi cần snapshot ổn định.
- Scroll cho batch processing/đọc toàn bộ tập dữ liệu theo luồng công việc, không phải UI pagination tương tác thông thường.

## 13. Total hits và độ chính xác của totalElements

Page thường cần tổng số phần tử để tính totalPages. Elasticsearch có thể giới hạn việc đếm total hits để giảm chi phí. Trong search response, total hits có thể có relation:

| Relation | Ý nghĩa |
|---|---|
| eq | Tổng số hit được đếm chính xác |
| gte | Tổng số hit ít nhất bằng giá trị trả về |

Ví dụ response:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    }
  }
}
~~~

Điều này có nghĩa số lượng kết quả ít nhất là 10.000; không thể kết luận chính xác tổng số là 10.000.

Nếu API cần tổng chính xác, Elasticsearch hỗ trợ track_total_hits để yêu cầu đếm chính xác hơn. Việc này có thể tăng chi phí search, đặc biệt với query rộng và index lớn.

### 13.1. Page total có thể là ước lượng hoặc lower bound

Khi chuyển SearchHits thành PageImpl, đừng tự coi getTotalHits() luôn chính xác nếu response có relation gte. API cần phân biệt:

- Tổng chính xác.
- Tổng tối thiểu.
- Không yêu cầu tổng, chỉ cần biết còn trang tiếp theo.

Nếu giao diện chỉ cần nút Next, có thể tránh đếm toàn bộ total và lấy size + 1 hit hoặc dùng cơ chế Slice/cursor phù hợp.

### 13.2. Page và Slice

Page cung cấp totalElements và totalPages. Việc lấy tổng chính xác có thể cần thêm công việc hoặc count query.

Slice tập trung vào content hiện tại và thông tin còn phần tử tiếp theo, không cần biết tổng số phần tử toàn bộ. Nếu UI chỉ có Next/Previous, Slice hoặc cursor response có thể phù hợp hơn Page.

## 14. Phân trang với CriteriaQuery và SearchHits

Ví dụ service dùng CriteriaQuery:

~~~java
public SearchHits<Product> search(
        String category,
        Pageable pageable) {

    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("category").is(category));

    query.setPageable(pageable);

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

Caller:

~~~java
Pageable pageable = PageRequest.of(
        1,
        20,
        Sort.by(
                Sort.Order.asc("category"),
                Sort.Order.asc("sku")));

SearchHits<Product> hits = searchService.search(
        "accessories",
        pageable);
~~~

Spring Data chuyển page/size/sort từ Pageable vào search request. SearchHits giữ hit metadata để tầng trên có thể chuyển thành DTO hoặc Page.

## 15. Phân trang với NativeQuery

NativeQuery phù hợp khi cần kết hợp Query DSL và Pageable:

~~~java
public SearchHits<Product> search(
        String text,
        Pageable pageable) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q
                    .match(m -> m
                            .field("name")
                            .query(text)))
            .withPageable(pageable)
            .build();

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

Nếu query đã có sort trong NativeQuery builder và Pageable cũng chứa Sort, hãy chọn một nguồn sort duy nhất hoặc xác nhận thứ tự kết hợp đúng với version Spring Data đang dùng. Không để hai cấu hình sort vô tình ghi đè nhau.

## 16. API response cho phân trang

Không nhất thiết expose trực tiếp đối tượng Page của Spring Data ra ngoài API. Có thể chuyển thành DTO để giữ hợp đồng HTTP ổn định:

~~~java
public record PageResponse<T>(
        List<T> content,
        int page,
        int size,
        int numberOfElements,
        long totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious) {

    public static <T> PageResponse<T> from(Page<T> result) {
        return new PageResponse<>(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getNumberOfElements(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.hasNext(),
                result.hasPrevious());
    }
}
~~~

Controller:

~~~java
@GetMapping
public PageResponse<Product> find(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    Page<Product> result = service.find(PageRequest.of(page, size));
    return PageResponse.from(result);
}
~~~

DTO giúp API không phụ thuộc trực tiếp vào serialization details của Page implementation. Có thể bổ sung sort metadata hoặc totalRelation nếu API cần biểu diễn total hits lower bound.

## 17. Phân trang khi dữ liệu thay đổi giữa các request

from/size là offset pagination. Mỗi request search độc lập và có thể nhìn thấy một trạng thái index khác nhau.

Ví dụ:

1. Client tải trang 0 với 20 document.
2. Một document mới được thêm vào đầu thứ tự sort.
3. Client tải trang 1 với from = 20.

Do document mới chiếm vị trí đầu tiên, một document từ trang 0 cũ có thể bị đẩy sang trang 1. Client có thể thấy document trùng hoặc bỏ sót document khi duyệt các trang.

Xóa document hoặc cập nhật sort field giữa hai request cũng có thể làm offset dịch chuyển.

Đây là đặc tính của offset pagination trên dữ liệu thay đổi. Stable sort giúp thứ tự xác định trong một trạng thái dữ liệu, nhưng không khóa snapshot giữa nhiều request.

Nếu use case cần duyệt một tập kết quả ổn định, sử dụng PIT kết hợp search_after.

## 18. Deep pagination với search_after

search_after cho phép lấy trang tiếp theo dựa trên sort values của hit cuối cùng ở trang trước, thay vì bỏ qua một offset lớn.

Luồng:

~~~text
Search request 1
    size = 100
    sort = [createdAt, sku]
          |
          v
    Hits 1 ... 100
          |
          v
    Read sort values of hit 100
          |
          v
Search request 2
    size = 100
    search_after = sort values of hit 100
          |
          v
    Hits 101 ... 200
          |
          v
    Repeat with last hit sort values
~~~

Request đầu tiên:

~~~http
POST products/_search
{
  "size": 100,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    },
    {
      "sku": "asc"
    }
  ]
}
~~~

Giả sử hit cuối cùng có sort values:

~~~json
{
  "sort": [
    "2026-11-13T10:00:00.000Z",
    "SKU-0100"
  ]
}
~~~

Request tiếp theo truyền đúng mảng sort đó:

~~~http
POST products/_search
{
  "size": 100,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    },
    {
      "sku": "asc"
    }
  ],
  "search_after": [
    "2026-11-13T10:00:00.000Z",
    "SKU-0100"
  ]
}
~~~

Elasticsearch bắt đầu sau hit có sort values đó. Không tính offset và không cần bỏ qua hàng nghìn hit trước.

### 18.1. search_after cần sort ổn định

Sort values phải xác định thứ tự duy nhất. Nếu chỉ sort theo createdAt và nhiều document có cùng timestamp, có thể không có vị trí duy nhất để tiếp tục.

Thêm tie-breaker keyword duy nhất, ví dụ sku hoặc externalId:

~~~json
"sort": [
  {"createdAt": "asc"},
  {"sku": "asc"}
]
~~~

Không tự tạo search_after bằng cách chỉ truyền giá trị field chính. Phải truyền đầy đủ sort values trong đúng thứ tự Elasticsearch trả về ở hit cuối cùng.

### 18.2. search_after là pagination tuần tự

search_after phù hợp để đi tiếp từ trang hiện tại. Nó không hỗ trợ nhảy tùy ý đến page 500 bằng cách chỉ gửi số trang. Client phải giữ cursor/sort values của hit cuối ở trang trước.

Vì vậy, UI kiểu “đến trang số 500” không phù hợp với search_after thuần túy. Với use case đó, cần cân nhắc lại trải nghiệm, dùng offset cho các trang nông hoặc tạo cursor navigation.

## 19. Point In Time (PIT) kết hợp search_after

Nếu dữ liệu thay đổi trong lúc client duyệt nhiều trang, search_after không có snapshot cố định có thể bị ảnh hưởng bởi insert/update/delete giữa các request.

Point In Time tạo một view ổn định của index trong khoảng thời gian được giữ. Dùng PIT với search_after để duyệt các trang tuần tự trên cùng snapshot.

Mở PIT:

~~~http
POST products/_pit?keep_alive=1m
~~~

Elasticsearch trả PIT ID. Search bằng PIT:

~~~http
POST /_search
{
  "size": 100,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {"createdAt": "asc"},
    {"sku": "asc"}
  ]
}
~~~

Request tiếp theo dùng cùng PIT context và search_after values của hit cuối:

~~~http
POST /_search
{
  "size": 100,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {"createdAt": "asc"},
    {"sku": "asc"}
  ],
  "search_after": [
    "2026-11-13T10:00:00.000Z",
    "SKU-0100",
    4294967298
  ]
}
~~~

PIT có thể trả ID mới trong response. Nếu response cung cấp PIT ID mới, dùng ID mới nhất cho request tiếp theo.

Khi hoàn tất, đóng PIT:

~~~http
DELETE /_pit
{
  "id": "LATEST_PIT_ID"
}
~~~

Giữ PIT quá lâu sẽ giữ tài nguyên và segment cũ. Đặt keep_alive đủ dài cho một lượt duyệt, gia hạn khi tiếp tục và đóng PIT khi kết thúc hoặc hủy cursor.

### 19.1. PIT cung cấp snapshot, không phải transaction nghiệp vụ

PIT giữ góc nhìn tìm kiếm ổn định cho việc duyệt. Nó không khóa index và không tạo transaction cho ứng dụng. Document mới hoặc thay đổi sau thời điểm PIT được tạo không nhất thiết xuất hiện trong snapshot đó.

### 19.2. Tiebreaker với PIT

Khi dùng PIT, Elasticsearch bổ sung _shard_doc như tie-breaker nội bộ cho thứ tự hit nếu cần. Ứng dụng vẫn phải dùng nguyên sort values trả về trong hit cuối để tạo search_after. Không tự bỏ phần tử cuối trong mảng sort.

Nếu tự khai báo tie-breaker nghiệp vụ như sku, nó phải có mapping sort được và bảo đảm tính duy nhất trong phạm vi kết quả. Dù có PIT, vẫn dùng sort values nguyên vẹn từ response.

## 20. Khi nào dùng from/size, search_after hay scroll?

| Cơ chế | Phù hợp | Hạn chế |
|---|---|---|
| from/size | UI pagination nông, nhảy trang trực tiếp | Deep offset tốn tài nguyên, bị max_result_window giới hạn |
| search_after | Duyệt tuần tự dữ liệu lớn | Cần sort values trang trước, không nhảy tùy ý |
| PIT + search_after | Duyệt tuần tự ổn định trên snapshot | Phải quản lý PIT lifecycle và keep_alive |
| Scroll | Batch export/processing theo phiên | Không phù hợp cho pagination tương tác thông thường; giữ context phía server |

Scroll được thiết kế cho việc đọc một lượng lớn kết quả qua nhiều batch trong một phiên. Với ứng dụng mới cần duyệt sâu và ổn định, Elasticsearch khuyến nghị PIT kết hợp search_after thay vì dùng scroll như cơ chế pagination UI.

## 21. Phân trang reactive

Reactive repository vẫn dùng Pageable và PageRequest theo quy tắc zero-based:

~~~java
Flux<Product> findByCategory(String category, Pageable pageable);
~~~

Ví dụ:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.asc("price")));

Flux<Product> products = reactiveRepository.findByCategory(
        "accessories",
        pageable);
~~~

Kết quả là Flux vì reactive repository phát phần tử theo luồng. Pageable chỉ mang page/size/sort; nó không làm Flux tự trở thành Page có total metadata.

Nếu API reactive cần tổng số phần tử, có thể kết hợp query content và count:

~~~java
Mono<ReactiveProductPage> findPage(
        String category,
        Pageable pageable) {

    Flux<Product> content = repository.findByCategory(category, pageable);
    Mono<Long> total = repository.countByCategory(category);

    return Mono.zip(content.collectList(), total)
            .map(tuple -> new ReactiveProductPage(
                    tuple.getT1(),
                    pageable.getPageNumber(),
                    pageable.getPageSize(),
                    tuple.getT2()));
}
~~~

Đây là DTO minh họa. Hai request content/count có thể quan sát dữ liệu ở hai thời điểm khác nhau nếu index đang thay đổi. Nếu không cần total chính xác, tránh count query và trả metadata cursor/hasNext phù hợp.

## 22. Count và Page có thể tốn kém

Để tạo Page đầy đủ, ứng dụng cần totalElements. Với Elasticsearch, việc đếm chính xác tất cả hit có thể tốn thời gian tùy query, số shard và kích thước index.

Một số cách giảm chi phí:

- Giới hạn query bằng filter có chọn lọc.
- Tránh đếm chính xác nếu UI chỉ cần nút Next.
- Dùng Slice/cursor response khi không cần totalPages.
- Chỉ yêu cầu track_total_hits chính xác khi nghiệp vụ cần.
- Cache total nếu dữ liệu ít thay đổi và cache semantics phù hợp.
- Dùng aggregation/count API phù hợp nếu chỉ cần số lượng.

Không nên chạy một count query riêng cho mỗi request nếu giao diện không dùng tổng số.

## 23. Xử lý trang vượt quá kết quả

Nếu client yêu cầu page lớn hơn trang cuối:

~~~http
GET /products?page=100&size=20
~~~

API có thể trả Page rỗng với metadata page đã yêu cầu và totalElements hiện tại, hoặc trả 404/400 theo hợp đồng API. Hãy chọn một quy tắc nhất quán.

Với Page của Spring Data, nội dung có thể rỗng nhưng totalElements vẫn cho biết tập kết quả có bao nhiêu phần tử. Không tự đổi page về trang cuối mà không thông báo cho client, vì điều đó làm page metadata không khớp request.

Nếu page number âm hoặc size không hợp lệ, trả lỗi validation rõ ràng trước khi gọi Elasticsearch.

## 24. Kiểm thử ánh xạ page/size/from

Một integration test nên xác nhận:

- page 0 trả các document đầu theo sort.
- page 1 bắt đầu sau page 0 đúng số phần tử.
- size giới hạn số hit trả về.
- Trang cuối có thể ít hơn size.
- totalElements/totalPages phản ánh dữ liệu mong đợi.
- Sort ổn định giữa các request.
- Page ngoài cửa sổ được xử lý theo hợp đồng API.

Ví dụ:

~~~java
@Test
void mapsPageNumberAndSizeToExpectedWindow() {
    Pageable firstPage = PageRequest.of(
            0,
            2,
            Sort.by(Sort.Order.asc("sku")));
    Pageable secondPage = PageRequest.of(
            1,
            2,
            Sort.by(Sort.Order.asc("sku")));

    Page<Product> first = repository.findByCategory(
            "accessories",
            firstPage);
    Page<Product> second = repository.findByCategory(
            "accessories",
            secondPage);

    assertThat(first.getContent()).hasSize(2);
    assertThat(second.getContent()).hasSize(2);
    assertThat(first.getContent())
            .doesNotContainAnyElementsOf(second.getContent());
}
~~~

Test này cần fixture có ít nhất bốn sản phẩm và sort field xác định. Nếu chỉ sort theo field trùng lặp, test có thể chập chờn.

### 24.1. Kiểm thử mapping from/size trực tiếp

Khi cần xác minh request Elasticsearch thực sự có from và size như mong muốn, có thể dùng mock client/request capture hoặc integration test quan sát search request. Không chỉ kiểm tra PageRequest được tạo đúng; phải xác nhận query/operations đã nhận Pageable.

### 24.2. Kiểm thử deep pagination

Không tạo hàng chục nghìn document trong mọi unit test chỉ để thử max_result_window. Có thể:

- Unit test validation page/size/window ở service.
- Integration test nhỏ xác nhận setting thấp tùy chỉnh và lỗi khi vượt.
- Test riêng cho cursor/search_after với tập dữ liệu đủ để có nhiều batch.

## 25. Các lỗi thường gặp

### Nhầm page number với from

page là chỉ số trang, from là offset. Tính from = page × size.

### Dùng page bắt đầu từ 1 cho PageRequest

PageRequest bắt đầu từ 0. Nếu API nhận số trang bắt đầu từ 1, chuyển đổi rõ ràng tại biên.

### Không giới hạn size

Client có thể yêu cầu response quá lớn. Đặt default và max size ở server.

### Quên Pageable trong Query

Tạo PageRequest nhưng không gắn vào repository method hoặc Query thì Elasticsearch không nhận pagination như mong muốn. Truyền Pageable vào repository hoặc gọi query.setPageable/withPageable.

### Sort không ổn định

Sort field có nhiều giá trị trùng có thể làm hit đổi vị trí. Thêm tie-breaker keyword duy nhất.

### Sort trên text field

Text field được phân tích; dùng keyword subfield hoặc field có kiểu sort phù hợp.

### Sort trực tiếp trên _id

Không mặc định coi _id là field sort thông thường. Lưu một field keyword duy nhất phù hợp làm tie-breaker.

### Vượt max_result_window

from + size vượt giới hạn mặc định 10.000 sẽ thất bại. Dùng search_after/PIT cho deep traversal thay vì tăng setting vô hạn.

### Nghĩ total hits luôn chính xác

Elasticsearch có thể trả total relation gte. Kiểm tra total hits semantics trước khi dùng để tính totalPages chính xác.

### Dùng Page dù không cần tổng số

Count chính xác có thể tốn chi phí. Nếu UI chỉ cần biết còn trang tiếp theo, dùng Slice hoặc cursor.

### Dữ liệu thay đổi giữa các trang

Offset pagination có thể trùng hoặc bỏ sót hit khi index thay đổi. PIT + search_after phù hợp cho lượt duyệt cần snapshot ổn định.

### Dùng search_after nhưng không giữ sort values

Phải gửi nguyên sort array của hit cuối trang trước. Không tự tính cursor từ field tùy ý.

### Dùng search_after để nhảy tới page tùy ý

search_after là cursor tuần tự. Không hỗ trợ random access page number trực tiếp.

### Giữ PIT quá lâu

PIT giữ tài nguyên và segment. Đặt keep_alive vừa đủ, gia hạn khi tiếp tục và đóng khi hoàn tất.

### Dùng Scroll cho UI pagination

Scroll dành cho batch processing/đọc lượng lớn theo phiên. Dùng from/size cho trang nông hoặc PIT + search_after cho deep traversal.

## 26. Quy trình thiết kế pagination cho API

Khi thêm phân trang vào endpoint Spring Data Elasticsearch:

1. Xác định giao diện cần page number hay cursor.
2. Nếu chỉ có các trang đầu, dùng Pageable/PageRequest.
3. Quy định page zero-based hoặc one-based trong hợp đồng API.
4. Chọn default size và max size ở server.
5. Kiểm tra page không âm, size dương và offset không vượt giới hạn.
6. Tạo PageRequest với sort ổn định.
7. Truyền Pageable vào repository method hoặc gắn vào Query.
8. Chọn Page nếu cần total metadata; chọn List/SearchHits/Slice/cursor nếu phù hợp hơn.
9. Xác định total hits có cần chính xác hay chỉ cần lower bound.
10. Bảo đảm sort field có mapping hỗ trợ sort và có tie-breaker.
11. Dùng from/size trong giới hạn max_result_window.
12. Chuyển sang PIT + search_after cho deep traversal hoặc snapshot ổn định.
13. Đóng PIT và quản lý cursor lifecycle.
14. Kiểm thử page 0, page tiếp theo, trang cuối, sort và trường hợp vượt giới hạn.

## 27. Tổng kết

Spring Data Pageable biểu diễn page number, page size và sort. Page number bắt đầu từ 0; offset được tính bằng pageNumber × pageSize. Spring Data Elasticsearch chuyển offset thành Elasticsearch from và page size thành size. Repository query method có thể nhận Pageable; với Query object, gắn Pageable bằng setPageable hoặc withPageable tùy loại query.

Page cung cấp content cùng totalElements/totalPages, còn List chỉ chứa các phần tử. SearchHits giữ metadata hit và total hits từ Elasticsearch. Total hits có thể chỉ là lower bound nếu Elasticsearch không đếm chính xác toàn bộ; chỉ yêu cầu exact count khi nghiệp vụ cần.

from/size phù hợp cho trang nông và cho phép nhảy trang trực tiếp, nhưng chi phí tăng theo from + size. Elasticsearch mặc định giới hạn index.max_result_window ở 10.000. Không nên tăng giới hạn vô hạn để hỗ trợ deep pagination. Với duyệt tuần tự dữ liệu lớn, dùng search_after; nếu cần snapshot ổn định khi dữ liệu thay đổi, kết hợp Point In Time và đóng PIT khi hoàn tất.

Sort phải ổn định và dùng field có mapping phù hợp. Thêm tie-breaker keyword duy nhất để giảm hit trùng/bỏ sót giữa các trang. Tuy nhiên offset pagination vẫn có thể dịch chuyển khi dữ liệu thay đổi giữa các request; PIT + search_after giải quyết tốt hơn nhu cầu duyệt một snapshot.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch – Query API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch – PageRequest API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html)
- [Spring Data Elasticsearch – SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Elasticsearch – Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch – Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch – Point in Time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Elasticsearch – Scroll API](https://www.elastic.co/guide/en/elasticsearch/reference/current/scroll-api.html)
