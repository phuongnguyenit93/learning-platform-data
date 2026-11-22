# Bootstrap index từ dữ liệu cũ mà không mất thay đổi mới

Khi tạo một Elasticsearch index mới cho hệ thống đang chạy, ứng dụng thường phải nạp lại dữ liệu đã tồn tại trước đó. Trong lúc quá trình nạp dữ liệu diễn ra, người dùng vẫn tạo mới, cập nhật hoặc xóa bản ghi. Nếu chỉ quét dữ liệu cũ rồi ghi vào index mới, những thay đổi phát sinh trong thời gian bootstrap có thể bị bỏ sót hoặc bị dữ liệu cũ ghi đè.

Ví dụ, job bootstrap đọc sản phẩm P-100 với giá 100. Trong lúc job đang chạy, người dùng đổi giá thành 120. Nếu event cập nhật giá 120 được ghi vào index mới trước, rồi job bootstrap mới ghi bản snapshot giá 100 sau đó, index mới sẽ quay lại trạng thái cũ. Một trường hợp khác là sản phẩm bị xóa trong lúc bootstrap; nếu snapshot cũ được ghi sau event xóa, sản phẩm có thể xuất hiện trở lại.

Muốn bootstrap an toàn, cần phối hợp hai luồng dữ liệu:

1. **Snapshot:** dữ liệu hiện có tại một mốc nhất quán.
2. **Change stream:** mọi thay đổi phát sinh sau mốc snapshot đó.

Sau khi nạp snapshot vào index mới, ứng dụng phát lại các thay đổi đã ghi nhận, bắt kịp luồng cập nhật hiện tại rồi mới chuyển truy vấn sang index mới. Cơ chế này thường được xây dựng bằng database change data capture (CDC), transactional outbox hoặc một change log có thứ tự.

## 1. Bài toán bootstrap khi hệ thống vẫn ghi dữ liệu

Giả sử hệ thống có nguồn dữ liệu chuẩn là database và Elasticsearch đang phục vụ tìm kiếm. Cần tạo index mới để thay đổi mapping, analyzer, cấu trúc document hoặc cách phân tích dữ liệu.

Trong thời gian bootstrap:

- Người dùng vẫn tạo document mới.
- Document cũ vẫn được cập nhật.
- Một số document bị xóa.
- Job bootstrap đọc dữ liệu theo từng trang và ghi theo batch.
- Các event thay đổi có thể đến trước hoặc sau bản snapshot tương ứng.

Mục tiêu là index mới phản ánh đầy đủ trạng thái nguồn tại thời điểm cutover, không bỏ sót thay đổi và không để dữ liệu cũ ghi đè dữ liệu mới.

### 1.1. Vì sao chỉ quét dữ liệu cũ là không đủ?

Một cách làm đơn giản là:

1. Đọc toàn bộ bảng sản phẩm.
2. Ghi từng trang vào index mới.
3. Khi hoàn tất, chuyển alias sang index mới.

Cách này có một khoảng trống: các thay đổi xảy ra sau khi job đã đọc qua một bản ghi nhưng trước khi cutover có thể không nằm trong snapshot. Nếu ứng dụng vẫn ghi vào index cũ, index mới không nhận được những thay đổi đó.

Ngay cả khi ứng dụng đồng thời ghi cả index cũ và mới, thứ tự ghi có thể gây race condition. Job snapshot có thể ghi dữ liệu cũ sau một lần cập nhật mới.

### 1.2. Hai luồng dữ liệu cần được phối hợp

~~~text
                  Nguồn dữ liệu chuẩn
                         |
              +----------+----------+
              |                     |
              v                     v
       Snapshot nhất quán       Change stream
              |                (CDC / Outbox)
              v                     |
       Bulk bootstrap               |
              |                     |
              v                     v
             Index mới <--- Replay và catch-up
                         |
                         v
                  Kiểm tra dữ liệu
                         |
                         v
                  Chuyển read alias
~~~

Snapshot giúp nạp trạng thái đã tồn tại. Change stream giúp đưa index mới đến trạng thái hiện tại. Hai luồng phải có một mốc nối chính xác hoặc một cơ chế version đủ mạnh để xử lý phần giao nhau.

## 2. Các khái niệm cần có

| Khái niệm | Ý nghĩa |
| --- | --- |
| Source of truth | Nguồn dữ liệu chuẩn, nơi nghiệp vụ thực hiện ghi |
| Target index | Index mới đang được bootstrap |
| Snapshot | Ảnh chụp dữ liệu nguồn tại một thời điểm nhất quán |
| Watermark | Vị trí trong change log xác định ranh giới snapshot |
| CDC | Change Data Capture, ghi nhận thay đổi ở database |
| Transactional outbox | Bảng event được ghi cùng transaction nghiệp vụ |
| Replay | Phát lại event đã ghi nhận vào target index |
| Catch-up | Xử lý change stream đến gần hoặc bằng vị trí hiện tại |
| Cutover | Chuyển read alias sang index mới |
| Tombstone | Bản ghi đánh dấu document đã bị xóa, giữ version của thao tác xóa |

Một watermark có thể là database log sequence number (LSN), binlog position, transaction ID có semantics phù hợp, Kafka offset hoặc vị trí của outbox event. Không nên mặc định một timestamp ứng dụng có thể thay thế watermark của database.

## 3. Các chiến lược bootstrap

Không có một quy trình duy nhất phù hợp với mọi hệ thống. Lựa chọn phụ thuộc nguồn dữ liệu, khả năng dừng ghi, mức tải và yêu cầu nhất quán.

| Chiến lược | Cách làm | Khi phù hợp | Rủi ro chính |
| --- | --- | --- | --- |
| Maintenance window | Dừng ghi, nạp snapshot, chuyển alias rồi mở ghi | Dataset nhỏ, chấp nhận downtime | Downtime dài nếu import chậm |
| Snapshot + CDC | Chụp snapshot nhất quán, replay log sau watermark | Hệ thống đang chạy, cần giảm downtime | Cần CDC và quản lý offset |
| Snapshot + transactional outbox | Snapshot nguồn, phát lại outbox sau mốc tương ứng | Ứng dụng kiểm soát được transaction và event | Cần thiết kế outbox, thứ tự và retention |
| Overlap + source version | Cho snapshot và event chạy chồng nhau, từ chối dữ liệu version cũ | Không có snapshot/log boundary hoàn hảo | Cần version đơn điệu và xử lý delete đúng |
| Dual-write | Ứng dụng ghi cả index cũ và mới | Chỉ phù hợp khi có cơ chế retry/đối soát rõ ràng | Hai lần ghi không atomic, dễ lệch dữ liệu |

Với hệ thống đang nhận ghi liên tục, snapshot kết hợp CDC hoặc outbox thường là phương án dễ chứng minh không mất thay đổi nhất.

### 3.1. Maintenance window

Nếu có thể tạm dừng toàn bộ thao tác ghi:

1. Chặn request tạo/sửa/xóa.
2. Chờ các transaction đang chạy hoàn tất.
3. Chụp snapshot nguồn.
4. Nạp snapshot vào index mới.
5. Refresh và kiểm tra index.
6. Chuyển alias.
7. Mở lại thao tác ghi.

Vì không có thay đổi trong lúc snapshot và index mới được tạo, không cần replay event. Đây là cách đơn giản nhưng downtime có thể dài.

### 3.2. Snapshot + CDC

CDC đọc database transaction log và ghi lại insert, update, delete theo thứ tự commit. Một connector CDC thường có thể cung cấp vị trí log để xác định snapshot tương ứng.

Quy trình:

1. Khởi động CDC và xác định vị trí bắt đầu.
2. Tạo consistent snapshot gắn với vị trí log đó.
3. Nạp snapshot vào index mới.
4. Phát lại CDC event bắt đầu sau snapshot position.
5. Tiếp tục tiêu thụ event mới trong lúc kiểm tra.
6. Cutover khi target đã bắt kịp một watermark được xác nhận.

Điểm quan trọng là snapshot và log position phải được phối hợp theo cơ chế của database/CDC connector. Không tự lấy thời gian hệ thống trước khi query rồi giả định đó là ranh giới transaction chính xác.

### 3.3. Snapshot + transactional outbox

Nếu ứng dụng tự quản lý thay đổi nghiệp vụ, transactional outbox là một lựa chọn:

- Transaction nghiệp vụ cập nhật bảng dữ liệu và ghi event vào bảng outbox trong cùng transaction.
- Publisher đọc outbox và gửi event đến message broker.
- Projector đọc event và cập nhật Elasticsearch.

Vì event được ghi cùng transaction nguồn, ứng dụng tránh được tình trạng database commit thành công nhưng publish event thất bại.

Để bootstrap, cần xác định mốc outbox tương ứng với snapshot. Có thể dùng database consistent snapshot và watermark/ID outbox được xác định trong cùng phạm vi transaction phù hợp. Nếu không có cơ chế snapshot-offset đồng bộ, dùng overlap có version và reconciliation thay vì dựa vào timestamp ước lượng.

### 3.4. Dual-write không tự bảo đảm nhất quán

Một cách thường được nghĩ đến là sau mỗi lần ghi database, ứng dụng gọi Elasticsearch hai lần: một lần vào index cũ và một lần vào index mới.

Nếu database commit thành công nhưng lần ghi thứ hai thất bại, hai index lệch nhau. Nếu request timeout sau khi Elasticsearch đã ghi nhưng client chưa nhận response, retry có thể tạo side effect lặp. Hai lần ghi không nằm trong cùng một transaction phân tán.

Nếu vẫn dùng dual-write, cần outbox hoặc durable retry, ID ổn định, version, giám sát lỗi từng đích và reconciliation. Dual-write đơn thuần không phải bảo đảm không mất dữ liệu.

## 4. Chọn đúng watermark cho snapshot

Watermark là phần quan trọng nhất của quy trình. Nó xác định event nào đã được phản ánh trong snapshot và event nào phải replay.

Ví dụ:

~~~text
Database transaction log
       |
       +-- LSN 100: cập nhật P-1
       |
       +-- LSN 101: tạo P-2
       |
       +-- LSN 102: snapshot boundary
       |
       +-- LSN 103: đổi giá P-1
       |
       +-- LSN 104: xóa P-2
       |
       +-- LSN 105: tạo P-3

Snapshot phản ánh trạng thái tại LSN 102.
Replay các thay đổi sau LSN 102.
~~~

Khi replay, cần xác định semantics inclusive/exclusive rõ ràng. Nếu snapshot đã bao gồm transaction tại watermark W, chỉ replay các transaction sau W. Nếu snapshot chưa bao gồm W, phải replay từ W. Một event bị bỏ qua hoặc phát lại hai lần đều cần được xử lý có chủ đích.

### 4.1. Timestamp không phải watermark an toàn

Không nên chỉ dùng điều kiện updatedAt lớn hơn thời điểm bắt đầu bootstrap làm change capture duy nhất.

Các vấn đề:

- Đồng hồ của nhiều application instance có thể lệch nhau.
- Transaction có thể bắt đầu trước nhưng commit sau.
- Nhiều thay đổi có cùng độ chính xác timestamp.
- Một bản ghi có thể được cập nhật nhưng timestamp không được thay đổi đúng.
- Delete có thể không còn bản ghi để truy vấn theo updatedAt.
- Job snapshot đọc một hàng trước khi transaction cập nhật commit.

Timestamp hữu ích cho reconciliation hoặc lọc sơ bộ, nhưng cần một log position, outbox sequence hoặc source version có semantics rõ ràng để làm ranh giới.

### 4.2. CDC position

Tùy database, watermark có thể là:

- MySQL binlog file/position hoặc GTID.
- PostgreSQL WAL LSN hoặc replication slot position.
- SQL Server LSN trong CDC/change tracking.
- Kafka offset của topic change event.
- Một sequence được ghi trong outbox và đồng bộ với snapshot transaction.

Tên và cách lấy position phụ thuộc database/connector. Hãy dùng cơ chế snapshot mode được connector hỗ trợ thay vì tự ghép log position và query snapshot bằng hai thao tác không liên quan.

## 5. Tạo snapshot nhất quán

Snapshot phải đại diện cho trạng thái nguồn tại cùng một mốc logic. Nếu job đọc từng trang trong lúc dữ liệu thay đổi mà không có snapshot isolation, các trang có thể phản ánh những thời điểm khác nhau.

Ví dụ:

1. Job đọc trang 1 lúc 10:00.
2. Một transaction đổi sản phẩm trong trang 2 lúc 10:01.
3. Job đọc trang 2 lúc 10:02.
4. Job đọc trang 3 lúc 10:03.

Kết quả có thể trộn trạng thái trước và sau thay đổi. CDC có thể sửa phần chênh lệch nếu ranh giới snapshot được xác định đúng; nếu không, có thể bị bỏ sót hoặc áp dụng sai thứ tự.

### 5.1. Dùng consistent snapshot của database

Database có thể cung cấp transaction snapshot hoặc cơ chế snapshot export. Job bootstrap cần đọc toàn bộ dữ liệu theo snapshot đó, trong khi CDC giữ lại các transaction phát sinh sau vị trí tương ứng.

Không giữ transaction snapshot mở quá lâu nếu database không chịu được. Dataset lớn có thể tạo áp lực MVCC, giữ lại row versions hoặc làm tăng dung lượng transaction log. Cần đo thời gian snapshot và cấu hình retention phù hợp.

### 5.2. Phân trang theo key ổn định

Với dữ liệu lớn, không nên dùng offset pagination rất sâu nếu database phải bỏ qua nhiều hàng ở mỗi trang. Keyset pagination thường hiệu quả hơn:

~~~sql
SELECT id, name, brand_id, price, source_version
FROM product
WHERE id > :last_seen_id
ORDER BY id
LIMIT :batch_size;
~~~

