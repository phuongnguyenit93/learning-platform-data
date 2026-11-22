# saveAll và giới hạn bảo đảm thành công toàn bộ

Trong Spring Data Elasticsearch, saveAll là cách thuận tiện để lưu nhiều entity thông qua repository. Tuy nhiên, tên phương thức không có nghĩa toàn bộ danh sách được lưu trong một transaction nguyên tử. Elasticsearch không cung cấp transaction nhiều document theo kiểu cơ sở dữ liệu quan hệ; một lần bulk request có thể lưu thành công một số document và thất bại ở những document khác.

Khi dùng saveAll, cần phân biệt ba điều:

- **API ở tầng repository:** nhận một tập entity và yêu cầu lưu chúng.
- **Cách thực thi ở tầng client:** tùy phiên bản và implementation, framework có thể gửi bulk request hoặc thực hiện các thao tác ghi theo cơ chế khác.
- **Kết quả ở phía Elasticsearch:** từng thao tác document có thể thành công hoặc thất bại độc lập. Bulk API không rollback những item đã thành công khi một item khác lỗi.

Vì vậy, saveAll hữu ích để giảm mã lặp và có thể tận dụng bulk indexing, nhưng không phải cam kết all-or-nothing. Nếu nghiệp vụ cần biết chính xác document nào đã được lưu, cần thiết kế cách nhận diện kết quả từng item, xử lý lỗi và retry an toàn.

## 1. saveAll dùng để làm gì?

Với repository đồng bộ, có thể lưu nhiều entity bằng một lời gọi:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {
    }

Service:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public Iterable<Product> saveProducts(
                List<Product> products) {
            return repository.saveAll(products);
        }
    }

saveAll nhận một Iterable entity và trả về các entity đã được lưu theo contract của repository. Mã nghiệp vụ không phải tự gọi save trong vòng lặp.

Nếu ứng dụng lưu danh sách:

    List<Product> products = List.of(
        new Product("p-101", "Keyboard", 45.0),
        new Product("p-102", "Mouse", 20.0),
        new Product("p-103", "Monitor", 220.0)
    );

    Iterable<Product> saved = productRepository.saveAll(products);

thì ứng dụng yêu cầu Spring Data lưu ba document. Cách framework thực hiện phía dưới phụ thuộc phiên bản Spring Data Elasticsearch và implementation được sử dụng.

Trong các implementation hỗ trợ bulk, nhiều thao tác được gom vào một request để giảm số lần round trip giữa ứng dụng và Elasticsearch. Điều này thường có lợi cho throughput khi index nhiều document. Nhưng việc gom request không biến các thao tác thành một transaction.

## 2. Bulk API hoạt động theo từng item

Elasticsearch Bulk API nhận nhiều action trong một HTTP request. Mỗi action mô tả một thao tác trên document, ví dụ index, create, update hoặc delete.

Ví dụ bulk request:

    POST _bulk
    { "index": { "_index": "products", "_id": "p-101" } }
    { "name": "Keyboard", "price": 45.0 }
    { "index": { "_index": "products", "_id": "p-102" } }
    { "name": "Mouse", "price": 20.0 }
    { "index": { "_index": "products", "_id": "p-103" } }
    { "name": "Monitor", "price": 220.0 }

Elasticsearch xử lý từng action và trả về một kết quả cho mỗi item. Một response có thể có cấu trúc như:

    {
      "took": 18,
      "errors": true,
      "items": [
        {
          "index": {
            "_index": "products",
            "_id": "p-101",
            "status": 201,
            "result": "created"
          }
        },
        {
          "index": {
            "_index": "products",
            "_id": "p-102",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field [price]"
            }
          }
        },
        {
          "index": {
            "_index": "products",
            "_id": "p-103",
            "status": 201,
            "result": "created"
          }
        }
      ]
    }

Trong ví dụ:

- p-101 được tạo thành công.
- p-102 thất bại do lỗi parse/mapping.
- p-103 vẫn có thể được tạo thành công.

Response cấp HTTP của Bulk API có thể là HTTP 200 trong khi trường errors là true. HTTP 200 ở đây cho biết request bulk đã được xử lý ở cấp giao thức; nó không chứng minh mọi item đều thành công.

Điểm cần nhớ là mỗi item có status và có thể có error riêng. Bulk API không tự hủy p-101 và p-103 chỉ vì p-102 thất bại.

## 3. Vì sao saveAll không có bảo đảm all-or-nothing?

Một transaction all-or-nothing có hai trạng thái tổng quát:

- Tất cả thao tác thành công và được commit.
- Có ít nhất một thao tác thất bại, toàn bộ thay đổi được rollback.

Bulk API không hoạt động theo mô hình đó. Mỗi thao tác document được Elasticsearch xử lý độc lập. Nếu một item thất bại vì mapping, version conflict hoặc lỗi dữ liệu, các item khác vẫn có thể hoàn tất.

Ngay cả khi Spring Data gửi bulk request trong một HTTP call, một HTTP call không đồng nghĩa với một transaction. Request chỉ là cách vận chuyển nhiều action; tính nguyên tử vẫn được xác định bởi semantics của từng action ở server.

Có thể hình dung:

    saveAll([A, B, C, D])
              |
              v
        Bulk request
              |
       +------+------+
       |      |      |
       v      v      v
       A      B      C      D
       |      |      |      |
       OK    ERROR   OK     OK
       |      |      |      |
       +------+------+
              |
              v
    A, C, D đã được lưu
    B cần được xử lý riêng

Không có bước rollback tự động cho A, C và D.

### Nếu saveAll ném exception thì sao?

Spring Data Elasticsearch có thể phát hiện lỗi trong quá trình ghi và ném exception tùy implementation, phiên bản và abstraction được gọi. Một số tầng API có thể cung cấp thông tin bulk response hoặc danh sách item thất bại; tầng repository có thể bọc lỗi thành exception.

Khi gặp exception, không nên kết luận rằng không có document nào được lưu. Một phần danh sách có thể đã thành công trước khi lỗi được báo về ứng dụng. Cần kiểm tra thông tin lỗi ở mức item hoặc đối chiếu trạng thái document bằng id.

Ngược lại, nếu saveAll trả về bình thường, đó là tín hiệu thao tác theo contract của implementation đã hoàn tất mà không báo lỗi. Nhưng điều đó vẫn không tạo ra cam kết transaction để rollback các thao tác khác nếu một lỗi được phát hiện ở tầng ngoài.

## 4. Phân biệt contract của repository và semantics của Elasticsearch

CrudRepository.saveAll cung cấp API lưu nhiều entity trong hệ sinh thái Spring Data. Contract này giúp ứng dụng dùng cách gọi nhất quán giữa các loại repository.

Tuy nhiên, contract repository không thay đổi đặc tính của database phía dưới:

| Tầng | Điều được cung cấp | Điều không được suy ra |
|---|---|---|
| Repository saveAll | Một lời gọi lưu nhiều entity | Không tự đảm bảo transaction nhiều document |
| Spring Data implementation | Cách chuyển entity thành thao tác ghi | Không đảm bảo mọi phiên bản dùng cùng một cơ chế bulk |
| Elasticsearch Bulk API | Gom nhiều action vào một request | Không rollback các item thành công |
| Elasticsearch document operation | Kết quả riêng cho từng document | Không có transaction ACID bao trùm toàn bộ bulk |

Vì vậy, khi nâng cấp Spring Data Elasticsearch, cần kiểm tra implementation và tài liệu đúng phiên bản nếu hiệu năng, exception hoặc thông tin item-level là yêu cầu quan trọng. Không nên dựa vào giả định rằng mọi phiên bản saveAll đều tạo cùng loại bulk request hoặc trả cùng cấu trúc lỗi.

## 5. saveAll thường dùng index semantics

Trong Spring Data Elasticsearch, save và saveAll thường phù hợp với hành vi lưu entity theo id. Với thao tác index thông thường:

- Nếu document chưa tồn tại, Elasticsearch tạo document.
- Nếu document cùng id đã tồn tại, nội dung document có thể được thay thế bằng nội dung mới theo semantics của index operation.

Ví dụ:

    Product updated = new Product("p-101", "Keyboard Pro", 59.0);
    productRepository.save(updated);

Nếu p-101 đã tồn tại, thao tác lưu theo index semantics có thể ghi nội dung mới cho document đó. Đây là hành vi phù hợp với mô hình lưu trạng thái hiện tại, nhưng cần được hiểu rõ khi retry.

Nếu nghiệp vụ cần chỉ tạo mới và từ chối khi id đã tồn tại, cần dùng create semantics thay vì giả định saveAll sẽ hoạt động như một lệnh insert-only. Bulk action create thất bại với conflict nếu document id đã tồn tại.

