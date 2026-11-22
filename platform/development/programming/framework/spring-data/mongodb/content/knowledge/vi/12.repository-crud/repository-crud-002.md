# Thiết kế giao diện cơ sở bằng @NoRepositoryBean

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Data MongoDB thường có nhiều aggregate root, chẳng hạn Product, Customer và Order. Mỗi kiểu document có repository riêng, nhưng tất cả có thể cần những thao tác chung như tìm theo ID, đếm bản ghi và xử lý tình huống không tìm thấy. Thay vì sao chép các phương thức chung vào mọi interface, chúng ta có thể tạo **giao diện repository cơ sở**.

Vấn đề là Spring Data tự tìm các repository interface để tạo bean. Một giao diện generic như BaseMongoRepository<T, ID> không có domain cụ thể, vì vậy **không nên được tạo thành một repository bean độc lập**. Annotation **@NoRepositoryBean** giải quyết đúng vấn đề này.

Trong module **SPRING_DATA_MONGODB**, cơ chế đó hỗ trợ thiết kế tầng repository khi kết nối MongoDB, ánh xạ document và thao tác bằng **MongoTemplate** hoặc **MongoRepository**. Các phương thức repository là nền tảng để phát triển truy vấn, aggregation, index, transaction, reactive access, kiểm thử và phân tích hiệu năng; tuy vậy @NoRepositoryBean chỉ tác động đến **việc tạo repository bean**, không tự thay đổi những chức năng đó.

Mục tiêu sau bài học:

1. Hiểu tại sao repository generic cần @NoRepositoryBean.
2. Tạo base interface dùng chung và repository con gắn domain/ID cụ thể.
3. Chọn hợp đồng CRUD đầy đủ hoặc giới hạn API chỉ đọc.
4. Phân biệt default method, derived query và custom implementation.
5. Biết khi nào cần repository fragment hoặc repository base class.
6. Kiểm thử khả năng tạo bean, ánh xạ collection, thao tác CRUD và các trường hợp cấu hình lỗi.

## 2. Spring Data tạo repository như thế nào?

Khai báo thông thường:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {
}
~~~

Trong quá trình repository scanning, Spring Data tìm các interface hợp lệ, xác định **domain type** và **ID type**, sau đó dùng repository factory tạo proxy/bean. Bean đó có thể được inject vào một service và thực hiện thao tác MongoDB.

~~~mermaid
flowchart TD
    A["Repository scanning"] --> B{"Interface được tìm thấy"}
    B -->|"Concrete repository"| C["Đọc domain + ID"]
    C --> D["Repository factory"]
    D --> E["Repository proxy/bean"]
    B -->|"@NoRepositoryBean"| F["Bỏ qua tạo bean riêng"]
    F --> G["Vẫn cho phép repository con kế thừa"]
    G --> C
~~~

Với ProductRepository, kiểu cụ thể là ProductDocument và ObjectId. Còn với BaseMongoRepository<T, ID>, hai tham số vẫn là generic, nên nó chỉ là **một hợp đồng trung gian**, không thể biết trước collection nào cần thao tác.

## 3. Ý nghĩa chính xác của @NoRepositoryBean

Annotation thuộc Spring Data Commons:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
~~~

Một base interface tối giản:

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

Annotation báo với Spring Data: **đừng tạo repository bean trực tiếp cho BaseMongoRepository**. Nó không cấm các interface con kế thừa và sử dụng toàn bộ hợp đồng CRUD.

Hai interface cụ thể:

~~~java
public interface ProductRepository
        extends BaseMongoRepository<ProductDocument, ObjectId> {
}

public interface CustomerRepository
        extends BaseMongoRepository<CustomerDocument, ObjectId> {
}
~~~

Spring Data có thể tạo bean ProductRepository và CustomerRepository bình thường nếu chúng nằm trong phạm vi scanning và các domain type hợp lệ.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| @NoRepositoryBean trên BaseMongoRepository<T, ID> | Không có repository bean độc lập cho base generic. |
| ProductRepository kế thừa base, không có @NoRepositoryBean | Tạo bean cụ thể cho ProductDocument. |
| @NoRepositoryBean đặt nhầm trên ProductRepository | ProductRepository không được tự tạo bean; inject có thể lỗi. |
| Base interface có Java default method | Repository con kế thừa phần thân phương thức. |
| Base khai báo method trừu tượng tùy ý | Phải có khả năng query derivation hoặc implementation phù hợp. |

