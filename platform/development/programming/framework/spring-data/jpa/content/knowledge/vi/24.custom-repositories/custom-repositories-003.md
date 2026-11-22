# Quy ước tên lớp triển khai, hậu tố và phạm vi quét

## 1. Vì sao Spring Data cần quy ước tên implementation?

Spring Data JPA tạo repository proxy từ interface. Các thao tác CRUD, query method và những tính năng như Querydsl được ghép vào proxy từ các thành phần do Spring Data cung cấp. Khi cần viết logic truy vấn riêng, ta có thể bổ sung một implementation tùy biến.

Để tự tìm implementation mà không cần khai báo thủ công từng bean, Spring Data dùng quy ước tên và phạm vi quét. Hai yếu tố quan trọng là:

- **Tên fragment interface:** tên contract chứa các method tùy biến.
- **Implementation postfix:** hậu tố được nối vào tên fragment interface để tìm lớp triển khai. Mặc định là `Impl`.

Ví dụ, fragment interface tên `CustomerSearch` sẽ được tìm cùng implementation tên `CustomerSearchImpl`. Nếu cấu hình postfix thành `Custom`, Spring Data sẽ tìm `CustomerSearchCustom`.

Quy ước này thuộc cơ chế khám phá repository fragment của Spring Data. Nó khác với việc Spring component scan một class có annotation `@Component`, và cũng khác với việc JPA scan entity.

## 2. Mô hình được khuyến nghị: Repository Fragment

### 2.1. Tách contract tùy biến thành interface riêng

Mỗi nhóm chức năng tùy biến nên được mô tả bằng một interface nhỏ. Ví dụ:

```java
package com.acme.customer.repository;

public interface CustomerSearch {

    List<Customer> searchByKeyword(String keyword);
}
```

Repository chính kế thừa fragment interface:

```java
package com.acme.customer.repository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Như vậy, client chỉ cần inject `CustomerRepository` nhưng có thể gọi cả CRUD method lẫn `searchByKeyword()`.

Fragment interface có thể được đặt tên theo năng lực mà nó cung cấp, chẳng hạn `CustomerSearch`, `CustomerStatistics` hoặc `CustomerBulkOperations`. Không bắt buộc phải đặt tên theo mẫu `CustomerRepositoryCustom`, miễn implementation tuân theo quy ước nối hậu tố.

### 2.2. Đặt tên lớp triển khai

Với postfix mặc định `Impl`, lớp triển khai là:

```java
package com.acme.customer.repository;

public class CustomerSearchImpl implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<Customer> searchByKeyword(String keyword) {
        String pattern = "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

        return entityManager.createQuery("""
            select c
            from Customer c
            where lower(c.name) like :pattern
            order by c.name, c.id
            """, Customer.class)
            .setParameter("pattern", pattern)
            .getResultList();
    }
}
```

Quy tắc tên là:

| Fragment interface | Postfix | Implementation được tìm |
|---|---|---|
| `CustomerSearch` | `Impl` | `CustomerSearchImpl` |
| `CustomerStatistics` | `Impl` | `CustomerStatisticsImpl` |
| `CustomerBulkOperations` | `Impl` | `CustomerBulkOperationsImpl` |

Implementation là một Spring bean thông thường sau khi được Spring Data phát hiện. Có thể constructor-inject service, `JdbcTemplate`, mapper hoặc các dependency khác. Ví dụ dùng `@PersistenceContext` để nhận EntityManager được quản lý bởi Spring.

Các import và entity `Customer` trong ví dụ cần tồn tại trong dự án. Đây là các đoạn minh họa cấu trúc fragment, không phải một chương trình Java độc lập.

### 2.3. Repository có thể ghép nhiều fragment

Một repository có thể kết hợp nhiều interface tùy biến:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics,
                CustomerBulkOperations {
}
```

Mỗi fragment có implementation riêng:

- `CustomerSearchImpl`
- `CustomerStatisticsImpl`
- `CustomerBulkOperationsImpl`

