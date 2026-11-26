# Metadata của repository, entity và kiểu kết quả

## 1. Proxy cần biết nhiều hơn tên phương thức

Một repository có thể khai báo:

```java
Page<ProductSummary> findByActiveTrue(Pageable pageable);
```

Để xử lý lời gọi này, hạ tầng cần biết:

- Repository quản lý domain nào và kiểu ID nào.
- Phương thức thuộc nhóm CRUD, truy vấn hay phần triển khai mở rộng.
- Domain có những thuộc tính nào và chúng được lưu bằng tên gì.
- Pageable là tham số điều khiển phân trang hay một giá trị cần đưa vào điều kiện.
- Kết quả là một Page chứa projection, thay vì một entity đơn lẻ.

Các thông tin mô tả cấu trúc, kiểu và hợp đồng đó được gọi là **metadata**.

Trong module **SPRING_DATA_COMMONS**, metadata giúp hạ tầng repository tái sử dụng những quy tắc chung cho CRUD, derived query, phân trang, projection, Query by Example và auditing. Store module bổ sung thông tin và cách thực thi theo kho dữ liệu.

Bài này phân biệt ba nhóm trọng tâm:

1. Metadata của repository.
2. Metadata của entity và thuộc tính.
3. Metadata của phương thức, tham số và kiểu kết quả.

## 2. Metadata khác với dữ liệu đang được lưu

| Thông tin | Thuộc nhóm nào? |
| --- | --- |
| Repository quản lý Product | Metadata repository |
| ID của Product có kiểu String | Metadata kiểu/định danh |
| Thuộc tính name ánh xạ sang product_name | Metadata mapping |
| Phương thức trả Page<ProductSummary> | Metadata kết quả |
| SKU của một sản phẩm bằng KEY-001 | Giá trị dữ liệu của một instance |
| Sản phẩm đang có giá 1.200.000 VND | Giá trị dữ liệu |
| createdAt của một bản ghi là một thời điểm cụ thể | Dữ liệu auditing |
| Một thuộc tính được đánh dấu là thời điểm tạo | Metadata auditing |

Metadata mô tả cách hiểu dữ liệu và hợp đồng truy cập. Nó không phải toàn bộ nội dung bản ghi trong cơ sở dữ liệu.

Một số abstraction kết hợp metadata với instance để đưa ra quyết định, chẳng hạn xác định đối tượng mới dựa vào ID hoặc version. Điều đó vẫn không làm metadata trở thành bản sao dữ liệu lưu trữ.

## 3. Bản đồ các abstraction thường gặp

| Abstraction | Câu hỏi chính |
| --- | --- |
| RepositoryMetadata | Interface repository quản lý domain và ID nào? |
| RepositoryInformation | Repository được ghép với base implementation và các phương thức thế nào? |
| PersistentEntity | Kiểu domain có cấu trúc mapping và các thuộc tính gì? |
| PersistentProperty | Một thuộc tính có tên, kiểu và vai trò mapping nào? |
| EntityInformation | Lấy ID và đánh giá trạng thái mới của một instance theo chiến lược nào? |
| QueryMethod | Phương thức truy vấn có hợp đồng tham số và kết quả gì? |
| Parameters | Đâu là tham số bind, đâu là tham số điều khiển đặc biệt? |
| ReturnedType và ResultProcessor | Kết quả cần được nhìn như domain, DTO hay projection nào? |

Không cần ứng dụng trực tiếp sử dụng tất cả các abstraction này. Chúng chủ yếu phục vụ hạ tầng, tooling hoặc những phần mở rộng repository.

Cũng không nên gộp chúng thành một đối tượng “metadata chung” rồi giả định nó biết mọi thứ từ schema đến giá trị đang nằm trong database.

## 4. Ví dụ domain dùng để theo dõi các tầng metadata

Ví dụ chính chọn một Product được mapping cho MongoDB để nhìn rõ abstraction PersistentEntity và PersistentProperty. Những hợp đồng repository và kết quả vẫn thuộc phần dùng chung của Commons.

### 4.1. Product

```java
package example.metadata;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("products")
public class Product {

    @Id
    private String id;

    private String sku;

    @Field("product_name")
    private String name;

    private String category;

    private Long priceInVnd;

    private boolean active;

    public Product() {
    }

    public Product(
            String sku,
            String name,
            String category,
            Long priceInVnd,
            boolean active
    ) {
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.priceInVnd = priceInVnd;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public Long getPriceInVnd() {
        return priceInVnd;
    }

    public boolean isActive() {
        return active;
    }
}
```

