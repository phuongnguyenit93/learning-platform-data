# Thứ tự callback bằng Ordered hoặc @Order

Spring Data Elasticsearch cung cấp EntityCallback để can thiệp vào entity tại những thời điểm xác định trong quá trình ghi và đọc document. Một ứng dụng có thể có nhiều callback cùng xử lý một entity: chuẩn hóa dữ liệu, tạo field tìm kiếm, gán metadata hoặc bổ sung thông tin sau khi đọc.

Khi nhiều callback cùng thuộc một giai đoạn, thứ tự thực thi ảnh hưởng trực tiếp đến kết quả. Ví dụ, callback tạo chuỗi tìm kiếm phải chạy sau callback chuẩn hóa tên; callback tùy chỉnh có thể cần chạy trước hoặc sau callback auditing để sử dụng các trường ngày tạo và ngày sửa.

Spring Data hỗ trợ hai cách chỉ định thứ tự:

- Implement interface org.springframework.core.Ordered và trả về giá trị từ getOrder().
- Gắn annotation org.springframework.core.annotation.Order lên class callback hoặc bean method.

Quy tắc cốt lõi là **giá trị order càng nhỏ thì callback được gọi càng sớm**. Thứ tự này áp dụng trong cùng callback chain; nó không thay đổi thứ tự cố định giữa các giai đoạn của lifecycle.

## 1. EntityCallback trong Spring Data Elasticsearch

EntityCallback là một hook có kiểu dữ liệu gắn với domain type. Spring Data gọi callback ở các checkpoint trong quá trình chuyển entity thành document, ghi document, đọc document và chuyển document thành entity.

Ví dụ một sản phẩm cần các bước trước khi ghi:

1. Chuẩn hóa tên và SKU.
2. Tạo giá trị phục vụ tìm kiếm.
3. Gán metadata auditing như người tạo và thời điểm sửa.
4. Chuyển entity thành Elasticsearch Document và ghi vào index.

Nếu các bước này được đặt trong nhiều callback, ứng dụng cần khai báo thứ tự để bước sau nhìn thấy kết quả của bước trước.

Entity callback có một số đặc điểm:

- Callback gắn với loại entity thông qua generic type, ví dụ BeforeConvertCallback<Product>.
- Callback có thể trả về chính entity hoặc một instance đã thay đổi.
- Các callback được thực thi tuần tự theo thứ tự đã sắp xếp.
- Callback đồng bộ và reactive được phân tách; API đồng bộ chỉ gọi callback đồng bộ, API reactive chỉ gọi callback reactive.
- Callback được đăng ký trong Spring ApplicationContext để implementation của Spring Data tìm thấy.

EntityCallback phù hợp với thay đổi entity đồng bộ và có thứ tự rõ ràng. Đây là lựa chọn phù hợp hơn ApplicationEvent nếu logic bắt buộc phải hoàn tất theo một thứ tự trước khi thao tác lưu tiếp tục.

## 2. Các callback trong lifecycle của Elasticsearch

Spring Data Elasticsearch cung cấp callback cho cả chiều ghi và chiều đọc.

### 2.1. Chiều ghi

Luồng ghi ở mức khái niệm:

~~~text
Entity
  |
  v
BeforeConvertCallback
  |
  v
Entity -> Elasticsearch Document
  |
  v
Ghi document vào Elasticsearch
  |
  v
AfterSaveCallback
  |
  v
Entity được trả về cho caller
~~~

BeforeConvertCallback<T> chạy trước khi entity được chuyển thành Document. Callback có thể trả về entity đã chuẩn hóa hoặc một instance khác. Entity được trả về sẽ là đầu vào cho bước convert tiếp theo.

AfterSaveCallback<T> chạy sau khi document đã được lưu. Callback nhận entity và IndexCoordinates, rồi trả về entity cho luồng gọi. Thay đổi entity trong callback này không tự động ghi lại document lần thứ hai.

### 2.2. Chiều đọc

Luồng đọc:

~~~text
Elasticsearch trả về document
  |
  v
AfterLoadCallback
  |
  v
Document -> Entity
  |
  v
AfterConvertCallback
  |
  v
Entity được trả về cho caller
~~~

