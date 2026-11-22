# Vai trò của Querydsl và lựa chọn so với Specification

Querydsl và Spring Data JPA Specification đều giúp xây dựng truy vấn động từ nhiều điều kiện tìm kiếm. Điểm khác nhau nằm ở cách mô tả truy vấn: Querydsl cung cấp DSL có kiểu dữ liệu rõ ràng với các lớp Q được sinh từ Entity, còn Specification sử dụng JPA Criteria API để tạo các predicate có thể kết hợp.

Querydsl thường hấp dẫn khi truy vấn có nhiều JOIN, biểu thức, subquery hoặc projection và nhóm phát triển muốn viết truy vấn theo phong cách fluent, dễ đọc. Specification phù hợp khi chủ yếu cần ghép các điều kiện lọc có thể tái sử dụng, muốn dựa trên API Criteria chuẩn của JPA và hạn chế phụ thuộc thư viện ngoài.

Không có lựa chọn nào luôn nhanh hơn. Cả hai đều được chuyển thành truy vấn mà JPA provider thực thi trên database. Hãy chọn theo độ phức tạp truy vấn, yêu cầu type safety, cách tổ chức code, khả năng bảo trì và hệ sinh thái dependency của dự án.

## 1. Querydsl giải quyết bài toán gì?

Trong một màn hình tìm kiếm khách hàng, người dùng có thể nhập tên, email, trạng thái hoạt động và khoảng thời gian đăng ký. Mỗi tham số là tùy chọn nên câu truy vấn cần thay đổi theo dữ liệu đầu vào.

Nếu dùng nhiều method Repository cố định, số lượng method có thể tăng nhanh:

~~~java
findByNameContaining(String name);
findByEmail(String email);
findByActive(Boolean active);
findByNameContainingAndActive(String name, Boolean active);
findByEmailAndActive(String email, Boolean active);
// Còn nhiều tổ hợp khác...
~~~

Nếu dùng một câu JPQL tĩnh với nhiều điều kiện dạng tham số null, câu truy vấn có thể trở nên dài và khó tối ưu. Querydsl cho phép ghép predicate theo từng điều kiện thực sự được cung cấp.

Querydsl là thư viện Java để xây dựng truy vấn bằng API fluent. Với Querydsl JPA, các biểu thức được tạo từ mô hình Entity và được chuyển thành JPQL để JPA provider thực thi. Querydsl cũng có các module khác, ví dụ Querydsl SQL; cần phân biệt Querydsl JPA với việc viết SQL trực tiếp.

## 2. Q-type được sinh từ Entity

Querydsl sử dụng annotation processor để sinh các lớp metamodel có tiền tố Q từ các Entity. Ví dụ Entity Customer thường tạo ra lớp QCustomer.

Entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private String email;
    private Boolean active;

    protected Customer() {
    }

    public Customer(String name, String email, Boolean active) {
        this.name = name;
        this.email = email;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public Boolean getActive() {
        return active;
    }
}
~~~

Sau khi chạy build với Querydsl annotation processor, mã nguồn được sinh có thể được sử dụng như sau:

~~~java
QCustomer customer = QCustomer.customer;
~~~

QCustomer cung cấp các path có kiểu tương ứng với thuộc tính Entity, ví dụ customer.name, customer.email, customer.active và customer.id.

Điểm mạnh là IDE có thể gợi ý thuộc tính và compiler có thể phát hiện nhiều lỗi sai tên hoặc sai kiểu ngay lúc biên dịch. Nếu đổi tên thuộc tính Entity và build lại, code sử dụng Q-type cũ sẽ báo lỗi để được cập nhật.

Q-type là mã được sinh trong quá trình build; thông thường không cần tự viết hoặc sửa trực tiếp lớp Q. Hãy bảo đảm thư mục generated sources được cấu hình đúng và được IDE/build tool nhận diện.

## 3. Cấu hình Querydsl cho dự án Spring Data JPA

Để dùng Querydsl JPA, dự án cần:

1. Dependency Querydsl JPA tương thích với phiên bản Java, Spring Data và JPA provider.
2. Querydsl annotation processor để sinh Q-type từ Entity.
3. Cấu hình build tool để đưa generated sources vào compilation.
4. Phiên bản artifact tương thích với namespace persistence của dự án.

