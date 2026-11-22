# Retry xung đột và giới hạn an toàn với cập nhật không lặp

Khi nhiều worker cùng cập nhật một document Elasticsearch, một request có thể đọc source cũ trong khi request khác đã ghi phiên bản mới. Elasticsearch dùng optimistic concurrency control để phát hiện tình huống này. Với Update API, ứng dụng có thể yêu cầu Elasticsearch tự thử lại khi gặp version conflict bằng tham số `retry_on_conflict`.

Tuy nhiên, retry xung đột không giống retry toàn bộ request từ ứng dụng. Sự khác biệt này đặc biệt quan trọng với các thao tác **không lặp an toàn** (non-idempotent), chẳng hạn tăng bộ đếm, trừ tồn kho hoặc cộng điểm. Nếu client timeout sau khi server đã ghi thành công rồi gửi lại cùng lệnh, thao tác có thể được áp dụng hai lần.

Bài học tập trung vào cách giới hạn retry, phân biệt conflict với timeout, dùng optimistic concurrency control và thiết kế script update an toàn trong Spring Data Elasticsearch.

## 1. Vì sao update có thể gặp conflict?

Elasticsearch lưu document trên shard và quản lý phiên bản nội bộ. Khi Update API xử lý một document, về cơ bản nó:

1. Đọc source hiện tại của document.
2. Áp dụng partial document hoặc chạy script trên source đó.
3. Gửi phiên bản mới để ghi.
4. Kiểm tra document có bị thay đổi trong khoảng thời gian xử lý hay không.

Giả sử hai worker cùng đọc document có `stock = 10`:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant ES as Elasticsearch
    A->>ES: Đọc stock = 10
    B->>ES: Đọc stock = 10
    A->>ES: Ghi stock = 12
    ES-->>A: Update thành công
    B->>ES: Ghi stock = 13 dựa trên source cũ
    ES-->>B: Version conflict
~~~

Nếu Elasticsearch chấp nhận ghi của B dựa trên source cũ, thay đổi của A có thể bị mất. Optimistic concurrency control ngăn việc ghi đè âm thầm đó.

Một conflict không nhất thiết là lỗi dữ liệu. Nó cho biết trạng thái document đã thay đổi so với phiên bản mà request đang dựa vào. Ứng dụng cần quyết định có thể thử lại trên phiên bản mới hay phải trả conflict cho nghiệp vụ xử lý.

## 2. Phân biệt retry_on_conflict và retry ở client

Có hai tầng retry khác nhau:

| Cơ chế | Ai thực hiện | Khi nào retry | Điều gì được gửi lại |
|---|---|---|---|
| `retry_on_conflict` | Elasticsearch | Update gặp version conflict trong quá trình read-modify-write | Elasticsearch đọc lại document, chạy lại update/script rồi thử ghi |
| Application retry | Ứng dụng hoặc message consumer | Client nhận lỗi, timeout hoặc không nhận được response | Toàn bộ request được gửi lại từ client |

Với `retry_on_conflict`, Elasticsearch biết lần ghi trước không thành công do conflict và có thể chạy lại update trên source mới nhất. Lần thử bị conflict không được commit thành một thay đổi document đã lưu.

Với application retry sau timeout, client có thể không biết request đầu đã commit hay chưa. Nếu server đã cập nhật thành công nhưng response bị mất, gửi lại cùng script tăng bộ đếm có thể làm bộ đếm tăng thêm lần nữa.

Đây là điểm cốt lõi khi làm việc với update không idempotent: retry nội bộ do conflict có semantics khác với gửi lại request sau một kết quả không xác định.

## 3. Idempotent và non-idempotent update

Một thao tác là idempotent nếu thực hiện cùng thao tác nhiều lần tạo ra cùng trạng thái cuối cùng như thực hiện một lần.