Spring Data tạo repository composition từ base repository, các repository aspect và custom fragments. Cách này giúp chia logic theo năng lực, dễ tái sử dụng và tránh một lớp implementation khổng lồ.

Một fragment interface cũng có thể được nhiều repository sử dụng nếu cùng cần một chức năng. Ví dụ `AuditableSearch` có thể được tái sử dụng ở nhiều repository có cùng kiểu domain hoặc contract phù hợp.

## 3. Hậu tố mặc định Impl và cách tùy chỉnh

### 3.1. Quy ước mặc định

Nếu không cấu hình gì thêm, Spring Data sử dụng postfix `Impl`.

Ví dụ:

```text
CustomerSearch       -> CustomerSearchImpl
OrderSearch          -> OrderSearchImpl
InvoiceReport        -> InvoiceReportImpl
```

Hậu tố được nối trực tiếp vào tên interface fragment. Không thêm dấu gạch dưới, dấu chấm hoặc từ khóa `Repository` vào giữa nếu không có trong tên interface.

### 3.2. Đổi postfix bằng @EnableJpaRepositories

Có thể thay đổi postfix cho repository configuration:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.acme.customer.repository",
    repositoryImplementationPostfix = "Custom"
)
public class JpaRepositoryConfiguration {
}
```

Với cấu hình trên, Spring Data tìm:

```text
CustomerSearch -> CustomerSearchCustom
```

Nếu interface là `CustomerSearch`, class tên `CustomerSearchImpl` sẽ không khớp postfix `Custom` của cấu hình đó. Tên class và cấu hình phải thống nhất.

Có thể dùng một hậu tố dễ nhận biết theo convention của nhóm, nhưng nên giữ một giá trị thống nhất trong phạm vi repository configuration. Tránh mỗi fragment dùng một hậu tố tùy ý vì cơ chế autodetection sẽ khó dự đoán.

### 3.3. Postfix áp dụng theo repository configuration

`repositoryImplementationPostfix` là thuộc tính của `@EnableJpaRepositories`. Nếu ứng dụng có nhiều cấu hình repository cho các persistence unit hoặc package khác nhau, mỗi cấu hình có thể cần postfix và phạm vi package riêng.

Ví dụ minh họa:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.acme.sales.repository",
    entityManagerFactoryRef = "salesEntityManagerFactory",
    transactionManagerRef = "salesTransactionManager",
    repositoryImplementationPostfix = "Impl"
)
class SalesRepositoryConfiguration {
}

@Configuration
@EnableJpaRepositories(
    basePackages = "com.acme.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager",
    repositoryImplementationPostfix = "Custom"
)
class BillingRepositoryConfiguration {
}
```

Đây là cấu hình minh họa cho ứng dụng có hai persistence unit; các bean EntityManagerFactory và transaction manager phải được khai báo tương ứng. Không để hai cấu hình quét trùng package repository nếu không chủ đích.

## 4. Phạm vi quét repository và implementation

### 4.1. basePackages xác định nơi tìm repository interface

Với cấu hình:

```java
@EnableJpaRepositories(
    basePackages = "com.acme.persistence"
)
class PersistenceConfiguration {
}
```

Spring Data tìm các repository interface trong package được khai báo và các package con theo quy tắc scan của repository infrastructure.

Ví dụ cấu trúc:

```text
com.acme
└── persistence
    ├── customer
    │   ├── CustomerRepository.java
    │   ├── CustomerSearch.java
    │   └── CustomerSearchImpl.java
    └── order
        ├── OrderRepository.java
        ├── OrderSearch.java
        └── OrderSearchImpl.java
```

Cấu hình `basePackages = "com.acme.persistence"` bao phủ các repository trong `customer` và `order`, cùng các package con của phạm vi đó.

Nếu chỉ khai báo `com.acme.persistence.customer`, repository ở `com.acme.persistence.order` sẽ nằm ngoài phạm vi cấu hình này.

### 4.2. Implementation fragment được tìm trong phạm vi repository

Repository infrastructure tự phát hiện custom implementation fragments bằng cách quét các lớp trong package của repository và các package con thuộc phạm vi repository đã tìm thấy.

