# Giới hạn index.max_result_window và chi phí phân trang sâu

Elasticsearch hỗ trợ phân trang bằng hai tham số quen thuộc là **from** và **size**. Cách này phù hợp với danh sách có số trang vừa phải, nhưng chi phí tăng khi người dùng yêu cầu một offset rất sâu. Để tránh một truy vấn buộc mỗi shard phải giữ quá nhiều kết quả trung gian, Elasticsearch đặt giới hạn **index.max_result_window**, mặc định thường là 10.000.

Khi request vượt giới hạn, Elasticsearch từ chối truy vấn với lỗi result window quá lớn. Tăng setting có thể làm request chạy qua, nhưng không loại bỏ chi phí CPU, heap, merge và network của deep pagination. Với dữ liệu lớn, nên xem lại cách điều hướng kết quả: dùng search_after kết hợp Point in Time (PIT) cho cursor pagination ổn định, hoặc dùng scroll cho một số quy trình batch phù hợp.

Bài này giải thích cách from/size hoạt động, vì sao phân trang sâu tốn tài nguyên, cách cấu hình và kiểm thử max_result_window, cách dùng Spring Data Elasticsearch, và cách chọn chiến lược thay thế dựa trên yêu cầu sản phẩm.

## 1. from và size hoạt động như thế nào?

Một search request dùng from và size để bỏ qua một số hit đầu rồi trả về số hit tiếp theo:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    { "createdAt": "desc" }
  ]
}
~~~

- **from** là số hit cần bỏ qua trước khi bắt đầu trả kết quả.
- **size** là số hit tối đa cần trả về.
- Trang đầu với 20 item dùng from = 0, size = 20.
- Trang thứ hai dùng from = 20, size = 20.
- Trang thứ ba dùng from = 40, size = 20.

Công thức offset của page-based pagination:

\[
from = pageNumber \times pageSize
\]

Trong đó pageNumber bắt đầu từ 0. Ví dụ trang 50 với page size 20 có from = 1.000.

Elasticsearch không chỉ cần tìm đúng 20 hit cuối cùng. Để trả về kết quả ở offset 1.000, các shard cần tìm và giữ đủ tập ứng viên đến vị trí from + size, sau đó coordinator hợp nhất kết quả từ các shard và loại bỏ phần bị bỏ qua.

## 2. index.max_result_window là gì?

index.max_result_window là index setting giới hạn tổng của from + size trong một search request. Giá trị mặc định phổ biến là **10.000**.

Điều kiện:

\[
from + size \leq index.max\_result\_window
\]

Ví dụ với giới hạn 10.000:

| from | size | from + size | Kết quả |
|---:|---:|---:|---|
| 0 | 20 | 20 | Hợp lệ |
| 980 | 20 | 1.000 | Hợp lệ |
| 9.980 | 20 | 10.000 | Hợp lệ |
| 10.000 | 20 | 10.020 | Vượt giới hạn |
| 50.000 | 100 | 50.100 | Vượt giới hạn |

Giới hạn này áp dụng cho search result window của index. Nó không có nghĩa index chỉ chứa được 10.000 document hoặc chỉ có thể tìm thấy 10.000 kết quả. Elasticsearch vẫn có thể index và search trên tập dữ liệu lớn hơn; giới hạn nói về cách lấy một đoạn kết quả theo offset.

Setting được cấu hình theo index, vì vậy các index khác nhau có thể có giá trị khác nhau. Với alias trỏ tới nhiều index, cần kiểm tra setting của các index đích và bảo đảm request hoạt động nhất quán.

## 3. Vì sao Elasticsearch đặt giới hạn 10.000?

Deep pagination làm tăng lượng công việc ở mỗi shard. Giả sử một index có 5 shard chính và ứng dụng yêu cầu:

~~~text
from = 90,000
size = 100
from + size = 90,100
~~~

Để xác định 100 hit ở vị trí đó, mỗi shard cần thu thập một tập ứng viên đủ lớn cho phần kết quả được yêu cầu. Coordinator phải nhận, hợp nhất và sắp xếp các ứng viên từ shard rồi bỏ qua 90.000 hit đầu.

Chi phí có thể tăng ở nhiều nơi:

- **CPU:** mỗi shard phải xử lý và chọn nhiều hit hơn.
- **Heap:** các cấu trúc lưu top hits và sort values cần bộ nhớ.
- **Network:** shard gửi nhiều ứng viên hơn về coordinating node.
- **Coordinator:** phải merge kết quả lớn từ nhiều shard.
- **Latency:** request cần nhiều công việc hơn trước khi trả trang sâu.
- **Concurrency:** nhiều truy vấn sâu cùng lúc có thể cạnh tranh tài nguyên với indexing và search khác.

Giới hạn mặc định là một hàng rào bảo vệ để ngăn một request vô tình yêu cầu quá nhiều kết quả trung gian. Tăng giới hạn không làm chi phí biến mất; nó chỉ cho phép request yêu cầu một cửa sổ lớn hơn.

## 4. Chi phí tăng theo from + size, không chỉ theo số hit trả về

Hai request có thể cùng trả 20 hit nhưng chi phí khác nhau đáng kể:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20
}
~~~

và:

~~~http
POST /products/_search
{
  "from": 50000,
  "size": 20
}
~~~

Request thứ hai vẫn chỉ trả 20 hit về client, nhưng cần xử lý vị trí sâu hơn nhiều. Số hit trong response không phản ánh toàn bộ công việc Elasticsearch đã thực hiện.

Đó là lý do không nên đánh giá hiệu năng pagination chỉ bằng kích thước JSON response. Cần đo query latency, CPU, heap, shard workload, network và coordinating node khi offset tăng.

## 5. Ví dụ lỗi result window quá lớn

Nếu index có max_result_window = 10.000, request sau vượt giới hạn:

~~~http
POST /products/_search
{
  "from": 10000,
  "size": 50,
  "query": {
    "match_all": {}
  }
}
~~~

Elasticsearch có thể trả lỗi dạng:

~~~json
{
  "error": {
    "root_cause": [
      {
        "type": "illegal_argument_exception",
        "reason": "Result window is too large, from + size must be less than or equal to: [10000] but was [10050]."
      }
    ],
    "type": "search_phase_execution_exception"
  },
  "status": 400
}
~~~

Nội dung chính xác của error reason có thể khác theo phiên bản và cấu hình, nhưng nguyên nhân là from + size vượt giới hạn.

Trong ứng dụng, không nên biến lỗi này thành một retry tự động. Gửi lại cùng request không thể làm cửa sổ hợp lệ. Hãy xử lý ở tầng API: giới hạn page number, yêu cầu người dùng thu hẹp bộ lọc hoặc chuyển sang cursor pagination.

## 6. Kiểm tra và thay đổi setting

Đọc setting của một index:

~~~http
GET /products/_settings?include_defaults=true
~~~

Có thể lọc kết quả theo tên setting:

~~~http
GET /products/_settings/index.max_result_window
~~~

Thay đổi setting cho index:

~~~http
PUT /products/_settings
{
  "index": {
    "max_result_window": 20000
  }
}
~~~

index.max_result_window là một index setting có thể thay đổi động trên các phiên bản Elasticsearch hiện hành. Hãy kiểm tra tài liệu và phiên bản cluster cụ thể trước khi thay đổi trong production.

Việc tăng lên 20.000 không đồng nghĩa hệ thống có thể phục vụ deep pagination miễn phí. Chỉ tăng khi đã đo tải, xác định page depth thực sự cần thiết và đánh giá tài nguyên cluster.

## 7. Vì sao không nên tăng max_result_window thật lớn?

Một cách xử lý nhanh khi gặp lỗi là đặt giới hạn thành 100.000 hoặc 1.000.000. Điều này có thể làm request hết lỗi giới hạn, nhưng cũng cho phép client yêu cầu một lượng kết quả trung gian rất lớn.

Rủi ro:

- Một người dùng có thể gửi request deep pagination gây tải cao.
- Nhiều request đồng thời có thể làm heap và CPU tăng mạnh.
- Coordinating node phải merge nhiều hit hơn.
- Search latency của các endpoint khác có thể tăng.
- Cluster có thể gặp circuit breaker hoặc thiếu bộ nhớ.
- Tăng giới hạn che giấu thiết kế pagination không phù hợp.

Không tăng max_result_window chỉ để làm cho một trang rất xa có thể truy cập. Hãy xác định người dùng có thật sự cần nhảy trực tiếp tới trang đó hay chỉ cần đi tiếp qua kết quả.