Giá trong ví dụ là số nguyên VND, biểu diễn bằng Long để tập trung vào kiểu thuộc tính. Đây không phải yêu cầu rằng mọi domain tiền tệ phải dùng Long.

Tên Java name khác tên trường lưu trữ product_name. Sự khác biệt này sẽ xuất hiện trong mapping metadata.

### 4.2. Projection

```java
package example.metadata;

public interface ProductSummary {

    String getSku();

    String getName();

    Long getPriceInVnd();
}
```

ProductSummary là hình dạng kết quả đọc. Nó không thay Product trở thành domain gốc của repository.

### 4.3. Repository

```java
package example.metadata;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByActiveTrue();

    Page<ProductSummary> findByActiveTrue(
            Pageable pageable
    );

    Slice<Product> findByCategory(
            String category,
            Pageable pageable
    );

    <R> List<R> findByCategory(
            String category,
            Class<R> resultType
    );

    long countByActiveTrue();
}
```

Mỗi public type đặt trong một tệp Java riêng. Các đoạn kiểm tra metadata ở những phần sau dùng chính các kiểu này.

Việc mô tả và đọc metadata không tự tạo repository bean hoặc kết nối MongoDB. Muốn thực thi repository thật, vẫn cần store module và cấu hình phù hợp.

## 5. RepositoryMetadata: domain type và ID type

### 5.1. Đọc generic trên hợp đồng repository

Với:

```java
CrudRepository<Product, String>
```

hạ tầng xác định:

```text
Repository interface = ProductRepository
Domain type          = Product
ID type              = String
```

Đây là thông tin từ hợp đồng repository. Nó không phải kết quả của một truy vấn database.

Có thể quan sát bằng API Commons:

```java
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.support.DefaultRepositoryMetadata;

RepositoryMetadata metadata =
        new DefaultRepositoryMetadata(
                ProductRepository.class
        );

System.out.println(
        metadata.getRepositoryInterface().getSimpleName()
);
System.out.println(
        metadata.getDomainType().getSimpleName()
);
System.out.println(
        metadata.getIdType().getSimpleName()
);
```

Kết quả có ý nghĩa:

```text
ProductRepository
Product
String
```

Ví dụ dùng repository kế thừa Repository qua CrudRepository, phù hợp với DefaultRepositoryMetadata. Những hình thức khai báo khác có thể cần con đường tạo metadata tương ứng của hạ tầng.

### 5.2. Generic có thể nằm qua nhiều tầng

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface LookupRepository<T, ID>
        extends Repository<T, ID> {

    java.util.Optional<T> findById(ID id);
}
```

Một repository cụ thể:

```java
public interface ProductLookupRepository
        extends LookupRepository<Product, String> {
}
```

Hạ tầng cần giải quyết generic qua cây kế thừa để đi từ T, ID đến Product, String. Chỉ nhìn getReturnType của một method khai báo trên interface generic có thể cho thông tin thô hoặc kiểu chưa được giải quyết theo repository cụ thể.

Vì thế, công cụ tự viết không nên suy domain bằng cách lấy interface cha đầu tiên rồi ép kiểu theo một cấu trúc cố định.

### 5.3. Domain của repository không đổi theo từng method

Dù ProductRepository có phương thức trả ProductSummary hoặc long, domain type của nó vẫn là Product.

Không được suy rằng:

```text
Có method trả ProductSummary
    → repository quản lý ProductSummary

Có method trả long
    → repository quản lý Long
