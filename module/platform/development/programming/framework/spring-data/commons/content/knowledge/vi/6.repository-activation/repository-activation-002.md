# Annotation @Enable...Repositories của từng store module

Một interface repository chưa tự trở thành bean chỉ vì đã được viết trong mã nguồn. Spring cần một cơ chế phát hiện interface, xác định module chịu trách nhiệm, đăng ký bean definition và tạo implementation hoặc proxy thích hợp.

Spring Data Commons cung cấp hạ tầng dùng chung cho quá trình này. Việc kích hoạt repository lại thuộc module tích hợp store, với các annotation như `@EnableJpaRepositories`, `@EnableMongoRepositories` hoặc `@EnableR2dbcRepositories`. Mỗi annotation kết nối việc quét repository với repository factory và hạ tầng dữ liệu của công nghệ tương ứng.

Bài học thuộc chương **Kích hoạt repository**, tập trung vào bốn câu hỏi: cấu hình có được nạp không, quét package nào, module nào quản lý repository và repository sử dụng tài nguyên dữ liệu nào.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của họ annotation `@Enable...Repositories`.
- Chọn annotation theo store và mô hình imperative hoặc reactive.
- Cấu hình phạm vi quét bằng `basePackages` hoặc `basePackageClasses`.
- Phân biệt quét repository với quét component và nhận diện kiểu persistence.
- Gắn repository với đúng bean hạ tầng khi có nhiều nguồn dữ liệu.
- Phối hợp cấu hình tường minh với auto-configuration của Spring Boot.
- Chẩn đoán trường hợp không có bean, trùng bean hoặc tạo repository thất bại.

## 2. Từ interface đến bean repository

Xét một khai báo JPA:

```java
package example.customer.jpa;

import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaCustomerRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

`CustomerEntity` là entity JPA được mapping phù hợp. Interface xác định hợp đồng thao tác và kiểu miền, nhưng chưa tự cung cấp một object để Spring inject vào service.

Một luồng kích hoạt khái quát là:

```text
Nạp lớp cấu hình
    -> xử lý annotation kích hoạt của module
    -> xác định phạm vi và điều kiện quét
    -> nhận diện các interface repository phù hợp
    -> đăng ký bean definition qua hạ tầng module
    -> tạo repository factory với tài nguyên dữ liệu
    -> tạo proxy và các thành phần thực thi
    -> cung cấp bean cho nơi sử dụng