AfterLoadCallback<T> nhận Document vừa được đọc và có thể chỉnh sửa document trước khi convert. AfterConvertCallback<T> nhận entity đã được tạo từ document và có thể chỉnh sửa entity trước khi trả về caller.

### 2.3. Callback phase và thứ tự là hai khái niệm khác nhau

| Phase | Thời điểm | Dữ liệu callback nhận hoặc trả |
| --- | --- | --- |
| BeforeConvert | Trước khi convert entity thành Document | Entity |
| AfterSave | Sau khi lưu document | Entity |
| AfterLoad | Sau khi đọc Document, trước khi convert | Document |
| AfterConvert | Sau khi convert Document thành entity | Entity |
| AuditingEntityCallback | Trong phase BeforeConvert | Entity có các trường auditing |

Order chỉ sắp xếp các callback có thể tham gia cùng một callback chain. Ví dụ, order 10 và 20 có thể quyết định hai BeforeConvertCallback chạy theo thứ tự nào. Nó không thể khiến AfterSaveCallback chạy trước BeforeConvertCallback; lifecycle đã xác định phase đó.

### 2.4. Callback nào được Spring Data Elasticsearch hỗ trợ?

Tài liệu Spring Data Elasticsearch hiện hành liệt kê các callback store-specific gồm:

- BeforeConvertCallback
- AfterLoadCallback
- AfterConvertCallback
- AfterSaveCallback
- AuditingEntityCallback

Tài liệu Spring Data Commons có ví dụ tổng quát về BeforeSaveCallback. Không nên suy luận rằng mọi callback trong tài liệu Commons đều được mọi store module hỗ trợ. Với Spring Data Elasticsearch, hãy kiểm tra danh sách callback của đúng phiên bản dependency trước khi thiết kế dựa trên một phase cụ thể.

Các callback reactive tương ứng có tiền tố Reactive, ví dụ ReactiveBeforeConvertCallback và ReactiveAfterSaveCallback.

## 3. Quy tắc sắp xếp: số nhỏ chạy trước

Spring sử dụng order value để sắp xếp các callback. Giá trị càng nhỏ thì độ ưu tiên thực thi càng cao.

| Order value | Ý nghĩa |
| ---: | --- |
| Ordered.HIGHEST_PRECEDENCE | Ưu tiên cao nhất, thường là số nguyên nhỏ nhất |
| -100 | Chạy trước callback có order 0 |
| 0 | Chạy trước callback có order 10 |
| 10 | Chạy sau order 0 |
| 100 | Chạy sau order 10 |
| Ordered.LOWEST_PRECEDENCE | Ưu tiên thấp nhất, thường là số nguyên lớn nhất |

Ví dụ ba callback có thứ tự:

~~~text
NormalizeProductCallback  order = 10
AuditingEntityCallback    order = 100
BuildSearchTextCallback  order = 200
~~~

Kết quả:

~~~text
NormalizeProductCallback
          |
          v
AuditingEntityCallback
          |
          v
BuildSearchTextCallback
          |
          v
Entity được convert thành Document
~~~

Không nên nhầm LOWEST_PRECEDENCE với ưu tiên cao nhất. Tên này có nghĩa callback được xếp ở cuối trong nhóm được sắp xếp theo order.

### 3.1. Giá trị mặc định

Callback không khai báo order thường được xem là có Ordered.LOWEST_PRECEDENCE, vì vậy chạy sau các callback có order value tường minh.

Tài liệu Spring Data Elasticsearch cũng mô tả callback được tạo bằng lambda expression không có typing information để lọc theo entity type và mặc định được gọi cuối. Nếu cần callback chỉ áp dụng cho một loại entity và muốn lọc hiệu quả, nên dùng class hoặc enum có generic type rõ ràng.

### 3.2. Tránh dùng cùng một order value cho logic phụ thuộc nhau

Nếu hai callback cần chạy theo thứ tự xác định, hãy gán hai giá trị khác nhau. Khi hai callback có cùng order, không nên dựa vào thứ tự đăng ký bean, tên class hoặc thứ tự component scan để quyết định callback nào chạy trước.

Ví dụ:

~~~java
@Component
@Order(10)
class NormalizeNameCallback implements BeforeConvertCallback<Product> {
    // ...
}

