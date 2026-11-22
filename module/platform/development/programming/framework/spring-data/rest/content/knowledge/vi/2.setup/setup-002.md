# Quản lý dependency bằng Spring Boot BOM hoặc Spring Data BOM

## Mục tiêu

Sau bài này, bạn có thể giải thích vai trò của BOM (Bill of Materials), chọn đúng BOM cho ứng dụng Spring Data REST, cấu hình dependency bằng Maven hoặc Gradle, nâng phiên bản có kiểm soát và kiểm tra phiên bản thực tế mà build tool đã phân giải.

## 1. Vì sao cần quản lý dependency tập trung?

Một ứng dụng Spring Data REST thường sử dụng nhiều thư viện có quan hệ chặt chẽ: Spring Framework, Spring Data REST, Spring Data Commons, Spring Data JPA hoặc một module lưu trữ khác, cùng các thư viện nền tảng. Các module Spring Data được phát triển theo nhịp riêng nên số phiên bản của chúng không nhất thiết giống nhau. Ví dụ, không nên suy luận rằng Spring Data REST 5.x phải đi cùng Spring Data JPA 5.x.

Nếu tự gán phiên bản cho từng dependency, dự án dễ gặp tình trạng lệch phiên bản, lỗi tương thích hoặc phải sửa nhiều nơi khi nâng cấp. BOM giải quyết việc này bằng cách cung cấp một tập hợp phiên bản đã được chọn và kiểm thử cùng nhau.

BOM là một POM chuyên khai báo thông tin quản lý dependency. Khi import BOM, Maven hoặc Gradle biết phiên bản mặc định cần dùng cho các thư viện thuộc BOM. BOM **không tự thêm thư viện vào classpath**. Bạn vẫn phải khai báo dependency mà ứng dụng thực sự sử dụng; BOM chỉ giúp quản lý phiên bản của chúng.

## 2. Phân biệt hai BOM

| Tiêu chí | Spring Boot BOM | Spring Data BOM |
|---|---|---|
| Artifact | org.springframework.boot:spring-boot-dependencies | org.springframework.data:spring-data-bom |
| Phạm vi | Bộ phiên bản được Spring Boot tuyển chọn: Spring Framework, Spring Data và nhiều thư viện bên thứ ba | Các module thuộc hệ sinh thái Spring Data |
| Mục đích | Giữ các dependency của một ứng dụng Spring Boot tương thích với phiên bản Boot đang dùng | Giữ các module Spring Data tương thích trong cùng một release train |
| Trường hợp thường dùng | Ứng dụng Spring Boot | Ứng dụng Spring MVC/Spring Framework không dùng Spring Boot, hoặc trường hợp cần chủ động quản lý release train Spring Data |

### Spring Boot BOM

Artifact spring-boot-dependencies là BOM do mỗi phiên bản Spring Boot cung cấp. Danh sách phiên bản được tuyển chọn và kiểm thử theo phiên bản Boot đó. Vì vậy, khi dùng Spring Boot, đây thường là nguồn quản lý phiên bản chính cho toàn bộ ứng dụng.

Spring Boot có starter dành cho Spring Data REST là spring-boot-starter-data-rest. Starter này khai báo nhóm dependency cần thiết và kết hợp với auto-configuration của Spring Boot. Bạn vẫn phải khai báo starter trong dự án; việc import BOM không tự thêm starter.

### Spring Data BOM

Artifact spring-data-bom là BOM của Spring Data. Nó gom các phiên bản tương thích của những module như Spring Data Commons, Spring Data REST, Spring Data JPA, MongoDB, Redis, JDBC và các module khác trong cùng release train.

Spring Data dùng CalVer cho release train, theo dạng YYYY.MINOR.MICRO. Ví dụ 2026.0.2 là một phiên bản release train được tài liệu chính thức liệt kê tại thời điểm biên soạn. Các module thành viên có số phiên bản riêng; BOM giúp chọn đúng tổ hợp thay vì yêu cầu chúng có cùng số phiên bản.

Nếu không dùng Spring Boot, bạn thường khai báo trực tiếp module Spring Data REST là spring-data-rest-webmvc và dùng Spring Data BOM để quản lý phiên bản của module này cùng các module Spring Data khác.

## 3. Chọn BOM nào?

- **Dự án dùng Spring Boot:** ưu tiên Spring Boot BOM. Dùng starter spring-boot-starter-data-rest và để BOM quản lý phiên bản.
- **Dự án Spring MVC/Spring Framework không dùng Spring Boot:** dùng Spring Data BOM để đồng bộ các module Spring Data; đồng thời cấu hình Spring MVC và các dependency nền tảng phù hợp.
- **Dự án Spring Boot cần nâng riêng Spring Data:** trước tiên kiểm tra phiên bản Spring Data mà Boot đang quản lý và ma trận tương thích. Chỉ override release train khi có lý do cụ thể và đã kiểm tra tương thích.
- **Dự án dùng nhiều module Spring Data:** không tự chọn từng phiên bản module. Dùng một release train BOM làm nguồn quản lý chung.

