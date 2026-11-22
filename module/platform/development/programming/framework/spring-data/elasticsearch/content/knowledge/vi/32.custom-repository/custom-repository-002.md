# Định nghĩa Repository fragment và lớp triển khai

Spring Data repository cung cấp sẵn các thao tác phổ biến như save, findById, delete và các query method được suy ra từ tên phương thức. Khi ứng dụng cần một hành vi riêng, chẳng hạn kết hợp nhiều điều kiện tìm kiếm, gọi ElasticsearchOperations, xử lý aggregation hoặc ghi một read model đặc biệt, có thể mở rộng repository bằng custom implementation.

Spring Data hiện đại tổ chức custom repository theo mô hình **repository fragments**. Mỗi fragment là một phần hành vi độc lập gồm một interface mô tả API và một class triển khai interface đó. Repository chính ghép một hoặc nhiều fragment cùng với repository base interface để tạo thành một proxy hoàn chỉnh.

Ví dụ, ProductRepository có thể kết hợp:

- ElasticsearchRepository để có CRUD và các query method thông thường.
- ProductSearchFragment để cung cấp tìm kiếm sản phẩm nâng cao.
- ProductStatisticsFragment để cung cấp aggregation hoặc thống kê riêng.

Mỗi fragment có trách nhiệm riêng, có thể được kiểm thử và tái sử dụng độc lập. Spring Data ghép chúng vào repository proxy khi khởi tạo application context.

## 1. Repository fragment là gì?

Repository fragment là một thành phần hành vi có thể gắn vào một Spring Data repository. Fragment thường gồm hai phần:

1. **Fragment interface:** khai báo các method mà repository muốn cung cấp.
2. **Fragment implementation:** class triển khai các method đã khai báo.

Ví dụ:

~~~java
public interface ProductSearchFragment {

    List<Product> searchByTextAndBrand(
        String text,
        String brandId,
        Pageable pageable
    );
}
~~~

Lớp triển khai:

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByTextAndBrand(
            String text,
            String brandId,
            Pageable pageable) {
        // Xây dựng query và gọi ElasticsearchOperations.
        return List.of();
    }
}
~~~

Repository chính kế thừa fragment interface:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
~~~

Khi Spring Data tạo ProductRepository proxy, method searchByTextAndBrand được chuyển đến ProductSearchFragmentImpl. Các method CRUD vẫn được xử lý bởi repository base implementation.

Fragment không phải một Elasticsearch index, mapping type hay document con. Nó là một cách tổ chức hành vi Java ở tầng repository.

## 2. Repository được ghép từ những thành phần nào?

Một repository Spring Data có thể được xem như một composition của nhiều thành phần:

~~~text
ProductRepository
       |
       +-------------------------------+
       |                               |
       v                               v
ElasticsearchRepository       ProductSearchFragment
       |                               |
       v                               v
Repository base implementation ProductSearchFragmentImpl
       |
       v
CRUD và query infrastructure

       ProductRepository proxy
               |
               v
       API thống nhất cho caller
~~~

Repository composition thường gồm:

- **Repository base interface:** ví dụ CrudRepository, PagingAndSortingRepository hoặc ElasticsearchRepository.
- **Repository base implementation:** cung cấp hành vi mặc định như save, findById, delete.
- **Custom fragments:** các interface và implementation bổ sung hành vi nghiệp vụ.
- **Repository aspects:** các thành phần hạ tầng bổ sung mà Spring Data hỗ trợ, tùy store và cấu hình.

Caller chỉ inject ProductRepository. Nó không cần tự tạo ProductSearchFragmentImpl hoặc biết fragment nào đang xử lý method.

### 2.1. Vì sao nên tách fragment?

Một repository lớn có thể tích lũy nhiều logic khác nhau: tìm kiếm nâng cao, thống kê, bulk update, export, đồng bộ và xử lý dữ liệu. Nếu dồn tất cả vào một class implementation, class đó khó kiểm thử và khó tái sử dụng.

Tách thành fragments giúp:

- Mỗi fragment có một nhóm method liên quan.
- Có thể dùng lại fragment cho nhiều repository.
- Có thể inject dependency riêng cho từng implementation.
- Có thể kiểm thử trực tiếp implementation mà không cần khởi tạo repository proxy.
- Có thể thay đổi một phần hành vi mà không làm thay đổi toàn bộ repository.
- Có thể ghi đè method mặc định của repository khi có nhu cầu rõ ràng.

## 3. Quy ước đặt tên fragment và implementation

Spring Data tìm implementation của fragment dựa trên tên interface và implementation postfix. Postfix mặc định là Impl.

Nếu fragment interface tên ProductSearchFragment, implementation class thường có tên:

~~~text
ProductSearchFragment
ProductSearchFragmentImpl
~~~

Ví dụ:

~~~java
public interface ProductSearchFragment {
    List<Product> searchSimilar(String text);
}
~~~

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    @Override
    public List<Product> searchSimilar(String text) {
        // Custom implementation.
        return List.of();
    }
}
~~~

Tên implementation được ghép từ tên fragment interface và postfix. Nếu repository kết hợp nhiều fragment, mỗi fragment có implementation tương ứng.

### 3.1. Phân biệt fragment implementation và repository-name implementation

Có hai kiểu tên dễ nhầm:

| Kiểu | Interface | Implementation mặc định |
| --- | --- | --- |
| Fragment hiện đại | ProductSearchFragment | ProductSearchFragmentImpl |
| Custom implementation gắn trực tiếp tên repository theo quy ước cũ | ProductRepository | ProductRepositoryImpl |

Spring Data hiện đại khuyến nghị mô hình fragment vì nó làm rõ ranh giới trách nhiệm và cho phép composition nhiều phần độc lập.

Không nên tạo ProductRepositoryImpl chỉ để chứa mọi method tùy biến nếu các method có thể tách thành fragments rõ ràng. Cách triển khai legacy vẫn có thể xuất hiện trong dự án cũ, nhưng cần hiểu chính xác cơ chế discovery và tránh trộn hai mô hình một cách thiếu chủ đích.

### 3.2. Thay đổi implementation postfix

Postfix mặc định là Impl. Có thể cấu hình postfix khác khi bật repository scanning:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    repositoryImplementationPostfix = "Custom"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Khi dùng postfix Custom, implementation của ProductSearchFragment phải theo tên:

~~~text
ProductSearchFragmentCustom
~~~

Tên interface fragment vẫn là ProductSearchFragment. Chỉ hậu tố implementation thay đổi.

Chỉ thay postfix khi dự án có quy ước rõ ràng. Nếu không, giữ Impl giúp code dễ nhận diện và phù hợp convention mặc định của Spring Data.

## 4. Vị trí package và cơ chế discovery

Spring Data cần tìm được fragment implementation trên classpath. Thông thường, implementation được đặt trong cùng package với repository interface hoặc package con mà repository scanning có thể tìm thấy.

Ví dụ cấu trúc:

~~~text
com.example.catalog
|
+-- repository
|   |
|   +-- ProductRepository.java
|   +-- ProductSearchFragment.java
|   +-- ProductStatisticsFragment.java
|   |
|   +-- ProductSearchFragmentImpl.java
|   +-- ProductStatisticsFragmentImpl.java
|
+-- document
|   |
|   +-- Product.java
|
+-- service
    |
    +-- ProductCatalogService.java
~~~

Có thể tổ chức fragment interface và implementation trong package con nếu cấu hình scanning bao phủ vị trí đó. Điều quan trọng là implementation phải nằm trong vùng package mà repository infrastructure có thể phát hiện.

### 4.1. Repository scanning

Với Spring Boot, repository scanning thường được tự động cấu hình theo package của application class và các cấu hình Spring Data Elasticsearch.

Nếu khai báo thủ công:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = {
        "com.example.catalog.repository",
        "com.example.inventory.repository"
    }
)
public class RepositoryConfiguration {
}
~~~

