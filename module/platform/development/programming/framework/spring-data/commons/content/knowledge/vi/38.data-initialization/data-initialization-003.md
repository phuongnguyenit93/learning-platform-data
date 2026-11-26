# Kiểu miền trong dữ liệu mẫu và lựa chọn repository tương ứng

## Mục tiêu và phạm vi

Một file dữ liệu mẫu có thể chứa nhiều loại đối tượng: nhóm sản phẩm, sản phẩm, khách hàng hoặc đơn hàng. Khi nạp dữ liệu ở tầng repository, Spring Data cần biết mỗi object thuộc kiểu miền nào để chọn repository phù hợp.

Bài học thuộc chương **Khởi tạo dữ liệu** của module **SPRING_DATA_COMMONS**. Trọng tâm là mối liên hệ giữa metadata kiểu trong fixture, object Java sau deserialization và metadata của repository đã được đăng ký.

Sau bài học, bạn có thể:

1. Giải thích vai trò của `_class` trong JSON repository populator.
2. Chọn đúng domain type và ID type của repository.
3. Phân biệt lỗi đọc kiểu, lỗi tìm repository và lỗi lưu dữ liệu.
4. Xử lý fixture chứa nhiều aggregate mà không suy diễn cascade hoặc liên kết tự động.
5. Nhận diện các giới hạn về nhiều store, reactive, chạy lại và transaction.

Ví dụ chính dùng Java 17 trở lên, Spring Data Commons 4.x với Jackson 3 và một ứng dụng MongoDB imperative đã được cấu hình. MongoDB chỉ là store minh họa. Cơ chế định tuyến theo kiểu thuộc Commons; model, mapping và hành vi lưu thực tế vẫn phải phù hợp module store.

Các đoạn JSON và Java trong bài là tài liệu thực hành. Chúng mô tả các resource/đơn vị mã nguồn của ví dụ, không yêu cầu mọi ứng dụng phải dùng đúng những package hoặc tên collection đó.

## 1. Luồng từ dữ liệu mẫu đến repository

Luồng khái niệm:

~~~mermaid
flowchart LR
    A["Resource JSON hoặc XML"] --> B["ResourceReader"]
    B --> C["Object có kiểu Java cụ thể"]
    C --> D["Tra metadata repository theo kiểu miền"]
    D --> E["RepositoryInvoker"]
    E --> F["save của repository đã chọn"]
    F --> G["Mapping và thao tác lưu theo store"]
~~~

Với JSON reader của ví dụ, một bản ghi:

~~~json
{
  "_class": "com.example.seed.Product",
  "id": "prd-coffee",
  "sku": "COFFEE-01",
  "name": "Coffee",
  "categoryId": "cat-drinks"
}
~~~

được dùng để tạo object `com.example.seed.Product`. Sau đó hạ tầng tìm repository quản lý kiểu object đó.

Nó không chọn repository bằng:

- Tiền tố của ID.
- Tên file JSON.
- Tên collection viết trong fixture.
- Tên field `sku` hay `categoryId`.
- Một bean name được đoán từ chuỗi `_class`.

Nếu object Java là Product, repository cần quản lý Product hoặc được metadata hạ tầng xác định là phù hợp với kiểu đó.

Tổng quan cơ chế được trình bày trong [Spring Data Commons — Repository Populators](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.repository-populators).

## 2. Ba khái niệm kiểu cần tách biệt

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Kiểu miền | `Product` | Kiểu object mà repository quản lý |
| Kiểu ID | `String` | Kiểu định danh mà repository sử dụng |
| Kiểu repository | `ProductRepository` | Interface cung cấp các thao tác cho domain type |

Ví dụ:

~~~java
public interface ProductRepository
    extends CrudRepository<Product, String> {
}
~~~

Trong chữ ký này:

- Product là domain type.
- String là ID type.
- ProductRepository là interface repository.

`_class` trong fixture cần giúp reader tạo **Product**, không phải tạo ProductRepository.

Hai repository có thể cùng dùng ID kiểu String nhưng quản lý hai domain khác nhau. Việc cả hai record đều có `"id": "sample-001"` không làm chúng được định tuyến đến cùng repository.

