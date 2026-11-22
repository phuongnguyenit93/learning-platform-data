# Kết hợp nhiều fragment và xử lý phương thức trùng trong Spring Data JPA

Spring Data JPA cho phép một repository được ghép từ nhiều thành phần: repository base như JpaRepository, các repository fragment do ứng dụng định nghĩa và những fragment do Spring Data cung cấp. Mỗi fragment có thể đóng gói một nhóm hành vi riêng, ví dụ tìm kiếm nâng cao, báo cáo, bulk operation hoặc tích hợp một hệ thống khác.

Khi nhiều fragment được kết hợp, đôi khi chúng khai báo cùng một method signature. Một fragment cũng có thể định nghĩa method trùng với method của repository base. Cần hiểu cách Spring Data ghép fragment, quy tắc phát hiện implementation, thứ tự ưu tiên khi có xung đột và giới hạn của hệ thống kiểu Java. Bài học này trình bày kiến trúc fragment hiện đại, cách đặt tên interface/implementation, ví dụ ghép nhiều fragment, cách xử lý method collision, khi nào dùng custom repository base class và cách kiểm thử để xác nhận method được gọi đúng implementation.

## 1. Repository Spring Data được ghép từ những thành phần nào?

Một repository Spring Data không nhất thiết chỉ là một interface được triển khai bởi một class duy nhất. Khi khởi tạo repository, Spring Data tạo một composition từ các thành phần cần thiết.

Các nhóm thường gặp:

- **Repository base implementation**: cung cấp CRUD và các thao tác chuẩn. Với JpaRepository, implementation mặc định thường là SimpleJpaRepository.
- **Custom repository fragments**: các phần mở rộng do ứng dụng định nghĩa, mỗi fragment có interface và implementation riêng.
- **Spring Data aspects/fragments**: các chức năng tích hợp như Querydsl hoặc những khả năng khác mà module cung cấp.
- **Query methods**: method được Spring Data phân tích từ tên hoặc cấu hình bằng @Query.

Ví dụ một repository có thể ghép CRUD, tìm kiếm tùy chỉnh và báo cáo:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment,
                CustomerReportFragment {
}
~~~

Ở đây:

- JpaRepository cung cấp save, findById, findAll, delete và các thao tác CRUD.
- CustomerSearchFragment cung cấp các phương thức tìm kiếm nâng cao.
- CustomerReportFragment cung cấp các phương thức tổng hợp hoặc báo cáo.

Repository vẫn được inject và sử dụng như một bean Spring thông thường. Người gọi không cần tự tạo từng fragment hoặc ghép chúng thủ công.

## 2. Fragment là gì?

Một fragment là một phần chức năng độc lập của repository. Thông thường fragment có:

1. Một interface khai báo các method.
2. Một class implementation thực hiện các method.
3. Một repository chính kế thừa interface fragment đó.

Ví dụ:

~~~java
public interface CustomerSearchFragment {
    List<Customer> search(CustomerSearchCriteria criteria);
}
~~~

Implementation:

~~~java
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    private final EntityManager entityManager;

    public CustomerSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Customer> search(CustomerSearchCriteria criteria) {
        // Xây dựng Criteria API hoặc JPQL động tại đây.
        return List.of();
    }
}
~~~

Repository chính:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment {
}
~~~

Spring Data phát hiện implementation của fragment theo quy ước tên và đưa nó vào repository composition.

Fragment hữu ích khi một nhóm method có trách nhiệm riêng, có thể kiểm thử độc lập hoặc tái sử dụng ở nhiều repository.

## 3. Quy ước đặt tên interface và implementation

Theo quy ước mặc định, implementation class của fragment dùng tên interface cộng hậu tố Impl.

| Fragment interface | Implementation mặc định |
|---|---|
| CustomerSearchFragment | CustomerSearchFragmentImpl |
| CustomerReportFragment | CustomerReportFragmentImpl |
| BulkArchiveFragment | BulkArchiveFragmentImpl |
| CustomizedSave | CustomizedSaveImpl |

Ví dụ:

~~~java
public interface CustomerReportFragment {
    long countCustomersCreatedBetween(
        LocalDateTime from,
        LocalDateTime to
    );
}
~~~

Class implementation:

~~~java
public class CustomerReportFragmentImpl
        implements CustomerReportFragment {

    private final EntityManager entityManager;

    public CustomerReportFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public long countCustomersCreatedBetween(
            LocalDateTime from,
            LocalDateTime to) {
        return entityManager.createQuery(
            """
            select count(c)
            from Customer c
            where c.createdAt >= :from
              and c.createdAt < :to
            """,
            Long.class
        )
        .setParameter("from", from)
        .setParameter("to", to)
        .getSingleResult();
    }
}
~~~