Với Spring Boot 3 và Jakarta Persistence, cần chọn artifact Querydsl dùng namespace Jakarta (thường được phân phối qua classifier jakarta ở các dòng phiên bản Querydsl tương ứng). Dự án Spring Boot 2 dùng javax.persistence cần bộ artifact phù hợp với namespace cũ. Không trộn Q-type hoặc processor dùng javax với ứng dụng dùng jakarta.

Tên dependency và cấu hình annotation processor có thể khác giữa Maven, Gradle và phiên bản Querydsl. Hãy dùng cùng một phiên bản Querydsl cho runtime và annotation processor, kiểm tra repository dependency management của dự án và chạy clean build để xác nhận Q-type được sinh.

Một lệnh build Maven thường là:

~~~bash
./mvnw clean compile
~~~

Với Gradle:

~~~bash
./gradlew clean compileJava
~~~

Tên lệnh có thể thay đổi theo wrapper của dự án. Mục đích của clean build là xác nhận generated source được tạo lại từ Entity hiện tại, tránh phụ thuộc vào Q-type cũ còn sót trong thư mục build.

## 4. Dùng QuerydslPredicateExecutor với Spring Data

Spring Data JPA tích hợp Querydsl qua QuerydslPredicateExecutor. Repository chỉ cần kế thừa interface này để có các thao tác truy vấn bằng Predicate.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Các thao tác thường dùng gồm:

- findOne(predicate): tìm một kết quả phù hợp.
- findAll(predicate): lấy các Entity phù hợp.
- findAll(predicate, sort): lấy và sắp xếp kết quả.
- findAll(predicate, pageable): lấy một Page.
- count(predicate): đếm kết quả phù hợp.
- exists(predicate): kiểm tra có kết quả phù hợp hay không.

Ví dụ tạo điều kiện tìm kiếm động:

~~~java
import com.querydsl.core.BooleanBuilder;

public Page<Customer> search(
        String name,
        String email,
        Boolean active,
        Pageable pageable) {

    QCustomer customer = QCustomer.customer;
    BooleanBuilder predicate = new BooleanBuilder();

    if (name != null && !name.isBlank()) {
        predicate.and(customer.name.containsIgnoreCase(name));
    }

    if (email != null && !email.isBlank()) {
        predicate.and(customer.email.equalsIgnoreCase(email));
    }

    if (active != null) {
        predicate.and(customer.active.eq(active));
    }

    return customerRepository.findAll(predicate, pageable);
}
~~~

BooleanBuilder cho phép thêm điều kiện theo từng tham số. containsIgnoreCase tạo điều kiện tìm chuỗi con không phân biệt hoa thường; equalsIgnoreCase so sánh chuỗi không phân biệt hoa thường; eq so sánh theo giá trị chính xác của thuộc tính.

Khi không có điều kiện nào được thêm, BooleanBuilder rỗng có thể biểu diễn predicate không có điều kiện WHERE tùy cách Querydsl/provider xử lý. Nếu nghiệp vụ không cho phép tìm toàn bộ dữ liệu, hãy kiểm tra đầu vào và từ chối truy vấn rỗng ở tầng service.

## 5. BooleanExpression và ghép predicate

Ngoài BooleanBuilder, Querydsl có thể ghép các BooleanExpression trực tiếp:

~~~java
QCustomer customer = QCustomer.customer;

BooleanExpression predicate =
        customer.active.isTrue()
                .and(customer.name.containsIgnoreCase("an"))
                .and(customer.email.endsWithIgnoreCase("@example.com"));

List<Customer> result = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .fetch();
~~~

Các phương thức and(), or() và not() giúp thể hiện quan hệ logic:

~~~java
BooleanExpression nameMatches =
        customer.name.containsIgnoreCase(keyword);

BooleanExpression emailMatches =
        customer.email.containsIgnoreCase(keyword);

BooleanExpression search =
        nameMatches.or(emailMatches)
                   .and(customer.active.isTrue());
~~~

Biểu thức cuối tương ứng với:

~~~text
(nameMatches OR emailMatches) AND active = true
~~~

Việc dùng biến trung gian giúp thể hiện nhóm điều kiện rõ ràng và giảm lỗi do kết hợp AND/OR sai thứ tự. Querydsl expression là immutable theo cách sử dụng thông thường: các phép kết hợp trả về biểu thức mới để tiếp tục xây dựng predicate.

