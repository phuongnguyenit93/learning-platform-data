# Mô hình miền có annotation của nhiều store và sự mơ hồ

## 1. Một lớp có hai annotation không tự tạo ra một chiến lược lưu trữ rõ ràng

Khi ứng dụng dùng đồng thời Spring Data JPA và Spring Data MongoDB, bạn có thể muốn tái sử dụng một lớp Customer cho cả hai:

```java
@jakarta.persistence.Entity
@org.springframework.data.mongodb.core.mapping.Document("customers")
public class Customer {
    // Các thuộc tính chung.
}
```

Java có thể chấp nhận khai báo này. Nhưng từ đó không thể kết luận:

- Mỗi repository tự được gán duy nhất cho một store.
- Lệnh save tự quyết định ghi vào SQL hay MongoDB theo dữ liệu.
- Một lần lưu sẽ đồng bộ cả hai kho.
- Hai hệ thống mapping có cùng cách hiểu về ID, version và quan hệ.
- Transaction sẽ tự bao phủ cả hai công nghệ.

Trong module **SPRING_DATA_COMMONS**, repository là abstraction dùng chung. Khi có nhiều store module, hạ tầng vẫn cần xác định factory nào chịu trách nhiệm cho từng repository cụ thể.

Bài này tập trung vào một nguồn mơ hồ: **domain mang dấu hiệu nhận diện của nhiều store**, đặc biệt khi các phạm vi quét repository chồng lấn.

## 2. Phân biệt bốn quyết định độc lập

| Quyết định | Câu hỏi |
| --- | --- |
| Nhận diện repository | Interface nào là repository cần được xử lý? |
| Gán repository cho module | Factory của JPA hay MongoDB tạo proxy cho interface đó? |
| Mapping domain | Lớp và thuộc tính được ánh xạ ra bảng/document thế nào? |
| Chọn tài nguyên | Repository sử dụng EntityManagerFactory hoặc MongoTemplate nào? |

Một annotation domain có thể tham gia cả mapping và nhận diện store. Tuy nhiên, nó không thay thế toàn bộ bốn quyết định.

Ví dụ, tách được repository JPA khỏi repository MongoDB chưa chứng minh repository JPA đã trỏ đúng EntityManagerFactory khi ứng dụng có nhiều nguồn dữ liệu quan hệ.

Tương tự, một entity được JPA nhận diện hợp lệ không tự làm một CrudRepository chung trở thành ứng viên chỉ dành cho JPA nếu domain đồng thời có dấu hiệu của store khác.

## 3. Vì sao nhiều store cần nhận diện chặt hơn?

### 3.1. Commons cung cấp hợp đồng mà nhiều module cùng hiểu

Một repository có thể khai báo:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {
}
```

CrudRepository thuộc Commons. Bản thân interface cha này không nói dữ liệu phải nằm trong bảng SQL hay collection MongoDB.

Khi nhiều hạ tầng repository theo store cùng tham gia, Spring Data có cơ chế cấu hình repository chặt hơn, thường được gọi là strict repository configuration.

Các module sử dụng những dấu hiệu như:

- Repository kế thừa interface đặc thù của module.
- Domain có annotation mà module dùng để nhận diện.
- Phạm vi quét và các bộ lọc cấu hình đang áp dụng.

Chi tiết nhận diện cần được đọc theo module và phiên bản. Điều quan trọng là không có quy tắc toàn cục rằng “mọi CrudRepository đều thuộc store xuất hiện trước trong dependency”.

### 3.2. Dấu hiệu có thể đúng với nhiều module cùng lúc

Với một Customer vừa có Entity vừa có Document:

```text
CustomerRepository
    |
    +-- CrudRepository<Customer, String>
                    |
                    v
                 Customer
                    |
                    +-- @Entity   → dấu hiệu mà JPA có thể nhận diện
                    |
                    +-- @Document → dấu hiệu mà MongoDB có thể nhận diện
