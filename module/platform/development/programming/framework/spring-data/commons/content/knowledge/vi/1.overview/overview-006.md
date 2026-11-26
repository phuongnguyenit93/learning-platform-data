# Quan hệ giữa Commons, Spring Framework, Spring Boot và các store module

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích vai trò của Spring Data Commons trong hệ sinh thái Spring, phân biệt phần hạ tầng với phần triển khai dành cho từng kho dữ liệu, và lần theo một lời gọi repository từ ứng dụng đến cơ sở dữ liệu.

Phạm vi của module **SPRING_DATA_COMMONS** là các abstraction dùng chung của Spring Data: repository, CRUD, truy vấn suy ra từ tên phương thức, phân trang, sắp xếp, projection và auditing. Những abstraction này giúp thống nhất cách biểu đạt nhu cầu truy cập dữ liệu. Tuy nhiên, việc thực thi vẫn phụ thuộc vào store module và khả năng của kho dữ liệu cụ thể.

Một câu hỏi xuyên suốt bài học là: khi viết một interface repository và ứng dụng có thể truy vấn dữ liệu, chính xác thành phần nào đã làm từng việc?

## 1. Bốn thành phần, bốn trách nhiệm

Spring Framework, Spring Boot, Spring Data Commons và các store module có quan hệ phối hợp. Chúng không phải bốn tên gọi cho cùng một thư viện.

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Spring Framework | Cung cấp nền tảng cho ứng dụng: IoC container, dependency injection, tài nguyên, sự kiện, hạ tầng transaction và các cơ chế mở rộng | Quản lý service bean, áp dụng transaction interceptor |
| Spring Boot | Hỗ trợ khởi động và cấu hình ứng dụng qua starter, dependency management và auto-configuration | Cấu hình hạ tầng JPA khi dependency, thuộc tính và các điều kiện liên quan phù hợp |
| Spring Data Commons | Cung cấp hợp đồng và hạ tầng dùng chung cho các dự án Spring Data | `Repository`, `CrudRepository`, `Pageable`, metadata repository, hạ tầng tạo repository proxy |
| Store module | Hiện thực hoặc tích hợp các abstraction với công nghệ lưu trữ cụ thể | Spring Data JPA, Spring Data MongoDB, Spring Data JDBC, Spring Data Redis |

Trong ngữ cảnh này, **store** là loại kho dữ liệu hoặc công nghệ truy cập mà một Spring Data module hỗ trợ. Với Spring Data JPA, module tích hợp thông qua JPA; nó còn cần một JPA provider để thực hiện công việc bên dưới.

Ba phân biệt cần nhớ:

- Spring Framework cung cấp nền tảng chạy ứng dụng; Spring Data bổ sung mô hình truy cập dữ liệu.
- Spring Data Commons cung cấp các khái niệm chung; store module biết cách áp dụng chúng cho một công nghệ cụ thể.
- Spring Boot giúp lắp ghép và cấu hình các thành phần; logic truy cập dữ liệu vẫn do các thư viện được cấu hình thực hiện.

Một ứng dụng có thể dùng Spring Data mà không dùng Spring Boot. Ngược lại, ứng dụng dùng Spring Boot không nhất thiết cần Spring Data.

## 2. Nhìn quan hệ qua hai sơ đồ

### 2.1. Quan hệ trách nhiệm

```text
Spring Boot
  └─ Hỗ trợ chọn dependency và tự động cấu hình khi đủ điều kiện
       ├─ Các bean và hạ tầng của Spring Framework
       └─ Store module, ví dụ Spring Data JPA hoặc MongoDB
            ├─ Tái sử dụng abstraction và hạ tầng của Commons
            └─ Tích hợp công nghệ truy cập dữ liệu cụ thể
```

Sơ đồ này mô tả trách nhiệm, không phải một chuỗi dependency duy nhất. Spring Framework cũng được Commons và store module sử dụng trực tiếp. Trong một ứng dụng thực tế, các quan hệ là một đồ thị.

Boot không phải lớp bắt buộc mà mọi lời gọi repository phải đi qua lúc thực thi. Sau khi context đã khởi tạo, service sử dụng repository bean được tạo trong context.

### 2.2. Đường đi của một lời gọi truy cập dữ liệu

