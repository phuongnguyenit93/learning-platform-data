# Phân trang truy vấn và giới hạn khi dữ liệu được phát thành Flux

Trong Spring Data Elasticsearch Reactive, một truy vấn có thể trả về dữ liệu dưới dạng Reactor `Flux<T>`. Điều này cho phép ứng dụng xử lý kết quả theo luồng, kết hợp với các toán tử reactive và điều tiết tốc độ tiêu thụ. Tuy nhiên, **Flux không tự động có nghĩa là Elasticsearch sẽ phát toàn bộ index thành một luồng vô hạn hoặc tự chuyển sang trang tiếp theo**.

Một request search vẫn có giới hạn số hit được trả về bởi Elasticsearch. Muốn đọc trang tiếp theo, ứng dụng phải tạo request mới với `Pageable`, hoặc dùng cơ chế phân trang sâu như `search_after`. Backpressure của Reactor điều khiển nhu cầu ở phía subscriber; nó không tự thay đổi `size`, `from` hay tự mở thêm search request.

Bài học này trình bày cách phân trang truy vấn reactive, giới hạn số dữ liệu phát ra, xử lý nhiều trang có kiểm soát và chọn cơ chế phù hợp khi tập dữ liệu lớn.

## 1. Flux trong truy vấn Elasticsearch Reactive

`Flux<T>` là publisher có thể phát ra không, một hoặc nhiều phần tử. Với Spring Data Elasticsearch Reactive, các API tìm kiếm thường trả về `Flux<SearchHit<T>>` hoặc `Flux<T>`, tùy phương thức được gọi.

Ví dụ:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;

Flux<SearchHit<ProductDocument>> hits =
        operations.search(query, ProductDocument.class);
~~~

Mỗi `SearchHit<ProductDocument>` đại diện cho một kết quả và có thể chứa:

- Entity đã được chuyển đổi qua Spring Data.
- Document ID và tên index.
- Điểm liên quan.
- Sort values.
- Highlight fields và metadata khác nếu request yêu cầu.

Nếu chỉ cần entity, có thể ánh xạ:

~~~java
Flux<ProductDocument> products =
        operations.search(query, ProductDocument.class)
                .map(SearchHit::getContent);
~~~

Một `Flux` từ một request search thường là luồng hữu hạn chứa các hit của request đó. Số hit bị giới hạn bởi query và cấu hình phân trang. Nó hoàn tất sau khi phát xong kết quả của request.

## 2. Flux không tự động phân trang

Giả sử query được gửi với `size = 20`. Elasticsearch trả về tối đa 20 hit cho request đó. Khi subscriber nhận hết 20 hit, Flux hoàn tất.

~~~text
Một request search:
  Elasticsearch trả hit 1 ... hit 20
                |
                v
       Flux<SearchHit<T>>
                |
                v
       Subscriber nhận 20 hit
                |
                v
             complete
~~~

Nếu index có 10.000 document, việc nhận được 20 hit không có nghĩa Reactor sẽ tự gửi request tiếp theo để lấy hit 21 đến 40.

Cần phân biệt ba giới hạn:

| Giới hạn | Được điều khiển bởi | Ý nghĩa |
|---|---|---|
| Số hit Elasticsearch trả về | `size` và `from`, hoặc `search_after` | Kích thước và vị trí trang ở backend |
| Số phần tử subscriber yêu cầu | Reactive Streams demand | Số phần tử subscriber sẵn sàng nhận |
| Số phần tử ứng dụng giữ trong bộ nhớ | Các toán tử và cấu trúc ứng dụng | Mức buffering/accumulation ở phía client |

Ba giới hạn này liên quan nhưng không thay thế nhau. Ví dụ `take(5)` có thể chỉ phát năm phần tử cho subscriber, dù request backend đã lấy cả trang 100 hit.

## 3. Phân trang bằng Pageable

Với phân trang thông thường, Spring Data sử dụng `Pageable`. `PageRequest.of(page, size)` tạo một trang có chỉ số bắt đầu từ 0.

Ví dụ lấy 20 sản phẩm ở trang đầu:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();
~~~

Trang tiếp theo:

~~~java
NativeQuery nextQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(PageRequest.of(1, 20))
        .build();
~~~

Với `page = 0`, `size = 20`, request lấy các vị trí đầu tiên. Với `page = 1`, request lấy trang kế tiếp theo offset tương ứng.

Công thức offset:

\[
from = page \times size
\]

Ví dụ:

| Page (0-based) | Size | From |
|---:|---:|---:|
| 0 | 20 | 0 |
| 1 | 20 | 20 |
| 2 | 20 | 40 |
| 3 | 20 | 60 |

Không nhầm page index với vị trí hit. Trang bắt đầu từ 0, còn vị trí hit bắt đầu từ 0 theo offset.