| Thao tác | Ví dụ | Tính lặp |
|---|---|---|
| Gán một giá trị cố định | `status = PUBLISHED` | Thường idempotent |
| Đặt cờ | `active = true` | Thường idempotent |
| Tăng bộ đếm | `count += 1` | Không idempotent |
| Trừ tồn kho | `stock -= quantity` | Không idempotent |
| Thêm phần tử có kiểm tra trùng | Chỉ add nếu chưa có | Có thể idempotent theo quy tắc so sánh |
| Ghi timestamp hiện tại | `updatedAt = now` | Mỗi lần thực hiện có thể cho kết quả khác |
| Cộng điểm thưởng | `points += amount` | Không idempotent |

Ví dụ script tăng bộ đếm:

~~~painless
ctx._source.viewCount += 1;
~~~

Mỗi lần script được thực thi thành công sẽ tăng thêm một. Nếu ứng dụng gửi cùng event hai lần, kết quả tăng hai lần.

Ví dụ gán trạng thái:

~~~painless
ctx._source.status = params.status;
~~~

Nếu gửi lại cùng giá trị `status`, trạng thái cuối vẫn giống nhau. Thao tác này thường idempotent về mặt source, dù metadata như version hoặc thời điểm cập nhật vẫn có thể thay đổi.

Không nên chỉ dựa vào tên HTTP method để kết luận một update idempotent. Cần xét logic script, tham số, side effect và cách ứng dụng retry.

## 4. Dùng retry_on_conflict cho Update API

Update API hỗ trợ tham số `retry_on_conflict` để Elasticsearch thử lại khi có version conflict.

~~~http
POST /products/_update/P-1001?retry_on_conflict=3
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 2
    }
  }
}
~~~

Trong ví dụ:

- `P-1001` là document ID.
- `retry_on_conflict=3` giới hạn số lần thử lại khi gặp conflict.
- Script được thực thi trên source hiện tại của document.
- Nếu lần ghi bị conflict, Elasticsearch đọc lại và chạy lại script trong giới hạn retry.

Giả sử hai worker cùng tăng stock. Một worker ghi trước. Worker còn lại gặp conflict, đọc source mới rồi áp dụng lượng tăng của chính nó trên giá trị mới. Nếu retry thành công, cả hai thao tác đều được phản ánh.

Nếu số lần conflict vượt giới hạn, request vẫn thất bại. `retry_on_conflict` không bảo đảm request chắc chắn thành công và không phải cơ chế chờ vô hạn.

### Giới hạn retry phải hữu hạn

Chọn một giá trị nhỏ, có căn cứ từ mức tranh chấp và thời gian đáp ứng cho phép. Không tăng retry thật lớn để che giấu một document nóng bị nhiều worker cập nhật liên tục.

Một retry limit hữu hạn giúp:

- Giới hạn công việc Elasticsearch phải làm cho một request.
- Giữ latency có thể dự đoán hơn.
- Tránh một request tranh chấp chiếm tài nguyên quá lâu.
- Đưa trường hợp contention kéo dài về ứng dụng để xử lý có chủ đích.

Không có một con số retry phù hợp cho mọi workload. Hãy đo conflict rate, latency và throughput trên dữ liệu thật trước khi điều chỉnh.

## 5. Cấu hình retry_on_conflict trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `UpdateQuery` để xây dựng request cập nhật. Có thể đặt giới hạn retry bằng builder method `withRetryOnConflict(...)`.

Ví dụ dùng script tăng stock:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Script;
import org.springframework.data.elasticsearch.core.query.ScriptType;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public class ProductStockService {

    private final ElasticsearchOperations operations;

    public ProductStockService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void increaseStock(String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive"
            );
        }

        Script script = new Script(
                ScriptType.INLINE,
                "painless",
                "if (ctx._source.stock == null) { "
                        + "ctx._source.stock = 0; "
                        + "} "
                        + "ctx._source.stock += params.quantity",
                Map.of("quantity", quantity)
        );

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
                .withScript(script)
                .withRetryOnConflict(3)
                .build();

        operations.update(
                updateQuery,
                IndexCoordinates.of("products")
        );
    }
}
~~~

Ở đây:

- `ScriptType.INLINE` chỉ định script source nằm trong request.
- `painless` là ngôn ngữ script.
- `params.quantity` nhận lượng tăng.
- `withRetryOnConflict(3)` giới hạn retry nội bộ khi gặp version conflict.
- `operations.update(...)` thực thi update trên index đích.

Kiểu `Script` trong ví dụ là `org.springframework.data.elasticsearch.core.query.Script` của Spring Data. Tránh import nhầm kiểu Script của Elasticsearch Java API Client.

Retry nội bộ bảo vệ thao tác read-modify-write trước conflict đồng thời. Nó không chống một event bị consumer xử lý lặp hoặc client gửi lại request sau timeout.

## 6. Khi nào nên dùng optimistic concurrency control tường minh?

Có trường hợp ứng dụng muốn tự kiểm soát phiên bản document. Ví dụ:

1. Đọc document và hiển thị cho người dùng.
2. Người dùng chỉnh sửa.
3. Trong lúc đó một người khác đã cập nhật document.
4. Ứng dụng muốn từ chối ghi đè và yêu cầu người dùng tải lại dữ liệu.

Khi đọc document, Elasticsearch có thể trả về:

- `_seq_no`: sequence number của thao tác trên shard.
- `_primary_term`: primary term của shard.

Request cập nhật có thể gửi lại hai giá trị này dưới dạng điều kiện:

~~~http
POST /products/_update/P-1001?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "name": "Wireless Keyboard Pro"
  }
}
~~~

Elasticsearch chỉ chấp nhận update nếu document vẫn ở đúng sequence number và primary term được đọc trước đó. Nếu document đã thay đổi, request trả version conflict.

### retry_on_conflict và if_seq_no/if_primary_term phục vụ hai chính sách khác nhau

- `retry_on_conflict`: yêu cầu Elasticsearch tự đọc lại và thử áp dụng update lên source mới.
- `if_seq_no` + `if_primary_term`: yêu cầu update chỉ được phép nếu document vẫn đúng phiên bản ứng dụng đã đọc.

Khi dùng điều kiện OCC tường minh, nếu nhận conflict thì ứng dụng thường cần đọc lại, so sánh thay đổi và quyết định có thể áp dụng lại hay phải báo xung đột cho người dùng. Không nên kết hợp hai chính sách như thể chúng có cùng mục tiêu; điều kiện sequence/term cũ không thể trở thành điều kiện mới chỉ bằng cách lặp nguyên request.

## 7. Dùng điều kiện OCC qua UpdateQuery

Trong các phiên bản Spring Data Elasticsearch có hỗ trợ các thuộc tính OCC trên `UpdateQuery`, có thể gắn sequence number và primary term:

~~~java
UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withDocument(partialDocument)
        .withIfSeqNo(seqNo)
        .withIfPrimaryTerm(primaryTerm)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

`seqNo` và `primaryTerm` phải được lấy từ response đọc document trước đó, không tự sinh hoặc tự tăng ở ứng dụng.

Tên builder method và kiểu số có thể phụ thuộc phiên bản Spring Data Elasticsearch đang dùng. Đối chiếu Javadoc đúng dependency của dự án. Nếu API hiện tại không expose các thuộc tính cần thiết, có thể dùng Elasticsearch Java API Client trực tiếp để gửi điều kiện OCC.

Với OCC tường minh, một conflict là tín hiệu cho ứng dụng quyết định. Đọc lại document, áp dụng quy tắc merge hoặc trả lỗi để người dùng giải quyết. Không retry mù với cùng sequence number và primary term cũ.

## 8. Retry nội bộ có làm script tăng bị áp dụng hai lần không?

Đây là câu hỏi quan trọng với thao tác không idempotent.

Giả sử script:

~~~painless
ctx._source.counter += params.amount;
~~~

Elasticsearch đọc counter, chạy script rồi thử ghi. Nếu lần ghi đó thất bại do version conflict, thay đổi của lần thử đó chưa được commit vào document. Khi `retry_on_conflict` kích hoạt, Elasticsearch đọc source mới và chạy lại script trên source mới.

