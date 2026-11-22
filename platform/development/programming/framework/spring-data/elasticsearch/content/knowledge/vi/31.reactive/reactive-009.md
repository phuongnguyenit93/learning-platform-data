# Backpressure, giới hạn concurrency và kiểm soát bộ nhớ

Trong Spring Data Elasticsearch Reactive, dữ liệu được xử lý qua `Mono` và `Flux` của Project Reactor. Reactive giúp ứng dụng xử lý I/O bất đồng bộ và truyền dữ liệu theo luồng, nhưng không tự động bảo đảm bộ nhớ luôn thấp hoặc Elasticsearch không bị quá tải. Nếu upstream phát dữ liệu nhanh hơn downstream xử lý, nếu `flatMap` mở quá nhiều request cùng lúc hoặc nếu ứng dụng gom toàn bộ kết quả vào một `List`, hệ thống vẫn có thể dùng hết heap.

Ba cơ chế cần thiết kế cùng nhau:

- **Backpressure:** điều tiết số phần tử downstream yêu cầu từ upstream.
- **Concurrency limit:** giới hạn số thao tác Elasticsearch hoặc tác vụ xử lý đang chạy đồng thời.
- **Memory bound:** giới hạn kích thước page, prefetch, queue, batch và số dữ liệu được giữ trong RAM.

Trong một pipeline reactive, backpressure điều tiết nhu cầu theo Reactive Streams; `flatMap`/`concatMap` quyết định mức xử lý đồng thời; còn page size, prefetch và các buffer quyết định lượng dữ liệu có thể nằm chờ. Muốn ingestion hoặc search ổn định, cần đặt giới hạn rõ ràng ở cả ba lớp.

## 1. Reactive không có nghĩa là không giới hạn bộ nhớ

Một pipeline có thể không block thread nhưng vẫn giữ rất nhiều object trong heap:

```java
repository.findAll()
    .collectList()
    .flatMap(products -> processAll(products));
```

`findAll()` trả `Flux`, nhưng `collectList()` yêu cầu giữ toàn bộ phần tử cho đến khi nguồn hoàn tất. Nếu index có hàng triệu document, danh sách có thể vượt quá bộ nhớ khả dụng.

Tương tự, pipeline dưới đây có thể mở quá nhiều request đồng thời:

```java
ids.flatMap(id -> repository.findById(id));
```

Overload `flatMap` không truyền concurrency rõ ràng sẽ dùng giá trị mặc định của Reactor. Giá trị mặc định có thể phù hợp với nhiều pipeline nhỏ, nhưng không nên coi đó là giới hạn đã được thiết kế theo năng lực Elasticsearch và kích thước document của ứng dụng.

Reactive chỉ cung cấp cơ chế truyền tín hiệu và điều tiết demand. Ứng dụng vẫn phải chọn page size, concurrency, prefetch, queue capacity và chính sách khi downstream chậm.

## 2. Reactive Streams demand và backpressure

Reactive Streams có bốn thành phần cơ bản:

- `Publisher`: phát dữ liệu.
- `Subscriber`: nhận dữ liệu.
- `Subscription`: kết nối giữa hai bên, cho phép subscriber yêu cầu thêm phần tử hoặc hủy.
- `request(n)`: subscriber thông báo muốn nhận tối đa thêm `n` phần tử.

Backpressure là cách downstream điều tiết lượng dữ liệu yêu cầu từ upstream. Downstream xử lý xong một phần tử hoặc một nhóm phần tử rồi mới yêu cầu thêm.

```text
Elasticsearch / Publisher
          |
          | onNext(item)
          v
       Operator A
          |
          v
       Operator B
          |
          v
      Subscriber
          |
          | request(n)
          +-----------------------> upstream
```

Trong Reactor, phần lớn operator giữ và truyền demand theo Reactive Streams. Một số operator có queue hoặc prefetch để lấy trước một lượng phần tử nhằm tăng throughput. Vì vậy, backpressure không có nghĩa upstream chỉ phát đúng một item sau khi downstream xử lý xong item trước; pipeline có thể có một lượng dữ liệu đang được yêu cầu hoặc xếp hàng.

### Ví dụ Subscriber yêu cầu theo lô

Ở mức Reactive Streams, subscriber có thể yêu cầu 10 phần tử, xử lý chúng, sau đó yêu cầu thêm 10. Khi dùng Reactor operators thông thường, framework quản lý subscription và demand giúp ứng dụng; ta thường cấu hình operator thay vì tự viết `Subscriber`.

## 3. Backpressure trong Spring Data Elasticsearch

Các API reactive của Spring Data Elasticsearch trả về `Mono<T>` hoặc `Flux<T>`. Ví dụ repository:

```java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByCategory(String category);
}
```

Ví dụ service đọc kết quả:

```java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<ProductDocument> search(Query query) {
    return operations.search(query, ProductDocument.class)
        .map(SearchHit::getContent);
}
```

