# Xử lý version conflict khi ghi và cập nhật

Khi nhiều request hoặc nhiều service cùng ghi một document Elasticsearch, một writer có thể đọc dữ liệu cũ rồi ghi đè thay đổi mới hơn của writer khác. Đây là vấn đề lost update (mất cập nhật). Elasticsearch dùng optimistic concurrency control để phát hiện trường hợp document đã thay đổi kể từ lúc writer đọc nó. Khi điều kiện phiên bản không còn đúng, thao tác ghi bị từ chối với version conflict thay vì âm thầm ghi đè dữ liệu mới.

Spring Data Elasticsearch hỗ trợ optimistic locking ở cấp entity thông qua annotation @Version. Với các request cập nhật trực tiếp, Elasticsearch cung cấp cặp if_seq_no và if_primary_term. Update API còn có retry_on_conflict để thử lại một update khi gặp conflict. Nếu dữ liệu đến từ một hệ thống nguồn khác có version nghiệp vụ riêng, có thể dùng external versioning cho các thao tác index phù hợp.

Bài học này phân biệt các loại version, cách phát hiện và xử lý conflict khi index/update/delete, cách dùng @Version và UpdateQuery trong Spring Data, cách xử lý lỗi bulk và cách kiểm thử các tình huống ghi đồng thời.

## 1. Version conflict là gì?

Giả sử một sản phẩm có stock = 10. Hai request cùng đọc document ở trạng thái đó:

~~~text
Thời điểm     Writer A                  Writer B
----------------------------------------------------------
t1            Đọc stock = 10
t2                                      Đọc stock = 10
t3            Ghi stock = 8
t4                                      Ghi stock = 7
~~~

Nếu Writer B ghi một document đầy đủ dựa trên bản đọc cũ, nó có thể ghi đè trạng thái mà Writer A vừa lưu. Một thay đổi đã thành công nhưng bị mất khỏi trạng thái cuối.

Optimistic concurrency control (OCC) yêu cầu writer gửi kèm thông tin phiên bản mà nó đã đọc. Elasticsearch chỉ chấp nhận ghi nếu document vẫn ở phiên bản đó. Nếu document đã thay đổi, Elasticsearch trả conflict để ứng dụng đọc lại và quyết định cách hợp nhất.

~~~text
Writer A đọc document + concurrency token
                |
                v
Writer B cập nhật document
                |
                v
Writer A gửi update với token cũ
                |
                v
Elasticsearch kiểm tra token
        /               \
       /                 \
  Còn đúng             Đã thay đổi
     |                      |
     v                      v
  Ghi thành công       409 Version Conflict
                            |
                            v
                    Ứng dụng đọc lại và xử lý
~~~

Elasticsearch dùng optimistic locking vì nhiều hệ thống có xung đột ghi tương đối ít. Thay vì khóa document trong suốt thời gian ứng dụng xử lý, hệ thống cho phép nhiều writer làm việc rồi kiểm tra điều kiện tại thời điểm ghi.

## 2. Phân biệt các loại version và concurrency token

Elasticsearch có một số khái niệm liên quan nhưng không thể thay thế cho nhau:

| Khái niệm | Mục đích | Nguồn giá trị |
|---|---|---|
| Internal document version (_version) | Theo dõi phiên bản nội bộ của document | Elasticsearch |
| Sequence number (_seq_no) | Định danh thứ tự operation trên primary shard | Elasticsearch |
| Primary term (_primary_term) | Phân biệt nhiệm kỳ của primary shard | Elasticsearch |
| External version | So sánh version do hệ thống bên ngoài cung cấp | Database/event/source system |
| Spring Data @Version | Bật version-based optimistic locking cho entity | Spring Data và Elasticsearch |

Hai cơ chế OCC thường gặp là:

1. Version-based concurrency dùng version của document, thường được Spring Data expose qua @Version.
2. Sequence-number-based concurrency dùng đồng thời _seq_no và _primary_term trong request if_seq_no/if_primary_term.

Không chỉ gửi _seq_no mà bỏ _primary_term. Cặp giá trị này phải được giữ nguyên như một token.

### 2.1. Internal _version

Elasticsearch gán _version cho document. Với internal versioning mặc định, mỗi lần ghi thành công làm version tăng. Có thể xem version trong response:

~~~http
GET products/_doc/p-100
~~~

Response rút gọn:

~~~json
{
  "_index": "products",
  "_id": "p-100",
  "_version": 7,
  "found": true,
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

_version do Elasticsearch quản lý. Không dùng nó như version nghiệp vụ của seller, product hoặc event trừ khi ứng dụng chủ động chọn cơ chế external versioning.

### 2.2. Sequence number và primary term

Elasticsearch gán sequence number cho mỗi operation được thực thi trên primary shard. Primary term thay đổi khi primary shard được thay thế/elected trong một nhiệm kỳ mới.

GET document trả các metadata này:

~~~http
GET products/_doc/p-100
~~~

Response minh họa:

~~~json
{
  "_index": "products",
  "_id": "p-100",
  "_seq_no": 42,
  "_primary_term": 3,
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

Ứng dụng giữ cặp (42, 3) để nói rằng: chỉ cập nhật nếu document vẫn ở đúng trạng thái đã đọc. Nếu một operation khác đã thay đổi document hoặc primary term đã thay đổi, điều kiện không còn đúng.

## 3. Conditional update bằng if_seq_no và if_primary_term

Giả sử ứng dụng vừa đọc document và nhận _seq_no = 42, _primary_term = 3. Có thể gửi partial update với hai giá trị này:

~~~http
POST products/_update/p-100?if_seq_no=42&if_primary_term=3
{
  "doc": {
    "price": 1399000
  }
}
~~~

Nếu document chưa thay đổi kể từ lúc đọc, update thành công. Nếu writer khác đã ghi trước, Elasticsearch trả HTTP 409 với lỗi version_conflict_engine_exception.

Điểm quan trọng:

- Phải lấy cả _seq_no và _primary_term từ cùng một lần đọc.
- Không tái sử dụng token cũ sau khi update đã thành công.
- Sau conflict, đọc document mới và tính lại thay đổi theo dữ liệu mới.
- Không retry mù với cùng token vì điều kiện vẫn sai.

### 3.1. Conditional index

OCC cũng áp dụng cho thao tác index:

~~~http
PUT products/_doc/p-100?if_seq_no=42&if_primary_term=3
{
  "name": "Wireless Keyboard",
  "price": 1399000,
  "active": true
}
~~~

Nếu điều kiện đúng, document được ghi. Nếu document đã thay đổi, request bị conflict. Index ghi toàn bộ document source, vì vậy chỉ dùng khi ứng dụng có đầy đủ trạng thái cần lưu; nếu chỉ thay price, partial update thường phù hợp hơn.

### 3.2. Conditional delete

Có thể ngăn xóa một document đã bị thay đổi kể từ lần đọc:

~~~http
DELETE products/_doc/p-100?if_seq_no=42&if_primary_term=3
~~~

Nếu token đã cũ, Elasticsearch từ chối xóa. Điều này hữu ích khi thao tác xóa phụ thuộc vào trạng thái mà người dùng hoặc service đã xem trước đó.

## 4. Lấy concurrency token trong Search API

Nếu ứng dụng đọc document bằng GET theo ID, response có _seq_no và _primary_term. Khi đọc qua Search API, có thể yêu cầu Elasticsearch trả hai metadata này cho từng hit bằng seq_no_primary_term:

~~~http
GET products/_search
{
  "seq_no_primary_term": true,
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

Mỗi hit có thể chứa:

~~~json
{
  "_id": "p-100",
  "_seq_no": 42,
  "_primary_term": 3,
  "_source": {
    "name": "Wireless Keyboard"
  }
}
~~~

Nếu UI hoặc service cần gửi lại token cho thao tác cập nhật, hãy đưa nó qua một DTO có tên rõ ràng, ví dụ seqNo và primaryTerm. Không lấy _version rồi truyền nhầm vào if_seq_no.

## 5. Dùng @Version trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ optimistic locking cho entity thông qua annotation org.springframework.data.annotation.Version.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Version
    private Long version;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long price;

    public Product() {
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public Long getPrice() {
        return price;
    }

    public void setPrice(Long price) {
        this.price = price;
    }
}
~~~

Khi entity được lưu lần đầu, Spring Data/Elasticsearch quản lý version. Sau khi lưu thành công, hãy dùng entity trả về từ save để giữ metadata mới:

~~~java
Product saved = repository.save(product);
Long currentVersion = saved.getVersion();
~~~

Ở lần lưu tiếp theo, version trong entity được dùng để phát hiện thay đổi đồng thời. Nếu một writer khác đã lưu document sau khi entity được đọc, thao tác save với version cũ sẽ thất bại thay vì ghi đè thay đổi mới.

### 5.1. Vì sao nên dùng Long thay vì long?

Dùng kiểu wrapper Long giúp biểu diễn trạng thái chưa có version bằng null. Primitive long luôn có giá trị mặc định 0, dễ làm mờ khác biệt giữa entity mới và entity đã có version nếu code tự khởi tạo hoặc gán giá trị.

Không tự tăng version trong setter hoặc tự gán version dựa trên thời gian. Version do cơ chế lưu trữ quản lý.

### 5.2. Repository save và optimistic locking

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Service có thể lưu entity:

~~~java
Product product = repository.findById("p-100").orElseThrow();
product.setPrice(1399000L);

Product saved = repository.save(product);
~~~

Nếu không có writer khác thay đổi document kể từ lúc đọc, save thành công. Nếu version đã cũ, Spring Data chuyển lỗi concurrency từ Elasticsearch thành exception thuộc hệ thống exception của Spring, thường là OptimisticLockingFailureException.

### 5.3. @Version không tự giải quyết mọi thao tác

@Version là metadata cho entity persistence. Không nên giả định mọi custom query, Painless script, UpdateQuery hoặc bulk request tự động dùng version property của entity.

Khi dùng các API update cấp thấp, hãy kiểm tra request thực tế và truyền concurrency condition tương ứng, chẳng hạn if_seq_no/if_primary_term hoặc cơ chế version guard trong script. Entity có @Version không làm một bulk request nhiều document trở thành transaction.

## 6. Xử lý OptimisticLockingFailureException

Khi Spring Data phát hiện version cũ, ứng dụng có thể bắt OptimisticLockingFailureException:

~~~java
import org.springframework.dao.OptimisticLockingFailureException;

public Product changePrice(String productId, long newPrice) {
    Product product = repository.findById(productId).orElseThrow();
    product.setPrice(newPrice);

    try {
        return repository.save(product);
    } catch (OptimisticLockingFailureException exception) {
        throw new ProductChangedConcurrentlyException(
                "Product was changed by another request: " + productId,
                exception);
    }
}
~~~

Có hai cách phản hồi tùy nghiệp vụ:

- Báo conflict cho caller và yêu cầu tải lại dữ liệu.
- Tự đọc trạng thái mới, hợp nhất thay đổi và thử lại nếu thao tác có thể được tính lại an toàn.

Không nên bắt exception rồi trả về entity cũ như thể update thành công.

### 6.1. Retry phải đọc lại dữ liệu

Một cách xử lý retry:

~~~java
public Product changePriceWithRetry(String productId, long newPrice) {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Product product = repository.findById(productId).orElseThrow();
        product.setPrice(newPrice);

        try {
            return repository.save(product);
        } catch (OptimisticLockingFailureException exception) {
            if (attempt == maxAttempts) {
                throw exception;
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

Ví dụ này minh họa việc đọc entity mới trong mỗi lần thử. Trong hệ thống thực tế, thêm backoff/jitter và giới hạn thời gian retry. Quan trọng hơn, xác định việc áp dụng lại thay đổi có đúng nghiệp vụ hay không.

Nếu thao tác là “đặt price thành 1.399.000”, đọc lại rồi gán cùng giá mới thường có thể tính lại. Nếu thao tác là “giảm stock đi 2”, phải bảo đảm không áp dụng cùng một yêu cầu hai lần khi client retry sau timeout.

### 6.2. Khi nào không nên tự retry?

Không tự retry nếu:

- Người dùng cần xác nhận vì thay đổi mới làm thay đổi quyết định nghiệp vụ.
- Hai writer sửa cùng một field theo quy tắc không thể tự hợp nhất.
- Update phụ thuộc một trạng thái cũ, ví dụ chuyển order từ PAID sang CANCELLED trong khi writer khác đã SHIPPED.
- Lỗi thực tế là mapping/parsing/authentication chứ không phải conflict tạm thời.

Trong các trường hợp đó, trả conflict cho tầng nghiệp vụ để xử lý rõ ràng.

## 7. Cập nhật bằng UpdateQuery và if_seq_no/if_primary_term

Khi dùng ElasticsearchOperations thay vì repository save, có thể gắn concurrency token vào UpdateQuery:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public void updatePrice(
        ElasticsearchOperations operations,
        String productId,
        long expectedSeqNo,
        long expectedPrimaryTerm,
        long newPrice) {

    UpdateQuery update = UpdateQuery.builder(productId)
            .withDocument(Document.from(Map.of(
                    "price", newPrice)))
            .withIfSeqNo(expectedSeqNo)
            .withIfPrimaryTerm(expectedPrimaryTerm)
            .build();

    operations.update(
            update,
            IndexCoordinates.of("products"));
}
~~~

expectedSeqNo và expectedPrimaryTerm phải lấy từ cùng một lần đọc document. Nếu một writer khác thay đổi document trước khi update chạy, Elasticsearch từ chối thao tác.

### 7.1. Cập nhật một field và giữ nguyên field khác

Document.from(Map.of("price", newPrice)) tạo partial document. Các field khác không nằm trong payload được giữ nguyên. Đây là cách phù hợp khi chỉ thay một vài field và không muốn ghi lại toàn bộ entity.

### 7.2. Kiểm soát conflict trong script

Nếu muốn thay đổi dựa trên trạng thái hiện tại, có thể dùng Painless script:

~~~java
UpdateQuery update = UpdateQuery.builder(productId)
        .withScript("""
            if (ctx._source.stock >= params.quantity) {
                ctx._source.stock -= params.quantity;
            } else {
                ctx.op = 'noop';
            }
            """)
        .withParams(Map.of("quantity", 2))
        .withIfSeqNo(expectedSeqNo)
        .withIfPrimaryTerm(expectedPrimaryTerm)
        .build();
~~~

Nếu token cũ, update bị conflict trước khi áp dụng thay đổi. Nếu token còn đúng, script kiểm tra stock rồi giảm số lượng hoặc trả noop. Cần xác định rõ noop có nghĩa gì trong nghiệp vụ và response.

Không nên coi script là transaction với document khác. Nó chỉ kiểm soát một document trong một update operation.

## 8. retry_on_conflict của Update API

Update API có tham số retry_on_conflict. Khi update bị conflict do một writer khác ghi cùng document, Elasticsearch có thể đọc lại source mới và thử áp dụng update thêm một số lần.

REST API:

~~~http
POST products/_update/p-100?retry_on_conflict=3
{
  "doc": {
    "price": 1399000
  }
}
~~~

Bulk API biểu diễn tùy chọn này trong metadata action:

~~~http
POST products/_bulk
{"update":{"_index":"products","_id":"p-100","retry_on_conflict":3}}
{"doc":{"price":1399000}}
~~~

Với Spring Data UpdateQuery:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of(
                "price", 1399000L)))
        .withRetryOnConflict(3)
        .build();
~~~

retry_on_conflict hữu ích khi update có thể được áp dụng lại trên source mới và ứng dụng không cần tự đọc/merge từng conflict. Đây không phải cơ chế đảm bảo thành công; nếu hết số lần retry mà vẫn conflict, thao tác vẫn thất bại.

### 8.1. retry_on_conflict khác if_seq_no/if_primary_term thế nào?

| Cơ chế | Hành vi | Khi phù hợp |
|---|---|---|
| if_seq_no + if_primary_term | Chỉ ghi nếu document vẫn đúng phiên bản đã đọc | Cần bảo vệ một quyết định dựa trên snapshot cụ thể |
| retry_on_conflict | Elasticsearch tự thử lại update sau conflict | Update có thể được tính lại trên source mới |
| Spring Data @Version | Kiểm tra version của entity khi save | Entity persistence qua repository/operations |
| External versioning | So sánh version do nguồn bên ngoài gửi | Đồng bộ projection từ database/event có version tăng dần |

Không dùng retry_on_conflict để che giấu xung đột nghiệp vụ. Nếu thay đổi mới làm cho yêu cầu cũ không còn hợp lệ, cần trả conflict và yêu cầu caller quyết định.

### 8.2. Lưu ý khi kết hợp retry và script

Script được chạy lại trên source mới khi Elasticsearch retry do version conflict. Vì vậy, script phải được thiết kế với semantics mong muốn.

Một script cộng dồn:

~~~text
ctx._source.stock += params.delta
~~~

có thể đúng nếu mỗi update request chỉ được xử lý một lần thành công và retry nội bộ chỉ thay thế lần thử conflict chưa commit. Nhưng nếu ứng dụng gửi lại toàn bộ request sau timeout hoặc message broker phát lại event, delta có thể được cộng lần thứ hai. Hai loại retry này khác nhau.

Với event-driven counter, hãy dùng event ID/deduplication hoặc lưu version đã áp dụng. Với dữ liệu trạng thái cuối, gán giá trị tuyệt đối thường dễ retry an toàn hơn.

## 9. External versioning cho đồng bộ từ hệ thống nguồn

Một hệ thống có thể có version nghiệp vụ riêng. Ví dụ database tăng sellerVersion mỗi khi seller thay đổi:

~~~json
{
  "sellerId": "seller-7",
  "name": "North Star Retail",
  "version": 18
}
~~~

Khi index projection vào Elasticsearch, có thể dùng external versioning để từ chối event cũ:

~~~http
PUT sellers/_doc/seller-7?version=18&version_type=external
{
  "sellerId": "seller-7",
  "name": "North Star Retail"
}
~~~

Với version_type=external, Elasticsearch chỉ chấp nhận ghi khi version bên ngoài lớn hơn version đang lưu. Nếu event version 17 đến sau version 18, request bị conflict và không ghi đè trạng thái mới.

### 9.1. external_gte

version_type=external_gte cho phép version gửi lên bằng hoặc lớn hơn version hiện tại:

~~~http
PUT sellers/_doc/seller-7?version=18&version_type=external_gte
{
  "sellerId": "seller-7",
  "name": "North Star Retail"
}
~~~

Điều này hỗ trợ replay cùng một version. Tuy nhiên, chỉ dùng khi mọi payload cùng version đại diện cho cùng một trạng thái. Nếu hai payload khác nhau có cùng version, request đến sau có thể ghi đè payload trước dù version không tăng.

### 9.2. External version và _version không phải cùng một nguồn

Khi dùng external versioning, giá trị version đến từ database hoặc event producer. Nó không phải version tự tăng mặc định của Elasticsearch. Không lấy một giá trị _version nội bộ rồi giả định nó tương đương aggregateVersion của database.

### 9.3. Bulk index với external version

Bulk action index có thể truyền version và version_type trong metadata:

~~~http
POST _bulk
{"index":{"_index":"sellers","_id":"seller-7","version":18,"version_type":"external"}}
{"sellerId":"seller-7","name":"North Star Retail"}
~~~

Khi event cũ đến sau, item đó thất bại với conflict. Bulk response vẫn có thể có các item khác thành công; cần kiểm tra từng item.

Với partial update, external versioning không phải lúc nào cũng là lựa chọn trực tiếp tương đương index action. Dùng if_seq_no/if_primary_term hoặc script so sánh business version trong _source nếu cần điều khiển update một phần.

### 9.4. Khi nào dùng external versioning?

Phù hợp khi:

- Database nguồn cấp một version tăng đơn điệu cho từng aggregate.
- Event có thể đến trùng hoặc sai thứ tự.
- Projection Elasticsearch có thể được index lại bằng trạng thái mới nhất.
- Mỗi version xác định một trạng thái document đầy đủ.

Không phù hợp nếu nguồn không có version ổn định hoặc nhiều producer tạo version không có thứ tự thống nhất.

## 10. Bulk write và version conflict

Bulk API cho phép gửi concurrency metadata cho từng action. Ví dụ index action với if_seq_no/if_primary_term:

~~~http
POST _bulk
{"index":{"_index":"products","_id":"p-100","if_seq_no":42,"if_primary_term":3}}
{"name":"Wireless Keyboard","price":1399000}
{"delete":{"_index":"products","_id":"p-101","if_seq_no":17,"if_primary_term":2}}
~~~

Nếu token của một item đã cũ, item đó thất bại với 409. Các item khác vẫn có thể thành công.

### 10.1. Kiểm tra lỗi từng item

Bulk response có thể có:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p-100",
        "status": 200,
        "result": "updated"
      }
    },
    {
      "delete": {
        "_id": "p-101",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "if_seq_no and if_primary_term do not match"
        }
      }
    }
  ]
}
~~~

