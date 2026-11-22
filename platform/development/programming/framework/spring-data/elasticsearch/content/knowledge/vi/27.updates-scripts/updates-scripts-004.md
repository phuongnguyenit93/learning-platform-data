# Script cập nhật bằng Painless và tham số script

Elasticsearch hỗ trợ cập nhật document bằng script. Thay vì gửi một phần document cố định, ứng dụng có thể yêu cầu Elasticsearch chạy một đoạn mã trên document hiện tại để tính giá trị mới, kiểm tra điều kiện, bỏ qua cập nhật hoặc xóa document.

Ngôn ngữ script mặc định thường dùng cho thao tác này là **Painless**. Script có thể đọc và thay đổi `ctx._source`, đồng thời nhận dữ liệu đầu vào qua map `params`.

Trong Spring Data Elasticsearch, có thể tạo một `Script` kiểu inline, gắn vào `UpdateQuery`, rồi gọi `ElasticsearchOperations.update(...)`. Cách này phù hợp khi muốn cập nhật một document theo ID bằng logic có điều kiện hoặc phép tính.

## 1. Khi nào cần script update?

Nếu chỉ muốn gán một vài field bằng giá trị cố định, partial document thường đơn giản hơn:

~~~json
POST /products/_update/P-1001
{
  "doc": {
    "status": "PUBLISHED"
  }
}
~~~

Nhưng một số nghiệp vụ cần đọc giá trị hiện tại trước khi quyết định cập nhật:

- Tăng số lượng tồn kho thêm một lượng.
- Tăng bộ đếm mỗi khi có sự kiện.
- Chỉ đổi trạng thái nếu trạng thái hiện tại vẫn là `DRAFT`.
- Thêm một phần tử vào danh sách nếu chưa tồn tại.
- Cập nhật thời điểm xử lý.
- Bỏ qua request nếu giá trị mới giống giá trị hiện tại.
- Xóa document khi một điều kiện nghiệp vụ được thỏa mãn.

Ví dụ tăng tồn kho:

~~~json
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

Elasticsearch đọc document hiện tại, chạy script với tham số `quantity = 5`, sau đó ghi lại source đã thay đổi nếu script cho phép cập nhật.

## 2. Painless là gì?

Painless là ngôn ngữ scripting được Elasticsearch thiết kế để chạy trong các ngữ cảnh như update, query, ingest và aggregation. Ngôn ngữ này có cú pháp gần Java, hỗ trợ kiểu dữ liệu và API được Elasticsearch cho phép trong từng script context.

Painless không phải một JVM shell tổng quát. Script chạy trong sandbox với các giới hạn và quyền truy cập theo context. Không nên giả định có thể gọi tùy ý mọi class Java, truy cập filesystem hoặc mở kết nối mạng từ script.

Một số thành phần thường gặp trong update script:

| Thành phần | Ý nghĩa |
|---|---|
| `ctx._source` | Map chứa nội dung document hiện tại |
| `params` | Map tham số do request truyền vào |
| `ctx._id` | Document ID trong context hỗ trợ thuộc tính này |
| `ctx._index` | Tên index của document |
| `ctx.op` | Điều khiển thao tác, ví dụ cập nhật, xóa hoặc bỏ qua |
| `ctx._source.field` | Đọc hoặc gán field trong document |

Với Update API theo ID, script thường thao tác trên `ctx._source`. Thay đổi trong script được lưu thành source mới của document. Script không tự thay đổi mapping của index.

## 3. Đọc và cập nhật ctx._source

Giả sử document hiện tại:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "stock": 12,
  "status": "PUBLISHED"
}
~~~

Tăng tồn kho thêm 5:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

Sau khi cập nhật, document có thể là:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "stock": 17,
  "status": "PUBLISHED"
}
~~~

Script có thể gán giá trị mới:

~~~painless
ctx._source.status = params.status;
ctx._source.updatedAt = params.updatedAt;
~~~

Có thể đọc giá trị trước khi thay đổi:

~~~painless
if (ctx._source.stock < params.minimumStock) {
    ctx._source.status = 'LOW_STOCK';
}
~~~

