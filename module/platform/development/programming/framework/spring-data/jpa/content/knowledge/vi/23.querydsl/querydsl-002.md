# Cấu hình sinh Q-type tương thích Jakarta Persistence với Querydsl

## 1. Q-type là gì?

Querydsl là thư viện xây dựng truy vấn bằng Java với API fluent và kiểm tra kiểu ở compile time. Thay vì viết chuỗi tên thuộc tính như JPQL hoặc Criteria API thuần, Querydsl tạo ra một lớp metamodel cho mỗi domain type. Các lớp này thường có tiền tố `Q`, ví dụ:

- Entity `Customer` tạo ra `QCustomer`.
- Entity `PurchaseOrder` tạo ra `QPurchaseOrder`.
- Embedded type `Address` có thể tạo ra `QAddress`.

Q-type mô tả thuộc tính của kiểu nguồn bằng các path có kiểu cụ thể. Ví dụ `QCustomer.customer.email` là `StringPath`, `QCustomer.customer.id` là path của kiểu ID và `QCustomer.customer.createdAt` là path tương ứng với kiểu ngày giờ.

Nhờ vậy, IDE có thể gợi ý thuộc tính và compiler phát hiện nhiều lỗi tên trường hoặc kiểu dữ liệu trước khi chạy ứng dụng. Khi đổi tên thuộc tính entity, mã sử dụng Q-type cũng cần được biên dịch lại; nếu Q-type chưa được sinh hoặc đã cũ, build sẽ báo lỗi.

Q-type là mã nguồn được sinh tự động bởi annotation processor. Thông thường không viết hoặc chỉnh sửa các lớp `Q...` bằng tay.

## 2. Vì sao Jakarta Persistence cần cấu hình riêng?

Từ Spring Boot 3 và Spring Framework 6, hệ sinh thái JPA chuyển từ namespace Java EE `javax.persistence.*` sang Jakarta EE `jakarta.persistence.*`.

Hai namespace này khác nhau ở cấp package và binary name. Ví dụ:

| API cũ | API Jakarta |
|---|---|
| `javax.persistence.Entity` | `jakarta.persistence.Entity` |
| `javax.persistence.Id` | `jakarta.persistence.Id` |
| `javax.persistence.EntityManager` | `jakarta.persistence.EntityManager` |
| `javax.persistence.MappedSuperclass` | `jakarta.persistence.MappedSuperclass` |

Một annotation processor chỉ nhận diện `javax.persistence.Entity` có thể không phát hiện entity được đánh dấu bằng `jakarta.persistence.Entity`. Kết quả thường là build vẫn biên dịch entity nhưng không sinh ra `QCustomer`, hoặc sinh mã dựa trên namespace không tương thích với ứng dụng.

Vì vậy, cấu hình Querydsl phải đồng bộ ở ba nơi:

1. Thư viện Querydsl JPA dùng lúc biên dịch/chạy.
2. Querydsl annotation processor dùng để sinh Q-type.
3. Jakarta Persistence API mà annotation processor cần để nhận diện entity.

Không trộn artifact dành cho `javax.persistence` với entity và provider dùng `jakarta.persistence`.

## 3. Chọn đúng dòng Querydsl

Hiện có hai lựa chọn thường gặp trong dự án Jakarta:

| Lựa chọn | Group ID | Cách bật Jakarta | Ghi chú |
|---|---|---|---|
| Querydsl upstream 5.1.x | `com.querydsl` | Dùng classifier `jakarta` cho `querydsl-jpa` và `querydsl-apt` | Được Spring Data reference minh họa |
| OpenFeign Querydsl fork 6.x trở lên | `io.github.openfeign.querydsl` | Fork dùng namespace `jakarta.*` trực tiếp; annotation processor dùng classifier `jpa` | Fork duy trì tiếp sau khi upstream chậm phát triển; Spring Data hỗ trợ ở mức best effort |

Tài liệu Spring Data hiện hành lưu ý hoạt động bảo trì của Querydsl upstream đã chậm lại và cộng đồng đã fork dự án dưới group ID `io.github.openfeign.querydsl`. Spring Data hỗ trợ fork này theo best-effort. Cần kiểm tra phiên bản Spring Data, Spring Boot, JDK và JPA provider trong dự án trước khi chọn. Không trộn module từ hai group ID trong cùng một cấu hình.

Các ví dụ dưới đây minh họa hai cấu hình riêng. Chọn một cấu hình duy nhất cho dự án.