@Component
@Order(20)
class BuildSearchTextCallback implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Callback tạo search text sẽ chạy sau callback chuẩn hóa tên.

## 4. Cách thứ nhất: implement Ordered

Ordered là interface của Spring Core. Callback triển khai interface này và trả về order value từ phương thức getOrder().

~~~java
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@Component
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product>, Ordered {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setName(entity.getName().trim());
        entity.setSku(entity.getSku().trim().toUpperCase());
        return entity;
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

Trong ví dụ:

- Callback chỉ áp dụng cho entity Product.
- Callback chạy ở phase BeforeConvert.
- Tên và SKU được chuẩn hóa trước khi entity được convert.
- getOrder() trả về 10 để xác định vị trí trong callback chain.

### 4.1. Khi nào nên dùng Ordered?

Dùng Ordered khi:

- Thứ tự là một phần rõ ràng của implementation callback.
- Bạn muốn order được định nghĩa ngay trong class.
- Callback được đóng gói và tái sử dụng như một thành phần độc lập.
- Giá trị order có thể được tính hoặc lấy từ cấu hình trong implementation.

Một class chỉ cần implement Ordered nếu nó thực sự cần thứ tự tường minh. Callback không phụ thuộc callback khác có thể giữ mặc định.

### 4.2. Trả về entity mới cho immutable type

Không phải entity nào cũng mutable. Với record hoặc immutable class, callback nên tạo instance mới thay vì thay đổi field.

~~~java
public record Product(
    String id,
    String name,
    String sku
) {}

@Component
public class NormalizeImmutableProductCallback
        implements BeforeConvertCallback<Product>, Ordered {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        return new Product(
            entity.id(),
            entity.name().trim(),
            entity.sku().trim().toUpperCase()
        );
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

Giá trị callback trả về mới là entity được chuyển đổi và lưu. Nếu callback tạo instance mới nhưng trả về instance cũ, thay đổi sẽ không được sử dụng.

## 5. Cách thứ hai: dùng @Order

Order là annotation của Spring Core. Có thể đặt annotation lên class callback hoặc lên phương thức Bean tạo callback.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@Component
@Order(20)
public class BuildSearchTextCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setSearchText(
            entity.getName() + " " + entity.getSku()
        );
        return entity;
    }
}
~~~

Callback này chạy ở order 20. Nếu callback chuẩn hóa có order 10, callback tạo search text nhận entity đã được chuẩn hóa.

### 5.1. Đặt Order trên bean method

Nếu callback được khai báo trong configuration class:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;

@Configuration
public class ProductCallbackConfiguration {

    @Bean
    @Order(20)
    BeforeConvertCallback<Product> buildSearchTextCallback() {
        return (entity, index) -> {
            entity.setSearchText(
                entity.getName() + " " + entity.getSku()
            );
            return entity;
        };
    }
}
~~~

Đây là callback lambda nên không có generic type information ở runtime giống một class implementation cụ thể. Tài liệu Spring Data khuyến nghị dùng class hoặc enum nếu cần type filtering hiệu quả. Với ứng dụng có nhiều entity type và nhiều callback, class riêng thường dễ đọc và dễ kiểm thử hơn.

### 5.2. Order không điều khiển bean creation

Order quyết định thứ tự sử dụng các bean trong những cơ chế có hỗ trợ order, chẳng hạn entity callback chain. Nó không có nghĩa Spring phải khởi tạo bean theo thứ tự đó.

Không dùng Order thay cho:

- DependsOn khi thật sự cần quy định quan hệ khởi tạo bean.
- Dependency injection khi một bean cần bean khác.
- Transaction hoặc synchronization khi cần điều khiển thứ tự giao dịch.
- Cơ chế ordering riêng của event listener hoặc task executor.

Trong EntityCallback, Order được dùng để sắp xếp callback khi Spring Data gọi callback chain.

## 6. Chọn Ordered hay Order?

Hai cách đều biểu diễn cùng một khái niệm order. Chọn cách nào tùy theo cách bạn muốn quản lý cấu hình.

