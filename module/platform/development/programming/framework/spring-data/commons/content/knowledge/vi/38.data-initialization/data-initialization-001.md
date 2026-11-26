# Repository populator và mục đích nạp dữ liệu mẫu

## 1. Vì sao ứng dụng cần dữ liệu mẫu?

Trong chương **Khởi tạo dữ liệu** của module **SPRING_DATA_COMMONS**, repository populator là một cơ chế nạp các object vào repository từ tài nguyên đã chuẩn bị, thường là JSON hoặc XML.

Một ứng dụng vừa có schema và repository chưa chắc đã có dữ liệu để quan sát hành vi. Một tập mẫu nhỏ giúp:

- Mở màn hình danh sách mà không phải nhập thủ công mọi bản ghi.
- Minh họa CRUD và các derived query.
- Thử bộ lọc, phân trang, sắp xếp hoặc projection trên dữ liệu biết trước.
- Tạo một trạng thái ban đầu dễ tái tạo cho demo và một số kiểm thử tích hợp.
- Chia sẻ cùng một tình huống học tập trong nhóm.

Ví dụ, danh mục có hai sản phẩm với SKU ổn định và mức giá khác nhau giúp kiểm tra một query theo khoảng giá. Giá trị mẫu được lựa chọn để phân biệt kết quả đúng và sai, thay vì chỉ làm database “có vài dòng”.

Mục tiêu của populator là nạp dữ liệu qua abstraction repository. Nó không tự tạo schema, không tự giải quyết mọi quan hệ và không thay thế quy trình quản lý dữ liệu vận hành.

## 2. Populator nằm ở tầng repository

Luồng khái quát:

~~~mermaid
flowchart LR
    A["Resource JSON hoặc XML"] --> B["ResourceReader / Unmarshaller"]
    B --> C["Object theo kiểu domain"]
    C --> D["Repository phù hợp"]
    D --> E["save theo module dữ liệu"]
    E --> F["Store"]
~~~

Spring Data Commons cung cấp abstraction để nạp ở tầng repository thay vì bắt buộc mô tả dữ liệu bằng SQL. Tài liệu giới thiệu JSON qua Jackson và XML qua Spring OXM. [Repository populators của Spring Data](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.repository-populators)

Tính dùng chung nằm ở tầng giao tiếp với repository, không phải lời hứa rằng mọi fixture sẽ chạy nguyên vẹn trên mọi store.

Những khác biệt vẫn có thể ảnh hưởng:

- Mapping của domain type.
- Chiến lược cấp ID và xác định entity mới.
- Converter và kiểu dữ liệu.
- Cách lưu aggregate hoặc quan hệ.
- Transaction, constraint và index.
- Callback hoặc auditing mà module thực sự áp dụng.

### 2.1. Các thành phần chính

| Thành phần | Trách nhiệm |
| --- | --- |
| RepositoryPopulator | Hợp đồng nạp object vào tập repository |
| ResourceReader | Đọc resource thành object hoặc tập object |
| ResourceReaderRepositoryPopulator | Kết hợp reader với repository để thực hiện nạp |
| FactoryBean tương ứng | Cấu hình reader, resources và tích hợp lifecycle |
| Repository của domain type | Thực hiện thao tác lưu theo module đang dùng |

RepositoryPopulator nhận abstraction Repositories để tìm các repository có trong context. Khi một object được đọc, hạ tầng chọn repository xử lý kiểu object đó. [API RepositoryPopulator](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/init/RepositoryPopulator.html)

Không nên hình dung populator là một SQL script runner được đổi tên. Nó đi qua mô hình object và đường lưu repository.

## 3. Phân biệt với các cơ chế khởi tạo khác

| Nhu cầu | Cơ chế cần đánh giá |
| --- | --- |
| Tạo bảng, cột, constraint, index theo phiên bản | Schema migration hoặc cơ chế schema của stack |
| Chèn dữ liệu bằng SQL theo database | SQL data initialization hoặc migration phù hợp |
| Nạp object mẫu qua repository | Repository populator |
| Dữ liệu cần đi qua use case và invariant nghiệp vụ | Initializer gọi service/domain có chủ đích |
| Fixture riêng của từng test | Setup/fixture của test đó |
| Import lượng dữ liệu lớn có theo dõi tiến độ | Một luồng import có thiết kế riêng |