**@NoRepositoryBean không phải @Repository.** Một annotation ngăn tạo repository bean cho interface trung gian; annotation còn lại thường dùng nhận diện thành phần tầng persistence. Repository scanning của Spring Data có thể tự tạo bean cho repository hợp lệ mà không yêu cầu đặt @Repository lên từng interface con.

## 4. Ví dụ đầy đủ: Product và Customer dùng chung base

### 4.1. Hai document độc lập

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    boolean active
) {}
~~~

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public record CustomerDocument(
    @Id ObjectId id,
    String displayName,
    String email
) {}
~~~

Annotation **@Document** xác định collection. BaseMongoRepository không cần biết Product hay Customer được lưu ở đâu; repository con cùng hạ tầng MongoDB sử dụng metadata domain để chọn collection tương ứng.

### 4.2. Base interface chứa một default method hữu ích

~~~java
package com.example.catalog;

import java.util.NoSuchElementException;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    default T getRequired(ID id) {
        return findById(id).orElseThrow(
            () -> new NoSuchElementException(
                "Document not found for id: " + id
            )
        );
    }
}
~~~

Hàm getRequired có **phần thân Java** và gọi findById vốn đã được repository cung cấp. Spring Data không cần phân tích getRequired thành query và cũng không cần viết một implementation class mới cho phương thức này.

### 4.3. Repository con có truy vấn riêng

~~~java
package com.example.catalog;

import java.util.Optional;
import org.bson.types.ObjectId;

public interface ProductRepository
        extends BaseMongoRepository<ProductDocument, ObjectId> {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;

public interface CustomerRepository
        extends BaseMongoRepository<CustomerDocument, ObjectId> {
}
~~~

ProductRepository có getRequired, save, insert, findById, deleteById và findBySku. CustomerRepository cũng có getRequired và CRUD chung, nhưng **không kế thừa findBySku**, vì CustomerDocument không có thuộc tính sku.

### 4.4. Sử dụng qua service

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public ProductDocument create(String sku, String name) {
        ProductDocument draft = new ProductDocument(
            null, sku, name, true
        );
        return products.insert(draft);
    }

    public ProductDocument getById(ObjectId id) {
        return products.getRequired(id);
    }
}
~~~

Với record immutable, phương thức insert trả về entity đã lưu; nên sử dụng **đối tượng trả về** vì ID có thể được gán khi persistence tạo một instance mới. getRequired sử dụng findById và ném ngoại lệ nếu không có document phù hợp; nó chưa quyết định HTTP status hay cấu trúc lỗi của tầng API.

~~~mermaid
flowchart LR
    A["BaseMongoRepository<T, ID>"] --> B["ProductRepository<ProductDocument, ObjectId>"]
    A --> C["CustomerRepository<CustomerDocument, ObjectId>"]
    B --> D["products collection"]
    C --> E["customers collection"]
~~~

## 5. Điều gì xảy ra nếu quên @NoRepositoryBean?

Xét giao diện này:

~~~java
// Chưa đánh dấu @NoRepositoryBean.
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

Khi nó nằm trong phạm vi scanning, Spring Data có thể cố tạo repository riêng cho interface generic. Nhưng T và ID chưa có giá trị cụ thể, dẫn đến lỗi khởi tạo repository hoặc thiếu metadata domain. Tình huống chính xác và nội dung exception phụ thuộc cấu hình, nhưng gốc vấn đề vẫn là interface dùng để kế thừa đang bị xem như repository hoàn chỉnh.

Sửa:

~~~java
@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

Nếu có nhiều tầng trung gian vẫn generic, nên đánh dấu từng tầng không được tạo repository bean:

~~~java
@NoRepositoryBean
public interface AuditedRepository<T, ID>
        extends BaseMongoRepository<T, ID> {
}
~~~

AuditedRepository trong ví dụ chưa triển khai auditing; tên chỉ để minh họa tầng kế thừa. Nếu thật sự cần auditing, phải cấu hình và thiết kế cơ chế audit riêng.

