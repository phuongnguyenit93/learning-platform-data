# Repository bean không được tạo hoặc bị quét sai package

## 1. “Không inject được repository” có nhiều nguyên nhân

Một service không nhận được repository không có nghĩa lỗi luôn nằm ở annotation `@Repository`. Có thể Spring Data chưa phát hiện interface, cấu hình repository chưa được nạp, factory không xác định được store, hoặc bean đã được đăng ký nhưng thất bại khi tạo query hay khởi tạo mapping.

Trong chương Lỗi và chẩn đoán của Spring Data Commons, mục tiêu là xác định đúng giai đoạn thất bại:

```text
Class có trên runtime classpath
    -> cấu hình repository được nạp
    -> interface được phát hiện trong phạm vi scan
    -> xác định module/factory phù hợp
    -> đăng ký bean definition
    -> tạo repository proxy và các thành phần cần thiết
    -> dependency injection chọn được bean
    -> phương thức thực thi được trên store
```

Các bước có thể được thực hiện sớm hoặc trì hoãn tùy cấu hình. Một bean definition tồn tại chưa chứng minh repository đã khởi tạo hoàn chỉnh, và inject thành công cũng chưa chứng minh kết nối hay mọi query đều đúng.

Spring Data Commons cung cấp mô hình Repository và cơ chế cấu hình dùng chung. Hạ tầng tạo repository, mapping, transaction và truy vấn cụ thể vẫn phụ thuộc module như JPA, MongoDB, JDBC hoặc R2DBC.

## 2. Phân loại triệu chứng trước khi sửa

| Triệu chứng | Ý nghĩa cần kiểm tra | Không nên kết luận ngay |
| --- | --- | --- |
| Không có bean phù hợp với kiểu repository | Interface chưa được đăng ký, sai context hoặc sai kiểu inject | Chắc chắn thiếu `@Repository` |
| `UnsatisfiedDependencyException` tại service | Một dependency không được thỏa mãn; cần đọc tiếp cause | Service là nơi chứa nguyên nhân gốc |
| `BeanCreationException` gắn với repository | Quá trình tạo bean hoặc thành phần liên quan thất bại | Package chắc chắn chưa được quét |
| Lỗi tạo query hoặc đường dẫn thuộc tính | Interface có thể đã được phát hiện nhưng method không hợp lệ | Cần mở rộng scan package |
| Lỗi JPA về entity chưa được quản lý | Entity không thuộc mapping của entity manager factory được chọn hoặc model sai | Repository chưa có bean definition |
| Có nhiều bean cùng phù hợp | Dependency injection không chọn được duy nhất một bean | Không có repository nào được tạo |
| Trùng tên bean khi khởi động | Các cấu hình hoặc interface tạo bean cùng tên | Bật ghi đè bean là cách sửa đủ |

`NoSuchBeanDefinitionException` và `NoUniqueBeanDefinitionException` thể hiện hai tình huống khác nhau. Trường hợp thứ nhất thiếu bean phù hợp; trường hợp thứ hai có quá nhiều ứng viên. Thêm scan khi đã có nhiều bean có thể làm lỗi phức tạp hơn.

Với exception bị bọc nhiều lớp, đọc chuỗi nguyên nhân và tìm điểm đầu tiên giải thích thao tác cụ thể không thực hiện được. Không dừng ở dòng “không tạo được service” nếu cause phía dưới chỉ ra một derived query viết sai.

## 3. Hiểu repository scan khác component scan

### 3.1. Interface repository cần factory, không chỉ một annotation

Spring Data thường phát hiện một interface repository thông qua việc kế thừa `Repository` hoặc các interface phù hợp như `CrudRepository`, `JpaRepository`, `MongoRepository`. Cơ chế khai báo khác như `@RepositoryDefinition` cũng tồn tại, nhưng vẫn cần hạ tầng repository của module.

Thêm `@Repository` vào một interface thông thường không tự tạo implementation cho interface đó. Repository proxy phải được factory tương ứng xây dựng.

Một interface đúng cho JPA có thể là:

```java
interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

Đoạn mã giả định `Customer` là entity JPA hợp lệ, có ID kiểu `Long` và thuộc entity manager factory mà repository sử dụng. Chỉ có interface này trong source code chưa đủ để ứng dụng tạo bean.

### 3.2. Component scan nạp cấu hình và service

Component scan giúp tìm các thành phần như service, controller và class cấu hình. Nếu class chứa `@EnableJpaRepositories` nằm ngoài phạm vi scan và không được import, cấu hình đó sẽ không tham gia context.

Như vậy có hai câu hỏi riêng:

1. Class cấu hình repository có được nạp không?
2. Khi được nạp, class đó cấu hình scan repository ở package nào?

Sửa câu hỏi thứ hai không có tác dụng nếu class cấu hình chưa được nạp.

### 3.3. Entity scan là phạm vi khác

Trong JPA, repository scan và entity scan giải quyết hai việc khác nhau. Repository scan tìm interface để tạo proxy; entity scan hoặc cấu hình persistence unit xác định các class được provider quản lý.

Có thể gặp tình huống repository được phát hiện nhưng entity của nó không thuộc entity manager factory đang dùng. Khi đó cần kiểm tra mapping và cấu hình entity, không chỉ tăng phạm vi repository scan.

Với các module khác, mapping context và metadata được cấu hình theo cơ chế tương ứng. Không áp nguyên annotation hoặc quy tắc entity scanning của JPA lên MongoDB hay R2DBC.

## 4. Package của ứng dụng và phạm vi mặc định

Trong một ứng dụng Spring Boot thông thường, package chứa class ứng dụng chính là một tín hiệu quan trọng cho các phạm vi auto-configuration. Cách bố trí dễ hiểu là đặt class ứng dụng trên các package tính năng:

```text
com.example.learning
    LearningApplication
    customer
        domain
        repository
        service
```

Khi repository và model chuyển sang một package nằm ngoài cây đó, không nên mặc định chúng vẫn được auto-configuration tìm thấy.

Ví dụ:

```text
com.example.learning.LearningApplication
com.example.customer.repository.CustomerRepository
com.example.customer.domain.Customer
```

Ở đây, `com.example.customer` không phải package con của `com.example.learning`.

Một điểm dễ nhầm trong Spring Boot là `scanBasePackages` của `@SpringBootApplication` điều chỉnh component scan. Nó không tự đồng nghĩa với việc đã điều chỉnh repository scan và entity scan theo cùng danh sách. Khi mở rộng ứng dụng sang package khác, cần kiểm tra các cơ chế này riêng.

Cũng không nên mở rộng tất cả tới một package gốc quá rộng như `com.example` chỉ để lỗi biến mất. Phạm vi quá rộng có thể kéo vào repository của module khác, cấu hình không chủ định hoặc các bean trùng tên. Nên xác định package thực sự thuộc cấu hình cần tạo.

## 5. Cấu hình tường minh bằng marker theo kiểu

### 5.1. Ví dụ riêng cho JPA trong Spring Boot

Với bố cục package tách rời ở trên, cấu hình có thể chỉ rõ repository và entity:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(basePackageClasses = CustomerRepository.class)
@EntityScan(basePackageClasses = Customer.class)
class CustomerPersistenceConfiguration {
}
```

Ví dụ lược bỏ import. `@EnableJpaRepositories` thuộc Spring Data JPA; `@EntityScan` là cấu hình hỗ trợ của Spring Boot, cần dùng package import phù hợp với phiên bản ứng dụng.

Class cấu hình này phải được component scan tìm thấy hoặc được import tường minh, chẳng hạn:

```java
@SpringBootApplication
@Import(CustomerPersistenceConfiguration.class)
public class LearningApplication {

    public static void main(String[] args) {
        SpringApplication.run(LearningApplication.class, args);
    }
}
```

Ví dụ giả định ứng dụng đã có cấu hình datasource, JPA provider và hạ tầng cần thiết. `@EnableJpaRepositories` không tự cung cấp mọi bean hạ tầng chỉ từ một interface repository.

`basePackageClasses` lấy package của các kiểu được truyền vào làm phạm vi scan. Có thể dùng repository thật như ví dụ hoặc một marker đặt trong package tương ứng. Cách này giảm lỗi gõ chuỗi package khi refactor.

Nếu marker đặt ở package cha quá rộng hoặc package anh em không chứa repository, kết quả vẫn có thể sai. Marker là cách xác định phạm vi, không phải bảo đảm tự động rằng phạm vi đó đúng.

### 5.2. Kiểm tra model và annotation đúng hệ sinh thái