```

Các thành phần phía sau proxy có thể xử lý phương thức CRUD chuẩn, derived query, truy vấn khai báo, fragment hoặc implementation tùy chỉnh. Không phải mọi phương thức đều được thực thi bằng cùng một đường đi.

Thời điểm tạo và kiểm tra một phần hạ tầng có thể phụ thuộc cấu hình bootstrap hoặc lazy initialization. Vì thế, context khởi động thành công chưa luôn chứng minh tất cả truy vấn và kết nối đã được sử dụng thành công.

## 3. Annotation thuộc module nào thì kích hoạt repository của module đó

| Nhu cầu | Annotation thường sử dụng | Module chịu trách nhiệm |
| --- | --- | --- |
| Repository JPA | `@EnableJpaRepositories` | Spring Data JPA |
| Repository MongoDB imperative | `@EnableMongoRepositories` | Spring Data MongoDB |
| Repository MongoDB reactive | `@EnableReactiveMongoRepositories` | Hướng reactive của Spring Data MongoDB |
| Repository JDBC | `@EnableJdbcRepositories` | Spring Data JDBC |
| Repository R2DBC | `@EnableR2dbcRepositories` | Spring Data R2DBC |

Tên gần giống nhau không có nghĩa các annotation là bí danh. Repository JPA cần cơ chế JPA; một annotation MongoDB không tạo implementation JPA chỉ vì interface đó cùng kế thừa abstraction của Commons.

Một số package thường gặp:

```text
org.springframework.data.jpa.repository.config.EnableJpaRepositories
org.springframework.data.mongodb.repository.config.EnableMongoRepositories
org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories
org.springframework.data.jdbc.repository.config.EnableJdbcRepositories
org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories
```

Không có một annotation chung của Commons có thể tự kết nối mọi repository với mọi store mà không cần module và cấu hình tương ứng.

Ngay cả giữa các annotation có cùng tiền tố, danh sách thuộc tính cũng có thể khác nhau. Không chép một thuộc tính cấu hình của JPA sang MongoDB chỉ vì tên annotation có cấu trúc tương tự. Hãy đối chiếu API của module và dòng phiên bản thực tế.

## 4. Điều kiện trước khi bật quét repository

Cần phân biệt ba nhóm điều kiện:

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| Dependency | Có module store và các thư viện tương thích trên classpath không? |
| Cấu hình được nạp | Lớp chứa annotation có thực sự tham gia application context không? |
| Hạ tầng dữ liệu | Bean factory, template, entity manager hoặc connection cần dùng đã được cấu hình chưa? |

### 4.1. Dependency phải phù hợp với repository

Nếu muốn dùng `@EnableJpaRepositories`, dự án phải có Spring Data JPA cùng hạ tầng cần thiết. Chỉ thêm `spring-data-commons` không cung cấp annotation và repository factory của JPA.

Với reactive repository, còn phải chọn module và driver đáp ứng mô hình reactive. Thêm một thư viện kiểu dữ liệu reactive cạnh repository đồng bộ không tự làm hạ tầng truy cập dữ liệu trở thành non-blocking.

### 4.2. Có `@Configuration` trong mã chưa chắc đã được nạp

Một lớp cấu hình chỉ có tác dụng khi được context biết đến, chẳng hạn được component scan tìm thấy, được `@Import` hoặc được đăng ký tường minh khi tạo context.

Ví dụ, nếu cấu hình nằm ngoài phạm vi scan của ứng dụng và không được import, annotation kích hoạt bên trong nó sẽ không được xử lý.

Không nên bắt đầu sửa query hoặc mapping trước khi xác nhận cấu hình kích hoạt đã thực sự được nạp.

### 4.3. Annotation kích hoạt không thay thế cấu hình kết nối

Bật quét repository không tự giải quyết toàn bộ URL, credential, driver, schema hoặc database. Một số ứng dụng Boot có thể được auto-configuration cung cấp các thành phần liên quan, nhưng đó là cơ chế cấu hình bổ sung với điều kiện riêng.

Trong một context tự cấu hình, ứng dụng phải cung cấp hạ tầng dữ liệu cần thiết. Một repository được phát hiện đúng vẫn có thể thất bại lúc tạo bean vì thiếu tài nguyên phía dưới.

## 5. Cấu hình phạm vi quét package

### 5.1. `basePackages`: chỉ định bằng tên package

Ví dụ cấu hình JPA:

```java
package example.configuration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(basePackages = "example.customer.jpa")
public class CustomerJpaRepositoriesConfiguration {
}
```

Phạm vi thường bao gồm package được chỉ định và các package con theo cơ chế scan. Không nên đặt phạm vi quá rộng nếu bên dưới có repository thuộc nhiều store hoặc nhiều nguồn dữ liệu.

Chuỗi package dễ đọc nhưng việc đổi package có thể không cập nhật mọi chuỗi tham chiếu theo cách IDE xử lý tham chiếu kiểu.

### 5.2. `basePackageClasses`: dùng kiểu đại diện

Một lựa chọn khác:

```java
package example.configuration;

import example.customer.jpa.JpaCustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackageClasses = JpaCustomerRepository.class)
public class CustomerJpaRepositoriesConfiguration {
}
```

Kiểu được truyền vào đại diện cho package cần quét. Thuộc tính này không có nghĩa “chỉ tạo duy nhất bean của lớp được ghi ở đây”; các candidate phù hợp khác trong phạm vi package vẫn có thể được nhận diện.

Có thể dùng một marker type rỗng đặt ở package repository để biểu đạt ranh giới package thay vì gắn cấu hình vào một repository cụ thể. Marker này không cần là repository.

### 5.3. Khi không chỉ định package

Với các annotation đang xét, nếu không cung cấp phạm vi tường minh, điểm xuất phát quét thường là package của lớp cấu hình mang annotation. Vì thế, vị trí lớp cấu hình là điều có ảnh hưởng thực tế.

Ví dụ:

```text
example.configuration
    CustomerJpaRepositoriesConfiguration

example.customer.jpa
    JpaCustomerRepository
