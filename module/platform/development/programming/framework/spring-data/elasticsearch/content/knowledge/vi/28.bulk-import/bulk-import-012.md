# Kiểm tra đủ dữ liệu, đối soát lỗi và tiếp tục sau gián đoạn

Một tiến trình nhập dữ liệu vào Elasticsearch thường đọc dữ liệu từ file, database, message queue hoặc một hệ thống nguồn rồi gửi nhiều document bằng Bulk API. Một bulk request có thể chứa nhiều thao tác, nhưng Elasticsearch không xử lý toàn bộ request như một transaction. Một số document có thể được ghi thành công trong khi những document khác thất bại.

Vì vậy, nhập liệu đáng tin cậy cần ba khả năng: **đếm và đối soát dữ liệu**, **phân loại và xử lý lỗi theo từng item**, và **tiếp tục từ checkpoint sau khi tiến trình bị dừng**. Nếu chỉ kiểm tra HTTP status của bulk request hoặc ghi nhớ rằng batch đã gửi, ứng dụng có thể bỏ sót lỗi, nhập trùng dữ liệu hoặc không biết cần chạy lại phần nào.

Bài học này trình bày cách tổ chức một pipeline bulk trong Spring Data Elasticsearch: xác định số lượng đầu vào, kiểm tra kết quả từng document, lưu trạng thái batch, retry lỗi tạm thời, đưa lỗi không thể tự phục hồi vào danh sách xử lý riêng và tiếp tục an toàn sau timeout hoặc restart.

## 1. Bulk request không phải transaction

Bulk API gom nhiều thao tác index, create, update hoặc delete vào một request để giảm overhead mạng và tăng thông lượng. Elasticsearch thực hiện từng thao tác độc lập trong bulk.

Ví dụ một batch có 100 document:

- 92 document được index thành công.
- 5 document lỗi mapping hoặc dữ liệu.
- 2 document gặp version conflict.
- 1 document bị từ chối tạm thời do tải cluster.

Bulk request có thể trả về response tổng thể thành công ở tầng HTTP nhưng vẫn có item thất bại. Response chứa thông tin cho từng thao tác và một cờ tổng hợp cho biết có lỗi hay không.

Điều này dẫn tới hai nguyên tắc:

1. Không coi một bulk request thành công ở tầng HTTP là bằng chứng mọi document đã được ghi.
2. Không gửi lại toàn bộ batch chỉ vì một item thất bại nếu các item khác đã thành công và thao tác không idempotent.

Một bulk request không có rollback toàn bộ. Ứng dụng phải đối soát và xử lý từng item.

## 2. Xác định thế nào là dữ liệu đầy đủ

Trước khi chạy import, cần định nghĩa chính xác tập dữ liệu dự kiến. Không phải lúc nào số dòng trong file cũng bằng số document cần index.

Ví dụ một file có 10.000 dòng:

- 9.850 dòng hợp lệ và được đưa vào index.
- 100 dòng bị loại theo quy tắc nghiệp vụ.
- 30 dòng trùng source key và được gộp.
- 20 dòng thiếu field bắt buộc, cần báo lỗi.

Nếu chỉ so sánh số document index thành công với 10.000, báo cáo sẽ không thể giải thích chênh lệch.

Một mô hình đối soát nên phân biệt các con số:

| Chỉ số | Ý nghĩa |
|---|---|
| sourceRead | Số bản ghi đã đọc từ nguồn |
| accepted | Số bản ghi vượt qua validation và được nhận xử lý |
| rejected | Số bản ghi bị loại do validation hoặc quy tắc nghiệp vụ |
| duplicate | Số bản ghi trùng theo khóa nghiệp vụ |
| attempted | Số thao tác thực sự gửi đến Elasticsearch |
| succeeded | Số thao tác được Elasticsearch xác nhận thành công |
| noop | Số thao tác không làm thay đổi document, nếu operation có semantics này |
| failed | Số thao tác thất bại |
| retryPending | Số thao tác còn chờ retry |
| deadLetter | Số thao tác đã hết retry hoặc cần xử lý thủ công |

Các nhóm này phải có định nghĩa không chồng lấn hoặc có quy tắc cộng rõ ràng. Ví dụ rejected có thể là một tập con của sourceRead, còn succeeded + failed + retryPending nên đối soát với attempted sau khi đã xử lý response của batch.

### Định nghĩa khóa đối soát

Mỗi bản ghi nguồn nên có một định danh ổn định, chẳng hạn source ID, business key hoặc event ID. Không dùng vị trí trong một danh sách đã sắp xếp lại làm định danh lâu dài.

Một record ledger có thể chứa:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "sourceId": "ERP-P-100",
  "targetId": "P-100",
  "sourceVersion": 42,
  "status": "SUCCEEDED",
  "attempts": 1,
  "lastError": null
}
~~~

Ledger cho phép biết record nào đã được xử lý, record nào bị loại, record nào cần retry. Với nguồn lớn, ledger có thể nằm trong database hoặc message store phù hợp thay vì một file log cục bộ.

