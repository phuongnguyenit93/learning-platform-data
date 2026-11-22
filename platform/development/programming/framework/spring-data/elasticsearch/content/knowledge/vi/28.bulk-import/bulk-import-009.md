# Refresh policy khi nhập dữ liệu và đánh đổi tốc độ

Elasticsearch là hệ thống tìm kiếm near-real-time (NRT): document đã được ghi thành công chưa chắc xuất hiện ngay trong kết quả `_search`. Document chỉ trở nên nhìn thấy qua search sau khi shard được refresh. Vì vậy, khi nhập dữ liệu bằng Index API hoặc Bulk API, ứng dụng cần chọn thời điểm refresh phù hợp giữa độ mới của kết quả tìm kiếm và throughput ghi.

Refresh policy quyết định request ghi có yêu cầu refresh ngay, chờ lần refresh kế tiếp hay để Elasticsearch refresh theo lịch. Ba lựa chọn thường gặp là `false`, `true` và `wait_for`. Ngoài ra, có thể điều chỉnh `index.refresh_interval` để thay đổi tần suất refresh của index, đặc biệt trong các đợt bulk load lớn.

Lựa chọn phù hợp phụ thuộc vào cách ứng dụng đọc dữ liệu sau khi ghi:

- Nếu người dùng cần tìm thấy document ngay sau mỗi lần ghi, ưu tiên `refresh=wait_for` hoặc `refresh=true` ở đúng điểm cần read-after-write.
- Nếu nhập dữ liệu liên tục với throughput cao, thường để refresh mặc định hoặc tăng interval.
- Nếu nạp hàng triệu document vào index mới, có thể tạm tắt periodic refresh, nhập theo bulk rồi refresh một lần sau khi hoàn tất.

## 1. Refresh là gì?

Elasticsearch lưu dữ liệu vào Lucene index. Khi một document được index hoặc cập nhật, thay đổi được ghi nhận trong các cấu trúc nội bộ và translog, nhưng searcher hiện tại chưa nhất thiết nhìn thấy thay đổi đó. Refresh mở các segment mới để chúng có thể được tìm kiếm.

```text
Ứng dụng gửi index/bulk request
             |
             v
Elasticsearch ghi thay đổi
             |
             +----> Realtime GET có thể đọc document mới
             |
             v
       Chưa refresh
             |
             +----> _search chưa chắc thấy document
             |
             v
          Refresh
             |
             v
       Searcher mới
             |
             v
       _search thấy dữ liệu
```

Refresh là thao tác làm dữ liệu đã ghi trở nên nhìn thấy qua search. Nó không đồng nghĩa với flush, force merge hoặc commit nghiệp vụ.

### Near-real-time khác với real-time

Elasticsearch cung cấp GET theo ID với khả năng realtime mặc định: một document vừa ghi thường có thể được đọc bằng GET ngay cả trước lần refresh kế tiếp. Search dựa trên Lucene searcher nên chỉ thấy thay đổi sau refresh.

Ví dụ:

```http
PUT /products/_doc/p-100
Content-Type: application/json

{
  "name": "Wireless Headphones"
}
```

Ngay sau khi request ghi thành công, thao tác sau có thể đọc document:

```http
GET /products/_doc/p-100
```

Nhưng truy vấn tìm kiếm:

```http
POST /products/_search
{
  "query": {
    "term": {
      "_id": "p-100"
    }
  }
}
```

có thể chưa thấy document cho tới khi shard được refresh.

## 2. Refresh interval mặc định

`index.refresh_interval` điều khiển khoảng thời gian giữa các lần refresh tự động của index. Giá trị mặc định phổ biến là `1s` đối với index đang được tìm kiếm. Elasticsearch có thể tối ưu refresh cho index không có hoạt động search trong một khoảng thời gian; khi cấu hình workload, hãy kiểm tra setting thực tế thay vì giả định mọi index luôn refresh đúng mỗi giây.

Kiểm tra setting:

```http
GET /products/_settings?include_defaults=true&filter_path=*.settings.index.refresh_interval,*.defaults.index.refresh_interval
```

