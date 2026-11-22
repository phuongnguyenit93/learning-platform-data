# UpdateQuery, nội dung doc và trường cần cập nhật

Trong Spring Data Elasticsearch, `UpdateQuery` mô tả một thao tác cập nhật document đã tồn tại trong index. Thay vì gửi lại toàn bộ entity như thao tác index/save, ứng dụng có thể gửi một phần nội dung `doc` chỉ chứa những field cần thay đổi, hoặc gửi script để cập nhật giá trị dựa trên trạng thái hiện tại của document.

Điểm cốt lõi là phân biệt **nội dung document được gửi để cập nhật** với **các field thực sự xuất hiện trong payload cập nhật**. Với partial document update, field không có trong `doc` thường được giữ nguyên; field có trong `doc` được thêm hoặc thay giá trị. Nếu gửi cả object hoặc array, cần hiểu cách Elasticsearch merge cấu trúc đó. Đặc biệt, array thường được thay thế như một giá trị hoàn chỉnh, không tự merge từng phần tử theo ID.

`UpdateQuery` là lớp mô tả request; `ElasticsearchOperations.update(...)` mới thực thi thao tác trên index. Cách này hữu ích khi chỉ cần thay một vài thuộc tính, muốn dùng script cho phép tính atomic hoặc cần kiểm soát upsert và xử lý xung đột cập nhật.

## 1. Update document khác gì save/index document?

Giả sử một sản phẩm được lưu trong index:

```json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 120,
  "stock": 35,
  "description": "Wireless mechanical keyboard",
  "active": true
}
```

Một request thay đổi giá chỉ cần cập nhật `price`:

```json
POST /products/_update/KB-1001
{
  "doc": {
    "price": 135
  }
}
```

Sau update, document vẫn giữ `sku`, `name`, `stock`, `description` và `active`; chỉ `price` đổi thành `135`.

Nếu ứng dụng tạo một entity chỉ có `sku` và `price`, rồi gọi `save(entity)` để index lại cùng ID, các field không có trong entity có thể bị mất khỏi `_source` vì thao tác index ghi lại nội dung document. Do đó:

| Thao tác | Ý nghĩa |
|---|---|
| `save(entity)` / index document | Ghi document theo nội dung entity; thường thay thế source hiện tại của ID đó |
| `UpdateQuery` với `doc` | Gửi partial document để cập nhật field được cung cấp |
| `UpdateQuery` với script | Chạy logic cập nhật trên source hiện tại ở Elasticsearch |
| Update by query | Áp dụng update/script lên nhiều document thỏa query |

Chọn update khi muốn thay một phần document mà không phải đọc rồi ghi lại toàn bộ entity. Chọn save/index khi ứng dụng có bản đầy đủ, chuẩn của document và chủ đích thay thế nội dung.

## 2. UpdateQuery và ElasticsearchOperations

`UpdateQuery` thuộc package `org.springframework.data.elasticsearch.core.query`. Nó đóng gói thông tin cần cho Update API như document partial, script, upsert, routing, retry khi conflict và một số tùy chọn khác tùy phiên bản.

`ElasticsearchOperations` cung cấp API thực thi:

```java
UpdateResponse response = operations.update(updateQuery, indexCoordinates);
```

Trong đó:

- `updateQuery` mô tả ID và nội dung/script cần cập nhật.
- `indexCoordinates` xác định index hoặc alias đích.
- `UpdateResponse` chứa kết quả của thao tác update theo response Elasticsearch và phiên bản Spring Data.

Khác với repository save, UpdateQuery cho phép ứng dụng chủ động xác định phần dữ liệu cần ghi.

## 3. Tạo partial doc bằng Document

Spring Data Elasticsearch dùng `Document` để biểu diễn nội dung JSON ở dạng map. Có thể tạo một `Document` chỉ chứa những field cần thay đổi:

```java
import org.springframework.data.elasticsearch.core.document.Document;

Document partial = Document.create()
    .append("price", 135)
    .append("stock", 30);
```