Tên class cần khớp với tên fragment interface và hậu tố đang cấu hình. Nếu interface là CustomerReportFragment nhưng class lại tên CustomerReportImpl, Spring Data có thể không phát hiện implementation theo quy ước mặc định.

Implementation class cần nằm trong phạm vi package mà cơ chế repository scanning có thể tìm thấy, thường là cùng package với repository hoặc package con phù hợp.

## 4. Thay đổi implementation postfix

Hậu tố mặc định là Impl. Có thể thay đổi hậu tố khi cấu hình repository scanning:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "example.repository",
    repositoryImplementationPostfix = "JpaImpl"
)
public class JpaRepositoryConfiguration {
}
~~~

Khi cấu hình hậu tố JpaImpl, các fragment implementation cần đặt tên tương ứng:

- CustomerSearchFragmentJpaImpl
- CustomerReportFragmentJpaImpl

Không chỉ đổi tên class mà quên cấu hình postfix, hoặc đổi cấu hình mà để lại tên class theo hậu tố cũ.

Trong Spring Boot, repository scanning thường được cấu hình tự động theo package của ứng dụng. Chỉ khai báo @EnableJpaRepositories riêng khi cần kiểm soát package, entity manager hoặc postfix.

## 5. Fragment có thể được tái sử dụng giữa nhiều repository

Một fragment không bắt buộc gắn với duy nhất một repository. Ví dụ, nhiều repository có thể cần khả năng tìm kiếm theo mã ngoài.

Interface:

~~~java
public interface ExternalCodeLookup<T> {
    Optional<T> findByExternalCode(String code);
}
~~~

Implementation generic có thể nhận EntityManager và thông tin entity phù hợp. Tuy nhiên, để viết query tổng quát an toàn, cần biết entity type, tên property và kiểu dữ liệu; có thể truyền cấu hình qua constructor hoặc tạo fragment chuyên biệt theo domain.

Repository sử dụng:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment {
}

public interface SupplierRepository
        extends JpaRepository<Supplier, Long>,
                SupplierSearchFragment {
}
~~~

Mỗi fragment có thể đóng gói logic phù hợp với entity tương ứng. Không nên ép mọi repository dùng một implementation generic nếu tên property, quan hệ hoặc quy tắc nghiệp vụ khác nhau.

Khi thiết kế fragment dùng chung, hãy xác định rõ phần nào thực sự chung: thuật toán, transaction boundary, mapping kết quả hay chỉ là chữ ký method.

## 6. Kết hợp nhiều fragment trong một repository

Ví dụ một CustomerRepository kết hợp ba nhóm chức năng:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment,
                CustomerReportFragment,
                CustomerArchiveFragment {
}
~~~

Các interface fragment:

~~~java
public interface CustomerSearchFragment {
    List<Customer> search(CustomerSearchCriteria criteria);
}

public interface CustomerReportFragment {
    long countCreatedBetween(
        LocalDateTime from,
        LocalDateTime to
    );
}

public interface CustomerArchiveFragment {
    int archiveInactiveBefore(LocalDateTime cutoff);
}
~~~

Các implementation tương ứng:

~~~text
CustomerSearchFragmentImpl
CustomerReportFragmentImpl
CustomerArchiveFragmentImpl
~~~

Mỗi implementation chịu trách nhiệm cho đúng nhóm method. Điều này giúp:

- Giảm một class implementation quá lớn.
- Phân tách query tìm kiếm, báo cáo và cập nhật hàng loạt.
- Dễ kiểm thử từng phần.
- Tái sử dụng fragment.
- Thay đổi một nhóm hành vi mà ít ảnh hưởng phần còn lại.

Một fragment có thể sử dụng EntityManager, Criteria API, JdbcTemplate hoặc một dependency khác được Spring inject. Chọn công cụ theo loại query và nhu cầu kiểm soát SQL.

## 7. Spring Data ghép fragment theo thứ tự nào?

Thứ tự khai báo fragment trong repository interface có ý nghĩa khi nhiều fragment cung cấp method cùng signature.

Ví dụ:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                PreferredCustomerLookup,
                LegacyCustomerLookup {
}
~~~

Nếu cả PreferredCustomerLookup và LegacyCustomerLookup cùng khai báo một method signature, fragment được khai báo trước có mức ưu tiên cao hơn trong composition. Trong ví dụ, PreferredCustomerLookup được đặt trước LegacyCustomerLookup.

