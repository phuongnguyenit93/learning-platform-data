# Version conflict, tài liệu không tồn tại và cập nhật thất bại

Khi làm việc với Elasticsearch, một thao tác đọc hoặc cập nhật có thể không thành công vì document đã bị thay đổi, document không tồn tại, index chưa được tạo hoặc request không đáp ứng điều kiện ghi. Những tình huống này có thể cùng xuất hiện dưới dạng lỗi 404, 409 hoặc một item lỗi trong bulk response, nhưng nguyên nhân và cách phục hồi hoàn toàn khác nhau.

Spring Data Elasticsearch cung cấp các abstraction như **ElasticsearchOperations** và **ReactiveElasticsearchOperations**. Các abstraction này giúp ứng dụng thao tác với entity, nhưng không loại bỏ các quy tắc concurrency và kết quả của Elasticsearch server. Ứng dụng vẫn cần hiểu document version, optimistic concurrency control, update/upsert, partial bulk failure và cách phân loại exception.

Bài này trình bày cách nhận diện version conflict, phân biệt document missing với index missing, chọn hành vi khi update một document không tồn tại, chẩn đoán các nguyên nhân update thất bại và thiết kế recovery không làm mất dữ liệu mới.

## 1. Phân biệt các kết quả khi thao tác document

### 1.1. Một số trạng thái thường gặp

| Tình huống | Kết quả thường gặp | Ý nghĩa |
|---|---|---|
| Document tồn tại và đọc được | 200 hoặc có kết quả | Document được tìm thấy |
| Document không tồn tại khi GET trực tiếp | 404 | Không có document với ID đó |
| Search không tìm thấy document | 200, hits.total bằng 0 | Query hợp lệ nhưng không có hit |
| Index hoặc alias không tồn tại | 404, index_not_found_exception | Resource đích không tồn tại |
| Update document không tồn tại | 404, document_missing_exception | Update API không có document để sửa |
| Ghi với điều kiện version cũ | 409, version conflict | Document đã thay đổi kể từ lúc đọc |
| Create document với ID đã tồn tại | 409, version conflict | ID đã được sử dụng |
| Request sai mapping hoặc dữ liệu | Thường 400 | Payload không phù hợp với mapping/API |
| Không đủ quyền | 401 hoặc 403 | Authentication hoặc authorization thất bại |
| Cluster từ chối vì quá tải | Có thể 429 | Request cần được điều tiết và xử lý theo retry policy |

Không nên chỉ nhìn status code. Hãy đọc error type, index, document ID, operation type và response body để xác định đúng nguyên nhân.

### 1.2. GET 404 khác với search không có hit

GET theo ID hỏi Elasticsearch có document cụ thể hay không:

~~~http
GET /products/_doc/P1001
~~~

Nếu ID không tồn tại, endpoint có thể trả HTTP 404 với found false.

Search query không có kết quả thường trả HTTP 200 cùng danh sách hits rỗng:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "sku": "UNKNOWN-SKU"
    }
  }
}
~~~

Hai kết quả này không tương đương với lỗi hạ tầng. Một document không được tìm thấy có thể là trạng thái nghiệp vụ bình thường.

### 1.3. Document missing khác index missing

Ví dụ:

- **document_missing_exception**: index có tồn tại nhưng document ID cần update không có.
- **index_not_found_exception**: index hoặc resource được request tham chiếu không tồn tại.

Cách xử lý cũng khác nhau:

- Document missing: kiểm tra ID, thứ tự xử lý, retention hoặc chính sách tạo mới.
- Index missing: kiểm tra provisioning, alias, template, môi trường và thứ tự deploy.

Không tự tạo index mới khi gặp mọi lỗi 404. Làm vậy có thể tạo index sai mapping hoặc che giấu lỗi cấu hình.

### 1.4. Không phải mọi delete missing đều là lỗi

Delete API có thể trả kết quả not_found khi document đã không còn. Trong nhiều use case, delete theo ID được xem là thao tác idempotent: mục tiêu cuối cùng là document không tồn tại.

Điều này khác với update missing. Update thường cần document hiện hữu, trừ khi request được cấu hình rõ ràng để upsert.

Ứng dụng nên định nghĩa rõ việc xóa một ID chưa tồn tại là thành công, cảnh báo hay lỗi nghiệp vụ.

## 2. Version conflict là gì?

### 2.1. Hai client cùng sửa một document

Giả sử document sản phẩm đang có giá 100:

1. Client A đọc document.
2. Client B đọc cùng document.
3. Client A thay giá thành 110 và lưu.
4. Client B thay tên sản phẩm trên bản dữ liệu cũ rồi lưu toàn bộ document.

Nếu không có concurrency control, thao tác của B có thể ghi đè giá 110 bằng giá cũ 100. Đây là lost update.

Version conflict là cơ chế phát hiện rằng dữ liệu đã thay đổi kể từ lúc client đọc hoặc kể từ khi client lấy version token.

### 2.2. Optimistic concurrency control

Optimistic concurrency control (OCC) giả định xung đột không xảy ra thường xuyên. Client đọc trạng thái, xử lý dữ liệu rồi chỉ ghi nếu document vẫn ở phiên bản mà client đã đọc.

Nếu document đã thay đổi, server từ chối thao tác để client quyết định cách giải quyết.

OCC phù hợp khi:

- Nhiều request có thể cập nhật cùng một document.
- Không muốn giữ lock trong suốt thời gian xử lý.
- Mỗi update cần dựa trên trạng thái mới nhất.
- Mất update là không thể chấp nhận.