HTTP status của bulk request không đủ để kết luận mọi item thành công. Hãy kiểm tra errors và từng phần tử trong items.

### 10.2. Spring Data BulkFailureException

bulkIndex và bulkUpdate trong Spring Data có thể ném BulkFailureException khi một hoặc nhiều item thất bại. Exception cung cấp thông tin document lỗi qua getFailedDocuments(), bao gồm ID, status và error message trong các phiên bản API hiện hành.

~~~java
try {
    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        if (failure.status() == 409) {
            log.info("Concurrent update for product {}", id);
        } else {
            log.error(
                    "Update failed for {}: {}",
                    id,
                    failure.errorMessage());
        }
    });

    throw exception;
}
~~~

Không retry toàn bộ batch chỉ vì một item có version conflict. Những item đã thành công không cần chạy lại. Với item conflict, đọc lại document và xử lý theo quy tắc nghiệp vụ.

### 10.3. Giữ correlation với input

Trong batch có thể có nhiều loại lỗi. Nên giữ map từ document ID hoặc operation ID về event/command gốc để:

- Biết field nào được yêu cầu thay đổi.
- Biết version mong đợi.
- Xác định lỗi conflict hay mapping.
- Retry đúng item.
- Gửi item không thể xử lý sang DLQ.

Không chỉ log exception tổng quát rồi bỏ batch.

