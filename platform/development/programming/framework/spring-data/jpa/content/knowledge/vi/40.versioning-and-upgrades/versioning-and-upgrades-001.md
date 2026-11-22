# Đọc ma trận tương thích Java, Spring Boot, Spring Data và Hibernate

## Mục tiêu

Một ứng dụng Spring Data JPA không chỉ có bốn phiên bản cần khớp nhau. Nó là một tập hợp thành phần có quan hệ phụ thuộc: JDK, Spring Boot, Spring Framework, Spring Data JPA, Jakarta Persistence API, Hibernate ORM, JDBC driver, database engine và build tool. Một phiên bản có thể được Spring Boot hỗ trợ nhưng chưa chắc đã được một thư viện bên thứ ba trong dependency graph hỗ trợ trên cùng JDK.

Đọc ma trận tương thích giúp trả lời ba câu hỏi:

1. Bộ phiên bản này có nằm trong phạm vi hỗ trợ được công bố của từng thành phần không?
2. Dependency management đang chọn chính xác phiên bản nào khi build?
3. Bộ phiên bản đã resolve có hoạt động cùng nhau trong ứng dụng, test, CI và môi trường production không?

Quy tắc quan trọng là **lấy phần giao của tất cả yêu cầu**, không chỉ nhìn một dòng Spring Boot. Spring Boot BOM là điểm xuất phát tốt vì nó quản lý một tập dependency đã được kiểm thử cùng nhau. Sau đó vẫn phải xác nhận JDK, Hibernate, database driver, database và các thư viện được override.

Bài này trình bày cách đọc từng lớp, cách dùng BOM, cách phát hiện xung đột, ví dụ ma trận chính thức tại ngày 09-11-2026 và một dự án Maven nhỏ để kiểm tra dependency graph thực tế.

## 1. Ma trận tương thích không phải một bảng duy nhất

Mỗi dự án công bố một loại ràng buộc riêng:

- Spring Boot công bố JDK tối thiểu/tối đa, Spring Framework tối thiểu và các build tool được hỗ trợ.
- Spring Boot BOM công bố phiên bản dependency mà Boot quản lý, bao gồm Spring Data JPA, Hibernate ORM và Jakarta Persistence API.
- Spring Data công bố release train BOM và yêu cầu đối với Spring Framework.
- Hibernate công bố phiên bản Java, Jakarta Persistence, database integration và các nền tảng Spring Boot tương thích.
- JDBC driver công bố JDK/database version được hỗ trợ.
- Database vendor công bố phiên bản server, protocol và driver tương thích.

Không có một phép so sánh đơn giản như “Spring Boot 3 thì Hibernate 6” là đủ. Cần kiểm tra cả phiên bản cụ thể và phạm vi hỗ trợ của từng dự án.

Một cấu hình hợp lệ phải đồng thời thỏa:

~~~text
JDK được Spring Boot hỗ trợ
AND JDK được Hibernate hỗ trợ
AND Spring Framework nằm trong phạm vi Spring Data yêu cầu
AND Spring Data JPA nằm trong dependency set tương ứng
AND Jakarta Persistence API phù hợp với Hibernate
AND JDBC driver hỗ trợ JDK và database server
AND build tool hỗ trợ phiên bản Spring Boot
~~~

Một ma trận chỉ cho biết khả năng tương thích theo công bố. Nó không thay thế integration test trên database thật, cũng không tự chứng minh rằng ứng dụng không có lỗi runtime.

## 2. Hiểu vai trò của từng thành phần

| Thành phần | Vai trò | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| JDK | Biên dịch và chạy ứng dụng Java | Phiên bản Java nào được framework và thư viện hỗ trợ? |
| Spring Boot | Nền tảng ứng dụng và dependency management | Boot release nào phù hợp JDK và Spring Framework? |
| Spring Framework | Core container, transaction, web và tích hợp | Spring Data yêu cầu Framework generation nào? |
| Spring Data JPA | Repository abstraction và tích hợp JPA | Module version nào thuộc release train/BOM tương ứng? |
| Jakarta Persistence | API chuẩn ORM | Hibernate implementation hỗ trợ JPA API generation nào? |
| Hibernate ORM | JPA provider và ORM engine | Phiên bản Hibernate nào tương thích JDK, JPA và Boot? |
| JDBC driver | Kết nối Java tới database | Driver hỗ trợ JDK và database server version nào? |
| Database engine | Nơi thực thi SQL và lưu dữ liệu | Dialect, kiểu dữ liệu, locking và tính năng SQL có được hỗ trợ? |
| Maven/Gradle | Resolve dependency và build | Build tool version có nằm trong yêu cầu của Boot không? |

