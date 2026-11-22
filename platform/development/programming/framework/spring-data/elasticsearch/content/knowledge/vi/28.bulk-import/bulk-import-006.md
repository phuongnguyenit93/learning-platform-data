# Phân loại lỗi có thể retry và lỗi dữ liệu không hợp lệ

Khi nhập dữ liệu hàng loạt vào Elasticsearch, không phải mọi lỗi đều nên được xử lý giống nhau. Một số lỗi chỉ xuất hiện tạm thời do cluster quá tải, shard chưa sẵn sàng hoặc kết nối bị gián đoạn. Những lỗi khác xuất phát từ chính dữ liệu gửi lên, chẳng hạn trường sai kiểu, thiếu giá trị bắt buộc hoặc JSON không hợp lệ. Retry một bản ghi sai dữ liệu thường chỉ làm request thất bại thêm lần nữa; ngược lại, bỏ qua một lỗi tạm thời có thể làm mất dữ liệu đáng lẽ đã ghi được.

Với **Bulk API**, một request có thể chứa nhiều thao tác và Elasticsearch xử lý từng item riêng. Vì vậy, HTTP status của toàn request chưa đủ để kết luận tất cả bản ghi thành công hay thất bại. Ứng dụng cần đọc cờ **errors**, duyệt từng phần tử trong **items**, phân loại lỗi theo status và error type, rồi quyết định retry, sửa dữ liệu, đưa vào hàng chờ cách ly hoặc báo lỗi vận hành.

Bài này sử dụng index **products** và các thao tác index, create, update. Nội dung tập trung vào phân loại lỗi retryable và lỗi dữ liệu không hợp lệ, xử lý partial success, backoff, idempotency, dead-letter queue và cách triển khai trong Spring Data Elasticsearch.

## 1. Vì sao phải phân loại lỗi?

Giả sử ứng dụng gửi một bulk request gồm 500 sản phẩm. Elasticsearch có thể ghi thành công 492 item, từ chối 5 item vì dữ liệu không phù hợp mapping và từ chối 3 item còn lại do node quá tải.

Nếu ứng dụng chỉ kiểm tra HTTP 200, nó có thể tưởng rằng cả 500 sản phẩm đã được ghi. Nếu ứng dụng retry toàn bộ request, 492 item thành công có thể bị gửi lại, tạo xung đột duplicate, ghi đè dữ liệu hoặc áp dụng script tăng số lượng nhiều lần.

Mỗi loại lỗi cần một hành động khác nhau:

- **Lỗi tạm thời:** chờ một khoảng thời gian rồi thử lại có giới hạn.
- **Lỗi dữ liệu:** cách ly bản ghi, sửa dữ liệu hoặc mapping rồi mới gửi lại.
- **Lỗi cấu hình/quyền:** sửa cấu hình, credential hoặc trạng thái index.
- **Xung đột nghiệp vụ:** đọc lại trạng thái và giải quyết theo quy tắc, không retry mù quáng.
- **Kết quả chưa rõ:** đối chiếu trạng thái bằng ID hoặc khóa idempotency trước khi gửi lại.

Một chiến lược retry tốt cần trả lời ba câu hỏi cho từng item:

1. Elasticsearch đã xác nhận thao tác thành công chưa?
2. Nếu thất bại, nguyên nhân có thể tự biến mất mà không sửa dữ liệu không?
3. Nếu gửi lại, thao tác có gây ghi trùng hoặc thay đổi dữ liệu thêm lần nữa không?

## 2. Bulk API có thể thành công một phần

Bulk API nhận nhiều action trong cùng request. Response thường có cấu trúc gồm:

- **errors:** cho biết có ít nhất một item thất bại hay không.
- **items:** danh sách kết quả tương ứng với các action đã gửi.
- Mỗi item chứa tên operation như index, create, update hoặc delete.
- Kết quả item có status, result hoặc error tùy trường hợp.

Ví dụ response rút gọn:

~~~json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "p-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "p-1002",
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
        "_id": "p-1003",
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

Trong ví dụ:

- p-1001 đã được tạo.
- p-1002 bị từ chối vì giá trị price không phù hợp mapping.
- p-1003 bị từ chối do Elasticsearch từ chối thực thi trong tình trạng áp lực tài nguyên.

HTTP response của bulk request có thể là 200 dù một số item thất bại. Do đó, ứng dụng phải kiểm tra **errors** và từng item trong **items**.

Thứ tự item trong response tương ứng với thứ tự action trong request. Có thể dùng ID để đối chiếu rõ ràng; không nên chỉ dựa vào vị trí nếu ứng dụng đã biến đổi hoặc lọc danh sách ở giữa quá trình xử lý.

## 3. Phân loại theo nguyên nhân, không chỉ theo status

Status code giúp định hướng, nhưng một status có thể bao gồm nhiều nguyên nhân. Hãy kết hợp:

- HTTP status hoặc status của từng item.
- **error.type**.
- **error.reason**.
- operation đã gửi (index/create/update/delete).
- trạng thái index, shard và cluster.
- liệu request có thể đã được thực hiện trước khi client timeout hay không.

Bảng dưới đây là hướng phân loại ban đầu, không phải luật tuyệt đối cho mọi phiên bản hoặc mọi cluster:

| Nhóm | Ví dụ status/type | Hướng xử lý |
|---|---|---|
| Từ chối tạm thời do quá tải | 429, es_rejected_execution_exception | Retry có backoff và giảm áp lực |
| Shard hoặc cluster tạm thời chưa sẵn sàng | Một số lỗi 503, unavailable_shards_exception | Retry có giới hạn sau khi kiểm tra trạng thái |
| Lỗi gateway hoặc mạng | 502, 503, 504, connection reset | Có thể retry; trước đó cần xét kết quả có thể đã được ghi |
| Request timeout | 408 hoặc client timeout | Kết quả có thể chưa rõ; đối chiếu và retry idempotent |
| Dữ liệu không hợp lệ | 400, mapper_parsing_exception, document_parsing_exception | Không retry nguyên trạng; cách ly và sửa dữ liệu |
| Query hoặc payload sai định dạng | 400, parse_exception, x_content_parse_exception, illegal_argument_exception | Sửa request hoặc producer |
| Script lỗi | 400, script_exception | Sửa script hoặc tham số; không retry nguyên trạng |
| Tài liệu đã tồn tại trong create-only | 409, resource_already_exists_exception | Xử lý duplicate theo nghiệp vụ |
| Xung đột phiên bản | 409, version_conflict_engine_exception | Đọc lại, tính lại hoặc dùng retry policy phù hợp |
| Thiếu tài liệu khi update/delete | 404, document_missing_exception | Kiểm tra ID và semantics; không retry mặc định |
| Index không tồn tại | 404, index_not_found_exception | Kiểm tra provisioning/alias; chỉ retry sau khi index được tạo |
| Không có quyền | 401 hoặc 403 | Sửa credential/quyền; không retry liên tục |
| Request quá lớn | 413 hoặc lỗi payload tương đương | Chia nhỏ bulk; kiểm tra kích thước từng document |
| Cluster block | Lỗi block do read-only hoặc disk watermark | Giải quyết nguyên nhân vận hành trước khi gửi lại |

