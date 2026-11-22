# Quản lý tài nguyên tìm kiếm và chuyển đổi ngoại lệ

Spring Data Elasticsearch cung cấp nhiều API để làm việc với Elasticsearch ngoài các phương thức CRUD của repository. Ứng dụng có thể tạo index, ghi mapping, cập nhật settings, quản lý alias, lưu search template, thực hiện truy vấn và xử lý vòng đời các tài nguyên tìm kiếm. Khi những thao tác này gặp lỗi, Spring Data còn có cơ chế chuyển một số exception đặc thù của Elasticsearch sang hệ thống exception thống nhất của Spring.

Hai nhóm khả năng này giúp ứng dụng quản lý Elasticsearch có cấu trúc hơn:

- Các thao tác quản lý index và truy vấn được gom qua **ElasticsearchOperations**, **IndexOperations** và các interface liên quan.
- Các lỗi từ tầng persistence có thể được chuyển thành **DataAccessException** để service xử lý theo abstraction của Spring.

Bài học tập trung vào cách chọn đúng interface, quản lý vòng đời tài nguyên, sử dụng stored search template và hiểu giới hạn của exception translation.

## 1. Phân biệt các nhóm Operations

Spring Data Elasticsearch tổ chức API theo nhóm chức năng tương ứng với Elasticsearch API:

| Interface | Trách nhiệm |
| --- | --- |
| IndexOperations | Quản lý index ở cấp tài nguyên: tạo, xóa, kiểm tra tồn tại, settings, mapping, alias và index template |
| DocumentOperations | Lưu, cập nhật, đọc và xóa document theo ID |
| SearchOperations | Thực hiện tìm kiếm, đếm, multi-search, stream, scroll và Point in Time |
| ScriptOperations | Lưu, đọc và xóa stored script/search template |
| ElasticsearchOperations | API cấp cao kết hợp document và search operations, đồng thời cung cấp helper để lấy IndexOperations |

ElasticsearchOperations không phải một repository. Nó là abstraction cấp thấp hơn repository, phù hợp khi cần truy vấn linh hoạt, quản lý index hoặc thao tác không được biểu diễn tự nhiên bằng query method.

### 1.1. Inject ElasticsearchOperations

Spring Boot cùng starter Spring Data Elasticsearch thường cấu hình bean ElasticsearchOperations để ứng dụng sử dụng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Constructor injection giúp thể hiện rõ service phụ thuộc vào API persistence/search. Không nên tự tạo client trong từng service nếu ứng dụng đã có client được Spring quản lý.

### 1.2. Lấy IndexOperations theo entity hoặc tên index

Có hai cách lấy đối tượng quản lý index:

~~~java
IndexOperations byEntity = operations.indexOps(ProductDocument.class);

IndexOperations byIndexName =
    operations.indexOps(IndexCoordinates.of("catalog-products-v2"));
~~~

indexOps(ProductDocument.class) sử dụng metadata của entity, chẳng hạn tên index trong @Document. indexOps(IndexCoordinates) làm việc với tên index hoặc tập index được chỉ định rõ. Cách thứ hai hữu ích khi quản lý index vật lý có version, alias hoặc tài nguyên không gắn trực tiếp với một entity.

## 2. Quản lý vòng đời index bằng IndexOperations

Index là tài nguyên cấp cao chứa mapping, settings và các document. Tạo index và thay đổi mapping cần được quản lý có chủ đích, đặc biệt trong môi trường staging và production.

### 2.1. Kiểm tra và tạo index

Giả sử entity được khai báo:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters và setters
}
~~~

Có thể tạo index cùng mapping được sinh từ annotation:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

createWithMapping() tạo index và mapping tương ứng với metadata của entity. Nếu cần tách riêng hai bước, có thể gọi create() rồi putMapping(). Với cấu hình settings và mapping tường minh, IndexOperations cũng cung cấp các phương thức tạo index nhận settings và mapping.

Lưu ý: lấy được IndexOperations hoặc ElasticsearchOperations không có nghĩa index tự được tạo. Khi dùng các API này trực tiếp, ứng dụng phải gọi thao tác tạo index. Spring Data repository có cơ chế tự tạo index/mapping theo cấu hình document, nhưng đó là hành vi bootstrap riêng của repository.

### 2.2. Đọc mapping và settings