### Spring Data JPA và Hibernate không phải cùng một thư viện

Spring Data JPA cung cấp repository abstraction như JpaRepository, derived query, Specification và repository composition. Hibernate ORM là một JPA provider triển khai API persistence và thực thi SQL.

Vì vậy, dependency graph thường có cả hai:

~~~text
Ứng dụng
  └── spring-boot-starter-data-jpa
        ├── spring-data-jpa
        ├── spring-orm
        ├── jakarta.persistence-api
        └── hibernate-core
~~~

Tên phiên bản của Spring Data JPA không cần giống Hibernate. Hai dự án phát hành độc lập; Boot BOM chọn các phiên bản tương thích cho một release line.

### Jakarta Persistence là lớp hợp đồng

Spring Data JPA gọi API Jakarta Persistence; Hibernate triển khai API đó. Nếu API và provider thuộc hai generation không tương thích, lỗi có thể xuất hiện ở compile time, lúc khởi tạo EntityManagerFactory hoặc khi chạy query.

Không chỉ nhìn tên “JPA”. Hãy xác định chính xác Jakarta Persistence 2.2, 3.0, 3.1 hay 3.2.

## 3. Đọc ma trận theo thứ tự

Khi chọn một bộ version, đọc theo thứ tự sau:

1. **Chọn JDK runtime.** Xác định JDK mà máy developer, CI và production sẽ chạy.
2. **Chọn Spring Boot release line.** Kiểm tra yêu cầu Java và build tool.
3. **Đọc managed dependency coordinates của Boot.** Ghi lại Spring Framework, Spring Data JPA, Hibernate và Jakarta Persistence.
4. **Đối chiếu Spring Data.** Xác nhận module thuộc release train phù hợp và yêu cầu Framework không cao hơn phiên bản Boot cung cấp.
5. **Đối chiếu Hibernate.** Kiểm tra JDK, Jakarta Persistence và Spring Boot generation được hỗ trợ.
6. **Đối chiếu JDBC driver/database.** Kiểm tra cả Java driver và server version.
7. **Kiểm tra dependency graph đã resolve.** Không dựa vào phiên bản khai báo trong file build; kiểm tra phiên bản Maven/Gradle thực sự chọn.
8. **Build, test và chạy trên runtime mục tiêu.** Matrix hợp lệ là điều kiện cần; integration test xác nhận hành vi thực tế.

Đừng bắt đầu bằng việc tìm một phiên bản Hibernate “mới nhất” rồi ép Spring Boot dùng nó. Trước hết chọn platform release line, sau đó xem dependency management của platform.

## 4. Ví dụ ma trận chính thức tại ngày 09-11-2026

Bảng dưới đây minh họa hai release line được tài liệu chính thức công bố. Đây là snapshot để học cách đọc, không phải lời khuyên nâng cấp mọi dự án lên cùng một phiên bản.

| Thành phần | Spring Boot 3.4.13 | Spring Boot 4.1.2 |
| --- | --- | --- |
| Java theo Spring Boot | 17 đến 24 | 17 đến 27 |
| Spring Framework | 6.2.15 | 7.0.10 |
| Spring Data JPA do Boot quản lý | 3.4.13 | 4.1.2 |
| Hibernate ORM do Boot quản lý | 6.6.39.Final | 7.4.13.Final |
| Jakarta Persistence | 3.1.0 | 3.2 generation |
| Hibernate tương thích Spring Boot | Hibernate 6.6 hỗ trợ Boot 3.4–3.5 | Hibernate 7.4 hỗ trợ Boot 4.1 |

Nguồn cho từng dòng:

- Spring Boot 3.4.13 System Requirements: Java 17–24, Spring Framework 6.2.15 trở lên.
- Spring Boot 3.4.13 Managed Dependency Coordinates: Spring Data JPA 3.4.13, Hibernate Core 6.6.39.Final, Jakarta Persistence API 3.1.0.
- Spring Boot 4.1.2 System Requirements: Java 17–27, Spring Framework 7.0.10 trở lên.
- Spring Boot managed coordinates 4.1.2: Spring Data JPA 4.1.2 và Hibernate Core 7.4.13.Final.
- Hibernate 6.6 compatibility: Jakarta Persistence 3.1 và Spring Boot 3.4–3.5.
- Hibernate 7.4 compatibility: Jakarta Persistence 3.2 và Spring Boot 4.1.

Điểm quan trọng khi đọc bảng: JDK range của Spring Boot không tự động trở thành JDK range của mọi dependency bên thứ ba. Hibernate có ma trận Java riêng. Ví dụ, Hibernate 6.6 công bố Java 11, 17, 21; Java 25 được ghi rõ từ bản 6.6.40 trở lên. Vì Boot 3.4.13 quản lý Hibernate 6.6.39.Final, phần giao được liệt kê rõ giữa hai ma trận là Java 17 và 21. Java 24 nằm trong dải Boot nhưng không xuất hiện trong danh sách JDK tương thích của bản Hibernate này; cần kiểm tra release note/support policy cụ thể trước khi chọn.

Tương tự, Hibernate 7.4 công bố Java 17, 21, 25 và 26. Dù Spring Boot 4.1.2 công bố hỗ trợ đến Java 27, không nên suy ra Hibernate 7.4.13 cũng đã được công bố hỗ trợ Java 27 nếu ma trận Hibernate chưa liệt kê phiên bản đó.

## 5. Tính phần giao của các ràng buộc

Giả sử dự án chọn Spring Boot 3.4.13:

- Boot yêu cầu tối thiểu Java 17 và công bố hỗ trợ đến Java 24.
- Boot quản lý Spring Framework 6.2.15.
- Boot quản lý Spring Data JPA 3.4.13.
- Boot quản lý Hibernate ORM 6.6.39.Final.
- Boot quản lý Jakarta Persistence API 3.1.0.
- Hibernate 6.6 tương thích Spring Boot 3.4–3.5 và Jakarta Persistence 3.1.
- Hibernate 6.6.39 có danh sách JDK được hỗ trợ cần đối chiếu riêng; Java 17 và 21 là phần giao được liệt kê rõ với dải Java của Boot.

Một bộ nền tảng dễ tái lập là:

~~~text
JDK:                  17
Spring Boot:          3.4.13
Spring Framework:     6.2.15 (Boot-managed)
Spring Data JPA:      3.4.13 (Boot-managed)
Hibernate ORM:        6.6.39.Final (Boot-managed)
Jakarta Persistence:  3.1.0 (Boot-managed)
~~~

Đây là cách đọc dependency matrix, không phải yêu cầu phải pin tất cả các phiên bản trên vào pom.xml. Trong dự án dùng Boot parent/BOM, thường chỉ khai báo Spring Boot starter và để Boot quản lý phiên bản.

### Không lấy phiên bản lớn nhất ở mỗi cột

Ví dụ không nên tự ghép:

~~~text
Spring Boot 3.4.x
Spring Framework 7.x
Spring Data JPA 4.x
Hibernate 7.4.x
Jakarta Persistence 3.2
~~~

Đây là cách chọn độc lập từng cột và có thể tạo một dependency graph không được hỗ trợ. Các major generation cần được nâng cấp như một platform set có kiểm soát.

## 6. Spring Data release train và phiên bản module

Spring Data sử dụng release train để quản lý nhiều module có lịch phát hành khác nhau. Release train có tên theo lịch, ví dụ dạng YYYY.MINOR.MICRO; phiên bản của module như Spring Data JPA không nhất thiết giống số release train.

Ví dụ:

- Spring Data JPA có version riêng.
- Spring Data Commons có version riêng.
- Spring Data JDBC, MongoDB, Redis và các module khác cũng có version riêng.
- Release train BOM quy định tập version tương thích giữa các module.
- Spring Boot chọn một tập Spring Data module version phù hợp với Boot release line.

