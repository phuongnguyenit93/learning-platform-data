# BulkOptions, kích thước lô và giới hạn theo phiên bản

Khi nhập hoặc cập nhật nhiều document trong Elasticsearch, gửi từng document bằng một request riêng thường tạo ra nhiều overhead mạng và xử lý. Bulk API cho phép gửi nhiều thao tác index, create, update hoặc delete trong một request. Spring Data Elasticsearch cung cấp các API bulk và lớp BulkOptions để cấu hình một số thuộc tính của request bulk.

Có ba khái niệm cần phân biệt:

- **BulkOptions:** cấu hình cách Elasticsearch xử lý một request bulk, ví dụ refresh policy, timeout, số shard copy cần hoạt động và ingest pipeline nếu phiên bản hỗ trợ.
- **Batch size:** số thao tác hoặc tổng dung lượng dữ liệu ứng dụng gom vào một request bulk.
- **Giới hạn theo phiên bản và cluster:** các giới hạn về kích thước HTTP request, API của Spring Data, Elasticsearch Java API Client, số lượng thao tác và tài nguyên cluster.

BulkOptions không tự chia một danh sách lớn thành nhiều batch. Ứng dụng cần xác định kích thước lô, chia dữ liệu và gửi từng bulk request. Kích thước phù hợp phụ thuộc vào kích thước document, mapping, số shard, tốc độ ingest, mạng và cấu hình cluster.

## 1. Vì sao nên dùng Bulk API?

Giả sử cần nhập 50.000 sản phẩm vào index products. Nếu gọi save hoặc index riêng cho từng sản phẩm, ứng dụng phải gửi nhiều request:

    for (Product product : products) {
        operations.save(product);
    }

Mỗi request riêng có overhead kết nối, serialization, scheduling và xử lý ở Elasticsearch. Khi số document lớn, chi phí này có thể làm giảm throughput.

Bulk API gom nhiều thao tác vào một request:

    POST products/_bulk
    {"index":{"_id":"p-1"}}
    {"name":"Keyboard K8","price":120}
    {"index":{"_id":"p-2"}}
    {"name":"Mouse M3","price":45}
    {"delete":{"_id":"p-3"}}

Bulk request có thể chứa nhiều loại thao tác. Mỗi thao tác thường có một dòng metadata và, với index/create/update, một dòng payload tương ứng. Delete chỉ cần dòng metadata.

Lợi ích chính:

- Giảm số request HTTP.
- Tăng throughput khi nhập dữ liệu lớn.
- Cho phép kết hợp index, create, update và delete trong cùng bulk request.
- Dễ điều chỉnh kích thước batch và số worker.
- Có thể áp dụng một số thiết lập request chung qua BulkOptions.

Bulk không phải transaction. Một request có thể thành công với một số item và thất bại với item khác. Ứng dụng phải kiểm tra kết quả từng item.

## 2. Bulk API và BulkOptions giải quyết hai vấn đề khác nhau

Bulk API định nghĩa danh sách thao tác cần thực hiện. BulkOptions cấu hình cách request đó được gửi và xử lý ở cấp request.

Ví dụ về trách nhiệm:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Danh sách IndexQuery/UpdateQuery | Những document hoặc thao tác nào cần thực hiện? |
| BulkOptions | Request dùng refresh policy, timeout, routing hoặc pipeline nào? |
| Batch/chunking ở ứng dụng | Một request chứa bao nhiêu thao tác hoặc bao nhiêu byte? |
| Concurrency | Có bao nhiêu bulk request chạy đồng thời? |
| Retry policy | Khi item lỗi tạm thời, ứng dụng thử lại phần nào và sau bao lâu? |
| Mapping và cluster settings | Document, request và workload có nằm trong giới hạn không? |

Không nên nhầm BulkOptions với một bộ điều khiển batch tự động. Nếu đưa một triệu IndexQuery vào một lần bulkIndex, BulkOptions không tự bảo đảm danh sách đó được chia thành nhiều request nhỏ.

## 3. BulkOptions trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp BulkOptions như một abstraction cho một số tham số của Bulk API. Các tùy chọn thường gặp trong các phiên bản hiện đại gồm:

| Tùy chọn | Ý nghĩa |
|---|---|
| refreshPolicy | Quy định khi nào thay đổi trở nên nhìn thấy qua search |
| timeout | Thời gian chờ cho các điều kiện xử lý mà Bulk API hỗ trợ |
| waitForActiveShards | Số shard copy cần hoạt động trước khi thao tác được thực hiện |
| pipeline | Ingest pipeline mặc định áp dụng cho document trong request |
| routing | Routing mặc định của request khi API và thao tác hỗ trợ |
| includeSourceOnError | Có đưa source vào chi tiết lỗi hay không, nếu phiên bản hỗ trợ |

Danh sách method và option chính xác phụ thuộc phiên bản Spring Data Elasticsearch. Không phải mọi phiên bản đều có cùng builder method hoặc cùng kiểu dữ liệu cho timeout, refresh và waitForActiveShards.

Ví dụ minh họa cách xây dựng:

    BulkOptions bulkOptions = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout("2m")
        .withWaitForActiveShards("1")
        .build();