```

Hai package là các nhánh khác nhau. Nếu cấu hình chỉ quét từ `example.configuration`, không nên mặc định repository ở `example.customer.jpa` sẽ được tìm thấy.

Trong Spring Boot, cơ chế xác định package mặc định cho auto-configuration có quy tắc riêng. Cần phân biệt nó với phạm vi của một annotation kích hoạt do ứng dụng thêm tường minh.

## 6. Kích hoạt repository JPA và kiểm tra hạ tầng liên quan

Cấu hình tối thiểu ở mức kích hoạt repository có thể là:

```java
@Configuration
@EnableJpaRepositories(basePackageClasses = JpaCustomerRepository.class)
class CustomerJpaRepositoriesConfiguration {
}
```

Các kiểu được import như ví dụ ở phần trước. Cấu hình giả định hạ tầng JPA phù hợp đã có, bao gồm entity manager factory, mapping entity và cơ chế giao dịch cần thiết.

Một entity đơn giản để hình dung ranh giới mapping:

```java
package example.customer.jpa;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class CustomerEntity {
    @Id
    private Long id;

    private String email;

    protected CustomerEntity() {
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Ví dụ dùng namespace Jakarta Persistence và phải được đặt trong bộ dependency hỗ trợ namespace đó. Nó chỉ minh họa metadata entity, không cung cấp toàn bộ cấu hình chạy hoặc chiến lược tạo ID.

### 6.1. Repository scan và entity scan là hai việc

`@EnableJpaRepositories` giúp tìm repository. Nó không mặc định làm mọi lớp được tham chiếu trở thành managed entity của mọi `EntityManagerFactory`.

Nếu repository đã được tạo đến bước xử lý domain nhưng entity manager không biết `CustomerEntity`, ứng dụng có thể báo lỗi kiểu không được quản lý. Khi đó phải kiểm tra entity mapping và phạm vi kiểu mà factory đang quản lý.

Trong ứng dụng Boot có thể sử dụng cơ chế entity scanning phù hợp, chẳng hạn `@EntityScan` khi cần điều chỉnh phạm vi. Với factory tự cấu hình, các package hoặc managed type thường được thiết lập ở cấu hình factory tương ứng.

Không dùng việc mở rộng repository scan để thay thế việc sửa entity mapping của đúng factory.

### 6.2. Gắn với factory và transaction manager có tên

Nếu dùng bean có tên riêng:

```java
@Configuration
@EnableJpaRepositories(
        basePackageClasses = JpaCustomerRepository.class,
        entityManagerFactoryRef = "customerEntityManagerFactory",
        transactionManagerRef = "customerTransactionManager")
class CustomerJpaRepositoriesConfiguration {
}
```

Hai tên phải trỏ tới bean có vai trò phù hợp. `entityManagerFactoryRef` không nhận tên `DataSource` như một thay thế cho `EntityManagerFactory`.

Khi dùng cấu hình mặc định, các tên mặc định của module có thể đủ cho một ứng dụng đơn giản. Khi có nhiều factory hoặc transaction manager, tham chiếu tường minh giúp làm rõ repository thuộc tài nguyên nào.

Chỉ đặt `@Primary` lên một datasource không phải cách mô tả đầy đủ quan hệ giữa mọi repository, entity manager factory và transaction manager.

## 7. Kích hoạt repository MongoDB imperative

Giả sử mô hình và repository đặt trong package MongoDB riêng:

```java
package example.customer.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class CustomerDocument {
    @Id
    private String id;

    private String email;

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

```java
package example.customer.mongo;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoCustomerRepository
        extends MongoRepository<CustomerDocument, String> {
}
```

Cấu hình kích hoạt có thể là:

```java
package example.configuration;

import example.customer.mongo.MongoCustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
        basePackageClasses = MongoCustomerRepository.class,
        mongoTemplateRef = "customerMongoTemplate")
public class CustomerMongoRepositoriesConfiguration {
}
```

Ví dụ giả định bean thao tác MongoDB có tên `customerMongoTemplate` đã được cấu hình với client, database và mapping phù hợp.

`mongoTemplateRef` trỏ tới hạ tầng thao tác MongoDB mà repository cần, không phải chỉ là một tên `MongoClient`. Nếu ứng dụng chỉ có template mặc định phù hợp, có thể không cần đặt tham chiếu tên riêng.

Bật repository không tự tạo collection theo mọi chính sách, tạo mọi index hay kích hoạt auditing. Những khả năng đó có cấu hình và đường thực thi riêng.

## 8. MongoDB reactive sử dụng annotation riêng

Repository reactive có thể có dạng:

```java
package example.customer.mongoreactive;

import example.customer.mongo.CustomerDocument;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveCustomerRepository
        extends ReactiveMongoRepository<CustomerDocument, String> {
}
```

Cấu hình tương ứng:

```java
package example.configuration;

import example.customer.mongoreactive.ReactiveCustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories;

@Configuration
@EnableReactiveMongoRepositories(
        basePackageClasses = ReactiveCustomerRepository.class,
        reactiveMongoTemplateRef = "customerReactiveMongoTemplate")
public class CustomerReactiveMongoRepositoriesConfiguration {
}
```

Bean `customerReactiveMongoTemplate` phải cung cấp hạ tầng reactive tương ứng. Một `MongoTemplate` imperative không phải vật thay thế trực tiếp cho reactive template.

Ứng dụng cần các dependency, driver và cấu hình phù hợp với mô hình đó. Không kích hoạt cả imperative và reactive chỉ để “cho chắc”. Nếu có nhu cầu thật sự dùng cả hai, hãy tách phạm vi repository và làm rõ tài nguyên cho từng hướng.

Ví dụ tái sử dụng một kiểu document để minh họa metadata. Trong dự án thực, cần kiểm tra mapping, converter và yêu cầu mô hình của các đường truy cập được lựa chọn.

## 9. Phân biệt những cơ chế thường bị nhầm

| Cơ chế | Mục đích chính | Điều cần phân biệt |
| --- | --- | --- |
| `@ComponentScan` | Phát hiện component và lớp cấu hình theo quy tắc của container | Không tự tổng hợp implementation cho mọi repository interface |
| `@Enable...Repositories` | Kích hoạt phát hiện và tạo repository của module | Không thay thế mọi cấu hình kết nối hoặc mapping |
| Metadata entity/document | Cho module biết cách biểu diễn mô hình persistence | Không tự cung cấp bean repository nếu hạ tầng chưa kích hoạt |
| `@RepositoryDefinition` | Định nghĩa domain và ID cho interface theo cách khai báo được hỗ trợ | Vẫn cần cơ chế phát hiện và tạo repository |
| `@NoRepositoryBean` | Đánh dấu interface trung gian không tạo repository bean trực tiếp | Không tắt repository cụ thể kế thừa nó |
| Annotation bật auditing | Kích hoạt cơ chế metadata auditing theo module | Không phải cơ chế bật repository scan |
| Cấu hình quản lý giao dịch | Điều phối lời gọi trong ranh giới giao dịch phù hợp | Không tự tìm mọi repository interface |

### 9.1. Có cần `@Repository` trên interface không?

Với repository interface được Spring Data nhận diện qua cơ chế repository scan, thường không cần thêm `@Repository` chỉ để tạo proxy.

Ngược lại, thêm `@Repository` lên một interface rồi chỉ bật component scan không thay thế repository factory của store. Container cần cơ chế biết cách tạo implementation cho hợp đồng đó.

### 9.2. Base interface generic phải được phân loại đúng

Ví dụ base dùng chung:

```java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface LookupRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);
}
```

Interface này dùng để kế thừa. Repository cụ thể mới cung cấp domain và ID thực tế. `@NoRepositoryBean` ngăn việc xử lý base như một repository đích cần tạo bean trực tiếp.

Khi có nhiều module store trên classpath, repository cụ thể còn cần các dấu hiệu và cấu hình đủ rõ để module nhận diện đúng. Không phải mọi interface kế thừa abstraction chung đều tự động thuộc module bạn mong muốn.

## 10. Ứng dụng có nhiều store

Khi cả Spring Data JPA và MongoDB xuất hiện, hạ tầng phải xác định repository nào thuộc module nào. Các căn cứ liên quan có thể gồm interface đặc thù được kế thừa, metadata domain và phạm vi cấu hình.

Một cấu trúc rõ ràng:

```text
example.customer.jpa
    CustomerEntity
    JpaCustomerRepository