### 2.3. Elasticsearch sequence number và primary term

Elasticsearch cung cấp hai giá trị dùng cho optimistic concurrency control:

- **_seq_no**: sequence number của thao tác đã thay đổi document.
- **_primary_term**: term của primary shard xử lý thao tác đó.

Khi đọc document, response có thể chứa hai giá trị này. Client gửi lại chúng khi update/index/delete để yêu cầu thao tác chỉ thành công nếu document vẫn ở đúng trạng thái đã đọc.

Ví dụ:

~~~http
GET /products/_doc/P1001
~~~

Response có thể chứa:

~~~json
{
  "_index": "products",
  "_id": "P1001",
  "_seq_no": 12,
  "_primary_term": 3,
  "_source": {
    "name": "Keyboard",
    "price": 100
  }
}
~~~

Nếu client dùng hai token trên để cập nhật, Elasticsearch kiểm tra chúng với trạng thái hiện tại. Nếu document đã thay đổi, request bị từ chối với version conflict thay vì âm thầm ghi đè dữ liệu mới.

### 2.4. Gửi điều kiện if_seq_no và if_primary_term

Ví dụ update chỉ khi document chưa thay đổi:

~~~http
POST /products/_update/P1001?if_seq_no=12&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "price": 110
  }
}
~~~

Nếu một client khác đã cập nhật document sau lần đọc, cặp token cũ không còn hợp lệ và Elasticsearch trả 409.

Có thể dùng cùng điều kiện concurrency cho index hoặc delete API khi cần bảo vệ thao tác dựa trên snapshot đã đọc.

### 2.5. Không nhầm _version với _seq_no/_primary_term

Elasticsearch cũng có trường **_version** cho document. Đây là một cơ chế version khác với cặp sequence number/primary term dùng cho OCC.

Trong tài liệu hoặc log, hãy ghi rõ đang nói tới:

- Internal document version (**_version**).
- Sequence number (**_seq_no**).
- Primary term (**_primary_term**).
- Version property được Spring Data ánh xạ qua **@Version**.

Không tự thay thế một loại token bằng loại khác. Dùng đúng request parameter/API mà client và phiên bản Spring Data hỗ trợ.

## 3. Sử dụng @Version trong Spring Data Elasticsearch

### 3.1. Đánh dấu version property

Spring Data Elasticsearch hỗ trợ annotation **@Version** để theo dõi version của entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Version
    private Long version;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructors, getters and setters.
}
~~~

Khi Spring Data đọc và lưu entity có version, version property tham gia vào cơ chế phát hiện cập nhật cạnh tranh theo contract của phiên bản Spring Data Elasticsearch đang dùng.

### 3.2. Luồng save có version

Một luồng điển hình:

1. Đọc entity từ Elasticsearch.
2. Spring Data ánh xạ version vào property.
3. Ứng dụng thay đổi entity.
4. Gọi save.
5. Spring Data dùng thông tin version để kiểm tra cập nhật.
6. Nếu version không còn hợp lệ, thao tác thất bại với lỗi optimistic locking.

Ví dụ:

~~~java
ProductDocument product =
    repository.findById("P1001").orElseThrow();

product.setPrice(110.0);

ProductDocument saved = repository.save(product);
~~~

Nếu một transaction/request khác đã lưu phiên bản mới sau lần đọc, save có thể ném **OptimisticLockingFailureException** (hoặc exception được dịch tương ứng trong phiên bản đang dùng).

### 3.3. Bắt optimistic locking exception

Có thể xử lý ở tầng service:

~~~java
try {
    return repository.save(product);
} catch (OptimisticLockingFailureException conflict) {
    throw new ProductUpdateConflictException(
        product.getId(),
        conflict
    );
}
~~~

Trong API web, ứng dụng có thể chuyển conflict thành HTTP 409 để caller biết dữ liệu đã thay đổi và cần tải lại hoặc giải quyết xung đột.

Không biến conflict thành HTTP 500 chung chung nếu đó là tình huống concurrency đã được dự kiến trong thiết kế.

### 3.4. Version property cần được quản lý nhất quán

Không tự ý đặt version property về giá trị cũ hoặc xóa nó khỏi entity trước khi save. Làm như vậy có thể phá cơ chế phát hiện stale update.

Khi tạo document mới, để Spring Data khởi tạo version theo contract của mapping. Khi đọc document, giữ version được trả về. Khi dùng DTO, bảo đảm thông tin version cần thiết được truyền qua use case update nếu ứng dụng dựa vào nó.

### 3.5. Không đồng nhất @Version với mọi API OCC

**@Version** là abstraction ở tầng Spring Data. Nếu ứng dụng gọi Elasticsearch Java API Client trực tiếp, nó có thể sử dụng **if_seq_no** và **if_primary_term** rõ ràng.

Không giả định mọi version Spring Data ánh xạ annotation @Version theo cùng một cơ chế nội bộ với raw OCC token. Kiểm tra tài liệu của release train và API được dùng trước khi trộn hai mô hình trong cùng một entity.

## 4. Cập nhật toàn bộ document và cập nhật một phần

### 4.1. save thường ghi representation của entity

Repository **save(entity)** phù hợp khi ứng dụng muốn lưu entity đã được ánh xạ. Nếu entity có ID đã tồn tại, thao tác index thường thay thế source của document theo semantics index operation.

Ví dụ entity chỉ chứa:

~~~json
{
  "id": "P1001",
  "name": "Keyboard"
}
~~~