Ví dụ đặt interval thành 5 giây:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "5s"
  }
}
```

Giá trị lớn hơn giảm tần suất refresh và thường cải thiện throughput indexing, nhưng tăng độ trễ trước khi document xuất hiện trong search. Giá trị nhỏ giúp dữ liệu mới nhanh được tìm thấy hơn nhưng tạo nhiều segment nhỏ và tăng công việc merge.

### Một số giá trị thường gặp

| Giá trị | Hành vi | Trường hợp sử dụng |
|---|---|---|
| `1s` | Refresh thường xuyên, độ trễ tìm kiếm thấp | Tìm kiếm gần realtime cho ứng dụng tương tác |
| `5s` hoặc `10s` | Refresh ít thường xuyên hơn | Ingestion liên tục, chấp nhận dữ liệu trễ vài giây |
| `30s` | Giảm thêm overhead refresh | Hệ thống ưu tiên throughput hơn độ mới tức thời |
| `-1` | Tắt periodic refresh | Bulk load lớn hoặc giai đoạn nhập dữ liệu có kiểm soát |

Các giá trị trên là ví dụ để lựa chọn và đo lường, không phải quy tắc cố định cho mọi index.

## 3. Ba giá trị refresh của request ghi

Index API, Update API và Bulk API hỗ trợ tham số `refresh` với các lựa chọn chính:

| Giá trị | Ý nghĩa | Đánh đổi |
|---|---|---|
| `false` | Không yêu cầu refresh do request này; để refresh theo lịch | Throughput tốt hơn, search có thể thấy dữ liệu trễ |
| `true` | Yêu cầu refresh ngay các shard bị ảnh hưởng bởi request | Read-after-write qua search nhanh hơn, tăng chi phí refresh |
| `wait_for` | Chờ lần refresh kế tiếp làm thay đổi nhìn thấy qua search | Không chủ động ép refresh ngay, thường cân bằng hơn giữa visibility và throughput |

`false` là lựa chọn mặc định nếu không chỉ định tham số. Nó không tắt refresh tự động của index; nó chỉ có nghĩa request ghi không yêu cầu refresh ngay.

## 4. `refresh=false`: để Elasticsearch refresh theo lịch

Ví dụ:

```http
POST /products/_doc/p-101?refresh=false
Content-Type: application/json

{
  "name": "Mechanical Keyboard"
}
```

Request ghi document và trả kết quả mà không chờ search visibility. Khi refresh tự động tiếp theo diễn ra, document sẽ xuất hiện trong search.

Đây thường là lựa chọn phù hợp cho:

- Ingestion liên tục với nhiều document.
- Bulk import không yêu cầu search thấy từng batch ngay.
- Event stream hoặc log indexing.
- Các pipeline mà consumer đọc dữ liệu sau một khoảng trễ chấp nhận được.

Không nên gọi `refresh=true` sau từng document chỉ để bảo đảm dữ liệu được tìm thấy ngay nếu yêu cầu nghiệp vụ không thực sự cần độ trễ thấp đến vậy.

## 5. `refresh=true`: refresh ngay sau request

Ví dụ với Index API:

```http
PUT /products/_doc/p-102?refresh=true
Content-Type: application/json

{
  "name": "USB-C Hub"
}
```

Sau khi request hoàn tất, các shard bị ảnh hưởng được refresh để thay đổi có thể nhìn thấy qua search.

Với Bulk API:

```http
POST /products/_bulk?refresh=true
Content-Type: application/x-ndjson

{ "index": { "_id": "p-103" } }
{ "name": "Monitor Stand" }
{ "index": { "_id": "p-104" } }
{ "name": "Laptop Sleeve" }
```

Bulk request trên thực hiện nhiều action và yêu cầu refresh sau request. Refresh được thực hiện cho các shard tham gia request; nó không có nghĩa mọi shard của toàn cluster đều bị refresh.

### Vì sao `refresh=true` làm giảm throughput?

Refresh tạo searcher/segment mới và làm phát sinh công việc quản lý segment. Nếu ứng dụng gửi nhiều request nhỏ với `refresh=true`, mỗi request có thể gây thêm một lần refresh. Hệ quả thường gặp:

- Nhiều segment nhỏ hơn.
- Tăng chi phí merge segment.
- Tăng CPU và I/O.
- Giảm throughput indexing.
- Tăng độ trễ của các request search hoặc write khi cluster chịu tải.

Nếu cần ghi 10.000 document, một bulk request với refresh sau cùng thường hiệu quả hơn 10.000 request đơn lẻ đều yêu cầu refresh.

## 6. `refresh=wait_for`: chờ dữ liệu có thể tìm thấy

`wait_for` yêu cầu request ghi chờ cho tới khi một lần refresh làm thay đổi của request nhìn thấy qua search. Khác với `true`, nó không chủ động ép một lần refresh ngay lập tức; request có thể được hoàn tất bởi lần refresh định kỳ kế tiếp hoặc một refresh do request khác kích hoạt.

Ví dụ:

```http
PUT /products/_doc/p-105?refresh=wait_for
Content-Type: application/json