## 6. Chọn đúng repository gốc

Không phải dự án nào cũng muốn công bố đầy đủ thao tác CRUD.

| Interface | Phạm vi | Khi dùng |
| --- | --- | --- |
| Repository<T, ID> | Marker interface, tự chọn chữ ký | Muốn công bố API có chọn lọc. |
| CrudRepository<T, ID> | Hợp đồng CRUD thông dụng | Cần thao tác cơ bản, không đặc thù MongoDB. |
| ListCrudRepository<T, ID> | Biến thể CRUD với kết quả danh sách | Dùng khi phiên bản Spring Data có hỗ trợ. |
| MongoRepository<T, ID> | Hợp đồng đồng bộ dành riêng MongoDB | Khi cần CRUD MongoDB thông dụng. |
| ReactiveMongoRepository<T, ID> | Hợp đồng CRUD reactive | Dùng Mono/Flux trong ứng dụng reactive. |

Trong các phiên bản Spring Data mới, một số khả năng như phân trang hoặc sorting nằm ở những interface chuyên biệt. Hãy xem đúng API của phiên bản đang dùng khi lựa chọn hợp đồng cho base.

### 6.1. Base CRUD đầy đủ

~~~java
@NoRepositoryBean
public interface FullAccessMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

Đây là lựa chọn đơn giản khi mọi repository con đều được phép công bố CRUD. Nó không có nghĩa các user cuối có quyền ghi database; việc bảo vệ thao tác cần xử lý ở các tầng khác.

### 6.2. Base chỉ đọc bằng Repository<T, ID>

~~~java
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadOnlyMongoRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    boolean existsById(ID id);

    Iterable<T> findAll();
}
~~~

Repository cụ thể:

~~~java
public interface ProductReadRepository
        extends ReadOnlyMongoRepository<ProductDocument, ObjectId> {
}
~~~

Các chữ ký này tương ứng với thao tác CRUD mà implementation cơ sở biết xử lý. Vì interface không công bố save hay delete, code nhận ProductReadRepository **không thể gọi trực tiếp các phương thức ghi qua kiểu đó**.

Tuy nhiên, đây chỉ là **giới hạn API Java**. Code khác vẫn có thể dùng MongoTemplate, driver hoặc một repository khác để ghi dữ liệu. Nếu cần cấm ghi thực sự, phải áp dụng quyền truy cập MongoDB và các kiểm soát ứng dụng phù hợp.

## 7. Phân biệt bốn loại phương thức

| Loại | Ví dụ | Cơ chế |
| --- | --- | --- |
| CRUD kế thừa | findById, save, deleteById | Hạ tầng repository có triển khai sẵn. |
| Java default method | getRequired | Có phần thân trong interface, dùng API kế thừa. |
| Derived query | findBySku(String sku) | Spring Data phân tích tên method theo property của domain. |
| Custom method | existsAnyByIds(Iterable<ID>) | Cần implementation rõ ràng nếu không có trong CRUD tiêu chuẩn. |

### 7.1. Default method không phải derived query

~~~java
@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    default boolean isEmptyRepository() {
        return count() == 0;
    }
}
~~~

Spring Data không cần tìm property tên emptyRepository; Java đã có cách tính bằng count. Đổi lại, thao tác count có chi phí truy vấn riêng, nên không nên gọi liên tục trên collection rất lớn khi không cần thiết.

### 7.2. Derived query cần property có thật

~~~java
// Không phù hợp trong base nếu không phải domain nào cũng có status.
List<T> findByStatus(String status);
~~~

Nếu ProductDocument không có field status, Spring Data có thể lỗi khi khởi tạo ProductRepository do không phân giải được property. Chỉ đưa những query thực sự chung vào base khi các domain đều có hợp đồng property tương ứng.

Phương thức findBySku phải nằm trong ProductRepository vì sku là thuộc tính riêng của ProductDocument.

### 7.3. @NoRepositoryBean không tạo implementation tùy ý

~~~java
@NoRepositoryBean
public interface ExtendedMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    boolean existsAnyByIds(Iterable<ID> ids);
}
~~~