`partial` không cần chứa `sku`, `name`, `description` hoặc `active`. Khi gửi như phần `doc` của Update API, các field không được cung cấp không bị ghi đè chỉ vì chúng vắng mặt.

### 3.1 Tạo UpdateQuery

```java
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .build();
```

Builder nhận ID document. `withDocument(partial)` đặt nội dung partial doc cần merge vào document hiện tại.

### 3.2 Thực thi update

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

public class ProductUpdateService {

    private final ElasticsearchOperations operations;

    public ProductUpdateService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse updatePrice(String id, double newPrice) {
        Document partial = Document.create()
            .append("price", newPrice);

        UpdateQuery updateQuery = UpdateQuery.builder(id)
            .withDocument(partial)
            .build();

        return operations.update(
            updateQuery,
            IndexCoordinates.of("products")
        );
    }
}
```

Ví dụ này chỉ cập nhật `price` của document có ID được truyền vào. Nếu document không tồn tại, hành vi mặc định là update không thành công theo semantics của Elasticsearch Update API; muốn tạo mới khi thiếu phải cấu hình upsert.

### 3.3 Dùng Document khi cần nhiều field

```java
Document partial = Document.create()
    .append("price", 135.0)
    .append("stock", 30)
    .append("active", true);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .build();

operations.update(updateQuery, IndexCoordinates.of("products"));
```

Chỉ ba field có mặt trong partial doc được cập nhật. Các field khác tiếp tục giữ giá trị hiện tại trong document.

## 4. Chọn đúng field cần cập nhật

Một partial doc nên chứa đúng các field thuộc yêu cầu nghiệp vụ. Không nên serialize toàn bộ request DTO hoặc entity vào `Document` nếu request chỉ được phép thay một vài thuộc tính.

Ví dụ request API:

```java
public record UpdateProductRequest(
    Double price,
    Integer stock,
    Boolean active
) {
}
```

Service có thể thêm field chỉ khi request thực sự cung cấp giá trị:

```java
Document partial = Document.create();

if (request.price() != null) {
    partial.append("price", request.price());
}

if (request.stock() != null) {
    partial.append("stock", request.stock());
}

if (request.active() != null) {
    partial.append("active", request.active());
}

