# SeqNoPrimaryTerm và cách mang metadata khi cập nhật

Elasticsearch hỗ trợ optimistic concurrency control (kiểm soát đồng thời lạc quan) bằng cặp metadata `_seq_no` và `_primary_term`. Khi đọc một document, ứng dụng có thể giữ lại hai giá trị này rồi gửi chúng cùng yêu cầu cập nhật hoặc xóa. Elasticsearch chỉ thực hiện thao tác nếu document vẫn ở đúng trạng thái mà ứng dụng đã đọc. Nếu một tiến trình khác đã thay đổi document, request cũ nhận lỗi version conflict thay vì âm thầm ghi đè dữ liệu mới.

Trong Spring Data Elasticsearch, metadata này cần được mang theo từ kết quả đọc đến thao tác ghi tiếp theo. Có thể lấy sequence number và primary term từ `SearchHit`, đóng gói vào DTO hoặc một kiểu `SeqNoPrimaryTerm` của ứng dụng, rồi truyền chúng vào `IndexQuery`, `UpdateQuery` hoặc Elasticsearch Java API Client tương ứng với phiên bản đang dùng.

Điều quan trọng là không xem `_seq_no` và `_primary_term` như hai field nghiệp vụ của document. Đây là metadata do Elasticsearch quản lý để xác định phiên bản thao tác trên shard. Ứng dụng giữ chúng như một concurrency token và gửi lại khi muốn cập nhật có điều kiện.

## 1. Vấn đề lost update

Giả sử hai người dùng cùng đọc một sản phẩm có số lượng tồn kho là 10. Cả hai cùng nhận dữ liệu ở thời điểm gần như nhau:

```text
Document ban đầu: stock = 10

Người dùng A đọc stock = 10
Người dùng B đọc stock = 10

A tính stock mới = 9 và ghi thành công
B tính stock mới = 8 dựa trên stock cũ = 10

Nếu B ghi đè không có kiểm soát:
  stock = 8

Thay đổi của A có thể bị mất.
```

Đây là lost update: một cập nhật dựa trên dữ liệu cũ ghi đè một cập nhật mới hơn. Với dữ liệu quan trọng, việc ghi đè âm thầm có thể gây sai tồn kho, trạng thái đơn hàng hoặc thông tin tài khoản.

Optimistic concurrency control cho phép cả hai tiến trình đọc bình thường, nhưng khi ghi thì Elasticsearch xác minh metadata mà tiến trình đã đọc. Chỉ một request có thể cập nhật document từ đúng phiên bản đó; request còn lại bị từ chối và phải đọc lại dữ liệu mới nhất trước khi quyết định.

## 2. `_seq_no` là gì?

`_seq_no` (sequence number) là số thứ tự thao tác do Elasticsearch cấp trong phạm vi một shard. Mỗi thao tác thay đổi dữ liệu được ghi nhận với sequence number tương ứng, giúp Elasticsearch xác định thứ tự các thao tác trên shard.

Một số đặc điểm:

- Sequence number được quản lý ở cấp shard, không phải số thứ tự toàn cluster.
- Mỗi thao tác index, update hoặc delete được ghi nhận bằng sequence number.
- Giá trị tăng theo lịch sử thao tác trên shard.
- Hai document ở hai shard khác nhau có thể có cùng `_seq_no`.
- Không dùng `_seq_no` như ID nghiệp vụ hoặc số version toàn cục.

Ví dụ response GET:

```json
{
  "_index": "products",
  "_id": "p-100",
  "_version": 7,
  "_seq_no": 42,
  "_primary_term": 3,
  "found": true,
  "_source": {
    "name": "Wireless Mouse",
    "stock": 10
  }
}
```

Trong ví dụ, thao tác cuối cùng trên document có sequence number 42 trong lịch sử shard và primary term 3.

## 3. `_primary_term` là gì?

`_primary_term` là số thế hệ của primary shard. Khi primary shard được promote sau một sự cố hoặc thay đổi phân bổ shard, Elasticsearch tăng primary term để phân biệt lịch sử thao tác của primary cũ và primary mới.

