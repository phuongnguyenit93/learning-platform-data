# Giới hạn callback, auditing khi dùng script, bulk hoặc client trực tiếp

## 1. Vì sao callback và auditing có thể không chạy cho mọi thao tác ghi?

Spring Data Elasticsearch cung cấp entity callback và auditing để bổ sung thông tin hoặc thay đổi entity tại những điểm xác định trong vòng đời lưu trữ. Ví dụ, trước khi lưu một đơn hàng, ứng dụng có thể tự động điền:

- Thời điểm tạo: `createdAt`.
- Người tạo: `createdBy`.
- Thời điểm cập nhật gần nhất: `lastModifiedAt`.
- Người cập nhật gần nhất: `lastModifiedBy`.

Khi ứng dụng ghi entity thông qua Spring Data, framework có thể chuyển entity sang document, gọi callback, áp dụng auditing rồi gửi dữ liệu đến Elasticsearch.

Tuy nhiên, không phải mọi thao tác ghi đều đi qua vòng đời entity đó. Một ứng dụng có thể ghi bằng script trong Update API, `_update_by_query`, Bulk API với các `UpdateQuery` hoặc action JSON, `ElasticsearchClient` trực tiếp, REST client hoặc một dịch vụ khác ghi vào cùng index.

Những thao tác này thường làm việc trực tiếp với document hoặc `_source`. Chúng không nhất thiết có một object Java được Spring Data chuyển đổi. Vì vậy, callback và auditing của Spring Data không tự động được gọi.

Đây là giới hạn quan trọng khi thiết kế hệ thống có nhiều đường ghi. Nếu chỉ dựa vào `@CreatedDate` và `@LastModifiedDate`, dữ liệu có thể đầy đủ khi ghi qua repository nhưng thiếu audit metadata khi được cập nhật bằng script hoặc client trực tiếp.

Bài học này giải thích callback chạy ở đâu, những đường ghi nào có thể bỏ qua callback, và cách duy trì audit metadata nhất quán khi dùng script, bulk hoặc client cấp thấp.

## 2. Entity callback hoạt động ở đâu?

Entity callback là hook do Spring Data gọi tại một điểm xác định trong quá trình xử lý entity. Callback có thể nhận entity, trả về chính entity đó hoặc trả về một instance đã được thay đổi.

Spring Data Elasticsearch sử dụng EntityCallback API cho các điểm chính:

| Callback | Thời điểm | Mục đích |
|---|---|---|
| `BeforeConvertCallback` | Trước khi entity được chuyển thành `Document` | Chuẩn hóa dữ liệu, gán giá trị mặc định, cập nhật field |
| `AfterSaveCallback` | Sau khi entity được lưu thành công qua đường lưu entity | Thực hiện xử lý sau lưu |
| `AfterLoadCallback` | Sau khi đọc kết quả từ Elasticsearch thành `Document` và trước khi convert | Thay đổi document trước khi ánh xạ |
| `AfterConvertCallback` | Sau khi document được convert thành entity | Hoàn thiện entity sau khi đọc |
| `AuditingEntityCallback` | Trước khi convert entity | Gán các field auditing như ngày tạo, ngày cập nhật và người thực hiện |

Callback được đăng ký dưới dạng Spring bean trong `ApplicationContext`. Template có thể lấy các bean đó và gọi chúng tại đúng checkpoint.

Ví dụ một callback trước khi convert:

~~~java
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;

@Component
public class OrderDefaultsCallback implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order, IndexCoordinates index) {
        if (order.getStatus() == null) {
            order.setStatus("NEW");
        }

        return order;
    }
}
~~~

Khi một thao tác lưu entity đi qua callback chain, Spring Data gọi `onBeforeConvert` trước khi chuyển entity thành document. Giá trị trả về của callback là entity tiếp tục được xử lý.

Với entity immutable, callback có thể trả về một instance mới thay vì sửa object ban đầu:

~~~java
@Component
public class OrderDefaultsCallback implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order, IndexCoordinates index) {
        if (order.status() != null) {
            return order;
        }

        return new Order(
            order.id(),
            order.customerId(),
            "NEW",
            order.createdAt(),
            order.lastModifiedAt()
        );
    }
}
~~~

Không nên giả định callback luôn sửa trực tiếp object đầu vào. Hãy sử dụng entity mà callback trả về để tiếp tục quá trình lưu.

## 3. Các callback Elasticsearch hỗ trợ

Spring Data Elasticsearch có danh sách callback gắn với vòng đời riêng của module. Các callback thường dùng gồm:

| Interface | Method | Mục đích |
|---|---|---|
| `BeforeConvertCallback<T>` | `onBeforeConvert(T, IndexCoordinates)` | Thay đổi entity trước khi convert |
| `AfterSaveCallback<T>` | `onAfterSave(T, IndexCoordinates)` | Xử lý entity sau khi lưu |
| `AfterLoadCallback<T>` | `onAfterLoad(Document, Class<T>, IndexCoordinates)` | Thay đổi document sau khi đọc |
| `AfterConvertCallback<T>` | `onAfterConvert(T, Document, IndexCoordinates)` | Xử lý entity sau khi convert |
| `AuditingEntityCallback` | `onBeforeConvert(Object, IndexCoordinates)` | Điền audit metadata |

`AuditingEntityCallback` là callback nội bộ do auditing infrastructure đăng ký. Nó được gọi ở bước trước khi convert entity.

Không nên áp dụng máy móc tên callback từ Spring Data JPA hoặc Spring Data MongoDB cho Elasticsearch. Mỗi store có vòng đời và danh sách callback cụ thể. Hãy kiểm tra API của phiên bản Spring Data Elasticsearch đang sử dụng.

