# Cơ chế tạo proxy và triển khai Repository mặc định

Spring Data Elasticsearch cho phép khai báo repository dưới dạng interface mà không cần tự viết implementation cho các thao tác CRUD thông thường. Ví dụ, một interface kế thừa `ElasticsearchRepository<ProductDocument, String>` có thể được inject vào service và sử dụng các phương thức `save`, `findById`, `findAll` hoặc `deleteById`.

Điều đó không có nghĩa Spring tạo mã nguồn Java cho từng repository trong lúc biên dịch. Khi ứng dụng khởi động, hạ tầng repository của Spring Data phát hiện interface, tạo factory, xây dựng implementation nền và dùng cơ chế proxy để định tuyến lời gọi phương thức. Proxy chuyển lời gọi tới đúng thành phần: implementation CRUD mặc định, query executor, custom repository fragment hoặc default method của interface.

Hiểu cơ chế này giúp giải thích vì sao chỉ cần khai báo interface là đã có repository bean, một phương thức `findBySku` có thể tự tạo truy vấn, và khi cần có thể bổ sung logic riêng mà không phải tự triển khai toàn bộ repository.

## 1. Repository interface và implementation mặc định

Giả sử ứng dụng quản lý sản phẩm:

~~~java
import java.util.Optional;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

`ProductRepository` chỉ là interface. Nó khai báo kiểu document là `ProductDocument` và kiểu ID là `String`, đồng thời kế thừa các thao tác repository mà Spring Data cung cấp.

Document tương ứng có thể được khai báo:

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

Service có thể inject interface:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductDocument save(ProductDocument product) {
        return repository.save(product);
    }
}
~~~

Không có lớp `ProductRepositoryImpl` do người phát triển viết trong ví dụ này. Spring Data tạo một bean tương thích với interface tại runtime. Bean đó là proxy được cấu hình để định tuyến từng lời gọi.

### 1.1. Các phương thức đến từ đâu?

Repository thường kết hợp ba nhóm phương thức:

| Nhóm phương thức | Ví dụ | Thành phần xử lý |
| --- | --- | --- |
| CRUD và paging/sorting cơ bản | `save`, `findById`, `deleteById`, `findAll` | Implementation nền, thường là `SimpleElasticsearchRepository` |
| Query method | `findBySku`, `findByNameContaining` | Query lookup strategy và query executor |
| Phương thức tùy chỉnh | `searchWithBusinessRules` | Custom repository fragment hoặc implementation được đăng ký |

Interface cũng có thể khai báo `default` method. Những phương thức này có phần thân ngay trong interface và được hạ tầng proxy gọi theo cơ chế default method invocation.

## 2. Điều kiện để Spring phát hiện repository

Spring cần biết package nào chứa repository interface và cách tạo factory bean cho chúng.

### 2.1. Component scanning và repository scanning

Trong ứng dụng Spring Boot thông thường, lớp `@SpringBootApplication` đặt ở package gốc. Spring Boot auto-configuration cùng repository scanning sẽ phát hiện các repository trong phạm vi package được cấu hình.

Ví dụ cấu trúc:

~~~text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── ProductDocument.java
│   ├── ProductRepository.java
│   └── ProductService.java
└── config
~~~

Lớp khởi động:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Nếu repository nằm ngoài vùng package được quét, có thể khai báo rõ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.product"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Trong ứng dụng Spring Boot đã có auto-configuration, thường không cần thêm `@EnableElasticsearchRepositories` chỉ để lặp lại cấu hình mặc định. Annotation này hữu ích khi cần chỉ định package, factory bean, repository base class hoặc bootstrap mode.

### 2.2. @EnableElasticsearchRepositories làm gì?

`@EnableElasticsearchRepositories` nhập cơ chế đăng ký repository của Spring Data Elasticsearch vào application context. Ở mức khái quát, annotation này:

1. Đăng ký registrar chuyên biệt cho Elasticsearch.
2. Registrar đọc các thuộc tính như `basePackages`, postfix của implementation, factory bean class, base class và bootstrap mode.
3. Hạ tầng repository quét các interface phù hợp.
4. Mỗi repository được đăng ký thành một bean definition dùng factory bean của Spring Data Elasticsearch.
5. Factory bean tạo repository instance và proxy khi bean được khởi tạo.

