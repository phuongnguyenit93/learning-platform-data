# Id ổn định, thao tác create và tính lặp an toàn

Khi nhập dữ liệu vào Elasticsearch, ứng dụng có thể gửi cùng một document nhiều lần do retry mạng, consumer nhận lại message, job chạy lại hoặc batch được phát lại sau sự cố. Nếu mỗi lần ghi tạo một document ID mới, dữ liệu trùng sẽ xuất hiện. Nếu ghi đè không đúng cách, một sự kiện cũ có thể làm mất dữ liệu mới hơn.

Ba khái niệm giúp kiểm soát vấn đề này:

- **ID ổn định (deterministic ID)**: cùng một thực thể hoặc sự kiện luôn được ánh xạ tới cùng document ID.
- **Create có điều kiện**: chỉ tạo document khi ID chưa tồn tại; nếu đã có thì Elasticsearch trả conflict.
- **Idempotency**: thực hiện lại cùng một thao tác nhiều lần vẫn tạo ra cùng trạng thái cuối cùng như thực hiện một lần.

Trong Spring Data Elasticsearch, có thể gán ID cho entity hoặc tạo `IndexQuery` với ID xác định trước. Khi cần semantics chỉ tạo mới, chọn operation `CREATE` thay vì `INDEX`. Với bulk ingestion, phải đọc kết quả từng item vì một request bulk có thể thành công một phần.

## 1. Vì sao ID ổn định quan trọng?

Giả sử một hệ thống nhận sự kiện sản phẩm:

~~~json
{
  "eventId": "evt-2026-000184",
  "productId": "P-1001",
  "status": "PUBLISHED"
}
~~~

Nếu mỗi lần xử lý ứng dụng để Elasticsearch tự sinh ID, cùng một sự kiện được gửi lại có thể tạo thêm document:

~~~text
Lần 1: _id = generated-A
Retry:  _id = generated-B
Retry:  _id = generated-C
~~~

Một sự kiện logic đã tạo ra ba document. Điều này có thể làm sai số lượng, aggregation, báo cáo và dữ liệu downstream.

Nếu dùng ID ổn định theo event:

~~~text
eventId = evt-2026-000184
       -> _id = evt-2026-000184
~~~

Mọi lần xử lý cùng event đều nhắm vào cùng một document. Ứng dụng có thể dùng create để bảo đảm chỉ có một lần tạo thành công.

ID ổn định không chỉ là tối ưu lưu trữ. Nó là một phần của thiết kế tính đúng đắn trong hệ thống phân tán, nơi timeout không cho biết chắc server đã thực hiện request hay chưa.

## 2. Chọn ID theo thực thể hay theo sự kiện

Trước khi tạo ID, cần xác định document đại diện cho điều gì.

| Mô hình document | Nguồn ID phù hợp | Ý nghĩa |
|---|---|---|
| Bản ghi hiện tại của sản phẩm | Product ID / business key | Một document đại diện trạng thái mới nhất của sản phẩm |
| Sự kiện đơn hàng | Event ID | Mỗi sự kiện logic có một document riêng |
| Trạng thái xử lý message | Message ID hoặc idempotency key | Một message chỉ được ghi nhận một lần |
| Snapshot theo ngày | Entity ID + ngày snapshot | Mỗi thực thể có một snapshot cho từng kỳ |
| Bản ghi theo tenant | Tenant ID + business key | Business key được giới hạn trong phạm vi tenant |

Ví dụ, nếu `productId` duy nhất toàn hệ thống, có thể dùng trực tiếp làm Elasticsearch document ID. Nếu chỉ duy nhất trong một tenant, cần đưa tenant vào định danh:

~~~text
tenant-42:P-1001
tenant-77:P-1001
~~~

Hai sản phẩm có cùng mã `P-1001` trong hai tenant khác nhau sẽ có ID khác nhau.

Nếu document đại diện cho event, không nên dùng `productId` làm ID vì nhiều event khác nhau của cùng sản phẩm sẽ ghi đè lẫn nhau. Hãy dùng event ID hoặc một khóa idempotency duy nhất cho event đó.