Primary term giúp ngăn một request cũ dựa trên lịch sử primary trước đó được áp dụng nhầm sau khi shard đã chuyển sang primary khác.

Các điểm cần nhớ:

- Primary term được quản lý ở cấp shard.
- Giá trị thay đổi khi một primary mới được bầu/promote.
- Nó không phải số lần document được cập nhật.
- Nhiều document trên cùng shard có thể có cùng primary term.
- Không tự tăng primary term ở ứng dụng và không đưa giá trị này vào `_source`.

## 4. Vì sao cần cả hai giá trị?

`_seq_no` xác định vị trí thao tác trong lịch sử shard; `_primary_term` xác định thế hệ primary đã tạo ra thao tác đó. Cặp giá trị kết hợp tạo thành concurrency token cho lần đọc.

```text
Concurrency token = (_seq_no, _primary_term)

Ví dụ:
  _seq_no       = 42
  _primary_term = 3
```

Khi gửi cập nhật với cả hai giá trị, Elasticsearch kiểm tra thao tác mới có còn dựa trên trạng thái hiện tại mà ứng dụng đã đọc hay không. Nếu metadata không còn khớp, request bị từ chối với conflict.

Không chỉ gửi `_seq_no` hoặc chỉ gửi `_primary_term` để thay thế cặp điều kiện. Optimistic concurrency control của các API tương ứng dùng cả `if_seq_no` và `if_primary_term`.

## 5. Đọc metadata bằng GET API

GET theo ID trả metadata `_seq_no` và `_primary_term` trong response:

```http
GET /products/_doc/p-100
```

Response rút gọn:

```json
{
  "_index": "products",
  "_id": "p-100",
  "_version": 7,
  "_seq_no": 42,
  "_primary_term": 3,
  "found": true,
  "_source": {
    "name": "Wireless Mouse",
    "stock": 10
  }
}
```

GET realtime mặc định có thể trả document mới nhất theo ID ngay cả khi thay đổi chưa được refresh để search nhìn thấy. Đây là điểm hữu ích khi ứng dụng cần đọc document và lấy concurrency token trước khi cập nhật.

### Metadata không nằm trong `_source`

`_seq_no`, `_primary_term` và `_version` là metadata của hit/document do Elasticsearch trả về. Chúng không tự động trở thành các thuộc tính trong `_source`. Nếu ứng dụng muốn giữ chúng qua nhiều tầng, cần lấy từ response metadata và lưu riêng trong DTO hoặc object quản lý trạng thái.

## 6. Đọc metadata trong Search API

Kết quả `_search` có thể yêu cầu Elasticsearch trả sequence number và primary term của từng hit bằng tùy chọn `seq_no_primary_term`:

```http
POST /products/_search
Content-Type: application/json

{
  "seq_no_primary_term": true,
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
```

Hit có thể chứa:

```json
{
  "_index": "products",
  "_id": "p-100",
  "_score": 1.0,
  "_seq_no": 42,
  "_primary_term": 3,
  "_source": {
    "name": "Wireless Mouse",
    "stock": 10,
    "status": "PUBLISHED"
  }
}
```

Tùy chọn này hữu ích khi lấy danh sách bằng search rồi muốn cập nhật có điều kiện từng hit. Nếu không yêu cầu metadata, response search có thể không chứa cặp giá trị này; đừng suy ra từ `_version` hoặc tự tính.

## 7. Gửi cập nhật có điều kiện bằng Index API

Index API hỗ trợ `if_seq_no` và `if_primary_term`. Ví dụ ứng dụng đã đọc document với `_seq_no = 42` và `_primary_term = 3`:

```http
PUT /products/_doc/p-100?if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "name": "Wireless Mouse",
  "stock": 9,
  "status": "PUBLISHED"
}
```

Elasticsearch chỉ index document nếu sequence number và primary term hiện tại phù hợp với cặp điều kiện. Nếu một tiến trình khác đã cập nhật hoặc xóa document sau lần đọc, request có thể trả HTTP `409 Conflict`.

### Lưu ý với Index API