### Đăng ký callback

Callback có thể được đăng ký bằng `@Component`:

~~~java
@Component
public class ProductCallback implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        product.setNormalizedName(
            product.getName().trim().toLowerCase()
        );

        return product;
    }
}
~~~

Hoặc đăng ký bằng `@Bean`:

~~~java
@Configuration
public class ElasticsearchCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Product> productCallback() {
        return (product, index) -> {
            product.setStatus(
                product.getStatus() == null ? "ACTIVE" : product.getStatus()
            );
            return product;
        };
    }
}
~~~

Template Spring Data được tích hợp với `ApplicationContext` để nhận các callback bean. Nếu tự tạo một template hoặc tự thay thế `EntityCallbacks`, cần bảo đảm callback auditing mặc định vẫn được cấu hình trong chain.

### Thứ tự thực thi

Callback có thể implement `Ordered` hoặc dùng `@Order` để xác định thứ tự. Giá trị order thấp hơn được gọi trước.

`AuditingEntityCallback` có order 100. Callback tùy chỉnh có thể được sắp xếp trước hoặc sau tùy nhu cầu.

Ví dụ callback chuẩn hóa dữ liệu cần chạy trước auditing:

~~~java
@Component
@Order(50)
public class NormalizeOrderCallback implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order, IndexCoordinates index) {
        order.setCode(order.getCode().trim().toUpperCase());
        return order;
    }
}
~~~

Nếu callback sau đó thay đổi field audit, nó có thể ghi đè giá trị do auditing vừa đặt. Vì vậy, không nên để nhiều callback cùng quản lý một field nếu không có quy tắc thứ tự rõ ràng.

## 4. Auditing trong Spring Data Elasticsearch

Auditing giúp tự động ghi lại ai tạo hoặc cập nhật entity và thời điểm thao tác xảy ra.

Các annotation phổ biến:

| Annotation | Ý nghĩa |
|---|---|
| `@CreatedDate` | Thời điểm tạo entity |
| `@CreatedBy` | Người tạo entity |
| `@LastModifiedDate` | Thời điểm cập nhật gần nhất |
| `@LastModifiedBy` | Người cập nhật gần nhất |

Ví dụ entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    private String customerId;

    private String status;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdAt;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedAt;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    // Constructors, getters và setters
}
~~~

Các field này là metadata trong document. Khi auditing chạy, Spring Data cập nhật giá trị trước khi entity được convert và gửi đi.

### Bật auditing

Cần bật auditing bằng annotation cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
~~~

Nếu entity dùng `@CreatedBy` hoặc `@LastModifiedBy`, ứng dụng cần cung cấp `AuditorAware` để Spring Data biết người đang thực hiện thao tác.

Ví dụ:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("system");
    }
}
~~~

Trong ứng dụng thực tế, giá trị nên được lấy từ SecurityContext hoặc thông tin người dùng của request. Ví dụ trên dùng chuỗi cố định để minh họa cấu trúc interface.

Có thể chỉ định bean rõ ràng:

~~~java
@Configuration
@EnableElasticsearchAuditing(auditorAwareRef = "auditorAware")
public class ElasticsearchAuditingConfiguration {
}
~~~

Nếu chỉ dùng field ngày tạo và ngày cập nhật, không cần triển khai `AuditorAware`. Nếu có nhiều `AuditorAware` với các kiểu dữ liệu khác nhau, cấu hình `auditorAwareRef` để chọn bean tương ứng.

### Chọn thời gian

Mặc định, auditing dùng thời gian hiện tại qua `CurrentDateTimeProvider`. Nếu cần đồng bộ clock hoặc kiểm thử xác định, có thể cung cấp `DateTimeProvider` riêng.

Điều này đặc biệt hữu ích khi nhiều service cùng ghi vào một index. Nếu mỗi service sử dụng clock khác nhau, timestamp có thể lệch nhau. Một quy ước thời gian UTC và nguồn clock thống nhất sẽ giúp dữ liệu dễ đối chiếu hơn.

## 5. Phân biệt thời điểm tạo và cập nhật

Auditing cần biết entity là mới hay đã tồn tại để xử lý `createdAt` và `lastModifiedAt` phù hợp.

Trong Elasticsearch, sự hiện diện của ID không đủ để xác định entity mới. Một entity mới có thể được ứng dụng gán ID trước khi lưu. Vì vậy, tài liệu Spring Data Elasticsearch hướng dẫn có thể dùng `Persistable<ID>` để cung cấp logic `isNew()`.

Ví dụ:

~~~java
import org.springframework.data.domain.Persistable;

@Document(indexName = "orders")
public class Order implements Persistable<String> {

    @Id
    private String id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return id == null || createdAt == null;
    }
}
~~~

Đây chỉ là một quy tắc minh họa. Trong hệ thống thực tế, cần chọn điều kiện `isNew()` phù hợp với vòng đời entity và dữ liệu cũ. Ví dụ, nếu một document cũ không có `createdAt` do migration, điều kiện trên có thể coi nó là mới khi lưu lại.

Không nên dùng ID làm điều kiện duy nhất nếu ứng dụng cho phép tạo ID ở phía client.

## 6. Callback và auditing khi dùng save(entity)

Đường lưu entity thông thường qua `ElasticsearchOperations.save(entity)` là đường đi rõ ràng nhất để callback và auditing hoạt động.

Luồng khái quát:

~~~text
ElasticsearchOperations.save(entity)
              |
              v
      BeforeConvertCallback
              |
              v
      AuditingEntityCallback
              |
              v
       Mapping / Conversion
              |
              v
        Index API request
              |
              v
         AfterSaveCallback
~~~

Thứ tự thực tế giữa các callback `BeforeConvertCallback` phụ thuộc order. Auditing callback chạy ở order 100.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final ElasticsearchOperations operations;

    public OrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order create(Order order) {
        return operations.save(order);
    }
}
~~~

Nếu auditing được bật, entity có metadata phù hợp và callback chain được đăng ký đúng, các field audit sẽ được cập nhật trước khi document được lưu.

Đường lưu thông qua repository cũng dùng Spring Data infrastructure:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
~~~

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order create(Order order) {
        return repository.save(order);
    }
}
~~~

Repository không tự tạo một cơ chế auditing riêng. Nó sử dụng template-backed Spring Data persistence path.

## 7. Callback có chạy khi dùng saveAll hoặc bulk index không?

Không nên kết luận rằng mọi thao tác bulk đều bỏ qua callback. Cần phân biệt loại bulk và cách tạo request.

### saveAll(entities)

`saveAll(entities)` của repository và `ElasticsearchOperations.save(Iterable)` là đường lưu entity. Spring Data tạo các `IndexQuery` từ entity rồi thực hiện bulk indexing.

Trong implementation template hiện hành:

- `save(entity)` gọi `BeforeConvertCallback` trước khi tạo index request.
- `save(Iterable)` tạo `IndexQuery` từ các entity.
- Bulk operation gọi helper xử lý callback cho từng `IndexQuery` có chứa object entity.
- Sau khi bulk hoàn tất, callback `AfterSaveCallback` được gọi cho các entity tương ứng.

Vì vậy, khi dùng đường lưu entity qua `saveAll` hoặc `save(Iterable)`, callback và auditing có thể được thực thi cho từng entity trước khi bulk request được gửi.

Ví dụ:

~~~java
List<Order> orders = List.of(order1, order2, order3);

Iterable<Order> saved = orderRepository.saveAll(orders);
~~~

Đây vẫn là đường lưu entity của Spring Data. Không cần tự gán audit fields chỉ vì phương thức nội bộ dùng Bulk API.

### bulkIndex với IndexQuery có object entity

Spring Data cung cấp `IndexQuery` để mô tả thao tác index. Nếu `IndexQuery` chứa object entity, template có thể gọi callback cho object đó.

Ví dụ:

~~~java
IndexQuery indexQuery = new IndexQueryBuilder()
    .withId(order.getId())
    .withObject(order)
    .build();

operations.bulkIndex(
    List.of(indexQuery),
    IndexCoordinates.of("orders")
);
~~~

Ở đường này, `withObject(order)` cho template biết entity nào cần được xử lý. Callback `BeforeConvertCallback` và `AfterSaveCallback` có thể được gọi qua bulk helper.

### bulkIndex với Document hoặc JSON có sẵn

Nếu `IndexQuery` chỉ chứa document đã tạo sẵn, không có object entity, Spring Data không có entity để truyền vào callback.

Ví dụ:

~~~java
IndexQuery indexQuery = new IndexQueryBuilder()
    .withId("order-100")
    .withSource("""
        {
          "status": "NEW",
          "createdAt": "2026-11-13T10:00:00Z"
        }
        """)
    .build();
~~~

Trong trường hợp này, template gửi document đã chuẩn bị. Không có entity Java để `AuditingEntityCallback` tự động điền metadata.

Nếu muốn audit metadata đầy đủ, hãy bổ sung các field trước khi tạo JSON/Document hoặc chuyển sang đường lưu entity.

### bulkUpdate với UpdateQuery

`bulkUpdate(List<UpdateQuery>)` là đường cập nhật document. `UpdateQuery` mô tả dữ liệu hoặc script cập nhật, không phải một entity đang được convert.

Implementation callback helper của template xử lý object trong `IndexQuery`; nó không tự động chạy auditing cho một `UpdateQuery` chứa partial document hoặc script.

Vì vậy, không nên giả định:

~~~java
operations.bulkUpdate(updateQueries, Order.class);
~~~

sẽ tự cập nhật `lastModifiedAt` và `lastModifiedBy` cho từng order. Hãy đưa các field audit vào nội dung update hoặc script.

### Bảng tổng hợp bulk

| Đường ghi | Entity callback / auditing | Ghi chú |
|---|---|---|
| `repository.saveAll(entities)` | Có, qua đường lưu entity | Entity được xử lý trước khi bulk index |
| `operations.save(Iterable)` | Có, qua đường lưu entity | Tạo IndexQuery từ entity |
| `bulkIndex(IndexQuery có object)` | Có thể có | Callback helper cần object entity |
| `bulkIndex(IndexQuery chỉ có Document/JSON)` | Không có entity để callback | Tự chuẩn bị audit fields |
| `bulkUpdate(List<UpdateQuery>)` | Không tự động chạy auditing cho update payload/script | Gửi audit fields trong update |
| Bulk API trực tiếp | Không | Tự xử lý metadata trong từng action |

Điểm quan trọng là từ `bulk` không đủ để suy ra callback có hay không. Hãy xem thao tác bulk đang đi qua đường lưu entity hay gửi trực tiếp document/update action.

## 8. Update(entity) không giống save(entity)

Một điểm dễ bỏ sót là `ElasticsearchOperations.update(entity)` không nhất thiết đi qua cùng callback chain với `save(entity)`.

Trong implementation template, update entity được chuyển thành `UpdateQuery` chứa partial document. Đường này không chạy cùng helper `BeforeConvertCallback` và `AfterSaveCallback` như save entity.