`Flux` cho phép consumer nhận kết quả bất đồng bộ. Nếu downstream là WebFlux response hoặc một operator reactive khác, demand có thể lan truyền ngược qua pipeline. Tuy nhiên, một search request vẫn có thể lấy về một page với kích thước đã cấu hình; demand của downstream không tự động làm Elasticsearch trả page nhỏ hơn.

### Backpressure không phải giới hạn page size

Có hai tầng khác nhau:

1. Elasticsearch quyết định mỗi search request trả tối đa bao nhiêu hit qua `size`/pageable.
2. Reactor quyết định downstream nhận và xử lý các phần tử từ publisher theo demand và prefetch.

Nếu một request search lấy 5.000 hit, toàn bộ response page có thể đã được deserialize trước khi downstream xử lý từng hit. Đặt `limitRate(10)` không biến page 5.000 hit thành request Elasticsearch có `size=10`.

## 4. Giới hạn concurrency với `flatMap`

`flatMap` chuyển mỗi phần tử thành một publisher con và cho phép nhiều publisher con chạy đồng thời. Tham số `concurrency` giới hạn số inner publisher hoạt động cùng lúc.

```java
Flux<ProductDocument> saved = products
    .flatMap(repository::save, 8);
```

Ở đây tối đa 8 thao tác save được subscribe đồng thời qua pipeline này. Đây là giới hạn ở cấp subscription/pipeline, không phải giới hạn toàn cluster. Nếu có 10 instance ứng dụng, mỗi instance chạy concurrency 8, tổng số thao tác có thể lên tới khoảng 80, chưa kể các pipeline khác.

### Chọn concurrency

| Concurrency | Hành vi | Đánh đổi |
|---:|---|---|
| 1 | Một inner publisher tại một thời điểm | Dễ kiểm soát, throughput có thể thấp |
| 4–8 | Một số request đồng thời có giới hạn | Điểm bắt đầu để benchmark |
| 16–32 | Tăng mức song song | Có thể tăng throughput nhưng cũng tăng in-flight requests và heap |
| Rất lớn/không giới hạn | Nhiều request cùng lúc | Dễ gây queue lớn, áp lực connection pool, thread, heap và Elasticsearch |

Không có con số tối ưu chung. Bắt đầu với concurrency nhỏ, đo throughput và p95/p99 latency, sau đó tăng từng bước cho đến khi throughput không tăng thêm hoặc tài nguyên bắt đầu bão hòa.

### `flatMap` không đảm bảo thứ tự

Các inner publisher hoàn tất theo tốc độ riêng, nên output có thể khác thứ tự input. Nếu thứ tự không quan trọng, `flatMap` thường có throughput tốt. Nếu cần giữ thứ tự phát ra, cân nhắc `flatMapSequential` hoặc `concatMap`.

## 5. `concatMap` khi cần xử lý tuần tự

`concatMap` chỉ subscribe inner publisher tiếp theo sau khi publisher hiện tại hoàn tất:

```java
Flux<UpdateResult> results = ids
    .concatMap(id -> updateOne(id));
```

Ưu điểm:

- Chỉ một thao tác inner đang chạy tại một thời điểm.
- Dễ giữ thứ tự xử lý.
- Giảm lượng request đang bay và đơn giản hóa trạng thái phụ thuộc tuần tự.

Hạn chế là throughput có thể thấp nếu mỗi request có latency cao. Nếu các document độc lập, có thể dùng `flatMap(..., concurrency)` với giới hạn vừa phải.

## 6. `flatMapSequential` khi cần output có thứ tự

`flatMapSequential` cho phép xử lý nhiều inner publisher đồng thời nhưng phát kết quả theo thứ tự nguồn:

```java
Flux<Result> results = ids
    .flatMapSequential(this::loadAndTransform, 8, 16);
```

Tham số `8` giới hạn concurrency; `16` là prefetch cho mỗi inner publisher. Vì các publisher sau có thể hoàn tất trước publisher đầu, kết quả hoàn tất sớm có thể phải chờ trong buffer để giữ thứ tự.

Do đó, giữ thứ tự có thể tăng bộ nhớ khi một tác vụ đầu bị chậm. Nếu không cần thứ tự, `flatMap` thường tránh được kiểu buffer chờ này.

## 7. Phân biệt concurrency, prefetch và `limitRate`

Các tham số này giải quyết những vấn đề khác nhau:

| Cơ chế | Điều khiển | Không có nghĩa là |
|---|---|---|
| `flatMap(mapper, concurrency)` | Số inner publisher đồng thời | Kích thước page Elasticsearch |
| `flatMap(mapper, concurrency, prefetch)` | Concurrency và lượng demand lấy trước từ mỗi inner | Giới hạn byte chính xác |
| `limitRate(highTide)` | Chia demand upstream thành các đợt nhỏ | Giới hạn số request Elasticsearch đồng thời |
| `buffer(n)` | Số item gom trong một buffer | Giới hạn tổng số item của nguồn |
| `onBackpressureBuffer(n)` | Sức chứa queue khi downstream chậm | Cơ chế tự giảm tốc mọi producer |