```text
Service của ứng dụng
        |
        v
Repository proxy
        |
        +--> Phương thức CRUD --> Triển khai repository của store
        |
        +--> Phương thức truy vấn --> Hạ tầng truy vấn của store
        |
        +--> Phương thức mở rộng --> Fragment do ứng dụng cung cấp
                                           |
                                           v
                        API truy cập dữ liệu tương ứng
                                           |
                                           v
                                  Kho dữ liệu
```

Với JPA, nhánh truy cập có thể đi qua `EntityManager`, JPA provider và JDBC driver. Với MongoDB, nhánh tương ứng đi qua hạ tầng MongoDB và MongoDB driver. Cùng sử dụng repository proxy không làm hai đường thực thi trở thành giống nhau.

## 3. Spring Framework đóng góp điều gì?

### 3.1. Container và dependency injection

Repository muốn được inject vào service phải trở thành một bean trong Spring application context. Spring Framework cung cấp container để quản lý các bean và quan hệ phụ thuộc giữa chúng.

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }
}
```

Đoạn code giả định `CustomerRepository` đã được đăng ký bởi cấu hình repository phù hợp. Constructor injection thuộc cơ chế của Spring Framework; việc tạo implementation cho repository interface cần thêm hạ tầng Spring Data.

Chỉ đánh dấu một interface là thành phần của ứng dụng không đủ để tạo ra một implementation repository hoạt động. Cần có store module, cấu hình repository và hạ tầng truy cập dữ liệu tương ứng.

### 3.2. Transaction và cơ chế áp dụng hành vi

Spring Framework cung cấp abstraction quản lý transaction và các interceptor liên quan. Store module tích hợp với cơ chế đó và có thể thiết lập hành vi mặc định cho các phương thức repository.

Một transaction có hoạt động như mong đợi hay không còn phụ thuộc vào:

- Transaction manager thực tế được cấu hình.
- Công nghệ lưu trữ và driver đang sử dụng.
- Cách gọi phương thức và ranh giới transaction.
- Các điều kiện triển khai, chẳng hạn khả năng transaction của hệ thống lưu trữ.

Không thể nhìn thấy `@Transactional` rồi kết luận mọi store đều có cùng mức cô lập, rollback hay transaction nhiều đối tượng. Annotation biểu đạt yêu cầu; phần hạ tầng và kho dữ liệu quyết định cách đáp ứng.

### 3.3. Spring Framework có thể truy cập dữ liệu mà không cần Spring Data

Spring Framework có những công cụ như `JdbcTemplate` để ứng dụng tự thực hiện truy cập dữ liệu. Spring Data bổ sung một mô hình khác, nổi bật là repository abstraction và các tích hợp theo store.

Vì vậy, “đang dùng Spring để truy cập cơ sở dữ liệu” chưa đủ để kết luận ứng dụng đang dùng Spring Data Commons hoặc repository interface.

## 4. Spring Data Commons nằm ở đâu?

### 4.1. Commons cung cấp ngôn ngữ chung

Các kiểu dữ liệu sau xuất hiện trong nhiều store module:

| Nhóm | Ví dụ | Ý nghĩa chung |
| --- | --- | --- |
| Repository và CRUD | `Repository<T, ID>`, `CrudRepository<T, ID>` | Biểu đạt kiểu thực thể, kiểu định danh và hợp đồng thao tác dữ liệu |
| Phân trang, sắp xếp | `Pageable`, `PageRequest`, `Page<T>`, `Slice<T>`, `Sort` | Mô tả yêu cầu hoặc kết quả phân đoạn và thứ tự |
| Query by Example | `Example<T>`, `ExampleMatcher` | Mô tả đối tượng mẫu và cách so khớp |
| Auditing | `@CreatedDate`, `@LastModifiedDate`, `AuditorAware<T>` | Biểu đạt metadata thời gian và chủ thể thay đổi |
| Metadata và mở rộng repository | `RepositoryMetadata`, `@NoRepositoryBean` | Hỗ trợ nhận diện kiểu, hợp đồng và cấu trúc repository |

Đây là các hợp đồng và thành phần nền tảng. Một kiểu nằm trong Commons không có nghĩa mọi store đều hỗ trợ đầy đủ mọi cách sử dụng kiểu đó.

Chẳng hạn, `ExampleMatcher` có thể mô tả ý định so khớp, nhưng khả năng dịch ý định đó thành truy vấn, những kiểu thuộc tính được hỗ trợ và giới hạn truy vấn thuộc về store module.

### 4.2. Commons còn cung cấp hạ tầng

Commons không chỉ là tập interface. Nó còn cung cấp các thành phần dùng chung để:

- Phân tích thông tin domain type và identifier type của repository.
- Hỗ trợ tạo repository proxy.
- Ghép các phần triển khai repository.
- Phân tích cấu trúc tên phương thức truy vấn và đường dẫn thuộc tính.
- Hỗ trợ projection, mapping metadata và auditing.

Ví dụ, tên phương thức `findByStatusOrderByCreatedAtDesc` có thể được phân tích thành điều kiện trên thuộc tính `status` và yêu cầu sắp xếp theo `createdAt`. Các thành phần phân tích dùng chung giúp store module không phải tự xây lại toàn bộ bước này.

Tuy nhiên, Commons không tự quyết định câu SQL, truy vấn tài liệu hay lệnh truy cập kho dữ liệu cuối cùng. Store module kết hợp kết quả phân tích với mapping và cơ chế truy vấn của nó.

### 4.3. Commons riêng lẻ chưa đủ cho một repository thực tế

Chỉ thêm dependency `spring-data-commons` có thể giúp code biên dịch với các kiểu như `Pageable` hoặc `Repository`. Điều đó chưa tạo ra:

- Kết nối tới cơ sở dữ liệu.
- Mapping dành riêng cho JPA hoặc MongoDB.
- Repository implementation dành cho một store.
- Cấu hình kích hoạt và quét repository tương ứng.

Muốn gọi repository để đọc hoặc ghi dữ liệu, ứng dụng phải có các phần tích hợp phù hợp ở những lớp còn lại.

## 5. Store module biến hợp đồng thành thao tác cụ thể

### 5.1. Ví dụ với Spring Data JPA

Giả sử ứng dụng quản lý khách hàng trong cơ sở dữ liệu quan hệ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    private Long id;

    private String email;
    private String status;

    protected Customer() {
    }

    public Customer(Long id, String email, String status) {
        this.id = id;
        this.email = email;
        this.status = status;
    }
}
```