## 3. Chia dữ liệu thành batch có ranh giới rõ ràng

Không nên tạo một bulk request chứa toàn bộ dữ liệu import. Batch nhỏ hơn giúp giới hạn payload, memory, thời gian xử lý và phạm vi cần phục hồi khi có lỗi.

Một batch nên có:

- job ID hoặc run ID.
- batch ID duy nhất trong job.
- source range, offset, page token hoặc partition.
- danh sách source ID.
- số lượng bản ghi đầu vào, accepted và rejected.
- trạng thái gửi và trạng thái đối soát.
- thời điểm bắt đầu, kết thúc và attempt number.

Ví dụ manifest batch:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "batchId": "partition-02-offset-5000",
  "sourcePartition": "02",
  "startOffset": 5000,
  "endOffsetExclusive": 6000,
  "recordCount": 1000,
  "status": "PENDING"
}
~~~

Dùng batch theo số document là cách đơn giản, nhưng cần chú ý kích thước byte. Một document chứa nội dung lớn có thể làm request nặng dù số lượng document thấp.

Chọn batch size bằng đo đạc trên dữ liệu thực tế. Theo dõi payload bytes, thời gian bulk, heap, CPU, tỷ lệ lỗi và tải cluster. Không có một con số cố định phù hợp cho mọi mapping và workload.

## 4. Đọc kết quả từng item của Bulk API

Bulk response có trạng thái tổng thể và danh sách item theo thứ tự các thao tác trong request. Mỗi item cho biết operation type, ID, status, kết quả hoặc thông tin lỗi.

Ví dụ response rút gọn:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-101",
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
        "_id": "P-102",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    }
  ]
}
~~~

Ở ví dụ:

- P-100 được tạo thành công.
- P-101 thất bại do dữ liệu không phù hợp mapping.
- P-102 bị từ chối tạm thời do cluster đang quá tải.

Cờ errors cho biết có ít nhất một item lỗi. Nó không cho biết tất cả item đều lỗi hay toàn bộ request cần retry.

### Ghép response với input

Bulk API trả item theo thứ tự operation trong request. Khi tự xây bulk request, cần giữ một danh sách metadata song song với các thao tác để liên hệ response item với source record:

~~~java
record PendingItem(
    String sourceId,
    String targetId,
    int sourcePosition
) {}
~~~

Khi response trả về, đối chiếu từng item với metadata ở cùng vị trí. Không chỉ dựa vào message lỗi hoặc thứ tự log để suy ra source record.

Nếu một request trộn nhiều operation type, giữ rõ operation type trong metadata. Một item index, update, delete hoặc create có thể có semantics thành công khác nhau.

### Đừng chỉ đếm response items

Số item trong response cần khớp số thao tác đã gửi. Nếu không khớp, không nên tự đánh dấu batch hoàn tất. Ghi nhận lỗi protocol/response, giữ batch ở trạng thái cần đối soát và điều tra.

Một response hợp lệ có thể có item success và item failure. Hãy đếm theo từng trạng thái và lưu danh sách item lỗi.

## 5. Bulk bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp bulk operations qua ElasticsearchOperations. Với index operations, có thể tạo danh sách IndexQuery:

~~~java
List<IndexQuery> queries = products.stream()
    .map(product -> new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build())
    .toList();

List<IndexedObjectInformation> indexed =
    operations.bulkIndex(
        queries,
        IndexCoordinates.of("products")
    );
~~~

Đây là dạng sử dụng thường gặp trong Spring Data Elasticsearch. Overload, BulkOptions và kiểu kết quả có thể thay đổi theo release train đang dùng. Cần kiểm tra dependency và API cụ thể của dự án.

Spring Data giúp chuyển entity sang document theo mapping/converter đã cấu hình. Tuy nhiên, khi cần đối soát chi tiết từng item, phải hiểu cách phiên bản đang dùng biểu diễn kết quả lỗi. Một số API có thể ném exception chứa thông tin lỗi bulk thay vì trả danh sách item hoàn chỉnh.

### Khi cần response item-level rõ ràng

Elasticsearch Java API Client trả BulkResponse với danh sách item. Ví dụ minh họa:

~~~java
BulkResponse response = elasticsearchClient.bulk(bulk -> bulk
    .index("products")
    .operations(operation -> operation.index(index -> index
        .id("P-100")
        .document(product)
    ))
    .operations(operation -> operation.index(index -> index
        .id("P-101")
        .document(anotherProduct)
    ))
);

if (response.errors()) {
    for (int i = 0; i < response.items().size(); i++) {
        BulkResponseItem item = response.items().get(i);

        if (item.error() != null) {
            // Đối chiếu item với metadata input cùng vị trí.
        }
    }
}
~~~

Cú pháp builder và generic document mapping phụ thuộc phiên bản Elasticsearch Java API Client. Ví dụ nhấn mạnh cách đọc response: kiểm tra errors, duyệt từng item và liên hệ item với source record.

Nếu ứng dụng dùng Spring Data Operations cho phần lớn tác vụ, có thể giữ bulk ở Operations và tạo adapter để chuẩn hóa kết quả hoặc exception thành một cấu trúc nội bộ thống nhất.