Vì vậy, một lần Update API thành công chỉ commit một lần thay đổi của request đó. Việc script được đánh giá lại sau conflict không đồng nghĩa các lần thử thất bại đều đã cộng vào document.

Nhưng nếu client gửi lại một Update API mới sau timeout, server có thể đã commit request đầu. Request mới là một lần cập nhật riêng và có thể cộng thêm lần nữa.

Phân biệt bằng ví dụ:

~~~text
Một request, retry nội bộ:
  Thử 1: đọc 10 -> tính 12 -> ghi conflict (không commit)
  Thử 2: đọc 15 -> tính 17 -> ghi thành công
  Kết quả: 17

Hai request do client gửi lại:
  Request 1: 10 -> 12 -> ghi thành công
  Client timeout, không nhận response
  Request 2: 12 -> 14 -> ghi thành công
  Kết quả: 14
~~~

Trong ví dụ đầu, chỉ lần ghi thành công được lưu. Trong ví dụ sau, cả hai request độc lập đều có thể được commit.

Do đó, `retry_on_conflict` giải quyết cạnh tranh giữa các writer trong một request update. Nó không cung cấp idempotency key cho request từ client.

## 9. Giới hạn an toàn cho application retry

Application retry cần chính sách riêng. Một request timeout không cho biết chắc Elasticsearch đã nhận, xử lý hay commit thao tác chưa.

Trước khi retry, phân loại tình huống:

| Tình huống | Có nên retry ngay? | Hướng xử lý |
|---|---|---|
| HTTP 409 do OCC | Không gửi lại nguyên request mù | Đọc lại và quyết định merge hoặc báo conflict |
| Update API hết retry_on_conflict | Có thể thử lại có giới hạn nếu nghiệp vụ cho phép | Đọc trạng thái mới, áp dụng lại quy tắc |
| HTTP 429 | Có thể retry | Backoff, jitter, giới hạn số lần |
| Lỗi kết nối trước khi gửi request | Có thể retry | Giữ nguyên idempotency key và payload |
| Timeout sau khi gửi request | Kết quả chưa xác định | Đối soát trạng thái trước khi áp dụng lại non-idempotent action |
| HTTP 400 do script/mapping | Không | Sửa source, params hoặc mapping |
| HTTP 401/403 | Không retry liên tục | Sửa xác thực hoặc quyền |
| HTTP 404 document missing | Theo nghiệp vụ | Kiểm tra ID, dùng upsert nếu phù hợp |

Một policy retry ở ứng dụng nên có:

- Số lần retry tối đa.
- Deadline tổng cho toàn bộ thao tác.
- Exponential backoff.
- Jitter để các worker không đồng loạt retry.
- Phân loại lỗi retryable và permanent.
- Logging/metrics cho từng nguyên nhân.
- Giới hạn concurrency để không làm cluster quá tải.

Ví dụ backoff tăng dần:

~~~java
Duration delay = Duration.ofMillis(100);

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return executeUpdate();
    } catch (RetryableException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }

        sleepWithJitter(delay);
        delay = delay.multipliedBy(2);
    }
}
~~~

Đây là pseudocode mô tả chính sách. Trong ứng dụng thực tế, dùng retry library hoặc scheduler có hỗ trợ interrupt, deadline và cancellation thay vì tự viết vòng lặp chặn thread. Không retry các lỗi dữ liệu hoặc authorization như thể chúng là lỗi mạng tạm thời.

## 10. Không retry thao tác cộng dồn khi chưa có idempotency

Ví dụ consumer nhận event cộng điểm:

~~~json
{
  "eventId": "evt-184",
  "accountId": "A-1001",
  "points": 50
}
~~~

Script:

~~~painless
ctx._source.points += params.points;
~~~

Nếu cùng event được giao lại, điểm có thể được cộng thêm 50 lần nữa. Deterministic document ID của account không giải quyết được việc event bị lặp, vì cả hai request đều cập nhật cùng document và đều hợp lệ.