Một status 429 thường cho thấy áp lực tài nguyên hoặc request bị từ chối tạm thời. Nhưng nếu cùng một document luôn gây circuit breaker do kích thước quá lớn, retry nhanh không giải quyết được vấn đề. Ngược lại, lỗi 404 index_not_found có thể là tạm thời trong lúc triển khai index, nhưng là lỗi cấu hình nếu tên index hoặc alias sai vĩnh viễn.

## 4. Lỗi retryable thường gặp

Các lỗi sau thường có thể thử lại sau khi chờ, với điều kiện ứng dụng có giới hạn và bảo đảm thao tác an toàn khi lặp:

### 429 Too Many Requests

Elasticsearch có thể trả 429 khi thread pool từ chối request do hàng đợi hoặc node đang chịu tải. Trong Bulk API, item có thể mang lỗi **es_rejected_execution_exception**.

Cách xử lý:

- Tạm dừng trước khi gửi lại.
- Dùng exponential backoff có jitter.
- Giảm số bulk request chạy đồng thời.
- Giảm batch size nếu request quá lớn hoặc xử lý quá lâu.
- Theo dõi thread pool rejection, CPU, heap và tốc độ indexing.

Không tăng số worker để “đẩy nhanh” khi cluster đang trả 429. Việc đó có thể tạo thêm request bị từ chối và làm tình hình xấu hơn.

### 503 và shard chưa sẵn sàng

Một số lỗi 503 hoặc **unavailable_shards_exception** có thể xuất hiện khi shard chưa hoạt động, node đang khởi động hoặc cluster đang phục hồi. Có thể retry sau khi kiểm tra trạng thái cluster.

Nếu index chưa được tạo hoặc shard không thể khởi tạo vì cấu hình sai, retry vô hạn sẽ không giúp. Cần phân biệt sự cố đang hồi phục với lỗi provisioning.

### 502, 504 và lỗi mạng

Gateway có thể trả 502/504, hoặc client nhận connection reset, socket timeout hay lỗi kết nối. Trong trường hợp này, client có thể không biết Elasticsearch đã xử lý request hay chưa.

Đây là **kết quả không chắc chắn**. Một request có thể đã được ghi thành công nhưng response bị mất trên đường về. Chỉ retry khi thao tác có tính idempotent hoặc ứng dụng có cách đối chiếu trạng thái.

### Timeout

Search/index/bulk request có thể timeout ở tầng client, proxy hoặc server. Cần xác định timeout nào xảy ra:

- Client timeout: client ngừng chờ response.
- Gateway timeout: proxy ngừng chờ upstream.
- Server timeout hoặc task bị hủy: request có thể đã bị hủy hoặc có kết quả một phần tùy API.

Không mặc định timeout nghĩa là không có dữ liệu nào được ghi. Hãy kiểm tra theo ID, operation key hoặc nguồn dữ liệu trước khi replay.

## 5. Lỗi dữ liệu không hợp lệ thường gặp

Lỗi dữ liệu thường có thể tái hiện nếu gửi lại cùng payload. Vì vậy, không retry nguyên trạng.

### Sai kiểu dữ liệu theo mapping

Mapping khai báo price là double nhưng producer gửi một chuỗi không chuyển đổi được:

~~~json
{
  "sku": "KB-1001",
  "price": "ninety dollars"
}
~~~

Elasticsearch có thể trả **mapper_parsing_exception**. Cần sửa producer hoặc dữ liệu trước khi gửi lại.

### Thiếu hoặc sai cấu trúc trường

Một index có thể đặt **dynamic: strict**, yêu cầu trường đúng schema. Document gửi thêm trường không được phép hoặc sai cấu trúc nested có thể bị từ chối.

~~~json
{
  "sku": "KB-1001",
  "unknownField": "unexpected"
}
~~~

Nếu mapping strict, đây là lỗi schema chứ không phải sự cố mạng.

### Ngày giờ không đúng format

Nếu mapping yêu cầu date theo định dạng đã cấu hình nhưng producer gửi ngày không hợp lệ, document sẽ không parse được. Cần chuẩn hóa ngày giờ, timezone và format ở nguồn.

### Giá trị enum không được hỗ trợ

Ứng dụng chỉ chấp nhận ACTIVE và INACTIVE, nhưng producer gửi ARCHIVED trong một trường bị kiểm soát bởi pipeline hoặc validation. Cần cập nhật hợp đồng dữ liệu hoặc chuyển đổi giá trị trước khi ghi.

### JSON hoặc NDJSON sai cú pháp

Bulk request dùng NDJSON: mỗi action metadata nằm trên một dòng và source/update body ở dòng tiếp theo khi cần. Thiếu newline cuối, sai cấu trúc hoặc serialize sai có thể làm request bị từ chối. Đây là lỗi producer/request, không phải lỗi tạm thời.

## 6. Phân biệt lỗi dữ liệu và lỗi mapping

Không phải mọi **mapper_parsing_exception** đều có nghĩa bản ghi nguồn sai. Nguyên nhân có thể nằm ở:

- Producer gửi giá trị sai kiểu.
- Mapping hiện tại không phù hợp với schema nghiệp vụ.
- Một index cũ có mapping khác index mới.
- Dynamic mapping suy luận kiểu từ tài liệu đầu tiên không phù hợp.
- Alias trỏ đến nhiều index có mapping không đồng nhất.
- Nested/object field có cấu trúc không như dự kiến.

Trước khi sửa từng bản ghi, hãy đọc mapping thực tế:

~~~http
GET /products/_mapping
~~~