Do đó, không suy luận rằng Spring Data JPA phải có cùng số major/minor với Spring Boot. Hãy xem artifact version trong Boot managed coordinates hoặc release train BOM.

### Khi ứng dụng dùng Spring Boot

Nếu dùng Spring Boot parent hoặc import Boot BOM, mặc định hãy để Boot chọn Spring Data JPA:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

Không thêm version riêng cho spring-data-jpa nếu không có lý do cụ thể.

### Khi không dùng Spring Boot

Nếu dự án dùng Spring Framework trực tiếp, Spring Data BOM giúp chọn các module cùng release train:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2025.0.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo module mà không ghi version:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jpa</artifactId>
</dependency>
~~~

Khi dùng Spring Data BOM độc lập, phải kiểm tra yêu cầu Spring Framework của release train đó. Không lấy BOM mới nhất rồi ghép với một Spring Framework cũ mà không xác nhận compatibility.

## 7. Spring Boot BOM quản lý dependency thế nào?

Spring Boot phát hành một curated dependency list dưới dạng BOM tên spring-boot-dependencies. BOM cung cấp version mặc định cho nhiều thư viện đã được chọn cùng release line.

Khi dùng Spring Boot parent, dependency có trong BOM có thể khai báo mà không cần version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

Starter kéo theo các thành phần phù hợp, ví dụ Spring Data JPA, Spring ORM, Hibernate và Jakarta Persistence API.

Lợi ích:

- Các dependency Spring được căn chỉnh theo cùng release line.
- Hibernate modules dùng version đồng bộ.
- Không cần tự pin từng transitive dependency.
- Nâng Boot có thể nâng cả tập dependency theo cấu hình đã được kiểm thử.
- Giảm nguy cơ chọn nhầm API/provider generation.

### BOM không có nghĩa mọi dependency trong dự án đều tự động tương thích

Một dependency do dự án tự thêm có thể không nằm trong Boot BOM. Một library khác cũng có thể mang theo transitive dependency với version khác. Vì vậy cần kiểm tra dependency tree sau khi thêm thư viện.

### Không import nhiều BOM một cách tùy tiện

Nếu import Boot BOM, Spring Data BOM và Hibernate BOM cùng lúc, thứ tự dependency management hoặc version override có thể làm kết quả khác mong đợi.

Chỉ thêm BOM thứ hai khi có mục đích rõ ràng, đã đọc quy tắc precedence của build tool và đã kiểm tra effective POM/dependency graph. Trong ứng dụng Boot thông thường, Boot BOM nên là nguồn quản lý dependency chính.

## 8. Phân biệt javax.persistence và jakarta.persistence

Đây là một ranh giới quan trọng khi nâng cấp từ hệ Spring cũ sang Spring Boot 3+.

| Nền tảng | Persistence namespace thường dùng |
| --- | --- |
| Spring Boot 2.x / Hibernate 5.x generation | javax.persistence.* |
| Spring Boot 3.x / Hibernate 6.x generation | jakarta.persistence.* |
| Spring Boot 4.x / Hibernate 7.x generation | jakarta.persistence.* |

Jakarta Persistence 3.x dùng package jakarta.persistence. Các annotation và interface thường gặp:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
~~~

Nếu source code vẫn import javax.persistence.Entity trong một dự án Boot 3 hoặc Boot 4, compiler có thể không tìm thấy annotation tương ứng hoặc provider không nhận mapping như mong muốn.

Không thêm cả hai API chỉ để “cho chạy được”. Một class entity không nên trộn annotation javax và jakarta. Khi nâng cấp major generation, cần chuyển import, dependency, annotation processor, thư viện tích hợp và test fixture sang namespace phù hợp.

## 9. Đọc ma trận Hibernate ORM

Hibernate có compatibility page riêng theo từng series. Khi đọc cần kiểm tra:

- Java runtime được hỗ trợ.
- Jakarta Persistence version được triển khai.
- Jakarta EE generation nếu ứng dụng phụ thuộc container.
- Spring Boot generation tương thích.
- Database dialect và database version.
- Support/maintenance status của series.

### Jakarta Persistence version