Sau khi tạo index, có thể đọc lại cấu hình thực tế:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

Document mapping = indexOperations.getMapping();
Document settings = indexOperations.getSettings();
~~~

Mapping mô tả cách Elasticsearch hiểu từng field: kiểu dữ liệu, analyzer, multi-fields, object/nested và dynamic behavior. Settings mô tả cấu hình index như shard, replica, refresh interval và các tùy chọn lưu trữ.

Không nên xem annotation hoặc file JSON trong mã nguồn là bằng chứng duy nhất về cấu hình đang chạy. Index có thể đã được tạo từ trước, được quản lý bằng template hoặc được cập nhật trực tiếp trên cluster. Đọc mapping/settings từ Elasticsearch giúp xác nhận trạng thái thực tế.

### 2.3. Ghi mapping

Nếu index đã tồn tại và cần bổ sung mapping field tương thích, có thể dùng:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

indexOperations.putMapping();
~~~

Hoặc tạo mapping từ một class khác:

~~~java
Document mapping =
    operations.indexOps(ProductDocument.class).createMapping();

operations.indexOps(IndexCoordinates.of("catalog-products"))
    .putMapping(mapping);
~~~

Việc cập nhật mapping có giới hạn của Elasticsearch. Có thể thêm field mới hoặc bổ sung một số thuộc tính được hỗ trợ, nhưng không thể tùy ý đổi kiểu của field đã được lập chỉ mục. Nếu cần thay đổi không tương thích, thường phải tạo index mới và reindex dữ liệu.

### 2.4. Xóa index

IndexOperations cung cấp thao tác xóa index:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("catalog-products-test"));

if (indexOperations.exists()) {
    indexOperations.delete();
}
~~~

Xóa index làm mất document và cấu hình thuộc index đó. Chỉ dùng thao tác này với tài nguyên đã xác định rõ, chẳng hạn index test hoặc index cũ sau khi hoàn tất migration. Không dùng tên index lấy trực tiếp từ request người dùng để gọi delete.

## 3. Quản lý alias và index version

Alias là tên logic trỏ tới một hoặc nhiều index. Ứng dụng có thể sử dụng alias ổn định trong khi đội vận hành tạo index vật lý mới theo version.

~~~text
catalog-products  (alias)
        |
        v
catalog-products-v2  (index vật lý hiện tại)
~~~

Khi cần đổi schema, có thể tạo catalog-products-v3, nạp dữ liệu, kiểm tra rồi chuyển alias. Ứng dụng tiếp tục dùng alias catalog-products, nên không cần thay tên index trong mọi service.

### 3.1. Tạo alias

Có thể quản lý alias qua IndexOperations và API alias actions của Spring Data. Elasticsearch REST API minh họa việc gắn alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "catalog-products-v2",
        "alias": "catalog-products",
        "is_write_index": true
      }
    }
  ]
}
~~~

is_write_index chỉ rõ index nhận thao tác ghi khi alias trỏ tới nhiều index. Nếu alias chỉ trỏ tới một index, cần thống nhất quy tắc read/write trong thiết kế ứng dụng.

### 3.2. Chuyển alias nguyên tử

Khi index mới đã sẵn sàng, có thể xóa liên kết cũ và thêm liên kết mới trong cùng một aliases request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "catalog-products-v2",
        "alias": "catalog-products"
      }
    },
    {
      "add": {
        "index": "catalog-products-v3",
        "alias": "catalog-products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Việc chuyển alias trong một request giúp tránh khoảng thời gian ứng dụng tham chiếu tới một alias không tồn tại giữa hai thao tác riêng lẻ. Trước khi chuyển, cần kiểm tra document count, mapping, truy vấn và chính sách đồng bộ dữ liệu mới phát sinh trong thời gian migration.

### 3.3. Khi nào dùng alias?

- Giữ tên index ổn định trong mã ứng dụng.
- Chuyển traffic đọc/ghi sang index mới sau reindex.
- Tách read alias và write alias khi cần quy trình triển khai rõ ràng.
- Hỗ trợ rollover hoặc quản lý nhiều index theo thời gian.

Alias không phải bản sao dữ liệu. Nó chỉ là tên tham chiếu tới index. Xóa alias không đồng nghĩa xóa index, còn xóa index sẽ làm alias trỏ tới index đó mất hiệu lực.

## 4. Index templates và stored search templates

Hai loại template có mục tiêu khác nhau:

| Loại template | Công dụng |
| --- | --- |
| Index template | Áp dụng settings, mappings và aliases cho index mới có tên khớp pattern |
| Search template | Lưu một truy vấn tìm kiếm có tham số để tái sử dụng |

Không nên nhầm search template với index template chỉ vì cả hai cùng có tên template.

### 4.1. Index template

Index template giúp chuẩn hóa cấu hình cho index mới. Ví dụ:

~~~http
PUT /_index_template/catalog-template
{
  "index_patterns": ["catalog-products-*"],
  "priority": 100,
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "1s"
    },
    "mappings": {
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "name": {
          "type": "text"
        }
      }
    }
  }
}
~~~