### Chuẩn hóa kết quả bulk

Một cấu trúc kết quả nội bộ giúp phần orchestration không phụ thuộc vào API cụ thể:

~~~java
enum ItemOutcome {
    SUCCEEDED,
    NOOP,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE
}

record BulkItemOutcome(
    String sourceId,
    String targetId,
    ItemOutcome outcome,
    Integer status,
    String errorType,
    String errorReason
) {}
~~~

Adapter chuyển BulkResponse hoặc exception Spring Data sang danh sách BulkItemOutcome. Service phía trên chỉ cần xử lý các trạng thái đã chuẩn hóa.

## 6. Phân loại lỗi để quyết định retry

Không phải lỗi nào cũng được giải quyết bằng cách gửi lại cùng request. Phân loại lỗi trước khi retry:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Dữ liệu/mapping | 400, parse exception, field sai kiểu | Sửa dữ liệu hoặc mapping; không retry mù |
| Authentication/authorization | 401, 403 | Dừng job và sửa quyền/cấu hình |
| Index hoặc resource không tồn tại | 404, index chưa được tạo | Kiểm tra provisioning và target |
| Quá tải/tạm thời | 429, một số 502/503 | Retry có backoff |
| Timeout/mất kết nối | Không rõ request đã được áp dụng hay chưa | Đối soát hoặc replay idempotent |
| Version conflict | 409 | Đọc lại và xử lý theo chính sách concurrency |
| Payload quá lớn | Request bị từ chối do kích thước | Giảm batch hoặc document size |

Status code chỉ là một tín hiệu. Cần đọc error type, reason và operation semantics. Ví dụ 409 khi create có thể có nghĩa document ID đã tồn tại; đây có thể là lỗi duplicate theo nghiệp vụ hoặc kết quả chấp nhận được khi import idempotent.

### Retry có giới hạn và backoff

Với lỗi tạm thời, dùng exponential backoff có jitter:

~~~text
attempt 1: chờ khoảng 0.5 giây
attempt 2: chờ khoảng 1 giây
attempt 3: chờ khoảng 2 giây
attempt 4: chờ khoảng 4 giây
...
~~~

Các khoảng trên chỉ minh họa. Cần cấu hình base delay, maximum delay, số lần retry và tổng thời gian tối đa theo SLA. Jitter giúp nhiều worker không đồng loạt retry cùng thời điểm.

Không retry vô hạn. Khi hết số lần thử, chuyển record sang trạng thái dead-letter hoặc chờ xử lý thủ công, kèm thông tin nguồn và lỗi cuối.

### Retry theo item, không retry cả batch theo mặc định

Nếu một batch có 1.000 item và 990 thành công, chỉ 10 item lỗi tạm thời cần được đưa vào retry queue. Gửi lại cả 1.000 item vừa tốn tài nguyên vừa có thể lặp side effect nếu operation không idempotent.

Nếu hệ thống không thể xác định item nào đã thành công vì request timeout trước khi nhận response, cần áp dụng chiến lược replay an toàn và đối soát sau đó. Đây là trường hợp khác với response trả về rõ ràng từng item.

## 7. Idempotency khi chạy lại dữ liệu

Một import có thể bị chạy lại vì:

- Tiến trình crash sau khi Elasticsearch đã ghi nhưng trước khi checkpoint được lưu.
- Client timeout và không biết bulk đã hoàn thành hay chưa.
- Operator chạy lại job.
- Message queue giao lại message.
- Retry được thực hiện sau khi worker restart.

Để replay an toàn, cần định nghĩa cùng một source record chạy lại sẽ tạo ra kết quả như thế nào.

### Dùng ID đích ổn định

Nếu cùng một source record luôn ánh xạ tới cùng Elasticsearch document ID, thao tác index với cùng ID và cùng nội dung có thể được replay mà không tạo thêm document mới:

~~~java
IndexQuery query = new IndexQueryBuilder()
    .withId(sourceRecord.getBusinessId())
    .withObject(product)
    .build();
~~~

Nếu mỗi lần chạy tạo ID ngẫu nhiên, replay có thể tạo duplicate document.

### Phân biệt index, create và update

| Operation | Khi chạy lại | Rủi ro/ý nghĩa |
|---|---|---|
| index cùng ID | Ghi đè document bằng nội dung gửi | Thường phù hợp cho đồng bộ snapshot nếu payload xác định |
| create cùng ID | Lần sau có thể nhận conflict vì ID đã tồn tại | Có thể dùng để phát hiện duplicate |
| update gán giá trị | Có thể an toàn nếu gán cùng giá trị | Phụ thuộc script và payload |
| update increment | Mỗi lần chạy lại có thể cộng thêm lần nữa | Không idempotent nếu không có deduplication |
| scripted append | Có thể thêm trùng nếu script không kiểm tra | Cần kiểm tra uniqueness hoặc event ID |
| delete cùng ID | Xóa lần đầu; lần sau tùy semantics not-found | Cần quy định not-found là thành công hay lỗi |