## 3. Các đặc tính của một deterministic ID tốt

Một ID ổn định nên có các đặc tính:

1. Cùng một thực thể logic luôn tạo cùng ID.
2. Hai thực thể khác nhau không vô tình dùng chung ID.
3. Có thể tạo lại ID sau khi process restart.
4. Không phụ thuộc thời gian retry hoặc số lần nhận message.
5. Không chứa dữ liệu nhạy cảm nếu ID xuất hiện trong log hoặc URL.
6. Có định dạng được chuẩn hóa thống nhất giữa producer và consumer.

Ví dụ ghép tenant và business key:

~~~java
public final class DocumentIds {

    private DocumentIds() {
    }

    public static String product(String tenantId, String productId) {
        return tenantId + ":" + productId;
    }
}
~~~

Sử dụng:

~~~java
String id = DocumentIds.product("tenant-42", "P-1001");
~~~

Nếu business key có thể chứa dấu phân cách, cần escaping hoặc encoding rõ ràng. Một lựa chọn khác là tạo hash từ chuỗi canonical:

~~~java
String canonicalKey = tenantId + "\u0000" + productId;
String id = sha256Hex(canonicalKey);
~~~

Hash giúp ID ngắn và tránh đưa trực tiếp business key vào document ID. Tuy nhiên, vẫn phải giữ quy tắc canonicalization ổn định: trim, Unicode normalization, phân biệt hoa thường và encoding phải giống nhau giữa mọi producer.

Không dùng timestamp hiện tại hoặc random UUID mới cho mỗi lần retry nếu mục tiêu là cùng một thực thể luôn có cùng ID.

## 4. ID của entity và metadata _id

Trong Spring Data Elasticsearch, annotation `@Id` ánh xạ thuộc tính Java vào metadata document ID của Elasticsearch.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters and setters
}
~~~

Ở đây:

- `id` là document ID metadata của Elasticsearch.
- `productId` là field nghiệp vụ trong `_source`.
- `tenantId` là field dùng cho filter, phân quyền hoặc truy vấn.

Hai giá trị `id` và `productId` có thể giống nhau nhưng không bắt buộc phải giống. Nếu ID được tạo từ tenant và product ID, source vẫn có thể lưu business key riêng để truy vấn.

Ví dụ:

~~~java
ProductDocument product = new ProductDocument();
product.setId(DocumentIds.product(tenantId, productId));
product.setTenantId(tenantId);
product.setProductId(productId);
product.setName("Wireless Keyboard");
~~~

Khi ID đã được tạo trước, mọi lần ghi lại cùng sản phẩm đều nhắm đến cùng document.

## 5. Phân biệt INDEX và CREATE

Elasticsearch có hai thao tác ghi thường gặp trong Index API:

| Operation | Khi ID chưa tồn tại | Khi ID đã tồn tại |
|---|---|---|
| `index` | Tạo document | Thay thế document source bằng nội dung gửi lên |
| `create` | Tạo document | Trả lỗi conflict HTTP 409 |

Ví dụ INDEX:

~~~http
PUT /products/_doc/tenant-42:P-1001
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "name": "Wireless Keyboard"
}
~~~

Gửi lại cùng request sẽ ghi vào cùng ID. Đây là hành vi upsert/replace theo ID: document được tạo nếu chưa có, hoặc source được thay thế nếu đã có.

Ví dụ CREATE:

~~~http
PUT /products/_create/tenant-42:P-1001
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "name": "Wireless Keyboard"
}
~~~

Nếu ID chưa tồn tại, document được tạo. Nếu ID đã tồn tại, Elasticsearch trả conflict và không ghi đè document hiện tại.

Dùng CREATE khi nghiệp vụ yêu cầu "chỉ tạo một lần". Dùng INDEX khi nghiệp vụ yêu cầu "đưa document về trạng thái đầy đủ mà request hiện tại mô tả".

Không coi hai operation là tương đương chỉ vì cả hai đều nhận document ID.

## 6. Vì sao CREATE hỗ trợ chống tạo trùng?