Repository thuộc nhánh JPA:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

Ở đây có sự phối hợp của nhiều phần:

| Chi tiết trong ví dụ | Thành phần liên quan |
| --- | --- |
| `@Entity`, `jakarta.persistence.Id` | API JPA, không phải annotation của Commons |
| `JpaRepository` | Spring Data JPA, mở rộng mô hình repository dùng chung |
| Domain type `Customer`, ID type `Long` | Metadata được hạ tầng repository sử dụng |
| Phân tích ý nghĩa của `findByEmail` | Hạ tầng truy vấn dùng chung phối hợp với Spring Data JPA |
| Truy vấn dựa trên mapping của JPA | Spring Data JPA và JPA provider |
| Chuyển thao tác tới cơ sở dữ liệu quan hệ | JPA provider và JDBC driver |

Với các phương thức CRUD cơ sở, Spring Data JPA thường dùng implementation `SimpleJpaRepository`. Những phương thức truy vấn do ứng dụng khai báo được xử lý qua cơ chế truy vấn của repository; không nên hình dung rằng mỗi phương thức tự động trở thành một phương thức Java mới trong `SimpleJpaRepository`.

JPA provider, chẳng hạn Hibernate khi được chọn trong ứng dụng, thực hiện các trách nhiệm ORM như quản lý trạng thái entity và sinh SQL theo cách cấu hình. Commons không đảm nhiệm các trách nhiệm đó.

### 5.2. Ví dụ tương ứng với Spring Data MongoDB