Quy tắc thực hành là chọn một nguồn quản lý phiên bản chính. Trong ứng dụng Spring Boot thông thường, nguồn đó là Spring Boot BOM. Chỉ đưa Spring Data BOM vào thêm khi bạn chủ động override release train và đã kiểm soát thứ tự ưu tiên của dependency management.

## 4. Cấu hình bằng Maven

### 4.1. Spring Boot với spring-boot-starter-parent

Đây là cách ngắn gọn khi dự án có thể kế thừa parent POM của Spring Boot. Parent đã kế thừa dependency management từ spring-boot-dependencies, vì vậy không cần import BOM lần nữa.

Ví dụ phần liên quan trong pom.xml:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <!-- Chỉ thêm nếu ứng dụng dùng JPA làm tầng lưu trữ -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Không cần khai báo version cho hai starter vì Spring Boot BOM đã quản lý chúng. Nếu ứng dụng dùng MongoDB, Redis hoặc một store khác, hãy chọn starter tương ứng thay vì thêm starter JPA một cách máy móc.

### 4.2. Spring Boot nhưng không kế thừa parent POM

Một dự án có thể phải kế thừa parent POM nội bộ của tổ chức. Khi đó, vẫn có thể dùng Spring Boot BOM bằng cách import nó trong dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
</dependencies>
~~~

Cách import này cung cấp dependency management nhưng không kế thừa plugin management từ Spring Boot parent. Nếu cần cấu hình plugin Maven, hãy khai báo hoặc quản lý plugin riêng.

### 4.3. Ứng dụng không dùng Spring Boot: import Spring Data BOM

Với ứng dụng Spring MVC/Spring Framework không dùng Spring Boot, có thể import Spring Data BOM rồi khai báo các module cần thiết mà không gắn version cho từng module:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-rest-webmvc</artifactId>
    </dependency>

    <!-- Chỉ thêm nếu dùng Spring Data JPA -->
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Spring Data BOM quản lý phiên bản các module Spring Data. Nó không thay thế cấu hình Spring MVC, Spring Framework, transaction hoặc cấu hình kết nối database. Khi tích hợp Spring Data REST vào ứng dụng Spring MVC hiện có, cần cấu hình MVC cho Spring Data REST theo tài liệu tương ứng. Nếu dùng Spring Boot, bước cấu hình MVC này thường được auto-configuration xử lý.

### 4.4. Override Spring Data release train trong dự án Spring Boot

Khi dùng spring-boot-starter-parent, Spring Boot cung cấp property spring-data-bom.version để chọn release train Spring Data khác với mặc định:

~~~xml
<properties>
    <spring-data-bom.version>2026.0.2</spring-data-bom.version>
</properties>
~~~

Chỉ đặt property này sau khi xác nhận release train được chọn tương thích với phiên bản Spring Boot và Spring Framework của dự án. Không nâng riêng Spring Data REST hoặc Spring Data JPA bằng một version tùy ý.

Nếu không dùng Spring Boot parent và phải import cả hai BOM, Spring Boot hướng dẫn đặt phần override Spring Data BOM **trước** phần import spring-boot-dependencies trong dependencyManagement. Thứ tự này có ý nghĩa đối với các dependency được quản lý trùng nhau. Hãy dùng cách override có chủ đích, ghi rõ lý do và kiểm tra effective POM sau khi thay đổi.

## 5. Cấu hình bằng Gradle

### 5.1. Spring Boot với Gradle native BOM support

Gradle hỗ trợ import BOM bằng hàm platform(). Ví dụ dưới đây dùng Spring Boot plugin cho tác vụ build ứng dụng và khai báo Boot BOM để quản lý phiên bản dependency:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
~~~

Sau khi BOM được áp dụng, các dependency do BOM quản lý có thể được khai báo mà không cần version. Nếu dự án dùng plugin io.spring.dependency-management, Spring Boot Gradle plugin có thể tự import spring-boot-dependencies BOM; trong trường hợp đó không cần khai báo thêm cùng BOM bằng platform().

### 5.2. Ứng dụng không dùng Spring Boot với Spring Data BOM

Với Gradle project không dùng Spring Boot, có thể dùng Spring Data BOM trực tiếp:

~~~groovy
dependencies {
    implementation platform('org.springframework.data:spring-data-bom:2026.0.2')

    implementation 'org.springframework.data:spring-data-rest-webmvc'
    implementation 'org.springframework.data:spring-data-jpa'
}
~~~