Thứ tự composition cũng cho phép custom fragment ghi đè hành vi của repository base hoặc một số repository aspect. Custom implementation có ưu tiên cao hơn base implementation trong cơ chế composition, vì vậy có thể thay đổi cách một method kế thừa được xử lý.

Dù có quy tắc ưu tiên, không nên cố tình tạo nhiều method cùng signature nếu có thể thiết kế API rõ ràng hơn. Hãy dùng tên method riêng hoặc gom hành vi vào một fragment có trách nhiệm duy nhất. Khi thật sự cần precedence, ghi rõ thứ tự interface và viết integration test xác nhận implementation được gọi.

## 8. Ví dụ xung đột giữa hai fragment

Giả sử có hai cách tra cứu khách hàng theo mã:

~~~java
public interface FastCustomerLookup {
    Optional<Customer> findByExternalCode(String code);
}

public interface VerifiedCustomerLookup {
    Optional<Customer> findByExternalCode(String code);
}
~~~

Hai implementation có thể thực hiện quy tắc khác nhau:

~~~java
public class FastCustomerLookupImpl
        implements FastCustomerLookup {

    @Override
    public Optional<Customer> findByExternalCode(String code) {
        // Truy vấn nhanh theo index.
        return Optional.empty();
    }
}

public class VerifiedCustomerLookupImpl
        implements VerifiedCustomerLookup {

    @Override
    public Optional<Customer> findByExternalCode(String code) {
        // Tra cứu và áp dụng thêm quy tắc xác minh.
        return Optional.empty();
    }
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                VerifiedCustomerLookup,
                FastCustomerLookup {
}
~~~

Theo thứ tự composition, VerifiedCustomerLookup được ưu tiên khi hai fragment cùng cung cấp signature đó.

Tuy nhiên, đây là thiết kế dễ gây nhầm lẫn cho người đọc. Tên method giống nhau nhưng ý nghĩa khác nhau. Một người gọi findByExternalCode không thể nhìn vào chữ ký để biết có áp dụng xác minh hay không.

Thiết kế rõ hơn là đổi tên theo ý nghĩa:

~~~java
public interface FastCustomerLookup {
    Optional<Customer> findFastByExternalCode(String code);
}

public interface VerifiedCustomerLookup {
    Optional<Customer> findVerifiedByExternalCode(String code);
}
~~~

Khi đó caller chọn rõ hành vi mong muốn và không phụ thuộc thứ tự fragment.

## 9. Method trùng với CRUD method của JpaRepository

Custom fragment có thể định nghĩa method trùng với method của base repository nếu chữ ký tương thích và mục đích là thay đổi hành vi.

Ví dụ JpaRepository cung cấp method save với chữ ký generic. Một fragment có thể khai báo cùng hợp đồng:

~~~java
public interface CustomizedSave<T> {
    <S extends T> S save(S entity);
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomizedSave<Customer> {
}
~~~

Implementation fragment phải thực hiện đúng hợp đồng generic của save. Trước khi thay đổi save, cần xem xét đầy đủ semantics của JPA:

- Entity mới cần persist.
- Entity detached có thể cần merge.
- Entity đang managed có thể không cần thao tác bổ sung.
- ID được sinh có thể chỉ có sau persist/flush tùy strategy.
- Cascade, lifecycle callback và optimistic locking phải được giữ đúng.
- Return value phải phản ánh instance theo hợp đồng JPA/repository mà ứng dụng mong đợi.

Không thay save bằng một lời gọi persist đơn giản cho mọi trạng thái. persist và merge có semantics khác nhau; implementation sai có thể gây lỗi detached entity, duplicate key hoặc trả về instance không đúng.

Nếu chỉ cần thêm hành vi trước/sau khi lưu, cân nhắc service method, domain event, entity callback hoặc một method fragment riêng như saveWithAudit thay vì thay toàn bộ save.

## 10. Java phân biệt overload và duplicate signature như thế nào?

Cần phân biệt ba trường hợp:

**Trường hợp A: khác danh sách tham số**

~~~java
Optional<Customer> findByExternalCode(String code);

Optional<Customer> findByExternalCode(
    String code,
    boolean activeOnly
);
~~~

Đây là overload hợp lệ vì danh sách tham số khác nhau.

**Trường hợp B: chỉ khác kiểu trả về**

~~~java
Customer findByExternalCode(String code);

List<Customer> findByExternalCode(String code);
~~~

Đây không phải hai overload hợp lệ trong Java. Java không cho phép phân biệt method chỉ bằng kiểu trả về. Hai khai báo có cùng tên và cùng danh sách tham số gây name clash hoặc lỗi biên dịch.

**Trường hợp C: cùng signature được kế thừa từ nhiều interface**

Nếu nhiều interface khai báo cùng signature và kiểu trả về tương thích, một implementation method có thể đáp ứng hợp đồng chung. Nếu kiểu trả về không tương thích, compiler có thể báo lỗi.

Ví dụ return type covariant có thể hợp lệ khi kiểu trả về cụ thể là subtype tương thích:

~~~java
interface BaseLookup {
    Object lookup(String key);
}

interface CustomerLookup {
    Customer lookup(String key);
}
~~~

Một class triển khai cả hai có thể cung cấp:

~~~java
public Customer lookup(String key) {
    // Customer là subtype của Object.
    return null;
}
~~~

Ngược lại, hai kiểu trả về không có quan hệ tương thích không thể được giải quyết chỉ bằng thứ tự fragment. Đây là lỗi ở hệ thống kiểu Java trước khi Spring Data xây repository.

## 11. Bảng phân biệt các tình huống method collision

| Tình huống | Java compile? | Cách xử lý |
|---|---|---|
| Cùng tên, khác tham số | Có thể | Overload nếu chữ ký hợp lệ |
| Cùng tên, cùng tham số, chỉ khác return type | Không | Đổi tên hoặc hợp nhất chữ ký |
| Cùng signature trong hai interface, return tương thích | Có thể | Một implementation đáp ứng hợp đồng |
| Cùng signature trong hai interface, return không tương thích | Thường không | Sửa API/type hierarchy |
| Hai fragment có cùng method signature | Có thể | Xác định thứ tự composition và kiểm thử |
| Fragment trùng method base repository | Có thể nếu chữ ký tương thích | Custom fragment có thể override base behavior |
| Query method và fragment method cùng tên | Có thể gây mơ hồ | Tránh collision hoặc kiểm thử rõ resolution |

Thứ tự fragment chỉ giải quyết việc chọn implementation trong composition khi các chữ ký đã hợp lệ về mặt Java. Nó không thể chữa lỗi compile do hai method chỉ khác kiểu trả về.

## 12. Khi nhiều fragment có method cùng tên nhưng khác ý nghĩa

Đừng chỉ dựa vào việc fragment nào được khai báo trước để che giấu một API không rõ ràng.

Ví dụ hai method cùng tên findActive:

- Một fragment lọc theo cờ active trong database.
- Một fragment kiểm tra trạng thái hoạt động theo thời gian.
- Một fragment còn kiểm tra trạng thái tài khoản từ hệ thống bên ngoài.

Dù cùng trả Optional<Customer>, ý nghĩa nghiệp vụ khác nhau. Nên đặt tên phản ánh hành vi:

- findByActiveFlag
- findCurrentlyAvailable
- findVerifiedActiveCustomer

Tên method tốt giúp người gọi hiểu điều kiện mà không cần mở implementation. Nếu hành vi có cùng tên nhưng khác chiến lược thực thi, hãy dùng một method với strategy/configuration rõ ràng thay vì hai fragment cạnh tranh.

## 13. Method khai báo trực tiếp trong repository interface

Repository interface có thể khai báo query method trực tiếp:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Query("""
        select c
        from Customer c
        where lower(c.email) = lower(:email)
        """)
    Optional<Customer> findEmailIgnoreCase(
        @Param("email") String email
    );
}
~~~

Các method này thuộc cơ chế query lookup của Spring Data. Nếu một method cùng signature cũng xuất hiện trong custom fragment, người đọc khó biết ý định thiết kế và việc phân giải có thể không giống điều mong đợi nếu không hiểu composition.

Khuyến nghị:

- Không khai báo cùng method trong repository interface và fragment nếu không có chủ đích rõ ràng.
- Nếu method là query khai báo đơn giản, đặt trực tiếp trong repository interface.
- Nếu method cần custom implementation, đặt trong fragment interface và để repository kế thừa fragment.
- Nếu muốn thay đổi method base, dùng fragment override có chủ đích và test.
- Tránh để query method và custom fragment cạnh tranh cùng một tên/chữ ký.

## 14. Custom fragment khác custom repository base class thế nào?

Hai cơ chế này giải quyết phạm vi khác nhau.

**Custom fragment** bổ sung một nhóm hành vi vào repository cụ thể hoặc nhiều repository được chọn. Đây thường là lựa chọn tốt cho chức năng tìm kiếm nâng cao, bulk action hoặc báo cáo.

**Custom repository base class** thay đổi implementation nền cho nhiều repository cùng sử dụng. Ví dụ, ứng dụng muốn mọi repository có một method chung để flush sau khi save hoặc áp dụng một quy tắc kỹ thuật thống nhất.

Bảng so sánh:

| Tiêu chí | Fragment | Custom base class |
|---|---|---|
| Phạm vi | Repository được khai báo kế thừa fragment | Các repository dùng base class cấu hình |
| Tái sử dụng | Ghép chọn lọc | Áp dụng rộng |
| Tổ chức | Nhiều interface/implementation nhỏ | Một lớp nền kế thừa SimpleJpaRepository |
| Override CRUD | Có thể qua fragment | Có thể override base method |
| Phù hợp | Tính năng theo nhóm nghiệp vụ | Hành vi nền dùng chung |
| Độ ảnh hưởng | Cục bộ | Có thể ảnh hưởng nhiều repository |

Không tạo custom base class chỉ để thêm một method cho một repository. Ngược lại, không cần khai báo cùng một fragment ở hàng chục repository nếu đó thực chất là hành vi nền bắt buộc của toàn bộ repository.

## 15. Ví dụ custom repository base class

Một base class tùy chỉnh có thể kế thừa SimpleJpaRepository:

~~~java
public class CustomJpaRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID> {

    public CustomJpaRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {
        super(entityInformation, entityManager);
    }

    // Có thể override hoặc bổ sung hành vi dùng chung.
}
~~~

Cấu hình:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "example.repository",
    repositoryBaseClass = CustomJpaRepositoryImpl.class
)
public class JpaConfiguration {
}
~~~