## 11. Version conflict trong Update By Query

Update By Query tìm document bằng query, sau đó cập nhật từng document theo version đã đọc. Nếu document bị writer khác thay đổi trước khi update được áp dụng, thao tác có thể gặp version conflict.

Mặc định, update-by-query có thể dừng khi gặp conflict. Có thể yêu cầu tiếp tục các document khác:

~~~http
POST products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "script": {
    "source": "ctx._source.active = params.active",
    "params": {
      "active": false
    }
  }
}
~~~

conflicts=proceed chỉ cho phép job tiếp tục; nó không giải quyết các document conflict. Response có version_conflicts để ứng dụng biết số trường hợp bị bỏ qua. Nếu tất cả document phải được cập nhật, cần chạy lại phần conflict hoặc đối soát.

Với Spring Data UpdateQuery dùng query selection, có thể cấu hình withAbortOnVersionConflict(false). Đọc ByQueryResponse.getVersionConflicts() và getFailures() để biết kết quả.

## 12. Phân biệt version conflict với các lỗi khác

HTTP 409 thường xuất hiện trong một số tình huống conflict nhưng không phải mọi 409 đều có cùng ý nghĩa:

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| OCC conflict | seq_no/primary_term hoặc version không còn khớp | Đọc lại, merge hoặc bỏ thao tác cũ |
| Create conflict | ID đã tồn tại | Kiểm tra duplicate; không tự ghi đè |
| External version conflict | Version gửi lên cũ hơn hoặc không thỏa điều kiện | Bỏ event cũ hoặc lấy trạng thái mới |
| Mapping/parsing error | Dữ liệu không phù hợp mapping | Sửa payload/schema; không retry nguyên dữ liệu |
| 429 rejected execution | Cluster quá tải | Backoff, giảm concurrency |
| 5xx/service unavailable | Lỗi tạm thời hoặc hạ tầng | Retry có giới hạn và kiểm tra trạng thái ghi |

