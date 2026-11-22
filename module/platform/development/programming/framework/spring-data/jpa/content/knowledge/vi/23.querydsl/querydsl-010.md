# Đánh giá phiên bản, nguồn phát hành và chi phí phụ thuộc Querydsl

Querydsl là thư viện Java giúp xây dựng truy vấn kiểu SQL bằng API fluent và các kiểu Java được sinh từ model domain. Với Spring Data JPA, Querydsl hữu ích khi điều kiện tìm kiếm được ghép động, có nhiều nhánh AND/OR, join, sắp xếp hoặc phân trang mà vẫn muốn kiểm tra tên thuộc tính ở compile time.

Khi đưa Querydsl vào dự án, cần đánh giá ba vấn đề riêng:

1. **Phiên bản và tương thích**: chọn đúng nhánh Querydsl cho Java, Jakarta Persistence, Hibernate/EclipseLink và Spring Data đang dùng.
2. **Nguồn phát hành**: phân biệt dự án Querydsl gốc với fork cộng đồng OpenFeign, xác minh GitHub release và artifact trên Maven Central.
3. **Chi phí phụ thuộc**: tính cả dependency runtime, annotation processor lúc build, mã Q được sinh, cấu hình IDE/CI, bảo trì và giấy phép.

Tại thời điểm **09-11-2026**, danh sách phát hành và Maven Central cho thấy nhánh OpenFeign đã có phiên bản **7.7**, xuất bản ngày 23-09-2026. Dự án Querydsl gốc hiện vẫn liệt kê **5.1.0** là release mới nhất của repository đó. Spring Data ghi rõ việc bảo trì Querydsl đã chậm lại, cộng đồng đã fork dự án dưới OpenFeign và Spring Data hỗ trợ fork này theo cơ chế best-effort. Vì vậy, chỉ nhìn tên thư viện Querydsl là chưa đủ để quyết định dependency.

## 1. Querydsl mang lại điều gì cho Spring Data JPA?

Querydsl cung cấp DSL có kiểu dữ liệu cho truy vấn. Annotation processor đọc entity và sinh các lớp query type thường có tiền tố **Q**, ví dụ **QPerson**, **QBook**. Các lớp này phản ánh thuộc tính của domain model bằng kiểu Java.

Ví dụ, với entity:

~~~java
@Entity
public class Person {

    @Id
    private Long id;

    private String firstName;

    private String lastName;

    private Boolean active;
}
~~~

Sau khi annotation processing chạy, Querydsl tạo kiểu Q tương ứng. Code truy vấn có thể viết:

~~~java
QPerson person = QPerson.person;

List<Person> people = queryFactory
    .selectFrom(person)
    .where(
        person.firstName.containsIgnoreCase("an")
            .and(person.active.isTrue())
    )
    .orderBy(person.lastName.asc(), person.id.asc())
    .fetch();
~~~

Các biểu thức như **person.firstName**, **containsIgnoreCase**, **and** và **orderBy** được kiểm tra theo kiểu Java. Nếu đổi tên thuộc tính trong entity và build lại, compiler giúp phát hiện những query còn tham chiếu tên cũ.

Querydsl không tự thay thế JPA provider. Với Querydsl JPA, thư viện xây dựng biểu thức truy vấn và chuyển chúng qua JPA; Hibernate hoặc EclipseLink vẫn chịu trách nhiệm tạo SQL và thực thi trên database. Do đó, Querydsl không tự làm truy vấn nhanh hơn. Hiệu năng vẫn phụ thuộc SQL sinh ra, index, số lượng dữ liệu, fetch plan và execution plan của database.

## 2. Phân biệt dự án gốc và fork OpenFeign

Có hai dòng artifact cần nhận diện:

| Dòng phát hành | Repository nguồn | Maven groupId | Ghi chú |
|---|---|---|---|
| Querydsl gốc | github.com/querydsl/querydsl | com.querydsl | Repository gốc hiện liệt kê release 5.1.0 |
| Fork cộng đồng OpenFeign | github.com/OpenFeign/querydsl | io.github.openfeign.querydsl | Dòng phát triển tiếp tục với các release 6.x và 7.x |