Các generic này là thành phần cơ bản của [Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

### Domain type không nhất thiết trùng kiểu response API

Nếu endpoint public trả `ProductSummaryResponse`, điều đó không có nghĩa fixture của repository nên dùng:

~~~json
{
  "_class": "com.example.api.ProductSummaryResponse",
  "id": "prd-coffee",
  "name": "Coffee"
}
~~~

Reader có thể tạo DTO đó nếu class tồn tại và dữ liệu hợp lệ. Nhưng nếu không có repository quản lý DTO này, bước chọn repository không thể hoạt động như mong muốn.

Muốn dùng schema fixture độc lập với domain, cần một loader ánh xạ fixture DTO sang aggregate trước khi gọi repository. Repository populator không tự suy ra phép ánh xạ từ việc các field trùng tên.

## 3. _class chọn class để tạo object

Trong Jackson resource reader của ví dụ, khóa kiểu mặc định là `_class`. Giá trị thường là tên class đầy đủ:

~~~json
{
  "_class": "com.example.seed.Category",
  "id": "cat-drinks",
  "name": "Drinks"
}
~~~

Reader đọc metadata kiểu, resolve class bằng class loader và deserialize object về class đó.

Các thông tin khác nhau:

| Giá trị | Có phù hợp mặc định với ví dụ không? |
|---|---|
| `com.example.seed.Category` | Có, nếu class tồn tại và deserialize được |
| `Category` | Không tự có cơ chế thêm package của ứng dụng |
| `categoryRepository` | Là tên bean minh họa, không phải tên domain class |
| `categories` | Có thể là tên collection, không tự là domain class |
| `category` | Không tự trở thành alias domain |

Khi đổi package hoặc đổi tên class, fixture dùng tên class đầy đủ cũng phải được cập nhật tương ứng.

Hành vi lookup có thể đối chiếu trong [JacksonResourceReader](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/init/JacksonResourceReader.html) và [mã nguồn reader](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/repository/init/JacksonResourceReader.java).

### Đổi tên type key khác với tạo alias

Reader có thể được cấu hình dùng khóa khác:

~~~java
JacksonResourceReader reader = new JacksonResourceReader();
reader.setTypeKey("entityType");
~~~

Khi đó fixture có thể đặt tên class dưới `entityType`. Thao tác này đổi **tên khóa**, không tạo một bảng ánh xạ từ `"product"` sang Product.class.

Nếu muốn schema dạng:

~~~json
{
  "kind": "product",
  "id": "prd-coffee",
  "name": "Coffee"
}
~~~

cần một reader hoặc loader có quy tắc ánh xạ kind được định nghĩa rõ. Không chỉ đổi type key thành `kind` rồi kỳ vọng reader mặc định hiểu mọi tên rút gọn.

Fixture chứa thông tin class nên là tài nguyên do ứng dụng kiểm soát. Không tái sử dụng trực tiếp cơ chế resolve class này để nhận tên class tùy ý từ request HTTP.

## 4. Ví dụ hai aggregate và hai repository

Để minh họa cụ thể, ta dùng hai record có mapping MongoDB.

### 4.1. Category

~~~java
package com.example.seed;

import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("sample_categories")
public record Category(
    @Id String id,
    String name
) {
    public Category {
        Objects.requireNonNull(id, "category id is required");
        Objects.requireNonNull(name, "category name is required");
    }
}
~~~

### 4.2. Product

~~~java
package com.example.seed;

import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("sample_products")
public record Product(
    @Id String id,
    String sku,
    String name,
    String categoryId
) {
    public Product {
        Objects.requireNonNull(id, "product id is required");
        Objects.requireNonNull(sku, "sku is required");
        Objects.requireNonNull(name, "product name is required");
        Objects.requireNonNull(categoryId, "category id is required");
    }
}
~~~

Các constructor chỉ kiểm tra một số giá trị bắt buộc trong ví dụ. Chúng chưa kiểm tra tính duy nhất của SKU hoặc sự tồn tại của Category.

Model dùng ID được gán trước và một field `categoryId` đơn giản. Nó không khai báo một quan hệ ORM hoặc một cơ chế tự đọc Category.

### 4.3. Repository

~~~java
package com.example.seed;

import org.springframework.data.repository.CrudRepository;

public interface CategoryRepository
    extends CrudRepository<Category, String> {
}
~~~

~~~java
package com.example.seed;

import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
    extends CrudRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
~~~

Ứng dụng cần có module MongoDB và cấu hình đăng ký các repository này. Annotation domain cùng cấu hình module giúp xác định store; chỉ có interface Commons không tự tạo kết nối database.

Nếu thay sang JPA, JDBC hoặc store khác, phải thiết kế model/mapping và cấu hình phù hợp. Không thêm annotation của một store rồi coi record này tự trở thành entity hợp lệ cho mọi store khác.

## 5. Một fixture có thể chứa nhiều kiểu miền

Giả sử resource `seed/catalog.json` có nội dung:

~~~json
[
  {
    "_class": "com.example.seed.Category",
    "id": "cat-drinks",
    "name": "Drinks"
  },
  {
    "_class": "com.example.seed.Product",
    "id": "prd-coffee",
    "sku": "COFFEE-01",
    "name": "Coffee",
    "categoryId": "cat-drinks"
  }
]
~~~

Mỗi phần tử top-level khai báo kiểu riêng. Hạ tầng có thể tạo một danh sách object Java không đồng nhất:

~~~text
Category
Product
~~~

Khi populate, từng object được đưa đến repository phù hợp.

| Phần tử | Class sau đọc JSON | Repository mong đợi |
|---|---|---|
| Category mẫu | `Category.class` | CategoryRepository |
| Product mẫu | `Product.class` | ProductRepository |

Không cần mỗi file chỉ chứa một domain type. Tách file theo aggregate vẫn có thể hữu ích cho việc tổ chức, thứ tự và chẩn đoán, nhưng tên file không thay thế metadata kiểu.

### Giữ metadata ở root rõ ràng

Đặt type key của mỗi root object ở vị trí dễ thấy và đúng schema của resource reader. Không dựa vào metadata nằm đâu đó trong object lồng để đoán kiểu root.

Field `categoryId` chỉ chứa ID. Nó không làm populator tự tìm Category rồi thay field thành một object Category.

Nếu bản ghi dùng một schema khác như `"category": {"id": "..."}`, đó là một mô hình khác cần constructor, mapping và quy tắc quan hệ phù hợp.

## 6. Cấu hình populator đúng phiên bản Jackson

Với Spring Data Commons 4.x và Jackson 3, có thể dùng:

~~~java
package com.example.seed;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init.JacksonRepositoryPopulatorFactoryBean;

@Configuration
@Profile("demo-data")
public class SampleDataConfiguration {

    @Bean
    JacksonRepositoryPopulatorFactoryBean sampleDataPopulator() {
        JacksonRepositoryPopulatorFactoryBean factory =
            new JacksonRepositoryPopulatorFactoryBean();

        factory.setResources(new Resource[] {
            new ClassPathResource("seed/catalog.json")
        });

        return factory;
    }
}
~~~

Snippet này chỉ cấu hình việc đọc resource và populate repository. Nó giả định database, mapping và repository đã được ứng dụng cấu hình, và profile `demo-data` được bật khi muốn nạp dữ liệu mẫu.

Factory bean tích hợp vào vòng đời application context. Không cần tự gọi populate ngay trong phương thức `@Bean` trước khi context hoàn tất đăng ký các thành phần cần thiết.

API được mô tả trong [JacksonRepositoryPopulatorFactoryBean](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/init/JacksonRepositoryPopulatorFactoryBean.html).

### Không trộn Jackson 2 và Jackson 3

| Hạ tầng | Reader/factory minh họa | ObjectMapper tương ứng |
|---|---|---|
| Nhánh Jackson 3 của Commons 4.x | `JacksonResourceReader` / `JacksonRepositoryPopulatorFactoryBean` | `tools.jackson.databind.ObjectMapper` |
| Nhánh Jackson 2 trong các phiên bản hỗ trợ | `Jackson2ResourceReader` / `Jackson2RepositoryPopulatorFactoryBean` | `com.fasterxml.jackson.databind.ObjectMapper` |

Các class mới không có số 3 trong tên. Không tự tạo tên `Jackson3RepositoryPopulatorFactoryBean` từ suy đoán.

Jackson2 factory đã được đánh dấu deprecated từ Commons 4.0 để chuyển sang factory mới. Điều đó không có nghĩa thay tên class là đủ nếu các dependency hoặc mapper vẫn thuộc nhánh Jackson khác.

Xem thông tin phiên bản trong [Jackson2RepositoryPopulatorFactoryBean](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/init/Jackson2RepositoryPopulatorFactoryBean.html).

Nếu cấu hình mapper riêng, cần xử lý đúng metadata kiểu và các field domain. Reader mặc định được đối chiếu có chính sách bỏ qua unknown properties; vì vậy, JSON đọc được chưa chứng minh mọi tên field trong fixture đều đúng với ý định nghiệp vụ.


## 7. Repository được chọn từ metadata đã đăng ký

`Repositories` là abstraction truy cập các repository cùng metadata trong bean factory. Có thể hỏi:

~~~java
Repositories repositories = new Repositories(applicationContext);

boolean exists = repositories.hasRepositoryFor(Product.class);

Optional<Object> selected =
    repositories.getRepositoryFor(Product.class);
~~~

Các biến trong đoạn này giả định có một application context đã được cấu hình và khởi tạo phù hợp.

Một bean tên `productRepository` không đủ để chứng minh nó là repository quản lý Product. Hạ tầng cần metadata domain/repository do quá trình tạo repository cung cấp.

Cũng không chọn repository bằng class proxy runtime của bean. Class proxy có thể mang tên kỹ thuật khác interface; metadata domain và repository interface mới là thông tin cần đối chiếu.

Xem API [Repositories](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/support/Repositories.html).

### Kiểm tra repository, domain và ID type cùng nhau

Một công cụ kiểm tra cho ví dụ:

~~~java
package com.example.seed;

import org.springframework.data.repository.core.RepositoryInformation;
import org.springframework.data.repository.support.Repositories;

public final class SeedRepositoryInspection {

    private SeedRepositoryInspection() {
    }

    public static void requireTarget(
        Repositories repositories,
        Class<?> expectedDomain,
        Class<?> expectedRepository,
        Class<?> expectedIdType
    ) {
        RepositoryInformation information = repositories
            .getRepositoryInformationFor(expectedDomain)
            .orElseThrow(() -> new IllegalStateException(
                "No repository metadata for "
                    + expectedDomain.getName()
            ));

        if (!information.getDomainType().equals(expectedDomain)) {
            throw new IllegalStateException(
                "Unexpected repository domain type"
            );
        }

        if (!information.getRepositoryInterface()
                .equals(expectedRepository)) {
            throw new IllegalStateException(
                "Unexpected repository interface for "
                    + expectedDomain.getName()
            );
        }

        if (!information.getIdType().equals(expectedIdType)) {
            throw new IllegalStateException(
                "Unexpected repository ID type"
            );
        }

        if (information.isReactiveRepository()) {
            throw new IllegalStateException(
                "This initializer expects an imperative repository"
            );
        }

        if (!information.getCrudMethods().hasSaveMethod()) {
            throw new IllegalStateException(
                "The repository does not expose save"
            );
        }

        Object selected = repositories
            .getRepositoryFor(expectedDomain)
            .orElseThrow(() -> new IllegalStateException(
                "Repository instance not available"
            ));

        if (!expectedRepository.isInstance(selected)) {
            throw new IllegalStateException(
                "The selected bean does not match the expected interface"
            );
        }
    }
}
~~~

Có thể gọi trong một test hoặc custom initializer:

~~~java
SeedRepositoryInspection.requireTarget(
    repositories,
    Category.class,
    CategoryRepository.class,
    String.class
);

SeedRepositoryInspection.requireTarget(
    repositories,
    Product.class,
    ProductRepository.class,
    String.class
);
~~~

Helper cố ý yêu cầu domain type và repository interface khớp chính xác với thiết kế của ví dụ. Nếu ứng dụng hỗ trợ các kiểu thay thế hoặc kế thừa, phải định nghĩa chính sách tương ứng.

Đây là công cụ kiểm tra do ứng dụng tự viết. Factory populator mặc định không tự gọi helper này. Muốn kiểm tra tất cả target trước khi lưu, phải chủ động đưa bước đó vào loader phù hợp hoặc kiểm thử cấu hình trước khi dùng.

Các thông tin được dùng ở đây thuộc [RepositoryMetadata](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMetadata.html) và [CrudMethods](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/CrudMethods.html).

## 8. Có repository chưa đủ; cần phương thức lưu phù hợp

Một repository chỉ cung cấp đọc có thể hợp lệ cho ứng dụng:

~~~java
public interface ProductReadRepository
    extends Repository<Product, String> {

    Optional<Product> findById(String id);
}
~~~

Nhưng nó chưa cung cấp phương thức save mà initializer cần.

Tương tự, `PagingAndSortingRepository` trong các thế hệ Spring Data hiện đại không tự kế thừa toàn bộ CRUD. Một interface có thể đọc và phân trang nhưng không có khả năng lưu tương ứng.

Không nhất thiết phải expose mọi phương thức của CrudRepository. Có thể định nghĩa các phương thức tương thích theo nhu cầu, nhưng phương thức lưu phải được hạ tầng nhận diện đúng.

Một phương thức tùy biến tên `importProduct` không tự trở thành phương thức mà populator sẽ gọi chỉ vì nó nhận Product.

`RepositoryInvoker` là lớp trừu tượng hóa việc gọi các thao tác CRUD. Nếu không có save, việc gọi `invokeSave` không được xem là thành công. Xem [RepositoryInvoker](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/support/RepositoryInvoker.html).

### Generic base repository cần được cụ thể hóa

Ví dụ base interface:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface SeedBaseRepository<T, ID>
    extends CrudRepository<T, ID> {
}
~~~

Một repository cụ thể cần bind T và ID, chẳng hạn Product và String. Không kỳ vọng một base interface còn generic sẽ tự chọn được kiểu miền cho mọi object mẫu.

`@NoRepositoryBean` giúp hạ tầng không cố tạo instance trực tiếp cho base repository đó. Metadata của repository concrete mới là thứ được dùng khi định tuyến fixture.

## 9. Có hai lần “chọn” khác nhau khi dùng nhiều module

Trong ứng dụng nhiều store, cần phân biệt:

1. Lúc đăng ký bean: interface repository thuộc module nào?
2. Lúc populate: object miền được đưa tới repository đã đăng ký nào?

`_class` giải quyết việc tạo kiểu object, không thay thế cấu hình chọn module.

Ví dụ một hệ thống có:

~~~text
ProductDocument -> Mongo repository
ProductEntity   -> JPA repository
~~~

Hai domain class khác nhau giúp thể hiện hai mô hình lưu trữ rõ ràng. Fixture chỉ tới từng class và mỗi class phải có repository phù hợp trong context.

Khi nhiều repository factory xuất hiện, Spring Data có chế độ cấu hình chặt hơn để xác định binding dựa trên interface module, annotation domain và phạm vi scan. Xem [Using Repositories with Multiple Spring Data Modules](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html#repositories.multiple-modules).

### Cùng một domain type, nhiều repository

Giả sử có hai repository cùng quản lý `Product.class` nhưng mục đích hoặc store khác nhau. Fixture:

~~~json
{
  "_class": "com.example.seed.Product",
  "id": "prd-coffee",
  "sku": "COFFEE-01",
  "name": "Coffee",
  "categoryId": "cat-drinks"
}
~~~

không tự chỉ rõ nó muốn dùng repository thứ nhất hay thứ hai.

Không tự suy rằng:

- Cả hai repository sẽ cùng được gọi.
- Tên file quyết định repository đích.
- `@Qualifier` ở một service khác sẽ điều khiển populator.
- Thứ tự scan luôn là một hợp đồng ổn định để chọn target.

Cấu hình ưu tiên có thể ảnh hưởng cách registry chọn repository trong hạ tầng cụ thể. Nếu ứng dụng có nhiều ứng viên, cần kiểm tra kết quả lookup thực tế theo phiên bản/cấu hình thay vì dựa vào suy đoán.

Có thể đối chiếu cơ chế registry trong [mã nguồn Repositories](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/repository/support/Repositories.java).

Nếu yêu cầu seed vào hai store, hãy dùng initializer gọi hai đích tường minh, hoặc tách model/context/luồng khởi tạo phù hợp. Một object trong fixture không phải một lệnh fan-out lưu vào mọi repository có kiểu gần giống.

### Interface và annotation module phải nhất quán

Nếu model dùng annotation của nhiều store, hoặc phạm vi scan chồng lấn, việc bind repository có thể trở nên không rõ ràng.

Trong ví dụ MongoDB chính, Category và Product có `@Document` và các repository được đăng ký qua module MongoDB. Nếu chuyển một repository sang `JpaRepository`, model cũng phải là model JPA phù hợp; không chỉ thay interface để “ép” dữ liệu mẫu sang một database khác.

Cách tạo repository và phạm vi scan được mô tả trong [Creating Repository Instances](https://docs.spring.io/spring-data/commons/reference/repositories/create-instances.html).

## 10. Không nhầm _class của fixture với type hint của store

Spring Data MongoDB cũng có thể lưu field `_class` trong document để phục vụ type mapping. Có thể dùng `@TypeAlias` để thay cách biểu diễn type hint ở tầng mapping.

Tuy cùng tên field, đây là hai điểm xử lý khác nhau:

| Giai đoạn | Thành phần xử lý | Mục đích |
|---|---|---|
| Đọc fixture JSON | Repository ResourceReader | Tạo object Java từ dữ liệu mẫu |
| Đọc/ghi document MongoDB | MappingMongoConverter và type mapper | Chuyển giữa object và document trong store |

Do đó, một alias MongoDB như:

~~~java
@TypeAlias("product")
~~~

không tự làm JacksonResourceReader mặc định hiểu:

~~~json
{
  "_class": "product"
}
~~~

Reader của ví dụ resolve tên class theo class loader. Muốn dùng alias ở fixture, phải có cơ chế giải alias trong chính luồng đọc fixture.

Chính sách type hint của MongoDB được mô tả riêng trong [MongoDB Type Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/converters-type-mapping.html).

Tương tự, tên table, collection hoặc keyspace không phải một tên class. Đổi tên nơi lưu trữ có thể không yêu cầu đổi fixture nếu domain type và dữ liệu vẫn giữ hợp đồng tương ứng.

## 11. Aggregate lồng nhau không được tự tách sang repository khác

Ví dụ fixture Product có một object lồng:

~~~json
{
  "_class": "com.example.seed.Product",
  "id": "prd-coffee",
  "sku": "COFFEE-01",
  "name": "Coffee",
  "category": {
    "id": "cat-drinks",
    "name": "Drinks"
  }
}
~~~

JSON này không khớp model Product chính của bài vì model đó có `categoryId`, không có property `category`.

Ngay cả khi domain có property Category và reader tạo được graph, populator cũng không mặc nhiên coi từng object lồng là một root cần đưa tới repository riêng. Nó lưu root được reader trả về theo cơ chế populate.

Việc lưu graph có thể là:

- Embedded document trong một store.
- Quan hệ có cascade trong một mô hình khác.
- Tham chiếu cần lưu aggregate đích trước.
- Một graph không được store hỗ trợ theo cấu hình đang có.

Không lấy JSON lồng nhau làm bằng chứng có cascade hoặc có lookup theo ID.

### ID tham chiếu không tự tạo ràng buộc

Trong fixture chính:

~~~json
"categoryId": "cat-drinks"
~~~

chỉ gán một chuỗi cho Product. Nó chưa chứng minh Category tương ứng tồn tại.

Nếu nghiệp vụ yêu cầu mọi Product phải tham chiếu Category hợp lệ, cần kiểm tra điều kiện đó ở tầng phù hợp. Thứ tự Category đứng trước Product trong file không thay thế kiểm tra quan hệ.

Nếu dùng ID do store sinh, các object mẫu phía sau cũng không tự nhận ID vừa được sinh cho object phía trước. Loader cần một cơ chế liên kết tường minh nếu muốn thực hiện việc đó.

Có thể dùng ID mẫu ổn định khi model/store cho phép, hoặc dùng loader điều phối việc lưu và lấy instance trả về rồi thiết lập liên kết.

## 12. Kiểu đúng chưa chứng minh save có đúng ý nghĩa

Tìm được repository phù hợp chỉ giải quyết một giai đoạn.

Sau đó còn có:

- Constructor hoặc invariant của domain.
- Mapping field và ID.
- Cách phát hiện entity mới.
- Version/optimistic locking.
- Constraint của database.
- Callback và auditing.
- Transaction và lỗi hạ tầng.

Trong JPA, save có thể dẫn đến persist hoặc merge tùy trạng thái entity. ID gán sẵn và version ảnh hưởng cơ chế nhận diện entity mới. Xem [Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html).

Trong MongoDB, save/insert và mapping document có hợp đồng riêng. Không mặc định thay store thì mọi giá trị ID hay cách cập nhật vẫn có cùng ý nghĩa. Xem [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html).

### Chạy lại không tự trở thành idempotent

Một fixture dùng ID ổn định có thể giúp kết quả lặp lại dễ kiểm soát hơn ở một số model, nhưng chưa bảo đảm mọi lần chạy đều không có tác dụng phụ.

Cần xác định:

- Lần sau cập nhật lại, bỏ qua hay báo lỗi nếu đã có dữ liệu?
- Có được ghi đè dữ liệu đã được chỉnh sửa sau lần seed trước?
- Có cần giữ createdAt hoặc version hiện tại?
- Unique key ngoài ID có gây xung đột không?
- Callback có tạo tác vụ hoặc event mỗi lần save không?

Repository populator không tự là một công cụ migration có version và trạng thái hoàn thành cho từng bản ghi.

### Auditing chạy qua hạ tầng được cấu hình

Nếu domain có auditing, giá trị được lưu có thể chịu tác động của callback, DateTimeProvider và AuditorAware.

Ở thời điểm khởi tạo, có thể chưa có người dùng HTTP hiện tại. Nếu cần danh tính hệ thống hoặc thời gian xác định trong test, phải cấu hình chúng phù hợp thay vì giả định fixture tự quyết định mọi metadata.

Auditing cũng phải được bật theo module để hoạt động. Xem [Spring Data Commons Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).


## 13. Vòng đời và transaction phải được hiểu đúng

Factory populator của ví dụ tích hợp với sự kiện refresh của application context tương ứng. Nó tạo registry repository từ context rồi populate các resource đã cấu hình.

Điều đó không có nghĩa:

- Mỗi file luôn là một transaction duy nhất.
- Mọi store được rollback cùng nhau nếu một phần tử lỗi.
- Các runner hoặc initializer khác có thứ tự đúng chỉ vì được đặt tên tương tự.
- Một lần khởi động thành công biến fixture thành dữ liệu chỉ được nạp một lần mãi mãi.

Cơ chế lifecycle được thể hiện trong [AbstractRepositoryPopulatorFactoryBean](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/repository/init/AbstractRepositoryPopulatorFactoryBean.java).

### Gọi save từng object không phải tự động bulk insert

Trong luồng populator được đối chiếu, từng object được đưa qua RepositoryInvoker rồi gọi save.

Một JSON array lớn không tự làm tất cả phần tử trở thành một lệnh bulk tối ưu của database. Nếu cần khối lượng dữ liệu lớn, chiến lược batch, import hoặc công cụ theo store cần được đánh giá riêng.

Nếu một thao tác lưu ở phần tử sau thất bại, các phần tử đã được lưu trước có thể còn tồn tại nếu không có transaction bao quanh phù hợp. Các resource trước đó cũng có thể đã được xử lý.

Chỉ gắn `@Transactional` lên phương thức tạo factory bean không tự làm lần populate diễn ra sau đó nằm trong transaction của phương thức tạo bean.

Muốn có tính nguyên tử, phải xác định ranh giới thực thi thật, transaction manager và khả năng của store. Với nhiều store, không suy rằng có transaction phân tán chỉ vì tất cả repository cùng nằm trong một context.

Luồng save qua invoker được thể hiện trong [ResourceReaderRepositoryPopulator](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/repository/init/ResourceReaderRepositoryPopulator.java).

### Khi cần điều phối quan hệ hoặc quy tắc nghiệp vụ

Một custom initializer thường phù hợp hơn nếu phải:

- Đọc tất cả fixture rồi validate toàn bộ trước lần ghi đầu tiên.
- Resolve alias hoặc mã nghiệp vụ thay vì tên class.
- Gọi service tạo aggregate có invariant phức tạp.
- Lưu đối tượng A, lấy ID được sinh rồi tạo B.
- Chọn tường minh nhiều repository cho cùng một kiểu.
- Áp dụng chính sách skip/update/replace theo dữ liệu đã có.
- Kiểm soát transaction hoặc retry ở một ranh giới xác định.

Không bắt buộc viết custom loader cho mọi fixture. Với model đơn giản, repository rõ ràng và dữ liệu do dự án kiểm soát, populator có sẵn có thể đủ.

## 14. Reactive repository cần luồng khởi tạo tương ứng

Ví dụ chính dùng repository imperative. Không suy rằng thay:

~~~java
CrudRepository<Product, String>
~~~

bằng:

~~~java
ReactiveCrudRepository<Product, String>
~~~

sẽ giữ nguyên mọi hành vi của populator imperative.

Luồng ResourceReaderRepositoryPopulator được đối chiếu gọi `invokeSave` và không mô tả một pipeline điều phối publisher, subscription và completion cho các thao tác reactive.

Với reactive store, cần xác định cơ chế initializer được hỗ trợ hoặc tự điều phối việc lưu theo mô hình reactive. Tiêu chí hoàn tất phải là công việc lưu đã hoàn tất theo hợp đồng, không chỉ là đã tạo ra publisher.

Cũng không coi việc gọi `subscribe()` rồi kết thúc initializer ngay là bằng chứng seed đã xong. Lifecycle, lỗi và trạng thái sẵn sàng của ứng dụng phải gắn với quá trình thực thi thực tế.

Khả năng của từng loại repository được nêu trong [Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html). Cần kiểm tra thêm integration cụ thể của module store đang dùng.

## 15. Kiểm thử theo ba giai đoạn

Một kiểm thử đầy đủ cần tách ít nhất ba câu hỏi:

| Giai đoạn | Câu hỏi |
|---|---|
| Đọc fixture | Mỗi phần tử trở thành đúng class và giữ đúng giá trị chưa? |
| Chọn repository | Metadata trong context có trỏ tới đúng repository và save method chưa? |
| Lưu thực tế | Dữ liệu đã có ở đúng store với ID, liên kết và constraint đúng chưa? |

Một parser test thành công không chứng minh database đã được ghi. Một ứng dụng không báo lỗi deserialize cũng chưa chứng minh field bị gõ sai đã được phát hiện.

### 15.1. Kiểm thử reader từ dữ liệu trong bộ nhớ

Ví dụ dùng các record Category/Product ở trên và Jackson reader của Commons 4.x:

~~~java
package com.example.seed;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.data.repository.init.JacksonResourceReader;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SeedTypeResolutionTest {

    private final JacksonResourceReader reader =
        new JacksonResourceReader();

    private Object read(String json) throws Exception {
        return reader.readFrom(
            new ByteArrayResource(
                json.getBytes(StandardCharsets.UTF_8)
            ),
            getClass().getClassLoader()
        );
    }

    @Test
    void readsEachRootUsingItsOwnDomainType() throws Exception {
        String json = """
            [
              {
                "_class": "com.example.seed.Category",
                "id": "cat-drinks",
                "name": "Drinks"
              },
              {
                "_class": "com.example.seed.Product",
                "id": "prd-coffee",
                "sku": "COFFEE-01",
                "name": "Coffee",
                "categoryId": "cat-drinks"
              }
            ]
            """;

        Object decoded = read(json);
        List<?> objects = assertInstanceOf(
            List.class,
            decoded
        );

        assertEquals(2, objects.size());

        Category category = assertInstanceOf(
            Category.class,
            objects.get(0)
        );

        Product product = assertInstanceOf(
            Product.class,
            objects.get(1)
        );

        assertEquals("cat-drinks", category.id());
        assertEquals("prd-coffee", product.id());
        assertEquals("COFFEE-01", product.sku());
        assertEquals(category.id(), product.categoryId());
    }

    @Test
    void requiresTheTypeMetadata() {
        String json = """
            {
              "id": "cat-drinks",
              "name": "Drinks"
            }
            """;

        assertThrows(
            IllegalArgumentException.class,
            () -> read(json)
        );
    }

    @Test
    void doesNotTreatARepositoryBeanNameAsADomainClass() {
        String json = """
            {
              "_class": "categoryRepository",
              "id": "cat-drinks",
              "name": "Drinks"
            }
            """;

        assertThrows(
            IllegalArgumentException.class,
            () -> read(json)
        );
    }
}
~~~

Mẫu này dùng resource trong bộ nhớ và JUnit. Nó kiểm tra phần resolve type/deserialization, chưa tạo repository hoặc ghi dữ liệu.

Khi nâng cấp reader hoặc cấu hình mapper, cần giữ các test theo hợp đồng thực sự của phiên bản đang dùng. Không buộc một thông báo lỗi nội bộ dài của Jackson trở thành hợp đồng test nếu ứng dụng chỉ cần phân biệt đúng nhóm lỗi.

### 15.2. Kiểm tra metadata trong application context thật

Trong một integration test đã cấu hình module/store, tạo registry từ chính context đó rồi gọi helper:

~~~java
Repositories repositories = new Repositories(context);

SeedRepositoryInspection.requireTarget(
    repositories,
    Category.class,
    CategoryRepository.class,
    String.class
);

SeedRepositoryInspection.requireTarget(
    repositories,
    Product.class,
    ProductRepository.class,
    String.class
);
~~~

Đoạn này cần context có repository thật và metadata do hạ tầng Spring Data tạo ra. Chỉ đăng ký một mock có tên giống repository vào bean factory không nhất thiết tạo đủ metadata để Repositories khám phá.

Nếu mục đích của test là xác nhận module binding, phải dùng cấu hình module tương ứng thay vì chỉ mock kết quả lookup.

### 15.3. Readback qua repository

Sau khi initializer hoàn tất trên một store test phù hợp:

~~~java
Category category = categories
    .findById("cat-drinks")
    .orElseThrow();

Product product = products
    .findById("prd-coffee")
    .orElseThrow();

assertEquals("Drinks", category.name());
assertEquals("COFFEE-01", product.sku());
assertEquals(category.id(), product.categoryId());
~~~

Ở đoạn này, `categories` và `products` là repository được inject vào integration test. Cần cấu hình store test và kích hoạt initializer theo đúng lifecycle muốn kiểm tra.

Chỉ kiểm tra `count() > 0` có thể bỏ sót việc sai repository, sai kiểu hoặc sai liên kết. Nên đọc đúng ID và xác nhận những field quan trọng của fixture.

### 15.4. Kiểm tra lần chạy tiếp theo

Chạy lại fixture trên dữ liệu đã tồn tại rồi xác nhận chính sách đã chọn:

- Số bản ghi có thay đổi như dự kiến không?
- Giá trị đã sửa có được giữ hay bị cập nhật theo chủ đích?
- Có lỗi unique constraint hoặc optimistic locking không?
- Auditing/callback có tác động đã được chấp nhận không?
- Nếu một record lỗi giữa chừng, trạng thái còn lại có đúng ranh giới transaction đã thiết kế không?

Đây là mẫu kiểm thử và hướng thực hành; bài học không khẳng định đã chạy test trên một ứng dụng hoặc database cụ thể.

## 16. Phân loại lỗi để sửa đúng giai đoạn

| Hiện tượng | Giai đoạn cần kiểm tra | Nguyên nhân thường gặp |
|---|---|---|
| Không tìm được type key | Đọc resource | Thiếu `_class` hoặc reader dùng type key khác |
| Không resolve được class | Đọc kiểu | Sai package, đổi tên class, class không ở classpath |
| Class đúng nhưng không tạo được object | Deserialization | Constructor, giá trị bắt buộc hoặc kiểu field không phù hợp |
| Object là DTO ngoài domain | Chọn repository | Fixture trỏ tới kiểu không được repository quản lý |
| Không tìm được repository | Đăng ký/lookup | Sai scan, profile, context hoặc domain generic |
| Repository được chọn không như mong muốn | Registry | Nhiều repository cùng domain hoặc cấu hình module không rõ |
| Có repository nhưng không save được | Invocation | Repository chỉ đọc hoặc không expose save phù hợp |
| Save thất bại ở store | Mapping/persistence | ID, version, constraint, schema hoặc kết nối |
| Product có categoryId nhưng Category không có | Dữ liệu/liên kết | Không có cơ chế kiểm tra hoặc seed liên quan chưa hoàn tất |
| Lần sau xuất hiện thêm dữ liệu | Chính sách chạy lại | ID sinh mới hoặc seed không idempotent |
| Type alias đọc được từ DB nhưng không đọc được fixture | Sai tầng metadata | Alias của store không tự là alias của ResourceReader |
| Tạo publisher nhưng chưa có dữ liệu | Mô hình thực thi | Chưa điều phối completion của thao tác reactive |
| Một số record đã có dù lần seed báo lỗi | Transaction | Không có ranh giới nguyên tử bao quanh toàn bộ công việc |

Sửa lỗi ở đúng giai đoạn giúp tránh những thay đổi không liên quan. Chẳng hạn, đổi tên bean repository không sửa được lỗi class loader; thêm field `collection` vào JSON cũng không sửa được việc DTO không có repository quản lý.

## 17. Khi nào nên dùng lựa chọn nào?

| Tình huống | Cách tiếp cận có thể phù hợp |
|---|---|
| Fixture nhỏ, domain rõ, mỗi domain có đích lưu rõ | Repository populator có sẵn |
| Muốn đọc XML thay JSON | ResourceReader/unmarshaller phù hợp cùng cơ chế repository |
| Muốn alias ổn định tách khỏi tên Java | Reader hoặc loader có bảng ánh xạ được kiểm soát |
| Cần gọi service để tạo aggregate đúng nghiệp vụ | Custom initializer điều phối service |
| Cần kết quả save để nối ID được sinh | Loader giữ instance/ID trả về và tạo quan hệ tường minh |
| Cùng domain phải lưu vào hai store | Gọi từng đích rõ ràng, không dựa vào lookup mơ hồ |
| Reactive store | Luồng seed có quản lý publisher, lỗi và completion |
| Dữ liệu lớn hoặc migration có version | Cơ chế batch/import/migration phù hợp yêu cầu thực tế |

Store-independent ở tầng Commons có nghĩa cơ chế dùng abstraction repository thay vì cố định một ngôn ngữ SQL. Nó không có nghĩa mọi store có cùng schema, transaction, cascade, ID generation hoặc lifecycle callback.

## 18. Bài thực hành

1. Định nghĩa hai aggregate có repository và ID type rõ ràng.
2. Viết fixture có metadata kiểu cho từng root object.
3. Dùng reader đúng phiên bản Jackson để kiểm tra class và giá trị sau deserialization.
4. Đối chiếu repository interface, domain type, ID type và save method trong context.
5. Nạp fixture vào một store test được hỗ trợ rồi đọc lại theo ID.
6. Thử đổi type metadata thành tên bean repository và phân loại lỗi nhận được.
7. Thử một class load được nhưng không có repository quản lý.
8. Thử một repository chỉ đọc để quan sát khác biệt với lỗi deserialize.
9. Thiết kế rõ việc liên kết hai aggregate thay vì dựa vào JSON lồng nhau.
10. Chạy lại fixture và xác minh chính sách update/skip/error.
11. Nếu có nhiều module, kiểm tra cả module binding lẫn runtime repository lookup.
12. Khi cần alias, quan hệ phức tạp hoặc reactive, chọn loader đủ khả năng điều phối.

Điều cần giải thích được là: **metadata kiểu tạo object miền; metadata repository xác định đích lưu; save đi qua implementation của store; đọc được fixture chưa đồng nghĩa chọn đúng repository hoặc đã khởi tạo dữ liệu thành công.**