## 4. Reactive repository với Pageable và Flux

Reactive repository có thể nhận `Pageable` như một tham số và trả kết quả dưới dạng `Flux<T>`.

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByStatus(
            String status,
            Pageable pageable
    );

    Mono<Long> countByStatus(String status);
}
~~~

Cách gọi:

~~~java
Pageable firstPage = PageRequest.of(0, 25);

Flux<ProductDocument> products =
        productRepository.findByStatus("PUBLISHED", firstPage);
~~~

`Flux` trả các document trong trang được yêu cầu. Nếu cần tổng số document phù hợp, có thể gọi một phương thức count riêng:

~~~java
Mono<Long> total =
        productRepository.countByStatus("PUBLISHED");
~~~

Trong reactive flow, không nên mong đợi một `Page<T>` đồng bộ chứa cả content và total count nếu API repository không hỗ trợ kiểu trả về đó. Việc lấy count có thể là một truy vấn bất đồng bộ riêng.

Một lựa chọn khác là dùng `ReactiveElasticsearchOperations.searchForPage(...)` để nhận `Mono<SearchHits<T>>`, trong đó có danh sách hit và metadata cấp response.

## 5. Phân biệt search trả Flux và searchForPage trả Mono

Spring Data Elasticsearch Reactive cung cấp các kiểu kết quả phù hợp với hai nhu cầu:

| API | Kết quả | Khi dùng |
|---|---|---|
| `search(query, Entity.class)` | `Flux<SearchHit<Entity>>` | Muốn xử lý từng hit của request |
| `searchForPage(query, Entity.class)` | `Mono<SearchHits<Entity>>` | Muốn metadata và danh sách hit của một trang |
| Repository method trả `Flux<Entity>` | `Flux<Entity>` | Muốn entity trực tiếp theo query method |
| Repository count method | `Mono<Long>` | Muốn tổng số document phù hợp |

Ví dụ dùng `searchForPage`:

~~~java
Mono<SearchHits<ProductDocument>> pageResult =
        operations.searchForPage(query, ProductDocument.class);

Flux<ProductDocument> productsInPage =
        pageResult.flatMapMany(result ->
                Flux.fromIterable(result.getSearchHits())
                        .map(SearchHit::getContent)
        );
~~~

`SearchHits<T>` cung cấp:

- `getSearchHits()`: danh sách hit trong trang.
- `getTotalHits()`: tổng số hit được báo cáo trong response.
- `getMaxScore()`: score cao nhất nếu có.
- `getAggregations()`: aggregation container nếu query có aggregation.
- Metadata khác tùy loại request và phiên bản.

`searchForPage` vẫn chỉ trả một trang theo `Pageable`. Kiểu trả về `Mono` không tự động lấy các trang tiếp theo.

## 6. Tạo query theo từng trang

Có thể viết một hàm tạo query theo số trang:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

private Query queryForPage(int page, int pageSize) {
    return NativeQuery.builder()
            .withQuery(elasticsearchQuery)
            .withPageable(PageRequest.of(page, pageSize))
            .build();
}
~~~

Sau đó thực hiện một trang:

~~~java
Mono<SearchHits<ProductDocument>> fetchPage(int page) {
    Query query = queryForPage(page, 50);
    return operations.searchForPage(query, ProductDocument.class);
}
~~~

Để đọc trang đầu:

~~~java
Flux<ProductDocument> firstPage =
        fetchPage(0)
                .flatMapMany(result ->
                        Flux.fromIterable(result.getSearchHits())
                                .map(SearchHit::getContent)
                );
~~~

Nếu chỉ cần một trang, dừng tại đây. Không cần tạo vòng lặp hoặc lấy count toàn bộ index.

## 7. Đọc nhiều trang tuần tự thành một Flux

Nếu nghiệp vụ cần xử lý toàn bộ tập kết quả theo từng trang, ứng dụng phải chủ động tạo request tiếp theo.

Một cách đơn giản là dùng đệ quy có trì hoãn bằng `Flux.defer(...)`. Mỗi lần chỉ tải trang kế tiếp sau khi trang hiện tại đã được phát xong.

~~~java
private static final int PAGE_SIZE = 200;
private static final int MAX_PAGES = 100;

private Flux<ProductDocument> readPages(int page) {
    if (page >= MAX_PAGES) {
        return Flux.error(
                new IllegalStateException("Maximum page limit reached")
        );
    }

    Query query = queryForPage(page, PAGE_SIZE);

    return operations.searchForPage(query, ProductDocument.class)
            .flatMapMany(result -> {
                List<SearchHit<ProductDocument>> pageHits =
                        result.getSearchHits();

                Flux<ProductDocument> currentPage =
                        Flux.fromIterable(pageHits)
                                .map(SearchHit::getContent);

                if (pageHits.size() < PAGE_SIZE) {
                    return currentPage;
                }

                return currentPage.concatWith(
                        Flux.defer(() -> readPages(page + 1))
                );
            });
}
~~~