Spring Data JPA mô tả Querydsl là thư viện truy vấn fluent có kiểu dữ liệu. Tài liệu Spring cũng nói rõ maintenance của dự án gốc đã chậm lại và cộng đồng đã fork dưới OpenFeign. Spring Data hỗ trợ fork theo best-effort, nghĩa là có tích hợp nhưng không cam kết mức hỗ trợ như một thành phần do Spring trực tiếp phát hành.

Cần phân biệt ba tên sau:

- **OpenFeign** là cộng đồng duy trì fork và repository nguồn.
- **io.github.openfeign.querydsl** là Maven groupId dùng để tải artifact fork.
- **com.querydsl** vẫn là package Java của API và các lớp Q được sinh trong fork.

Đổi groupId không có nghĩa toàn bộ import Java đổi sang package io.github.openfeign. Các import như **com.querydsl.core.types.Predicate**, **com.querydsl.jpa.impl.JPAQueryFactory** vẫn được giữ trong dòng fork theo hướng dẫn migration.

## 3. Đánh giá phiên bản hiện hành

Các nguồn phát hành cần đối chiếu:

| Nguồn | Phiên bản được liệt kê | Ý nghĩa |
|---|---:|---|
| GitHub Querydsl gốc | 5.1.0 | Release mới nhất được liệt kê trong repository gốc |
| GitHub OpenFeign/querydsl | 7.7 | Release mới nhất của fork tại ngày 09-11-2026 |
| Maven Central, OpenFeign querydsl-jpa/querydsl-apt | 7.7 | Artifact 7.7 được xuất bản ngày 23-09-2026 |
| Tài liệu Spring Data JPA | Có ví dụ cho cả hai groupId | Hướng dẫn setup, đồng thời ghi chú fork được hỗ trợ best-effort |

Một số trang hướng dẫn tĩnh có thể hiển thị phiên bản cũ hơn release mới nhất. Ví dụ trang quick start của OpenFeign từng hiển thị 7.1 trong khi danh sách phát hành và artifact Maven Central đã có 7.7. Khi chọn version, hãy kiểm tra release tag và artifact đang được publish, không sao chép một con số từ snippet cũ mà không xác minh.

### Chọn version theo nền tảng

| Nền tảng ứng dụng | Hướng lựa chọn |
|---|---|
| Ứng dụng cũ dùng Java EE với namespace javax.persistence | Giữ dòng artifact tương thích javax của Querydsl gốc; không chuyển thẳng sang fork 6+ |
| Ứng dụng đã dùng Jakarta Persistence nhưng còn phụ thuộc dòng Querydsl gốc 5.x | Dòng gốc có artifact classifier jakarta; cần kiểm tra compatibility và kế hoạch nâng cấp |
| Ứng dụng mới dùng JDK 17+, Spring Boot 3+ và Jakarta Persistence | Có thể đánh giá fork OpenFeign 6+; 7.7 là release mới nhất được tìm thấy tại ngày 09-11-2026 |
| Ứng dụng dùng Hibernate/EclipseLink phiên bản mới | Đối chiếu yêu cầu tối thiểu của fork với phiên bản provider do Spring Boot BOM quản lý và chạy integration test |

Theo migration guide của fork, từ Querydsl 6 trở đi, fork dùng namespace **jakarta.\*** thay cho **javax.\*** và yêu cầu Java 17 trở lên. Hướng dẫn migration nêu Hibernate 6+, EclipseLink 4+ và Spring Boot 3+ là các nền tảng tương ứng cho dòng Jakarta này. Với một dự án cụ thể, vẫn phải kiểm tra JPA API và provider version thực tế thay vì chỉ nhìn số phiên bản Spring Boot.

### Khác biệt quan trọng ở tọa độ Maven

Ví dụ artifact Querydsl gốc cho JPA Jakarta:

~~~xml
<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-jpa</artifactId>
    <version>5.1.0</version>
    <classifier>jakarta</classifier>
</dependency>
~~~

Ví dụ artifact JPA của fork OpenFeign:

~~~xml
<dependency>
    <groupId>io.github.openfeign.querydsl</groupId>
    <artifactId>querydsl-jpa</artifactId>
    <version>7.7</version>
</dependency>
~~~

Annotation processor cũng khác classifier:

~~~xml
<!-- Querydsl gốc, JPA Jakarta -->
<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-apt</artifactId>
    <version>5.1.0</version>
    <classifier>jakarta</classifier>