Các lớp registrar, extension và factory là chi tiết nội bộ của framework. Tên lớp hoặc cách tổ chức có thể thay đổi theo phiên bản Spring Data, nhưng vai trò chung của quá trình đăng ký vẫn là tìm interface và cấu hình factory để tạo bean.

## 3. Các thành phần chính trong quá trình tạo repository

Hạ tầng repository được xây dựng trên Spring Data Commons. Spring Data Elasticsearch cung cấp phần mở rộng để hiểu document, query và thao tác Elasticsearch.

### 3.1. RepositoryConfigurationExtension

Phần mở rộng cấu hình của module Elasticsearch mô tả các thành phần đặc thù cần dùng khi đăng ký repository, chẳng hạn factory bean class và các quy tắc cấu hình cho repository interface.

Nhờ extension, Spring Data Commons có thể dùng cùng một cơ chế tổng quát cho nhiều module như JPA, MongoDB và Elasticsearch, trong khi mỗi module vẫn cung cấp implementation riêng.

### 3.2. RepositoryFactoryBeanSupport

Factory bean là đối tượng Spring quản lý để tạo repository bean. Trong hạ tầng Spring Data, `RepositoryFactoryBeanSupport` cung cấp phần lớn quy trình chung:

- Nhận repository interface cần tạo.
- Nhận cấu hình về entity information, custom implementation và repository base class.
- Tạo repository factory tương ứng với module.
- Khởi tạo factory và lấy repository proxy.
- Trả proxy cho Spring container dưới kiểu interface mà ứng dụng inject.

Với Elasticsearch, factory bean chuyên biệt tạo ra factory dành cho repository Elasticsearch.

### 3.3. RepositoryFactorySupport

`RepositoryFactorySupport` là lớp nền quan trọng của Spring Data Commons. Nó cung cấp thuật toán chung để tạo proxy cho repository. Factory chuyên biệt của Elasticsearch kế thừa hoặc sử dụng cơ chế này và cung cấp phần phụ thuộc vào Elasticsearch.

Các trách nhiệm chính gồm:

- Xây dựng repository metadata từ interface.
- Tạo target repository và kết hợp repository fragments.
- Chuẩn bị query lookup strategy cho các query method.
- Cấu hình proxy và các interceptor/advisor.
- Áp dụng các extension hoặc post-processor dành cho repository.

### 3.4. ElasticsearchRepositoryFactory

Factory của Elasticsearch biết cách tạo entity information, target repository và query implementation phù hợp với Elasticsearch. Khi tạo repository mặc định, nó sử dụng `SimpleElasticsearchRepository` làm implementation nền.

Factory cũng cung cấp query lookup strategy chuyên biệt để tạo truy vấn Elasticsearch từ tên phương thức hoặc khai báo query.

### 3.5. SimpleElasticsearchRepository

`SimpleElasticsearchRepository<T, ID>` là implementation nền cho các thao tác repository Elasticsearch. Nó làm việc với `ElasticsearchOperations` và metadata của entity để thực hiện các hoạt động như:

- Lưu một entity hoặc nhiều entity.
- Tìm document theo ID.
- Tìm nhiều document và trả về kết quả phù hợp với kiểu repository.
- Xóa document.
- Đếm document.
- Xử lý các biến thể CRUD và paging/sorting mà interface kế thừa yêu cầu.

Các phương thức cụ thể có thể khác giữa phiên bản Spring Data Elasticsearch. Nên xem Javadoc của đúng phiên bản dự án khi cần mở rộng hoặc override implementation nền.

## 4. Quy trình tạo repository proxy

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["@EnableElasticsearchRepositories / Boot auto-configuration"] --> B["Repository registrar"]
    B --> C["Quét repository interfaces"]
    C --> D["Đăng ký repository FactoryBean"]
    D --> E["ElasticsearchRepositoryFactoryBean"]
    E --> F["ElasticsearchRepositoryFactory"]
    F --> G["Tạo entity metadata và target repository"]
    G --> H["SimpleElasticsearchRepository + repository fragments"]
    H --> I["ProxyFactory và interceptors"]
    I --> J["Repository proxy bean"]
    J --> K["Inject vào service"]