Đảm bảo package của repository và fragment implementation nằm trong phạm vi phù hợp. Nếu repository được phát hiện nhưng fragment implementation không được tìm thấy, method custom có thể báo lỗi khi gọi hoặc repository không khởi tạo được do thiếu fragment implementation.

### 4.2. Dependency injection trong implementation

Fragment implementation là Spring-managed component trong repository composition. Có thể inject ElasticsearchOperations, converter, service hoặc các dependency khác qua constructor.

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;
    private final ProductSearchMapper mapper;

    public ProductSearchFragmentImpl(
            ElasticsearchOperations operations,
            ProductSearchMapper mapper) {
        this.operations = operations;
        this.mapper = mapper;
    }
}
~~~

Ưu tiên constructor injection để dependency được thể hiện rõ và dễ kiểm thử. Không tự tạo ElasticsearchClient hoặc ElasticsearchOperations bên trong implementation nếu ứng dụng đã cấu hình các bean tương ứng.

Nếu implementation được Spring Data phát hiện và đăng ký theo convention, không cần tạo thêm một bean thứ hai trùng tên cho cùng implementation. Nếu dự án tự đăng ký bean, hãy bảo đảm tên bean và cách discovery không tạo ra hai candidate cạnh tranh.

## 5. Ví dụ hoàn chỉnh: fragment tìm kiếm sản phẩm

Giả sử Product document có các field:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Double)
    private double price;

    // Constructors, getters và setters
}
~~~

### 5.1. Khai báo fragment interface

~~~java
import java.util.List;

import org.springframework.data.domain.Pageable;

public interface ProductSearchFragment {

    List<Product> searchByTextAndBrand(
        String text,
        String brandId,
        Pageable pageable
    );
}
~~~

Fragment interface chỉ khai báo contract. Nó không cần extends ElasticsearchRepository và không cần biết cách tạo query.

### 5.2. Viết implementation

~~~java
import java.util.stream.Collectors;

import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByTextAndBrand(
            String text,
            String brandId,
            Pageable pageable) {

        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q
                .bool(b -> b
                    .must(m -> m
                        .match(mm -> mm
                            .field("name")
                            .query(text)
                        )
                    )
                    .filter(f -> f
                        .term(t -> t
                            .field("brandId")
                            .value(brandId)
                        )
                    )
                )
            )
            .withPageable(pageable)
            .build();

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return hits.getSearchHits()
            .stream()
            .map(SearchHit::getContent)
            .collect(Collectors.toList());
    }
}
~~~

Implementation dùng ElasticsearchOperations để gửi NativeQuery. Query kết hợp:

- Match query trên field name để tìm kiếm toàn văn.
- Term filter trên brandId để lọc chính xác theo thương hiệu.
- Pageable để phân trang.

Trong ví dụ này, implementation trả về List<Product>. Nếu caller cần total hits, score, highlight hoặc metadata của từng hit, nên trả về SearchHits<Product> hoặc một DTO riêng thay vì chỉ lấy content.

Tên field trong query phải khớp mapping Elasticsearch. Nếu mapping dùng field khác hoặc tên field được tùy chỉnh bằng @Field(name = "..."), hãy sử dụng tên field thực tế.

### 5.3. Ghép fragment vào repository

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
~~~

Repository được sử dụng như một API thống nhất:

~~~java
List<Product> products = productRepository.searchByTextAndBrand(
    "mechanical keyboard",
    "BRAND-10",
    PageRequest.of(0, 20)
);
~~~

Caller chỉ phụ thuộc ProductRepository. Spring Data tìm fragment implementation và kết nối method với repository proxy.

## 6. Kết hợp nhiều fragments trong một repository

Một repository có thể kết hợp nhiều fragment:

~~~java
public interface ProductStatisticsFragment {

    long countByBrand(String brandId);

    Map<String, Long> countByCategory();
}
~~~

~~~java
public interface ProductBulkFragment {