</dependency>

<!-- Fork OpenFeign, JPA -->
<dependency>
    <groupId>io.github.openfeign.querydsl</groupId>
    <artifactId>querydsl-apt</artifactId>
    <version>7.7</version>
    <classifier>jpa</classifier>
</dependency>
~~~

Artifact ID vẫn là **querydsl-jpa** và **querydsl-apt**, nhưng groupId và classifier không giống nhau. Không trộn hai dòng trong cùng classpath: chúng dùng các package Java trùng nhau, nên có thể tạo duplicate class, thứ tự classpath khó đoán và lỗi runtime khó truy tìm.

## 4. Kiểm tra nguồn phát hành và độ tin cậy

Một dependency nên được kiểm tra theo nhiều lớp, không chỉ dựa vào việc Maven tải được artifact.

### Repository và người duy trì

Xác định repository chính xác:

- Querydsl gốc: https://github.com/querydsl/querydsl
- Fork OpenFeign: https://github.com/OpenFeign/querydsl

Kiểm tra release notes, tag, contributor activity, issue, pull request và cách dự án xử lý lỗi bảo mật. Với fork cộng đồng, cần hiểu rõ ai đang duy trì và mức hỗ trợ mà tổ chức của bạn cần.

### Artifact trên Maven Central

Kiểm tra tọa độ đầy đủ:

- groupId.
- artifactId.
- version.
- classifier nếu có.
- POM và dependency được khai báo.
- ngày publish và metadata của artifact.

Không tải một JAR có tên giống Querydsl từ repository không rõ nguồn. Tên file giống nhau không chứng minh artifact có cùng publisher hoặc nội dung.

### Release tag và tính nhất quán

Đối chiếu version trong GitHub release với version trên Maven Central. Với môi trường yêu cầu kiểm soát chuỗi cung ứng phần mềm, nên xác minh tag/chữ ký khi có, checksum artifact, license, SBOM và kết quả quét dependency theo quy trình của tổ chức.

Không dùng SNAPSHOT hoặc version động cho build production. Ghim một version cụ thể giúp mọi máy developer và CI giải quyết cùng dependency graph.

### Mức hỗ trợ của Spring Data

Spring Data cung cấp tích hợp Querydsl, ví dụ **QuerydslPredicateExecutor**, nhưng tài liệu ghi rõ fork OpenFeign được hỗ trợ best-effort. Nếu hệ thống phụ thuộc sâu vào integration này, cần có integration test của dự án để kiểm tra hành vi sau mỗi lần nâng Spring Data hoặc Querydsl.

## 5. Tương thích Jakarta, Java và annotation processor

Querydsl cần sinh các lớp Q từ entity. Quá trình này diễn ra lúc compile thông qua annotation processor, không phải lúc ứng dụng xử lý request.

Fork OpenFeign 6+ sử dụng Jakarta Persistence:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
~~~

Nếu entity còn dùng:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
~~~

thì không thể chỉ đổi Maven groupId sang fork 6+ rồi mong annotation processor nhận diện đúng entity. Phải kiểm tra namespace của toàn bộ persistence stack.

Các điểm tương thích cần rà soát:

- JDK dùng để compile và chạy ứng dụng.
- Jakarta Persistence API version.
- Hibernate hoặc EclipseLink version.
- Spring Boot/Spring Data version.
- Annotation processor classifier.
- Compiler plugin và cấu hình annotation processing.
- IDE có nhận thư mục generated source hay không.

### Java 17+ và JDK 23+

Fork OpenFeign 6+ yêu cầu Java 17 trở lên theo migration guide. Tài liệu Querydsl JPA cũng lưu ý rằng trên JDK 23+, annotation processing cần được bật rõ ràng; không nên dựa vào việc javac tự dò processor trên compile classpath.

Với Maven, dùng **maven-compiler-plugin** và khai báo processor trong **annotationProcessorPaths**. Tách processor khỏi runtime classpath giúp giảm dependency không cần thiết khi chạy ứng dụng.

## 6. Cấu hình Maven cho OpenFeign Querydsl

Ví dụ sau dùng JDK 17+ và version 7.7. Version của Jakarta Persistence API trong annotation processor path cần khớp với stack mà dự án sử dụng; ví dụ dưới dùng Jakarta Persistence 3.2.0.

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <querydsl.version>7.7</querydsl.version>
</properties>

