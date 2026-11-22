# Scroll API và trường hợp quét dữ liệu theo lô

Scroll API của Elasticsearch cho phép đọc một tập kết quả lớn theo từng trang mà không phải gửi lại truy vấn từ đầu cho mỗi trang. Sau lần tìm kiếm đầu tiên, Elasticsearch tạo một scroll context và trả về `scroll_id`. Ứng dụng dùng ID này để lấy các batch tiếp theo cho đến khi không còn hit, rồi giải phóng context.

Scroll phù hợp với các công việc quét dữ liệu như export hàng triệu document, backfill index, đồng bộ dữ liệu, chạy báo cáo ngoại tuyến hoặc xử lý hàng loạt. Nó không phải lựa chọn tốt cho phân trang tương tác sâu trên giao diện; với trường hợp đó, nên cân nhắc `search_after` kết hợp Point in Time (PIT). Khi dùng scroll, cần kiểm soát batch size, thời gian giữ context, bộ nhớ ứng dụng, lỗi từng batch và việc đóng scroll đúng cách.

## 1. Vì sao cần Scroll API?

Elasticsearch giới hạn số document có thể lấy bằng `from` và `size` trong một search request. Cách phân trang thông thường phù hợp với vài trang đầu:

```http
GET /events/_search
{
  "from": 0,
  "size": 20,
  "query": { "match_all": {} }
}
```

Để lấy trang tiếp theo, ứng dụng tăng `from`. Nhưng `from` càng lớn, Elasticsearch càng phải giữ và bỏ qua nhiều kết quả trước vị trí cần lấy. Cơ chế này tốn tài nguyên khi truy vấn sâu và bị giới hạn bởi `index.max_result_window` (mặc định thường là 10.000 cho `from + size`).

Nếu cần xử lý hàng trăm nghìn hoặc hàng triệu document, việc tăng `from` liên tục không phù hợp. Scroll giải quyết bài toán quét bằng cách giữ một search context và tiếp tục đọc từ vị trí đã lưu trong context đó.

### Những trường hợp phù hợp

- Export dữ liệu lớn ra file CSV/JSON hoặc hệ thống lưu trữ khác.
- Backfill dữ liệu từ index cũ sang index mới.
- Đồng bộ định kỳ một tập document sang hệ thống bên ngoài.
- Tính toán ngoại tuyến cần đọc toàn bộ document phù hợp điều kiện.
- Chạy tác vụ bảo trì theo batch, chẳng hạn kiểm tra và cập nhật document.
- Đọc dữ liệu để nạp vào pipeline xử lý theo lô.

### Những trường hợp không phù hợp

- Phân trang người dùng qua các trang 1, 2, 3, 4 trong giao diện.
- Autocomplete hoặc request tìm kiếm có độ trễ thấp.
- Request HTTP ngắn cần trả kết quả ngay cho người dùng.
- Công việc chỉ cần vài chục hoặc vài trăm kết quả đầu tiên.
- Tác vụ cần resume ổn định sau nhiều giờ hoặc nhiều ngày mà không có checkpoint riêng.

## 2. Scroll context hoạt động như thế nào?

Khi ứng dụng gửi search request có tham số `scroll`, Elasticsearch mở một scroll context cho lần tìm kiếm. Context giữ trạng thái đọc trên một snapshot của dữ liệu tìm kiếm tại thời điểm bắt đầu. Response đầu tiên chứa batch đầu tiên và một `scroll_id`.

Các request tiếp theo không gửi lại query ban đầu. Chúng gửi `scroll_id` để yêu cầu batch kế tiếp. Elasticsearch tiếp tục từ vị trí đã lưu trong context và trả về ID dùng cho lần gọi tiếp theo.

```text
Ứng dụng
   |
   | 1. POST /events/_search?scroll=1m
   |    size = 500
   v
Elasticsearch
   |
   | 2. Batch 1 + scroll_id
   v
Ứng dụng xử lý batch 1
   |
   | 3. POST /_search/scroll
   |    scroll_id mới nhất
   v
Elasticsearch
   |
   | 4. Batch 2 + scroll_id mới
   v
Ứng dụng xử lý batch 2
   |
   |             ...
   v
Không còn hit
   |
   | 5. DELETE /_search/scroll
   v
Giải phóng scroll context
```

Scroll context giữ một góc nhìn nhất quán của index theo search view lúc bắt đầu. Document được index sau thời điểm đó không tự xuất hiện trong lượt scroll đang chạy. Những thay đổi sau đó cũng không làm snapshot của scroll chuyển sang trạng thái mới giữa chừng.

Scroll ID là chuỗi opaque do Elasticsearch cấp. Không phân tích cấu trúc, không tự tạo và không dùng lại ID cũ nếu response mới đã trả một ID khác. Luôn dùng `scroll_id` mới nhất nhận được từ response gần nhất.