| Tiêu chí | Ordered | Order |
| --- | --- | --- |
| Cách khai báo | Implement interface | Annotation trên class hoặc bean method |
| Vị trí giá trị | getOrder() | Giá trị annotation |
| Phù hợp | Order thuộc implementation | Order là metadata cấu hình |
| Có thể override logic | Có thể trả giá trị từ method | Giá trị khai báo tĩnh |
| Độ rõ trong class | Thấy ngay qua interface và method | Thấy ngay trên annotation |

Ví dụ cùng một mục đích:

~~~java
class FirstCallback implements BeforeConvertCallback<Product>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        return entity;
    }
}
~~~

~~~java
@Component
@Order(10)
class SecondCallback implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        return entity;
    }
}
~~~

Không cần triển khai cả Ordered và Order với hai giá trị khác nhau trên cùng callback. Hãy chọn một nguồn order để tránh gây nhầm lẫn cho người bảo trì.

## 7. Thứ tự callback auditing

Spring Data Elasticsearch tích hợp auditing qua AuditingEntityCallback. Callback này chạy ở phase BeforeConvert và đánh dấu các trường auditing trước khi entity được convert thành document.

Các annotation thường dùng:

| Annotation | Ý nghĩa |
| --- | --- |
| CreatedDate | Thời điểm entity được tạo |
| LastModifiedDate | Thời điểm entity được cập nhật gần nhất |
| CreatedBy | Người tạo entity |
| LastModifiedBy | Người cập nhật gần nhất |

Ví dụ entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;
    private String sku;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    // Constructors, getters và setters
}
~~~

### 7.1. Bật Elasticsearch auditing

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

Ví dụ trả về auditor cố định để minh họa. Trong ứng dụng thực tế, AuditorAware thường lấy user hiện tại từ security context hoặc một context thực thi đáng tin cậy. Với job nền, có thể trả về tài khoản service phù hợp.

Nếu chỉ cần ngày tạo và ngày sửa, auditing vẫn có thể cập nhật các trường date mà không cần AuditorAware. Muốn dùng CreatedBy và LastModifiedBy, cần cung cấp nguồn auditor.

### 7.2. Order mặc định của AuditingEntityCallback

Trong tài liệu Spring Data Elasticsearch hiện hành, AuditingEntityCallback có order 100. Các callback store-specific thông thường như BeforeConvertCallback mặc định có Ordered.LOWEST_PRECEDENCE.

Điều đó có nghĩa:

- Callback có order 50 chạy trước auditing.
- Auditing callback chạy ở order 100.
- Callback có order 150 chạy sau auditing.
- Callback không khai báo order thường chạy ở cuối callback chain.

Ví dụ:

~~~text
NormalizeProductCallback     Order(50)
             |
             v
AuditingEntityCallback       order 100
             |
             v
BuildAuditSearchTextCallback Order(150)
             |
             v
Convert entity -> Document
~~~

Nếu callback tạo dữ liệu phụ thuộc createdAt, updatedAt, createdBy hoặc updatedBy, hãy đặt order sau auditing. Nếu callback thay đổi dữ liệu đầu vào mà auditing không phụ thuộc, có thể đặt nó trước auditing.

Giá trị order 100 là chi tiết triển khai của auditing callback trong các phiên bản được tài liệu tham chiếu. Nếu logic của ứng dụng phụ thuộc chính xác vào con số này, hãy xác nhận Javadoc hoặc source của phiên bản Spring Data Elasticsearch đang dùng.

### 7.3. Ví dụ callback sau auditing

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@Component
@Order(150)
public class BuildProductAuditTextCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setAuditText(
            entity.getCreatedBy() + " " +
            entity.getUpdatedBy() + " " +
            entity.getUpdatedAt()
        );
        return entity;
    }
}
~~~

Vì order 150 lớn hơn order 100 của auditing callback, callback này chạy sau khi auditing đã đánh dấu entity. Nếu chạy trước auditing, các trường auditor có thể chưa được gán ở lần lưu hiện tại.

Chỉ tạo field tổng hợp từ audit metadata nếu có yêu cầu tìm kiếm hoặc hiển thị rõ ràng. Không nên sao chép các trường này một cách máy móc.

## 8. Callback chain truyền kết quả như thế nào?

Các callback trong cùng chain được gọi tuần tự. Kết quả của callback trước được dùng làm đầu vào cho callback tiếp theo.

