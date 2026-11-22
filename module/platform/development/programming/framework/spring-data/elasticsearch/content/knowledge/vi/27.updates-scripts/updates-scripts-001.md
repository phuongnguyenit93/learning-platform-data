# Phân biệt index toàn bộ tài liệu và partial update

Trong Elasticsearch, cập nhật một document có thể được thực hiện theo hai cách chính:

- **Index toàn bộ document**: gửi một representation mới của document với cùng ID. Nội dung _source hiện tại được thay thế bằng nội dung mới.
- **Partial update**: gửi một phần field cần thay đổi hoặc một script. Elasticsearch áp dụng thay đổi lên document hiện có và giữ lại các field không được đụng tới.

Hai thao tác có thể cùng dùng một document ID nhưng semantics khác nhau. Chọn sai có thể làm mất dữ liệu: một DTO chỉ chứa vài field được gửi qua save() có thể thay thế toàn bộ source và khiến các field còn lại biến mất. Ngược lại, partial update phù hợp khi chỉ thay đổi một vài thuộc tính, nhưng cần xử lý rõ field null, array, object lồng nhau, document chưa tồn tại và xung đột ghi đồng thời.

Trong Spring Data Elasticsearch, save() thường biểu diễn thao tác index document; partial update được thực hiện qua ElasticsearchOperations và UpdateQuery, bulk update hoặc Elasticsearch Java API Client. Bài này phân biệt các semantics, minh họa REST DSL và Java API, đồng thời chỉ ra cách chọn thao tác an toàn theo nghiệp vụ.

## 1. Hai cách cập nhật và khác biệt cốt lõi

Giả sử document trong index products đang có source:

~~~json
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 259900,
  "active": true,
  "description": "Bluetooth mouse with rechargeable battery",
  "stock": 42
}
~~~

Ứng dụng chỉ muốn đổi giá thành 279900.

Nếu gửi toàn bộ document qua Index API:

~~~http
PUT /products/_doc/P-1001
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 279900,
  "active": true,
  "description": "Bluetooth mouse with rechargeable battery",
  "stock": 42
}
~~~

Elasticsearch thay thế source của document bằng JSON vừa gửi. Tất cả field cần giữ phải có mặt trong representation mới.

Nếu dùng Update API với partial document:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

Chỉ priceInCents được cập nhật. Các field như sku, name, description, stock tiếp tục giữ giá trị hiện có.

| Tiêu chí | Index toàn bộ document | Partial update |
|---|---|---|
| API Elasticsearch | Index API | Update API |
| Nội dung gửi lên | Toàn bộ document mới | Chỉ field thay đổi hoặc script |
| Field không gửi | Không còn trong source mới | Giữ nguyên |
| Field gửi với null | Phụ thuộc JSON/converter; source mới có thể chứa null hoặc bỏ qua theo cấu hình | Được đặt thành null nếu field null được gửi |
| Document chưa tồn tại | Tạo mới theo Index API | Mặc định báo không tìm thấy, trừ khi cấu hình upsert |
| Dùng trong Spring Data | save() / saveAll() | UpdateQuery, bulk update hoặc client API |
| Phù hợp | Ghi mới hoặc thay thế snapshot đầy đủ | Chỉnh sửa một phần document hiện có |

Cả hai cách cuối cùng đều làm Elasticsearch cập nhật cấu trúc được lập chỉ mục cho document. Partial update không phải thao tác sửa một cột vật lý như database quan hệ; Elasticsearch lấy source hiện tại, áp dụng patch/script rồi index lại document đã thay đổi.

## 2. Index API: thay thế toàn bộ document

Index API ghi document theo ID. Nếu ID chưa tồn tại, document được tạo. Nếu ID đã tồn tại, source cũ được thay thế bằng source mới.

~~~http
PUT /products/_doc/P-1001
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 279900,
  "active": true,
  "stock": 42
}
~~~

Nếu source cũ có description nhưng JSON mới không có field đó, source mới không còn description.

Điều này có thể đúng nếu ứng dụng đang ghi một snapshot đầy đủ và chủ động muốn thay thế trạng thái document. Nó có thể gây mất dữ liệu nếu ứng dụng chỉ có một phần thông tin.

### 2.1. save() trong Spring Data Elasticsearch

Với repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Có thể lưu:

~~~java
Product product = loadCompleteProduct();
product.setPriceInCents(279900L);

productRepository.save(product);
~~~

Hoặc dùng Operations:

~~~java
Product saved = operations.save(product);
~~~

save() là thao tác ghi document theo ID và thường dùng Index API. Nếu ID đã tồn tại, document được index lại với nội dung từ object được serialize. Vì vậy object truyền vào cần đại diện cho trạng thái đầy đủ mà ứng dụng muốn lưu.