```

Nếu cả hai phép quét đều nhìn thấy CustomerRepository, cùng một ứng viên có thể được nhiều module chấp nhận.

Việc có thêm annotation không làm thông tin luôn rõ hơn. Trong trường hợp này, nó có thể làm nhiều module cùng thấy đủ dấu hiệu để xử lý.

### 3.3. Không có ý nghĩa ưu tiên từ thứ tự annotation

Hai cách viết:

```java
@Entity
@Document("customers")
```

và:

```java
@Document("customers")
@Entity
```

không biểu đạt thứ tự ưu tiên “JPA trước” hoặc “MongoDB trước”.

Tên annotation, vị trí trên lớp và thứ tự dependency không phải một cơ chế chọn store động cho mỗi lời gọi.

## 4. Ví dụ mơ hồ đầy đủ về ý tưởng

### 4.1. Một lớp mang mapping của cả hai store

```java
package example.customer.shared;

@jakarta.persistence.Entity
@jakarta.persistence.Table(name = "customers")
@org.springframework.data.mongodb.core.mapping.Document("customers")
public class Customer {

    @jakarta.persistence.Id
    @org.springframework.data.annotation.Id
    private String id;

    private String email;

    protected Customer() {
    }

    public Customer(String id, String email) {
        this.id = id;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

ID String được ứng dụng cấp trong ví dụ để không trộn thêm câu hỏi về bộ sinh ID. Hai annotation ID có nguồn khác nhau và phục vụ hai hệ thống mapping khác nhau.

Đây là ví dụ cần phân tích rủi ro, không phải cấu trúc khuyến nghị để bắt đầu một ứng dụng nhiều store.

### 4.2. Repository chỉ dựa trên Commons

```java
package example.customer.shared;

import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);
}
```

### 4.3. Hai phép quét cùng nhìn thấy interface

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableJpaRepositories(
        basePackages = "example.customer.shared"
)
@EnableMongoRepositories(
        basePackages = "example.customer.shared"
)
public class MixedRepositoryConfiguration {
}
```

Ví dụ giả định hạ tầng JPA và MongoDB cần thiết đã được chuẩn bị. Nó chỉ làm nổi bật việc hai phép quét cùng có thể xử lý một repository.

Kết quả có thể là xung đột đăng ký bean hoặc lỗi khởi tạo/cấu hình liên quan. Không dựa vào một thông báo hay thứ tự đăng ký cố định cho mọi phiên bản.

Nếu cấu hình cho phép ghi đè bean, việc ứng dụng đi xa hơn trong quá trình khởi động không chứng minh repository đã được gán đúng. Có thể một đăng ký đã che đăng ký còn lại.

## 5. Interface đặc thù giúp nhận diện nhưng không phải bộ loại trừ toàn cục

Một cách cải thiện thông thường là dùng interface của store:

```java
public interface CustomerJpaRepository
        extends org.springframework.data.jpa.repository.JpaRepository<
                Customer, String> {
}
```

```java
public interface CustomerMongoRepository
        extends org.springframework.data.mongodb.repository.MongoRepository<
                Customer, String> {
}
```

Các interface cha thể hiện ý định rõ hơn so với CrudRepository chung. Tuy nhiên, không nên suy rằng chỉ riêng việc mở rộng JpaRepository luôn ngăn module MongoDB nhìn nhận một domain có Document.

### 5.1. Dấu hiệu nhận diện không nhất thiết loại trừ lẫn nhau

Module có thể chấp nhận một ứng viên nhờ interface đặc thù **hoặc** nhờ annotation trên domain.

Nếu hai phép quét vẫn chồng lấn và Customer vẫn có cả hai annotation, dấu hiệu domain có thể tiếp tục khiến một module khác thấy ứng viên phù hợp.

Vì vậy, thiết kế cần phối hợp:

1. Interface thể hiện store.
2. Domain có mapping rõ ràng.
3. Phạm vi quét không chồng lấn ngoài ý muốn.
4. Tài nguyên store được cấu hình đúng.

Không mô tả một trong bốn mục là cách sửa tuyệt đối cho mọi cấu hình.

### 5.2. Tên interface không có cùng ý nghĩa với interface cha

Tên CustomerJpaRepository chỉ là tên Java nếu nó vẫn mở rộng một hợp đồng Commons và không có cấu hình bổ sung.

Tương tự, tên package chứa chữ mongo không tự kích hoạt MongoDB nếu cấu hình quét vẫn phủ toàn bộ ứng dụng theo cách chồng lấn.

Tên giúp người đọc hiểu thiết kế. Cấu hình và metadata được hạ tầng thực sự sử dụng mới quyết định việc đăng ký.

## 6. Phân biệt các annotation có tên gần nhau

| Nội dung | JPA | MongoDB |
| --- | --- | --- |
| Annotation domain tiêu biểu | `jakarta.persistence.Entity` | `org.springframework.data.mongodb.core.mapping.Document` |
| Annotation ID | `jakarta.persistence.Id` | `org.springframework.data.annotation.Id` |
| Mapping vị trí lưu | Bảng và mapping quan hệ theo JPA | Collection và mapping document |
| Hạ tầng truy cập | EntityManager/JPA provider | MongoOperations/MongoDB driver |

Một import nhầm có thể làm domain thiếu mapping mà store mong đợi. Nhưng sửa import ID không tự giải quyết mọi vấn đề gán repository.

Các annotation auditing chung như CreatedDate, LastModifiedDate cũng không phải một cơ chế xác định duy nhất repository thuộc JPA hay MongoDB.

Khi đọc lỗi, dùng tên package đầy đủ để phân biệt. Tên ngắn Id hoặc Document chưa đủ mô tả công nghệ đang được cấu hình.

## 7. Thiết kế dễ kiểm soát: tách domain nghiệp vụ khỏi model lưu trữ

Một hướng rõ ràng là tách ba vai trò:

```text
example.customer.domain
    Customer

example.customer.persistence.jpa
    CustomerEntity
    CustomerJpaRepository

example.customer.persistence.mongo
    CustomerReadDocument
    CustomerReadRepository

example.customer.config
    CustomerRepositoryConfiguration
```

Domain nghiệp vụ không cần mang đồng thời các annotation của nhiều kho. Model JPA và MongoDB có thể cùng biểu đạt một khách hàng nhưng phục vụ cách lưu khác nhau.

| Model | Vai trò trong ví dụ |
| --- | --- |
| Customer | Dữ liệu nghiệp vụ dùng để trao đổi trong ứng dụng |
| CustomerEntity | Trạng thái khách hàng được lưu trong cơ sở dữ liệu quan hệ |
| CustomerReadDocument | Biểu diễn phục vụ đọc hoặc tra cứu trong MongoDB |

Việc tách lớp không nhất thiết buộc dùng kiến trúc phức tạp. Điểm cần giữ là ownership mapping của mỗi lớp rõ ràng.

## 8. Ví dụ model riêng cho từng store

### 8.1. Domain không có annotation lưu trữ

Ví dụ dùng Java 17:

```java
package example.customer.domain;

public record Customer(
        String customerCode,
        String email
) {
}
```

CustomerCode là mã nghiệp vụ ổn định để liên hệ các biểu diễn. Nó không bắt buộc trùng kiểu persistence ID của mọi store.

### 8.2. Entity JPA

```java
package example.customer.persistence.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class CustomerEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
            name = "customer_code",
            nullable = false,
            unique = true
    )
    private String customerCode;