Cần kiểm tra field có thể thiếu hoặc null trước khi thực hiện phép toán. Nếu `stock` không tồn tại, phép cộng trực tiếp có thể gây lỗi runtime.

Ví dụ an toàn hơn:

~~~painless
if (ctx._source.stock == null) {
    ctx._source.stock = 0;
}
ctx._source.stock += params.quantity;
~~~

Đoạn script trên khởi tạo stock bằng 0 nếu field chưa có, sau đó mới tăng. Nếu nghiệp vụ yêu cầu document thiếu stock phải bị từ chối, hãy kiểm tra và báo lỗi thay vì tự khởi tạo.

## 4. Truyền giá trị qua params

Không nên nối trực tiếp giá trị đầu vào vào chuỗi source của script. Hãy giữ source ổn định và truyền dữ liệu riêng qua `params`.

Ví dụ:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.newStatus",
    "params": {
      "newStatus": "PUBLISHED"
    }
  }
}
~~~

Ưu điểm của params:

- Script source không phải thay đổi theo từng giá trị đầu vào.
- Tránh lỗi quote và escape khi ghép chuỗi.
- Tách logic cập nhật khỏi dữ liệu nghiệp vụ.
- Giúp Elasticsearch tái sử dụng compiled script cache khi source giống nhau.
- Giảm nguy cơ tạo script từ nội dung không đáng tin cậy.

Nếu cần cập nhật nhiều field:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status; ctx._source.updatedBy = params.user; ctx._source.updatedAt = params.time",
    "params": {
      "status": "PUBLISHED",
      "user": "admin-01",
      "time": "2026-11-13T10:00:00Z"
    }
  }
}
~~~

Không truyền một đoạn mã Painless do client tùy ý gửi lên. Client nên gửi dữ liệu và lựa chọn nghiệp vụ nằm trong allowlist; source script do ứng dụng quản lý.

## 5. Cập nhật có điều kiện

Một script có thể kiểm tra giá trị hiện tại trước khi thay đổi.

Ví dụ chỉ xuất bản sản phẩm nếu trạng thái hiện tại là `DRAFT`:

~~~painless
if (ctx._source.status == 'DRAFT') {
    ctx._source.status = 'PUBLISHED';
    ctx._source.publishedAt = params.publishedAt;
} else {
    ctx.op = 'noop';
}
~~~

Nếu trạng thái không phải DRAFT, script đặt `ctx.op = 'noop'`. Elasticsearch không ghi lại document trong trường hợp đó.

Có thể kiểm tra nhiều điều kiện:

~~~painless
if (ctx._source.stock == null) {
    throw new IllegalArgumentException('stock is required');
}

if (ctx._source.stock >= params.quantity) {
    ctx._source.stock -= params.quantity;
    ctx._source.updatedAt = params.updatedAt;
} else {
    ctx.op = 'noop';
}
~~~

Ví dụ trên chỉ trừ tồn kho nếu đủ số lượng. Tuy nhiên, việc dùng `noop` hay trả lỗi phải theo hợp đồng nghiệp vụ:

- `noop`: yêu cầu không làm thay đổi document.
- Ném exception: request thất bại và ứng dụng nhận lỗi.
- Cập nhật trạng thái từ chối: nếu nghiệp vụ cần lưu lại lý do hoặc trạng thái xử lý.

Không nên dùng `noop` để che giấu lỗi dữ liệu hoặc lỗi lập trình. Hãy phân biệt điều kiện không cần cập nhật với dữ liệu không hợp lệ.

## 6. Điều khiển thao tác bằng ctx.op

Trong update script, `ctx.op` cho phép điều khiển kết quả xử lý document. Các giá trị thường dùng trong update context gồm:

| Giá trị | Hành vi |
|---|---|
| `index` | Lưu document sau khi script thay đổi source |
| `noop` | Không ghi thay đổi |
| `delete` | Xóa document |

Ví dụ bỏ qua khi giá trị không thay đổi:

~~~painless
if (ctx._source.status == params.status) {
    ctx.op = 'noop';
} else {
    ctx._source.status = params.status;
}
~~~

Ví dụ xóa document nếu đã hết hạn:

~~~painless
if (ctx._source.expiresAt < params.cutoffTime) {
    ctx.op = 'delete';
}
~~~

Khi dùng ngày giờ, cần thống nhất kiểu dữ liệu và định dạng. Nếu field được lưu dưới dạng date, hãy truyền tham số có kiểu và đơn vị phù hợp với cách script so sánh; không so sánh chuỗi ngày tùy tiện nếu định dạng không bảo đảm thứ tự từ điển trùng với thứ tự thời gian.

`ctx.op` chỉ điều khiển thao tác trong context hỗ trợ nó. Không dùng các giá trị này như một API Java chung hoặc giả định mọi script context đều có cùng tập thao tác.

## 7. Gắn Painless Script vào UpdateQuery của Spring Data

Spring Data Elasticsearch cung cấp các lớp `Script`, `ScriptType` và `UpdateQuery` để xây dựng update request.

Ví dụ tăng tồn kho:

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
                .build();

        operations.update(
                updateQuery,
                IndexCoordinates.of("products")
        );
    }
}
~~~

Luồng xử lý:

1. Tạo source script bằng Painless.
2. Chọn kiểu `ScriptType.INLINE`.
3. Chỉ định language là `painless`.
4. Truyền tham số trong map.
5. Gắn script vào `UpdateQuery` theo document ID.
6. Gọi `ElasticsearchOperations.update(...)` với index hoặc alias đích.

Các import và builder method cần khớp với phiên bản Spring Data Elasticsearch trong dự án. Trong ví dụ, `Script` là kiểu của Spring Data Elasticsearch, không phải `co.elastic.clients.elasticsearch._types.Script` của Java API Client.

## 8. Tách script source khỏi code bằng hằng số

Nếu một script được dùng ở nhiều service, có thể đặt source vào hằng số hoặc một lớp chuyên trách:

~~~java
public final class ProductScripts {

    private ProductScripts() {
    }

    public static final String INCREASE_STOCK =
            "if (ctx._source.stock == null) { "
            + "ctx._source.stock = 0; "
            + "} "
            + "ctx._source.stock += params.quantity";
}
~~~

Sau đó:

~~~java
Script script = new Script(
        ScriptType.INLINE,
        "painless",
        ProductScripts.INCREASE_STOCK,
        Map.of("quantity", quantity)
);
~~~

Không nên tạo một source string mới bằng cách chèn từng giá trị vào script. Hãy giữ script ổn định và thay đổi params.

Nếu source script dài, có thể quản lý bằng file resource hoặc stored script. Khi đó cần có quy trình triển khai và versioning để đảm bảo ứng dụng gọi đúng script đang tồn tại trên cluster.

## 9. Cập nhật nhiều field trong cùng một script

Một script có thể cập nhật nhiều field trong một lần update:

~~~painless
ctx._source.status = params.status;
ctx._source.updatedBy = params.updatedBy;
ctx._source.updatedAt = params.updatedAt;

if (ctx._source.auditCount == null) {
    ctx._source.auditCount = 0;
}
ctx._source.auditCount += 1;
~~~

Java:

~~~java
Map<String, Object> params = Map.of(
        "status", "PUBLISHED",
        "updatedBy", "admin-01",
        "updatedAt", "2026-11-13T10:00:00Z"
);

Script script = new Script(
        ScriptType.INLINE,
        "painless",
        ProductScripts.PUBLISH_PRODUCT,
        params
);

UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(script)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

Các thay đổi của một update script được áp dụng như một lần cập nhật document. Nếu script lỗi, Elasticsearch không lưu một phần các thay đổi rồi bỏ dở phần còn lại như một transaction nhiều document. Request update đó thất bại.

Tuy nhiên, điều này không biến một chuỗi nhiều update request thành transaction. Nếu cập nhật nhiều document, mỗi document có thể thành công hoặc thất bại riêng.

## 10. Xử lý field null, thiếu và kiểu dữ liệu

Painless thao tác trên source JSON đã được deserialize thành các kiểu dữ liệu runtime. Một field có thể:

- Không tồn tại.
- Có giá trị null.
- Có kiểu số nguyên.
- Có kiểu số thực.
- Có kiểu chuỗi hoặc danh sách.
- Có kiểu khác với giả định của script do dữ liệu lịch sử.

Ví dụ kiểm tra trước khi cộng:

~~~painless
def currentStock = ctx._source.stock;

if (currentStock == null) {
    currentStock = 0;
}

ctx._source.stock = currentStock + params.quantity;
~~~

Nếu dữ liệu cũ chứa `stock` dưới dạng chuỗi, phép cộng có thể lỗi hoặc tạo hành vi không mong muốn. Nên chuẩn hóa mapping và dữ liệu trước khi chạy script trên toàn bộ index.

Với số lượng, giá và tiền tệ:

- Xác định kiểu số được lưu trong source.
- Truyền params bằng kiểu Java tương ứng.
- Tránh trộn integer, long, double và decimal tùy tiện.
- Với tiền, cân nhắc lưu đơn vị nhỏ nhất dưới dạng integer/long hoặc dùng quy ước scaled numeric.
- Validate giá trị âm, tràn số và giới hạn nghiệp vụ trước khi gửi.

Ví dụ kiểm tra số lượng:

~~~painless
if (params.quantity <= 0) {
    throw new IllegalArgumentException('quantity must be positive');
}

if (ctx._source.stock == null) {
    throw new IllegalArgumentException('stock is missing');
}

ctx._source.stock += params.quantity;
~~~

Validation ở script giúp bảo vệ dữ liệu khi có nhiều client, nhưng vẫn nên validate ở tầng ứng dụng để trả lỗi sớm và dễ hiểu.

## 11. Cập nhật danh sách trong _source

Painless có thể thao tác với list trong source.

Ví dụ thêm tag nếu chưa có:

~~~painless
if (ctx._source.tags == null) {
    ctx._source.tags = [];
}

if (!ctx._source.tags.contains(params.tag)) {
    ctx._source.tags.add(params.tag);
} else {
    ctx.op = 'noop';
}
~~~

Params:

~~~json
{
  "tag": "FEATURED"
}
~~~

Xóa một tag:

~~~painless
if (ctx._source.tags != null) {
    ctx._source.tags.removeIf(tag -> tag == params.tag);
}
~~~

Với danh sách lớn hoặc cấu trúc lồng nhau, cần chú ý chi phí đọc, duyệt và ghi lại toàn bộ source. Nếu một danh sách tăng không giới hạn, nên xem xét thiết kế document hoặc index khác thay vì liên tục thêm phần tử vào cùng một mảng.

Nếu danh sách có thể chứa kiểu dữ liệu không đồng nhất, hãy kiểm tra kiểu phần tử trước khi gọi phương thức hoặc so sánh.

## 12. Script update và upsert

Update theo ID thường yêu cầu document đã tồn tại. Nếu document chưa tồn tại, Elasticsearch có thể trả lỗi document missing.

Upsert cho phép cung cấp document ban đầu khi ID chưa tồn tại. Có hai khái niệm cần phân biệt:

- `upsert`: source được dùng khi document chưa tồn tại.
- `scripted_upsert`: yêu cầu script vẫn chạy trong trường hợp document chưa tồn tại.

Ví dụ ý tưởng: tạo bộ đếm với giá trị ban đầu 0, rồi tăng theo tham số.

~~~json
POST /counters/_update/order-count
{
  "scripted_upsert": true,
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.count == null) { ctx._source.count = 0; } ctx._source.count += params.increment",
    "params": {
      "increment": 1
    }
  },
  "upsert": {
    "count": 0
  }
}
~~~

Trong Spring Data Elasticsearch, có thể tạo upsert document và gắn vào UpdateQuery:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

Document upsert = Document.create();
upsert.put("count", 0);

UpdateQuery updateQuery = UpdateQuery.builder("order-count")
        .withScript(script)
        .withUpsert(upsert)
        .withScriptedUpsert(true)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("counters")
);
~~~

Khi bật scripted upsert, script được chạy cả khi document chưa tồn tại. Hãy thiết kế script để hoạt động đúng với source upsert được cung cấp.