Kiểm tra document gây lỗi và đối chiếu với schema producer. Nếu mapping sai, sửa mapping bằng quy trình phù hợp (thường tạo index mới và reindex khi cần thay đổi kiểu field), sau đó replay các bản ghi đã cách ly.

Không retry hàng nghìn document vào một index có mapping sai. Cần sửa nguyên nhân chung trước rồi mới replay.

## 7. Bảng quyết định retry ban đầu

Có thể dùng bảng sau làm chính sách khởi đầu, sau đó điều chỉnh theo error type và vận hành của hệ thống:

| Status / error type | Retry tự động? | Điều kiện |
|---|---|---|
| 429 es_rejected_execution_exception | Có | Backoff, giảm concurrency và giới hạn số lần |
| 503 unavailable_shards_exception | Có | Cluster/shard đang phục hồi; có giới hạn thời gian |
| 502 / 504 | Có điều kiện | Kết quả có thể chưa rõ; operation phải idempotent hoặc được đối chiếu |
| Client connection timeout | Có điều kiện | Không giả định request chưa được xử lý |
| 400 mapper_parsing_exception | Không | Sửa document hoặc mapping |
| 400 document_parsing_exception | Không | Sửa cấu trúc hoặc giá trị |
| 400 x_content_parse_exception | Không | Sửa JSON/NDJSON |
| 400 script_exception | Không | Sửa script hoặc params |
| 401 / 403 | Không | Sửa quyền hoặc credential |
| 404 document_missing_exception | Không mặc định | Kiểm tra ID và yêu cầu upsert |
| 404 index_not_found_exception | Chỉ khi provisioning có chủ đích | Chờ index/alias sẵn sàng, không retry vô hạn |
| 409 resource_already_exists_exception | Không | Xử lý duplicate/create-only |
| 409 version_conflict_engine_exception | Có điều kiện | Đọc lại và tính lại, hoặc dùng retry_on_conflict khi semantics cho phép |
| 413 Payload Too Large | Không gửi nguyên bulk lại | Chia nhỏ; xử lý riêng document quá lớn |
| Cluster read-only/block | Chưa retry | Giải quyết disk watermark hoặc block trước |

Không dùng status code một mình làm bộ phân loại cuối cùng. Hãy lưu error type và operation để có thể bổ sung quy tắc chính xác khi gặp lỗi mới.

## 8. Xử lý partial success: chỉ retry item thất bại

Một bulk request có thể gồm cả item thành công và thất bại. Ứng dụng nên tạo danh sách retry riêng chỉ từ các item cần retry.

Luồng tổng quát:

~~~text
Tạo bulk request
       |
       v
Gửi tới Elasticsearch
       |
       v
Đọc response.items
       |
       +---- item thành công ----> ghi nhận thành công
       |
       +---- lỗi retryable -----> retry queue
       |
       +---- lỗi dữ liệu -------> quarantine / DLQ
       |
       +---- lỗi cấu hình ------> cảnh báo và dừng pipeline
~~~

Không gửi lại toàn bộ 500 item chỉ vì một item có status 400. Làm như vậy vừa lãng phí tài nguyên vừa có thể tạo tác dụng phụ.

Ví dụ response có 100 item:

- 93 item thành công.
- 4 item lỗi mapping.
- 3 item bị 429.

Ứng dụng nên ghi nhận 93 thành công, đưa 4 item lỗi mapping vào quarantine và chỉ retry 3 item 429 sau backoff.

Cần giữ lại payload và metadata action ban đầu để có thể tái tạo đúng request cho từng item. Với bulk update, metadata và body của một action gồm hai dòng NDJSON; khi tách item, phải giữ đúng cặp action/body.

## 9. Exponential backoff và jitter

Nếu nhiều worker cùng nhận 429 rồi retry sau đúng một giây, chúng có thể cùng gửi lại và tiếp tục bị từ chối. Hiện tượng này tạo retry storm.

**Exponential backoff** tăng khoảng chờ theo số lần thử:

\[
d_n = \min(d_{\max}, d_0 \times 2^n)
\]

Trong đó:

- \(d_0\) là khoảng chờ ban đầu.
- \(n\) là số lần retry đã thực hiện.
- \(d_{\max}\) là giới hạn tối đa.

**Jitter** thêm yếu tố ngẫu nhiên để các worker không đồng bộ thời điểm retry.

Ví dụ full jitter:

\[
wait_n = random(0, \min(d_{\max}, d_0 \times 2^n))
\]

Một cấu hình minh họa:

| Lần retry | Khoảng chờ tối đa |
|---|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |

Đây là ví dụ, không phải giá trị bắt buộc. Có thể dùng Retry-After nếu tầng proxy hoặc dịch vụ có cung cấp header phù hợp. Cần đặt:

- Số lần retry tối đa.
- Tổng thời gian retry tối đa.
- Khoảng chờ tối đa.
- Giới hạn concurrency của retry worker.
- Chính sách đưa item vào DLQ khi hết ngân sách retry.

Không retry liên tục trong vòng lặp không có delay. Điều đó tiêu thụ CPU và làm cluster quá tải hơn.

## 10. Giảm batch size khi gặp quá tải hoặc payload quá lớn

Batch size ảnh hưởng đến lượng dữ liệu trong một request. Bulk quá lớn có thể tăng bộ nhớ, thời gian xử lý và xác suất timeout. Tuy nhiên, batch quá nhỏ lại tăng overhead mạng.

Nếu gặp 413 hoặc lỗi request quá lớn, chia bulk thành các phần nhỏ hơn. Nếu chỉ một document rất lớn, chia bulk không giải quyết được document đó; cần kiểm tra kích thước source, giới hạn field hoặc thiết kế lưu trữ.

Một chiến lược thích nghi:

1. Bắt đầu với batch theo số item và tổng byte mục tiêu.
2. Nếu gặp 429, giảm concurrency trước; có thể giảm batch size nếu request đang tạo áp lực.
3. Nếu gặp 413, chia đôi batch và gửi lại các phần nhỏ hơn.
4. Nếu một item vẫn thất bại khi đứng riêng, cách ly item đó.
5. Khi cluster ổn định, tăng batch size từ từ nếu throughput cần cải thiện.

Nên giới hạn cả **số item** lẫn **tổng kích thước byte**. 500 document nhỏ và 500 document có source rất lớn là hai request rất khác nhau.

Không có một batch size tối ưu áp dụng cho mọi cluster. Hãy đo heap, CPU, indexing throughput, rejection và latency trong điều kiện tải đại diện.