Cần có một khóa nhận diện thao tác, ví dụ `eventId`, và lưu dấu vết đã áp dụng theo một thiết kế phù hợp.

Một cách đơn giản cho tập event nhỏ là kiểm tra danh sách ID đã xử lý trong cùng document:

~~~painless
if (ctx._source.processedEventIds == null) {
    ctx._source.processedEventIds = [];
}

if (ctx._source.processedEventIds.contains(params.eventId)) {
    ctx.op = 'noop';
} else {
    ctx._source.points += params.points;
    ctx._source.processedEventIds.add(params.eventId);
}
~~~

Script này làm cho cùng event ID không cộng điểm hai lần trên document đó, vì cập nhật số điểm và dấu event được ghi trong cùng một lần update document.

Nhưng danh sách `processedEventIds` sẽ tăng mãi nếu không có chính sách lưu trữ. Không nên dùng một mảng vô hạn trên document có tuổi thọ dài.

Các lựa chọn cho hệ thống lớn:

- Lưu idempotency record riêng theo event ID với deterministic ID và CREATE.
- Dùng event sequence/version đơn điệu theo từng aggregate nếu mô hình nghiệp vụ cho phép.
- Dùng ledger hoặc event store làm nguồn sự thật và xây projection có khả năng rebuild.
- Giữ cửa sổ deduplication có thời hạn nếu hợp đồng nghiệp vụ chỉ yêu cầu chống lặp trong khoảng thời gian xác định.

Nếu idempotency record và document nghiệp vụ nằm ở hai document khác nhau, hai thao tác không tự trở thành transaction nguyên tử. Cần thiết kế trạng thái xử lý, retry và đối soát để xử lý crash giữa hai bước. Không khẳng định một marker riêng lẻ bảo đảm exactly-once cho toàn hệ thống.

## 11. Dùng sequence nghiệp vụ để chống event cũ

Với dữ liệu trạng thái có version tăng dần theo từng sản phẩm, có thể chỉ áp dụng event có sequence mới hơn.

~~~painless
if (ctx._source.eventVersion == null
        || params.eventVersion > ctx._source.eventVersion) {
    ctx._source.status = params.status;
    ctx._source.eventVersion = params.eventVersion;
} else {
    ctx.op = 'noop';
}
~~~

Cách này ngăn event cũ ghi đè trạng thái mới và làm event cùng version trở thành no-op.

Điều kiện quan trọng:

- Version phải do nguồn có thẩm quyền cấp.
- Version có thứ tự trong phạm vi đúng aggregate, chẳng hạn từng product ID.
- Mọi writer phải tuân thủ cùng quy tắc.
- Nếu event là phép cộng dồn và có thể đến sai thứ tự, bỏ qua version thấp hơn có thể làm mất một sự kiện hợp lệ.

Sequence version phù hợp với cập nhật trạng thái snapshot. Nó không tự thay thế event ledger khi mọi event đều phải được áp dụng đúng một lần.

## 12. Giữ giới hạn nghiệp vụ ngay trong script

Với thao tác trừ tồn kho, script nên kiểm tra điều kiện trước khi thay đổi:

~~~painless
if (params.quantity <= 0) {
    throw new IllegalArgumentException('quantity must be positive');
}

if (ctx._source.stock == null) {
    throw new IllegalArgumentException('stock is missing');
}

if (ctx._source.stock < params.quantity) {
    ctx.op = 'noop';
} else {
    ctx._source.stock -= params.quantity;
}
~~~

Script tránh stock âm bằng cách kiểm tra và trừ trong cùng một thao tác update. Không tách thành hai request "đọc stock" rồi "ghi stock" vì một worker khác có thể thay đổi stock giữa hai bước.

Tuy nhiên, `noop` chỉ cho biết document không được cập nhật. Nếu nghiệp vụ cần phân biệt "không đủ hàng" với "đã xử lý event trước đó", hãy thiết kế response hoặc trạng thái rõ ràng. Không nên dùng một kết quả noop chung cho nhiều lý do khác nhau mà không có cách quan sát.