Không nhầm `scripted_upsert` với `doc_as_upsert`. `doc_as_upsert` dùng partial document làm source upsert; `scripted_upsert` cho phép script chạy trong luồng upsert. Chọn một cách phù hợp với logic cần thực hiện và kiểm tra giới hạn kết hợp của API phiên bản đang dùng.

## 13. Phân biệt script update, partial document và update_by_query

Ba cơ chế có mục tiêu khác nhau:

| Cơ chế | Phạm vi | Phù hợp khi |
|---|---|---|
| Partial document update (`doc`) | Một document theo ID | Gán các field cố định |
| Script update (`script`) | Một document theo ID | Tính toán hoặc kiểm tra giá trị hiện tại |
| Update by query | Nhiều document khớp query | Chạy cùng logic trên một tập document |

Partial update:

~~~json
POST /products/_update/P-1001
{
  "doc": {
    "status": "PUBLISHED"
  }
}
~~~

Script update:

~~~json
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

Update by query:

~~~json
POST /products/_update_by_query
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

Update by query có thể xử lý nhiều document theo query, nhưng cần quan tâm đến số lượng document, version conflict, timeout, throttling và kết quả từng batch. Không dùng update-by-query cho một document nếu Update API theo ID đã đủ.

## 14. Thực hiện update_by_query và tham số

Một update-by-query request có thể nhận script và params tương tự Update API:

~~~json
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "status": "DRAFT"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.newStatus; ctx._source.updatedAt = params.updatedAt",
    "params": {
      "newStatus": "ARCHIVED",
      "updatedAt": "2026-11-13T10:00:00Z"
    }
  }
}
~~~

`conflicts=proceed` cho phép tiến trình tiếp tục khi gặp version conflict, nhưng không có nghĩa mọi document đều được cập nhật. Response có số lượng updated, version conflicts, failures và thông tin batch.

Nếu cần bảo đảm tất cả document đều được cập nhật, không nên chỉ đặt `conflicts=proceed` rồi coi request thành công là dữ liệu đã đồng bộ đầy đủ. Cần kiểm tra response và có chiến lược retry/đối soát cho các document thất bại.

Update-by-query không phải một transaction nguyên tử trên toàn bộ tập document. Một số document có thể đã được cập nhật trước khi request gặp lỗi hoặc timeout.

## 15. Tham số script và kiểu dữ liệu Java

Params là dữ liệu JSON được truyền vào Painless. Trong Java, có thể dùng map:

~~~java
Map<String, Object> params = Map.of(
        "quantity", 5,
        "status", "PUBLISHED",
        "enabled", true
);
~~~

Các giá trị thường dùng:

| Java | JSON/Painless |
|---|---|
| `String` | string |
| `Integer`, `Long` | number nguyên |
| `Double`, `Float` | number thực |
| `Boolean` | boolean |
| `List<?>` | array |
| `Map<String, ?>` | object |
| `null` | JSON null, nếu map cho phép chứa null |

Lưu ý `Map.of(...)` không cho phép key hoặc value null. Nếu cần truyền giá trị null, hãy dùng một map có thể chứa null như `HashMap` và xác định rõ script sẽ xử lý giá trị đó ra sao.

Ví dụ truyền danh sách:

~~~java
Map<String, Object> params = Map.of(
        "newTags",
        List.of("FEATURED", "PROMOTED")
);
~~~

Painless có thể lặp qua tham số:

~~~painless
if (ctx._source.tags == null) {
    ctx._source.tags = [];
}

for (def tag : params.newTags) {
    if (!ctx._source.tags.contains(tag)) {
        ctx._source.tags.add(tag);
    }
}
~~~

Không truyền object Java tùy ý mà JSON serializer không thể chuyển đổi. Hãy dùng kiểu dữ liệu đơn giản, rõ ràng và tương thích với JSON.

## 16. Stored script và inline script

Có hai cách gửi script:

- **Inline script**: source nằm trực tiếp trong request.
- **Stored script**: source được lưu trên Elasticsearch bằng ID, request chỉ tham chiếu ID.

Inline script:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Stored script được tạo bằng Stored Script API:

~~~http
PUT /_scripts/set-product-status
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status"
  }
}
~~~

Sau đó dùng ID:

~~~json
{
  "script": {
    "id": "set-product-status",
    "params": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Stored script hữu ích khi cùng logic được dùng bởi nhiều service hoặc cần triển khai script độc lập với ứng dụng. Cần versioning và kiểm soát quyền cập nhật stored scripts.

Trong Spring Data, có thể dùng kiểu script phù hợp với phiên bản để tham chiếu script ID thay vì source inline. Hãy kiểm tra constructor/builder của `Script` trong dependency đang dùng, vì cách biểu diễn script type có thể khác giữa các thế hệ API.

## 17. Script compilation và hiệu năng

Elasticsearch biên dịch Painless script và có cơ chế cache compiled script. Nếu mỗi request tạo source khác nhau do nhúng giá trị, cache có thể kém hiệu quả và số lần biên dịch tăng.

Nên:

- Giữ source script ổn định.
- Truyền dữ liệu thay đổi qua params.
- Tránh script quá dài hoặc làm quá nhiều việc.
- Tránh lặp trên mảng rất lớn nếu có thể xử lý ở ứng dụng hoặc đổi mô hình dữ liệu.
- Dùng partial document update nếu chỉ cần gán field cố định.
- Đo hiệu năng trước khi chạy update-by-query trên index lớn.

Script có thể tiêu tốn CPU và tạo write load đáng kể, đặc biệt khi update nhiều document. Cần đặt giới hạn, theo dõi thời gian chạy và chọn batch/throttling phù hợp.

## 18. Xử lý version conflict và retry

Elasticsearch dùng optimistic concurrency control. Nếu document thay đổi giữa lúc update đọc source và lúc ghi lại, thao tác có thể gặp version conflict.

Với Update API theo ID, có thể cấu hình retry-on-conflict để Elasticsearch thử lại thao tác khi có xung đột:

~~~http
POST /products/_update/P-1001?retry_on_conflict=3
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 1
    }
  }
}
~~~

Trong Spring Data, `UpdateQuery` có builder option cho retry conflict ở các phiên bản hỗ trợ:

~~~java
UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(script)
        .withRetryOnConflict(3)
        .build();
~~~

Retry không biến thao tác thành transaction nhiều document. Nó yêu cầu Elasticsearch thử lại update khi phát hiện xung đột.

Đối với script cộng dồn, cần cân nhắc tính idempotent. Nếu ứng dụng gửi lại cùng một event do timeout, script có thể cộng số lượng hai lần. Retry nội bộ của Elasticsearch xử lý version conflict; nó không giải quyết duplicate request ở tầng ứng dụng. Dùng event ID, idempotency key hoặc cơ chế deduplication nếu nghiệp vụ yêu cầu mỗi sự kiện chỉ được áp dụng một lần.

## 19. Bảo mật và kiểm soát script

Script là logic được thực thi trên cluster. Không nên cho client bên ngoài gửi source Painless tùy ý.

Một số nguyên tắc:

1. Source script do ứng dụng hoặc đội triển khai quản lý.
2. Giá trị đầu vào truyền qua params.
3. Validate kiểu dữ liệu, miền giá trị và kích thước tham số.
4. Không cho phép người dùng tự chọn field tùy ý nếu điều đó có thể sửa dữ liệu nhạy cảm.
5. Giới hạn quyền gọi update trên index cần thiết.
6. Tách quyền quản lý stored scripts khỏi quyền update runtime khi có thể.
7. Theo dõi script compilation, lỗi runtime và thời gian thực thi.
8. Không ghi bí mật vào params hoặc log.
9. Tránh script thực hiện vòng lặp không giới hạn hoặc xử lý cấu trúc quá lớn.
10. Kiểm tra chính sách script của Elasticsearch cluster và các giới hạn theo context.

Painless có sandbox nhưng không thay thế authorization của Elasticsearch. Người có quyền update document vẫn có thể làm thay đổi dữ liệu trong phạm vi quyền được cấp.

## 20. Những lỗi thường gặp

### Ghép tham số vào source string

Ghép trực tiếp user input vào source làm tăng nguy cơ lỗi quote, script cache miss và injection. Dùng `params`.