Ví dụ:

```java
Flux<Result> results = source
    .limitRate(64)
    .flatMap(this::callElasticsearch, 8, 16);
```

Ở đây `limitRate(64)` điều tiết demand từ upstream theo nhóm; `flatMap` cho phép tối đa 8 inner publisher; mỗi inner có prefetch 16. Không thể suy ra đây là đúng 64 hoặc 128 request đang chạy. Cần hiểu cách từng publisher phát dữ liệu và operator đặt queue.

## 8. Dùng `limitRate` để điều tiết demand

`limitRate` chia request upstream lớn thành các nhóm nhỏ hơn. Ví dụ:

```java
Flux<ProductDocument> products = repository.findAll()
    .limitRate(100);
```

Reactor sẽ điều tiết lượng demand gửi lên upstream theo high-tide và replenishment strategy của operator. Có thể truyền thêm `lowTide` để kiểm soát ngưỡng yêu cầu bổ sung:

```java
Flux<ProductDocument> products = repository.findAll()
    .limitRate(100, 75);
```

`limitRate` hữu ích khi muốn tránh upstream nhận một request demand quá lớn và muốn điều tiết việc phát phần tử qua pipeline. Tuy nhiên, nó không phải bộ giới hạn tốc độ theo giây, không giới hạn concurrency của nhiều inner publisher và không giảm `size` của một search request đã được gửi.

## 9. `onBackpressureBuffer`: buffer có giới hạn

Khi upstream không thể hoặc không tuân theo tốc độ downstream, có thể dùng buffer. Nhưng buffer không giới hạn mặc định là rủi ro nếu nguồn có thể phát nhiều dữ liệu.

Ví dụ buffer có sức chứa tối đa 1.000 item:

```java
import reactor.core.publisher.BufferOverflowStrategy;

Flux<Event> buffered = eventSource
    .onBackpressureBuffer(
        1_000,
        dropped -> log.warn("Backpressure buffer overflow: {}", dropped.id()),
        BufferOverflowStrategy.ERROR
    );
```

Khi queue đầy, chiến lược `ERROR` phát lỗi thay vì tiếp tục tăng bộ nhớ vô hạn. Ứng dụng có thể bắt lỗi ở biên pipeline, ghi nhận metric và xử lý theo chính sách nghiệp vụ.

### Không dùng unbounded buffer cho nguồn không giới hạn

```java
source.onBackpressureBuffer();
```

Overload không có giới hạn dung lượng có thể tích lũy dữ liệu nếu producer nhanh hơn consumer trong thời gian dài. Điều đó có thể biến một hệ thống không block thành hệ thống giữ ngày càng nhiều object trong heap.

### Chọn overflow strategy

| Strategy | Khi queue đầy | Phù hợp |
|---|---|---|
| `ERROR` | Kết thúc pipeline bằng lỗi | Dữ liệu không được phép mất; caller có thể retry hoặc dừng producer |
| `DROP_OLDEST` | Bỏ phần tử cũ nhất trong buffer | Chỉ cần trạng thái gần nhất, chấp nhận mất dữ liệu cũ |
| `DROP_LATEST` | Bỏ phần tử mới đến | Giữ dữ liệu đang chờ, chấp nhận bỏ cập nhật mới |

Chọn strategy theo ngữ nghĩa dữ liệu. Không dùng drop cho đơn hàng, thanh toán hoặc event cần được xử lý đầy đủ nếu chưa có durable retry mechanism.

## 10. `onBackpressureDrop`, `onBackpressureLatest` và `onBackpressureError`

Reactor có các operator xử lý khi downstream không theo kịp:

```java
source.onBackpressureDrop(item -> recordDropped(item));
```

`onBackpressureDrop` bỏ phần tử không thể chuyển tiếp theo demand hiện tại. Đây là lựa chọn mất dữ liệu có chủ đích.

```java
source.onBackpressureLatest();
```

`onBackpressureLatest` giữ lại phần tử mới nhất trong khi downstream chậm; các giá trị trung gian có thể bị bỏ. Hữu ích cho trạng thái snapshot, telemetry hoặc giá trị UI chỉ cần cập nhật mới nhất.

```java
source.onBackpressureError();
```

`onBackpressureError` biến tình trạng không đáp ứng demand thành lỗi. Đây là cách fail fast thay vì giữ một lượng dữ liệu không kiểm soát.

Các operator này không thay thế queue bền vững. Nếu producer là message broker, cần cân nhắc ack/nack, offset, retry và dead-letter queue để không mất event khi pipeline bị lỗi.

## 11. Kiểm soát bộ nhớ bằng page size

Với Elasticsearch search, page size là một trong những yếu tố quyết định lượng dữ liệu được lấy về mỗi request. Ví dụ tạo query với page size 500:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withPageable(PageRequest.of(0, 500))
    .build();