Một mô hình lưu trong MongoDB có thể dùng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class CustomerDocument {

    @Id
    private String id;

    private String email;

    public CustomerDocument() {
    }

    public CustomerDocument(String id, String email) {
        this.id = id;
        this.email = email;
    }
}
```

Repository tương ứng:

```java
import java.util.Optional;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerDocumentRepository
        extends MongoRepository<CustomerDocument, String> {

    Optional<CustomerDocument> findByEmail(String email);
}
```

Tên phương thức truy vấn giống ví dụ JPA. Tuy nhiên, Spring Data MongoDB sử dụng mapping tài liệu và cơ chế truy vấn MongoDB. Nó không sử dụng `EntityManager` hoặc tự chuyển mô hình tài liệu thành entity JPA.

Các ví dụ JPA và MongoDB minh họa hai cấu hình riêng. Nếu dùng cả hai trong một ứng dụng, cần cấu hình riêng phạm vi repository và hạ tầng của từng store.

### 5.3. Một API chung không bảo đảm cùng ngữ nghĩa

`save` là ví dụ điển hình. Hợp đồng chung giúp ứng dụng biểu đạt thao tác lưu một đối tượng, nhưng cơ chế thực hiện phụ thuộc store.

Với JPA, thao tác có liên quan đến trạng thái entity, quyết định đối tượng mới hay đã tồn tại và persistence context. Với MongoDB, cơ chế lưu dựa vào mapping tài liệu, định danh và chiến lược phát hiện đối tượng mới của module tương ứng.

Do đó, không suy ra từ tên `save` rằng mọi store đều:

- Thực hiện đúng một lệnh ghi giống nhau.
- Gửi thay đổi xuống kho dữ liệu ngay tại cùng một thời điểm.
- Có chung cơ chế dirty checking.
- Có cùng quy tắc cập nhật từng trường hoặc toàn bộ đối tượng.
- Cung cấp cùng bảo đảm về transaction.

Khi hợp đồng chỉ yêu cầu trả về đối tượng đã lưu, nên sử dụng giá trị trả về thay vì giả định instance đầu vào luôn là instance kết quả.

## 6. Spring Boot tham gia như thế nào?

### 6.1. Starter tập hợp dependency

Một ứng dụng JPA dùng Boot thường khai báo starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đoạn cấu hình này giả định dự án đã dùng Spring Boot parent hoặc nhập dependency management tương ứng, và có cấu hình build ứng dụng Java thông thường. H2 là lựa chọn cơ sở dữ liệu nhúng cho ví dụ; ứng dụng sử dụng hệ quản trị khác cần driver và cấu hình tương ứng.

Starter đưa các dependency liên quan vào classpath theo tập hợp được Boot lựa chọn. Trong một cấu hình JPA thông thường, ứng dụng nhận được Spring Data JPA, Commons và các thành phần hỗ trợ ORM/JDBC thông qua cây dependency.

Starter không phải một implementation repository và không thay thế store module. Artifact `spring-boot-starter-data-jpa` thuộc Spring Boot; artifact `spring-data-jpa` thuộc Spring Data JPA.

### 6.2. Auto-configuration lắp ghép bean theo điều kiện

Boot kiểm tra classpath, các thuộc tính cấu hình và những bean đã tồn tại để quyết định áp dụng auto-configuration nào.

Với một ứng dụng JPA phù hợp, các phần cấu hình có thể phối hợp để chuẩn bị:

1. `DataSource` hoặc sử dụng nguồn dữ liệu đã có.
2. Hạ tầng `EntityManagerFactory`.
3. Transaction manager phù hợp.
4. Cấu hình phát hiện và đăng ký JPA repository.

Auto-configuration không có nghĩa “mọi thứ luôn tự xuất hiện”. Thiếu driver, sai thuộc tính kết nối, repository nằm ngoài phạm vi quét hoặc điều kiện cấu hình không thỏa mãn đều có thể khiến ứng dụng không khởi tạo được phần mong muốn.

Nhiều auto-configuration nhường chỗ khi người dùng khai báo bean phù hợp, nhưng cần xem đúng điều kiện của từng cấu hình. Không nên coi đó là quy tắc chung rằng cứ khai báo một bean bất kỳ thì Boot ngừng toàn bộ cấu hình dữ liệu.

### 6.3. Dependency management giữ các phiên bản tương thích

Spring Data Commons và store module phải tương thích với nhau và với nền tảng Spring đang dùng. Boot dependency management giúp quản lý một tập phiên bản đã được phối hợp.

Nguyên tắc thực hành:

- Khi dùng Boot, ưu tiên các phiên bản được dependency management của Boot chọn.
- Không tự nâng riêng Commons chỉ vì muốn dùng một interface hoặc API mới.
- Nếu phải thay phiên bản, đánh giá cả Spring Data release train, store module, Spring Framework và nền tảng Java liên quan.
- Khi không dùng Boot, có thể dùng Spring Data BOM để quản lý các module Spring Data; vẫn phải bảo đảm tương thích với Spring Framework và các dependency còn lại.

Commons có version mới hơn không đồng nghĩa store module hiện tại có thể sử dụng an toàn với version đó. Mã nguồn có thể biên dịch trong một số tình huống nhưng ứng dụng vẫn gặp lỗi liên kết API lúc chạy.

### 6.4. Không dùng Boot vẫn dùng được Spring Data

Trong cấu hình thủ công, ứng dụng có thể khai báo `@EnableJpaRepositories` hoặc `@EnableMongoRepositories`, đồng thời cung cấp hạ tầng truy cập dữ liệu tương ứng.

Với JPA, việc chỉ thêm `@EnableJpaRepositories` chưa đủ: cần chuẩn bị `EntityManagerFactory`, transaction manager và các dependency/cấu hình liên quan. Boot giảm phần công việc lắp ghép này khi điều kiện phù hợp.

Khả năng hoạt động độc lập với Boot cho thấy repository abstraction thuộc Spring Data. Boot là lớp hỗ trợ cấu hình và trải nghiệm phát triển.

## 7. Lần theo một truy vấn từ đầu đến cuối

Xét lời gọi sau trong ứng dụng JPA đã cấu hình:

```java
customers.findByEmail("mai@example.com");
```

### Giai đoạn khởi tạo

1. Spring application context bắt đầu tạo các bean.
2. Boot, nếu được sử dụng và đủ điều kiện, hỗ trợ cấu hình hạ tầng JPA và đăng ký repository.
3. Hạ tầng Spring Data phát hiện `CustomerRepository`, xác định domain type và kiểu ID.
4. Factory của Spring Data JPA phối hợp hạ tầng Commons để tạo repository proxy và thiết lập cách xử lý các phương thức.
5. Repository bean được inject vào `CustomerService`.

Đây là luồng khái niệm. Thời điểm khởi tạo chi tiết còn tùy cấu hình, bao gồm cách khởi tạo repository và bean trong ứng dụng.

### Giai đoạn thực thi

1. Service gọi `findByEmail` trên repository bean.
2. Proxy điều phối lời gọi đến cơ chế thực thi truy vấn thích hợp.
3. Với một derived query thông thường, hạ tầng phân tích nhận diện thuộc tính `email`; Spring Data JPA gắn yêu cầu đó với mapping và cơ chế truy vấn JPA.
4. JPA provider và JDBC driver thực hiện truy cập cơ sở dữ liệu.
5. Kết quả được chuyển thành kiểu trả về `Optional<Customer>`.

Nếu phương thức sử dụng một truy vấn khai báo hoặc fragment tùy chỉnh, đường điều phối có thể khác. Tên giống derived query không có nghĩa mọi phương thức luôn đi qua cùng một chiến lược.

Kiểu trả về `Optional<Customer>` biểu đạt tối đa một kết quả mong đợi. Nó không tạo ràng buộc duy nhất cho cột email. Nếu nghiệp vụ yêu cầu email duy nhất, cần thiết kế ràng buộc dữ liệu phù hợp; kết quả nhiều bản ghi cho truy vấn đơn có thể gây lỗi.

Ở thời điểm service gọi repository, Boot không phân tích lại tên phương thức để tự sinh truy vấn. Công việc cấu hình và đăng ký do Boot hỗ trợ đã tạo điều kiện cho các thành phần Spring Data vận hành.

## 8. Phần dùng chung và giới hạn theo store

### 8.1. Phân trang và sắp xếp

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable request = PageRequest.of(
        0,
        20,
        Sort.by("email").ascending()
);
```