example.customer.mongo
    CustomerDocument
    MongoCustomerRepository
```

Sau đó mỗi cấu hình trỏ vào đúng package và hạ tầng như các ví dụ riêng ở trên.

Cần tránh:

- Hai annotation quét cùng một package lớn mà không có chủ đích.
- Interface chung không có dấu hiệu rõ để phân loại khi nhiều store cùng tham gia.
- Domain được gắn metadata của nhiều module nhưng không có thiết kế mapping và lựa chọn factory rõ ràng.
- Mặc định repository JPA và MongoDB cùng tên sẽ luôn được phân biệt theo ý định nghiệp vụ.

Tên bean cũng cần được xem xét. Hai repository ở các package khác nhau nhưng có cùng tên đơn giản có thể gặp vấn đề đặt tên theo cấu hình naming đang dùng. Đừng giả định package khác nhau tự giải quyết mọi xung đột tên bean.

Nếu một domain cần nhiều cách lưu trữ, có thể tách mô hình persistence và dùng adapter. Không cần bắt một repository bean duy nhất chịu trách nhiệm cho mọi loại store.

## 11. Nhiều nguồn dữ liệu trong cùng một store

Bài toán không chỉ xuất hiện khi có hai công nghệ. Hai datasource JPA hoặc hai database MongoDB cũng cần ranh giới repository rõ ràng.

Ví dụ một ứng dụng có dữ liệu bán hàng và dữ liệu lưu vết qua JPA:

| Nhóm repository | Package | Entity manager factory | Transaction manager |
| --- | --- | --- | --- |
| Bán hàng | `example.sales.repository` | `salesEntityManagerFactory` | `salesTransactionManager` |
| Lưu vết | `example.audit.repository` | `auditEntityManagerFactory` | `auditTransactionManager` |

Cấu hình bán hàng:

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "example.sales.repository",
        entityManagerFactoryRef = "salesEntityManagerFactory",
        transactionManagerRef = "salesTransactionManager")
class SalesRepositoriesConfiguration {
}
```

