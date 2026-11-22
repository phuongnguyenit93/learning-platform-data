# Lập ma trận phiên bản Java, Hibernate, Jakarta Persistence, Spring và cơ sở dữ liệu

Một dự án Java có thể build thành công nhưng vẫn lỗi khi chạy vì các thành phần persistence không cùng một thế hệ. Ví dụ: ứng dụng dùng Spring Boot 3, Hibernate 6 và Jakarta Persistence, nhưng một thư viện nội bộ vẫn import javax.persistence.Entity; hoặc ứng dụng đã nâng JDK nhưng JDBC driver cũ không hỗ trợ runtime mới; hoặc Hibernate sinh SQL khác khiến database version hiện tại không hiểu một tính năng.

Để kiểm soát rủi ro đó, nhóm cần một **ma trận tương thích phiên bản** (*version compatibility matrix*). Ma trận ghi rõ tổ hợp Java runtime/compiler, Spring Boot/Spring Framework, Hibernate ORM, Jakarta Persistence API, JDBC driver và database server đã được hỗ trợ hoặc kiểm thử. Nó giúp trả lời:

- Phiên bản Java tối thiểu và phiên bản Java được CI kiểm thử là gì?
- Spring Boot BOM quản lý Spring Framework, Hibernate và Jakarta Persistence ở phiên bản nào?
- Hibernate provider đang triển khai thế hệ javax.persistence hay jakarta.persistence?
- JDBC driver có hỗ trợ cả Java runtime và database server đang dùng không?
- Database dialect, SQL features, migration tool và Testcontainers có tương thích không?
- Tổ hợp nào là production-supported, tổ hợp nào chỉ mới compile hoặc smoke-test?
- Khi nâng cấp, phải thay đổi thành phần nào trước và cần kiểm chứng những ranh giới nào?

Bài thuộc chương **Nâng cấp và tương thích** trong module Data Persistence Relational Access ORM Hibernate. Trọng tâm là **lập, duy trì và sử dụng ma trận**, không phải chọn một con số phiên bản “mới nhất” rồi giả định mọi thành phần còn lại sẽ tương thích.

---

## 1. Vì sao phải lập ma trận?

Một ứng dụng persistence không chỉ có một dependency Hibernate. Stack điển hình:

~~~text
JDK / Java runtime
  └─ Spring Boot
       └─ Spring Framework
            └─ Spring Data JPA (nếu dùng)
                 └─ Hibernate ORM
                      └─ Jakarta Persistence API
                           └─ JDBC driver
                                └─ Database server
~~~

Ngoài ra còn có Hibernate Envers, Hibernate Validator, connection pool, migration tool, build plugins, bytecode enhancement, observability, Testcontainers và runtime container.

Các thành phần có quan hệ phụ thuộc và compatibility khác nhau:

- Spring Boot quản lý dependency versions thông qua BOM.
- Hibernate ORM triển khai một phiên bản Jakarta Persistence cụ thể.
- Hibernate Envers cần cùng dòng phiên bản với Hibernate ORM.
- JDBC driver có yêu cầu Java runtime riêng.
- Database server phải hỗ trợ SQL và features mà Hibernate/dialect sử dụng.
- Java compiler target, runtime JDK và bytecode của dependencies phải tương thích.

### 1.1. Dependency tree không phải ma trận tương thích

Dependency tree trả lời: **Build thực tế đã resolve những artifact và version nào?**

Ma trận trả lời: **Tổ hợp đó có được nhà cung cấp hỗ trợ và dự án kiểm thử trên môi trường mục tiêu hay không?**

Ứng dụng có thể resolve thành công Hibernate 6.x và Jakarta Persistence API 3.x nhưng runtime vẫn lỗi vì một thư viện khác cung cấp javax.persistence, hoặc Spring integration được viết cho Hibernate API cũ.

### 1.2. Compile được không có nghĩa chạy đúng

Một số lỗi chỉ xuất hiện lúc runtime:

- NoSuchMethodError, NoClassDefFoundError.
- ClassNotFoundException do package namespace đổi.
- AbstractMethodError do SPI/interface khác phiên bản.
- Hibernate bootstrap không nhận dialect/property cũ.
- JDBC driver không hỗ trợ server authentication/TLS protocol.
- Database không hiểu SQL syntax hoặc function được sinh ra.
- Schema validation phát hiện type/sequence behavior khác.
- Spring transaction manager và Hibernate integration không đồng bộ.
- Bytecode enhancement plugin không khớp ORM version.

### 1.3. Ma trận là tài liệu vận hành

Ma trận phải được cập nhật khi nâng Java LTS, Spring Boot, Hibernate ORM/Envers, chuyển namespace javax sang jakarta, đổi JDBC driver/database major version, thêm dialect/tenant routing hoặc thay Testcontainers/database image.

Không nên chỉ viết ma trận một lần trong tài liệu kiến trúc rồi để nó lỗi thời.

## 2. Phân biệt các loại tương thích

Một ô trong ma trận không chỉ có trạng thái “compatible” hoặc “incompatible”. Cần biết đang nói về loại tương thích nào.

| Loại | Câu hỏi | Ví dụ bằng chứng |
| --- | --- | --- |
| Source compatibility | Code compile được với API này không? | Maven/Gradle compile |
| Binary compatibility | Bytecode đã compile có chạy với library mới không? | Runtime tests, linkage checks |
| Platform compatibility | JDK, servlet container, module system có hỗ trợ không? | Runtime startup |
| Specification compatibility | Provider có triển khai Persistence API version tương ứng không? | Hibernate release docs/TCK statements |
| Framework integration | Spring integration có hỗ trợ provider/version này không? | Boot BOM, Spring docs |
| JDBC compatibility | Driver hỗ trợ Java runtime/database server không? | Driver support matrix |
| SQL/dialect compatibility | Database hiểu SQL/types/features được dùng không? | Integration tests/EXPLAIN/schema tests |
| Operational compatibility | Pool, TLS, authentication, replication, backup có hoạt động không? | Environment tests |
| Support lifecycle | Thành phần còn được bảo trì/security fixes không? | Vendor lifecycle policy |
| Project-tested compatibility | Tổ hợp đã qua CI và staging của dự án chưa? | CI matrix/release evidence |

### 2.1. Supported khác tested

- **Vendor-supported:** nhà cung cấp tuyên bố hỗ trợ tổ hợp.
- **Project-tested:** dự án đã chạy test trên tổ hợp.
- **Production-certified:** quy trình nội bộ đã xác nhận tổ hợp đủ điều kiện production.
- **Compile-only:** chỉ xác nhận source/build, chưa xác nhận runtime.
- **Experimental:** đang đánh giá, không dùng production.
- **Blocked:** đã biết không tương thích hoặc không còn được chấp nhận.

Một tổ hợp vendor-supported vẫn có thể lỗi do application mapping, query, database extensions hoặc cấu hình riêng. Một tổ hợp chạy được trong một test đơn lẻ cũng không có nghĩa vendor hỗ trợ.

### 2.2. Không suy ra tương thích bắc cầu

Nếu Spring Boot hỗ trợ Java 17 và Hibernate hỗ trợ Java 17, không tự động kết luận mọi phiên bản Hibernate đều được Spring Boot line đó hỗ trợ. Tương thích phải xét **tổ hợp cụ thể** và integration layer, không chỉ từng thành phần đứng riêng.

## 3. Các trục phải có trong ma trận

Một ma trận thực dụng nên có ít nhất những trục sau:

| Trục | Cần ghi |
| --- | --- |
| Java | JDK build, minimum runtime, production runtime, compiler release |
| Spring Boot | Release line, patch được quản lý |
| Spring Framework | Version do Boot BOM quản lý |
| Spring Data JPA | Version nếu ứng dụng dùng |
| Hibernate ORM | Core provider version |
| Jakarta Persistence | API artifact/version và namespace |
| Hibernate Envers | Version khớp Hibernate core |
| JDBC driver | Artifact, version, Java/server compatibility |
| Database | Product, major/minor, extensions, configuration |
| Dialect | Dialect class/auto-detection behavior |
| Connection pool | HikariCP hoặc provider khác |
| Migration | Flyway/Liquibase và schema version |
| Build | Maven/Gradle, compiler plugin, test plugin |
| Runtime | OS/container/application server |
| Test | Testcontainers image, integration test profile |
| Status | Supported/tested/experimental/blocked |
| Evidence | Release notes, support docs, CI run, incident record |

### 3.1. Ghi rõ phạm vi phiên bản

Đừng viết:

~~~text
Java: 17+
Hibernate: 6
Database: PostgreSQL
~~~

