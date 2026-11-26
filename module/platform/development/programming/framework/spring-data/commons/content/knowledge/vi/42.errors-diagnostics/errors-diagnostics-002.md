# Không xác định được store trong chế độ nhiều mô-đun

## 1. Đọc đúng ý nghĩa của thông báo store assignment

Trong chương **Lỗi và chẩn đoán** của module **SPRING_DATA_COMMONS**, một lỗi thường gặp xuất hiện khi ứng dụng có nhiều module Spring Data nhưng repository không thể hiện đủ rõ nó thuộc công nghệ lưu trữ nào.

Một thông báo điển hình chứa đoạn:

~~~text
Could not safely identify store assignment for repository candidate ...
~~~

Thông báo gắn với việc một module đánh giá một repository candidate. Nó không tự có nghĩa database mất kết nối, query sai cú pháp hoặc mọi repository trong ứng dụng đều không được tạo.

Cần trả lời ba câu hỏi trước khi sửa:

1. Module nào đang phát thông báo?
2. Repository nào đang được đánh giá?
3. Repository đó có được module đúng nhận và tạo bean hay không?

Ví dụ MongoDB không nhận một repository JPA có thể chỉ là hệ quả phạm vi quét quá rộng. Nếu JPA đã tạo đúng bean và ứng dụng hoạt động, không nên thêm annotation MongoDB vào entity JPA chỉ để dòng log biến mất.

Bài dùng **Java 17, Spring Boot 3.5, Spring Data Commons/JPA 3.5 và Spring Data MongoDB 4.5** để minh họa. Cần đối chiếu API và cấu hình tương ứng nếu ứng dụng dùng dòng phiên bản khác.

## 2. Vì sao Spring Data chuyển sang strict configuration?

Khi chỉ có một module repository trong ứng dụng, việc gắn một repository chung vào module đó thường đơn giản.

Khi phát hiện nhiều repository factory trên classpath, Spring Data chuyển sang **strict repository configuration mode**. Mỗi module phải có cơ sở để nhận diện repository phù hợp.

Hai tín hiệu phổ biến là:

- Type hierarchy chứa repository interface đặc thù của module.
- Domain type có annotation mà module nhận diện.

Ví dụ:

| Module | Interface đặc thù trong ví dụ | Annotation domain |
| --- | --- | --- |
| JPA | `JpaRepository` | `jakarta.persistence.Entity` |
| MongoDB | `MongoRepository` | `org.springframework.data.mongodb.core.mapping.Document` |