```

Sau đó xử lý từng hit:

```java
return operations.search(query, ProductDocument.class)
    .map(SearchHit::getContent)
    .flatMap(this::processProduct, 8);
```

Page size và concurrency có tác động khác nhau:

- Page size lớn hơn: một response chứa nhiều hit hơn, giảm số lần gọi trang nhưng tăng payload và bộ nhớ cho response.
- Concurrency lớn hơn: nhiều thao tác xử lý hoặc request có thể chạy cùng lúc, tăng số dữ liệu in-flight.
- Prefetch lớn hơn: operator có thể yêu cầu trước nhiều phần tử hơn, làm queue tăng.

Không đặt page size rất lớn chỉ để giảm số request. Hãy đo kích thước trung bình của `_source`, thời gian deserialize và heap trong một batch.

## 12. Backpressure không thay thế pagination

Một `Flux<SearchHit<T>>` có thể phát các hit của một trang, nhưng một search request vẫn có giới hạn kết quả theo `size`. Muốn quét nhiều trang, ứng dụng phải tạo cơ chế pagination phù hợp.

Với deep pagination hoặc export dữ liệu lớn, có thể dùng Point in Time (PIT) kết hợp `search_after` khi yêu cầu cần snapshot và sort ổn định. Scroll cũng có thể phù hợp cho một số tác vụ batch/export theo phiên bản Elasticsearch và client.

```text
Mở PIT
   |
   v
Search page 1 (size = 500)
   |
   v
Xử lý page 1 với concurrency giới hạn
   |
   v
Lấy sort values của hit cuối
   |
   v
Search page tiếp theo với search_after
   |
   +----> lặp cho đến khi hết hit
   |
   v
Đóng PIT
```

Nên lấy trang kế tiếp sau khi trang hiện tại đã được xử lý hoặc đã được đưa vào một hàng đợi có giới hạn. Nếu liên tục tải trang mới trước khi consumer xử lý xong trang cũ, ứng dụng có thể giữ nhiều page trong heap và mất lợi ích của backpressure.

## 13. Xử lý tuần tự từng page

Với pagination theo cursor, thường nên chỉ có một page request tiếp theo đang được tạo tại một thời điểm. Có thể dùng một luồng điều khiển đệ quy reactive hoặc `expand`/`concatMap` tùy cách biểu diễn cursor.

Pseudocode:

```java
Mono<Void> scanPages(Cursor cursor) {
    return fetchPage(cursor)
        .flatMap(page -> processPage(page)
            .then(Mono.defer(() -> {
                if (page.nextCursor() == null) {
                    return Mono.empty();
                }
                return scanPages(page.nextCursor());
            })));
}
```

Đây là mẫu điều khiển khái niệm; kiểu `Cursor`, `Page` và `fetchPage` do ứng dụng định nghĩa. Điểm quan trọng là chỉ lấy cursor tiếp theo sau khi `processPage` hoàn tất, nhờ đó số page giữ trong RAM được giới hạn.

Nếu cần xử lý hit trong page song song, giới hạn concurrency:

```java
Mono<Void> processPage(Page<ProductDocument> page) {
    return Flux.fromIterable(page.items())
        .flatMap(this::processOne, 8)
        .then();
}
```

Không dùng `flatMap` không giới hạn cho hàng nghìn hit trong một page nếu mỗi `processOne` mở request Elasticsearch hoặc gọi dịch vụ khác.

## 14. Giới hạn concurrency toàn ứng dụng

Tham số `flatMap(..., 8)` chỉ giới hạn một subscription. Trong hệ thống có nhiều request HTTP, scheduler và consumer, mỗi request có thể tạo pipeline riêng. Tổng concurrency có thể tăng theo số request đồng thời.

Ví dụ:

```text
8 request HTTP đang chạy
Mỗi request flatMap concurrency = 8

Tổng inner operations có thể gần 64
```

Nếu mỗi instance có 64 operations và chạy 5 instance, cluster có thể nhận khoảng 320 operations từ luồng này. Đây là phép tính ước lượng, chưa tính retries, pagination và các luồng khác.

### Dùng bulkhead/semaphore khi cần giới hạn chia sẻ

Nếu cần giới hạn tổng số thao tác trên một dependency giữa nhiều request trong cùng instance, có thể dùng `flatMap` qua một semaphore reactive hoặc một cơ chế bulkhead như Resilience4j Reactor. Ví dụ khái niệm với semaphore:

```java
Mono<Result> guardedCall(Input input) {
    return Mono.usingWhen(
        acquirePermit(),
        permit -> callElasticsearch(input),
        Permit::release
    );
}
```

`acquirePermit()` và `Permit` là abstraction ứng dụng cần triển khai sao cho acquisition không block event loop và release luôn được gọi khi complete, error hoặc cancel. Không dùng `java.util.concurrent.Semaphore.acquire()` theo kiểu blocking trực tiếp trong event-loop thread.

Nếu có nhiều instance, semaphore trong JVM chỉ giới hạn từng instance. Muốn quota toàn cluster, cần giới hạn ở gateway, queue consumer group, distributed rate limiter hoặc tầng vận hành phù hợp.

## 15. Giới hạn concurrency cho ghi dữ liệu

Khi ghi nhiều document, không nên mở một request cho mọi phần tử cùng lúc:

```java
Flux<ProductDocument> saved = Flux.fromIterable(products)
    .flatMap(repository::save, 8);