Điều này quan trọng với event hoặc dữ liệu append-only: retry một thao tác create sau khi lần đầu đã thành công có thể trả về conflict, trong khi retry index với id ổn định có thể ghi lại cùng document. Hai lựa chọn có hành vi khác nhau.

## 6. Xử lý kết quả từng item

Khi ứng dụng cần kiểm soát thành công/thất bại theo document, cần có một định danh ổn định để liên kết item trong response với bản ghi nguồn.

Ví dụ một lô nhập dữ liệu:

| ID | Sản phẩm | Kết quả |
|---|---|---|
| p-101 | Keyboard | Thành công |
| p-102 | Mouse | Thất bại do mapping |
| p-103 | Monitor | Thành công |

Ứng dụng nên ghi nhận:

- ID document.
- Loại thao tác.
- Trạng thái HTTP/item.
- Loại lỗi và thông tin lỗi.
- Số lần retry.
- Thời điểm xử lý.

Nếu sử dụng Elasticsearch Java Client trực tiếp, BulkResponse cung cấp thông tin như errors() và danh sách items(). Mỗi item response có status, id và error nếu thao tác thất bại.

Ví dụ khái quát:

    BulkResponse response = client.bulk(request);

    if (response.errors()) {
        for (BulkResponseItem item : response.items()) {
            if (item.error() != null) {
                // Record item.id(), item.status(), item.error()
            }
        }
    }

Tên class và getter có thể thay đổi theo phiên bản Java API Client; cần dùng API tương ứng dependency của dự án. Ý tưởng không thay đổi: đọc trạng thái từng item thay vì chỉ kiểm tra HTTP status của toàn request.

Nếu dùng repository saveAll, abstraction có thể không trả đầy đủ item-level response theo cách ứng dụng cần. Khi đó, có thể:

1. Kiểm tra exception cụ thể của phiên bản Spring Data Elasticsearch.
2. Sử dụng ElasticsearchOperations hoặc bulk API có kết quả chi tiết hơn.
3. Gọi Elasticsearch Java Client trực tiếp cho luồng import cần kiểm soát từng item.
4. Ghi lại id nguồn để có thể đối chiếu và xử lý lại các item thất bại.

Không nên chọn abstraction chỉ vì mã ngắn hơn nếu nghiệp vụ cần biết chính xác từng item đã thành công hay chưa.

## 7. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng nên retry. Cần phân biệt lỗi dữ liệu/cấu hình với lỗi tạm thời.

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Lỗi mapping hoặc parse | mapper_parsing_exception, giá trị sai kiểu | Sửa dữ liệu hoặc mapping rồi mới gửi lại |
| Thiếu quyền | HTTP 401/403 | Sửa authentication/authorization; không retry liên tục |
| Index/resource không tồn tại | HTTP 404 hoặc lỗi index | Kiểm tra provisioning và tên index |
| Version conflict | HTTP 409 | Xử lý theo nghiệp vụ, kiểm tra id/version |
| Quá tải tạm thời | HTTP 429, rejected execution | Retry có backoff và giới hạn concurrency |
| Lỗi dịch vụ tạm thời | Một số lỗi 502/503/504 | Retry có giới hạn nếu thao tác an toàn |
| Timeout/mất kết nối | Không nhận được response | Trạng thái có thể chưa rõ; phải đối chiếu hoặc dùng idempotency |

Lỗi mapping thường sẽ tiếp tục xảy ra nếu gửi lại cùng document mà không sửa dữ liệu hoặc mapping. Retry liên tục chỉ làm tăng tải và tạo thêm log lỗi.

Với lỗi quá tải như 429, có thể dùng exponential backoff kèm jitter:

    delay = min(maxDelay, baseDelay * 2^attempt) + jitter

Ví dụ:

- Lần đầu chờ khoảng 200 ms.
- Lần hai chờ khoảng 400 ms.
- Lần ba chờ khoảng 800 ms.
- Dừng sau số lần thử tối đa hoặc khi hết thời gian cho phép.

Giá trị cụ thể cần dựa trên latency và khả năng của cluster. Không nên cho tất cả worker retry cùng một thời điểm, vì điều đó có thể tạo thêm đợt tải đột biến.

## 8. Retry an toàn và tính idempotent

Một thao tác idempotent có nghĩa việc thực hiện lại cùng một yêu cầu không làm thay đổi kết quả cuối cùng ngoài lần thực hiện đầu tiên, theo định nghĩa nghiệp vụ của ứng dụng.

### Dùng id ổn định với index operation