Cơ chế và các ví dụ nhiều module được mô tả trong [Using Repositories with Multiple Spring Data Modules](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/definition.html#repositories.multiple-modules).

Không nên hiểu đây là một thuật toán chung luôn “chọn interface trước, bỏ qua mọi annotation sau”. Mỗi module đánh giá candidate theo các tín hiệu của nó; metadata mâu thuẫn có thể khiến nhiều module cùng thấy một candidate phù hợp.

### Những thứ không tự chọn store

| Dấu hiệu | Vì sao chưa đủ |
| --- | --- |
| Tên CustomerJpaRepository | Tên tự đặt không thay cho type hierarchy hoặc cấu hình |
| ID là Long | Nhiều store hỗ trợ ID số |
| ID là String | Không chỉ MongoDB mới có ID chuỗi |
| Interface nằm trong folder có chữ mongo | Phải có cấu hình quét package tương ứng |
| Có `@Repository` | Stereotype không phải selector công nghệ lưu trữ |
| Có URL database trong cấu hình | Kết nối và nhận diện repository là hai bước khác nhau |
| Method trả `Page` hoặc projection | Đây là abstraction kết quả, không chỉ định module |
| Gắn `@Transactional` | Metadata giao dịch không chọn repository factory |

Tên package có tác dụng khi được dùng làm phạm vi scanning. Nó không tự mang ý nghĩa routing chỉ vì cách đặt tên.

## 3. Ví dụ mơ hồ: chỉ kế thừa abstraction chung

Giả sử có một domain không có metadata lưu trữ:

~~~java
public class Customer {

    private Long id;
    private String email;
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

`CrudRepository` thuộc Commons và được nhiều module sử dụng. Khi cả JPA và MongoDB cùng tham gia repository configuration, riêng khai báo này chưa nói CustomerRepository cần factory nào.

Thêm một generic base không tự làm thông tin rõ hơn:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ApplicationRepository<T, ID>
        extends CrudRepository<T, ID> {
}
~~~

~~~java
public interface CustomerRepository
        extends ApplicationRepository<Customer, Long> {
}
~~~

Ở concrete repository, type hierarchy vẫn chỉ cho thấy abstraction chung. Nếu domain và cấu hình không bổ sung thông tin cần thiết, candidate vẫn có thể bị bỏ qua trong strict mode.

Không sửa bằng cách chọn ngẫu nhiên `@Entity` hoặc `@Document`. Trước tiên phải xác định dữ liệu đó thực sự thuộc store nào.

## 4. Metadata domain đúng và metadata mâu thuẫn

### 4.1. Annotation có thể cung cấp tín hiệu nhận diện

Nếu Customer là entity JPA, dùng đúng annotation JPA và bảo đảm entity được persistence unit quản lý.

Nếu Customer là MongoDB document, dùng annotation MongoDB tương ứng và mapping phù hợp.

Kiểm tra **đầy đủ package import**, không chỉ tên ngắn:

~~~java
import jakarta.persistence.Entity;
import org.springframework.data.mongodb.core.mapping.Document;
~~~

Một annotation có cùng tên ngắn từ thư viện khác không nhất thiết được module đang dùng nhận diện. Với ví dụ Boot 3/JPA 3.5, không lấy annotation `javax.persistence.Entity` của một nền tảng cũ thay cho `jakarta.persistence.Entity`.

### 4.2. Không gắn cả hai annotation chỉ để dập thông báo

Ví dụ dễ gây mâu thuẫn:

~~~java
@jakarta.persistence.Entity
@org.springframework.data.mongodb.core.mapping.Document
public class Customer {
    // ...
}
~~~

Nếu nhiều scanner cùng nhìn thấy các repository generic của domain này, metadata có thể không còn phân biệt được module duy nhất.

Dùng chung một kiểu cho nhiều công nghệ là một lựa chọn kiến trúc cần cấu hình có chủ đích. Không nên biến nó thành cách chữa lỗi mặc định.

Với phần lớn ví dụ cần ranh giới rõ, tách `JpaCustomer` và `MongoCustomer`, rồi chuyển đổi qua model ứng dụng nếu cần, sẽ làm mapping và chẩn đoán dễ hiểu hơn.

### 4.3. Được nhận diện chưa có nghĩa mapping đã hợp lệ

Một interface kế thừa JpaRepository có thể được nhận là candidate JPA, nhưng sau đó vẫn lỗi vì domain không thuộc persistence unit.

Đây là bước khác với không nhận diện được store:

~~~text
Nhận diện repository thuộc JPA
              |
              v
Tạo factory và kiểm tra metadata entity
              |
              v
Có thể lỗi: domain chưa được JPA quản lý
~~~

Vì vậy, “Not a managed type” không được xử lý bằng cách bỏ qua store assignment rồi thêm qualifier vào điểm inject.

## 5. Phân biệt các giai đoạn và triệu chứng

Một luồng chẩn đoán hữu ích:

~~~text
Classpath có những module repository nào?
                  |
                  v
Module nào đang quét package nào?
                  |
                  v
Candidate có được module đó nhận diện không?
                  |
                  v
Factory có đủ metadata và tài nguyên để tạo proxy không?
                  |
                  v
Bean có được đăng ký đúng tên/type không?
                  |
                  v
Ứng dụng có inject và gọi đúng bean không?
~~~

| Triệu chứng | Giai đoạn cần xem trước |
| --- | --- |
| Không xác định store assignment | Nhận diện candidate trong module đang quét |
| Không có bean repository để inject | Candidate có được quét, nhận và tạo bean không |
| Trùng bean definition | Phạm vi quét chồng nhau hoặc tên bean trùng |
| Có nhiều bean phù hợp dependency | Điểm inject và các implementation đã được đăng ký |
| Not a managed type | Metadata JPA và phạm vi entity scanning |
| Không tìm thấy template hoặc factory nguồn dữ liệu | Tham chiếu tài nguyên của repository factory |
| Query method không hợp lệ | Candidate đã đi xa hơn bước nhận diện, cần xem tạo query |
| Connection timeout | Kết nối backend, sau khi phân biệt với lỗi scanning |

Một dòng thông báo “không nhận candidate” không nhất thiết là exception làm ứng dụng dừng. Cần đọc tiếp kết quả đăng ký của module đúng và exception chain nếu có.

Trong implementation Commons 3.5, logic nhận diện và thông báo candidate bị loại có thể đối chiếu tại [RepositoryConfigurationExtensionSupport](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/repository/config/RepositoryConfigurationExtensionSupport.java).

Nếu bean thiếu, hãy tìm lỗi tạo bean xảy ra trước đó. Exception tại service có thể chỉ là hậu quả của một repository factory đã thất bại.

## 6. Ví dụ cấu hình rõ ràng cho JPA và MongoDB

Các public type đặt trong các file Java riêng. Ví dụ dùng cấu trúc package:

~~~text
example.multistore
    MultiStoreApplication
    config
        JpaStoreConfiguration
        MongoStoreConfiguration
    persistence.jpa
        JpaCustomer
        JpaCustomerRepository
    persistence.mongo
        MongoCustomer
        MongoCustomerRepository
~~~

Ứng dụng cần các dependency JPA, MongoDB, driver và cấu hình kết nối phù hợp. Các cấu hình repository dưới đây không tự tạo database hoặc thay toàn bộ cấu hình kết nối.

### 6.1. Domain và repository JPA

~~~java
package example.multistore.persistence.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_relational")
public class JpaCustomer {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String email;

    protected JpaCustomer() {
    }

    public JpaCustomer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

~~~java
package example.multistore.persistence.jpa;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaCustomerRepository
        extends JpaRepository<JpaCustomer, Long> {

    Optional<JpaCustomer> findByEmail(String email);
}
~~~

### 6.2. Domain và repository MongoDB

~~~java
package example.multistore.persistence.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customer_documents")
public record MongoCustomer(
        @Id String id,
        String email) {
}
~~~

~~~java
package example.multistore.persistence.mongo;

import java.util.Optional;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoCustomerRepository
        extends MongoRepository<MongoCustomer, String> {

    Optional<MongoCustomer> findByEmail(String email);
}
~~~

Hai repository có tên riêng, type hierarchy riêng và domain metadata riêng. Không yêu cầu một interface cùng kế thừa cả JpaRepository và MongoRepository.

### 6.3. Giới hạn phạm vi repository scanning

~~~java
package example.multistore.config;

import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

import example.multistore.persistence.jpa.JpaCustomer;
import example.multistore.persistence.jpa.JpaCustomerRepository;

@Configuration(proxyBeanMethods = false)
@EntityScan(basePackageClasses = JpaCustomer.class)
@EnableJpaRepositories(
        basePackageClasses = JpaCustomerRepository.class)
public class JpaStoreConfiguration {
}
~~~

~~~java
package example.multistore.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

import example.multistore.persistence.mongo.MongoCustomerRepository;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
        basePackageClasses = MongoCustomerRepository.class)
public class MongoStoreConfiguration {
}
~~~

`basePackageClasses` chọn package của class/interface được tham chiếu, không có nghĩa chỉ quét đúng một repository đó. Hãy giữ ranh giới package tương ứng với phạm vi mong muốn.

`@EntityScan` dành cho phần domain JPA trong ví dụ. Nó không thay cho cấu hình quét repository.

Các thuộc tính phạm vi và tài nguyên của hai annotation được mô tả trong [EnableJpaRepositories](https://docs.spring.io/spring-data/jpa/docs/3.5.x/api/org/springframework/data/jpa/repository/config/EnableJpaRepositories.html) và [EnableMongoRepositories](https://docs.spring.io/spring-data/mongodb/docs/4.5.x/api/org/springframework/data/mongodb/repository/config/EnableMongoRepositories.html).

### 6.4. Ứng dụng gốc

~~~java
package example.multistore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiStoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MultiStoreApplication.class,
                args);
    }
}
~~~