## 11. Idempotency quyết định có thể retry an toàn hay không

Một thao tác idempotent có thể được lặp lại mà không làm thay đổi kết quả cuối theo cách ngoài ý muốn. Điều này rất quan trọng khi client timeout và không biết request đã được xử lý hay chưa.

| Operation | Đặc tính khi gửi lại | Lưu ý |
|---|---|---|
| Index full document với ID cố định và payload giống nhau | Thường idempotent về source cuối | Cân nhắc pipeline, version và side effect bên ngoài |
| Update gán status = ACTIVE | Thường idempotent | Gửi lại cùng giá trị |
| Update script stock += 1 | Không idempotent | Retry có thể tăng thêm lần nữa |
| Create-only với ID cố định | Không tạo duplicate, lần sau có thể 409 | Cần phân biệt request đầu đã thành công nhưng response bị mất |
| Delete cùng ID | Thường idempotent về trạng thái cuối | Cần xác định 404 có phải kết quả chấp nhận được |
| Upsert partial doc gán giá trị cố định | Thường idempotent về các field được gán | Cẩn thận với script và dữ liệu khác thay đổi |

Ví dụ script không idempotent:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

Nếu request đã tăng stock từ 20 lên 21 nhưng response bị mất, gửi lại có thể tăng lên 22. Retry vì timeout mà không có idempotency key sẽ làm sai dữ liệu.

### Dùng ID sự kiện để chống áp dụng lặp

Với sự kiện nghiệp vụ như nhập kho, mỗi event nên có ID ổn định. Ứng dụng có thể lưu dấu event đã xử lý hoặc dùng mô hình dữ liệu đảm bảo một event chỉ được áp dụng một lần. Cách thực hiện phụ thuộc thiết kế hệ thống; chỉ có document ID sản phẩm chưa đủ để phân biệt hai lần nhập kho hợp lệ và một lần retry trùng.

Không nhầm **retry_on_conflict** với idempotency. retry_on_conflict xử lý xung đột phiên bản khi Update API thực hiện update; nó không phát hiện hai message nghiệp vụ giống nhau được gửi lại từ queue.

## 12. Xử lý 409 create conflict và version conflict

Status 409 có thể mang nhiều ý nghĩa.

### resource_already_exists_exception

Thường xảy ra với action **create** khi ID đã tồn tại. Đây không phải lỗi quá tải. Các hướng xử lý:

- Nếu nghiệp vụ yêu cầu create-only: báo duplicate hoặc đánh dấu bản ghi đã tồn tại theo chính sách.
- Nếu request trước có thể đã thành công nhưng response bị mất: đọc lại tài liệu, so sánh event key/version/payload để xác định kết quả.
- Nếu muốn cập nhật tài liệu hiện có: dùng update/upsert theo semantics phù hợp.

Không tự động chuyển mọi create conflict thành thành công. Hai document có cùng ID nhưng nội dung khác nhau có thể là xung đột dữ liệu cần điều tra.

### version_conflict_engine_exception

Lỗi này thường xuất hiện khi optimistic concurrency hoặc update đồng thời làm phiên bản thay đổi. Có thể xử lý bằng:

- Đọc lại tài liệu và tính lại thay đổi theo source mới.
- Dùng retry_on_conflict cho update có logic phù hợp.
- Trả conflict cho caller nếu người dùng phải giải quyết.
- Dùng if_seq_no và if_primary_term khi muốn bảo vệ phiên bản đã đọc.

Không retry lại một partial update dựa trên trạng thái cũ nếu việc đó có thể ghi đè thay đổi mới. Phải xác định update là gán giá trị tuyệt đối, tính toán trên giá trị hiện tại hay yêu cầu compare-and-set.

## 13. Dead-letter queue và quarantine

**Dead-letter queue (DLQ)** lưu các item không thể xử lý tiếp theo chính sách hiện tại. Nó giúp pipeline tiếp tục xử lý item tốt trong khi giữ lại item lỗi để điều tra hoặc replay.

Một record DLQ nên lưu đủ thông tin:

~~~json
{
  "eventId": "evt-90812",
  "index": "products",
  "documentId": "p-1002",
  "operation": "index",
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "errorReason": "failed to parse field [price]",
  "attempts": 1,
  "firstFailedAt": "2026-11-13T10:00:00Z",
  "lastFailedAt": "2026-11-13T10:00:00Z",
  "payload": {
    "sku": "KB-1002",
    "price": "ninety dollars"
  }
}
~~~

Đây là cấu trúc minh họa. DLQ thực tế cần có schema version, nguồn message, trace/correlation ID, lần thử cuối và trạng thái xử lý.

Phân biệt hai luồng:

- **Retry queue:** item có khả năng thành công sau khi chờ hoặc sau khi cluster phục hồi.
- **Quarantine/DLQ:** item cần con người hoặc quy trình sửa dữ liệu, mapping hay cấu hình trước khi replay.

Không đưa password, access token hoặc dữ liệu nhạy cảm không cần thiết vào log/DLQ. Payload có thể chứa dữ liệu cá nhân hoặc bí mật nghiệp vụ; cần áp dụng quyền truy cập, retention và masking phù hợp.

### Replay DLQ

Khi nguyên nhân đã được sửa:

1. Lấy một nhóm item trong DLQ.
2. Kiểm tra schema/version và payload.
3. Chuyển đổi hoặc sửa dữ liệu nếu cần.
4. Gửi lại bằng ID và idempotency key ổn định.
5. Kiểm tra từng item trong bulk response.
6. Đánh dấu replay thành công hoặc giữ lại lỗi mới.
7. Lưu lịch sử replay để tránh xử lý lặp không kiểm soát.

Không replay hàng triệu item cùng lúc ngay sau khi mapping được sửa. Bắt đầu với một nhóm nhỏ, xác nhận kết quả và tăng dần.

## 14. Lỗi request-level và lỗi item-level

Cần phân biệt request bị lỗi trước khi có kết quả item với lỗi của từng item trong response.

### Request-level failure

Ví dụ:

- Không kết nối được tới Elasticsearch.
- Request bị proxy từ chối.
- Credential không hợp lệ.
- NDJSON sai cú pháp ở mức toàn request.
- Index hoặc alias không tồn tại và request bị từ chối trước khi xử lý.
- Client timeout và không nhận được response.

Trong trường hợp này, ứng dụng có thể không có danh sách item thành công/thất bại. Nếu request có thể đã được gửi tới server, kết quả có thể không chắc chắn.