Điều kiện này chỉ an toàn nếu:

- ID có thứ tự ổn định và duy nhất.
- Snapshot vẫn được giữ nhất quán.
- Job lưu checkpoint last_seen_id sau khi batch được xử lý thành công.
- Không có quy tắc khiến bản ghi chưa đọc bị chuyển về phía trước/sau cursor ngoài semantics snapshot.

Nếu dùng khóa ghép, ORDER BY và điều kiện cursor phải chứa đủ các thành phần để tạo thứ tự toàn phần.

### 5.3. Không đánh dấu checkpoint trước khi ghi batch xong

Giả sử job đọc đến ID P-500 rồi ghi batch vào Elasticsearch. Nếu cập nhật checkpoint P-500 trước khi bulk hoàn tất, process có thể crash sau checkpoint nhưng trước khi ghi xong. Lần chạy tiếp theo sẽ bỏ qua phần dữ liệu chưa ghi.

Thứ tự an toàn:

1. Đọc batch từ snapshot.
2. Transform document.
3. Gửi bulk.
4. Kiểm tra item-level result.
5. Xử lý hoặc lưu riêng các item thất bại.
6. Chỉ cập nhật checkpoint sau khi batch đạt trạng thái hoàn tất theo chính sách.

Nếu batch có item thất bại, checkpoint cần phản ánh chính xác các item đã xử lý. Có thể lưu ID thất bại để retry riêng, hoặc không tiến checkpoint qua batch cho đến khi các item được xử lý.

## 6. Nạp snapshot bằng bulk

Không nên gọi một HTTP request cho mỗi document khi bootstrap hàng triệu bản ghi. Hãy chia dữ liệu thành batch và dùng Bulk API.

Một luồng tổng quát:

~~~text
Snapshot reader
      |
      v
Batch transformer
      |
      v
Bulk writer
      |
      v
New versioned index
      |
      v
Checkpoint store
~~~

### 6.1. Chuẩn bị target index

Tạo index mới với tên có version, ví dụ:

~~~text
products-v2
~~~

Trước khi nạp dữ liệu, cấu hình:

- Mapping chính xác cho document model mới.
- Analyzer, normalizer và multi-fields.
- Settings và số shard/replica phù hợp.
- Ingest pipeline nếu có.
- Alias đọc/ghi sau cutover.
- Quy tắc version hoặc sourceVersion.

Không dựa vào dynamic mapping trong lúc import lớn nếu dữ liệu có thể chứa kiểu không đồng nhất. Một document lỗi mapping có thể thất bại ở cấp item trong bulk response.

### 6.2. Bulk trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp BulkOperations để ghi nhiều entity:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.BulkMode;
import org.springframework.data.elasticsearch.core.BulkOperations;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductBootstrapWriter {

    private final ElasticsearchOperations operations;
    private final String targetIndex;

    public ProductBootstrapWriter(
            ElasticsearchOperations operations,
            String targetIndex) {
        this.operations = operations;
        this.targetIndex = targetIndex;
    }

    public void writeBatch(List<ProductIndexDocument> batch) {
        BulkOperations bulk = operations.bulkOps(
            BulkMode.BULK,
            ProductIndexDocument.class,
            IndexCoordinates.of(targetIndex)
        );

        bulk.insert(batch);
        bulk.execute();
    }
}
~~~

Ví dụ minh họa việc ghi một batch vào index đích cụ thể. API BulkOperations và khả năng truy cập failed item details phụ thuộc phiên bản Spring Data Elasticsearch. Với pipeline cần kiểm tra chính xác status/error từng item, hãy dùng API bulk expose BulkResponse hoặc API Java client phù hợp.

Không đánh dấu batch hoàn tất chỉ vì execute không ném exception nếu abstraction đang dùng không cung cấp đủ chi tiết kết quả theo yêu cầu ingestion. Cần xác định contract lỗi của đúng phiên bản.

### 6.3. Kích thước batch

Không có số lượng document cố định phù hợp mọi cluster. Hãy giới hạn theo cả số item và số byte:

- Document nhỏ có thể gom nhiều item hơn.
- Document lớn hoặc có nested fields cần batch nhỏ hơn.
- Ingest pipeline phức tạp có thể làm giảm throughput.
- Bulk response cũng chiếm memory phía client.
- Batch quá lớn làm tăng latency và khó retry từng phần.

Benchmark trên dữ liệu đại diện, theo dõi bulk took, client latency, 429 và heap. Điều chỉnh batch size và concurrency theo tải thực tế.

## 7. Change capture trong lúc bootstrap

Sau khi xác định snapshot boundary, cần giữ lại mọi thay đổi sau boundary cho đến khi target index bắt kịp.

Một event tối thiểu nên chứa:

~~~json
{
  "eventId": "evt-90001",
  "aggregateType": "Product",
  "aggregateId": "P-100",
  "aggregateVersion": 42,
  "operation": "UPSERT",
  "occurredAt": "2026-11-13T10:15:00Z",
  "payload": {
    "id": "P-100",
    "name": "Mechanical Keyboard",
    "price": 120
  }
}
~~~

Event delete:

~~~json
{
  "eventId": "evt-90002",
  "aggregateType": "Product",
  "aggregateId": "P-101",
  "aggregateVersion": 19,
  "operation": "DELETE",
  "occurredAt": "2026-11-13T10:16:00Z"
}
~~~

Các field quan trọng:

- eventId để deduplicate khi broker giao event nhiều lần.
- aggregateId để xác định document.
- aggregateVersion để từ chối event cũ.
- operation để phân biệt upsert và delete.
- payload đủ để dựng document hoặc áp dụng thay đổi.
- log position/partition offset để theo dõi tiến độ.

### 7.1. Full-state event và delta event

Full-state event chứa trạng thái đầy đủ của aggregate sau thay đổi. Projector có thể index lại document bằng ID ổn định. Cách này thường dễ retry và phục hồi.

Delta event chỉ chứa phần thay đổi, ví dụ chỉ có giá mới. Projector phải áp dụng delta theo đúng thứ tự và bảo đảm không bỏ sót event trước đó.

Nếu event đến trùng hoặc sai thứ tự, delta có nguy cơ làm trạng thái cuối sai. Khi có thể, dùng full-state projection hoặc mang source version và kiểm soát thứ tự chặt chẽ.

### 7.2. Partition theo aggregate ID

Nếu dùng Kafka hoặc message broker có partition, thường nên chọn aggregate ID làm partition key. Các event của cùng một aggregate sẽ được giữ thứ tự trong partition đó theo semantics broker.

Điều này giúp projector xử lý các thay đổi của cùng một document theo thứ tự. Các aggregate khác nhau vẫn có thể được xử lý song song.

Nếu nhiều nguồn event có thể cập nhật cùng document, cần một quy tắc ordering chung hoặc source version để quyết định event nào mới hơn.

## 8. Replay và catch-up

