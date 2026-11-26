# Tái sử dụng fragment generic cho nhiều kiểu miền

Trong chương **Repository fragment** của **SPRING_DATA_COMMONS**, bài này trình bày cách đóng gói một khả năng dùng chung thành fragment generic và ghép khả năng đó vào nhiều repository. Mục tiêu là giữ được kiểu miền tại nơi gọi, dùng chung implementation khi hợp lý và xác định rõ phần nào phụ thuộc công nghệ lưu trữ.

Ví dụ xuyên suốt là kiểm tra ràng buộc của `Customer` và `Product` trước một thao tác ghi được ứng dụng lựa chọn. Fragment chỉ kiểm tra đối tượng; service quyết định khi nào gọi kiểm tra và khi nào lưu. Cách phân chia này giúp quan sát riêng hợp đồng generic, quá trình ghép repository và trách nhiệm truy cập dữ liệu.

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng có hai repository:

- `CustomerRepository` quản lý khách hàng.
- `ProductRepository` quản lý sản phẩm.

Cả hai đều cần kiểm tra đối tượng theo cùng một quy trình: từ chối đầu vào null, chạy bộ kiểm tra và trả lỗi nếu có vi phạm. Nếu mỗi repository có một implementation riêng chứa nguyên quy trình đó, thay đổi cách xử lý lỗi phải sửa nhiều nơi.

Ta muốn thiết kế một khả năng có ý nghĩa như sau:

~~~text
EntityChecks<Customer> → nhận và trả Customer hoặc kiểu con hợp lệ
EntityChecks<Product>  → nhận và trả Product hoặc kiểu con hợp lệ
~~~

Khả năng dùng chung ở đây là **thuật toán kiểm tra**, còn ràng buộc cụ thể nằm trên từng kiểu miền. Không cần đưa tên trường, tên bảng hoặc câu truy vấn của từng entity vào fragment.

Trước khi chọn fragment, cũng nên cân nhắc một service kiểm tra thông thường. Fragment phù hợp khi nhóm phát triển muốn công khai khả năng này ngay trên API repository theo cơ chế tham gia có chủ đích. Nếu kiểm tra chỉ thuộc một luồng nghiệp vụ, đặt nó tại service có thể đơn giản hơn.

## 2. Hợp đồng generic và repository cụ thể