Ví dụ:

~~~java
operations.update(order);
~~~

Không nên mặc định rằng lệnh này tự cập nhật:

- `lastModifiedAt`.
- `lastModifiedBy`.
- Các giá trị chuẩn hóa do `BeforeConvertCallback` thêm.
- Các field nghiệp vụ được callback tính toán.

Nếu cần auditing cho update, có thể:

1. Dùng `save(entity)` nếu nghiệp vụ phù hợp với việc ghi lại toàn bộ entity.
2. Tự cập nhật audit fields trước khi tạo `UpdateQuery`.
3. Dùng script và truyền timestamp, actor qua params.
4. Tạo một service update dùng chung để mọi luồng cập nhật áp dụng cùng quy tắc.

Chọn cách cập nhật phải xét đến nguy cơ ghi đè field mà request không định thay đổi. Không thay thế partial update bằng full save nếu entity có thể đã cũ so với document trong index.

## 9. Script trong Update API bỏ qua auditing callback

Elasticsearch Update API cho phép chạy Painless script trực tiếp trên document.

Ví dụ tăng số lần xem:

~~~http
POST /products/_update/p-100
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.viewCount += params.increment",
    "params": {
      "increment": 1
    }
  }
}
~~~

Elasticsearch thực hiện script trên `_source` hiện tại rồi index lại kết quả. Request này không gửi một entity Java qua Spring Data converter. Vì vậy:

- `BeforeConvertCallback` không được tự động gọi.
- `AuditingEntityCallback` không được tự động gọi.
- `AfterSaveCallback` không được tự động gọi.
- Các annotation `@LastModifiedDate` và `@LastModifiedBy` không tự áp dụng.

Nếu script cần duy trì audit metadata, hãy cập nhật các field đó trong cùng script.

Ví dụ:

~~~http
POST /orders/_update/order-100
{
  "script": {
    "lang": "painless",
    "source": """
      ctx._source.status = params.status;
      ctx._source.lastModifiedAt = params.updatedAt;
      ctx._source.lastModifiedBy = params.actor;
    """,
    "params": {
      "status": "APPROVED",
      "updatedAt": "2026-11-13T10:15:30Z",
      "actor": "user-42"
    }
  }
}
~~~

Thời gian và actor được cung cấp từ ứng dụng qua params. Đây là cách rõ ràng để audit một scripted update.

Không nên hard-code user hoặc timestamp trong script source. Truyền giá trị qua params giúp giữ source ổn định và dễ tái sử dụng script đã biên dịch.

## 10. Script trong _update_by_query

`_update_by_query` cập nhật nhiều document khớp một query. Script làm việc trực tiếp với `ctx._source` của từng document.

Ví dụ cập nhật trạng thái và audit metadata cho các đơn hàng đang chờ:

~~~http
POST /orders/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "status": "PENDING"
    }
  },
  "script": {
    "lang": "painless",
    "source": """
      ctx._source.status = params.newStatus;
      ctx._source.lastModifiedAt = params.updatedAt;
      ctx._source.lastModifiedBy = params.actor;
    """,
    "params": {
      "newStatus": "EXPIRED",
      "updatedAt": "2026-11-13T10:15:30Z",
      "actor": "scheduler"
    }
  }
}
~~~

Request này không tạo entity Java cho từng document. Auditing callback của Spring Data không được gọi cho từng document được update.

Nếu script cần giữ `createdAt` và `createdBy`, không gán lại các field đó trong update script. Chỉ cập nhật metadata của lần thay đổi hiện tại.

Ví dụ script tạo giá trị createdAt khi thiếu và luôn cập nhật lastModifiedAt:

~~~json
{
  "script": {
    "lang": "painless",
    "source": """
      if (ctx._source.createdAt == null) {
        ctx._source.createdAt = params.updatedAt;
        ctx._source.createdBy = params.actor;
      }

      ctx._source.lastModifiedAt = params.updatedAt;
      ctx._source.lastModifiedBy = params.actor;
    """,
    "params": {
      "updatedAt": "2026-11-13T10:15:30Z",
      "actor": "migration-job"
    }
  }
}
~~~

Đây là ví dụ cho một migration có quy tắc cụ thể. Với dữ liệu production, cần kiểm tra document cũ, field thiếu và chính sách audit trước khi chạy trên toàn index.

### Các biến trong update script

Update script có thể sử dụng:

| Biến | Ý nghĩa |
|---|---|
| `ctx._source` | Nội dung document đang được cập nhật |
| `ctx._id` | ID document |
| `ctx._index` | Tên index |
| `ctx._version` | Version hiện tại |
| `ctx._routing` | Routing của document |
| `params` | Tham số do request truyền vào |
| `ctx.op` | Chọn hành động index, noop hoặc delete |

Update-by-query có Painless context riêng. Không nên giả định mọi biến của Update API đều có trong update-by-query context. Nếu cần timestamp hoặc actor, cách rõ ràng nhất là truyền qua params từ ứng dụng.

`_update_by_query` yêu cầu `_source` được bật để script chỉnh sửa nội dung document. Nó có thể gặp version conflict nếu document thay đổi trong lúc request xử lý; chọn `conflicts=proceed` chỉ khi nghiệp vụ chấp nhận bỏ qua các document xung đột và có kế hoạch xử lý chúng.

## 11. Script trong Bulk API

Bulk API có thể chứa các action `index`, `create`, `update` hoặc `delete`. Với action update, có thể gửi script:

~~~http
POST /orders/_bulk
{"update":{"_id":"order-101"}}
{"script":{"source":"ctx._source.lastModifiedAt = params.updatedAt; ctx._source.lastModifiedBy = params.actor","params":{"updatedAt":"2026-11-13T10:15:30Z","actor":"user-42"}}}
{"update":{"_id":"order-102"}}
{"script":{"source":"ctx._source.lastModifiedAt = params.updatedAt; ctx._source.lastModifiedBy = params.actor","params":{"updatedAt":"2026-11-13T10:15:30Z","actor":"user-42"}}}
~~~

Các action này do Elasticsearch xử lý trực tiếp. Spring Data không có entity object để chạy auditing callback.

Nếu bulk request dùng index action với source đã chuẩn bị sẵn, audit fields phải có trong source trước khi gửi. Nếu bulk request dùng update action với script, script cần cập nhật audit fields.

Với batch có nhiều người thực hiện khác nhau, không dùng chung một actor cho toàn bộ batch. Mỗi action cần mang actor đúng với thao tác tương ứng hoặc ứng dụng cần chia batch theo người thực hiện.

## 12. Client trực tiếp qua ElasticsearchClient

Spring Data Elasticsearch 6.x dùng Elasticsearch Java API Client. Template có phương thức `execute(ClientCallback)` để thực hiện thao tác trực tiếp trên client và hỗ trợ exception translation.

Ví dụ:

~~~java
import co.elastic.clients.elasticsearch.core.IndexResponse;

IndexResponse response = elasticsearchTemplate.execute(client ->
    client.index(i -> i
        .index("orders")
        .id(order.getId())
        .document(order)
    )
);
~~~

Đường này gọi trực tiếp client. Nó không đi qua `ElasticsearchOperations.save(entity)`, nên không tự chạy:

- `BeforeConvertCallback`.
- `AuditingEntityCallback`.
- `AfterSaveCallback`.

Việc dùng template làm nơi cung cấp client không có nghĩa là thao tác raw client được đưa trở lại vòng đời entity.

Tương tự, nếu ứng dụng inject `ElasticsearchClient` và gọi `client.index(...)`, `client.update(...)` hoặc `client.bulk(...)` trực tiếp, callback Spring Data không tự được gọi.

### Client trực tiếp có thể vẫn dùng converter không?

Ứng dụng có thể inject `ElasticsearchConverter` để chuyển entity thành `Document` hoặc `Map` trước khi gửi bằng client trực tiếp. Điều đó giúp tận dụng mapping annotation và quy tắc convert của Spring Data.

Tuy nhiên, converter không phải entity callback chain. Chỉ convert entity không tự động chạy auditing callback.

Nếu cần dùng client trực tiếp nhưng vẫn muốn audit metadata, ứng dụng phải:

1. Gọi một service hoặc helper chịu trách nhiệm áp dụng audit metadata.
2. Convert entity bằng converter nếu cần.
3. Gửi document bằng ElasticsearchClient.
4. Kiểm tra response và xử lý lỗi ghi.

Không nên cho rằng dùng cùng một converter đồng nghĩa với việc auditing đã được thực thi.

## 13. Các đường ghi và giới hạn callback

Bảng sau giúp chọn đúng đường ghi khi hệ thống có auditing:

| Đường ghi | Mapping/conversion của Spring Data | Entity callback | Auditing tự động |
|---|---|---|---|
| `repository.save(entity)` | Có | Có | Có, nếu đã bật |
| `operations.save(entity)` | Có | Có | Có, nếu đã bật |
| `repository.saveAll(entities)` | Có | Có qua đường save entity | Có, nếu đã bật |
| `operations.save(Iterable)` | Có | Có qua IndexQuery có object | Có, nếu đã bật |
| `operations.bulkIndex(IndexQuery có object)` | Có cho object | Có thể có | Có thể có |
| `operations.bulkIndex(Document/JSON)` | Dùng dữ liệu đã tạo | Không có entity để callback | Không tự động |
| `operations.update(entity)` | Chuyển thành UpdateQuery | Không đi qua save callback chain | Không tự động |
| `operations.bulkUpdate(UpdateQuery)` | Dùng update payload/query | Không tự động | Không tự động |
| `_update` với script | Elasticsearch xử lý `_source` | Không | Không |
| `_update_by_query` với script | Elasticsearch xử lý từng document | Không | Không |
| Bulk API trực tiếp | Client xử lý request | Không | Không |
| `ElasticsearchClient` trực tiếp | Client xử lý request | Không | Không |
| REST client hoặc service khác | Không qua Spring Data | Không | Không |

Bảng này phản ánh đường xử lý thông thường trong Spring Data Elasticsearch. Một ứng dụng có thể tự gọi callback hoặc tự bổ sung audit metadata, nhưng đó là logic do ứng dụng chủ động thực hiện.

## 14. Duy trì audit metadata trong script

Một quy tắc đơn giản cho update script:

- `createdAt` và `createdBy` chỉ được gán khi document được tạo lần đầu hoặc khi migration cần bổ sung dữ liệu thiếu.
- `lastModifiedAt` và `lastModifiedBy` được cập nhật mỗi lần có thay đổi nghiệp vụ.
- Actor phải đến từ danh tính đã xác thực hoặc một danh tính hệ thống rõ ràng.
- Timestamp phải được tạo từ clock thống nhất, thường là UTC.
- Không cho client tự gửi actor tùy ý nếu có thể giả mạo danh tính.

Ví dụ script cập nhật trạng thái:

~~~java
String script = """
    ctx._source.status = params.status;
    ctx._source.lastModifiedAt = params.updatedAt;
    ctx._source.lastModifiedBy = params.actor;
    """;