Cách bố trí dễ dự đoán nhất là để fragment interface và implementation cùng package với repository interface:

```text
com.acme.customer.repository
├── CustomerRepository.java
├── CustomerSearch.java
└── CustomerSearchImpl.java
```

Có thể tổ chức package con nếu nó vẫn nằm trong phạm vi scan phù hợp:

```text
com.acme.customer.repository
├── CustomerRepository.java
└── search
    ├── CustomerSearch.java
    └── CustomerSearchImpl.java
```

Điều quan trọng là implementation phải nằm trong phạm vi mà repository infrastructure dùng để phát hiện fragments. Chỉ đặt class ở một package bất kỳ trong ứng dụng không bảo đảm Spring Data sẽ ghép class đó vào repository.

Khi tổ chức nhiều module, hãy kiểm tra package của repository, package của fragment và base package cấu hình. Đừng chỉ dựa vào việc ứng dụng khởi động được hoặc class đã được IDE nhận diện.

### 4.3. basePackageClasses giúp tránh hard-code chuỗi package

Thay vì dùng tên package dạng String, có thể dùng marker class:

```java
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class
)
class PersistenceConfiguration {
}
```

Spring Data dùng package chứa class được chỉ định làm điểm bắt đầu scan. Cách này an toàn hơn khi refactor package vì compiler có thể theo dõi class reference.

Có thể tạo một marker interface riêng nếu muốn tách cấu hình khỏi repository cụ thể:

```java
package com.acme.persistence;

public interface PersistencePackageMarker {
}
```

```java
@EnableJpaRepositories(
    basePackageClasses = PersistencePackageMarker.class
)
class PersistenceConfiguration {
}
```

### 4.4. Spring component scan không thay thế repository scan

Ba phạm vi thường bị nhầm:

| Cơ chế | Tìm thành phần nào? | Cấu hình thường gặp |
|---|---|---|
| Repository scan | Interface kế thừa Spring Data Repository | `@EnableJpaRepositories` |
| Component scan | Bean có stereotype như `@Component`, `@Service`, `@Controller` | `@ComponentScan` hoặc `@SpringBootApplication` |
| Entity scan | Lớp JPA được ánh xạ thành entity/embeddable | Cấu hình entity scan hoặc persistence unit |

`@ComponentScan` có thể tìm service và các component khác, nhưng không tự tạo repository proxy từ interface. Ngược lại, `@EnableJpaRepositories` tìm repository interface và thiết lập cơ chế phát hiện fragment implementation theo quy ước Spring Data.

Trong Spring Boot, `@SpringBootApplication` thường đặt component scan và auto-configuration package theo package của class ứng dụng. Nếu repository nằm ngoài package tree đó, cần cấu hình phạm vi phù hợp bằng `@EnableJpaRepositories` hoặc tổ chức lại package.

Không nhầm việc entity đã được JPA scan với việc repository interface hoặc custom fragment đã được phát hiện. Đây là các cơ chế riêng.

## 5. Fragment nằm ngoài phạm vi scan

### 5.1. Vì sao implementation có thể không được tìm thấy?

Giả sử repository nằm ở:

```text
com.acme.orders.repository.OrderRepository
```

Nhưng fragment và implementation nằm ở package độc lập:

```text
com.acme.shared.search.SearchExtension
com.acme.shared.search.DefaultSearchExtension
```

Nếu package của fragment implementation nằm ngoài phạm vi autodetection của repository, Spring Data có thể không tự tìm thấy fragment đó.

Các dấu hiệu thường gặp:
- Repository interface mở rộng fragment nhưng application context báo thiếu implementation.
- Custom method không được ghép vào repository composition.
- Class implementation tồn tại và có thể được component scan, nhưng Spring Data không nhận ra nó là implementation của fragment tương ứng.

### 5.2. Đăng ký fragment dùng chung qua spring.factories

Với fragment được cung cấp từ package khác hoặc thư viện dùng chung, Spring Data hỗ trợ đăng ký implementation trong file:

```text
META-INF/spring.factories
```