```

Concurrency 8 là điểm bắt đầu để đo. Có thể tăng hoặc giảm dựa trên:

- Số connection mà reactive client có thể sử dụng.
- Latency mỗi request.
- Kích thước document.
- Số shard và replica.
- CPU, heap và indexing pressure của data node.
- Tỷ lệ retry hoặc lỗi 429.

Với ingestion throughput cao, bulk indexing thường hiệu quả hơn một request index riêng cho từng document. Tuy nhiên, bulk batch cũng cần giới hạn kích thước và số bulk request đồng thời.

## 16. Gom dữ liệu thành batch có giới hạn

Reactor có thể gom phần tử thành batch bằng `buffer(n)` hoặc `bufferTimeout(n, duration)`:

```java
Flux<List<ProductDocument>> batches = source
    .bufferTimeout(500, Duration.ofSeconds(2));
```

Batch phát ra khi đủ 500 phần tử hoặc hết 2 giây. Điều này tránh giữ một batch vô thời hạn khi tốc độ nguồn thấp.

Gửi batch với concurrency giới hạn:

```java
return source
    .bufferTimeout(500, Duration.ofSeconds(2))
    .flatMap(batch -> bulkIndex(batch), 2);
```

Ở đây mỗi bulk batch tối đa 500 item và tối đa 2 bulk operation được xử lý đồng thời từ pipeline này. Nếu mỗi document lớn, 500 item vẫn có thể là payload quá lớn; hãy đo theo byte, không chỉ theo số document.

### `buffer` cũng tiêu thụ bộ nhớ

`buffer(500)` giữ tối đa 500 item cho mỗi batch trước khi phát. Khi kết hợp concurrency 2, có thể có nhiều batch đang được xử lý đồng thời cùng với batch đang được lấp đầy. Ước lượng heap cần tính cả những vùng dữ liệu này.

Không dùng `buffer()` không tham số trên nguồn không giới hạn nếu mục tiêu là kiểm soát bộ nhớ; nó có thể đợi toàn bộ nguồn kết thúc rồi mới phát một danh sách.

## 17. Ước lượng bộ nhớ cho pipeline

Không thể tính chính xác heap chỉ từ số item vì kích thước document khác nhau và object Java có overhead. Tuy nhiên, có thể dùng ước lượng thô để chọn giới hạn ban đầu:

```text
Memory in-flight ≈
  active operations × average response/batch size
  + operator queues
  + prefetch buffers
  + application transformation objects
  + client/network buffers