Đây là ví dụ theo dạng builder thường gặp ở Spring Data Elasticsearch hiện đại. Trước khi dùng nguyên văn, kiểm tra package, method và overload trong phiên bản dependency của dự án. Nếu IDE không nhận một method, không nên tự thay bằng API của một thế hệ client khác mà chưa kiểm tra compatibility.

BulkOptions không thay thế dữ liệu của từng IndexQuery hoặc UpdateQuery. Ví dụ ID, source, version, routing riêng của một document hoặc script update có thể thuộc chính thao tác đó.

## 4. Refresh policy khi bulk nhập dữ liệu

Refresh quyết định khi nào document mới có thể được tìm thấy qua search. Indexing và search visibility không nhất thiết xảy ra đồng thời.

Các lựa chọn phổ biến:

| Refresh policy | Hành vi | Khi phù hợp |
|---|---|---|
| NONE | Không yêu cầu refresh riêng cho request; Elasticsearch refresh theo lịch và điều kiện bình thường | Bulk import lớn, không cần search thấy ngay |
| IMMEDIATE | Yêu cầu refresh ngay sau thao tác | Chỉ khi cần document hiển thị ngay, chấp nhận chi phí |
| WAIT_UNTIL | Chờ đến khi refresh làm thay đổi có thể nhìn thấy qua search | Cần read-after-write visibility mà không ép refresh ngay lập tức |

Tên enum và cách truyền giá trị phụ thuộc Spring Data version. Trong REST Bulk API, các giá trị tương ứng thường là false, true và wait_for.

### Vì sao IMMEDIATE có thể làm giảm throughput?

Refresh tạo segment mới để document được tìm thấy qua search. Nếu mỗi batch nhỏ đều yêu cầu refresh ngay, Elasticsearch có thể phải tạo nhiều segment nhỏ, tăng chi phí merge và I/O.

Với một đợt import lớn:

1. Gửi nhiều bulk request với refresh policy NONE.
2. Chờ tất cả batch hoàn tất.
3. Nếu cần search thấy dữ liệu ngay, thực hiện một lần refresh phù hợp sau import.

Không nên đặt IMMEDIATE mặc định cho mọi bulk request chỉ vì muốn kiểm tra dữ liệu ngay sau mỗi lần ghi. Hãy chọn visibility requirement theo use case.

WAIT_UNTIL khác IMMEDIATE: nó đợi refresh tiếp theo làm dữ liệu nhìn thấy, thay vì chủ động ép refresh ngay. Nếu cluster đang chịu tải hoặc refresh bị trì hoãn, request có thể phải chờ.

## 5. Timeout và wait_for_active_shards

Timeout và waitForActiveShards có liên quan đến khả năng xử lý request trên cluster, nhưng chúng không giống timeout tổng thể của HTTP client.

### Timeout

Bulk API có thể chờ điều kiện shard hoặc các thao tác liên quan trong một khoảng thời gian. Timeout của request không có nghĩa mọi bước indexing, ingest pipeline và replication chắc chắn kết thúc trong đúng thời gian đó.

Ứng dụng vẫn cần timeout ở HTTP client, timeout của job và deadline của worker. Nếu HTTP client hết thời gian chờ trong khi cluster vẫn đang xử lý, ứng dụng có thể không biết request đã hoàn tất đến đâu. Khi đó cần đối soát trạng thái và thiết kế retry an toàn.

### Wait for active shards

wait_for_active_shards quy định số shard copy cần active trước khi request được thực hiện. Ví dụ giá trị 1 thường có nghĩa primary shard phải active; giá trị all yêu cầu các shard copy được chỉ định phải active theo semantics của Elasticsearch.

Tùy chọn này không đồng nghĩa với việc mọi replica đã xác nhận từng thao tác sau khi bulk hoàn tất. Nó là điều kiện về shard availability trước khi thực hiện.

Chọn giá trị cao hơn có thể làm request chờ khi replica chưa sẵn sàng. Chọn giá trị thấp hơn giúp ghi tiếp tục khi primary hoạt động, nhưng cần hiểu yêu cầu durability và cluster health của hệ thống.

## 6. Ingest pipeline trong BulkOptions

Elasticsearch ingest pipeline có thể biến đổi document trước khi index, ví dụ:

- Chuẩn hóa field.
- Tạo field dẫn xuất.
- Parse dữ liệu từ một field đầu vào.
- Gắn metadata.
- Xử lý nội dung theo processor được cấu hình.

Bulk API có thể chỉ định pipeline ở cấp request. Nếu BulkOptions version hỗ trợ pipeline, ứng dụng có thể cấu hình pipeline mặc định cho các thao tác trong request.

Ví dụ REST:

    PUT _ingest/pipeline/product-normalize
    {
      "processors": [
        {
          "lowercase": {
            "field": "brand"
          }
        },
        {
          "set": {
            "field": "ingested",
            "value": true
          }
        }
      ]
    }

Bulk request:

    POST products/_bulk?pipeline=product-normalize
    {"index":{"_id":"p-1"}}
    {"name":"Keyboard K8","brand":"KEYCHRON"}