Index API thay thế `_source` của document bằng nội dung request. Nếu chỉ muốn thay đổi một vài field, phải gửi đầy đủ document mới hoặc dùng Update API. Không gửi một phần source vào Index API với kỳ vọng các field cũ tự được giữ lại.

## 8. Gửi cập nhật từng phần bằng Update API

Update API cũng hỗ trợ optimistic concurrency condition:

```http
POST /products/_update/p-100?if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "stock": 9
  }
}
```

Request chỉ cập nhật field `stock`, giữ các field khác theo hành vi update. Nếu document đã thay đổi từ khi ứng dụng đọc metadata, Elasticsearch trả conflict.

Đây là lựa chọn phù hợp khi ứng dụng chỉ thay đổi một phần document và muốn bảo vệ thao tác khỏi lost update.

## 9. Xóa có điều kiện bằng Delete API

Delete API cũng có thể dùng cùng cặp điều kiện:

```http
DELETE /products/_doc/p-100?if_seq_no=42&if_primary_term=3
```

Nếu document đã được cập nhật sau lần đọc, delete cũ không được phép xóa phiên bản mới hơn. Đây là điểm quan trọng khi một tiến trình đọc trạng thái rồi mới quyết định xóa document.

## 10. Điều gì xảy ra khi metadata đã cũ?

Giả sử hai request cùng đọc cặp token `(42, 3)`:

```text
Trạng thái ban đầu:
  seq_no = 42
  primary_term = 3

Request A gửi if_seq_no=42, if_primary_term=3
  -> thành công
  -> trạng thái mới seq_no = 43, primary_term = 3

Request B vẫn gửi if_seq_no=42, if_primary_term=3
  -> 409 version conflict
```

Elasticsearch không tự hợp nhất thay đổi của A và B. Ứng dụng phải quyết định cách giải quyết conflict dựa trên nghiệp vụ.

### Response conflict

Response thường có dạng:

```json
{
  "error": {
    "type": "version_conflict_engine_exception",
    "reason": "required seqNo [42], primary term [3]. current document has seqNo [43] and primary term [3]",
    "index": "products",
    "shard": "1",
    "index_uuid": "..."
  },
  "status": 409
}
```

Nội dung `reason` có thể khác theo version và tình huống cụ thể. Hãy xử lý theo HTTP status/error type thay vì parse nguyên văn chuỗi reason.

## 11. Quy trình xử lý conflict đúng cách

Khi nhận `409 Conflict`, không nên gửi lại ngay request cũ với cùng metadata vì cặp token vẫn đã cũ. Một quy trình phổ biến:

1. Đọc lại document mới nhất bằng GET hoặc query phù hợp.
2. Lấy `_seq_no` và `_primary_term` mới.
3. Đánh giá thay đổi mới có ảnh hưởng tới nghiệp vụ hay không.
4. Tính lại nội dung cập nhật dựa trên trạng thái mới.
5. Gửi request với cặp metadata mới.
6. Nếu tiếp tục conflict, retry có giới hạn và backoff hoặc trả lỗi để người dùng giải quyết.

Ví dụ tồn kho:

- Người dùng A và B cùng đọc stock = 10.
- A trừ 1, ghi thành công stock = 9.
- B nhận conflict khi muốn ghi stock = 8.
- B đọc lại stock = 9, kiểm tra điều kiện và tính lại stock = 8.
- B thử cập nhật với token mới.

Điều này giúp bảo toàn cả hai thao tác trừ kho nếu nghiệp vụ cho phép. Nếu B chỉ gửi lại giá trị 8 cũ mà không tính lại, kết quả có thể vẫn sai về mặt nghiệp vụ dù request mới thành công.

### Retry không phải lúc nào cũng đúng

Nếu cập nhật là một lệnh đặt trạng thái cụ thể, ví dụ “chuyển đơn hàng sang CANCELLED”, cần kiểm tra trạng thái mới nhất trước khi retry. Nếu một tiến trình khác đã chuyển đơn sang SHIPPED, không nên tự động ghi đè sang CANCELLED chỉ để hết conflict.

## 12. Phân biệt `_seq_no`/`_primary_term` với `_version`