Giả sử hai worker cùng nhận một message do consumer rebalance hoặc delivery at-least-once:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant ES as Elasticsearch
    A->>ES: create _id=evt-184
    B->>ES: create _id=evt-184
    ES-->>A: 201 Created
    ES-->>B: 409 Conflict
~~~

Elasticsearch kiểm tra điều kiện tạo ở phía server. Chỉ một request có thể tạo document với ID đó; request còn lại nhận conflict.

Điều này giúp chống hai worker đồng thời tạo cùng event thành hai document, miễn là cả hai dùng cùng ID ổn định và cùng index đích.

Tuy nhiên, HTTP 409 không tự chứng minh hai payload giống nhau. Có thể hai request dùng cùng ID nhưng nội dung khác. Ứng dụng cần xác định conflict là:

- Duplicate hợp lệ: cùng event và cùng nội dung logic.
- ID collision hoặc producer bug: cùng ID nhưng payload khác.
- Xung đột nghiệp vụ: một thực thể đã được tạo bởi quy trình khác.

Không nên bắt mọi lỗi 409 rồi bỏ qua mà không kiểm tra ý nghĩa.

## 7. Tạo document với ID cố định bằng Spring Data

Có thể gán ID vào entity và dùng `IndexQuery`.

~~~java
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

ProductDocument product = new ProductDocument();
product.setId("tenant-42:P-1001");
product.setTenantId("tenant-42");
product.setProductId("P-1001");
product.setName("Wireless Keyboard");

IndexQuery indexQuery = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build();

String indexedId = operations.index(
        indexQuery,
        IndexCoordinates.of("products")
);
~~~

Ví dụ trên dùng operation mặc định của Index API theo kiểu index. Nếu document đã tồn tại, nội dung có thể được ghi đè.

Khi ID được đặt trong entity và mapping metadata nhận diện `@Id`, Spring Data cũng có thể lấy ID từ entity. Việc đặt ID rõ ràng trước khi tạo query giúp thể hiện deterministic ID trong luồng nhập liệu.

## 8. Dùng CREATE qua IndexQuery

Spring Data Elasticsearch cung cấp operation type trên `IndexQuery`. Có thể chọn `IndexQuery.OpType.CREATE` để yêu cầu Elasticsearch chỉ tạo khi ID chưa tồn tại.

~~~java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

IndexQuery createQuery = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .withOpType(IndexQuery.OpType.CREATE)
        .build();

String createdId = operations.index(
        createQuery,
        IndexCoordinates.of("products")
);
~~~

Với operation này:

- ID chưa tồn tại: document được tạo.
- ID đã tồn tại: Elasticsearch trả conflict.
- Source hiện tại không bị ghi đè bởi request create trùng ID.

Hãy xử lý conflict ở tầng ứng dụng theo nghiệp vụ. Nếu muốn kiểm tra duplicate, có thể đọc document hiện tại và so sánh event ID, payload hash hoặc metadata nguồn.

API cụ thể có thể thay đổi theo phiên bản Spring Data Elasticsearch. Đối chiếu Javadoc của dependency trong dự án nếu builder hoặc enum không khớp.

## 9. Bulk create với ID ổn định

Khi nhập nhiều document, có thể tạo danh sách `IndexQuery` rồi gửi bằng `bulkIndex(... )`.

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.BulkOptions;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> createQueries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .withOpType(IndexQuery.OpType.CREATE)
                .build())
        .toList();

var results = operations.bulkIndex(
        createQueries,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products")
);
~~~

Mỗi item có ID riêng và operation CREATE. Elasticsearch xử lý từng action trong bulk request.

Một bulk request không phải transaction. Một số item có thể thành công trong khi item khác conflict hoặc thất bại vì mapping, validation hay lỗi tạm thời.

Vì vậy, sau khi gọi bulk, phải kiểm tra kết quả từng item và không chỉ dựa vào việc phương thức trả về bình thường.

## 10. Bulk API trả kết quả theo từng item