Pipeline có thể thêm thời gian xử lý cho mỗi document. Khi import lớn, benchmark với pipeline bật và tắt để hiểu throughput thực tế.

Nếu từng thao tác cần pipeline khác nhau hoặc cần bỏ qua pipeline mặc định, phải kiểm tra khả năng override của Bulk API và client version. Không giả định BulkOptions có thể biểu diễn mọi cấu hình per-item.

## 7. Routing mặc định và routing theo từng document

Routing xác định shard nhận document. Với custom routing, các document có cùng routing value được đưa về cùng shard.

BulkOptions ở một số phiên bản có thể cấu hình routing ở cấp request. Điều này phù hợp khi toàn bộ thao tác trong batch dùng cùng routing value, ví dụ import dữ liệu cho một tenant.

Nếu mỗi document có routing khác nhau, routing cần được đặt ở từng thao tác index/update tương ứng. Không dùng một routing mặc định chung nếu nó làm các document bị gửi đến shard sai.

Ví dụ:

    IndexQuery query = IndexQuery.builder()
        .withId(product.getId())
        .withObject(product)
        .withRouting(product.getTenantId())
        .build();

Tên builder method cho routing phụ thuộc phiên bản Spring Data. Hãy xác nhận rằng routing được gửi trong metadata của từng bulk item.

Routing sai có thể khiến:

- Document nằm trên shard khác với shard mà query theo routing tìm kiếm.
- Update/delete không tìm thấy document.
- Parent-child relation không hoạt động vì parent và child không cùng shard.
- Một shard bị quá tải nếu routing dồn phần lớn dữ liệu vào cùng một giá trị.

## 8. Kích thước lô: đếm document hay đo byte?

Một batch có 1.000 document nhỏ có thể nhẹ hơn batch 100 document lớn. Vì vậy, chỉ giới hạn số document không đủ để kiểm soát request size.

Nên theo dõi cả:

- Số thao tác trong một batch.
- Tổng byte của payload NDJSON.
- Kích thước trung bình và percentile của document.
- Thời gian hoàn thành mỗi bulk request.
- Số lỗi và số item bị reject.

Một cách bắt đầu phổ biến là thử batch payload ở khoảng vài MB đến khoảng 10 MB, sau đó benchmark để tìm vùng throughput tốt. Khoảng 5–15 MB thường được dùng làm điểm bắt đầu thử nghiệm, không phải giới hạn bắt buộc hay cấu hình tối ưu cho mọi cluster.

Không nên tạo một request rất lớn chỉ để giảm số lần gọi API. Request lớn có thể tốn bộ nhớ ở ứng dụng, qua mạng và ở coordinating/data node; khi lỗi, retry cũng tốn kém hơn.

### Ước lượng batch size

Giả sử document có kích thước JSON trung bình khoảng 4 KB. Nếu chọn 1.000 document mỗi batch, payload thô xấp xỉ:

    4 KB × 1.000 = 4 MB

Con số thực tế còn bao gồm metadata dòng bulk, dấu xuống dòng, field escaping và sự khác nhau giữa document. Hãy đo byte sau serialization nếu cần giới hạn request chính xác.

Một bộ cấu hình có thể bắt đầu như sau:

    int maxDocumentsPerBatch = 1000;
    long maxPayloadBytes = 8L * 1024 * 1024;

    // Thêm thao tác cho đến khi đạt một trong hai giới hạn.
    // Gửi batch rồi tiếp tục với phần dữ liệu còn lại.

Đây là giá trị khởi đầu để benchmark. Batch size tốt cần được xác định từ dữ liệu thực và khả năng của cluster.

## 9. Giới hạn kích thước request của Elasticsearch

Elasticsearch có giới hạn kích thước HTTP request thông qua cấu hình http.max_content_length. Giá trị mặc định thường gặp là 100 MB, nhưng cấu hình có thể được thay đổi và có thể khác theo phiên bản hoặc môi trường triển khai.

Không nên đặt bulk request sát giới hạn tối đa:

- Request có thể bị từ chối trước khi bulk action được xử lý.
- Buffering và serialization có thể tạo áp lực bộ nhớ.
- Proxy, gateway hoặc load balancer có thể có giới hạn thấp hơn Elasticsearch.
- Một request lớn khó retry và tốn thời gian hơn khi lỗi.

Hãy kiểm tra cấu hình cluster và hạ tầng mạng thực tế. Giới hạn ở reverse proxy hoặc ingress cũng có thể thấp hơn http.max_content_length.

Bulk API dùng NDJSON. Mỗi action và source cần đúng định dạng, mỗi dòng kết thúc bằng newline và request phải có newline cuối cùng. JSON array thông thường không phải định dạng bulk request.

## 10. Không có một số lượng document tối đa cố định cho mọi bulk

Bulk API không định nghĩa một con số document tối đa chung phù hợp cho mọi hệ thống. Giới hạn thực tế phụ thuộc:

- Kích thước source document.
- Số lượng thao tác và metadata.
- Số shard nhận dữ liệu.
- Ingest pipeline và mapping.
- Tốc độ disk và CPU.
- Heap, indexing buffer và indexing pressure.
- Số bulk request đồng thời.
- Queue và backpressure ở thread pool.