~~~

Có thể chia quá trình thành các bước chi tiết:

1. **Phát hiện interface.** Registrar tìm interface repository trong package đã cấu hình. Interface phải có cấu trúc hợp lệ và gắn với domain type có thể được Spring Data nhận diện.
2. **Đăng ký factory bean.** Spring container nhận bean definition cho repository. Bean definition lưu repository interface cùng các tùy chọn cần thiết.
3. **Khởi tạo factory.** Factory bean tạo `ElasticsearchRepositoryFactory` và cung cấp các phụ thuộc như `ElasticsearchOperations`, mapping context và custom conversions thông qua cấu hình của module.
4. **Tạo metadata.** Factory đọc generic type của repository để xác định domain class và ID class, rồi xây dựng entity information.
5. **Tạo target.** Factory tạo implementation nền, thông thường là `SimpleElasticsearchRepository`, và kết hợp các custom repository fragments nếu có.
6. **Tạo proxy.** `RepositoryFactorySupport` cấu hình `ProxyFactory`, gắn target và các interceptor/advisor để định tuyến lời gọi phương thức.
7. **Đưa bean vào context.** Proxy được trả về như implementation của repository interface. Service chỉ cần phụ thuộc vào interface.

Proxy thường là JDK dynamic proxy vì repository được khai báo dưới dạng interface. Cơ chế proxy cụ thể còn phụ thuộc cấu hình AOP và phiên bản framework; không nên dựa vào tên lớp proxy nội bộ trong mã nghiệp vụ.

## 5. Proxy định tuyến lời gọi phương thức như thế nào?

Proxy không thực hiện mọi thao tác theo cùng một cách. Các interceptor nhận lời gọi và xác định phương thức thuộc nhóm nào.

### 5.1. Phương thức CRUD đi tới implementation nền

Khi gọi:

~~~java
repository.save(product);
repository.findById("sku-1001");
repository.deleteById("sku-1001");
~~~

Proxy định tuyến các phương thức CRUD đã được kế thừa tới phần implementation nền trong repository composition, thường là `SimpleElasticsearchRepository`.

Implementation nền dùng `ElasticsearchOperations` để chuyển entity thành document representation và thực hiện thao tác với Elasticsearch. Nó không cần biết service nào đã gọi phương thức.

### 5.2. Query method đi qua QueryExecutorMethodInterceptor

Với phương thức:

~~~java
Optional<ProductDocument> findBySku(String sku);
~~~

Spring Data phân tích tên phương thức và tạo query implementation. `QueryExecutorMethodInterceptor` là một phần của hạ tầng proxy xử lý lời gọi query method. Query lookup strategy quyết định query được lấy từ khai báo hay được tạo từ tên phương thức.

Sau khi có query implementation, lời gọi được thực thi thông qua hạ tầng truy vấn của Spring Data Elasticsearch và `ElasticsearchOperations`/query execution phù hợp.

### 5.3. Custom fragment được gọi qua repository composition

Nếu repository kết hợp một custom fragment, proxy có thể định tuyến phương thức của fragment tới implementation tương ứng. Các fragment được kết hợp với implementation nền thành một repository composition.

Điều này giúp nhóm phát triển mở rộng repository theo từng phần nhỏ thay vì viết lại tất cả CRUD.

### 5.4. Default method được gọi trên interface

Java interface có thể chứa `default` method:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    default boolean existsBySku(String sku) {
        return findBySku(sku).isPresent();
    }
}
~~~

`existsBySku` có phần thân trong interface. Proxy sử dụng cơ chế gọi default method để thực thi phần thân đó. Khi default method gọi `findBySku`, lời gọi tiếp tục đi qua repository proxy và query method interceptor.

### 5.5. Object methods

Các phương thức như `toString`, `equals` và `hashCode` là phương thức của `Object`, không phải query method. Proxy có cách xử lý riêng cho nhóm phương thức này. Không nên dùng kết quả `toString()` của proxy để suy luận implementation cụ thể hoặc trạng thái kết nối Elasticsearch.

## 6. Query lookup strategy