Nội dung theo dạng fully qualified name của fragment interface bằng fully qualified name của implementation:

```properties
com.acme.shared.search.SearchExtension=com.acme.shared.search.DefaultSearchExtension
```

Repository sau đó mở rộng fragment:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long>,
                SearchExtension<Order> {
}
```

Đây là cơ chế hữu ích cho extension dùng chung hoặc thư viện tích hợp. File `spring.factories` phải nằm trong classpath resource của artifact được đóng gói; kiểm tra nội dung JAR khi cần điều tra lỗi discovery.

Không dùng `spring.factories` chỉ để che một lỗi package scan đơn giản. Với fragment chỉ dùng trong một bounded context, đặt fragment trong package repository được quét thường dễ hiểu hơn.

## 6. Quy ước cũ: tên implementation dựa trên repository interface

### 6.1. Mô hình legacy

Trước mô hình repository fragments, Spring Data thường tìm một lớp có tên bằng repository interface cộng postfix:

```text
CustomerRepository -> CustomerRepositoryImpl
```

Lớp đó triển khai một custom interface hoặc cung cấp các method tùy biến gắn với repository chính. Đây là quy ước single-custom-implementation lịch sử.

Tài liệu Spring Data hiện tại đánh dấu kiểu discovery dựa trên tên repository interface là deprecated và khuyến nghị chuyển sang fragment-based programming model. Không nên bắt đầu thiết kế mới bằng một lớp `CustomerRepositoryImpl` chứa mọi logic tùy biến.

### 6.2. Vì sao fragment model tốt hơn?

Fragment model có các lợi ích:

- Một repository có thể ghép nhiều custom implementation.
- Mỗi fragment có contract và trách nhiệm riêng.
- Fragment có thể tái sử dụng ở nhiều repository.
- Thứ tự composition và xung đột method có thể được kiểm soát.
- Tên implementation gắn với năng lực tùy biến thay vì gắn cứng với repository tổng.

Ví dụ:

```java
public interface CustomerSearch {
    List<Customer> search(String keyword);
}

public interface CustomerStatistics {
    long countByStatus(CustomerStatus status);
}

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics {
}
```

Implementation:

```java
public class CustomerSearchImpl implements CustomerSearch {
    // Logic tìm kiếm
}

public class CustomerStatisticsImpl implements CustomerStatistics {
    // Logic thống kê
}
```

Cách này giúp một thay đổi ở logic tìm kiếm không buộc nhóm phải chỉnh một implementation class lớn đang chứa cả thống kê, import và CRUD.

### 6.3. Tránh vô tình kích hoạt legacy discovery

Nếu trong cùng package có lớp tên `CustomerRepositoryImpl`, Spring Data có thể nhận diện nó theo quy ước cũ. Lớp này có thể được ghép vào repository ngoài dự định hoặc gây xung đột với fragments.

Khi chuyển sang fragment model:
1. Tạo interface riêng cho từng nhóm method tùy biến.
2. Tạo implementation theo tên fragment cộng postfix.
3. Cho repository chính kế thừa fragment interface.
4. Di chuyển method và logic sang implementation tương ứng.
5. Xóa hoặc đổi tên legacy class sau khi xác nhận không còn được dùng.
6. Chạy integration test để xác nhận repository composition.

Không giữ song song hai cơ chế cho cùng một method nếu không có chủ đích rõ ràng.

## 7. Nhiều implementation cùng tên và xử lý ambiguity

### 7.1. Tình huống trùng tên

Hai module có thể cùng chứa class tên `CustomerSearchImpl`:

```text
com.acme.customer.search.CustomerSearchImpl
com.acme.archive.search.CustomerSearchImpl
```

Nếu cả hai implementation đều nằm trong phạm vi discovery và cùng triển khai fragment interface, Spring Data cần xác định bean phù hợp. Cơ chế resolution sử dụng bean name để chọn implementation tương ứng.

### 7.2. Bean name theo convention

Tên bean mặc định thường được tạo bằng cách viết thường chữ cái đầu của tên class. Với fragment interface `CustomerSearch` và postfix `Impl`, bean name theo convention là `customerSearchImpl`.

Nếu cần phân biệt implementation, có thể gán bean name tường minh và đặt tên repository bean tương ứng với quy ước mà Spring Data dùng để tìm fragment bean.

Ví dụ về ý tưởng đặt tên:

```java
@Component("specialCustomerSearchImpl")
public class CustomerSearchImpl implements CustomerSearch {
    // Implementation đặc biệt
}
```

Nếu repository bean được đặt tên `specialCustomerSearch`, postfix `Impl` tạo tên fragment bean tương ứng `specialCustomerSearchImpl`. Hãy kiểm tra tên bean thực tế trong application context khi xử lý ambiguity; không đoán từ tên package.

Không tạo nhiều bean cùng tên hoặc khai báo component name trùng với repository proxy. Bean name là một phần của cơ chế wiring trong trường hợp có nhiều candidate.

### 7.3. Manual wiring

Nếu implementation cần cấu hình bean đặc biệt, có thể khai báo bean thủ công với tên phù hợp convention:

```java
@Configuration
class CustomerSearchConfiguration {