Hãy viết rõ:

~~~text
Java runtime: 17 (Temurin distribution)
Java compiler release: 17
Spring Boot: 3.3.x, exact patch pinned by build
Spring Framework: version resolved by Boot BOM
Hibernate ORM: version resolved by Boot BOM
Jakarta Persistence: API/provider version resolved by BOM
JDBC driver: PostgreSQL JDBC exact patch
Database: PostgreSQL 16.x
Test database: same major line, pinned image digest
~~~

Dấu x trong ví dụ chỉ biểu thị release line; production lockfile/build phải chứa exact patch version.

## 4. Hai namespace Persistence: javax và jakarta

Đây là một ranh giới lớn khi nâng từ hệ Java EE cũ sang Jakarta EE.

### 4.1. Trước Jakarta EE 9

Code JPA thường import:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.ManyToOne;
import javax.persistence.Version;
~~~

Các API thuộc package javax.persistence, ví dụ JPA 2.2.

### 4.2. Từ Jakarta EE 9

Namespace đổi thành:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Version;
~~~

Jakarta Persistence 3.x dùng jakarta.persistence.

### 4.3. Đây là binary/source break, không chỉ đổi tên dependency

javax.persistence.Entity và jakarta.persistence.Entity là hai class khác nhau. Java không coi chúng là cùng một annotation dù tên đơn giản giống nhau.

Nếu một entity import javax.persistence.Entity nhưng Hibernate 6/Jakarta stack tìm jakarta.persistence.Entity, entity có thể không được nhận diện đúng như mong đợi.

~~~java
// Legacy namespace
import javax.persistence.Entity;

// Jakarta namespace
import jakarta.persistence.Entity;
~~~

Không thể sửa vấn đề chỉ bằng cách đặt cả hai API JAR vào classpath. Hai namespace không thay thế nhau.

### 4.4. Quy tắc thế hệ thường gặp

| Thế hệ stack | Persistence namespace | Ghi chú |
| --- | --- | --- |
| Spring Boot 2.x / Spring 5.x | javax.persistence | Dòng legacy Java EE/JPA |
| Spring Boot 3.x / Spring 6.x | jakarta.persistence | Jakarta EE 9+ namespace |
| Hibernate ORM 5.6 | JPA 2.2 / javax.persistence | Dòng Hibernate 5 legacy |
| Hibernate ORM 6.x | Jakarta Persistence 3.x | Kiểm tra mức API cụ thể theo minor |
| Hibernate ORM 7.x | Jakarta Persistence 3.2 line | Kiểm tra Java minimum và integration theo minor |

Đây là **bản đồ thế hệ**, không phải danh sách đầy đủ mọi minor/patch hoặc bảo đảm mọi combination Boot/Hibernate được hỗ trợ.

### 4.5. Không để hai namespace cùng tồn tại trong domain model

Một thư viện nội bộ dùng javax.persistence có thể làm migration khó khăn. Cần tìm entity classes, @Embeddable, @MappedSuperclass, attribute converters, persistence listeners, repository signatures, custom Hibernate types, validation annotations, servlet APIs, XML mapping và reflection code tìm annotation theo class name.

Đừng chỉ thay import trong entity classes rồi kết luận đã chuyển xong. Một số Java SE packages vẫn dùng namespace javax, ví dụ javax.sql, javax.crypto và javax.net; chỉ chuyển những Jakarta EE APIs đã đổi namespace.

## 5. Java version: runtime, compiler và dependency bytecode

Java version trong ma trận cần phân biệt:

1. JDK dùng build.
2. Compiler source/target hoặc --release.
3. Java runtime production.
4. Minimum Java runtime của từng library.
5. Java runtime trong CI/test/production container.

Ví dụ Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Ví dụ Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

### 5.1. source, target và release

- **source**: cú pháp Java được compiler chấp nhận.
- **target**: bytecode target.
- **release**: đồng thời ràng buộc language/API surface theo Java release tương ứng.

Với build hiện đại, --release thường giúp tránh compile trên JDK mới nhưng vô tình dùng API không tồn tại ở runtime cũ.

### 5.2. JDK build mới không tự làm app tương thích runtime cũ

Một ứng dụng compile với JDK 21 nhưng dùng API Java 21 sẽ không chạy trên Java 17 chỉ vì class files có thể được cấu hình target thấp trong một số phần. --release 17 giới hạn API compile, nhưng dependencies cũng phải có bytecode/runtime requirements phù hợp.

### 5.3. Bytecode version

Java class file có major version. Runtime cũ không đọc được class file mới hơn và có thể báo:

~~~text
UnsupportedClassVersionError
~~~

Vì vậy kiểm tra bytecode của dependencies quan trọng, nhất là libraries mới và build plugins.

### 5.4. LTS và patch updates

Java 8, 11, 17, 21 là những mốc LTS quen thuộc; việc chọn runtime cần theo support policy của tổ chức, vendor và nền tảng triển khai. Patch updates trong cùng LTS vẫn cần kiểm thử TLS, GC, JIT, security provider và container behavior.

Không ghi “Java 17” rồi bỏ qua distribution/patch nếu production cần reproducibility.

## 6. Spring Boot, Spring Framework và dependency management

Spring Boot không chỉ là một thư viện; nó quản lý một tập dependency versions đã được tích hợp với nhau.

Ví dụ Maven:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Đây là ví dụ minh họa Boot 3.3.0, không phải khuyến nghị dùng patch đó cho production. Khi đã dùng Boot parent/BOM, thông thường không cần khai báo version thủ công cho Hibernate/Spring dependencies mà BOM quản lý.

### 6.1. Spring Boot BOM là điểm xuất phát của ma trận

BOM quản lý một tập version đã được release train phối hợp. Trước khi override Hibernate, Spring Framework, Jakarta APIs hoặc HikariCP, phải biết version mặc định do BOM chọn, lý do cần override, compatibility statement của Boot line, integration tests sẽ chứng minh gì và kế hoạch bỏ override khi Boot cập nhật BOM.

### 6.2. Representative release-line map

Bảng sau giúp nhận diện các thế hệ phổ biến. Nó **không thay thế dependency tree của patch version cụ thể** và không tuyên bố mọi patch trong release line đều tương đương.

| Spring Boot line | Spring Framework line | Hibernate ORM line thường được quản lý | Java baseline của Boot line | Persistence namespace |
| --- | --- | --- | --- | --- |
| 2.7.x | 5.3.x | 5.6.x | Java 8+ | javax.persistence / JPA 2.2 |
| 3.0.x | 6.0.x | 6.1.x | Java 17+ | jakarta.persistence |
| 3.1.x | 6.0.x | 6.2.x | Java 17+ | jakarta.persistence |
| 3.2.x | 6.1.x | 6.3.x | Java 17+ | jakarta.persistence |
| 3.3.x | 6.1.x | 6.5.x | Java 17+ | jakarta.persistence |
| 3.4.x | 6.2.x | 6.6.x | Java 17+ | jakarta.persistence |
| 3.5.x | 6.2.x | 6.6.x line | Java 17+ | jakarta.persistence |

Các version trên là **mốc đại diện để hiểu release train**, không phải cam kết mọi patch Boot 3.x resolve đúng một patch Hibernate duy nhất. Hãy đọc dependency management của chính Boot patch đang dùng và lưu kết quả thực tế vào ma trận dự án.

### 6.3. Spring Framework không nên override riêng tùy tiện

Một Boot release line tích hợp Spring Framework modules theo một bộ version. Nếu override spring-core, spring-context, spring-orm, spring-tx riêng lẻ, có thể tạo tập module Spring lệch version.

Nếu cần Spring Framework mới hơn, trước tiên kiểm tra Boot release line tương ứng hoặc có quyết định quản lý dependency có kiểm thử rõ.

### 6.4. Spring Data JPA cũng là một trục riêng

Spring Data JPA có version line gắn với Spring Data release train và Boot BOM. Nó tích hợp với Jakarta Persistence/Hibernate nhưng không phải Hibernate.

Cần ghi version thực tế của spring-data-jpa, spring-data-commons, spring-orm và spring-tx. Không tự nâng riêng Spring Data JPA qua nhiều release train vì API repository/query implementation có thể đổi.

## 7. Hibernate ORM và Jakarta Persistence API

Hibernate ORM là provider thực thi Jakarta Persistence. API version và provider version phải phù hợp.

### 7.1. Representative Hibernate generations