Ví dụ nguy hiểm:

~~~java
Product patch = new Product();
patch.setId("P-1001");
patch.setPriceInCents(279900L);

productRepository.save(patch);
~~~

Nếu object này chỉ có ID và giá, các field khác có thể bị mất khỏi source sau khi save, vì object được chuyển thành document mới. Kết quả cụ thể còn chịu ảnh hưởng cấu hình converter đối với null field, nhưng không nên dùng save() như một lệnh patch.

### 2.2. saveAll() cũng không phải partial update

saveAll() thường ghi nhiều document bằng bulk index operation. Mỗi object vẫn được xem là document cần index đầy đủ.

~~~java
productRepository.saveAll(products);
~~~

Nếu danh sách chứa các object chỉ có một vài field, không nên giả định các field cũ sẽ được giữ. Bulk chỉ là cách gửi nhiều thao tác hiệu quả hơn; nó không đổi semantics của từng thao tác index.

### 2.3. Index API và create-only

Index API có thể tạo mới hoặc thay thế theo ID. Nếu cần bảo đảm chỉ tạo khi ID chưa tồn tại, Elasticsearch có create operation:

~~~http
PUT /products/_create/P-1001
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 259900
}
~~~

Nếu ID đã tồn tại, create-only trả conflict thay vì ghi đè. Điều này hữu ích khi ID phải duy nhất và ứng dụng muốn phát hiện việc tạo trùng.

Không nhầm create-only với partial update: create-only chỉ kiểm soát điều kiện tạo mới, không thay đổi semantics cập nhật field.

## 3. Update API: thay đổi một phần document

Update API nhận một trong các dạng chính:

- doc: partial document chứa field cần thay đổi.
- script: script Painless thao tác trên _source.
- upsert: document dùng khi ID chưa tồn tại.
- doc_as_upsert: dùng chính doc làm document tạo mới nếu chưa tồn tại.

Ví dụ chỉ đổi giá:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

Document sau cập nhật vẫn giữ các field khác.

### 3.1. Field không có trong partial document được giữ nguyên

Giả sử source hiện tại:

~~~json
{
  "name": "Wireless Mouse",
  "priceInCents": 259900,
  "active": true,
  "stock": 42
}
~~~

Gửi:

~~~json
{
  "doc": {
    "stock": 35
  }
}
~~~

Source sau update về mặt dữ liệu:

~~~json
{
  "name": "Wireless Mouse",
  "priceInCents": 259900,
  "active": true,
  "stock": 35
}
~~~

Các field không được nêu trong doc được giữ lại. Đây là khác biệt quan trọng nhất so với index toàn bộ document.

### 3.2. Partial update không phải patch theo từng byte

Update API xử lý document ở phía Elasticsearch: đọc source hiện tại, áp dụng partial document hoặc script rồi index lại document đã thay đổi. Vì vậy:

- Không cần ứng dụng tải toàn bộ object về rồi gửi lại.
- Không có nghĩa Elasticsearch chỉ ghi một vài byte hoặc một cột.
- Document lớn và update thường xuyên vẫn có chi phí đọc source, xử lý và indexing.
- _source phải được bật để Update API hoạt động theo cơ chế thông thường.

Nếu cần thay đổi nhiều field cùng lúc, một partial document có thể chứa nhiều field:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "priceInCents": 279900,
    "stock": 35,
    "active": false
  }
}
~~~

Thao tác này cập nhật các field được gửi trong cùng một update request.

## 4. Phân biệt field bị bỏ qua, field null và xóa field

Đây là nguồn lỗi phổ biến khi xây dựng API patch.

### 4.1. Không gửi field

Nếu partial document không chứa field description, giá trị cũ được giữ nguyên:

~~~json
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

description không bị thay đổi.

### 4.2. Gửi field với null

Nếu gửi:

~~~json
{
  "doc": {
    "description": null
  }
}
~~~

Elasticsearch cập nhật field description thành null trong _source theo semantics của update. Field có thể không có indexed value để query, trừ khi mapping dùng null_value cho mục đích indexing. null_value không thay thế giá trị null trong _source.

Null khác với không gửi field. Với partial update, null là một giá trị được truyền vào và có thể mang nghĩa xóa giá trị nghiệp vụ, nhưng field vẫn có thể xuất hiện trong source dưới dạng null.

### 4.3. Xóa hẳn field khỏi _source

Nếu muốn loại field khỏi JSON source, dùng script:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "ctx._source.remove('description')"
  }
}
~~~

Script xóa key description khỏi _source. Sau update, field không còn tồn tại trong source.