    void reindexProducts(List<Product> products);
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment,
                ProductStatisticsFragment,
                ProductBulkFragment {
}
~~~

Các implementation tương ứng:

~~~text
ProductSearchFragmentImpl
ProductStatisticsFragmentImpl
ProductBulkFragmentImpl
~~~

Repository proxy ghép tất cả fragment vào một API. ProductSearchFragmentImpl chịu trách nhiệm tìm kiếm; ProductStatisticsFragmentImpl xử lý aggregation; ProductBulkFragmentImpl xử lý luồng ghi hàng loạt.

### 6.1. Thứ tự fragment khi có method trùng nhau

Một repository có thể ghép các fragment có method trùng chữ ký. Trong composition, thứ tự khai báo fragment trong repository interface có ý nghĩa đối với việc chọn implementation. Fragment đứng trước có độ ưu tiên cao hơn fragment đứng sau khi nhiều fragment cùng cung cấp một method.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                PreferredProductSearch,
                LegacyProductSearch {
}
~~~

Nếu cả PreferredProductSearch và LegacyProductSearch cùng khai báo method search(String), fragment đứng trước được ưu tiên trong composition. Không nên dựa vào hành vi này nếu thiết kế có thể tránh trùng method; tốt nhất đặt tên method rõ ràng hoặc chỉ để một fragment sở hữu contract đó.

Các custom fragment có thể được dùng để ghi đè method từ repository base implementation. Vì vậy, hãy kiểm tra signature và thứ tự composition nếu định nghĩa method trùng với save, findById hoặc method có sẵn khác.

### 6.2. Tránh trùng tên implementation

Nếu nhiều fragment interface có cùng simple name ở các package khác nhau, class implementation theo convention có thể gây nhập nhằng trong quá trình discovery.

Nên:

- Đặt tên fragment đủ cụ thể.
- Giữ package repository rõ ràng.
- Tránh hai fragment có cùng simple name trong cùng vùng scanning.
- Dùng tên bean tường minh nếu dự án cần giải quyết nhiều implementation candidate theo cơ chế Spring bean naming được phiên bản hỗ trợ.

Không giải quyết xung đột bằng cách tạo nhiều class cùng tên trong cùng package hoặc phụ thuộc vào thứ tự scan.

## 7. Dùng fragment để tùy biến method kế thừa

Fragment không chỉ thêm method mới. Nó còn có thể cung cấp implementation thay thế cho method mà repository đã kế thừa.

Ví dụ, ứng dụng muốn chuẩn hóa entity trước khi lưu hoặc áp dụng một quy tắc ghi riêng. Có thể khai báo fragment với method cùng signature save:

~~~java
public interface CustomizedProductSave {