Một batch 10.000 document nhỏ có thể chạy tốt trong môi trường này nhưng gây reject hoặc latency cao trong môi trường khác. Hãy benchmark bằng payload có kích thước và phân phối tương tự dữ liệu production.

## 11. Bulk API trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp ElasticsearchOperations để thực hiện bulk. Tùy phiên bản, các method thường gặp gồm bulkIndex cho IndexQuery, bulkUpdate cho UpdateQuery và bulkDelete cho thao tác xóa.

Ví dụ xây dựng IndexQuery:

    List<IndexQuery> queries = products.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

    List<IndexedObjectInformation> result =
        operations.bulkIndex(
            queries,
            options,
            IndexCoordinates.of("products")
        );

Các kiểu thường dùng:

    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
    import org.springframework.data.elasticsearch.core.IndexedObjectInformation;
    import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
    import org.springframework.data.elasticsearch.core.query.BulkOptions;
    import org.springframework.data.elasticsearch.core.query.IndexQuery;

Package hoặc chữ ký của một số lớp có thể khác giữa các major version. Hãy kiểm tra dependency thực tế và import từ đúng Spring Data Elasticsearch đang dùng.

Ví dụ trên tạo một danh sách IndexQuery rồi gửi trong một bulk request. Nếu products chứa quá nhiều phần tử, cần chia danh sách thành các batch trước khi gọi bulkIndex. BulkOptions không tự chia danh sách đó.

## 12. Chia danh sách thành nhiều batch

Một cách đơn giản là chia theo số document:

    int batchSize = 1000;

    for (int start = 0; start < products.size(); start += batchSize) {
        int end = Math.min(start + batchSize, products.size());
        List<Product> batch = products.subList(start, end);

        List<IndexQuery> indexQueries = batch.stream()
            .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .build())
            .toList();

        operations.bulkIndex(
            indexQueries,
            bulkOptions,
            IndexCoordinates.of("products")
        );
    }

Đây là cách dễ đọc khi document có kích thước tương đối đồng đều. Với document có kích thước biến động mạnh, nên chia theo tổng byte ước lượng hoặc byte sau serialization để tránh batch lớn bất thường.

### Tránh tạo toàn bộ IndexQuery trong bộ nhớ

Nếu nguồn dữ liệu có hàng triệu document, không nên tải toàn bộ vào List rồi mới chia batch. Hãy đọc dữ liệu theo trang hoặc stream:

    while (source.hasNext()) {
        List<Product> batch = source.readNextBatch(1000);
        bulkIndex(batch);
    }

Mã giả này thể hiện cách đọc và gửi tuần tự. Nguồn có thể là database cursor, file reader, message queue hoặc API phân trang.

Streaming giúp giới hạn bộ nhớ ứng dụng và cho phép áp dụng backpressure. Cần xác định checkpoint để job có thể tiếp tục hoặc chạy lại sau lỗi.

## 13. Bulk update và delete

Bulk không chỉ dành cho index mới. Ứng dụng có thể gom các UpdateQuery hoặc ID cần xóa.

Ví dụ tạo update query:

    UpdateQuery update = UpdateQuery.builder(product.getId())
        .withDocument(Document.from(
            Map.of("price", product.getPrice())
        ))
        .build();

Sau đó gửi nhiều update:

    operations.bulkUpdate(
        updateQueries,
        bulkOptions,
        IndexCoordinates.of("products")
    );

Chi tiết builder UpdateQuery và kiểu Document thay đổi theo phiên bản. Với update, cần xác định rõ:

- Partial document hay scripted update.
- Có dùng upsert hay không.
- Hành vi khi document chưa tồn tại.
- Version hoặc optimistic concurrency control.
- Retry on conflict nếu API thao tác hỗ trợ.

Bulk delete có thể gom nhiều ID hoặc query tương ứng tùy overload của Spring Data. Hãy kiểm tra chữ ký method và đảm bảo routing nếu document dùng custom routing.

## 14. Repository saveAll và BulkOptions

Spring Data repository cung cấp saveAll để lưu nhiều entity:

    productRepository.saveAll(products);

Đây là API thuận tiện khi không cần cấu hình chi tiết request. Implementation của Spring Data Elasticsearch thường có thể tối ưu thao tác nhiều entity bằng bulk, nhưng hành vi nội bộ và khả năng truyền BulkOptions phụ thuộc phiên bản.

Nếu cần kiểm soát refresh policy, timeout, waitForActiveShards hoặc pipeline, ElasticsearchOperations với bulk method và BulkOptions thường cho quyền điều khiển rõ hơn.

Không nên suy luận rằng saveAll luôn dùng đúng batch size mong muốn hoặc tự chia mọi danh sách lớn thành request nhỏ theo một ngưỡng cố định. Hãy kiểm tra implementation của phiên bản đang dùng và tự chunk dữ liệu khi cần kiểm soát.

## 15. Bulk response và partial failure

Bulk API có thể trả HTTP response thành công nhưng một số item bên trong thất bại. Response có trường errors và danh sách items tương ứng với từng thao tác.