Template được áp dụng khi tạo index mới khớp với index_patterns. Thay đổi template không tự cập nhật index đã tồn tại. Các index hiện hữu cần được cập nhật bằng API tương ứng hoặc quy trình migration.

Spring Data Elasticsearch cung cấp các API index template qua IndexOperations ở những phiên bản tương ứng. Khi cần tính năng mới của composable/component template mà abstraction chưa bao phủ, có thể dùng Elasticsearch Java API Client trực tiếp ở một adapter hạ tầng.

### 4.2. Stored search template

Search template lưu query DSL dạng Mustache script trong cluster. Spring Data cung cấp ScriptOperations thông qua ElasticsearchOperations.

Ví dụ lưu template:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.script.Script;

Script script = Script.builder()
    .withId("products-by-name")
    .withLanguage("mustache")
    .withSource("""
        {
          "query": {
            "match": {
              "name": "{{name}}"
            }
          },
          "from": "{{from}}",
          "size": "{{size}}"
        }
        """)
    .build();

operations.putScript(script);
~~~

Các placeholder như {{name}}, {{from}} và {{size}} được thay bằng tham số khi thực thi. Search template script dùng ngôn ngữ Mustache.

Có thể đọc hoặc xóa stored script bằng các phương thức tương ứng:

~~~java
operations.getScript("products-by-name");
operations.deleteScript("products-by-name");
~~~

Việc xóa script có thể làm hỏng các luồng tìm kiếm còn tham chiếu tới ID đó. Cần triển khai phiên bản template và ứng dụng theo thứ tự tương thích.

### 4.3. Thực thi SearchTemplateQuery

Tạo query từ stored template:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.SearchTemplateQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchTemplateQuery query = SearchTemplateQuery.builder()
    .withId("products-by-name")
    .withParams(Map.of(
        "name", "mechanical keyboard",
        "from", 0,
        "size", 20
    ))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Search template có ích khi query DSL phức tạp được dùng lại bởi nhiều nơi hoặc muốn quản lý nội dung query ở phía cluster. Tham số đầu vào vẫn phải được xác thực trong ứng dụng.

SearchTemplateQuery không hỗ trợ mọi tùy chọn giống các query thông thường. Ví dụ, Pageable hoặc Sort đặt trên query object có thể không được áp dụng; nếu template cần phân trang hoặc sort, hãy đưa các giá trị đó thành placeholder trong script.

### 4.4. Dùng template trong repository

Ở các phiên bản hỗ trợ, có thể gắn stored template với repository method:

~~~java
import org.springframework.data.elasticsearch.annotations.SearchTemplateQuery;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @SearchTemplateQuery(id = "products-by-name")
    SearchHits<ProductDocument> findByName(String name);
}
~~~

Tham số method được chuyển thành cặp key/value theo tên tham số để truyền vào search template. Kiểm tra cấu hình compiler giữ parameter names và phiên bản Spring Data Elasticsearch trước khi dựa vào cơ chế binding này.

## 5. Quản lý tài nguyên tìm kiếm dài hạn: Scroll và Point in Time

Một truy vấn trả về lượng lớn document có thể cần xử lý theo từng phần. Elasticsearch hỗ trợ Scroll và Point in Time (PIT). Đây là tài nguyên có vòng đời và cần được đóng khi hoàn thành.

### 5.1. Search stream

Spring Data cung cấp searchForStream để đọc kết quả theo từng phần:

~~~java
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.query.Query;

SearchHitsIterator<ProductDocument> stream =
    operations.searchForStream(
        query,
        ProductDocument.class,
        IndexCoordinates.of("catalog-products")
    );