    <S extends Product> S save(S entity);
}
~~~

Implementation:

~~~java
public class CustomizedProductSaveImpl
        implements CustomizedProductSave {

    private final ElasticsearchOperations operations;

    public CustomizedProductSaveImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public <S extends Product> S save(S entity) {
        entity.setName(entity.getName().trim());
        return operations.save(entity);
    }
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                CustomizedProductSave {
}
~~~

Custom fragment có thể được ưu tiên trước base repository implementation và thay đổi hành vi save cho repository composition đó.

### 7.1. Cẩn thận với method signature

Khi muốn ghi đè method kế thừa, signature phải tương thích:

- Tên method.
- Số lượng và kiểu tham số.
- Kiểu trả về tương thích.
- Generic type bounds.

Nếu signature khác, Spring Data có thể xem đó là một method mới thay vì override method cũ. Hãy kiểm tra compile-time và integration behavior.

### 7.2. Không gọi ngược repository để tránh đệ quy

Trong CustomizedProductSaveImpl, không inject ProductRepository rồi gọi repository.save(entity). Method đó có thể lại được dispatch đến chính fragment đang thực thi, gây đệ quy.

Gọi trực tiếp ElasticsearchOperations hoặc một service/base mechanism thích hợp. Nếu cần giữ toàn bộ hành vi mặc định của repository base implementation rồi bổ sung logic, hãy thiết kế fragment sao cho không tự gọi lại method đã override.

### 7.3. Override method CRUD có thể ảnh hưởng toàn repository

Nếu fragment override save, mọi lời gọi save qua repository composition đó có thể chạy custom implementation. Điều này ảnh hưởng cả code service, batch và các thành phần khác đang dùng repository.

Chỉ override CRUD khi quy tắc mới thực sự là hợp đồng chung của repository. Nếu chỉ cần một thao tác đặc biệt, thêm method có tên riêng sẽ an toàn và dễ hiểu hơn.

## 8. Fragment có thể tái sử dụng cho nhiều repository

Fragment có thể được thiết kế generic để dùng cho nhiều domain type.

Ví dụ:

~~~java
public interface SearchByText<T> {

    List<T> searchText(String text, Pageable pageable);
}
~~~

Implementation generic:

~~~java
public class SearchByTextImpl<T>
        implements SearchByText<T> {

    private final ElasticsearchOperations operations;
    private final Class<T> entityType;

    public SearchByTextImpl(
            ElasticsearchOperations operations,
            Class<T> entityType) {
        this.operations = operations;
        this.entityType = entityType;
    }

    @Override
    public List<T> searchText(String text, Pageable pageable) {
        // Tạo query theo mapping của entityType.
        // Ví dụ này lược bỏ phần xây dựng query.
        return List.of();
    }
}
~~~

Generic fragment có thể dùng lại contract, nhưng implementation cần biết domain type cụ thể để gọi operations.search và xác định field tìm kiếm. Việc cung cấp Class<T> cho một implementation generic có thể cần cấu hình factory hoặc một thiết kế khác tùy cách Spring Data resolve fragment instance.

Một cách thực tế hơn là tách contract generic nhưng tạo implementation riêng cho từng entity khi field mapping và search behavior khác nhau.

### 8.1. Khi nào nên generic?

Dùng fragment generic khi:

- Hành vi thực sự giống nhau giữa nhiều entity.
- Các entity tuân theo một interface hoặc convention field chung.
- Mapping và query có thể xác định một cách ổn định.
- Implementation không cần các quy tắc nghiệp vụ riêng của từng aggregate.

Không generic hóa chỉ để giảm vài dòng code. Một implementation riêng cho Product và Order có thể dễ đọc hơn một generic fragment có nhiều if/else theo class.

## 9. Fragment và custom repository base class

Spring Data còn cho phép thay repository base implementation bằng custom base class. Đây là một cơ chế khác với repository fragments.

| Repository fragment | Custom base class |
| --- | --- |
| Thêm một phần hành vi có interface riêng | Thay đổi nền tảng implementation của repository |
| Có thể ghép nhiều fragment | Một base class được áp dụng theo cấu hình repository |
| Phù hợp chức năng độc lập | Phù hợp hành vi chung cho nhiều repository |
| Có thể tái sử dụng theo composition | Thường áp dụng rộng cho một nhóm repository |
| Có thể override method qua fragment | Có thể override method base trực tiếp |

### 9.1. Ví dụ custom base class

Với Spring Data Elasticsearch, base class tùy biến có thể kế thừa SimpleElasticsearchRepository và bổ sung hành vi dùng chung. Tên constructor và API cần khớp với phiên bản Spring Data Elasticsearch.

Ví dụ khái niệm:

~~~java
public class CustomElasticsearchRepository<T, ID>
        extends SimpleElasticsearchRepository<T, ID> {

    public CustomElasticsearchRepository(
            ElasticsearchEntityInformation<T, ID> metadata,
            ElasticsearchOperations operations) {
        super(metadata, operations);
    }

    // Hành vi chung cho mọi repository dùng base class này.
}
~~~

Cấu hình repository factory có thể chỉ định base class qua thuộc tính repositoryBaseClass trong @EnableElasticsearchRepositories:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    repositoryBaseClass = CustomElasticsearchRepository.class
)
~~~

Đây là ví dụ định hướng. Constructor của SimpleElasticsearchRepository và ElasticsearchEntityInformation có thể thay đổi theo phiên bản. Hãy kiểm tra API đúng với dependency dự án trước khi triển khai.

Chọn custom base class khi mọi repository trong vùng cấu hình cần cùng một thay đổi nền tảng. Chọn fragment khi chỉ một số repository cần một khả năng cụ thể.

## 10. Fragment và query method, @Query

Không phải mọi query tùy biến đều cần fragment.

Spring Data Elasticsearch có thể tạo query từ tên method hoặc dùng @Query cho truy vấn khai báo. Fragment hữu ích khi logic cần nhiều bước hoặc phải dùng API Elasticsearch Java Client/ElasticsearchOperations trực tiếp.

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Tìm theo field đơn giản | Derived query method |
| Truy vấn cố định, ngắn | @Query |
| Kết hợp điều kiện động, phân tích tham số | Repository fragment |
| Dùng aggregation hoặc nhiều request | Repository fragment |
| Xử lý bulk/reindex tùy chỉnh | Repository fragment hoặc service chuyên trách |
| Hành vi chung cho mọi repository | Custom base class |

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByBrandId(String brandId);
}
~~~