## 6. Khi cần truy vấn phức tạp hơn: JPAQueryFactory

QuerydslPredicateExecutor phù hợp với các thao tác tìm Entity theo predicate và các kiểu trả về cơ bản. Khi cần kiểm soát SELECT, JOIN, projection, GROUP BY, subquery hoặc fetch join, có thể dùng JPAQueryFactory trong custom repository.

Cấu hình bean:

~~~java
import com.querydsl.jpa.impl.JPAQueryFactory;
import jakarta.persistence.EntityManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Ví dụ truy vấn:

~~~java
QCustomer customer = QCustomer.customer;

List<Customer> customers = queryFactory
        .selectFrom(customer)
        .where(
                customer.active.isTrue(),
                customer.name.containsIgnoreCase(keyword)
        )
        .orderBy(customer.name.asc(), customer.id.asc())
        .fetch();
~~~

selectFrom(customer) chọn Entity Customer. where() nhận các predicate; các điều kiện được kết hợp theo AND. orderBy() định nghĩa thứ tự ổn định bằng name rồi id. fetch() thực thi và trả List.

JPAQueryFactory nên được inject vào custom repository hoặc một thành phần persistence có trách nhiệm rõ ràng. Không nên đặt câu truy vấn database trong controller.

## 7. Projection với Querydsl

Nếu API chỉ cần một phần dữ liệu, Querydsl có thể chọn các biểu thức và ánh xạ kết quả sang DTO.

DTO:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        String email
) {
}
~~~

Truy vấn:

~~~java
QCustomer customer = QCustomer.customer;

List<CustomerSummary> summaries = queryFactory
        .select(Projections.constructor(
                CustomerSummary.class,
                customer.id,
                customer.name,
                customer.email
        ))
        .from(customer)
        .where(customer.active.isTrue())
        .orderBy(customer.name.asc())
        .fetch();
~~~

Projections.constructor tạo DTO bằng constructor có thứ tự tham số và kiểu dữ liệu tương ứng với các biểu thức SELECT. Record Java có canonical constructor nên thuận tiện cho DTO chỉ đọc.

Cần kiểm tra thứ tự và kiểu đối số. Nếu constructor không khớp, lỗi có thể xuất hiện lúc thực thi. Với dự án muốn kiểm tra projection mạnh hơn ở thời điểm biên dịch, có thể cân nhắc @QueryProjection và Q-type cho DTO, đổi lại DTO sẽ phụ thuộc annotation Querydsl.

Projection giúp chỉ định rõ dữ liệu cần trả về và tránh hydrate Entity đầy đủ khi không cần. Đây là một lợi thế của custom Querydsl query so với việc chỉ dùng các phương thức cơ bản của QuerydslPredicateExecutor.

## 8. JOIN và fetch join trong Querydsl

Querydsl JPA cho phép viết JOIN theo quan hệ Entity:

~~~java
QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

List<Customer> customers = queryFactory
        .selectFrom(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .distinct()
        .fetch();
~~~

Ví dụ này tìm khách hàng có ít nhất một đơn hàng trạng thái PAID. Nếu một Customer có nhiều đơn hàng phù hợp, JOIN có thể tạo nhiều dòng cho cùng Customer; distinct() giúp loại kết quả Entity trùng lặp.

Nếu muốn tải collection trong cùng truy vấn:

~~~java
List<Customer> customers = queryFactory
        .selectFrom(customer)
        .leftJoin(customer.orders).fetchJoin()
        .where(customer.active.isTrue())
        .distinct()
        .fetch();
~~~

fetchJoin() yêu cầu provider tải quan hệ cùng truy vấn chính, giúp tránh một số trường hợp N+1 khi ứng dụng cần truy cập collection ngay sau đó.

Không nên kết hợp collection fetch join với phân trang một cách tùy tiện. JOIN collection có thể nhân bản dòng SQL, làm phân trang sai ngữ nghĩa hoặc khiến provider tải quá nhiều dữ liệu rồi phân trang trong bộ nhớ. Với danh sách phân trang, cân nhắc lấy Page ID trước rồi tải quan hệ cho tập ID đó, dùng projection hoặc EntityGraph phù hợp.

## 9. Specification là gì?

Spring Data JPA Specification là abstraction để xây dựng predicate bằng JPA Criteria API. Interface Specification<T> có phương thức toPredicate() nhận Root, CriteriaQuery và CriteriaBuilder rồi trả về Predicate.

Repository cần kế thừa JpaSpecificationExecutor:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

Một Specification cho điều kiện tên:

~~~java
import org.springframework.data.jpa.domain.Specification;
import jakarta.persistence.criteria.Predicate;
import java.util.Locale;

public class CustomerSpecifications {

    public static Specification<Customer> nameContains(String name) {
        return (root, query, cb) -> {
            if (name == null || name.isBlank()) {
                return cb.conjunction();
            }

            String pattern =
                    "%" + name.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                    cb.lower(root.<String>get("name")),
                    pattern
            );
        };
    }

    public static Specification<Customer> isActive(Boolean active) {
        return (root, query, cb) -> {
            if (active == null) {
                return cb.conjunction();
            }

            return cb.equal(root.get("active"), active);
        };
    }
}
~~~