Cách hoạt động:

1. Gửi query cho trang hiện tại.
2. Nhận `Mono<SearchHits<T>>`.
3. Chuyển các hit trong trang thành Flux.
4. Nếu số hit ít hơn page size, đây là trang cuối.
5. Nếu trang đầy, chỉ sau khi trang hiện tại được phát xong mới gọi trang kế tiếp.
6. Nếu vượt giới hạn số trang, publisher phát lỗi để caller biết quá trình bị giới hạn.

Nếu tổng số document là bội số chính xác của page size, ví dụ 400 document với page size 200, flow sẽ yêu cầu thêm một trang rỗng để xác định đã hết dữ liệu. Đây là hành vi hợp lệ.

Giới hạn `MAX_PAGES` giúp bảo vệ một job khỏi chạy quá lâu hoặc đọc nhiều dữ liệu hơn dự kiến. Trong ứng dụng thực tế, giá trị này nên lấy từ cấu hình và có log/metric khi đạt giới hạn.

## 8. Vì sao dùng concatWith và Flux.defer?

`concatWith` nối hai publisher theo thứ tự: publisher đầu hoàn tất rồi mới subscribe publisher tiếp theo.

`Flux.defer` trì hoãn việc tạo publisher trang kế tiếp cho đến khi subscriber thực sự cần và trang hiện tại đã hoàn tất.

So sánh:

~~~java
return currentPage.concatWith(
        Flux.defer(() -> readPages(page + 1))
);
~~~

Với cách này, các trang được đọc tuần tự. Nó tránh tạo trước hàng trăm request search cùng lúc.

Không nên viết:

~~~java
return Flux.concat(
        readPages(page + 1),
        currentPage
);
~~~

Ví dụ trên còn đảo thứ tự trang và không thể hiện đúng ý định nối trang hiện tại trước trang tiếp theo.

Cũng không nên tạo một danh sách lớn các publisher bằng cách gọi hàm fetch page ngay từ đầu nếu không cần. Hãy trì hoãn request và chỉ tạo trang tiếp theo khi luồng đang được tiêu thụ.

## 9. Backpressure điều khiển tốc độ tiêu thụ

Reactive Streams có cơ chế demand. Subscriber có thể yêu cầu số phần tử mà nó sẵn sàng nhận. Reactor truyền nhu cầu này ngược lên upstream khi các publisher hỗ trợ backpressure.

Ví dụ:

~~~java
Flux<ProductDocument> products = readPages(0);

products
        .limitRate(32)
        .subscribe(this::processProduct);
~~~

`limitRate(32)` điều chỉnh cách Reactor yêu cầu dữ liệu upstream theo từng đợt. Nó có thể giúp điều tiết tốc độ phát trong pipeline, nhưng **không đổi page size của Elasticsearch thành 32**.

Nếu một trang backend có 200 hit, request search vẫn có thể lấy 200 hit. Reactor điều tiết việc phát các phần tử đó cho downstream.

Backpressure hữu ích khi:

- Consumer ghi dữ liệu sang hệ thống khác chậm hơn tốc độ đọc.
- Mỗi item cần xử lý CPU hoặc I/O.
- Muốn tránh downstream bị dồn quá nhiều phần tử cùng lúc.
- Pipeline gồm nhiều bước reactive có thể truyền demand.

Backpressure không tự giảm chi phí query ở Elasticsearch nếu request vẫn yêu cầu một trang quá lớn.

## 10. Phân biệt take, limitRate và Pageable size

Các toán tử thường bị nhầm lẫn:

| Cơ chế | Tác dụng | Có thay đổi size ở Elasticsearch không? |
|---|---|---|
| `PageRequest.of(page, size)` | Xác định trang và số hit backend trả | Có |
| `take(n)` | Chỉ phát tối đa n phần tử xuống downstream | Không tự động |
| `limitRate(n)` | Điều tiết demand giữa subscriber và upstream | Không |
| `buffer(n)` | Gom n phần tử thành một nhóm | Không |
| `collectList()` | Thu toàn bộ phần tử thành một List | Không |
| `onBackpressureBuffer()` | Lưu tạm phần tử khi downstream không theo kịp | Không |

Ví dụ:

~~~java
operations.search(queryWithPageSize100, ProductDocument.class)
        .take(5);
~~~

Elasticsearch có thể đã trả về một trang 100 hit, nhưng downstream chỉ nhận tối đa 5 hit. Điều này không tương đương với query backend có `size = 5`.

Nếu chỉ cần 5 document, hãy đặt page size là 5:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(PageRequest.of(0, 5))
        .build();