## 3. `keep_alive` có ý nghĩa gì?

Tham số `scroll`/`keep_alive` xác định thời gian Elasticsearch giữ scroll context khi ứng dụng chưa gửi request scroll tiếp theo.

Ví dụ:

```http
POST /events/_search?scroll=2m
```

`2m` có nghĩa context được giữ tối đa khoảng hai phút kể từ lần truy cập gần nhất nếu không có request tiếp theo. Mỗi lần gọi Scroll API có thể gia hạn thời gian giữ context bằng giá trị `scroll` mới.

Điều này không có nghĩa toàn bộ công việc chỉ được chạy trong hai phút. Một tác vụ có thể kéo dài hàng giờ nếu liên tục lấy batch tiếp theo trước khi context hết hạn và gia hạn keep_alive. Tuy nhiên, không nên đặt keep_alive quá dài để che giấu một consumer bị treo; context tồn tại lâu sẽ giữ tài nguyên trên cluster.

### Chọn keep_alive

- Đặt đủ dài để ứng dụng xử lý một batch và gửi request kế tiếp.
- Nếu mỗi batch xử lý mất 20 giây, keep_alive vài chục giây có thể quá sát; nên có khoảng đệm cho GC, mạng và tải cluster.
- Không đặt nhiều giờ nếu batch thường được xử lý trong vài giây.
- Nếu consumer có thể tạm dừng hoặc bị nghẽn lâu, cần thiết kế checkpoint/restart thay vì phụ thuộc vào scroll context sống mãi.

## 4. Gọi Scroll API bằng REST

### Bước 1: Bắt đầu scroll

Request đầu tiên chỉ định index, thời gian giữ context và kích thước batch:

```http
POST /events/_search?scroll=1m
Content-Type: application/json

{
  "size": 500,
  "sort": ["_doc"],
  "track_total_hits": false,
  "query": {
    "range": {
      "@timestamp": {
        "gte": "2026-01-01T00:00:00Z",
        "lt": "2026-02-01T00:00:00Z"
      }
    }
  }
}
```

Trong ví dụ:

- `size: 500` yêu cầu tối đa 500 document mỗi batch.
- `sort: ["_doc"]` dùng thứ tự nội bộ hiệu quả khi chỉ cần quét dữ liệu, không cần thứ tự nghiệp vụ.
- `track_total_hits: false` tránh tính tổng số hit chính xác nếu tác vụ không cần con số đó.
- `range` giới hạn tập document cần quét theo khoảng thời gian.

Response rút gọn:

```json
{
  "_scroll_id": "DXF1ZXJ5...opaque-scroll-id...",
  "timed_out": false,
  "_shards": {
    "total": 5,
    "successful": 5,
    "failed": 0
  },
  "hits": {
    "hits": [
      { "_id": "e-1", "_source": { "eventType": "login" } },
      { "_id": "e-2", "_source": { "eventType": "purchase" } }
    ]
  }
}
```

Response thật có thể chứa nhiều hit hơn ví dụ. Lưu lại `_scroll_id` và xử lý các hit trong batch hiện tại.

### Bước 2: Lấy batch tiếp theo

Gửi ID mới nhất tới endpoint `_search/scroll`:

```http
POST /_search/scroll
Content-Type: application/json

{
  "scroll": "1m",
  "scroll_id": "DXF1ZXJ5...opaque-scroll-id..."
}
```

Response trả về batch tiếp theo và có thể có `_scroll_id` mới. Hãy thay ID đang giữ bằng ID mới này.

### Bước 3: Lặp đến khi hết dữ liệu

Khi `hits.hits` rỗng, không còn batch tiếp theo trong lượt scroll đó. Không nên dựa vào số hit của batch trước để kết luận đã hết; điều kiện kết thúc là response scroll hiện tại không còn hit.

### Bước 4: Đóng scroll context

Khi hoàn tất hoặc khi tác vụ bị lỗi, giải phóng context:

```http
DELETE /_search/scroll
Content-Type: application/json

{
  "scroll_id": [
    "DXF1ZXJ5...latest-scroll-id..."
  ]
}
```

Có thể xóa nhiều scroll ID trong cùng request. Nếu dùng một ID, API cũng hỗ trợ dạng chuỗi theo cú pháp được server chấp nhận. Trong tác vụ có nhiều context, lưu và xóa đúng các ID mà ứng dụng đã mở.

## 5. Pseudocode cho vòng lặp scroll

Quy trình cơ bản:

```text
scrollId = null

try:
    page = startScroll(query, batchSize, keepAlive)
    scrollId = page.scrollId

    while page.hits is not empty:
        process(page.hits)

        page = continueScroll(scrollId, keepAlive)
        scrollId = page.scrollId
finally:
    if scrollId is not null:
        clearScroll(scrollId)
```