Fragment gồm một interface thể hiện khả năng và một implementation thực hiện khả năng ấy. Repository cụ thể kế thừa interface fragment để nhận thêm phương thức. Một implementation generic có thể phục vụ nhiều repository có kiểu miền khác nhau. Đây là cơ chế composition của Spring Data, được trình bày trong [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

Trong thiết kế của bài:

~~~mermaid
flowchart LR
    C[CustomerRepository] --> CB[CRUD cho Customer]
    C --> CF[EntityChecks Customer]
    P[ProductRepository] --> PB[CRUD cho Product]
    P --> PF[EntityChecks Product]
    CF --> I[EntityChecksImpl: mã dùng chung]
    PF --> I
    I --> V[Jakarta Validator]
~~~

Sơ đồ biểu diễn việc dùng chung mã implementation. Nó không cam kết số lượng instance bean hay cơ chế sinh một bean riêng cho mỗi tham số generic.

Có ba lớp thông tin cần giữ tách biệt:

| Thành phần | Trách nhiệm trong ví dụ |
| --- | --- |
| `EntityChecks<T>` | Định nghĩa một thao tác kiểm tra an toàn kiểu |
| `EntityChecksImpl<T>` | Thực hiện quy trình kiểm tra chung |
| Repository cụ thể | Gắn `T` với `Customer` hoặc `Product`, đồng thời chọn loại repository lưu trữ |

Viết `<T>` chỉ mở khả năng tham số hóa. Implementation vẫn phải có một thuật toán thực sự không phụ thuộc tên kiểu miền.

## 3. Ví dụ hoàn chỉnh: fragment kiểm tra dữ liệu

### 3.1. Điều kiện để áp dụng ví dụ

Ví dụ dùng các API thuộc namespace `jakarta.*`, một ứng dụng đã cấu hình JPA và một Bean Validation provider tương thích. Các class public dưới đây nằm trong các file Java riêng tương ứng với tên class.

Spring Data Commons cung cấp abstraction và cơ chế repository composition; `JpaRepository` thuộc Spring Data JPA; `Validator` thuộc Jakarta Validation. Có Commons trên classpath chưa đủ để chạy toàn bộ ví dụ.

Bố trí package minh họa:

~~~text
com.acme.shop
├── config
│   └── ValidationConfiguration.java
├── domain
│   ├── Customer.java
│   └── Product.java
├── repository
│   ├── EntityChecks.java
│   ├── EntityChecksImpl.java
│   ├── CustomerRepository.java
│   └── ProductRepository.java
└── service
    └── CatalogRegistrationService.java
~~~

Ứng dụng phải quét entity trong `com.acme.shop.domain`, quét repository trong `com.acme.shop.repository` và có cấu hình JPA, datasource cùng transaction manager phù hợp. Sơ đồ trên mô tả mã cần thêm; không thay thế cấu hình lưu trữ của ứng dụng.

### 3.2. Khai báo fragment

~~~java
package com.acme.shop.repository;

public interface EntityChecks<T> {

    <S extends T> S checkForWrite(S candidate);
}
~~~

Hợp đồng của phương thức:

- Đầu vào null bị từ chối.
- Đối tượng vi phạm constraint bị từ chối.
- Đối tượng hợp lệ được trả về nguyên tham chiếu.
- Phương thức không ghi dữ liệu và không tạo bản sao.

Tên `checkForWrite` mô tả mục đích sử dụng của ứng dụng. Nó không phải tên đặc biệt được Spring Data tự động gọi khi thực hiện `save`.

### 3.3. Viết implementation dùng chung

~~~java
package com.acme.shop.repository;

import java.util.Objects;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;

public class EntityChecksImpl<T> implements EntityChecks<T> {

    private final Validator validator;

    public EntityChecksImpl(Validator validator) {
        this.validator = Objects.requireNonNull(validator, "validator");
    }

    @Override
    public <S extends T> S checkForWrite(S candidate) {
        Objects.requireNonNull(candidate, "candidate");

        Set<ConstraintViolation<S>> violations =
                validator.validate(candidate);

        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }

        return candidate;
    }
}
~~~

Implementation không cần biết `Customer` hay `Product`. Bộ kiểm tra đọc constraint của chính đối tượng được truyền vào.

Không có `EntityManager`, `MongoTemplate` hoặc thao tác I/O do fragment trực tiếp thực hiện. Tuy nhiên, nếu ứng dụng tự viết một constraint validator truy vấn cơ sở dữ liệu, cần tính thêm chi phí và ranh giới transaction của validator đó. Ví dụ này chỉ dùng constraint cục bộ trên thuộc tính.

Dữ liệu của mỗi lần gọi nằm trong biến cục bộ. Không lưu `candidate`, tập lỗi hoặc kiểu miền hiện tại vào field, vì implementation có thể được nhiều lời gọi sử dụng đồng thời.

### 3.4. Cung cấp Validator

Nếu ứng dụng chưa có bean `jakarta.validation.Validator`, có thể cấu hình:

~~~java
package com.acme.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

`LocalValidatorFactoryBean` tích hợp Bean Validation vào Spring và có thể được inject dưới kiểu `jakarta.validation.Validator`. Cần có provider tương thích trên classpath. Nếu ứng dụng đã cung cấp bean phù hợp, tái sử dụng bean đó thay vì thêm cấu hình trùng. Xem [Java Bean Validation của Spring Framework](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).

Ví dụ gọi `validator.validate(candidate)` trực tiếp, dùng nhóm constraint mặc định. Nó không cần `@Validated` để kích hoạt lời gọi này và không tự kiểm tra mọi tham số của mọi phương thức repository.