Ví dụ entity dùng Jakarta Persistence:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    private Long id;

    private String email;

    protected Customer() {
    }
}
```

Annotation ID của JPA khác `org.springframework.data.annotation.Id` thường dùng trong các cơ chế mapping khác. Import một annotation có cùng tên đơn giản không có nghĩa provider sẽ quản lý nó đúng.

Cần dùng annotation tương thích với persistence provider và phiên bản ứng dụng. Nếu entity đã được tìm thấy nhưng mapping không hợp lệ, mở rộng scan không sửa được model.

### 5.3. Tránh thêm cấu hình chồng lấn một cách máy móc

Nếu ứng dụng đã có cấu hình repository tường minh, nên điều chỉnh phạm vi và tham chiếu hạ tầng tại cấu hình đó. Việc thêm một class `@EnableJpaRepositories` mới có package chồng lấn có thể tạo đăng ký trùng.

Cấu hình tường minh cũng có thể làm một phần auto-configuration tương ứng lùi lại theo điều kiện của Spring Boot. Vì vậy, khi chuyển từ tự động sang tường minh, phải xác nhận toàn bộ các repository cần thiết vẫn nằm trong phạm vi được đăng ký, không chỉ repository đang báo lỗi.

## 6. Interface cơ sở, generic và `@NoRepositoryBean`

Một interface dùng làm nền cho nhiều repository không nên bị tạo thành repository cụ thể với generic chưa được chốt:

```java
@NoRepositoryBean
interface JpaBaseRepository<T, ID> extends JpaRepository<T, ID> {
}
```

```java
interface CustomerRepository
        extends JpaBaseRepository<Customer, Long> {
}
```

Trong ví dụ, interface cơ sở không được tạo bean độc lập; interface cụ thể chốt domain type và ID type để factory tạo repository.

Nếu vô tình gắn trực tiếp `@NoRepositoryBean` lên `CustomerRepository`, interface đó có thể bị loại khỏi tập ứng viên cần tạo. Ngược lại, thiếu annotation ở một interface generic cơ sở có thể khiến framework thử xử lý một kiểu chưa đủ metadata.

Không nên xóa `@NoRepositoryBean` khỏi mọi nơi để tăng số bean. Cần xác định interface nào là hợp đồng nền và interface nào thực sự đại diện một repository của ứng dụng.

Nếu interface repository nằm lồng trong một class khác, cũng cần kiểm tra quy tắc phát hiện nested repositories của module. Một số cấu hình có tùy chọn hỗ trợ, nhưng không nên giả định mọi interface lồng đều được quét như interface top-level.

## 7. Nhiều store: cùng CRUD API chưa đủ để chọn factory

Khi có nhiều module repository, Spring Data có thể dùng chế độ cấu hình nghiêm ngặt để xác định repository thuộc store nào. Tín hiệu gồm interface đặc thù module và annotation của domain type.

Một khai báo chỉ dựa trên `CrudRepository` dùng chung có thể chưa đủ nếu model hoặc cấu hình cũng nhập nhằng. Một factory có thể bỏ qua interface mà nó không xác định được thuộc store của mình; hậu quả sau đó là không có bean để inject.

Thiết kế rõ hơn có thể dùng:

```java
interface JpaCustomerRepository
        extends JpaRepository<JpaCustomerRow, Long> {
}

interface MongoCustomerRepository
        extends MongoRepository<MongoCustomerDocument, String> {
}
```

Model JPA và model MongoDB cần mapping phù hợp riêng. Nếu một class được gắn đồng thời annotation của nhiều store, việc phân loại chỉ dựa vào annotation có thể không còn rõ ràng.

### Giới hạn scan và hạ tầng theo từng store

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = JpaCustomerRepository.class,
    entityManagerFactoryRef = "customerEntityManagerFactory",
    transactionManagerRef = "customerJpaTransactionManager"
)
class CustomerJpaConfiguration {
}
```

```java
@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = MongoCustomerRepository.class,
    mongoTemplateRef = "customerMongoTemplate"
)
class CustomerMongoConfiguration {
}
```

Các repository cần nằm trong các package được tổ chức phù hợp, và các bean hạ tầng được tham chiếu phải thực sự tồn tại. Với nhiều persistence unit JPA, entity cần được đăng ký vào đúng entity manager factory, không chỉ xuất hiện trong một entity scan bất kỳ.