Ví dụ:

    {
      "took": 25,
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-1",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-2",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field"
            }
          }
        },
        {
          "index": {
            "_id": "p-3",
            "status": 429,
            "error": {
              "type": "es_rejected_execution_exception",
              "reason": "rejected execution"
            }
          }
        }
      ]
    }

Trong ví dụ:

- p-1 đã được index thành công.
- p-2 thất bại do dữ liệu không phù hợp mapping.
- p-3 bị từ chối tạm thời do áp lực xử lý.

Không nên chỉ kiểm tra HTTP status hoặc giả định cả bulk request thành công nếu method không ném exception. Cần kiểm tra item-level result hoặc exception/result object do Spring Data trả về.

### Phân loại lỗi

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Dữ liệu không hợp lệ | Mapping parse error, field type sai | Đưa vào dead-letter/error report, sửa dữ liệu |
| Conflict | Version conflict | Đọc lại trạng thái hoặc áp dụng retry có kiểm soát |
| Quá tải tạm thời | HTTP 429, rejected execution | Backoff rồi retry item bị lỗi |
| Shard/cluster tạm thời | Unavailable shard, timeout | Retry có giới hạn sau khi kiểm tra trạng thái |
| Lỗi cấu hình | Index không tồn tại, pipeline sai | Dừng batch/job và sửa cấu hình |

Retry toàn bộ bulk khi chỉ một vài item thất bại có thể ghi lặp những thao tác đã thành công. Với index theo ID ổn định, việc gửi lại cùng document có thể idempotent về trạng thái cuối, nhưng update increment hoặc script không idempotent có thể bị áp dụng hai lần.

## 16. Retry và backoff

Khi Elasticsearch trả 429 hoặc lỗi quá tải tạm thời, không nên retry liên tục ngay lập tức. Cách thường dùng là exponential backoff có jitter:

    delay = min(maxDelay, baseDelay * 2^attempt)
    delay = random(0, delay)

Ví dụ khoảng chờ có thể tăng dần 100 ms, 200 ms, 400 ms, 800 ms rồi giới hạn ở một ngưỡng tối đa. Jitter giúp nhiều worker không cùng retry vào một thời điểm.

Nguyên tắc:

- Chỉ retry lỗi có khả năng tạm thời.
- Giới hạn số lần thử.
- Retry các item thất bại nếu có thể, không gửi lại cả batch một cách mù quáng.
- Giữ nguyên ID và payload để thao tác có tính lặp an toàn khi phù hợp.
- Không retry lỗi mapping hoặc lỗi dữ liệu không thể tự hết.
- Ghi lại item lỗi để đối soát.
- Dừng tăng concurrency nếu cluster đang bị overload.

Một số client hoặc framework có retry nội bộ cho lỗi cụ thể. Hãy kiểm tra hành vi của phiên bản đang dùng để tránh chồng nhiều tầng retry và tạo tải khuếch đại.

## 17. Tính idempotency của thao tác bulk

Retry an toàn phụ thuộc loại thao tác:

| Thao tác | Tính lặp lại thường gặp |
|---|---|
| index cùng ID và cùng source | Thường cho cùng trạng thái cuối |
| create cùng ID | Lần sau có thể conflict vì document đã tồn tại |
| delete cùng ID | Thường có thể lặp, nhưng kết quả status có thể khác |
| update đặt giá trị cố định | Có thể idempotent nếu cùng payload và semantics |
| update tăng counter | Không idempotent nếu áp dụng nhiều lần |
| script cộng thêm giá trị | Không idempotent nếu retry sau khi lần đầu đã thành công |

Nếu client timeout và không nhận được response, ứng dụng không thể mặc định rằng Elasticsearch chưa thực hiện request. Trạng thái có thể không rõ ràng. Cần thiết kế thao tác có thể retry, kiểm tra lại document hoặc dùng khóa/idempotency marker.

Đối với import snapshot, index theo ID ổn định thường dễ retry hơn update kiểu increment. Với event stream, cần lưu event ID hoặc version để tránh áp dụng cùng event nhiều lần.

## 18. Tuning batch size theo throughput

Không có batch size tối ưu cố định. Cách tốt nhất là benchmark theo từng bước:

1. Bắt đầu với batch nhỏ và số worker thấp.
2. Đo payload bytes, latency, throughput và lỗi.
3. Tăng batch size từng bước.
4. Quan sát throughput có tiếp tục tăng hay đã bão hòa.
5. Khi latency, memory hoặc reject tăng mạnh, giảm batch size hoặc concurrency.
6. Thử lại với document lớn, pipeline bật và mapping thực tế.

Các chỉ số nên theo dõi:

- Documents per second.
- Bytes per second.
- Bulk request latency p50/p95/p99.
- Số item lỗi theo status/error type.
- HTTP 429 và rejected execution.
- JVM heap, GC pause và allocation ở ứng dụng.
- CPU, disk I/O và indexing pressure ở cluster.
- Thread pool write/bulk queue và rejected count theo phiên bản.
- Segment count, merge time và refresh activity.