Không retry mọi lỗi 409 giống nhau. Ví dụ create conflict có thể có nghĩa document đã được tạo bởi lần chạy trước; trong một import idempotent, có thể xác minh payload rồi xem như đã hoàn tất. Nhưng nếu yêu cầu là tạo mới duy nhất, phải báo duplicate.

## 13. Thiết kế retry đúng cách

Một chiến lược retry cần xác định:

1. Loại lỗi nào được retry.
2. Có cần đọc lại document không.
3. Có cần tính lại nghiệp vụ không.
4. Số lần retry tối đa.
5. Backoff và jitter.
6. Cách xử lý khi hết retry.
7. Cách bảo đảm cùng một command không bị áp dụng hai lần.

### 13.1. Retry OCC conflict

Với if_seq_no/if_primary_term, token cũ không thể dùng lại. Retry phải:

- Đọc document mới.
- Kiểm tra điều kiện nghiệp vụ trên trạng thái mới.
- Tính lại thay đổi.
- Gửi update với token mới.

Nếu nghiệp vụ không cho phép tự hợp nhất, trả conflict cho caller.

### 13.2. Exponential backoff

Khi nhiều writer tranh chấp cùng document, retry ngay lập tức có thể tạo một vòng conflict mới. Dùng backoff có jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + randomJitter
~~~