Cấu hình lưu vết:

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "example.audit.repository",
        entityManagerFactoryRef = "auditEntityManagerFactory",
        transactionManagerRef = "auditTransactionManager")
class AuditRepositoriesConfiguration {
}
```

Đây là một phương án riêng cho bối cảnh hai nhóm repository. Các factory và transaction manager phải được khai báo đúng với datasource và entity mapping của từng nhóm.

Với MongoDB, ý tưởng tương tự được thể hiện bằng phạm vi repository và template tương ứng. Không copy thuộc tính `entityManagerFactoryRef` sang annotation MongoDB; phải sử dụng thuộc tính mà module MongoDB cung cấp.

`@Qualifier` ở nơi inject có thể chọn giữa các bean phù hợp, nhưng không sửa được một repository vốn đã được tạo với sai factory hoặc template. Quan hệ tài nguyên cần được cấu hình đúng từ bước tạo repository.

Tương tự, hai repository dùng hai transaction manager khác nhau không tự tạo một giao dịch nguyên tử bao trùm cả hai chỉ vì được gọi trong cùng service.

## 12. Phối hợp với auto-configuration của Spring Boot

Spring Boot có thể kích hoạt repository theo dependency, package mặc định và những điều kiện cấu hình tương ứng. Với ứng dụng theo cấu trúc thông thường, không phải lúc nào cũng cần viết thêm annotation `@Enable...Repositories`.

Trước khi thêm cấu hình tường minh, hãy xác định lý do:

- Repository nằm ngoài phạm vi mặc định cần sử dụng.
- Có nhiều nguồn dữ liệu hoặc nhiều template.
- Cần ranh giới package rõ ràng giữa các module.
- Cần tùy chỉnh factory, base class hoặc thuộc tính khác mà module hỗ trợ.

Boot có các điều kiện auto-configuration để phối hợp hoặc lùi lại khi ứng dụng cung cấp cấu hình riêng. Điều kiện cụ thể phụ thuộc module và phiên bản. Không nên suy ra “cứ thêm `@Enable...Repositories` là luôn bị trùng” hoặc “Boot luôn tự xử lý mọi cấu hình chồng nhau”.

Nếu hành vi khác dự kiến, hãy xem báo cáo điều kiện auto-configuration, các lớp cấu hình đã được nạp và nguồn đăng ký bean. Mục tiêu là tìm đúng cấu hình đang chịu trách nhiệm tạo repository.

Không bật cho phép ghi đè bean chỉ để làm mất thông báo xung đột mà chưa xác định nguyên nhân. Một context khởi động được nhờ bean sau ghi đè bean trước có thể vẫn dùng sai tài nguyên dữ liệu.

## 13. Những thuộc tính cấu hình cần đọc theo module

Ngoài phạm vi package và tham chiếu hạ tầng, một annotation kích hoạt có thể cung cấp các tùy chọn như bộ lọc candidate, chiến lược tra cứu truy vấn, repository base class, factory bean class hoặc cách xử lý repository lồng nhau.

Một số khả năng chỉ có ở module nhất định hoặc ở dòng phiên bản nhất định. Ví dụ, khi đọc cấu hình bootstrap của JPA, phải xem thuộc tính và semantics của JPA thay vì mặc định MongoDB có cùng lựa chọn.

Khi tùy chỉnh, nên trả lời:

1. Vấn đề cụ thể nào cần giải quyết?
2. Thuộc tính này thuộc annotation nào, package nào?
3. Module và phiên bản đang dùng có hỗ trợ không?
4. Thay đổi ảnh hưởng phạm vi scan, cách tạo bean hay thời điểm khởi tạo?
5. Có làm repository bị gắn sang hạ tầng khác ngoài dự kiến không?

Chỉ thay đổi tùy chọn khi có nhu cầu. Cấu hình ít nhưng rõ ranh giới thường dễ kiểm tra hơn một danh sách thuộc tính được sao chép từ nhiều ví dụ không cùng bối cảnh.

## 14. Chẩn đoán lỗi theo giai đoạn

| Triệu chứng | Giai đoạn cần xem | Hướng kiểm tra |
| --- | --- | --- |
| Không có bean repository để inject | Cấu hình, scan hoặc nhận diện candidate | Cấu hình có được nạp, package có đúng, interface có bị loại không |
| Thiếu entity manager factory hoặc template | Gắn hạ tầng và tạo bean | Tên tham chiếu, kiểu bean, cấu hình tài nguyên |
| Domain không được quản lý | Mapping của factory | Entity/document và managed type của đúng module |
| Có nhiều bean phù hợp | Đăng ký và injection | Có nhiều repository thật sự hay cùng candidate bị quét chồng |
| Trùng tên bean | Scan và naming | Phạm vi chồng, cấu hình lặp, hai interface trùng tên đơn giản |
| Không xác định được module cho repository | Phân loại trong bối cảnh nhiều store | Interface đặc thù, metadata domain và package |
| Query creation thất bại | Khởi tạo truy vấn | Tên thuộc tính, toán tử, annotation query và kiểu trả về |
| Bean có nhưng thao tác đầu tiên lỗi kết nối | Sử dụng tài nguyên runtime | Client, driver, URL, credential và môi trường store |

### 14.1. Đọc nguyên nhân sâu nhất

Thông báo không inject được service có thể chỉ là hậu quả. Nguyên nhân sâu hơn có thể là repository tạo thất bại, truy vấn sai hoặc entity manager không biết domain.

Ngược lại, nếu repository chưa từng được scan, sửa annotation của một query không giải quyết được việc thiếu bean.

### 14.2. Không dùng số repository được tìm thấy làm bằng chứng duy nhất

Log cho biết đã tìm thấy một số repository là thông tin hữu ích để xác nhận phạm vi scan. Nó chưa chứng minh mọi repository dùng đúng database hoặc thao tác nghiệp vụ chạy được.

Nếu một repository bị trỏ nhầm sang template vẫn có thể tạo được, lỗi về dữ liệu có thể chỉ xuất hiện khi thực hiện truy vấn. Cần kiểm tra cả nguồn hạ tầng thực tế.

## 15. Quy trình kiểm tra một cấu hình kích hoạt

### Bước 1: Xác định một nhóm repository

Ghi store, mô hình imperative/reactive, package và các domain tương ứng. Với nhiều nguồn dữ liệu, ghi thêm tài nguyên đích của nhóm.

### Bước 2: Chọn cơ chế chịu trách nhiệm

Quyết định nhóm này do auto-configuration phù hợp quản lý hay do cấu hình tường minh. Xác định cách lớp cấu hình tham gia context.

### Bước 3: Khoanh phạm vi scan

Ưu tiên package có ranh giới rõ. Dùng `basePackageClasses` nếu muốn tham chiếu kiểu và thuận tiện khi refactor. Đánh dấu đúng base interface không tạo bean trực tiếp.

### Bước 4: Gắn đúng tài nguyên

Với JPA, xác nhận entity manager factory, entity mapping và transaction manager. Với MongoDB, xác nhận template, client/database và mapping. Với các module khác, dùng hạ tầng mà module đó yêu cầu.

### Bước 5: Kiểm tra cả đăng ký lẫn thực thi

Xác nhận bean có thể được tạo và inject. Sau đó thực hiện một thao tác dữ liệu có ý nghĩa cùng một derived query nếu ứng dụng sử dụng. Nếu có nhiều nguồn, dùng dữ liệu phân biệt để phát hiện repository truy cập nhầm nguồn.

### Bước 6: Kiểm tra ranh giới khi cấu hình phức tạp

Đối chiếu các package không chồng ngoài ý muốn, tên bean không mâu thuẫn và service sử dụng đúng transaction manager theo thiết kế. Kiểm tra thêm trường hợp một module hoặc cấu hình không được bật nếu ứng dụng có cơ chế lựa chọn môi trường.

## 16. Tình huống thực hành

Ứng dụng có lớp chính ở `example.application`, repository khách hàng ở `example.customer.jpa` và một lớp cấu hình ở `example.infrastructure`. Nhóm thêm `@EnableJpaRepositories` không có tham số vào lớp cấu hình nhưng vẫn không inject được repository.

Có hai vấn đề độc lập cần kiểm tra:

1. `example.infrastructure` có được component scan hoặc import vào context không?
2. Nếu cấu hình đã được nạp, package mặc định của annotation có bao gồm `example.customer.jpa` không?

Một cách sửa có chủ đích là bảo đảm cấu hình được import và đặt `basePackageClasses = JpaCustomerRepository.class`. Sau đó vẫn phải xác nhận hạ tầng JPA quản lý `CustomerEntity`.

Nếu nhóm tiếp tục thêm MongoDB cho dữ liệu khác, hãy tạo ranh giới package và template riêng. Không mở rộng mọi annotation lên `example` chỉ để tìm được nhiều interface hơn, vì điều đó có thể tạo ra candidate không đúng module hoặc cấu hình quét chồng.

## 17. Câu hỏi tự kiểm tra

### Câu 1

Chỉ thêm `spring-data-commons` có thể dùng `@EnableJpaRepositories` để kết nối database không?

**Gợi ý trả lời:** Không. Cần module JPA cùng hạ tầng dữ liệu phù hợp. Commons cung cấp phần chung, không cung cấp toàn bộ implementation store.

### Câu 2

`basePackageClasses = SomeRepository.class` có nghĩa chỉ quét đúng interface đó không?

**Gợi ý trả lời:** Không. Kiểu được dùng để xác định package cần quét; các candidate phù hợp khác trong phạm vi vẫn có thể được nhận diện.

### Câu 3

Tại sao thêm repository scan chưa chắc sửa được lỗi entity không được quản lý?

**Gợi ý trả lời:** Repository scan và cấu hình managed entity của entity manager factory là hai việc khác nhau. Phải sửa mapping hoặc phạm vi entity ở đúng factory.

### Câu 4

Có thể dùng `mongoTemplateRef` để trỏ trực tiếp tới bean `MongoClient` không?

**Gợi ý trả lời:** Không. Thuộc tính đó cần bean hạ tầng thao tác MongoDB phù hợp, không phải chỉ client kết nối.

### Câu 5

Đổi từ imperative sang reactive MongoDB có chỉ cần giữ `@EnableMongoRepositories` và đổi kiểu trả về không?

**Gợi ý trả lời:** Không. Cần repository reactive, annotation kích hoạt, template, driver và cấu hình tương ứng.

### Câu 6

Vì sao `@Qualifier` ở service không sửa được repository đã gắn nhầm entity manager factory?

**Gợi ý trả lời:** Qualifier chọn bean để inject, trong khi factory đã được chọn ở cấu hình tạo repository. Phải sửa quan hệ tài nguyên tại nơi đăng ký repository.

### Câu 7

Spring Boot đã tạo repository đúng. Có bắt buộc thêm annotation kích hoạt tường minh không?

**Gợi ý trả lời:** Không. Chỉ thêm khi có nhu cầu cấu hình cụ thể và cần kiểm tra cơ chế auto-configuration phối hợp với cấu hình đó theo module đang dùng.