Nếu ứng dụng dùng id ổn định và gửi cùng nội dung bằng index operation, việc retry thường đưa document về cùng trạng thái cuối. Tuy nhiên, nếu một luồng khác đã cập nhật document giữa hai lần gửi, retry có thể ghi đè dữ liệu mới hơn.

Do đó, id ổn định giúp giảm nguy cơ tạo duplicate nhưng không tự giải quyết xung đột cập nhật đồng thời. Nếu cần bảo vệ phiên bản, hãy dùng cơ chế optimistic concurrency/versioning phù hợp.

### Dùng create operation

Với create operation, nếu lần đầu đã thành công nhưng response bị mất, retry cùng id sẽ có thể nhận conflict vì document đã tồn tại. Ứng dụng cần phân biệt conflict do lần ghi trước đã thành công với conflict do một document khác đã sử dụng id đó.

### Dùng id tự sinh

Nếu mỗi lần retry tạo một id mới, cùng một payload có thể tạo thành nhiều document. Đây là nguy cơ phổ biến khi producer gửi event và timeout khiến không biết request trước đã được server ghi hay chưa.

Với event ingestion, có thể dùng event id ổn định từ hệ thống nguồn hoặc một khóa idempotency để chống duplicate. Nếu không thể đảm bảo duy nhất, cần chấp nhận duplicate và xử lý ở tầng downstream.

## 9. Timeout không chứng minh request thất bại

Một tình huống dễ gây lỗi là:

1. Ứng dụng gửi bulk request.
2. Elasticsearch nhận request và lưu một số hoặc toàn bộ item.
3. Kết nối bị ngắt trước khi ứng dụng nhận response.
4. Ứng dụng thấy timeout và cho rằng tất cả item thất bại.
5. Ứng dụng gửi lại toàn bộ batch.

Trạng thái thực tế sau bước 3 là không chắc chắn. Có thể không item nào được lưu, một phần đã lưu, hoặc tất cả đã lưu. Timeout chỉ nói rằng ứng dụng không nhận được kết quả đúng hạn; nó không chứng minh server chưa thực hiện thao tác.

Để xử lý:

- Dùng id ổn định cho document.
- Theo dõi batch id và item id.
- Khi có thể, đối chiếu trạng thái document trước khi gửi lại.
- Chỉ retry phần chưa xác nhận hoặc dùng operation có semantics idempotent phù hợp.
- Lưu checkpoint để tiến trình import có thể tiếp tục sau khi ứng dụng khởi động lại.

Không nên retry mù quáng toàn bộ batch với id tự sinh nếu duplicate là vấn đề nghiệp vụ.

## 10. Chia batch thay vì gửi toàn bộ dữ liệu trong một lần

saveAll nhận một Iterable, nhưng điều đó không có nghĩa nên truyền một danh sách hàng triệu entity vào một lời gọi duy nhất.

Batch quá lớn có thể:

- Tạo request body lớn và tốn bộ nhớ ở ứng dụng.
- Làm tăng thời gian xử lý và độ trễ của một request.
- Tăng lượng dữ liệu cần retry khi một phần thất bại.
- Gây áp lực lên thread pool, network và heap của Elasticsearch.
- Tạo đợt indexing lớn ảnh hưởng search workload.

Nên chia dữ liệu thành các batch có kích thước phù hợp:

    int batchSize = 500;

    for (int from = 0; from < products.size(); from += batchSize) {
        int to = Math.min(from + batchSize, products.size());
        List<Product> batch = products.subList(from, to);

        productRepository.saveAll(batch);
    }

500 chỉ là ví dụ để minh họa, không phải con số tối ưu cho mọi hệ thống. Kích thước batch nên được đo theo byte của request, kích thước document, latency, throughput và tài nguyên cluster. Với document lớn, batch ít item hơn có thể phù hợp; với document nhỏ, batch lớn hơn có thể hiệu quả.

Nếu xử lý bất đồng bộ hoặc nhiều batch song song, cần giới hạn concurrency. Gửi quá nhiều bulk request cùng lúc có thể khiến Elasticsearch trả 429 và làm throughput tổng thể giảm.

### Theo dõi tiến độ theo batch

Một quy trình import đáng tin cậy nên lưu trạng thái:

| Batch | Trạng thái | Ghi chú |
|---|---|---|
| 1 | Hoàn tất | Tất cả item được xác nhận |
| 2 | Một phần thất bại | Lưu danh sách id lỗi để xử lý lại |
| 3 | Chưa chạy | Chờ worker tiếp tục |