Ứng dụng gốc nằm trên các package cấu hình nên chúng được component scanning phát hiện.

Trong dự án đã có cấu hình repository, cần điều chỉnh phạm vi đang dùng. Không cộng thêm nhiều annotation enable cùng quét một vùng rồi kỳ vọng strict mode tự giải quyết việc đăng ký trùng.

## 7. Chọn module khác với chọn nguồn dữ liệu trong module

Khi repository đã thuộc JPA, ứng dụng vẫn có thể có nhiều persistence unit. Khi repository đã thuộc MongoDB, ứng dụng vẫn có thể có nhiều MongoTemplate.

Đây là lớp cấu hình tiếp theo:

~~~text
Repository thuộc module nào?
            |
            v
Factory đó dùng EntityManagerFactory / MongoTemplate nào?
            |
            v
Tài nguyên ấy kết nối đến backend nào?
~~~

### 7.1. Nhiều persistence unit JPA

Một biến thể cấu hình:

~~~java
@EnableJpaRepositories(
        basePackageClasses = JpaCustomerRepository.class,
        entityManagerFactoryRef = "customerEntityManagerFactory",
        transactionManagerRef = "customerTransactionManager")
~~~

Các tên trên phải trỏ đến bean đã được cấu hình tương ứng. Đoạn annotation không tự định nghĩa các bean đó.