Một script cộng counter không trở nên idempotent chỉ vì Elasticsearch thực hiện update atomically. Atomicity của một lần update và tính idempotent của nhiều lần gửi lại là hai khái niệm khác nhau.

### Versioning và thứ tự dữ liệu

Nếu nguồn có version tăng dần, có thể lưu source version vào document và từ chối dữ liệu cũ ghi đè dữ liệu mới. Elasticsearch hỗ trợ external versioning trong Index API; cách cấu hình cụ thể phụ thuộc API đang dùng.

Một lựa chọn khác là lưu sourceUpdatedAt hoặc sourceVersion trong document và dùng script kiểm tra version trước khi áp dụng. Nếu event đến không đúng thứ tự, chỉ nhận event mới hơn theo quy tắc đã định.

Không dùng timestamp của worker làm version nếu nguồn dữ liệu mới là nơi quyết định thứ tự nghiệp vụ.

## 8. Checkpoint là gì và nên lưu ở đâu?

Checkpoint ghi nhận tiến độ mà job có thể tiếp tục sau restart. Nó cần bền vững qua process restart và phải được cập nhật theo kết quả đã đối soát.

Ví dụ checkpoint:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "partition": "02",
  "lastCommittedOffset": 5999,
  "lastCommittedBatchId": "partition-02-offset-5000",
  "status": "RUNNING",
  "updatedAt": "2026-11-13T10:30:00Z"
}
~~~

Checkpoint có thể lưu trong:

- Database quan hệ nếu hệ thống đã có job table.
- Durable key-value store.
- Message broker offset nếu nguồn là Kafka hoặc hệ thống tương tự.
- Object storage/manifest bền vững cho import file theo partition.
- Một index quản lý job riêng nếu phù hợp, nhưng cần hiểu Elasticsearch không phải transactional coordinator cho cả nguồn và đích.

Không chỉ lưu checkpoint trong biến bộ nhớ hoặc file tạm trên máy worker nếu job phải phục hồi khi máy bị thay thế.

### Checkpoint phải thể hiện tiến độ đã xác nhận

Không ghi checkpoint “đã xử lý tới offset 10.000” ngay sau khi đọc xong dữ liệu. Chỉ commit tiến độ khi mọi record trong phạm vi đó đã có kết quả được ghi nhận bền vững:

- Thành công.
- Bị loại theo validation và có lý do.
- Đã được đưa vào durable retry/dead-letter store.
- Hoặc trạng thái xử lý khác được chính sách job chấp nhận.

Nếu record thất bại chưa được lưu ở nơi có thể tiếp tục xử lý, không được bỏ qua nó bằng cách đẩy checkpoint qua vị trí đó.

## 9. Thứ tự xử lý an toàn cho một batch

Một trình tự thường dùng:

~~~text
Đọc source range
      |
      v
Validate và chuẩn hóa
      |
      +----> Rejected records -> lưu lỗi validation
      |
      v
Tạo bulk operations và metadata
      |
      v
Gửi bulk request
      |
      v
Đọc kết quả từng item
      |
      +----> Success / Noop -> ghi trạng thái thành công
      |
      +----> Retryable -> lưu retry queue
      |
      +----> Permanent -> lưu dead-letter/error store
      |
      v
Đối soát số lượng và lưu batch result
      |
      v
Commit checkpoint
~~~

Trình tự này giúp tránh checkpoint trước khi đã biết kết quả của batch. Việc lưu kết quả item và checkpoint nên được thiết kế để không tạo khoảng trống khi process crash giữa hai thao tác.

### Vấn đề crash giữa Elasticsearch và checkpoint store

Elasticsearch và database lưu checkpoint thường không nằm trong cùng một transaction phân tán. Có thể xảy ra:

1. Elasticsearch ghi thành công.
2. Process crash trước khi checkpoint database được commit.
3. Khi restart, source range được đọc lại.

Đây là lý do idempotency quan trọng. Nếu replay với cùng ID và cùng payload là an toàn, job có thể gửi lại range chưa commit rồi xác nhận lại trạng thái.

Nếu thao tác không idempotent, cần một deduplication ledger hoặc event ID được lưu bền vững để biết event đã áp dụng hay chưa. Không có checkpoint đơn lẻ nào tự tạo ra exactly-once giữa hai hệ thống độc lập.

## 10. Tiếp tục sau gián đoạn theo source type

Cách resume phụ thuộc nguồn dữ liệu.

### File CSV hoặc JSONL

Có thể chia file thành các range theo byte offset hoặc record number. Tuy nhiên, byte offset chỉ an toàn khi parser có thể bắt đầu tại ranh giới record hợp lệ. Với CSV có quoted newline, không thể tùy tiện seek theo dòng vật lý.

Các lựa chọn:

- Tạo manifest chứa byte range/record range hợp lệ trước khi import.
- Chia file thành các part độc lập.
- Lưu số record đã đọc và parser state nếu format cho phép.
- Ghi source ID của record lỗi vào error file/queue.
- Khi resume, đọc từ checkpoint hoặc replay một partition an toàn.