Có thể kết hợp:

~~~java
Specification<Customer> specification =
        CustomerSpecifications.nameContains(name)
                .and(CustomerSpecifications.isActive(active));

Page<Customer> page =
        customerRepository.findAll(specification, pageable);
~~~

Specification mô tả điều kiện lọc; Spring Data JPA thực thi nó qua Criteria API. Các Specification nhỏ có thể được tái sử dụng và ghép bằng and(), or() hoặc not().

## 10. Cùng một yêu cầu được viết bằng Querydsl và Specification

Giả sử yêu cầu là tìm khách hàng active, tên chứa từ khóa và email thuộc một domain.

### Querydsl

~~~java
QCustomer customer = QCustomer.customer;

BooleanBuilder predicate = new BooleanBuilder();

if (keyword != null && !keyword.isBlank()) {
    predicate.and(customer.name.containsIgnoreCase(keyword));
}

if (domain != null && !domain.isBlank()) {
    predicate.and(customer.email.endsWithIgnoreCase(domain));
}

predicate.and(customer.active.isTrue());

Page<Customer> result =
        customerRepository.findAll(predicate, pageable);
~~~

### Specification

~~~java
Specification<Customer> specification =
        CustomerSpecifications.nameContains(keyword)
                .and(CustomerSpecifications.isActive(true))
                .and((root, query, cb) -> {
                    if (domain == null || domain.isBlank()) {
                        return cb.conjunction();
                    }

                    return cb.like(
                            cb.lower(root.<String>get("email")),
                            "%" + domain.toLowerCase(Locale.ROOT)
                    );
                });

Page<Customer> result =
        customerRepository.findAll(specification, pageable);
~~~

Cả hai cách đều có thể biểu diễn điều kiện động. Querydsl thường ngắn và trực quan hơn khi có nhiều phép toán trên thuộc tính. Specification dùng Criteria API, có thể dài hơn do phải thao tác qua Root và CriteriaBuilder.

Cần thống nhất semantics đầu vào. Ví dụ endsWithIgnoreCase(domain) và LIKE '%domain' tương đương về ý tưởng nhưng việc escape ký tự wildcard và collation cần được kiểm tra theo implementation.

## 11. So sánh Querydsl và Specification

| Tiêu chí | Querydsl | Specification |
|---|---|---|
| Nền tảng | Thư viện Querydsl | JPA Criteria API qua Spring Data |
| Kiểu an toàn | Q-type sinh từ Entity, kiểm tra thuộc tính và kiểu tốt | Có thể dùng string path; có thể tăng type safety bằng JPA static metamodel |
| Cách viết | Fluent DSL, biểu thức gần với ngôn ngữ truy vấn | Lambda với Root, CriteriaBuilder, Predicate |
| Điều kiện động | BooleanBuilder, BooleanExpression | Ghép Specification bằng and/or/not |
| JOIN và đường dẫn | Cú pháp fluent, dễ đọc | Criteria join và path |
| Projection | Mạnh khi dùng JPAQueryFactory | Có thể dùng multiselect/construct nhưng code Criteria thường dài |
| Subquery | DSL có API riêng | CriteriaBuilder subquery |
| Phân trang cơ bản | QuerydslPredicateExecutor hoặc custom query | JpaSpecificationExecutor |
| Dependency | Cần Querydsl và annotation processor | Không cần thư viện truy vấn ngoài JPA/Spring Data |
| Build | Phải duy trì Q-type generation | Có thể dùng metamodel processor nếu muốn type-safe path |
| Phù hợp | Truy vấn động phức tạp, nhiều join/projection | Bộ lọc động, predicate tái sử dụng, kiến trúc dựa trên chuẩn JPA |