Nếu không có implementation hoặc query hỗ trợ, Spring Data có thể hiểu nhầm existsAnyByIds là một derived query và báo lỗi property resolution. Annotation @NoRepositoryBean chỉ bảo Spring Data **bỏ qua tạo bean từ interface trung gian**, không làm các method trừu tượng được triển khai tự động.

## 8. Mở rộng bằng repository base class

Nếu một thao tác đặc thù thực sự cần áp dụng cho **tất cả repository được cấu hình**, có thể xây implementation cơ sở kế thừa SimpleMongoRepository và cấu hình repository factory.

### 8.1. Hợp đồng dùng chung

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ExtendedMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    boolean existsAnyByIds(Iterable<ID> ids);
}
~~~

### 8.2. Implementation minh họa

~~~java
package com.example.catalog;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.repository.query.MongoEntityInformation;
import org.springframework.data.mongodb.repository.support.SimpleMongoRepository;

public class ExtendedMongoRepositoryImpl<T, ID>
        extends SimpleMongoRepository<T, ID>
        implements ExtendedMongoRepository<T, ID> {

    private final MongoOperations mongoOperations;
    private final Class<T> domainType;

    public ExtendedMongoRepositoryImpl(
            MongoEntityInformation<T, ID> information,
            MongoOperations mongoOperations) {
        super(information, mongoOperations);
        this.mongoOperations = mongoOperations;
        this.domainType = information.getJavaType();
    }

    @Override
    public boolean existsAnyByIds(Iterable<ID> ids) {
        Objects.requireNonNull(ids, "ids must not be null");

        List<ID> values = new ArrayList<>();
        ids.forEach(values::add);
        if (values.isEmpty()) {
            return false;
        }

        Query query = Query.query(
            Criteria.where("_id").in(values)
        );
        return mongoOperations.exists(query, domainType);
    }
}
~~~

Hàm existsAnyByIds kiểm tra xem có ít nhất một document mang ID thuộc tập đầu vào. Với tập rỗng, nó trả false và tránh một truy vấn không cần thiết. MongoOperations nhận **domainType**, nhờ đó có thể dùng metadata mapping để chọn collection phù hợp.

Ví dụ dựa trên các API của Spring Data MongoDB có hỗ trợ chữ ký constructor nêu trên. Khi đưa vào dự án thật, cần kiểm tra phiên bản thư viện và chữ ký SimpleMongoRepository/MongoEntityInformation, đặc biệt nếu hệ thống có converter ID tùy chỉnh hoặc nhiều template/database.

### 8.3. Đăng ký repositoryBaseClass

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackages = "com.example.catalog",
    repositoryBaseClass = ExtendedMongoRepositoryImpl.class
)
public class MongoRepositoryConfiguration {
}
~~~

Repository con:

~~~java
public interface ProductRepository
        extends ExtendedMongoRepository<ProductDocument, ObjectId> {
}
~~~

Service có thể gọi:

~~~java
boolean found = products.existsAnyByIds(
    java.util.List.of(idA, idB)
);
~~~

**Chỉ thêm class ExtendedMongoRepositoryImpl nhưng quên cấu hình repositoryBaseClass chưa đủ** để repository factory sử dụng implementation này. Nếu dự án đã có cấu hình repository scanning do Spring Boot hoặc cấu hình riêng đảm nhiệm, hãy tích hợp thuộc tính cần thiết vào một cấu hình nhất quán, tránh quét trùng cùng một interface.

### 8.4. Khi nào nên dùng repository fragment?

Repository base class ảnh hưởng các repository trong **phạm vi factory** đã cấu hình. Nếu chỉ ProductRepository cần tính năng riêng, ví dụ tìm kiếm full-text hoặc một aggregation phức tạp, **repository fragment** thường hợp lý hơn.

Fragment gồm một interface hợp đồng và một implementation được ghép vào repository có nhu cầu. Nó khác @NoRepositoryBean vì fragment cung cấp hành vi thực thi; @NoRepositoryBean chỉ xử lý việc có tạo repository bean cho interface trung gian hay không.