<dependencies>
    <!-- API Querydsl JPA dùng trong source code ứng dụng -->
    <dependency>
        <groupId>io.github.openfeign.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>7.7</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.15.0</version>
            <configuration>
                <release>17</release>
                <generatedSourcesDirectory>
                    target/generated-sources/java
                </generatedSourcesDirectory>
                <annotationProcessorPaths>
                    <path>
                        <groupId>io.github.openfeign.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>7.7</version>
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

Với JDK 23+, bật annotation processing theo hướng dẫn compiler hiện hành, ví dụ cấu hình **proc = full** trong Maven Compiler Plugin:

~~~xml
<configuration>
    <proc>full</proc>
</configuration>
~~~

Không sao chép version Jakarta Persistence 3.2.0 vào dự án Spring Boot 3.x nếu BOM của ứng dụng đang quản lý version khác. Hãy dùng version do nền tảng đang chọn quản lý và xác nhận compile/integration test.

### Gradle

Với Gradle, dependency runtime và annotation processor được khai báo riêng:

~~~groovy
def querydslVersion = "7.7"

dependencies {
    implementation "io.github.openfeign.querydsl:querydsl-jpa:$querydslVersion"

    annotationProcessor "io.github.openfeign.querydsl:querydsl-apt:$querydslVersion:jpa"
    annotationProcessor "jakarta.persistence:jakarta.persistence-api"

    testAnnotationProcessor "io.github.openfeign.querydsl:querydsl-apt:$querydslVersion:jpa"
    testAnnotationProcessor "jakarta.persistence:jakarta.persistence-api"
}
~~~

Cấu hình version Jakarta Persistence API theo BOM của dự án nếu Gradle cần chỉ định version tường minh. Nếu entity nằm trong module riêng, annotation processor phải được cấu hình ở module compile các entity đó.

## 7. Chi phí phụ thuộc: runtime, build và bảo trì

Querydsl không cần một server riêng hoặc một dịch vụ bên ngoài để thực thi query. Với JPA, Querydsl xây dựng biểu thức truy vấn trong ứng dụng và giao việc thực thi cho JPA provider. Tuy vậy, thư viện vẫn tạo ra chi phí ở nhiều lớp.

| Loại chi phí | Thành phần | Tác động |
|---|---|---|
| Runtime dependency | querydsl-jpa và querydsl-core cùng dependency cần thiết | Tăng artifact và classpath ứng dụng |
| Build-time dependency | querydsl-apt và Jakarta Persistence API cho processor | Tăng cấu hình compiler và thời gian compile |
| Generated source | Các lớp Q tương ứng entity | Tăng số source được compile và yêu cầu IDE/CI nhận diện generated source |
| Compatibility | JDK, Jakarta API, provider và Spring Data | Cần kiểm thử mỗi khi nâng nền tảng |
| Security/compliance | Dependency graph, license và vulnerability scan | Tăng công việc kiểm kê và cập nhật |
| Maintenance | Release cadence, issue và best-effort integration | Cần đội ngũ theo dõi fork và xử lý migration |

### Runtime cost

Ứng dụng cần thư viện Querydsl JPA để tạo và chạy truy vấn. Các lớp Q đã sinh là mã Java thông thường được compile vào ứng dụng. Không có dịch vụ Querydsl độc lập cần triển khai.

Không nên suy ra hiệu năng query chỉ từ việc dùng Querydsl. Hai câu truy vấn JPQL và Querydsl có thể tạo SQL tương tự nhau; tốc độ phụ thuộc SQL cuối cùng, index, join, số lượng hàng và cách fetch association.

### Build-time cost

Annotation processor chạy trong quá trình compile và sinh source. Khi model entity thay đổi, các lớp Q cần được tạo lại. Build sạch trên CI phải chạy annotation processing trước khi compile source sử dụng Q types.

Nếu processor bị đặt nhầm vào dependency runtime, ứng dụng mang thêm thư viện chỉ cần cho build. Dùng **annotationProcessorPaths** trong Maven hoặc configuration **annotationProcessor** trong Gradle để giữ ranh giới rõ ràng.

### Transitive dependency cost