{
  "name": "Wireless Mouse"
}
```

Sau khi request trả về thành công, document đã được refresh và có thể tìm thấy qua search.

### Khi nào nên dùng `wait_for`?

- Một thao tác ghi cần ngay sau đó chạy search để dựng trang kết quả.
- Người dùng vừa tạo dữ liệu và giao diện cần tìm thấy dữ liệu đó ngay sau khi API ghi trả về.
- Muốn đợi visibility nhưng không muốn ép refresh tức thời cho mọi request.

### `wait_for` vẫn có độ trễ

Nếu refresh interval là 1 giây, request có thể phải chờ gần một chu kỳ refresh, tùy thời điểm ghi. Nếu index đang bận hoặc refresh chậm, thời gian chờ có thể lớn hơn.

### Cẩn thận khi tắt refresh interval

Nếu `index.refresh_interval` được đặt thành `-1`, periodic refresh bị tắt. Request dùng `refresh=wait_for` có thể chờ mãi cho tới khi có một refresh khác được kích hoạt, ví dụ refresh thủ công. Không dùng `wait_for` trong giai đoạn tắt refresh nếu ứng dụng không chủ động tạo refresh.

## 7. So sánh `true` và `wait_for`

| Tiêu chí | `refresh=true` | `refresh=wait_for` |
|---|---|---|
| Có yêu cầu visibility sau khi request hoàn tất? | Có | Có |
| Chủ động ép refresh? | Có | Không, chờ refresh kế tiếp |
| Có thể chờ periodic refresh? | Thường không cần chờ chu kỳ kế tiếp | Có |
| Chi phí refresh riêng cho request | Có thể phát sinh refresh ngay | Có thể được gộp với refresh định kỳ hoặc do request khác |
| Latency request | Có thể tăng do refresh | Có thể tăng do phải chờ |
| Phù hợp | Cần refresh ngay có chủ đích | Cần read-after-write qua search nhưng muốn tránh ép refresh riêng |

Nếu nhiều request đồng thời dùng `wait_for`, Elasticsearch phải quản lý các listener đang chờ refresh. Quá nhiều request chờ có thể tạo áp lực. Với nhiều document, thường gom thành một bulk request rồi dùng một chính sách refresh phù hợp thay vì gửi nhiều request nhỏ chờ riêng lẻ.

## 8. Refresh API thủ công

Có thể yêu cầu refresh một index hoặc một số index bằng Refresh API:

```http
POST /products/_refresh
```

Hoặc:

```http
POST /products,inventory/_refresh
```

Refresh API hữu ích sau một đợt bulk load hoặc khi một bước workflow cần bảo đảm dữ liệu đã có thể tìm kiếm. Nó không thay thế cơ chế ghi và không phải thao tác commit/flush.

Không gọi refresh sau mỗi document. Hãy gom nhiều thao tác ghi rồi refresh một lần khi có yêu cầu visibility rõ ràng.

## 9. Refresh khác Flush và Force Merge

Ba khái niệm này dễ bị nhầm:

| Thao tác | Mục tiêu | Có làm dữ liệu mới searchable ngay? |
|---|---|---|
| Refresh | Mở searcher mới để nhìn thấy segment mới | Có |
| Flush | Thực hiện Lucene commit và bắt đầu translog generation mới | Không phải mục đích chính của flush; refresh visibility là việc riêng |
| Force merge | Gộp segment thành ít segment lớn hơn | Không dùng để thay refresh định kỳ |

Refresh phục vụ search visibility. Flush liên quan tới commit/translog và độ bền dữ liệu. Force merge là thao tác tối ưu segment thường dành cho index gần như không còn ghi.

Không gọi `_flush` để thay cho `_refresh` khi mục tiêu chỉ là làm document xuất hiện trong search. Cũng không chạy force merge thường xuyên trên index đang nhận ghi liên tục.

## 10. Tác động tới segment và merge

Lucene ghi dữ liệu thành các segment bất biến. Refresh làm segment mới có thể được tìm kiếm. Khi refresh quá thường xuyên, index có thể tạo nhiều segment nhỏ. Elasticsearch phải merge các segment này để quản lý chi phí tìm kiếm và lưu trữ.

```text
Nhiều request ghi nhỏ + refresh=true
             |
             v
       Nhiều segment nhỏ
             |
             v
       Merge thường xuyên
             |
             v
       CPU / I/O tăng
             |
             v
       Throughput ghi giảm