Sau khi snapshot đã được nạp, bắt đầu replay các thay đổi từ watermark.

~~~text
Snapshot at W
     |
     v
Bulk load snapshot
     |
     v
Replay events after W
     |
     v
Apply updates/deletes
     |
     v
Continue consuming new events
     |
     v
Lag approaches zero
~~~

### 8.1. Replay phải bền vững

Không giữ event trong memory của một process bootstrap duy nhất. Nếu process crash, event phải còn trong CDC log, outbox hoặc message broker để có thể replay lại.

Offset/checkpoint của consumer chỉ được commit sau khi các operation tương ứng đã được ghi thành công hoặc đã được xử lý theo chính sách lỗi. Nếu commit offset trước khi ghi Elasticsearch, process crash có thể làm event bị bỏ qua vĩnh viễn.

Nếu ghi Elasticsearch thành công nhưng commit offset thất bại, event có thể được giao lại. Vì vậy, projector phải idempotent.

### 8.2. Đo consumer lag

Lag là khoảng cách giữa vị trí mới nhất của change stream và vị trí projector đã xử lý.

Cần theo dõi:

- CDC log position hiện tại.
- Consumer offset đã commit.
- Số event đang chờ.
- Tuổi của event cũ nhất chưa xử lý.
- Tốc độ phát sinh event.
- Tốc độ xử lý event.
- Số item lỗi và retry queue.

Nếu tốc độ thay đổi nguồn cao hơn tốc độ replay, lag sẽ không giảm. Cần tăng năng lực projector, tối ưu bulk, giảm chi phí transform hoặc giảm concurrency ở nguồn nếu có thể.

### 8.3. Catch-up đến một barrier

Không nên cutover chỉ vì consumer lag hiển thị gần bằng 0 tại một thời điểm ngẫu nhiên.

Hãy xác định một barrier:

1. Lấy high watermark H của change stream.
2. Xác nhận target đã xử lý tất cả event đến H.
3. Xác nhận không có batch lỗi chưa giải quyết trước H.
4. Xác nhận mọi partition đã đến offset tương ứng.
5. Thực hiện cutover trong khi consumer vẫn tiếp tục xử lý event mới.

Với nhiều partition, barrier là tập offset theo partition chứ không nhất thiết là một số duy nhất.

## 9. Xử lý race condition giữa snapshot và event

Đây là phần dễ sai nhất của bootstrap. Snapshot và event có thể đến target theo thứ tự khác với thứ tự thay đổi trong nguồn.

### 9.1. Snapshot cũ ghi sau event mới

Timeline:

~~~text
Nguồn:
  v10: price = 100
  v11: price = 120

Target:
  1. Event v11 được replay -> price = 120
  2. Snapshot v10 được bulk ghi sau -> price = 100

Kết quả sai: target quay lại v10
~~~

Có hai cách chính để ngăn việc này:

- Đảm bảo snapshot được ghi xong trước khi replay event.
- Hoặc dùng source version để target từ chối dữ liệu có version cũ hơn.

Trong hệ thống lớn, nên có cả hai: trình tự pipeline rõ ràng và version guard để bảo vệ khi retry, resume hoặc có race bất ngờ.

### 9.2. Lưu source version trong document

Mỗi aggregate nên có một version đơn điệu tăng khi trạng thái thay đổi:

~~~json
{
  "id": "P-100",
  "name": "Mechanical Keyboard",
  "price": 120,
  "sourceVersion": 11
}
~~~

Snapshot và event đều mang sourceVersion. Projector chỉ áp dụng bản có version mới hơn trạng thái đã ghi.

Không nhầm sourceVersion nghiệp vụ với Elasticsearch internal _version. Elasticsearch _version là metadata quản lý document trong index; sourceVersion là version của nguồn dữ liệu chuẩn.

### 9.3. External versioning

Elasticsearch hỗ trợ external versioning cho Index API và các bulk index operation. Ứng dụng có thể gửi version lấy từ nguồn:

- external: chỉ chấp nhận version mới hơn version đang lưu.
- external_gte: chấp nhận version lớn hơn hoặc bằng version đang lưu.

Ví dụ ý tưởng với Java API Client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.VersionType;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;

BulkRequest.Builder request = new BulkRequest.Builder();

for (ProductIndexDocument document : batch) {
    request.operations(operation -> operation
        .index(index -> index
            .index(targetIndex)
            .id(document.id())
            .version(document.sourceVersion())
            .versionType(VersionType.ExternalGte)
            .document(document)
        )
    );
}

BulkResponse response = elasticsearchClient.bulk(request.build());
~~~

Đoạn code minh họa API Java client. Package, enum constant và builder method cần được đối chiếu với phiên bản Elasticsearch Java API Client trong dự án.

Với external versioning:

- Snapshot version 10 đến sau event version 11 sẽ bị từ chối.
- Event version 12 được chấp nhận sau version 11.
- Gửi lại event version 12 với external_gte có thể được chấp nhận lần nữa.

external_gte chỉ an toàn khi cùng một source version luôn đại diện cho cùng một trạng thái document. Nếu hai payload khác nhau dùng cùng version, payload đến sau có thể ghi đè payload trước. Hãy bảo đảm version duy nhất cho mỗi trạng thái hoặc dùng external strict versioning và cơ chế deduplicate phù hợp.

### 9.4. Version phải đơn điệu theo document

Không dùng timestamp millisecond làm version nếu có thể xảy ra hai thay đổi cùng thời điểm hoặc đồng hồ lệch. Tốt hơn là:

- Aggregate version tăng trong transaction nguồn.
- Sequence number do database cấp.
- Event sequence được quản lý bền vững theo aggregate.

Version phải tăng theo thứ tự nghiệp vụ của cùng một document. Không cần mọi document dùng chung một sequence toàn cục nếu source không cung cấp điều đó.

## 10. Xử lý delete để tránh document sống lại

Delete là trường hợp thường bị bỏ sót trong bootstrap.

Timeline:

1. Snapshot đọc thấy P-100 còn tồn tại.
2. Người dùng xóa P-100.
3. Delete event được áp dụng vào index mới.
4. Job snapshot chậm ghi P-100 vào index mới sau delete.

Document đã bị xóa lại xuất hiện.

### 10.1. Tombstone

Một giải pháp là biểu diễn delete bằng tombstone:

~~~json
{
  "id": "P-100",
  "sourceVersion": 15,
  "deleted": true,
  "deletedAt": "2026-11-13T10:16:00Z"
}
~~~

Tombstone giữ version của thao tác xóa. Query đọc sản phẩm phải lọc deleted=false. Khi snapshot cũ version 14 đến muộn, version guard từ chối nó vì tombstone đã có version 15.

Tombstone cần được giữ đủ lâu để mọi snapshot, event retry, consumer replay và job phục hồi cũ không còn có khả năng ghi lại dữ liệu trước delete.

Sau khi qua retention window và xác nhận không còn event cũ, có thể chạy cleanup để xóa tombstone.