## 4. Cấu hình Maven với Querydsl 5.1.x Jakarta classifier

Nếu dự án đang dùng Querydsl upstream 5.1.x, hãy thêm dependency JPA có classifier `jakarta`:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>5.1.0</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>
~~~

Tiếp theo, khai báo annotation processor trong `maven-compiler-plugin`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>5.1.0</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`querydsl-jpa` cung cấp API truy vấn JPA của Querydsl. `querydsl-apt` cung cấp annotation processor. Jakarta Persistence API được đưa vào processor path để processor nhận diện các annotation như `@Entity`, `@Embeddable` và `@MappedSuperclass`.

Các version trong ví dụ là một bộ minh họa. Hãy chọn phiên bản Jakarta Persistence API do Spring Boot BOM hoặc JPA provider của dự án quản lý; không hạ hoặc nâng API riêng lẻ nếu điều đó làm lệch stack hiện tại.

### Annotation processing trên JDK mới

Từ JDK 22, cần chủ động cấu hình annotation processor qua `annotationProcessorPaths` hoặc cơ chế opt-in tương ứng. Không nên dựa vào việc `javac` tự dò processor trên compile classpath.

Với JDK 23 trở lên, implicit annotation processing bị tắt mặc định. Nếu build dùng Maven Compiler Plugin và không chạy processor dù dependency đã khai báo, kiểm tra cấu hình processor rõ ràng; tài liệu OpenFeign minh họa thêm:

~~~xml
<configuration>
    <proc>full</proc>
    <annotationProcessorPaths>
        <!-- Querydsl APT and Jakarta Persistence API paths -->
    </annotationProcessorPaths>
</configuration>
~~~

`<proc>full</proc>` bật annotation processing trong compiler. Vẫn phải khai báo đúng processor và API trên `annotationProcessorPaths`; chỉ thêm `proc` mà thiếu processor thì Q-type không được sinh.

## 5. Cấu hình Gradle với Querydsl 5.1.x Jakarta classifier

Với Gradle, annotation processor cần nằm trong configuration `annotationProcessor`, không chỉ ở `implementation`.

Ví dụ `build.gradle` dùng Groovy DSL:

~~~groovy
dependencies {
    implementation 'com.querydsl:querydsl-jpa:5.1.0:jakarta'

    annotationProcessor 'com.querydsl:querydsl-apt:5.1.0:jakarta'
    annotationProcessor 'jakarta.persistence:jakarta.persistence-api:3.1.0'

    testAnnotationProcessor 'com.querydsl:querydsl-apt:5.1.0:jakarta'
    testAnnotationProcessor 'jakarta.persistence:jakarta.persistence-api:3.1.0'
}
~~~

Nếu dùng Kotlin DSL (`build.gradle.kts`):

~~~kotlin
dependencies {
    implementation("com.querydsl:querydsl-jpa:5.1.0:jakarta")

    annotationProcessor("com.querydsl:querydsl-apt:5.1.0:jakarta")
    annotationProcessor("jakarta.persistence:jakarta.persistence-api:3.1.0")

    testAnnotationProcessor("com.querydsl:querydsl-apt:5.1.0:jakarta")
    testAnnotationProcessor("jakarta.persistence:jakarta.persistence-api:3.1.0")
}
~~~

`annotationProcessor` áp dụng cho mã nguồn chính; `testAnnotationProcessor` cần thiết nếu test source set có entity hoặc model cần sinh Q-type. Phiên bản Jakarta Persistence API phải tương thích với Spring Boot/JPA provider đang dùng.

Không đặt `querydsl-apt` vào `implementation` để thay thế `annotationProcessor`. Processor là công cụ build, không phải thư viện runtime của ứng dụng.

## 6. Dùng OpenFeign Querydsl fork

Với dự án mới hoặc dự án chọn OpenFeign fork, artifact có group ID `io.github.openfeign.querydsl`. Fork từ phiên bản 6 trở lên dùng `jakarta.*` trực tiếp nên không dùng classifier `jakarta` cho `querydsl-jpa`.

Ví dụ Gradle Groovy DSL theo tài liệu Querydsl OpenFeign:

~~~groovy
dependencies {
    implementation 'io.github.openfeign.querydsl:querydsl-jpa:7.1'

    annotationProcessor 'io.github.openfeign.querydsl:querydsl-apt:7.1:jpa'
    annotationProcessor 'jakarta.persistence:jakarta.persistence-api'

    testAnnotationProcessor 'io.github.openfeign.querydsl:querydsl-apt:7.1:jpa'
    testAnnotationProcessor 'jakarta.persistence:jakarta.persistence-api'
}
~~~

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.github.openfeign.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>7.1</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.15.0</version>
            <configuration>
                <proc>full</proc>
                <annotationProcessorPaths>
                    <path>
                        <groupId>io.github.openfeign.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>7.1</version>
                        <classifier>jpa</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.2.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Ở đây, classifier `jpa` chọn JPA annotation processor của fork. Nó không phải classifier `jakarta` của artifact upstream. Chọn phiên bản Jakarta Persistence API tương ứng với nền tảng dự án; `3.2.0` trong ví dụ Maven phù hợp với stack Jakarta Persistence 3.2, còn dự án Spring Boot/JPA cũ hơn có thể cần phiên bản API khác theo BOM.

Tài liệu Spring Data hiện hành cũng có ví dụ Maven và Gradle cho OpenFeign fork. Nếu dùng fork, giữ tất cả module Querydsl cùng group ID `io.github.openfeign.querydsl`, không trộn `querydsl-core` hoặc `querydsl-apt` upstream `com.querydsl` vào cấu hình đó.

## 7. Đảm bảo entity dùng annotation Jakarta

Entity cần import từ `jakarta.persistence`:

~~~java
package com.example.customer;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;

    protected Customer() {
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Khi annotation processor chạy, nó đọc entity metadata và sinh `QCustomer` trong package tương ứng. Không cần thêm annotation riêng cho từng thuộc tính thông thường.

Nếu entity vẫn import `javax.persistence.Entity`, processor Jakarta có thể không nhận diện đúng. Hãy thống nhất toàn bộ entity, JPA provider, API dependency và Querydsl processor theo cùng namespace.

## 8. Q-type được sinh ở đâu?

Annotation processor chạy trong giai đoạn compile và tạo mã nguồn vào generated sources directory. Vị trí mặc định thường nằm dưới thư mục build, chẳng hạn:

- Maven: `target/generated-sources/annotations`
- Gradle: `build/generated/sources/annotationProcessor/java/main`

Tên thư mục có thể thay đổi theo cấu hình compiler hoặc plugin. Không nên giả định một đường dẫn duy nhất nếu dự án đã tùy chỉnh build.

Ví dụ entity `Customer` có thể tạo:

~~~java
package com.example.customer;

import static com.querydsl.core.types.PathMetadataFactory.*;

public class QCustomer extends EntityPathBase<Customer> {
    public static final QCustomer customer = new QCustomer("customer");

    public final StringPath email = createString("email");
    public final NumberPath<Long> id = createNumber("id", Long.class);
    public final StringPath fullName = createString("fullName");

    // Generated constructors and metadata omitted.
}
~~~

Đây là đoạn minh họa cấu trúc Q-type, không phải file hoàn chỉnh để tự viết. Q-type thật được processor sinh ra với imports, metadata, constructor và các path phù hợp với entity.

Không chỉnh sửa trực tiếp mã trong generated directory. Thay đổi entity hoặc processor configuration rồi chạy build để sinh lại.

## 9. Kiểm tra Q-type đã được sinh

Sau khi cấu hình, chạy build sạch để loại mã sinh cũ:

~~~bash
# Maven
mvn clean compile

# Gradle
./gradlew clean compileJava
~~~

Kiểm tra generated source directory để tìm `QCustomer.java` hoặc Q-type của entity cần dùng. Có thể chạy test sau khi compile:

~~~bash
# Maven
mvn clean test

# Gradle
./gradlew clean test
~~~

Nếu dự án có entity trong test source set, bảo đảm đã cấu hình `testAnnotationProcessor` ở Gradle hoặc cấu hình processor tương ứng cho test compilation trong Maven.

Trong IDE, bật annotation processing nếu IDE không tự nhận cấu hình build, sau đó đánh dấu generated sources directory là Generated Sources Root nếu cần. Ưu tiên để Maven/Gradle là nguồn cấu hình chính nhằm tránh build trên máy lập trình viên khác với CI.

## 10. Dùng Q-type với Querydsl JPA

Khi `QCustomer` đã được sinh, có thể sử dụng nó trong truy vấn:

~~~java
QCustomer customer = QCustomer.customer;

List<Customer> activeCustomers = queryFactory
    .selectFrom(customer)
    .where(
        customer.status.eq(CustomerStatus.ACTIVE)
            .and(customer.email.endsWithIgnoreCase("@example.com"))
    )
    .orderBy(
        customer.createdDate.desc(),
        customer.id.asc()
    )
    .fetch();
~~~

Ví dụ giả định entity có `status`, `email`, `createdDate` và `id`. Các path được sinh theo kiểu thực tế của thuộc tính. Nếu entity chỉ có `fullName` và `email`, không thể gọi `customer.status` hoặc `customer.createdDate`; hãy dùng đúng thuộc tính có trong model.

`JPAQueryFactory` thường được khởi tạo từ `EntityManager`:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Cần có import `jakarta.persistence.EntityManager` và các class Spring/JPA tương ứng. Bean factory dùng EntityManager do container quản lý; không tự tạo một EntityManager độc lập ngoài transaction lifecycle.

## 11. Tích hợp QuerydslPredicateExecutor với Spring Data repository

Nếu chỉ cần thực thi predicate qua repository abstraction, có thể mở rộng `QuerydslPredicateExecutor`:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Sau đó tạo predicate từ Q-type:

~~~java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.status.eq(CustomerStatus.ACTIVE)
    .and(customer.fullName.containsIgnoreCase("an"));

Iterable<Customer> result = customerRepository.findAll(predicate);
~~~

`QuerydslPredicateExecutor` cung cấp các thao tác như `findAll(predicate)`, `findOne(predicate)`, `count(predicate)` và `exists(predicate)`. Các overload hỗ trợ `Sort` và `Pageable` cho phép phân trang/sắp xếp theo repository API.

Ví dụ:

~~~java
Page<Customer> page = customerRepository.findAll(
    predicate,
    PageRequest.of(
        0,
        20,
        Sort.by("id").ascending()
    )
);
~~~

Dùng `JPAQueryFactory` khi cần kiểm soát chi tiết select, join, group, projection hoặc biểu thức truy vấn. Dùng `QuerydslPredicateExecutor` khi muốn tái sử dụng predicate với các thao tác repository phổ biến.

## 12. Cấu hình test source và entity trong nhiều module

Nếu entity được khai báo trong `src/test/java`, processor cần chạy trên test source set để sinh Q-type dùng trong test. Với Gradle, thêm `testAnnotationProcessor` như ví dụ ở trên.

Trong multi-module build:

- Module chứa entity chịu trách nhiệm chạy annotation processor và sinh Q-type cho entity của module đó.
- Module khác cần dùng Q-type phải có dependency tới artifact chứa các generated classes đã được biên dịch/đóng gói theo cách dự án thiết kế.
- Không cấu hình hai module cùng sinh một Q-type cho cùng một entity nếu điều đó tạo class trùng lặp.
- Đảm bảo generated sources được đưa vào compilation và artifact khi module cần chia sẻ chúng.

Nếu dự án tự tách model module, hãy kiểm tra output của module đó và dependency graph trước khi cấu hình thêm processor ở module tiêu thụ.

## 13. Lỗi thường gặp và cách khắc phục

### 13.1. Build thành công nhưng không có Q-type

Nguyên nhân thường gặp:

- `querydsl-apt` chưa nằm trong annotation processor path.
- JDK mới không tự chạy annotation processor do chưa opt-in.
- Processor dùng classifier sai.
- Entity chưa được compiler xử lý trong source set đó.
- Entity dùng `jakarta.persistence` nhưng processor đang dùng dòng `javax`.
- Generated source directory không được compiler/IDE nhận diện.

Cách kiểm tra:

1. Xác nhận processor có trong `annotationProcessorPaths` hoặc `annotationProcessor`.
2. Xác nhận artifact đúng group ID và classifier.
3. Xác nhận `jakarta.persistence-api` có trong processor path.
4. Chạy `clean compile` để sinh lại.
5. Kiểm tra output generated source và log compiler.

### 13.2. Lỗi không tìm thấy javax.persistence

Lỗi như `ClassNotFoundException: javax.persistence.Entity` hoặc `NoClassDefFoundError` thường cho thấy có dependency/processor cũ dùng namespace Java EE trong khi ứng dụng dùng Jakarta.

Kiểm tra dependency tree và loại bỏ cấu hình Querydsl cũ không tương thích. Không thêm cả `javax.persistence-api` lẫn `jakarta.persistence-api` để che lỗi namespace; hãy chọn một stack thống nhất.

### 13.3. Dùng sai classifier

Hai cấu hình không tương đương:

- Upstream `com.querydsl`: dùng classifier `jakarta` cho `querydsl-jpa` và `querydsl-apt`.
- OpenFeign `io.github.openfeign.querydsl`: dùng artifact JPA thông thường và classifier `jpa` cho `querydsl-apt`.

Không thay classifier `jakarta` thành `jpa` trên upstream artifact, cũng không thêm classifier `jakarta` vào fork chỉ vì ứng dụng dùng Jakarta.

### 13.4. Q-type có nhưng IDE báo không tìm thấy

Kiểm tra IDE đã bật annotation processing và nhận generated source directory chưa. Chạy build từ terminal để phân biệt lỗi IDE với lỗi cấu hình Maven/Gradle. Nếu terminal build thành công nhưng IDE báo đỏ, đồng bộ lại project và đánh dấu generated directory đúng cách.

### 13.5. Lỗi duplicate class hoặc Q-type cũ

Có thể do Q-type được tạo thủ công, generated source cũ còn sót, hoặc nhiều module cùng sinh một class. Dùng `clean`, bỏ file Q-type viết tay không cần thiết và chỉ định một nơi chịu trách nhiệm sinh mã.

### 13.6. Build local chạy nhưng CI không sinh Q-type

CI có thể dùng JDK khác hoặc chạy với annotation processing bị tắt. Ghi rõ JDK, Maven/Gradle wrapper và processor configuration trong repository. Không dựa vào thiết lập riêng của IDE.

## 14. Quy trình lựa chọn và kiểm tra cấu hình

Khi thêm Querydsl vào dự án Jakarta Persistence:

1. Xác định dự án dùng Spring Boot/Spring Data JPA và JDK phiên bản nào.
2. Xác nhận entity import `jakarta.persistence.*`.
3. Chọn một dòng Querydsl: upstream với classifier `jakarta`, hoặc OpenFeign fork với processor classifier `jpa`.
4. Khai báo `querydsl-jpa` ở dependency compile/runtime phù hợp.
5. Khai báo `querydsl-apt` trong annotation processor configuration, không chỉ trong implementation.
6. Đưa Jakarta Persistence API vào processor path.
7. Bảo đảm annotation processing được bật rõ ràng trên JDK mới.
8. Chạy build sạch và xác nhận Q-type xuất hiện trong generated sources.
9. Dùng Q-type trong một truy vấn thực tế hoặc repository test.
10. Chạy test trên cùng JDK và build tool như CI.

## 15. Ghi nhớ

- Q-type là metamodel Java được Querydsl sinh từ entity/domain model, ví dụ `Customer` thành `QCustomer`.
- Spring Boot 3 / Spring Data JPA 3 dùng Jakarta Persistence; entity cần import `jakarta.persistence.*`.
- Namespace `javax.persistence` và `jakarta.persistence` không tương thích binary.
- Upstream Querydsl 5.1.x cần classifier `jakarta` trên `querydsl-jpa` và `querydsl-apt`.
- OpenFeign Querydsl fork dùng group ID `io.github.openfeign.querydsl`; fork từ 6.x dùng Jakarta trực tiếp và JPA processor có classifier `jpa`.
- Không trộn group ID hoặc classifier giữa hai dòng Querydsl.
- `querydsl-apt` phải được cấu hình trong annotation processor path/configuration; nó không phải dependency runtime thông thường.
- Đưa Jakarta Persistence API vào processor path để processor nhận diện annotation.
- Với JDK 22+, cấu hình annotation processor rõ ràng; với JDK 23+, kiểm tra opt-in/`proc` theo Maven Compiler Plugin và tài liệu build tool.
- Q-type được sinh trong generated sources; không chỉnh sửa trực tiếp.
- Sau khi đổi entity hoặc dependency, chạy clean build và xác nhận generated Q-type được cập nhật.
- Kiểm thử cấu hình trên đúng JDK và build tool dùng trong CI.

## Tài liệu tham khảo

- [Spring Data JPA — Querydsl Extension and Annotation Processing](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [OpenFeign Querydsl — Querying JPA and Maven Integration](https://openfeign.github.io/querydsl/tutorials/jpa/)
- [OpenFeign Querydsl — Migration from javax to jakarta](https://github.com/OpenFeign/querydsl/blob/master/docs/migration.md)
- [Spring Data JPA — QuerydslJpaPredicateExecutor API](https://www.springframework.org/spring-data/data-jpa/docs/current/api/org/springframework/data/jpa/repository/support/QuerydslJpaPredicateExecutor.html)