Specification không nhất thiết phải dùng chuỗi tên thuộc tính. Có thể dùng JPA static metamodel như Customer_ để tăng type safety. Tuy nhiên, việc sinh static metamodel cũng cần cấu hình annotation processor và cú pháp Criteria vẫn verbose hơn Querydsl trong nhiều tình huống.

## 12. Ưu điểm và đánh đổi của Querydsl

### Ưu điểm

- Q-type giúp phát hiện sai tên thuộc tính và kiểu biểu thức sớm hơn.
- IDE hỗ trợ autocomplete và refactoring tốt.
- Biểu thức and/or/not rõ ràng, thuận tiện cho điều kiện động.
- JOIN, subquery, aggregate và projection có DSL nhất quán.
- JPAQueryFactory cho phép kiểm soát SELECT và cấu trúc query tốt hơn các phương thức cơ bản của QuerydslPredicateExecutor.
- Có thể dùng cùng một predicate cho nhiều truy vấn phù hợp.

### Đánh đổi

- Phải cấu hình và duy trì annotation processor.
- Build phụ thuộc phiên bản Querydsl và namespace javax/jakarta.
- Q-type được sinh; sau khi đổi Entity cần build lại để cập nhật.
- Thêm dependency và một DSL mà thành viên mới phải học.
- Querydsl JPA vẫn bị giới hạn bởi khả năng của JPQL/JPA provider; tính năng SQL riêng có thể cần native SQL.
- Predicate executor cơ bản không thay thế hoàn toàn custom repository khi cần projection, fetch join hoặc truy vấn báo cáo phức tạp.

Querydsl giúp code truy vấn rõ hơn, nhưng không tự làm câu SQL nhanh hơn. Hiệu năng phụ thuộc SQL cuối cùng, index, dữ liệu, execution plan và transaction.

## 13. Ưu điểm và đánh đổi của Specification

### Ưu điểm

- Dựa trên Criteria API của Jakarta Persistence.
- Không cần Querydsl runtime hoặc Q-type generation.
- Dễ ghép các điều kiện lọc thành module nhỏ.
- Tích hợp trực tiếp với JpaSpecificationExecutor.
- Phù hợp cho API tìm kiếm có nhiều tham số tùy chọn.
- Có thể chia sẻ Specification giữa nhiều service hoặc use case.

### Đánh đổi

- Criteria API thường dài và khó đọc hơn khi query có nhiều JOIN hoặc biểu thức.
- String-based path như root.get("name") dễ sai tên nếu không dùng static metamodel.
- Projection, grouping và query phức tạp có thể khiến Specification khó tổ chức.
- Specification tập trung vào predicate; nếu cần kiểm soát SELECT, fetch plan hoặc cấu trúc truy vấn, custom repository có thể phù hợp hơn.
- Thêm fetch join vào Specification có thể gây tác dụng phụ khi Spring Data tạo count query cho Page; cần kiểm soát riêng truy vấn nội dung và đếm.

Specification không phải lựa chọn yếu hơn. Với bộ lọc động chủ yếu là điều kiện WHERE, nó thường đủ và tránh thêm một thư viện.

## 14. Giới hạn của QuerydslPredicateExecutor

QuerydslPredicateExecutor cung cấp API thuận tiện để tìm Entity theo Predicate, nhưng không phải API truy vấn đầy đủ cho mọi use case.

Các thao tác của nó phù hợp với:
- findAll(predicate)
- findAll(predicate, sort)
- findAll(predicate, pageable)
- findOne(predicate)
- count(predicate)
- exists(predicate)

Khi cần:
- Chọn DTO hoặc interface projection phức tạp.
- JOIN và fetch join có kiểm soát.
- GROUP BY/HAVING.
- Subquery hoặc biểu thức SELECT tùy chỉnh.
- Truy vấn báo cáo.
- Tối ưu count query riêng.
- Lock mode, query hint hoặc cấu trúc truy vấn đặc biệt.