Với số lượng và tiền tệ, validate miền giá trị ở cả ứng dụng và script. Không cho client gửi số âm hoặc giá trị vượt giới hạn chỉ vì script có kiểm tra.

## 13. Tách retry conflict khỏi update_by_query

Update-by-query cập nhật nhiều document phù hợp với query. Nó có chính sách conflict riêng:

~~~http
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "status": "DRAFT"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ARCHIVED"
    }
  }
}
~~~

Hai khái niệm không giống nhau:

- `retry_on_conflict` thuộc Update API cho một document theo ID.
- `conflicts=proceed` trong update-by-query cho phép tiến trình tiếp tục khi gặp version conflict ở các document được xử lý.

Với `conflicts=proceed`, document xung đột có thể không được cập nhật trong lượt đó. Hãy kiểm tra `version_conflicts`, `failures`, `updated` và các trường thống kê trong response.

Update-by-query không phải transaction toàn bộ index. Một phần document có thể đã cập nhật trước khi task gặp lỗi hoặc timeout. Nếu cần retry, phải xác định tập document còn lại và bảo đảm script an toàn khi chạy lại.

Với script gán trạng thái cố định, chạy lại thường idempotent. Với script tăng số lượng, cộng điểm hoặc trừ tiền, chạy lại trên tập document đã cập nhật có thể áp dụng thao tác thêm lần nữa. Cần thiết kế điều kiện đánh dấu/version hoặc ledger để tránh điều đó.

## 14. Xử lý bulk update và partial failure

Bulk API cho phép gửi nhiều update action trong một request. Mỗi item có kết quả riêng; bulk không phải transaction.

Ví dụ action update có script:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"P-1001","retry_on_conflict":3}}
{"script":{"lang":"painless","source":"ctx._source.stock += params.quantity","params":{"quantity":2}}}
{"update":{"_index":"products","_id":"P-1002","retry_on_conflict":3}}
{"script":{"lang":"painless","source":"ctx._source.stock += params.quantity","params":{"quantity":1}}}
~~~

Khi nhận response:

1. Kiểm tra trường `errors`.
2. Duyệt từng item và action result.
3. Ghi nhận item thành công.
4. Phân loại version conflict, mapping error, missing document và lỗi tạm thời.
5. Chỉ retry item phù hợp.
6. Giữ nguyên idempotency key/event identity nếu thao tác có thể được giao lại.

Không gửi lại toàn bộ bulk chỉ vì một item lỗi. Những item đã thành công có thể bị áp dụng lần nữa nếu script không idempotent.

Bulk update có thể có `retry_on_conflict` trong metadata của từng update action. Giới hạn đó áp dụng cho conflict nội bộ của từng item; nó không giải quyết timeout của toàn bulk request hoặc duplicate event ở tầng consumer.

## 15. Giới hạn retry và backpressure

Khi một document bị nhiều worker cập nhật liên tục, tăng retry có thể làm tình hình xấu hơn. Mỗi retry nội bộ đều cần đọc và thử ghi lại. Nhiều request cùng tranh chấp có thể tạo ra nhiều vòng xử lý lặp.

Một chính sách vận hành nên đặt giới hạn ở nhiều tầng:

| Tầng | Giới hạn nên có | Mục đích |
|---|---|---|
| Update API | `retry_on_conflict` nhỏ và hữu hạn | Giải quyết contention ngắn |
| Application retry | Số lần tối đa và deadline | Giới hạn thời gian xử lý |
| Worker concurrency | Giới hạn số worker cùng cập nhật một aggregate | Giảm tranh chấp |
| Queue | Backpressure và retry delay | Tránh dồn tải vào cluster |
| Bulk | Kích thước batch và số request đồng thời | Giữ bộ nhớ/CPU trong giới hạn |
| Business logic | Idempotency key hoặc version | Chống áp dụng lặp |