Với file nén dạng stream, việc seek có thể không khả thi; có thể cần chia file trước hoặc chạy lại từ đầu với ID đích ổn định.

### Database

Dùng keyset pagination dựa trên khóa ổn định hoặc cặp khóa có thứ tự:

~~~sql
SELECT id, name, price, updated_at
FROM products
WHERE id > :lastId
ORDER BY id
LIMIT :batchSize;
~~~

Nếu nguồn có cập nhật trong lúc import, chỉ dùng lastId có thể không bắt được các thay đổi đến sau. Có thể cần snapshot, watermark theo updated_at kết hợp ID, change data capture hoặc một khoảng thời gian đối soát lại.

Tránh offset pagination sâu nếu bảng lớn và nguồn có thay đổi liên tục.

### Message queue

Với queue hỗ trợ partition offset, chỉ commit offset sau khi batch đã được xử lý và kết quả đã được ghi nhận bền vững. Nếu xử lý song song trong một partition, không commit vượt qua message có offset thấp hơn vẫn đang chờ kết quả.

Có thể dùng per-partition contiguous watermark: chỉ tiến watermark qua các offset liên tiếp đã hoàn tất. Các message hoàn tất ở offset cao hơn được ghi nhận riêng cho tới khi các offset trước đó hoàn tất.

### API phân trang

Nếu API nguồn trả continuation token, lưu token cùng query parameters và trạng thái job. Token có thể hết hạn hoặc phụ thuộc snapshot phía nguồn. Khi token không còn hợp lệ, cần chiến lược bắt đầu lại partition hoặc đối soát theo source ID.

Không tự tạo token từ số trang nếu API yêu cầu cursor opaque.

## 11. Checkpoint khi chạy song song

Nếu nhiều worker xử lý các batch độc lập, không nên dùng một biến lastOffset cập nhật theo thời điểm hoàn thành bất kỳ.

Ví dụ:

- Batch A xử lý offset 0–999, vẫn đang chạy.
- Batch B xử lý offset 1000–1999, đã hoàn thành.
- Batch C xử lý offset 2000–2999, đã hoàn thành.

Nếu checkpoint ghi 2999 khi A chưa xong, restart có thể bỏ qua 0–999.

Có hai cách phổ biến:

**Checkpoint theo batch:** mỗi batch có trạng thái riêng; resume bằng cách tìm các batch chưa terminal. Cách này dễ đối soát và phù hợp xử lý song song.

**Watermark liên tục:** lưu offset cao nhất mà tất cả offset trước nó đã hoàn tất. Khi A hoàn tất, watermark có thể nhảy từ -1 lên 2999 nếu B và C cũng đã hoàn tất.

Với queue partitioned, watermark cần được quản lý riêng cho từng partition. Không dùng một offset chung cho nhiều partition độc lập.

## 12. Lưu trạng thái job và batch

Một mô hình trạng thái đơn giản:

~~~text
PENDING
   |
   v
RUNNING
   |
   +----> SUCCEEDED
   |
   +----> COMPLETED_WITH_ERRORS
   |
   +----> RETRY_PENDING
   |
   +----> FAILED
   |
   +----> CANCELLED
~~~

Ý nghĩa cần được định nghĩa trong ứng dụng:

- **PENDING**: batch đã được lập kế hoạch, chưa gửi.
- **RUNNING**: đang đọc, validate hoặc gửi bulk.
- **SUCCEEDED**: mọi record đã có kết quả được chấp nhận và không còn lỗi cần xử lý.
- **COMPLETED_WITH_ERRORS**: batch đã kết thúc nhưng có record bị reject hoặc dead-letter theo chính sách.
- **RETRY_PENDING**: còn item lỗi tạm thời đang chờ thử lại.
- **FAILED**: job không thể tiếp tục do lỗi cấu hình/hạ tầng hoặc vượt chính sách retry.
- **CANCELLED**: operator đã dừng job theo cách có kiểm soát.

Không đánh dấu batch SUCCEEDED chỉ vì request đã gửi đi. Cần có kết quả bulk và đối soát.

### Tách trạng thái job và trạng thái item

Một job có thể đang RUNNING dù một số item đã vào dead-letter, miễn chính sách cho phép tiếp tục các batch khác. Tương tự, một batch có thể hoàn tất nhưng vẫn chứa record rejected đã được ghi nhận.

Trạng thái job là tổng hợp; trạng thái item là dữ liệu chi tiết để resume và báo cáo.

## 13. Lưu lỗi và dead-letter record

Mỗi lỗi nên chứa đủ dữ liệu để sửa hoặc retry:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "sourceId": "ERP-P-101",
  "targetId": "P-101",
  "batchId": "partition-02-offset-5000",
  "attempt": 3,
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "errorReason": "failed to parse field [price]",
  "payloadReference": "object://imports/job-123/records/ERP-P-101",
  "firstFailedAt": "2026-11-13T10:20:00Z",
  "lastFailedAt": "2026-11-13T10:25:00Z",
  "state": "DEAD_LETTER"
}
~~~