### 10.2. Vì sao không luôn dùng physical delete?

Elasticsearch có lưu thông tin version của document đã xóa trong một khoảng thời gian giới hạn thông qua cơ chế gc_deletes. Không nên dựa vào metadata delete đó để chống event cũ sau một thời gian replay dài hoặc sau khi hệ thống phục hồi từ backup.

Nếu một event upsert cũ đến sau khi metadata delete đã được dọn, document có thể được tạo lại. Tombstone document với sourceVersion bền vững giúp projector có thông tin để từ chối bản ghi cũ.

### 10.3. Delete event cũng phải có version

Event delete cần mang version mới hơn trạng thái trước đó. Không xử lý delete như một lệnh xóa vô điều kiện nếu có thể có event cũ đến muộn.

Nếu source không có aggregate version, cần một sequence hoặc tombstone ledger đủ bền để phân biệt delete mới với upsert cũ.

## 11. Idempotency và xử lý event giao lặp

CDC connector, message broker hoặc consumer có thể giao lại event khi retry. Một projector an toàn phải chấp nhận event được xử lý nhiều lần mà không làm trạng thái cuối sai.

Các nguyên tắc:

- Dùng document ID ổn định theo khóa nghiệp vụ.
- Mỗi event có eventId duy nhất.
- Mỗi aggregate có sourceVersion tăng đơn điệu.
- Ghi document bằng phép gán trạng thái xác định khi có thể.
- Deduplicate event hoặc dùng version guard.
- Không tăng counter chỉ bằng phép cộng khi chưa có cơ chế chống xử lý lặp.

### 11.1. At-least-once và exactly-once

Nhiều pipeline CDC/message broker cung cấp at-least-once delivery: event có thể được giao lại nhưng không nên bị mất khi consumer retry đúng cách.

Không nên giả định toàn bộ luồng từ database qua broker đến Elasticsearch có exactly-once transaction. Thay vào đó, thiết kế projector idempotent để event giao lặp không làm sai dữ liệu.

### 11.2. Full-state upsert dễ phục hồi hơn delta

Nếu event mang trạng thái đầy đủ của product sau thay đổi, projector có thể index lại cùng document ID và sourceVersion. Event lặp có thể được bỏ qua hoặc áp dụng lại an toàn theo version policy.

Nếu event chỉ mang delta như tăng tồn kho thêm 1, giao lặp có thể làm tồn kho tăng hai lần. Cần event deduplication bền vững hoặc tính trạng thái mới từ nguồn chuẩn.

## 12. Thiết kế projector cho bootstrap

Projector là thành phần chuyển snapshot row hoặc event thành Elasticsearch document.

Nên dùng chung quy tắc transform giữa snapshot và event:

~~~text
Snapshot row ------+
                   |
                   v
              Document mapper
                   |
                   v
              Index document
                   ^
                   |
Change event ------+
~~~

Nếu snapshot và event dùng hai mapper khác nhau, cùng một bản ghi nguồn có thể tạo ra hai dạng document khác nhau. Điều này dẫn đến sai lệch field, mapping hoặc logic tìm kiếm.

### 12.1. Mapper dùng chung

~~~java
public class ProductDocumentMapper {

    public ProductIndexDocument fromSnapshot(ProductRow row) {
        return new ProductIndexDocument(
            row.id(),
            row.name(),
            row.price(),
            row.version(),
            false
        );
    }

    public ProductIndexDocument fromEvent(ProductChanged event) {
        return new ProductIndexDocument(
            event.productId(),
            event.name(),
            event.price(),
            event.aggregateVersion(),
            false
        );
    }
}
~~~

Đây là ví dụ minh họa. Nếu event chỉ chứa delta, mapper phải lấy trạng thái đầy đủ hoặc projector phải áp dụng delta tuần tự theo version.

### 12.2. Lưu trạng thái tiến độ

Một bootstrap job thường cần lưu:

~~~json
{
  "jobId": "products-v2-bootstrap",
  "targetIndex": "products-v2",
  "snapshotBoundary": "LSN-102",
  "snapshotCursor": "P-50000",
  "snapshotCompleted": true,
  "replayPosition": "LSN-150",
  "cutoverBarrier": null,
  "status": "CATCHING_UP"
}
~~~

Checkpoint nên được lưu ở nơi bền vững, không chỉ trong memory của worker. Khi process restart, có thể tiếp tục từ cursor/offset đã xác nhận.

## 13. Tách snapshot writer và change projector

Snapshot loader và event projector có thể chạy song song, nhưng phải chia sẻ version policy và target index.

Một mô hình:

~~~text
Snapshot worker
    |
    +----> Read consistent snapshot
    |
    +----> Transform batches
    |
    +----> Bulk write with sourceVersion
                    |
                    v
                products-v2
                    ^
                    |
Change projector     |
    |                |
    +----> Read CDC/outbox
    |
    +----> Apply upsert/delete with sourceVersion
~~~

Nếu cả hai writer có thể ghi cùng document, external versioning hoặc một cơ chế serialization theo aggregate là cần thiết. Nếu không có version guard, nên buộc snapshot hoàn tất trước khi replay bắt đầu.

### 13.1. Chỉ một thành phần sở hữu version policy

Không để snapshot worker dùng một quy tắc ID/version và event projector dùng quy tắc khác. Cả hai phải thống nhất:

- Cùng document ID.
- Cùng sourceVersion semantics.
- Cùng transform logic.
- Cùng delete/tombstone behavior.
- Cùng quy tắc xử lý stale version.

Nếu event có version 20 nhưng snapshot row không có version tương ứng, không thể dùng external versioning để giải quyết race một cách đáng tin cậy. Cần bổ sung version nguồn hoặc thay đổi trình tự bootstrap.

## 14. Cutover bằng alias

Sau khi index mới đã được nạp và bắt kịp change stream, chuyển ứng dụng sang index mới.

Không nên thay đổi tên index trong mọi service hoặc cấu hình theo nhiều bước rời rạc. Dùng alias giúp giữ tên logic ổn định.

Ví dụ:

~~~text
products-read  -> products-v1
products-write -> products-v1
~~~

Sau khi bootstrap:

~~~text
products-read  -> products-v2
products-write -> products-v2
~~~

### 14.1. Tách read alias và write alias

Read alias dùng cho truy vấn. Write alias dùng cho ghi. Hai alias có thể được chuyển cùng một thao tác alias update.

Điều này giúp:

- Ứng dụng không phải biết index vật lý đang hoạt động.
- Có thể tạo index version mới song song.
- Cutover bằng cluster state update.
- Có thể giữ index cũ để rollback.

Nếu dùng một alias trỏ nhiều index, cần xác định write index rõ ràng. Với read alias, tránh để cùng một document tồn tại ở cả index cũ và mới rồi trả kết quả trùng ngoài ý muốn.

### 14.2. Atomic alias switch