try {
    while (stream.hasNext()) {
        ProductDocument product = stream.next();
        // Xử lý từng document
    }
} finally {
    stream.close();
}
~~~

Đóng stream giải phóng tài nguyên scroll phía client/server. Không nên giữ scroll context lâu hơn cần thiết hoặc mở nhiều stream không được đóng.

### 5.2. Point in Time

PIT tạo một view ổn định của index trong một khoảng thời gian để hỗ trợ phân trang sâu hoặc nhiều truy vấn liên tiếp trên cùng snapshot logic.

Ví dụ mở và đóng PIT:

~~~java
import java.time.Duration;

IndexCoordinates index = IndexCoordinates.of("catalog-products");
String pitId = operations.openPointInTime(
    index,
    Duration.ofMinutes(1)
);

try {
    // Tạo Query có Point In Time và thực hiện các trang tìm kiếm.
} finally {
    operations.closePointInTime(pitId);
}
~~~

Trong quá trình phân trang PIT, Elasticsearch có thể trả về PIT ID mới; hãy tiếp tục dùng ID mới nhất theo response và đóng ID cuối cùng khi hoàn tất. Keep-alive cần đủ cho thời gian xử lý nhưng không nên kéo dài không cần thiết.

Scroll và PIT không thay thế nhau trong mọi trường hợp. Chọn cơ chế theo yêu cầu nhất quán, cách phân trang và phiên bản Elasticsearch.

## 6. Exception translation trong Spring Data Elasticsearch

Elasticsearch client có thể ném exception riêng khi request thất bại. Nếu mọi service phải biết chi tiết exception của client, mã ứng dụng sẽ phụ thuộc chặt vào công nghệ lưu trữ.

Spring Data Elasticsearch cung cấp exception translation để chuyển một số runtime exception sang hệ thống exception của Spring trong package org.springframework.dao.

Mục tiêu là tạo một abstraction chung cho lỗi truy cập dữ liệu, tương tự cách Spring hỗ trợ JDBC, JPA hoặc các module persistence khác.

### 6.1. DataAccessException

DataAccessException là lớp gốc trong hệ thống exception truy cập dữ liệu của Spring. Các lớp con thể hiện nhóm lỗi khác nhau, chẳng hạn lỗi truy cập tài nguyên, lỗi API truy cập dữ liệu hoặc lỗi dữ liệu.

Lợi ích:

- Service không cần phụ thuộc trực tiếp vào mọi exception class của Elasticsearch client.
- Có thể tổ chức xử lý lỗi theo nhóm persistence.
- Giữ nguyên exception gốc làm cause để phục vụ logging và điều tra.
- Có thể chuẩn hóa phản hồi HTTP ở tầng web mà không để lộ chi tiết client.

Exception translation không có nghĩa mọi lỗi runtime đều trở thành DataAccessException. Nếu translator không nhận diện được exception, nó có thể trả về null để báo rằng exception đó không thuộc phạm vi chuyển đổi.

### 6.2. ElasticsearchExceptionTranslator

Với Elasticsearch Java API Client, Spring Data Elasticsearch cung cấp lớp:

~~~java
org.springframework.data.elasticsearch.client.elc.ElasticsearchExceptionTranslator
~~~

Lớp này triển khai PersistenceExceptionTranslator. Phương thức translateExceptionIfPossible(RuntimeException) cố gắng chuyển exception sang DataAccessException. Nếu không có ánh xạ phù hợp, kết quả là null.

Constructor của implementation hiện đại nhận JsonpMapper, vì một số exception từ Java API Client cần mapper để diễn giải nội dung response. API và package translator khác nhau giữa các thế hệ client. Trong các phiên bản mới dùng Java API Client, không nên sao chép ví dụ cũ dựa trên High Level REST Client.

Spring Data Elasticsearch mô tả các implementation Operations mặc định có hỗ trợ resource management và exception translation. Vì vậy, khi dùng ElasticsearchOperations hoặc repository được cấu hình bởi Spring, ứng dụng thường không cần tự gọi translator cho từng thao tác.

### 6.3. Cơ chế PersistenceExceptionTranslator của Spring

Spring định nghĩa interface PersistenceExceptionTranslator để các module persistence cung cấp khả năng chuyển exception đặc thù sang exception chuẩn.