| Hibernate ORM generation | Java baseline khái quát | Persistence API generation | Namespace | Ghi chú |
| --- | --- | --- | --- | --- |
| 5.6.x | Java 8+ | JPA 2.2 | javax.persistence | Legacy line; kiểm tra support lifecycle |
| 6.0–6.1 | Java 11+ theo dòng Hibernate 6 ban đầu | Jakarta Persistence 3.0 generation | jakarta.persistence | API/behavior migration lớn từ Hibernate 5 |
| 6.2–6.6 | Java 11+ theo Hibernate 6 line; Boot 3 thường yêu cầu Java 17 | Jakarta Persistence 3.1 generation | jakarta.persistence | Các minor bổ sung behavior/features |
| 7.x | Java 17+ theo dòng Hibernate 7 | Jakarta Persistence 3.2 generation | jakarta.persistence | Xác nhận exact minor/provider integration |

Minimum Java của Hibernate không nhất thiết là minimum Java của ứng dụng: nếu Boot line yêu cầu Java 17 thì toàn stack phải chạy ít nhất Java 17 dù Hibernate artifact riêng có thể chạy trên Java thấp hơn.

### 7.2. Không tự pin jakarta.persistence-api khác provider

~~~xml
<dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
    <version>...</version>
</dependency>
~~~

Dependency explicit có thể ghi đè version được provider/framework release train quản lý. Chỉ làm khi có lý do và xác minh provider support API đó.

Với Spring Boot, ưu tiên BOM; với ứng dụng container-managed, kiểm tra API do container cung cấp để tránh duplicate/conflicting classes.

### 7.3. Hibernate ORM và Envers phải được căn chỉnh

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-core</artifactId>
</dependency>

<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
</dependency>
~~~

Trong dự án Boot, BOM thường quản lý version. Nếu khai báo thủ công, giữ Hibernate Envers cùng version line với Hibernate core trừ khi tài liệu chính thức của release chỉ rõ cấu hình khác.

Các module Hibernate bổ sung như spatial, community dialects và processor cũng cần xem compatibility của đúng dòng release.

### 7.4. Hibernate 5 sang 6 không phải patch upgrade

Những thay đổi có thể ảnh hưởng:

- javax.persistence sang jakarta.persistence.
- Hibernate internal APIs và SPI.
- Type system và custom UserType/BasicType.
- SQL dialects và function registration.
- Identifier generation.
- Query/HQL parsing và behavior.
- Criteria/metadata APIs.
- Schema tooling.
- Logging categories và configuration properties.
- Bytecode enhancement.
- Cache integration.
- Envers mappings/query behavior.

Nếu ứng dụng dùng custom Hibernate types, listeners, interceptors, dialect subclasses hoặc code gọi org.hibernate internals, cần inventory riêng.

## 8. Cách đọc ma trận ví dụ cho Spring Boot

Có thể xây các profile đại diện:

### 8.1. Legacy profile: Boot 2.7

| Thành phần | Giá trị đại diện |
| --- | --- |
| Java | 8/11/17 tùy deployment/support policy của patch |
| Spring Boot | 2.7.x |
| Spring Framework | 5.3.x |
| Hibernate ORM | 5.6.x |
| JPA API | 2.2 |
| Namespace | javax.persistence |
| Envers | Cùng Hibernate 5.6 line |
| JDBC | Driver được xác nhận cho JDK + DB server |
| DB | Major version được dự án hỗ trợ/test |
| Trạng thái | Legacy/maintenance theo lifecycle của tổ chức |

Đây là baseline để nhận diện hệ cũ; không suy ra Boot 2.7 còn được vendor hỗ trợ miễn phí hoặc an toàn production ở thời điểm triển khai.

### 8.2. Jakarta migration profile: Boot 3.0/3.1

| Thành phần | Giá trị đại diện |
| --- | --- |
| Java | 17+ |
| Spring Boot | 3.0.x hoặc 3.1.x |
| Spring Framework | 6.0.x |
| Hibernate ORM | 6.1.x hoặc 6.2.x theo Boot line |
| Persistence API | Jakarta Persistence 3.x theo provider |
| Namespace | jakarta.persistence |
| Envers | Cùng Hibernate ORM line |
| JDBC | Driver hỗ trợ Java 17 và DB mục tiêu |
| DB | Giữ nguyên major ban đầu trong migration đầu tiên nếu có thể |

Điểm lớn nhất là chuyển namespace và integration stack. Tách migration này khỏi thay đổi database major version giúp thu hẹp phạm vi lỗi.

### 8.3. Boot 3.2–3.5 profile

Các release lines này tiếp tục nâng Spring Framework/Hibernate trong hệ Jakarta. Dùng BOM của Boot patch thực tế để xác định exact versions; đừng dựa vào bảng đại diện để override dependencies.

### 8.4. Hibernate 7 profile

Nếu cần Hibernate ORM 7/Jakarta Persistence 3.2, trước tiên xác định Spring Boot/Spring Framework line có chính thức quản lý provider đó hay không. Nếu chưa, đây là integration decision riêng cần proof-of-concept, compatibility tests và support ownership. Không chỉ đổi hibernate-core version trong một Boot 3 project rồi tuyên bố đã lên Hibernate 7.

## 9. Database và JDBC driver là hai trục khác nhau

Một ma trận thường chỉ ghi “PostgreSQL 16” hoặc “Oracle 19c” rồi bỏ qua driver. Điều đó chưa đủ.

### 9.1. JDBC driver cần tương thích với cả hai phía

Driver phải đáp ứng Java runtime version, database server major/minor, JDBC specification level cần dùng, TLS/certificate/authentication, connection pooling behavior, SQL type mapping, prepared statement behavior, generated keys, sequences, batching, LOBs và failover/replication features nếu dùng.

Driver mới có thể hỗ trợ Java runtime mới nhưng có behavior khác với DB server cũ; driver cũ có thể kết nối được nhưng thiếu hỗ trợ tính năng server mới.

### 9.2. Database server version

Cần ghi product/vendor, major/minor/patch, deployment flavor, extensions/plugins, collation/encoding/timezone, compatibility/SQL mode, authentication/TLS policy, replication/HA topology và server parameters ảnh hưởng ORM.

Không dùng một dòng “MySQL” cho mọi MySQL/MariaDB/Aurora-compatible engine. Tương thích giao thức không đồng nghĩa mọi SQL semantics giống nhau.

### 9.3. Representative database matrix

Bảng sau là **mẫu cách ghi**, không phải tuyên bố support chính thức cho mọi tổ hợp Hibernate/driver:

| Database | Server line mẫu | JDBC driver artifact mẫu | Những điểm cần xác minh |
| --- | --- | --- | --- |
| PostgreSQL | 15/16/17 | org.postgresql:postgresql | Driver support Java/server, sequences, JSON/JSONB, arrays, timezone, cursor fetch, SSL |
| MySQL | 8.0/8.4 | com.mysql:mysql-connector-j | SQL mode, collations, generated keys, timezone, JSON, authentication, TLS |
| MariaDB | 10.11/11.x | org.mariadb.jdbc:mariadb-java-client | Phân biệt driver MariaDB với MySQL Connector/J, dialect, sequence/identity, JSON behavior |
| Microsoft SQL Server | 2019/2022 | com.microsoft.sqlserver:mssql-jdbc | Java runtime classifier/support, datetime types, identity, snapshot isolation, TLS |
| Oracle Database | 19c/21c/23ai tùy tổ chức | com.oracle.database.jdbc:ojdbc11 hoặc artifact phù hợp | JDK requirement, driver/database interoperability, NUMBER/DATE/TIMESTAMP, LOB, sequences |

Version driver cụ thể phải được pin theo official driver compatibility matrix và chính sách security patch của dự án. Không chọn version chỉ vì nó là version mới nhất trên Maven Central.

### 9.4. Không mặc định mọi dialect tương thích

Hibernate 6 có thay đổi đáng kể về dialect architecture và khả năng auto-detect dựa trên database metadata. Một số dialect class cũ đã được tổ chức lại hoặc chuyển sang module riêng.

Hãy kiểm tra database version có được dialect hỗ trợ không, Hibernate có auto-detect dialect phù hợp không, custom dialect có dùng internal APIs đã đổi không, SQL functions/types được app sử dụng có được đăng ký không và community dialect module có cần thêm không.

Đừng copy org.hibernate.dialect.PostgreSQL95Dialect từ bài hướng dẫn cũ vào Hibernate 6 mà không kiểm tra class đó còn tồn tại/hợp lệ trong version mục tiêu.

## 10. Mẫu ma trận dự án đầy đủ

Một bảng trung tâm có thể trông như sau:

| Dimension | Production hiện tại | Target upgrade | Bằng chứng bắt buộc |
| --- | --- | --- | --- |
| JDK distribution | Temurin 17, patch pinned | Temurin 21, patch pinned | Runtime smoke, TLS, GC, JFR |
| Compiler release | 17 | 17 hoặc 21 theo policy | Reproducible build |
| Spring Boot | 3.2.x exact patch | 3.4.x exact patch | Boot release notes, CI |
| Spring Framework | BOM-managed 6.1.x | BOM-managed 6.2.x | Boot dependency management |
| Spring Data JPA | BOM-managed | BOM-managed | Repository integration tests |
| Hibernate ORM | BOM-managed 6.3.x | BOM-managed 6.6.x | Hibernate migration guide |
| Jakarta Persistence | Provider-aligned 3.1 | Provider-aligned 3.1 | API/provider compatibility |
| Hibernate Envers | Same ORM line | Same ORM line | Audit integration tests |
| JDBC driver | PostgreSQL JDBC exact patch | Supported patched release | Driver support matrix |
| Database server | PostgreSQL 15.x | PostgreSQL 16.x | SQL/schema/lock tests |
| Connection pool | HikariCP BOM-managed | BOM-managed | Pool/transaction stress |
| Migration tool | Flyway exact patch | Compatible patch | Migration/rollback tests |
| Test database | Testcontainers image pinned | Target DB image pinned | Integration suite |
| Status | Production certified | Candidate | Sign-off/evidence |

Các version ở đây chỉ là **ví dụ cách ghi current/target**. Dự án phải thay bằng actual resolved versions; không copy thành dependency policy.

### 10.1. Thêm status rõ ràng

| Status | Ý nghĩa |
| --- | --- |
| SUPPORTED | Vendor/platform tuyên bố hỗ trợ |
| TESTED | CI/integration test của dự án đã chạy |
| CERTIFIED | Đã qua acceptance/staging và được phê duyệt production |
| EXPERIMENTAL | Đang thử nghiệm, không production |
| BLOCKED | Không tương thích hoặc có rủi ro chưa xử lý |
| EOL | Hết vòng đời theo policy |
| UNKNOWN | Chưa có bằng chứng |

Có thể ghi nhiều trạng thái theo dimension: vendor=SUPPORTED, project=TESTED, production=NOT_CERTIFIED.

### 10.2. Gắn evidence link

Mỗi quyết định quan trọng nên có official support matrix URL/version, release notes/migration guide, build scan/dependency tree artifact, CI workflow/run ID, integration test report, database image digest và ADR/ticket chấp thuận exception.

Không chỉ ghi “team đã test” mà không có commit/run hoặc test scope.

## 11. Cách lấy version thực tế từ Maven

### 11.1. Kiểm tra parent/BOM

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
</parent>
~~~

Nếu dùng dependency management riêng, kiểm tra import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

### 11.2. Dependency tree

~~~bash
mvn dependency:tree -Dincludes=org.hibernate.orm:hibernate-core
mvn dependency:tree -Dincludes=jakarta.persistence:jakarta.persistence-api
mvn dependency:tree -Dincludes=org.springframework:spring-orm
mvn dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Xem cả transitive dependencies và version conflict/omitted nodes. Không chỉ đọc version trong pom.xml vì BOM/transitive dependency có thể quyết định version thực tế.

### 11.3. Effective POM

~~~bash
mvn help:effective-pom
~~~

Effective POM giúp thấy dependency management sau khi parent/profiles/properties được áp dụng.

### 11.4. Dependency convergence

Maven Enforcer có thể kiểm tra dependency convergence/upper bounds theo policy dự án. Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Rule có thể cần exclusions/exception được ghi nhận. Không thêm Enforcer rồi bỏ qua failures bằng cách disable rule vô thời hạn.

## 12. Cách lấy version thực tế từ Gradle

### 12.1. Dependency constraints/BOM

~~~kotlin
dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.3.0")
    )
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
~~~

Trong dự án dùng Spring Boot Gradle plugin, dependency management có thể được thiết lập theo cách khác. Tránh import cùng BOM nhiều lần với version conflict.

### 12.2. Dependency insight

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency hibernate-core \
  --configuration runtimeClasspath
~~~

Dùng dependencyInsight để biết dependency nào kéo version, version nào được chọn và tại sao.

### 12.3. Locking

Gradle dependency locking có thể pin resolved versions để build reproducible. Khi update lockfile, review thay đổi có chủ đích và chạy compatibility tests; lockfile không tự chứng minh version tương thích.

## 13. Ma trận Java × Spring Boot × Hibernate

Đừng tạo toàn bộ tích Descartes của mọi phiên bản Java, Boot, Hibernate. Hãy chỉ liệt kê các tổ hợp có ý nghĩa và được hỗ trợ.

Ví dụ:

| Java runtime | Boot 2.7 / Spring 5.3 | Boot 3.1 / Spring 6.0 | Boot 3.3 / Spring 6.1 | Boot 3.4 / Spring 6.2 |
| --- | --- | --- | --- | --- |
| Java 8 | Legacy candidate; kiểm tra exact patch | Không | Không | Không |
| Java 11 | Legacy candidate; kiểm tra support | Không với Boot 3 | Không | Không |
| Java 17 | Có thể chạy theo support của Boot 2.7 patch | Candidate | Candidate | Candidate |
| Java 21 | Kiểm tra Boot 2.7 support/tested patch | Candidate theo Boot line | Candidate | Candidate |
| Java 25 | Không suy ra hỗ trợ | Kiểm tra vendor line | Kiểm tra vendor line | Kiểm tra vendor line |

Bảng này chỉ minh họa cách đánh dấu candidate/blocked; Java compatibility cần dựa vào exact Spring Boot patch và JDK vendor policy.

### 13.1. Dấu X phải có lý do

Một ô NO có thể do framework yêu cầu Java cao hơn, namespace Persistence không tương thích, vendor không support, app đã dùng API không có ở runtime, CI không còn test hoặc database driver không support.

Ghi lý do và evidence, đừng chỉ đặt dấu X.

### 13.2. Tách minimum supported và tested JDK

~~~text
Minimum runtime by framework: 17
CI-tested runtime: 17, 21
Production runtime: 21
Developer local runtime: 21
~~~

Nếu vendor hỗ trợ Java 17 nhưng dự án chỉ CI-test Java 21, không ghi “Java 17 tested”.

## 14. Database × driver × Hibernate dialect matrix

Một database matrix nên có từng environment/server version và driver version.

| Database server | JDBC driver | Hibernate line | Dialect | Test focus |
| --- | --- | --- | --- | --- |
| PostgreSQL 15 | PostgreSQL JDBC pinned | Hibernate 6.6.x | Auto-detect hoặc dialect phù hợp | JSONB, arrays, sequences, timestamps, locking |
| PostgreSQL 16 | PostgreSQL JDBC pinned | Hibernate 6.6.x | Auto-detect hoặc dialect phù hợp | DDL, generated keys, query plans, isolation |
| MySQL 8.0 | MySQL Connector/J pinned | Hibernate 6.6.x | MySQL dialect line | SQL mode, collation, timezone, identity |
| SQL Server 2022 | Microsoft JDBC pinned | Hibernate 6.6.x | SQL Server dialect line | datetime precision, pagination, locking |
| Oracle 19c | Oracle JDBC pinned | Hibernate 6.6.x | Oracle dialect line | NUMBER mapping, sequences, LOB, pagination |

Đây là matrix **project-test example**, không phải vendor guarantee. Thay các version mẫu bằng tổ hợp server/driver/provider thực tế.

### 14.1. Test các kiểu dữ liệu quan trọng

- UUID.
- BigDecimal precision/scale.
- Instant, OffsetDateTime, LocalDateTime.
- Boolean representation.
- JSON/JSONB.
- Arrays.
- Enum mapping.
- LOB/BLOB/CLOB.
- Binary/UUID storage.
- Generated identity/sequence.
- Timestamp precision.
- Collation/case sensitivity.
- Null ordering.
- Numeric overflow/rounding.

### 14.2. Test SQL semantics, không chỉ schema create

Một schema có thể được Hibernate tạo thành công nhưng query behavior khác: pagination syntax, LIMIT/OFFSET hoặc FETCH FIRST, window functions, RETURNING/generated keys, locking clauses, batch insert, upsert/merge, JSON operators/functions, case-insensitive search và timezone conversions.

### 14.3. Dialect không sửa database server version

Hibernate dialect biết cách sinh SQL phù hợp database family/version, nhưng không nâng cấp database. Nếu app dùng một SQL feature chỉ có trong DB major mới, đặt dialect class cũ không làm feature xuất hiện.