Map<String, Object> params = Map.of(
    "status", "APPROVED",
    "updatedAt", Instant.now().toString(),
    "actor", currentUserId
);
~~~

Ứng dụng truyền script và params cho Update API hoặc Bulk Update action.

Nếu dùng một script được lưu trong Elasticsearch, vẫn truyền actor và timestamp qua params. Stored script không tự biết người dùng hiện tại của ứng dụng.

### Không ghi đè createdAt khi cập nhật

Ví dụ không phù hợp:

~~~painless
ctx._source.createdAt = params.now;
ctx._source.lastModifiedAt = params.now;
~~~

Đoạn script trên sẽ thay đổi cả thời điểm tạo, làm mất ý nghĩa audit.

Cách phù hợp hơn:

~~~painless
ctx._source.lastModifiedAt = params.now;
ctx._source.lastModifiedBy = params.actor;
~~~

Chỉ set `createdAt` và `createdBy` trong logic tạo document hoặc quy trình backfill có chủ đích.

## 15. Xây dựng một audit helper dùng chung

Nếu hệ thống có nhiều đường ghi, nên gom quy tắc audit vào một service hoặc helper để tránh mỗi nơi tự viết logic khác nhau.

Ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Component;

@Component
public class AuditMetadataFactory {

    private final Clock clock;
    private final CurrentActorProvider actorProvider;

    public AuditMetadataFactory(
            Clock clock,
            CurrentActorProvider actorProvider) {
        this.clock = clock;
        this.actorProvider = actorProvider;
    }

    public AuditMetadata forUpdate() {
        return new AuditMetadata(
            Instant.now(clock),
            actorProvider.currentActor()
        );
    }
}
~~~

DTO audit:

~~~java
import java.time.Instant;

public record AuditMetadata(
    Instant modifiedAt,
    String modifiedBy
) {
}
~~~

Một helper như vậy có thể được dùng bởi:

- Callback tùy chỉnh.
- Service tạo `UpdateQuery`.
- Service xây dựng Bulk action.
- Script update.
- Luồng ghi bằng client trực tiếp.

Ví dụ khi tạo UpdateQuery:

~~~java
AuditMetadata audit = auditMetadataFactory.forUpdate();

Map<String, Object> update = new HashMap<>();
update.put("status", "APPROVED");
update.put("lastModifiedAt", audit.modifiedAt());
update.put("lastModifiedBy", audit.modifiedBy());

UpdateQuery updateQuery = UpdateQuery.builder(orderId)
    .withDocument(Document.from(update))
    .build();
~~~

Ví dụ này minh họa cách đưa audit metadata vào partial update. Kiểu tạo `Document` cụ thể có thể khác theo API Spring Data Elasticsearch đang dùng.

Quan trọng là tất cả đường ghi dùng chung một nguồn actor và clock, tránh mỗi controller tự tạo timestamp hoặc tự suy luận người dùng.

## 16. Dùng ingest pipeline cho metadata chung

Elasticsearch ingest pipeline có thể bổ sung hoặc chuẩn hóa một số field trước khi document được index.

Ví dụ pipeline dùng timestamp ingest:

~~~http
PUT /_ingest/pipeline/add-ingest-time
{
  "processors": [
    {
      "set": {
        "field": "ingestedAt",
        "value": "{{{_ingest.timestamp}}}"
      }
    }
  ]
}
~~~

Pipeline có thể được gọi từ Index hoặc Bulk API thông qua tham số `pipeline`.

Ingest pipeline hữu ích cho metadata chung như thời điểm dữ liệu được ingest, chuẩn hóa chuỗi, thêm thông tin nguồn, chuyển đổi field và chuẩn hóa cấu trúc document.

Tuy nhiên, `ingestedAt` không nhất thiết giống `lastModifiedAt`. Ingest time là thời điểm Elasticsearch xử lý document qua pipeline; modified time là thời điểm nghiệp vụ thay đổi dữ liệu.

Pipeline cũng không tự biết người dùng hiện tại của ứng dụng. Nếu cần `createdBy` hoặc `lastModifiedBy`, ứng dụng phải truyền actor vào document hoặc request theo một cơ chế đáng tin cậy.

Có thể dùng pipeline kết hợp script hoặc audit helper, nhưng cần xác định rõ nguồn dữ liệu nào là nguồn có thẩm quyền cho từng field.

## 17. Sự khác biệt giữa callback đồng bộ và reactive

Spring Data tách callback đồng bộ và reactive.

- API đồng bộ dùng `BeforeConvertCallback`, `AfterSaveCallback` và các callback đồng bộ tương ứng.
- API reactive dùng `ReactiveBeforeConvertCallback`, `ReactiveAfterSaveCallback` và các callback reactive tương ứng.

Một callback đồng bộ không tự động được gọi trong reactive template. Tương tự, callback reactive không thay thế callback đồng bộ.

Ví dụ callback reactive:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveOrderCallback
        implements ReactiveBeforeConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            IndexCoordinates index) {

        order.setStatus(
            order.getStatus() == null ? "NEW" : order.getStatus()
        );

        return Mono.just(order);
    }
}
~~~

Auditing reactive cần bật bằng `@EnableReactiveElasticsearchAuditing` và dùng `ReactiveAuditorAware` nếu có field auditor.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableReactiveElasticsearchAuditing
public class ReactiveAuditingConfiguration {
}
~~~

Không nên đăng ký một callback đồng bộ rồi kỳ vọng nó chạy trong `ReactiveElasticsearchTemplate`. Hãy implement đúng loại callback của API đang dùng.