Checkpoint cần được lưu ở nơi bền vững nếu import phải tiếp tục sau restart. Không nên chỉ giữ danh sách lỗi trong bộ nhớ của process.

## 11. Ví dụ xử lý batch có ghi nhận lỗi

Với repository đơn giản, có thể bắt exception ở từng batch:

    for (List<Product> batch : batches) {
        try {
            productRepository.saveAll(batch);
            markBatchCompleted(batch);
        } catch (RuntimeException ex) {
            markBatchFailed(batch, ex);
            // Inspect the exception before deciding what to retry.
        }
    }

Đoạn mã này chỉ đánh dấu batch thành công khi lời gọi trả về bình thường. Nếu exception xảy ra, không nên đánh dấu toàn bộ batch là chưa được ghi; cần đối chiếu kết quả thực tế hoặc lấy item-level error từ tầng bulk.

Nếu cần xử lý từng item chính xác, có thể sử dụng Bulk API trực tiếp:

    BulkResponse response = client.bulk(request);

    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            markDocumentIndexed(item.id());
        } else {
            recordFailure(
                item.id(),
                item.status(),
                item.error().reason()
            );
        }
    }

Đây là mã minh họa về cách đọc kết quả. Tên kiểu dữ liệu và phương thức cần đối chiếu với phiên bản Elasticsearch Java Client trong dự án.

Sau khi phân loại:

- Item thành công được ghi nhận hoàn tất.
- Item lỗi dữ liệu được đưa vào dead-letter hoặc danh sách cần sửa.
- Item lỗi tạm thời được đưa vào retry queue.
- Item có kết quả không chắc chắn do timeout được đối chiếu bằng id trước khi gửi lại.

## 12. saveAll và transaction của Spring

Một số ứng dụng dùng @Transactional ở service và kỳ vọng các lệnh saveAll sẽ rollback toàn bộ khi có lỗi:

    @Transactional
    public void importProducts(List<Product> products) {
        productRepository.saveAll(products);
        // More database operations
    }

Không nên suy luận rằng annotation này làm cho nhiều document trong Elasticsearch trở thành một transaction nguyên tử. Elasticsearch không cung cấp transaction ACID nhiều document tương đương transaction của relational database.

Nếu ứng dụng có transaction manager cho một cơ sở dữ liệu khác, transaction đó cũng không tự động bao gồm thao tác ghi Elasticsearch. Khi database commit nhưng Elasticsearch thất bại, hai hệ thống có thể lệch trạng thái.

Nếu nghiệp vụ yêu cầu cập nhật dữ liệu quan trọng trong database và đồng bộ sang Elasticsearch, có thể dùng Transactional Outbox:

1. Trong transaction của database, cập nhật dữ liệu nghiệp vụ và ghi một outbox event.
2. Sau khi commit, một worker đọc outbox.
3. Worker index document vào Elasticsearch.
4. Khi Elasticsearch xác nhận, worker đánh dấu event đã xử lý.
5. Nếu lỗi tạm thời, worker retry theo chính sách; nếu lỗi dữ liệu, đưa vào trạng thái cần xử lý.

Luồng này tạo khả năng phục hồi và eventual consistency. Nó không biến database và Elasticsearch thành một distributed transaction, nhưng giúp không mất sự kiện đồng bộ khi process dừng giữa chừng.

## 13. Nếu nghiệp vụ thực sự cần all-or-nothing thì làm thế nào?

Trước tiên, cần xác định all-or-nothing áp dụng cho dữ liệu nào và trong ranh giới nào.

### Dữ liệu nguồn có tính giao dịch

Nếu một nhóm thay đổi phải cùng thành công hoặc cùng thất bại, hãy giữ nguồn dữ liệu có tính giao dịch trong cơ sở dữ liệu hỗ trợ transaction. Elasticsearch nên được xem là read model/search projection được đồng bộ từ nguồn.

Ví dụ:

    Database transaction
       |
       +-- Update product A
       +-- Update product B
       +-- Insert outbox event
                 |
                 v
             Commit
                 |
                 v
          Outbox processor
                 |
                 v
          Elasticsearch bulk
                 |
        +--------+--------+
        |                 |
        v                 v
     Success            Partial failure
        |                 |
        v                 v
     Mark done        Retry / dead letter

Database bảo đảm transaction cho dữ liệu nghiệp vụ. Elasticsearch được cập nhật bất đồng bộ và có thể có độ trễ trong một khoảng thời gian.

### Cần thay thế toàn bộ một tập dữ liệu tìm kiếm