Hibernate ORM 6.6 triển khai Jakarta Persistence 3.1. Hibernate ORM 7.4 triển khai Jakarta Persistence 3.2. Nếu code dùng API mới của JPA 3.2 nhưng provider chỉ triển khai JPA 3.1, compile có thể thất bại hoặc API runtime không đáp ứng.

### Spring Boot generation

Hibernate 6.6 công bố tương thích với Spring Boot 3.4–3.5. Hibernate 7.4 công bố tương thích với Spring Boot 4.1. Đây là tín hiệu mạnh hơn việc chỉ nhìn major version của Hibernate.

### Support status

Tương thích không đồng nghĩa còn được bảo trì đầy đủ. Một series có thể ở trạng thái limited support hoặc end-of-life. Khi chọn phiên bản cho dự án mới, kiểm tra cả compatibility matrix và maintenance policy/security support.

Không giữ một series đã EOL chỉ vì nó vẫn chạy được với JDK hiện tại.

## 10. Kiểm tra JDK thực tế, không chỉ Java source level

Có ba khái niệm cần phân biệt:

1. **JDK chạy Maven/Gradle:** JVM mà build tool đang dùng.
2. **Compiler release/target:** bytecode và API Java mà source được phép sử dụng.
3. **JDK production:** JVM thực sự chạy ứng dụng sau khi deploy.

Ví dụ pom có:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Điều này không tự chứng minh production đang chạy Java 17. Container image hoặc máy chủ có thể đang dùng Java 21, 24 hoặc một JDK khác.

Kiểm tra môi trường:

~~~bash
java -version
mvn -version
~~~

Nếu dùng Gradle:

~~~bash
./gradlew -version
~~~

Kiểm tra JDK trong CI và Docker image. Một dự án biên dịch với release 17 vẫn có thể gặp lỗi khi một dependency runtime yêu cầu JDK mới hơn.

### Toolchain

Maven Toolchains hoặc Gradle Java Toolchains giúp chọn compiler JDK có chủ đích. Dùng toolchain khi developer, CI và build agent có nhiều JDK khác nhau; vẫn phải đảm bảo runtime production nằm trong phạm vi dependency support.

## 11. Database và JDBC driver cũng thuộc ma trận

Một ứng dụng có thể resolve thành công Spring Data JPA và Hibernate nhưng vẫn không tương thích với database server hoặc JDBC driver.

Cần kiểm tra:

- Database server version có được Hibernate dialect hỗ trợ không.
- JDBC driver version hỗ trợ JDK đang dùng không.
- Driver có hỗ trợ protocol/TLS/authentication của server không.
- Kiểu dữ liệu, sequence, identity, JSON, array, enum và pagination có đúng dialect không.
- Locking, isolation và transaction semantics có giống yêu cầu nghiệp vụ không.
- Migration tool có hỗ trợ database version đó không.

Ví dụ Hibernate 6.x có dialect khác với Hibernate 7.x. Không nên copy cấu hình dialect cũ sang bản mới mà không kiểm tra tài liệu. Trong nhiều trường hợp Hibernate tự nhận dialect từ JDBC metadata; chỉ cấu hình dialect thủ công khi có lý do và đã xác minh.

### H2 không thay thế database production

H2 phù hợp cho test nhanh, nhưng không chứng minh PostgreSQL/MySQL/SQL Server/Oracle tương thích. Khi dùng native SQL, stored procedure, locking hoặc kiểu dữ liệu đặc thù, chạy integration test trên đúng database engine và JDBC driver của production, ví dụ qua Testcontainers.

## 12. Xác minh dependency graph bằng Maven

File pom.xml chỉ cho biết dependency trực tiếp và dependency management. Maven mới là công cụ resolve version cuối cùng.

### In effective POM

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM cho thấy cấu hình sau khi kế thừa parent và áp dụng dependency management.

### In dependency tree

~~~bash
mvn dependency:tree
~~~

Lọc các thành phần liên quan:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.data:spring-data-jpa,org.springframework:spring-orm,org.hibernate.orm:hibernate-core,jakarta.persistence:jakarta.persistence-api
~~~

Đọc output để xác định:

- Version nào được chọn.
- Dependency nào kéo version đó vào.
- Version nào bị loại do conflict.
- Có hai generation của cùng API xuất hiện trong graph hay không.

### Kiểm tra property