Một repository populator không phải công cụ migration có lịch sử phiên bản và chính sách chạy một lần đã được cung cấp sẵn.

Tương tự, dữ liệu danh mục bắt buộc cho mọi môi trường không nên bị xem là “demo data” chỉ vì được viết dưới dạng JSON. Cần phân loại mục đích trước khi chọn cách nạp.

Nếu ứng dụng dùng SQL, schema phải được tạo và sẵn sàng trước thao tác save. Spring Boot có các cơ chế khởi tạo database và tích hợp migration riêng; chúng cần được phối hợp theo thứ tự phù hợp. [Database initialization trong Spring Boot](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)

## 4. Ví dụ có phạm vi rõ ràng

Ví dụ chọn:

- Java 17 trở lên.
- Spring Data Commons 3.5.1 và Jackson 2.
- Spring Boot 3.5 để minh họa cấu hình ứng dụng.
- Spring Data JDBC cho phần mapping cụ thể.
- Database demo/test trống với schema đã sẵn sàng.
- Profile sample-data được bật có chủ đích.

Đây là baseline minh họa, không phải suy luận về môi trường của một dự án cụ thể.

Nếu chuyển sang một dòng dùng Jackson 3, phải chọn API/factory và cấu hình mapper tương thích với dòng Spring Data đó. Không truyền mapper của một major khác vào factory Jackson 2 trong ví dụ.

### 4.1. Domain type đơn giản

~~~java
package com.example.seed;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("catalog_product")
public class Product {

    @Id
    private Long id;

    private String sku;
    private String name;
    private BigDecimal price;

    public Product() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
~~~

Table ở đây thuộc relational mapping, còn Id thuộc Spring Data. Nếu dùng JPA hoặc document store, cần mapping tương ứng; không trộn annotation giữa các stack.

Ví dụ chọn class có constructor rỗng và accessor để phần đọc JSON dễ quan sát. Đó không phải yêu cầu mọi domain type bắt buộc phải là Java bean; việc dùng constructor, record hoặc converter khác phải được kiểm chứng với mapper và module thực tế.

### 4.2. Repository

~~~java
package com.example.seed;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    List<Product> findByPriceLessThan(BigDecimal maximum);
}
~~~

Các method tìm theo SKU và giá giúp kiểm tra dữ liệu mẫu sau khi nạp, thay vì chỉ nhìn log startup.

### 4.3. Schema minh họa

Với một SQL dialect hỗ trợ cú pháp tương ứng:

~~~sql
CREATE TABLE catalog_product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(32) NOT NULL,
    name VARCHAR(120) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT uq_catalog_product_sku UNIQUE (sku)
);
~~~

DDL cần được điều chỉnh cho database được chọn và thực thi bởi cơ chế schema của ứng dụng. Populator không tự tạo bảng từ nội dung JSON.

## 5. Fixture JSON và ý nghĩa của _class

Giả sử resource nằm tại sample-data/products.json trên classpath:

~~~json
[
  {
    "_class": "com.example.seed.Product",
    "sku": "SAMPLE_BOOK_01",
    "name": "Sổ tay Spring Data",
    "price": 125000.00
  },
  {
    "_class": "com.example.seed.Product",
    "sku": "SAMPLE_BOOK_02",
    "name": "Thực hành Repository",
    "price": 200000.00
  }
]
~~~

Trong reader Jackson 2 của phiên bản minh họa:

- _class là type key mặc định dùng để xác định class cần tạo.
- Giá trị là tên class mà class loader có thể resolve.
- Một JSON array được đọc thành tập object.
- Sau khi có object, populator chuyển nó tới repository phù hợp.

_class ở fixture này không phải tên repository hoặc tên bảng. Nó cũng không phải lời yêu cầu tạo schema. [Reader JSON của Spring Data Commons 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/repository/init/Jackson2ResourceReader.java)