Elasticsearch hỗ trợ nhiều alias actions trong một request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Các alias actions trong một request được áp dụng như một thay đổi cluster state thống nhất. Điều này tránh khoảng thời gian ứng dụng nhìn thấy alias đã bị gỡ nhưng chưa được gắn vào index mới.

### 14.3. Barrier trước cutover

Một trình tự cutover an toàn:

1. Ghi nhận high watermark H của CDC/outbox.
2. Đợi projector xử lý đến H trên index mới.
3. Kiểm tra không còn lỗi item chưa giải quyết trước H.
4. Đảm bảo các event mới tiếp tục được tiêu thụ sau H.
5. Chuyển read alias và write alias trong một alias request.
6. Xác nhận alias trỏ đến index mới.
7. Tiếp tục theo dõi lag và lỗi.

Nếu ứng dụng ghi trực tiếp vào Elasticsearch thay vì đi qua source event stream, cần một cơ chế barrier khác: tạm dừng writer trong thời gian ngắn, chờ request đang chạy hoàn tất, ghi nốt phần thay đổi còn thiếu rồi mới switch. Không cutover khi vẫn còn request ghi vào index cũ mà không được mirror sang index mới.

### 14.4. Spring Data và alias

Có thể cấu hình @Document indexName trỏ tới alias logic thay vì tên index vật lý:

~~~java
@Document(indexName = "products-write")
public class ProductIndexDocument {
    // ...
}
~~~

Read operation có thể dùng products-read thông qua IndexCoordinates hoặc cấu hình tương ứng. Khi alias chuyển đích, code ứng dụng tiếp tục dùng tên alias ổn định.

Với bootstrap, writer nên chỉ định target index vật lý mới một cách tường minh để không ghi nhầm vào alias đang phục vụ production. Sau cutover, các thao tác bình thường dùng write alias.

## 15. Kiểm tra index mới trước khi chuyển alias

Không chỉ kiểm tra tổng số document. Hai index có thể có cùng count nhưng chứa dữ liệu khác nhau.

### 15.1. Kiểm tra số lượng

So sánh:

- Số row nguồn trong snapshot.
- Số document được bulk thành công.
- Số tombstone.
- Số event replay.
- Số item thất bại đang chờ xử lý.
- Count theo partition, tenant hoặc category.

Nếu source có filter loại bỏ dữ liệu, cần tính expected count theo đúng điều kiện đó.

### 15.2. Kiểm tra nội dung mẫu

Lấy mẫu theo ID từ nguồn và index mới, so sánh:

- ID.
- Field bắt buộc.
- Field được transform.
- SourceVersion.
- Trạng thái deleted.
- Quan hệ/nested object.
- Các field phục vụ filter, sort và aggregation.

Nên lấy mẫu có chủ đích từ các nhóm dữ liệu khác nhau, bao gồm bản ghi mới, bản ghi cũ, dữ liệu thiếu field, dữ liệu có nhiều nested entries và bản ghi đã bị xóa.

### 15.3. Kiểm tra truy vấn thực tế

Chạy bộ query đại diện trên index mới:

- Full-text search.
- Filter theo keyword.
- Range query.
- Sort.
- Aggregation.
- Nested query nếu có.
- Phân trang.
- Query loại tombstone.

Mapping và analyzer mới có thể làm thay đổi relevance hoặc kết quả lọc dù document count đúng.

### 15.4. Kiểm tra freshness

Xác nhận target đã xử lý tới barrier offset. Đếm event lag bằng số lượng và tuổi event. Không cutover khi có poison event chưa xử lý nếu event đó có thể ảnh hưởng kết quả nghiệp vụ.

## 16. Xử lý lỗi và tiếp tục sau crash

Bootstrap có thể kéo dài hàng giờ hoặc nhiều ngày. Job phải có khả năng dừng và tiếp tục mà không nạp thiếu hoặc làm sai dữ liệu.

### 16.1. Checkpoint snapshot

Lưu cursor sau khi batch được xử lý đầy đủ. Nếu job crash:

1. Đọc checkpoint cuối.
2. Mở lại consistent snapshot nếu snapshot vẫn còn hiệu lực.
3. Tiếp tục từ cursor tương ứng.
4. Nếu snapshot không còn hiệu lực, tạo snapshot mới và xác định lại watermark/replay window.

Không tiếp tục cursor cũ trên một snapshot mới mà không chứng minh được semantics tương thích.

### 16.2. Bulk item failures

Bulk API có thể trả HTTP 200 nhưng một số item thất bại. Cần:

- Đọc errors và từng item response.
- Retry lỗi tạm thời như 429 với backoff.
- Sửa mapping hoặc dữ liệu với lỗi permanent.
- Ghi lỗi vào dead-letter queue khi không thể xử lý ngay.
- Không đánh dấu batch hoàn tất nếu còn item chưa có trạng thái cuối cùng theo chính sách.

Không retry toàn bộ batch một cách mù quáng. Các item đã thành công có thể bị ghi lại hoặc gây side effect nếu operation không idempotent.

### 16.3. Event replay bị giao lặp

Nếu event đã ghi vào Elasticsearch nhưng consumer crash trước khi commit offset, event sẽ được giao lại. Dùng eventId, sourceVersion và operation idempotent để bảo đảm kết quả cuối không đổi.

### 16.4. Poison event

Một event sai mapping hoặc dữ liệu không hợp lệ có thể khiến consumer liên tục thất bại. Không để một poison event chặn vô hạn mọi event sau đó nếu kiến trúc cho phép cô lập.

Đưa event vào dead-letter queue với:

- Event ID.
- Aggregate ID/version.
- Log position hoặc offset.
- Error type/reason.
- Payload đã được bảo vệ.
- Số lần thử.

Sau khi sửa lỗi, replay event theo thứ tự hoặc rebuild aggregate tương ứng. Chỉ bỏ qua event khi có quyết định nghiệp vụ rõ ràng và reconciliation xác nhận trạng thái đích.

## 17. Rollback sau cutover

Giữ index cũ trong một khoảng thời gian rollback. Tuy nhiên, rollback chỉ an toàn nếu hiểu index cũ đã nhận những thay đổi nào sau cutover.

### 17.1. Giữ hai index được cập nhật trong thời gian quan sát

Trong một cửa sổ ngắn sau cutover, projector có thể tiếp tục ghi cả index mới và cũ. Nếu index mới gặp lỗi nghiêm trọng, chuyển read alias về index cũ.

Điều này tăng chi phí ghi và cần kiểm soát version/offset cho cả hai đích. Chỉ giữ dual projection trong khoảng thời gian có mục đích rõ ràng.

### 17.2. Nếu index cũ không còn được cập nhật

Nếu sau cutover chỉ index mới nhận event, index cũ sẽ ngày càng stale. Khi rollback, ứng dụng có thể quay lại dữ liệu cũ.

Các lựa chọn:

- Tiếp tục dual-project trong rollback window.
- Trước khi rollback, replay change stream vào index cũ đến một barrier mới.
- Tạo một index rollback khác từ nguồn chuẩn.