if (partial.isEmpty()) {
    throw new IllegalArgumentException("No fields to update");
}
```

Sau đó dùng `partial` làm `doc`. Cách này phân biệt rõ “client không gửi field” với “client gửi một giá trị cần cập nhật”.

### 4.1 Không đồng nhất null với không được gửi

Trong JSON request, một field có thể:

- Không xuất hiện: client không yêu cầu thay đổi field đó.
- Xuất hiện với giá trị `null`: client muốn đặt field thành null, nếu nghiệp vụ cho phép.
- Xuất hiện với giá trị cụ thể: client muốn cập nhật sang giá trị đó.

Nếu dùng DTO với nullable field thông thường, cả “không gửi” và “gửi null” có thể cùng được ánh xạ thành Java `null`. Khi cần phân biệt, dùng JSON Merge Patch, `JsonNode`, wrapper có trạng thái presence hoặc DTO có kiểu biểu diễn rõ ràng cho ba trạng thái.

Ví dụ nếu `description` được phép xóa bằng null, hãy chỉ append `description: null` khi client thực sự gửi field. Nếu chỉ append khi giá trị khác null, API không thể yêu cầu đặt field về null.

### 4.2 Tên field trong Document

`Document` biểu diễn field trong JSON gửi tới Elasticsearch. Hãy dùng tên field theo mapping Elasticsearch, đặc biệt khi Java property có `@Field(name = "...")` hoặc tên được chuyển đổi bằng naming strategy.

Ví dụ:

```java
@Field(name = "product_status", type = FieldType.Keyword)
private String status;
```

Partial doc gửi trực tiếp có thể cần key `product_status` theo mapping, không tự giả định key là `status`. Kiểm tra mapping và cách converter/query API của phiên bản đang dùng xử lý tên field.

## 5. Cập nhật field lồng nhau

Elasticsearch partial update merge object JSON theo semantics của Update API. Nếu gửi một object con, các field con được cung cấp có thể được merge vào object hiện tại; field con không có trong partial object thường được giữ nguyên.

Document hiện tại:

```json
{
  "name": "Mechanical Keyboard",
  "manufacturer": {
    "name": "Northwind",
    "country": "VN",
    "supportEmail": "help@example.test"
  }
}
```

Partial update:

```json
{
  "doc": {
    "manufacturer": {
      "supportEmail": "support@example.test"
    }
  }
}
```

Theo semantics merge object, `manufacturer.supportEmail` được thay; `manufacturer.name` và `manufacturer.country` được giữ nguyên.

### 5.1 Array không được merge từng phần tử theo khóa

Với array, không nên giả định partial doc tự tìm phần tử có cùng `sku` rồi chỉ cập nhật một thuộc tính.

Document hiện tại:

```json
{
  "variants": [
    { "sku": "RED-M", "color": "red", "price": 120 },
    { "sku": "BLUE-L", "color": "blue", "price": 140 }
  ]
}
```

Nếu gửi:

```json
{
  "doc": {
    "variants": [
      { "sku": "RED-M", "price": 125 }
    ]
  }
}
```

array `variants` có thể bị thay bằng array chỉ chứa phần tử được gửi, làm mất `BLUE-L`. Elasticsearch không tự hiểu `sku` là khóa để merge từng phần tử array.

Nếu cần cập nhật một phần tử trong array, có hai hướng:

1. Đọc mảng hiện tại, sửa phần tử trong ứng dụng rồi gửi lại toàn bộ array; cần xử lý concurrency để tránh ghi đè thay đổi đồng thời.
2. Dùng script Painless để tìm phần tử theo khóa và thay field tương ứng trong `_source` ở phía Elasticsearch.

Nếu phần tử con có vòng đời và cập nhật độc lập thường xuyên, cân nhắc mô hình hóa chúng thành document riêng hoặc dùng nested/object theo đúng nhu cầu truy vấn.

## 6. Upsert: cập nhật hoặc tạo mới

Update API mặc định yêu cầu document đã tồn tại. Nếu muốn tạo document khi ID chưa có, có thể dùng upsert.

### 6.1 `doc_as_upsert`

`doc_as_upsert` yêu cầu dùng chính partial doc làm nội dung tạo mới nếu document chưa tồn tại:

```java
Document partial = Document.create()
    .append("sku", "KB-1001")
    .append("name", "Mechanical Keyboard")
    .append("price", 135.0)
    .append("stock", 30);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .withDocAsUpsert(true)
    .build();

operations.update(updateQuery, IndexCoordinates.of("products"));
```

Nếu ID chưa tồn tại, Elasticsearch tạo document từ nội dung `doc`. Vì vậy, partial doc phải đủ field tối thiểu để document mới hợp lệ theo mapping và nghiệp vụ. Không bật doc-as-upsert cho payload chỉ có một field như `stock` nếu document mới bắt buộc phải có `sku`, `name` và các field khác.

### 6.2 `upsert` riêng

Có thể chỉ định nội dung dùng riêng cho trường hợp document chưa tồn tại:

```java
Document partial = Document.create()
    .append("price", 135.0);

Document initialDocument = Document.create()
    .append("sku", "KB-1001")
    .append("name", "Mechanical Keyboard")
    .append("price", 135.0)
    .append("stock", 0)
    .append("active", true);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .withUpsert(initialDocument)
    .build();