Không suy rằng alias được một store sử dụng khi lưu dữ liệu sẽ tự là tên type hợp lệ cho reader fixture. Cần kiểm tra hợp đồng của reader đang dùng.

### 5.1. Vì sao fixture không đặt ID?

Ví dụ dùng ID do backend cấp khi lưu entity mới. Bỏ ID giúp thể hiện ý định tạo mới theo cấu hình mapping đã chọn.

Tuy nhiên, điều đó cũng có nghĩa nạp lại không tự tìm sản phẩm cũ theo SKU. Populator không suy rằng SKU là khóa để thực hiện merge.

SKU ổn định giúp test và demo tìm đúng đối tượng mà không hard-code ID được sinh. Unique constraint bảo vệ tính duy nhất theo schema, nhưng không làm loader tự bỏ qua bản ghi trùng.

### 5.2. Type metadata gắn fixture với mô hình Java

Nếu đổi package hoặc đổi tên Product, fixture chứa tên class cũ cũng phải được xem xét.

Đây là một lý do fixture nội bộ không nên được mặc định là một định dạng trao đổi công khai lâu dài. Với luồng import cần hợp đồng độc lập khỏi domain class, DTO và mapping theo use case có thể phù hợp hơn.

## 6. Đăng ký populator có kiểm soát

Cấu hình sau sử dụng mapper Jackson 2 do ứng dụng cung cấp, tạo bản sao riêng cho fixture và chỉ bỏ qua field metadata _class của Product:

~~~java
package com.example.seed;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.sql.init.dependency
        .DependsOnDatabaseInitialization;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init
        .Jackson2RepositoryPopulatorFactoryBean;

@Configuration(proxyBeanMethods = false)
@Profile("sample-data")
public class SampleDataConfiguration {

    @Bean
    @DependsOnDatabaseInitialization
    Jackson2RepositoryPopulatorFactoryBean productPopulator(
            ObjectMapper applicationMapper) {

        ObjectMapper fixtureMapper = applicationMapper.copy();
        fixtureMapper.enable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        fixtureMapper.addMixIn(
                Product.class, FixtureMetadata.class);

        var factory = new Jackson2RepositoryPopulatorFactoryBean();
        factory.setMapper(fixtureMapper);
        factory.setResources(new Resource[] {
                new ClassPathResource("sample-data/products.json")
        });

        return factory;
    }

    @JsonIgnoreProperties("_class")
    abstract static class FixtureMetadata {
    }
}
~~~

Mỗi public type của ví dụ được hiểu là một type riêng trong cùng package.

Điểm đáng chú ý:

1. Profile sample-data làm cho việc nạp được bật có chủ đích.
2. Resource được chỉ rõ, giúp quan sát tập dữ liệu sẽ được nạp.
3. Mapper dùng cho fixture không bị cấu hình bằng cách sửa trực tiếp mapper dùng chung.
4. _class được reader sử dụng làm metadata, còn mixin cho phép bỏ qua nó khi bind Product.
5. Các field lạ khác, chẳng hạn prcie thay cho price, được chọn chính sách từ chối.
6. Schema initialization là một điều kiện được xét riêng trong ví dụ SQL/Boot.

Factory có setter cho ObjectMapper và tạo Jackson2ResourceReader từ mapper đó. Reader mặc định của phiên bản minh họa bỏ qua unknown properties; việc tự cung cấp mapper có thể thay đổi hành vi này. Vì vậy cần cấu hình và kiểm thử có chủ đích. [Factory Jackson 2](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/repository/init/Jackson2RepositoryPopulatorFactoryBean.java)

DependsOnDatabaseInitialization thể hiện phụ thuộc khởi tạo database trong tích hợp Boot. Nó không tạo schema và không thay thế việc quản lý thứ tự với các hệ thống khởi tạo riêng ngoài cơ chế Boot nhận biết. [API DependsOnDatabaseInitialization](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/sql/init/dependency/DependsOnDatabaseInitialization.html)