Không chỉ đếm hai dependency trực tiếp. Hãy xem dependency graph thực tế của version đã pin, vì transitive dependencies có thể thay đổi giữa các release.

Maven:

~~~bash
mvn dependency:tree -Dincludes=io.github.openfeign.querydsl
~~~

Gradle runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Gradle annotation processor:

~~~bash
./gradlew dependencies --configuration annotationProcessor
~~~

Khi dependency graph có nhiều version cùng một thư viện, kiểm tra dependency convergence và version được Spring Boot BOM quản lý. Tránh nâng riêng JPA API hoặc Hibernate mà không xét tương thích toàn bộ stack.

## 8. Chi phí giấy phép và hỗ trợ

Tài liệu dự án OpenFeign Querydsl công bố giấy phép **Apache License 2.0**. Đây là giấy phép open source, không có phí license theo số request hoặc số instance như một dịch vụ thương mại.

Tuy vậy, “không có phí license” không đồng nghĩa tổng chi phí bằng 0:

- Tổ chức vẫn cần kiểm tra nghĩa vụ license, thông báo bản quyền và danh sách license của dependency bắc cầu.
- Không mặc định có SLA hoặc hỗ trợ thương mại chỉ vì artifact được publish trên Maven Central.
- Spring Data ghi rõ tích hợp fork là best-effort.
- Đội ngũ cần thời gian theo dõi release, CVE, tương thích và xử lý migration.

Nếu tổ chức yêu cầu support contract, thời gian phản hồi sự cố hoặc bảo đảm dài hạn, hãy đánh giá năng lực duy trì và phương án hỗ trợ riêng thay vì suy luận từ giấy phép Apache 2.0.

## 9. Tích hợp Querydsl với Spring Data JPA

Spring Data cung cấp **QuerydslPredicateExecutor** cho repository. Ví dụ:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person> {
}
~~~

Sau khi lớp QPerson được sinh, tạo predicate:

~~~java
QPerson person = QPerson.person;

Predicate predicate = person.firstName
    .containsIgnoreCase("an")
    .and(person.active.isTrue());

Iterable<Person> result = personRepository.findAll(predicate);
~~~

API executor hỗ trợ các thao tác như findAll, findOne, count và exists theo Predicate. Đây là cách nhanh để đưa điều kiện Querydsl vào repository chuẩn.

Khi cần projection tùy chỉnh, fetch join, group by hoặc truy vấn chuyên biệt, có thể dùng **JPAQueryFactory** trong custom repository:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

~~~java
@Repository
public class PersonQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PersonQueryRepository(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    public List<Person> search(String keyword) {
        QPerson person = QPerson.person;

        return queryFactory
            .selectFrom(person)
            .where(
                person.firstName.containsIgnoreCase(keyword)
                    .or(person.lastName.containsIgnoreCase(keyword))
            )
            .orderBy(person.lastName.asc(), person.id.asc())
            .fetch();
    }
}
~~~

Các ví dụ trên là các phần của ứng dụng Spring Boot có entity Person, repository và persistence context được cấu hình. Chúng không phải chương trình Java độc lập có thể chạy chỉ bằng javac.

## 10. Querydsl có đáng thêm vào dự án không?

Đánh giá lợi ích dựa trên loại truy vấn thực tế:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| CRUD và tìm kiếm theo một vài field cố định | Derived query của Spring Data |
| Truy vấn cố định, tương đối phức tạp | JPQL với @Query |
| Điều kiện JPA động có thể ghép AND/OR | Spring Data Specification hoặc Criteria API |
| Điều kiện động nhiều nhánh, join và sắp xếp cần type-safe DSL | Querydsl |
| SQL đặc thù database hoặc báo cáo dùng SQL trực tiếp | Native SQL/JdbcTemplate hoặc công cụ phù hợp |

Querydsl đáng cân nhắc khi:

- Form tìm kiếm có nhiều tiêu chí tùy chọn.
- Điều kiện AND/OR được ghép theo request.
- Có nhiều join và sort động.
- Muốn compiler phát hiện tham chiếu property không còn tồn tại.
- Có nhiều query phức tạp được tái sử dụng và cần chuẩn hóa cách viết.

Chi phí setup có thể không đáng nếu ứng dụng chỉ có vài derived query và một số JPQL đơn giản. Trong trường hợp đó, Spring Data Specification hoặc JPQL có thể đáp ứng nhu cầu mà không cần thêm thư viện và annotation processor.