`request` biểu đạt trang đầu tiên, kích thước 20 và thứ tự tăng dần theo thuộc tính `email`. Nó không chứa câu SQL hoặc một truy vấn MongoDB hoàn chỉnh.

Store module quyết định cách áp dụng yêu cầu đó. Chi phí lấy tổng số phần tử khi dùng `Page`, khả năng hỗ trợ một kiểu sắp xếp và cách ánh xạ tên thuộc tính phụ thuộc module và truy vấn cụ thể.

Một `Pageable` hợp lệ về mặt Java cũng không bảo đảm truy vấn có chỉ mục phù hợp hoặc hiệu năng tốt.

### 8.2. Projection và truy vấn theo ví dụ

Commons cung cấp các thành phần nền cho projection và Query by Example. Mỗi store quyết định mức hỗ trợ, cách đọc thuộc tính và cách thực thi.

Cùng một projection interface không bảo đảm hai store chỉ đọc đúng cùng một tập trường ở mức giao thức. Cùng một `ExampleMatcher` cũng không bảo đảm hỗ trợ mọi phép so khớp trong mọi kho dữ liệu.

Khi chuyển store, cần xem lại truy vấn thực tế và dữ liệu được trả về, ngoài việc kiểm tra code có biên dịch hay không.

### 8.3. Auditing và metadata