```

Kiểu aggregate mà repository quản lý và kiểu kết quả của một truy vấn là hai tầng khác nhau.

## 6. RepositoryInformation: metadata sau khi có thêm thông tin triển khai

RepositoryMetadata tập trung vào hợp đồng. RepositoryInformation bổ sung góc nhìn phục vụ việc ghép repository với implementation và phân loại phương thức.

Hạ tầng có thể cần biết:

- Base implementation nào thực hiện phương thức CRUD.
- Phương thức nào thuộc phần tùy chỉnh.
- Phương thức nào được xử lý như query method.
- Phương thức hợp đồng tương ứng với phương thức thực thi nào.

Không nên tự phân loại tất cả bằng tiền tố tên:

- Một default method có thân Java không chỉ là chuỗi ký tự để tạo query.
- Một fragment có thể cung cấp implementation cho phương thức nghiệp vụ.
- Một phương thức kế thừa có thể được base implementation xử lý.
- Một phương thức truy vấn có thể dùng cơ chế khai báo theo store.

RepositoryInformation không phải một kho chứa dữ liệu Product. Nó mô tả cấu trúc thực hiện của repository để proxy và các thành phần liên quan phối hợp.

## 7. Metadata entity: cấu trúc mapping của domain

### 7.1. PersistentEntity và PersistentProperty

Trong những module sử dụng mapping abstraction của Commons:

- PersistentEntity mô tả một kiểu domain.
- PersistentProperty mô tả một thuộc tính của kiểu đó.
- MappingContext quản lý và cung cấp metadata của các kiểu đã được nhận diện.

Metadata có thể cho biết:

| Mục | Ví dụ |
| --- | --- |
| Kiểu domain | Product |
| Thuộc tính ID | id |
| Kiểu Java của ID | String |
| Thuộc tính name | Có kiểu String |
| Vai trò version | Có hay không có thuộc tính version theo mapping |
| Cách tạo instance | Constructor hoặc cơ chế tạo đối tượng phù hợp |
| Thông tin theo store | Tên collection, tên trường lưu trữ, đặc điểm mapping |

Các module bổ sung metadata chuyên biệt. Với MongoDB, MongoPersistentEntity và MongoPersistentProperty mở rộng góc nhìn dùng chung bằng thông tin document.

### 7.2. Quan sát mapping mà không cần truy vấn dữ liệu

Với Product ở phần trước:

```java
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.core.mapping.MongoPersistentEntity;
import org.springframework.data.mongodb.core.mapping.MongoPersistentProperty;

MongoMappingContext mappingContext =
        new MongoMappingContext();

mappingContext.afterPropertiesSet();

MongoPersistentEntity<?> entity =
        mappingContext.getRequiredPersistentEntity(
                Product.class
        );

System.out.println(entity.getType().getSimpleName());
System.out.println(entity.getCollection());

MongoPersistentProperty idProperty =
        entity.getIdProperty();

if (idProperty != null) {
    System.out.println(idProperty.getName());
    System.out.println(idProperty.getType().getSimpleName());
    System.out.println(idProperty.getFieldName());
}

MongoPersistentProperty nameProperty =
        entity.getPersistentProperty("name");

if (nameProperty != null) {
    System.out.println(nameProperty.getFieldName());
}
```

Các thông tin có thể đối chiếu:

```text
Kiểu domain:             Product
Collection được mapping: products
Tên thuộc tính ID:       id
Kiểu Java của ID:        String
Tên trường ID MongoDB:   _id
Tên trường của name:     product_name
```

Đoạn code xây mapping metadata từ kiểu Java và annotation. Nó không tạo MongoClient và không đọc các document đang tồn tại.

Trong ứng dụng thực tế, nên sử dụng mapping context đã được cấu hình với các conversion và tùy chọn của ứng dụng. Một context tối giản để minh họa không thay thế toàn bộ cấu hình production.

### 7.3. Nhìn qua abstraction chung

Có thể nhận một PersistentEntity mà không biết chi tiết MongoDB:

```java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;

static void printProperties(
        PersistentEntity<?, ?> entity
) {
    System.out.println(entity.getType().getSimpleName());

    for (PersistentProperty<?> property : entity) {
        System.out.println(
                property.getName()
                        + " : "
                        + property.getType().getSimpleName()
        );
    }
}
```

Helper dùng tên và kiểu thuộc tính Java. Nếu cần collection hoặc tên trường MongoDB, phải sử dụng metadata chuyên biệt hoặc abstraction có hợp đồng tương ứng.

Đừng thêm một phép cast sang MongoPersistentProperty vào một utility được tuyên bố hỗ trợ mọi store nếu utility đó thực sự cần tính độc lập công nghệ.

### 7.4. Không phải mọi store dùng một mô hình mapping giống hệt nhau

JPA có metamodel và cơ chế mapping của JPA provider. Spring Data JPA tích hợp thêm các abstraction như JpaEntityInformation.

Không nên khẳng định mọi thông tin mapping JPA đều được đọc bằng MongoMappingContext, hoặc mọi store phải cung cấp cùng một loại PersistentEntity với đủ các chi tiết giống nhau.

Commons cung cấp những điểm dùng chung; store module quyết định cách kết hợp chúng với hệ thống mapping của công nghệ đang tích hợp.

## 8. EntityInformation: dùng metadata để làm việc với một instance

EntityInformation thuộc góc nhìn repository về entity, thường cung cấp những khả năng như:

- Biết kiểu domain và kiểu ID.
- Lấy ID từ một instance.
- Đánh giá instance có được xem là mới theo chiến lược áp dụng hay không.

Có thể viết một helper theo hợp đồng này:

```java
import org.springframework.data.repository.core.EntityInformation;