Nếu throughput không tăng khi tăng batch size, có thể bottleneck nằm ở disk, ingest pipeline, mapping, shard distribution hoặc concurrency chứ không phải số document mỗi request.

## 19. Tuning concurrency và backpressure

Batch size và số request đồng thời là hai biến khác nhau. Một batch lớn với một worker có thể tạo throughput khác nhiều so với batch nhỏ và nhiều worker.

Tăng concurrency quá cao có thể:

- Làm đầy write/bulk thread pool queue.
- Tăng indexing pressure.
- Tăng memory và network buffering.
- Tạo nhiều HTTP request đang chờ.
- Làm tăng số lỗi 429 và retry.
- Làm latency của search và indexing khác tăng.

Một chiến lược an toàn:

- Bắt đầu với ít worker.
- Chỉ tăng concurrency khi cluster còn headroom.
- Giới hạn số batch đang chờ.
- Khi gặp 429 liên tục, giảm concurrency hoặc tăng backoff.
- Không để producer đọc nhanh hơn tốc độ Elasticsearch có thể ghi trong thời gian dài.

Đây là backpressure: khi Elasticsearch chậm, nguồn dữ liệu phải giảm tốc thay vì tiếp tục tích lũy hàng đợi trong bộ nhớ.

## 20. Giới hạn từ mapping và document

Bulk API không bỏ qua giới hạn của từng document. Một thao tác bulk vẫn phải tuân theo:

- Mapping field type.
- Giới hạn kích thước document và request.
- Giới hạn số field hoặc mapping explosion.
- Giới hạn nested object nếu document có nested data.
- Ingest pipeline và script constraints.
- Versioning và concurrency control.

Nếu bulk thất bại do mapper_parsing_exception, tăng batch size hoặc đổi timeout không giải quyết được lỗi dữ liệu. Cần kiểm tra source và mapping.

### Mapping explosion

Nếu import dữ liệu có tên field động không kiểm soát, số lượng field trong mapping có thể tăng nhanh. Điều này làm cluster tốn bộ nhớ và query chậm hoặc chạm giới hạn total fields.

Hãy chuẩn hóa schema, dùng flattened hoặc object phù hợp cho dữ liệu key-value động khi use case cho phép, và kiểm soát dynamic mapping.

## 21. Giới hạn theo phiên bản Spring Data Elasticsearch

Spring Data Elasticsearch đã thay đổi client integration qua các major version. Những khác biệt thường ảnh hưởng code bulk:

- Package và kiểu của BulkOptions.
- Builder method và kiểu tham số của timeout, refresh và waitForActiveShards.
- Chữ ký bulkIndex, bulkUpdate, bulkDelete.
- Kiểu trả về và cách biểu diễn item error.
- Client bên dưới: các thế hệ cũ dùng High Level REST Client; các thế hệ mới dùng Elasticsearch Java API Client.
- Cách cấu hình ingest pipeline, routing và các option bổ sung.

Không nên lấy một đoạn code từ tài liệu của major version khác rồi giả định nó compile trên dự án hiện tại.

### Xác định phiên bản đang dùng

Kiểm tra dependency Spring Data Elasticsearch được resolve trong build:

    ./gradlew dependencies

Hoặc dùng dependencyInsight với cấu hình phù hợp:

    ./gradlew dependencyInsight \
        --dependency spring-data-elasticsearch \
        --configuration runtimeClasspath

Trên Windows PowerShell, có thể chạy lệnh Gradle wrapper tương ứng:

    .\gradlew.bat dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath

Kiểm tra cả phiên bản Elasticsearch Java API Client được kéo theo. Không tự nâng riêng client nếu Spring Data đã quản lý một phiên bản tương thích.

### Kiểm tra API BulkOptions thực tế

Trong IDE hoặc Javadoc của dependency đã resolve, kiểm tra:

- Package của BulkOptions.
- Các method có trong builder.
- Kiểu dữ liệu được yêu cầu cho timeout và refresh policy.
- Overload bulkIndex/bulkUpdate/bulkDelete.
- Kiểu kết quả và cách đọc item-level errors.

Nếu cần hành vi mà abstraction BulkOptions của phiên bản không cung cấp, cân nhắc dùng API client tương ứng hoặc nâng cấp Spring Data theo ma trận tương thích. Không trộn các class request của client cũ và mới trong cùng implementation.

## 22. Giới hạn theo phiên bản Elasticsearch server

Elasticsearch server cũng có thay đổi về Bulk API, mapping, ingest pipeline và cấu hình cluster qua các phiên bản. Khi ứng dụng và cluster khác major/minor version, cần kiểm tra:

- API endpoint và field có được phiên bản server hỗ trợ không.
- Client có gửi request format tương thích không.
- Bulk action và option mới có được server nhận không.
- Mapping type hoặc field type có còn hợp lệ không.
- Cấu hình cluster như http.max_content_length và indexing pressure có giá trị nào.
- Các giới hạn thread pool, queue và request size có khác môi trường khác không.

Không nên dựa vào giá trị mặc định của một cluster khác. Hãy kiểm tra cluster đang chạy và tài liệu đúng phiên bản.

### Không nhầm giới hạn client với giới hạn server