Các annotation như `@CreatedDate` biểu đạt metadata auditing dùng chung. Để các giá trị được điền khi lưu, ứng dụng còn cần kích hoạt auditing và tích hợp theo store, chẳng hạn cơ chế callback hoặc listener phù hợp.

Trong JPA, cấu hình auditing có những yêu cầu gắn với entity listener; MongoDB sử dụng tích hợp riêng. Chỉ khai báo annotation hoặc chỉ thêm starter không đủ để kết luận auditing đã hoạt động.

Metadata cũng có nhiều tầng: Commons cung cấp abstraction để mô tả repository và đối tượng; store module bổ sung thông tin như collection, mapping JPA hoặc cách chuyển đổi kiểu dữ liệu. Một abstraction chung không thay thế toàn bộ metadata riêng của công nghệ lưu trữ.

### 8.4. Blocking và reactive

Cách trả về `Mono` hoặc `Flux` thuộc mô hình reactive; một số abstraction reactive được dùng chung trong hệ sinh thái Spring Data. Store module vẫn phải có đường truy cập reactive phù hợp.

Bọc một lời gọi JPA đồng bộ vào `Mono` không tự biến JPA hoặc JDBC driver đang dùng thành cơ chế I/O không chặn. Khả năng reactive phải được xét theo cả repository, store module và driver.

## 9. Khi một ứng dụng có nhiều store module

Giả sử một ứng dụng vừa dùng Spring Data JPA vừa dùng Spring Data MongoDB. Hạ tầng cần xác định repository nào thuộc store nào.

Nếu một interface chỉ mở rộng `CrudRepository`, thông tin đó có thể chưa đủ rõ trong cấu hình nhiều store. Spring Data có cơ chế nhận diện dựa vào các dấu hiệu như repository interface đặc thù và annotation trên domain type; cách tổ chức gói và phạm vi quét vẫn rất quan trọng.

Cách tổ chức dễ kiểm soát:

```text
com.example.customer.jpa
  CustomerEntity
  CustomerJpaRepository

com.example.customer.mongo
  CustomerDocument
  CustomerMongoRepository
```

Sau đó cấu hình rõ:

- Repository JPA thuộc phạm vi quét JPA và gắn với hạ tầng JPA thích hợp.
- Repository MongoDB thuộc phạm vi quét MongoDB và gắn với hạ tầng MongoDB thích hợp.
- Domain type có mapping nhất quán với store mà repository sử dụng.

Tránh gắn đồng thời nhiều annotation định danh store lên cùng một domain type chỉ để tái sử dụng lớp mà chưa thiết kế rõ cách binding repository. Khi có nhiều module, sự nhập nhằng có thể khiến repository không được gán đúng store hoặc không được tạo.

Commons giúp chia sẻ hợp đồng giữa các module, nhưng không tự chọn một cơ sở dữ liệu mặc định cho mọi repository.

## 10. Mở rộng repository đúng tầng trách nhiệm

Ứng dụng có thể đặt hợp đồng dùng chung lên nền Commons:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ApplicationRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

`@NoRepositoryBean` cho biết interface trung gian này không phải ứng viên để tạo repository bean độc lập. Các repository cụ thể kế thừa nó vẫn cần được gắn với store phù hợp.

Interface chung giúp thống nhất hợp đồng của ứng dụng. Nó không tự cung cấp một implementation xuyên store cho các thao tác mới.

Ví dụ, nếu bổ sung phương thức tùy chỉnh `archiveById`, cần thiết kế cách thực hiện: fragment, base implementation theo store hoặc phương pháp truy vấn được hỗ trợ. Chỉ khai báo một phương thức có tên nghiệp vụ không bảo đảm nó được thực thi đúng.