static <T, ID> void inspectState(
        EntityInformation<T, ID> information,
        T entity
) {
    System.out.println(
            information.getJavaType().getSimpleName()
    );

    System.out.println(
            information.getIdType().getSimpleName()
    );

    System.out.println(information.getId(entity));
    System.out.println(information.isNew(entity));
}
```

Đối tượng EntityInformation phải do hạ tầng hoặc implementation phù hợp cung cấp. Helper không tự xây được chiến lược nhận diện mới chỉ từ tên lớp.

### 8.1. isNew không có nghĩa đã kiểm tra database

Một chiến lược có thể dựa vào:

- ID có giá trị hay chưa.
- Version.
- Quyết định từ Persistable.
- Metadata và quy tắc riêng của store.

Kết quả isNew phản ánh cách hạ tầng phân loại instance theo chiến lược đó. Không mặc định nó đã thực hiện truy vấn exists.

Một đối tượng có ID được ứng dụng cấp trước vẫn có thể là đối tượng mới. Một đối tượng còn ID sau rollback chưa chứng minh bản ghi đã commit.

### 8.2. Phân biệt hai abstraction về entity

| Abstraction | Trọng tâm |
| --- | --- |
| PersistentEntity | Cấu trúc thuộc tính và mapping |
| EntityInformation | Thông tin entity phục vụ repository, gồm ID và quyết định trạng thái |

Chúng có thể sử dụng thông tin liên quan nhưng không phải hai tên gọi thay thế hoàn toàn cho nhau.

Việc đọc được thuộc tính id trong mapping chưa tự chứng minh cách một implementation cụ thể sẽ quyết định insert hay update.

## 9. Metadata kết quả: kiểu bao và phần tử bên trong

### 9.1. Domain type không đủ để mô tả kết quả

Với ProductRepository, các phương thức có thể được đọc như sau:

| Chữ ký kết quả | Kiểu bao hoặc hình thức | Kiểu nội dung |
| --- | --- | --- |
| Product | Một đối tượng | Product |
| Optional<Product> | Không có hoặc có một kết quả | Product |
| List<Product> | Collection | Product |
| Page<ProductSummary> | Trang có metadata tổng | ProductSummary |
| Slice<Product> | Phần dữ liệu có thông tin tiếp tục | Product |
| long | Giá trị vô hướng | Số đếm theo hợp đồng method |

Không thể chỉ gọi getReturnType rồi kết luận toàn bộ hình dạng kết quả.

Với Page<ProductSummary>:

```text
Repository domain = Product
Raw return type   = Page
Element/result    = ProductSummary
```

Ba thông tin đều đúng và phục vụ các phần khác nhau của quá trình xử lý.

### 9.2. Kiểu bao ảnh hưởng chiến lược thực thi

Một method trả Page cho biết người gọi cần nội dung trang và metadata tổng theo hợp đồng.

Một method trả Slice không đưa ra cùng hợp đồng về tổng số phần tử.

Một method trả Optional không yêu cầu tạo một collection rỗng để biểu đạt không có dữ liệu.

Store module sử dụng thông tin này cùng query metadata để chọn cách thực thi. Nó không chỉ chạy một truy vấn bất kỳ rồi ép kiểu kết quả theo tên class Java.

### 9.3. Kiểu kết quả không tự chứng minh ngữ nghĩa nghiệp vụ

Optional<Product> không tạo index duy nhất trên SKU.

List<Product> không tự có thứ tự theo giá nếu method hoặc Sort không yêu cầu.

Page<ProductSummary> không tự chứng minh SQL hoặc command chỉ đọc đúng ba trường.

Metadata cho biết hợp đồng và hình dạng mà hạ tầng cần đáp ứng. Những bảo đảm về uniqueness, thứ tự và tối ưu truy vấn còn cần thiết kế và thực thi phù hợp.

## 10. QueryMethod: ghép thông tin method với repository

### 10.1. Đọc một method có Page và projection

Có thể quan sát các phần của một query method bằng API Commons:

```java
import java.lang.reflect.Method;