Sai `entityManagerFactoryRef` có thể làm repository dùng persistence unit không quản lý JpaCustomer, dù module JPA đã được nhận diện đúng.

### 7.2. Nhiều MongoTemplate

Biến thể tương ứng:

~~~java
@EnableMongoRepositories(
        basePackageClasses = MongoCustomerRepository.class,
        mongoTemplateRef = "customerMongoTemplate")
~~~

Template được tham chiếu phải có mapping, database factory và cấu hình phù hợp với nhóm repository này.

Không dùng qualifier ở service như cách thay thế cho việc chọn template trong cấu hình repository.

### 7.3. Phân biệt với lỗi inject nhiều bean

`@Qualifier` hoặc `@Primary` có thể giúp chọn giữa các bean đã tồn tại cho một dependency. Chúng không làm một repository candidate thiếu metadata tự được nhận diện và tạo bean.

Ví dụ nếu một application port có hai implementation hợp lệ, chọn implementation tại điểm inject là quyết định của ứng dụng. Nếu không có implementation vì repository bị loại lúc scanning, thêm qualifier không tạo ra implementation bị thiếu.

## 8. Dùng @NoRepositoryBean đúng mục đích

`@NoRepositoryBean` loại interface trung gian khỏi việc được tạo thành repository bean. Nó hữu ích khi interface còn các type variable chưa được ràng buộc.

Xem [API NoRepositoryBean](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/NoRepositoryBean.html).

### 8.1. Base chung không phải store selector

~~~java
@NoRepositoryBean
public interface ApplicationRepository<T, ID>
        extends CrudRepository<T, ID> {
}
~~~