Query lookup strategy xác định cách Spring Data tìm implementation cho một query method.

Ba chế độ phổ biến của Spring Data Commons:

| Strategy | Cách hoạt động |
| --- | --- |
| `CREATE` | Tạo query từ tên phương thức |
| `USE_DECLARED_QUERY` | Yêu cầu query được khai báo; không tự suy luận từ tên nếu không có khai báo |
| `CREATE_IF_NOT_FOUND` | Ưu tiên query khai báo; nếu không có thì tạo query từ tên phương thức |

Trong nhiều cấu hình, `CREATE_IF_NOT_FOUND` là lựa chọn mặc định. Cấu hình cụ thể và query annotation được hỗ trợ phụ thuộc phiên bản module.

### 6.1. Derived query từ tên phương thức

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    List<ProductDocument> findByNameContaining(String text);

    List<ProductDocument> findByPriceBetween(
        double minimum,
        double maximum
    );
}
~~~

Spring Data phân tích tên phương thức thành các phần:

- Tên property, ví dụ `sku`, `name`, `price`.
- Predicate, ví dụ `Containing`, `Between`.
- Kết hợp điều kiện bằng `And`, `Or`.
- Một số tùy chọn như sort, top/first hoặc phân trang nếu được hỗ trợ.

Tên property phải tương ứng với thuộc tính domain mà Spring Data nhận diện. Việc tên field trong Elasticsearch khác tên property Java được xử lý thông qua mapping metadata, chẳng hạn `@Field(name = "...")`.

Không phải mọi keyword derived query của module khác đều được Elasticsearch hỗ trợ với semantics giống nhau. Hãy tham khảo danh sách keyword của đúng phiên bản Spring Data Elasticsearch và kiểm thử query được tạo ra.

### 6.2. Query khai báo bằng @Query

Với truy vấn Elasticsearch phức tạp hơn, có thể khai báo query JSON:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("{\"term\": {\"sku\": \"?0\"}}")
    List<ProductDocument> searchExactSku(String sku);
}
~~~

`@Query` cho phép cung cấp query DSL JSON và bind tham số theo quy tắc của Spring Data Elasticsearch. Cú pháp placeholder, hỗ trợ sort/page và khả năng khai báo query phụ thuộc API của phiên bản. Với truy vấn động phức tạp, có thể dùng `ElasticsearchOperations` thay vì cố nhồi mọi logic vào chuỗi JSON.

### 6.3. Query method không phải implementation CRUD

`findBySku` không được xử lý bằng cách gọi một phương thức có sẵn trong `SimpleElasticsearchRepository`. Nó được tạo bởi query lookup strategy. Ngược lại, `findById` là thao tác CRUD nền. Hai phương thức cùng bắt đầu bằng `find` nhưng thuộc hai đường xử lý khác nhau.

## 7. Implementation mặc định làm việc với Elasticsearch như thế nào?

`SimpleElasticsearchRepository` là adapter giữa repository contract và `ElasticsearchOperations`.

Luồng lưu entity có thể mô tả:

~~~text
ProductService
    |
    v
ProductRepository proxy
    |
    v
CRUD method interceptor / repository composition
    |
    v
SimpleElasticsearchRepository.save(...)
    |
    v
ElasticsearchOperations.save(...)
    |
    v
MappingElasticsearchConverter
    |
    v
Elasticsearch Java API Client
    |
    v
Elasticsearch index
~~~

Implementation nền không tự serialize entity bằng Jackson `ObjectMapper`. Nó dùng các abstraction persistence của Spring Data Elasticsearch, trong đó mapping converter chuyển entity theo metadata. Phần JSON transport của client nằm ở tầng giao tiếp tiếp theo.

### 7.1. Entity information

Factory xây dựng entity information từ domain class. Metadata này cung cấp các thông tin như:

- Kiểu entity.
- Kiểu ID.
- Giá trị ID của một instance.
- Tên index hoặc thông tin index liên quan theo cấu hình document.
- Metadata cần thiết để thao tác persistence.

Annotation `@Id` xác định thuộc tính ID. `@Document` cung cấp metadata cho index và các tùy chọn liên quan. Nếu thiếu hoặc cấu hình sai metadata, repository có thể không khởi tạo hoặc thao tác không như mong muốn.