```

Khi document đã tồn tại, Elasticsearch áp dụng `partial`; khi chưa tồn tại, dùng `initialDocument` để tạo. Cách này cho phép nội dung tạo mới đầy đủ hơn nội dung update.

### 6.3 Chọn doc_as_upsert hay upsert riêng

| Trường hợp | Cách dùng |
|---|---|
| Partial doc đã đủ làm document mới | `doc_as_upsert` |
| Nội dung tạo mới khác nội dung cập nhật | `upsert` riêng |
| Chỉ cập nhật document hiện có | Không cấu hình upsert |
| Dùng script và muốn tạo mới khi chưa có | Scripted upsert theo API phù hợp |

Upsert không có nghĩa là mọi lỗi update đều tự động tạo document. Nó chỉ xử lý trường hợp document ID chưa tồn tại theo cấu hình request; lỗi mapping, validation hoặc cluster vẫn có thể thất bại.

## 7. Dùng script để cập nhật theo trạng thái hiện tại

Partial `doc` phù hợp khi giá trị mới đã được ứng dụng tính sẵn. Script phù hợp khi cần đọc giá trị hiện tại và thực hiện phép biến đổi atomic tại Elasticsearch.

Ví dụ tăng stock thêm một lượng:

```json
POST /products/_update/KB-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 5
    }
  }
}
```

Thay vì ứng dụng đọc stock hiện tại, cộng 5 rồi ghi giá trị mới (có nguy cơ lost update), script thực hiện phép cộng trong thao tác update ở Elasticsearch.

### 7.1 Script với điều kiện

Có thể kiểm tra trạng thái trước khi cập nhật:

```json
POST /products/_update/KB-1001
{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.stock >= params.amount) { ctx._source.stock -= params.amount; } else { ctx.op = 'none'; }",
    "params": {
      "amount": 2
    }
  }
}
```

Nếu stock đủ, script trừ số lượng. Nếu không đủ, `ctx.op = 'none'` khiến document không thay đổi. Trong nghiệp vụ thực tế, cần xác định response `noop` có nghĩa gì và trả kết quả phù hợp cho caller.

### 7.2 Script không nên nối trực tiếp input vào source

Không tạo script bằng cách nối chuỗi do người dùng gửi:

```java
// Không nên: input được nối trực tiếp vào script source.
String source = "ctx._source.stock += " + userInput;
```

Hãy giữ source cố định và truyền giá trị qua `params`. Cách này giảm nguy cơ script injection, tránh lỗi escaping và cho phép Elasticsearch cache compiled script hiệu quả hơn.

### 7.3 Script trong UpdateQuery

Spring Data Elasticsearch cung cấp các thuộc tính builder cho script như source, language, parameters và script type theo phiên bản. Ví dụ minh họa theo API builder thường gặp:

```java
Map<String, Object> params = Map.of("amount", 5);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withScript("ctx._source.stock += params.amount")
    .withLang("painless")
    .withParams(params)
    .build();

UpdateResponse response = operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
```

Tên method và overload script có thể thay đổi theo phiên bản Spring Data Elasticsearch; hãy đối chiếu Javadoc đúng dependency. Về mặt Elasticsearch, request tương ứng là một Update API có `script` và `params`.

### 7.4 Script thay đổi nhiều field

```json
POST /products/_update/KB-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock -= params.quantity; ctx._source.updatedAt = params.updatedAt; ctx._source.lastOrderId = params.orderId",
    "params": {
      "quantity": 2,
      "updatedAt": "2025-03-12T10:30:00Z",
      "orderId": "ORDER-9001"
    }
  }
}
```

Một script có thể cập nhật nhiều field dựa trên cùng trạng thái hiện tại. Hãy validate tham số ở ứng dụng và bảo đảm script xử lý field thiếu/null theo đúng nghiệp vụ.

## 8. Xóa field hoặc đặt field thành null

Hai thao tác có semantics khác nhau:

- Đặt field thành `null`: field có thể vẫn tồn tại trong `_source` với giá trị null.
- Xóa field khỏi `_source`: key bị loại khỏi object.

Partial doc:

```json
{
  "doc": {
    "description": null
  }
}
```

Script xóa key:

```json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.remove('description')"
  }
}
```

Nếu API có thao tác “clear field”, hãy quyết định dùng null hay remove. Mapping, query semantics và cách ứng dụng serialize document có thể làm hai trạng thái này khác nhau.

## 9. Cập nhật mảng nested/object

Với mảng object, cập nhật một thuộc tính của một phần tử theo khóa thường cần script hoặc read-modify-write toàn bộ array.

Ví dụ Painless tìm variant theo SKU:

```json
POST /products/_update/product-1001
{
  "script": {
    "lang": "painless",
    "source": "for (def variant : ctx._source.variants) { if (variant.sku == params.sku) { variant.price = params.price; } }",
    "params": {
      "sku": "RED-M",
      "price": 125
    }
  }
}
```

Script duyệt array hiện tại và thay giá của phần tử có SKU phù hợp. Cần quyết định điều gì xảy ra nếu không tìm thấy SKU: không làm gì, thêm variant mới hay báo lỗi. Có thể dùng cờ boolean trong script và đặt `ctx.op = 'none'` hoặc ném lỗi theo semantics đã chọn.

Nếu dùng read-modify-write ở ứng dụng, hãy kết hợp optimistic concurrency hoặc cơ chế kiểm soát phiên bản để tránh hai request đồng thời ghi đè thay đổi của nhau.

## 10. Xung đột cập nhật và retry_on_conflict

Elasticsearch Update API đọc document hiện tại, áp dụng partial doc/script rồi index lại document đã thay đổi. Nếu có một update khác xảy ra đồng thời, thao tác có thể gặp version conflict.

`retry_on_conflict` cho phép Elasticsearch thử lại update khi gặp conflict:

```java
UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(Document.create().append("stock", 30))
    .withRetryOnConflict(3)
    .build();