Nếu giao diện chỉ cần nút Next/Previous, cursor pagination thường phù hợp hơn. Nếu cần xuất toàn bộ dữ liệu, hãy dùng quy trình batch thay vì giả lập một trang cực lớn.

## 8. Giới hạn ở API ứng dụng

Ngay cả khi Elasticsearch cho phép cửa sổ 10.000, ứng dụng có thể đặt giới hạn thấp hơn để kiểm soát tải.

Ví dụ:

- pageSize tối đa 100.
- pageNumber không được âm.
- pageNumber × pageSize không vượt giới hạn nghiệp vụ.
- Chỉ một số role được phép dùng page size lớn.
- Search phải có điều kiện lọc hoặc thời gian timeout.
- Endpoint export dùng một API riêng thay vì tăng page number.

Một helper kiểm tra Pageable:

~~~java
public Pageable validatePageRequest(int page, int size) {
    int maxPageSize = 100;
    long maxWindow = 10_000L;

    if (page < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }

    if (size < 1 || size > maxPageSize) {
        throw new IllegalArgumentException("Invalid page size");
    }

    long from = (long) page * size;
    if (from + size > maxWindow) {
        throw new DeepPaginationNotSupportedException();
    }

    return PageRequest.of(page, size);
}
~~~

Dùng long khi tính offset để tránh tràn số nguyên nếu page hoặc size lớn. Không chỉ kiểm tra page < một con số tùy ý; hãy kiểm tra from + size theo giới hạn cấu hình của endpoint.

Nếu ứng dụng có nhiều index với max_result_window khác nhau, không nhất thiết expose setting thô cho client. Thường nên đặt chính sách API ổn định, có giới hạn rõ ràng và độc lập với setting nội bộ Elasticsearch.

## 9. PageRequest trong Spring Data Elasticsearch

Với repository hỗ trợ Pageable, Spring Data có thể chuyển PageRequest thành from/size và sort trong search request.

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("productId")
        )
);

Page<Product> page =
        productRepository.findByStatus("ACTIVE", pageable);
~~~

Trang thứ hai:

~~~java
Pageable pageable = PageRequest.of(1, 20);
~~~

Spring Data tính offset từ page number và page size. Vì vậy, page number lớn có thể tạo from vượt max_result_window.

API trả Page thường có thông tin totalElements và totalPages. Để tính tổng số phần tử, implementation có thể cần thực hiện count hoặc lấy total hits theo semantics của phiên bản. Việc yêu cầu tổng chính xác cũng có chi phí riêng; không phải lúc nào giao diện cũng cần con số chính xác.

## 10. SearchHits, SearchPage và Pageable

Khi dùng ElasticsearchOperations, ứng dụng có thể nhận SearchHits<T> hoặc chuyển kết quả thành SearchPage<T> tùy API.

Ví dụ khái quát:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

SearchHits cung cấp hit metadata và total hits. Nếu cần Spring Data Page abstraction, có thể dùng phương thức chuyển đổi SearchPage phù hợp với phiên bản.

Không giả định mọi overload đều thực hiện cùng một count request hoặc cùng chính sách total hits. Hãy kiểm tra query thực tế và cách API tính totalElements khi page sâu hoặc track_total_hits bị giới hạn.

## 11. Khi nào from/size vẫn là lựa chọn tốt?

from/size đơn giản và phù hợp trong các trường hợp:

- Danh sách nhỏ hoặc vừa.
- Người dùng chủ yếu xem vài trang đầu.
- Cần nhảy trực tiếp tới trang số cụ thể.
- Kết quả ít thay đổi trong lúc người dùng phân trang.
- API cần tích hợp với UI page-number truyền thống.
- from + size luôn nằm trong cửa sổ cho phép.

Không cần thay toàn bộ pagination của ứng dụng chỉ vì Elasticsearch có giới hạn 10.000. Hãy chọn theo hành vi thực tế của sản phẩm.

Ví dụ danh sách quản trị có 300 kết quả và page size 25 có thể dùng Pageable rất hợp lý. Một trang dữ liệu hàng triệu document cần được duyệt tuần tự thì nên dùng cursor hoặc batch processing.

## 12. search_after là gì?

search_after là cơ chế tiếp tục tìm kiếm dựa trên giá trị sort của hit cuối cùng trong trang trước. Thay vì yêu cầu Elasticsearch bỏ qua hàng chục nghìn hit đầu, client gửi một cursor biểu diễn vị trí tiếp tục.