## 15. Các dependency đặc biệt cần căn chỉnh

### 15.1. Hibernate Envers

- Dùng cùng release line với Hibernate ORM.
- Kiểm tra revision entity annotations/imports theo namespace.
- Test audit table schema và query behavior.
- Test Audited mappings, relation audit, custom revision listener.
- Kiểm tra migration từ schema cũ.

### 15.2. Hibernate Validator

Validator và Jakarta Validation API là trục khác với Persistence API. Từ thế hệ Jakarta, annotation namespace cũng có thể chuyển từ javax.validation sang jakarta.validation. Không suy rằng chỉ đổi persistence imports là xong.

### 15.3. HikariCP

Boot thường quản lý HikariCP version. Nếu override, kiểm tra Java baseline, JDBC driver behavior, pool metrics và transaction manager. Một Hikari upgrade có thể ảnh hưởng connection lifecycle/validation nhưng không thay database driver compatibility.

### 15.4. Flyway/Liquibase

Migration tool cần hỗ trợ Java runtime, database server và syntax migrations. Kiểm tra database support module/artifact nếu tool yêu cầu, version driver mà migration tool sử dụng, locking/history table behavior, baseline/repair/rollback policy và generated DDL so với Hibernate schema validation.

### 15.5. Testcontainers

Testcontainers cần Docker/runtime environment, module image và JDBC driver tương thích. Pin image theo major/minor hoặc digest để CI không tự thay database version khi upstream tag thay đổi.

### 15.6. Bytecode enhancement

Nếu build dùng Hibernate enhancement plugin, plugin version phải được căn chỉnh với Hibernate line và Maven/Gradle build. Enhancement chạy sai version có thể tạo bytecode không phù hợp hoặc bỏ sót enhancement settings.

## 16. Ma trận theo feature, không chỉ theo artifact

Một tổ hợp version có thể khởi động được nhưng một feature quan trọng chưa được kiểm chứng. Thêm bảng feature compatibility:

| Feature | Java | Spring | Hibernate | Persistence API | Database/driver | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Basic CRUD | JDK 21 | Boot 3.4 | ORM 6.6 | Jakarta 3.1 | PostgreSQL 16 | Tested |
| Envers auditing | JDK 21 | Boot 3.4 | Envers 6.6 | Jakarta 3.1 | PostgreSQL 16 | Tested |
| Batch insert | JDK 21 | Boot 3.4 | ORM 6.6 | Jakarta 3.1 | PostgreSQL 16 | Tested |
| JSON mapping | JDK 21 | Boot 3.4 | ORM 6.6 | Jakarta 3.1 | PostgreSQL 16 | Experimental |
| Multi-tenancy | JDK 21 | Boot 3.4 | ORM 6.6 | Jakarta 3.1 | PostgreSQL 16 | Tested |
| StatelessSession | JDK 21 | Boot 3.4 | ORM 6.6 | Jakarta 3.1 | PostgreSQL 16 | Not used |

Các trạng thái phải phản ánh test suite thực tế. Không ghi Tested chỉ vì framework có feature.

### 16.1. Vì sao feature matrix hữu ích?

Một nâng cấp có thể không phá CRUD nhưng thay đổi Envers revision behavior, query result ordering, sequence allocation, batch insert, custom type mapping, multi-tenant routing, LOB handling, lock timeout hoặc second-level cache serialization.

Feature matrix giúp QA tập trung vào những contract ứng dụng thật sự dùng.

## 17. Dependency alignment: tránh tự tạo version conflict

### 17.1. Ưu tiên một BOM làm nguồn quản lý chính

Với Spring Boot, dùng Spring Boot parent hoặc Boot BOM; không pin thủ công Spring/Hibernate modules nếu không cần; ghi exception/override trong dependency policy; kiểm tra effective POM/runtimeClasspath sau resolve.

### 17.2. Không override một module Hibernate đơn lẻ

Ví dụ rủi ro:

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-core</artifactId>
    <version>6.6.0.Final</version>
</dependency>
~~~

trong khi Envers hoặc dialect modules vẫn ở version cũ do BOM/explicit dependency khác. Hibernate modules có thể phụ thuộc API nội bộ; hãy align version.

### 17.3. Không có hai Persistence API jars không chủ đích

Kiểm tra dependency tree để phát hiện đồng thời:

~~~text
javax.persistence:javax.persistence-api
jakarta.persistence:jakarta.persistence-api
~~~

Có thể một legacy dependency kéo javax.persistence. Không xóa bừa vì thư viện đó có thể thực sự cần API cũ; cần nâng/loại/thay thư viện hoặc cách ly module.

### 17.4. Không ép tất cả transitive versions bằng exclusions vô điều kiện

Exclusion có thể làm build compile nhưng runtime thiếu class. Khi loại một transitive dependency, ghi lý do và kiểm tra runtime linkage.

### 17.5. Dùng dependency analysis như tín hiệu

Các công cụ hữu ích: Maven dependency:tree, Maven help:effective-pom, Maven Enforcer, Gradle dependencies/dependencyInsight, Gradle dependency locking, SBOM generation và dependency scanners.

Tool báo dependency unused/conflict không thay thế review framework compatibility.

## 18. Lập ma trận CI

Một ma trận CI hữu ích chỉ kiểm thử tổ hợp có mục đích, không chạy mọi combination có thể.

Ví dụ GitHub Actions matrix minh họa:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: [17, 21]
    database:
      - postgres:15
      - postgres:16
    include:
      - java: 21
        database: postgres:16
        profile: production-candidate

steps:
  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: "21"
  - run: ./mvnw -B verify
~~~

Đây là skeleton; thực tế cần service container/Testcontainers, credentials an toàn và matrix expression hợp lệ theo workflow hoàn chỉnh.

### 18.1. Chọn matrix theo mục tiêu

- **Minimum JDK:** kiểm tra runtime thấp nhất được hỗ trợ.
- **Production JDK:** kiểm tra đúng JDK triển khai.
- **Database min/max:** kiểm tra database versions còn được hỗ trợ.
- **Target upgrade:** kiểm tra candidate stack.
- **Cross-version smoke:** chạy migration/compatibility suite khi thay đổi major.

Không cần chạy toàn bộ test suite trên mọi JDK/database combination nếu chi phí quá cao; có thể phân tầng smoke/integration/full tests.

### 18.2. Ma trận build không nên dùng floating tags

Ví dụ postgres:latest làm CI có thể đổi database major bất ngờ. Pin image tag cụ thể, tốt hơn là digest khi cần reproducibility.

Tương tự, không dùng 1.+, 6.+, latest.release cho dependency production nếu yêu cầu build tái lập.

### 18.3. Matrix phải có test runtime thực

Một compile-only job không đủ. Ít nhất cần application context startup, Hibernate metadata/bootstrap, connection acquisition, schema validation/migration, CRUD transaction, query pagination/sorting, optimistic locking, rollback, batch writes, Envers nếu dùng, native SQL/custom types và connection pool shutdown/restart.

## 19. Chiến lược nâng cấp: thay đổi theo từng ranh giới

Không nâng Java, Spring Boot, Hibernate, JDBC driver và database major trong một bước nếu không có lý do bắt buộc. Khi tất cả đổi cùng lúc, failure attribution rất khó.

### 19.1. Inventory trước khi nâng

Lập danh sách JDK và vendor/patch, Spring Boot/Spring Framework/Spring Data, Hibernate modules và custom integrations, javax.* imports, JPA XML mappings, custom Hibernate types/dialects/listeners, JDBC driver, DB server/extensions, migration tool, Testcontainers, connection pool settings, runtime container/server và native SQL/stored procedures.

### 19.2. Chọn một target stack đã được support

Đọc compatibility requirements của Boot line mục tiêu và dependency management. Chốt JDK, database và driver target trước khi chỉnh code.

### 19.3. Nâng JDK trong stack hiện tại khi có thể

Tách thay đổi JDK khỏi major framework migration để phát hiện lỗi Java runtime/TLS/GC/build plugins độc lập. Nếu JDK hiện tại đã EOL hoặc target framework yêu cầu JDK cao hơn, lên kế hoạch chuyển trước hoặc đồng thời có kiểm soát.

### 19.4. Chuyển namespace javax sang jakarta

Đây là migration code và library ecosystem: source imports, servlet/filter APIs, validation APIs, persistence annotations, XML descriptors, custom integrations và generated code.

Dùng IDE/refactoring/search có kiểm soát, rồi compile và test runtime. Không thay thế toàn bộ chuỗi javax. vì một số Java SE packages vẫn hợp lệ; chỉ chuyển những Jakarta EE APIs đã đổi namespace.

