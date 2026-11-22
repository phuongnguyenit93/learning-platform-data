# Cập nhật annotation processor cho metamodel và Querydsl

Annotation processor là thành phần chạy trong lúc biên dịch Java để phân tích annotation trên entity và sinh mã nguồn hỗ trợ. Trong ứng dụng Spring Data JPA, hai nhóm mã được sinh thường gặp là:

- **JPA static metamodel:** các lớp có hậu tố `_`, ví dụ `Customer_`, dùng với Criteria API để tham chiếu thuộc tính entity có kiểm tra kiểu.
- **Querydsl Q-types:** các lớp có tiền tố `Q`, ví dụ `QCustomer`, dùng để xây dựng predicate và truy vấn có kiểu tĩnh bằng Querydsl.

Các lớp này được sinh từ entity, vì vậy cấu hình processor phải khớp phiên bản Java, Jakarta Persistence, Hibernate, Querydsl và hệ thống build. Khi nâng cấp Spring Boot hoặc Hibernate, chỉ nâng dependency runtime là chưa đủ; cần cập nhật cả processor path và xác nhận mã được sinh lại.

## 1. Annotation processor làm gì?

Trong lúc compile, Java compiler phát hiện các annotation processor được khai báo trên processor path, chuyển thông tin type/annotation cho processor và nhận các file nguồn được sinh thêm. Compiler tiếp tục biên dịch những file này cùng mã nguồn ứng dụng.

Quy trình rút gọn:

```text
Entity Java source
       |
       v
Java compiler + annotation processors
       |
       +--------------------------+
       |                          |
       v                          v
JPA metamodel generator      Querydsl APT
       |                          |
       v                          v
Customer_.java              QCustomer.java
       |                          |
       +-------------+------------+
                     |
                     v
             Compile generated code
                     |
                     v
               Application classes
```

Processor chạy ở build time, không phải lúc ứng dụng khởi động. Dependency processor thường được đặt trong cấu hình `annotationProcessor` của Gradle hoặc `annotationProcessorPaths` của Maven. Không cần đóng gói processor vào runtime chỉ để tạo `Customer_` hoặc `QCustomer`.

Hai loại mã sinh có mục đích khác nhau:

| Mã sinh | Ví dụ | Mục đích |
|---|---|---|
| JPA static metamodel | `Customer_` | Dùng thuộc tính có kiểu trong JPA Criteria API, EntityGraph và các API JPA liên quan |
| Querydsl Q-type | `QCustomer` | Dùng fluent API để xây dựng predicate/query Querydsl |
| Hibernate Processor output | Static metamodel và một số kiểm tra compile-time | Tạo metamodel; các phiên bản mới còn có thể kiểm tra HQL/JPQL ở compile time |

Bật một processor không tự động tạo loại mã sinh của processor khác. Nếu dự án dùng cả Criteria API typed metamodel và Querydsl, hãy cấu hình cả hai processor phù hợp.

## 2. JPA static metamodel và Criteria API

JPA static metamodel biểu diễn thuộc tính entity bằng các field có kiểu. Ví dụ entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String email;

    private CustomerStatus status;

    protected Customer() {
    }
}
```

Processor có thể sinh lớp `Customer_` tương tự:

```java
// Mã do annotation processor sinh; không tự chỉnh sửa.
@StaticMetamodel(Customer.class)
public abstract class Customer_ {
    public static volatile SingularAttribute<Customer, Long> id;
    public static volatile SingularAttribute<Customer, String> email;
    public static volatile SingularAttribute<Customer, CustomerStatus> status;
}
```

Tên và chi tiết field sinh ra phụ thuộc mapping, access strategy và processor. Không viết hoặc sửa lớp generated này bằng tay.

Dùng metamodel trong Criteria API:

```java
CriteriaBuilder builder = entityManager.getCriteriaBuilder();
CriteriaQuery<Customer> query = builder.createQuery(Customer.class);
Root<Customer> customer = query.from(Customer.class);

query.select(customer)
     .where(builder.equal(
             customer.get(Customer_.status),
             CustomerStatus.ACTIVE
     ));