## 11. Lộ trình nâng cấp từ Querydsl gốc sang OpenFeign

Migration guide của fork cho biết package Java vẫn giữ **com.querydsl.\*** và artifact ID như querydsl-jpa/querydsl-apt được giữ nguyên. Thay đổi chính là groupId, version, Jakarta namespace ở dòng 6+, và cách cấu hình annotation processor.

Checklist migration:

1. Kiểm kê tất cả artifact Querydsl trong Maven/Gradle, kể cả module SQL hoặc module backend khác.
2. Xác định dự án đang dùng javax.persistence hay jakarta.persistence.
3. Xác định JDK, Spring Boot, Spring Data và Hibernate/EclipseLink version.
4. Nếu chuyển sang fork 6+, bảo đảm stack dùng Jakarta và JDK 17+.
5. Đổi groupId từ com.querydsl sang io.github.openfeign.querydsl cho các artifact cần chuyển.
6. Đồng bộ version của querydsl-jpa và querydsl-apt.
7. Đổi classifier annotation processor từ jakarta của dòng gốc sang jpa của fork.
8. Thay cấu hình apt plugin cũ bằng maven-compiler-plugin hoặc annotationProcessor của Gradle.
9. Xóa dependency cũ để tránh hai artifact cung cấp cùng package com.querydsl.
10. Chạy clean build để xác nhận Q types được sinh lại.
11. Chạy integration test trên database/provider thực tế.
12. Kiểm tra query SQL, pagination, join, count và QuerydslPredicateExecutor sau khi nâng Spring Data.

Không sửa tay các lớp Q được sinh. Nếu build không tạo Q classes, kiểm tra annotation processor path, classifier, JDK, IDE generated-source folder và log compiler trước khi thay đổi query code.

## 12. Kiểm tra CI, dependency graph và phát hành

Một quy trình kiểm soát dependency có thể gồm:

~~~bash
mvn clean verify
mvn dependency:tree -Dincludes=io.github.openfeign.querydsl
~~~

Với Gradle:

~~~bash
./gradlew clean test
./gradlew dependencyInsight --dependency querydsl --configuration runtimeClasspath
./gradlew dependencies --configuration annotationProcessor
~~~

Trong CI, xác nhận:

- Build sạch vẫn sinh đủ Q types.
- Không phụ thuộc vào generated source còn sót từ lần compile trước.
- Runtime classpath chỉ có một dòng Querydsl.
- querydsl-jpa và querydsl-apt cùng version.
- Không có version JPA/Hibernate bị override ngoài ý muốn.
- Integration test chạy với database/provider giống môi trường mục tiêu.
- Dependency scan và license scan được thực hiện theo chính sách dự án.

Nếu IDE báo không tìm thấy QPerson nhưng Maven/Gradle build thành công, kiểm tra IDE có nhận generated source directory hay chưa. Không tự tạo QPerson bằng tay để che lỗi annotation processing.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không sinh QPerson | Annotation processor chưa được kích hoạt | Kiểm tra compiler plugin, processor path và classifier |
| Build được nhưng IDE báo Q type không tồn tại | IDE chưa nhận generated source | Đăng ký generated source directory và đồng bộ build |
| Lỗi javax/jakarta khi compile | Entity và Querydsl processor dùng namespace khác nhau | Chọn artifact tương thích với JPA namespace |
| ClassNotFoundException hoặc NoSuchMethodError | Trộn version hoặc trộn artifact gốc/fork | Kiểm tra dependency tree, chỉ dùng một dòng và đồng bộ version |
| Duplicate class trong classpath | Cả com.querydsl và io.github.openfeign.querydsl cùng được kéo vào | Loại artifact cũ hoặc dependency bắc cầu không mong muốn |
| Build CI khác máy developer | Q classes có sẵn cục bộ nhưng processor không chạy trong CI | Chạy clean build và cấu hình processor rõ ràng |
| Querydsl query không nhanh hơn JPQL | SQL cuối cùng và execution plan không tốt | Bật SQL log, kiểm tra index và execution plan |
| Spring Data executor thiếu khả năng cần dùng | QuerydslPredicateExecutor không bao phủ use case tùy chỉnh | Viết custom repository với JPAQueryFactory |
| Nâng Querydsl làm lỗi provider | Jakarta API hoặc Hibernate/EclipseLink không tương thích | Đối chiếu version platform và chạy integration test |
| Chọn version theo snippet cũ | Tài liệu tĩnh chưa cập nhật release | Kiểm tra GitHub release và Maven Central trước khi pin |