hãy dùng custom repository với JPAQueryFactory hoặc EntityManager. Không nên cố nhồi mọi truy vấn vào QuerydslPredicateExecutor chỉ vì Repository đã kế thừa interface này.

## 15. Tổ chức custom repository với JPAQueryFactory

Có thể tách phần truy vấn phức tạp thành một repository fragment:

~~~java
public interface CustomerSearchRepository {
    List<CustomerSummary> searchSummaries(
            String keyword,
            Boolean active
    );
}
~~~

Implementation:

~~~java
import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Projections;
import com.querydsl.jpa.impl.JPAQueryFactory;

public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public List<CustomerSummary> searchSummaries(
            String keyword,
            Boolean active) {

        QCustomer customer = QCustomer.customer;
        BooleanBuilder predicate = new BooleanBuilder();

        if (keyword != null && !keyword.isBlank()) {
            predicate.and(customer.name.containsIgnoreCase(keyword));
        }

        if (active != null) {
            predicate.and(customer.active.eq(active));
        }

        return queryFactory
                .select(Projections.constructor(
                        CustomerSummary.class,
                        customer.id,
                        customer.name,
                        customer.email
                ))
                .from(customer)
                .where(predicate)
                .orderBy(customer.name.asc(), customer.id.asc())
                .fetch();
    }
}
~~~

Repository chính kế thừa fragment:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                CustomerSearchRepository {
}
~~~

Theo quy ước repository fragment của Spring Data, implementation được đặt tên tương ứng với fragment interface và hậu tố mặc định phù hợp (thường là Impl). Nếu dự án cấu hình repository implementation postfix khác, tên lớp phải theo cấu hình đó.

Cách tổ chức này giữ truy vấn tùy chỉnh ở persistence layer và cho phép Repository chính kết hợp CRUD, predicate query cơ bản và truy vấn projection chuyên biệt.

## 16. Pagination và count với Querydsl

QuerydslPredicateExecutor có thể trả Page khi nhận Pageable:

~~~java
Page<Customer> page =
        customerRepository.findAll(predicate, pageable);
~~~

Spring Data chịu trách nhiệm tạo truy vấn nội dung và count tương ứng. Với predicate đơn giản, đây là cách tiện lợi.

Khi tự viết truy vấn bằng JPAQueryFactory, cần tự quản lý count nếu muốn trả Page:

~~~java
List<Customer> content = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();

Long total = queryFactory
        .select(customer.id.count())
        .from(customer)
        .where(predicate)
        .fetchOne();

return new PageImpl<>(
        content,
        pageable,
        total == null ? 0L : total
);
~~~

Đoạn này giả định truy vấn đếm trực tiếp từ Customer và không có JOIN làm nhân bản dòng. Nếu có JOIN collection, có thể cần count distinct theo ID hoặc một truy vấn đếm riêng tương ứng với kết quả logic.

Không dùng fetchResults() hoặc fetchCount() theo các ví dụ cũ trên mạng mà không kiểm tra phiên bản Querydsl. Các API này đã bị deprecated/loại bỏ trong các dòng Querydsl mới hơn; cách an toàn là viết content query và count query rõ ràng khi cần kiểm soát.

Nếu giao diện không cần totalElements, cân nhắc Slice hoặc một luồng Window/scrolling được hỗ trợ. Không chạy count chỉ để lấy nội dung trang.

## 17. JOIN collection, DISTINCT và N+1

Querydsl không tự loại bỏ các vấn đề ORM thường gặp.

Khi JOIN một collection:
- Một Entity cha có thể xuất hiện trên nhiều dòng SQL.
- Kết quả Entity có thể cần distinct().
- Count có thể cần countDistinct() trên ID.
- Fetch join collection kết hợp pagination cần được thiết kế cẩn thận.

Ví dụ:

~~~java
QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