## 18. Callback và ApplicationEvent không giống nhau

Spring Data Elasticsearch có hỗ trợ entity callback và một số store-specific application events.

Entity callback được thiết kế để chạy tuần tự tại checkpoint xác định trong processing chain. Callback có thể trả về entity đã thay đổi.

ApplicationEvent đi qua `ApplicationEventMulticaster`. Nếu ứng dụng cấu hình event multicaster bất đồng bộ, xử lý event có thể diễn ra trên thread khác và không còn bảo đảm thứ tự như callback đồng bộ.

Vì vậy, với logic cần thay đổi entity trước khi convert hoặc trước khi ghi, nên dùng EntityCallback thay vì phụ thuộc vào một event listener bất đồng bộ.

Ví dụ:

~~~java
@Component
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        product.setName(product.getName().trim());
        return product;
    }
}
~~~

Không nên dùng event listener để gán audit fields rồi giả định document chắc chắn đã được cập nhật trước khi template serialize entity nếu event multicaster có thể chạy bất đồng bộ.

## 19. Callback không phải transaction hoặc cơ chế audit bất biến

Entity callback giúp áp dụng logic trong một đường xử lý Spring Data. Nó không tạo một transaction phân tán giữa ứng dụng và Elasticsearch, cũng không phải một audit log bất biến.

Một vài giới hạn:

- Callback chỉ chạy khi đường gọi thực sự đi qua callback chain.
- Script hoặc client trực tiếp có thể bỏ qua callback.
- Một service khác có thể ghi document mà không áp dụng quy tắc audit của ứng dụng hiện tại.
- `AfterSaveCallback` không biến một request ghi thành transaction bao trùm hệ thống bên ngoài.
- Audit fields nằm trong document có thể bị ghi đè nếu một writer khác không tuân thủ quy tắc.
- Callback không thay thế event sourcing hoặc một hệ thống audit log append-only nếu nghiệp vụ cần lịch sử không thể sửa.

Nếu cần biết mọi thay đổi của document qua thời gian, chỉ giữ `lastModifiedAt` và `lastModifiedBy` là chưa đủ. Hai field đó chỉ phản ánh lần cập nhật gần nhất. Hãy cân nhắc lưu event hoặc audit record riêng để giữ lịch sử.

## 20. Kiểm thử callback và auditing

Nên kiểm thử riêng các đường ghi có và không có callback.

### Test save qua repository

~~~java
@Test
void shouldPopulateAuditFieldsWhenSavingEntity() {
    Order order = new Order();
    order.setStatus("NEW");

    Order saved = repository.save(order);

    assertThat(saved.getCreatedAt()).isNotNull();
    assertThat(saved.getLastModifiedAt()).isNotNull();
    assertThat(saved.getCreatedBy()).isEqualTo("test-user");
    assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
}
~~~

Test cần cấu hình auditor và auditing infrastructure. Với integration test Elasticsearch, nếu cần search ngay sau khi ghi, dùng refresh policy phù hợp hoặc chờ searchable theo cách có chủ đích.

### Test script update

Sau khi chạy script update, kiểm tra cả field nghiệp vụ và audit metadata:

~~~java
@Test
void shouldUpdateAuditMetadataInScriptedUpdate() {
    // Index một order đã có createdAt và createdBy.

    // Chạy update script với updatedAt và actor trong params.

    // Đọc lại document theo ID và kiểm tra:
    // - status đã đổi
    // - createdAt vẫn giữ nguyên
    // - createdBy vẫn giữ nguyên
    // - lastModifiedAt đã đổi
    // - lastModifiedBy đúng actor
}
~~~

Test này xác nhận script tự duy trì metadata thay vì trông chờ callback.

### Test bulk

Nên có test riêng cho:

- `saveAll(entities)`.
- `bulkIndex(IndexQuery có object)`.
- `bulkIndex(Document/JSON)`.
- `bulkUpdate(UpdateQuery)`.
- Bulk API trực tiếp.

Kết quả mong đợi phải phản ánh đúng đường ghi. Ví dụ, `saveAll` dùng entity lifecycle có thể được auditing tự động; bulk update bằng script phải tự ghi audit fields.

### Test client trực tiếp

Nếu một service gọi `ElasticsearchClient` trực tiếp, test nên xác nhận audit metadata đã được bổ sung trước khi request được gửi. Không nên chỉ kiểm tra callback bean đã tồn tại trong ApplicationContext.

## 21. Những lỗi thường gặp

**Cho rằng mọi thao tác ghi đều chạy callback.** Callback chỉ chạy khi đường gọi đi qua Spring Data entity lifecycle. Script và raw client không tự chạy callback.

**Cho rằng saveAll bỏ qua callback vì dùng Bulk API.** `saveAll` là đường lưu entity của Spring Data và có thể gọi callback cho từng entity. Hãy phân biệt nó với bulk update hoặc raw bulk request.

**Cho rằng bulkUpdate tự cập nhật LastModifiedDate.** `UpdateQuery` không phải entity lifecycle save. Hãy gửi audit fields trong partial document hoặc script.

**Cho rằng update(entity) tương đương save(entity).** Update tạo `UpdateQuery` và không nhất thiết đi qua BeforeConvert/Auditing callback. Kiểm tra API cụ thể trước khi kỳ vọng auditing.

**Cho rằng converter tự chạy auditing.** Converter chỉ chuyển đổi dữ liệu theo mapping. Entity callback là một bước riêng trong template.

**Cho rằng execute(ClientCallback) vẫn dùng callback.** `execute` cung cấp raw client. Thao tác trực tiếp qua client không chạy entity callback.