Method findByBrandId phù hợp với derived query. Nếu cần tìm theo nhiều điều kiện động, highlight, custom scoring hoặc nhiều aggregation, fragment sẽ dễ quản lý hơn.

## 11. Dùng ElasticsearchOperations bên trong fragment

Fragment implementation thường dùng ElasticsearchOperations để truy cập các tính năng cấp thấp hơn repository abstraction.

Một số khả năng:

- Search bằng NativeQuery.
- Aggregation và đọc aggregation result.
- Index/update/delete document theo logic tùy biến.
- Bulk operations.
- Truy vấn theo IndexCoordinates.
- Sử dụng SearchHits để lấy score, highlight và metadata.

### 11.1. Giữ mapping nhất quán

Nếu dùng ElasticsearchOperations với entity class:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Spring Data sử dụng mapping metadata của Product để chuyển source document thành entity.

Nếu query truy cập field cụ thể, tên field phải khớp mapping Elasticsearch. Không giả định tên Java property luôn giống tên field trong index nếu entity có cấu hình mapping tùy chỉnh.

### 11.2. Dùng IndexCoordinates khi cần

Có thể chỉ định index cụ thể:

~~~java
SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products-read")
);
~~~

Điều này hữu ích khi repository cần đọc từ alias hoặc index được chọn theo tenant/partition. Cần kiểm soát đích index để tránh ghi nhầm vào index không mong muốn.

### 11.3. Không đưa toàn bộ nghiệp vụ vào fragment

Fragment nên là adapter cho hành vi truy cập dữ liệu. Quy tắc nghiệp vụ phức tạp như kiểm tra quyền, tính giá, quyết định trạng thái hoặc phối hợp nhiều hệ thống thường nên nằm trong service/domain layer.

Fragment có thể nhận DTO/query criteria đã được service chuẩn bị, xây dựng Elasticsearch request và chuyển kết quả thành kiểu trả về phù hợp.

## 12. Reactive repository fragments

Nếu ứng dụng dùng ReactiveElasticsearchRepository hoặc ReactiveElasticsearchOperations, fragment cũng nên dùng reactive API.

Ví dụ contract:

~~~java
public interface ReactiveProductSearchFragment {

    Flux<Product> searchByBrand(String brandId);
}
~~~

Implementation có thể inject ReactiveElasticsearchOperations:

~~~java
public class ReactiveProductSearchFragmentImpl
        implements ReactiveProductSearchFragment {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchFragmentImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> searchByBrand(String brandId) {
        // Tạo query reactive rồi gọi operations.search(...).
        return Flux.empty();
    }
}
~~~

Repository:

~~~java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchFragment {
}
~~~

Implementation reactive cần trả Publisher type phù hợp như Mono hoặc Flux. Không gọi block() bên trong fragment vì thao tác đó làm mất lợi ích non-blocking và có thể gây deadlock hoặc làm nghẽn event loop.