Nếu implementation dùng `EntityManager`, implementation đó thuộc nhánh JPA của thiết kế. Một implementation sử dụng `MongoTemplate` thuộc nhánh MongoDB. Không đưa giả định của một store vào hợp đồng chung rồi mặc nhiên áp dụng cho tất cả store khác.

## 11. Nhận diện lỗi theo thành phần chịu trách nhiệm

| Hiện tượng | Thành phần nên kiểm tra trước | Lý do |
| --- | --- | --- |
| Inject repository thất bại vì thiếu bean | Đăng ký repository, phạm vi quét, điều kiện cấu hình Boot | Interface có thể chưa được hạ tầng repository xử lý |
| Không kết nối được cơ sở dữ liệu | Cấu hình kết nối, driver, hạ tầng của store | Commons không tạo khả năng kết nối độc lập |
| Tên derived query tham chiếu thuộc tính không tồn tại | Chữ ký repository và domain metadata | Phân tích truy vấn cần đường dẫn thuộc tính hợp lệ |
| Mapping entity hoặc document sai | Annotation, converter và mapping của store | Hợp đồng repository không tự sửa mapping |
| Có `@CreatedDate` nhưng không có giá trị khi lưu | Cấu hình auditing và tích hợp theo store | Annotation cần được hạ tầng phù hợp xử lý |
| Lỗi như `NoSuchMethodError` sau khi nâng dependency riêng lẻ | Tính tương thích của tập phiên bản | Commons và store module có thể lệch API |
| Code dùng chung nhưng hành vi transaction khác nhau | Transaction manager và khả năng của kho dữ liệu | Abstraction chung không đồng nhất bảo đảm của các store |

Bảng này giúp chọn điểm bắt đầu điều tra. Nó không thay thế stack trace, thông báo lỗi và kiểm tra cấu hình cụ thể của ứng dụng.

## 12. Tự kiểm tra mức hiểu

**Câu 1: Có thể chỉ thêm Commons rồi khai báo một `CrudRepository` để lưu vào bất kỳ cơ sở dữ liệu nào không?**

Không. Cần store module, dependency truy cập dữ liệu và cấu hình repository tương ứng. Commons cung cấp hợp đồng và hạ tầng dùng chung, không cung cấp mọi bộ máy lưu trữ.

**Câu 2: Nếu không dùng Boot thì repository có còn hoạt động không?**

Có, nếu ứng dụng tự cấu hình đầy đủ Spring context, store module và hạ tầng liên quan. Boot giúp giảm công việc cấu hình.

**Câu 3: Hai repository JPA và MongoDB cùng có `findByEmail` thì có chạy cùng một loại truy vấn không?**

Không. Chúng có thể chia sẻ cách diễn đạt và một phần hạ tầng phân tích, nhưng việc tạo và thực thi truy vấn theo store là khác nhau.

**Câu 4: Khi ứng dụng cần `Pageable`, có nên tự chọn phiên bản Commons mới nhất độc lập với Boot không?**

Không nên mặc định làm vậy. Cần dùng tập dependency tương thích; dependency management của Boot là điểm xuất phát khi ứng dụng dùng Boot.

**Câu 5: Annotation auditing của Commons có đủ để tự ghi thời gian tạo trong mọi store không?**

Không. Cần kích hoạt và cấu hình tích hợp auditing theo store. Đồng thời phải xác minh thao tác ghi thực tế đi qua cơ chế có xử lý auditing.

## 13. Những điểm cần nhớ

Spring Framework là nền tảng quản lý ứng dụng và các cơ chế hạ tầng. Spring Data Commons cung cấp hợp đồng cùng thành phần dùng chung cho truy cập dữ liệu. Store module đưa các hợp đồng đó đến một công nghệ lưu trữ cụ thể. Spring Boot hỗ trợ chọn dependency và lắp ghép cấu hình theo điều kiện.

Khi đọc một API Spring Data, hãy xác định ba điều: API biểu đạt yêu cầu gì, module nào hiện thực yêu cầu đó, và kho dữ liệu cung cấp bảo đảm gì. Cách phân tích này giúp dùng repository, CRUD, derived query, phân trang, projection và auditing đúng phạm vi hỗ trợ, đồng thời mở rộng repository mà không trộn lẫn các giả định giữa những store.