List<Customer> result = entityManager
        .createQuery(query)
        .getResultList();
```

So với viết tên thuộc tính dưới dạng chuỗi như `customer.get("status")`, `Customer_.status` cho phép compiler kiểm tra kiểu và phát hiện lỗi đổi tên thuộc tính sớm hơn.

Static metamodel cũng hữu ích khi tạo join, order, predicate động hoặc EntityGraph. Nó không thay thế Criteria API; nó bổ sung cách tham chiếu thuộc tính an toàn kiểu.

## 3. Chọn đúng Hibernate metamodel processor theo phiên bản

Tên artifact của Hibernate đã thay đổi theo dòng phiên bản:

| Hibernate ORM | Annotation processor | Ghi chú |
|---|---|---|
| Hibernate 5.x | `org.hibernate:hibernate-jpamodelgen` | Tọa độ của dòng cũ |
| Hibernate 6.x | `org.hibernate.orm:hibernate-jpamodelgen` | Dùng cùng phiên bản với Hibernate ORM đang chạy |
| Hibernate 7.x | `org.hibernate.orm:hibernate-processor` | Module được đổi tên từ `hibernate-jpamodelgen` |

Với Hibernate 7, `Hibernate Processor` tiếp tục tạo Jakarta Persistence static metamodel và có thêm khả năng kiểm tra HQL/JPQL được khai báo bằng annotation ở compile time. Vì vậy, khi nâng Hibernate từ 6 lên 7, hãy thay đúng artifact processor theo dòng mới thay vì giữ cấu hình cũ một cách máy móc.

Ví dụ Gradle cho Hibernate 6:

```groovy
dependencies {
    implementation "org.hibernate.orm:hibernate-core:$hibernateVersion"
    annotationProcessor "org.hibernate.orm:hibernate-jpamodelgen:$hibernateVersion"
}
```

Ví dụ Gradle cho Hibernate 7:

```groovy
dependencies {
    implementation "org.hibernate.orm:hibernate-core:$hibernateVersion"
    annotationProcessor "org.hibernate.orm:hibernate-processor:$hibernateVersion"
}
```

`hibernateVersion` phải khớp phiên bản Hibernate ORM được Spring Boot dependency management chọn. Nếu dự án dùng Spring Boot BOM, ưu tiên để BOM quản lý Hibernate thay vì tự nâng riêng `hibernate-core` hoặc processor lên một version không tương thích.

Chỉ chọn một Hibernate metamodel processor phù hợp với dòng Hibernate đang dùng. Không khai báo đồng thời `hibernate-jpamodelgen` và `hibernate-processor` cho cùng source set vì cả hai có thể cùng sinh các lớp metamodel và dẫn tới generated source trùng lặp.

## 4. Querydsl tạo Q-types như thế nào?

Querydsl là thư viện xây dựng truy vấn có kiểu tĩnh. Annotation processor đọc entity và sinh một lớp Q tương ứng.

Với `Customer`, processor sinh `QCustomer`, thường có các thuộc tính như `id`, `email`, `status`:

```java
// Mã sinh tự động; ví dụ minh họa cấu trúc.
public class QCustomer extends EntityPathBase<Customer> {

    public static final QCustomer customer =
            new QCustomer("customer");

    public final NumberPath<Long> id = createNumber("id", Long.class);
    public final StringPath email = createString("email");
    public final EnumPath<CustomerStatus> status =
            createEnum("status", CustomerStatus.class);
}
```

Dùng Q-type để tạo predicate:

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.status.eq(CustomerStatus.ACTIVE)
        .and(customer.email.containsIgnoreCase("example"));

Iterable<Customer> customers = customerRepository.findAll(predicate);
```

Không cần viết chuỗi JPQL cho từng điều kiện. Compiler kiểm tra tên thuộc tính và kiểu dữ liệu của biểu thức Querydsl. Ví dụ, so sánh `status` với một giá trị không đúng kiểu sẽ bị phát hiện trong quá trình compile.