```

Giá trị `3` cho phép retry một số lần theo cấu hình API. Retry hữu ích khi nhiều cập nhật đồng thời nhưng không phải giải pháp cho mọi xung đột. Nếu update phụ thuộc vào trạng thái nghiệp vụ cũ hoặc cần caller biết dữ liệu đã thay đổi, hãy dùng optimistic concurrency.

### 10.1 Optimistic concurrency với sequence number và primary term

Elasticsearch có thể bảo vệ update bằng `if_seq_no` và `if_primary_term`:

```http
POST /products/_update/KB-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "price": 135
  }
}
```

Update chỉ thành công nếu document vẫn ở sequence number và primary term mà ứng dụng đã đọc. Nếu document thay đổi, Elasticsearch trả version conflict; ứng dụng cần đọc lại và quyết định có tính lại update hay báo xung đột.

Trong Spring Data, `UpdateQuery` có thể expose các tùy chọn `ifSeqNo`/`ifPrimaryTerm` theo phiên bản. Dùng chúng khi cần bảo đảm cập nhật dựa trên phiên bản đã đọc, thay vì retry mù.

### 10.2 Chọn retry hay optimistic concurrency

| Nhu cầu | Cơ chế |
|---|---|
| Update đơn giản, có thể áp dụng lại khi conflict | `retry_on_conflict` |
| Caller cần phát hiện document đã thay đổi từ lúc đọc | `if_seq_no` + `if_primary_term` |
| Cập nhật số lượng tăng/giảm atomic | Script có params; cân nhắc retry policy |
| Quy tắc nghiệp vụ phụ thuộc trạng thái cũ và cần quyết định lại | Optimistic concurrency + đọc lại |

## 11. Routing, refresh và các tùy chọn khác

Ngoài ID và nội dung cập nhật, UpdateQuery có thể mang một số tùy chọn request:

- **Routing:** dùng cùng routing value đã dùng khi index document nếu index có custom routing.
- **Retry on conflict:** số lần thử lại khi update conflict.
- **Refresh policy:** điều khiển thời điểm thay đổi có thể nhìn thấy trong search.
- **Upsert:** tạo document nếu ID chưa tồn tại.
- **Fetch source:** yêu cầu trả source sau update nếu use case cần.
- **Sequence number/primary term:** optimistic concurrency nếu API phiên bản hỗ trợ.

Ví dụ cấu hình routing và refresh:

```java
UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(Document.create().append("price", 135))
    .withRouting("tenant-42")
    .withRetryOnConflict(3)
    .build();