### Item-level failure

Elasticsearch trả response bulk có items, trong đó mỗi action có kết quả riêng. Có thể xác định item nào thành công, item nào lỗi và retry riêng.

Luồng xử lý nên giữ hai lớp:

~~~text
Gửi BulkRequest
      |
      +-- Không nhận được BulkResponse
      |       |
      |       +--> Request-level failure
      |              |
      |              +--> Xác định kết quả có chắc chắn không
      |              +--> Retry/reconcile theo idempotency
      |
      +-- Nhận BulkResponse
              |
              +--> errors = false: ghi nhận hoàn tất
              |
              +--> errors = true:
                       duyệt từng item
                         |
                         +--> success
                         +--> retryable
                         +--> invalid / conflict / config
~~~

Không dùng cùng một exception handler cho cả hai trường hợp. Request-level timeout có thể không cho biết item nào đã được xử lý; item-level response cung cấp thông tin cụ thể để retry chính xác.

## 15. Ví dụ phân loại item bằng Java

Một mô hình đơn giản có thể chuyển response item thành hành động:

~~~java
enum FailureAction {
    SUCCESS,
    RETRY,
    QUARANTINE,
    CONFLICT,
    CONFIGURATION_ERROR,
    INVESTIGATE
}
~~~

Hàm phân loại minh họa:

~~~java
FailureAction classify(int status, String errorType) {
    if (status >= 200 && status < 300) {
        return FailureAction.SUCCESS;
    }

    if (status == 429
            || status == 502
            || status == 503
            || status == 504) {
        return FailureAction.RETRY;
    }

    if (status == 400) {
        return FailureAction.QUARANTINE;
    }

    if (status == 401 || status == 403) {
        return FailureAction.CONFIGURATION_ERROR;
    }

    if (status == 409) {
        if ("resource_already_exists_exception".equals(errorType)) {
            return FailureAction.CONFLICT;
        }
        if ("version_conflict_engine_exception".equals(errorType)) {
            return FailureAction.CONFLICT;
        }
    }

    if (status == 404) {
        return FailureAction.QUARANTINE;
    }

    return FailureAction.INVESTIGATE;
}
~~~

Đây chỉ là bộ khung ban đầu. Production cần xem error type, operation, index state và chính sách nghiệp vụ. Ví dụ:

- 404 index_not_found có thể cần dừng pipeline để chờ provisioning, không nên đưa từng document vào DLQ.
- 404 document_missing khi update không upsert có thể là lỗi dữ liệu hoặc semantics.
- 400 circuit breaker hoặc lỗi tài nguyên có thể cần điều tra thay vì coi là bản ghi sai.
- 409 version conflict có thể được retry sau khi đọc lại nếu logic cho phép.
- 429 cần backoff và giảm áp lực.

Tách phân loại thành service riêng giúp thêm error type mới mà không rải điều kiện status khắp code.

## 16. Đọc từng item từ Elasticsearch Java API Client

Với Elasticsearch Java API Client, bulk response có cờ **errors()** và danh sách **items()**. Mỗi item chứa status và error khi thất bại.

Ví dụ khung xử lý:

~~~java
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkResponse response = elasticsearchClient.bulk(bulkRequest);

if (!response.errors()) {
    recordAllSuccessful(response.items());
} else {
    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            recordSuccess(item);
            continue;
        }

        int status = item.status();
        String errorType = item.error().type();
        String reason = item.error().reason();

        FailureAction action = classifier.classify(
                status,
                errorType
        );

        switch (action) {
            case RETRY -> retryQueue.enqueue(
                    item,
                    status,
                    errorType,
                    reason
            );
            case QUARANTINE -> deadLetterQueue.store(
                    item,
                    status,
                    errorType,
                    reason
            );
            case CONFLICT -> conflictHandler.handle(
                    item,
                    errorType,
                    reason
            );
            case CONFIGURATION_ERROR ->
                    pipeline.pauseAndAlert(errorType, reason);
            case INVESTIGATE ->
                    incidentQueue.store(item, status, errorType, reason);
            case SUCCESS -> recordSuccess(item);
        }
    }
}
~~~

Đoạn mã minh họa cấu trúc xử lý. Trong ứng dụng thực tế, item là metadata/result của bulk action, không nhất thiết chứa lại toàn bộ payload nguồn. Vì vậy, hãy giữ danh sách operation và payload ban đầu theo cùng ID hoặc correlation key để retry/DLQ có đủ dữ liệu.

Tên package, kiểu generic và chữ ký getter của Java API Client có thể khác theo phiên bản. Dùng dependency tương thích với cluster và Spring Boot của dự án; kiểm tra kiểu status/error trong client được quản lý trước khi đưa đoạn code vào build.

### Đối chiếu response với payload đã gửi

Trước khi gửi bulk, nên tạo cấu trúc giữ payload và metadata:

~~~java
record PendingOperation(
        String eventId,
        String documentId,
        String operation,
        ProductDocument payload
) {
}
~~~

Khi tạo BulkRequest, giữ danh sách PendingOperation theo đúng thứ tự. Response items trả về theo thứ tự action, có thể đối chiếu bằng index, ID và operation. Tốt hơn nữa, dùng eventId/correlation ID trong tầng ứng dụng để ghi nhận kết quả.

Không dựa vào error reason làm khóa duy nhất. Hai document khác nhau có thể cùng thất bại với một error type nhưng cần xử lý riêng.

## 17. Tích hợp với Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp các API bulk như **bulkIndex**, **bulkUpdate** và **bulkDelete** qua ElasticsearchOperations, tùy phiên bản. Các API này giúp chuyển đổi entity hoặc query object theo abstraction của Spring Data.

Ví dụ dạng gọi bulk index thường gặp:

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
                BulkOptions.defaultOptions(),
                IndexCoordinates.of("products")
        );
~~~

Cách gọi trên minh họa bulk indexing thông qua Operations. Hợp đồng trả về và cách lỗi được báo có thể thay đổi theo phiên bản và overload. Nếu API ném exception khi có item thất bại, hãy xem cause và thông tin lỗi bulk có sẵn; không tự giả định toàn bộ batch đều thất bại hoặc đều thành công.

Với yêu cầu phân loại từng item chính xác, đặc biệt khi cần giữ error type/status của từng operation, Elasticsearch Java API Client có thể cung cấp quyền kiểm soát trực tiếp hơn qua BulkResponse.