import org.springframework.data.domain.Pageable;
import org.springframework.data.projection.SpelAwareProxyProjectionFactory;
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.support.DefaultRepositoryMetadata;
import org.springframework.data.repository.query.QueryMethod;

RepositoryMetadata metadata =
        new DefaultRepositoryMetadata(
                ProductRepository.class
        );

Method method = ProductRepository.class.getMethod(
        "findByActiveTrue",
        Pageable.class
);

QueryMethod queryMethod = new QueryMethod(
        method,
        metadata,
        new SpelAwareProxyProjectionFactory()
);

System.out.println(
        method.getReturnType().getSimpleName()
);

System.out.println(queryMethod.isPageQuery());

System.out.println(
        queryMethod.getParameters().hasPageableParameter()
);

System.out.println(
        queryMethod.getParameters()
                .getBindableParameters()
                .getNumberOfParameters()
);

System.out.println(
        queryMethod.getResultProcessor()
                .getReturnedType()
                .getReturnedType()
                .getSimpleName()
);
```

Đặt đoạn code trong một phương thức khai báo hoặc xử lý ReflectiveOperationException do bước getMethod.

Với chữ ký đang xét, các giá trị có ý nghĩa:

```text
Raw return type:       Page
Là page query:         true
Có Pageable:          true
Số tham số bind:      0
Kiểu kết quả nội dung: ProductSummary
```

Điều kiện active true nằm trong tên derived query, không đến từ một đối số giá trị của method. Pageable phục vụ điều khiển phân trang, không phải một giá trị category hay SKU để bind.

### 10.2. Đoạn code này chưa thực thi truy vấn

Tạo QueryMethod không tự:

- Tạo repository proxy.
- Tạo kết nối.
- Chạy find.
- Đọc dữ liệu thực tế.
- Xác nhận store hỗ trợ mọi tổ hợp kiểu trả về.

Nó giúp nhìn cấu trúc hợp đồng. Factory và query implementation của store còn sử dụng các thành phần chuyên biệt để tạo, thực thi và chuyển đổi kết quả.

Khi dùng các API hạ tầng trong công cụ riêng, đối chiếu chữ ký và hành vi với phiên bản Commons thực tế. Không dựa vào một constructor quan sát trên một dòng phiên bản để mặc định toàn bộ API nội bộ luôn bất biến.

## 11. Metadata tham số: không phải mọi đối số đều là điều kiện truy vấn

| Tham số | Vai trò thông thường |
| --- | --- |
| String sku | Giá trị bind cho điều kiện SKU |
| String category | Giá trị bind cho điều kiện nhóm |
| Pageable | Điều khiển phân trang và có thể mang Sort |
| Sort | Điều khiển thứ tự khi chữ ký được hỗ trợ |
| Class<R> khớp mẫu dynamic projection | Chọn hình dạng kết quả theo lời gọi |

Ví dụ:

```java
Slice<Product> findByCategory(
        String category,
        Pageable pageable
);
```

Method có hai tham số Java nhưng chỉ category là tham số giá trị điều kiện. Pageable không biến thành điều kiện so sánh với một thuộc tính tên pageable.

Vì vậy, công cụ tạo query không thể lấy tất cả args rồi lần lượt đưa vào các placeholder mà không phân loại tham số.

Với dynamic projection, việc nhận diện còn phụ thuộc quan hệ generic giữa tham số Class và kiểu kết quả. Không phải mọi tham số có kiểu Class đều tự động là một projection selector.

## 12. Dynamic projection: kiểu kết quả còn phụ thuộc lời gọi

Repository có method:

```java
<R> List<R> findByCategory(
        String category,
        Class<R> resultType
);
```

Hai lời gọi:

```java
List<Product> products = repository.findByCategory(
        "PHU_KIEN",
        Product.class
);

List<ProductSummary> summaries =
        repository.findByCategory(
                "PHU_KIEN",
                ProductSummary.class
        );