Elasticsearch có metadata `_version` và cặp `_seq_no`/`_primary_term`, nhưng chúng không phải cùng một cơ chế.

| Metadata | Ý nghĩa | Phạm vi |
|---|---|---|
| `_version` | Phiên bản document theo cơ chế versioning của Elasticsearch | Gắn với document và versioning API |
| `_seq_no` | Số thứ tự thao tác trên shard | Cấp shard |
| `_primary_term` | Thế hệ primary shard | Cấp shard |
| `(_seq_no, _primary_term)` | Token để kiểm tra thao tác dựa trên trạng thái đã đọc | Kết hợp shard history và primary generation |

Không lấy `_version` rồi gán vào `if_seq_no`. Hai giá trị không thể thay thế nhau. Tương tự, `@Version` của Spring Data là cơ chế versioning riêng được ánh xạ vào metadata version; nếu dùng seq_no/primary_term, phải truyền đúng cặp metadata tương ứng.

## 13. Mang metadata qua DTO trong ứng dụng

Một cách rõ ràng là tách document nghiệp vụ và concurrency metadata trong DTO trả về API:

```java
public record SeqNoPrimaryTerm(
        long seqNo,
        long primaryTerm) {
}

public record ProductView(
        String id,
        String name,
        int stock,
        SeqNoPrimaryTerm concurrency) {
}
```

Khi đọc SearchHit, lấy metadata của hit và đóng gói cùng dữ liệu:

```java
import org.springframework.data.elasticsearch.core.SearchHit;

ProductView toView(SearchHit<ProductDocument> hit) {
    ProductDocument product = hit.getContent();

    SeqNoPrimaryTerm token = new SeqNoPrimaryTerm(
        hit.getSeqNo(),
        hit.getPrimaryTerm()
    );

    return new ProductView(
        hit.getId(),
        product.getName(),
        product.getStock(),
        token
    );
}
```

Các accessor metadata của `SearchHit` có thể được biểu diễn trực tiếp bằng `getSeqNo()`/`getPrimaryTerm()` hoặc một accessor gom cặp trong các version Spring Data khác nhau. Dùng đúng API của version dự án; nguyên tắc là lấy từ metadata của hit, không đọc hai giá trị từ `_source`.

Nếu ứng dụng dùng GET API thay vì search, cũng cần lấy metadata từ response tương ứng. Có thể đóng gói vào một record riêng như trên để các tầng service/controller không phụ thuộc vào kiểu response Elasticsearch.

## 14. Trả concurrency token qua REST API

Ví dụ JSON trả về client:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse",
  "stock": 10,
  "concurrency": {
    "seqNo": 42,
    "primaryTerm": 3
  }
}
```

Khi client gửi lệnh cập nhật:

```json
{
  "stock": 9,
  "concurrency": {
    "seqNo": 42,
    "primaryTerm": 3
  }
}
```

Server sử dụng token này trong request cập nhật. Nếu document đã thay đổi, Elasticsearch trả conflict và server có thể chuyển thành HTTP `409 Conflict` cho client.

### Không coi token là dữ liệu được tin cậy

Client có thể gửi bất kỳ giá trị nào trong JSON. Token chỉ giúp kiểm tra concurrency; nó không thay thế xác thực, phân quyền, kiểm tra tenant hoặc validation nghiệp vụ. Server vẫn phải xác nhận người dùng có quyền sửa document ID đó và chỉ dùng token cho index/routing phù hợp.

Không nên cho client gửi raw index name, routing hoặc query tùy ý cùng concurrency token nếu API không có lý do rõ ràng. Hãy giữ các giá trị đó trong phạm vi server kiểm soát.

## 15. Sử dụng `IndexQuery` trong Spring Data Elasticsearch

Với thao tác index document qua `ElasticsearchOperations`, một số phiên bản Spring Data Elasticsearch cho phép mang sequence number và primary term trong `IndexQuery`.

Ví dụ về ý tưởng:

```java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

IndexQuery indexQuery = new IndexQueryBuilder()
    .withId(product.getId())
    .withObject(product)
    .withSeqNo(token.seqNo())
    .withPrimaryTerm(token.primaryTerm())
    .build();