Bulk request có thể chứa nhiều action. Ví dụ:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"create":{"_index":"products","_id":"tenant-42:P-1001"}}
{"tenantId":"tenant-42","productId":"P-1001","name":"Wireless Keyboard"}
{"create":{"_index":"products","_id":"tenant-42:P-1002"}}
{"tenantId":"tenant-42","productId":"P-1002","name":"Wireless Mouse"}
{"create":{"_index":"products","_id":"tenant-42:P-1001"}}
{"tenantId":"tenant-42","productId":"P-1001","name":"Duplicate Keyboard"}
~~~

Response có thể có dạng:

~~~json
{
  "errors": true,
  "items": [
    {
      "create": {
        "_index": "products",
        "_id": "tenant-42:P-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "create": {
        "_index": "products",
        "_id": "tenant-42:P-1002",
        "status": 201,
        "result": "created"
      }
    },
    {
      "create": {
        "_index": "products",
        "_id": "tenant-42:P-1001",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception"
        }
      }
    }
  ]
}
~~~

Bulk API vẫn xử lý các item còn lại dù một item thất bại. Trường `errors` cho biết có ít nhất một item lỗi; danh sách `items` cho biết kết quả từng action.

Với Bulk API dạng NDJSON:

- Mỗi action và document source nằm trên các dòng riêng theo loại operation.
- Không thêm dấu phẩy JSON giữa các action.
- Request phải kết thúc bằng newline.
- Không gửi một JSON array bao quanh toàn bộ action.
- Thứ tự response items tương ứng thứ tự action trong request.

## 11. Phân loại lỗi để retry đúng cách

Không nên retry toàn bộ bulk request khi chỉ một vài item thất bại.

| Kết quả | Ý nghĩa thường gặp | Cách xử lý |
|---|---|---|
| 200/201 | Item thành công | Ghi nhận hoàn tất |
| 409 với CREATE | ID đã tồn tại | Xác định duplicate hợp lệ hay conflict nghiệp vụ |
| 400 | Mapping hoặc dữ liệu không hợp lệ | Sửa dữ liệu/cấu trúc; không retry mù |
| 401/403 | Xác thực hoặc phân quyền | Sửa credential/role |
| 429 | Node đang quá tải hoặc bị từ chối tạm thời | Retry có backoff và giới hạn |
| 502/503/504 | Lỗi gateway/service tạm thời có thể xảy ra | Retry có kiểm soát sau khi đánh giá trạng thái |
| Timeout/mất kết nối | Không rõ server đã thực hiện hay chưa | Dùng ID ổn định và kiểm tra kết quả trước khi quyết định |

Khi timeout xảy ra, không thể suy ra request chưa được thực hiện. Elasticsearch có thể đã tạo document nhưng response bị mất trên đường về. Nếu gửi lại CREATE với cùng ID, lần retry có thể nhận 409. Đây chính là lúc ID ổn định và cách xử lý duplicate trở nên quan trọng.

Một retry policy tốt nên:

1. Chỉ retry item có lỗi tạm thời.
2. Dùng exponential backoff và jitter.
3. Có số lần retry tối đa.
4. Giữ nguyên ID và payload logic.
5. Đưa lỗi không retry được vào dead-letter queue hoặc báo lỗi rõ ràng.
6. Ghi nhận conflict riêng để đối soát.

Không retry liên tục ngay lập tức vì có thể làm cluster quá tải hơn.

## 12. CREATE và tính idempotent

Idempotency nghĩa là áp dụng cùng một thao tác nhiều lần có cùng hiệu ứng trạng thái như áp dụng một lần.

CREATE với ID ổn định có một đặc tính quan trọng:

- Lần đầu tạo document.
- Lần tiếp theo cùng ID bị conflict.
- Không tạo thêm document và không ghi đè source.

Xét về trạng thái dữ liệu, document vẫn chỉ có một bản. Nhưng xét về response, lần đầu trả thành công còn lần sau trả 409. Do đó, nếu API nghiệp vụ muốn trả cùng một kết quả cho mọi lần gọi, ứng dụng cần chuyển duplicate conflict thành kết quả "đã xử lý" sau khi xác minh.

Ví dụ logic:

~~~java
try {
    createDocument(event);
    return CreateResult.CREATED;
} catch (DuplicateDocumentException ex) {
    if (isSameEventAlreadyStored(event)) {
        return CreateResult.ALREADY_PROCESSED;
    }
    throw ex;
}
~~~

Đoạn code minh họa ý tưởng; cách nhận diện exception phụ thuộc client và lớp Spring Data đang dùng.

Không nên coi mọi conflict là duplicate thành công. Cùng ID nhưng khác event hoặc khác tenant có thể là lỗi dữ liệu cần điều tra.

## 13. INDEX với ID ổn định cũng có thể idempotent, nhưng semantics khác

Nếu gửi cùng payload đầy đủ nhiều lần vào cùng ID bằng INDEX, trạng thái source cuối cùng thường giống nhau:

~~~http
PUT /products/_doc/tenant-42:P-1001
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "status": "PUBLISHED"
}
~~~

Gửi lại cùng request không tạo document mới. Nhưng INDEX có thể thay thế source hiện tại. Nếu document đã được cập nhật bởi một nguồn khác, một request cũ có thể ghi đè dữ liệu mới hơn.

Ví dụ:

1. Event phiên bản 5 cập nhật status thành PUBLISHED.
2. Event phiên bản 6 cập nhật name thành Wireless Keyboard Pro.
3. Event cũ phiên bản 5 đến muộn và INDEX toàn bộ source cũ.
4. Tên mới có thể bị ghi đè trở lại.

ID ổn định ngăn tạo duplicate document, nhưng không tự giải quyết thứ tự sự kiện.

Chọn operation theo ý nghĩa dữ liệu:

- CREATE: chỉ chấp nhận lần tạo đầu tiên.
- INDEX: ghi lại toàn bộ source theo trạng thái request.
- UPDATE: sửa một phần source hoặc chạy script.
- Versioning/OCC: ngăn ghi đè dữ liệu cũ dựa trên version.

## 14. Kiểm soát thứ tự ghi bằng version

Nếu dữ liệu có thể đến không đúng thứ tự, cần một version nghiệp vụ tăng dần hoặc cơ chế optimistic concurrency control.

Ví dụ mỗi event mang version:

~~~json
{
  "productId": "P-1001",
  "version": 42,
  "name": "Wireless Keyboard Pro"
}
~~~

Elasticsearch hỗ trợ external versioning trong Index API. Với `version_type=external`, chỉ ghi khi version gửi lên lớn hơn version đang lưu:

~~~http
PUT /products/_doc/tenant-42:P-1001?version=42&version_type=external
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "version": 42,
  "name": "Wireless Keyboard Pro"
}
~~~

Nếu một event có version 41 đến sau version 42, Elasticsearch từ chối ghi version cũ.

Một biến thể là `external_gte`, chấp nhận version lớn hơn hoặc bằng version hiện tại. Chỉ dùng khi việc ghi lại cùng version là an toàn; hai payload khác nhau có cùng version có thể ghi đè lẫn nhau.

Ngoài external version, Elasticsearch hỗ trợ optimistic concurrency bằng `if_seq_no` và `if_primary_term`. Cách này phù hợp khi ứng dụng đọc document trước rồi chỉ cập nhật nếu document chưa bị thay đổi kể từ lần đọc đó.

Không dùng version tự tăng ở consumer theo thứ tự nhận message nếu message có thể đến sai thứ tự. Version phải phản ánh thứ tự nghiệp vụ do nguồn dữ liệu đáng tin cậy cấp.

## 15. CREATE không đồng nghĩa với exactly-once delivery

Message broker có thể giao message theo cơ chế at-least-once. Một message có thể được nhận lại khi consumer xử lý xong nhưng chưa commit offset, hoặc khi acknowledgment bị mất.

CREATE với ID ổn định giúp bảo đảm không tạo hai document cho cùng ID, nhưng không làm cho toàn bộ hệ thống trở thành exactly-once.

Ví dụ một consumer:

1. Nhận event.
2. Ghi document vào Elasticsearch thành công.
3. Process crash trước khi commit offset.
4. Broker giao lại event.
5. Consumer gọi CREATE lần nữa và nhận 409.