Không dùng null nếu nghiệp vụ yêu cầu field biến mất hoàn toàn. Chọn rõ semantics API:

| Ý định | Cách biểu diễn |
|---|---|
| Không thay đổi field | Không đưa field vào partial document |
| Đặt field thành null | Gửi field với null |
| Xóa key khỏi source | Script ctx._source.remove('field') |
| Đặt giá trị mặc định | Gửi giá trị cụ thể hoặc script |

### 4.4. Java null và JSON serialization

Khi tạo Document hoặc serialize DTO, cấu hình converter có thể quyết định field Java null có được ghi vào JSON hay bị bỏ qua. Vì vậy, đừng dựa vào một DTO có field null để biểu diễn ba trạng thái "không đổi", "xóa" và "đặt null" cùng lúc.

Đối với HTTP PATCH, nên dùng một representation có thể phân biệt field không được cung cấp với field được cung cấp rõ ràng là null. Có thể dùng JsonNode, wrapper kiểu Optional có semantics phù hợp, hoặc một command object có cờ present riêng.

## 5. Partial update với object lồng nhau và array

Với object lồng nhau, partial document thường được merge theo cấu trúc object. Tuy nhiên, cần xác nhận hành vi trên dữ liệu và phiên bản Elasticsearch thực tế, đặc biệt khi object chứa array hoặc khi ứng dụng phụ thuộc vào việc giữ từng sub-field.

Ví dụ source:

~~~json
{
  "name": "Wireless Mouse",
  "shipping": {
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "postalCode": "700000"
  }
}
~~~

Partial update:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "shipping": {
      "district": "District 3"
    }
  }
}
~~~

Với object merge, mục tiêu là chỉ đổi shipping.district và giữ các sub-field khác. Nếu ứng dụng cần bảo đảm tuyệt đối không ghi đè object lồng nhau trong một cấu trúc phức tạp, hãy dùng script gán đúng đường dẫn:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "ctx._source.shipping.district = params.district",
    "params": {
      "district": "District 3"
    }
  }
}
~~~

Nếu shipping có thể chưa tồn tại, script cần kiểm tra và khởi tạo object trước khi gán.

### 5.1. Array thường được thay thế, không tự động nối thêm

Giả sử source có:

~~~json
{
  "tags": ["wireless", "bluetooth"]
}
~~~

Gửi partial update:

~~~json
{
  "doc": {
    "tags": ["ergonomic"]
  }
}
~~~

Field tags được cập nhật bằng mảng mới; không nên kỳ vọng Elasticsearch tự nối phần tử mới vào array cũ.

Muốn append một phần tử, dùng script:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "if (ctx._source.tags == null) { ctx._source.tags = []; } ctx._source.tags.add(params.tag)",
    "params": {
      "tag": "ergonomic"
    }
  }
}
~~~

Muốn xóa một phần tử:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "if (ctx._source.tags != null) { ctx._source.tags.removeIf(tag -> tag == params.tag); }",
    "params": {
      "tag": "bluetooth"
    }
  }
}
~~~

Painless hỗ trợ một tập cú pháp và API collection theo context/phiên bản. Hãy kiểm tra script trên Elasticsearch version của dự án, nhất là khi dùng lambda hoặc collection method.

## 6. Partial update bằng ElasticsearchOperations

Trong Spring Data Elasticsearch, ElasticsearchOperations cung cấp abstraction cho các thao tác ngoài CRUD repository cơ bản. Với các phiên bản hiện đại, UpdateQuery mô tả một update request.

Ví dụ khái niệm theo API Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

Document partialDocument = Document.create();
partialDocument.put("priceInCents", 279900L);
partialDocument.put("stock", 35);

UpdateQuery updateQuery = UpdateQuery.builder("P-1001")
    .withDocument(partialDocument)
    .build();

UpdateResponse response =
    operations.update(updateQuery, Product.class);
~~~

Document trong ví dụ là org.springframework.data.elasticsearch.core.document.Document, không phải entity Product. Nó chứa các field cần patch.

Một số phiên bản cung cấp overload nhận IndexCoordinates để chỉ rõ index:

~~~java
UpdateResponse response = operations.update(
    updateQuery,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Chữ ký overload, kiểu response và builder method có thể khác giữa các minor version. Hãy kiểm tra ElasticsearchOperations, UpdateQuery.Builder và UpdateResponse trong dependency của dự án. Nếu project không có đúng overload, dùng API hiện có hoặc Elasticsearch Java API Client trực tiếp; không tự giả định một method framework tồn tại.

### 6.1. Tạo partial document

Có thể tạo Document từ map:

~~~java
Map<String, Object> fields = Map.of(
    "priceInCents", 279900L,
    "stock", 35
);

Document partialDocument = Document.from(fields);
~~~

Cách khởi tạo Document và factory method tùy phiên bản. Nếu dùng Map.of(...) thì không thể truyền null vì Java Map.of không chấp nhận null key/value. Hãy dùng cấu trúc có thể biểu diễn null rõ ràng nếu đó là ý định.

### 6.2. Cập nhật qua ID và index đích

Update cần xác định document ID và index/alias đích. Với repository có index name mặc định, có thể dùng entity class để Spring Data xác định index theo mapping. Nếu ứng dụng ghi vào index động hoặc alias, truyền IndexCoordinates tương ứng.

Không giả định UpdateQuery tự suy ra đúng index nếu domain type không có mapping hoặc index đích khác @Document(indexName=...).

## 7. Upsert: cập nhật hoặc tạo mới

Update API mặc định yêu cầu document đã tồn tại. Nếu ID chưa tồn tại, request có thể trả lỗi document missing.

Có hai cách phổ biến để định nghĩa dữ liệu khi document chưa tồn tại:

- doc_as_upsert: dùng chính doc làm source khi tạo document mới.
- upsert: cung cấp một document riêng để dùng khi ID chưa tồn tại.

### 7.1. doc_as_upsert

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "sku": "SKU-1001",
    "name": "Wireless Mouse",
    "stock": 35
  },
  "doc_as_upsert": true
}
~~~

Nếu P-1001 đã tồn tại, các field trong doc được cập nhật. Nếu chưa tồn tại, doc được dùng để tạo document mới.

Điều này hữu ích khi payload update cũng đủ để tạo document ban đầu. Nếu payload chỉ chứa stock, document mới có thể chỉ có stock và thiếu các field bắt buộc của nghiệp vụ.

### 7.2. upsert riêng

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "stock": 35
  },
  "upsert": {
    "sku": "SKU-1001",
    "name": "Wireless Mouse",
    "priceInCents": 259900,
    "stock": 35,
    "active": true
  }
}
~~~

Nếu document tồn tại, chỉ stock được cập nhật. Nếu chưa tồn tại, Elasticsearch index source trong upsert.

Dùng upsert riêng khi cấu trúc tạo mới cần đầy đủ hơn payload patch.

### 7.3. scripted_upsert

Nếu dùng script và muốn script chạy cả khi document chưa tồn tại, có thể dùng scripted_upsert cùng upsert:

~~~http
POST /products/_update/P-1001
{
  "scripted_upsert": true,
  "script": {
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.amount",
    "params": {
      "amount": 5
    }
  },
  "upsert": {}
}
~~~

Script được chạy cho trường hợp document chưa tồn tại theo cấu hình scripted_upsert. Hãy bảo đảm script khởi tạo các field cần thiết và upsert source đủ hợp lệ cho mapping/nghiệp vụ.

doc_as_upsert, upsert và scripted_upsert có semantics khác nhau. Chọn một cách phù hợp với luồng ghi, không bật chỉ để tránh lỗi document missing mà chưa xác định trạng thái khởi tạo.

## 8. Script update: thay đổi dữ liệu theo logic

Partial document phù hợp khi biết chính xác giá trị mới. Script phù hợp khi thay đổi phụ thuộc vào giá trị hiện tại hoặc cần thao tác trên collection.

Ví dụ tăng stock thêm một lượng:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 5
    }
  }
}
~~~

Nếu stock có thể chưa tồn tại, script cần xử lý:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.stock == null) { ctx._source.stock = params.amount; } else { ctx._source.stock += params.amount; }",
    "params": {
      "amount": 5
    }
  }
}
~~~

### 8.1. Đặt giá trị theo điều kiện

Ví dụ chỉ cập nhật trạng thái khi đơn hàng chưa bị hủy:

~~~http
POST /orders/_update/O-1001
{
  "script": {
    "source": "if (ctx._source.status != 'CANCELLED') { ctx._source.status = params.status; } else { ctx.op = 'none'; }",
    "params": {
      "status": "SHIPPED"
    }
  }
}
~~~

ctx.op = 'none' yêu cầu không ghi thay đổi nếu điều kiện không thỏa. Script update có thể dùng ctx.op để điều khiển thao tác theo context được hỗ trợ.

Không đưa chuỗi người dùng trực tiếp vào source. Giữ script ổn định và truyền dữ liệu động qua params để giảm rủi ro injection và tăng khả năng tái sử dụng compiled script.

### 8.2. Xóa document bằng script không giống xóa field