Có thể lưu payload đầy đủ hoặc tham chiếu tới nguồn lưu trữ an toàn. Tránh ghi thông tin nhạy cảm vào log hoặc dead-letter store nếu không cần thiết.

Một error record tốt cần:

- Source ID và target ID.
- Job/batch/partition.
- Operation type.
- Số lần thử.
- Status và error type.
- Reason đã chuẩn hóa.
- Payload hoặc payload reference.
- Thời gian lỗi đầu tiên và gần nhất.
- Trạng thái retry/dead-letter.
- Thông tin phiên bản nguồn nếu có.

Dead-letter queue không phải nơi để quên lỗi. Cần có quy trình xem, sửa dữ liệu, replay có kiểm soát và đóng lỗi.

## 14. Tiếp tục job sau khi worker restart

Khi khởi động lại, orchestration service nên:

1. Tìm job có trạng thái RUNNING hoặc RETRY_PENDING đã bị bỏ dở.
2. Đọc checkpoint và batch manifest bền vững.
3. Xác định batch đã được commit, batch đang dở và batch chưa chạy.
4. Tải retry items còn hạn.
5. Kiểm tra target index/alias và mapping.
6. Tiếp tục từ batch chưa hoàn tất hoặc replay range chưa commit theo chính sách idempotency.
7. Ghi lại kết quả và cập nhật checkpoint.
8. Hoàn tất job khi mọi record đã có trạng thái cuối theo quy tắc.

Không nên chỉ đọc trạng thái RUNNING rồi gửi lại toàn bộ job. Cần biết batch nào đã thành công, batch nào có item lỗi và batch nào chưa từng được gửi.

### Job lease và worker ownership

Nếu có nhiều instance có thể khởi động cùng một job, cần cơ chế lease/lock để chỉ một worker sở hữu một partition hoặc batch tại một thời điểm. Lease nên có thời hạn và được gia hạn khi worker còn hoạt động.

Khi worker chết, lease hết hạn để worker khác có thể tiếp quản. Nhưng lease không loại bỏ hoàn toàn khả năng worker cũ tiếp tục chạy sau pause dài. Kết hợp lease với idempotency, fencing token hoặc version của job state để ngăn worker cũ commit trạng thái lỗi thời.

## 15. Đối soát sau khi job hoàn tất

Một job chỉ được báo hoàn tất khi các số liệu có thể giải thích được.

Ví dụ báo cáo:

~~~json
{
  "jobId": "import-products-2026-11-13",
  "sourceRead": 10000,
  "accepted": 9850,
  "rejected": 100,
  "duplicate": 50,
  "attempted": 9850,
  "succeeded": 9820,
  "noop": 0,
  "deadLetter": 30,
  "retryPending": 0,
  "status": "COMPLETED_WITH_ERRORS"
}
~~~

Trong ví dụ, accepted là 9.850 record sau khi loại rejected và duplicate. Có 9.820 thành công và 30 dead-letter; tổng hai nhóm bằng attempted.

Nếu định nghĩa duplicate không phải loại bỏ mà là update lại document hiện có, cần điều chỉnh cách tính accepted/attempted. Quan trọng là quy tắc phải nhất quán và có thể giải thích.

### Đối soát số lượng không đủ để chứng minh đúng dữ liệu

Hai hệ thống có thể có cùng số document nhưng khác nội dung. Khi cần kiểm tra sâu, có thể đối chiếu:

- Source ID và target ID.
- Source version hoặc updated timestamp.
- Hash payload đã chuẩn hóa.
- Số lượng theo partition/category.
- Các field nghiệp vụ quan trọng.
- Tổng giá trị hoặc checksum theo nhóm.

Không nên hash JSON tùy tiện nếu thứ tự field, định dạng số, timezone hoặc null/empty có thể khác nhau. Cần canonicalize dữ liệu trước khi tạo checksum.

### Kiểm tra index sau import

Nếu job cần đảm bảo document có thể tìm kiếm được ngay sau khi hoàn tất, xác định refresh policy phù hợp. Refresh là điều kiện search visibility, không phải bằng chứng item-level bulk thành công.

Với import lớn, có thể trì hoãn refresh trong giai đoạn indexing rồi refresh một lần ở cuối nếu use case và cấu hình index cho phép. Không bật refresh tức thời cho từng item.

## 16. BulkProcessor và pipeline nhập liệu liên tục

Với nguồn dữ liệu liên tục, có thể dùng BulkProcessor của Elasticsearch Java API Client hoặc abstraction tương ứng trong phiên bản đang dùng để gom request theo:

- Số lượng operation.
- Tổng kích thước payload.
- Khoảng thời gian flush.
- Số request đồng thời.

Cần cấu hình bounded concurrency và giới hạn bộ nhớ. Nếu producer đọc nhanh hơn Elasticsearch xử lý, pipeline phải có backpressure hoặc hàng đợi giới hạn; không tích lũy vô hạn các document trong heap.