### 4.1. Tích hợp với Spring Data JPA

Spring Data JPA cung cấp `QuerydslPredicateExecutor` để repository có thể nhận Querydsl `Predicate`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Service có thể tạo predicate theo điều kiện đầu vào:

```java
@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Iterable<Customer> findActiveCustomers(String keyword) {
        QCustomer customer = QCustomer.customer;

        Predicate predicate = customer.status.eq(CustomerStatus.ACTIVE)
                .and(customer.email.containsIgnoreCase(keyword));

        return repository.findAll(predicate);
    }
}
```

Ví dụ giả định `CustomerStatus` là enum và `CustomerRepository` nằm trong package được Spring Data scan. Với phân trang, `QuerydslPredicateExecutor` cũng cung cấp phương thức nhận `Predicate` và `Pageable`.

Querydsl không bắt buộc cho mọi repository. Derived query, JPQL, Criteria API hoặc Specifications có thể phù hợp hơn tùy độ phức tạp. Dùng Querydsl khi cần dựng nhiều điều kiện động có kiểu tĩnh và muốn tái sử dụng biểu thức.

## 5. Chọn Querydsl artifact cho Jakarta hay javax

Đây là điểm dễ sai khi nâng ứng dụng từ Spring Boot 2 sang Spring Boot 3 hoặc mới hơn.

- Spring Boot 2 / JPA 2.x thường dùng namespace `javax.persistence.*`.
- Spring Boot 3+ / Jakarta Persistence 3+ dùng namespace `jakarta.persistence.*`.

Querydsl processor và runtime library phải tương thích với namespace entity đang sử dụng. Nếu entity import `jakarta.persistence.Entity` nhưng processor chỉ nhận `javax.persistence.Entity`, Q-types có thể không được sinh hoặc build báo lỗi kiểu không tương thích.

Hiện có hai lựa chọn thường gặp:

1. Artifact Querydsl gốc với group `com.querydsl`, dùng classifier `jakarta` cho Jakarta Persistence.
2. Fork do OpenFeign duy trì với group `io.github.openfeign.querydsl`; Spring Data JPA hiện có ví dụ cấu hình riêng cho fork này và hỗ trợ theo best-effort.

Không trộn runtime artifact của một fork với annotation processor của fork còn lại. Chọn một dòng và dùng cùng version cho `querydsl-jpa` và `querydsl-apt`.

### 5.1. Querydsl gốc với classifier jakarta

Ví dụ tọa độ Maven cho dự án Jakarta:

```xml
<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-jpa</artifactId>
    <version>${querydsl.version}</version>
    <classifier>jakarta</classifier>
</dependency>
```

Annotation processor tương ứng cũng cần classifier `jakarta`:

```xml
<path>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-apt</artifactId>
    <version>${querydsl.version}</version>
    <classifier>jakarta</classifier>
</path>
```

Không dùng cấu hình này với một dự án đang dùng `javax.persistence` nếu artifact/version được chọn chỉ hỗ trợ Jakarta.

### 5.2. OpenFeign Querydsl fork

Ví dụ với fork OpenFeign, runtime dependency không dùng classifier, còn processor dùng classifier `jpa`:

```xml
<dependency>
    <groupId>io.github.openfeign.querydsl</groupId>
    <artifactId>querydsl-jpa</artifactId>
    <version>${querydsl.version}</version>
</dependency>
```

Processor:

```xml
<path>
    <groupId>io.github.openfeign.querydsl</groupId>
    <artifactId>querydsl-apt</artifactId>
    <version>${querydsl.version}</version>
    <classifier>jpa</classifier>
</path>
```

Spring Data ghi nhận hoạt động bảo trì của Querydsl gốc đã chậm lại và cộng đồng tạo fork OpenFeign. Spring Data hỗ trợ fork này theo best-effort, vì vậy hãy kiểm tra release, issue và khả năng tương thích với phiên bản Spring Data JPA đang dùng trước khi nâng cấp.

## 6. Cấu hình Maven cho Hibernate metamodel và Querydsl