Với các bean DAO được đánh dấu @Repository, PersistenceExceptionTranslationPostProcessor có thể áp dụng advisor để chuyển exception phù hợp khi lời gọi đi qua bean đó. Spring Data cũng tích hợp cơ chế exception translation trong hạ tầng persistence của mình.

Luồng khái quát:

~~~text
Service
   |
   v
Repository / ElasticsearchOperations
   |
   v
Elasticsearch Java API Client
   |
   v
Exception từ client hoặc cluster
   |
   v
ElasticsearchExceptionTranslator
   |
   v
Spring DataAccessException hierarchy
   |
   v
Service / API exception handler
~~~

Nếu ứng dụng gọi trực tiếp client cấp thấp ở ngoài Spring Data, không nên giả định thao tác đó tự động được chuyển exception giống lời gọi repository hoặc template. Có thể cần dùng translator hoặc adapter riêng nếu muốn thống nhất hợp đồng lỗi.

## 7. Nhận diện và xử lý lỗi theo nhóm

Khi thao tác với Elasticsearch, lỗi thường xuất phát từ một trong các nhóm sau:

| Nhóm lỗi | Ví dụ nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Kết nối và tài nguyên | Cluster không truy cập được, timeout, node unavailable | Kiểm tra mạng, endpoint, TLS, credentials, trạng thái cluster; cân nhắc retry có giới hạn |
| Request hoặc query không hợp lệ | Field sai kiểu, query DSL không đúng, tham số thiếu | Sửa query/mapping hoặc validation đầu vào; không retry mù |
| Mapping và schema | Ghi chuỗi vào field số, thay đổi kiểu không tương thích | Kiểm tra mapping và dữ liệu; dùng index migration nếu cần |
| Tài nguyên không tồn tại | Index, alias hoặc stored script không có | Kiểm tra vòng đời tài nguyên và thứ tự triển khai |
| Xung đột dữ liệu | Version conflict hoặc điều kiện ghi không thỏa mãn | Đọc lại trạng thái, áp dụng optimistic concurrency hoặc quy tắc nghiệp vụ |
| Lỗi xác thực/phân quyền | Credentials sai hoặc thiếu privilege | Kiểm tra secret và role/privilege được cấp |

Exception translator giúp chuẩn hóa kiểu exception nhưng không thay thế việc phân loại nguyên nhân. Cùng một DataAccessException có thể cần hành động khác nhau tùy cause, HTTP status, thông tin Elasticsearch và ngữ cảnh nghiệp vụ.

### 7.1. Bảo toàn cause

Khi chuyển exception sang exception nghiệp vụ, nên giữ exception gốc làm cause:

~~~java
public class SearchUnavailableException extends RuntimeException {

    public SearchUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ví dụ service chuyển lỗi truy cập dữ liệu thành lỗi ứng dụng:

~~~java
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchFacade {

    private final ProductSearchService searchService;

    public ProductSearchFacade(ProductSearchService searchService) {
        this.searchService = searchService;
    }

    public SearchResult search(String text) {
        try {
            return searchService.search(text);
        } catch (DataAccessResourceFailureException ex) {
            throw new SearchUnavailableException(
                "Search service is temporarily unavailable",
                ex
            );
        }
    }
}
~~~

Ví dụ trên chỉ minh họa cách giữ cause và chuyển đổi ở ranh giới ứng dụng. Tên exception cụ thể được ném ra phụ thuộc translator và loại lỗi thực tế; không nên giả định mọi lỗi Elasticsearch đều là DataAccessResourceFailureException.

### 7.2. Không bắt mọi exception rồi trả kết quả rỗng

Một anti-pattern thường gặp:

~~~java
try {
    return repository.findBySku(sku);
} catch (Exception ex) {
    return Optional.empty();
}
~~~

Đoạn code này biến lỗi kết nối, lỗi mapping, lỗi lập trình và lỗi truy vấn thành kết quả "không tìm thấy". Người gọi không thể phân biệt sản phẩm không tồn tại với search cluster đang lỗi.

Nên để lỗi không mong đợi được propagate hoặc chuyển sang exception nghiệp vụ phù hợp. Chỉ trả kết quả rỗng khi truy vấn thực sự hoàn tất thành công và không có document phù hợp.

### 7.3. Retry phải có điều kiện

Không phải mọi lỗi truy cập dữ liệu đều có thể retry:

- Timeout hoặc lỗi mạng tạm thời có thể retry với backoff và giới hạn số lần.
- Lỗi validation hoặc query DSL sai sẽ tiếp tục thất bại nếu retry.
- Ghi dữ liệu cần xem xét tính idempotent và điều kiện version trước khi retry.
- Không retry vô hạn vì có thể làm cluster quá tải trong lúc đang phục hồi.

Nếu dùng Spring Retry hoặc cơ chế retry của ứng dụng, hãy cấu hình theo loại lỗi cụ thể, giới hạn attempts, backoff và timeout tổng.

## 8. Chuẩn hóa exception ở tầng API

Tầng web không nên trả stack trace, raw Elasticsearch response hoặc thông tin cluster cho client. Có thể dùng @RestControllerAdvice để chuyển exception ứng dụng thành response nhất quán.

Ví dụ:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(SearchUnavailableException.class)
    public ResponseEntity<ApiError> handleSearchUnavailable(
            SearchUnavailableException ex) {

        ApiError error = new ApiError(
            "SEARCH_UNAVAILABLE",
            "Search is temporarily unavailable"
        );

        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(error);
    }
}
~~~