```

Domain của repository vẫn là Product. Giá trị Class truyền vào giúp hạ tầng xác định hình dạng nội dung cần trả ở lần gọi cụ thể.

Không thể chỉ thấy raw return type là List rồi biết chắc phần tử là Product hay ProductSummary.

### 12.1. Kiểu generic và type token phục vụ hai việc liên quan

Ở cấp Java, R giúp compiler giữ quan hệ giữa Class<R> và List<R>.

Ở runtime, đối tượng Class được truyền vào mang thông tin lựa chọn cụ thể. Hạ tầng không tự đọc được toàn bộ ý định của caller chỉ nhờ tên biến nhận kết quả.

ResultProcessor và metadata về kiểu trả về có thể được điều chỉnh theo dynamic projection trong ngữ cảnh lời gọi.

### 12.2. Không phải thay đổi domain metadata

Dynamic projection thay cách nhìn kết quả đọc, không làm repository chuyển sang quản lý một aggregate khác.

Không vì method trả ProductSummary mà:

- Tạo collection riêng cho ProductSummary.
- Thay kiểu ID của ProductRepository.
- Biến ProductSummary thành đối tượng để lưu qua save của repository.
- Bỏ qua mapping của Product khi tạo query.

Các giới hạn projection vẫn theo store và dạng truy vấn thực tế.

## 13. Metadata tham gia luồng proxy như thế nào?

Có thể hình dung luồng khái niệm:

```text
Repository interface
        |
        v
Giải quyết domain type, ID type, interface hierarchy
        |
        v
Ghép base implementation và fragment
        |
        v
Diễn giải query method, parameters, returned type
        |
        v
Kết hợp mapping metadata của store
        |
        v
Repository proxy nhận một lời gọi
        |
        v
Phân loại đối số: bind / phân trang / sort / projection
        |
        v
Store thực hiện truy cập dữ liệu
        |
        v