```

Tăng refresh interval hoặc gom ghi theo bulk có thể giảm số lần tạo segment nhỏ. Tuy nhiên, refresh quá thưa làm search visibility trễ hơn. Mục tiêu là chọn điểm cân bằng phù hợp với SLA của sản phẩm.

## 11. Tăng `refresh_interval` cho ingestion liên tục

Nếu hệ thống nhập dữ liệu liên tục nhưng không cần search thấy ngay từng document, có thể tăng refresh interval.

Ví dụ đặt 10 giây:

```http
PUT /events/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "10s"
  }
}
```

Hệ quả:

- Ít lần refresh hơn.
- Thường giảm overhead tạo segment nhỏ.
- Throughput indexing có thể tăng.
- Dữ liệu mới có thể mất tới khoảng interval mới để xuất hiện trong search, tùy tải và hoạt động refresh.

Đây là cấu hình cấp index. Nếu có nhiều index, mỗi index có thể có refresh interval riêng. Hãy điều chỉnh đúng index/alias và kiểm tra setting sau khi cập nhật.

## 12. Tạm tắt refresh trong bulk load lớn

Với một đợt nạp dữ liệu lớn vào index mới hoặc index đang không phục vụ search realtime, có thể tạm tắt periodic refresh bằng `-1`.

### Bước 1: Ghi lại setting hiện tại

```http
GET /products/_settings?include_defaults=true
```

Lưu giá trị `index.refresh_interval` hiện tại để khôi phục đúng sau bulk load. Không mặc định luôn khôi phục về `1s`, vì index có thể đã được cấu hình khác.

### Bước 2: Tắt periodic refresh

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
```

### Bước 3: Gửi bulk request với refresh mặc định

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-201" } }
{ "name": "Keyboard", "category": "accessories" }
{ "index": { "_id": "p-202" } }
{ "name": "Gaming Mouse", "category": "accessories" }
{ "index": { "_id": "p-203" } }
{ "name": "4K Monitor", "category": "displays" }
```

Trong giai đoạn này, search có thể không thấy các document mới. Ứng dụng vẫn cần kiểm tra `errors` và từng item trong bulk response; refresh policy không làm bulk request trở thành transaction.

### Bước 4: Khôi phục refresh interval

Ví dụ index ban đầu dùng 1 giây:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
```

Trong thực tế, dùng chính giá trị đã lưu ở bước 1.

### Bước 5: Refresh một lần sau khi nhập

```http
POST /products/_refresh
```

Sau bước này, document đã nhập có thể được tìm kiếm. Có thể kiểm tra bằng `_count` hoặc `_search` với điều kiện đại diện.

### Sơ đồ bulk load

```text
Đọc refresh_interval cũ
          |
          v
Đặt refresh_interval = -1
          |
          v
Nhập dữ liệu theo Bulk API
          |
          v
Kiểm tra mọi bulk item
          |
          v
Khôi phục refresh_interval cũ
          |
          v
POST /index/_refresh
          |
          v
Kiểm tra search visibility
```

### Luôn khôi phục setting khi job lỗi

Nếu bulk load thất bại giữa chừng, đừng để index bị tắt refresh vô thời hạn. Job orchestration nên có bước cleanup/finally để khôi phục setting, kể cả khi một batch ném exception hoặc process cần đánh dấu trạng thái lỗi.

Nếu index được dùng bởi nhiều tiến trình, chỉ một job nên chịu trách nhiệm thay đổi refresh interval trong giai đoạn bulk load. Hai job cùng thay đổi setting có thể khôi phục sai giá trị hoặc làm search visibility khó dự đoán.

## 13. Chọn refresh policy theo loại workload

| Workload | Lựa chọn gợi ý | Lý do |
|---|---|---|
| API tạo một sản phẩm và ngay sau đó cần search thấy sản phẩm | `wait_for` | Đợi visibility mà không nhất thiết ép refresh ngay |
| Quy trình kiểm thử cần xác nhận document ngay lập tức | `true` hoặc manual refresh | Giảm sự bất định của test |
| Event ingestion liên tục, chấp nhận trễ vài giây | `false` và interval lớn hơn | Giảm overhead refresh |
| Bulk load index mới với hàng triệu document | Tạm đặt `-1`, bulk, restore và refresh một lần | Tránh refresh liên tục trong lúc nạp |
| Ghi theo batch và chỉ cần search thấy sau mỗi batch | `wait_for` hoặc refresh một lần sau batch | Cân bằng visibility và số lần refresh |
| Log/metric ingestion có throughput cao | `false`, interval theo SLA | Ưu tiên ingestion throughput |
| Dữ liệu ít thay đổi nhưng yêu cầu search mới ngay sau một workflow | `wait_for` ở cuối workflow | Chỉ chờ một lần visibility ở điểm cần thiết |