Nếu một document trở thành hot spot, cân nhắc thay đổi mô hình:

- Gom cập nhật theo key ở một consumer/partition.
- Dùng counter theo shard rồi tổng hợp khi đọc nếu semantics cho phép.
- Ghi event riêng rồi tạo projection.
- Chia dữ liệu theo aggregate hoặc tenant.
- Giảm số lần cập nhật cùng document bằng batch aggregation.

Không tăng giới hạn retry để che giấu một mô hình dữ liệu có contention quá cao.

## 16. Đọc kết quả update và quan sát noop/conflict

Sau update, ứng dụng nên quan sát kết quả thay vì chỉ bỏ qua response.

Elasticsearch Update API có thể trả các thông tin như:

- `result`: `updated`, `created` hoặc `noop`.
- `_version`: version document sau thao tác.
- `_seq_no` và `_primary_term`: thông tin concurrency của document.
- `get`: source nếu request yêu cầu trả phần document sau update.

Ví dụ response noop:

~~~json
{
  "_index": "products",
  "_id": "P-1001",
  "result": "noop",
  "_version": 8,
  "_seq_no": 19,
  "_primary_term": 2
}
~~~

Noop không đồng nghĩa với lỗi HTTP. Nó cho biết script đã quyết định không ghi thay đổi. Ứng dụng cần phân biệt no-op hợp lệ với thao tác không được áp dụng do điều kiện nghiệp vụ.

Nên ghi metrics:

- Số update thành công.
- Số noop.
- Số version conflict.
- Số request hết retry limit.
- Số application retry.
- Số timeout không xác định kết quả.
- Số duplicate event được phát hiện.
- Latency và số lần thử trung bình.

Các metrics này giúp nhận biết hot document, retry storm hoặc lỗi thiết kế idempotency.

## 17. Ví dụ service có giới hạn retry và xử lý kết quả

Ví dụ dưới đây cho thấy retry nội bộ được cấu hình riêng, còn kết quả của update được trả về cho caller để ghi nhận:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Script;
import org.springframework.data.elasticsearch.core.query.ScriptType;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

public class InventoryService {

    private static final int MAX_CONFLICT_RETRIES = 3;

    private final ElasticsearchOperations operations;

    public InventoryService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse reserve(
            String productId,
            int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive"
            );
        }

        Script script = new Script(
                ScriptType.INLINE,
                "painless",
                "if (ctx._source.stock == null) { "
                        + "throw new IllegalArgumentException('stock missing'); "
                        + "} "
                        + "if (ctx._source.stock < params.quantity) { "
                        + "ctx.op = 'noop'; "
                        + "} else { "
                        + "ctx._source.stock -= params.quantity; "
                        + "}",
                Map.of("quantity", quantity)
        );

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
                .withScript(script)
                .withRetryOnConflict(MAX_CONFLICT_RETRIES)
                .build();

        return operations.update(
                updateQuery,
                IndexCoordinates.of("products")
        );
    }
}
~~~

Đoạn code minh họa một update có điều kiện. Caller cần kiểm tra kết quả để biết thao tác đã update hay noop; nếu API phiên bản đang dùng biểu diễn response khác, điều chỉnh kiểu trả về theo Javadoc của dependency.

Quan trọng: ví dụ này không tự chống việc caller gửi cùng yêu cầu reserve hai lần. Nếu request có thể được retry sau timeout, cần bổ sung idempotency key và cơ chế deduplication theo nghiệp vụ trước khi trừ tồn kho.

## 18. Các lỗi thường gặp

### Đặt retry_on_conflict quá cao

Retry lớn không loại bỏ contention. Nó có thể làm latency và tải tăng. Dùng giới hạn nhỏ, đo conflict rate và xử lý hot spot ở kiến trúc.

### Nhầm retry nội bộ với retry của client

Elasticsearch chỉ biết conflict trong quá trình xử lý request. Nó không biết client có gửi lại cùng event sau timeout hay không.

### Retry nguyên request sau timeout với phép cộng dồn