### 7.2. ElasticsearchOperations

`ElasticsearchOperations` cung cấp API cấp cao để thao tác với document và query. `SimpleElasticsearchRepository` dùng abstraction này thay vì để mỗi phương thức repository tự tạo HTTP request.

Lợi ích:

- Tách repository contract khỏi client cấp thấp.
- Dùng chung mapping context và custom conversions.
- Tận dụng các API lưu, đọc, xóa, query và index operations.
- Giúp kiểm thử hoặc thay đổi cấu hình hạ tầng dễ hơn.

### 7.3. Repository không tự bảo đảm index đã được tạo

Việc repository bean được tạo thành công không đồng nghĩa index chắc chắn đã tồn tại hoặc có mapping đúng trong cluster. Spring Data có thể tạo index theo metadata tùy `@Document(createIndex = ...)`, `@Setting`, `@Mapping` và cấu hình bootstrap của phiên bản.

Trong production, index thường được quản lý qua migration hoặc quy trình triển khai. Nếu ứng dụng không có quyền tạo index, cần provision index trước khi repository thực hiện truy vấn.

## 8. Repository fragments: mở rộng implementation theo từng phần

Khi cần truy vấn hoặc thao tác không phù hợp với derived query, nên dùng repository fragment.

### 8.1. Khai báo fragment interface

~~~java
public interface ProductSearchExtension {

    List<ProductDocument> searchByBusinessRule(
        String category,
        double minimumPrice
    );
}
~~~

### 8.2. Cài đặt fragment

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchExtensionImpl
        implements ProductSearchExtension {

    private final ElasticsearchOperations operations;

    public ProductSearchExtensionImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<ProductDocument> searchByBusinessRule(
            String category,
            double minimumPrice) {

        // Xây dựng NativeQuery/CriteriaQuery phù hợp với nghiệp vụ,
        // sau đó gọi operations.search(...)
        throw new UnsupportedOperationException(
            "Thay bằng truy vấn Elasticsearch của ứng dụng"
        );
    }
}
~~~

Phần thân query được để minh họa vị trí mở rộng; trong ứng dụng thực tế, thay bằng `NativeQuery`, `CriteriaQuery` hoặc query builder phù hợp với phiên bản Spring Data Elasticsearch.

### 8.3. Kết hợp fragment vào repository

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchExtension {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

Repository proxy kết hợp fragment với implementation CRUD nền. Khi gọi `searchByBusinessRule`, lời gọi được chuyển tới `ProductSearchExtensionImpl`; các phương thức `save` và `findById` vẫn được xử lý bởi implementation nền.

Spring Data tìm implementation fragment theo quy ước tên và cấu hình postfix. Postfix mặc định thường là `Impl`, nhưng có thể thay đổi qua cấu hình repository. Hãy kiểm tra package scanning và tên implementation nếu fragment không được phát hiện.

### 8.4. Vì sao nên dùng fragment?

- Chia logic tìm kiếm phức tạp thành các thành phần có trách nhiệm riêng.
- Không phải kế thừa và override toàn bộ CRUD.
- Có thể tái sử dụng fragment ở nhiều repository nếu thiết kế phù hợp.
- Tách truy vấn đặc thù khỏi interface repository chính.
- Dễ kiểm thử implementation bằng cách inject `ElasticsearchOperations`.

## 9. Tùy chỉnh repository base class

Trong một số trường hợp, ứng dụng muốn thay đổi hành vi nền dùng chung cho nhiều repository, ví dụ bổ sung audit hoặc chuẩn hóa logic lưu. Khi đó có thể cấu hình `repositoryBaseClass`.

Ví dụ minh họa:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.repository.support.ElasticsearchEntityInformation;
import org.springframework.data.elasticsearch.repository.support.SimpleElasticsearchRepository;

public class AuditedElasticsearchRepository<T, ID>
        extends SimpleElasticsearchRepository<T, ID> {

    public AuditedElasticsearchRepository(
            ElasticsearchEntityInformation<T, ID> metadata,
            ElasticsearchOperations operations) {
        super(metadata, operations);
    }

    // Override phương thức CRUD cần bổ sung hành vi.
}
~~~

Sau đó cấu hình:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog",
    repositoryBaseClass = AuditedElasticsearchRepository.class
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Constructor và generic API của `SimpleElasticsearchRepository` có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy đối chiếu Javadoc và source của dependency đang dùng trước khi triển khai custom base class.

Custom base class có phạm vi ảnh hưởng rộng: mọi repository trong vùng cấu hình có thể dùng implementation này. Vì vậy, chỉ nên override những hành vi thật sự dùng chung. Nếu chỉ một repository cần một query đặc thù, repository fragment thường phù hợp hơn.

## 10. Default method và custom implementation

Có hai cách mở rộng nhỏ thường bị nhầm với việc thay implementation nền.

**Default method** nằm trong interface và có phần thân Java. Nó phù hợp để kết hợp các phương thức repository đã có:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    default ProductDocument getRequiredBySku(String sku) {
        return findBySku(sku)
            .orElseThrow(() -> new IllegalArgumentException(
                "Product not found: " + sku
            ));
    }
}
~~~