Điểm quan trọng là `clearScroll` phải được gọi trong `finally`. Nếu chỉ đóng khi vòng lặp kết thúc bình thường, exception trong lúc xử lý một batch có thể làm context tồn tại đến khi hết keep_alive.

## 6. Dùng Scroll API qua Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp API cấp cao để duyệt search result theo stream. `ElasticsearchOperations.searchForStream(...)` trả về `SearchHitsIterator<T>`, giúp ứng dụng đọc từng hit mà không phải tự quản lý `scroll_id` ở mỗi vòng lặp.

Ví dụ:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.stereotype.Service;

@Service
public class EventExportService {

    private final ElasticsearchOperations operations;

    public EventExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportEvents() {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.range(r -> r
                .field("@timestamp")
                .gte(co.elastic.clients.json.JsonData.of("2026-01-01T00:00:00Z"))
                .lt(co.elastic.clients.json.JsonData.of("2026-02-01T00:00:00Z"))
            ))
            .withPageable(PageRequest.of(0, 500))
            .build();

        try (SearchHitsIterator<EventDocument> hits =
                operations.searchForStream(
                    query,
                    EventDocument.class,
                    IndexCoordinates.of("events"))) {

            while (hits.hasNext()) {
                SearchHit<EventDocument> hit = hits.next();
                EventDocument event = hit.getContent();
                writeToExport(event);
            }
        }
    }

    private void writeToExport(EventDocument event) {
        // Ghi event ra file hoặc hệ thống đích.
    }
}
```

`searchForStream` là lựa chọn tiện dụng cho việc duyệt lượng lớn kết quả. Iterator phải được đóng; try-with-resources bảo đảm `close()` được gọi cả khi vòng lặp ném exception. Cách triển khai bên dưới sử dụng cơ chế scroll của Spring Data ở các phiên bản hỗ trợ API này.

`PageRequest.of(0, 500)` đặt kích thước trang/batch ban đầu. Kích thước phù hợp phụ thuộc kích thước `_source`, tốc độ xử lý và năng lực cluster. Cấu hình thời gian scroll và chữ ký API có thể khác theo phiên bản Spring Data Elasticsearch; hãy đối chiếu Javadoc của dependency đang dùng.

### Vì sao phải giữ `SearchHit<T>`?

`SearchHitsIterator<T>` duyệt các `SearchHit<T>`, không chỉ entity thuần. Điều đó cho phép đọc `_id`, score, index và metadata của hit nếu cần. Nếu chỉ cần document, lấy `hit.getContent()`; nếu cần ID hoặc metadata, giữ `SearchHit` trong bước xử lý.

## 7. Quản lý scroll thủ công qua `ElasticsearchOperations`

Khi cần kiểm soát từng batch hoặc cần làm việc trực tiếp với scroll ID, một số phiên bản Spring Data Elasticsearch cung cấp các thao tác:

- `searchScrollStart(...)`: bắt đầu scroll và nhận batch đầu tiên.
- `searchScrollContinue(...)`: dùng scroll ID để lấy batch kế tiếp.
- `searchScrollClear(...)`: giải phóng scroll context.

Ví dụ theo API Spring Data có các phương thức scroll này:

```java
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchScrollHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public void scanInBatches(
        ElasticsearchOperations operations,
        Query query) {

    long keepAliveMillis = 60_000L;
    IndexCoordinates index = IndexCoordinates.of("events");
    query.setPageable(PageRequest.of(0, 500));

    String scrollId = null;
    try {
        SearchScrollHits<EventDocument> page =
            operations.searchScrollStart(
                keepAliveMillis,
                query,
                EventDocument.class,
                index
            );

        scrollId = page.getScrollId();

        while (!page.getSearchHits().isEmpty()) {
            for (SearchHit<EventDocument> hit : page.getSearchHits()) {
                process(hit.getContent());
            }

            page = operations.searchScrollContinue(
                scrollId,
                keepAliveMillis,
                EventDocument.class,
                index
            );

            scrollId = page.getScrollId();
        }
    } finally {
        if (scrollId != null) {
            operations.searchScrollClear(scrollId);
        }
    }
}
```

Đây là mẫu cho các phiên bản có `SearchScrollHits` và các phương thức `searchScrollStart`, `searchScrollContinue`, `searchScrollClear`. Chữ ký overload có thể thay đổi giữa các phiên bản Spring Data; nếu dự án không có các phương thức này, dùng `searchForStream` hoặc Elasticsearch Java API Client tương ứng. Trong triển khai thực tế, nếu một response tiếp tục trả scroll ID mới, luôn cập nhật biến `scrollId` trước khi gọi tiếp hoặc dọn dẹp.

## 8. Chọn batch size

Batch size là số document Elasticsearch cố gắng trả về trong mỗi trang scroll. Nó không phải số lượng document của toàn bộ tác vụ.

| Batch size | Ưu điểm | Hạn chế |
|---:|---|---|
| Nhỏ, ví dụ 100 | Payload nhỏ, dễ kiểm soát bộ nhớ ứng dụng | Nhiều round trip, overhead mạng cao hơn |
| Trung bình, ví dụ 500–1.000 | Cân bằng giữa payload và số request trong nhiều workload | Vẫn cần đo theo kích thước document |
| Lớn, ví dụ 5.000+ | Ít request hơn khi document nhỏ và cluster khỏe | Response lớn, tăng heap, GC và áp lực mạng |

Không có batch size tối ưu chung cho mọi index. Một batch 1.000 document có thể nhỏ nếu mỗi document vài trăm byte, nhưng rất lớn nếu `_source` chứa blob văn bản dài hoặc nhiều nested object.

### Cách chọn thực tế

1. Bắt đầu với batch vừa phải, ví dụ 500 hoặc 1.000 document.
2. Đo kích thước response, thời gian lấy batch và thời gian xử lý batch.
3. Theo dõi heap, GC, network throughput và search thread pool.
4. Tăng batch nếu round trip là nút thắt và bộ nhớ còn dư.
5. Giảm batch nếu response lớn, ứng dụng bị GC nhiều hoặc consumer không theo kịp.

### Batch size không đồng nghĩa với batch write

Scroll kiểm soát lượng dữ liệu đọc từ Elasticsearch. Nếu ứng dụng ghi dữ liệu sang một index khác bằng Bulk API, batch write có thể có kích thước khác batch read. Không nhất thiết đọc 1.000 document thì phải ghi đúng 1.000 document trong một bulk request.

## 9. Chọn keep_alive và tránh context hết hạn

Keep_alive phải đủ để xử lý batch hiện tại và gửi request tiếp theo. Nếu một batch cần nhiều phút vì phải gọi dịch vụ bên ngoài, scroll context có thể hết hạn trước khi ứng dụng tiếp tục.

Các lựa chọn khi xử lý chậm:

- Giảm số việc thực hiện đồng bộ trong vòng xử lý mỗi hit.
- Đưa dữ liệu vào queue nội bộ nhanh rồi xử lý downstream theo worker riêng, nếu kiến trúc cho phép.
- Tăng keep_alive có kiểm soát và theo dõi số context đang mở.
- Giảm batch size để tránh xử lý một batch quá lâu.
- Dùng checkpoint bền vững và khởi động lại scan khi context hết hạn.

Không nên tăng keep_alive vô hạn để giữ một scroll context trong lúc consumer có thể dừng hàng giờ. Scroll ID không phải checkpoint bền vững cho một job dài ngày.

## 10. Dùng `_doc` sort khi quét dữ liệu

Nếu mục tiêu là đọc toàn bộ document mà không cần thứ tự nghiệp vụ, sort theo `_doc` thường là lựa chọn hiệu quả cho Scroll API:

```json
{
  "size": 500,
  "sort": ["_doc"],
  "query": {
    "match_all": {}
  }
}
```

`_doc` cho phép Elasticsearch trả document theo thứ tự nội bộ thuận tiện cho việc quét. Không nên dùng thứ tự này để hiển thị kết quả cho người dùng vì nó không có ý nghĩa nghiệp vụ ổn định.

Nếu cần thứ tự cụ thể, hãy khai báo sort theo field phù hợp. Với nhiều shard, cần cân nhắc giá trị tie-breaker và semantics của sort để tránh thứ tự không xác định giữa các document có cùng giá trị. Scroll vẫn tiếp tục từ context đã tạo, nhưng sort theo field có thể tốn tài nguyên hơn `_doc`.

## 11. Giảm payload bằng source filtering

Khi export hoặc xử lý batch, không phải lúc nào ứng dụng cũng cần toàn bộ `_source`. Có thể chỉ lấy các field cần thiết:

```http
POST /events/_search?scroll=1m
{
  "size": 500,
  "sort": ["_doc"],
  "_source": ["@timestamp", "eventType", "userId"],
  "query": {
    "match_all": {}
  }
}
```

Source filtering giúp giảm payload truyền qua mạng và lượng dữ liệu phải deserialize. Tuy nhiên, entity class được Spring Data ánh xạ có thể thiếu một số field nếu query chỉ lấy một phần source. Với projection hoặc DTO chỉ đọc, hãy dùng kiểu đích phản ánh đúng tập field được lấy.

Có thể loại bỏ `_source` hoàn toàn nếu chỉ cần doc values hoặc metadata trong một số kiểu query, nhưng khi đó cần thiết kế truy xuất field phù hợp và không kỳ vọng entity đầy đủ được dựng lên.

## 12. Quét theo điều kiện và theo khoảng thời gian

Không nên mặc định scan toàn bộ index nếu chỉ cần một tập con. Thu hẹp query ngay từ đầu giúp giảm số document phải chuyển qua mạng và xử lý.

Ví dụ chỉ quét sự kiện trong tháng:

```json
{
  "size": 500,
  "sort": ["_doc"],
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "@timestamp": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2026-02-01T00:00:00Z"
            }
          }
        },
        {
          "term": {
            "eventType": "purchase"
          }
        }
      ]
    }
  }
}
```

Dùng `filter` cho điều kiện lọc không cần relevance score. Với scan batch, thường không cần tính score; `match_all`, `term`, `range` và bool filter là những lựa chọn phổ biến.

Nếu dữ liệu được chia theo index thời gian, chỉ truy vấn các index phù hợp thay vì wildcard toàn bộ lịch sử. Có thể dùng alias hoặc danh sách index được xác định bởi job.

## 13. Xử lý từng batch an toàn

Một vòng scroll chỉ giải quyết việc đọc dữ liệu. Ứng dụng vẫn phải xử lý batch với chiến lược lỗi phù hợp.

Một quy trình đơn giản:

```text
Lấy batch
   |
   v