Document chỉ có một bản, nhưng consumer vẫn phải xử lý duplicate response và commit offset theo chính sách.

Nếu consumer thực hiện thêm side effect như gửi email, trừ tiền hoặc phát message khác, CREATE ở Elasticsearch không bảo đảm side effect đó chỉ chạy một lần. Cần idempotency key hoặc transactional outbox/deduplication ở đúng hệ thống sở hữu side effect.

## 16. Dùng event ID làm idempotency key

Với event ingestion, nên có ID duy nhất từ producer:

~~~json
{
  "eventId": "evt-2026-000184",
  "eventType": "PRODUCT_PUBLISHED",
  "occurredAt": "2026-11-13T10:00:00Z",
  "tenantId": "tenant-42",
  "productId": "P-1001"
}
~~~

Có thể dùng `eventId` làm document ID:

~~~java
eventDocument.setId(event.getEventId());
~~~

Nếu producer không có event ID, có thể tạo idempotency key từ các thuộc tính định danh bất biến của sự kiện. Không dùng timestamp nhận ở consumer vì mỗi lần retry có thể tạo timestamp khác nhau.

Nếu hai event hợp lệ có cùng payload nhưng là hai sự kiện độc lập, hash payload có thể khiến chúng bị gộp nhầm. ID phải phản ánh danh tính của event theo nghiệp vụ, không chỉ nội dung tình cờ giống nhau.

## 17. Bulk create với Elasticsearch Java API Client

Nếu cần kiểm soát trực tiếp từng action create, Elasticsearch Java API Client cung cấp Bulk API.

Ví dụ với typed client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkOperation;

List<BulkOperation> operations = products.stream()
        .map(product -> BulkOperation.of(op -> op
                .create(c -> c
                        .index("products")
                        .id(product.getId())
                        .document(product)
                )
        ))
        .toList();

BulkResponse response = client.bulk(b -> b
        .operations(operations)
);
~~~

Sau khi gửi, kiểm tra:

~~~java
if (response.errors()) {
    response.items().forEach(item -> {
        if (item.error() != null) {
            System.err.println(
                    item.id() + ": " + item.error().reason()
            );
        }
    });
}
~~~

Đây là API Java Client trực tiếp. Nếu dùng client trực tiếp, mapping/deserialization và exception handling do client cùng ứng dụng quản lý. Khi dùng Spring Data `ElasticsearchOperations.bulkIndex(... )`, Spring Data sử dụng mapping metadata và conversion của nó để tạo request.

Không trộn kiểu operation hoặc request builder giữa các thế hệ client cũ và Java API Client hiện tại.

## 18. Ghi nhận kết quả bulk trong ứng dụng

Một batch ingestion nên có kết quả tổng hợp rõ ràng:

~~~java
public record BulkIngestionReport(
        int submitted,
        int created,
        int duplicates,
        int retryableFailures,
        int permanentFailures
) {
}
~~~

Khi xử lý kết quả, phân loại từng item:

- Created: document mới được tạo.
- Duplicate: create trả conflict và payload/event đã được xác minh là cùng một thao tác.
- Retryable failure: lỗi tạm thời có thể retry.
- Permanent failure: dữ liệu sai, mapping lỗi hoặc quyền không đủ.
- Unknown: timeout hoặc mất kết nối, cần đối soát bằng deterministic ID.

Đối với Spring Data, kiểu kết quả bulk có thể là danh sách thông tin document đã index hoặc exception tùy operation và phiên bản. Nếu cần phân loại chi tiết lỗi từng item, hãy xác nhận API có cung cấp bulk response item metadata hay dùng Java API Client trực tiếp để lấy `BulkResponse.items()`.

Không giả định danh sách kết quả chỉ chứa các item thành công luôn cho biết đầy đủ nguyên nhân của mọi item bị bỏ qua.

## 19. Bulk request không phải transaction

Một bulk request giúp giảm overhead mạng và xử lý nhiều action trong một lần gửi. Nó không bảo đảm toàn bộ batch thành công hoặc rollback toàn bộ nếu một action lỗi.

Ví dụ:

~~~text
Item 1: CREATE thành công
Item 2: CREATE thành công
Item 3: 409 conflict
Item 4: 400 mapping error
Item 5: CREATE thành công
~~~

Sau request:

- Ba document có thể đã được tạo.
- Một item đã tồn tại.
- Một item bị lỗi dữ liệu.
- Không có rollback tự động cho các item thành công.

Ứng dụng cần lưu trạng thái từng item hoặc ít nhất danh sách lỗi để có thể retry/đối soát. Nếu batch lớn, hãy chia batch theo kích thước phù hợp và giới hạn số request đồng thời.

## 20. Thiết kế retry sau timeout

Timeout là tình huống khó vì client không biết chắc Elasticsearch đã xử lý request hay chưa.

Với CREATE và ID ổn định:

1. Gửi create.
2. Client timeout.
3. Không biết item đã được tạo hay chưa.
4. Retry cùng ID và cùng payload.
5. Nếu document chưa tồn tại, retry tạo thành công.
6. Nếu document đã tồn tại, retry nhận 409.
7. Ứng dụng xác minh document hiện tại và phân loại duplicate.

Với INDEX và ID ổn định, retry cùng payload thường đưa document về cùng source, nhưng có thể ghi đè thay đổi mới hơn. Nếu có nhiều writer, cần version hoặc OCC.

Với script tăng số lượng:

~~~painless
ctx._source.stock += params.quantity;
~~~

Retry cùng request có thể cộng thêm lần nữa. Script này không idempotent. Cần thiết kế event deduplication, lưu event ID đã áp dụng hoặc thay đổi mô hình dữ liệu để tránh xử lý lặp.

Không phải mọi thao tác đều trở nên idempotent chỉ vì document ID ổn định.

## 21. Refresh và khả năng đọc sau khi create

Một document được ghi thành công chưa chắc lập tức xuất hiện trong search query thông thường. Elasticsearch refresh làm các thay đổi được hiển thị cho search.

Bulk/index request có thể cấu hình refresh policy phù hợp, ví dụ:

- `false` hoặc mặc định: không ép refresh ngay.
- `wait_for`: chờ lần refresh tiếp theo làm dữ liệu có thể tìm kiếm.
- `true`: yêu cầu refresh ngay, có thể tăng chi phí.

Không nên đặt refresh ngay cho từng item trong ingestion throughput cao. Nếu cần kiểm tra document ngay sau create, có thể dùng GET theo ID để đọc realtime hoặc dùng refresh policy phù hợp với yêu cầu.

Phân biệt:
- Write acknowledged: thao tác ghi đã được Elasticsearch xác nhận.
- Search visible: document đã xuất hiện trong search sau refresh.
- Durable: dữ liệu đáp ứng cấu hình replication/flush và mức bảo đảm của cluster.

## 22. Quy tắc tạo ID khi có tenant, version và event

Một số mẫu thiết kế:

### Document trạng thái hiện tại

~~~text
_id = tenantId + ":" + productId
~~~

Dùng khi chỉ có một document hiện tại cho mỗi sản phẩm trong tenant.

### Event log

~~~text
_id = eventId
~~~

Dùng khi mỗi event là một document riêng và cần deduplication theo event.

### Snapshot định kỳ

~~~text
_id = tenantId + ":" + productId + ":" + snapshotDate
~~~

Dùng khi mỗi ngày hoặc mỗi kỳ có một snapshot.

### Dữ liệu theo nguồn

~~~text
_id = tenantId + ":" + sourceSystem + ":" + sourceRecordId
~~~

Dùng khi nhiều hệ thống nguồn có thể cấp cùng business key.

Hãy định nghĩa ID trong một utility hoặc contract dùng chung, không để mỗi producer tự nối chuỗi theo quy tắc khác nhau.

## 23. Những lỗi thường gặp

### Dùng UUID mới cho mỗi lần retry

Mỗi lần retry tạo ID mới sẽ sinh document trùng. Tạo ID từ business key hoặc event ID bất biến.

### Dùng product ID cho event log

Nhiều event của cùng sản phẩm ghi đè lẫn nhau. Event document cần event ID riêng.