### 3.5. Hai kiểu miền có ràng buộc khác nhau

Entity khách hàng:

~~~java
package com.acme.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    private String displayName;

    protected Customer() {
    }

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }
}
~~~

Entity sản phẩm:

~~~java
package com.acme.shop.domain;

import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    private String sku;

    @NotNull
    @Positive
    private BigDecimal price;

    protected Product() {
    }

    public Product(String sku, BigDecimal price) {
        this.sku = sku;
        this.price = price;
    }

    public Long getId() {
        return id;
    }
}
~~~

Các constraint đặt trên field nên ví dụ không cần getter cho mọi thuộc tính để bộ kiểm tra truy cập chúng. Ràng buộc tên khách hàng và ràng buộc giá sản phẩm khác nhau, nhưng không làm thay đổi thuật toán trong `EntityChecksImpl`.

Đây mới là kiểm tra trạng thái của một đối tượng. Nó chưa chứng minh SKU duy nhất hoặc dữ liệu không bị một transaction khác sửa đồng thời.

### 3.6. Ghép cùng fragment vào hai repository

~~~java
package com.acme.shop.repository;

import com.acme.shop.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>, EntityChecks<Customer> {
}
~~~

~~~java
package com.acme.shop.repository;

import com.acme.shop.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long>, EntityChecks<Product> {
}
~~~

Hai repository dùng chung source của fragment, nhưng kiểu được phép truyền vào khác nhau:

~~~java
Customer checkedCustomer =
        customers.checkForWrite(new Customer("Lan"));

Product checkedProduct =
        products.checkForWrite(
                new Product("BOOK-001", new BigDecimal("120000"))
        );

// Không biên dịch nếu bỏ dấu comment:
// customers.checkForWrite(new Product("BOOK-002", BigDecimal.TEN));
~~~

Đoạn gọi giả định `customers` và `products` đã được inject theo đúng repository tương ứng.

Khai báo kiểu miền chính xác trên repository giúp phát hiện nhầm lẫn tại thời điểm biên dịch. Không thay `EntityChecks<Customer>` bằng raw type `EntityChecks`, vì raw type làm suy yếu bảo đảm này.

### 3.7. Gọi kiểm tra và lưu tại service

~~~java
package com.acme.shop.service;

import java.math.BigDecimal;

import com.acme.shop.domain.Customer;
import com.acme.shop.domain.Product;
import com.acme.shop.repository.CustomerRepository;
import com.acme.shop.repository.ProductRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogRegistrationService {

    private final CustomerRepository customers;
    private final ProductRepository products;

    public CatalogRegistrationService(
            CustomerRepository customers,
            ProductRepository products) {
        this.customers = customers;
        this.products = products;
    }

    @Transactional
    public Customer registerCustomer(String displayName) {
        Customer candidate = new Customer(displayName);
        Customer checked = customers.checkForWrite(candidate);
        return customers.save(checked);
    }

    @Transactional
    public Product registerProduct(String sku, BigDecimal price) {
        Product candidate = new Product(sku, price);
        Product checked = products.checkForWrite(candidate);
        return products.save(checked);
    }
}
~~~

Ranh giới transaction được đặt tại service để bao trùm luồng nghiệp vụ. Fragment kiểm tra trong ví dụ không cần mở transaction riêng.

Với `registerProduct("BOOK-001", new BigDecimal("-1"))`, kiểm tra thất bại trước khi service đi đến lệnh `save`. Với dữ liệu hợp lệ, service lưu đối tượng và trả về kết quả của `save`.

Việc gọi kiểm tra tường minh không loại bỏ validation có thể được provider JPA kích hoạt tại các sự kiện vòng đời. Cũng cần tránh kiểm tra trùng nhiều lần nếu ứng dụng không có nhu cầu xác định lỗi sớm.

## 4. Vì sao dùng cả T và S?

So sánh hai chữ ký:

~~~java
T checkForWrite(T candidate);
~~~

~~~java
<S extends T> S checkForWrite(S candidate);
~~~