```

Ví dụ một pipeline có 8 thao tác đồng thời, mỗi thao tác giữ một batch khoảng 4 MB, đã có khoảng 32 MB dữ liệu batch đang hoạt động, chưa tính queue, source object, JSON decoding, client buffer và heap overhead.

Nếu mỗi thao tác có thêm queue 16 item, mỗi item trung bình 100 KB, phần queue có thể tăng thêm khoảng:

\[
8 \times 16 \times 100\text{ KB} \approx 12.8\text{ MB}
\]

Đây chỉ là mô hình ước lượng. Thực tế phụ thuộc operator, prefetch, cách client decode response, object graph và garbage collection.

### Đếm item chưa đủ

Queue tối đa 1.000 item có thể an toàn với event 200 byte nhưng nguy hiểm với document 2 MB. Với payload lớn, giới hạn page size, batch theo byte và source filtering quan trọng hơn chỉ đặt queue capacity theo số phần tử.

## 18. Giảm payload bằng source filtering

Nếu chỉ cần một số field, không nên lấy toàn bộ `_source`:

```json
{
  "_source": ["id", "name", "category"],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Giảm field trả về giúp giảm network payload, JSON decoding và số object được tạo trong heap. Với Spring Data, dùng query source filtering hoặc projection phù hợp với API version.

Không lấy các trường blob, mô tả dài hoặc nested payload nếu bước downstream không cần chúng. Nếu cần chi tiết, có thể truy xuất bổ sung theo ID ở một bước riêng với concurrency giới hạn.

## 19. Tránh `collectList()` trên luồng không giới hạn

`collectList()` có thể phù hợp với kết quả nhỏ có giới hạn rõ ràng:

```java
return repository.findByCategory("accessories")
    .take(100)
    .collectList();
```

Nhưng không phù hợp với full index scan hoặc nguồn không giới hạn:

```java
return repository.findAll().collectList();
```

Thay vào đó, xử lý từng phần tử hoặc từng batch:

```java
return repository.findByCategory("accessories")
    .flatMap(this::processOne, 8)
    .then();
```

Hoặc gom batch có kích thước cố định:

```java
return repository.findByCategory("accessories")
    .buffer(500)
    .concatMap(this::processBatch)
    .then();
```

Nếu API cần trả danh sách cho client, đặt page size nhỏ và trả `Page`/cursor thay vì tích lũy toàn bộ tập dữ liệu trong một response.

## 20. Scheduler và blocking calls

Reactive Elasticsearch client nên được dùng theo API reactive, không gọi `.block()` bên trong event-loop pipeline.

Tránh:

```java
return repository.findById(id)
    .map(product -> {
        ProductDocument saved = repository.save(product).block();
        return saved;
    });
```

Đây là blocking trong callback và có thể làm nghẽn event-loop. Thay bằng composition:

```java
return repository.findById(id)
    .flatMap(product -> {
        product.setName("Updated name");
        return repository.save(product);
    });
```

Nếu buộc phải gọi một API blocking cũ, cô lập nó trên `Schedulers.boundedElastic()`:

```java
Mono<Result> result = Mono.fromCallable(() -> legacyBlockingCall())
    .subscribeOn(Schedulers.boundedElastic());
```

Không chuyển reactive Elasticsearch I/O sang `boundedElastic` một cách mặc định; reactive client vốn được thiết kế cho I/O bất đồng bộ. `boundedElastic` dành cho các đoạn blocking không thể tránh.

## 21. Cancellation và giải phóng tài nguyên

Reactive Streams cho phép downstream cancel subscription. Ví dụ người dùng đóng HTTP connection hoặc một job bị dừng, cancellation có thể truyền ngược qua pipeline.

Ứng dụng cần bảo đảm cleanup cho tài nguyên được mở trong quá trình xử lý:

- PIT context.
- Scroll context nếu API đang dùng scroll.
- Semaphore permit.
- File hoặc stream output.
- Temporary resource và batch staging.

Với tài nguyên bất đồng bộ, `usingWhen` giúp gắn cleanup vào các đường complete, error và cancel:

```java
Flux<SearchHit<ProductDocument>> scan = Flux.usingWhen(
    openPit(),
    pit -> fetchPages(pit),
    pit -> closePit(pit),
    (pit, error) -> closePit(pit),
    pit -> closePit(pit)
);
```

`openPit`, `fetchPages` và `closePit` là các hàm do ứng dụng triển khai theo Elasticsearch client đang dùng. Ví dụ minh họa vòng đời resource; cần bảo đảm `closePit` trả `Publisher` và được gọi an toàn, kể cả khi request đang chạy bị cancel.

Cancellation của client không phải lúc nào cũng có nghĩa Elasticsearch đã dừng ngay một thao tác server đã nhận. Hãy coi cancellation là yêu cầu hủy pipeline/client request và vẫn quản lý resource/task theo API cụ thể.

## 22. Retry và backpressure

Retry có thể làm tăng concurrency và tải nếu không được giới hạn. Khi Elasticsearch trả lỗi tạm thời như 429 hoặc một số 5xx, có thể retry với backoff:

```java
return repository.save(product)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(3))
        .jitter(0.5)
    );
```

Ví dụ trên minh họa số lần retry và backoff; trong thực tế cần phân loại lỗi trước khi retry. Không retry lỗi mapping, validation hoặc 400. Version conflict 409 cần đọc lại và tính lại dữ liệu theo nghiệp vụ; không chỉ gửi lại cùng payload.

Khi nhiều request đồng thời cùng retry, số request có thể tăng đột biến. Backoff có jitter, giới hạn concurrency và circuit breaker/bulkhead giúp tránh retry storm.

### Idempotency khi retry ghi

Retry một thao tác ghi phải an toàn khi request trước đã thành công nhưng response bị mất. Dùng ID document ổn định, upsert semantics phù hợp hoặc idempotency key ở tầng ứng dụng. Không tự động retry các thao tác tạo ID ngẫu nhiên nếu có thể tạo duplicate.

## 23. Xử lý lỗi từng phần trong bulk pipeline

Bulk request có thể thành công một phần. Reactive pipeline không nên coi HTTP response thành công là mọi document đều đã được index.

Một thiết kế có thể:

1. Gom batch có kích thước giới hạn.
2. Gửi bulk request.
3. Kiểm tra `errors` và từng item response.
4. Phân loại lỗi retryable và permanent.
5. Retry có giới hạn chỉ các item phù hợp.
6. Ghi permanent failures vào dead-letter store hoặc trả lỗi job.

Nếu dùng `flatMap` để xử lý nhiều bulk batch, giới hạn số batch đồng thời. Không để một nguồn vô hạn tạo hàng nghìn batch đang chờ bulk request.

## 24. Backpressure trong WebFlux endpoint

Controller reactive nên trả `Flux`/`Mono` để framework điều phối subscription thay vì tự subscribe trong controller.

Ví dụ:

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<ProductView> streamProducts() {
        return service.streamProducts()
            .map(ProductView::from);
    }
}
```

WebFlux có thể ghi response theo stream và điều tiết demand dựa trên khả năng gửi dữ liệu tới client. Nhưng nếu service đã `collectList()` toàn bộ kết quả trước khi trả, lợi ích streaming đã mất. Cần giữ pipeline streaming từ Elasticsearch đến response và giới hạn page/buffer ở các bước trung gian.

### Không gọi `subscribe()` trong service để tạo side effect ngoài luồng

Ví dụ không nên:

```java
public void reindex() {
    repository.findAll()
        .flatMap(this::saveToTarget, 8)
        .subscribe();
}
```

Method trả về ngay, lỗi có thể không được caller quan sát, lifecycle và cancellation khó kiểm soát. Thay vào đó, trả `Mono<Void>`:

```java
public Mono<Void> reindex() {
    return repository.findAll()
        .flatMap(this::saveToTarget, 8)
        .then();
}
```

Caller ở biên ứng dụng quyết định subscribe. Với WebFlux, framework subscribe cho request; với scheduler/job runner, runner quản lý subscription và trạng thái job.

## 25. Quan sát demand, concurrency và queue

Muốn điều chỉnh backpressure, cần đo các điểm chính:

- Số request Elasticsearch đang in-flight.
- Số inner publisher đang hoạt động.
- Thời gian hoàn tất một request search/index/bulk.
- Page size và kích thước response trung bình.
- Batch size theo item và theo byte.
- Số item trong buffer/queue.
- Số lần buffer overflow/drop.
- Số lần retry và retry delay.
- Tỷ lệ 429, 5xx và timeout.
- Heap usage, allocation rate và GC pause.
- Connection pool usage và pending acquire.
- Elasticsearch search/indexing thread pool, indexing pressure và node CPU.

Reactor có hook `doOnRequest` để quan sát demand trong quá trình chẩn đoán:

```java
Flux<ProductDocument> pipeline = repository.findAll()
    .doOnRequest(n -> metrics.recordRequested(n))
    .flatMap(this::processOne, 8, 16);