Không nên áp dụng một refresh policy duy nhất cho mọi request trong hệ thống. Các luồng ghi khác nhau có thể có SLA visibility khác nhau.

## 14. Bulk API và refresh policy

Bulk API nhận nhiều action trong một request. Tham số `refresh` được áp dụng cho request bulk, không phải từng action riêng lẻ.

Ví dụ:

```http
POST /products/_bulk?refresh=wait_for
Content-Type: application/x-ndjson

{ "index": { "_id": "p-301" } }
{ "name": "USB Cable" }
{ "index": { "_id": "p-302" } }
{ "name": "USB Charger" }
{ "index": { "_id": "p-303" } }
{ "name": "USB Dock" }
```

Request chờ cho tới khi các thay đổi của bulk request nhìn thấy qua search. Điều này thường hợp lý hơn việc gọi từng Index API với `refresh=true`.

### Kiểm tra Bulk response

Bulk response có thể trả HTTP 200 nhưng một số item vẫn thất bại:

```json
{
  "errors": true,
  "items": [
    { "index": { "_id": "p-301", "status": 201 } },
    {
      "index": {
        "_id": "p-302",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
```

Refresh chỉ quyết định thời điểm thay đổi được nhìn thấy qua search. Nó không khắc phục mapping error và không bảo đảm mọi item trong bulk đều thành công. Ứng dụng phải kiểm tra `errors` và từng item.

## 15. Cấu hình RefreshPolicy trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp enum `RefreshPolicy` để biểu diễn chính sách refresh trong các API hỗ trợ.

Các giá trị tương ứng:

| Spring Data | Elasticsearch REST | Ý nghĩa |
|---|---|---|
| `RefreshPolicy.NONE` | `false` | Không yêu cầu refresh riêng cho request |
| `RefreshPolicy.IMMEDIATE` | `true` | Refresh ngay |
| `RefreshPolicy.WAIT_UNTIL` | `wait_for` | Chờ refresh kế tiếp |

### Khai báo trên `@Document`

Có thể đặt refresh policy mặc định cho các thao tác ghi của entity bằng annotation `@Document` trong các phiên bản Spring Data Elasticsearch hỗ trợ thuộc tính này:

```java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

@Document(
    indexName = "products",
    refreshPolicy = RefreshPolicy.WAIT_UNTIL
)
public class ProductDocument {
    // fields
}
```

Với cấu hình này, thao tác ghi gắn với entity có thể dùng `WAIT_UNTIL` theo metadata của mapping. Hãy kiểm tra version Spring Data Elasticsearch của dự án vì các overload và phạm vi áp dụng refresh policy có thể khác nhau giữa các phiên bản.

### Refresh thủ công bằng `IndexOperations`

Khi ứng dụng đã ghi xong một batch và muốn refresh rõ ràng:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
```

Hoặc lấy index operations từ entity class:

```java
IndexOperations indexOperations = operations.indexOps(ProductDocument.class);
indexOperations.refresh();
```

API này phù hợp khi muốn gom nhiều lần ghi rồi chủ động refresh một lần ở ranh giới batch/workflow.

### Bulk write trong Spring Data

Khi dùng `ElasticsearchOperations` để bulk index, chọn `BulkOptions` hoặc cấu hình refresh policy theo API của version đang dùng. Ví dụ ở các phiên bản có hỗ trợ builder refresh policy:

```java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions bulkOptions = BulkOptions.builder()
    .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
    .build();
```

Sau đó truyền `bulkOptions` vào phương thức bulk operation tương ứng của `ElasticsearchOperations`. Tên overload và cách gọi bulk index thay đổi theo phiên bản; hãy dùng đúng API của dependency dự án. Nếu không cần visibility ngay sau batch, dùng chính sách không yêu cầu refresh và để index refresh theo lịch.

## 16. Refresh trong Repository và ElasticsearchOperations

Repository abstraction giúp ghi entity thuận tiện, nhưng refresh policy thường được quyết định bởi metadata entity hoặc cấu hình của operation/client.

Ví dụ:

```java
productRepository.save(product);
```

Lệnh `save` không nên được hiểu mặc định là document chắc chắn đã searchable ngay khi method trả về. Nếu ứng dụng cần tìm document vừa lưu, hãy:

- Cấu hình refresh policy phù hợp cho entity/operation.
- Hoặc gọi `IndexOperations.refresh()` ở điểm cần đồng bộ.
- Hoặc thiết kế luồng đọc dùng GET theo ID nếu chỉ cần lấy document vừa ghi.

Không gọi refresh sau mọi `save()` trong một vòng lặp ingestion lớn. Hãy dùng bulk operation và refresh một lần theo batch hoặc theo SLA.

## 17. Test và refresh

Integration test thường gặp tình huống:

```java
repository.save(product);