`T` là kiểu miền mà repository đã gắn vào fragment. `S` là kiểu cụ thể của đối tượng tại một lần gọi, với điều kiện `S` phải nằm trong giới hạn `T`.

Ví dụ chỉ minh họa Java generics:

~~~java
class Item {
}

class SpecialItem extends Item {
}

void inspect(EntityChecks<Item> checks, SpecialItem item) {
    SpecialItem checked = checks.checkForWrite(item);
}
~~~

Nếu phương thức trả về `T`, kiểu kết quả tại vị trí này chỉ là `Item`. Với `<S extends T>`, kết quả giữ được kiểu `SpecialItem`.

Chữ ký generic cũng tạo nghĩa vụ cho implementation: phương thức phải thật sự trả về kiểu tương thích với `S`. Ví dụ chính trả nguyên tham chiếu nên đáp ứng điều đó mà không cần ép kiểu.

Một implementation lấy `candidate`, tạo một đối tượng thuộc kiểu miền khác rồi ép sang `S` sẽ phá vỡ hợp đồng. Thêm `@SuppressWarnings("unchecked")` không sửa được sai lệch về thiết kế.

Khả năng giữ kiểu con ở Java không tự chứng minh kiểu con đã được ánh xạ đúng trong kho dữ liệu. Nếu muốn lưu kiểu con bằng JPA, vẫn phải thiết kế ánh xạ kế thừa phù hợp.

## 5. Khi nào cần thêm tham số ID?

Fragment hiện tại chỉ nhận đối tượng nên không cần biết kiểu khóa chính. Đưa `ID` vào lúc này sẽ làm API dài hơn mà chưa thể hiện thêm ràng buộc có ích.

Khi khả năng thực sự làm việc với định danh, hợp đồng có thể cần hai tham số:

~~~java
public interface ExistingEntityChecks<T, ID> {

    void checkExisting(ID id);
}
~~~

Ví dụ ghép kiểu:

~~~text
ExistingEntityChecks<Customer, Long>
ExistingEntityChecks<Document, String>
~~~

Đây chỉ là minh họa hợp đồng. Nó chưa có implementation và không được ghép vào repository của ví dụ chính.

Muốn thực hiện `checkExisting`, implementation phải có một cơ chế tải dữ liệu. Generics không cung cấp cơ chế ấy. Cần xác định adapter hoặc API lưu trữ cụ thể, kiểu miền tại runtime và hành vi khi không tìm thấy đối tượng.

Không nên inject chính repository đang được tạo vào fragment rồi gọi ngược repository đó một cách mặc định. Thiết kế như vậy dễ tạo phụ thuộc vòng; nếu phương thức được gọi lại chính là phương thức fragment đang thay thế, còn có nguy cơ đệ quy.

## 6. Khi thuật toán cần một năng lực của kiểu miền

Không phải fragment nào cũng phù hợp với `T` không có giới hạn. Chẳng hạn, một khả năng đánh dấu lưu trữ cần đối tượng cung cấp hành vi tương ứng:

~~~java
import java.time.Instant;

public interface Archivable {

    void markArchived(Instant at);
}
~~~

~~~java
import java.time.Instant;

public interface ArchiveMarker<T extends Archivable> {

    <S extends T> S markForArchive(S aggregate, Instant at);
}
~~~

Có thể thiết kế phần thực thi thuần miền như sau:

~~~java
import java.time.Instant;
import java.util.Objects;

public class ArchiveMarkerImpl<T extends Archivable>
        implements ArchiveMarker<T> {

    @Override
    public <S extends T> S markForArchive(S aggregate, Instant at) {
        Objects.requireNonNull(aggregate, "aggregate");
        Objects.requireNonNull(at, "at");

        aggregate.markArchived(at);
        return aggregate;
    }
}
~~~

Đây là một phương án thiết kế độc lập, không phải phần bắt buộc để chạy ví dụ `EntityChecks`.