## 14. Checklist quyết định trước khi thêm dependency

- [ ] Truy vấn động có đủ phức tạp để cần DSL type-safe không?
- [ ] Specification hoặc JPQL có đáp ứng với ít dependency hơn không?
- [ ] Dự án đang dùng javax.persistence hay jakarta.persistence?
- [ ] JDK và JPA provider đáp ứng yêu cầu của dòng Querydsl được chọn không?
- [ ] Đã phân biệt repository gốc và fork OpenFeign chưa?
- [ ] Đã xác minh release tag và artifact Maven Central chưa?
- [ ] Version querydsl-jpa và querydsl-apt đã được đồng bộ chưa?
- [ ] Annotation processor có được tách khỏi runtime classpath không?
- [ ] IDE và CI có sinh/nhận Q classes ổn định không?
- [ ] Dependency tree, license và vulnerability scan đã được kiểm tra chưa?
- [ ] Có integration test bảo vệ các query quan trọng không?
- [ ] Đã tính đến best-effort support của Spring Data với fork chưa?

## 15. Kết luận

Khi đánh giá Querydsl, hãy bắt đầu từ nguồn phát hành và nền tảng tương thích. Dòng Querydsl gốc hiện liệt kê 5.1.0; fork cộng đồng OpenFeign tiếp tục phát triển và đã phát hành 7.7 tại ngày 09-11-2026. Spring Data hỗ trợ fork theo best-effort. Với dòng OpenFeign 6+, cần JDK 17+ và Jakarta Persistence.

Chi phí của Querydsl gồm dependency runtime, annotation processor, generated Q source, cấu hình IDE/CI, kiểm soát version, license và công bảo trì. Không có phí license theo request cho Apache 2.0, nhưng vẫn cần quản lý dependency và hỗ trợ vận hành.

Nếu dự án có nhiều truy vấn động phức tạp, Querydsl có thể mang lại giá trị nhờ DSL type-safe và khả năng ghép predicate. Nếu nhu cầu chỉ là CRUD hoặc vài truy vấn cố định, derived query, Specification hay JPQL có thể đơn giản hơn. Quyết định cuối cùng nên dựa trên truy vấn thực tế, compatibility matrix và chi phí bảo trì của đội ngũ.

## 16. Nguồn tham khảo và cách xác minh

Các thông tin về version và tọa độ dependency thay đổi theo thời gian. Những nguồn dưới đây được đối chiếu tại ngày 09-11-2026:

1. [Spring Data JPA – Querydsl Extension](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html): mô tả Querydsl, trạng thái bảo trì, hỗ trợ best-effort cho OpenFeign, QuerydslPredicateExecutor và cấu hình Maven/Gradle.
2. [OpenFeign Querydsl – GitHub Releases](https://github.com/OpenFeign/querydsl/releases): danh sách tag và release của fork.
3. [Maven Central – OpenFeign querydsl-jpa](https://central.sonatype.com/artifact/io.github.openfeign.querydsl/querydsl-jpa): tọa độ và version artifact đã publish.
4. [Maven Central – OpenFeign querydsl-apt](https://central.sonatype.com/artifact/io.github.openfeign.querydsl/querydsl-apt): artifact annotation processor và version đã publish.
5. [OpenFeign Querydsl – Migration Guide](https://github.com/OpenFeign/querydsl/blob/master/docs/migration.md): thay đổi groupId, Jakarta namespace, yêu cầu Java và processor classifier.
6. [OpenFeign Querydsl – JPA Tutorial](https://openfeign.github.io/querydsl/tutorials/jpa/): cấu hình annotation processor, generated Q types và cách viết query.
7. [Querydsl gốc – GitHub Releases](https://github.com/querydsl/querydsl/releases): lịch sử release của repository gốc.

Khi áp dụng vào một dự án mới, kiểm tra lại version đang publish, release note và dependency graph tại thời điểm khóa version.