**Custom fragment** là một interface riêng với implementation riêng. Nó phù hợp cho logic cần inject dependency hoặc truy vấn phức tạp. Fragment không yêu cầu repository chính phải chứa toàn bộ phần thân method.

Trong các phiên bản Spring Data hiện đại, mô hình repository composition và fragment là cách mở rộng được ưu tiên. Một số dự án cũ có thể dùng quy ước custom implementation gắn trực tiếp với repository interface. Khi làm việc với codebase cũ, hãy kiểm tra cách đặt tên và cơ chế phát hiện mà phiên bản đang dùng hỗ trợ.

## 11. Bootstrap mode và thời điểm tạo proxy

Repository proxy được tạo trong quá trình khởi tạo application context, nhưng thời điểm khởi tạo có thể phụ thuộc bootstrap mode:

| Mode | Hành vi khái quát |
| --- | --- |
| `DEFAULT` | Khởi tạo repository theo cơ chế eager thông thường |
| `LAZY` | Trì hoãn khởi tạo repository cho tới khi bean được sử dụng |
| `DEFERRED` | Trì hoãn một phần việc khởi tạo, sau đó hoàn tất bootstrap trước khi ứng dụng sẵn sàng theo cơ chế của framework |

Có thể cấu hình qua `@EnableElasticsearchRepositories(bootstrapMode = ...)` nếu phiên bản module hỗ trợ thuộc tính này.

Bootstrap mode ảnh hưởng thời điểm phát hiện một số lỗi:

- Với eager bootstrap, lỗi tạo query hoặc cấu hình repository có thể xuất hiện ngay khi application context khởi động.
- Với lazy bootstrap, một số lỗi chỉ xuất hiện khi repository thực sự được dùng.
- Với deferred bootstrap, framework có thể hoàn tất khởi tạo repository ở giai đoạn sau của bootstrap.

Không nên chọn LAZY chỉ để che lỗi cấu hình. Ứng dụng cần có readiness check phù hợp để tránh nhận traffic khi repository hoặc kết nối Elasticsearch chưa sẵn sàng.

## 12. Kiểm tra và quan sát repository proxy

Khi debug, có thể kiểm tra bean được inject có phải proxy hay không:

~~~java
import java.lang.reflect.Proxy;
import org.springframework.aop.support.AopUtils;

boolean springAopProxy = AopUtils.isAopProxy(productRepository);
boolean jdkProxy = Proxy.isProxyClass(productRepository.getClass());
~~~

Thông tin này hữu ích khi điều tra proxy, nhưng không nên phụ thuộc vào tên lớp proxy do Spring tạo ra vì đó là chi tiết triển khai.

Một số cách debug khác:

- Bật log phù hợp cho package repository của Spring Data để xem quá trình bootstrap và query.
- Đặt breakpoint tại `RepositoryFactoryBeanSupport`, `RepositoryFactorySupport` hoặc query interceptor trong source đúng phiên bản.
- Đặt breakpoint ở `SimpleElasticsearchRepository` để theo dõi CRUD.
- Đặt breakpoint ở custom fragment để xác nhận proxy có route đúng method.
- Kiểm tra mapping và index thực tế khi lỗi xuất phát từ persistence thay vì proxy.