    @Bean("customerSearchImpl")
    CustomerSearch customerSearch(
            EntityManager entityManager,
            CustomerSearchSupport support) {
        return new CustomerSearchBean(entityManager, support);
    }
}
```

Ví dụ này dùng một class bean riêng tên `CustomerSearchBean`; bean name mới là yếu tố được dùng để nối fragment. Khi đã tự khai báo bean, tránh đồng thời để autodetection tạo thêm một bean implementation khác cho cùng fragment.

## 8. Implementation là Spring bean thông thường

### 8.1. Constructor injection

Fragment implementation có thể nhận dependency như một bean Spring:

```java
public class CustomerSearchImpl implements CustomerSearch {

    private final CustomerSearchSupport support;

    public CustomerSearchImpl(CustomerSearchSupport support) {
        this.support = support;
    }

    @Override
    public List<Customer> searchByKeyword(String keyword) {
        return support.search(keyword);
    }
}
```

Không cần cho implementation kế thừa `SimpleJpaRepository` chỉ để thêm một method tùy biến. Fragment chỉ triển khai interface chức năng của nó.

### 8.2. Dùng EntityManager

Khi cần Criteria API hoặc JPQL riêng, implementation có thể dùng EntityManager:

```java
public class CustomerSearchImpl implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<Customer> searchByKeyword(String keyword) {
        return entityManager.createQuery(
            "select c from Customer c where c.name like :pattern",
            Customer.class
        )
        .setParameter("pattern", "%" + keyword + "%")
        .getResultList();
    }
}
```

Trong ứng dụng có nhiều persistence unit, phải bảo đảm implementation nhận đúng EntityManager. Có thể chỉ định unit name trong `@PersistenceContext`, dùng `@Qualifier` cho bean phù hợp hoặc sử dụng `JpaContext` khi domain type được quản lý bởi một EntityManager duy nhất.

### 8.3. Transaction boundary

Fragment implementation là bean Spring nên có thể dùng `@Transactional`. Hãy đặt transaction boundary theo use case và tránh giả định mọi custom method tự động có cùng transaction semantics với CRUD method kế thừa.

Với query chỉ đọc, `@Transactional(readOnly = true)` có thể biểu đạt ý định. Với thao tác ghi, cần transaction ghi phù hợp và xử lý exception/rollback theo yêu cầu nghiệp vụ.

## 9. Phân biệt fragment implementation và custom repository base class

Hai extension point này phục vụ hai mục tiêu khác nhau.

### 9.1. Repository fragment

Fragment mở rộng một số repository cụ thể bằng cách cho repository interface kế thừa custom interface:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Implementation thường tên `CustomerSearchImpl`. Chỉ repository nào kế thừa `CustomerSearch` mới có chức năng đó.

### 9.2. Custom base class

Nếu muốn thay đổi hành vi nền tảng cho nhiều repository, có thể kế thừa `SimpleJpaRepository` và cấu hình `repositoryBaseClass`:

```java
public class MyRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID> {