Nếu chỉ sửa được việc tạo bean nhưng trỏ vào nhầm database, cấu hình vẫn sai. Bước xác nhận cuối phải gồm thao tác đọc/ghi có thể phân biệt store hoặc datasource đích trong môi trường kiểm thử phù hợp.

`@Primary` và `@Qualifier` giúp chọn giữa các bean đã có theo vai trò tương ứng. Chúng không tự chọn repository factory cho một interface chưa được đăng ký đúng.

## 8. Profile, điều kiện và runtime classpath

### 8.1. Cấu hình có tồn tại nhưng đang không hoạt động

Một class cấu hình có thể bị loại bởi profile hoặc điều kiện cấu hình. Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Profile("customer-persistence")
@EnableJpaRepositories(basePackageClasses = CustomerRepository.class)
class CustomerPersistenceConfiguration {
}
```

Nếu profile không được bật, không thể suy ra repository sẽ được tạo chỉ vì class này có trong source code. Cần xác nhận profile và property thực tế của tiến trình đang lỗi, không chỉ file cấu hình người phát triển đang nhìn.

Auto-configuration cũng có thể bị exclude, thiếu điều kiện hạ tầng hoặc bị tắt bằng property của module. Tên và ý nghĩa property cần theo phiên bản đang sử dụng. Không bật ngẫu nhiên nhiều property mà chưa xác định điều kiện nào đang loại cấu hình.

### 8.2. File nguồn tồn tại không có nghĩa class có trên runtime classpath

Trong dự án nhiều module, repository có thể nằm ở module chưa được thêm vào dependency runtime, hoặc class không xuất hiện trong artifact đang triển khai. IDE nhìn thấy file không chứng minh tiến trình đã tải được kiểu đó.

Cần phân biệt:

- Source package và artifact chứa class.
- Dependency được dùng khi compile với dependency của tiến trình runtime.
- Artifact mới đã được triển khai hay tiến trình vẫn chạy bản cũ.
- Classpath của ứng dụng với classpath riêng của test.

Nếu class không có trong runtime classpath, mở rộng scan package sẽ không tìm được nó. Nếu class có nhưng cấu hình không được nạp, sửa dependency cũng chưa giải quyết toàn bộ vấn đề.

## 9. Repository được phát hiện nhưng khởi tạo thất bại

### 9.1. Derived query sai

Ví dụ domain có field `email`, nhưng repository khai báo:

```java
Optional<Customer> findByEamil(String email);
```

Factory có thể đã phát hiện interface và bắt đầu tạo query. Lỗi đường dẫn thuộc tính như `PropertyReferenceException` hoặc lỗi tạo query bọc bên ngoài không phải bằng chứng package chưa được quét.

Cách xử lý là sửa tên method hoặc biểu thức truy vấn theo model, rồi kiểm chứng repository. Không mở rộng scan để chữa lỗi chính tả.

### 9.2. Model hoặc hạ tầng chưa sẵn sàng

Các trường hợp khác gồm:

- Entity không thuộc persistence unit được repository sử dụng.
- Generic domain type hoặc ID type không đúng.
- Thiếu entity manager factory, template, mapping context hoặc dependency của fragment.
- Fragment implementation không được phát hiện theo cấu hình mong muốn.
- Lỗi converter hoặc metadata làm quá trình khởi tạo thất bại.
- Lỗi kết nối hay cấu hình store tại giai đoạn thực tế có truy cập hạ tầng.

Tùy module và chế độ bootstrap, một số lỗi chỉ xuất hiện khi gọi repository lần đầu. Chuyển sang lazy initialization có thể dời thời điểm lỗi, nhưng không sửa nguyên nhân.

### 9.3. Bean bị nhập nhằng hoặc trùng tên

Hai interface ở hai package khác nhau có thể cùng tạo tên bean mặc định giống nhau. Hai cấu hình scan chồng lấn cũng có thể cố đăng ký cùng repository nhiều lần.

Bật ghi đè bean có thể che việc một định nghĩa thay thế định nghĩa khác, khiến ứng dụng dùng repository ngoài ý định. Cần thu hẹp scan hoặc đặt cấu hình/tên bean rõ ràng theo nhu cầu thực tế.

Nếu inject một interface chung mà nhiều repository hoặc adapter đều triển khai, cần chọn dependency rõ. Không dùng một tên qualifier đoán từ tên class implementation fragment thay cho việc xác định đúng repository bean.

## 10. Chẩn đoán khác biệt giữa ứng dụng và test

| Môi trường | Điều dễ nhầm |
| --- | --- |
| Unit test với Mockito | Không có Spring context để tự tạo repository |
| Test web slice | Repository thường nằm ngoài phạm vi được nạp |
| Test repository slice | Có hỗ trợ module nhưng không tự nạp mọi service/configuration bên ngoài phạm vi |
| Test toàn ứng dụng | Có thể thấy cấu hình, profile và dependency khác test slice |
| Ứng dụng đóng gói | Runtime classpath và property có thể khác IDE |

Với JPA, một test slice như `@DataJpaTest` có thể tạo môi trường kiểm tra repository, nhưng vẫn cần xác định package, model và hạ tầng phù hợp. Với các module khác, dùng test support của module tương ứng.

Nếu đang test controller và repository không được nạp, có thể cung cấp mock dependency theo mục tiêu của test đó. Nhưng một mock không chứng minh ứng dụng thật đã đăng ký repository. Không dùng việc thêm mock vào test cấu hình toàn ứng dụng để che lỗi wiring cần được kiểm tra.

Cũng cần xem test có tìm đúng class cấu hình ứng dụng không. Một class cấu hình thử nghiệm hoặc profile riêng có thể làm context khác với tiến trình đang gặp lỗi.

## 11. Quan sát bằng chứng thay vì sửa thử nhiều annotation

### 11.1. Thu hẹp log vào cấu hình repository

Có thể bật log phù hợp cho package cấu hình repository của Spring Data, ví dụ:

```yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
```

Log hữu ích khi cho thấy module nào đang scan, phạm vi nào được xử lý và ứng viên nào không được nhận diện. Nội dung cụ thể phụ thuộc phiên bản/module; không cần cố định nguyên văn message để chẩn đoán.

Trong Spring Boot, báo cáo điều kiện auto-configuration có thể giúp giải thích cấu hình nào được áp dụng hoặc lùi lại. Nó bổ sung cho repository scan log, không thay thế việc đọc exception của một bean đã khởi tạo thất bại.

Không cần bật toàn bộ query log nếu repository chưa được đăng ký. Bắt đầu ở tầng cấu hình giúp tránh nhiễu và lượng dữ liệu log không cần thiết.

### 11.2. Phân biệt định nghĩa bean và bean hoạt động được

Một kiểm tra context có thể xác nhận số bean theo kiểu:

```java
@SpringBootTest
class CustomerRepositoryWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsExactlyOneCustomerRepository() {
        assertThat(context.getBeansOfType(CustomerRepository.class))
            .hasSize(1);
    }
}
```

Ví dụ dùng JUnit Jupiter và AssertJ, lược bỏ import cùng cấu hình hạ tầng. Nếu context thất bại trước khi test chạy, phải đọc nguyên nhân startup; assertion chưa được thực hiện không phải lỗi test ngẫu nhiên.

Việc tra bean có thể kích hoạt phần khởi tạo còn trì hoãn. Sau khi xác nhận wiring, nên có test gọi một phương thức phù hợp trên store kiểm thử để xác nhận đường thực thi cần thiết. Một assertion số bean không thay thế test mapping hoặc query.

### 11.3. Kiểm tra đúng context

Ứng dụng có thể có nhiều application context hoặc context cha/con. Bean được đăng ký ở một context không mặc nhiên có nghĩa mọi nơi đều nhìn thấy nó theo cùng cách.

Nếu bằng chứng log nói đã tạo repository nhưng nơi inject vẫn báo thiếu, cần đối chiếu context, kiểu inject, generic type và qualifier. Không chỉ đối chiếu tên đơn giản của interface trong log.

## 12. Quy trình xử lý theo thứ tự

### Bước 1: Ghi lại triệu chứng chính xác

Xác định kiểu repository cần inject, bean nào đang phụ thuộc vào nó, context nào lỗi và thời điểm lỗi: startup, lần gọi đầu hay chỉ trong test.

### Bước 2: Đọc chuỗi nguyên nhân

Phân biệt thiếu bean, có nhiều bean và tạo bean thất bại. Nếu cause là query hoặc mapping, xử lý đúng tầng đó trước khi thay đổi scan.

### Bước 3: Xác nhận class và cấu hình thực sự có mặt

Kiểm tra runtime classpath, class cấu hình được nạp, profile, điều kiện và các auto-configuration bị loại trừ liên quan.

### Bước 4: Đối chiếu ba phạm vi

```text
Component/configuration scan
Repository scan
Domain mapping hoặc entity scan của store
```

Chỉ rõ cấu hình nào chịu trách nhiệm cho từng phạm vi và package thực tế nằm ở đâu.

### Bước 5: Xác định factory và hạ tầng

Kiểm tra interface đặc thù module, domain annotation, entity manager factory hoặc template được tham chiếu. Với đa store hoặc đa datasource, dùng dữ liệu kiểm thử phân biệt được đích truy cập.

### Bước 6: Sửa phạm vi nhỏ nhất giải quyết nguyên nhân

Ví dụ import class cấu hình chưa được nạp, đổi marker package, bổ sung entity vào đúng persistence unit hoặc sửa một method query. Tránh đồng thời mở rộng mọi scan và bật ghi đè bean vì sẽ khó biết thay đổi nào cần thiết.

### Bước 7: Xác nhận lại ở hai mức

Xác nhận có đúng bean repository cần dùng, rồi xác nhận một thao tác dữ liệu đại diện. Đồng thời kiểm tra các repository khác không bị mất sau khi thay auto-configuration bằng cấu hình tường minh.

## 13. Tình huống thực hành: chuyển repository sang module dùng chung

Ban đầu `CustomerRepository` nằm dưới package của ứng dụng chính. Sau khi tách module, repository chuyển sang `com.example.customer.repository`, còn entity chuyển sang `com.example.customer.domain`.

Service bắt đầu báo không có bean. Một người thêm `@Repository` lên interface; người khác tăng component scan nhưng sau đó lại gặp lỗi entity chưa được quản lý.

Phân tích hợp lý là:

1. Xác nhận module mới có trong runtime classpath.
2. Xác nhận cấu hình repository đã scan package mới, thay vì chỉ mở component scan.
3. Đưa entity vào mapping của đúng entity manager factory.
4. Giữ phạm vi repository khác đang dùng, tránh thu hẹp ngoài ý muốn khi cấu hình tường minh.
5. Kiểm tra tạo bean và một query đại diện trong môi trường test.

Ở đây có thể tồn tại hai lỗi kế tiếp nhau: ban đầu interface không được phát hiện, sau đó model chưa được quản lý. Việc lỗi thay đổi sau một sửa chữa không nhất thiết chứng minh sửa chữa đó sai; cần xác định giai đoạn mới đã tiến tới đâu.

## 14. Bài tập vận dụng

Một ứng dụng có JPA và MongoDB. Repository dùng `CrudRepository<Customer, Long>`, domain được gắn annotation của cả hai store, class cấu hình nằm ngoài component scan và test hiện tại là web slice. Khi chạy production, service báo thiếu repository; khi thêm scan rộng, ứng dụng lại báo trùng bean.

Hãy đề xuất cách chẩn đoán:

1. Những triệu chứng nào thuộc context test và triệu chứng nào thuộc cấu hình ứng dụng?
2. Class cấu hình nào cần được nạp và mỗi factory nên scan package nào?
3. Làm thế nào xác định rõ model và interface theo store?
4. Vì sao `@Repository`, `@Primary` hoặc bật ghi đè bean chưa đủ để giải quyết toàn bộ vấn đề?
5. Cần bằng chứng nào để xác nhận repository trỏ vào đúng store sau khi khởi tạo thành công?

Một lời giải tốt cần chỉ ra nguyên nhân ở từng giai đoạn, thay vì gom mọi lỗi thành “Spring không scan được”.

## 15. Điểm cần nhớ

Repository bean có thể thiếu vì classpath, cấu hình chưa hoạt động, phạm vi scan, nhận diện store hoặc cách chọn dependency. Một repository đã được phát hiện vẫn có thể thất bại khi tạo query, mapping hoặc hạ tầng.

Chẩn đoán hiệu quả bắt đầu bằng việc phân loại exception, tách component scan khỏi repository scan và domain mapping, rồi xác nhận factory cùng tài nguyên thực tế. Các abstraction chung của Spring Data giúp tổ chức API; cách tạo bean và khả năng thực thi vẫn cần được kiểm tra theo module cùng datastore đang sử dụng.