| Nhu cầu | Cơ chế nên xem xét |
| --- | --- |
| Chia sẻ getRequired dựa trên findById | Default method trong base interface. |
| Chia sẻ CRUD tiêu chuẩn | Base interface kế thừa MongoRepository. |
| Chỉ Product cần aggregation tùy chỉnh | Custom fragment của ProductRepository. |
| Nhiều repository cần cùng thao tác nền tảng có code riêng | Custom base class / fragment dùng chung. |
| Ngăn tạo bean từ base generic | @NoRepositoryBean. |

## 9. Chọn kiểu generic T và ID chính xác

Giao diện trung gian:

~~~java
@NoRepositoryBean
interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

Repository con phải ràng buộc đúng domain và kiểu ID:

~~~java
interface ProductRepository
        extends BaseMongoRepository<ProductDocument, ObjectId> {
}
~~~

Không nên dùng kiểu ID không tương thích:

~~~java
// Không phù hợp khi ProductDocument khai báo @Id ObjectId.
interface WrongProductRepository
        extends BaseMongoRepository<ProductDocument, String> {
}
~~~

Một số trường hợp Spring Data có thể chuyển giữa String hex và BSON ObjectId, nhưng việc khai báo type parameter sai khiến hợp đồng Java thiếu rõ ràng và khó kiểm thử. Khi domain dùng ObjectId, nên thống nhất ObjectId trong repository và service nếu không có lý do thiết kế khác.

### 9.1. Không nhầm kiểu T với tên collection

Trong ví dụ ProductDocument mang **@Document(collection = "products")** và CustomerDocument mang **@Document(collection = "customers")**. Dù cùng kế thừa BaseMongoRepository, mỗi repository con thao tác theo **metadata domain type** riêng.

Nếu ứng dụng có nhiều database hoặc MongoTemplate, hạ tầng repository được gắn với cấu hình MongoDB tương ứng; @NoRepositoryBean không định tuyến repository sang database khác.

## 10. Phạm vi quét repository và dependency injection

Trong ứng dụng Spring Boot có cấu trúc package thông dụng, repository scanning thường được cấu hình tự động theo package ứng dụng. Nếu repository ở ngoài phạm vi đó, cần cấu hình rõ:

~~~java
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@EnableMongoRepositories(
    basePackages = "com.example.catalog"
)
public class RepositoryConfiguration {
}
~~~

Ví dụ trên minh họa scanning; nếu đã dùng **repositoryBaseClass** như phần 8, cần khai báo các thuộc tính trong cấu hình factory thích hợp, tránh tạo hai cấu hình quét trùng.

Trong service, Spring Data repository là bean được inject:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogLookupService {
    private final ProductRepository products;

    public CatalogLookupService(ProductRepository products) {
        this.products = products;
    }
}
~~~

Không cần đặt @Repository lên ProductRepository nếu repository scanning đã tạo bean hợp lệ. Ngược lại, **không đặt @NoRepositoryBean lên ProductRepository** nếu muốn inject trực tiếp repository này.

### 10.1. Kiểm tra đúng ý nghĩa của NoRepositoryBean

Một lỗi trong kiểm thử:

~~~java
// Sai kỳ vọng nếu đã có ProductRepository được tạo thành công.
applicationContext.getBeansOfType(BaseMongoRepository.class).isEmpty();
~~~

Tại sao sai? ProductRepository là một bean **có kiểu con** của BaseMongoRepository. Vì vậy truy vấn các bean theo BaseMongoRepository.class vẫn có thể trả về ProductRepository. @NoRepositoryBean chỉ ngăn **bean riêng dành cho interface base generic**, không loại bỏ các bean cụ thể khỏi hệ phân cấp type.

Khi kiểm tra, hãy xác nhận ProductRepository thực sự được inject và gọi được các phương thức, đồng thời không có một repository bean độc lập cho BaseMongoRepository.

## 11. @NoRepositoryBean không thay đổi ngữ nghĩa CRUD

### 11.1. Soft delete

Nếu định nghĩa:

~~~java
@NoRepositoryBean
interface SoftDeleteRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

thì deleteById vẫn có **ngữ nghĩa xóa của MongoRepository**. Chỉ đổi tên interface không làm dữ liệu được “đánh dấu đã xóa”. Muốn soft delete cần triển khai phương thức và policy riêng, gồm field trạng thái, query mặc định, index, retention và kiểm thử.

### 11.2. Multi-tenancy