Một request có thể bị giới hạn ở nhiều lớp:

    Ứng dụng tạo payload
          |
          v
    Spring Data / Java API Client
          |
          v
    HTTP client và connection pool
          |
          v
    Proxy / gateway / ingress
          |
          v
    Elasticsearch HTTP layer
          |
          v
    Coordinating node và data node

Giới hạn ở lớp thấp hơn có thể khiến request bị từ chối trước khi Elasticsearch xử lý. Khi điều tra lỗi request quá lớn hoặc timeout, cần xác định lớp thực sự trả lỗi.

## 23. Bulk và alias an toàn khi reindex/import

Khi import vào index được quản lý qua alias, cần bảo đảm thao tác bulk ghi đúng index đích. Với alias có thể trỏ nhiều index, thao tác ghi cần write index phù hợp.

Một số phiên bản BulkOptions hoặc Bulk API hỗ trợ require_alias để buộc target phải là alias. Nếu phiên bản có hỗ trợ, tùy chọn này có thể giúp tránh ghi nhầm trực tiếp vào index vật lý.

Không nên giả định mọi phiên bản Spring Data BulkOptions đều có method tương ứng. Nếu yêu cầu này quan trọng, kiểm tra API client và request thực tế của phiên bản đang dùng.

Một quy trình import an toàn thường gồm:

1. Tạo index mới với mapping và settings đã xác định.
2. Bulk import theo batch có giới hạn.
3. Kiểm tra số document, lỗi item và các query mẫu.
4. Refresh khi cần để xác minh dữ liệu qua search.
5. Chuyển alias theo thao tác phù hợp.
6. Giữ khả năng rollback theo quy trình vận hành.

Không nên đổi alias trước khi import và xác minh hoàn tất nếu người dùng cần đọc dữ liệu liên tục.

## 24. Bulk với ingest pipeline và refresh trong một job import

Một job import lớn có thể sử dụng các cấu hình:

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout("2m")
        .withWaitForActiveShards("1")
        .withPipeline("product-normalize")
        .build();

    for (List<Product> batch : batches) {
        List<IndexQuery> queries = toIndexQueries(batch);
        operations.bulkIndex(
            queries,
            options,
            IndexCoordinates.of("products")
        );
    }

Sau khi mọi batch hoàn tất, nếu cần kiểm tra bằng search ngay:

    operations.indexOps(IndexCoordinates.of("products"))
        .refresh();

Đây là ví dụ theo API builder phổ biến; kiểm tra option pipeline và kiểu RefreshPolicy ở version thực tế. Việc refresh sau import nên được thực hiện có chủ đích, không bắt buộc nếu ứng dụng chấp nhận visibility theo refresh schedule bình thường.

Nếu một batch có item lỗi, job cần ghi lại item thất bại và quyết định tiếp tục hay dừng. Không đánh dấu import hoàn tất chỉ vì vòng lặp đã gửi hết các request.

## 25. Theo dõi và xử lý lỗi trong Spring Data

Các API Spring Data có thể trả metadata cho thao tác thành công và có thể ném exception khi bulk request thất bại ở cấp request. Tùy phiên bản, một số item failure có thể được biểu diễn trong exception hoặc response object.

Không nên giả định mọi item lỗi đều xuất hiện dưới dạng một exception giống nhau. Hãy đọc kiểu trả về của method và tài liệu của phiên bản.

Một luồng xử lý nên:

1. Gửi batch.
2. Nhận kết quả hoặc exception.
3. Phân loại lỗi cấp request và lỗi cấp item.
4. Ghi lại ID, operation type, status và reason cho item lỗi.
5. Retry lỗi tạm thời theo backoff.
6. Đưa lỗi dữ liệu không thể retry vào error file hoặc dead-letter queue.
7. Cập nhật checkpoint sau khi xử lý xong batch theo chính sách.

Không ghi toàn bộ source nhạy cảm vào log khi lỗi. Nếu cần lưu payload để điều tra, phải áp dụng chính sách bảo vệ dữ liệu và thời hạn lưu.

## 26. Batch size theo số byte

Với dữ liệu có kích thước khác nhau, có thể xây dựng chunker theo byte:

    List<IndexQuery> currentBatch = new ArrayList<>();
    long currentBytes = 0;

    for (Product product : source) {
        IndexQuery query = toIndexQuery(product);
        long estimatedBytes = estimateBulkBytes(query);

        boolean countLimitReached =
            currentBatch.size() >= maxDocuments;
        boolean byteLimitReached =
            currentBytes + estimatedBytes > maxPayloadBytes;

        if (!currentBatch.isEmpty()
                && (countLimitReached || byteLimitReached)) {
            sendBulk(currentBatch);
            currentBatch.clear();
            currentBytes = 0;
        }

        currentBatch.add(query);
        currentBytes += estimatedBytes;
    }

    if (!currentBatch.isEmpty()) {
        sendBulk(currentBatch);
    }

Đây là mã minh họa. estimateBulkBytes cần tính cả metadata và source serialization theo định dạng bulk. Nếu dùng JSON serializer khác với serializer của Spring Data, số byte ước lượng có thể lệch. Một cách chính xác hơn là dùng cùng serializer hoặc đo payload thực tế trước khi gửi.