Giả sử có:

- Callback A: trim tên.
- Callback B: chuyển tên thành lowercase.
- Callback C: tạo search text.

Với order 10, 20 và 30:

~~~text
Input: "  Mechanical Keyboard  "
                |
                v
       A: trim whitespace
                |
                v
       "Mechanical Keyboard"
                |
                v
       B: lowercase
                |
                v
       "mechanical keyboard"
                |
                v
       C: build search text
                |
                v
       Entity cuối cùng
                |
                v
       Convert và persist
~~~

Callback phải trả về instance đã thay đổi. Nếu callback mutate entity rồi trả về entity đó, thay đổi được truyền tiếp. Với immutable object, trả về instance mới.

### 8.1. Ví dụ nhiều callback

Callback chuẩn hóa:

~~~java
@Component
@Order(10)
class NormalizeProductName implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        entity.setName(entity.getName().trim());
        return entity;
    }
}
~~~

Callback tạo slug:

~~~java
@Component
@Order(20)
class BuildProductSlug implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        entity.setSlug(toSlug(entity.getName()));
        return entity;
    }

    private String toSlug(String value) {
        return value.toLowerCase().replace(" ", "-");
    }
}
~~~

Callback tạo search text:

~~~java
@Component
@Order(30)
class BuildProductSearchText implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        entity.setSearchText(
            entity.getName() + " " + entity.getSku() + " " + entity.getSlug()
        );
        return entity;
    }
}
~~~

Thứ tự này bảo đảm slug được tạo từ tên đã trim, còn search text sử dụng tên và slug đã được tạo trước đó.

### 8.2. Một class có thể triển khai nhiều callback interface

Một component có thể triển khai nhiều callback interface:

~~~java
@Component
@Order(100)
class ProductLifecycleCallbacks
        implements BeforeConvertCallback<Product>,
                   AfterConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        // Chuẩn bị dữ liệu trước khi ghi.
        return entity;
    }

    @Override
    public Product onAfterConvert(
            Product entity,
            Document document,
            IndexCoordinates index) {
        // Hoàn thiện entity sau khi đọc.
        return entity;
    }
}
~~~

Order của bean được dùng khi callback tương ứng được sắp xếp trong phase của nó. Thứ tự BeforeConvert và AfterConvert vẫn thuộc hai chain khác nhau.

## 9. Callback type và domain type

Generic type giúp Spring Data xác định callback áp dụng cho loại entity nào:

~~~java
BeforeConvertCallback<Product>
BeforeConvertCallback<Order>
AfterConvertCallback<Customer>
~~~

Callback BeforeConvertCallback<Product> được thiết kế để xử lý Product. Nó không nên chứa logic dành cho mọi loại entity.

Nếu callback cần xử lý nhiều entity type, có thể:

- Tạo callback riêng cho từng type.
- Dùng một interface chung cho nhóm entity có cùng hành vi.
- Tạo một component triển khai nhiều callback interface có generic type cụ thể.

Không nên dùng lambda không có type information trong hệ thống có nhiều callback và nhiều domain type nếu điều đó khiến framework phải kiểm tra callback với các entity không phù hợp.

### 9.1. IndexCoordinates trong callback

Callback Elasticsearch nhận IndexCoordinates để biết index hoặc các index mà thao tác đang hướng tới:

~~~java
@Override
public Product onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    if (index.getIndexNames().length == 0) {
        return entity;
    }

    // Có thể áp dụng quy tắc theo index nếu thực sự cần.
    return entity;
}
~~~

Trong nhiều trường hợp, callback nên phụ thuộc vào domain type thay vì tên index. Dùng index coordinates khi một entity được lưu vào nhiều index hoặc khi có quy tắc đặc biệt theo đích ghi.

## 10. Đăng ký callback trong ApplicationContext

Spring Data lấy các EntityCallback bean từ ApplicationContext. Có thể đăng ký bằng component scanning:

~~~java
@Component
@Order(10)
class NormalizeProductCallback implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Hoặc đăng ký bằng configuration:

~~~java
@Configuration
class ProductCallbacksConfiguration {

    @Bean
    @Order(10)
    NormalizeProductCallback normalizeProductCallback() {
        return new NormalizeProductCallback();
    }
}
~~~