    @Column(nullable = false)
    private String email;

    protected CustomerEntity() {
    }

    public CustomerEntity(
            String customerCode,
            String email
    ) {
        this.customerCode = customerCode;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public String getEmail() {
        return email;
    }
}
```

ID Long do cơ sở dữ liệu quan hệ cấp. CustomerCode có ràng buộc duy nhất theo mapping JPA trong ví dụ; việc tạo schema/ràng buộc thực tế vẫn cần được quản lý theo môi trường.

Entity không có Document nên không công khai dấu hiệu mapping MongoDB trên chính lớp này.

### 8.3. Repository JPA

```java
package example.customer.persistence.jpa;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerJpaRepository
        extends JpaRepository<CustomerEntity, Long> {

    Optional<CustomerEntity> findByCustomerCode(
            String customerCode
    );
}
```

Domain type của repository là CustomerEntity. Không dùng Customer record nghiệp vụ làm entity chỉ vì tên của nó gần với khái niệm cần lưu.

### 8.4. Document MongoDB

```java
package example.customer.persistence.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customer_views")
public class CustomerReadDocument {

    @Id
    private String customerCode;

    private String email;

    public CustomerReadDocument() {
    }

    public CustomerReadDocument(
            String customerCode,
            String email
    ) {
        this.customerCode = customerCode;
        this.email = email;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public String getEmail() {
        return email;
    }
}
```

Trong document này, customerCode là thuộc tính được mapping thành định danh MongoDB. Repository dùng String làm ID.

Tên thuộc tính định danh không bắt buộc phải là id khi có mapping rõ ràng. Vì vậy findById trên repository MongoDB nhận mã như C-001, còn findById của repository JPA nhận persistence ID Long.

### 8.5. Repository MongoDB

```java
package example.customer.persistence.mongo;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerReadRepository
        extends MongoRepository<CustomerReadDocument, String> {
}
```

Hai repository quản lý hai kiểu lưu trữ khác nhau:

```text
CustomerJpaRepository
    └─ CustomerEntity
         └─ bảng customers, ID Long

CustomerReadRepository
    └─ CustomerReadDocument
         └─ collection customer_views, ID String
```

Không còn một lớp phải cùng lúc đáp ứng hai bộ mapping chỉ để biểu đạt cùng một khách hàng.

## 9. Chia phạm vi quét repository

### 9.1. Cấu hình theo package của interface đại diện

```java
package example.customer.config;

import example.customer.persistence.jpa.CustomerJpaRepository;
import example.customer.persistence.mongo.CustomerReadRepository;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableJpaRepositories(
        basePackageClasses = CustomerJpaRepository.class
)
@EnableMongoRepositories(
        basePackageClasses = CustomerReadRepository.class
)
public class CustomerRepositoryConfiguration {
}
```

Cấu hình giả định:

- Class cấu hình được ứng dụng nạp.
- Hạ tầng JPA và MongoDB tương ứng đã có.
- Entity nằm trong phạm vi mapping JPA thích hợp.
- Mỗi nhóm repository nằm trong package riêng như cây thư mục đã nêu.

BasePackageClasses chọn **package của class được truyền vào**, không chỉ đúng một interface. Các package con cũng cần được tổ chức phù hợp với phạm vi quét.

Nếu đặt CustomerJpaRepository và CustomerReadRepository trong cùng package rồi truyền từng interface làm basePackageClasses, hai phạm vi vẫn có thể trùng nhau. Đổi tham số từ chuỗi thành class không tự giải quyết thiết kế package.

### 9.2. Component scan không thay thế repository scan

Cần phân biệt:

| Loại phát hiện | Thành phần được tìm |
| --- | --- |
| Component scan | Configuration, service và các component của ứng dụng |
| Repository scan | Interface repository để đăng ký qua hạ tầng Spring Data |
| Entity/mapping scan | Các kiểu cần được hệ thống mapping nhận diện |

Trong Boot, các cơ chế có mặc định thuận tiện nhưng vẫn khác trách nhiệm. Thay scanBasePackages của SpringBootApplication không nên được hiểu là đã chia repository cho từng store.

Nếu entity nằm ngoài phạm vi mặc định, cần cấu hình việc nhận diện entity phù hợp. Đừng dùng một cấu hình entity scan như cách thay thế cho việc chỉ rõ repository nào thuộc factory nào.

### 9.3. Kiểm tra toàn bộ các phép quét có hiệu lực

Một cấu hình hẹp không bù lại chắc chắn cho một cấu hình rộng khác đang hoạt động.

Khi điều tra, xem:

- Các class cấu hình repository được nạp.
- Profile đang bật.
- Cấu hình import từ module khác.
- Cấu hình test có thể chỉ nạp một phần ứng dụng.
- Những điều kiện auto-configuration thực tế được áp dụng.

Mục tiêu là hiểu tổng thể interface nào được từng factory nhìn thấy, không chỉ sửa một annotation rồi bỏ qua các đường đăng ký còn lại.

## 10. Chọn đúng tài nguyên sau khi đã chọn đúng store

Nếu mỗi store có một bộ hạ tầng theo tên mặc định, cấu hình trước có thể đủ trong môi trường tương ứng.

Nếu ứng dụng có các bean mang tên riêng, có thể thay cấu hình trước bằng dạng tường minh:

```java
@Configuration
@EnableJpaRepositories(
        basePackageClasses = CustomerJpaRepository.class,
        entityManagerFactoryRef = "customerEntityManagerFactory",
        transactionManagerRef = "customerJpaTransactionManager"
)
@EnableMongoRepositories(
        basePackageClasses = CustomerReadRepository.class,
        mongoTemplateRef = "customerReadMongoTemplate"
)
public class CustomerRepositoryConfiguration {
}
```

Giữ các import và package của class cấu hình ở phần trước. Các bean được tham chiếu phải thực sự tồn tại và được cấu hình đúng; annotation này không tự tạo chúng.

Đây là một phiên bản thay thế cấu hình, không phải class trùng tên để nạp thêm bên cạnh bản trước.

Hai mức lựa chọn là:

```text
Repository nào thuộc store nào?
                |
                v
Repository đó dùng bộ tài nguyên nào trong store?
```

Ví dụ, chọn JPA đúng nhưng trỏ sai EntityManagerFactory vẫn có thể gây lỗi managed type hoặc truy cập nhầm cơ sở dữ liệu quan hệ.

## 11. Chuyển đổi dữ liệu qua mã nghiệp vụ ổn định

Với model đã tách, có thể viết mapper tường minh:

```java
import example.customer.domain.Customer;
import example.customer.persistence.jpa.CustomerEntity;
import example.customer.persistence.mongo.CustomerReadDocument;

public final class CustomerMapping {