**Chỉ dùng @LastModifiedDate mà không bật auditing.** Annotation chỉ khai báo metadata. Cần bật `@EnableElasticsearchAuditing` để auditing infrastructure được đăng ký.

**Dùng @CreatedBy nhưng không có AuditorAware.** Spring Data không biết actor hiện tại nếu ứng dụng không cung cấp nguồn auditor.

**Không xác định entity mới đúng cách.** ID có thể đã được gán trước khi lưu. Xem xét `Persistable.isNew()` và dữ liệu audit hiện có.

**Để callback tùy chỉnh ghi đè audit fields.** Kiểm tra thứ tự callback và tránh nhiều thành phần cùng quản lý một field.

**Dùng một callback đồng bộ cho reactive API.** Reactive stack có callback riêng và auditing riêng.

**Coi ingestedAt là lastModifiedAt.** Thời điểm ingest và thời điểm thay đổi nghiệp vụ có ý nghĩa khác nhau.

**Ghi đè createdAt khi chạy update script.** Chỉ cập nhật last-modified fields trong update thông thường. Giữ creation metadata.

**Dùng actor từ request body.** Actor phải lấy từ danh tính đã xác thực hoặc nguồn tin cậy, tránh người dùng giả mạo người sửa.

**Cho rằng callback tạo audit log bất biến.** Các field trong document có thể bị cập nhật lại. Nếu cần lịch sử không thể sửa, dùng audit record hoặc event log riêng.

## 22. Quy trình thiết kế nhất quán cho nhiều đường ghi

Khi một index có nhiều cách ghi, nên thiết kế quy tắc audit trước khi triển khai:

1. Xác định các field audit cần lưu: created time, created actor, modified time, modified actor.
2. Xác định nguồn actor đáng tin cậy cho request người dùng, job và service nội bộ.
3. Chọn nguồn clock và quy ước timestamp, thường là UTC.
4. Bật Spring Data auditing cho đường lưu entity.
5. Định nghĩa `AuditorAware` hoặc `ReactiveAuditorAware` nếu cần actor.
6. Kiểm tra logic `isNew()` khi entity có ID được gán trước.
7. Dùng callback cho các thay đổi cần xảy ra trước khi convert entity.
8. Với `saveAll`, kiểm tra đây là đường lưu entity hay raw bulk.
9. Với `UpdateQuery`, scripted update và update-by-query, truyền audit metadata tường minh.
10. Với ElasticsearchClient hoặc REST client trực tiếp, áp dụng audit helper trước khi gửi request.
11. Giữ nguyên creation metadata khi update.
12. Kiểm thử từng đường ghi, không suy luận kết quả của bulk/script từ test save entity.
13. Nếu có nhiều hệ thống cùng ghi, chuẩn hóa hợp đồng audit hoặc dùng một lớp ingest/service có thẩm quyền.
14. Nếu cần lịch sử đầy đủ, ghi audit event riêng thay vì chỉ cập nhật last-modified fields.

Một sơ đồ triển khai:

~~~text
                 +---------------------+
                 |    Audit policy     |
                 | Actor + Clock + Rule|
                 +----------+----------+
                            |
             +--------------+---------------+
             |              |               |
             v              v               v
       Spring Data       Script / Bulk    Direct Client
       save / saveAll    UpdateQuery      ElasticsearchClient
             |              |               |
             v              v               v
       EntityCallback   Params + Script   Audit helper
       AuditingCallback
             |              |               |
             +--------------+---------------+
                            |
                            v
                    Elasticsearch index
~~~

Mục tiêu là mọi đường ghi đều tuân thủ cùng một quy tắc audit, dù cơ chế thực thi khác nhau.

## Kết luận

Entity callback và auditing của Spring Data Elasticsearch hoạt động trong vòng đời xử lý entity. `BeforeConvertCallback` và `AuditingEntityCallback` có thể bổ sung dữ liệu trước khi entity được chuyển thành document; `AfterSaveCallback`, `AfterLoadCallback` và `AfterConvertCallback` phục vụ các checkpoint tương ứng.

`save(entity)`, `saveAll(entities)` và các đường bulk index có object entity có thể đi qua callback chain. Nhưng `UpdateQuery`, script trong Update API, `_update_by_query`, bulk action tự tạo và thao tác qua `ElasticsearchClient` trực tiếp không tự động chạy auditing callback. Việc dùng `ElasticsearchConverter` cũng không đồng nghĩa auditing đã được thực thi.

Khi dùng script, bulk update hoặc client trực tiếp, hãy tự truyền timestamp và actor qua params hoặc audit helper, giữ nguyên creation metadata và cập nhật last-modified metadata. Nếu hệ thống có nhiều writer, hãy chuẩn hóa nguồn actor, clock và quy tắc audit để dữ liệu nhất quán trên mọi đường ghi. Khi cần lịch sử thay đổi bất biến, hãy lưu audit event riêng thay vì chỉ dựa vào các field trên document.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Entity Callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html)
- [Spring Data Elasticsearch — Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/data-commons/auditing.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — AuditingEntityCallback API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/event/AuditingEntityCallback.html)
- [Spring Data Elasticsearch — EnableElasticsearchAuditing API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/config/EnableElasticsearchAuditing.html)
- [Spring Data Elasticsearch — ElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchTemplate.html)
- [Elasticsearch — Update API](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/update-document)
- [Elasticsearch — Update by query API](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/update-by-query-api)
- [Elasticsearch — Update by query Painless context](https://www.elastic.co/docs/reference/scripting-languages/painless/painless-update-by-query-context)
- [Elasticsearch — Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