Không cần thêm EnableSpringDataWebSupport chỉ để nạp fixture này. Chức năng populator được cấu hình ở tầng repository; các ví dụ web khác trong Spring Data không có nghĩa đây là một thao tác HTTP.

## 7. Thời điểm chạy trong lifecycle

Với factory của bản 3.5.1, việc populate được gọi khi factory nhận ContextRefreshedEvent của ApplicationContext mà nó thuộc về.

Đường tích hợp này không chỉ là “gọi save ngay lúc Java chạy method Bean”. Factory tạo populator và tham gia xử lý sự kiện context. [Lifecycle của factory](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/repository/init/AbstractRepositoryPopulatorFactoryBean.java)

Hệ quả cần tính:

- Repository phải sẵn sàng khi nạp.
- Store và schema/index cần thiết phải dùng được.
- Một service hoặc endpoint được sử dụng sau khởi tạo cần biết dữ liệu mẫu đã nạp thành công hay chưa.
- Context mới hoặc việc refresh thuộc vòng đời tương ứng có thể dẫn tới lần nạp tiếp theo.

Không coi ContextRefreshedEvent là một lịch sử bền vững chứng minh fixture đã chạy đúng một lần trên database này.

Trong kiểm thử, dữ liệu nạp ở startup thuộc vòng đời context. Một transaction bắt đầu riêng cho test method không tự biến phần nạp trước đó thành dữ liệu sẽ được rollback cùng test.

## 8. Nạp qua repository không đồng nghĩa chạy đầy đủ use case

ResourceReaderRepositoryPopulator đọc resource, lấy từng object rồi gọi thao tác save thông qua repository invoker phù hợp.

Nó không mặc nhiên gọi ProductService.create, không gửi HTTP request và không áp dụng Valid của một controller. [Luồng đọc và lưu object](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/repository/init/ResourceReaderRepositoryPopulator.java)

Cần phân biệt:

| Thành phần | Có tự được populator bảo đảm không? |
| --- | --- |
| Deserialize thành object | Có, qua reader đã cấu hình |
| Chọn repository cho domain type | Có, theo hạ tầng repository |
| Luật nghiệp vụ đặt trong service | Không tự đi qua service đó |
| Validation đặt tại controller | Không có request controller để kích hoạt |
| Mapping/converter của repository | Phụ thuộc đường lưu và module thực tế |
| Callback/auditing của module | Cần cấu hình và kiểm chứng đúng module |
| Tạo tài khoản, gửi email, phát workflow | Không phải mục đích tự động của populator |

Nếu một aggregate chỉ hợp lệ sau một chuỗi use case, nạp trực tiếp một object có thể bỏ qua invariant hoặc tác động nghiệp vụ quan trọng.

Trong trường hợp đó, hãy chọn initializer gọi domain/service thích hợp hoặc một fixture có hợp đồng riêng. Không đưa mọi rule vào setter chỉ để JSON trông như một lệnh tạo đầy đủ.

### 8.1. Validation cần được kiểm chứng riêng

Mapper có thể từ chối field lạ nhưng không vì thế mà tự kiểm tra mọi constraint nghiệp vụ.

Ví dụ price bằng số âm có thể được deserialize thành BigDecimal hợp lệ về mặt kiểu. Nếu schema chỉ khai báo NOT NULL và domain không kiểm tra giá, thao tác nạp vẫn có thể lưu một giá trị không mong muốn.

Ngược lại, một store/provider có thể kích hoạt validation ở vòng đời lưu theo cấu hình riêng. Không khái quát hành vi của một provider thành cam kết của Commons.

Một fixture tốt phải được kiểm tra bằng các điều kiện chấp nhận có ý nghĩa, không chỉ bằng việc JSON parse được.

## 9. Chạy lại và idempotency là bài toán riêng

Idempotency trong bối cảnh này có nghĩa lần nạp tiếp theo đạt trạng thái mục tiêu đã định, không vô tình tạo thêm hoặc phá dữ liệu.

Populator chuẩn không tự cung cấp một chính sách nghiệp vụ chung như:

~~~text
Nếu SKU chưa tồn tại thì tạo,
nếu đã tồn tại thì giữ nguyên,
nếu khác giá thì báo lỗi.
~~~

Với fixture của ví dụ, ID không được gửi và store cấp ID mới. Lần nạp tiếp theo trên database còn dữ liệu có thể cố tạo thêm hai sản phẩm. Unique constraint trên SKU có thể khiến lần nạp đó thất bại.

Không nên suy rằng:

- Tên file giống nhau sẽ được framework nhớ là đã nạp.
- Một profile chỉ chạy được đúng một lần.
- Có ID cố định thì mọi module đều tự upsert an toàn.
- Thêm version vào fixture luôn làm mọi lần save trở nên tương thích.
- count bằng 0 là một cơ chế kiểm soát đầy đủ cho nạp lại.

### 9.1. ID cố định không phải lời giải dùng chung

Hành vi save còn phụ thuộc cách nhận diện entity mới và khả năng của store. ID, version, Persistable hoặc chiến lược tùy biến có thể làm thay đổi nhánh thực thi.

Một fixture mang ID đã gán có thể cần cách xử lý khác với fixture để ID null. Không sử dụng một kết quả quan sát từ một backend để tuyên bố đây là cơ chế merge chung của Spring Data.

### 9.2. Chọn chính sách theo môi trường

| Môi trường/nhu cầu | Chính sách có thể chọn |
| --- | --- |
| Demo trên database dùng riêng, tạo mới mỗi lần | Nạp fixture vào trạng thái trống đã biết |
| Test cần dữ liệu khác nhau từng case | Chuẩn bị fixture tại phạm vi test phù hợp |
| Local cần giữ dữ liệu giữa các lần chạy | Initializer có chính sách theo khóa nghiệp vụ |
| Dữ liệu tham chiếu bắt buộc theo phiên bản | Migration hoặc cơ chế quản lý thay đổi dữ liệu |
| Import có thể chạy lại sau lỗi | Luồng import có kiểm soát tiến độ và retry |

Một initializer theo khóa nghiệp vụ vẫn phải xử lý cạnh tranh đồng thời và ràng buộc store. exists rồi save không tự ngăn hai tiến trình cùng tạo.

Không đặt thao tác xóa toàn bộ dữ liệu vào một đường startup chỉ để “chống trùng” nếu đó không phải chính sách đã xác định cho database cô lập dùng riêng.

## 10. Transaction và trạng thái nạp dở

Mặc định không nên coi toàn bộ tập resource là một transaction nguyên tử.

Cách gọi save và transaction thực tế phụ thuộc repository/module và các transaction bao quanh. Cơ chế nạp qua từng object không tự tạo một transaction chung cho mọi resource, mọi repository hoặc nhiều store.

Ví dụ có ba object hợp lệ về cú pháp JSON:

1. Sản phẩm thứ nhất lưu thành công.
2. Sản phẩm thứ hai lưu thành công.
3. Sản phẩm thứ ba vi phạm constraint khi ghi.

Nếu không có transaction bao quanh phù hợp, hai bản ghi trước có thể vẫn còn dù quá trình startup báo lỗi.

Một lỗi đọc JSON ở resource tiếp theo cũng có thể xảy ra sau khi resource trước đã được lưu. Ngược lại, reader có thể đọc/deserialise toàn bộ một resource trước khi bắt đầu lưu các object của chính resource đó. Cần phân biệt lỗi ở bước đọc với lỗi ở bước ghi, không suy thứ tự ghi chỉ từ vị trí một dòng JSON.

### 10.1. Kết quả sau lỗi cần có chính sách

Trước khi dùng populator cho một tình huống cụ thể, cần trả lời:

- Lỗi có làm context khởi tạo thất bại không?
- Dữ liệu đã ghi trước lỗi được giữ hay rollback?
- Lần thử lại xử lý trạng thái dở thế nào?
- Có thể xác nhận độc lập trạng thái mục tiêu không?
- Những repository nào tham gia và chúng có chung tài nguyên transaction không?