Không xóa index cũ ngay sau cutover nếu chưa hoàn tất thời gian quan sát và chưa có bản sao phục hồi phù hợp.

## 18. Phương án khi nguồn dữ liệu cũ là Elasticsearch index

Nếu dữ liệu cũ nằm trong một Elasticsearch index thay vì database, vẫn cần snapshot và change capture. Có thể dùng Point in Time (PIT) cùng search_after để đọc một view ổn định của index cũ.

### 18.1. PIT và search_after

PIT giữ một view index ổn định trong thời gian đọc. search_after phân trang theo sort values thay vì offset sâu.

Ví dụ query:

~~~http
POST /products-v1/_pit?keep_alive=2m
~~~

Sau đó search trên PIT:

~~~http
POST /_search
{
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "2m"
  },
  "size": 500,
  "sort": [
    { "_shard_doc": "asc" }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Trang tiếp theo dùng search_after với sort values của hit cuối cùng. Cần giữ PIT còn hiệu lực và lưu cursor bền vững theo quy trình đọc.

### 18.2. PIT không tự ghi nhận thay đổi sau snapshot

PIT cung cấp một view ổn định của index tại thời điểm tạo PIT. Nó không tự cung cấp change log để cập nhật target với mọi thay đổi phát sinh sau đó.

Nếu ứng dụng vẫn ghi vào index cũ, cần:

- Mirror các thay đổi mới sang target bằng outbox/event ở tầng ứng dụng.
- Hoặc tạm dừng ghi trong giai đoạn snapshot và cutover.
- Hoặc có một change log độc lập để replay.

Không thể chỉ mở PIT, đọc hết document rồi giả định target đã bắt kịp các lần ghi xảy ra sau khi PIT được tạo.

### 18.3. Reindex API

Elasticsearch Reindex API có thể sao chép document từ index nguồn sang index đích. Tuy nhiên, một lần reindex đơn lẻ không tự giải quyết mọi thay đổi đồng thời nếu nguồn tiếp tục được cập nhật.

Nếu dùng Reindex API:

- Tạo target mapping/settings trước.
- Xác định nguồn và target rõ ràng.
- Xử lý version/conflicts nếu có.
- Dùng change capture hoặc maintenance window cho phần thay đổi mới.
- Kiểm tra task completion và failures.

Reindex API cũng không tự tạo transaction xuyên suốt giữa index cũ và index mới.

## 19. Những lỗi thường gặp

**Quét dữ liệu rồi cutover ngay.** Các thay đổi phát sinh trong lúc quét có thể không có trong index mới. Cần CDC/outbox hoặc maintenance window.

**Bắt đầu CDC sau khi snapshot đã chạy lâu.** Những thay đổi xảy ra trước lúc capture bắt đầu có thể bị mất. Bắt đầu capture trước hoặc phối hợp snapshot với log position.

**Dùng timestamp làm watermark duy nhất.** Transaction commit order, clock skew và độ chính xác timestamp có thể tạo khoảng trống. Dùng log sequence hoặc outbox position có semantics rõ.

**Không dùng consistent snapshot.** Các trang có thể phản ánh thời điểm khác nhau. Dùng transaction snapshot phù hợp hoặc CDC connector hỗ trợ snapshot mode.

**Để snapshot ghi đè event mới.** Dữ liệu cũ có thể thắng dữ liệu mới do race. Dùng trình tự snapshot/replay hoặc source version guard.

**Bỏ qua delete event.** Document bị xóa trong lúc bootstrap có thể sống lại khi snapshot ghi muộn. Dùng tombstone/version hoặc bảo đảm replay và snapshot ordering.

**Physical delete rồi giả định version được giữ mãi.** Metadata delete có retention hữu hạn. Tombstone bền vững phù hợp hơn với replay window dài.

**Dùng event delta nhưng không kiểm soát thứ tự.** Event giao lặp hoặc đến sai thứ tự có thể làm trạng thái sai. Dùng aggregate version, partition key hoặc full-state event.

**Commit consumer offset trước khi ghi target.** Crash có thể làm event bị mất khỏi replay. Commit sau khi ghi hoặc lưu trạng thái xử lý bền vững.

**Không kiểm tra item failures của bulk.** HTTP 200 vẫn có thể chứa document thất bại. Duyệt từng item và retry subset lỗi.

**Đánh dấu checkpoint trước khi bulk hoàn tất.** Crash có thể làm job bỏ qua dữ liệu chưa ghi. Chỉ tiến checkpoint sau khi batch đạt trạng thái cuối.

**Dùng dual-write trực tiếp như một transaction.** Một đích có thể thành công, đích khác thất bại. Dùng outbox, retry và reconciliation.

**Cutover khi consumer lag còn lớn.** Index mới chưa phản ánh các thay đổi gần nhất. Đợi barrier offset và xử lý hết lỗi trước barrier.

**Chỉ so sánh document count.** Count bằng nhau không chứng minh nội dung giống nhau. So sánh version, sample, aggregate và query thực tế.

**Xóa index cũ ngay sau cutover.** Có thể cần rollback hoặc đối chiếu. Giữ index cũ theo retention window.

**Rollback về index cũ đã stale.** Sau cutover, index cũ có thể không nhận thay đổi mới. Tiếp tục dual-project hoặc replay trước rollback.

## 20. Quy trình bootstrap an toàn

Một quy trình thực tế có thể triển khai theo các bước:

1. Xác định nguồn dữ liệu chuẩn và target index version mới.
2. Tạo mapping, settings, analyzer và alias cần thiết cho target.
3. Bảo đảm mọi thay đổi nguồn được ghi vào CDC/outbox bền vững.
4. Bắt đầu capture trước snapshot và xác định watermark nhất quán.
5. Mở consistent snapshot tại boundary đã chọn.
6. Đọc snapshot theo keyset/cursor ổn định.
7. Transform dữ liệu bằng cùng mapper được dùng cho event projection.
8. Bulk write vào target, kiểm tra item result và lưu checkpoint.
9. Sau khi snapshot hoàn tất, replay change stream sau watermark.
10. Dùng sourceVersion, idempotency và tombstone để chống stale write, duplicate và resurrection.
11. Tiếp tục catch-up trong lúc kiểm tra dữ liệu và query.
12. Ghi nhận barrier offset và đợi target xử lý đến barrier.
13. Kiểm tra không còn item failure chưa giải quyết trước barrier.
14. So sánh count, version, sample, delete state và truy vấn nghiệp vụ.
15. Chuyển read/write alias bằng một alias request.
16. Tiếp tục consumer trên index mới và theo dõi lag/error.
17. Giữ index cũ trong rollback window hoặc tiếp tục dual projection.
18. Sau thời gian ổn định, dọn index cũ và tombstone theo retention policy.

## 21. Ví dụ kiến trúc với Spring Data Elasticsearch

Một thiết kế có thể tách ba thành phần:

- Snapshot reader đọc dữ liệu nguồn theo consistent snapshot.
- Document mapper tạo cùng một dạng ProductIndexDocument cho snapshot và event.
- Elasticsearch writer bulk ghi document vào target index.
- Event projector xử lý CDC/outbox và áp dụng version guard.

### 21.1. Document model

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-write")
public class ProductIndexDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private double price;

    @Field(type = FieldType.Long)
    private long sourceVersion;

    @Field(type = FieldType.Boolean)
    private boolean deleted;

    // Constructors, getters và setters
}
~~~