operations.index(indexQuery, IndexCoordinates.of("products"));
```

`withSeqNo(...)` và `withPrimaryTerm(...)` là cách biểu diễn ở các API Spring Data có hỗ trợ hai thuộc tính này. Tên builder hoặc overload có thể khác theo version. Hãy kiểm tra Javadoc của dependency thực tế; nếu API phiên bản đang dùng không cung cấp hai setter đó, dùng Elasticsearch Java API Client để gửi `ifSeqNo` và `ifPrimaryTerm` trực tiếp.

Lưu ý `IndexQuery` thay thế source document. Nếu mục tiêu chỉ cập nhật một field, cân nhắc `UpdateQuery` hoặc Update API để tránh ghi đè những field không có trong object.

## 16. Cập nhật một phần bằng `UpdateQuery`

Một số phiên bản Spring Data Elasticsearch hỗ trợ điều kiện sequence number và primary term trên `UpdateQuery`. Mẫu sử dụng về mặt logic:

```java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

Document partialDocument = Document.create();
partialDocument.put("stock", 9);

UpdateQuery updateQuery = UpdateQuery.builder("p-100")
    .withDocument(partialDocument)
    .withIfSeqNo(token.seqNo())
    .withIfPrimaryTerm(token.primaryTerm())
    .build();

operations.update(updateQuery, IndexCoordinates.of("products"));
```

Các builder method cụ thể có thể khác giữa các version. Nếu version không có `withIfSeqNo`/`withIfPrimaryTerm`, không được bỏ điều kiện rồi coi thao tác vẫn an toàn; hãy dùng API client trực tiếp hoặc nâng cấp lên API hỗ trợ concurrency token.

Khi xử lý response update, vẫn phải bắt và phân loại version conflict. Việc truyền token không loại bỏ khả năng conflict; nó giúp phát hiện conflict đúng cách.

## 17. Dùng Elasticsearch Java API Client trực tiếp

Elasticsearch Java API Client cung cấp thuộc tính `ifSeqNo` và `ifPrimaryTerm` trên các request phù hợp.

Ví dụ Update API:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.UpdateResponse;
import co.elastic.clients.json.JsonData;

UpdateResponse<ProductDocument> response = client.update(u -> u
    .index("products")
    .id("p-100")
    .ifSeqNo(token.seqNo())
    .ifPrimaryTerm(token.primaryTerm())
    .doc(JsonData.of(Map.of("stock", 9))),
    ProductDocument.class
);
```

Tên generic, kiểu `doc(...)` và overload response phụ thuộc phiên bản Elasticsearch Java API Client. Hai điều kiện quan trọng là `.ifSeqNo(...)` và `.ifPrimaryTerm(...)`; chúng ánh xạ tới `if_seq_no` và `if_primary_term` của REST API.

Ví dụ Index API:

```java
client.index(i -> i
    .index("products")
    .id("p-100")
    .ifSeqNo(token.seqNo())
    .ifPrimaryTerm(token.primaryTerm())
    .document(updatedProduct)
);
```

Với Delete API:

```java
client.delete(d -> d
    .index("products")
    .id("p-100")
    .ifSeqNo(token.seqNo())
    .ifPrimaryTerm(token.primaryTerm())
);
```

Nếu ứng dụng đang dùng `ElasticsearchOperations` cho phần lớn truy vấn nhưng cần một request có concurrency condition chưa được abstraction hỗ trợ, có thể dùng client đã được cấu hình trong Spring context. Cần bảo đảm cùng cluster, credentials, TLS, timeout và lifecycle quản lý connection.

## 18. Bulk API và metadata cho từng action

Bulk API hỗ trợ điều kiện sequence number và primary term ở metadata của từng action.

Ví dụ:

```http
POST /_bulk
Content-Type: application/x-ndjson

{ "update": { "_index": "products", "_id": "p-100", "if_seq_no": 42, "if_primary_term": 3 } }
{ "doc": { "stock": 9 } }
{ "delete": { "_index": "products", "_id": "p-200", "if_seq_no": 17, "if_primary_term": 2 } }
```