    private CustomerMapping() {
    }

    public static Customer toDomain(
            CustomerEntity entity
    ) {
        return new Customer(
                entity.getCustomerCode(),
                entity.getEmail()
        );
    }

    public static CustomerReadDocument toReadDocument(
            Customer customer
    ) {
        return new CustomerReadDocument(
                customer.customerCode(),
                customer.email()
        );
    }
}
```

Mapper không tự ghi dữ liệu. Nó chỉ chuyển đổi biểu diễn.

Với khách hàng có mã C-001:

| Biểu diễn | Định danh hoặc khóa dùng để liên hệ |
| --- | --- |
| Entity JPA | ID Long riêng; customerCode bằng C-001 |
| Domain | customerCode bằng C-001 |
| Document MongoDB | ID String từ customerCode bằng C-001 |

Không ép ID kỹ thuật của hai store phải có cùng kiểu nếu nghiệp vụ không yêu cầu. Mã ổn định giúp ứng dụng liên hệ hai biểu diễn mà không gắn mọi mapping vào một class.

Khi cập nhật entity JPA hiện có, cần giữ persistence ID và trạng thái/version theo thiết kế. Không dựng lại entity mới từ domain rồi mặc định save sẽ tự tìm đúng bản ghi bằng customerCode.

## 12. Tách model không tự đồng bộ hai kho

Giả sử JPA là nguồn dữ liệu chính, MongoDB là model đọc. Đây là một quyết định kiến trúc, không phải hệ quả tự động của annotation.

Cần xác định:

- Thao tác nào ghi vào nguồn chính.
- Khi nào model đọc được cập nhật.
- Cách xử lý cập nhật model đọc thất bại.
- Cách chống lặp và xử lý thứ tự thay đổi nếu cập nhật qua sự kiện.
- Cách đối soát hoặc xây lại model đọc khi cần.

Có thể chọn cơ chế đồng bộ phù hợp, chẳng hạn một quy trình cập nhật có kiểm soát hoặc outbox/sự kiện. Việc lựa chọn và triển khai nằm ngoài cơ chế nhận diện repository.

Một lần gọi CustomerJpaRepository.save không tự gọi CustomerReadRepository.save. Một annotation Transactional cũng không tự biến transaction JPA thành transaction nguyên tử bao phủ MongoDB.

Phân biệt rõ **gán repository đúng store** với **đồng bộ dữ liệu giữa các store** giúp tránh giải quyết một vấn đề bằng cấu hình dành cho vấn đề khác.

## 13. Nếu chủ ý giữ một lớp cho nhiều store

Không phải mọi thiết kế nhiều annotation đều bị Java cấm. Tuy nhiên, dùng chung một persistence class là một lựa chọn phải kiểm soát rõ, không phải cách mặc định để giảm số lớp.

Ít nhất cần làm rõ:

| Vấn đề | Câu hỏi phải trả lời |
| --- | --- |
| Binding repository | Factory nào nhìn thấy từng interface, có phép quét chồng lấn không? |
| ID | Hai store có cùng cách cấp và biểu diễn ID không? |
| Version | Kiểm soát đồng thời của từng store sử dụng annotation và trạng thái nào? |
| Quan hệ | Association JPA được biểu diễn thành document theo cách nào? |
| Trường không lưu | Trường bị bỏ qua ở store này có bị bỏ qua ở store kia không? |
| Constructor và chuyển đổi | Hai hệ thống mapping có tạo và đọc object đúng không? |
| Callback và auditing | Mỗi đường ghi kích hoạt cơ chế nào? |
| Đồng bộ | Ai chịu trách nhiệm ghi vào từng kho và xử lý lỗi? |

Ngay cả khi tách phạm vi quét đủ để gán repository rõ ràng, các khác biệt mapping vẫn còn.

Ví dụ, annotation Transient của một hệ thống không nên được mặc định có cùng tác dụng ở hệ thống khác. Một quan hệ lazy của JPA cũng không tự có cùng ý nghĩa khi được chuyển thành document.

Nếu các yêu cầu bắt đầu kéo model theo hai hướng khác nhau, tách persistence class thường giúp ownership rõ hơn. Domain hoặc DTO dùng chung vẫn có thể giữ phần biểu đạt nghiệp vụ không phụ thuộc store.

## 14. Những cách sửa nhìn có vẻ hợp lý nhưng chưa giải quyết binding

| Cách thay đổi | Vì sao chưa đủ |
| --- | --- |
| Đổi thứ tự Entity và Document | Thứ tự annotation không biểu đạt ưu tiên store |
| Đổi tên thành JpaCustomerRepository | Tên Java không thay thế metadata và phạm vi quét |
| Chỉ thay interface cha nhưng giữ domain hai annotation, scan chồng lấn | Một module khác vẫn có thể nhận diện qua domain |
| Thêm Primary | Chủ yếu ảnh hưởng chọn bean khi inject, không quyết định factory sở hữu repository |
| Thêm Qualifier ở service | Không ngăn repository bị đăng ký sai hoặc trùng từ trước |
| Bật ghi đè bean | Có thể che xung đột thay vì làm ownership rõ |
| Đặt NoRepositoryBean lên concrete repository | Có thể làm mất bean cần dùng; không chọn một store thay cho store khác |
| Chỉ sửa import Id | Có thể sửa mapping nhưng không tự chia phạm vi repository |
| Chỉ chỉnh component scan | Repository scanning và entity mapping có trách nhiệm riêng |
| Thêm Transactional | Không giải quyết nhận diện module hoặc đồng bộ hai kho |

Những annotation trên có công dụng riêng trong bối cảnh phù hợp. Vấn đề là không dùng chúng thay cho quyết định gán repository.

Nếu ứng dụng thực tế chỉ cần một store, loại bỏ hoặc không kích hoạt phần hạ tầng không dùng có thể làm phạm vi đơn giản hơn. Nếu thực sự cần cả hai, phải giữ cấu hình nhiều store có chủ đích.

## 15. Chẩn đoán theo chuỗi: interface → domain → scanner → factory → tài nguyên

### 15.1. Xác định đúng interface đang gặp vấn đề

Ghi lại:

- Tên đầy đủ của repository.
- Các interface cha, kể cả base generic trung gian.
- Domain type và ID type đã đóng.
- Những query method được kế thừa.
- Annotation loại khỏi phát hiện nếu có.

Một base có NoRepositoryBean không chọn store cho repository con. Repository con vẫn cần được nhận diện theo metadata và cấu hình của nó.

### 15.2. Xem toàn bộ mapping của domain

Kiểm tra tên package đầy đủ của các annotation và mapping thực tế có hiệu lực.

Phân biệt:

- Domain có một store annotation hay nhiều store annotation.
- Lớp được chọn có thật sự là entity/document dự kiến.
- Kiểu ID có khớp hợp đồng repository.
- Annotation mới thêm có ảnh hưởng nhận diện module khác hay không.

Không chỉ xem tên lớp là CustomerEntity rồi kết luận chắc chắn nó không có Document.

### 15.3. Liệt kê scanner nào nhìn thấy interface

Đối chiếu từng EnableJpaRepositories, EnableMongoRepositories và các cấu hình có hiệu lực.

Với basePackageClasses, lấy package của class chỉ mốc rồi kiểm tra phạm vi đó. Với chuỗi basePackages, kiểm tra cả các package con.

Nếu sử dụng bộ lọc include/exclude, phải xem điều kiện thực sự áp dụng. Không giả định một bộ lọc theo tên hoặc annotation của ứng dụng tự tương đương với quy tắc strict mặc định.

### 15.4. Xác định factory thực tế được đăng ký

Xem log khởi tạo, thông tin đăng ký bean và loại FactoryBean khi cần.

Các dấu hiệu có thể khác nhau:

| Dấu hiệu | Điều cần nghĩ tới |
| --- | --- |
| Không có bean repository | Bị loại khỏi phạm vi, không nhận diện được store hoặc khởi tạo thất bại |
| Trùng tên/định nghĩa bean | Nhiều đường đăng ký cùng nhìn thấy ứng viên hoặc xung đột tên khác |
| Log không xác định an toàn store | Thiếu dấu hiệu nhận diện đủ rõ trong cấu hình cụ thể |
| Context chạy nhưng hành vi không đúng | Cần xác minh factory và tài nguyên, không chỉ trạng thái khởi động |
| Managed type hoặc mapping lỗi | Domain đã đi vào một đường xử lý không phù hợp hoặc mapping chưa đủ |

Domain hai annotation có thể khiến nhiều module cùng nhận diện được, nên không bắt buộc xuất hiện thông báo “không xác định được store”. Vắng thông báo đó cũng không chứng minh mọi binding đã đúng.

### 15.5. Kiểm tra tài nguyên sau cùng

Khi đã biết repository thuộc JPA, xác định EntityManagerFactory và transaction manager mà nó dùng.

Khi đã biết repository thuộc MongoDB, xác định MongoTemplate và database tương ứng.

Một lỗi kết nối hoặc mapping không nên bị gán ngay cho strict configuration nếu factory và phạm vi đã đúng. Chuỗi kiểm tra giúp phân biệt các tầng nguyên nhân.

## 16. Kiểm tra tích hợp phải nạp được cả hai phía

### 16.1. Test một store riêng có thể bỏ sót vấn đề

Một test slice chỉ nạp JPA có thể chạy tốt vì hạ tầng MongoDB không tham gia. Một test MongoDB riêng cũng có thể chạy tốt theo cách tương tự.

Điều đó chưa chứng minh ứng dụng khi nạp cả hai sẽ gán repository đúng.

Cần một cấu hình test tích hợp có cả hai hạ tầng và phạm vi quét tương ứng với ứng dụng cần kiểm tra.

### 16.2. Các quan sát hữu ích

Trong môi trường thử riêng, không có cơ chế đồng bộ tự động ngoài ý muốn:

1. Context khởi tạo được với hai store.
2. CustomerJpaRepository được tạo qua hạ tầng JPA.
3. CustomerReadRepository được tạo qua hạ tầng MongoDB.
4. Ghi một CustomerEntity rồi đọc lại từ cơ sở dữ liệu quan hệ.
5. Xác nhận thao tác đó không tự tạo document nếu chưa thực hiện quy trình cập nhật model đọc.
6. Ghi một CustomerReadDocument và xác nhận dữ liệu xuất hiện đúng collection.
7. Kiểm tra mã khách hàng liên hệ được hai biểu diễn khi chủ động cập nhật model đọc.

Có thể kiểm tra factory đăng ký hoặc quan sát thao tác thực tế qua công cụ truy cập của từng store. Không chỉ kiểm tra service được inject thành công.

Mỗi thao tác xác minh cần tính đến transaction và thời điểm commit. Đọc từ một context khác trước commit có thể chưa thấy dữ liệu dù repository đã gán đúng.

### 16.3. Không dùng việc cho phép ghi đè làm tiêu chí thành công

Một test chỉ chứng minh “không còn lỗi trùng bean” là chưa đủ nếu cách đạt được là cho phép một đăng ký che đăng ký khác.

Tiêu chí cần là repository được gán cho đúng module, đúng tài nguyên và truy cập đúng dữ liệu.

## 17. Bài thực hành theo tình huống

### Tình huống A: thêm Document vào entity đang dùng JPA

Ban đầu Customer chỉ có Entity và một CrudRepository. Sau khi thêm Document, ứng dụng có thêm MongoDB repository infrastructure và bắt đầu gặp xung đột.

**Cần giải thích:** lớp đã cung cấp dấu hiệu nhận diện cho nhiều module. Kiểm tra các phép quét trước khi đổi tên bean hoặc bật ghi đè.

**Hướng thiết kế:** tách entity và document; hoặc nếu có lý do dùng chung lớp, thiết lập phạm vi và cơ chế mapping có chủ đích, rồi xác minh binding thực tế.

### Tình huống B: đã đổi sang JpaRepository nhưng lỗi vẫn còn

Domain vẫn có cả Entity và Document. Hai cấu hình vẫn quét cùng package rộng.

**Cần giải thích:** interface đặc thù không phải một bộ loại trừ toàn cục cho mọi module. Dấu hiệu domain vẫn có thể khiến module khác chấp nhận ứng viên.

**Hướng thiết kế:** đối chiếu cả interface, domain và phạm vi quét; không chỉ dừng ở một dòng extends.

### Tình huống C: dùng basePackageClasses nhưng vẫn chồng lấn

Hai interface chỉ mốc nằm trong cùng package.

**Cần giải thích:** basePackageClasses chọn package, không chọn riêng từng interface được nêu.

**Hướng thiết kế:** đặt repository theo store vào package riêng hoặc thiết kế bộ lọc rõ ràng khi có yêu cầu đặc biệt.

### Tình huống D: tách model xong nhưng dữ liệu không tự xuất hiện ở cả hai kho

Ghi CustomerEntity thành công nhưng MongoDB chưa có CustomerReadDocument.

**Cần giải thích:** cấu hình gán repository không phải cơ chế đồng bộ dữ liệu.

**Hướng thiết kế:** xác định nguồn chính và quy trình cập nhật model đọc với chính sách xử lý lỗi phù hợp.

### Tình huống E: repository đúng store nhưng sai nguồn dữ liệu

CustomerJpaRepository được tạo bởi JPA nhưng tham chiếu EntityManagerFactory không chứa entity hoặc không trỏ cơ sở dữ liệu dự kiến.

**Cần giải thích:** chọn store và chọn tài nguyên là hai mức cấu hình khác nhau.

**Hướng thiết kế:** xác minh entityManagerFactoryRef, transactionManagerRef và mapping của bộ hạ tầng tương ứng.

## 18. Điều cần nhớ

Một domain mang annotation của nhiều store có thể làm nhiều module cùng nhận diện repository là ứng viên của mình. Sự mơ hồ đến từ tổ hợp interface, mapping và phạm vi quét, không chỉ từ tên lớp.

Thiết kế dễ theo dõi là tách model lưu trữ, khai báo repository theo store, chia package quét và chỉ rõ tài nguyên khi cần. Giữ domain hoặc DTO chung ở mức nghiệp vụ, rồi chuyển đổi bằng khóa liên hệ ổn định.

Spring Data Commons giúp tái sử dụng hợp đồng repository, CRUD, truy vấn, phân trang và metadata. Nó không tự quyết định ownership giữa các store và không tự đồng bộ những kho dữ liệu đó chỉ vì các model cùng mô tả một đối tượng nghiệp vụ.