Update script có thể điều khiển operation, ví dụ ctx.op = 'delete' để xóa document trong update context. Còn ctx._source.remove('field') chỉ xóa một field khỏi source của document.

Phân biệt rõ hai ý định để tránh xóa cả document khi chỉ muốn bỏ một thuộc tính.

## 9. Update theo điều kiện: Update By Query

Nếu cần cập nhật nhiều document được chọn bởi query, có thể dùng Update By Query API:

~~~http
POST /products/_update_by_query
{
  "query": {
    "term": {
      "category": "clearance"
    }
  },
  "script": {
    "source": "ctx._source.active = false"
  }
}
~~~

Elasticsearch tìm các document khớp query và chạy script cho từng document. Đây là thao tác nhiều document, phù hợp với migration dữ liệu hoặc cập nhật hàng loạt theo điều kiện.

### 9.1. Update By Query không phải transaction toàn bộ tập

Update By Query không bảo đảm toàn bộ tập document được cập nhật trong một transaction nguyên tử. Có thể xảy ra:

- Một số document cập nhật thành công, một số thất bại.
- Version conflict.
- Timeout hoặc task bị hủy.
- Cần retry hoặc tiếp tục theo kết quả task.
- Cluster chịu tải lớn khi xử lý nhiều document.

Hãy kiểm tra response và failures, đặt query đủ hẹp, cân nhắc conflicts=proceed, throttling và slices khi phù hợp. conflicts=proceed cho phép tiếp tục khi gặp conflict nhưng không tự giải quyết logic xung đột; các document conflict vẫn có thể không được cập nhật.

### 9.2. Update By Query và Spring Data Elasticsearch

Khả năng hỗ trợ Update By Query ở abstraction Spring Data thay đổi theo phiên bản. Nếu ElasticsearchOperations trong dependency không expose API phù hợp, có thể dùng Elasticsearch Java API Client trực tiếp để tạo UpdateByQueryRequest.

Không nhầm UpdateQuery cho một document với Update By Query. Một thao tác xác định document bằng ID; thao tác kia chọn nhiều document bằng query.

## 10. Bulk update và nhiều document

Nếu có danh sách ID và mỗi document cần partial update, có thể dùng bulk update để giảm số request mạng.

Ví dụ khái niệm:

~~~java
List<UpdateQuery> updates = new ArrayList<>();

updates.add(
    UpdateQuery.builder("P-1001")
        .withDocument(documentForFirstProduct)
        .build()
);

updates.add(
    UpdateQuery.builder("P-1002")
        .withDocument(documentForSecondProduct)
        .build()
);