### Giữ payload để có thể retry

Khi dùng Spring Data, đừng chỉ giữ danh sách entity rồi bỏ đi sau khi gọi bulk. Hãy giữ batch gốc hoặc operation envelope cho đến khi xác nhận từng item đã thành công hoặc được chuyển sang retry/DLQ.

Một service có thể có cấu trúc:

~~~java
public void ingest(List<ProductDocument> batch) {
    try {
        bulkWriter.write(batch);
    } catch (RuntimeException exception) {
        failureHandler.handleBatchFailure(batch, exception);
    }
}
~~~

Đây mới là khung luồng xử lý. Nếu bulkWriter không cung cấp item-level result, failureHandler phải phân tích exception hoặc gửi lại theo chiến lược có kiểm soát. Đối với hệ thống cần partial success chính xác, nên dùng API trả về từng item result thay vì chỉ nhận một exception tổng quát.

Không bắt Exception rồi bỏ qua. Mọi item phải đi tới một trạng thái có thể kiểm tra: thành công, chờ retry, bị cách ly, xung đột cần xử lý hoặc pipeline đang tạm dừng.

## 18. Retry queue cần lưu những gì?

Một retry item nên có:

- Payload gốc hoặc tham chiếu tới payload lưu bền vững.
- Index/alias đích.
- Document ID.
- Operation type (index/create/update/delete).
- Event ID hoặc idempotency key.
- Error status và error type gần nhất.
- Số lần retry.
- Thời điểm thất bại đầu tiên và gần nhất.
- Thời điểm được phép retry tiếp theo.
- Schema version.
- Trace/correlation ID.
- Thông tin partition/offset nếu lấy từ message broker.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-90813",
  "index": "products",
  "documentId": "p-1003",
  "operation": "index",
  "attempt": 2,
  "nextAttemptAt": "2026-11-13T10:00:08Z",
  "lastError": {
    "status": 429,
    "type": "es_rejected_execution_exception"
  },
  "schemaVersion": 4,
  "payloadRef": "object-store://ingest/evt-90813"
}
~~~

Nếu payload lớn hoặc nhạy cảm, có thể lưu payload trong kho dữ liệu có kiểm soát và chỉ lưu tham chiếu trong queue. Cần bảo đảm payload vẫn tồn tại cho đến khi item được xử lý xong.

Retry queue nên có giới hạn dung lượng và chính sách retention. Nếu queue liên tục tăng, đó là tín hiệu pipeline đang không theo kịp hoặc cluster đang gặp vấn đề kéo dài.

## 19. Giới hạn retry và tránh retry storm

Retry không thể kéo dài vô hạn. Một chính sách vận hành nên xác định:

- Số lần thử tối đa, ví dụ 5 lần.
- Tổng thời gian thử lại tối đa, ví dụ 10 phút.
- Exponential backoff có jitter.
- Số worker retry tối đa.
- Tỷ lệ retry so với ingest bình thường.
- Điều kiện pause pipeline khi tỷ lệ lỗi vượt ngưỡng.
- Điều kiện chuyển item sang DLQ.

Các con số chỉ là ví dụ để minh họa. Hãy chọn theo SLA, tốc độ phục hồi cluster và thời hạn dữ liệu cần được ingest.

Nếu toàn bộ bulk batch liên tục bị 429, có thể giảm tốc độ producer, giảm concurrency hoặc tạm dừng tiêu thụ message. Nếu chỉ một số shard bị áp lực, cần theo dõi phân bố shard và node thay vì chỉ giảm tốc độ toàn hệ thống.

Một circuit breaker ở tầng ứng dụng có thể tạm dừng gửi request khi tỷ lệ lỗi tạm thời vượt ngưỡng. Khi cluster phục hồi, cho phép một số request thử nghiệm trước khi mở lại toàn bộ throughput.

## 20. Xử lý index không tồn tại và lỗi cấu hình

Không phải lỗi nào không thuộc nhóm dữ liệu đều nên retry tự động.

Ví dụ **index_not_found_exception**:

- Nếu deployment vừa tạo index và job chạy sớm hơn bước provisioning, có thể chờ index sẵn sàng trong một khoảng ngắn.
- Nếu tên index sai, alias chưa tồn tại hoặc môi trường thiếu cấu hình, retry sẽ không tự sửa được.
- Nếu index bị xóa ngoài ý muốn, cần quy trình khôi phục hoặc tạo lại có chủ đích.

Với 401/403, kiểm tra credential, role và quyền index. Không gửi hàng nghìn request tiếp tục khi account không có quyền.

Với cluster block do disk watermark hoặc index read-only, cần giải quyết dung lượng hoặc block trước. Retry liên tục trong lúc disk đầy chỉ làm tăng log và queue.

Nếu lỗi cấu hình ảnh hưởng toàn pipeline, nên **pause** consumer hoặc worker và phát cảnh báo. Không đưa mọi document vào DLQ vì payload có thể hoàn toàn hợp lệ.

## 21. Kiểm tra dữ liệu trước khi gửi bulk

Validation phía ứng dụng giúp phát hiện sớm các lỗi có thể dự đoán:

- ID không rỗng và đúng quy tắc.
- Trường bắt buộc có giá trị.
- Kiểu số nằm trong miền hợp lệ.
- Date/time theo định dạng thống nhất.
- Enum nằm trong tập được hỗ trợ.
- String không vượt giới hạn nghiệp vụ.
- Nested object và array đúng cấu trúc.
- Schema version được hỗ trợ.
- Operation type hợp lệ.

Ví dụ:

~~~java
public void validate(ProductDocument product) {
    if (product.id() == null || product.id().isBlank()) {
        throw new InvalidProductException("Product ID is required");
    }

    if (product.sku() == null || product.sku().isBlank()) {
        throw new InvalidProductException("SKU is required");
    }

    if (product.price() == null || product.price() < 0) {
        throw new InvalidProductException("Price must be non-negative");
    }

    if (product.stock() == null || product.stock() < 0) {
        throw new InvalidProductException("Stock must be non-negative");
    }
}
~~~

Validation phía ứng dụng không thay thế mapping Elasticsearch. Nó giúp thông báo lỗi gần nguồn hơn và đưa ra thông điệp dễ hiểu cho producer.

Nếu validation thất bại trước khi gửi request, có thể đưa record vào quarantine mà không tiêu tốn tài nguyên Elasticsearch. Cần giữ lại lỗi validation có cấu trúc, ví dụ field, rule và giá trị đã được masking phù hợp.