Không chỉ catch mọi exception rồi tiếp tục chạy ứng dụng như thể dữ liệu mẫu đã đầy đủ. Một demo thiếu một nửa fixture có thể tạo kết luận sai về query hoặc màn hình cần kiểm thử.

Nếu yêu cầu atomicity vượt quá khả năng của đường nạp đang dùng, cần một cơ chế điều phối transaction/import phù hợp thay vì gán kỳ vọng đó cho tên RepositoryPopulator.

## 11. Quan hệ và thứ tự resource

Ví dụ Product được chọn độc lập để tránh phải giải quyết quan hệ giữa nhiều aggregate ngay trong bài đầu.

Với dữ liệu có tham chiếu:

- Entity con có thể cần khóa của entity cha.
- ID được store sinh có thể chưa biết trong file fixture.
- Cách lưu object lồng nhau khác nhau theo module và mapping.
- Constraint ở database có thể yêu cầu thứ tự ghi.
- Callback có thể thay đổi state hoặc metadata trong quá trình save.

Không mặc định loader sẽ tự giải một đồ thị dependency tùy ý hoặc gán lại mọi tham chiếu theo khóa nghiệp vụ.

Nếu dùng nhiều resource và thứ tự có ý nghĩa, có thể liệt kê chúng tường minh:

~~~java
factory.setResources(new Resource[] {
        new ClassPathResource("sample-data/categories.json"),
        new ClassPathResource("sample-data/products.json")
});
~~~

Các type và quan hệ thực tế vẫn phải được thiết kế phù hợp. Thứ tự resource không tự giải quyết một tham chiếu tới ID vừa được sinh nhưng fixture không biết.

Cũng không dựa vào việc đặt tên file 01, 02 để suy rằng mọi cơ chế tìm resource bằng wildcard luôn cung cấp thứ tự nghiệp vụ cần thiết.

Đối với aggregate có quan hệ phức tạp, một initializer dùng service/domain có thể diễn đạt ý định và nhận ID kết quả rõ hơn.

## 12. Kiểm thử dữ liệu mẫu bằng hành vi đọc thật

Ví dụ integration test trong một ứng dụng Boot có repository JDBC, schema test đã sẵn sàng và database cô lập, trống trước khi context được tạo:

~~~java
package com.example.seed;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("sample-data")
@Import(SampleDataConfiguration.class)
class ProductSampleDataTest {

    @Autowired
    ProductRepository products;

    @Test
    void loadsExpectedProductsAndSupportsDerivedQuery() {
        Product first = products.findBySku("SAMPLE_BOOK_01")
                .orElseThrow();

        assertNotNull(first.getId());
        assertEquals("Sổ tay Spring Data", first.getName());
        assertEquals(0,
                new BigDecimal("125000.00")
                        .compareTo(first.getPrice()));

        List<String> cheaperSkus = products
                .findByPriceLessThan(new BigDecimal("150000.00"))
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(List.of("SAMPLE_BOOK_01"), cheaperSkus);
        assertEquals(2L, products.count());
    }
}
~~~

Assertion count bằng 2 chỉ có ý nghĩa với điều kiện database test chứa đúng fixture này và không có thao tác khác thêm dữ liệu. Không dùng nó trên một database dùng chung không kiểm soát.

Test tìm theo SKU giúp tránh phụ thuộc vào ID sinh tự động. Assertion giá dùng so sánh giá trị BigDecimal thay vì buộc scale sau một vòng đọc/ghi phải giống nguyên văn JSON.

Các đoạn code trong bài minh họa cách thiết kế kiểm thử; chúng không xác nhận đã chạy trong một môi trường cụ thể.