~~~

Có thể kết hợp cả hai khi muốn bảo vệ cả backend lẫn downstream, nhưng phải hiểu mỗi giới hạn áp dụng ở tầng nào.

## 11. Giới hạn page size và bộ nhớ

Page size lớn làm giảm số request cần gửi nhưng tăng lượng dữ liệu phải:

- Được Elasticsearch tìm và serialize.
- Truyền qua mạng.
- Deserialize ở client.
- Giữ trong bộ nhớ trong khi xử lý.
- Chuyển đổi thành entity và phát xuống pipeline.

Page size quá nhỏ làm tăng số round trip và overhead request.

Một lựa chọn thực tế cần dựa trên kích thước document, số field được trả, độ trễ mạng và tốc độ xử lý downstream. Không có một page size tối ưu cho mọi index.

Có thể đặt giới hạn ở tầng service:

~~~java
private int normalizePageSize(int requestedSize) {
    int defaultSize = 50;
    int maxSize = 500;

    if (requestedSize <= 0) {
        return defaultSize;
    }

    return Math.min(requestedSize, maxSize);
}
~~~

Không tin trực tiếp page size do client gửi lên. Một request với size hàng trăm nghìn có thể tạo tải lớn và làm tăng heap usage ở cả ứng dụng lẫn Elasticsearch.

Nên có thêm giới hạn:

- Số trang tối đa cho export.
- Tổng thời gian chạy.
- Số request đồng thời.
- Kích thước batch đầu ra.
- Số document được phép xử lý trong một job.

## 12. Giới hạn from/size của Elasticsearch

Phân trang bằng `Pageable` thường được chuyển thành `from/size`. Elasticsearch có giới hạn `index.max_result_window`; giá trị mặc định phổ biến là 10.000.

Ví dụ:

- `page = 0, size = 100`: from = 0.
- `page = 50, size = 100`: from = 5.000.
- `page = 100, size = 100`: from = 10.000.

Request có `from + size` vượt giới hạn có thể bị từ chối.

Tăng `max_result_window` có thể làm request sâu được chấp nhận, nhưng Elasticsearch phải giữ và xử lý nhiều kết quả trước vị trí cần trả. Việc tăng giới hạn không biến offset pagination thành cơ chế hiệu quả cho hàng triệu document.

Dùng `from/size` cho phân trang giao diện ở độ sâu vừa phải. Với export hoặc quét lượng lớn document, cân nhắc `search_after` kết hợp PIT.

## 13. Sort ổn định khi đọc nhiều trang

Khi phân trang, thứ tự kết quả cần ổn định. Nếu chỉ sort theo field không duy nhất như `createdAt`, nhiều document có thể có cùng giá trị. Thứ tự giữa chúng có thể thay đổi giữa các request.

Nên thêm một tie-breaker duy nhất có mapping hỗ trợ sort:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("productId")
);

Pageable pageable = PageRequest.of(0, 100, sort);
~~~

Ở đây `productId` cần là field keyword có giá trị duy nhất trong phạm vi tập dữ liệu đang đọc.

Không nên sort trực tiếp trên metadata `_id` như một keyword field có doc values. Nếu cần tie-breaker theo ID, lưu một field keyword tương ứng trong source.

Sort ổn định giúp giảm nguy cơ document bị lặp hoặc bỏ sót do các giá trị sort bằng nhau. Tuy nhiên, nó không giữ snapshot dữ liệu nếu index thay đổi giữa các request.

## 14. Dữ liệu thay đổi giữa các trang

`from/size` gửi nhiều request độc lập. Nếu document được thêm, xóa hoặc cập nhật giữa các request, vị trí offset có thể dịch chuyển.

Ví dụ:

1. Trang đầu lấy document 1 đến 20.
2. Một document mới được thêm vào đầu thứ tự sort.
3. Trang tiếp theo dùng `from = 20`.
4. Một document đã thấy có thể xuất hiện lại hoặc một document khác bị bỏ qua.

Nếu ứng dụng cần snapshot nhất quán trong lúc đọc nhiều trang, hãy cân nhắc Point in Time (PIT) kết hợp `search_after`. PIT giữ góc nhìn dữ liệu đã mở; `search_after` dùng sort values của hit cuối để tiếp tục.

PIT không khóa ghi. Các thay đổi sau thời điểm mở PIT không được đưa vào snapshot đang dùng. Cần đóng PIT sau khi hoàn tất và gia hạn keep alive theo thời gian giữa các request.

## 15. Phân trang sâu bằng search_after

`search_after` tiếp tục từ sort values của hit cuối trang trước, thay vì dùng offset lớn.

Ví dụ query:

~~~java
NativeQuery firstPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .build();
~~~

Sau khi nhận trang, lấy sort values của hit cuối:

~~~java
List<SearchHit<ProductDocument>> hits = searchHits.getSearchHits();

List<Object> searchAfter = hits
        .get(hits.size() - 1)
        .getSortValues();
~~~

Query tiếp theo giữ nguyên query và sort, đồng thời truyền con trỏ:

~~~java
NativeQuery nextPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withSearchAfter(searchAfter)
        .build();
~~~

`search_after` không phải page number. Giữ page index ở 0 và dùng sort values để xác định vị trí tiếp tục.

Với dữ liệu có thể thay đổi, kết hợp PIT để các trang nhìn cùng một snapshot. Các API mở/đóng PIT và gắn PIT vào query cần dùng đúng reactive API được hỗ trợ trong phiên bản Spring Data Elasticsearch của dự án; một số phiên bản cung cấp phương thức reactive trên operations, còn trường hợp khác có thể cần dùng Java API Client phù hợp.

Khi nhận response mới, cập nhật PIT ID nếu Elasticsearch trả ID mới. Dùng ID mới nhất cho request tiếp theo và khi đóng PIT.

## 16. Đọc nhiều trang search_after thành Flux

Có thể mô hình hóa mỗi trang như một bước reactive:

1. Gửi query hiện tại.
2. Phát các hit của trang.
3. Lấy sort values của hit cuối.
4. Tạo query kế tiếp bằng search_after.
5. Lặp đến khi trang rỗng hoặc ít hơn page size.

Pseudocode:

~~~java
private Flux<ProductDocument> readAfter(List<Object> cursor) {
    NativeQuery query = buildQueryWithSearchAfter(cursor);

    return operations.searchForPage(query, ProductDocument.class)
            .flatMapMany(result -> {
                List<SearchHit<ProductDocument>> hits =
                        result.getSearchHits();

                Flux<ProductDocument> current =
                        Flux.fromIterable(hits)
                                .map(SearchHit::getContent);

                if (hits.size() < PAGE_SIZE) {
                    return current;
                }

                List<Object> nextCursor =
                        hits.get(hits.size() - 1).getSortValues();

                return current.concatWith(
                        Flux.defer(() -> readAfter(nextCursor))
                );
            });
}
~~~

`buildQueryWithSearchAfter(...)` phải giữ nguyên query, sort, page size và PIT metadata. Đây là pseudocode tập trung vào cấu trúc luồng; chữ ký mở/đóng PIT và builder cụ thể cần khớp phiên bản Spring Data Elasticsearch đang dùng.

Không tính lại cursor từ entity. Hãy dùng `getSortValues()` của response để giữ đúng kiểu dữ liệu và thứ tự sort.

## 17. Dùng concatMap và flatMap đúng cách

Khi mỗi trang được tải từ một publisher, toán tử nối trang ảnh hưởng thứ tự và mức concurrency.

| Toán tử | Hành vi | Dùng khi |
|---|---|---|
| `concatMap` | Subscribe tuần tự, giữ thứ tự nguồn | Trang sau phụ thuộc cursor trang trước |
| `flatMap` | Có thể chạy nhiều publisher đồng thời, kết quả xen kẽ | Các request độc lập và không cần thứ tự |
| `flatMapSequential` | Cho phép chạy đồng thời nhưng phát theo thứ tự nguồn | Cần giữ thứ tự nhưng chấp nhận buffering |

Với pagination dùng `search_after`, trang tiếp theo phụ thuộc sort values của trang hiện tại. Không thể tạo trước tất cả request song song vì chưa có cursor của các trang sau.

Với các page number độc lập, có thể dùng concurrency giới hạn nếu dữ liệu không cần thứ tự:

~~~java
Flux.range(0, 10)
        .flatMap(
                page -> fetchPage(page),
                2
        );
~~~

Tham số concurrency là 2, nên tối đa hai page request được subscribe đồng thời. Nhưng nếu phát kết quả trực tiếp, các trang có thể hoàn thành không theo thứ tự. Nếu cần giữ thứ tự trang, dùng `flatMapSequential` hoặc `concatMap`, đồng thời cân nhắc buffering.

Không dùng concurrency không giới hạn cho hàng trăm hoặc hàng nghìn trang.

## 18. Giới hạn tổng số kết quả với take

Nếu API cho phép client yêu cầu tối đa N kết quả, có thể giới hạn ở hai tầng:

- Giới hạn page size hoặc tổng số trang ở backend.
- Dùng `take(N)` như hàng rào bổ sung ở reactive pipeline.

Ví dụ:

~~~java
Flux<ProductDocument> limited =
        readPages(0)
                .take(1_000);
~~~

`take(1_000)` dừng phát sau 1.000 phần tử và hủy upstream subscription. Nếu logic phân trang tạo request kế tiếp bằng `defer`, việc hủy có thể ngăn các trang chưa bắt đầu được tải.