Hãy thêm module store đúng với hệ thống lưu trữ thực tế. Spring Data BOM đồng bộ phiên bản các module Spring Data; ứng dụng vẫn cần cấu hình Spring MVC và các thành phần nền tảng phù hợp.

### 5.3. platform() và enforcedPlatform()

- platform() đưa các phiên bản trong BOM vào dependency graph dưới dạng constraints. Đây là lựa chọn mặc định phù hợp trong đa số dự án.
- enforcedPlatform() áp đặt phiên bản trong BOM như yêu cầu bắt buộc và có thể ghi đè các phiên bản khác trong dependency graph.

Chỉ dùng enforcedPlatform() khi dự án thực sự cần ép toàn bộ dependency theo một bộ phiên bản đã xác định. Nếu dùng không đúng mục đích, nó có thể áp đặt phiên bản lên cả dependency bắc cầu và gây xung đột với thư viện khác.

## 6. Kiểm tra phiên bản đã được phân giải

Cấu hình trong pom.xml hoặc build.gradle chỉ là yêu cầu đầu vào. Hãy kiểm tra dependency graph sau khi build tool phân giải dependency để biết phiên bản thực tế.

Với Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

- help:effective-pom cho thấy cấu hình POM sau khi kế thừa parent và import dependency management.
- dependency:tree cho biết dependency trực tiếp, dependency bắc cầu và phiên bản được chọn.
- clean verify kiểm tra quá trình build và các bước kiểm thử đã cấu hình.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
./gradlew build
~~~

dependencyInsight giúp truy ra dependency nào yêu cầu một module, các version constraint có liên quan và lý do Gradle chọn phiên bản cuối cùng.

Khi kiểm tra, tập trung vào các module Spring Data REST, Spring Data Commons, module store đang dùng và Spring Framework. Nếu thấy nhiều phiên bản hoặc một phiên bản bị override ngoài dự kiến, kiểm tra lại BOM, thứ tự import, version khai báo trực tiếp và dependency bắc cầu.

## 7. Lỗi thường gặp

1. **Đặt BOM trong dependencies thay vì dependencyManagement của Maven.** BOM cần được import với type pom và scope import trong dependencyManagement.
2. **Nghĩ rằng BOM tự thêm thư viện.** BOM chỉ quản lý version; phải khai báo starter hoặc module ứng dụng cần dùng.
3. **Gắn version riêng cho từng module Spring Data.** Việc này có thể phá vỡ tổ hợp phiên bản đã được release train kiểm thử.
4. **Dùng Spring Data BOM mới tùy ý cùng Spring Boot BOM.** Hai bộ quản lý có thể quy định phiên bản cho cùng dependency. Cần dùng cơ chế override được tài liệu Spring Boot hỗ trợ và kiểm tra effective POM/dependency graph.
5. **Nhầm starter với module Spring Data REST.** Ứng dụng Spring Boot thường dùng spring-boot-starter-data-rest; tích hợp Spring MVC không dùng Boot thường khai báo spring-data-rest-webmvc.
6. **Chỉ kiểm tra file build mà không kiểm tra dependency graph.** Phiên bản cuối cùng có thể chịu ảnh hưởng của dependency bắc cầu, constraint hoặc rule phân giải của Gradle.

## 8. Quy trình đề xuất

1. Xác định dự án có dùng Spring Boot hay chỉ dùng Spring Framework/Spring MVC.
2. Chọn Spring Boot BOM cho ứng dụng Boot; chọn Spring Data BOM cho ứng dụng không dùng Boot.
3. Khai báo starter hoặc module thực sự cần dùng, bỏ version nếu BOM đã quản lý.
4. Chỉ override release train khi có yêu cầu rõ ràng và đã kiểm tra tương thích.
5. Chạy dependency:tree hoặc dependencyInsight, sau đó chạy build và test.
6. Khi nâng cấp, thay đổi phiên bản BOM hoặc phiên bản Spring Boot theo một lượt có kiểm soát rồi kiểm tra lại toàn bộ dependency graph.

## 9. Tài liệu tham khảo

- [Spring Boot — Build Systems và Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Maven Plugin: Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot — Gradle Plugin: Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST — Dependencies và Spring Data Release Train BOM](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html)

**Ghi chú phiên bản:** 4.1.2 và 2026.0.2 trong ví dụ là các version minh họa được tài liệu Spring liệt kê tại thời điểm biên soạn (11/11/2026). Khi áp dụng cho dự án thật, hãy chọn phiên bản ổn định tương thích với nền tảng và kiểm tra lại tài liệu của đúng release đang sử dụng.