### 12.1. Ma trận kiểm thử nên có

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Profile sample-data bật | Resource được nạp và dữ liệu đọc lại đúng |
| Profile không bật | Không nạp fixture chỉ vì file có trên classpath |
| Resource không tồn tại | Lỗi phù hợp với chính sách khởi tạo |
| _class thiếu hoặc sai | Reader không diễn giải nhầm type |
| Property viết sai | Bị phát hiện theo cấu hình mapper đã chọn |
| Giá trị vi phạm constraint | Kết quả lỗi và state sau lỗi được hiểu rõ |
| Nạp lại trên dữ liệu có sẵn | Hành vi đúng với chính sách restart |
| Hai tiến trình khởi tạo đồng thời | Constraint/chính sách cạnh tranh hoạt động |
| Quan hệ giữa object | Reference và thứ tự ghi đúng |
| Auditing/version được sử dụng | Metadata đúng với module và ngữ cảnh khởi tạo |
| Dữ liệu mẫu dùng cho phân trang/sort | Các giá trị được chọn đủ để phân biệt kết quả |

Một mock repository chỉ ghi nhận save được gọi chưa chứng minh mapping, converter hoặc constraint store hoạt động. Test tích hợp đọc lại là bằng chứng cần thiết cho đường nạp mẫu.

Ngược lại, một context test thành công không có nghĩa mọi use case nghiệp vụ đã được chạy: populator vẫn có thể đi thẳng qua repository.

## 13. JSON, XML và cấu hình reader

JSON thường dễ đọc cho fixture nhỏ. XML có thể phù hợp khi ứng dụng đã có mô hình và cấu hình OXM tương ứng.

Trong bản 3.5.1:

| Lựa chọn | Thành phần điển hình |
| --- | --- |
| JSON với Jackson 2 | Jackson2RepositoryPopulatorFactoryBean và Jackson2ResourceReader |
| XML qua Spring OXM | UnmarshallerRepositoryPopulatorFactoryBean và Unmarshaller |

Factory cho unmarshaller yêu cầu một Unmarshaller được cấu hình. Nó không tự suy ra toàn bộ JAXB/OXM setup từ một file XML bất kỳ. [Unmarshaller repository populator](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/repository/init/UnmarshallerRepositoryPopulatorFactoryBean.java)

Không chuyển nguyên quy tắc _class của ví dụ JSON thành một giả định bắt buộc cho mọi định dạng XML. Reader và cơ chế mapping quyết định object được tạo như thế nào.

### 13.1. Chọn mapper phù hợp với fixture

Nếu fixture có Instant, UUID, enum hoặc value object đặc thù, phải xác nhận mapper có khả năng đọc đúng representation đã chọn.

Tạo một ObjectMapper mặc định không tự có mọi module của ứng dụng. Ngược lại, dùng mapper của ứng dụng mà không kiểm tra policy unknown property cũng có thể làm hành vi fixture đổi theo một tùy biến web.

Với reader đi qua cây JSON, số thập phân lớn cũng cần được kiểm thử về độ chính xác của cả bước đọc cây lẫn bind sang domain type. Đừng chỉ nhìn kiểu field cuối cùng là BigDecimal rồi bỏ qua pipeline trước đó.

Fixture chỉ nên chứa dữ liệu từ nguồn được kiểm soát. Type metadata cho phép reader xác định class cần tạo, nên không coi ví dụ populator này là một endpoint import JSON không tin cậy.

Nếu cần nhận dữ liệu từ người dùng, nên có hợp đồng input, giới hạn type, validation và mapping phù hợp cho luồng import đó.

## 14. Thiết kế một tập dữ liệu mẫu có giá trị

Một fixture hữu ích không cần lớn, nhưng mỗi nhóm dữ liệu nên có lý do tồn tại.

Ví dụ để học repository:

| Mục tiêu | Dữ liệu có thể chuẩn bị |
| --- | --- |
| Derived query theo giá | Hai hoặc nhiều giá trị ở hai phía của ngưỡng |
| Sort có khóa phụ | Các bản ghi cùng giá hoặc cùng thời gian chính |
| Phân trang | Đủ item cho nhiều trang và trang cuối không đầy |
| Projection | Field cần công bố và field không thuộc response |
| Nullable field | Giá trị có mặt và null nếu miền dữ liệu cho phép |
| Unicode | Chuỗi tiếng Việt xác định |
| Auditing | Actor/thời gian phù hợp với cấu hình kiểm thử |