Validate từng document
   |
   v
Xử lý / chuyển đổi
   |
   v
Ghi kết quả hoặc gửi queue
   |
   v
Ghi nhận metrics/checkpoint
   |
   v
Lấy batch tiếp theo
```

### Không giữ toàn bộ kết quả trong RAM

Nếu mục tiêu là export hàng triệu document, hãy ghi từng batch ra output hoặc truyền tiếp vào pipeline. Không gom tất cả document vào một `List` lớn rồi mới ghi file, vì cách đó làm bộ nhớ tăng theo tổng số document.

### Xử lý lỗi theo document

Một document không hợp lệ không nhất thiết phải làm dừng cả job. Tùy yêu cầu, có thể:

- Ghi lỗi vào dead-letter file/queue và tiếp tục document tiếp theo.
- Dừng batch nếu lỗi ảnh hưởng tính đúng đắn toàn bộ dữ liệu.
- Retry lỗi tạm thời với backoff.
- Không retry vô hạn lỗi mapping, validation hoặc dữ liệu sai định dạng.

### Xử lý lỗi khi ghi Bulk API

Nếu mỗi batch đọc được ghi sang Elasticsearch khác, Bulk API có thể có một số item thành công và một số item thất bại. Response HTTP thành công không đảm bảo mọi item đều thành công. Hãy kiểm tra lỗi theo từng item và retry có chọn lọc.

## 14. Idempotency và checkpoint cho job quét dữ liệu

Scroll context là trạng thái tạm thời ở Elasticsearch. Nếu process chết, mạng đứt hoặc keep_alive hết hạn, scroll ID có thể không còn dùng được. Vì vậy, không nên coi scroll ID là checkpoint lâu dài.

Để job có thể chạy lại an toàn:

- Dùng ID nguồn ổn định khi ghi vào hệ thống đích.
- Thiết kế thao tác ghi có tính idempotent hoặc có thể upsert.
- Ghi nhận checkpoint nghiệp vụ bền vững nếu cần resume.
- Có thể chia công việc theo khoảng thời gian, tenant hoặc range khóa ổn định.
- Nếu restart từ đầu một partition, bảo đảm xử lý lặp không tạo dữ liệu trùng hoặc làm hỏng trạng thái.

Với job có checkpoint theo timestamp, nên dùng khoảng nửa mở `[from, to)` và lưu watermark đã xử lý. Nhưng timestamp đơn lẻ có thể trùng giữa nhiều document; cần thêm tie-breaker như ID hoặc dùng `search_after` với sort ổn định để checkpoint chính xác.

Scroll phù hợp với một lượt scan có thời gian hữu hạn. Nếu cần dừng và tiếp tục qua nhiều giờ/ngày với vị trí bền vững, PIT + `search_after` hoặc thiết kế partition/checkpoint riêng thường phù hợp hơn.

## 15. Snapshot và dữ liệu thay đổi trong lúc scroll

Scroll giữ search context dựa trên trạng thái index lúc bắt đầu. Điều đó giúp các batch tiếp theo đọc từ cùng một góc nhìn thay vì mỗi request lại nhìn thấy một tập document mới.

Hệ quả:

- Document mới được index sau khi scroll bắt đầu không xuất hiện trong lượt scan đó.
- Các thay đổi sau thời điểm bắt đầu không làm lượt scroll chuyển sang snapshot mới.
- Scroll không phải transaction nghiệp vụ và không khóa các thao tác ghi của hệ thống.
- Một job vừa scan vừa sửa cùng index cần hiểu rõ rằng kết quả đọc vẫn dựa trên snapshot ban đầu.

Nếu yêu cầu xử lý phải bao gồm mọi thay đổi phát sinh trong lúc scan, cần thêm cơ chế bắt delta như change log, outbox, CDC hoặc một lượt incremental scan sau backfill. Không giả định scroll tự động theo kịp dữ liệu mới.

## 16. Giải phóng scroll context

Mỗi scroll context tiêu tốn tài nguyên trên node giữ shard context. Cần giải phóng ngay sau khi hoàn tất.

Các nguyên tắc:

- Luôn dùng `try/finally` hoặc try-with-resources với iterator có hỗ trợ close.
- Dùng scroll ID mới nhất từ response gần nhất.
- Dọn dẹp cả khi xử lý batch ném exception.
- Không tạo nhiều scroll context song song hơn mức cluster chịu được.
- Không giữ scroll context trong lúc người dùng chờ hoặc tương tác.

Có thể kiểm tra số context mở qua Node Stats:

```http
GET /_nodes/stats/indices/search
```

Trong response, theo dõi `indices.search.open_contexts` trên các node. Nếu số context tăng liên tục, có thể ứng dụng không đóng scroll hoặc đang tạo quá nhiều lượt scan đồng thời.

### Scroll context và segment

Scroll context có thể giữ các segment cũ cần thiết cho snapshot, khiến merge không thể loại bỏ ngay các segment đó. Điều này làm tăng dung lượng disk tạm thời và chi phí tài nguyên nếu context tồn tại lâu. Vì vậy, thời gian sống và số context mở cần được kiểm soát.

## 17. Xử lý timeout, lỗi shard và scroll ID hết hạn

Một search response có thể có `timed_out: true` hoặc `_shards.failed` lớn hơn 0. Ứng dụng batch cần quyết định có chấp nhận kết quả một phần hay phải dừng job.

Một số trường hợp:

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Scroll ID không còn hợp lệ | Context đã hết keep_alive hoặc bị clear | Khởi tạo scan mới từ checkpoint bền vững |
| Request timeout | Cluster bận, batch quá lớn hoặc mạng chậm | Giảm batch, xem tải cluster và tăng timeout có kiểm soát |
| Shard failure | Shard unavailable hoặc lỗi truy vấn | Kiểm tra `_shards.failures`, logs và trạng thái cluster |
| Consumer xử lý quá chậm | Batch lớn hoặc downstream chậm | Giảm batch, giảm công việc đồng bộ hoặc dùng queue/backpressure |
| Quá nhiều open contexts | Không đóng scroll hoặc quá nhiều job song song | Dọn dẹp context và giới hạn concurrency |
| Job chết giữa batch | Process bị dừng hoặc lỗi không xử lý | Retry idempotent và khởi động lại từ checkpoint |

Không nên bỏ qua `timed_out` hoặc shard failure nếu tác vụ yêu cầu đầy đủ dữ liệu. Với export/billing/audit, cần xác định rõ điều kiện thành công và ghi nhận số document xử lý được.

## 18. Scroll và `search_after` + Point in Time (PIT)

Scroll và `search_after` đều giúp duyệt lượng lớn kết quả, nhưng phục vụ các kiểu công việc khác nhau.

| Tiêu chí | Scroll | `search_after` + PIT |
|---|---|---|
| Mục tiêu chính | Quét dữ liệu theo lô, export, batch processing | Phân trang sâu và duyệt kết quả có thứ tự |
| Cơ chế tiếp tục | Scroll ID do server quản lý | Sort values của hit cuối cùng |
| Snapshot | Scroll context giữ search view ban đầu | PIT giữ snapshot; mỗi request dùng `search_after` |
| Sắp xếp | `_doc` thường hiệu quả khi chỉ scan | Cần sort ổn định và dùng giá trị sort làm cursor |
| Quản lý trạng thái | Context server-side, phải clear | PIT server-side và cursor do client giữ |
| Phù hợp UI pagination | Không | Phù hợp hơn |
| Resume lâu dài | Scroll ID tạm thời, không phải checkpoint bền vững | Cursor/PIT cũng có hạn sống; cần checkpoint ứng dụng nếu resume dài hạn |

Elasticsearch khuyến nghị PIT kết hợp `search_after` cho nhiều trường hợp phân trang sâu thay vì scroll. Scroll vẫn hữu ích cho scan/batch khi ứng dụng muốn lấy lần lượt toàn bộ tập kết quả mà không cần tạo sort nghiệp vụ.

### Ví dụ mở PIT

```http
POST /events/_pit?keep_alive=1m
```

Response trả về PIT ID.

### Search trang đầu với PIT

```http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "PIT_ID_FROM_OPEN_RESPONSE",
    "keep_alive": "1m"
  },
  "sort": [
    { "@timestamp": "asc" },
    { "_shard_doc": "asc" }
  ],
  "query": {
    "match_all": {}
  }
}
```

### Search trang tiếp theo

Lấy mảng `sort` của hit cuối cùng trong trang trước và truyền vào `search_after`:

```json
{
  "size": 500,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "@timestamp": "asc" },
    { "_shard_doc": "asc" }
  ],
  "search_after": [
    "2026-01-01T12:30:00Z",
    4294967298
  ],
  "query": {
    "match_all": {}
  }
}
```

PIT ID có thể được làm mới trong response; hãy dùng ID mới nhất. Khi hoàn tất, đóng PIT:

```http
DELETE /_pit
Content-Type: application/json