Với document cực lớn, cần xử lý riêng để một document đơn lẻ không vượt giới hạn request. Không thể chia source JSON của một document thành nhiều bulk item để vượt giới hạn mà vẫn giữ document nguyên vẹn.

## 27. Những lỗi thường gặp

### Nghĩ BulkOptions tự chia batch

BulkOptions cấu hình request, không phải chunker. Ứng dụng phải tự chia danh sách thành nhiều request nếu dữ liệu lớn.

### Chỉ giới hạn số document

Document có kích thước khác nhau. Theo dõi cả số thao tác và tổng byte payload.

### Đặt batch sát giới hạn request tối đa

Proxy, gateway hoặc Elasticsearch có thể từ chối request. Chừa khoảng dự phòng và benchmark với payload thực.

### Dùng IMMEDIATE cho mọi batch

Refresh liên tục có thể làm tăng segment và giảm throughput. Dùng NONE cho import lớn nếu không cần search visibility ngay.

### Cho rằng WAIT_UNTIL giống IMMEDIATE

WAIT_UNTIL đợi refresh kế tiếp làm dữ liệu visible; IMMEDIATE yêu cầu refresh ngay. Hai lựa chọn có hành vi và chi phí khác nhau.

### Chỉ kiểm tra HTTP status

Bulk có thể thành công ở cấp request nhưng có item thất bại. Kiểm tra errors và kết quả từng item.

### Retry toàn bộ batch khi chỉ một item lỗi

Có thể áp dụng lại các thao tác đã thành công. Phân loại lỗi và retry item thất bại khi có thể.

### Retry vô hạn lỗi mapping

Lỗi dữ liệu không tự hết khi thử lại. Đưa item vào error handling để sửa dữ liệu hoặc mapping.

### Tăng concurrency khi cluster đã reject

Nhiều worker hơn có thể làm overload nặng hơn. Dùng backpressure và giảm tốc khi nhận 429.

### Dùng một routing cho batch có nhiều tenant

Routing cấp request chỉ phù hợp khi các thao tác dùng chung routing. Với routing khác nhau, cấu hình theo từng item.

### Giả định saveAll có batch size cố định

Hành vi nội bộ phụ thuộc phiên bản. Nếu cần kiểm soát batch size, tự chunk và dùng bulk API phù hợp.

### Dùng code BulkOptions từ major version khác

Builder method và package thay đổi theo Spring Data/client version. Kiểm tra dependency thực tế trước khi áp dụng.

### Nhầm timeout request với thời gian hoàn tất toàn bộ job

Timeout của Bulk API, HTTP client và job là các lớp khác nhau. Thiết kế deadline, retry và đối soát trạng thái riêng.

## 28. Quy trình thiết kế bulk import

Một quy trình thực tế có thể đi theo thứ tự:

1. Xác định thao tác cần thực hiện: index, create, update hay delete.
2. Kiểm tra mapping và ingest pipeline trước khi import dữ liệu lớn.
3. Chọn ID ổn định và routing đúng cho từng document.
4. Chọn batch size khởi đầu dựa trên số document và tổng byte.
5. Chọn số worker thấp rồi tăng dần qua benchmark.
6. Dùng BulkOptions để đặt refresh, timeout, active shards và pipeline phù hợp.
7. Gửi từng batch qua ElasticsearchOperations hoặc API tương ứng.
8. Kiểm tra kết quả từng item và phân loại lỗi.
9. Retry lỗi tạm thời bằng backoff có giới hạn.
10. Ghi dead-letter/error report cho lỗi dữ liệu hoặc cấu hình.
11. Theo dõi throughput, latency, 429, heap, disk và indexing pressure.
12. Điều chỉnh batch size/concurrency dựa trên số liệu.
13. Refresh một lần sau import nếu yêu cầu visibility ngay.
14. Chỉ đánh dấu job hoàn tất khi mọi item đã được xử lý theo chính sách.

## Kết luận

BulkOptions cấu hình một số thuộc tính của bulk request như refresh policy, timeout, waitForActiveShards, pipeline hoặc routing tùy phiên bản. Kích thước lô là quyết định riêng của ứng dụng: cần chia dữ liệu thành nhiều request và kiểm soát cả số thao tác lẫn tổng byte payload. Bulk API không phải transaction; một request có thể có item thành công và item thất bại, vì vậy phải đọc kết quả từng item, phân loại lỗi và retry có giới hạn.

Trong Spring Data Elasticsearch, ElasticsearchOperations cung cấp các bulk method để gửi IndexQuery, UpdateQuery hoặc thao tác xóa cùng BulkOptions. Repository saveAll tiện cho use case đơn giản, nhưng không nên giả định nó cho phép kiểm soát mọi request option hoặc batch size. Hãy kiểm tra đúng phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client đang được resolve, vì package, builder method và kiểu option có thể thay đổi giữa các major version. Benchmark theo payload, số shard, concurrency và workload thực tế; chọn refresh và backpressure phù hợp để đạt throughput tốt mà không gây áp lực quá mức lên cluster.
