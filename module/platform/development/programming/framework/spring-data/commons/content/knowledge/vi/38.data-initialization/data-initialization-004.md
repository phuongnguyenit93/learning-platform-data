# Dependency tùy chọn, cấu hình resource và vòng đời khởi tạo

## 1. Ba điều kiện để dữ liệu khởi tạo được nạp đúng

Trong chương **Khởi tạo dữ liệu** của module **SPRING_DATA_COMMONS**, repository populator giúp đọc đối tượng từ resource rồi lưu chúng qua repository phù hợp.

Cơ chế này hữu ích cho dữ liệu tham chiếu nhỏ, dữ liệu minh họa hoặc fixture của một môi trường học. Để nó hoạt động đúng, cần đồng thời xác định:

1. Dependency nào cung cấp bộ đọc JSON hoặc XML.
2. Resource nằm ở đâu và được ánh xạ thành domain object như thế nào.
3. Thời điểm nào trong vòng đời application context việc lưu dữ liệu được thực hiện.

Có JSON trên classpath chưa đủ để tự nạp dữ liệu. Có class populator trong Commons cũng chưa đủ để tạo repository hoặc cơ sở dữ liệu.

Luồng khái quát:

```text
Resource JSON/XML
      |
      v
ResourceReader hoặc Unmarshaller
      |
      v
Domain object hoặc Collection<domain object>
      |
      v
Tìm repository tương ứng với kiểu đối tượng
      |
      v
Gọi thao tác lưu qua RepositoryInvoker
```

Phần dùng chung điều phối đọc và lưu. Mapping entity, phát hiện đối tượng mới, transaction, cascade và cách ghi dữ liệu vẫn thuộc module lưu trữ cùng cấu hình ứng dụng.

Sau bài học, bạn có thể chọn dependency cần thiết, cấu hình resource rõ ràng, giải thích thời điểm populate và nhận diện các giới hạn về chạy lại, thứ tự cùng tính nguyên tử.

## 2. Dependency tùy chọn nghĩa là gì?

### 2.1. Chỉ đưa vào ứng dụng những thành phần được sử dụng

Commons cung cấp abstraction và các điểm tích hợp, nhưng không bắt mọi ứng dụng phải kéo theo toàn bộ thư viện JSON/XML.

Ví dụ trong POM của dòng Commons 3.5, `jackson-databind` và `spring-oxm` được khai báo optional. Ứng dụng sử dụng những nhánh tích hợp đó cần bảo đảm dependency cần thiết có mặt qua khai báo trực tiếp hoặc dependency phù hợp khác. Xem [POM chính thức của Commons 3.5](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/pom.xml).

| Nhu cầu | Thành phần cần có trong ứng dụng |
| --- | --- |
| Populator JSON dùng Jackson 2 | Commons cùng Jackson 2 databind và các module dữ liệu cần thiết |
| Populator JSON dùng API Jackson 3 | Phiên bản Commons có API tương ứng cùng Jackson 3 phù hợp |
| Populator XML qua Spring OXM | `spring-oxm` và một `Unmarshaller` đã cấu hình |
| XML qua JAXB | API và runtime JAXB tương thích với nền tảng |
| Lưu domain object | Module lưu trữ, repository, mapping và kết nối backend |

Các tọa độ thường gặp:

- Jackson 2 databind: `com.fasterxml.jackson.core:jackson-databind`.
- Spring OXM: `org.springframework:spring-oxm`.
- JAXB API: `jakarta.xml.bind:jakarta.xml.bind-api`.
- Một runtime JAXB phù hợp, chẳng hạn implementation do nền tảng lựa chọn.

Không cần thêm XML stack nếu ứng dụng chỉ dùng JSON. Ngược lại, thêm một JAXB API chưa chắc đã cung cấp runtime thực hiện unmarshalling.

Nên giữ các phiên bản theo BOM hoặc dependency management của nền tảng đang dùng. “Optional” không có nghĩa phiên bản của thư viện có thể chọn tùy ý.

### 2.2. Phân biệt Jackson 2 và Jackson 3 theo phiên bản