BulkProcessor listener thường có callback trước và sau mỗi bulk request. Sau callback thành công, vẫn cần duyệt item-level response để tìm lỗi từng operation. Callback lỗi request không cung cấp bằng chứng mọi item đều chưa được áp dụng; timeout có thể khiến kết quả không rõ ràng.

### Flush và close

Khi job kết thúc bình thường:

1. Ngừng nhận thêm input.
2. Flush các operation đang chờ.
3. Chờ các bulk request đang chạy hoàn tất.
4. Đối soát response và retry queue.
5. Lưu checkpoint cuối.
6. Đóng processor/client resource theo vòng đời ứng dụng.

Khi shutdown bất thường, durable source và checkpoint phải đủ để khởi động lại mà không phụ thuộc vào buffer còn nằm trong heap.

## 17. Backpressure và điều chỉnh tốc độ import

Tăng số worker hoặc batch size không phải lúc nào cũng tăng thông lượng. Khi Elasticsearch bị quá tải, tỷ lệ 429 tăng, retry làm request nhiều hơn và job có thể chậm thêm.

Theo dõi:

- Bulk latency p50/p95.
- Payload bytes mỗi request.
- Tỷ lệ 429 và 5xx.
- Tỷ lệ item lỗi theo mapping/validation.
- Queue depth.
- Số retry đang chờ.
- CPU, heap, disk I/O và indexing pressure của cluster.
- Thời gian chờ từ source tới khi record được xác nhận.

Khi tỷ lệ 429 tăng, giảm concurrency hoặc tốc độ gửi, thêm backoff và tăng dần trở lại khi cluster ổn định. Điều chỉnh dựa trên metric thay vì cố định tốc độ cao nhất.

## 18. Ví dụ tổ chức một batch import trong service

Một service orchestration có thể tách rõ đọc nguồn, gửi bulk, đối soát và checkpoint:

~~~java
public BatchResult importBatch(SourceBatch batch) {
    ValidatedBatch validated = validator.validate(batch);

    errorStore.saveRejected(
        batch.jobId(),
        validated.rejectedRecords()
    );

    List<BulkItemOutcome> outcomes =
        bulkWriter.write(validated.acceptedRecords());

    reconciliation.verify(
        validated,
        outcomes
    );

    errorStore.saveFailures(
        outcomes.stream()
            .filter(outcome ->
                outcome.outcome() == ItemOutcome.RETRYABLE_FAILURE
                    || outcome.outcome() == ItemOutcome.PERMANENT_FAILURE)
            .toList()
    );

    checkpointStore.commitBatch(
        batch.jobId(),
        batch.batchId(),
        outcomes
    );

    return BatchResult.from(validated, outcomes);
}
~~~

Đây là cấu trúc minh họa, không phải một transaction duy nhất. Trong triển khai thực tế, việc lưu item outcomes và commit batch phải có quy tắc phục hồi nếu process crash giữa các bước. Có thể dùng trạng thái PREPARED/RESULTS_RECORDED/COMMITTED hoặc một bảng ledger có khóa duy nhất để thao tác lặp không tạo trạng thái mâu thuẫn.

### Phân tách trách nhiệm

- SourceReader: đọc range hoặc partition và giữ source cursor.
- Validator: kiểm tra schema và quy tắc nghiệp vụ.
- BulkWriter: chuyển record thành operation và gọi Elasticsearch.
- OutcomeMapper: chuyển response/exception thành trạng thái từng item.
- RetryScheduler: xếp lịch retry cho lỗi tạm thời.
- DeadLetterStore: lưu lỗi cần sửa hoặc can thiệp.
- ReconciliationService: đối chiếu expected và actual counts.
- CheckpointStore: lưu tiến độ bền vững.
- JobCoordinator: lease, resume và quản lý trạng thái job.

Tách lớp giúp kiểm thử từng phần và thay đổi API Spring Data mà không phải viết lại logic đối soát.

## 19. Kiểm thử lỗi và khả năng resume

Một import pipeline không thể chỉ test đường chạy thành công. Cần mô phỏng các tình huống thất bại ở ranh giới giữa source, Elasticsearch và checkpoint store.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Một item lỗi mapping trong bulk | Item lỗi được lưu, item khác vẫn được xác nhận thành công |
| Một item trả 429 | Chỉ item retryable được đưa vào retry |
| Bulk response có errors = true | Job đọc item list, không đánh dấu cả batch thất bại đồng loạt |
| Timeout trước khi nhận response | Batch giữ trạng thái cần đối soát hoặc replay idempotent |
| Crash sau bulk success, trước checkpoint | Restart replay không tạo duplicate hoặc double increment |
| Crash sau khi lưu retry, trước checkpoint | Resume không làm mất retry record |
| Crash giữa hai batch | Batch đã commit được bỏ qua, batch chưa commit được chạy lại |
| Worker chạy song song | Checkpoint không vượt qua batch chưa hoàn tất |
| Worker lease hết hạn | Worker mới tiếp quản an toàn |
| Retry hết giới hạn | Record chuyển dead-letter |
| Source thay đổi trong lúc import | Snapshot/watermark hoặc reconciliation phát hiện chênh lệch |
| Refresh chưa xảy ra | Phân biệt item đã index với item đã search-visible |