Nếu document trên Elasticsearch trước đó còn price, category và tags, việc ghi toàn bộ entity mới có thể làm các field không còn trong source bị mất.

Vì vậy, không dùng save như thể nó luôn là partial update.

### 4.2. Update API cho partial document

Update API cho phép gửi một phần field:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "doc": {
    "price": 110
  }
}
~~~

Chỉ field được gửi trong doc được cập nhật theo merge semantics của update API. Các field khác trong _source được giữ lại.

Partial update phù hợp khi service chỉ sở hữu một số field và không muốn ghi đè toàn bộ document.

### 4.3. Update không tự tạo document missing

Mặc định, update API yêu cầu document tồn tại. Nếu document không có, Elasticsearch trả **document_missing_exception**.

Đây là hành vi có chủ đích: ứng dụng không vô tình tạo mới document chỉ vì một lệnh update nhắm tới ID sai.

Nếu muốn tạo mới khi chưa tồn tại, phải cấu hình upsert rõ ràng.

### 4.4. Không dùng save để che giấu lỗi update

Một pattern nguy hiểm là khi update trả 404, ứng dụng lập tức gọi save với một entity chỉ có một vài field. Điều đó có thể tạo document thiếu dữ liệu hoặc ghi đè document được tạo đồng thời bởi service khác.

Trước khi fallback sang create, cần xác định:

- Document missing có phải trạng thái hợp lệ không?
- Nguồn dữ liệu nào sở hữu document?
- Có đủ dữ liệu để tạo document hoàn chỉnh không?
- Một writer khác có thể vừa tạo document hay không?
- Có cần điều kiện create-only hoặc idempotency key không?

## 5. Upsert khi document không tồn tại

### 5.1. Upsert là gì?

Upsert kết hợp update và insert:

- Nếu document tồn tại, áp dụng phần update.
- Nếu document không tồn tại, tạo document từ payload upsert.

Upsert hữu ích cho counter, trạng thái tổng hợp hoặc dữ liệu mà thao tác tạo mới và cập nhật có thể được mô tả trong cùng một request.

Không bật upsert mặc định cho mọi update. Nếu document missing biểu thị lỗi logic hoặc ID sai, upsert có thể che giấu lỗi đó.

### 5.2. Dùng trường upsert

Ví dụ:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "doc": {
    "price": 110
  },
  "upsert": {
    "name": "Keyboard",
    "sku": "SKU-1001",
    "price": 110,
    "active": true
  }
}
~~~

Nếu P1001 tồn tại, phần doc được áp dụng. Nếu chưa tồn tại, Elasticsearch tạo document từ upsert.

Payload upsert phải đủ các field bắt buộc để document mới hợp lệ.

### 5.3. Dùng doc_as_upsert

Nếu payload doc cũng chính là document cần tạo khi missing, có thể dùng:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "doc": {
    "name": "Keyboard",
    "price": 110
  },
  "doc_as_upsert": true
}
~~~

Khi document chưa tồn tại, nội dung doc được dùng làm source ban đầu.

### 5.4. Scripted upsert

Nếu update dùng script và script cũng cần chạy khi document chưa tồn tại, cần xem xét **scripted_upsert** cùng payload **upsert**.

Ví dụ khái niệm:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "scripted_upsert": true,
  "script": {
    "source": "ctx._source.count = (ctx._source.count ?: 0) + params.amount",
    "params": {
      "amount": 1
    }
  },
  "upsert": {
    "count": 0
  }
}
~~~

Scripted upsert có thể áp dụng script cho cả trường hợp document chưa tồn tại. Cần kiểm tra semantics chính xác của request và script trong phiên bản Elasticsearch.

### 5.5. Upsert không giải quyết mọi race condition

Hai client có thể cùng gửi upsert cho một ID. Elasticsearch xử lý request theo semantics update và concurrency của shard, nhưng nghiệp vụ vẫn cần xác định cách hợp nhất dữ liệu.

Nếu upsert là phép tăng counter, script cần chạy trên trạng thái mới nhất và không gửi side effect ra ngoài. Nếu hai client cung cấp hai giá trị khác nhau cho cùng field, cần quy tắc ưu tiên hoặc version từ nguồn dữ liệu.

## 6. retry_on_conflict và optimistic concurrency

### 6.1. retry_on_conflict dành cho Update API

Update API hỗ trợ **retry_on_conflict** để Elasticsearch thử lại một update khi xảy ra version conflict trong quá trình update nội bộ.

Ví dụ:

~~~http
POST /products/_update/P1001?retry_on_conflict=3
Content-Type: application/json

{
  "doc": {
    "lastViewedAt": "2026-11-13T10:00:00Z"
  }
}
~~~

Giá trị 3 cho phép một số lần retry nội bộ theo semantics API. Nó không phải retry cho mọi loại lỗi như mapping error, authorization hoặc index missing.

### 6.2. Khi nào retry_on_conflict phù hợp?

Có thể phù hợp khi:

- Update là thao tác nguyên tử ở server.
- Payload/script có thể áp dụng lại trên source mới.
- Xung đột ngắn hạn do nhiều update đồng thời.
- Ứng dụng không cần tự đọc lại toàn bộ entity để tính lại thay đổi.

Với script increment, Elasticsearch có thể chạy lại script trên source mới nhất. Điều này khác với client gửi lại một bản document stale đã được tính từ lần đọc cũ.

### 6.3. Script phải an toàn khi được thực thi lại

Không đặt side effect bên ngoài Elasticsearch trong update script. Script có thể được thực thi lại khi retry conflict.