Không trộn đồng bộ và reactive một cách tùy tiện. Fragment được thiết kế cho reactive repository nên sử dụng ReactiveElasticsearchOperations và reactive return types.

## 13. Kiểm thử repository fragment

Fragment có thể được kiểm thử riêng vì implementation là class Java thông thường nhận dependency qua constructor.

### 13.1. Unit test implementation

Có thể mock ElasticsearchOperations và xác nhận fragment gọi đúng API:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchFragmentImplTest {

    @Mock
    ElasticsearchOperations operations;

    @Test
    void shouldExecuteSearch() {
        ProductSearchFragmentImpl fragment =
            new ProductSearchFragmentImpl(operations);

        // Thiết lập SearchHits mock và gọi method.
        // Xác nhận operations.search được gọi với query phù hợp.
    }
}
~~~

Unit test nên tập trung vào:

- Query được tạo với field và điều kiện đúng.
- Pageable được chuyển vào query.
- Kết quả được ánh xạ đúng.
- Các trường hợp không có kết quả.
- Validation tham số đầu vào nếu fragment chịu trách nhiệm validation.

### 13.2. Integration test repository composition

Unit test implementation không chứng minh Spring Data đã phát hiện fragment. Cần integration test với ApplicationContext để xác nhận:

- ProductRepository bean được tạo.
- Fragment interface được ghép vào repository proxy.
- Method custom gọi đúng implementation.
- Dependency được inject.
- Method CRUD mặc định vẫn hoạt động.
- Nếu fragment override method base, implementation tùy biến thực sự được gọi.

Có thể dùng Elasticsearch test container hoặc một Elasticsearch instance dành riêng cho test tùy hạ tầng dự án.

### 13.3. Test naming convention

Nếu repository khởi tạo thất bại do không tìm thấy implementation:

1. Kiểm tra fragment interface có được extends trong repository không.
2. Kiểm tra implementation class có implement đúng interface không.
3. Kiểm tra tên class có hậu tố đúng không.
4. Kiểm tra package nằm trong vùng scanning.
5. Kiểm tra repositoryImplementationPostfix nếu đã cấu hình.
6. Kiểm tra class có dependency nào không thể khởi tạo không.
7. Kiểm tra có bean trùng tên hoặc implementation candidate nhập nhằng không.

## 14. Lỗi thường gặp

**Chỉ khai báo fragment interface mà không có implementation.** Spring Data không thể thực thi custom method. Tạo class triển khai đúng interface và đúng convention.

**Đặt implementation tên ProductRepositoryImpl trong khi đang dùng fragment ProductSearchFragment.** Với fragment hiện đại, tên theo fragment interface là ProductSearchFragmentImpl.

**Đặt implementation ngoài package scanning.** Repository có thể không tìm thấy fragment. Đặt class trong package phù hợp hoặc điều chỉnh vùng scanning.

**Quên thêm fragment interface vào repository extends.** Implementation tồn tại nhưng không được ghép vào repository nếu fragment không thuộc composition.

**Dùng sai postfix.** Nếu cấu hình repositoryImplementationPostfix là Custom, class hậu tố Impl có thể không được phát hiện theo convention đó.

**Tạo bean implementation trùng lặp.** Đăng ký đồng thời bằng nhiều cơ chế có thể tạo bean candidate nhập nhằng. Chọn một cơ chế đăng ký phù hợp.

**Inject repository vào chính fragment để gọi method bị override.** Có thể gây vòng lặp dispatch. Dùng ElasticsearchOperations hoặc service phù hợp.

**Để nhiều fragment cùng cung cấp một method mà không kiểm soát thứ tự.** Kết quả phụ thuộc fragment composition order. Tránh trùng method hoặc khai báo thứ tự có chủ đích.

**Override save chỉ để thêm một xử lý nhỏ.** Điều này có thể thay đổi mọi lời gọi save qua repository. Cân nhắc method riêng hoặc callback phù hợp.

**Dùng fragment thay cho service layer.** Fragment nên tập trung vào truy cập dữ liệu và query. Quy tắc nghiệp vụ rộng nên ở service/domain layer.