Nếu một repository bean không được tạo, hãy xem lỗi đầu tiên trong log khởi động. Các nguyên nhân thường gặp gồm package scan sai, thiếu bean `ElasticsearchOperations`, domain metadata không hợp lệ, query method không phân tích được hoặc custom fragment không tìm thấy implementation.

## 13. Những lỗi thường gặp

**Tự viết ProductRepositoryImpl chỉ để có CRUD.** Spring Data đã cung cấp implementation nền. Chỉ cần interface kế thừa repository phù hợp; tạo custom implementation khi có hành vi thật sự riêng.

**Đặt repository ngoài package scan.** Registrar không phát hiện interface nên service không inject được bean. Đặt lớp khởi động ở package gốc hoặc cấu hình `basePackages`.

**Nhầm derived query với CRUD method.** `findBySku` được tạo qua query lookup strategy; `findById` là phương thức CRUD nền. Khi debug, hãy xác định đúng đường xử lý.

**Cho rằng mọi method tên findBy đều được hỗ trợ.** Keyword và semantics phụ thuộc module Elasticsearch. Kiểm tra tài liệu module và query thực tế.

**Đặt sai tên custom fragment implementation.** Spring Data không tìm thấy implementation nếu tên, postfix hoặc package không theo quy ước cấu hình.

**Dùng custom base class cho một trường hợp đặc thù.** Base class tác động tới nhiều repository. Dùng fragment cho logic riêng của một nhóm repository.

**Tưởng repository proxy sẽ tự tạo index trong mọi cấu hình.** Index creation phụ thuộc metadata, `createIndex`, settings, mapping và quy trình triển khai. Kiểm tra index trước khi vận hành.

**Dựa vào tên lớp proxy trong mã nghiệp vụ.** Proxy là chi tiết framework. Inject và sử dụng qua repository interface.

**Tạo client Elasticsearch mới trong implementation CRUD tùy chỉnh.** Dùng `ElasticsearchOperations` được Spring quản lý để giữ cấu hình và vòng đời client thống nhất.

## 14. Quy trình lần theo một lời gọi repository

Khi cần hiểu một phương thức repository đang được xử lý ở đâu, có thể lần theo thứ tự:

1. Tìm interface repository và xác định domain type, ID type cùng các interface cha.
2. Xác nhận package được Spring Data Elasticsearch quét.
3. Xem repository bean được đăng ký qua auto-configuration hay `@EnableElasticsearchRepositories`.
4. Xác định factory bean và repository factory mà phiên bản đang dùng tạo ra.
5. Xác định phương thức là CRUD nền, query method, default method hay custom fragment.
6. Với CRUD, theo dõi `SimpleElasticsearchRepository` và `ElasticsearchOperations`.
7. Với query method, theo dõi query lookup strategy, query creator hoặc declared query.
8. Với fragment, xác nhận implementation được phát hiện và method được đưa vào repository composition.
9. Kiểm tra mapping converter và Elasticsearch request nếu method đã được gọi nhưng dữ liệu sai.
10. Kiểm tra response hoặc exception từ Elasticsearch nếu lỗi xảy ra ở tầng server.

## 15. Tài liệu tham khảo

- [Spring Data Commons - Repository query methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): cách Spring Data phân tích query method và quy tắc đặt tên.
- [Spring Data Commons - Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): repository fragments và custom implementation.
- [Spring Data Elasticsearch - Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html): cách khai báo và sử dụng repository Elasticsearch.
- [Spring Data Elasticsearch API - ElasticsearchRepositoryFactory](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/repository/support/ElasticsearchRepositoryFactory.html): factory chuyên biệt cho Elasticsearch.
- [Spring Data Commons API - RepositoryFactorySupport](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryFactorySupport.html): cơ chế nền tạo repository proxy.

Các tên lớp nội bộ, constructor và API cấu hình có thể thay đổi theo phiên bản. Khi cần đọc source hoặc viết custom factory/base class, hãy dùng source và Javadoc khớp với Spring Data Elasticsearch được quản lý trong dependency của dự án.