Script nên chỉ thay đổi _source theo một phép biến đổi xác định trên trạng thái hiện tại. Tránh logic phụ thuộc thời gian hoặc random nếu không có chủ đích.

### 6.4. retry_on_conflict không thay thế if_seq_no/if_primary_term

Hai cách giải quyết conflict có mục tiêu khác nhau:

- **retry_on_conflict**: server thử lại update operation trên trạng thái mới hơn.
- **if_seq_no** và **if_primary_term**: client yêu cầu chỉ ghi nếu document vẫn đúng snapshot đã đọc.

Nếu nghiệp vụ yêu cầu caller phải biết dữ liệu đã đổi và quyết định lại, OCC token phù hợp hơn. Nếu một phép update nguyên tử có thể áp dụng lại an toàn, retry_on_conflict có thể phù hợp.

## 7. Chiến lược giải quyết version conflict

### 7.1. Fail fast và yêu cầu caller tải lại

Với dữ liệu do người dùng chỉnh sửa, cách đơn giản và an toàn là trả HTTP 409:

1. Client gửi update cùng version đã đọc.
2. Server phát hiện version conflict.
3. API trả conflict.
4. Client tải dữ liệu mới.
5. Người dùng hoặc logic ứng dụng hợp nhất thay đổi.
6. Gửi update mới dựa trên version mới.

Cách này tránh âm thầm ghi đè thay đổi của người khác.

### 7.2. Read-modify-write có giới hạn

Một service có thể tự giải quyết conflict bằng cách đọc lại document, tính lại thay đổi rồi thử ghi lại:

~~~text
read current document and version
calculate desired state
attempt conditional write

if version conflict:
    reload current document
    recalculate change
    retry within a small bounded budget

if budget exhausted:
    return conflict or send to reconciliation
~~~

Điểm quan trọng là phải tính lại thay đổi từ dữ liệu mới. Không gửi lại nguyên payload đã tạo từ document stale.

### 7.3. Merge theo field ownership

Nếu hai service sở hữu các field khác nhau, partial update có thể giảm xung đột và giảm nguy cơ ghi đè.

Ví dụ:

- Catalog service sở hữu name, description, category.
- Pricing service sở hữu price, currency.
- Inventory service sở hữu availableQuantity.

Mỗi service chỉ update các field thuộc quyền sở hữu của nó. Nếu cùng update một field, cần quy tắc nghiệp vụ rõ ràng.

### 7.4. Last-write-wins

Last-write-wins phù hợp khi nghiệp vụ chấp nhận giá trị đến sau ghi đè giá trị trước, ví dụ một số cache hoặc projection có thể tái tạo.

Không dùng timestamp từ client không đáng tin cậy để quyết định thứ tự. Nếu cần ordering, dùng version từ nguồn dữ liệu hoặc timestamp được kiểm soát.

### 7.5. External versioning

Nếu hệ thống nguồn có version tăng đơn điệu, Elasticsearch hỗ trợ external versioning để chỉ nhận document khi version nguồn thỏa điều kiện.

Ví dụ khái niệm:

~~~http
PUT /products/_doc/P1001?version=42&version_type=external
Content-Type: application/json

{
  "name": "Keyboard",
  "price": 110
}
~~~

Với **external**, request chỉ được chấp nhận khi version mới lớn hơn version đang lưu. **external_gte** có semantics cho phép version bằng nhau; cần cân nhắc kỹ vì duplicate event cùng version có thể ghi đè.

External versioning hữu ích cho event ingestion hoặc đồng bộ từ database có version riêng. Không dùng version tùy ý không có thứ tự nhất quán.

## 8. Tài liệu không tồn tại: thiết kế hành vi nghiệp vụ

### 8.1. Missing có thể là trạng thái bình thường

Một ID không tồn tại có thể có nhiều ý nghĩa:

- User yêu cầu xem sản phẩm đã bị xóa.
- Event update đến trước event create.
- Document hết hạn theo retention.
- Consumer nhận message trễ.
- ID sai hoặc dữ liệu nguồn không nhất quán.
- Index chưa được provision.

Ứng dụng cần phân biệt những trường hợp này thay vì xử lý mọi missing theo cùng một cách.

### 8.2. Phân biệt not found với lỗi hệ thống

Ở tầng service, có thể chuyển kết quả repository thành domain result:

~~~java
public ProductDocument getProduct(String id) {
    return repository.findById(id)
        .orElseThrow(() -> new ProductNotFoundException(id));
}
~~~

Không chuyển mọi exception thành ProductNotFoundException. Connection failure, timeout và authorization error không phải document missing.

### 8.3. Xử lý update đến trước create

Trong event-driven ingestion, event update có thể tới trước event create do ordering hoặc retry ở broker.

Một số lựa chọn:

- Giữ event trong retry queue chờ create.
- Lưu event vào pending store.
- Dùng upsert nếu payload đủ để tạo trạng thái hợp lệ.
- Đọc nguồn dữ liệu chuẩn để tái tạo document.
- Bỏ qua event cũ nếu có version ordering rõ ràng.

Không tự tạo document thiếu field chỉ để tránh lỗi 404.

### 8.4. Delete và tombstone

Nếu document bị xóa nhưng event cũ đến muộn, hệ thống có thể vô tình tạo lại document nếu update được cấu hình upsert.

Với dữ liệu đồng bộ từ event stream, có thể cần tombstone hoặc version của sự kiện xóa để ngăn event cũ khôi phục dữ liệu đã xóa.

### 8.5. Missing index phải được xử lý ở provisioning

Nếu index chưa tồn tại, kiểm tra:

- Deployment có chạy migration/provisioning chưa?
- Alias có được tạo đúng không?
- Tên index theo environment có đúng không?
- Template có áp dụng cho index mới không?
- Runtime principal có đủ quyền gọi API cần thiết không?

Không cấp quyền manage cho mọi runtime service chỉ để chúng tự tạo index khi gặp 404.

## 9. Update thất bại do mapping và dữ liệu

### 9.1. Mapping conflict

Nếu field được mapping là long nhưng ứng dụng gửi chuỗi không chuyển đổi được, update có thể thất bại với mapper_parsing_exception.

Ví dụ mapping:

~~~json
{
  "properties": {
    "price": {
      "type": "double"
    }
  }
}
~~~

Payload sai:

~~~json
{
  "doc": {
    "price": "free"
  }
}
~~~

Đây là lỗi dữ liệu/mapping, không phải version conflict. Retry cùng payload sẽ tiếp tục thất bại.

### 9.2. Field type đã được xác định không thể tùy ý đổi

Elasticsearch không cho phép thay đổi một field từ text sang date trực tiếp trên cùng mapping như một phép update thông thường.

Nếu schema thay đổi không tương thích, thường cần tạo index mới với mapping đúng, reindex dữ liệu và chuyển alias theo quy trình migration.

Không xử lý mapping error bằng cách thêm retry hoặc tạo lại index đang chứa dữ liệu production.

### 9.3. Script error

Update script có thể thất bại vì:

- Field không tồn tại theo giả định của script.
- Kiểu dữ liệu không đúng.
- Truy cập null.
- Script syntax sai.
- Script vượt giới hạn hoặc policy.
- Runtime parameter không hợp lệ.

Kiểm tra script và payload đầu vào. Có thể thêm guard trong script để xử lý field thiếu, nhưng phải bảo đảm logic nghiệp vụ vẫn đúng.

### 9.4. Index read-only hoặc cluster block

Update có thể bị từ chối vì index bị block read-only, chẳng hạn khi cluster áp dụng flood-stage disk watermark.

Đây là vấn đề trạng thái cluster/storage. Retry liên tục không giải quyết được cho tới khi nguyên nhân được xử lý và block được gỡ theo quy trình vận hành.

Kiểm tra cluster health, disk usage, index settings và block reason trước khi thay đổi settings.

## 10. Update thất bại do security hoặc hạ tầng

### 10.1. Authentication và authorization

- 401: credential sai, hết hạn, bị revoke hoặc header không đúng.
- 403: principal đã xác thực nhưng thiếu privilege hoặc bị policy chặn.

Không retry vô hạn 401/403. Kiểm tra API key, role, index pattern và TLS.

### 10.2. Rejection và overload

429 hoặc es_rejected_execution_exception có thể cho biết cluster đang quá tải.

Hướng xử lý:

- Backoff có jitter.
- Giảm concurrency.
- Giảm bulk size nếu phù hợp.
- Retry có giới hạn.
- Theo dõi write thread pool và node resource.
- Dùng bounded queue và backpressure.

Không tăng retry rate khi cluster đã từ chối request.

### 10.3. Timeout và kết quả không xác định

Nếu client timeout, server có thể đã xử lý update nhưng response chưa về. Không giả định request chưa được thực hiện.

Với write operation:

- Dùng ID ổn định.
- Dùng OCC/version hoặc operation ID.
- Đọc lại trạng thái nếu cần xác minh.
- Retry chỉ khi thao tác an toàn khi lặp.
- Không tạo ID mới ở mỗi attempt.

### 10.4. Connection reset hoặc node failure

Một số lỗi transport có thể xảy ra trong lúc request đang được xử lý. Hãy phân loại theo exception và tính idempotent, không chỉ dựa vào việc connection bị đóng.

Nếu update dùng script tăng counter, retry sau connection reset có thể tăng hai lần nếu request đầu đã thành công. Cần thiết kế deduplication hoặc operation semantics phù hợp.

## 11. Phân tích Bulk API khi có update failure

### 11.1. HTTP 200 không có nghĩa tất cả item thành công

Bulk API xử lý nhiều operation trong một request. Elasticsearch có thể trả HTTP 200 nhưng trường errors là true vì một hoặc nhiều item thất bại.

Ví dụ:

~~~json
{
  "errors": true,
  "items": [
    {
      "update": {
        "_id": "P1001",
        "status": 200,
        "result": "updated"
      }
    },
    {
      "update": {
        "_id": "P1002",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "version conflict"
        }
      }
    },
    {
      "update": {
        "_id": "P1003",
        "status": 404,
        "error": {
          "type": "document_missing_exception",
          "reason": "document missing"
        }
      }
    }
  ]
}
~~~

Trong ví dụ:

- P1001 đã cập nhật.
- P1002 gặp version conflict.
- P1003 không tồn tại.

Ứng dụng phải đọc từng item response để quyết định recovery.

### 11.2. Retry riêng item lỗi

Không gửi lại cả bulk nếu một số item đã thành công. Tạo retry batch chỉ gồm item có thể phục hồi:

- Version conflict: đọc lại/tính lại hoặc dùng retry policy thích hợp.
- Document missing: upsert, chờ create hoặc dead-letter tùy nghiệp vụ.
- Mapping error: không retry mù.
- 429: backoff và giảm tải.
- 401/403: xử lý credential/role.

### 11.3. Bulk update có retry_on_conflict

Update action trong bulk có thể khai báo retry_on_conflict trong metadata của từng item, nếu API/version hỗ trợ.