Mỗi action có token riêng của document tương ứng. Không dùng chung một cặp sequence number/primary term cho tất cả document trong batch.

### Bulk response có thể thành công một phần

Bulk API có thể trả HTTP 200 nhưng một số item nhận 409 conflict:

```json
{
  "errors": true,
  "items": [
    {
      "update": {
        "_id": "p-100",
        "status": 200,
        "result": "updated"
      }
    },
    {
      "delete": {
        "_id": "p-200",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "..."
        }
      }
    }
  ]
}
```

Ứng dụng phải kiểm tra `errors` và từng item. Retry chỉ các item conflict sau khi đọc lại metadata và tính lại hành động. Không gửi lại toàn bộ bulk request một cách mù quáng nếu các item khác đã thành công.

## 19. Sequence number và primary term sau khi ghi

Sau một lần index/update thành công, response có thể trả metadata mới như `_seq_no`, `_primary_term` và `_version`. Nếu ứng dụng cần thực hiện tiếp một cập nhật khác dựa trên kết quả mới, hãy dùng cặp metadata mới từ response vừa nhận.

Không tiếp tục dùng token của lần đọc đầu cho nhiều lần ghi liên tiếp. Sau mỗi lần ghi thành công, document có sequence number mới. Token cũ sẽ không còn phù hợp cho thao tác kế tiếp.

Ví dụ:

```text
Đọc:       seq_no=42, primary_term=3
Cập nhật A thành công
Response:  seq_no=43, primary_term=3
Cập nhật B dựa trên trạng thái sau A
Điều kiện: if_seq_no=43, if_primary_term=3
```

Nếu thao tác ghi không trả metadata cần thiết hoặc ứng dụng không giữ response, có thể GET lại document để lấy token mới trước lần cập nhật tiếp theo.

## 20. Routing và concurrency token

Sequence number và primary term thuộc shard chứa document. Nếu index sử dụng custom routing, các request GET/search/update/index/delete phải dùng đúng routing để đến đúng shard.

Ví dụ:

```http
GET /tenant-products/_doc/p-100?routing=tenant-42
```

Sau khi lấy token từ document, request update cũng cần giữ routing tương ứng:

```http
POST /tenant-products/_update/p-100?routing=tenant-42&if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "stock": 9
  }
}
```

Nếu gửi request tới shard khác do routing sai, document có thể không được tìm thấy hoặc metadata không áp dụng cho đúng document. Token không thay thế routing.

## 21. Kết hợp concurrency control với nghiệp vụ

Optimistic concurrency control chỉ phát hiện document đã thay đổi. Nó không tự quyết định thay đổi đó có hợp lệ theo nghiệp vụ hay không.

Ví dụ chuyển trạng thái đơn hàng:

```text
Đọc order: status = PAID
           seq_no = 20
           primary_term = 2

Ứng dụng định chuyển sang CANCELLED.

Trong lúc đó, worker khác chuyển order sang SHIPPED.

Update với token cũ -> 409 conflict.

Ứng dụng đọc lại:
  status = SHIPPED

Quy tắc nghiệp vụ quyết định không cho chuyển sang CANCELLED.
```

Nếu không có concurrency token, lệnh cancel có thể ghi đè trạng thái SHIPPED. Với token, ứng dụng có cơ hội đánh giá lại trạng thái mới nhất.

### Trường hợp tăng/giảm counter

Nếu nghiệp vụ là tăng/giảm số đếm, có thể dùng update script phía Elasticsearch để thực hiện phép biến đổi nguyên tử trên document, hoặc dùng concurrency control với retry có giới hạn. Chọn cách phù hợp với tính chất phép toán và yêu cầu kiểm soát.

Không đọc số hiện tại rồi tính giá trị tuyệt đối ở client nếu có thể dùng phép cập nhật nguyên tử phù hợp. Tuy nhiên, script cũng cần điều kiện nghiệp vụ và không tự giải quyết mọi bài toán phân tán.

## 22. Giới hạn retry và backoff