Annotation ngăn tạo bean cho ApplicationRepository. Concrete repository kế thừa nó vẫn cần đủ metadata để thuộc module mong muốn.

Không gắn `@NoRepositoryBean` vào repository concrete đang cần inject chỉ để thông báo biến mất. Khi đó có thể đã chủ động loại chính bean ứng dụng cần dùng.

### 8.2. Base riêng cho module giữ tín hiệu trong hierarchy

Ví dụ một lựa chọn thay cho việc concrete repository kế thừa JpaRepository trực tiếp:

~~~java
package example.multistore.persistence.jpa;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface JpaApplicationRepository<T, ID>
        extends JpaRepository<T, ID> {
}
~~~

Concrete repository có thể kế thừa `JpaApplicationRepository<JpaCustomer, Long>`. Type hierarchy vẫn chứa interface đặc thù JPA.

Nếu muốn có abstraction nghiệp vụ dùng chung giữa các store, có thể tách application port khỏi repository interface rồi viết adapter cho từng store. Không nhất thiết buộc mọi persistence repository đi qua cùng một base generic thiếu thông tin.

### 8.3. @RepositoryDefinition cũng cần được phân biệt module

`@RepositoryDefinition` có thể mô tả domain và ID cho một interface không kế thừa Repository theo cách thông thường. Nó không phải annotation chọn riêng JPA hoặc MongoDB.

Khi dùng nhiều module, vẫn phải xem domain metadata, cấu hình và cách module nhận diện candidate đó.

## 9. Module có mặt nhưng không cần repository

Một ứng dụng có thể dùng JPA để lưu nghiệp vụ và Redis chỉ làm cache. Việc có dependency Redis không có nghĩa mọi repository JPA phải trở thành Redis repository.

Nếu log cho thấy một module không cần repository đang quét các candidate của module khác, cần xem lại phạm vi và cơ chế bật repository của module đó.

Với **Spring Boot 3.5**, nếu ứng dụng thực sự không dùng Redis repositories, có thể tắt phần repository auto-configuration bằng:

~~~properties
spring.data.redis.repositories.enabled=false
~~~

Thuộc tính này được liệt kê trong [Common Application Properties của Spring Boot](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).

Nó không mang nghĩa tắt toàn bộ khả năng Redis hoặc sửa mọi cấu hình thủ công. Nếu ứng dụng có `@EnableRedisRepositories` riêng, cần xử lý cấu hình đó theo ý định thực tế.

Không áp dụng thuộc tính của Redis cho module khác theo cách đoán tên. Các module có thể cung cấp thuộc tính và kiểu cấu hình khác nhau.

Nếu module được kéo vào ngoài ý định và hoàn toàn không sử dụng, xem lại dependency thực tế cùng dependency bắc cầu. Nếu module vẫn cần cho template/client, chỉ giới hạn phần repository cần thiết.

### Repository imperative và reactive cũng phải khớp

Dùng MongoRepository và ReactiveMongoRepository là hai lựa chọn hạ tầng khác nhau. Cấu hình enable/scanning cần phù hợp với loại repository mà ứng dụng sử dụng.

Một interface reactive chung của Commons không tự chỉ ra mọi store có hỗ trợ cách thực thi đó. Đừng sửa lỗi nhận diện bằng cách đổi return type tùy tiện rồi để factory không phù hợp xử lý.

## 10. Xác minh sau sửa bằng context có đủ module

### 10.1. Xác minh metadata và bean trước

Sau khi sửa, cần kiểm tra:

- Repository cần dùng có đúng một bean theo type mong muốn.
- Factory tạo repository thuộc module dự định.
- Domain JPA được persistence unit tương ứng quản lý.
- Repository MongoDB dùng template đúng.
- Query thật có thể thực thi trên backend được cấu hình.

Không chỉ nhìn việc thông báo cũ đã biến mất. Nó có thể biến mất vì repository không còn được quét.