List<Customer> customers = queryFactory
        .selectFrom(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .distinct()
        .fetch();
~~~

Nếu chỉ cần khách hàng có đơn hàng PAID, EXISTS/subquery có thể là cách biểu đạt khác. Nếu cần tải đơn hàng để sử dụng ngay, fetch join có thể phù hợp nhưng cần kiểm tra kích thước kết quả.

Querydsl chỉ là cách xây dựng query. N+1, lazy loading, duplicate rows, transaction boundary và fetch strategy vẫn phải được xử lý như khi dùng JPQL hoặc Specification.

## 18. Khi nào nên chọn Querydsl?

Querydsl thường là lựa chọn phù hợp khi:

1. Bộ lọc động có nhiều điều kiện tùy chọn và nhiều nhóm AND/OR.
2. Query có nhiều JOIN, subquery, biểu thức hoặc truy vấn theo quan hệ.
3. Cần projection DTO và kiểm soát SELECT.
4. Cần tái sử dụng predicate trong nhiều truy vấn.
5. Nhóm muốn type safety và refactoring hỗ trợ tốt từ Q-type.
6. Dự án đã có Querydsl và chi phí cấu hình/duy trì đã được chấp nhận.

Ví dụ, hệ thống tìm kiếm đơn hàng có thể lọc theo khách hàng, trạng thái, khoảng ngày, tổng tiền, sản phẩm, địa chỉ giao hàng và nhiều tổ hợp điều kiện. Querydsl có thể giúp xây dựng predicate và JOIN rõ ràng hơn.

## 19. Khi nào nên chọn Specification?

Specification thường phù hợp khi:

1. Điều kiện chủ yếu là các predicate WHERE đơn giản.
2. API có nhiều bộ lọc tùy chọn nhưng ít projection hoặc truy vấn báo cáo.
3. Muốn chia nhỏ điều kiện thành các Specification tái sử dụng.
4. Muốn dựa trên JPA Criteria API và hạn chế dependency ngoài.
5. Nhóm đã quen Criteria API hoặc muốn giữ persistence layer theo chuẩn JPA.
6. Truy vấn không cần nhiều thao tác SELECT/JOIN phức tạp.

Ví dụ, màn hình quản trị khách hàng lọc theo tên, trạng thái, ngày tạo và tenant có thể được xây dựng bằng các Specification nhỏ rồi ghép theo nhu cầu.

## 20. Có thể kết hợp Querydsl và Specification không?

Một ứng dụng có thể sử dụng cả hai theo từng nhóm use case, miễn là ranh giới và quy ước rõ ràng.

Ví dụ:
- Specification cho các bộ lọc CRUD và danh sách quản trị đơn giản.
- Querydsl custom repository cho tìm kiếm nhiều JOIN, projection hoặc báo cáo.
- JPQL/@Query cho truy vấn tĩnh ngắn, dễ đọc.
- Native SQL cho tính năng đặc thù database mà JPQL/Querydsl JPA không biểu diễn được.

Không cần chuyển mọi Repository sang Querydsl chỉ vì một truy vấn phức tạp. Cũng không cần ép mọi truy vấn vào Specification nếu Criteria API khiến code khó đọc.

Điều quan trọng là tránh triển khai cùng một điều kiện nghiệp vụ theo nhiều cách không nhất quán. Nếu có logic tenant, soft delete hoặc quyền truy cập, hãy đặt nó ở một lớp có thể được kiểm tra và tái sử dụng trong mọi query path liên quan.

## 21. Kiểm thử Querydsl và Specification

Cả hai cách cần integration test để xác nhận JPA provider tạo truy vấn đúng.

Với Querydsl, nên kiểm tra:
- Q-type được sinh từ Entity hiện tại.
- Predicate có và không có tham số tùy chọn.
- Kết hợp AND/OR đúng logic.
- JOIN không tạo kết quả trùng ngoài ý muốn.
- Projection map đúng kiểu và thứ tự constructor.
- Page totalElements/count đúng khi có JOIN.
- Fetch join không phá phân trang.
- Query chạy được trên database mục tiêu.

Với Specification, nên kiểm tra:
- Mỗi Specification riêng lẻ.
- Ghép and()/or()/not().
- Tham số null hoặc rỗng được xử lý đúng.
- JOIN và DISTINCT.
- Count query khi Specification dùng JOIN.
- Không thêm fetch join làm sai count query.
- Kết quả và thứ tự phân trang.

Một test có thể dùng @DataJpaTest với dữ liệu fixture nhỏ. Với truy vấn có collation, JSON, kiểu database riêng hoặc tối ưu index, cần integration test trên cùng engine với production. Không kết luận hiệu năng từ H2 hoặc chỉ từ thời gian test vài bản ghi.

## 22. Những lỗi thường gặp

**Q-type không được sinh**

Kiểm tra annotation processor, classifier Jakarta/Javax, generated sources directory và clean build. Đừng tự tạo Q-type thủ công để che lỗi cấu hình.

**Runtime và annotation processor không cùng phiên bản**

Dễ gây lỗi biên dịch hoặc khác biệt API. Quản lý version đồng bộ.

**Dùng QuerydslPredicateExecutor cho truy vấn cần projection/fetch join**

Executor chủ yếu cung cấp thao tác theo Predicate. Chuyển sang custom repository với JPAQueryFactory khi cần kiểm soát SELECT và JOIN.

**BooleanBuilder rỗng làm truy vấn không lọc dữ liệu**

Nếu nghiệp vụ không cho phép trả toàn bộ dữ liệu, validate điều kiện đầu vào và từ chối truy vấn rỗng.

**Nhầm Q-type với tên bảng/cột**

QCustomer là metamodel của Entity Customer. Các thuộc tính Q phản ánh mô hình Java; provider vẫn chịu trách nhiệm chuyển thành SQL.

**Specification dùng string path sai tên**

root.get("lastNmae") có thể chỉ phát hiện khi query chạy. Dùng static metamodel nếu muốn tăng type safety.

**Dùng fetch join collection cùng Page**

Có thể nhân bản dòng hoặc làm pagination không đúng. Tách truy vấn ID và truy vấn tải quan hệ nếu cần.

**Đếm trùng khi JOIN**

Xác định cấp độ Entity cần đếm và dùng count distinct theo khóa khi phù hợp.

**Cho rằng Querydsl nhanh hơn Specification**

Hai cách đều tạo truy vấn cho JPA provider. So sánh SQL và execution plan thực tế; DSL không tự tối ưu database.

**Dùng Querydsl JPA cho cú pháp SQL riêng**

Querydsl JPA vẫn làm việc qua mô hình JPA/JPQL. Với CTE, window function hoặc operator database không được hỗ trợ, cân nhắc native SQL hoặc giải pháp chuyên biệt.

## 23. Quy trình ra quyết định

Khi bắt đầu một truy vấn động:

1. Xác định kết quả cần trả Entity, projection hay DTO.
2. Đánh giá số lượng điều kiện và cấu trúc AND/OR.
3. Nếu chỉ là bộ lọc WHERE đơn giản, thử derived query hoặc Specification.
4. Nếu cần DSL type-safe cho nhiều JOIN, subquery và biểu thức, cân nhắc Querydsl.
5. Nếu dùng QuerydslPredicateExecutor nhưng cần projection hoặc fetch join, tạo custom repository với JPAQueryFactory.
6. Nếu truy vấn tĩnh ngắn, @Query JPQL có thể là lựa chọn đơn giản nhất.
7. Nếu cần SQL đặc thù database, dùng native query và cô lập phụ thuộc đó.
8. Kiểm tra dependency, annotation processor và namespace Jakarta/Javax.
9. Viết integration test cho điều kiện tùy chọn, JOIN, projection, count và dữ liệu biên.
10. Đo SQL và execution plan trước khi kết luận cách nào có hiệu năng tốt hơn.

## 24. Kết luận

Querydsl cung cấp DSL truy vấn có kiểu dữ liệu rõ ràng thông qua Q-type được sinh từ Entity. Nó đặc biệt hữu ích cho truy vấn động phức tạp, nhiều JOIN, subquery và projection. Spring Data JPA có thể tích hợp QuerydslPredicateExecutor cho các thao tác Predicate cơ bản; khi cần kiểm soát SELECT và fetch plan, dùng custom repository với JPAQueryFactory.

Specification dựa trên JPA Criteria API, phù hợp với các bộ lọc động có thể tái sử dụng và giúp giảm dependency ngoài. Criteria API thường dài hơn nhưng đủ cho nhiều màn hình tìm kiếm thông thường. Chọn Querydsl khi DSL và type safety đem lại lợi ích rõ ràng; chọn Specification khi predicate là trọng tâm và muốn giữ cách tiếp cận chuẩn JPA. Cả hai có thể cùng tồn tại trong một ứng dụng theo ranh giới use case rõ ràng. Hiệu năng cuối cùng phụ thuộc SQL, index, execution plan và database, không phụ thuộc riêng tên thư viện.