Constructor phải tương thích với cách Spring Data tạo repository base class trong phiên bản đang dùng. Kiểm tra API của release train và giữ constructor cần thiết.

Base class nên tập trung vào hành vi thật sự dùng chung. Đừng đặt logic nghiệp vụ riêng của Customer vào base class dùng cho Product, Order và Invoice.

Nếu chỉ một số repository cần method đặc biệt, fragment dễ kiểm soát phạm vi hơn.

## 16. Fragment có thể dùng EntityManager và Criteria API

Custom fragment thường hữu ích khi query không thể diễn đạt gọn bằng derived query hoặc @Query.

Ví dụ một fragment tìm Customer theo nhiều điều kiện:

~~~java
public interface CustomerSearchFragment {
    List<Customer> search(CustomerSearchCriteria criteria);
}
~~~

Implementation minh họa:

~~~java
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    private final EntityManager entityManager;

    public CustomerSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Customer> search(CustomerSearchCriteria criteria) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Customer> query =
            cb.createQuery(Customer.class);
        Root<Customer> customer = query.from(Customer.class);

        List<Predicate> predicates = new ArrayList<>();

        if (criteria.email() != null) {
            predicates.add(
                cb.equal(customer.get("email"), criteria.email())
            );
        }

        if (criteria.active() != null) {
            predicates.add(
                cb.equal(customer.get("active"), criteria.active())
            );
        }

        if (!predicates.isEmpty()) {
            query.where(predicates.toArray(Predicate[]::new));
        }

        query.orderBy(
            cb.asc(customer.get("lastName")),
            cb.asc(customer.get("id"))
        );

        return entityManager.createQuery(query).getResultList();
    }
}
~~~