Một slice chỉ bật JPA có thể chạy tốt nhưng chưa kiểm chứng tình huống đồng thời có MongoDB. Cần một test context đại diện cho cấu hình nhiều module thực tế.

### 10.2. Kiểm tra factory trong ví dụ dùng mặc định

Ví dụ dưới đây giả định backend test đã sẵn sàng, schema JPA đã tồn tại và fixture không có email dùng để kiểm tra kết quả rỗng.

~~~java
package example.multistore;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.data.jpa.repository.support.JpaRepositoryFactoryBean;
import org.springframework.data.mongodb.repository.support.MongoRepositoryFactoryBean;

import example.multistore.persistence.jpa.JpaCustomerRepository;
import example.multistore.persistence.mongo.MongoCustomerRepository;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = MultiStoreApplication.class)
class StoreBindingTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void repositoriesUseExpectedFactories() {
        assertThat(context.getBeanNamesForType(
                JpaCustomerRepository.class))
                .containsExactly("jpaCustomerRepository");

        assertThat(context.getBeanNamesForType(
                MongoCustomerRepository.class))
                .containsExactly("mongoCustomerRepository");

        assertThat(context.getBean(
                "&jpaCustomerRepository"))
                .isInstanceOf(
                        JpaRepositoryFactoryBean.class);

        assertThat(context.getBean(
                "&mongoCustomerRepository"))
                .isInstanceOf(
                        MongoRepositoryFactoryBean.class);
    }

    @Test
    void queryMethodsCanExecuteInConfiguredStores() {
        String missingEmail =
                "absent-for-binding-test@example.test";

        var jpaRepository = context.getBean(
                JpaCustomerRepository.class);

        var mongoRepository = context.getBean(
                MongoCustomerRepository.class);

        assertThat(jpaRepository.findByEmail(missingEmail))
                .isEmpty();

        assertThat(mongoRepository.findByEmail(missingEmail))
                .isEmpty();
    }
}
~~~

Trong cơ chế FactoryBean của Spring, tên bean thông thường trả sản phẩm; tiền tố `&` truy xuất chính factory. Với cấu hình mặc định của ví dụ, kiểm tra factory giúp tránh suy đoán từ tên class proxy.