List<ProductDocument> results =
    repository.findByName("Wireless Headphones");

assertThat(results).hasSize(1);
```

Test có thể thất bại ngẫu nhiên nếu search chạy trước lần refresh kế tiếp. Có vài cách xử lý:

### Cách 1: Dùng `WAIT_UNTIL` trong test

Đảm bảo write operation chờ tới khi document searchable. Cách này mô phỏng hành vi read-after-write nhưng làm test chờ refresh.

### Cách 2: Refresh index sau khi nạp fixture

```java
repository.saveAll(products);
operations.indexOps(ProductDocument.class).refresh();

List<ProductDocument> results = repository.findAll();
```

Đây thường là cách rõ ràng cho test fixture: nạp dữ liệu trước, refresh một lần, sau đó thực hiện assertions.

### Cách 3: Dùng refresh policy cho request test

Nếu API ghi hỗ trợ refresh policy theo operation, có thể đặt `IMMEDIATE` cho test nhỏ cần visibility tức thì. Không nên mang cấu hình `IMMEDIATE` từ test sang production ingestion mà chưa đánh giá throughput.

### Không dùng sleep cố định

`Thread.sleep(1000)` không phải cách đồng bộ đáng tin cậy. Refresh interval có thể khác, cluster có thể bận và CI có thể chậm. Dùng refresh API hoặc `WAIT_UNTIL` để đồng bộ theo sự kiện thực tế.

## 18. Đánh đổi giữa throughput và search visibility

Refresh interval càng ngắn, dữ liệu càng nhanh xuất hiện trong search, nhưng chi phí refresh/segment càng thường xuyên. Refresh interval càng dài, throughput ghi thường tốt hơn, nhưng search có thể trả dữ liệu cũ lâu hơn.

```text
Refresh interval ngắn
    |
    +--> Search visibility nhanh
    +--> Nhiều refresh/segment nhỏ
    +--> Merge và CPU/I/O tăng
    +--> Throughput ghi có thể giảm

Refresh interval dài
    |
    +--> Ít refresh hơn
    +--> Ít overhead segment hơn
    +--> Throughput ghi có thể tăng
    +--> Search visibility trễ hơn