```

Routing phải khớp với routing khi document được index. Nếu bỏ routing hoặc dùng sai routing, Elasticsearch có thể không tìm thấy document ở shard mong muốn.

Không đặt refresh `IMMEDIATE` cho mọi update chỉ để đọc thấy dữ liệu ngay lập tức. Refresh thường xuyên có thể làm giảm hiệu năng indexing. Dùng refresh policy theo yêu cầu nhất quán của API; mặc định chờ refresh định kỳ thường phù hợp với workload ghi lớn.

## 12. Bulk update nhiều document

Nếu cần cập nhật nhiều document theo danh sách ID, không nên gửi từng request tuần tự khi có thể gom thành bulk request. Spring Data Elasticsearch có API `bulkUpdate(...)` với collection `UpdateQuery` theo phiên bản.

Ví dụ khởi tạo danh sách update:

```java
List<UpdateQuery> updates = List.of(
    UpdateQuery.builder("KB-1001")
        .withDocument(Document.create().append("price", 135))
        .build(),
    UpdateQuery.builder("KB-1002")
        .withDocument(Document.create().append("price", 145))
        .build(),
    UpdateQuery.builder("MS-2001")
        .withDocument(Document.create().append("stock", 50))
        .build()
);

operations.bulkUpdate(updates, IndexCoordinates.of("products"));
```

Bulk giảm overhead network và cho phép Elasticsearch xử lý nhiều thao tác trong một request. Tuy nhiên, một bulk request không phải transaction nguyên tử: một số item có thể thành công trong khi item khác thất bại. Hãy kiểm tra kết quả từng item theo API trả về của phiên bản, ghi nhận ID lỗi và retry có chọn lọc.

### 12.1 Chia bulk thành batch vừa phải

Không gom hàng trăm nghìn update vào một request duy nhất. Chọn batch size theo payload, latency, throughput và giới hạn cluster. Theo dõi lỗi 429/rejected execution, retry có backoff và tránh tạo quá nhiều request đồng thời.

### 12.2 Bulk update khác update_by_query

- `bulkUpdate`: ứng dụng chỉ định từng ID và partial update/script cho từng document.
- `update_by_query`: Elasticsearch tìm document theo query rồi áp dụng script/update trên tất cả document match.

Nếu danh sách ID đã biết, bulk update thường phù hợp. Nếu cần thay đổi mọi document thỏa một điều kiện, update by query có thể phù hợp hơn nhưng cần hiểu conflict, slicing, throttling và tác động cluster.

## 13. Update by query và UpdateQuery không giống nhau

`UpdateQuery` mô tả update cho một document ID cụ thể. Update by query là thao tác trên tập document thỏa query:

```http
POST /products/_update_by_query
{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = 'ARCHIVED'"
  }
}
```

Update by query có thể xử lý lượng document lớn và có các tùy chọn riêng như conflicts, slices, requests_per_second, refresh và wait_for_completion. Không dùng nó thay thế một UpdateQuery đơn lẻ khi đã biết ID document.

## 14. Mapping và chuyển đổi dữ liệu

Partial doc vẫn phải tương thích với mapping của index. Nếu field `price` là `double`, gửi chuỗi không parse được có thể gây lỗi mapping. Nếu field là `keyword`, hãy gửi giá trị phù hợp. Nếu field có custom date format, giá trị ngày cần tương thích format.

Ví dụ entity:

```java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Integer)
    private Integer stock;
}
```

Partial `Document` nên gửi số đúng kiểu:

```java
Document partial = Document.create()
    .append("price", 135.0)
    .append("stock", 30);