Tuy nhiên, request đang chạy có thể đã gửi đến Elasticsearch và có thể đã lấy cả trang. Vì vậy, `take` không thay thế page size hoặc giới hạn backend.

Nếu page size là 200 và take là 1.000, luồng có thể tải tối đa các trang cần thiết để phát đủ 1.000 kết quả. Trang cuối có thể chỉ được tiêu thụ một phần.

## 19. Tránh collectList trên tập dữ liệu lớn

`collectList()` gom tất cả phần tử thành một List và chỉ phát Mono sau khi toàn bộ luồng hoàn tất:

~~~java
Mono<List<ProductDocument>> allProducts =
        readPages(0).collectList();
~~~

Cách này tiện khi số kết quả nhỏ và cần xử lý toàn bộ cùng lúc. Nhưng với hàng trăm nghìn hoặc hàng triệu document, list có thể chiếm nhiều heap và gây OutOfMemoryError.

Với export hoặc batch processing, xử lý từng phần tử hoặc gom thành batch có kích thước cố định:

~~~java
readPages(0)
        .buffer(200)
        .concatMap(batch -> exportBatch(batch));
~~~

`buffer(200)` tạo các list tối đa 200 phần tử, giúp giới hạn bộ nhớ ở mức batch thay vì giữ toàn bộ tập kết quả.

Nếu `exportBatch(...)` thực hiện I/O, nên trả về publisher reactive thay vì gọi blocking API bên trong pipeline.

## 20. Xử lý lỗi trong quá trình phân trang

Một luồng phân trang có thể lỗi ở bất kỳ request trang nào:

- Timeout hoặc mất kết nối.
- Query không hợp lệ.
- Mapping không tương thích.
- Vượt giới hạn `max_result_window`.
- PIT hết hạn.
- Shard failure.
- Lỗi xử lý downstream khi ghi batch.

Nếu một trang lỗi, Flux thường phát error và kết thúc. Các trang sau không tiếp tục tự động.

Có thể ghi log và chuyển lỗi thành kết quả nghiệp vụ:

~~~java
readPages(0)
        .doOnError(error ->
                log.error("Product export failed", error)
        )
        .onErrorMap(error ->
                new ProductExportException("Unable to read products", error)
        );
~~~

Không dùng `onErrorResume(error -> Flux.empty())` một cách tùy tiện. Cách đó có thể biến một export thiếu dữ liệu thành kết quả thành công rỗng.

Nếu retry, chỉ retry lỗi có khả năng phục hồi. Với timeout không rõ request đã hoàn tất hay chưa, đọc search thường an toàn hơn update, nhưng vẫn cần giữ cùng query/cursor và chính sách snapshot. Với PIT hết hạn, mở PIT mới không tái tạo được snapshot cũ; cần quyết định khởi động lại hoặc đối soát.

## 21. Timeout, cancellation và deadline

Một export reactive nên có giới hạn thời gian và khả năng hủy:

~~~java
readPages(0)
        .timeout(Duration.ofMinutes(10))
        .doOnCancel(() -> log.info("Product export cancelled"));
~~~

`timeout(...)` giới hạn thời gian chờ theo cấu hình Reactor. Nếu hết hạn, publisher phát lỗi timeout.

`doOnCancel(...)` giúp ghi nhận subscriber đã hủy. Đây không phải bằng chứng rằng mọi request backend đã được dừng ngay lập tức; việc hủy request phụ thuộc client và trạng thái network call.

Nếu đang dùng PIT, hãy đảm bảo đường cleanup được thực hiện khi hoàn tất, lỗi hoặc cancellation. Có thể dùng `usingWhen` để gắn lifecycle của resource bất đồng bộ với publisher:

~~~java
Flux<ProductDocument> export =
        Flux.usingWhen(
                openPit(),
                pitId -> readPagesWithPit(pitId),
                this::closePit,
                (pitId, error) -> closePit(pitId),
                this::closePit
        );
~~~

Đây là cấu trúc minh họa. `openPit()` và `closePit(...)` cần trả về publisher reactive phù hợp với API PIT của phiên bản đang dùng. Mục tiêu là đóng PIT khi publisher complete, error hoặc cancel.

## 22. Giới hạn số request và backpressure ở downstream

Nếu mỗi hit được chuyển tiếp tới một service khác, tốc độ xử lý downstream có thể thấp hơn tốc độ đọc.

Ví dụ xử lý tuần tự:

~~~java
readPages(0)
        .concatMap(product -> inventoryClient.update(product));
~~~

`concatMap` chờ xử lý publisher của một sản phẩm hoàn tất trước khi chuyển sang sản phẩm kế tiếp. Điều này giữ concurrency thấp nhưng có thể giảm throughput.