~~~bash
mvn help:evaluate -Dexpression=java.version -q -DforceStdout
~~~

Lệnh này đọc property của Maven project. Vẫn phải kiểm tra JDK thực tế bằng mvn -version.

### Khi thấy version không như mong đợi

1. Mở effective POM.
2. Tìm dependencyManagement đang quản lý artifact.
3. Kiểm tra direct dependency có khai báo version riêng không.
4. Kiểm tra BOM import và thứ tự import.
5. Kiểm tra transitive dependency mang version khác.
6. Dùng dependency tree để xác nhận version cuối cùng.
7. Sau khi chỉnh, build lại và chạy test.

Không sửa bằng cách thêm version ngẫu nhiên vào dependency đầu tiên thấy trong tree. Trước hết xác định nguồn quản lý version.

## 13. Xác minh dependency graph bằng Gradle

Gradle có thể in toàn bộ dependency theo configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence-api --configuration runtimeClasspath
~~~

Dependency insight cho biết version được chọn, constraint và dependency path. Đây là cách nhanh để phát hiện một library đã kéo Hibernate hoặc Jakarta Persistence API khác với Boot BOM.

Nếu dùng Gradle native BOM support:

~~~gradle
dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:3.4.13")
    implementation "org.springframework.boot:spring-boot-starter-data-jpa"
    runtimeOnly "com.h2database:h2"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

Nếu dùng Spring Boot Gradle plugin, plugin có thể tự import Boot dependency management theo cách cấu hình tương ứng. Không cần lặp lại platform nếu plugin đã cung cấp cùng BOM.

## 14. Ví dụ Maven sử dụng version do Spring Boot quản lý

Ví dụ dưới đây dùng Spring Boot 3.4.13, Java 17, Spring Data JPA và H2. Không khai báo version riêng cho Spring Data JPA, Hibernate hay Jakarta Persistence; Boot BOM chọn chúng.

### Cấu trúc dự án

~~~text
compatibility-check/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/compatibility/
        │   ├── CompatibilityApplication.java
        │   ├── Book.java
        │   └── BookRepository.java
        └── resources/
            └── application.properties
~~~

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compatibility-check</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:compatibilitydb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

### Book.java

~~~java
package com.example.compatibility;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

### BookRepository.java

~~~java
package com.example.compatibility;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

### CompatibilityApplication.java

~~~java
package com.example.compatibility;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompatibilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompatibilityApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookRepository repository) {
        return args -> {
            repository.save(new Book("Spring Data JPA"));

            System.out.println("Spring Data JPA compatibility check:");
            repository.findAll().forEach(book ->
                    System.out.println(book.getId() + " | " + book.getTitle()));
        };
    }
}
~~~

### Build và chạy

~~~bash
java -version
mvn -version
mvn clean verify
mvn spring-boot:run
~~~

Output phần ứng dụng trên database H2 mới:

~~~text
Spring Data JPA compatibility check:
1 | Spring Data JPA
~~~

ID 1 là kết quả của database in-memory mới và một bản ghi được insert trong ví dụ. Build command xác nhận compile/test/package; lệnh dependency:tree ở phần trước xác nhận version đã resolve.

### Phiên bản dependency dự kiến theo Boot 3.4.13

Tài liệu managed coordinates của Boot 3.4.13 công bố:

~~~text
org.springframework.data:spring-data-jpa:3.4.13
org.springframework: spring-framework modules: 6.2.15
org.hibernate.orm:hibernate-core:6.6.39.Final
jakarta.persistence:jakarta.persistence-api:3.1.0
~~~

Output thực tế có thể có thêm dependency và module khác. Dùng dependency:tree để xác nhận trên project được build, không coi bảng trong tài liệu là thay thế cho output của build.

## 15. Khi nào được override version do Boot quản lý?

Đôi khi cần nâng một dependency vì bug fix, security advisory hoặc tính năng mà Boot release line chưa quản lý. Đây là quyết định có chủ đích, cần xác nhận compatibility.

Trước khi override, hãy trả lời:

1. Version mới có tương thích với Spring Framework đang dùng không?
2. Spring Data JPA version có hỗ trợ Hibernate version mới không?
3. Hibernate version mới có triển khai Jakarta Persistence API hiện tại không?
4. Các Hibernate module như core, envers, spatial, hibernate-micrometer có cùng version không?
5. JDBC driver và database dialect có tương thích không?
6. Có migration guide cho thay đổi API, SQL generation, type mapping hoặc behavior không?
7. Test integration có chạy trên JDK và database production không?

### Override một property có sẵn

Boot có một số property để tùy chỉnh version dependency được quản lý. Tên property và phạm vi hỗ trợ phụ thuộc Boot release. Chỉ dùng property được tài liệu đúng release line công bố.

Không tự đặt một property tùy ý rồi cho rằng Maven/Gradle sẽ áp dụng nó.

### Override trực tiếp dependency

Khi khai báo version riêng, dependency đó có thể vượt qua lựa chọn trong Boot BOM. Cần kiểm tra effective POM và dependency tree để biết kết quả cuối cùng.

Không chỉ đổi hibernate-core nếu các module Hibernate khác trong graph vẫn ở version cũ. Không thêm Jakarta Persistence API version mới chỉ để compile nếu provider không triển khai generation đó.

### Không override chỉ vì một version mới hơn

Version mới hơn không luôn tương thích với platform cũ. Hãy tìm compatibility matrix, migration guide và release notes trước khi nâng.

## 16. Nâng cấp theo platform, không nâng từng thư viện ngẫu nhiên

Khi nâng từ Boot 2.x lên Boot 3.x, thay đổi lớn gồm:

- JDK tối thiểu tăng lên Java 17.
- Spring Framework 5 chuyển sang 6.
- Spring Data JPA 2.x chuyển sang 3.x.
- Hibernate 5 chuyển sang 6.
- Java EE javax namespace chuyển sang Jakarta namespace.
- Jakarta Persistence API chuyển sang 3.1 generation trong Boot 3.4.

Khi nâng lên Boot 4.x, kiểm tra lại:

- Spring Framework 7.
- Spring Data JPA 4.x.
- Hibernate 7.x.
- Jakarta Persistence 3.2.
- Servlet/container generation và các starter/module có thay đổi.
- Thư viện bên thứ ba đã hỗ trợ Spring Framework 7 và Jakarta Persistence 3.2 chưa.

Không nên chỉ sửa import javax thành jakarta rồi coi migration đã xong. Cần kiểm tra method/API đã deprecated hoặc thay đổi, dialect, type mapping, query parsing, transaction behavior, test infrastructure và integration library.

### Trình tự nâng cấp có kiểm soát

1. Đọc migration guide của Spring Boot cho từng major generation.
2. Đọc migration guide của Spring Framework, Spring Data và Hibernate.
3. Chốt JDK và build tool.
4. Nâng Boot parent/BOM.
5. Bỏ các version override cũ không còn cần thiết.
6. Chuyển namespace và sửa compile errors.
7. Chạy unit test và repository integration test.
8. Chạy test trên database engine production.
9. Kiểm tra SQL sinh ra, schema validation, transaction và locking.
10. Kiểm tra startup, observability, deployment image và rollback plan.

## 17. Đọc lỗi dựa trên dấu hiệu version mismatch

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| NoClassDefFoundError: javax/persistence/... | Code/library cũ dùng javax trong ứng dụng Jakarta | Tìm dependency còn kéo javax.persistence và kiểm tra imports. |
| NoClassDefFoundError: jakarta/persistence/... | Thiếu Jakarta API hoặc provider generation không đúng | Xem dependency tree và Hibernate version. |
| NoSuchMethodError trong Spring Data/Hibernate | Compile/runtime resolve hai version khác nhau hoặc override không tương thích | Kiểm tra dependency tree, packaged jar và runtime classpath. |
| UnsupportedClassVersionError | Runtime JDK thấp hơn bytecode của class | So sánh javac release với JDK production. |
| Failed to configure a DataSource / driver not found | JDBC driver thiếu hoặc version không phù hợp | Kiểm tra runtime dependency và driver compatibility. |
| Could not determine recommended JdbcType / dialect errors | Mapping hoặc dialect không phù hợp provider/database | Đọc Hibernate migration guide, dialect và type mapping. |
| EntityManagerFactory startup failure | API/provider mismatch, mapping hoặc schema lỗi | Xem root cause, dependency graph và persistence metadata. |
| Spring Data repository method không khởi tạo | API/module version lệch hoặc query method không hợp lệ | Kiểm tra Spring Data JPA version và startup stack trace. |
| Method not found sau khi nâng major | API thay đổi giữa generation | Đọc migration guide của đúng module. |