```

Khi dùng `Document` trực tiếp, đừng mặc định mọi converter metadata của entity đều tự áp dụng cho key và giá trị. Nếu cần custom conversion, date/time serialization hoặc field name mapping, cân nhắc dùng converter để tạo `Document` hoặc kiểm tra JSON request thực tế.

## 15. Kết quả UpdateResponse

Update API có thể trả trạng thái như:

- `updated`: document đã được cập nhật.
- `created`: document được tạo thông qua upsert.
- `noop`: script hoặc request không làm thay đổi document.
- `not_found`: document không tồn tại trong một số response/API flow.
- Version conflict hoặc lỗi mapping/request: thao tác thất bại.

Response có thể chứa version, sequence number và primary term tùy API. Hãy xử lý các trạng thái này theo nghiệp vụ; không coi mọi response không ném exception là “đã thay đổi dữ liệu”. Nếu dùng script có `ctx.op = 'none'`, `noop` là kết quả có chủ đích.

## 16. Những lỗi thường gặp

### 16.1 Gửi toàn bộ entity khi chỉ muốn cập nhật một field

Nếu serialize toàn bộ entity, field null hoặc giá trị mặc định có thể ghi đè dữ liệu hiện tại. Tạo partial `Document` chỉ chứa field được phép thay đổi.

### 16.2 Nghĩ field vắng mặt và field null giống nhau

Field vắng mặt thường được giữ nguyên; field gửi null có thể được đặt thành null. API cần biểu diễn rõ sự khác biệt giữa không gửi và xóa/clear.

### 16.3 Cập nhật một phần tử array bằng partial array

Elasticsearch không tự merge array theo `sku` hoặc ID con. Gửi array mới có thể thay toàn bộ array. Dùng script hoặc read-modify-write có concurrency control.

### 16.4 Quên upsert

Update document không tồn tại sẽ không tự tạo nếu không cấu hình upsert. Dùng `doc_as_upsert` hoặc upsert riêng khi nghiệp vụ cho phép.

### 16.5 Dùng doc_as_upsert với payload thiếu field bắt buộc

Nếu document chưa tồn tại, partial doc sẽ trở thành document mới. Bảo đảm nó đủ dữ liệu tối thiểu hoặc cung cấp upsert đầy đủ.

### 16.6 Tính toán giá trị mới ở ứng dụng rồi ghi đè

Đọc stock, cộng/trừ ở Java rồi update có thể mất thay đổi của request đồng thời. Dùng script atomic hoặc optimistic concurrency phù hợp.

### 16.7 Dùng routing sai

Document được index với custom routing phải được update bằng cùng routing. Nếu không, Elasticsearch có thể không tìm thấy document.

### 16.8 Không xử lý version conflict

Nhiều writer có thể cập nhật cùng ID. Chọn retry_on_conflict hoặc optimistic concurrency theo semantics nghiệp vụ và ghi nhận conflict.

### 16.9 Bulk request được coi là transaction

Bulk có thể thành công một phần. Kiểm tra kết quả từng item, retry có chọn lọc và thiết kế thao tác idempotent.

### 16.10 Refresh ngay sau mọi update

Refresh immediate làm tăng chi phí. Chỉ dùng khi cần read-after-write tức thì; nếu không, dùng refresh policy mặc định hoặc theo batch.

## 17. Quy trình xây dựng service cập nhật an toàn

Một service update có thể tổ chức theo các bước:

1. Xác thực ID và quyền cập nhật document.
2. Chỉ cho phép field thuộc allowlist nghiệp vụ.
3. Phân biệt field không được gửi với field được yêu cầu đặt null.
4. Validate kiểu dữ liệu và giới hạn giá trị.
5. Tạo partial `Document` chỉ chứa field cần thay đổi.
6. Chọn update, script hoặc upsert theo yêu cầu.
7. Thêm routing/concurrency option nếu index cần.
8. Thực thi bằng `ElasticsearchOperations.update(...)`.
9. Kiểm tra UpdateResponse và xử lý not-found/noop/conflict.
10. Chỉ refresh ngay nếu API cần đọc thấy thay đổi tức thì.

Với cập nhật nhiều document, dùng bulk theo batch vừa phải và kiểm tra kết quả từng item. Với update phức tạp trên array hoặc phép tính atomic, cân nhắc script Painless với params.

## 18. Ví dụ service tổng hợp

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;
import org.springframework.stereotype.Service;

@Service
public class ProductUpdateService {

    private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductUpdateService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse changePrice(String id, double price) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }

        Document partial = Document.create()
            .append("price", price);

        UpdateQuery update = UpdateQuery.builder(id)
            .withDocument(partial)
            .withRetryOnConflict(3)
            .build();

        return operations.update(update, PRODUCTS);
    }

    public UpdateResponse increaseStock(String id, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        UpdateQuery update = UpdateQuery.builder(id)
            .withScript("ctx._source.stock += params.amount")
            .withLang("painless")
            .withParams(Map.of("amount", amount))
            .withRetryOnConflict(3)
            .build();

        return operations.update(update, PRODUCTS);
    }

    public UpdateResponse createOrUpdate(
            String id,
            String sku,
            String name,
            double price) {

        Document partial = Document.create()
            .append("price", price);

        Document initial = Document.create()
            .append("sku", sku)
            .append("name", name)
            .append("price", price)
            .append("stock", 0)
            .append("active", true);

        UpdateQuery update = UpdateQuery.builder(id)
            .withDocument(partial)
            .withUpsert(initial)
            .build();

        return operations.update(update, PRODUCTS);
    }
}
```