Các ví dụ JSON chính của bài dùng **Java 17, Commons 3.5 và Jackson 2**:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.repository.init.Jackson2RepositoryPopulatorFactoryBean;
```

Từ Commons 4.0 có `JacksonRepositoryPopulatorFactoryBean` cho đường Jackson 3:

```java
import tools.jackson.databind.ObjectMapper;
import org.springframework.data.repository.init.JacksonRepositoryPopulatorFactoryBean;
```

Factory mới xuất hiện từ 4.0; factory Jackson 2 được đánh dấu deprecated từ dòng này để chuyển sang API mới. Xem [API JacksonRepositoryPopulatorFactoryBean](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/init/JacksonRepositoryPopulatorFactoryBean.html) và [mã nguồn tại tag 4.0.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.0.0/src/main/java/org/springframework/data/repository/init/JacksonRepositoryPopulatorFactoryBean.java).

Hai `ObjectMapper` ở trên thuộc hai package khác nhau. Không chỉ đổi tên factory rồi truyền mapper của nhánh còn lại.

Khi áp dụng cho phiên bản khác, đối chiếu đúng API và dependency đã resolve; không trộn ví dụ từ các dòng tài liệu khác nhau.

## 3. Domain và repository của ví dụ JSON

Để làm ví dụ cụ thể, phần này chọn JPA. Cơ chế populator vẫn điều phối qua repository, nhưng các annotation persistence dưới đây thuộc lựa chọn JPA.

```java
package example.catalog;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "countries")
public class Country {

    @Id
    private String code;

    private String name;