## 22. Phân loại lỗi theo từng operation

Cùng một status có thể có ý nghĩa khác nhau tùy operation.

| Operation | Lỗi | Cách hiểu |
|---|---|---|
| **index** | 409 version conflict khi dùng external version | Phiên bản nguồn đến trễ hoặc không đúng thứ tự |
| **create** | 409 resource already exists | ID đã có; duplicate hoặc request trước đã thành công |
| **update** | 404 document missing | Không có tài liệu và không bật upsert |
| **update** | 409 version conflict | Có cập nhật đồng thời hoặc điều kiện phiên bản không còn đúng |
| **delete** | 404 document missing | Có thể là kết quả chấp nhận được nếu delete idempotent theo nghiệp vụ |
| **mọi operation** | 429 rejected execution | Áp lực tài nguyên; có thể retry sau backoff |
| **index/update** | 400 mapper parsing | Payload hoặc mapping không tương thích |

Ví dụ, 409 của create không nên được xử lý như 409 version conflict của update. Một bên là điều kiện ID đã tồn tại; bên kia là phiên bản tài liệu thay đổi trong quá trình cập nhật.

Tương tự, 404 của delete có thể được coi là thành công theo trạng thái cuối nếu yêu cầu là “đảm bảo tài liệu không tồn tại”. Nhưng 404 của update không upsert thường cho thấy thiếu tài liệu cần cập nhật. Hãy quyết định theo semantics nghiệp vụ, không theo status riêng lẻ.

## 23. Thứ tự dữ liệu và sự kiện đến trễ

Khi ingest từ message broker hoặc nhiều producer, cùng một document có thể nhận event không theo thứ tự. Một event cũ đến sau event mới có thể ghi đè dữ liệu mới nếu dùng index với ID cố định và không có kiểm soát version.

Các lựa chọn:

- Dùng external version hoặc version type phù hợp với mô hình nguồn.
- Dùng sequence/timestamp nghiệp vụ và chỉ áp dụng event mới hơn.
- Dùng script kiểm tra version trong source trước khi cập nhật.
- Dùng optimistic concurrency khi client đọc rồi cập nhật.
- Đưa event xung đột vào quy trình reconcile.

Không dùng thời gian nhận tại Elasticsearch thay cho thời gian phát sinh nghiệp vụ nếu producer có thể gửi trễ. Timestamp nguồn phải được xác định rõ và đồng bộ.

Nếu dùng external version, hiểu rõ semantics external và external_gte trước khi triển khai. external_gte cho phép cùng version ghi đè theo điều kiện tương ứng; điều này có thể phù hợp với replay idempotent nhưng cũng có thể che giấu hai payload khác nhau có cùng version. Cần có quy tắc version rõ ràng.

## 24. Theo dõi ingest và cảnh báo

Một pipeline ingest nên theo dõi ít nhất:

- Số item đã gửi.
- Số item thành công.
- Số item thất bại theo status và error type.
- Tỷ lệ retry.
- Số item trong retry queue.
- Số item trong DLQ/quarantine.
- Tuổi của item lâu nhất trong queue.
- Số lần retry trung bình và tối đa.
- Bulk latency và bytes/request.
- Tỷ lệ 429 và rejected execution.
- Số 400 mapper parsing theo index/field.
- Số 409 create conflict và version conflict.
- Số timeout/request không rõ kết quả.
- Heap, CPU, disk và indexing pressure của cluster.

Tách metric theo **error type** và **index** để nhận ra lỗi mapping chỉ xảy ra ở một nhóm dữ liệu. Không chỉ ghi một bộ đếm chung bulk_failed.

### Ví dụ dashboard

| Metric | Ý nghĩa |
|---|---|
| bulk_items_total | Tổng số item đã xử lý |
| bulk_items_succeeded_total | Item thành công |
| bulk_items_retry_total | Item đang hoặc đã được retry |
| bulk_items_quarantined_total | Item bị cách ly |
| bulk_retry_queue_depth | Độ dài retry queue |
| bulk_dlq_depth | Số item đang chờ điều tra |
| bulk_request_duration | Thời gian mỗi bulk request |
| bulk_item_failure{type,status} | Lỗi theo loại và status |
| bulk_payload_bytes | Kích thước bulk request |
| bulk_unknown_outcome_total | Request timeout hoặc mất response cần reconcile |

Đặt cảnh báo khi retry queue tăng liên tục, DLQ vượt ngưỡng, tỷ lệ 429 cao hoặc lỗi mapping xuất hiện đột biến sau một lần deploy.

## 25. Ví dụ luồng ingest có retry và DLQ

Một service ingest có thể tách các trách nhiệm:

~~~java
public void processBatch(List<PendingOperation> operations) {
    BulkOutcome outcome = bulkWriter.execute(operations);

    for (ItemOutcome item : outcome.items()) {
        switch (item.action()) {
            case SUCCESS -> successRecorder.record(item);
            case RETRY -> retryQueue.schedule(
                    item.originalOperation(),
                    item.nextAttemptAt()
            );
            case QUARANTINE -> deadLetterQueue.store(
                    item.originalOperation(),
                    item.failure()
            );
            case CONFLICT -> conflictResolver.resolve(item);
            case PAUSE_PIPELINE -> pipelineController.pause(
                    item.failure()
            );
        }
    }
}
~~~

Các kiểu **BulkOutcome**, **ItemOutcome**, **PendingOperation** và các interface queue trong ví dụ là mô hình ứng dụng, không phải class có sẵn của Spring Data Elasticsearch.

Tách các thành phần giúp:

- Bulk writer chỉ chịu trách nhiệm gửi và lấy response.
- Classifier quyết định loại lỗi.
- Retry queue lên lịch thử lại.
- DLQ lưu dữ liệu không hợp lệ.
- Conflict resolver xử lý duplicate hoặc version conflict.
- Pipeline controller dừng ingest khi lỗi cấu hình ảnh hưởng toàn hệ thống.
- Metrics ghi nhận kết quả theo từng item.

Không để logic retry, mapping validation, queue và HTTP response tập trung trong một vòng lặp lớn. Khi một loại lỗi mới xuất hiện, có thể bổ sung quy tắc mà không làm thay đổi toàn bộ pipeline.

## 26. Kiểm thử phân loại lỗi

Nên kiểm thử cả classifier và hành vi xử lý bulk response.