Ví dụ giả định CustomerSearchCriteria là DTO có email và Boolean active; entity Customer có các property tương ứng. Trong code thực tế cần bổ sung import và mapping phù hợp.

Fragment có thể dùng JPQL, Criteria API, native SQL hoặc JdbcTemplate. Hãy chọn cách phù hợp với yêu cầu kiểu dữ liệu, khả năng portable và hiệu năng.

## 17. Transaction trong custom fragment

Không nên mặc định mọi method custom fragment đều nhận transaction giống method CRUD kế thừa.

Các method CRUD được Spring Data cung cấp có transaction configuration mặc định theo repository implementation. Query method khai báo và custom fragment method có thể cần transaction được cấu hình rõ ràng.

Ví dụ fragment chỉ đọc:

~~~java
@Transactional(readOnly = true)
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    // EntityManager và các method truy vấn.
}
~~~

Ví dụ fragment ghi dữ liệu:

~~~java
@Transactional
public class CustomerArchiveFragmentImpl
        implements CustomerArchiveFragment {

    // Thực hiện bulk update hoặc thao tác ghi.
}
~~~

Có thể đặt @Transactional trên method cụ thể thay vì cả class nếu các method có nhu cầu khác nhau.

Nếu service điều phối nhiều repository hoặc nhiều fragment trong một use case, transaction boundary ở service thường rõ ràng hơn. Tránh mở transaction riêng lẻ không cần thiết khiến một nghiệp vụ nhiều bước không còn atomic.