Ví dụ minh họa ba nhu cầu khác nhau: cập nhật field bằng partial doc, thay đổi stock theo phép cộng script và upsert với nội dung tạo mới riêng. Các method script/builder cụ thể cần đối chiếu phiên bản Spring Data Elasticsearch đang sử dụng.

## 19. Nguyên tắc sử dụng

- Dùng `UpdateQuery` khi cần cập nhật một document theo ID mà không ghi lại toàn bộ source.
- Dùng `Document` partial chỉ chứa field được phép thay đổi.
- Hiểu rõ field vắng mặt, field null và thao tác remove có semantics khác nhau.
- Kiểm tra tên field theo mapping Elasticsearch, nhất là khi Java property có tên khác.
- Không giả định array object được merge từng phần tử; dùng script hoặc read-modify-write có concurrency control.
- Dùng `doc_as_upsert` khi partial doc đủ làm document mới; dùng upsert riêng khi nội dung tạo mới khác nội dung update.
- Dùng script với params cho phép tính dựa trên trạng thái hiện tại và tránh nối input vào script source.
- Dùng `retry_on_conflict` cho conflict có thể retry; dùng sequence number/primary term khi cần optimistic concurrency.
- Truyền routing đúng với cách document đã được index.
- Dùng bulk update cho nhiều ID nhưng xử lý kết quả từng item vì bulk không nguyên tử.
- Phân biệt update theo ID với update by query.
- Không ép refresh immediate nếu không cần read-after-write tức thì.
- Kiểm tra `UpdateResponse` và xử lý updated/created/noop/not-found/conflict theo nghiệp vụ.

## 20. Tổng kết

`UpdateQuery` là cách Spring Data Elasticsearch mô tả thao tác Update API cho một document. Với `withDocument(Document)`, ứng dụng gửi partial doc chỉ chứa field cần thay đổi; field không xuất hiện thường được giữ nguyên. Điều này khác với `save(entity)`/index document, vốn thường ghi lại source theo nội dung entity. Cần phân biệt field vắng mặt với null, và đặc biệt nhớ rằng array không tự merge từng phần tử theo khóa.

Khi document chưa tồn tại, có thể dùng `doc_as_upsert` nếu partial doc đủ làm document mới hoặc cung cấp upsert riêng. Khi cần cập nhật dựa trên trạng thái hiện tại, script Painless với params cho phép thực hiện phép tính atomic ở Elasticsearch. Với writer đồng thời, chọn `retry_on_conflict` hoặc optimistic concurrency qua sequence number/primary term. Với nhiều ID, dùng bulk update theo batch và kiểm tra kết quả từng item.

Trong Spring Data Elasticsearch, tạo `UpdateQuery`, chọn đúng ID/document/script/options rồi gọi `ElasticsearchOperations.update(...)` với `IndexCoordinates`. Hãy giới hạn field được cập nhật ở tầng nghiệp vụ, kiểm tra mapping/routing, xử lý response rõ ràng và chỉ dùng refresh tức thì khi cần. Thiết kế đúng partial doc và concurrency giúp tránh mất field, lost update và lỗi dữ liệu khi cập nhật document.

## Tài liệu tham khảo

- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Update by query API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Elasticsearch — Painless scripting](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-guide.html)
- [Spring Data Elasticsearch Reference — Template API](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch API — UpdateQuery](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