Không tạo một callback object mới trong repository method hoặc service mỗi lần save. Callback nên là bean được quản lý bởi Spring để framework tìm thấy và sắp xếp.

### 10.1. Template và repository

Các template implementation của Spring Data thường có quyền truy cập ApplicationContext và nhận callback beans. Repository sử dụng template/operations tương ứng cũng đi qua cơ chế mapping và callback được cấu hình.

Nếu tự tạo ElasticsearchTemplate hoặc ElasticsearchOperations thủ công, cần bảo đảm cấu hình callback được gắn vào template. Một bean callback nằm trong context khác hoặc không được đăng ký sẽ không tự động được gọi.

### 10.2. Gọi Java API Client trực tiếp

Nếu gọi trực tiếp:

~~~java
elasticsearchClient.index(request);
~~~

thì thao tác không đi qua Spring Data entity mapping lifecycle. Vì vậy, không nên kỳ vọng BeforeConvertCallback, AfterSaveCallback hoặc auditing callback của Spring Data tự chạy.

Nếu một luồng ingestion dùng raw Elasticsearch Java API Client hoặc Bulk REST API, ứng dụng phải gọi logic chuẩn hóa/auditing tương ứng ở tầng service/projector hoặc sử dụng một đường ghi Spring Data có hỗ trợ callback.

Điều này đặc biệt quan trọng khi một phần ứng dụng ghi bằng repository còn phần khác ghi bằng raw bulk client. Nếu hai luồng không dùng chung quy tắc, dữ liệu có thể có audit fields hoặc search fields không nhất quán.

## 11. Callback và ApplicationEvent không giống nhau

Spring Data có thể phát store-specific events như BeforeSaveEvent. EntityCallback là một cơ chế riêng:

| EntityCallback | ApplicationEvent |
| --- | --- |
| Có generic type gắn với domain type | Event có kiểu riêng theo sự kiện |
| Được gọi tại checkpoint lifecycle xác định | Được publish qua ApplicationEventMulticaster |
| Hỗ trợ callback chain theo order | Listener có cơ chế order riêng |
| Trả về entity hoặc document đã thay đổi | Event listener không phải lúc nào cũng có cơ chế trả entity mới vào luồng lưu |
| Có API đồng bộ và reactive riêng | Có thể được xử lý bất đồng bộ tùy cấu hình |

Nếu dùng asynchronous event multicaster, listener có thể chạy trên thread khác và thứ tự xử lý không còn phù hợp để làm bước chuẩn hóa bắt buộc trước khi lưu.

EntityCallback được thiết kế để xử lý entity tại lifecycle checkpoint và đảm bảo thứ tự thực thi trong chain tương ứng. Event phù hợp cho thông báo, tích hợp hoặc side effect tùy kiến trúc.

## 12. Reactive callback có thứ tự riêng

Spring Data Elasticsearch có API reactive với các callback interface tương ứng:

- ReactiveBeforeConvertCallback<T>
- ReactiveAfterLoadCallback<T>
- ReactiveAfterConvertCallback<T>
- ReactiveAfterSaveCallback<T>
- ReactiveAuditingEntityCallback

Callback reactive trả về Publisher thay vì entity trực tiếp. Thứ tự vẫn được áp dụng trong reactive callback chain, nhưng reactive API chỉ xem các reactive callback.