Đối với bulk update/delete bằng JPQL, cần hiểu persistence context không tự đồng bộ trạng thái từng entity đang managed sau khi query bulk chạy. Có thể cần clear/refresh hoặc thiết kế transaction phù hợp.

## 18. Dependency injection và package scanning

Implementation fragment là thành phần Spring được phát hiện trong quá trình tạo repository. Constructor injection giúp khai báo dependency rõ ràng:

~~~java
public class CustomerReportFragmentImpl
        implements CustomerReportFragment {

    private final EntityManager entityManager;
    private final Clock clock;

    public CustomerReportFragmentImpl(
            EntityManager entityManager,
            Clock clock) {
        this.entityManager = entityManager;
        this.clock = clock;
    }
}
~~~

Lưu ý:

- Đặt implementation ở package được Spring Data repository scanning phát hiện.
- Tên class phải khớp fragment interface và postfix.
- Repository phải kế thừa fragment interface.
- Dependency phải là bean Spring hợp lệ.
- Tránh dependency vòng giữa fragment và chính repository đang chứa fragment.
- Dùng constructor injection thay vì field injection để dễ kiểm thử.

Nếu implementation class không được phát hiện, kiểm tra tên, package, postfix và phạm vi @EnableJpaRepositories trước khi đổi kiến trúc.

## 19. Legacy single custom implementation và fragment hiện đại

Spring Data từng hỗ trợ một class implementation tùy chỉnh cho toàn bộ repository theo quy ước tên repository cộng Impl.

Ví dụ:

~~~text
CustomerRepository
CustomerRepositoryImpl
~~~

Mô hình này có thể vẫn xuất hiện trong codebase cũ. Tuy nhiên, khi repository có nhiều nhóm chức năng, một class duy nhất dễ trở nên lớn và gắn chặt với một repository.

Mô hình fragment tách nhỏ hơn:

~~~text
CustomerRepository
CustomerSearchFragment
CustomerSearchFragmentImpl
CustomerReportFragment
CustomerReportFragmentImpl
~~~

Ưu điểm của fragment:

- Mỗi phần có interface rõ ràng.
- Có thể tái sử dụng giữa repository.
- Có thể ghép nhiều implementation.
- Dễ xác định trách nhiệm và kiểm thử.
- Có thể kiểm soát precedence khi cần override.

Khi bảo trì hệ thống cũ, không nhất thiết phải viết lại ngay. Hãy chuyển dần các nhóm chức năng độc lập sang fragment khi có nhu cầu thay đổi hoặc tái sử dụng. Tránh để cả single custom implementation và fragment cùng xử lý một method signature mà không có quy tắc rõ.

## 20. Generic repository và @NoRepositoryBean

Có thể tạo một interface nền dùng chung:

~~~java
@NoRepositoryBean
public interface AuditableRepository<T, ID>
        extends JpaRepository<T, ID> {

    List<T> findCreatedAfter(Instant timestamp);
}
~~~

@NoRepositoryBean báo cho Spring Data rằng đây là repository base interface, không tạo bean repository độc lập cho interface generic này.

Repository cụ thể:

~~~java
public interface CustomerRepository
        extends AuditableRepository<Customer, Long> {
}
~~~

Nếu method chung cần implementation custom, có thể tạo fragment generic hoặc custom base class. Chọn theo phạm vi:

- Fragment nếu repository cụ thể chủ động ghép hành vi.
- Custom base class nếu mọi repository trong cấu hình cần cùng implementation.
- Query method generic chỉ khi property/type mapping thực sự thống nhất.

Không khai báo repository generic làm bean cụ thể khi chưa có domain type, vì Spring Data không thể xác định entity và ID để tạo repository.

## 21. Xử lý collision theo quy trình

Khi phát hiện hai fragment hoặc fragment và base repository có method trùng, hãy kiểm tra theo thứ tự:

1. So sánh tên method và danh sách tham số sau type erasure.
2. Kiểm tra kiểu trả về có tương thích hay không.
3. Xác định method có phải overload hợp lệ hay chỉ khác return type.
4. Xác định các fragment nào khai báo method đó.
5. Xem thứ tự fragment trong repository interface.
6. Kiểm tra method có đồng thời được khai báo trực tiếp với @Query hay derived query không.
7. Xác định có chủ đích override base implementation hay không.
8. Nếu hai hành vi khác nhau, đổi tên method để thể hiện rõ nghiệp vụ.
9. Nếu cần precedence, sắp xếp fragment theo thứ tự rõ ràng.
10. Viết integration test để xác nhận implementation thực sự được gọi.