Ví dụ delay cơ sở:

| Lần thử | Delay |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |

Đây là giá trị minh họa. Hãy giới hạn tổng thời gian retry và theo dõi tỷ lệ conflict để phát hiện hotspot.

### 13.3. Idempotency khi client timeout

Một trường hợp khó là client gửi update, Elasticsearch đã ghi thành công nhưng response bị mất do timeout. Client không biết request đã commit hay chưa.

Nếu client gửi lại một phép cộng/trừ, dữ liệu có thể bị thay đổi hai lần. Với command không idempotent, cần event ID/deduplication, sequence/version nghiệp vụ hoặc thiết kế operation có thể xác định trạng thái cuối.

Gán field thành một giá trị xác định thường dễ retry hơn:

~~~json
{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

So với script tăng counter:

~~~text
ctx._source.orderCount += 1
~~~

Script delta cần cơ chế chống duplicate riêng.

## 14. Version conflict không giải quyết nhất quán nhiều document

OCC bảo vệ một document tại thời điểm ghi. Nó không tạo transaction giữa nhiều document hoặc nhiều index.

Ví dụ thay đổi sellerName cần cập nhật:

- seller document.
- 500 listing documents.
- recommendation documents.

Mỗi document có version riêng. Một số update có thể thành công trong khi một số khác conflict. Không có rollback tự động cho các document đã thành công.

Với projection phân tán, cần kết hợp:

- Event có aggregate version.
- Idempotent update.
- Retry riêng item conflict.
- Dead-letter queue cho lỗi lâu dài.
- Reconciliation để tìm projection bị stale.
- Rebuild index từ source of truth khi cần.

Nếu nguồn chuẩn là database quan hệ, transactional outbox hoặc CDC giúp không mất event giữa lúc commit dữ liệu nguồn và publish message. Elasticsearch vẫn được cập nhật theo eventual consistency.

## 15. Kết hợp @Version với nhiều writer

Giả sử hai service cùng đọc Product có version 7:

~~~text
Service A đọc Product version 7
Service B đọc Product version 7

Service A đổi price và save -> thành công, version 8
Service B đổi name và save -> conflict vì version 7 đã cũ
~~~

Ngay cả khi A và B sửa hai field khác nhau, @Version vẫn có thể từ chối toàn bộ save của B vì entity được lưu như một đơn vị versioned. Đây là hành vi bảo vệ lost update.

Sau conflict, service B có thể đọc lại version 8, áp dụng thay đổi name lên entity mới rồi save version tiếp theo. Như vậy, thay đổi price của A được giữ lại.

Nếu các service thực sự sở hữu field độc lập và cần cập nhật song song, có thể cân nhắc partial update theo field hoặc tách projection/ownership rõ ràng. Tuy nhiên, phải thiết kế để các thao tác không ghi đè nhau và không vi phạm invariant nghiệp vụ.

## 16. Xóa document có kiểm soát phiên bản

Xóa cũng có thể race với update:

1. Service A đọc document và quyết định xóa.
2. Service B cập nhật document.
3. Service A gửi delete theo token cũ.

Nếu dùng if_seq_no/if_primary_term, delete chỉ thành công khi document vẫn ở phiên bản đã đọc. Nếu document thay đổi, delete bị conflict và ứng dụng có thể đánh giá lại quyết định.

~~~http
DELETE products/_doc/p-100?if_seq_no=42&if_primary_term=3
~~~

Với bulk delete, metadata của từng action có thể mang if_seq_no và if_primary_term:

~~~http
POST _bulk
{"delete":{"_index":"products","_id":"p-100","if_seq_no":42,"if_primary_term":3}}
~~~

Không nhầm version conflict với document missing. Nếu document đã bị xóa bởi writer khác, response có thể thể hiện not found thay vì conflict tùy trạng thái và API.

## 17. Quan sát và chẩn đoán version conflict

Khi conflict xuất hiện thường xuyên, cần xác định:

- Document ID nào có tỷ lệ conflict cao.
- Index và shard chứa document đó.
- Service hoặc worker nào cùng ghi.
- Conflict đến từ @Version, seq_no/primary_term, external version hay create duplicate.
- Retry có thành công không.
- Số lần retry trung bình và tỷ lệ hết retry.
- Có một aggregate hoặc tenant tạo hotspot hay không.

Metrics gợi ý:

| Metric | Ý nghĩa |
|---|---|
| optimistic_lock_conflicts_total | Tổng số conflict khi save/update |
| bulk_items_failed_total{status="409"} | Số bulk item conflict |
| update_retry_attempts | Số lần retry nội bộ/ứng dụng |
| update_retry_exhausted_total | Số thao tác hết retry |
| projection_version_lag | Chênh lệch version nguồn và projection |
| conflict_rate_by_index | Tỷ lệ conflict theo index |

Không ghi toàn bộ source hoặc thông tin nhạy cảm vào log chỉ để debug conflict. ID, index, version token, event ID và loại thao tác thường đủ để truy vết.

## 18. Kiểm thử version conflict

Unit test cho logic merge không đủ để xác nhận Elasticsearch thực hiện OCC. Cần integration test với Elasticsearch thật hoặc Testcontainers.

### 18.1. Kiểm thử @Version

Kịch bản:

1. Lưu một Product mới.
2. Đọc cùng document thành hai object A và B.
3. Cập nhật A rồi save thành công.
4. Cập nhật B rồi save.
5. Xác nhận lần save B ném OptimisticLockingFailureException.

Ví dụ:

~~~java
@Test
void staleEntityCannotOverwriteNewerVersion() {
    Product initial = repository.save(
            new Product("p-100", "Keyboard", 1000L));

    Product writerA = repository.findById(initial.getId()).orElseThrow();
    Product writerB = repository.findById(initial.getId()).orElseThrow();

    writerA.setPrice(1200L);
    repository.save(writerA);

    writerB.setName("Old Keyboard");

    assertThatThrownBy(() -> repository.save(writerB))
            .isInstanceOf(OptimisticLockingFailureException.class);
}
~~~

Đây là ví dụ kiểm thử minh họa; constructor, getter/setter và index setup cần khớp entity thực tế.

### 18.2. Kiểm thử if_seq_no/if_primary_term

Kịch bản:

1. GET document, lấy seq_no và primary_term.
2. Ghi một thay đổi khác để token thay đổi.
3. Gửi update với token cũ.
4. Xác nhận request bị 409.
5. GET lại document và xác nhận thay đổi mới vẫn còn.

Test này chứng minh conditional write ngăn stale writer ghi đè dữ liệu.

### 18.3. Kiểm thử retry_on_conflict

Tạo nhiều request đồng thời cập nhật cùng document. Xác nhận update có retry_on_conflict có thể hoàn tất trong số lần retry cho phép, nhưng vẫn kiểm tra trạng thái cuối theo invariant nghiệp vụ.

Không chỉ assert request trả thành công. Với script tăng counter, xác nhận counter đúng với số command duy nhất đã gửi, không phải số lần client retry.

### 18.4. Kiểm thử external versioning

Gửi version 18 trước, sau đó gửi version 17. Xác nhận event version 17 bị conflict và source vẫn giữ trạng thái version 18. Nếu dùng external_gte, thêm test replay version 18 với cùng payload và test bảo đảm producer không phát hai payload khác nhau cho cùng version.

### 18.5. Kiểm thử bulk partial failure

Gửi bulk gồm:

- Một item có token hiện hành.
- Một item có token cũ.
- Một item có mapping error.

Xác nhận item hợp lệ thành công, item conflict được nhận diện riêng, mapping error không bị retry mù và batch có thể được phục hồi mà không chạy lại các action không idempotent.

## 19. Quy trình xử lý conflict trong service

Khi một thao tác ghi bị conflict, service có thể thực hiện:

1. Xác định cơ chế gây conflict: @Version, seq_no/primary_term, external version hay create duplicate.
2. Xác định thay đổi nghiệp vụ có thể tự hợp nhất hay cần caller quyết định.
3. Nếu tự hợp nhất được, đọc trạng thái mới nhất.
4. Kiểm tra lại invariant nghiệp vụ trên trạng thái mới.
5. Tính lại thay đổi.
6. Gửi update với version/token mới.
7. Giới hạn số lần retry và dùng backoff.
8. Nếu vẫn conflict, trả lỗi rõ ràng hoặc đưa command vào luồng xử lý lại.
9. Với bulk, chỉ retry item thất bại.
10. Ghi metrics và correlation ID để theo dõi.

## 20. Các lỗi thường gặp

### Dùng _version thay cho _seq_no

_version và _seq_no là hai metadata khác nhau. if_seq_no phải nhận sequence number, đồng thời cần if_primary_term lấy từ cùng response.

### Chỉ lưu seq_no mà quên primary_term

Hai giá trị tạo thành một concurrency token. Không tự tạo hoặc ghép seq_no từ lần đọc này với primary_term từ lần đọc khác.

### Retry cùng token sau 409

Token đã cũ vẫn cũ. Phải đọc lại document và lấy token mới nếu muốn thử lại.

### Bắt conflict rồi save lại entity cũ

Entity cũ vẫn mang version cũ. Đọc lại entity mới, hợp nhất thay đổi và lưu phiên bản mới.

### Dùng @Version nhưng nghĩ mọi custom update tự được bảo vệ

UpdateQuery, script và native bulk có thể cần điều kiện concurrency riêng. Kiểm tra request và dùng if_seq_no/if_primary_term hoặc version guard phù hợp.

### Dùng retry_on_conflict cho xung đột nghiệp vụ

Elasticsearch chỉ có thể thử lại update kỹ thuật. Nếu trạng thái mới khiến yêu cầu không còn hợp lệ, ứng dụng phải quyết định.

### Retry mọi lỗi 409

Create duplicate, external version conflict và OCC conflict có ý nghĩa khác nhau. Phân loại error type trước khi retry.

### Dùng external_gte với payload không xác định

Hai payload khác nhau cùng version có thể ghi đè nhau. Chỉ dùng external_gte khi một version xác định duy nhất một trạng thái.

### Coi bulk là transaction

Item conflict không rollback item đã thành công. Kiểm tra từng item và retry chọn lọc.

### Bỏ qua version conflict trong update-by-query

conflicts=proceed chỉ tiếp tục job. Các document conflict vẫn chưa được cập nhật và cần đối soát.

### Dùng OCC để mong đợi transaction nhiều document

OCC bảo vệ từng document. Muốn projection nhiều document hội tụ, cần event, retry, idempotency và reconciliation.

## 21. Chọn cơ chế nào?

| Tình huống | Cơ chế phù hợp |
|---|---|
| Lưu entity qua Repository/ElasticsearchOperations và muốn phát hiện entity cũ | @Version |
| Đọc document, chỉnh sửa rồi chỉ ghi nếu chưa ai thay đổi | if_seq_no + if_primary_term |
| Update script có thể áp dụng lại trên source mới | retry_on_conflict |
| Đồng bộ snapshot có business version từ database | External versioning |
| Nhiều item trong bulk có concurrency token riêng | if_seq_no/if_primary_term theo từng action |
| Update-by-query gặp conflict và cần tiếp tục các item khác | conflicts=proceed, sau đó đối soát |
| Thay đổi nhiều document/index cần eventual consistency | Event/outbox, idempotency, retry và reconciliation |

Không có một cơ chế duy nhất phù hợp mọi trường hợp. Chọn theo nguồn version, kiểu update, mức độ tự động merge được và yêu cầu nghiệp vụ.

## 22. Tổng kết

Version conflict xảy ra khi một writer cố ghi dựa trên trạng thái cũ trong khi document đã được writer khác thay đổi. Elasticsearch có internal _version và optimistic concurrency token _seq_no/_primary_term. Conditional write với if_seq_no và if_primary_term chỉ thành công nếu document vẫn ở đúng trạng thái đã đọc. Spring Data Elasticsearch hỗ trợ version-based optimistic locking cho entity qua @Version và có thể báo OptimisticLockingFailureException khi entity đã stale.

Update API có retry_on_conflict để thử lại update sau conflict kỹ thuật. Cơ chế này phù hợp khi update có thể được áp dụng lại trên source mới; nó không thay thế quyết định nghiệp vụ và không giải quyết duplicate request từ client. External versioning phù hợp khi nguồn dữ liệu cung cấp version tăng dần, giúp từ chối event cũ. Bulk và update-by-query vẫn có thể thất bại một phần, vì vậy phải kiểm tra từng item hoặc ByQueryResponse.

Khi gặp conflict, không ghi lại entity cũ hoặc retry cùng token. Hãy đọc trạng thái mới, kiểm tra invariant, hợp nhất thay đổi nếu được phép và giới hạn retry. Với dữ liệu lặp trên nhiều document, OCC chỉ bảo vệ từng document; cần thêm outbox/CDC, event version, idempotency, retry và reconciliation để các projection hội tụ.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Object Mapping and Versioning](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Elasticsearch Operations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch – BulkFailureException API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.html)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