Chỉ kiểu miền triển khai `Archivable` mới dùng được `ArchiveMarker<T>`. Quy tắc như “đã lưu trữ thì không đổi thời điểm” có thể nằm trong phương thức `markArchived` của miền.

Thao tác trên chỉ thay đổi đối tượng trong bộ nhớ. Cách ghi thay đổi xuống kho dữ liệu phải được xác định riêng. Không suy rằng mọi kho đều có dirty checking hoặc một thao tác `save` với cùng ngữ nghĩa.

Giới hạn `T extends Archivable` phù hợp khi tất cả kiểu tham gia thật sự chia sẻ năng lực đó. Nếu chỉ một vài trường có tên giống nhau nhưng hành vi khác nhau, reflection theo tên trường thường che giấu sự khác biệt thay vì tạo abstraction có ích.

## 7. T không tự trở thành Class<T> tại runtime

Implementation của `EntityChecks` không cần domain class vì nó đã có đối tượng để kiểm tra. Nhu cầu sẽ khác nếu fragment phải tạo truy vấn mà chưa có entity.

Đoạn dưới không hợp lệ:

~~~java
// Không biên dịch:
// Class<T> domainType = T.class;
~~~

Java áp dụng type erasure; tham số kiểu không tạo ra một class runtime riêng cho từng cách tham số hóa. Xem [Type Erasure của Oracle](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html).

Hệ quả thiết kế:

- Không giả định `new GenericFragment<Customer>()` tự truyền `Customer.class` vào constructor.
- Đổi constructor thành `GenericFragmentImpl(Class<T> type)` chưa đủ; cần cấu hình cách cung cấp giá trị.
- `candidate.getClass()` cho biết lớp runtime của đối tượng hiện có, có thể là lớp proxy; nó không phải một giải pháp tổng quát để biết miền repository.
- Không ghi đè một field `currentDomainType` theo từng request rồi dùng field đó cho truy vấn tiếp theo.