Có thể cho phép số tác vụ đồng thời hữu hạn:

~~~java
readPages(0)
        .flatMap(
                product -> inventoryClient.update(product),
                8
        );
~~~

Tối đa tám thao tác downstream được chạy đồng thời. Nếu thứ tự không quan trọng và hệ thống đích chịu được tải, cách này có thể tăng throughput.

Hãy chọn concurrency theo khả năng của hệ thống đích, connection pool và giới hạn rate. Không tăng concurrency chỉ để làm Flux phát nhanh hơn nếu Elasticsearch hoặc service downstream đang quá tải.

## 23. Tránh blocking trong reactive pipeline

Không gọi `block()` hoặc `toIterable()` bên trong pipeline reactive:

~~~java
// Không nên:
Flux<ProductDocument> products =
        operations.search(query, ProductDocument.class)
                .map(SearchHit::getContent)
                .map(product -> blockingService.enrich(product).block());
~~~

Blocking làm thread xử lý reactive phải chờ và có thể gây starvation hoặc deadlock trong một số scheduler.

Nếu có thư viện chỉ hỗ trợ blocking, hãy cô lập nó trên scheduler phù hợp:

~~~java
Flux<ProductDocument> enriched =
        products.flatMap(product ->
                Mono.fromCallable(() -> blockingService.enrich(product))
                        .subscribeOn(Schedulers.boundedElastic())
        );
~~~

Đây là giải pháp tương thích cho công việc blocking có giới hạn. Ưu tiên client reactive end-to-end nếu có.

Không gọi `subscribe()` bên trong service chỉ để khởi chạy công việc rồi trả về void. Hãy trả `Flux` hoặc `Mono` cho caller để caller kiểm soát subscription, cancellation và lỗi.

## 24. Tổng số hit không phải lúc nào cũng là count chính xác

`SearchHits.getTotalHits()` hữu ích khi giao diện cần hiển thị số lượng kết quả. Nhưng Elasticsearch có thể giới hạn việc đếm chính xác total hits theo cấu hình tracking.

Nếu cần tổng số chính xác để tính tổng trang, hãy xác định query có bật theo dõi tổng hit phù hợp hay không. Với tập dữ liệu lớn, việc đếm chính xác có thể tốn chi phí.

Đối với job đọc tuần tự, thường có thể dừng khi trang trả về ít hit hơn page size hoặc trang rỗng. Cách này tránh phải lấy tổng count trước khi bắt đầu. Nếu page cuối có số hit đúng bằng page size, có thể cần thêm một request rỗng để xác nhận kết thúc.

Không nên tính `totalPages` từ một total hit có thể bị giới hạn rồi giả định số trang đó luôn chính xác.

## 25. Search after và PIT cho luồng dữ liệu lớn

Với export sâu hoặc hàng triệu document, `from/size` không phải lựa chọn phù hợp. `search_after` dùng sort values của hit cuối để tiếp tục, còn PIT giữ snapshot nhất quán qua nhiều request.

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Mở PIT"] --> B["Search trang đầu"]
    B --> C["Phát hit của trang"]
    C --> D["Lấy sort values cuối trang"]
    D --> E["Cập nhật PIT ID nếu response trả ID mới"]
    E --> F["Search với search_after"]
    F --> G{"Có thêm hit?"}
    G -->|Có| C
    G -->|Không| H["Đóng PIT"]
~~~

Các nguyên tắc:

- Query và sort phải giữ nguyên giữa các trang.
- Sort cần có tie-breaker ổn định.
- Dùng sort values từ hit cuối, không tự tạo cursor từ entity.
- Dùng PIT ID mới nhất nếu response trả ID mới.
- Gia hạn keep alive đủ cho thời gian xử lý giữa các request.
- Đóng PIT khi complete, error hoặc cancel.
- Nếu PIT hết hạn, không mở PIT mới rồi dùng cursor cũ như thể cùng snapshot.

Reactive flow chỉ thay đổi cách ứng dụng phối hợp I/O và xử lý kết quả. Nó không thay đổi yêu cầu về cursor, sort ổn định hoặc lifecycle của PIT.

## 26. Phân trang và bảo mật API

Nếu API cho client truyền page và size, cần xác thực và giới hạn:

~~~java
int page = Math.max(requestedPage, 0);
int size = normalizePageSize(requestedSize);

Pageable pageable = PageRequest.of(page, size);
~~~

Ngoài page/size, query cần áp dụng filter theo tenant, quyền truy cập và phạm vi dữ liệu từ server. Không để client tự bỏ qua filter bảo mật bằng cách gửi query hoặc cursor tùy ý.

Với cursor `search_after`, không nên để client sửa trực tiếp sort values hoặc PIT ID. Có thể đóng gói chúng thành token opaque do server tạo và ký/mã hóa. Token nên gắn với query fingerprint, tenant, page size và thời hạn.