Nếu request đầu đã commit, request thứ hai sẽ cộng thêm lần nữa. Cần idempotency key, event deduplication hoặc đối soát trạng thái.

### Dùng OCC token cũ để retry mãi

`if_seq_no` và `if_primary_term` cũ sẽ tiếp tục không khớp sau khi document đã thay đổi. Đọc lại và quyết định merge hoặc trả conflict.

### Dùng retry_on_conflict thay cho validation

Retry không sửa dữ liệu sai, script lỗi, mapping sai hoặc quyền truy cập thiếu. Chỉ retry lỗi tạm thời có thể phục hồi.

### Coi noop là thành công nghiệp vụ trong mọi trường hợp

Noop chỉ có nghĩa không ghi document. Cần định nghĩa rõ đó là duplicate, điều kiện không thỏa hay không có thay đổi.

### Retry toàn bộ bulk

Một số item có thể đã thành công. Retry cả batch có thể lặp lại các thao tác không idempotent. Phân loại từng item và retry có chọn lọc.

### Dùng update_by_query như một transaction

Update-by-query có thể thành công một phần và có version conflict. Kiểm tra response, failures và số document thực sự được cập nhật.

### Dùng danh sách event ID không giới hạn

Lưu mọi event ID mãi trong một document làm source phình to và update ngày càng đắt. Chọn ledger, sequence hoặc cửa sổ deduplication phù hợp.

### Cho rằng deterministic ID là đủ

ID ổn định chống tạo nhiều document cho cùng khóa. Nó không ngăn hai update hợp lệ cùng tăng một bộ đếm hoặc hai side effect được thực hiện lặp.

## 19. Quy trình thiết kế retry an toàn

Khi triển khai cập nhật đồng thời:

1. Xác định thao tác là idempotent hay non-idempotent.
2. Xác định nguồn conflict: nhiều writer, stale read hay OCC token.
3. Với update theo ID, chọn `retry_on_conflict` hữu hạn cho contention ngắn.
4. Nếu dùng `if_seq_no` và `if_primary_term`, xử lý conflict bằng đọc lại và quyết định merge.
5. Không retry mù lỗi mapping, script, validation hoặc authorization.
6. Đặt giới hạn retry, deadline, backoff và jitter ở application layer.
7. Với phép cộng/trừ, xác định idempotency key hoặc sequence nghiệp vụ.
8. Phân biệt timeout không rõ kết quả với version conflict đã biết.
9. Với bulk, đọc kết quả từng item và chỉ retry item phù hợp.
10. Với update-by-query, kiểm tra `version_conflicts` và `failures`.
11. Giới hạn concurrency và theo dõi hot document.
12. Ghi metrics cho conflict, noop, retry và duplicate.
13. Kiểm thử hai writer đồng thời, timeout sau commit và message được giao lặp.
14. Xác nhận source cuối cùng bằng GET hoặc search sau khi test hoàn tất.

## Tài liệu tham khảo

- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch — Update by query API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Painless update context](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-update-context.html)
- [Spring Data Elasticsearch — UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch — Script API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Script.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)

## Kết luận

`retry_on_conflict` cho phép Elasticsearch đọc lại document và chạy lại update sau một version conflict trong cùng request. Giới hạn này xử lý cạnh tranh read-modify-write; nó không chống việc ứng dụng gửi lại một phép cộng/trừ sau timeout không rõ kết quả. Trong Spring Data Elasticsearch, có thể cấu hình giới hạn bằng `UpdateQuery.withRetryOnConflict(...)`; khi cần kiểm soát phiên bản tường minh, dùng `if_seq_no` và `if_primary_term`, đọc lại và giải quyết conflict ở ứng dụng. Với cập nhật không idempotent, phải bổ sung idempotency key, event deduplication hoặc sequence nghiệp vụ, đồng thời giới hạn retry, deadline, concurrency và kiểm tra từng item trong bulk để tránh áp dụng cùng một thay đổi nhiều lần.