Không tự thêm các field minh họa vào entity thật chỉ để có nhiều tình huống. Dataset phải phản ánh mô hình và mục tiêu bài học.

Một số thực hành giúp fixture dễ duy trì:

- Dùng khóa nghiệp vụ rõ và ổn định để test tìm dữ liệu.
- Dùng dữ liệu tổng hợp thay cho thông tin người dùng thật.
- Giữ thời gian và giá trị có thể xác định lại khi chúng tham gia assertion.
- Ghi nhận giả định về database trống, schema và profile.
- Cập nhật fixture cùng thay đổi domain/mapping.
- Kiểm tra giá trị quan trọng sau khi nạp, không chỉ số bản ghi.

Nếu fixture bắt đầu cần xử lý hàng nghìn quan hệ, nhiều bước nghiệp vụ, retry và kiểm soát lỗi chi tiết, hãy đánh giá lại liệu một populator đơn giản còn là abstraction phù hợp không.

## 15. Chẩn đoán lỗi thường gặp

| Biểu hiện | Khả năng cần xem xét |
| --- | --- |
| Context không khởi động vì không tìm được type | _class sai tên, class không có hoặc class loader không phù hợp |
| Không tìm được repository để lưu | Domain type chưa được quản lý hoặc repository chưa được phát hiện |
| Lỗi bảng/column không tồn tại | Schema chưa có hoặc mapping không khớp |
| Resource đọc được nhưng field bị null | Property sai tên, creator/accessor hoặc mapper không phù hợp |
| Lần đầu chạy được, lần sau lỗi trùng | Chưa có chính sách idempotency cho database còn dữ liệu |
| Dữ liệu chỉ nạp một phần | Lỗi ghi giữa chừng và transaction không bao toàn bộ |
| Fixture không xuất hiện trong test | Profile/configuration không được nạp hoặc test slice khác context dự định |
| Test riêng qua, chạy chung sai | Database, context hoặc dữ liệu khởi tạo bị dùng chung |
| Auditing không có actor | Chưa định nghĩa actor cho đường startup hoặc auditing chưa được cấu hình |
| JSON hợp lệ nhưng dữ liệu nghiệp vụ sai | Populator không đi qua rule của service/domain như kỳ vọng |

Log “đọc resource” chỉ chứng minh một bước đã bắt đầu. Cần phân biệt đọc, deserialize, gọi save và xác nhận dữ liệu sau lưu.

Hạ tầng có thể phát sự kiện RepositoriesPopulatedEvent sau khi hoàn tất vòng populate. Sự kiện đó không thay thế các assertion nghiệp vụ hoặc tự chứng minh atomicity của mọi tài nguyên tham gia.

## 16. Tự kiểm tra

1. Repository populator hoạt động ở tầng nào và khác SQL script runner ở đâu?
2. Vì sao _class là tên domain type, không phải tên bảng hoặc repository?
3. Một fixture không có ID có thể gặp vấn đề gì khi nạp lại?
4. Vì sao ID cố định không tự bảo đảm idempotency trên mọi store?
5. Populator có tự gọi validation ở controller hoặc use case tạo sản phẩm không?
6. Khi object thứ ba lỗi lúc ghi, có thể kết luận hai object đầu đã rollback không?
7. Vì sao cần kiểm thử lại bằng repository thay vì chỉ nhìn log?
8. Transaction của test method có tự rollback dữ liệu đã nạp trước đó lúc startup không?
9. Khi nào nên dùng initializer gọi service hoặc một cơ chế migration/import khác?
10. Cần chuẩn bị dữ liệu như thế nào để kiểm tra sort và phân trang có ý nghĩa?

Repository populator cung cấp một cách thuận tiện để đưa dữ liệu mẫu có kiểm soát vào repository. Giá trị của nó nằm ở khả năng tái tạo một trạng thái học tập, demo hoặc kiểm thử rõ ràng, đi cùng các giả định được xác định về schema, môi trường, vòng đời lưu trữ và hành vi khi nạp lại.