Nếu yêu cầu là chỉ công bố một phiên bản index khi tất cả document đã được nạp và xác minh, có thể dùng versioned index:

1. Tạo index mới, ví dụ products_import_2026_11.
2. Nạp dữ liệu vào index mới theo batch.
3. Thu thập và xử lý mọi item failure.
4. Kiểm tra số document, mapping và truy vấn quan trọng.
5. Chỉ khi toàn bộ dữ liệu đạt yêu cầu mới chuyển alias read/write sang index mới.
6. Nếu nạp thất bại, giữ alias trỏ đến index cũ và sửa hoặc xóa index staging theo quy trình.

Cách này tạo hành vi publish/rollback ở cấp alias. Nó không làm từng bulk request nguyên tử, nhưng người dùng có thể tiếp tục đọc phiên bản cũ cho đến khi index mới hoàn chỉnh.

### Dùng thao tác bù trừ

Một số nghiệp vụ có thể ghi nhận những document đã thành công rồi thực hiện thao tác bù trừ nếu có item thất bại. Đây là mô hình compensation/Saga, không phải rollback transaction của Elasticsearch.

Thao tác bù trừ cũng có thể thất bại và cần retry. Vì vậy, phải thiết kế trạng thái và nhật ký đủ rõ để biết document nào đã được ghi, đã được bù trừ hay còn đang chờ xử lý.

## 14. Những lỗi thường gặp

### Nghĩ rằng saveAll là một transaction

saveAll là API lưu nhiều entity. Bulk request có thể có item thành công và item thất bại; Elasticsearch không rollback các item thành công. Hãy xử lý kết quả theo từng document khi nghiệp vụ yêu cầu.

### Chỉ kiểm tra HTTP 200 của Bulk API

Bulk API có thể trả HTTP 200 nhưng errors là true. Cần đọc kết quả từng item và không đánh dấu cả batch thành công chỉ dựa trên HTTP status.

### Khi exception xảy ra, giả định chưa có dữ liệu nào được ghi

Một phần item có thể đã thành công trước khi lỗi được báo. Hãy đối chiếu item response hoặc kiểm tra theo id trước khi chạy lại toàn bộ batch.

### Retry mọi lỗi

Lỗi mapping, authentication hoặc quyền truy cập thường không tự biến mất khi retry. Phân loại lỗi và chỉ retry lỗi tạm thời.

### Dùng id tự sinh rồi retry toàn batch

Request lần đầu có thể đã ghi một phần dữ liệu. Retry với id mới có thể tạo duplicate. Dùng id ổn định hoặc cơ chế chống duplicate.

### Gửi một batch quá lớn

Batch lớn làm tăng bộ nhớ, latency và lượng dữ liệu cần retry. Chia batch, đo request size và giới hạn concurrency.

### Dùng @Transactional để kỳ vọng rollback Elasticsearch

Spring transaction không tự tạo transaction nhiều document trên Elasticsearch. Nếu cần tính nhất quán giữa database và Elasticsearch, dùng outbox hoặc mô hình đồng bộ có khả năng phục hồi.

### Không lưu checkpoint import

Khi process dừng giữa chừng, ứng dụng không biết batch nào đã hoàn tất và item nào cần retry. Hãy lưu tiến độ và lỗi ở nơi bền vững.

## Kết luận

saveAll giúp lưu nhiều entity qua repository và có thể tận dụng bulk indexing tùy implementation của Spring Data Elasticsearch. Tuy nhiên, một lời gọi lưu nhiều entity không đồng nghĩa với transaction all-or-nothing. Bulk API xử lý từng item độc lập; một số document có thể thành công trong khi document khác thất bại, và HTTP 200 vẫn có thể đi kèm errors: true.

Khi xây dựng luồng import, hãy dùng id ổn định, chia batch, đọc kết quả item-level, phân loại lỗi và retry có kiểm soát. Timeout cần được xem là trạng thái chưa chắc chắn cho đến khi đối chiếu được kết quả. Nếu nghiệp vụ thực sự cần công bố toàn bộ dữ liệu cùng lúc, hãy nạp vào index phiên bản mới rồi chuyển alias sau khi xác minh; nếu cần transaction cho dữ liệu nguồn, giữ transaction ở cơ sở dữ liệu phù hợp và đồng bộ sang Elasticsearch qua outbox. Cách tiếp cận này phản ánh đúng giới hạn của saveAll và giúp hệ thống phục hồi an toàn khi chỉ một phần dữ liệu được ghi thành công.