ApiError là DTO do ứng dụng định nghĩa. Không nên ánh xạ mọi DataAccessException sang HTTP 503. Lỗi query hoặc mapping do ứng dụng gửi sai có thể là lỗi phía server; lỗi dữ liệu không hợp lệ có thể cần response khác; lỗi tài nguyên hoặc cluster tạm thời mới có thể phù hợp với 503.

Log nội bộ có thể lưu exception gốc cùng correlation ID, nhưng response cho client chỉ nên chứa thông tin đủ để xử lý ở tầng giao tiếp.

## 9. Quản lý lỗi khi thao tác tài nguyên

Các thao tác quản lý index và template thường được thực hiện trong startup, migration hoặc deployment. Một số tình huống cần xử lý riêng:

**Index đã tồn tại.** Kiểm tra bằng exists() trước khi tạo, hoặc để migration quản lý trạng thái. Nếu nhiều instance cùng chạy bước tạo, vẫn có thể xảy ra race condition giữa kiểm tra và tạo.

**Mapping không tương thích.** Không cố ghi mapping mới nếu thay đổi yêu cầu đổi kiểu field. Tạo index version mới, reindex và chuyển alias.

**Alias không tồn tại hoặc trỏ sai index.** Kiểm tra aliases API và index đích trước khi chuyển traffic. Giữ bước rollback rõ ràng.

**Search template chưa được lưu.** Triển khai stored script trước khi triển khai code gọi template ID đó. Khi đổi template, có thể dùng ID version mới để rollout an toàn.

**PIT/scroll không được đóng.** Dùng finally hoặc try-with-resources khi API hỗ trợ để giải phóng tài nguyên ngay cả khi xử lý document gặp exception.

**Xóa index thất bại do thiếu quyền.** Kiểm tra role/privilege và quy trình triển khai; không lặp lại thao tác xóa tự động vô hạn.

## 10. Đưa quản lý tài nguyên vào kiến trúc ứng dụng

Không nên để controller trực tiếp tạo index, thay alias hoặc xóa stored script. Những thao tác này thuộc hạ tầng và vòng đời triển khai.

Một cách tổ chức:

~~~text
com.example.catalog
├── product
│   ├── api
│   ├── application
│   └── infrastructure
│       └── elasticsearch
│           ├── ProductRepository.java
│           ├── ProductSearchAdapter.java
│           └── ProductIndexManager.java
├── search
│   ├── application
│   └── infrastructure
│       └── SearchTemplateManager.java
└── shared
    └── error
        ├── SearchUnavailableException.java
        └── ApiExceptionHandler.java
~~~

Trách nhiệm có thể phân chia:

- ProductRepository: CRUD và query method đơn giản.
- ProductSearchAdapter: truy vấn phức tạp bằng ElasticsearchOperations.
- ProductIndexManager: tạo/kiểm tra index và mapping theo quy trình bootstrap hoặc migration.
- SearchTemplateManager: cài đặt, cập nhật và xóa stored search templates.
- SearchUnavailableException: exception nghiệp vụ để application layer diễn đạt lỗi.
- ApiExceptionHandler: chuyển exception ứng dụng thành HTTP response.