```

`doOnRequest` có thể được gọi nhiều lần với giá trị demand khác nhau. Không nên log từng lần ở mức INFO trong production với throughput cao; hãy dùng metric/counter hoặc log sampling.

## 26. Chọn page size, concurrency và prefetch theo từng workload

Một cách tiếp cận thực tế là điều chỉnh từng biến độc lập:

| Workload | Page/batch size ban đầu | Concurrency ban đầu | Lưu ý |
|---|---:|---:|---|
| Search API tương tác | 20–100 hits | 1–4 downstream calls | Ưu tiên latency và payload nhỏ |
| Export dữ liệu | 500 hits/page | 2–4 page processors | Dùng PIT + search_after hoặc cơ chế scan phù hợp; không giữ nhiều page |
| Bulk ingestion | 200–1.000 docs/batch | 1–4 bulk requests | Điều chỉnh theo byte và bulk latency |
| Enrichment qua service ngoài | Batch nhỏ | 4–8 calls | Tôn trọng rate limit của dependency |
| Xử lý CPU nặng | Batch theo heap budget | Số worker theo CPU | Tách CPU work khỏi I/O reactive khi cần |

Đây là điểm khởi đầu để benchmark, không phải giá trị production mặc định. Kích thước document, cluster và SLA có thể làm lựa chọn tối ưu khác đi đáng kể.

## 27. Một pipeline reactive có giới hạn đầu-cuối

Ví dụ kết hợp page size, xử lý đồng thời có giới hạn và batch output:

```java
public Mono<Void> exportProducts(Query query) {
    return operations.search(query, ProductDocument.class)
        .map(SearchHit::getContent)
        .limitRate(64)
        .flatMap(this::transformProduct, 8, 8)
        .buffer(200)
        .concatMap(this::writeExportBatch)
        .then();
}
```

Ý nghĩa:

- Search query cần có page size phù hợp; `limitRate` chỉ điều tiết demand trên publisher.
- `flatMap(..., 8, 8)` giới hạn số transform publisher và prefetch của mỗi inner.
- `buffer(200)` gom tối đa 200 kết quả transform thành batch.
- `concatMap` ghi từng batch theo thứ tự và chỉ một batch tại một thời điểm.
- `then()` chuyển pipeline thành `Mono<Void>` biểu thị hoàn tất.

Nếu `writeExportBatch` chậm, demand sẽ giảm ngược qua các operator. Các buffer vẫn có sức chứa hữu hạn theo cấu hình. Với dữ liệu lớn hơn một page, cần bổ sung pagination loop/cursor để lấy trang tiếp theo tuần tự; đoạn code không tự động biến một search page thành full index scan.

## 28. Những lỗi thường gặp

### Nghĩ `Flux` tự động bảo vệ heap

`collectList`, unbounded buffer, page lớn hoặc quá nhiều inner publisher vẫn có thể giữ dữ liệu không giới hạn. Hãy giới hạn từng queue và page.

### Dùng `flatMap` không giới hạn cho request Elasticsearch

Số request in-flight có thể tăng theo tốc độ nguồn. Chọn concurrency rõ ràng và tính tổng theo số request/instance.

### Nhầm `limitRate` với concurrency limit

`limitRate` điều tiết demand; `flatMap` concurrency giới hạn số inner publisher. Cần chọn đúng operator theo mục tiêu.

### Dùng `onBackpressureBuffer()` không giới hạn

Queue có thể tăng mãi khi consumer chậm. Dùng capacity hữu hạn và chính sách overflow rõ ràng.

### Drop dữ liệu nghiệp vụ khi buffer đầy

`DROP_OLDEST`, `DROP_LATEST` và `onBackpressureDrop` làm mất phần tử. Chỉ dùng cho dữ liệu có thể mất; event nghiệp vụ cần queue bền vững hoặc fail/retry.

### Dùng page size lớn để giảm số request

Response lớn làm tăng heap và thời gian deserialize. Đo theo byte và source filtering.

### Dùng `flatMapSequential` mà không tính buffer

Publisher hoàn tất sớm có thể phải chờ kết quả trước, làm tăng dữ liệu đang giữ. Chỉ giữ thứ tự nếu nghiệp vụ cần.

### Gọi `.block()` hoặc `.subscribe()` trong service

Blocking có thể làm nghẽn event loop; subscribe nội bộ làm mất quyền kiểm soát lifecycle/error của caller. Compose publisher và trả về cho caller.

### Retry vô hạn khi Elasticsearch trả 429

Retry không giới hạn tạo retry storm. Dùng backoff, jitter, max attempts và concurrency cap.

### Tải page tiếp theo trước khi xử lý xong page hiện tại

Nhiều page có thể cùng nằm trong heap. Giữ page processing tuần tự hoặc dùng queue có giới hạn.

## 29. Quy trình thiết kế pipeline reactive an toàn

Khi xây dựng search/export/ingestion reactive, hãy thực hiện:

1. Xác định throughput, latency và search visibility cần đạt.
2. Ước lượng kích thước document/response trung bình và trường hợp lớn nhất.
3. Chọn page size hoặc bulk batch size có giới hạn.
4. Chọn concurrency cho `flatMap` dựa trên năng lực dependency.
5. Chọn prefetch và `limitRate` nếu cần điều tiết demand.
6. Tránh `collectList()` và unbounded buffer trên nguồn lớn/không giới hạn.
7. Chọn overflow policy; chỉ drop khi dữ liệu có thể mất.
8. Giới hạn tổng concurrency theo số request và số instance.
9. Dùng pagination cursor để scan nhiều page, không tải trước quá nhiều trang.
10. Cô lập blocking calls khỏi event loop và không block reactive Elasticsearch client.
11. Thiết kế cancellation/cleanup cho PIT, scroll, permit và tài nguyên khác.
12. Retry lỗi tạm thời với backoff/jitter và idempotency.
13. Theo dõi in-flight requests, queue, heap, GC, 429, latency và Elasticsearch node metrics.
14. Benchmark tăng/giảm từng giới hạn trước khi triển khai production.

## 30. Kết luận

Backpressure cho phép downstream điều tiết demand tới upstream, nhưng không tự giới hạn kích thước response Elasticsearch, số request được mở bởi mọi pipeline hay tổng lượng dữ liệu nằm trong heap. Trong Reactor, `flatMap` với concurrency rõ ràng giới hạn số inner publisher; `concatMap` tuần tự hóa; `flatMapSequential` giữ thứ tự nhưng có thể phải buffer; `limitRate` chia demand thành nhóm; các operator `onBackpressure...` quyết định hành vi khi downstream không theo kịp.

Để kiểm soát bộ nhớ, cần giới hạn page size, batch size, prefetch, queue capacity và số page in-flight. Tránh `collectList()` trên nguồn lớn, tránh buffer không giới hạn và chỉ dùng drop cho dữ liệu có thể mất. Với Spring Data Elasticsearch Reactive, giữ pipeline ở dạng `Flux`/`Mono`, không gọi `.block()` hoặc tự `subscribe()` trong service, giới hạn concurrency theo tổng tải toàn ứng dụng, xử lý pagination tuần tự và cleanup tài nguyên khi cancel. Cuối cùng, dùng metrics và benchmark để cân bằng throughput, latency, heap và tải Elasticsearch.

## Tài liệu tham khảo

- [Project Reactor – Reference Guide: Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/request.html)
- [Project Reactor – `Flux` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor – `Mono` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactive Streams – Specification](https://www.reactive-streams.org/)
- [Spring Data Elasticsearch – Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch – Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive.html)
- [Elasticsearch – Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch – Point in Time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