Nếu nhiều writer cùng cập nhật một document nóng, retry ngay lập tức có thể tạo vòng xung đột liên tục. Nên:

- Giới hạn số lần retry.
- Dùng exponential backoff có jitter.
- Đọc lại document và token mới trước khi tính lại.
- Theo dõi tỷ lệ 409 theo index và use case.
- Xem xét chia nhỏ document hoặc giảm số writer cùng tranh chấp một document.
- Trả conflict về client nếu không thể giải quyết tự động một cách an toàn.

Ví dụ chính sách retry minh họa:

| Lần thử | Khoảng chờ cơ sở |
|---:|---:|
| 1 | 20 ms |
| 2 | 40 ms |
| 3 | 80 ms |
| 4 | Dừng và trả conflict |

Thời gian thực tế nên có jitter và được điều chỉnh theo latency hệ thống. Không retry vô hạn.

## 23. Khi nào dùng `@Version` thay cho SeqNoPrimaryTerm?

Spring Data Elasticsearch hỗ trợ `@Version` để ánh xạ version metadata của Elasticsearch vào thuộc tính entity. Đây là cơ chế optimistic locking dựa trên version.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;
    private int stock;

    // Constructors, getters and setters
}
```

`@Version` có thể phù hợp nếu ứng dụng làm việc qua entity mapping và muốn Spring Data quản lý version property. Cặp sequence number/primary term phù hợp khi ứng dụng muốn dùng concurrency token trực tiếp của Elasticsearch hoặc cần mang metadata từ search hit qua một request update khác.

Không dùng lẫn hai cơ chế trong cùng một request. Chọn một cách kiểm soát nhất quán theo API và version Spring Data. Đặc biệt, không gán `_version` vào `if_seq_no` hoặc coi `@Version` là một alias của `SeqNoPrimaryTerm`.

## 24. Không lưu concurrency token vào `_source` nếu không có lý do

Có thể nghĩ tới việc thêm field `seqNo` và `primaryTerm` vào document source để client đọc lại. Cách này thường không cần thiết và dễ gây nhầm lẫn:

- Elasticsearch tự quản lý metadata thật bên ngoài `_source`.
- Giá trị lưu trong `_source` có thể cũ ngay sau lần update tiếp theo.
- Cập nhật source field token cùng lúc với document tạo ra vòng phụ thuộc khó quản lý.
- Client có thể nhầm giá trị nghiệp vụ trong source với metadata engine.

Hãy lấy metadata từ response và mang nó qua DTO hoặc HTTP header/body theo hợp đồng API. Chỉ lưu token trong hệ thống ứng dụng nếu cần phục vụ một workflow cụ thể; không coi bản sao đó là nguồn sự thật.

## 25. Kiểm thử optimistic concurrency

Integration test nên chạy với Elasticsearch tương thích để xác nhận server thực sự kiểm tra token.

Kịch bản hai client cùng đọc:

1. Index document `p-100` với stock = 10.
2. GET document và lấy token A.
3. GET lại document và lấy token B; hai token ban đầu giống nhau.
4. Gửi update A với token A, đổi stock = 9; kỳ vọng thành công.
5. Gửi update B với token B, đổi stock = 8; kỳ vọng HTTP 409.
6. GET document; xác nhận stock vẫn là 9.
7. Đọc token mới và thực hiện retry nghiệp vụ nếu phù hợp.

Ví dụ REST flow:

```http
GET /products/_doc/p-100
```

Giả sử nhận `_seq_no = 42`, `_primary_term = 3`.

```http
POST /products/_update/p-100?if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "doc": { "stock": 9 }
}
```

Gửi lại request với đúng token cũ phải tạo conflict sau khi lần đầu thành công.

### Các trường hợp cần kiểm thử thêm

- Cập nhật bằng token hiện tại thành công.
- Cập nhật bằng token cũ bị 409.
- Xóa bằng token cũ không xóa document đã cập nhật.
- Bulk có một item conflict và các item khác thành công.
- Token từ một shard/document khác không được dùng nhầm.
- Routing đúng với index có custom routing.
- Retry đọc lại token mới và tính lại giá trị nghiệp vụ.
- Primary shard failover không khiến ứng dụng tự chế token.

## 26. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| HTTP 409 khi update | Document đã thay đổi sau lần đọc | GET mới, đánh giá và tính lại update |
| GET trả metadata nhưng search hit không có | Chưa bật `seq_no_primary_term` trong search request hoặc API không ánh xạ metadata | Bật tùy chọn và kiểm tra SearchHit accessor |
| Cập nhật luôn conflict | Ứng dụng tái sử dụng token cũ sau một lần ghi thành công | Dùng metadata mới từ response hoặc GET lại |
| Document không tìm thấy khi dùng routing | Routing sai hoặc thiếu | Dùng đúng routing của document |
| Bulk HTTP 200 nhưng có lỗi | Một số item có 409 hoặc lỗi khác | Kiểm tra `errors` và từng item status |
| Nhầm `_version` với `_seq_no` | Trộn hai cơ chế metadata | Dùng đúng cặp `if_seq_no`/`if_primary_term` |
| Retry vẫn tạo conflict | Nhiều writer đang cập nhật document nóng | Backoff, giới hạn retry hoặc thay đổi mô hình ghi |

Khi điều tra, ghi nhận index, document ID, routing, token đã gửi, HTTP status và error type. Tránh log toàn bộ `_source` nếu chứa dữ liệu nhạy cảm.

## 27. Quy trình mang metadata từ đọc đến cập nhật

Một luồng cập nhật có kiểm soát có thể đi theo các bước:

```text
GET hoặc SEARCH document
          |
          v