### 19.5. Nâng Spring Boot/Hibernate cùng release train

Ưu tiên Boot BOM quản lý Spring/Hibernate. Sau khi upgrade, đọc migration guides và sửa custom Hibernate APIs/types/dialects.

### 19.6. Giữ database major cố định trong lần đầu nếu có thể

Nâng ORM/framework trước trên DB hiện tại đã được target Hibernate hỗ trợ. Sau đó nâng DB/driver riêng. Nếu phải nâng cả hai vì support lifecycle, chia phases và test mỗi cặp.

### 19.7. Upgrade driver có thể độc lập nhưng cần test

JDBC driver là điểm kết nối giữa runtime và DB. Thay driver có thể đổi TLS/authentication, type mapping, generated keys, fetch/cursor behavior, prepared statement caching và exception codes. Pin exact driver patch và test transaction/LOB/batching.

## 20. Thứ tự nâng cấp mẫu: Boot 2.7 sang Boot 3.x

~~~mermaid
flowchart TD
    A["Inventory + dependency matrix"] --> B["Chọn JDK/DB target được hỗ trợ"]
    B --> C["Nâng JDK và build plugins"]
    C --> D["Chuyển javax APIs sang jakarta"]
    D --> E["Nâng Spring Boot/Spring Framework"]
    E --> F["Nâng Hibernate ORM + Envers theo BOM"]
    F --> G["Nâng JDBC driver và xác minh DB dialect"]
    G --> H["Schema/query/transaction integration tests"]
    H --> I["Staging load + rollback rehearsal"]
    I --> J["Production rollout"]
~~~

Một số dự án có thể cần chuyển namespace và Boot trong cùng branch vì dependency constraints; vẫn nên tách commits/phases để review và bisect được.

### 20.1. Tìm imports legacy

~~~bash
grep -R "javax.persistence" src
grep -R "javax.validation" src
grep -R "javax.servlet" src
~~~

Trong PowerShell có thể dùng:

~~~powershell
Get-ChildItem -Recurse -File -Include *.java,*.xml |
    Select-String -Pattern 'javax\.persistence|javax\.validation|javax\.servlet'
~~~

Review kết quả, không replace mọi javax package.

### 20.2. Kiểm tra API usage nội bộ Hibernate

Tìm code gọi các package như org.hibernate.type.*, org.hibernate.dialect.*, org.hibernate.boot.*, org.hibernate.engine.*, org.hibernate.event.* và org.hibernate.query.*.

Không phải mọi usage đều internal hoặc bị break, nhưng custom type/dialect/SPI thường có migration cost cao hơn JPA-standard code.

### 20.3. Test schema generation/validation

Không để ddl-auto=update tự âm thầm thay schema production trong một major upgrade. Dùng migration scripts có review, sau đó chạy Hibernate schema validation/metadata checks theo policy.

## 21. Kiểm thử database compatibility

### 21.1. Test trên cùng database engine

H2 không thay thế PostgreSQL/MySQL/SQL Server/Oracle để chứng minh SQL compatibility. Các database có khác biệt về types, identity/sequence, JSON, collation, locking/isolation, null ordering, pagination, timestamp precision, DDL syntax, constraints/indexes, generated keys và transaction behavior.

Dùng Testcontainers hoặc môi trường DB thật phù hợp với production engine/major.

### 21.2. Schema migration tests

Một migration test nên:

1. Tạo database trống ở đúng version.
2. Chạy toàn bộ migrations từ baseline.
3. Kiểm tra schema metadata.
4. Bootstrap Hibernate với schema validation.
5. Chạy CRUD và query tests.
6. Kiểm tra constraints/indexes/triggers.
7. Kiểm tra upgrade từ version schema cũ.
8. Kiểm tra rollback/forward-fix policy.

### 21.3. Không chỉ test fresh database

Một hệ thống đang production có schema history và dữ liệu cũ. Cần test fresh install, upgrade từ schema version gần nhất, upgrade từ schema version còn được hỗ trợ, large table/index migration, existing Envers audit data, null/default/backfill và mixed application versions trong rolling deployment nếu hỗ trợ.

### 21.4. Test dữ liệu biên

- Unicode/collation.
- Max decimal precision.
- Timestamp daylight saving/timezone.
- Large LOB.
- Empty/null strings.
- Large batch.
- Duplicate keys.
- Concurrent updates.
- Deadlock/lock timeout.
- Transaction rollback.
- Connection loss/retry.

## 22. JDBC driver và connection pool compatibility

Driver upgrade cần test authentication mechanism, TLS certificates/ciphers, DNS/failover behavior, connection validation, prepared statement caching, fetch size/cursor, generated keys, batch update counts, LOB streaming, timezone properties, exception SQLState/vendor codes, socket/read/login timeouts và network interruption during commit.

### 22.1. HikariCP không che được driver incompatibility

Một pool có thể tạo connection thành công nhưng query/LOB/authentication/failover vẫn lỗi. Test full transaction lifecycle, không chỉ health check SELECT 1.

### 22.2. Connection lifetime và server policy

Kiểm tra DB/proxy/load balancer idle timeout, TCP keepalive, pool maxLifetime và validation policy. Driver mới có thể đổi default connection behavior.

### 22.3. Failover và commit uncertainty

Khi DB failover xảy ra giữa COMMIT và response, client có thể không biết transaction đã commit hay chưa. Ma trận nên có failure/retry test và business idempotency policy.

## 23. Support lifecycle và security

Một tổ hợp có thể tương thích kỹ thuật nhưng không còn được bảo trì.

Ma trận nên có vendor support end date, community support/EOL, security maintenance status, runtime patch cadence, database extended support status, JDBC driver support status và internal exception/waiver expiry.

### 23.1. Không chỉ nhìn major version

Một patch cũ trong release line vẫn có thể chứa CVE hoặc bug được sửa ở patch mới. Pin version giúp reproducible nhưng phải có quy trình cập nhật security patches.

### 23.2. SBOM

Generate Software Bill of Materials để biết ứng dụng thực sự ship artifact nào, kể cả transitive dependencies. SBOM hỗ trợ security review, license review và incident response; nó không tự chứng minh compatibility.

### 23.3. Exception phải có owner và ngày hết hạn

~~~text
Component: legacy JDBC driver
Reason: vendor database certification pending
Status: exception approved
Owner: persistence platform team
Mitigation: restricted network + integration monitoring
Review date: 2026-12-15
Exit plan: upgrade to supported driver line
~~~

Không để “temporary override” tồn tại vô thời hạn.

## 24. Ma trận production, staging, local và CI

Môi trường khác nhau có thể làm test mất giá trị.

| Môi trường | Java | DB | Driver | Vai trò |
| --- | --- | --- | --- | --- |
| Developer local | JDK 21 | PostgreSQL container 16 | Pinned driver | Feedback nhanh |
| CI minimum | JDK 17 | PostgreSQL 15 | Pinned driver | Kiểm tra minimum supported |
| CI production candidate | JDK 21 | PostgreSQL 16 | Pinned driver | Kiểm tra target production |
| Staging | JDK 21 patch production | Same DB major/config class | Same driver | Load/operational validation |
| Production | Exact approved runtime | Managed PostgreSQL 16 | Exact approved driver | Certified combination |

Không cần mọi môi trường dùng cùng patch database nếu có lý do, nhưng phải biết chính xác khác biệt và đảm bảo staging phản ánh các behavior quan trọng của production.

### 24.1. Local H2 vẫn có chỗ dùng

H2 phù hợp cho một số unit/repository smoke tests nhanh, nhưng không được coi là bằng chứng thay thế database compatibility. Giữ một bộ integration suite chạy engine thật.

### 24.2. Testcontainers pin image

~~~java
@Testcontainers
class OrderRepositoryIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4");
}
~~~

Tag cụ thể ở ví dụ cần được thay bằng version/digest đã được tổ chức chấp thuận. Không dùng postgres:latest.

## 25. Quản lý version matrix như code

Một file YAML/JSON có thể lưu trạng thái:

~~~yaml
matrixVersion: 1
profiles:
  production:
    java:
      distribution: temurin
      runtime: "21"
      compilerRelease: "21"
    springBoot: "3.4.x"
    springFramework: "bom-managed"
    hibernateOrm: "bom-managed"
    jakartaPersistence: "provider-aligned"
    hibernateEnvers: "same-as-hibernate-core"
    jdbc:
      artifact: "org.postgresql:postgresql"
      version: "pinned-in-build"
    database:
      product: "PostgreSQL"
      major: "16"
    status:
      vendor: "SUPPORTED"
      project: "TESTED"
      production: "CERTIFIED"