### Dùng INDEX trong khi yêu cầu create-only

INDEX ghi đè source nếu ID đã tồn tại. Dùng CREATE khi cần từ chối document trùng.

### Bỏ qua mọi lỗi 409

409 có thể là duplicate hợp lệ, nhưng cũng có thể là ID collision hoặc xung đột dữ liệu. Xác minh payload hoặc event identity trước khi coi là thành công.

### Retry toàn bộ bulk sau lỗi một item

Một số item đã thành công. Retry toàn batch có thể gây conflict hoặc ghi đè không mong muốn. Phân loại và retry từng item cần thiết.

### Cho rằng bulk là transaction

Bulk có partial success. Phải đọc kết quả item và lưu trạng thái xử lý.

### Cho rằng deterministic ID giải quyết thứ tự event

ID ổn định ngăn duplicate document, nhưng event cũ vẫn có thể ghi đè event mới bằng INDEX. Dùng external version hoặc OCC khi cần.

### Cho rằng retry_on_conflict chống duplicate event

Retry-on-conflict giải quyết version conflict trong update, không chống việc consumer nhận lại cùng event. Cần idempotency key/deduplication.

### Không phân biệt _id và field business key

`_id` là metadata của Elasticsearch; business key trong `_source` là field dữ liệu. Có thể trùng giá trị nhưng mục đích khác nhau.

### Coi write thành công là search thấy ngay

Refresh quyết định khi nào document xuất hiện trong search. Đừng dùng sleep cố định để chờ; hãy dùng GET theo ID, refresh policy hoặc chờ điều kiện có kiểm soát.

## 24. Quy trình triển khai ingestion an toàn

Khi thiết kế pipeline nhập dữ liệu:

1. Xác định document đại diện cho entity hiện tại hay event.
2. Chọn business key hoặc event ID ổn định.
3. Chuẩn hóa và tạo deterministic ID bằng một quy tắc dùng chung.
4. Quyết định semantics CREATE hay INDEX.
5. Nếu cần chống ghi đè dữ liệu mới hơn, thêm external version hoặc OCC.
6. Tạo `IndexQuery` với ID và operation type phù hợp.
7. Gửi từng item hoặc batch bằng `ElasticsearchOperations`/Bulk API.
8. Đọc kết quả từng item, không chỉ trạng thái tổng thể.
9. Phân loại duplicate, conflict, lỗi vĩnh viễn và lỗi tạm thời.
10. Retry có backoff chỉ với item có thể retry.
11. Với timeout, retry cùng ID và payload logic rồi đối soát.
12. Đảm bảo script cộng dồn hoặc side effect khác có cơ chế deduplication.
13. Chọn refresh policy theo nhu cầu đọc sau ghi.
14. Ghi log/metric về created, duplicate, failed và retry.
15. Kiểm thử trường hợp message lặp, hai worker đồng thời, timeout sau khi server ghi và event đến sai thứ tự.

## Tài liệu tham khảo

- [Elasticsearch — Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Create operation type](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html#operation-type)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch — Refresh parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-refresh.html)
- [Spring Data Elasticsearch — IndexQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/IndexQuery.html)
- [Spring Data Elasticsearch — IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)

## Kết luận

ID ổn định giúp mọi lần xử lý cùng một thực thể hoặc event nhắm đến cùng document. CREATE bảo đảm chỉ tạo khi ID chưa tồn tại; INDEX ghi hoặc thay thế source tại ID đó. Trong Spring Data Elasticsearch, có thể gán ID qua `@Id`/entity hoặc `IndexQuery`, chọn `IndexQuery.OpType.CREATE` và gửi nhiều item bằng `bulkIndex(... )`. Bulk request có thể thành công một phần, vì vậy phải kiểm tra từng item, phân loại 409 và retry lỗi tạm thời có kiểm soát. Deterministic ID là nền tảng cho idempotency, nhưng không tự giải quyết thứ tự event, duplicate side effect hoặc update script cộng dồn; các trường hợp đó cần versioning, OCC hoặc deduplication theo nghiệp vụ.