sourceVersion là version nghiệp vụ từ nguồn. deleted biểu diễn tombstone nếu hệ thống chọn lưu delete marker trong index.

### 21.2. Mapper dùng chung

~~~java
public class ProductIndexMapper {

    public ProductIndexDocument fromSnapshot(ProductRow row) {
        ProductIndexDocument document = new ProductIndexDocument();
        document.setId(row.id());
        document.setName(row.name());
        document.setPrice(row.price());
        document.setSourceVersion(row.version());
        document.setDeleted(false);
        return document;
    }

    public ProductIndexDocument fromEvent(ProductChanged event) {
        ProductIndexDocument document = new ProductIndexDocument();
        document.setId(event.productId());
        document.setName(event.name());
        document.setPrice(event.price());
        document.setSourceVersion(event.aggregateVersion());
        document.setDeleted(false);
        return document;
    }

    public ProductIndexDocument tombstone(ProductDeleted event) {
        ProductIndexDocument document = new ProductIndexDocument();
        document.setId(event.productId());
        document.setSourceVersion(event.aggregateVersion());
        document.setDeleted(true);
        return document;
    }
}
~~~

Đây là ví dụ rút gọn. Mapper thực tế cần xử lý đầy đủ field, null semantics, nested objects, analyzer input và schema version.

### 21.3. Snapshot reader và bulk writer

~~~java
public class ProductBootstrapService {

    private final ProductSnapshotRepository source;
    private final ProductIndexMapper mapper;
    private final ProductBootstrapWriter writer;
    private final BootstrapCheckpointStore checkpoints;

    public void bootstrap(SnapshotHandle snapshot) {
        String cursor = checkpoints.lastProductId();

        while (true) {
            List<ProductRow> rows =
                source.readNextPage(snapshot, cursor, 500);

            if (rows.isEmpty()) {
                break;
            }

            List<ProductIndexDocument> documents = rows.stream()
                .map(mapper::fromSnapshot)
                .toList();

            writer.writeBatch(documents);

            cursor = rows.get(rows.size() - 1).id();
            checkpoints.saveLastProductId(cursor);
        }

        checkpoints.markSnapshotCompleted();
    }
}
~~~

Ví dụ này minh họa keyset cursor và checkpoint. Trong triển khai thực tế, writer phải cung cấp kết quả từng item; chỉ lưu checkpoint khi mọi document trong batch đã được ghi thành công hoặc đã được đưa vào durable retry/DLQ theo chính sách. SnapshotHandle phải giữ cùng một consistent snapshot hoặc đại diện cho snapshot đã được materialize.

### 21.4. Event projector

~~~java
public class ProductChangeProjector {

    private final ProductIndexMapper mapper;
    private final VersionAwareProductWriter writer;
    private final EventCheckpointStore checkpoints;

    public void handle(ProductEvent event) {
        switch (event.type()) {
            case PRODUCT_CHANGED ->
                writer.upsert(mapper.fromEvent(event.asChanged()));
            case PRODUCT_DELETED ->
                writer.upsert(mapper.tombstone(event.asDeleted()));
        }

        checkpoints.markProcessed(event.position());
    }
}
~~~

VersionAwareProductWriter phải áp dụng sourceVersion một cách nguyên tử khi ghi. Nếu event đã cũ hơn document hiện tại, không được ghi đè. Nếu ghi thành công rồi process crash trước khi commit offset, event được giao lại nhưng lần ghi sau phải idempotent.

### 21.5. Vì sao không chỉ dùng ElasticsearchOperations.save?

ElasticsearchOperations.save rất phù hợp cho thao tác ghi thông thường theo mapping Spring Data. Tuy nhiên, nếu bootstrap cho phép snapshot và event chạy đồng thời, cần bảo vệ version theo nguồn.

Không nên giả định save tự động dùng sourceVersion trong entity để từ chối ghi cũ. SourceVersion chỉ là một field trong source trừ khi ứng dụng ánh xạ nó thành external version hoặc tự kiểm tra/ghi có điều kiện.

Nếu cần external versioning hoặc thao tác bulk có metadata version riêng, dùng Elasticsearch Java API Client hoặc API Spring Data cụ thể có hỗ trợ version semantics trong phiên bản dự án.

## 22. Checklist trước khi cutover

Trước khi chuyển alias, cần xác nhận:

- [ ] Target index có mapping/settings đúng.
- [ ] Snapshot được đọc từ một consistent view.
- [ ] Snapshot boundary và change stream position đã được xác định.
- [ ] Change capture bắt đầu trước hoặc đồng bộ chính xác với snapshot.
- [ ] Mọi trang snapshot đã được ghi và checkpoint đúng.
- [ ] Bulk item failures đã được xử lý.
- [ ] Event sau watermark đã được replay.
- [ ] Consumer đã xử lý đến cutover barrier.
- [ ] Event lặp không tạo sai dữ liệu.
- [ ] Event cũ không ghi đè version mới.
- [ ] Delete không làm document sống lại.
- [ ] Count, sample, sourceVersion và query nghiệp vụ đã được kiểm tra.
- [ ] Read alias và write alias có target rõ ràng.
- [ ] Kế hoạch rollback và retention của index cũ đã sẵn sàng.

## 23. Tài liệu tham khảo

- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): bulk indexing, response từng item và xử lý lỗi.
- [Elasticsearch - Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index): document ID, versioning và index operation.
- [Elasticsearch - Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control): sequence number, primary term và kiểm soát ghi đồng thời.
- [Elasticsearch - Aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html): alias actions và chuyển index đích.
- [Elasticsearch - Point in Time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html): giữ một view ổn định khi đọc và phân trang.
- [Elasticsearch - Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html): sao chép document giữa các index và theo dõi task.
- [Spring Data Elasticsearch - Bulk operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): BulkOperations và ElasticsearchOperations.
- [Debezium - Snapshotting](https://debezium.io/documentation/reference/stable/connectors/index.html): cơ chế snapshot và change capture của các connector CDC.
- [Debezium - Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): phát event từ transactional outbox.

Tên API, builder method và cơ chế snapshot/CDC cụ thể phụ thuộc phiên bản Spring Data Elasticsearch, Elasticsearch Java API Client, database và connector. Hãy kiểm tra tài liệu tương ứng với dependency và hạ tầng đang chạy. Nguyên tắc quan trọng là snapshot phải có ranh giới nhất quán, mọi thay đổi sau ranh giới phải được giữ lại và replay, còn version/idempotency/tombstone bảo vệ target trước event trùng hoặc đến sai thứ tự.