**Dùng ElasticsearchOperations đồng bộ trong reactive fragment.** Điều này có thể block luồng reactive. Inject ReactiveElasticsearchOperations và trả Flux/Mono.

**Giả định custom base class và fragment là cùng một cơ chế.** Fragment là phần composition độc lập; base class thay implementation nền tảng của repository.

**Không kiểm thử repository proxy.** Unit test implementation không xác nhận Spring Data discovery. Bổ sung integration test cho ApplicationContext.

## 15. Quy trình tạo một repository fragment

Khi cần thêm một hành vi repository tùy biến:

1. Xác định method nào không phù hợp với derived query hoặc @Query.
2. Tạo fragment interface với tên thể hiện trách nhiệm.
3. Khai báo method và kiểu trả về rõ ràng.
4. Tạo implementation class theo convention tên fragment cộng postfix Impl.
5. Inject ElasticsearchOperations hoặc dependency cần thiết qua constructor.
6. Xây dựng query và xử lý kết quả trong implementation.
7. Thêm fragment interface vào repository chính.
8. Đặt implementation trong vùng package scanning.
9. Nếu dùng postfix tùy chỉnh, đồng bộ tên class và cấu hình repository scanning.
10. Kiểm thử implementation và repository composition.
11. Kiểm tra các method trùng signature với fragment khác hoặc base repository.
12. Chỉ override method CRUD khi thay đổi đó là hành vi chủ đích của repository.

## 16. Ví dụ tổng hợp cấu trúc project

~~~text
src/main/java/com/example/catalog
|
+-- document
|   |
|   +-- Product.java
|
+-- repository
|   |
|   +-- ProductRepository.java
|   |
|   +-- fragment
|       |
|       +-- ProductSearchFragment.java
|       +-- ProductSearchFragmentImpl.java
|       +-- ProductStatisticsFragment.java
|       +-- ProductStatisticsFragmentImpl.java
|
+-- service
|   |
|   +-- ProductCatalogService.java
|
+-- config
    |
    +-- ElasticsearchConfiguration.java
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment,
                ProductStatisticsFragment {
}
~~~

Fragment interface:

~~~java
public interface ProductSearchFragment {
    SearchHits<Product> searchProducts(ProductSearchCriteria criteria);
}
~~~

Implementation:

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<Product> searchProducts(ProductSearchCriteria criteria) {
        Query query = buildQuery(criteria);
        return operations.search(query, Product.class);
    }

    private Query buildQuery(ProductSearchCriteria criteria) {
        // Chuyển criteria thành NativeQuery hoặc query Spring Data phù hợp.
        return NativeQuery.builder().build();
    }
}
~~~

Service sử dụng repository:

~~~java
@Service
public class ProductCatalogService {

    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    public SearchHits<Product> search(ProductSearchCriteria criteria) {
        return repository.searchProducts(criteria);
    }
}
~~~

Service không cần biết method searchProducts đến từ fragment nào. Nó chỉ sử dụng contract của ProductRepository.

## 17. Tài liệu tham khảo

- [Spring Data Elasticsearch - Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html): repository fragments, custom implementation discovery và composition.
- [Spring Data Commons - Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): fragment interface, implementation postfix, nhiều fragment và thứ tự composition.
- [Spring Data Elasticsearch - Repository configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html): khai báo repository và cấu hình scanning.
- [Spring Data Elasticsearch - Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): dùng ElasticsearchOperations để thực hiện các thao tác cấp thấp.
- [Spring Data Elasticsearch API - EnableElasticsearchRepositories](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/repository/config/EnableElasticsearchRepositories.html): các thuộc tính cấu hình repository scanning, implementation postfix và base class.

Các class, constructor và builder method trong ví dụ phụ thuộc phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Hãy đối chiếu Javadoc của dependency dự án khi triển khai. Ý tưởng chính là fragment interface định nghĩa một phần API repository, implementation class cung cấp hành vi, còn repository chính ghép fragment với base repository thành một proxy thống nhất.