Base generic không tự thêm điều kiện tenantId vào mọi derived query, aggregation hoặc MongoTemplate call. Nếu cần cách ly tenant, cần chính sách rõ và kiểm tra mọi đường đọc/ghi, không chỉ một repository interface.

### 11.3. Transaction

@NoRepositoryBean không tạo transaction. Dù nhiều repository cùng kế thừa một base, các lần save trên nhiều document không tự trở thành một đơn vị nguyên tử. Transaction phải được cấu hình trên MongoDB deployment phù hợp và đặt ranh giới theo bất biến nghiệp vụ.

### 11.4. Cascade reference

Khi một entity tham chiếu document khác bằng ObjectId, @DBRef hoặc @DocumentReference, việc gọi save/delete trên repository cha không tự cascade-save/cascade-delete document đích theo mặc định. Quy tắc xử lý liên kết là thiết kế nghiệp vụ độc lập với base repository.

## 12. Chuyên biệt hóa repository trong hệ thống reactive

Một dự án dùng ReactiveMongoRepository cần một base reactive riêng:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseReactiveMongoRepository<T, ID>
        extends ReactiveMongoRepository<T, ID> {
}
~~~

Repository cụ thể:

~~~java
public interface ReactiveProductRepository
        extends BaseReactiveMongoRepository<ProductDocument, ObjectId> {
}
~~~

Reactive default method có thể trả về Mono:

~~~java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;

@NoRepositoryBean
public interface BaseReactiveMongoRepository<T, ID>
        extends ReactiveMongoRepository<T, ID> {

    default Mono<T> getRequired(ID id) {
        return findById(id).switchIfEmpty(
            Mono.error(new NoSuchElementException(
                "Document not found for id: " + id
            ))
        );
    }
}
~~~

**@NoRepositoryBean vẫn ngăn tạo bean cho generic base**, nhưng không biến MongoRepository đồng bộ thành reactive. Không dùng block() trong default method để lấy giá trị Mono đồng bộ. Những custom repository base cho reactive cũng cần hạ tầng implementation phù hợp với reactive driver/template.

## 13. Thiết kế package và phạm vi tái sử dụng

Một cấu trúc minh họa:

~~~text
com.example.catalog
├── persistence
│   ├── base
│   │   ├── BaseMongoRepository.java
│   │   └── ExtendedMongoRepositoryImpl.java
│   ├── product
│   │   ├── ProductDocument.java
│   │   └── ProductRepository.java
│   └── customer
│       ├── CustomerDocument.java
│       └── CustomerRepository.java
└── service
    └── ProductService.java
~~~

BaseMongoRepository là hợp đồng hạ tầng được nhiều repository kế thừa; các query domain nằm trong repository cụ thể. Khi nhiều module dùng chung base interface, cần giữ API của nó nhỏ và rõ. Một “super repository” chứa hàng chục phương thức business-specific thường tạo coupling và nguy cơ lỗi query ở domain không có property tương ứng.

Khi chia sẻ base repository qua nhiều dịch vụ, cần xét sự tương thích phiên bản Spring Data, lựa chọn kiểu ID, chính sách exception và phạm vi scanning. Không cần tạo thư viện chung chỉ để chia sẻ một phương thức getRequired nếu chi phí phụ thuộc lớn hơn lợi ích.

## 14. Kiểm thử tích hợp

Kiểm thử repository nên chạy với **MongoDB dành riêng cho test**, ví dụ một instance Testcontainers được cấu hình cho ứng dụng. Chỉ mock ProductRepository không xác nhận được repository factory có tạo bean con hay không.

Các điều cần xác minh:

1. ProductRepository được tạo và inject thành công.
2. BaseMongoRepository không được tạo thành bean generic độc lập.
3. Phương thức default getRequired hoạt động trên repository con.
4. ProductRepository dùng collection products theo @Document.
5. findBySku dùng property có thật; save/insert và ID hoạt động đúng.
6. Nếu thêm custom base implementation, method tùy chỉnh được gọi qua implementation đã đăng ký.