Ví dụ NDJSON:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"P1001","retry_on_conflict":3}}
{"doc":{"price":110}}
~~~

Cấu hình này chỉ xử lý conflict theo semantics update action. Nó không tự xử lý document missing, mapping error hoặc security failure.

### 11.4. Giữ mapping giữa request và response item

Bulk response item được trả theo thứ tự operation tương ứng trong request. Khi ứng dụng lọc item lỗi, hãy giữ ID, operation type và payload gốc để có thể xác định chính xác thao tác cần retry hoặc dead-letter.

Không chỉ lưu vị trí mảng nếu batch có thể được chia, gộp hoặc reorder ở các tầng khác.

## 12. Sử dụng Elasticsearch Java API Client cho OCC

### 12.1. Đọc document và lấy concurrency token

Java API Client có thể trả metadata của response bao gồm sequence number và primary term tùy API được gọi.

Mẫu khái niệm:

~~~java
GetResponse<ProductDocument> response =
    client.get(
        request -> request
            .index("products")
            .id("P1001"),
        ProductDocument.class
    );

if (!response.found()) {
    throw new ProductNotFoundException("P1001");
}

long seqNo = response.seqNo();
long primaryTerm = response.primaryTerm();
ProductDocument current = response.source();
~~~

Tên accessor và kiểu response cần khớp với phiên bản Elasticsearch Java API Client trong dự án.

### 12.2. Conditional update

Ví dụ gửi update với hai token vừa đọc:

~~~java
UpdateResponse<ProductDocument> response =
    client.update(
        request -> request
            .index("products")
            .id("P1001")
            .ifSeqNo(seqNo)
            .ifPrimaryTerm(primaryTerm)
            .doc(Map.of("price", 110.0)),
        ProductDocument.class
    );
~~~

Nếu token đã stale, server trả version conflict. Client có thể đọc lại và đưa ra quyết định nghiệp vụ.

Đây là cách dùng low-level Java API Client. Nếu cùng ứng dụng dùng Spring Data repository, hãy thống nhất tầng nào chịu trách nhiệm concurrency để tránh hai cơ chế version không đồng bộ.

### 12.3. Đọc lại và tính lại thay đổi

Mẫu xử lý:

~~~java
public ProductDocument updatePrice(
        String id,
        double requestedPrice) {

    for (int attempt = 1; attempt <= 3; attempt++) {
        ProductSnapshot current = loadWithConcurrencyToken(id);

        ProductDocument updated =
            applyPriceChange(current.document(), requestedPrice);

        try {
            return conditionalUpdate(
                id,
                updated,
                current.seqNo(),
                current.primaryTerm()
            );
        } catch (VersionConflictException conflict) {
            if (attempt == 3) {
                throw new ProductUpdateConflictException(id, conflict);
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

Đoạn code là pseudo-code để mô tả read-modify-write. Trong ứng dụng thực, phải xác định cách applyPriceChange giải quyết thay đổi đồng thời và cách phân loại exception từ client.

Không dùng vòng lặp vô hạn. Mỗi conflict retry cần giới hạn, có thể thêm backoff nhỏ nếu contention cao.

## 13. Xử lý lỗi trong Spring Data Elasticsearch

### 13.1. Exception translation

Spring Data có thể dịch lỗi từ client thành exception thuộc hệ sinh thái Spring Data/DAO. Tên và hierarchy cụ thể phụ thuộc phiên bản và đường API.

Các nhóm cần nhận diện:

- OptimisticLockingFailureException: conflict khi cập nhật theo version.
- DataAccessResourceFailureException hoặc exception transport tương ứng: kết nối/hạ tầng.
- DataIntegrityViolationException hoặc mapping-related exception: dữ liệu không hợp lệ theo contract.
- NoSuchIndexException hoặc exception tương ứng: index/resource missing nếu được abstraction dịch.
- Exception từ Elasticsearch Java API Client: có thể cần đọc status và error type từ response.

Không bắt Exception rồi coi mọi lỗi là retryable.

### 13.2. Repository findById

Với imperative repository:

~~~java
Optional<ProductDocument> product =
    repository.findById(id);
~~~

Không tìm thấy document thường được biểu diễn bằng Optional.empty().

Với reactive repository:

~~~java
Mono<ProductDocument> product =
    reactiveRepository.findById(id);
~~~

Không tìm thấy document thường được biểu diễn bằng Mono.empty().

Đây là trạng thái không có kết quả, không phải error signal. Nếu nghiệp vụ yêu cầu bắt buộc có document, chuyển empty thành domain exception ở service.

### 13.3. ElasticsearchOperations get/find

Các method get, search hoặc multiGet có contract khác nhau. Một số API có thể trả null, empty collection hoặc kết quả có missing entry tùy operation.

Đọc Javadoc của đúng phiên bản trước khi giả định cách biểu diễn missing. Không biến null thành lỗi hạ tầng.

### 13.4. UpdateQuery và UpdateResponse

Spring Data Elasticsearch cung cấp abstraction update để gửi partial update. Cách tạo UpdateQuery, Document và đọc UpdateResponse phụ thuộc version.

Khi dùng abstraction này, cần xác định:

- Update có được cấu hình upsert không?
- Response có expose result updated, created, noop hay không?
- Có expose status/error chi tiết đủ cho recovery không?
- OCC/version token được truyền bằng API nào?
- Exception có được Spring dịch hay vẫn là client exception?

Nếu cần metadata item-level hoặc OCC parameter chưa được abstraction expose, có thể dùng Elasticsearch Java API Client ở một component được cô lập.

### 13.5. Không để abstraction che mất thông tin lỗi

Một tầng repository/service nên chuyển lỗi kỹ thuật thành kết quả domain có ý nghĩa, nhưng cần giữ cause và metadata quan trọng như status, error type, index, document ID và operation.

Thông tin này giúp logging, retry policy và observability phân biệt conflict với missing hoặc mapping error.

## 14. Thiết kế retry an toàn cho update

### 14.1. Retry cùng payload stale thường không có ích

Nếu OCC từ chối vì document đã thay đổi, gửi lại cùng payload với cùng version token sẽ tiếp tục conflict.

Cần đọc lại trạng thái và tính lại update, hoặc trả conflict để caller quyết định.

### 14.2. Giới hạn retry

Contention kéo dài có thể khiến nhiều client liên tục đọc và ghi lại cùng document. Retry vô hạn làm tăng tải và kéo dài request.

Đặt:

- Số lần retry tối đa.
- Backoff và jitter khi nhiều writer tranh chấp.
- Deadline tổng thể.
- Metric conflict rate.
- Cơ chế trả 409 hoặc đưa operation vào queue khi hết budget.

### 14.3. Retry không được che giấu business conflict

Có những xung đột không thể tự giải quyết:

- Hai người cùng sửa địa chỉ giao hàng.
- Hai giao dịch cùng thay đổi trạng thái đơn hàng theo hai hướng không tương thích.
- Hai nguồn dữ liệu cùng sở hữu một field.
- Event mới và event cũ đến sai thứ tự.

Những trường hợp này cần quy tắc nghiệp vụ: từ chối, merge, ưu tiên nguồn, version ordering hoặc reconciliation.

### 14.4. Script atomic có thể giảm read-modify-write

Nếu phép biến đổi có thể biểu diễn bằng script nguyên tử ở server, không cần client đọc document rồi ghi lại toàn bộ source.

Ví dụ tăng counter:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "script": {
    "source": "ctx._source.viewCount = (ctx._source.viewCount ?: 0) + params.increment",
    "params": {
      "increment": 1
    }
  }
}
~~~

Script chạy trên trạng thái hiện tại của document, giảm nguy cơ lost update so với read-modify-save toàn bộ source. Tuy nhiên, nếu client retry cùng lệnh sau timeout, counter vẫn có thể tăng hai lần nếu lần đầu đã thành công. Muốn chống duplicate cần operation ID hoặc deduplication logic.

## 15. Quan sát và chẩn đoán update failure

### 15.1. Log có cấu trúc

Khi update thất bại, log các trường:

- Index hoặc alias.
- Document ID.
- Operation type: index/update/delete.
- Status code.
- Elasticsearch error type.
- Version hoặc OCC token nếu được phép.
- Retry attempt.
- Correlation/batch ID.
- Thời gian request.
- Kết quả sau recovery.

Không log toàn bộ source nếu có dữ liệu nhạy cảm.

### 15.2. Metric cần theo dõi

Theo dõi:

- Số update thành công.
- Số update noop.
- Số document missing.
- Số index missing.
- Version conflict count.
- 400 mapping/script error count.
- 401/403 count.
- 429/rejection count.
- Retry count và retry exhaustion.
- Bulk item failure theo error type.
- Update latency p50/p95/p99.

Không dùng document ID làm label metric vì cardinality có thể tăng rất lớn. Dùng log/trace cho định danh cụ thể.

### 15.3. Dùng conflict rate để tìm contention

Nếu conflict tăng đột biến, kiểm tra:

- Có nhiều worker xử lý cùng một key không?
- Batch có bị duplicate không?
- Consumer có xử lý song song vượt mức cần thiết không?
- Một document tổng hợp có trở thành hot spot không?
- Có thể chia document hoặc chuyển phép cập nhật sang event aggregation không?

Không chỉ tăng retry_on_conflict. Retry nhiều hơn có thể giảm lỗi nhìn thấy nhưng che giấu thiết kế contention kém.

### 15.4. Theo dõi missing document theo nguồn

Missing document tăng có thể phản ánh:

- Event ordering sai.
- Producer phát event update trước create.
- Retention xóa document quá sớm.
- Sai index/alias theo môi trường.
- Consumer dùng ID không nhất quán.
- Reindex hoặc alias switch đang diễn ra.

Phân nhóm theo operation và nguồn sự kiện để tìm nguyên nhân.

## 16. Kiểm thử version conflict và missing document

### 16.1. Test document missing

Tạo một ID không tồn tại và xác nhận:

- Repository findById trả empty.
- Update không upsert trả lỗi document missing theo API.
- Update có upsert tạo document nếu đó là behavior được yêu cầu.
- Delete missing được xử lý theo contract của ứng dụng.

### 16.2. Test optimistic concurrency

Một integration test nên:

1. Tạo document.
2. Đọc document và giữ version/OCC token.
3. Cập nhật document bằng client thứ hai.
4. Gửi update bằng token cũ.
5. Xác nhận 409 hoặc exception optimistic locking tương ứng.
6. Đọc lại document và xác nhận dữ liệu mới của writer thứ hai còn nguyên.

Test này chứng minh hệ thống phát hiện stale update thay vì chỉ kiểm tra annotation.

### 16.3. Test retry có tính toán lại

Giả lập hoặc tạo conflict thực:

- Lần đầu đọc version A.
- Một writer khác lưu version B.
- Writer đầu nhận conflict.
- Writer đầu đọc lại B.
- Tính lại update dựa trên B.
- Ghi thành công version mới.

Xác nhận không mất field được writer thứ hai cập nhật.

### 16.4. Test bulk partial failure

Gửi một bulk chứa:

- Một item hợp lệ.
- Một item conflict.
- Một item document missing.
- Một item mapping error.

Xác nhận response được phân loại từng item, chỉ retry item phù hợp và item đã thành công không bị gửi lại.

### 16.5. Test concurrent writer

Dùng nhiều thread hoặc worker đồng thời cập nhật cùng document. Kiểm tra:

- Không có lost update khi OCC được bật.
- Retry budget được tôn trọng.
- Conflict được trả về rõ ràng khi hết retry.
- Metric conflict tăng đúng.
- Không tạo retry storm.

## 17. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| 409 khi save entity | Version cũ hoặc document đã thay đổi | Đọc lại, merge hoặc trả conflict |
| Cập nhật mới bị mất | Ghi toàn bộ source từ entity stale | Dùng OCC hoặc partial update |
| 404 khi update | Document ID không tồn tại | Xác định missing có hợp lệ không; chọn upsert hoặc xử lý nghiệp vụ |
| 404 khi mọi thao tác cùng index | Index/alias không tồn tại | Kiểm tra provisioning và alias |
| Search trả 200 nhưng không có hit | Query không khớp document | Kiểm tra query, refresh và dữ liệu |
| Delete trả not_found | Document đã không tồn tại | Xử lý theo contract idempotent |
| 400 mapper_parsing_exception | Field type/payload không tương thích | Sửa dữ liệu hoặc migration mapping |
| Script exception | Script sai hoặc field thiếu | Kiểm tra script và input |
| 403 khi update | Thiếu write privilege | Kiểm tra role và index pattern |
| 429 khi update | Cluster quá tải | Backoff, jitter và giảm concurrency |
| Update được tạo document ngoài ý muốn | Bật upsert quá rộng | Chỉ bật upsert khi nghiệp vụ cho phép |
| Retry conflict vẫn thất bại | Gửi lại payload hoặc token stale | Đọc lại và tính lại state |
| Counter tăng nhiều lần | Retry update script sau timeout | Dùng event ID/deduplication |
| Bulk HTTP 200 nhưng dữ liệu thiếu | Không kiểm tra item errors | Phân loại từng bulk item |
| Runtime tự tạo index sai mapping | Cấp quyền provisioning cho runtime | Tách migration/provisioning khỏi writer |

## 18. Quy trình xử lý một update thất bại

Khi một thao tác update thất bại:

1. Ghi nhận index/alias, document ID, operation và status.
2. Đọc error type/reason để phân biệt missing, conflict, mapping, security và overload.
3. Nếu document missing, kiểm tra index có tồn tại và xác định chính sách create/upsert.
4. Nếu version conflict, xác định writer khác đã thay đổi field nào.
5. Chọn fail-fast, merge, read-modify-write hoặc atomic script theo nghiệp vụ.
6. Nếu retry, giới hạn số lần và tính lại từ trạng thái mới.
7. Không retry lỗi mapping, authorization hoặc cấu hình cố định.
8. Với bulk, chỉ retry item lỗi phù hợp.
9. Giữ operation ID/version để chống duplicate khi timeout hoặc redelivery.
10. Ghi metric, log và alert theo error type.
11. Kiểm thử race condition và negative cases bằng Elasticsearch thật.
12. Rà soát ownership của document/field nếu conflict lặp lại.

## 19. Những điểm cần ghi nhớ

- Version conflict thường là dấu hiệu dữ liệu đã thay đổi kể từ lúc đọc; nó bảo vệ ứng dụng khỏi lost update.
- Elasticsearch OCC dùng **_seq_no** và **_primary_term**; không nhầm chúng với **_version**.
- Spring Data Elasticsearch hỗ trợ **@Version** để phát hiện cập nhật cạnh tranh theo contract của phiên bản.
- Document missing khác index/alias missing; cùng là 404 nhưng cần xử lý khác nhau.
- Repository findById thường biểu diễn missing bằng **Optional.empty()** hoặc **Mono.empty()**.
- save ghi representation của entity; dùng Update API khi chỉ muốn thay đổi một phần document.
- Update không tự tạo document missing; dùng upsert, doc_as_upsert hoặc scripted_upsert khi nghiệp vụ cho phép.
- retry_on_conflict là retry cho Update API khi có conflict, không phải retry tổng quát cho mọi lỗi.
- Với OCC token stale, không gửi lại cùng payload; hãy đọc lại và tính lại hoặc trả HTTP 409.
- Script update có thể chạy lại; không đặt side effect bên ngoài trong script.
- Timeout không chứng minh write chưa xảy ra; thiết kế ID ổn định và deduplication.
- Bulk response có thể HTTP 200 nhưng một số item thất bại; xử lý theo từng item.
- Mapping, script, security và overload errors cần các hướng phục hồi riêng.
- Tách quyền provisioning khỏi runtime để tránh ứng dụng tự tạo index sai.
- Theo dõi conflict rate, missing rate, update failure theo error type và retry exhaustion.

Version conflict, document missing và update failure là ba tín hiệu khác nhau về trạng thái dữ liệu hoặc môi trường. Khi phân loại đúng nguyên nhân, dùng OCC để bảo vệ cập nhật cạnh tranh, chỉ upsert khi có chủ đích và retry theo trạng thái mới, ứng dụng Spring Data Elasticsearch có thể phục hồi lỗi mà không làm mất thay đổi hợp lệ hoặc tạo dữ liệu ngoài ý muốn.