### Kiểm thử đối soát

Tạo batch có 10 record:

- 7 record thành công.
- 1 record lỗi mapping.
- 1 record 429.
- 1 record bị loại ở validation.

Kỳ vọng:

- sourceRead = 10.
- accepted = 9.
- rejected = 1.
- attempted = 9.
- succeeded = 7.
- retryPending = 1.
- deadLetter = 1 nếu lỗi mapping được phân loại permanent.

Sau khi sửa dữ liệu và retry item 429 thành công, báo cáo mới cần phản ánh trạng thái cuối và lịch sử attempt. Không cộng cùng một item vào succeeded nhiều lần chỉ vì nó đã được gửi nhiều lần.

### Kiểm thử resume sau crash

Một test có thể mô phỏng:

1. Đọc batch A.
2. Gửi bulk và nhận một số item success, một item retryable.
3. Lưu item outcomes.
4. Dừng process trước khi commit checkpoint.
5. Khởi động lại job.
6. Replay batch A hoặc khôi phục từ ledger theo thiết kế.
7. Xác nhận document thành công không bị nhân đôi, counter không tăng thêm ngoài dự kiến và item retry được xử lý.
8. Commit checkpoint khi batch đã có kết quả bền vững.

Test này quan trọng hơn việc chỉ kiểm tra method checkpoint được gọi.

## 20. Các lỗi thường gặp khi nhập liệu

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Job báo thành công nhưng thiếu document | Chỉ kiểm tra HTTP status hoặc không đọc item errors | Đối soát từng item và expected counts |
| Một batch bị gửi lại toàn bộ | Không lưu outcome theo item | Retry đúng item lỗi hoặc replay idempotent |
| Document bị trùng sau restart | ID đích không ổn định | Dùng deterministic ID/business key |
| Counter tăng nhiều lần | Script increment bị replay | Dùng event ID/deduplication |
| Checkpoint vượt qua record lỗi | Commit theo offset đã đọc thay vì kết quả đã lưu | Commit theo batch/contiguous watermark |
| Lỗi mapping bị retry mãi | Không phân biệt permanent và transient | Phân loại error type/status |
| Cluster quá tải hơn sau khi retry | Retry đồng loạt, không backoff | Exponential backoff với jitter và giảm concurrency |
| Bulk response không ghép được với source | Không giữ metadata theo operation order | Lưu source ID/target ID song song |
| Tổng count không khớp | Định nghĩa rejected/duplicate/attempted không rõ | Chuẩn hóa công thức reconciliation |
| Worker cũ ghi checkpoint sau worker mới | Không có lease/fencing/version | Dùng lease và fencing token |
| Search chưa thấy dữ liệu mới | Chưa refresh | Quy định refresh policy và phân biệt indexing với visibility |
| Dead-letter không được xử lý | Chỉ lưu log, không có quy trình replay | Xây luồng sửa dữ liệu và replay có kiểm soát |

## 21. Checklist vận hành bulk import

- [ ] Có job ID và batch ID ổn định.
- [ ] Mỗi source record có ID để đối soát.
- [ ] Định nghĩa rõ sourceRead, accepted, rejected, duplicate và attempted.
- [ ] Batch giới hạn cả số document và payload bytes.
- [ ] Giữ metadata để ghép từng response item với source record.
- [ ] Kiểm tra cờ errors và mọi item trong bulk response.
- [ ] Phân loại lỗi permanent, retryable và uncertain outcome.
- [ ] Retry có giới hạn, backoff và jitter.
- [ ] Không retry toàn bộ batch khi đã biết chính xác item thành công.
- [ ] Dùng ID đích ổn định và operation có tính idempotent khi replay.
- [ ] Có ledger, retry store hoặc dead-letter store bền vững.
- [ ] Checkpoint chỉ tiến sau khi kết quả batch đã được ghi nhận.
- [ ] Xử lý crash giữa Elasticsearch write và checkpoint commit.
- [ ] Worker song song dùng checkpoint theo batch hoặc contiguous watermark.
- [ ] Có lease/ownership để tránh hai worker cùng commit một partition.
- [ ] Đối soát số lượng và, khi cần, checksum/source version.
- [ ] Có chính sách refresh phù hợp với search visibility.
- [ ] Theo dõi latency, 429, queue depth và retry rate.
- [ ] Integration test mô phỏng lỗi item và restart giữa chừng.

Một pipeline bulk đáng tin cậy không kết thúc ở thời điểm gửi request. Nó kết thúc khi từng record đã có trạng thái được ghi nhận, số lượng đầu vào và đầu ra được đối soát, lỗi được retry hoặc lưu để xử lý, và checkpoint chỉ ra chính xác phần dữ liệu có thể tiếp tục. Kết hợp item-level response, ID ổn định, idempotency, durable ledger và checkpoint theo batch giúp job phục hồi sau timeout hoặc restart mà không âm thầm bỏ sót hay nhân đôi dữ liệu.