Maven Compiler Plugin cho phép khai báo riêng processor path. Đây là nơi đặt các processor chạy trong compile; không cần đưa chúng vào runtime classpath.

Ví dụ cho ứng dụng Jakarta dùng Hibernate 7 và OpenFeign Querydsl. Các property version cần được quản lý bởi Spring Boot BOM hoặc dependency management của dự án:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.plugin.version>3.15.0</maven.compiler.plugin.version>
    <hibernate.version>VERSION_FROM_BOOT_BOM</hibernate.version>
    <querydsl.version>QUERYDSL_VERSION</querydsl.version>
    <jakarta.persistence.version>JPA_API_VERSION</jakarta.persistence.version>
</properties>

<dependencies>
    <!-- Runtime Querydsl API -->
    <dependency>
        <groupId>io.github.openfeign.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>${querydsl.version}</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>${maven.compiler.plugin.version}</version>
            <configuration>
                <release>${maven.compiler.release}</release>
                <annotationProcessorPaths>
                    <!-- Hibernate 7: dùng hibernate-processor.
                         Với Hibernate 6, đổi thành hibernate-jpamodelgen. -->
                    <path>
                        <groupId>org.hibernate.orm</groupId>
                        <artifactId>hibernate-processor</artifactId>
                        <version>${hibernate.version}</version>
                    </path>

                    <!-- Querydsl OpenFeign fork -->
                    <path>
                        <groupId>io.github.openfeign.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>${querydsl.version}</version>
                        <classifier>jpa</classifier>
                    </path>

                    <!-- Jakarta Persistence API cho processor -->
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>${jakarta.persistence.version}</version>
                    </path>
                </annotationProcessorPaths>
                <generatedSourcesDirectory>
                    ${project.build.directory}/generated-sources/annotations
                </generatedSourcesDirectory>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Các giá trị `VERSION_FROM_BOOT_BOM`, `QUERYDSL_VERSION` và `JPA_API_VERSION` là placeholder cần thay bằng version thực tế của dự án. Không copy nguyên placeholder vào build. Nếu Spring Boot BOM đã quản lý version Hibernate/Jakarta API, hãy giữ chúng đồng bộ với runtime dependency. Maven Compiler Plugin có tùy chọn `annotationProcessorPathsUseDepMgmt` để áp dụng dependency management cho processor paths trong các cấu hình phù hợp; cách đơn giản nhất để tránh mơ hồ là khai báo version processor rõ ràng.

Nếu dùng Hibernate 6, thay:

```xml
<artifactId>hibernate-processor</artifactId>
```

bằng:

```xml
<artifactId>hibernate-jpamodelgen</artifactId>
```

và vẫn dùng version khớp `hibernate-core`.

Với JDK 23 trở lên, không dựa vào việc compiler tự dò processor trên compile classpath. Khai báo `annotationProcessorPaths` hoặc danh sách processor tường minh, đồng thời bổ sung `<proc>full</proc>` vào `<configuration>` của Maven Compiler Plugin phiên bản hỗ trợ tùy chọn này. Với JDK cũ hơn, chỉ dùng `proc=full` khi phiên bản compiler hỗ trợ; nếu không, bỏ cấu hình đó. Cách khai báo tường minh giúp build không phụ thuộc vào cơ chế tự dò processor đã bị tắt mặc định trên JDK mới.

## 7. Cấu hình Gradle

Gradle dùng configuration riêng cho processor:

- `annotationProcessor`: processor cho source set main.
- `testAnnotationProcessor`: processor cho source set test.
- `implementation`: thư viện Querydsl mà code ứng dụng gọi.

Ví dụ Groovy DSL với Hibernate 7 và OpenFeign Querydsl:

```groovy
dependencies {
    implementation "io.github.openfeign.querydsl:querydsl-jpa:$querydslVersion"

    // Hibernate 7 static metamodel + compile-time processor
    annotationProcessor "org.hibernate.orm:hibernate-processor:$hibernateVersion"

    // Querydsl Q-type generator for Jakarta Persistence
    annotationProcessor "io.github.openfeign.querydsl:querydsl-apt:$querydslVersion:jpa"
    annotationProcessor "jakarta.persistence:jakarta.persistence-api:$jakartaPersistenceVersion"

    // Chỉ cần nếu test source cũng khai báo entity cần sinh Q-types/metamodel
    testAnnotationProcessor "org.hibernate.orm:hibernate-processor:$hibernateVersion"
    testAnnotationProcessor "io.github.openfeign.querydsl:querydsl-apt:$querydslVersion:jpa"
    testAnnotationProcessor "jakarta.persistence:jakarta.persistence-api:$jakartaPersistenceVersion"
}
```

Với Hibernate 6, thay `hibernate-processor` bằng `hibernate-jpamodelgen`. Nếu không dùng Querydsl, bỏ dependency `querydsl-jpa` và `querydsl-apt`; nếu không dùng static metamodel/Hibernate compile-time processing, bỏ processor Hibernate tương ứng.

Ví dụ Kotlin DSL:

```kotlin
dependencies {
    implementation("io.github.openfeign.querydsl:querydsl-jpa:$querydslVersion")

    annotationProcessor("org.hibernate.orm:hibernate-processor:$hibernateVersion")
    annotationProcessor("io.github.openfeign.querydsl:querydsl-apt:$querydslVersion:jpa")
    annotationProcessor("jakarta.persistence:jakarta.persistence-api:$jakartaPersistenceVersion")

    testAnnotationProcessor("org.hibernate.orm:hibernate-processor:$hibernateVersion")
    testAnnotationProcessor("io.github.openfeign.querydsl:querydsl-apt:$querydslVersion:jpa")
    testAnnotationProcessor("jakarta.persistence:jakarta.persistence-api:$jakartaPersistenceVersion")
}
```

Đặt version trong `gradle.properties`, version catalog hoặc dependency constraints. Không để Hibernate processor khác version với Hibernate ORM runtime. Nếu dự án dùng Kotlin entity, annotation processing có thể cần KAPT hoặc KSP tùy plugin và processor; cấu hình Java `annotationProcessor` không tự động xử lý mọi source Kotlin.

## 8. Dùng cả metamodel và Querydsl trong cùng dự án

Hai processor có thể cùng được cấu hình vì chúng sinh ra các loại class khác nhau:

- Hibernate/JPA processor sinh `Customer_`.
- Querydsl APT sinh `QCustomer`.

Ví dụ sử dụng song song:

```java
// JPA Criteria API
Root<Customer> root = criteriaQuery.from(Customer.class);
criteriaQuery.where(
        criteriaBuilder.equal(
                root.get(Customer_.status),
                CustomerStatus.ACTIVE
        )
);

// Querydsl
QCustomer qCustomer = QCustomer.customer;
Predicate predicate = qCustomer.status.eq(CustomerStatus.ACTIVE);
```

Đừng khai báo hai generator khác nhau cùng sinh một loại static metamodel. Ví dụ, nếu đã dùng Hibernate Processor để sinh `Customer_`, không thêm một JPA metamodel generator thứ hai cũng tạo cùng lớp. Ngược lại, Querydsl APT sinh `QCustomer`, nên nó có thể cùng tồn tại với Hibernate Processor.

Khi dùng nhiều processor, hãy khai báo tất cả trong cùng processor path và xác nhận mỗi processor nhận đúng annotation namespace. Nếu build báo duplicate generated type, kiểm tra xem có processor cũ còn nằm trong dependency, cấu hình IDE hoặc module khác không.

## 9. Kiểm tra mã được sinh sau khi nâng cấp

Sau khi cập nhật dependency/configuration, chạy clean build để loại bỏ generated source cũ:

Maven:

```bash
mvn clean compile
```

Gradle:

```bash
./gradlew clean compileJava
```

Với Gradle Kotlin hoặc test entities, có thể cần chạy thêm `compileTestJava`. Với Maven, chạy `mvn clean test` để kiểm tra cả test compile và test runtime.

Kiểm tra thư mục generated source:

- Maven thường dùng `target/generated-sources/annotations`.
- Gradle Java main thường dùng `build/generated/sources/annotationProcessor/java/main`.
- Gradle test thường dùng `build/generated/sources/annotationProcessor/java/test`.

Xác nhận tối thiểu:

1. Entity `Customer` tạo được `Customer_` nếu Hibernate/JPA metamodel processor đã bật.
2. Entity `Customer` tạo được `QCustomer` nếu Querydsl APT đã bật.
3. Các lớp generated import đúng `jakarta.persistence` hoặc `javax.persistence` theo dự án.
4. Mã ứng dụng có thể import và compile với generated classes.
5. Một Criteria query và một Querydsl predicate mẫu chạy được với database test.
6. Build không còn warning/error về processor version hoặc duplicate class.

Không sửa trực tiếp file trong thư mục generated. Hãy sửa entity, annotation hoặc cấu hình processor rồi chạy lại build. Generated source thường không cần commit vào Git nếu dự án có thể tái tạo chúng trong mọi build.

## 10. Cấu hình IDE

IDE có thể dùng build system riêng để biên dịch và đôi khi không tự đồng bộ processor configuration ngay sau khi sửa Maven/Gradle.

Trong IntelliJ IDEA:

1. Reload Maven hoặc Gradle project sau khi sửa dependency.
2. Bật annotation processing trong cấu hình compiler nếu IDE dùng compiler nội bộ.
3. Kiểm tra generated source directory đã được nhận diện là Generated Sources Root.
4. Chạy clean build từ terminal để so sánh với kết quả IDE.

Trong Eclipse, kiểm tra Java Compiler > Annotation Processing và cấu hình factory path nếu workspace không tự nhận processor từ Maven/Gradle.

Nếu terminal build thành công nhưng IDE báo không tìm thấy `QCustomer` hoặc `Customer_`, thường vấn đề nằm ở IDE chưa đồng bộ generated source hoặc annotation processing. Nếu cả terminal build cũng thiếu file, hãy kiểm tra processor path và namespace.

## 11. Lỗi thường gặp khi cập nhật processor

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không sinh `Customer_` | Hibernate processor thiếu hoặc sai artifact theo version | Hibernate 6 dùng `hibernate-jpamodelgen`; Hibernate 7 dùng `hibernate-processor` |
| Không sinh `QCustomer` | Querydsl APT chưa nằm trên processor path | Khai báo `querydsl-apt` trong Maven/Gradle annotation processor configuration |
| Q-types không nhận entity Jakarta | Dùng nhầm processor variant `javax` | Chọn classifier/variant Jakarta phù hợp |
| Build chạy nhưng không có generated code trên JDK mới | Dựa vào implicit annotation processing | Khai báo processor path tường minh |
| `javax.persistence` và `jakarta.persistence` không tương thích | Trộn dependency hoặc processor của hai namespace | Đồng bộ Spring Boot, JPA API, Hibernate và Querydsl variant |
| Duplicate class `Customer_` | Hai metamodel generator cùng chạy hoặc generated source cũ | Chỉ giữ một metamodel generator, chạy clean build |
| Duplicate class `QCustomer` | Nhiều Querydsl processor/fork cùng được cấu hình | Chọn một Querydsl fork và một APT path |
| `NoClassDefFoundError` trong annotation processing | Processor thiếu API cần thiết hoặc version lệch | Bổ sung API vào processor path và đồng bộ version |
| IDE không nhận Q-type nhưng CLI build thành công | IDE chưa bật/sync annotation processing | Reload build project và đánh dấu generated sources |
| Generated class lỗi sau khi đổi entity package | File sinh cũ còn sót trong output | Chạy clean build và kiểm tra source set |
| Processor Hibernate không tương thích với Hibernate runtime | Dùng version độc lập với dependency management | Dùng cùng version Hibernate ORM hoặc version được BOM hỗ trợ |

Một lỗi namespace thường xuất hiện khi dự án chuyển từ Spring Boot 2 sang 3: entity đã đổi import sang `jakarta.persistence`, nhưng Querydsl vẫn dùng artifact `javax`. Cần đổi cả runtime library và annotation processor, không chỉ sửa import trong entity.