Backpressure không phải cơ chế bảo mật hoặc quota. Một subscriber có thể yêu cầu dữ liệu rất chậm hoặc giữ subscription mở lâu; API vẫn cần timeout, rate limit, giới hạn số trang và cleanup resource.

## 27. Các lỗi thường gặp

### Nghĩ Flux tự lấy toàn bộ index

Một search Flux thường chỉ phát các hit của request hiện tại. Tạo request trang kế tiếp hoặc dùng cursor rõ ràng.

### Dùng take thay cho backend page size

`take(n)` giới hạn phần tử phát ra, không nhất thiết giới hạn số hit Elasticsearch đã lấy. Đặt `Pageable` phù hợp.

### Nghĩ limitRate giảm size của search request

`limitRate` điều tiết demand của Reactor. Nó không thay đổi `size` trong Elasticsearch.

### Trả về Page đồng bộ trong reactive repository

Reactive repository nên trả `Flux`/`Mono`. Nếu cần total count, dùng count publisher hoặc `searchForPage` phù hợp.

### Tạo mọi page request song song

Các trang dùng `search_after` phụ thuộc cursor của trang trước. Dùng `concatMap` hoặc nối publisher theo thứ tự.

### Dùng flatMap không giới hạn

Concurrency quá lớn có thể gây áp lực lên Elasticsearch, connection pool và downstream. Đặt concurrency hữu hạn.

### collectList toàn bộ dữ liệu lớn

`collectList` giữ mọi phần tử trong heap. Xử lý theo từng hit hoặc buffer batch nhỏ.

### Dùng from/size vượt max_result_window

Phân trang sâu có thể bị từ chối hoặc tốn nhiều tài nguyên. Chuyển sang search_after/PIT cho export lớn.

### Không sort ổn định

Các document có cùng sort value có thể đổi thứ tự giữa các trang. Thêm tie-breaker duy nhất.

### Không xử lý dữ liệu thay đổi giữa các trang

Các request offset độc lập có thể nhìn các trạng thái index khác nhau. Dùng PIT nếu cần snapshot nhất quán.

### Nuốt lỗi bằng Flux.empty()

Export có thể bị coi là thành công dù mới đọc được một phần. Phát lỗi rõ ràng và ghi checkpoint nếu có khả năng tiếp tục.

### Không cleanup PIT khi cancel

Subscriber có thể hủy trước khi đọc hết. Gắn cleanup vào complete, error và cancel.

## 28. Quy trình chọn cách phân trang

Khi xây dựng truy vấn reactive:

1. Nếu chỉ cần một tập kết quả nhỏ, đặt page size rõ ràng và trả `Flux<SearchHit<T>>` hoặc `Flux<T>`.
2. Nếu cần metadata của một trang, dùng `searchForPage(...)` trả `Mono<SearchHits<T>>`.
3. Nếu cần nhiều trang vừa phải, tạo từng `PageRequest` và nối các publisher bằng `concatMap`/`concatWith`.
4. Giới hạn page size, số trang, thời gian và concurrency.
5. Dùng `take(n)` như giới hạn phát bổ sung, không thay cho giới hạn backend.
6. Tránh `collectList` trên tập kết quả lớn.
7. Với phân trang sâu, chuyển sang `search_after` và sort ổn định.
8. Dùng PIT nếu cần snapshot nhất quán giữa các request.
9. Xử lý cancellation, timeout, lỗi và cleanup resource.
10. Nếu API trả cursor cho client, bảo vệ cursor và gắn nó với query/tenant đã xác thực.
11. Theo dõi số hit, số trang, thời gian mỗi trang, retry và lỗi downstream.
12. Kiểm thử cả trang rỗng, trang cuối ngắn hơn page size và trang cuối đầy đủ đúng page size.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-repositories.html)
- [Spring Data Elasticsearch — Search Operations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ReactiveSearchOperations.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch — Point in time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)

## Kết luận

Trong Spring Data Elasticsearch Reactive, `Flux` biểu diễn kết quả được phát theo luồng nhưng không tự động phân trang. Backend page size do `Pageable` hoặc cursor điều khiển; Reactor backpressure điều tiết demand và tốc độ downstream. Với một trang, dùng `search(...)` hoặc `searchForPage(...)`; với nhiều trang, tạo request kế tiếp một cách tường minh và nối tuần tự bằng `concatWith`/`concatMap`. Giới hạn page size, số trang, concurrency và thời gian; tránh gom toàn bộ dữ liệu lớn vào `collectList`. Khi cần đọc sâu và nhất quán, dùng `search_after` với sort ổn định và PIT, đồng thời quản lý cancellation và cleanup resource.