### Unit test cho classifier

~~~java
@Test
void classifiesRejectedExecutionAsRetryable() {
    assertEquals(
            FailureAction.RETRY,
            classifier.classify(
                    429,
                    "es_rejected_execution_exception"
            )
    );
}

@Test
void classifiesMappingErrorAsQuarantine() {
    assertEquals(
            FailureAction.QUARANTINE,
            classifier.classify(
                    400,
                    "mapper_parsing_exception"
            )
    );
}

@Test
void classifiesCreateDuplicateAsConflict() {
    assertEquals(
            FailureAction.CONFLICT,
            classifier.classify(
                    409,
                    "resource_already_exists_exception"
            )
    );
}
~~~

### Test partial success

Tạo response giả lập có:

- Một item thành công.
- Một item 400 mapper parsing.
- Một item 429 rejected execution.

Xác nhận:

- Item thành công không được gửi lại.
- Item 400 được chuyển vào DLQ/quarantine.
- Item 429 được lên lịch retry.
- Số lượng và ID item ở từng đích chính xác.

### Integration test

Với Elasticsearch tương thích, có thể:

- Gửi một document hợp lệ.
- Gửi một document sai kiểu theo mapping.
- Gửi create hai lần với cùng ID.
- Tạo xung đột update đồng thời.
- Kiểm tra bulk response có errors và item status tương ứng.

Không dựa hoàn toàn vào mock để xác nhận error type của Elasticsearch. Error type và chi tiết response cần được kiểm tra bằng integration test trên phiên bản cluster thực tế hoặc môi trường tương thích.

## 27. Các lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bulk HTTP 200 nhưng dữ liệu thiếu | Không kiểm tra errors và từng item | Duyệt toàn bộ items |
| Retry lại cả batch | Không tách item thành công và thất bại | Chỉ retry failed items |
| 400 lặp đi lặp lại | Retry payload sai mapping/JSON | Quarantine và sửa dữ liệu |
| 429 tăng sau khi bật retry | Retry đồng loạt, không backoff | Exponential backoff, jitter, giảm concurrency |
| Tồn kho tăng gấp đôi | Retry script cộng sau timeout | Idempotency key hoặc event deduplication |
| Create retry trả 409 | Request đầu có thể đã thành công hoặc ID đã tồn tại | Đối chiếu tài liệu và event ID |
| Update trả 409 liên tục | Cạnh tranh ghi hoặc version cũ | Đọc lại, tính lại hoặc điều chỉnh concurrency |
| Retry queue không giảm | Lỗi cấu hình hoặc cluster kéo dài | Pause pipeline, sửa nguyên nhân |
| DLQ tăng sau deploy | Producer/schema không tương thích mapping | Kiểm tra version và mapping, replay sau khi sửa |
| Bulk timeout nhưng không biết item nào ghi | Response bị mất sau khi server xử lý | Reconcile theo ID/version/event key |
| Item bị mất khi tách retry | Không giữ payload/action gốc | Lưu operation envelope cho đến khi hoàn tất |
| Mọi lỗi đều bị ghi là invalid data | Classifier chỉ dựa vào exception tổng | Phân loại request-level và item-level riêng |

## 28. Quy trình vận hành khi bulk có lỗi

Khi một batch thất bại một phần, có thể thực hiện theo thứ tự:

1. **Xác định có nhận được BulkResponse không.** Nếu không, phân loại request-level và đánh giá kết quả có thể chưa rõ.
2. **Đọc errors.** Nếu false, ghi nhận batch thành công theo response.
3. **Duyệt từng item.** Lưu ID, operation, status, error type và reason.
4. **Đánh dấu item thành công.** Không đưa chúng vào retry queue.
5. **Phân loại item thất bại.** Retryable, dữ liệu không hợp lệ, conflict, cấu hình hoặc cần điều tra.
6. **Lên lịch retry.** Dùng backoff, jitter, giới hạn số lần và thời gian.
7. **Cách ly dữ liệu sai.** Lưu payload và lỗi có cấu trúc trong DLQ/quarantine.
8. **Pause khi lỗi cấu hình diện rộng.** Không tiếp tục gửi hàng loạt vào index hoặc cluster đang sai trạng thái.
9. **Reconcile kết quả không rõ.** Dùng ID, version hoặc event key để kiểm tra trước khi replay.
10. **Theo dõi và báo cáo.** Ghi metrics theo error type, index và producer.
11. **Sửa nguyên nhân gốc.** Mapping, producer, quyền, cluster capacity hoặc logic concurrency.
12. **Replay có kiểm soát.** Bắt đầu với nhóm nhỏ và xác nhận kết quả từng item.

## 29. Nguyên tắc thiết kế chính sách retry

- Không retry mọi exception.
- Không dùng HTTP 200 để kết luận toàn bộ bulk thành công.
- Phân biệt request-level failure với item-level failure.
- Chỉ retry các item có nguyên nhân có khả năng hồi phục.
- Không retry nguyên trạng lỗi mapping, JSON, validation hoặc script.
- Dùng error type cùng status và operation để phân loại.
- Chỉ retry failed items khi response cung cấp kết quả từng item.
- Dùng exponential backoff và jitter để tránh retry storm.
- Giới hạn attempts, elapsed time và concurrency.
- Bảo đảm idempotency hoặc reconcile trước khi retry request có kết quả không rõ.
- Xử lý create conflict và version conflict theo semantics riêng.
- Lưu payload cùng metadata để retry và DLQ.
- Pause pipeline khi lỗi cấu hình hoặc trạng thái cluster ảnh hưởng diện rộng.
- Theo dõi tỷ lệ lỗi, queue depth, DLQ và thời gian xử lý.

Một pipeline Bulk API ổn định phải coi mỗi item là một kết quả độc lập. **Lỗi tạm thời** như 429 hoặc một số lỗi 5xx có thể được retry sau backoff; **lỗi dữ liệu** như mapper parsing hoặc JSON sai cần được cách ly và sửa trước khi replay; **409** cần phân biệt duplicate create với version conflict; còn timeout phải được xem là kết quả có thể chưa rõ. Khi kiểm tra từng item, chỉ retry phần thất bại, giữ payload và ID ổn định, đồng thời bảo đảm thao tác có thể lặp an toàn, ứng dụng sẽ tránh ghi trùng, không che giấu dữ liệu lỗi và duy trì được tiến độ ingest ngay cả khi một phần batch gặp sự cố.