Trong production, nên cân nhắc tách quyền quản trị index khỏi quyền đọc/ghi document. Ứng dụng runtime thường chỉ cần quyền thao tác dữ liệu và search; bước migration/deployment có thể dùng credential có quyền quản trị index/template/alias.

## 11. Quy trình triển khai và vận hành đề xuất

Một quy trình quản lý tài nguyên tìm kiếm có thể thực hiện như sau:

1. Khai báo document metadata, mapping và settings cần thiết.
2. Xác định index vật lý, alias đọc/ghi và quy tắc version.
3. Tạo hoặc cập nhật index template cho các index mới nếu cluster dùng template.
4. Tạo index mới bằng migration hoặc IndexOperations, sau đó xác nhận mapping/settings.
5. Nạp hoặc reindex dữ liệu và kiểm tra số document, query và aggregation.
6. Chuyển alias khi index mới sẵn sàng.
7. Triển khai stored search template trước code sử dụng template ID mới.
8. Dùng ElasticsearchOperations cho query đặc thù, PIT hoặc stream; luôn đóng tài nguyên dài hạn.
9. Theo dõi cluster health, query latency, indexing failures và các exception đã được chuyển đổi.
10. Xóa tài nguyên cũ sau thời gian xác nhận và theo chính sách lưu trữ.
11. Chuẩn hóa exception tại application boundary và API boundary; giữ cause cho logging.
12. Chỉ retry lỗi có tính tạm thời và thao tác có thể retry an toàn.

## 12. Những lỗi thường gặp

**Nghĩ rằng IndexOperations tự tạo index.** Việc lấy object IndexOperations không gửi request. Phải gọi create(), createWithMapping() hoặc thao tác tương ứng.

**Dùng IndexOperations cho mọi thao tác document.** IndexOperations quản lý tài nguyên index. Dùng DocumentOperations hoặc ElasticsearchOperations cho lưu/đọc/xóa document.

**Dùng index template thay cho search template.** Index template cấu hình index mới; search template lưu query có tham số. Hai tài nguyên không thay thế nhau.

**Thay đổi index template rồi chờ index cũ đổi settings.** Template chỉ áp dụng khi tạo index mới. Index hiện hữu cần update riêng.

**Chuyển alias trước khi reindex hoàn tất.** Người dùng có thể đọc dữ liệu chưa đầy đủ. Xác nhận dữ liệu và query trước khi chuyển.

**Xóa index theo tên do client truyền.** Có thể xóa nhầm tài nguyên. Dùng allowlist hoặc mapping giữa nghiệp vụ và tên index được quản lý.

**Không đóng stream hoặc PIT.** Tài nguyên search tồn tại lâu gây áp lực lên cluster. Luôn quản lý vòng đời bằng finally hoặc cơ chế đóng phù hợp.

**Giả định mọi exception Elasticsearch đều được chuyển thành DataAccessException.** Translator chỉ chuyển exception phù hợp; exception từ code người dùng có thể được giữ nguyên.

**Bắt mọi DataAccessException rồi retry.** Lỗi mapping, query hoặc validation sẽ không tự hết. Phân loại theo cause và tính idempotent.

**Trả raw exception cho API client.** Điều đó có thể lộ tên index, query, endpoint hoặc chi tiết cluster. Chuyển thành lỗi ứng dụng có thông tin tối thiểu.

## 13. Tài liệu tham khảo

- [Spring Data Elasticsearch - Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): phân biệt IndexOperations, DocumentOperations, SearchOperations và ElasticsearchOperations; các query API.
- [Spring Data Elasticsearch - Miscellaneous Operation Support](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html): index settings, mapping, stored search templates, Scroll và Point in Time.
- [Spring Data Elasticsearch API - IndexOperations](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/IndexOperations.html): API quản lý index.
- [Spring Data Elasticsearch API - ElasticsearchExceptionTranslator](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchExceptionTranslator.html): exception translator cho Elasticsearch Java API Client.
- [Spring Framework - DAO support](https://docs.spring.io/spring-framework/reference/data-access/dao.html): hệ thống exception truy cập dữ liệu và exception translation.

Các API, package và hành vi có thể khác theo phiên bản Spring Data Elasticsearch và Elasticsearch Java Client. Khi triển khai, hãy đối chiếu Javadoc và tài liệu của đúng phiên bản dependency trong dự án.