Hai factory được mô tả trong [JpaRepositoryFactoryBean](https://docs.spring.io/spring-data/jpa/docs/3.5.x/api/org/springframework/data/jpa/repository/support/JpaRepositoryFactoryBean.html) và [MongoRepositoryFactoryBean](https://docs.spring.io/spring-data/mongodb/docs/4.5.x/api/org/springframework/data/mongodb/repository/support/MongoRepositoryFactoryBean.html).

Nếu dự án chủ ý đổi tên bean hoặc dùng factory tùy chỉnh, điều chỉnh test theo cấu hình đã công bố. Không dùng các tên mặc định trên như quy tắc bắt buộc cho mọi ứng dụng.

### 10.3. Hiểu kết quả test đúng phạm vi

Test factory xác minh việc đăng ký và lựa chọn module. Test query rỗng xác minh một đường query có thể thực thi, không phải toàn bộ hợp đồng nghiệp vụ.

Nếu test query lỗi vì thiếu bảng hoặc backend không sẵn sàng, cần xử lý vấn đề đó riêng. Không quay lại đổi annotation store khi factory đã được chứng minh đúng.

Nếu thay repository bằng mock trong test context, test không còn kiểm chứng factory persistence thật của repository đó. Một test service dùng mock phù hợp cho logic service nhưng không chứng minh store binding.

## 11. Thu thập bằng chứng chẩn đoán vừa đủ

Có thể bật log tập trung cho cấu hình repository:

~~~properties
logging.level.org.springframework.data.repository.config=DEBUG
~~~

Trong ứng dụng Boot, condition evaluation report còn giúp xem repository auto-configuration nào có hoặc không có hiệu lực. Kết hợp nó với cấu hình enable thủ công; không chỉ xem một nguồn riêng lẻ.

Một bản ghi chẩn đoán hữu ích có:

| Thông tin | Mục đích |
| --- | --- |
| Các module repository thực sự có trên runtime classpath | Giải thích vì sao xuất hiện strict mode |
| Tên đầy đủ repository candidate | Tránh nhầm interface cùng tên ở package khác |
| Module phát thông báo | Biết candidate bị module nào từ chối |
| Type hierarchy của repository | Tìm interface đặc thù hoặc base generic |
| Domain type và package annotation | Kiểm tra tín hiệu nhận diện thật |
| Phạm vi quét của từng cấu hình | Phát hiện quét chồng hoặc bỏ sót |
| Kết quả đăng ký bean/factory | Xác minh module đúng đã nhận candidate |
| Exception chain đầu tiên có ý nghĩa | Phân biệt nguyên nhân với lỗi inject theo sau |
| EntityManagerFactory/MongoTemplate được tham chiếu | Phân biệt chọn module với chọn tài nguyên |

Khi chia sẻ chẩn đoán, tên bean, type và package thường có ích hơn việc đưa toàn bộ chuỗi kết nối hoặc dữ liệu nghiệp vụ vào log.

### Các cách sửa thường không đúng nguyên nhân

| Cách làm | Vì sao có thể không giải quyết |
| --- | --- |
| Thêm @Repository vào mọi interface | Không chỉ định module lưu trữ |
| Đổi Long sang String | ID type không phải selector store |
| Thêm @Primary ở service | Không tạo repository bị thiếu |
| Gắn @NoRepositoryBean lên concrete repository | Có thể loại bean cần dùng |
| Gắn cả @Entity và @Document lên domain | Có thể tạo tín hiệu mâu thuẫn |
| Đổi tên folder nhưng giữ scanning cũ | Phạm vi quét thực tế chưa đổi theo ý định |
| Bật bean definition overriding | Có thể che đăng ký trùng hoặc sai factory |
| Tắt log | Chỉ làm mất triệu chứng quan sát được |
| Loại mọi module ngoài JPA | Có thể làm mất khả năng MongoDB/cache thực sự cần |
| Chỉ chạy một test slice | Có thể bỏ qua đúng tình huống nhiều module |

Hai interface có cùng tên ngắn nhưng ở package khác cũng có thể gặp vấn đề tên bean với chiến lược đặt tên đang dùng. Đó là lỗi đăng ký bean cần xem riêng; đổi tên hoặc cấu hình tên phù hợp không thay thế việc xác định store.

## 12. Quy trình xử lý theo thứ tự

1. Xác định ứng dụng thật sự cần những store và loại repository nào.
2. Đọc module phát thông báo cùng tên đầy đủ của candidate.
3. Kiểm tra type hierarchy, domain metadata và import annotation.
4. Kiểm tra phạm vi scanning, generic base và annotation loại trừ.
5. Tách metadata mâu thuẫn hoặc cấu hình ranh giới store rõ ràng.
6. Đối chiếu factory cùng tài nguyên được tham chiếu.
7. Xác minh context nhiều module tạo đủ bean và chạy được query thật.

Nếu chỉ module không liên quan từ chối một candidate đã được module đúng quản lý, hướng sửa thường nằm ở phạm vi quét hoặc việc bật repository không cần thiết.

Nếu không module nào nhận repository cần dùng, bổ sung tín hiệu đúng với công nghệ dự định và kiểm tra cấu hình quét. Nếu nhiều module cùng nhận hoặc cùng đăng ký một candidate, thu hẹp ranh giới và loại metadata/cấu hình chồng lấn.

Repository abstraction dùng chung cho phép ứng dụng làm việc với nhiều store. Khi có nhiều module, chính sự rõ ràng của type, mapping và phạm vi cấu hình giúp các abstraction đó được gắn với đúng implementation.