    public Country() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Repository:

```java
package example.catalog;

import org.springframework.data.repository.CrudRepository;

public interface CountryRepository
        extends CrudRepository<Country, String> {
}
```

Ứng dụng vẫn cần cấu hình JPA, quét entity và repository, cùng schema hoặc cơ chế tạo schema phù hợp. Với store khác, dùng mapping định danh và repository mà store đó hỗ trợ.

Resource JSON minh họa tại `seed/countries.json` trên classpath:

```json
[
  {
    "_class": "example.catalog.Country",
    "code": "VN",
    "name": "Việt Nam"
  },
  {
    "_class": "example.catalog.Country",
    "code": "JP",
    "name": "Nhật Bản"
  }
]
```

Trong đường reader JSON này, `_class` giúp xác định kiểu Java của từng đối tượng. Tên class phải khớp với class có trong ứng dụng, và phải có repository phù hợp cho kiểu đó.

Đây là metadata của dữ liệu khởi tạo, không phải yêu cầu thêm một thuộc tính `_class` vào entity.

Reader không tự biến một DTO bất kỳ thành entity. Nếu `_class` chỉ đến kiểu không có repository lưu tương ứng, quá trình persist có thể thất bại.

Vì type hint xác định class được tạo, resource seed nên là dữ liệu do ứng dụng kiểm soát. Cơ chế này khác với thiết kế một API nhập JSON tùy ý từ client.

## 4. Cấu hình JSON populator trong Commons 3.5

### 4.1. FactoryBean do Spring quản lý

Ví dụ ứng dụng đã có một bean `ObjectMapper` được cấu hình cho các kiểu dữ liệu cần đọc:

```java
package example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init.Jackson2RepositoryPopulatorFactoryBean;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

@Configuration
@Profile("demo")
public class ReferenceDataConfiguration {

    @Bean
    Jackson2RepositoryPopulatorFactoryBean referenceDataPopulator(
            ObjectMapper applicationMapper) {

        ObjectMapper seedMapper = applicationMapper.copy();
        seedMapper.addMixIn(Country.class, SeedTypeHint.class);
        seedMapper.enable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        Resource[] resources = {
                new ClassPathResource("seed/countries.json")
        };

        for (Resource resource : resources) {
            if (!resource.exists() || !resource.isReadable()) {
                throw new IllegalStateException(
                        "Không đọc được resource khởi tạo: "
                                + resource.getDescription());
            }
        }

        Jackson2RepositoryPopulatorFactoryBean factory =
                new Jackson2RepositoryPopulatorFactoryBean();

        factory.setMapper(seedMapper);
        factory.setResources(resources);
        return factory;
    }

    @JsonIgnoreProperties("_class")
    private abstract static class SeedTypeHint {
    }
}
```

Có bốn quyết định của ứng dụng trong ví dụ:

1. Chỉ đăng ký cấu hình khi profile `demo` hoạt động.
2. Dùng mapper copy để giữ những hỗ trợ kiểu dữ liệu cần thiết mà không sửa mapper chung.
3. Bỏ qua riêng metadata `_class` khi ánh xạ `Country`, đồng thời từ chối field JSON khác không thuộc mô hình.
4. Kiểm tra resource mong đợi có tồn tại và đọc được.

Profile điều khiển việc đăng ký cấu hình. Nó không thay thế dependency cần thiết khi biên dịch hoặc nạp phần cấu hình đó.

### 4.2. Vì sao phải chú ý mapper tùy chỉnh?

Ở reader Jackson 2 của Commons 3.5, mapper mặc định được tạo riêng và tắt `FAIL_ON_UNKNOWN_PROPERTIES`. Reader đọc type hint rồi dùng mapper để ánh xạ node thành kiểu đã tìm được. Xem [Jackson2ResourceReader](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/repository/init/Jackson2ResourceReader.java).

Khi truyền mapper riêng, ứng dụng chịu trách nhiệm với chính sách unknown field và các module đã đăng ký. Nếu mapper bật kiểm tra field không biết nhưng chưa xử lý `_class`, metadata này có thể làm deserialize thất bại.

Mixin trong ví dụ giữ domain không cần khai báo thuộc tính cho metadata seed. Nó cũng cho phép bắt một lỗi chính tả như `nmae` thay vì âm thầm bỏ field đó.

Với domain có `Instant`, `LocalDate`, `Optional` hoặc kiểu riêng, kiểm tra mapper dùng cho seed có module, format và converter cần thiết. Không mặc định rằng mapper do populator tự tạo giống mapper của ứng dụng web.

### 4.3. Tạo bean chưa đồng nghĩa đã lưu dữ liệu

Bean method trả về `Jackson2RepositoryPopulatorFactoryBean`. Spring quản lý callback và listener của factory; sản phẩm của factory là `ResourceReaderRepositoryPopulator`.

Không tự tạo factory bằng `new` ở một đoạn code rồi gọi `getObject()` trước khi lifecycle được hoàn tất và kỳ vọng nó tự nhận các event của context.

Trong cách truy xuất bean của Spring, tên bean thông thường trỏ tới sản phẩm factory; tiền tố `&` dùng khi cần chính factory. Phân biệt này giúp tránh nhầm giữa cấu hình factory và việc gọi populate trực tiếp.

## 5. Resource: vị trí, số lượng và thứ tự

### 5.1. Chọn đúng abstraction

| Cách cấu hình | Ý nghĩa |
| --- | --- |
| `new ClassPathResource("seed/countries.json")` | Một resource theo đường dẫn classpath |
| `resourceLoader.getResource("classpath:seed/countries.json")` | Resolve một location qua `ResourceLoader` |
| Location có tiền tố `file:` | Resource từ hệ thống file theo môi trường triển khai |
| Pattern `classpath*:seed/reference/*.json` | Tìm nhiều resource qua `ResourcePatternResolver` |

Constructor `ClassPathResource` nhận đường dẫn classpath, không cần thêm tiền tố `classpath:` vào chuỗi của constructor này.

Resource trên classpath có thể nằm trong JAR. Vì vậy, không thay cơ chế đọc stream bằng `getFile()` rồi suy rằng mọi resource đều là file vật lý riêng. Spring mô tả các khả năng này trong [tài liệu Resources](https://docs.spring.io/spring-framework/reference/core/resources.html).

### 5.2. Pattern rỗng và resource trùng

Khi dùng resolver để lấy nhiều file, cần quyết định rõ nếu pattern không khớp file nào.

Ví dụ thay phần tạo mảng resource trong bean method, với `context` là `ApplicationContext` được inject:

```java
Resource[] resources =
        context.getResources("classpath*:seed/reference/*.json");

if (resources.length == 0) {
    throw new IllegalStateException(
            "Không tìm thấy resource dữ liệu tham chiếu");
}

java.util.Arrays.sort(
        resources,
        java.util.Comparator.comparing(Resource::getDescription));

factory.setResources(resources);
```

Đoạn này cần đặt trong phương thức cho phép xử lý `IOException`, và `factory` là factory đã được cấu hình mapper.

Việc có một mảng resource rỗng không luôn tự gây lỗi ở populator. Nếu dữ liệu bắt buộc phải có, ứng dụng cần kiểm tra yêu cầu đó.

`classpath*:` có thể tìm thấy nhiều resource cùng tên từ các thành phần classpath khác nhau. Vì thế, cũng cần xác định có cho phép dữ liệu trùng nguồn hay không.

### 5.3. Thứ tự kỹ thuật không thay cho quan hệ dữ liệu

Populator đọc các resource theo collection đã cấu hình. Sắp xếp theo mô tả làm thứ tự rõ hơn, nhưng không chứng minh thứ tự đó đúng với phụ thuộc nghiệp vụ.

Nếu bảng thành phố cần quốc gia tồn tại trước, hãy thiết kế thứ tự resource hoặc luồng seed theo quan hệ đó. Với dữ liệu có phụ thuộc phức tạp, một service khởi tạo tường minh có thể phù hợp hơn việc dựa vào kết quả glob.

Mỗi factory dùng một đường reader đã chọn. Không đưa cả JSON và XML vào cùng danh sách rồi kỳ vọng nó tự suy ra reader theo phần mở rộng.

Resource được cấu hình trước khi factory tạo sản phẩm. Đây không phải cơ chế theo dõi thay đổi file; sửa resource sau khi ứng dụng đã khởi tạo không tự kích hoạt một lần populate mới.

## 6. Phương án XML qua Spring OXM

### 6.1. Chọn Unmarshaller phù hợp

`UnmarshallerRepositoryPopulatorFactoryBean` dùng abstraction `org.springframework.oxm.Unmarshaller`. Factory yêu cầu một unmarshaller đã được cung cấp; chỉ thêm XML resource chưa đủ.

Nếu chọn JAXB cho ví dụ, domain `Country` cần mapping JAXB tương ứng. Với biến thể thực hành XML, có thể bổ sung lên class `Country`:

```java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "country")
@XmlAccessorType(XmlAccessType.FIELD)
```

Các annotation này được đặt cùng các annotation persistence trên class đã khai báo. Đây là bổ sung cho phương án XML, không phải dependency bắt buộc của phương án JSON.

Resource `seed/country.xml` minh họa một đối tượng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<country>
    <code>VN</code>
    <name>Việt Nam</name>
</country>
```

### 6.2. Cấu hình factory XML

```java
package example.catalog;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init.UnmarshallerRepositoryPopulatorFactoryBean;
import org.springframework.oxm.Unmarshaller;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
@Profile("xml-demo")
public class XmlReferenceDataConfiguration {

    @Bean
    Jaxb2Marshaller seedUnmarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setClassesToBeBound(Country.class);
        return marshaller;
    }

    @Bean
    UnmarshallerRepositoryPopulatorFactoryBean xmlReferenceDataPopulator(
            @Qualifier("seedUnmarshaller") Unmarshaller unmarshaller) {

        UnmarshallerRepositoryPopulatorFactoryBean factory =
                new UnmarshallerRepositoryPopulatorFactoryBean();

        factory.setUnmarshaller(unmarshaller);
        factory.setResources(new Resource[] {
                new ClassPathResource("seed/country.xml")
        });

        return factory;
    }
}
```

`Jaxb2Marshaller` triển khai cả abstraction marshaller và unmarshaller. Cần JAXB API/runtime tương thích; Spring OXM không tự cung cấp mọi implementation XML. Xem [tài liệu Spring OXM](https://docs.spring.io/spring-framework/reference/data-access/oxm.html).

Ở factory XML, thiếu unmarshaller bị phát hiện trong quá trình khởi tạo bean. Cơ chế này được thể hiện trong [UnmarshallerRepositoryPopulatorFactoryBean](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/repository/init/UnmarshallerRepositoryPopulatorFactoryBean.java).

### 6.3. Chú ý hình dạng object sau unmarshalling

Populator lưu object do reader trả về, hoặc từng phần tử nếu kết quả là collection. Nó không tự hiểu mọi wrapper XML do ứng dụng định nghĩa.

Ví dụ, nếu unmarshaller trả một object `Countries` chứa field `List<Country>`, không nên mặc định populator sẽ tự lấy field đó rồi lưu từng quốc gia. Phải bảo đảm hình dạng kết quả phù hợp hoặc bổ sung bước đọc/chuyển đổi theo thiết kế.

Mapping XML, validation schema và validation nghiệp vụ cũng là các phần riêng. Có một `Unmarshaller` không tự chứng minh mọi nội dung XML đã được kiểm tra bằng XSD.

Hai cấu hình JSON và XML trong bài là phương án minh họa thay thế. Nếu cùng bật chúng với cùng dữ liệu, cả hai có thể thực hiện lưu; cần chủ động tránh nạp trùng ngoài ý định.

## 7. Vòng đời khởi tạo: lúc nào việc ghi thực sự diễn ra?

### 7.1. Hai giai đoạn khác nhau

Ở cơ chế factory của Commons 3.5, có thể phân biệt:

| Giai đoạn | Việc diễn ra |
| --- | --- |
| Tạo và cấu hình factory bean | Nhận mapper/unmarshaller, resources và application context |
| Khởi tạo sản phẩm factory | Tạo `ResourceReaderRepositoryPopulator` với reader và resources |
| Nhận `ContextRefreshedEvent` của context tương ứng | Tìm repository rồi gọi `populate(...)` |
| Đọc và lưu thành công các resource | Có thể phát `RepositoriesPopulatedEvent` qua publisher đã cấu hình |

Factory kiểm tra application context của event trước khi thực hiện populate. Không nên hiểu một event từ bất kỳ context nào đều là yêu cầu nạp dữ liệu của factory này. Xem [AbstractRepositoryPopulatorFactoryBean](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/repository/init/AbstractRepositoryPopulatorFactoryBean.java).

### 7.2. Trình tự thông thường với event đồng bộ

```text
Bắt đầu refresh ApplicationContext
        |
        v
Đăng ký và tạo các bean cần thiết
        |
        v
Factory nhận resources và reader
        |
        v
Tạo ResourceReaderRepositoryPopulator
        |
        v
ContextRefreshedEvent
        |
        v
Factory xử lý event của context tương ứng
        |
        v
Đọc resource -> tạo domain object -> gọi repository save
        |
        v
RepositoriesPopulatedEvent của lần populate đó
        |
        v
Hoàn tất đường refresh
        |
        v
Trong Spring Boot: ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
```

Sơ đồ mô tả đường event đồng bộ thông thường. Nếu ứng dụng thay event multicaster bằng cơ chế bất đồng bộ, phải kiểm tra lại giả định về việc dữ liệu đã sẵn sàng trước consumer khác.

Trong Boot, các runner được gọi sau khi context đã refresh; `ApplicationReadyEvent` nằm sau runner. Trình tự ứng dụng được mô tả trong [tài liệu SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html).

### 7.3. Những nơi có thể đọc quá sớm

Một bean dùng `@PostConstruct` để kiểm tra quốc gia `VN` có thể chạy trước khi populator nhận event refresh. Vì vậy, phụ thuộc vào repository bean không đồng nghĩa phụ thuộc vào việc seed đã hoàn tất.

Tương tự, một callback khởi tạo singleton trước khi publish refresh event chưa phải tín hiệu dữ liệu seed đã có.

Nếu consumer cần dữ liệu sau populate, chọn một pha tương ứng:

- Một bước chạy sau refresh trong thiết kế đồng bộ.
- Một cơ chế điều phối gắn với lần populate cần thiết.
- Một service khởi tạo có quy trình và trạng thái hoàn tất rõ ràng.

Không suy rằng `@Order` đặt trên một bean bất kỳ tự giải quyết được mọi quan hệ trước/sau giữa tạo bean, event listener và migration.

### 7.4. RepositoriesPopulatedEvent nói lên điều gì?

Event này cho biết một lời gọi populate đã đi đến bước hoàn tất trong luồng thực thi của nó. Nó không tự mang các bảo đảm sau:

- Mọi populator khác trong ứng dụng cũng đã chạy xong.
- Số lượng dữ liệu bắt buộc đã đúng với nghiệp vụ.
- Một transaction bên ngoài đã commit.
- Toàn bộ ứng dụng đã sẵn sàng nhận mọi yêu cầu.

Nếu có nhiều factory, cần xác định event nào liên quan đến consumer nào. Một listener chung không nên coi event đầu tiên là tín hiệu tất cả nguồn dữ liệu đã được nạp.

Ở implementation được mô tả, publisher được factory cung cấp từ context. Nếu tự tạo một populator ngoài cơ chế đó, cần hiểu rằng cấu hình publisher và việc gọi populate là trách nhiệm của người gọi.

## 8. Phối hợp với schema, migration và consumer

### 8.1. Có repository chưa đủ để backend sẵn sàng

Trước khi lưu dữ liệu, các điều kiện persistence cần được đáp ứng:

- Kết nối backend hoạt động.
- Schema, collection hoặc cấu trúc cần thiết tồn tại theo yêu cầu store.
- Migration bắt buộc đã hoàn tất.
- Mapping và metadata repository hợp lệ.
- Quyền ghi của tài khoản ứng dụng phù hợp.

Repository populator không tạo một hệ thống migration cho toàn bộ schema. Với SQL, việc Flyway, Liquibase hoặc cơ chế schema initialization chạy theo thứ tự nào phụ thuộc cấu hình nền tảng.

Nếu một runner tùy chỉnh chỉ tạo bảng sau refresh, populator chạy ở refresh có thể truy cập bảng quá sớm. Cần thiết kế dependency hoặc pha khởi tạo thực tế, không chỉ đổi tên bean.

### 8.2. Một runner có thể dùng để kiểm tra kết quả

Trong ứng dụng Boot với đường event đồng bộ, có thể dùng một bước kiểm tra sau refresh:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@Bean
@Profile("demo")
ApplicationRunner verifyReferenceData(CountryRepository repository) {
    return args -> {
        if (!repository.existsById("VN")) {
            throw new IllegalStateException(
                    "Thiếu quốc gia VN sau bước khởi tạo");
        }
    };
}
```

Bean method này được đặt trong cấu hình của ứng dụng. Nó kiểm tra kết quả, không gọi populate lần nữa.

Nếu lựa chọn một runner để tự điều phối seed thay cho factory lắng nghe refresh, hãy giữ một đường thực thi duy nhất cho tập dữ liệu đó. Đăng ký factory tự động rồi lại gọi populate trong runner có thể gây lưu hai lần.

### 8.3. Không trộn mọi nhiệm vụ vào seed

Có thể phân biệt:

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Dữ liệu demo nhỏ theo profile | Repository populator |
| Đọc dữ liệu tham chiếu đơn giản qua repository | Populator, kèm chính sách chạy lại rõ ràng |
| Thay đổi schema có phiên bản | Công cụ migration phù hợp |
| Khởi tạo có nhiều bước nghiệp vụ và transaction | Service/luồng seed tường minh |
| Nhập khối lượng lớn, cần checkpoint và retry | Quy trình import hoặc batch được thiết kế riêng |

Không có lựa chọn nào được suy ra chỉ từ định dạng JSON hay XML. Quyết định phụ thuộc vòng đời, khối lượng, quan hệ dữ liệu và yêu cầu chạy lại.

## 9. Tính nguyên tử, chạy lại và nhiều instance

### 9.1. Populator không tự bọc cả tập dữ liệu trong một transaction

Implementation `ResourceReaderRepositoryPopulator` đọc từng resource rồi gọi `invokeSave` cho từng object. Trong lớp này không có một transaction chung bao quanh mọi resource và mọi repository. Xem [mã nguồn ResourceReaderRepositoryPopulator](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/repository/init/ResourceReaderRepositoryPopulator.java).

Transaction thực tế phụ thuộc người gọi, repository và store. Vì vậy, khi phần tử sau bị lỗi lưu, phần tử trước có thể đã được commit.

Không nên suy rằng thêm `@Transactional` lên bean method tạo factory sẽ bao phủ các lần ghi phát sinh sau đó khi nhận refresh event. Hai thời điểm thực thi khác nhau.

Nếu cần all-or-nothing, phải thiết kế một ranh giới transaction phù hợp với store và đường gọi thực sự thực hiện ghi.

### 9.2. Phân biệt lỗi đọc và lỗi lưu

Trong reader JSON của ví dụ, một resource mảng được đọc và ánh xạ thành danh sách trước khi populator duyệt lưu từng phần tử.

Do đó, nếu deserialize resource đó thất bại, populator có thể chưa lưu phần tử nào từ chính resource ấy. Tuy nhiên, các resource trước đó có thể đã được xử lý.

Một ví dụ khác: mọi object đều deserialize được, nhưng object thứ hai vi phạm ràng buộc khi lưu. Khi ấy trạng thái dữ liệu phụ thuộc transaction, và việc object đầu đã được ghi là khả năng cần xét đến.

“Ứng dụng khởi động lỗi” không tự đồng nghĩa “backend chưa thay đổi”.

### 9.3. ID cố định giúp nhận diện, chưa bảo đảm idempotent

JSON mẫu dùng khóa `VN` và `JP` để nhận diện dữ liệu ổn định. Điều này hữu ích khi chạy lại, nhưng chưa tự quyết định hành vi lưu:

- Store có thể cập nhật bản ghi đã có.
- Cơ chế phát hiện đối tượng mới có thể dẫn đến nhánh persist khác.
- Constraint hoặc version có thể gây lỗi.
- Một giá trị seed có thể ghi đè dữ liệu người dùng đã sửa.

Populator không tự gọi `existsById` để chỉ chèn khi thiếu. Cũng không tự giữ một lịch sử seed đã chạy theo phiên bản.

Cần chọn chính sách rõ: chỉ chạy trên kho rỗng, chỉ thêm bản ghi thiếu, đồng bộ dữ liệu tham chiếu hay áp dụng seed có phiên bản.

### 9.4. Singleton không có nghĩa chỉ chạy một lần toàn hệ thống

Factory thông thường tạo một sản phẩm singleton trong context. Điều đó không phải cơ chế “đã seed rồi” lưu trong backend.

Một lần khởi động context mới có thể thực hiện nạp lại. Nhiều instance ứng dụng có thể cùng chạy seed với cùng dữ liệu. Kiểm tra context trong listener cũng không tạo distributed lock.

Nếu nhiều instance cùng quản lý dữ liệu tham chiếu chung, cần một cơ chế phối hợp hoặc thao tác ghi có tính lặp phù hợp. Mẫu “kiểm tra chưa có rồi chèn” riêng lẻ cũng cần xét tình huống cạnh tranh và constraint của backend.

## 10. Validation, auditing và khả năng của từng store

Deserialize được một object chỉ chứng minh reader đã ánh xạ được dữ liệu. Nó chưa chứng minh mọi validation hoặc quy tắc trong service/controller của ứng dụng đã chạy.

Các thao tác seed đi thẳng qua repository có thể bỏ qua luồng nghiệp vụ đặt ở service. Module hoặc persistence provider có thể có callback và kiểm tra riêng khi lưu; cần xác định chính xác lớp nào chịu trách nhiệm cho quy tắc cần bảo vệ.

Với auditing, khởi tạo lúc startup thường không có request HTTP cùng người dùng hiện tại. Nếu auditor là bắt buộc, ứng dụng cần một chính sách system auditor hoặc cơ chế thích hợp cho pha này.

Cũng cần kiểm tra:

- ID được gán sẵn có phù hợp với chiến lược định danh không.
- Quan hệ lồng nhau có được persist theo cascade mà module thực sự hỗ trợ không.
- Field ngày giờ được parse theo format nào.
- Version và optimistic locking được xử lý ra sao khi seed chạy lại.
- Domain có nhiều repository/module thì metadata chọn đúng repository không.

Commons cung cấp điều phối dùng chung. Nó không làm mọi store có cùng cơ chế cascade, transaction hoặc upsert.

Với dữ liệu lớn, lưu từng object qua vòng lặp này không tương đương một bulk loader tự tối ưu. Reader JSON còn tạo cây và danh sách object trong bộ nhớ cho resource. Chọn quy trình import phù hợp nếu kích thước dữ liệu vượt mục tiêu seed nhỏ của thiết kế.

## 11. Thực hành quan sát vòng đời và lỗi

Một tập quan sát có ích:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Bật profile demo, resource hợp lệ | Context khởi động và repository đọc được VN, JP |
| Không bật profile demo | Không có lần ghi từ cấu hình demo |
| Resource thiếu | Thất bại rõ tại bước kiểm tra/đọc đã thiết kế |
| JSON sai cú pháp | Lỗi reader; xác định resource nào đã được xử lý trước |
| Thiếu hoặc sai `_class` | Lỗi xác định kiểu trước khi chọn repository lưu |
| Mapper thiếu module ngày giờ | Lỗi deserialize ở kiểu tương ứng, không nhầm thành lỗi repository |
| Type hint trỏ đến kiểu không có repository | Đọc được object chưa đủ để lưu thành công |
| XML thiếu unmarshaller/runtime | Phân biệt lỗi cấu hình bean với lỗi parse XML |
| Ghi một phần tử bị constraint từ chối | Kiểm tra trạng thái thực tế của phần tử/resource trước |
| Khởi động lại cùng backend | Xác minh đúng chính sách chạy lại |
| Hai factory nạp cùng dữ liệu | Nhận diện số lần lưu và ảnh hưởng cập nhật |
| Ứng dụng đã khởi động rồi resource thay đổi | Không tự có cơ chế reload nếu ứng dụng chưa thiết kế thêm |

Nên quan sát log đọc resource, thời điểm event, lần gọi repository và dữ liệu sau cùng. Một event hoàn tất không thay thế việc kiểm tra những khóa nghiệp vụ bắt buộc.

Trong kiểm thử tích hợp, seed chạy trong lúc khởi tạo application context có thể xảy ra trước transaction của từng test method. Không mặc định rằng `@Transactional` trên test method sẽ rollback dữ liệu đã được seed từ startup.

Test có context được cache cũng không đồng nghĩa seed được chạy lại trước từng phương thức. Cần database hoặc namespace dữ liệu riêng cùng chính sách reset phù hợp với mục tiêu kiểm thử.

## 12. Lỗi thường gặp và cách suy luận

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Thiếu class Jackson/OXM | Nhánh tích hợp được dùng nhưng dependency tùy chọn chưa có | Bổ sung đúng dependency theo nền tảng |
| Truyền mapper không đúng kiểu | Trộn Jackson 2 và Jackson 3 | Đối chiếu factory, package mapper và phiên bản Commons |
| Có file JSON nhưng không có dữ liệu | Chưa đăng ký populator, profile tắt hoặc resource không được chọn | Kiểm tra bean, profile và danh sách resource |
| Pattern không có file mà startup vẫn thành công | Mảng resource rỗng chưa bị ứng dụng từ chối | Kiểm tra điều kiện dữ liệu bắt buộc |
| Chạy trong IDE được nhưng trong JAR lỗi resource | Giả định classpath resource là file vật lý hoặc resource chưa được đóng gói | Dùng Resource/stream và kiểm tra artifact |
| Mapper báo field `_class` không biết | Mapper riêng bật kiểm tra field nhưng chưa xử lý type hint | Dùng mapping/mixin phù hợp cho seed |
| Dữ liệu ngày giờ không đọc được | Mapper seed khác mapper ứng dụng hoặc thiếu module | Cấu hình reader với mapper đúng khả năng |
| Consumer ở PostConstruct không thấy dữ liệu | Consumer chạy trước populate tại refresh event | Chọn pha khởi tạo sau dữ liệu hoặc điều phối tường minh |
| Seed chạy trước bước tạo schema tùy chỉnh | Các pha khởi tạo chưa có quan hệ phù hợp | Thiết kế thứ tự theo dependency/vòng đời thực tế |
| Startup thất bại nhưng vẫn còn bản ghi | Không có transaction chung cho toàn seed | Kiểm tra trạng thái và ranh giới ghi |
| Khởi động lại làm ghi đè hoặc tạo trùng | Chưa có chính sách chạy lại | Thiết kế ID, constraint và hành vi seed phù hợp |
| Event hoàn tất đến nhưng dữ liệu mong đợi chưa đủ | Có nhiều populator hoặc resource rỗng, thiếu kiểm tra nghiệp vụ | Theo dõi đúng nguồn và kiểm tra kết quả bắt buộc |

Trước khi bật một cấu hình khởi tạo, hãy xác định reader và dependency, danh sách resource, repository đích, thời điểm ghi, ranh giới transaction và chính sách chạy lại. Những quyết định này giúp repository populator hoạt động đúng trong vòng đời ứng dụng và đúng với khả năng của kho dữ liệu được chọn.