Ví dụ JUnit 5 với cấu hình MongoDB test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @Autowired
    private MongoTemplate template;

    @Test
    void concreteRepositoryInheritsBaseMethod() {
        assertThat(template.getCollectionName(ProductDocument.class))
            .isEqualTo("products");

        String sku = "TEST-" + UUID.randomUUID();
        ProductDocument inserted = products.insert(
            new ProductDocument(null, sku, "Sample", true)
        );
        ObjectId id = inserted.id();

        assertThat(id).isNotNull();
        try {
            ProductDocument found = products.getRequired(id);
            assertThat(found.sku()).isEqualTo(sku);
            assertThat(products.findBySku(sku)).isPresent();
        } finally {
            products.deleteById(id);
        }
    }
}
~~~

Ví dụ yêu cầu Spring Boot test và MongoDB test đã được cấu hình đúng. Nếu dự án sử dụng repositoryBaseClass tùy chỉnh, phải import/cấu hình đúng factory trong test để kiểm chứng đường chạy production.

### 14.1. Kiểm thử lỗi cấu hình

Những ca kiểm tra nên có trong quy trình review:

- Quên @NoRepositoryBean trên interface generic: kiểm tra hành vi startup.
- Gắn nhầm @NoRepositoryBean trên repository cụ thể: xác nhận bean không được tạo.
- Đưa findBySku lên base nhưng một domain không có sku: bắt lỗi derived query.
- Đổi kiểu ID repository từ ObjectId sang String mà không đổi model: phát hiện sai hợp đồng.
- Có custom method nhưng quên cấu hình implementation: phát hiện lỗi tạo repository.

Không cần để các cấu hình lỗi cố ý ở lại mã production; chúng là tình huống huấn luyện hoặc fixture riêng nếu dự án có nhu cầu kiểm thử cơ chế startup.

## 15. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Spring cố tạo repository cho BaseMongoRepository | Quên @NoRepositoryBean ở interface generic | Đánh dấu @NoRepositoryBean ở đúng base. |
| ProductRepository không inject được | Đặt @NoRepositoryBean lên concrete interface hoặc scan thiếu | Xác minh annotation, package scanning. |
| Không xác định được domain/ID | Interface vẫn generic hoặc ràng buộc type sai | Chốt T/ID trong repository con. |
| Startup báo thiếu property | Derived query ở base dùng field không có trên mọi domain | Chuyển query về repository có field đó. |
| Custom method không chạy | Chỉ khai báo chữ ký, chưa có implementation | Dùng default method, fragment hoặc repositoryBaseClass. |
| Custom base class bị bỏ qua | Chưa đăng ký repositoryBaseClass | Kiểm tra cấu hình repository factory. |
| Truy vấn tới sai collection | Sai @Document hoặc template/database | Kiểm tra domain metadata và cấu hình MongoDB. |
| Read-only API vẫn có nơi ghi dữ liệu | Hạn chế interface không phải quyền truy cập database | Bổ sung phân quyền và ranh giới ứng dụng. |
| Reactive code bị chặn luồng | Dùng repository đồng bộ hoặc block() | Dùng ReactiveMongoRepository và pipeline Mono/Flux. |

Quy trình điều tra theo thứ tự:

1. Xác định tên interface mà repository factory đang xử lý.
2. Xem interface đó là base generic hay repository concrete và có @NoRepositoryBean ở đúng nơi không.
3. Xác nhận domain type, ID type và annotation @Document.
4. Kiểm tra phạm vi scanning và template/database được dùng.
5. Nếu có derived query, đối chiếu method name với property Java của domain.
6. Nếu có custom method, kiểm tra fragment/base implementation và cấu hình repositoryBaseClass.
7. Khi đã tạo bean thành công nhưng truy vấn chậm, kiểm tra index, dữ liệu thực và kế hoạch truy vấn MongoDB; @NoRepositoryBean không trực tiếp điều khiển hiệu năng query.

## 16. Bài tập thực hành

### Bài tập 1: đặt annotation ở đâu?

~~~java
interface SharedRepository<T, ID>
        extends MongoRepository<T, ID> {}

interface ItemRepository
        extends SharedRepository<ItemDocument, ObjectId> {}
~~~

**Câu hỏi:** thêm @NoRepositoryBean ở đâu để vẫn inject ItemRepository?

**Đáp án:** gắn annotation vào SharedRepository, vì nó là interface trung gian generic. ItemRepository là interface concrete nên không được đánh dấu nếu muốn Spring Data tạo bean.