~~~

Giá trị bom-managed là cách diễn đạt khái niệm; trong machine-readable matrix cần export exact resolved version từ build.

### 25.1. Tách desired state và observed state

- **Desired:** version dự án định dùng.
- **Resolved:** dependency resolver đã chọn.
- **Runtime observed:** class/package/database thực tế khi chạy.
- **Certified:** tổ hợp đã qua gate.

Nếu chỉ lưu desired versions, transitive override có thể khiến production chạy một tổ hợp khác.

### 25.2. Tự động tạo report

CI có thể resolve Maven/Gradle dependency graph, extract JDK version và compiler release, ghi database image/version, generate SBOM, compare với approved matrix, fail build khi có unapproved override và upload report/evidence.

Không nhất thiết tự động suy mọi compatibility; tool có thể phát hiện drift, còn quyết định support cần evidence.

### 25.3. Review matrix trong dependency PR

Mỗi PR nâng Spring Boot/Hibernate/JDBC nên có version before/after, BOM diff, dependency tree diff, release notes, namespace/API changes, test results, database/driver compatibility evidence và rollback plan.

## 26. Những anti-pattern khi lập ma trận

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| Chỉ ghi Java và Hibernate | Bỏ qua Spring/JPA/driver/DB | Ghi toàn stack |
| Ghi latest | Không reproducible | Pin exact versions |
| Chỉ kiểm tra compile | Lỗi runtime/integration | Startup + DB integration tests |
| Coi javax và jakarta thay thế nhau | Entity không được nhận diện | Chọn một namespace theo stack |
| Override Hibernate ngoài Boot BOM | Spring/Hibernate integration lệch | Dùng BOM hoặc exception có test |
| Nâng ORM và DB cùng lúc | Khó xác định root cause | Chia phases |
| Dùng H2 làm bằng chứng DB support | SQL semantics khác production | Test engine thật |
| Chỉ test fresh schema | Upgrade dữ liệu cũ có thể fail | Test migration từ production-like schema |
| Không pin Testcontainers image | CI tự đổi DB version | Pin tag/digest |
| Chỉ ghi vendor-supported | App-specific features chưa test | Thêm project-tested/certified |
| Bỏ qua driver | TLS/types/failover lỗi | Driver là một dimension |
| Dùng dialect class từ blog cũ | Class/API đã đổi | Đối chiếu Hibernate version |
| Không ghi EOL | Stack cũ không còn security fixes | Lifecycle column + owner |
| Chỉ giữ desired versions | Runtime drift | Resolve/report actual versions |
| Bỏ qua custom Hibernate APIs | Migration compile/runtime failures | Inventory custom SPI/types/dialects |
| Không có rollback rehearsal | Upgrade không có đường lui | Test rollback/forward recovery |

## 27. Quy trình lập ma trận từ một dự án hiện có

### Bước 1 — Thu thập actual versions

JDK vendor/version của build và production, Maven/Gradle wrapper, Spring Boot parent/plugin/BOM, effective dependency versions, Hibernate core và module artifacts, Persistence API JAR/namespace, JDBC driver, database server, connection pool, migration/test dependencies.

### Bước 2 — Vẽ dependency relationships

Đánh dấu thành phần nào được Boot BOM quản lý, thành phần nào do ứng dụng pin, thành phần nào do container/database cung cấp.

### Bước 3 — Đối chiếu support matrices

Tra tài liệu release chính thức của JDK, Spring Boot, Spring Framework, Hibernate, Jakarta Persistence, JDBC driver và database. Ghi release/document version cùng ngày xác minh.

### Bước 4 — Phân loại hard boundaries

Java minimum/runtime bytecode, javax versus jakarta, Hibernate provider API level, Spring Boot managed versions, JDBC driver/server pair và database SQL/dialect features.

### Bước 5 — Tạo project-tested matrix

Chạy build, startup, migration, CRUD, transaction, query, Envers/custom mappings và failure tests trên tổ hợp mục tiêu.

### Bước 6 — Ghi status và owner

Mỗi tổ hợp có status, evidence, owner, review date và exception/exit plan.

### Bước 7 — Đưa vào CI/dependency update workflow

Tự động phát hiện drift và yêu cầu review khi dependency/DB/JDK thay đổi.

## 28. Ví dụ một quyết định nâng cấp

Giả sử dự án hiện tại:

~~~text
Java 11
Spring Boot 2.7
Spring Framework 5.3
Hibernate ORM 5.6
JPA 2.2 / javax.persistence
PostgreSQL 14
PostgreSQL JDBC driver pinned
~~~

Mục tiêu:

~~~text
Java 21
Spring Boot 3.4
Spring Framework 6.2
Hibernate ORM 6.6 line (Boot-managed)
Jakarta Persistence 3.1
PostgreSQL 16
Supported JDBC driver line
~~~

### 28.1. Các thay đổi chính

1. Java runtime tăng lên 21.
2. Spring Boot/Spring Framework major generation đổi.
3. javax.persistence chuyển sang jakarta.persistence.
4. Hibernate 5.6 chuyển sang Hibernate 6.6.
5. Custom Hibernate types/dialects/listeners cần migration.
6. JDBC driver được cập nhật theo support matrix.
7. Database 14 lên 16.
8. Migration scripts và Testcontainers images đổi.
9. Envers schema/query behavior phải được xác minh.

### 28.2. Chia phase

| Phase | Thay đổi | Gate |
| --- | --- | --- |
| 0 | Inventory + current baseline | Dependency/SBOM/report |
| 1 | JDK upgrade trong stack cũ nếu được hỗ trợ | Build/runtime/GC/TLS |
| 2 | Namespace migration | Compile + entity bootstrap |
| 3 | Boot 3/Hibernate 6 upgrade | ORM integration suite |
| 4 | JDBC driver update | Connection/CRUD/LOB/batch/failover |
| 5 | Database 16 upgrade | Migration/query/locking/load |
| 6 | Staging/canary | SLO + operational checks |
| 7 | Production rollout | Rollback/forward-fix ready |

Thứ tự cụ thể phụ thuộc dependency constraints và support windows. Có thể phải gộp phase 2/3 nhưng vẫn giữ evidence riêng.

### 28.3. Những test bắt buộc cho persistence

- Entity scanning và metadata bootstrap.
- ID generation: identity/sequence/table.
- Embeddable, converters, inheritance.
- JPQL/HQL/Criteria queries.
- Native SQL.
- Pagination/sorting.
- Fetch joins/lazy loading.
- Batch insert/update.
- Optimistic/pessimistic locking.
- Transaction propagation/rollback.
- LOB/JSON/UUID/time types.
- Envers revisions/relations.
- Multi-tenancy nếu dùng.
- Schema validation và migration.
- Connection pool under load.
- Database failover/retry.

### 28.4. Rollback không đơn giản là redeploy code cũ

Nếu app mới đã chạy migration schema không tương thích với app cũ, redeploy code cũ có thể thất bại. Dùng expand-contract migrations khi cần rolling deploy:

1. Thêm schema structures tương thích cả app cũ và mới.
2. Deploy code đọc/ghi theo giai đoạn.
3. Backfill dữ liệu.
4. Chuyển traffic/feature flag.
5. Chỉ xóa schema cũ sau khi rollback window kết thúc.

Đối với database major upgrade, rollback có thể cần restore/replica/snapshot hoặc forward fix; không giả định downgrade server luôn an toàn.

## 29. Checklist duyệt một version upgrade PR

- [ ] JDK build/runtime/version được ghi rõ.
- [ ] Java compiler release khớp target policy.
- [ ] Spring Boot release line được hỗ trợ trên JDK đó.
- [ ] Spring Framework/Spring Data được BOM quản lý nhất quán.
- [ ] Hibernate ORM phù hợp Boot/provider integration.
- [ ] Jakarta Persistence API khớp namespace/provider.
- [ ] Không còn dependency javax.persistence ngoài ý muốn.
- [ ] Hibernate Envers/module versions được align.
- [ ] Custom types/dialects/listeners đã được kiểm tra.
- [ ] JDBC driver hỗ trợ Java runtime và DB server.
- [ ] Database major/minor nằm trong support policy.
- [ ] Dialect/SQL features được xác minh.
- [ ] Flyway/Liquibase migration được test.
- [ ] Testcontainers image pin.
- [ ] CRUD/query/transaction/locking/batch tests pass.
- [ ] Envers/custom mappings pass nếu có.
- [ ] Load/connection pool/failover tests phù hợp.
- [ ] Dependency tree/SBOM diff được review.
- [ ] EOL/security lifecycle được cập nhật.
- [ ] Staging/canary và rollback/forward-fix plan sẵn sàng.
- [ ] Matrix/evidence/owner/review date được cập nhật.