    public MyRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {
        super(entityInformation, entityManager);
    }
}
```

Đăng ký:

```java
@EnableJpaRepositories(
    basePackages = "com.acme.repository",
    repositoryBaseClass = MyRepositoryImpl.class
)
class JpaConfiguration {
}
```

Đây là custom base implementation được repository factory dùng làm lớp nền cho các repository thuộc configuration. Nó không phải fragment và không được tìm bằng cách nối tên fragment interface với postfix.

Không dùng `repositoryBaseClass` chỉ để thêm một method tìm kiếm cho một repository. Trường hợp đó repository fragment đơn giản và ít ảnh hưởng hơn.

## 10. Checklist tổ chức package và tên lớp

| Thành phần | Ví dụ | Quy tắc |
|---|---|---|
| Repository interface | `CustomerRepository` | Được tìm trong repository base package |
| Fragment interface | `CustomerSearch` | Repository chính kế thừa interface này |
| Fragment implementation | `CustomerSearchImpl` | Tên fragment cộng postfix |
| Postfix mặc định | `Impl` | Giá trị mặc định |
| Postfix tùy chỉnh | `Custom` | Khai báo qua `repositoryImplementationPostfix` |
| Repository scan root | `com.acme.persistence` | Xác định phạm vi repository discovery |
| Fragment ngoài phạm vi | `com.acme.shared.search` | Cân nhắc đăng ký qua `spring.factories` |
| Custom base class | `MyRepositoryImpl` | Cấu hình qua `repositoryBaseClass`, không phải fragment |

Ví dụ cấu trúc được khuyến nghị:

```text
com.acme
└── customer
    ├── domain
    │   └── Customer.java
    └── repository
        ├── CustomerRepository.java
        ├── CustomerSearch.java
        ├── CustomerSearchImpl.java
        ├── CustomerStatistics.java
        └── CustomerStatisticsImpl.java
```

## 11. Kiểm thử việc phát hiện implementation

### 11.1. Kiểm thử qua repository proxy

Dùng `@DataJpaTest` để kiểm tra repository và custom fragment trong persistence slice:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void invokesCustomFragmentImplementation() {
        List<Customer> result =
            repository.searchByKeyword("an");

        assertThat(result).isNotNull();
    }
}
```

Test cần chuẩn bị dữ liệu phù hợp và assertion theo kết quả mong muốn. Nếu implementation phụ thuộc bean ngoài persistence slice, import dependency cần thiết vào test bằng cấu hình phù hợp.

### 11.2. Kiểm tra các trường hợp discovery

Nên có test hoặc kiểm tra context cho các tình huống:

- Fragment interface được repository chính kế thừa.
- Tên implementation khớp postfix mặc định.
- Tên implementation khớp postfix tùy chỉnh.
- Implementation nằm trong package được repository scan bao phủ.
- Fragment ngoài package được đăng ký đúng qua `spring.factories`.
- Nhiều implementation cùng tên được phân giải theo bean name.
- Legacy `CustomerRepositoryImpl` không vô tình can thiệp.
- Nhiều repository configuration không quét chồng lấn ngoài dự kiến.
- Implementation nhận đúng EntityManager và transaction manager.

### 11.3. Kiểm tra artifact đã đóng gói

Nếu chạy được trong IDE nhưng không tìm thấy fragment sau khi đóng gói, hãy kiểm tra JAR:

- Class implementation có trong artifact không?
- Fragment interface có trong classpath không?
- File `META-INF/spring.factories` có được đóng gói đúng không?
- Package của repository có thuộc phạm vi scan khi chạy production không?
- Có profile/configuration nào thay đổi `@EnableJpaRepositories` không?