Không sửa lỗi bằng cách loại bỏ dependency ngẫu nhiên. Xác định class được load từ artifact nào, version nào và dependency path nào đã đưa nó vào.

## 18. Checklist đọc ma trận trước khi tạo dự án

- [ ] Đã chọn JDK runtime và kiểm tra trên máy developer, CI, production.
- [ ] Spring Boot release line hỗ trợ JDK và build tool đã chọn.
- [ ] Đã đọc managed dependency coordinates của đúng bản Boot.
- [ ] Spring Framework nằm trong yêu cầu của Spring Data release line.
- [ ] Spring Data JPA version được quản lý bởi Boot BOM hoặc Spring Data BOM phù hợp.
- [ ] Jakarta Persistence API generation phù hợp Hibernate provider.
- [ ] Hibernate compatibility page liệt kê Spring Boot generation đang dùng.
- [ ] JDK nằm trong phần giao giữa Boot và Hibernate.
- [ ] JDBC driver hỗ trợ JDK và database server version.
- [ ] Database dialect và tính năng SQL phù hợp.
- [ ] Không trộn javax.persistence và jakarta.persistence.
- [ ] Không có version override không được giải thích.
- [ ] Dependency tree không có API/provider generation xung đột.
- [ ] Maven effective POM hoặc Gradle dependencyInsight đã được kiểm tra.
- [ ] Build/test chạy thành công trên JDK mục tiêu.
- [ ] Integration test chạy trên database production-like.
- [ ] Đã kiểm tra maintenance status và security support của các release line.

## 19. Nguyên tắc thực hành

- Chọn JDK và Spring Boot release line trước, rồi đọc các dependency version do Boot quản lý.
- Xem Spring Data JPA và Hibernate là hai thành phần riêng, được căn chỉnh qua BOM.
- Kiểm tra Jakarta Persistence API generation thay vì chỉ nhìn chữ JPA.
- Tính phần giao giữa JDK range của Boot và Hibernate.
- Dùng Spring Boot BOM làm nguồn quản lý version mặc định trong ứng dụng Boot.
- Chỉ dùng Spring Data BOM độc lập khi không dựa vào Boot dependency management hoặc khi đã xác minh compatibility.
- Không trộn version của nhiều major generation.
- Dùng Maven dependency:tree/effective-pom hoặc Gradle dependencyInsight để xem version thực tế.
- Kiểm tra JDBC driver và database server, không dừng ở compile thành công.
- Đọc migration guide và support lifecycle trước khi nâng major.
- Xác nhận bộ version bằng build, integration test và runtime production-like.

Điểm cốt lõi: **Đọc ma trận tương thích bằng cách giao các ràng buộc của JDK, Spring Boot, Spring Framework, Spring Data JPA, Jakarta Persistence, Hibernate và database driver. Dùng Boot BOM để giữ dependency đồng bộ, kiểm tra version thực tế bằng dependency tree, rồi xác nhận bằng integration test trên JDK và database mục tiêu.** 

## 20. Tài liệu tham khảo chính thức

- Spring Boot 3.4 System Requirements: https://docs.spring.io/spring-boot/3.4/system-requirements.html
- Spring Boot 3.4 Managed Dependency Coordinates: https://docs.spring.io/spring-boot/3.4/appendix/dependency-versions/coordinates.html
- Spring Boot Build Systems and Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Spring Boot 4.1 System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot Managed Dependency Coordinates: https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html
- Spring Data Dependencies and Release Train BOM: https://docs.spring.io/spring-data/jpa/reference/data-commons/dependencies.html
- Hibernate ORM 6.6 Compatibility: https://hibernate.org/orm/releases/6.6/
- Hibernate ORM 7.4 Compatibility: https://hibernate.org/orm/releases/7.4/
- Hibernate ORM Documentation and Migration Guides: https://hibernate.org/orm/documentation/