### Không kiểm tra field null

Phép cộng hoặc gọi method trên field thiếu/null có thể gây lỗi. Kiểm tra trước khi thao tác hoặc từ chối dữ liệu theo nghiệp vụ.

### Nhầm Script của Spring Data với Script của Java Client

Spring Data có kiểu `org.springframework.data.elasticsearch.core.query.Script`; Java API Client có kiểu riêng. Chọn đúng kiểu theo API đang gọi.

### Dùng Painless như Java đầy đủ

Painless chạy trong sandbox và chỉ cho phép API phù hợp với script context. Không giả định mọi class hoặc thư viện Java đều có thể dùng.

### Dùng script cho phép gán đơn giản

Nếu chỉ cập nhật `status = PUBLISHED`, partial document thường dễ hiểu hơn. Chỉ dùng script khi cần logic hoặc tính toán dựa trên giá trị hiện tại.

### Quên xử lý document chưa tồn tại

Update theo ID có thể thất bại nếu document không tồn tại. Dùng upsert khi nghiệp vụ cho phép và xác định rõ script có chạy khi upsert hay không.

### Nhầm noop với thành công nghiệp vụ

`ctx.op = 'noop'` chỉ có nghĩa không ghi document. Ứng dụng vẫn cần quyết định đó là kết quả hợp lệ, xung đột nghiệp vụ hay điều kiện bị từ chối.

### Cho rằng update-by-query nguyên tử

Update-by-query xử lý nhiều document theo batch. Có thể có partial success, conflict và failure. Luôn kiểm tra response.

### Retry làm duplicate event biến mất

Retry-on-conflict không chống duplicate request từ client. Dùng idempotency hoặc deduplication cho event có thể được gửi lại.

### Cập nhật mapping bằng Painless

Painless sửa source của document, không thay đổi mapping. Muốn đổi kiểu field hoặc cấu trúc mapping, cần quy trình quản lý mapping/reindex phù hợp.

## 21. Quy trình triển khai script update

Khi triển khai một cập nhật bằng Painless:

1. Xác định cập nhật là cho một document hay nhiều document.
2. Dùng partial document nếu chỉ gán giá trị cố định.
3. Viết Painless source với logic rõ ràng và có kiểm tra null.
4. Truyền dữ liệu thay đổi qua params.
5. Validate kiểu và miền giá trị ở ứng dụng.
6. Tạo Spring Data `Script` và `UpdateQuery`.
7. Chọn index/alias đích và routing nếu document yêu cầu custom routing.
8. Xác định hành vi khi document không tồn tại: lỗi, upsert hoặc scripted upsert.
9. Chọn chính sách noop, delete hoặc exception cho các nhánh điều kiện.
10. Cấu hình retry conflict nếu phù hợp.
11. Kiểm thử với document tồn tại, thiếu field, null, sai kiểu và điều kiện không thỏa.
12. Kiểm tra duplicate request và tính idempotent.
13. Theo dõi lỗi script, version conflict và thời gian thực thi.
14. Với update-by-query, kiểm tra số lượng updated, conflicts và failures.
15. Quản lý stored script bằng versioning và phân quyền triển khai.

## Tài liệu tham khảo

- [Elasticsearch — Painless scripting language](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-guide.html)
- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Update by query API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Elasticsearch — Script APIs](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting-using.html)
- [Spring Data Elasticsearch — Reference documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Data Elasticsearch — UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)

## Kết luận

Painless cho phép cập nhật document dựa trên source hiện tại, tham số đầu vào và điều kiện nghiệp vụ. Trong Spring Data Elasticsearch, tạo `Script` với source ổn định và params, gắn vào `UpdateQuery`, rồi gọi `ElasticsearchOperations.update(...)`. Dùng `ctx._source` để đọc/sửa dữ liệu, `params` để truyền giá trị, và `ctx.op` để điều khiển noop hoặc delete khi phù hợp. Phân biệt update một document với update-by-query, xử lý upsert và version conflict có chủ đích, đồng thời không dùng script thay cho partial update khi chỉ cần gán field cố định.