Một lỗi package scan thường không được giải quyết bằng cách thêm annotation `@Component` ngẫu nhiên. Hãy xác định cơ chế discovery nào đang thiếu.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Custom method không có implementation | Repository chưa kế thừa fragment interface | Thêm fragment interface vào extends list |
| Không tìm thấy implementation | Sai tên hoặc postfix | So khớp tên interface + postfix |
| Lớp Impl nằm ngoài phạm vi | Package không được repository infrastructure quét | Đặt trong phạm vi hoặc đăng ký extension |
| Đổi postfix nhưng giữ tên class cũ | Tên class không còn khớp cấu hình | Đổi class name hoặc trả postfix về đúng giá trị |
| Component tồn tại nhưng repository không ghép fragment | Nhầm component scan với fragment discovery | Kiểm tra repository scan và quy ước fragment |
| Hai implementation cùng tên gây nhầm | Bean name không phân giải đúng candidate | Đặt bean name rõ ràng hoặc thu hẹp phạm vi scan |
| Legacy implementation bị ghép ngoài ý muốn | Còn class RepositoryNameImpl | Chuyển sang fragment model và loại legacy discovery |
| Dùng base class để thêm method cho một repository | Nhầm repositoryBaseClass với fragment | Dùng custom fragment |
| EntityManager sai persistence unit | Nhiều EntityManagerFactory | Dùng unit name, Qualifier hoặc JpaContext |
| Test slice thiếu dependency | Bean ngoài phạm vi DataJpaTest | Import dependency/configuration phù hợp |

## 13. Checklist trước khi đưa custom repository vào ứng dụng

- [ ] Chức năng tùy biến đã được tách thành fragment interface rõ ràng.
- [ ] Repository chính đã kế thừa fragment interface.
- [ ] Implementation class có tên bằng fragment interface cộng postfix.
- [ ] Postfix thực tế khớp cấu hình `repositoryImplementationPostfix`.
- [ ] Fragment implementation nằm trong phạm vi discovery của repository.
- [ ] `basePackages` hoặc `basePackageClasses` bao phủ đúng repository.
- [ ] Không nhầm repository scan với component scan hoặc entity scan.
- [ ] Fragment ngoài phạm vi được đăng ký theo cơ chế phù hợp.
- [ ] Không còn legacy repository-name implementation gây xung đột ngoài ý muốn.
- [ ] Bean name rõ ràng nếu có nhiều implementation cùng tên.
- [ ] EntityManager và transaction manager được nối đúng persistence unit.
- [ ] Custom base class chỉ dùng khi muốn thay đổi hành vi nền cho nhiều repository.
- [ ] Integration test xác nhận fragment thực sự được ghép vào repository proxy.
- [ ] Artifact production chứa đủ class và resource cần thiết.

## 14. Tài liệu tham khảo chính thức

- [Spring Data JPA — Custom Repository Implementations](https://docs.spring.io/spring-data/jpa/reference/repositories/custom-implementations.html): repository fragments, postfix, discovery, ambiguity, manual wiring, `spring.factories` và custom base class.
- [Spring Data JPA — Defining Repository Interfaces](https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html): định nghĩa repository interface và cấu hình package scan.

## 15. Kết luận

Spring Data JPA khuyến nghị mô hình repository fragment cho chức năng tùy biến. Repository chính kế thừa fragment interface; implementation được tìm bằng cách nối tên fragment với postfix, mặc định là `Impl`. Có thể đổi postfix bằng `@EnableJpaRepositories(repositoryImplementationPostfix = "...")`, nhưng tên class phải khớp chính xác với cấu hình.

Phạm vi repository scan quyết định interface nào được phát hiện và nơi Spring Data tìm fragment implementation. `basePackages` hoặc `basePackageClasses` nên được cấu hình có chủ đích; fragment nằm ngoài phạm vi có thể cần đăng ký qua `META-INF/spring.factories`. Component scan, entity scan và repository scan là ba cơ chế khác nhau.

Quy ước cũ đặt một lớp theo tên repository cộng `Impl` đã được tài liệu hiện tại đánh dấu deprecated; nên ưu tiên fragment nhỏ, có contract rõ và có thể tái sử dụng. Chỉ dùng custom repository base class khi muốn thay đổi hành vi nền cho toàn bộ repository thuộc configuration. Cuối cùng, hãy kiểm tra package, postfix, bean name, transaction và repository proxy bằng integration test trên cấu hình thực tế.