Đừng giải quyết collision chỉ bằng cách đổi thứ tự interface mà không ghi lại ý định. Một lần refactor thêm fragment mới có thể vô tình đổi implementation được chọn.

## 22. Kiểm thử fragment và precedence

Một bộ test nên kiểm tra cả kết quả và implementation thực tế.

Ví dụ test repository:

~~~java
@DataJpaTest
class CustomerRepositoryFragmentTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void customSearchFragmentIsAvailable() {
        List<Customer> results =
            repository.search(new CustomerSearchCriteria(
                "a@example.com",
                true
            ));

        assertEquals(1, results.size());
    }
}
~~~

Test này giả định fixture đã được chuẩn bị và CustomerSearchCriteria có constructor tương ứng.

Với collision, hãy tạo hai fragment trả về kết quả khác nhau hoặc dùng spy/test double phù hợp để xác nhận fragment được ưu tiên. Không chỉ kiểm tra rằng repository khởi động thành công; cần xác nhận method được dispatch đến đúng implementation.

Các trường hợp cần test:

- Tất cả fragment được phát hiện.
- Constructor dependencies được inject.
- Custom method trả kết quả đúng.
- Method trùng giữa hai fragment chọn implementation theo thứ tự mong đợi.
- Fragment override base method có semantics chính xác.
- Transaction rollback khi custom method ghi lỗi.
- Bulk operation và persistence context được xử lý đúng.
- Query phân trang và count query không bị ảnh hưởng bởi fragment khác.
- Generic fragment hoạt động với từng entity type.
- Repository base class tùy chỉnh được áp dụng đúng phạm vi.

## 23. Lỗi thường gặp và cách khắc phục

**1. Fragment implementation không được phát hiện**

Kiểm tra implementation có tên fragment interface cộng postfix hay không, nằm trong package được quét hay không, và repository có kế thừa fragment interface không.

**2. Tạo class UserRepositoryImpl nhưng Spring vẫn không dùng**

Nếu đang theo mô hình fragment, class implementation phải khớp tên fragment interface. UserRepositoryImpl thuộc quy ước single custom implementation cũ, không thay thế tự động mọi fragment.

**3. Hai method chỉ khác kiểu trả về**

Java không cho overload chỉ bằng return type. Đổi tên, thay tham số hoặc hợp nhất thành một method với kiểu trả về phù hợp.

**4. Hai fragment cùng signature trả kết quả khác nhau**

Kiểm tra thứ tự khai báo fragment. Tốt hơn nên đổi tên method nếu ý nghĩa khác nhau; nếu chủ đích override, viết integration test xác nhận precedence.

**5. Custom fragment không override method CRUD như mong đợi**

Kiểm tra chữ ký generic có tương thích với base method không, fragment có được phát hiện không và method có bị query declaration khác cạnh tranh không.

**6. Method ghi chạy ngoài transaction**

Cấu hình @Transactional trên custom fragment method/class hoặc đặt transaction boundary ở service.

**7. EntityManager hoạt động nhưng dữ liệu chưa được đồng bộ**

Kiểm tra flush, clear và trạng thái persistence context, đặc biệt sau bulk update/delete.

**8. Nhiều fragment phụ thuộc lẫn nhau**

Xem lại ranh giới trách nhiệm. Fragment nên phụ thuộc service/repository khác theo thiết kế rõ ràng, tránh vòng dependency và tránh gọi lại chính repository composition gây đệ quy.

**9. Custom base class ảnh hưởng repository không mong muốn**

Kiểm tra repository scanning configuration và phạm vi basePackages. Dùng fragment nếu chỉ một số repository cần hành vi đó.

**10. Refactor fragment làm đổi hành vi method trùng**

Kiểm tra thứ tự interface và test precedence. Đừng dựa vào tên class hoặc thứ tự file trong package.

## 24. Quy trình thiết kế repository composition

Khi thêm chức năng tùy chỉnh:

1. Xác định nhóm hành vi có độc lập với CRUD không.
2. Nếu chỉ là một query đơn giản, cân nhắc derived query hoặc @Query trước.
3. Nếu cần implementation tùy chỉnh, tạo fragment interface riêng.
4. Đặt implementation theo tên interface cộng postfix.
5. Inject EntityManager hoặc dependency qua constructor.
6. Đưa fragment interface vào danh sách extends của repository.
7. Nếu cần nhiều fragment, giữ mỗi fragment một trách nhiệm rõ.
8. Kiểm tra method signature giữa các fragment và base interface.
9. Tránh method trùng nếu ý nghĩa nghiệp vụ khác nhau.
10. Nếu cố ý override, sắp xếp fragment theo precedence và ghi rõ lý do.
11. Cấu hình transaction cho method custom.
12. Dùng custom base class chỉ khi hành vi thực sự dùng chung cho nhiều repository.
13. Viết integration test cho discovery, kết quả, transaction và precedence.
14. Kiểm tra cấu hình package/postfix khi nâng cấp Spring Data.