{
  "id": "LATEST_PIT_ID"
}
```

`search_after` yêu cầu sort ổn định. PIT thường bổ sung `_shard_doc` làm tie-breaker để xác định thứ tự giữa các document có giá trị sort trùng nhau.

## 19. Scroll không phải Bulk API

Scroll là cơ chế đọc. Bulk API là cơ chế ghi nhiều action trong một request. Hai API thường được kết hợp trong tác vụ migration nhưng có vai trò khác nhau.

```text
Scroll API
   |
   v
Đọc 500 document
   |
   v
Chuyển đổi dữ liệu
   |
   v
Bulk API
   |
   v
Ghi nhiều document sang index đích
```

Ví dụ, job reindex tùy chỉnh có thể đọc batch từ index nguồn bằng scroll, chuyển đổi từng document, sau đó ghi batch sang index đích bằng Bulk API. Cần kiểm tra từng item của bulk response và retry lỗi tạm thời có chọn lọc.

Nếu chỉ cần sao chép dữ liệu giữa các index Elasticsearch mà không cần biến đổi phức tạp, API `_reindex` thường đơn giản hơn và có hỗ trợ xử lý nội bộ. Nếu cần logic Java riêng, enrichment từ hệ thống ngoài hoặc chuyển đổi schema phức tạp, scroll + bulk cho phép kiểm soát chi tiết hơn.

## 20. So sánh Scroll với `_reindex`

| Tiêu chí | Scroll + ứng dụng + Bulk | `_reindex` API |
|---|---|---|
| Chuyển đổi dữ liệu bằng Java | Linh hoạt | Hạn chế trong script/pipeline server-side |
| Enrichment từ API ngoài | Có thể | Không trực tiếp |
| Sao chép đơn giản index sang index | Cần tự viết pipeline | Thường phù hợp hơn |
| Kiểm soát từng document | Cao | Ít hơn ở tầng ứng dụng |
| Phức tạp vận hành | Phải quản lý scroll, bulk, retry và checkpoint | Elasticsearch quản lý phần lớn pipeline nội bộ |
| Phù hợp | ETL tùy biến | Copy/reindex theo query và mapping đích |

Không nên tự triển khai scroll + bulk nếu `_reindex` đã đáp ứng yêu cầu. Ngược lại, khi cần xử lý nghiệp vụ hoặc tích hợp hệ thống ngoài, ứng dụng có thể cần kiểm soát từng batch.

## 21. Theo dõi tiến độ và metrics

Một job scan nên ghi nhận tiến độ ở cấp batch:

- Số batch đã đọc.
- Tổng document đã đọc.
- Tổng document xử lý thành công.
- Tổng document lỗi hoặc bị bỏ qua.
- Thời gian lấy batch.
- Thời gian xử lý batch.
- Kích thước response trung bình.
- Số lần retry.
- Thời điểm bắt đầu và kết thúc.

Không nhất thiết log toàn bộ document hoặc scroll ID. Log số lượng và checkpoint an toàn giúp điều tra mà không làm lộ dữ liệu nhạy cảm hoặc tạo log quá lớn.

Nếu job có nhiều partition chạy song song, theo dõi metrics riêng cho từng partition và giới hạn concurrency. Mở quá nhiều scroll cùng lúc có thể làm cluster cạn tài nguyên ngay cả khi mỗi scroll có batch nhỏ.

## 22. Bảo mật và quyền truy cập

Tác vụ scroll thường đọc lượng dữ liệu lớn, vì vậy tài khoản chạy job chỉ nên có quyền đọc cần thiết trên index/alias liên quan. Không cấp quyền quản trị cluster nếu job chỉ cần search.

Scroll ID là thông tin trạng thái tạm thời của search context. Không ghi nó vào log công khai hoặc truyền qua nơi không tin cậy. Bảo vệ kết nối bằng TLS và quản lý credentials qua cơ chế secret của môi trường chạy.

Với export chứa dữ liệu cá nhân, cần giới hạn field bằng source filtering và kiểm soát nơi lưu file đầu ra, thời gian lưu và quyền truy cập. Đây là trách nhiệm của pipeline ứng dụng, không phải chức năng tự động của Scroll API.

## 23. Lỗi thường gặp

### Quên truyền `scroll` ở request đầu

Không có scroll context thì request tiếp theo không thể tiếp tục bằng scroll ID. Request đầu tiên phải yêu cầu scroll.

### Dùng scroll ID cũ

Response tiếp theo có thể trả ID mới. Luôn thay biến hiện tại bằng ID mới nhất trước lần gọi tiếp theo và trước cleanup.

### Không clear context

Context tiếp tục giữ tài nguyên cho tới khi hết keep_alive. Dùng `finally` hoặc try-with-resources để đóng sớm.

### Đặt keep_alive quá ngắn

Nếu xử lý batch lâu hơn keep_alive, context có thể hết hạn. Đo thời gian xử lý và đặt khoảng đệm phù hợp.

### Đặt batch size quá lớn

Response lớn có thể làm tăng heap, GC, network và thời gian xử lý. Điều chỉnh theo kích thước document và năng lực consumer.

### Dùng scroll cho phân trang UI

Scroll giữ server-side context và không phù hợp với việc người dùng chuyển trang tùy ý. Dùng `search_after` + PIT cho deep pagination.

### Coi scroll ID là checkpoint lâu dài

Scroll context có thời hạn và có thể mất khi node/context không còn. Dùng checkpoint nghiệp vụ bền vững và xử lý idempotent.

### Chỉ kiểm tra HTTP status của Bulk API

Bulk request có thể có item lỗi riêng. Phải kiểm tra từng item trước khi đánh dấu batch hoàn tất.

### Quét toàn bộ `_source` dù chỉ cần vài field

Payload lớn làm giảm throughput. Dùng source filtering hoặc projection phù hợp.

## 24. Quy trình triển khai job quét dữ liệu theo lô

Khi xây dựng một job đọc dữ liệu lớn, có thể đi theo trình tự:

1. Xác định index/alias nguồn và query giới hạn tập document cần đọc.
2. Chọn Scroll nếu đây là tác vụ scan/batch; chọn PIT + `search_after` nếu cần duyệt theo thứ tự hoặc phân trang sâu.
3. Chọn batch size ban đầu dựa trên kích thước document và năng lực consumer.
4. Chọn keep_alive đủ cho thời gian xử lý một batch, có khoảng đệm.
5. Dùng `_doc` sort nếu không cần thứ tự nghiệp vụ.
6. Chỉ lấy các field cần thiết bằng source filtering.
7. Xử lý từng batch, không giữ toàn bộ tập kết quả trong RAM.
8. Thiết kế retry, idempotency và checkpoint bền vững cho job có thể chạy lại.
9. Luôn clear scroll context trong `finally` hoặc đóng iterator.
10. Theo dõi open contexts, heap, GC, network, shard failures và tiến độ batch.
11. Kiểm thử trường hợp context hết hạn, process dừng giữa batch và downstream bị lỗi.
12. Chỉ đánh dấu job hoàn tất sau khi tất cả batch và item ghi đích đã được xác nhận.

## 25. Kết luận

Scroll API cho phép quét một tập document lớn theo từng batch bằng cách giữ search context và tiếp tục đọc qua `scroll_id`. Request đầu tiên xác định query, batch size và keep_alive; các request tiếp theo lấy batch mới bằng ID mới nhất; khi hoàn tất hoặc gặp lỗi, ứng dụng phải clear context.

Trong Spring Data Elasticsearch, `searchForStream(...)` cung cấp cách duyệt kết quả thuận tiện và cần đóng iterator. Khi cần kiểm soát thủ công, có thể dùng các thao tác scroll start/continue/clear mà phiên bản Spring Data hỗ trợ hoặc gọi REST API trực tiếp. Hãy chọn batch size theo kích thước document và năng lực xử lý, dùng `_doc` khi chỉ cần scan, giới hạn `_source`, xử lý từng batch với idempotency và checkpoint. Scroll phù hợp với export/backfill/batch processing; với phân trang sâu có thứ tự, PIT kết hợp `search_after` thường là lựa chọn phù hợp hơn.

## Tài liệu tham khảo

- [Elasticsearch – Scroll search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results#scroll-search-results)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Clear scroll API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-clear-scroll)
- [Elasticsearch – Point in Time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
- [Elasticsearch – Search after and PIT pagination](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Spring Data Elasticsearch – Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – `SearchHitsIterator` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHitsIterator.html)