Mapping, projection và bao kết quả theo hợp đồng
```

Thời điểm xây từng phần có thể phụ thuộc cách khởi tạo và cấu hình. Không nên hiểu sơ đồ là toàn bộ metadata đều được dựng lại từ đầu trong mỗi lần gọi.

### 13.1. Metadata định hướng, store thực thi

Với Page<ProductSummary>, hạ tầng cần phối hợp:

- Domain Product để biết nguồn truy vấn.
- Mapping thuộc tính để tạo truy vấn đúng.
- Pageable để giới hạn và sắp xếp.
- Projection để biểu đạt dữ liệu người gọi cần.
- Chiến lược page để cung cấp metadata tổng theo hợp đồng.

Commons không tự chuyển mọi yêu cầu thành SQL hoặc MongoDB command. Store module và hạ tầng bên dưới thực hiện phần chuyển đổi cụ thể.

### 13.2. Không gán mọi trách nhiệm cho ResultProcessor

ResultProcessor hỗ trợ việc nhìn và xử lý kết quả theo ReturnedType, bao gồm projection trong các trường hợp được hỗ trợ.

Nó không tự mở kết nối, chạy count, tạo index hoặc bảo đảm transaction. Việc trả một Page hoàn chỉnh còn cần cơ chế thực thi truy vấn và thông tin phân trang tương ứng.

Tương tự, ProjectionFactory hỗ trợ tạo hình dạng projection. Nó không thay mapping domain và không tự xác nhận hiệu năng truy vấn.

## 14. Những điều metadata không tự chứng minh

| Đọc được thông tin | Không tự chứng minh |
| --- | --- |
| Domain type là Product | Có collection hoặc bảng chứa dữ liệu Product |
| ID type là String | Mọi ID String đều tồn tại hoặc có định dạng nghiệp vụ hợp lệ |
| Collection được mapping là products | Collection đã được tạo, có index hoặc có đủ quyền truy cập |
| name được mapping thành product_name | Tất cả document cũ đều có đúng trường đó |
| Method trả Optional<Product> | SKU có ràng buộc duy nhất |
| Method trả Page | Mỗi lần gọi luôn có đúng hai truy vấn |
| Method trả projection ba getter | Store chỉ đọc đúng ba trường vật lý trong mọi trường hợp |
| Thuộc tính được đánh dấu auditing | Cơ chế auditing đã được bật và chạy trên mọi đường ghi |
| isNew trả false | Đã truy vấn và xác nhận bản ghi tồn tại |
| Generic giải quyết thành công | Toàn bộ mapping và kiểu trả về được store hỗ trợ |

Metadata Java và cấu hình mapping là một nguồn thông tin. Trạng thái vật lý của kho, dữ liệu cũ, ràng buộc, quyền truy cập và hiệu năng là các nguồn thông tin khác.

Nếu cần đối chiếu schema hoặc document thực tế, phải dùng công cụ hoặc API phù hợp. Đọc PersistentEntity không phải một phép kiểm tra toàn bộ database.

## 15. Những lỗi thường gặp khi tự khai thác metadata

### 15.1. Lấy class runtime của proxy làm domain

```java
Class<?> runtimeType = repository.getClass();
```

Class này có thể là class proxy được tạo lúc chạy. Nó không phải Product và cũng không nhất thiết có tên cố định giữa các lần chạy.

Không suy domain bằng tên class proxy hoặc bằng vị trí đầu tiên trong danh sách interface mà proxy thực hiện.

Ưu tiên interface repository cụ thể và các abstraction metadata mà hạ tầng cung cấp.

### 15.2. Chỉ đọc raw return type

Với Page<ProductSummary>, getReturnType cho Page. Nếu công cụ dừng ở đây, nó bỏ mất kiểu nội dung và thông tin projection.

Nếu tự dùng reflection generic, còn phải xử lý type variable, interface kế thừa và wrapper. Các abstraction Commons giúp tổng hợp một phần công việc đó theo hợp đồng repository.

### 15.3. Dùng tên trường lưu trữ để viết derived query

Trong domain mẫu:

```text
Tên thuộc tính Java: name
Tên trường MongoDB: product_name
```

Derived query và Sort thường diễn đạt theo đường dẫn thuộc tính Java. Store dùng mapping để chuyển sang tên trường lưu trữ.

Không tự đặt method theo tên product_name rồi mong parser coi đó là tên thuộc tính name. Dấu gạch dưới trong phương thức truy vấn còn có ý nghĩa xử lý đường dẫn, không chỉ là một ký tự sao chép từ storage field.

### 15.4. Tự cho rằng metadata repository sẽ sửa sai kiểu ID

Nếu một repository khai báo ID Long trong khi domain được mapping với ID String, metadata repository có thể phản ánh đúng điều bạn đã khai báo là Long.

Điều đó không làm mapping domain đổi theo. Phải đối chiếu hai nguồn thông tin và sửa hợp đồng cho nhất quán.

Không trông chờ generic metadata tự biến một khai báo sai thành kiểu ID mà bạn có ý định sử dụng.

### 15.5. Đánh đồng property type với biểu diễn vật lý

PersistentProperty có thể cho biết một thuộc tính Java có kiểu Long. Cách chuyển đổi và biểu diễn trong kho còn có thể chịu ảnh hưởng bởi converter hoặc cấu hình của store.

Một công cụ chỉ đọc getType không nên tự nhận là đã biết đầy đủ định dạng storage và mọi quy tắc chuyển đổi.

### 15.6. Cache metadata không xét phạm vi cấu hình

Hạ tầng thường có thể tái sử dụng metadata thay vì phân tích lại mỗi bản ghi.

Nhưng metadata chỉ dựa vào kiểu repository có phạm vi khác metadata mapping phụ thuộc context, naming strategy hoặc custom conversion.

Nếu xây cache trong một thư viện mở rộng, xác định khóa và vòng đời theo đúng loại metadata. Không đưa giá trị dữ liệu của entity vào một đối tượng metadata dùng chung rồi chia sẻ giữa các request.

## 16. Chẩn đoán lỗi bằng cách chọn đúng tầng

| Triệu chứng | Metadata hoặc cấu hình nên kiểm tra |
| --- | --- |
| Không giải quyết được domain type | Interface generic, repository cụ thể và RepositoryMetadata |
| Domain hoặc ID không nhất quán | Hợp đồng repository so với entity mapping |
| Không tìm thấy thuộc tính trong derived query | Tên Java và đường dẫn thuộc tính |
| Query nhận sai số tham số | Phân loại bindable/special parameter |
| Projection thiếu hoặc sai thuộc tính | Getter, ReturnedType, mapping và mức hỗ trợ store |
| Method không đi vào fragment mong muốn | Cấu trúc ghép implementation và phân loại method |
| Page có kết quả nhưng tổng không đúng | Query/count, điều kiện và cơ chế phân trang theo store |
| Auditing không có giá trị | Metadata role và cấu hình callback/listener thực tế |
| Đọc metadata được nhưng truy vấn thất bại | Kết nối, mapping đầy đủ, hỗ trợ store và trạng thái kho |

Một lỗi có thể cần đối chiếu nhiều tầng. Ví dụ, projection có getter name hợp lệ nhưng query tùy chỉnh không cung cấp giá trị tương ứng có thể làm kết quả khác mong đợi.

Không chỉ thay một annotation ở entity nếu nguyên nhân nằm ở chữ ký kết quả hoặc implementation query.

## 17. Bài thực hành đối chiếu ba nhóm metadata

### Bước 1: kiểm tra hợp đồng repository

Tạo RepositoryMetadata cho ProductRepository và ghi nhận:

```text
Repository interface = ProductRepository
Domain type          = Product
ID type              = String
```

Lặp lại với ProductLookupRepository để thấy generic vẫn được giải quyết qua interface trung gian.

Các bước này đọc cấu trúc Java, không yêu cầu Product đã có bản ghi trong MongoDB.

### Bước 2: kiểm tra mapping entity

Dùng MongoMappingContext của ví dụ và đối chiếu:

- Product được mapping tới products.
- id là thuộc tính ID có kiểu String.
- Trường lưu trữ của ID là _id.
- name được mapping thành product_name.

Giải thích vì sao những thông tin này không chứng minh collection đang có index hoặc document.

### Bước 3: kiểm tra metadata kết quả

Đọc method findByActiveTrue có tham số Pageable:

- Raw return type là Page.
- Kiểu nội dung là ProductSummary.
- Domain của repository vẫn là Product.
- Có một tham số Pageable.
- Không có tham số giá trị điều kiện để bind từ caller ở chữ ký này.

Phân biệt điều kiện active true được biểu đạt trong tên method với cách provider có thể thể hiện hằng boolean trong truy vấn vật lý.

### Bước 4: phân loại tham số

Với findByCategory(String, Pageable):

```text
category → giá trị điều kiện
pageable → thông tin điều khiển phân trang
```

Với findByCategory(String, Class<R>):

```text
category   → giá trị điều kiện
resultType → lựa chọn dynamic projection khi khớp hợp đồng
```

Giải thích vì sao không thể bind toàn bộ đối số Java theo cùng một quy tắc.

### Bước 5: chỉ sau đó mới thử thực thi qua store

Khi đã có MongoDB và repository được cấu hình:

1. Nạp vài Product với SKU, nhóm và trạng thái đã biết.
2. Gọi truy vấn trả entity và truy vấn trả ProductSummary.
3. Đối chiếu các trường giá trị.
4. Quan sát command khi cần để xác nhận cách lấy dữ liệu.
5. Giữ riêng kết luận từ metadata và kết luận từ lần truy vấn thực tế.

Một phép đọc metadata thành công không phải kết quả kiểm tra kết nối. Một truy vấn trả dữ liệu đúng cũng chưa tự chứng minh mọi tổ hợp projection hoặc phân trang được hỗ trợ.

## 18. Các câu hỏi cần tự trả lời được

**Vì sao repository quản lý Product nhưng method có thể trả ProductSummary?**

Vì domain type mô tả đối tượng gốc mà repository quản lý, còn returned type mô tả hình dạng kết quả của một method cụ thể.

**Vì sao getReturnType trả Page vẫn chưa đủ?**

Vì nó chỉ là kiểu thô của wrapper, chưa cho toàn bộ thông tin về phần tử, projection và generic trong ngữ cảnh repository.

**PersistentEntity có chứa toàn bộ bản ghi Product không?**

Không. Nó mô tả cấu trúc mapping; giá trị của từng instance là dữ liệu khác.

**EntityInformation.isNew có phải một truy vấn tồn tại không?**

Không mặc định. Nó đánh giá trạng thái theo chiến lược, có thể dựa vào ID, version hoặc Persistable.

**Pageable có được tính như một giá trị lọc thông thường không?**

Không. Nó là tham số điều khiển đặc biệt trong các chữ ký được hỗ trợ.

**Có thể dùng MongoMappingContext để mô tả toàn bộ mapping JPA không?**

Không. JPA có hệ thống metamodel và tích hợp riêng; cần dùng abstraction phù hợp với store.

## 19. Điều cần giữ khi đọc hạ tầng repository

Luôn tách ba câu hỏi: repository quản lý kiểu nào, entity được mapping ra sao và từng method cần trả hình dạng kết quả gì.

RepositoryMetadata, metadata entity và QueryMethod bổ sung cho nhau. Chúng giúp proxy hiểu hợp đồng và chọn đường xử lý, còn store module cùng hạ tầng bên dưới thực hiện truy vấn, chuyển đổi và truy cập dữ liệu.

Sự phân biệt này giúp bạn mở rộng repository, xử lý projection, phân trang, QBE và auditing mà không nhầm cấu trúc Java với trạng thái thực tế của kho dữ liệu.