operations.bulkUpdate(
    updates,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Tên overload và response của bulkUpdate phụ thuộc Spring Data Elasticsearch version. Hãy xác nhận trên ElasticsearchOperations của dự án.

Bulk request là nhóm nhiều thao tác độc lập trong một request. Một item lỗi không nhất thiết làm mọi item khác thất bại. Luôn kiểm tra item-level result và xử lý retry theo từng document phù hợp.

Nếu mỗi document cần logic khác nhau, tạo UpdateQuery riêng cho từng ID. Nếu cùng một script/điều kiện áp dụng cho một tập document lớn, Update By Query có thể phù hợp hơn.

## 11. Xung đột ghi đồng thời và optimistic concurrency

Hai request có thể cùng đọc một document rồi ghi thay đổi. Nếu cả hai dùng full index với source cũ, request đến sau có thể ghi đè thay đổi của request trước. Đây là lost update.

Ví dụ:

1. Request A đọc stock = 10.
2. Request B đọc stock = 10.
3. A ghi stock = 8.
4. B ghi stock = 7 dựa trên bản cũ.
5. Kết quả cuối là 7, thay vì có thể phải là 5 nếu cả hai đơn đều trừ 2 và 3.

Update script tăng/giảm dựa trên source hiện tại có thể giảm kiểu lost update do read-modify-write ở tầng ứng dụng, vì thao tác script được thực thi tại Elasticsearch. Tuy nhiên, nghiệp vụ vẫn cần xác định rõ quy tắc khi có xung đột và retry.

### 11.1. Optimistic concurrency với sequence number và primary term

Elasticsearch hỗ trợ optimistic concurrency control bằng if_seq_no và if_primary_term. Client gửi giá trị phiên bản mà nó đã đọc; Elasticsearch chỉ cập nhật nếu document vẫn ở đúng phiên bản đó.

REST ví dụ:

~~~http
POST /products/_update/P-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

Nếu document đã thay đổi kể từ khi đọc, Elasticsearch trả version conflict. Ứng dụng có thể đọc lại, kiểm tra nghiệp vụ và quyết định retry hoặc trả conflict cho caller.

Spring Data Elasticsearch có các cơ chế version/concurrency tùy thế hệ API và mapping. @Version là annotation cần tìm hiểu khi dùng optimistic locking trong entity:

~~~java
@Version
private Long version;
~~~

Chữ ký và semantics tích hợp @Version phụ thuộc phiên bản Spring Data Elasticsearch và cách client thực hiện thao tác. Với UpdateQuery hoặc client request tùy chỉnh, kiểm tra rõ cách truyền concurrency token; không giả định mọi overload update tự động dùng cùng token như repository save.

### 11.2. retry_on_conflict

Update API có tùy chọn retry_on_conflict để Elasticsearch thử lại update khi gặp version conflict:

~~~http
POST /products/_update/P-1001?retry_on_conflict=3
{
  "script": {
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

Tùy chọn này hữu ích với phép cập nhật dựa trên trạng thái hiện tại, chẳng hạn tăng counter. Elasticsearch đọc phiên bản mới rồi thử lại script theo số lần được cấu hình.

Không bật retry một cách mù quáng cho mọi business operation. Script phải an toàn khi chạy lại trên source mới; nếu thao tác không idempotent hoặc có side effect ngoài Elasticsearch, cần thiết kế riêng.

## 12. No-op detection và refresh

Update API có thể phát hiện request không tạo thay đổi thực tế và trả kết quả noop thay vì ghi lại document. Có thể điều khiển bằng detect_noop:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "active": true
  },
  "detect_noop": true
}
~~~

Nếu active đã là true, Elasticsearch có thể xác định không cần reindex document.

Refresh là một khái niệm khác. Update thành công không có nghĩa Search API lập tức nhìn thấy dữ liệu mới; Elasticsearch là hệ thống near-real-time. Có thể dùng refresh policy phù hợp trong thao tác ghi hoặc chờ refresh tự nhiên.

Không bật refresh=wait_for sau mọi lần update trong luồng ghi tải cao nếu không cần tính hiển thị tức thì. Refresh thường xuyên có thể ảnh hưởng hiệu năng indexing.

## 13. Mapping và kiểu dữ liệu khi cập nhật

Partial update không cho phép thay đổi kiểu mapping của field hiện có.

Ví dụ priceInCents đã mapping long. Gửi string:

~~~json
{
  "doc": {
    "priceInCents": "two hundred"
  }
}
~~~

có thể gây lỗi parsing hoặc mapping. Nếu cần đổi kiểu field, thường phải tạo index mới với mapping phù hợp và reindex dữ liệu.

Thêm field mới có thể kích hoạt dynamic mapping nếu index cho phép. Tuy nhiên, dựa vào dynamic mapping cho dữ liệu production có thể dẫn đến kiểu dữ liệu ngoài ý muốn. Nên định nghĩa mapping rõ ràng cho field quan trọng.

Partial update không tự cập nhật annotation Java hoặc mapping metadata. Mapping của index và serialization của entity là hai phần cần đồng bộ.

## 14. Chọn full index hay partial update?

Có thể dùng các câu hỏi sau để quyết định:

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Tạo document mới từ object đầy đủ | save() / Index API |
| Đồng bộ snapshot đầy đủ từ nguồn chuẩn | Index API |
| Thay thế toàn bộ source bằng phiên bản mới | Index API |
| Chỉ đổi một vài field đã biết | Update API với doc |
| Tăng/giảm counter dựa trên giá trị hiện tại | Script update |
| Thêm/xóa phần tử trong array | Script update |
| Xóa một field khỏi source | Script ctx._source.remove(...) |
| Tạo nếu chưa có, cập nhật nếu đã có | Update API với upsert phù hợp |
| Cập nhật nhiều ID theo patch khác nhau | Bulk update |
| Cập nhật mọi document theo điều kiện | Update By Query |
| Cần phát hiện ghi đồng thời | Optimistic concurrency |
| Cần cập nhật toàn bộ dữ liệu sau đổi mapping | Tạo index mới và reindex |

Một nguyên tắc dễ nhớ: save() dành cho object đại diện cho document đầy đủ; partial update dành cho command chỉ mô tả thay đổi.

## 15. Ví dụ service: cập nhật một field an toàn

Giả sử API cho phép thay đổi giá sản phẩm. Service không cần đọc toàn bộ entity rồi save lại.

~~~java
@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void changePrice(String productId, long newPriceInCents) {
        if (newPriceInCents < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }

        Document patch = Document.create();
        patch.put("priceInCents", newPriceInCents);

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
            .withDocument(patch)
            .build();

        operations.update(
            updateQuery,
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

Ví dụ dùng API Spring Data Elasticsearch 5.x theo dạng thường gặp. Kiểm tra import, overload và response type trong phiên bản dự án. Nếu document không tồn tại, thao tác mặc định có thể báo lỗi; service cần quyết định có trả 404, dùng upsert hay tạo document riêng.

Ưu điểm của cách này là command chỉ mang field cần đổi, giảm nguy cơ ghi đè các field khác mà service không sở hữu.

## 16. Ví dụ service: tăng stock bằng script

Nếu yêu cầu là tăng stock theo một lượng, không cần đọc stock về Java rồi cộng:

~~~java
public void increaseStock(String productId, long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }

    UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(
            "if (ctx._source.stock == null) { " +
            "ctx._source.stock = params.amount; " +
            "} else { ctx._source.stock += params.amount; }"
        )
        .withParams(Map.of("amount", amount))
        .build();

    operations.update(
        updateQuery,
        Product.class,
        IndexCoordinates.of("products")
    );
}
~~~

Tên builder method và kiểu tham số script có thể khác giữa các minor version. Một số API yêu cầu đối tượng Script cụ thể hoặc cấu hình script type riêng. Hãy kiểm tra UpdateQuery.Builder của dependency đang dùng.

Nếu yêu cầu là không cho stock âm hoặc không vượt tồn kho, script cần kiểm tra điều kiện và báo kết quả phù hợp. Đừng chỉ cộng/trừ rồi hy vọng tầng Java đã kiểm soát được mọi request đồng thời.

## 17. API PATCH và thiết kế command object

Một HTTP endpoint PATCH thường biểu diễn thay đổi một phần:

~~~http
PATCH /products/P-1001
Content-Type: application/json

{
  "priceInCents": 279900
}
~~~

Không nên deserialize payload vào một entity Product đầy đủ rồi gọi repository.save() nếu các field không có trong request sẽ thành null/default.

Thay vào đó, dùng một patch DTO:

~~~java
public record ProductPatchRequest(
    Long priceInCents,
    Boolean active,
    Integer stock
) {
}
~~~

Tuy nhiên, DTO trên vẫn cần semantics rõ ràng cho null:

- Field không được gửi có nghĩa không thay đổi.
- Field gửi null có thể có nghĩa đặt null hoặc xóa.
- Primitive như boolean/int không phân biệt được thiếu với false/0 sau deserialize trong nhiều cấu hình.

Có thể dùng JsonNode, wrapper kiểu PatchField<T> hoặc custom deserializer để giữ thông tin field có xuất hiện trong request hay không.

Sau khi validate, service tạo Document chỉ gồm các field thực sự được yêu cầu cập nhật. Đây là ranh giới quan trọng giữa API contract và Elasticsearch Update API.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Sau save, field cũ biến mất | Object gửi vào chỉ có một phần dữ liệu và Index API thay source | Dùng object đầy đủ hoặc UpdateQuery |
| Partial update không thay đổi field | Tên field sai hoặc Document không chứa key mong muốn | Kiểm tra JSON request thực tế |
| Field trở thành null ngoài ý muốn | DTO null được serialize thành field null | Phân biệt field thiếu và null trong patch DTO |
| Muốn xóa field nhưng vẫn thấy null | Gửi null chỉ đặt giá trị null | Dùng script remove khỏi _source |
| Array bị thay toàn bộ | Partial doc gán array mới | Dùng script append/remove nếu cần thao tác phần tử |
| Update document không tồn tại bị lỗi | Chưa cấu hình upsert | Dùng upsert hoặc xử lý not found |
| Update script lỗi khi field thiếu | Script truy cập field chưa khởi tạo | Kiểm tra và khởi tạo field trong Painless |
| Mapping exception | Giá trị gửi không tương thích kiểu field | Kiểm tra mapping và kiểu dữ liệu |
| Ghi đồng thời làm mất thay đổi | Full index từ source cũ hoặc thiếu concurrency control | Dùng script update, optimistic concurrency và xử lý conflict |
| Bulk update có một số item lỗi | Bulk item độc lập và có thể thất bại riêng | Kiểm tra từng item result |
| Update By Query cập nhật một phần | Conflict, timeout hoặc task failure | Kiểm tra failures/task status và retry có kiểm soát |
| Search chưa thấy dữ liệu vừa update | Chưa refresh | Dùng refresh policy phù hợp |
| UpdateQuery không biên dịch | Builder/API khác version | Kiểm tra Javadoc của dependency |
| @Version không ngăn conflict như mong đợi | Update path không truyền token theo cách giả định | Xác nhận concurrency API của đúng version |

## 19. Kiểm thử semantics thay vì chỉ kiểm tra request thành công

Integration test nên xác nhận dữ liệu sau thao tác.

### 19.1. Kiểm tra index thay thế toàn bộ source

1. Lưu Product có name, price, stock và description.
2. Tạo một object cùng ID nhưng chỉ có name và price.
3. Gọi save.
4. Đọc document lại và xác nhận semantics thay thế theo mapping/converter hiện tại.

Test này giúp phát hiện việc dùng save cho patch object.

### 19.2. Kiểm tra partial update giữ field khác

1. Lưu Product đầy đủ.
2. Gửi UpdateQuery chỉ có priceInCents.
3. Refresh index nếu test đọc bằng Search API.
4. Đọc lại document.
5. Xác nhận price đổi và name, stock, description vẫn còn.

### 19.3. Kiểm tra null, remove và array

Viết test riêng cho:

- Không gửi field: giá trị cũ giữ nguyên.
- Gửi null: source có null theo semantics mong muốn.
- Script remove: key biến mất khỏi source.
- Array patch: xác nhận array được thay thế.
- Script append/remove: xác nhận phần tử được thêm hoặc bỏ đúng.

### 19.4. Kiểm tra upsert và concurrency

- Update ID chưa tồn tại mà không upsert phải cho kết quả phù hợp.
- doc_as_upsert tạo document theo payload.
- upsert tạo source đầy đủ theo cấu hình.
- Version conflict được xử lý theo chính sách ứng dụng.
- retry_on_conflict chỉ dùng với script có thể chạy lại an toàn.

Với test chỉ đọc ngay sau thao tác ghi, nhớ rằng Elasticsearch Search API là near-real-time. Có thể cần refresh trong test; không nên ép refresh sau mọi thao tác trong production.

## 20. Quy trình chọn thao tác cập nhật

Khi xây dựng service ghi dữ liệu, hãy xác định:

1. Object đầu vào có đại diện cho toàn bộ document hay chỉ một phần?
2. Field không có trong request phải giữ nguyên, xóa hay nhận giá trị mặc định?
3. Document chưa tồn tại thì trả not found, tạo mới hay dùng upsert?
4. Thay đổi có phụ thuộc giá trị hiện tại không?
5. Có thao tác trên array hoặc object lồng nhau không?
6. Có nhiều request cập nhật cùng document đồng thời không?
7. Có cần optimistic concurrency hoặc retry không?
8. Cập nhật một ID, nhiều ID hay mọi document theo query?
9. Có cần refresh ngay để Search API thấy dữ liệu mới không?
10. Mapping hiện tại có tương thích với giá trị mới không?

Chọn API:

- Full snapshot → save() / Index API.
- Patch field → Update API với doc.
- Logic phụ thuộc source hiện tại → script update.
- Tạo mới khi chưa có → upsert hoặc doc_as_upsert.
- Nhiều ID → bulk update.
- Nhiều document theo điều kiện → Update By Query.

## 21. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Tạo mới hoặc thay thế toàn bộ document | save() / Index API |
| Ghi nhiều document đầy đủ | saveAll() / bulk index |
| Cập nhật một vài field | UpdateQuery với Document |
| Cập nhật theo phép tính trên source hiện tại | Painless script update |
| Xóa một field | ctx._source.remove('field') |
| Thêm/xóa phần tử array | Script update |
| Cập nhật hoặc tạo mới | upsert / doc_as_upsert |
| Chạy script cả khi chưa có document | scripted_upsert |
| Cập nhật nhiều ID | Bulk update |
| Cập nhật document được query chọn | Update By Query |
| Phát hiện ghi đồng thời | if_seq_no, if_primary_term, version control |
| Retry khi conflict | retry_on_conflict nếu operation an toàn khi chạy lại |
| Tránh ghi khi giá trị không đổi | detect_noop |
| Đọc kết quả mới qua Search API | Refresh policy phù hợp |

Index toàn bộ document và partial update có semantics khác nhau dù cùng dùng một ID. save()/Index API thay source bằng representation mới, vì vậy chỉ dùng khi object đầu vào là trạng thái đầy đủ. Update API với doc giữ field không được gửi; script phù hợp với phép tính trên source hiện tại, thao tác array hoặc xóa field. Hãy xác định rõ ý nghĩa của field bị thiếu và field null, chọn upsert khi cần tạo mới, và thiết kế optimistic concurrency cho dữ liệu có nhiều luồng ghi. Trong Spring Data Elasticsearch, dùng ElasticsearchOperations/UpdateQuery hoặc client API đúng phiên bản, rồi kiểm thử dữ liệu sau thao tác để xác nhận các field ngoài phạm vi patch vẫn được giữ nguyên.