## 25. Checklist tự đánh giá

- [ ] Tôi giải thích được repository composition.
- [ ] Tôi phân biệt base repository, custom fragment và query method.
- [ ] Tôi biết fragment gồm interface và implementation.
- [ ] Tôi đặt tên implementation theo interface cộng postfix.
- [ ] Tôi biết thay đổi repositoryImplementationPostfix.
- [ ] Tôi biết kết hợp nhiều fragment trong một repository.
- [ ] Tôi hiểu thứ tự fragment ảnh hưởng precedence.
- [ ] Tôi biết custom fragment có thể override base implementation khi chữ ký tương thích.
- [ ] Tôi phân biệt overload hợp lệ với duplicate signature.
- [ ] Tôi hiểu Java không cho overload chỉ khác return type.
- [ ] Tôi biết xử lý method trùng giữa nhiều interface.
- [ ] Tôi phân biệt fragment với custom repository base class.
- [ ] Tôi biết khi nào dùng @NoRepositoryBean.
- [ ] Tôi cấu hình transaction cho custom method.
- [ ] Tôi hiểu EntityManager, flush và bulk operation trong fragment.
- [ ] Tôi kiểm thử fragment discovery và method precedence.
- [ ] Tôi tránh để legacy implementation và fragment cùng cạnh tranh một method.

## 26. Câu hỏi ôn tập

**1. Repository fragment là gì?**

Là một phần chức năng repository có interface và implementation riêng, được ghép vào repository chính bằng cách kế thừa fragment interface.

**2. Một repository có thể kết hợp bao nhiêu fragment?**

Có thể kết hợp nhiều fragment. Nên chia theo trách nhiệm rõ ràng và tránh tạo quá nhiều fragment nhỏ không có giá trị tái sử dụng.

**3. Implementation fragment được tìm theo tên nào?**

Mặc định là tên fragment interface cộng hậu tố Impl, ví dụ CustomerSearchFragmentImpl. Hậu tố có thể được cấu hình bằng repositoryImplementationPostfix.

**4. Nếu hai fragment có cùng method signature thì sao?**

Thứ tự fragment trong repository composition quyết định ưu tiên; fragment khai báo trước có mức ưu tiên cao hơn khi có xung đột. Hãy tránh collision không cần thiết và kiểm thử khi chủ đích dựa vào precedence.

**5. Spring Data có thể dùng fragment để override save không?**

Có thể nếu fragment khai báo hợp đồng tương thích với method base. Nhưng implementation phải giữ semantics persist/merge, lifecycle, cascade, ID và locking; không thay save bằng persist đơn giản.

**6. Java có cho hai method cùng tên, cùng tham số nhưng khác return type không?**

Không. Java không phân biệt overload bằng kiểu trả về. Hai khai báo đó gây lỗi compile/name clash.

**7. Khác biệt giữa fragment và custom base class là gì?**

Fragment được ghép chọn lọc vào repository. Custom base class thay implementation nền cho các repository thuộc cấu hình dùng base class đó.

**8. Khi nào nên dùng custom base class?**

Khi một hành vi kỹ thuật thật sự cần áp dụng chung cho nhiều repository, ví dụ một quy tắc persistence thống nhất. Nếu chỉ một vài repository cần chức năng, fragment thường phù hợp hơn.

**9. Vì sao cần test method precedence?**

Repository có thể khởi động thành công nhưng method vẫn được dispatch đến fragment khác với ý định. Test xác nhận implementation thực tế và bảo vệ hành vi khi refactor.

**10. Có nên giữ hai fragment cùng tên method nhưng ý nghĩa khác nhau không?**

Thường không. Đổi tên theo hành vi nghiệp vụ để caller chọn rõ chức năng, giảm phụ thuộc vào thứ tự composition.

Thiết kế fragment tốt giúp repository có thể mở rộng theo từng nhóm chức năng mà vẫn giữ ranh giới rõ. Khi hiểu quy tắc tên implementation, thứ tự composition và giới hạn overload của Java, bạn có thể xử lý method collision có chủ đích và kiểm thử được hành vi cuối cùng.

## Tài liệu tham khảo

- [Spring Data JPA — Custom Repository Implementations](https://docs.spring.io/spring-data/jpa/reference/repositories/custom-implementations.html)
- [Spring Data Commons — Repository Composition](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