```

Không thể tối ưu cả hai phía vô hạn. Hãy xác định SLA: người dùng cần thấy dữ liệu mới trong 100 ms, 1 giây, 5 giây hay 30 giây? Từ đó chọn refresh policy và interval.

### Ví dụ lựa chọn theo SLA

| Yêu cầu search visibility | Cách tiếp cận có thể phù hợp |
|---|---|
| Ngay sau một thao tác đơn lẻ | `wait_for` hoặc `true` tại thao tác đó |
| Trong khoảng 1–2 giây | Refresh interval mặc định hoặc gần mức đó |
| Trong vòng 5–10 giây | Tăng interval và để `refresh=false` |
| Sau khi hoàn tất cả batch import | Tắt periodic refresh tạm thời rồi refresh một lần |
| Không yêu cầu search realtime | Interval dài hơn, đánh giá workload cụ thể |

## 19. Đo hiệu năng trước và sau khi đổi policy

Không nên chỉ dựa vào cảm giác “bulk nhanh hơn”. Hãy đo trên dữ liệu và cluster gần production.

Các chỉ số nên quan sát:

- Documents indexed mỗi giây.
- Bulk request latency p50/p95/p99.
- Search latency p50/p95/p99.
- CPU và heap trên data node.
- GC pause và allocation rate.
- Số segment trên shard.
- Merge time và merge throttling.
- Disk I/O và network throughput.
- Độ trễ từ lúc write thành công đến lúc search thấy document.
- Tỷ lệ bulk item thất bại.

Có thể kiểm tra segment:

```http
GET /products/_segments
```

Và theo dõi index stats:

```http
GET /products/_stats/indexing,refresh,merge,search
```

So sánh các kịch bản cùng dữ liệu, cùng bulk size và cùng số shard:

1. Refresh mặc định.
2. `refresh_interval` dài hơn.
3. Bulk request với `refresh=wait_for`.
4. Tắt periodic refresh trong bulk load rồi refresh một lần.

Ghi lại cả throughput và độ trễ search visibility. Một cấu hình làm write nhanh hơn nhưng khiến dữ liệu trễ quá SLA vẫn không phải cấu hình phù hợp.

## 20. Tối ưu Bulk API cùng Refresh Policy

Refresh chỉ là một yếu tố của tốc độ nhập dữ liệu. Bulk indexing còn phụ thuộc kích thước batch, số worker, số shard/replica, mapping, pipeline, network và khả năng xử lý của cluster.

Một số nguyên tắc:

- Dùng Bulk API thay vì gửi từng document nếu có thể.
- Điều chỉnh bulk request size theo số byte và thời gian xử lý, không chỉ theo số document.
- Bắt đầu với số worker vừa phải và tăng dần khi cluster còn dư tài nguyên.
- Tránh gửi quá nhiều bulk request đồng thời làm indexing pressure tăng.
- Chỉ lấy các field cần thiết trong pipeline xử lý.
- Dùng refresh interval dài hơn khi SLA cho phép.
- Với bulk load index mới, cân nhắc tắt periodic refresh trong giai đoạn nạp.
- Kiểm tra từng item trong bulk response và retry lỗi tạm thời có chọn lọc.
- Chỉ force merge khi index gần như không còn ghi và có mục tiêu vận hành rõ ràng.

### Không nhầm Bulk size với Refresh interval

Bulk size điều khiển số/khối lượng action trong một request. Refresh interval điều khiển tần suất shard tạo searcher mới. Tăng bulk size không tự động thay đổi refresh interval; hai tham số giải quyết hai nguồn overhead khác nhau.

## 21. Các rủi ro khi tắt refresh

Đặt `index.refresh_interval = -1` có thể cải thiện tốc độ bulk load, nhưng cần hiểu các hệ quả:

- Search không nhìn thấy dữ liệu mới cho tới khi có refresh.
- `refresh=wait_for` có thể chờ vô hạn nếu không có refresh nào xảy ra.
- Các ứng dụng khác đang đọc index có thể tiếp tục thấy snapshot cũ.
- Nếu job lỗi và quên khôi phục setting, index có thể không refresh tự động.
- Nhiều job cùng thay đổi setting có thể ghi đè cấu hình của nhau.
- Tắt refresh không có nghĩa tắt translog hoặc làm mất cơ chế durability mặc định.

Chỉ tắt refresh khi có ranh giới bulk load rõ ràng và có người/tiến trình chịu trách nhiệm khôi phục.

## 22. Refresh và durability

Refresh quyết định search visibility, không phải cam kết durability. Elasticsearch dùng translog và cơ chế flush/commit để quản lý độ bền dữ liệu. Với cấu hình mặc định, translog durability thường được đồng bộ theo request để bảo vệ các thao tác đã được xác nhận.

Vì vậy:

- Không cần gọi refresh để “lưu bền” document.
- Không dùng `refresh=false` như cách tắt durability.
- Không dùng flush thay cho refresh nếu mục tiêu là search visibility.
- Không thay đổi `index.translog.durability` chỉ để tối ưu refresh nếu chưa hiểu trade-off về mất dữ liệu khi sự cố.

Tách biệt hai yêu cầu: “ghi đã được Elasticsearch xác nhận an toàn” và “search đã nhìn thấy document”. Chúng được điều khiển bởi các cơ chế khác nhau.

## 23. Refresh với alias và nhiều index

Nếu ứng dụng ghi qua alias trỏ tới nhiều index hoặc alias rollover, refresh policy của request chỉ ảnh hưởng các shard tham gia thao tác ghi. `POST /alias/_refresh` có thể refresh các index mà alias đại diện.

Trong bulk load:

- Xác định index thực tế mà alias đang ghi.
- Điều chỉnh refresh interval trên đúng index cần nạp.
- Nếu alias trỏ nhiều index, kiểm tra setting từng index.
- Không vô tình tắt refresh trên index đang phục vụ workload tương tác khác.
- Sau khi nạp, khôi phục setting cho từng index đã thay đổi.

Với data stream, cần hiểu backing index write hiện tại và chính sách rollover. Không giả định thay đổi setting trên một backing index sẽ áp dụng cho các index được tạo trong tương lai; dùng index template để cấu hình mặc định cho index mới nếu phù hợp.

## 24. Lỗi thường gặp

### Nghĩ `refresh=false` là tắt refresh tự động

`false` chỉ không yêu cầu refresh do request ghi. Index vẫn refresh theo `index.refresh_interval` nếu periodic refresh đang bật.

### Dùng `refresh=true` sau mỗi document

Việc này có thể tạo nhiều segment nhỏ và giảm throughput. Gom dữ liệu bằng Bulk API và refresh theo batch hoặc theo SLA.

### Dùng `wait_for` khi refresh interval là `-1`

Request có thể chờ cho tới khi một refresh khác xảy ra. Trong bulk load tắt refresh, không dùng `wait_for` nếu chưa có bước manual refresh.

### Nghĩ `refresh=true` refresh toàn bộ cluster

Nó yêu cầu refresh các shard bị ảnh hưởng bởi request, không phải mọi shard của mọi index trong cluster.

### Nhầm refresh với flush

Refresh làm dữ liệu searchable; flush liên quan Lucene commit/translog. Dùng đúng API theo mục tiêu.

### Quên khôi phục `refresh_interval`

Sau bulk load, periodic refresh có thể vẫn bị tắt. Ghi lại setting cũ và khôi phục trong cleanup/finally.

### Kiểm tra HTTP status nhưng bỏ qua Bulk item errors

Bulk response có thể trả HTTP 200 với `errors: true`. Kiểm tra từng item trước khi refresh và đánh dấu batch thành công.

### Dùng sleep trong integration test

Sleep cố định không bảo đảm refresh đã xảy ra. Dùng `WAIT_UNTIL` hoặc gọi `IndexOperations.refresh()`.

### Force merge sau mỗi bulk batch

Force merge tốn tài nguyên và không thay refresh. Chỉ dùng khi index gần như không còn ghi và có lý do vận hành rõ ràng.

## 25. Quy trình triển khai ingestion có kiểm soát

Một pipeline nhập dữ liệu có thể triển khai theo trình tự:

1. Xác định SLA search visibility cho dữ liệu mới.
2. Chọn `refresh=false`, `true` hoặc `wait_for` cho từng loại thao tác.
3. Kiểm tra `index.refresh_interval` thực tế.
4. Dùng Bulk API để giảm overhead request.
5. Chọn bulk size và số worker theo đo lường.
6. Với bulk load lớn, lưu setting cũ rồi tạm đặt interval `-1` nếu workload cho phép.
7. Ghi dữ liệu và kiểm tra mọi bulk item.
8. Trong cleanup/finally, khôi phục refresh interval ban đầu.
9. Refresh thủ công một lần nếu cần dữ liệu searchable ngay sau load.
10. Xác nhận search visibility bằng query đại diện.
11. Theo dõi throughput, latency, segment, merge, CPU, heap và độ trễ search.
12. Điều chỉnh interval theo SLA và kết quả đo, không theo một giá trị mặc định cứng.

## 26. Kết luận

Refresh policy điều khiển thời điểm dữ liệu mới trở nên nhìn thấy qua search. `refresh=false` để index refresh theo lịch; `refresh=true` yêu cầu refresh ngay các shard bị ảnh hưởng; `refresh=wait_for` chờ lần refresh kế tiếp. `index.refresh_interval` điều chỉnh tần suất refresh tự động, trong khi Refresh API cho phép chủ động refresh ở ranh giới một batch hoặc workflow.

Refresh thường xuyên giúp search thấy dữ liệu mới nhanh hơn nhưng tạo nhiều segment nhỏ, tăng merge và giảm throughput ghi. Với ingestion liên tục, có thể tăng refresh interval nếu SLA cho phép. Với bulk load lớn, có thể tạm tắt periodic refresh, nhập bằng Bulk API, khôi phục setting cũ và refresh một lần sau khi hoàn tất. Trong Spring Data Elasticsearch, dùng `RefreshPolicy` và `IndexOperations.refresh()` theo API phiên bản dự án. Luôn phân biệt refresh với flush/durability, kiểm tra từng bulk item và bảo đảm khôi phục setting sau khi job lỗi.

## Tài liệu tham khảo

- [Elasticsearch – Near real-time search](https://www.elastic.co/docs/manage-data/data-store/near-real-time-search)
- [Elasticsearch – Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
- [Elasticsearch – Index API refresh parameter](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Index settings: `index.refresh_interval`](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Elasticsearch – Tune for indexing speed](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/indexing-speed)
- [Spring Data Elasticsearch – Object mapping and `@Document`](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