## 12. Quy trình nâng cấp annotation processor

Thực hiện theo thứ tự để dễ tìm lỗi:

1. **Ghi nhận phiên bản hiện tại:** Java, Spring Boot, Spring Data JPA, Hibernate ORM, Jakarta Persistence và Querydsl.
2. **Xác định namespace:** kiểm tra entity import `javax.persistence` hay `jakarta.persistence`.
3. **Chọn processor phù hợp:** Hibernate 6 dùng `hibernate-jpamodelgen`; Hibernate 7 dùng `hibernate-processor`; Querydsl chọn đúng Jakarta variant/fork.
4. **Cập nhật build:** đặt processor trong Maven `annotationProcessorPaths` hoặc Gradle `annotationProcessor`; khai báo Querydsl runtime dependency riêng.
5. **Đồng bộ version:** dùng BOM hoặc version property nhất quán với ORM/runtime.
6. **Bật processing tường minh:** đặc biệt với JDK 23+ và Maven Compiler Plugin.
7. **Xóa generated output cũ:** chạy `clean` để tránh dùng nhầm class được sinh từ entity/version trước.
8. **Kiểm tra generated sources:** xác nhận cả `Customer_` và `QCustomer` được sinh nếu dự án dùng cả hai.
9. **Kiểm thử truy vấn:** compile Criteria API và Querydsl predicate, sau đó chạy integration test.
10. **Đồng bộ IDE và CI:** cùng JDK, build tool và processor config phải được dùng ở local và pipeline.

Không nâng riêng Querydsl/Hibernate processor vượt khỏi dải tương thích của Spring Boot/Spring Data đang dùng. Nếu dependency management của framework chưa hỗ trợ version mới, hãy kiểm tra compatibility matrix và migration guide trước khi override.

## 13. Checklist hoàn tất

- [ ] Đã xác định Java, Spring Boot, Spring Data JPA, Hibernate và JPA API version.
- [ ] Đã chọn đúng namespace `javax` hoặc `jakarta`.
- [ ] Hibernate 6 dùng `hibernate-jpamodelgen`; Hibernate 7 dùng `hibernate-processor`.
- [ ] Chỉ có một processor sinh JPA static metamodel.
- [ ] Querydsl runtime và APT dùng cùng fork/version.
- [ ] Querydsl Jakarta classifier/variant khớp với entity namespace.
- [ ] Processor được khai báo ở compile-time path, không dựa vào classpath runtime.
- [ ] JDK 23+ có cấu hình annotation processing tường minh.
- [ ] Generated source được tạo lại từ clean build.
- [ ] Criteria API dùng được `Customer_` và Querydsl dùng được `QCustomer`.
- [ ] Test source có processor riêng nếu test khai báo entity cần generate.
- [ ] IDE và CI dùng cùng cấu hình build.
- [ ] Không commit hoặc sửa thủ công generated source trái với quy ước dự án.

Cập nhật annotation processor là một phần của nâng cấp persistence stack. Hãy đồng bộ processor với phiên bản Hibernate và namespace Jakarta/Javax, cấu hình Querydsl APT riêng với runtime library, rồi xác nhận generated source bằng clean build. Khi `Customer_` và `QCustomer` được sinh đúng và truy vấn mẫu compile/test thành công, dự án đã có cơ sở tin cậy để tiếp tục nâng cấp.

## Tài liệu tham khảo

- [Hibernate ORM – Hibernate Processor](https://hibernate.org/orm/processor/)
- [Hibernate ORM 7 – Project setup and hibernate-processor](https://docs.hibernate.org/orm/7.4/repositories/html_single/)
- [Hibernate ORM 6.6 – hibernate-jpamodelgen module](https://docs.hibernate.org/orm/6.6/quickstart/html_single/)
- [Spring Data JPA – Querydsl extension and annotation processing](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [OpenFeign Querydsl – JPA tutorial](https://openfeign.github.io/querydsl/tutorials/jpa/)