Ví dụ minh họa:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.core.Ordered;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ReactiveNormalizeProductCallback
        implements ReactiveBeforeConvertCallback<Product>, Ordered {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setName(entity.getName().trim());
        return Mono.just(entity);
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

Ví dụ dùng Mono.just. Trong ứng dụng thực tế, nếu callback gọi dịch vụ bất đồng bộ, hãy trả về publisher tương ứng và không block trong callback.

Không implement callback đồng bộ rồi kỳ vọng ReactiveElasticsearchOperations tự gọi nó. Hai API callback được tách biệt để tránh trộn semantics đồng bộ và reactive.

## 13. Xử lý exception trong callback

Callback là một phần của lifecycle operation. Nếu callback ném exception, luồng xử lý hiện tại có thể dừng tại phase đó.

| Phase phát sinh lỗi | Hệ quả thường gặp |
| --- | --- |
| BeforeConvert | Entity chưa được convert/ghi; thao tác lưu thất bại |
| AfterLoad | Document đã được đọc nhưng không thể tiếp tục pipeline đọc bình thường |
| AfterConvert | Document đã convert nhưng entity không được trả về bình thường |
| AfterSave | Document có thể đã được ghi trước khi callback ném lỗi; caller vẫn có thể nhận exception |

### 13.1. Không dùng AfterSave để kiểm tra trước khi ghi

Nếu một điều kiện bắt buộc phải được kiểm tra trước khi document được lưu, đặt logic trong BeforeConvert hoặc tầng service trước khi gọi save.

Nếu AfterSaveCallback ném exception, không nên giả định Elasticsearch đã rollback document vừa ghi. Caller có thể thấy lỗi dù document đã tồn tại trong index.

### 13.2. Không nuốt exception tùy tiện

Không nên bắt mọi exception rồi trả entity cũ như thể thao tác thành công. Nếu callback tạo dữ liệu bắt buộc cho search, bỏ qua lỗi có thể khiến document thiếu field và tạo ra lỗi khó phát hiện.

Nếu callback chỉ thực hiện side effect không bắt buộc, cân nhắc tách side effect sang event/outbox hoặc một luồng riêng có retry thay vì chặn thao tác lưu chính.

## 14. Kiểm thử thứ tự callback

Thứ tự callback nên được kiểm tra ở hai mức:

1. Unit test cho từng callback, xác nhận nó biến đổi entity đúng.
2. Integration test với Spring ApplicationContext và Elasticsearch operations, xác nhận callback được đăng ký và chạy theo thứ tự dự kiến.

### 14.1. Unit test cho callback

~~~java
@Test
void shouldTrimProductNameBeforeConvert() {
    Product product = new Product();
    product.setName("  Keyboard  ");

    Product result = callback.onBeforeConvert(
        product,
        IndexCoordinates.of("products")
    );

    assertThat(result.getName()).isEqualTo("Keyboard");
}
~~~

### 14.2. Kiểm tra thứ tự bằng trace

Trong integration test, mỗi callback có thể thêm một marker vào một field test-only hoặc ghi vào một collector được inject:

~~~text
normalize
auditing
build-search-text
~~~

Sau khi save entity, xác nhận marker theo thứ tự mong đợi. Không dùng thứ tự component scanning làm assertion.

Một cách khác là kiểm tra kết quả cuối cùng: search text đã dùng tên chuẩn hóa và audit fields đã được gán trước khi convert.

### 14.3. Kiểm thử auditing

Với EnableElasticsearchAuditing, kiểm tra:

- Insert mới có createdAt và createdBy.
- Update giữ nguyên createdAt và createdBy.
- Update thay đổi updatedAt và updatedBy.
- Callback chạy sau auditing có thể đọc được các giá trị cần thiết.
- Entity không được đánh dấu auditable không bị thay đổi ngoài dự kiến.

Nếu dùng clock hoặc auditor provider tùy chỉnh, inject implementation có thể kiểm soát để test không phụ thuộc thời gian hoặc user thực tế.

## 15. Lỗi thường gặp khi dùng Ordered và Order

**Cho rằng số order lớn hơn sẽ chạy trước.** Spring dùng thứ tự tăng dần; số nhỏ hơn chạy trước.

**Nhầm LOWEST_PRECEDENCE là ưu tiên cao nhất.** Giá trị này đặt callback ở cuối nhóm được sắp xếp.

**Cho rằng Order điều khiển bean creation.** Annotation sắp xếp callback khi sử dụng; nó không điều khiển thời điểm Spring khởi tạo bean.

**Đặt cùng order cho hai callback phụ thuộc nhau.** Thứ tự giữa chúng không nên được coi là hợp đồng. Gán giá trị khác nhau.

**Đặt callback tạo search field trước callback chuẩn hóa.** Search field có thể chứa dữ liệu chưa chuẩn hóa. Sắp xếp pipeline theo dependency dữ liệu.

**Cho rằng auditing chạy cuối.** Auditing callback có order 100 trong tài liệu Spring Data Elasticsearch hiện hành; callback mặc định LOWEST_PRECEDENCE thường chạy sau auditing.

**Không khai báo EnableElasticsearchAuditing.** Entity có annotation auditing nhưng auditing infrastructure chưa được bật nên các trường không được cập nhật như mong đợi.

**Không cung cấp AuditorAware khi cần CreatedBy/LastModifiedBy.** Các trường actor cần một nguồn cung cấp auditor.

**Dùng callback đồng bộ cho reactive operations.** Reactive API chỉ xét reactive callbacks. Implement đúng loại callback.

**Gọi raw Java API Client nhưng chờ callback Spring Data chạy.** Raw client bỏ qua entity mapping lifecycle của Spring Data. Gọi logic tương ứng ở tầng ứng dụng hoặc dùng operations phù hợp.

**Cho rằng AfterSave có thể sửa document đã lưu.** Callback chạy sau khi persist. Thay đổi entity trả về không tự ghi lại document.

**Dùng callback cho side effect cần bảo đảm giao dịch.** Callback không biến Elasticsearch và hệ thống ngoài thành một distributed transaction. Dùng outbox hoặc quy trình bền vững cho side effect.

**Dùng lambda cho mọi callback.** Lambda không cung cấp type information rõ như class generic và có thể làm giảm hiệu quả lọc callback theo domain type. Dùng class khi cần type filtering.

**Dựa vào ví dụ callback tổng quát của Spring Data Commons mà không kiểm tra hỗ trợ Elasticsearch.** Mỗi store module có tập callback riêng. Đối chiếu danh sách của đúng phiên bản.

## 16. Quy trình thiết kế thứ tự callback

Khi ứng dụng có nhiều callback:

1. Xác định lifecycle phase cần can thiệp.
2. Chọn callback interface được Spring Data Elasticsearch hỗ trợ trong phiên bản dự án.
3. Xác định callback nào phụ thuộc kết quả callback khác.
4. Vẽ thứ tự dữ liệu cần đi qua, ví dụ normalize, auditing, build search fields.
5. Gán order value tăng dần theo dependency.
6. Dùng Ordered hoặc Order; không khai báo hai giá trị mâu thuẫn.
7. Đăng ký callback trong ApplicationContext.
8. Kiểm tra callback generic type phù hợp entity.
9. Nếu dùng auditing, xác nhận EnableElasticsearchAuditing và auditor provider.
10. Nếu dùng reactive operations, triển khai reactive callback tương ứng.
11. Kiểm tra đường ghi có đi qua Spring Data operations hay raw client.
12. Viết test xác nhận thứ tự và kết quả cuối cùng.

Ví dụ pipeline ghi Product:

~~~text
BeforeConvert callback chain
    |
    +-- order 10: normalize name and SKU
    |
    +-- order 100: AuditingEntityCallback
    |
    +-- order 150: build search/audit fields
    |
    v
Convert Product to Document
    |
    v
Persist to Elasticsearch
    |
    v
AfterSave callback chain
~~~

Không cần tạo callback cho mọi thao tác. Chỉ tách callback khi có một trách nhiệm rõ ràng, có thể tái sử dụng hoặc cần được kiểm soát thứ tự độc lập.

## 17. Tài liệu tham khảo

- [Spring Data Elasticsearch - Entity Callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html): callback lifecycle, đăng ký callback, order và auditing callback.
- [Spring Data Elasticsearch API - BeforeConvertCallback](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/event/BeforeConvertCallback.html): chữ ký và thời điểm gọi BeforeConvertCallback.
- [Spring Data Elasticsearch - Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html): bật auditing và cấu hình auditor.
- [Spring Framework - Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): quy tắc order value và các hằng số precedence.
- [Spring Framework - Order](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html): annotation chỉ định thứ tự ưu tiên.
- [Spring Data Commons - Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): callback chain, synchronous/reactive callbacks và cách đăng ký bean.

Các chữ ký callback, callback interface được hỗ trợ và chi tiết auditing có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy kiểm tra tài liệu/Javadoc khớp với dependency của dự án. Quy tắc sắp xếp vẫn là: order value nhỏ chạy trước; thứ tự này chỉ sắp xếp callback trong cùng lifecycle chain, không thay đổi thứ tự giữa các phase.