### Bài tập 2: default method có cần implementation không?

~~~java
@NoRepositoryBean
interface BaseRepository<T, ID> extends MongoRepository<T, ID> {
    default T require(ID id) {
        return findById(id).orElseThrow();
    }
}
~~~

**Đáp án:** không cần implementation class riêng cho require. Đây là default method dùng findById có sẵn, không bị phân tích như derived query.

### Bài tập 3: sai derived query

ProductDocument có sku nhưng CustomerDocument không có. Điều gì xảy ra nếu đặt findBySku(String sku) ở BaseMongoRepository?

**Đáp án:** repository của domain không có sku có thể lỗi lúc khởi tạo vì Spring Data không phân giải được property. Đưa findBySku vào ProductRepository.

### Bài tập 4: giới hạn CRUD

Thiết kế ReadOnlyMongoRepository<T, ID> chỉ công bố findById, existsById và findAll.

**Gợi ý:** kế thừa Repository<T, ID>, thêm @NoRepositoryBean và khai báo các chữ ký tương thích với CRUD implementation. Muốn cấm ghi thực sự cần quyền MongoDB và kiến trúc ứng dụng phù hợp.

### Bài tập 5: triển khai method tùy chỉnh

Base interface có existsAnyByIds(Iterable<ID> ids) nhưng ứng dụng lỗi khi tạo repository con. Điều cần xem là gì?

**Đáp án:** kiểm tra phương thức đã có default body hoặc custom implementation hay chưa. Nếu dùng SimpleMongoRepository mở rộng, cần cấu hình repositoryBaseClass; @NoRepositoryBean không tự triển khai method.

### Bài tập 6: hiểu sai bean type

Một test yêu cầu applicationContext.getBeansOfType(BaseMongoRepository.class) trả rỗng dù ProductRepository hoạt động. Vì sao kỳ vọng này sai?

**Đáp án:** ProductRepository là một bean có type kế thừa BaseMongoRepository, nên tra cứu theo type base vẫn có thể trả ProductRepository. Annotation chỉ ngăn tạo bean trực tiếp cho interface base.

### Bài tập 7: đổi sang reactive

Ứng dụng dùng Reactor, muốn getRequired trả Mono<T>. Có nên tiếp tục dùng MongoRepository cho base?

**Đáp án:** không. Tạo BaseReactiveMongoRepository kế thừa ReactiveMongoRepository, gắn @NoRepositoryBean và viết default method trả Mono, tránh block().

## 17. Các nguyên tắc cần ghi nhớ

1. **@NoRepositoryBean được đặt trên interface repository trung gian** mà Spring Data không nên tạo bean riêng.
2. **Repository cụ thể gắn domain/ID vẫn được Spring Data tạo bean** nếu nằm trong phạm vi scanning và không bị đánh dấu loại trừ.
3. **MongoRepository chia sẻ CRUD**, còn collection được quyết định bởi domain metadata và cấu hình MongoDB của repository con.
4. **Java default method** không cần implementation riêng; derived query phải khớp property Java; custom method phải có cơ chế triển khai.
5. **Repository fragment và repositoryBaseClass** cung cấp hành vi bổ sung, còn @NoRepositoryBean chỉ điều khiển repository discovery.
6. **ReadOnlyRepository giới hạn API biên dịch**, không thay thế phân quyền database.
7. **ReactiveMongoRepository cần base reactive riêng** với các phương thức Mono/Flux.
8. **Soft delete, transaction, tenant và cascade phải thiết kế riêng**, không tự xuất hiện từ annotation.
9. **Kiểm thử repository với MongoDB test thật** để xác nhận bean, ID, collection và hành vi CRUD trước khi mở rộng.

Thiết kế giao diện cơ sở bằng **@NoRepositoryBean** giúp tầng repository của **SPRING_DATA_MONGODB** nhất quán, tránh tạo nhầm bean generic và giữ ranh giới rõ giữa CRUD dùng chung với truy vấn nghiệp vụ của từng document. Đây là nền tảng cho việc phát triển repository, MongoTemplate, aggregation, index và các luồng truy cập dữ liệu có thể kiểm thử và bảo trì.