Trang đầu:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Giả sử hit cuối trang có sort values:

~~~json
[
  "2026-11-13T08:30:00Z",
  "p-020"
]
~~~

Trang tiếp theo:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Elasticsearch bắt đầu sau vị trí sort đó. Chi phí không phải tăng tuyến tính theo số trang đã duyệt giống from/size deep offset.

search_after yêu cầu sort được xác định. Tất cả sort values của hit cuối phải được giữ nguyên, đúng thứ tự và đúng kiểu dữ liệu. Nếu sort có hai field, cursor phải có hai giá trị tương ứng.

## 13. Vì sao search_after cần sort ổn định?

Nếu nhiều document có cùng sort value, ranh giới giữa hai trang có thể không xác định. Một hit có thể bị lặp hoặc bị bỏ qua khi các giá trị sort không phân biệt được.

Hãy thêm tie-breaker duy nhất:

~~~json
"sort": [
  { "createdAt": "desc" },
  { "productId": "asc" }
]
~~~

Trong đó productId là keyword và duy nhất trong phạm vi query. Nếu query có thể chạy trên nhiều tenant, cần bảo đảm khóa cuối cùng duy nhất trên toàn tập kết quả.

Không dùng một field không ổn định như random score làm cursor sort nếu muốn duyệt tuần tự. Không thay đổi sort giữa các request trang.

Có thể dùng PIT để có snapshot ổn định; với PIT, Elasticsearch có cơ chế tie-breaker nội bộ như _shard_doc trong các phiên bản hiện hành. Dù vậy, ứng dụng vẫn phải giữ sort values đúng như response và theo tài liệu của phiên bản đang dùng.

## 14. Point in Time kết hợp search_after

Nếu dữ liệu được thêm, sửa hoặc xóa trong lúc người dùng đang phân trang, kết quả từ nhiều request có thể không còn thuộc cùng một snapshot. PIT giữ một view nhất quán trong khoảng thời gian được chỉ định.

Luồng:

1. Mở PIT cho index hoặc alias.
2. Gửi trang đầu với PIT, sort và size.
3. Lấy sort values của hit cuối.
4. Gửi trang tiếp theo với PIT ID mới nhất và search_after.
5. Lặp lại đến khi hết dữ liệu.
6. Đóng PIT khi hoàn tất.

Mở PIT:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Search đầu tiên:

~~~http
POST /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Trang tiếp theo thêm sort values từ hit cuối vào search_after. Nếu response trả PIT ID mới, hãy dùng ID mới nhất cho request kế tiếp.

Đóng PIT:

~~~http
DELETE /_pit
{
  "id": "PIT_ID"
}
~~~

PIT giữ search context và tiêu thụ tài nguyên trong thời gian tồn tại. Đặt keep_alive vừa đủ, đóng khi xong và xử lý trường hợp client ngừng phân trang. Không mở PIT mới cho mỗi trang nếu mục tiêu là duy trì một snapshot nhất quán.

## 15. search_after không phải page-number pagination

search_after phù hợp với điều hướng tuần tự:

- Trang đầu.
- Trang tiếp theo.
- Trang tiếp theo nữa.
- Quay lại trang trước nếu ứng dụng tự lưu cursor hoặc cache kết quả cần thiết.

Nó không hỗ trợ nhảy trực tiếp tới trang thứ 5.000 theo cách from/size. Client phải có cursor từ hit cuối của trang trước để tiếp tục.

| Nhu cầu UI/API | Chiến lược phù hợp |
|---|---|
| Nhảy tới trang số bất kỳ | from/size trong giới hạn |
| Next/Load more | search_after |
| Duyệt dữ liệu lớn, cần snapshot | PIT + search_after |
| Xuất dữ liệu theo batch | PIT + search_after hoặc scroll phù hợp |
| Đếm và thống kê, không cần hit | Aggregation với size = 0 |

Nếu giao diện hiện tại bắt buộc hiển thị tổng số trang và nút nhảy tới trang cuối, cursor pagination có thể yêu cầu thay đổi UX. Không nên giả lập page number bằng cách gửi from rất lớn.

## 16. Dùng search_after với Elasticsearch Java API Client

Java API Client cho phép cấu hình sort và search_after trong SearchRequest. Ví dụ khung cho hai sort field:

~~~java
SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .size(20)
        .sort(sort -> sort.field(f -> f
                .field("createdAt")
                .order(SortOrder.Desc)
        ))
        .sort(sort -> sort.field(f -> f
                .field("productId")
                .order(SortOrder.Asc)
        ))
        .query(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
);

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);
~~~

Lấy cursor từ hit cuối:

~~~java
List<FieldValue> cursor =
        response.hits().hits().get(response.hits().hits().size() - 1).sort();
~~~

Gửi request tiếp theo:

~~~java
SearchRequest nextRequest = SearchRequest.of(s -> s
        .index("products")
        .size(20)
        .sort(sort -> sort.field(f -> f
                .field("createdAt")
                .order(SortOrder.Desc)
        ))
        .sort(sort -> sort.field(f -> f
                .field("productId")
                .order(SortOrder.Asc)
        ))
        .searchAfter(cursor)
        .query(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
);
~~~

Ví dụ minh họa API client hiện đại; import và kiểu trả về cần khớp phiên bản. Trước khi lấy hit cuối, phải kiểm tra response có hit hay không. Khi dùng PIT, request cần truyền PIT ID và keep_alive theo API client, không để query chuyển sang một search context khác.

## 17. search_after với Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp NativeQuery để cấu hình query nâng cao. Các phiên bản hiện đại có hỗ trợ search-after thông qua API tương ứng của NativeQuery/SearchHits, nhưng chữ ký cụ thể có thể thay đổi.

Luồng khái quát:

1. Tạo NativeQuery với query và sort.
2. Gửi request đầu.
3. Lấy sort values từ SearchHit cuối.
4. Dùng các giá trị đó làm search-after cho NativeQuery tiếp theo.
5. Giữ cùng query, sort và PIT nếu đang dùng snapshot.

Ví dụ lấy sort values:

~~~java
SearchHits<Product> hits =
        operations.search(firstPageQuery, Product.class);

List<Object> searchAfter =
        hits.getSearchHit(hits.getSearchHits().size() - 1)
                .getSortValues();
~~~

Một số API trả danh sách hit qua iterator hoặc accessor khác; hãy dùng cách lấy hit cuối phù hợp phiên bản. Cũng cần xử lý trường hợp trang rỗng trước khi truy cập phần tử cuối.

Nếu NativeQuery builder trong phiên bản dự án có withSearchAfter, có thể truyền danh sách sort values đó vào query kế tiếp. Nếu cần PIT hoặc tính năng chưa được abstraction hỗ trợ, dùng Java API Client trực tiếp tại tầng repository adapter.

Không tự serialize sort values thành chuỗi rồi parse lại theo phỏng đoán. Giữ kiểu dữ liệu gốc hoặc chuyển đổi theo kiểu chính xác mà Java API Client yêu cầu.

## 18. Scroll API và use case batch

Scroll API từng được dùng phổ biến để duyệt lượng lớn document theo batch. Nó giữ search context trên cluster và cho client lấy các batch tiếp theo bằng scroll ID.

Scroll phù hợp với một số tác vụ batch/export cần duyệt tập kết quả lớn, nhưng không phải lựa chọn mặc định cho phân trang giao diện tương tác. Với các luồng mới cần deep pagination và snapshot, Elasticsearch khuyến nghị cân nhắc PIT + search_after.

Nếu dùng scroll:

- Đặt scroll keep_alive phù hợp.
- Xử lý hết batch cho đến khi response không còn hit.
- Giữ scroll ID mới nhất nếu response thay đổi.
- Clear scroll khi hoàn tất.
- Không giữ scroll context lâu hơn cần thiết.
- Giới hạn số job chạy đồng thời.
- Không dùng scroll như cursor vĩnh viễn cho người dùng.

Scroll context tiêu thụ tài nguyên. Nếu client bị ngắt giữa chừng mà không clear, context có thể tồn tại đến khi hết thời gian giữ.

## 19. Scroll khác search_after thế nào?

| Tiêu chí | from/size | search_after | Scroll |
|---|---|---|---|
| Mục đích | Page-number pagination | Cursor/next-page | Duyệt batch |
| Deep pagination | Đắt, bị giới hạn window | Phù hợp | Phù hợp cho batch |
| Nhảy tới trang tùy ý | Có trong giới hạn | Không trực tiếp | Không |
| Snapshot ổn định | Không tự bảo đảm | Dùng PIT khi cần | Giữ search context |
| Tài nguyên | Tăng theo offset | Theo batch và sort | Giữ scroll context |
| UX tương tác | Tốt cho trang đầu | Tốt cho next/load more | Không phù hợp thường lệ |
| Dọn tài nguyên | Không cần cursor context | Đóng PIT nếu dùng | Clear scroll |

Chọn theo mục tiêu. Không thay mọi Pageable bằng scroll hoặc search_after một cách máy móc.

## 20. track_total_hits và chi phí đếm tổng

Một trang tìm kiếm có thể cần biết tổng số hit chính xác để hiển thị “1–20 trong 125.432 kết quả”. Tuy nhiên, tính exact total hits có thể làm tăng công việc của Elasticsearch.

Có thể điều khiển track_total_hits:

~~~http
POST /products/_search
{
  "track_total_hits": false,
  "from": 0,
  "size": 20,
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Hoặc đặt ngưỡng:

~~~json
"track_total_hits": 10000
~~~

Khi dùng false hoặc ngưỡng, response có thể không cung cấp tổng chính xác; total relation có thể thể hiện gte thay vì eq.

Điều này không thay thế max_result_window. track_total_hits điều khiển cách đếm tổng kết quả; max_result_window giới hạn from + size.

Nếu giao diện chỉ cần biết còn kết quả tiếp theo hay không, có thể lấy size + 1 hit hoặc dùng cursor flow thay vì yêu cầu exact total. Cách thiết kế phụ thuộc API và khả năng của abstraction đang dùng.

## 21. Aggregation không cần phân trang hits

Nếu endpoint chỉ cần thống kê, đừng yêu cầu hàng nghìn hit rồi bỏ đi. Dùng size = 0 và aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

Trong trường hợp này, aggregation trả buckets mà không cần tải hit documents về. max_result_window không phải cơ chế phân trang bucket; terms size và composite aggregation có quy tắc riêng.

Nếu cần duyệt số lượng bucket rất lớn, cân nhắc composite aggregation với after_key thay vì tăng terms size vô hạn.

## 22. Các giới hạn khác không nên nhầm với max_result_window

Elasticsearch có nhiều setting liên quan tới kết quả và tài nguyên:

- **index.max_result_window:** giới hạn from + size cho search hits.
- **index.max_inner_result_window:** giới hạn result window của inner hits và một số trường hợp tương ứng.
- **search.max_buckets:** giới hạn số bucket aggregation trong một search response.
- **index.max_rescore_window:** giới hạn cửa sổ rescore trong các trường hợp áp dụng.
- **track_total_hits:** điều khiển mức độ đếm tổng hits.
- **scroll keep_alive:** thời gian giữ scroll context.
- **PIT keep_alive:** thời gian giữ Point in Time.

Không tăng max_result_window để giải quyết lỗi search.max_buckets hoặc inner hits. Hãy đọc chính xác error type và setting liên quan.

## 23. Thiết kế API cursor pagination

Một API cursor có thể trả:

~~~json
{
  "items": [
    {
      "id": "p-001",
      "name": "Mechanical Keyboard"
    }
  ],
  "nextCursor": "opaque-cursor-token",
  "hasNext": true
}
~~~

Cursor có thể chứa sort values và thông tin query context, hoặc là một token tham chiếu tới state lưu phía server.

Không nên để client tùy ý sửa sort values, tenant filter hoặc index trong cursor. Có thể ký token hoặc lưu state server-side. Nếu cursor chứa thông tin nhạy cảm, không gửi payload plaintext trong URL.

Cursor cần gắn với:

- Query/filter đã chuẩn hóa.
- Sort order.
- Tenant hoặc phạm vi quyền nếu có.
- PIT ID nếu dùng PIT.
- Sort values của hit cuối.
- Phiên bản schema/API nếu cần.
- Thời điểm hết hạn.

Ở mỗi request tiếp theo, xác thực principal hiện tại và bảo đảm cursor thuộc cùng phạm vi truy cập. Không xem cursor là credential thay thế authorization.

## 24. Kiểm thử max_result_window

Một integration test nên xác nhận behavior ở ranh giới setting:

1. Tạo index test với max_result_window nhỏ, ví dụ 100.
2. Gửi request from = 80, size = 20: phải hợp lệ.
3. Gửi request from = 81, size = 20: phải bị từ chối.
4. Gửi request size = 101 từ 0: phải bị từ chối.
5. Xác nhận ứng dụng chuyển lỗi vượt giới hạn thành lỗi API phù hợp.
6. Xác nhận request hợp lệ vẫn trả đúng thứ tự và số lượng.

Dùng setting nhỏ trong test giúp kiểm tra logic mà không cần index hàng chục nghìn document. Cần đảm bảo test thật sự tạo setting trên index test và không dùng nhầm alias trỏ sang index khác.

Ví dụ REST:

~~~http
PUT /products-pagination-test/_settings
{
  "index": {
    "max_result_window": 100
  }
}
~~~

Sau đó tạo fixture đủ số lượng để kiểm tra pagination. Lỗi window được xác định từ from + size; không nhất thiết phải có đúng số document đó trong index để request vượt setting.

## 25. Kiểm thử pagination qua Spring Data

Với repository và Pageable, kiểm tra cả page hợp lệ lẫn page vượt giới hạn:

~~~java
@Test
void acceptsPageWithinResultWindow() {
    Pageable pageable = PageRequest.of(4, 20);

    StepVerifier.create(
            reactiveRepository.findByStatus("ACTIVE", pageable)
    )
    .expectNextCount(20)
    .verifyComplete();
}
~~~

Đoạn trên chỉ minh họa Flux repository method. Với Page trả về Mono<Page<T>>, dùng StepVerifier để kiểm tra Mono và content. Chữ ký repository cụ thể tùy khai báo.

Với page vượt giới hạn, API có thể trả exception khi subscription thực hiện request. Test cần xác nhận exception được chuyển thành lỗi nghiệp vụ/API, thay vì retry tự động hoặc trả danh sách rỗng giả tạo.

Không nên chỉ test helper validatePageRequest. Cần ít nhất một integration test xác nhận request thực tế được gửi tới Elasticsearch có from/size đúng.

## 26. Kiểm thử search_after không lặp và không mất document

Tạo fixture có số lượng lớn hơn nhiều page size, ví dụ 257 document. Sort theo createdAt và productId.

Test:

1. Mở PIT.
2. Lấy trang đầu với size 50.
3. Lưu tất cả ID.
4. Lấy sort values của hit cuối.
5. Gửi request kế tiếp bằng search_after.
6. Lặp đến khi hết kết quả.
7. Đóng PIT.
8. Xác nhận tổng ID bằng 257.
9. Xác nhận tất cả ID duy nhất.
10. Xác nhận thứ tự sort đúng.

Nếu không dùng PIT, test có thể chạy trên fixture không thay đổi trong lúc phân trang. Nhưng không nên dùng kết quả đó để khẳng định behavior khi có ghi đồng thời.

## 27. Kiểm thử khi dữ liệu thay đổi giữa các trang

Một test hữu ích là mô phỏng insert hoặc update sau khi trang đầu đã được lấy.

Với from/size, thay đổi dữ liệu có thể làm vị trí offset dịch chuyển và dẫn đến lặp hoặc bỏ sót. Đây là một đặc tính cần hiểu, không nhất thiết là bug của Elasticsearch.

Với PIT + search_after, các request trong cùng PIT tiếp tục nhìn snapshot đã mở. Test có thể:

1. Mở PIT và lấy trang đầu.
2. Thêm document mới vào index.
3. Tiếp tục phân trang bằng PIT cũ.
4. Xác nhận document mới không chen vào snapshot hiện tại.
5. Đóng PIT và mở PIT mới.
6. Xác nhận truy vấn mới có thể nhìn thấy document mới.

Cách này giúp chứng minh lý do dùng PIT khi cần duyệt kết quả ổn định.

## 28. Kiểm thử performance cho deep pagination

Không chỉ kiểm thử đúng/sai. Cần đo latency và tài nguyên ở nhiều độ sâu.

| from | size | Mục tiêu |
|---:|---:|---|
| 0 | 20 | Trang đầu |
| 1.000 | 20 | Offset vừa |
| 5.000 | 20 | Offset sâu |
| 9.980 | 20 | Gần giới hạn mặc định |
| 10.000 | 20 | Kiểm tra vượt giới hạn |

Đo:

- p50, p95, p99 latency.
- CPU của data node và coordinating node.
- Heap usage và GC.
- Search thread pool queue/rejections.
- Network bytes giữa shard và coordinator.
- Concurrent request throughput.
- Ảnh hưởng tới indexing và các query khác.

So sánh from/size với search_after/PIT trên cùng dataset, mapping, shard count và sort. Không kết luận từ một lần chạy đơn lẻ; warm-up, cache và tải nền có thể làm kết quả thay đổi.

## 29. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trang sâu trả 400 | from + size vượt max_result_window | Giới hạn page hoặc đổi chiến lược |
| Tăng max_result_window nhưng search chậm | Chi phí deep pagination vẫn còn | Dùng search_after/PIT |
| Trang sau lặp document | Sort không có tie-breaker ổn định | Thêm unique sort field |
| Trang sau bỏ sót document | Dữ liệu thay đổi giữa offset requests | PIT + search_after nếu cần snapshot |
| search_after trả sai vị trí | Cursor thiếu sort value hoặc sai kiểu/thứ tự | Dùng toàn bộ sort values từ hit cuối |
| search_after không ổn định | Sort field trùng hoặc thay đổi | Thêm tie-breaker và dùng PIT |
| Page count chậm | Exact total hits/count tốn chi phí | Xem track_total_hits và UX |
| Export giữ nhiều heap | Dùng collectList hoặc page offset lớn | Xử lý batch/cursor |
| Scroll context bị giữ lâu | Không clear scroll | Clear và giới hạn keep_alive |
| Tăng setting sai index | Alias trỏ nhiều index hoặc sửa nhầm target | Kiểm tra backing index và settings |
| Nhầm max_result_window với max_buckets | Setting áp dụng cho loại kết quả khác | Đọc đúng error và setting |
| API cho page number rất lớn | Không validate offset ở tầng ứng dụng | Kiểm tra from + size trước khi query |

## 30. Quy trình chọn chiến lược phân trang

Có thể chọn theo nhu cầu:

1. **Danh sách nhỏ, cần số trang và nhảy trang:** dùng from/size với page size và page depth có giới hạn.
2. **Danh sách dài, chỉ cần next/load more:** dùng search_after với sort ổn định.
3. **Dữ liệu có thay đổi nhưng cần duyệt một tập nhất quán:** dùng PIT + search_after.
4. **Export hoặc batch processing:** dùng PIT + search_after; cân nhắc scroll khi phù hợp với API và workload.
5. **Chỉ cần thống kê:** dùng aggregation với size = 0.
6. **Cần đếm tổng chính xác:** đánh giá track_total_hits và chi phí count; chỉ yêu cầu exact khi UI thực sự cần.
7. **Client muốn nhảy tới trang rất sâu:** xem lại UX hoặc cung cấp tìm kiếm/điều kiện lọc hẹp hơn thay vì tăng offset không giới hạn.

## 31. Nguyên tắc vận hành

- Giữ max_result_window ở mức có chủ đích.
- Kiểm tra from + size trước khi gửi request nếu API dùng page number.
- Không tăng setting lớn chỉ để bỏ qua lỗi deep pagination.
- Đặt sort ổn định với tie-breaker duy nhất.
- Dùng search_after cho cursor pagination.
- Dùng PIT khi cần snapshot nhất quán qua nhiều request.
- Đóng PIT và scroll context khi hoàn tất.
- Giới hạn page size, concurrency và timeout.
- Chỉ yêu cầu exact total hits khi có nhu cầu sản phẩm.
- Dùng size = 0 cho aggregation-only request.
- Phân biệt max_result_window, max_inner_result_window và search.max_buckets.
- Kiểm thử ranh giới setting và hành vi thật trên Elasticsearch.
- Benchmark latency và tài nguyên thay vì chỉ đo response size.

index.max_result_window bảo vệ Elasticsearch khỏi các request from/size yêu cầu cửa sổ kết quả quá lớn. Với mặc định 10.000, một request chỉ hợp lệ khi from + size không vượt giới hạn. Deep pagination tốn CPU, heap, network và công việc merge vì các shard phải thu thập nhiều ứng viên hơn số hit cuối cùng được trả về. Tăng setting có thể mở rộng cửa sổ nhưng không loại bỏ chi phí. Với giao diện cần nhảy trang trong phạm vi nhỏ, Pageable vẫn phù hợp; với dữ liệu lớn cần đi tiếp tuần tự, search_after và PIT thường là lựa chọn tốt hơn; còn export/batch cần một chiến lược duyệt dữ liệu có kiểm soát.