Có thể cung cấp thông tin kiểu bằng cấu hình tường minh hoặc metadata của repository. Với API `RepositoryMethodContext`, metadata của lời gọi cần được bật trước khi dùng; không mặc định sẵn có. Tham khảo phần metadata trong [hướng dẫn custom implementation](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

Ngay cả khi đã biết `Customer.class`, fragment vẫn chưa biết tên bảng thực tế, tên collection, quy tắc ánh xạ thuộc tính hoặc khả năng truy vấn của kho. Không lấy tên class chuyển thành chữ thường rồi coi đó là quy tắc ánh xạ dùng được cho mọi hệ thống.

## 8. Đăng ký implementation và xử lý lỗi ghép fragment

Theo quy ước mặc định, interface `EntityChecks` đi với implementation `EntityChecksImpl`; class phải nằm trong phạm vi phát hiện implementation. Ví dụ đặt chúng cùng package với repository. Constructor được dùng để inject dependency như bean thông thường. Xem [cấu hình custom implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

Trong phạm vi ví dụ, nên giữ cách đăng ký đơn giản: một implementation phù hợp, một `Validator` rõ ràng, cùng package repository được cấu hình.

Khi khởi động gặp lỗi, kiểm tra theo dữ kiện thực tế:

| Biểu hiện | Điểm cần kiểm tra trong thiết kế này |
| --- | --- |
| `checkForWrite` bị xử lý như một query method | Repository đã kế thừa fragment chưa, implementation có được ghép vào không |
| Không tìm được bean `Validator` | Có provider và bean validation phù hợp chưa |
| Có nhiều dependency cùng kiểu | Bean nào được chọn, có cần qualifier không |
| Chạy được ở một repository nhưng lỗi ở repository khác | Phạm vi quét của từng cấu hình repository có giống dự kiến không |
| Kiểu miền của lời gọi không bị kiểm tra | Có raw type hoặc ép kiểu làm mất thông tin generic không |
| Constraint không xuất hiện trong kết quả | Constraint có đặt trên thuộc tính đúng và nhóm kiểm tra có đúng không |

Nếu chuyển fragment vào một thư viện riêng, không suy rằng chỉ thêm JAR là nó được ghép tự động. Khi đó cần thiết kế và kiểm chứng cách đăng ký extension tương ứng với phiên bản Spring Data của ứng dụng.

## 9. Fragment thuần và base repository generic là hai vai trò khác nhau

`EntityChecks<T>` là interface khả năng thuần, không kế thừa `Repository`. Vì vậy không cần thêm `@NoRepositoryBean` chỉ vì nó có tham số generic.

Nếu muốn nhiều repository cùng thừa hưởng cả CRUD lẫn khả năng kiểm tra, có thể tạo một interface trung gian:

~~~java
package com.acme.shop.repository;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface CheckedRepository<T, ID>
        extends CrudRepository<T, ID>, EntityChecks<T> {
}
~~~

`@NoRepositoryBean` ngăn Spring Data tạo repository trực tiếp từ interface trung gian còn để mở tham số kiểu. Nó không cung cấp implementation cho `checkForWrite`. Xem [Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

Đây là lựa chọn tổ chức API, không phải yêu cầu để chạy ví dụ ban đầu. Hai repository cụ thể vẫn có thể kế thừa trực tiếp `JpaRepository` và `EntityChecks`.

Trong ứng dụng có nhiều module lưu trữ, cần làm rõ repository thuộc module nào bằng interface đặc thù, ánh xạ miền hoặc phạm vi quét thích hợp. Một base interface chỉ kế thừa `CrudRepository` không tự giải quyết mọi trường hợp phân biệt JPA với MongoDB. Quy tắc phân biệt được mô tả trong [cấu hình nhiều Spring Data module](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

## 10. Phân biệt tái sử dụng theo kiểu miền và theo kho dữ liệu

Hai câu hỏi phải được trả lời độc lập:

1. Thuật toán có dùng được cho nhiều kiểu miền không?
2. Implementation có dùng được với công nghệ lưu trữ khác không?

| Thiết kế | Khả năng dùng chung | Điều kiện còn lại |
| --- | --- | --- |
| Kiểm tra constraint trên đối tượng như ví dụ chính | Nhiều kiểu miền | Cùng hạ tầng validation và hợp đồng lỗi |
| Đánh dấu đối tượng thông qua `Archivable` | Các kiểu có năng lực đó | Có luồng ghi dữ liệu phù hợp |
| Fragment gọi `EntityManager` | Nhiều entity JPA nếu thuật toán phù hợp | Cấu hình JPA, transaction và mapping đúng |
| Fragment gọi `MongoTemplate` | Nhiều document nếu thuật toán phù hợp | Quy tắc ánh xạ và thao tác MongoDB đúng |
| Fragment dùng truy vấn với tên trường cố định | Chỉ các miền đáp ứng tiền đề ấy | Tiền đề phải được công khai và kiểm tra |

Không dùng implementation dựa trên `EntityManager` cho repository MongoDB chỉ bằng cách đổi `T`. Tương tự, một fragment blocking không trở thành reactive khi ghép vào repository reactive. Luồng reactive cần hợp đồng trả về, thời điểm thực thi và dependency phù hợp.

Các API như phân trang, sắp xếp, projection hoặc Query by Example chỉ nên xuất hiện trong fragment khi khả năng đó thực sự cần chúng. Đưa `Pageable` vào chữ ký không tự tạo thuật toán đếm tổng hoặc bảo đảm kho dữ liệu hỗ trợ mọi kiểu truy vấn.

Với auditing, cũng cần phân biệt khả năng tự đặt giá trị trên đối tượng với hạ tầng tự ghi nhận người tạo, người sửa và thời điểm. Ví dụ kiểm tra dữ liệu không thay thế cấu hình auditing của từng module.

## 11. Không vô tình thay đổi hợp đồng ghi dữ liệu

Trong ví dụ chính:

~~~java
customers.checkForWrite(customer);
customers.save(customer);
~~~

Đây là hai lời gọi tách biệt. Người gọi khác vẫn có thể gọi thẳng `save` mà không đi qua `checkForWrite`. Vì thế fragment này cung cấp một khả năng, chưa phải một cơ chế bắt buộc áp dụng chính sách cho mọi đường ghi.

Nếu yêu cầu nghiệp vụ là mọi thao tác ghi đều phải được kiểm tra, cần xem xét toàn bộ đường ghi: `save`, `saveAll`, bulk update, template, SQL trực tiếp và tác vụ nhập dữ liệu. Quy định tại một phương thức chưa bao phủ tất cả.

Khi cân nhắc thay thế `save` bằng fragment, phải thiết kế riêng:

- Cách thực hiện ghi thật mà không gọi vòng vào chính `save` đã bị thay thế.
- Ngữ nghĩa đối tượng mới, đối tượng đã tồn tại và đối tượng tách khỏi persistence context.
- Kiểu kết quả được trả lại, transaction, sự kiện và hành vi lỗi.
- Những đường ghi còn nằm ngoài phạm vi can thiệp.

Không tự viết một câu `INSERT` rồi coi nó tương đương mọi ngữ nghĩa của `save`. Cũng không gom các luật nghiệp vụ khác nhau vào một fragment chỉ để giảm số lượng class.

Nếu hai fragment cùng khai báo một phương thức có cùng chữ ký, hãy làm rõ trách nhiệm và cách phân phối lời gọi trước khi ghép chúng. Dùng tên khả năng riêng thường giúp hợp đồng dễ đọc và dễ kiểm chứng hơn.

## 12. Tình huống cần kiểm chứng khi áp dụng

Các tình huống dưới đây là kế hoạch kiểm chứng cho người học, không phải kết quả chạy thử kèm bài:

| Tình huống | Kỳ vọng cần xác nhận |
| --- | --- |
| Customer hợp lệ gọi qua repository | Trả đúng đối tượng, không phát sinh thao tác lưu từ fragment |
| Product có giá âm | Ném `ConstraintViolationException` |
| Đầu vào null | Bị từ chối ngay tại biên fragment |
| Truyền Product vào `EntityChecks<Customer>` | Trình biên dịch từ chối |
| Gọi hai repository trong cùng application context | Cả hai phân phối lời gọi đến fragment đúng |
| Gọi trực tiếp `save` | Không nhầm đó là lời gọi tự động đến `checkForWrite` |
| Nhiều lời gọi đồng thời | Không dùng chung dữ liệu candidate hoặc lỗi qua field |

Kiểm tra implementation bằng đối tượng Java thông thường chỉ chứng minh thuật toán của class. Để chứng minh tên implementation, phạm vi quét và repository composition đúng, cần một kiểm tra tích hợp gọi qua bean repository.

Khi kiểm tra constraint bằng tập lỗi, nên xác nhận thuộc tính và loại vi phạm cần thiết thay vì phụ thuộc thứ tự phần tử của `Set` hoặc toàn bộ thông báo đã dịch.

## 13. Bài thực hành mở rộng

Thêm kiểu miền `Supplier` với mã nhà cung cấp bắt buộc và email có constraint phù hợp. Sau đó:

1. Tạo repository cụ thể kế thừa `EntityChecks<Supplier>`.
2. Giữ nguyên source của `EntityChecksImpl`.
3. Viết một luồng service gọi kiểm tra rồi lưu supplier.
4. Xác nhận constraint của supplier không làm thay đổi cách kiểm tra customer và product.
5. Ghi rõ các luật vẫn phải do cơ sở dữ liệu hoặc nghiệp vụ bảo đảm, chẳng hạn mã duy nhất và quyền tạo nhà cung cấp.

Sản phẩm của bài thực hành là một khả năng kiểm tra được dùng lại với hợp đồng rõ ràng. Khi thêm kiểu miền mới chỉ cần khai báo constraint và ghép interface, ta đã tái sử dụng được đúng phần chung mà vẫn giữ trách nhiệm của từng miền và từng kho dữ liệu.