## 30. Bài tập thực hành

### Bài 1 — Phân biệt matrix và dependency tree

Dependency tree cho thấy Hibernate 6.6 và Jakarta Persistence API 3.1. Vì sao chưa đủ để kết luận ứng dụng production-compatible?

### Bài 2 — javax và jakarta

Một entity import javax.persistence.Entity chạy với Spring Boot 3/Hibernate 6. Giải thích tại sao hai annotation cùng tên vẫn không tương thích. Nêu những file/artefacts cần tìm khi migration.

### Bài 3 — Java baseline

Hibernate provider yêu cầu Java 11 nhưng Spring Boot line yêu cầu Java 17. Runtime tối thiểu của ứng dụng là bao nhiêu? Vì sao?

### Bài 4 — BOM override

Một dự án Boot 3.3 override hibernate-core sang version khác nhưng Envers vẫn theo BOM. Những lỗi nào có thể xảy ra? Cách quản lý alignment?

### Bài 5 — Spring Data JPA

Vì sao Spring Data JPA phải là một dimension riêng trong matrix dù nó dùng Hibernate làm provider?

### Bài 6 — JDBC driver

Driver kết nối được PostgreSQL nhưng chưa được kiểm thử với Java runtime mới. Những tính năng nào cần test ngoài SELECT 1?

### Bài 7 — Database version

Hibernate dialect hỗ trợ PostgreSQL family nhưng ứng dụng cần một function chỉ có ở server major mới. Dialect có thể làm server cũ hỗ trợ function đó không?

### Bài 8 — Ma trận representative

Lập một matrix cho Boot 2.7/Java 11/Hibernate 5.6 và Boot 3.4/Java 21/Hibernate 6.6, ghi namespace và các điểm migration.

### Bài 9 — H2

Một test suite chạy qua H2. Vì sao chưa chứng minh query/locking/type behavior đúng trên PostgreSQL production?

### Bài 10 — Testcontainers

Tại sao dùng postgres:latest làm CI image gây rủi ro? Cách pin database image?

### Bài 11 — Hibernate 5 → 6

Liệt kê năm nhóm custom integrations có thể bị ảnh hưởng khi nâng major Hibernate.

### Bài 12 — Envers

Vì sao Envers nên align version với Hibernate ORM? Nêu test cases cần chạy khi nâng.

### Bài 13 — Java compiler

Giải thích khác nhau giữa source, target và --release. Vì sao --release giúp kiểm soát API surface?

### Bài 14 — Vendor-supported vs project-tested

Một vendor tuyên bố hỗ trợ Java 21 nhưng CI dự án chỉ chạy Java 17. Ma trận nên ghi trạng thái thế nào?

### Bài 15 — Database driver pair

Thiết kế các cột cần có để ghi compatibility giữa database server, JDBC driver và Java runtime.

### Bài 16 — Dependency convergence

Một project có hai version jakarta.persistence-api được kéo transitive. Những công cụ nào giúp tìm nguyên nhân và vì sao không nên chỉ thêm exclusion tùy tiện?

### Bài 17 — Schema migration

Một ORM upgrade làm thay đổi DDL. Tại sao không nên dựa vào ddl-auto=update ở production? Thiết kế migration test.

### Bài 18 — Upgrade sequencing

Dự án muốn nâng đồng thời JDK, Boot, Hibernate, driver và DB. Vì sao chia phases giúp giảm thời gian điều tra sự cố?

### Bài 19 — Feature matrix

Một stack đã qua CRUD tests nhưng chưa test Envers và multi-tenancy. Status hai features đó nên là gì? Vì sao không gắn nhãn toàn stack CERTIFIED?

### Bài 20 — Support lifecycle

Một tổ hợp vẫn chạy nhưng Hibernate line đã EOL. Những rủi ro nào cần ghi trong matrix và exception record?

### Bài 21 — Rolling deployment

Một migration xóa column cũ ngay khi app mới được deploy. Vì sao app cũ còn chạy có thể lỗi? Mô tả expand-contract.

### Bài 22 — Version drift

Ma trận desired ghi Hibernate 6.6 nhưng production runtime resolve 6.5 do dependency override. Cần kiểm tra ở đâu và cập nhật artifact nào?

### Gợi ý đáp án

- **Bài 1:** Cần Boot/Spring integration, namespace, Java, driver/server pair, runtime tests và project evidence.
- **Bài 2:** Là hai binary types khác nhau; tìm imports, XML, generated code, listeners, custom integrations và transitive APIs.
- **Bài 3:** Java 17 vì constraint cao nhất trong stack quyết định minimum runtime.
- **Bài 4:** NoSuchMethodError, SPI incompatibility, linkage/runtime errors; dùng BOM hoặc align tất cả Hibernate modules.
- **Bài 5:** Repository/query implementation và Spring integration có release train/API compatibility riêng.
- **Bài 6:** TLS/auth, batch, generated keys, LOB, timezone, fetch/cursor, failover, exception codes.
- **Bài 7:** Không; dialect sinh SQL nhưng server phải thực thi feature.
- **Bài 8:** Boot 2.7 thường javax/JPA 2.2/Hibernate 5.6; Boot 3.4 jakarta/JPA 3.1/Hibernate 6.6 line, exact versions theo BOM.
- **Bài 9:** SQL dialect, type mapping, locks, isolation, sequences, JSON và pagination khác engine.
- **Bài 10:** Tag floating khiến DB version đổi không kiểm soát; pin tag/digest.
- **Bài 11:** Custom types, dialects, event listeners, interceptors, boot metadata/query APIs, enhancement.
- **Bài 12:** Module dùng provider APIs; test revision creation, relation auditing, deletes, schema and query.
- **Bài 13:** Source controls syntax, target controls bytecode, release also restricts platform APIs.
- **Bài 14:** vendor=SUPPORTED, project=NOT_TESTED; không ghi CERTIFIED.
- **Bài 15:** Product/server version, driver artifact/version, Java runtime, JDBC level, TLS/auth, features, status/evidence.
- **Bài 16:** Maven dependency tree/effective POM hoặc Gradle dependencyInsight; exclusions có thể làm thiếu runtime classes.
- **Bài 17:** DDL changes cần reviewed migration, schema validation và upgrade tests trên dữ liệu cũ.
- **Bài 18:** Giữ phạm vi biến đổi nhỏ giúp gán lỗi cho một boundary và rollback độc lập.
- **Bài 19:** NOT_TESTED/UNKNOWN; chưa đủ bằng chứng để certify feature.
- **Bài 20:** Security fixes/support, operational risk, exception owner/expiry/exit plan.
- **Bài 21:** App cũ vẫn query column đã bị xóa; giữ schema backward-compatible qua expand-contract.
- **Bài 22:** Dependency resolution, BOM override, lockfile/container artifact; update matrix từ actual resolved runtime.

---

## Tổng kết

**Ma trận phiên bản là hợp đồng tương thích có bằng chứng giữa Java, Spring, Hibernate, Jakarta Persistence, JDBC driver và database.**

1. Ghi rõ **Java build/runtime/compiler**, không chỉ ghi một con số JDK.
2. Dùng **Spring Boot BOM** làm nguồn dependency management chính khi dự án dùng Boot; kiểm tra exact versions thực tế sau resolve.
3. Phân biệt javax.persistence (JPA 2.x legacy) và jakarta.persistence (Jakarta Persistence 3.x). Đây là namespace/binary boundary thực sự.
4. Align Hibernate ORM, Envers và các Hibernate modules; kiểm tra Spring Data/Spring Framework integration.
5. Xem **JDBC driver và database server là một cặp**, đồng thời kiểm tra Java runtime, TLS/authentication, SQL types và operational behavior.
6. Xây cả component matrix lẫn feature matrix; phân biệt vendor-supported, project-tested và production-certified.
7. Tự động phát hiện dependency drift trong CI, pin database images, lưu evidence và lifecycle status.
8. Nâng cấp theo phases, test schema/data cũ và chuẩn bị rollback hoặc forward-fix trước production rollout.

**Một tổ hợp chỉ nên được coi là production-ready khi phiên bản đã được xác định chính xác, các thành phần nằm trong support policy, và những persistence features mà ứng dụng thật sự sử dụng đã qua kiểm thử trên database/driver/runtime đại diện cho production.**