Đọc _seq_no và _primary_term
          |
          v
Đóng gói thành SeqNoPrimaryTerm
          |
          v
Trả DTO/token cho tầng service hoặc client
          |
          v
Nhận yêu cầu cập nhật cùng token
          |
          v
Kiểm tra quyền và validation nghiệp vụ
          |
          v
Gửi update với if_seq_no + if_primary_term
          |
      +---+---+
      |       |
      v       v
   Thành công 409 conflict
      |       |
      v       v
Lấy token mới  Đọc lại và đánh giá
      |       |
      v       v
Trả kết quả  Retry có giới hạn hoặc trả conflict
```

Các nguyên tắc quan trọng:

1. Lấy token từ metadata của đúng document và đúng shard.
2. Giữ cặp `_seq_no`/`_primary_term` cùng ID và routing cần thiết.
3. Gửi cả hai điều kiện trong request ghi.
4. Sau khi ghi thành công, dùng token mới nếu tiếp tục cập nhật.
5. Khi conflict, đọc lại và tính lại nghiệp vụ thay vì gửi lại token cũ.
6. Giới hạn retry và ghi nhận conflict metrics.

## 28. Kết luận

`_seq_no` và `_primary_term` là metadata Elasticsearch dùng để kiểm soát cập nhật đồng thời. Sequence number đánh dấu thứ tự thao tác trên shard; primary term đánh dấu thế hệ primary shard. Kết hợp hai giá trị thành concurrency token, ứng dụng có thể gửi `if_seq_no` và `if_primary_term` trong Index, Update hoặc Delete API để bảo đảm thao tác chỉ áp dụng nếu document vẫn ở trạng thái đã đọc.

Trong Spring Data Elasticsearch, hãy lấy metadata từ `SearchHit` hoặc response GET, đóng gói thành `SeqNoPrimaryTerm`/DTO và mang theo tới thao tác ghi. Các API `IndexQuery`, `UpdateQuery` và Elasticsearch Java API Client có thể cung cấp cách truyền điều kiện tùy version. Khi token đã cũ, Elasticsearch trả 409; ứng dụng cần đọc lại, kiểm tra nghiệp vụ, tính lại thay đổi và retry có giới hạn. Không nhầm cặp này với `_version` hoặc `@Version`, không lưu metadata engine vào `_source` như dữ liệu nghiệp vụ và không tái sử dụng token cũ sau một lần ghi thành công.

## Tài liệu tham khảo

- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Get API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-get)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Spring Data Elasticsearch – Object mapping and versioning](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Search operations and SearchHit](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
