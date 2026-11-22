# Thêm `spring-boot-starter-data-rest` với Maven và Gradle

Spring Data REST xuất các Spring Data repository thành REST resources theo mô hình hypermedia. Khi thêm starter vào một ứng dụng Spring Boot có Spring MVC, Boot tự cấu hình phần tích hợp này. Bạn có thể tạo API CRUD cơ bản từ repository mà không cần viết một controller cho từng thao tác.

Ví dụ trong bài dùng Spring Boot 4.1.2 và Java 17. Đây là phiên bản minh họa; nếu dự án đã dùng một dòng Spring Boot khác, hãy giữ phiên bản hiện tại của dự án và để dependency management của phiên bản đó quản lý các thư viện Spring.

## 1. Hiểu đúng vai trò của starter

Tọa độ dependency:

- Group: `org.springframework.boot`
- Artifact: `spring-boot-starter-data-rest`

Starter này cung cấp tích hợp Spring Data REST với Spring MVC và cấu hình tự động của Spring Boot. Nó không tự tạo domain model, repository hoặc hệ quản trị cơ sở dữ liệu. Bạn vẫn cần một Spring Data module phù hợp với nơi lưu dữ liệu, chẳng hạn:

- JPA: `spring-boot-starter-data-jpa` cùng JDBC driver.
- MongoDB: `spring-boot-starter-data-mongodb`.
- JDBC: `spring-boot-starter-data-jdbc`.

Trong ví dụ thực hành bên dưới, JPA và H2 chỉ là phần lưu trữ để minh họa. Dependency cần thêm để xuất repository qua REST vẫn là `spring-boot-starter-data-rest`.

Spring Data REST được xây dựng trên Spring MVC. Nếu ứng dụng hiện tại là ứng dụng MVC, starter đã cung cấp phần tích hợp web cần thiết; không thêm một web starter khác chỉ để tạo các endpoint Spring Data REST. Nếu ứng dụng chỉ dùng WebFlux, hãy cân nhắc thiết kế endpoint reactive bằng WebFlux thay vì coi starter này là một giải pháp REST reactive.

## 2. Thêm dependency bằng Maven

Nếu dự án dùng `spring-boot-starter-parent`, hãy khai báo phiên bản Spring Boot ở parent. Maven sẽ lấy phiên bản phù hợp của các starter từ dependency management do parent cung cấp.

Ví dụ phần liên quan trong `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>people-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Xuất Spring Data repositories thành REST resources -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>

        <!-- Backend lưu trữ dùng trong ví dụ -->
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

Trong một dự án đã có parent và các dependency khác, không thay parent chỉ để thêm Spring Data REST. Chỉ cần thêm dependency sau vào thẻ `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
~~~

Nếu dự án không kế thừa `spring-boot-starter-parent`, có thể import BOM `org.springframework.boot:spring-boot-dependencies` trong `<dependencyManagement>`. Khi BOM đã được import, dependency starter cũng không cần khai báo version riêng. Cách này giữ các phiên bản Spring Boot và Spring Data tương thích với nhau.

## 3. Thêm dependency bằng Gradle

Với Gradle Groovy DSL, khai báo Spring Boot plugin và import BOM để Gradle quản lý phiên bản các dependency:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    // Xuất Spring Data repositories thành REST resources
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'

    // Backend lưu trữ dùng trong ví dụ
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu dự án đã áp dụng plugin `io.spring.dependency-management` và plugin này import BOM Spring Boot, không cần khai báo thêm dòng `implementation platform(...)`. Chỉ thêm các dependency vào khối `dependencies` hiện có.

Với Gradle Kotlin DSL trong `build.gradle.kts`, phần dependency tương đương là:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("com.h2database:h2")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Trong cả hai DSL, `implementation` đặt thư viện trên compile và runtime classpath của ứng dụng; `runtimeOnly` phù hợp với JDBC driver chỉ cần khi chạy. Không khai báo một version độc lập cho từng starter khi BOM đã quản lý chúng.

## 4. Tạo repository để Spring Data REST xuất endpoint

Chỉ thêm dependency chưa làm xuất hiện endpoint nếu ứng dụng chưa có repository. Cần có domain type, repository tương ứng và cấu hình lưu trữ hợp lệ.

Ví dụ tối giản dưới đây dùng JPA và H2. Đặt các lớp trong cùng package hoặc package con của lớp ứng dụng có `@SpringBootApplication` để component/repository scanning tìm thấy chúng.

**Lớp khởi động — `DemoApplication.java`:**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**Entity — `Person.java`:**

~~~java
package com.example.demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Person() {
        // Constructor không tham số cho JPA.
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

**Repository — `PersonRepository.java`:**

~~~java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

`JpaRepository` cung cấp các thao tác lưu, tìm, cập nhật và xóa cơ bản. `@RepositoryRestResource(path = "people")` đặt đường dẫn collection rõ ràng để API không phụ thuộc vào quy tắc tự suy ra tên resource từ tên domain class.

**Cấu hình — `src/main/resources/application.properties`:**

~~~properties
spring.datasource.url=jdbc:h2:mem:peopledb
spring.datasource.username=sa
spring.datasource.password=

# Chỉ dùng create-drop cho ví dụ với cơ sở dữ liệu trong bộ nhớ.
spring.jpa.hibernate.ddl-auto=create-drop

# Đặt tiền tố cho các endpoint Spring Data REST.
spring.data.rest.base-path=/api
~~~

Khi ứng dụng khởi động, Spring Boot cấu hình Spring Data REST và Spring Data JPA. Repository được phát hiện trong phạm vi scan sẽ được xuất theo quy tắc phát hiện repository của Spring Data REST, trừ khi repository hoặc cấu hình đánh dấu không xuất.

Với cấu hình trên, API collection có địa chỉ:

~~~text
http://localhost:8080/api/people
~~~

Các thao tác thường gặp:

| HTTP request | Ý nghĩa |
| --- | --- |
| `GET /api/people` | Lấy danh sách Person |
| `POST /api/people` | Tạo Person mới |
| `GET /api/people/{id}` | Lấy một Person |
| `PUT /api/people/{id}` | Thay thế dữ liệu Person |
| `PATCH /api/people/{id}` | Cập nhật một phần Person |
| `DELETE /api/people/{id}` | Xóa Person |

HTTP method cụ thể được xuất phụ thuộc vào các method mà repository cung cấp và cấu hình export. Ví dụ trên dùng `JpaRepository`, vì vậy có đủ các thao tác CRUD thông dụng.

## 5. Chạy và kiểm tra

Với Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`. Nếu không có Maven Wrapper, dùng `mvn spring-boot:run`.

Với Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`.

Khi ứng dụng đã chạy, gửi request tạo một bản ghi:

~~~bash
curl -i -X POST http://localhost:8080/api/people -H "Content-Type: application/json" -H "Accept: application/hal+json" --data '{"name":"An"}'
~~~

Kết quả mong đợi là HTTP `201 Created`. Response thường có header `Location` trỏ đến resource vừa tạo và representation theo HAL. ID do database sinh ra nên giá trị cụ thể có thể khác nhau.

Đọc collection vừa tạo:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/people
~~~

Kết quả mong đợi là HTTP `200 OK`. Nội dung HAL có các liên kết `_links`; khi collection có dữ liệu, các phần tử thường nằm trong `_embedded`. Với PowerShell, gọi `curl.exe` để tránh alias `curl` của Windows PowerShell.

Có thể mở endpoint gốc `http://localhost:8080/api` để xem các liên kết tài nguyên mà Spring Data REST công bố. Nếu không đặt `spring.data.rest.base-path`, các resource mặc định được phục vụ từ URI gốc.

## 6. Những điểm cần hiểu khi dùng trong ứng dụng thật

- **Repository là API surface:** Spring Data REST có thể xuất trực tiếp thao tác repository thành HTTP API. Vì vậy, thêm một repository công khai có thể làm xuất hiện endpoint mới. Chỉ xuất các repository mà client thực sự được phép truy cập.
- **Starter không thay thế database:** `spring-boot-starter-data-rest` không tự cung cấp JPA, MongoDB, JDBC driver hay cấu hình kết nối. Chọn đúng Spring Data store và cấu hình datasource/connection riêng.
- **Không cần controller cho CRUD mặc định:** Các thao tác CRUD cơ bản có thể được xử lý bởi repository đã xuất. Khi cần workflow nghiệp vụ, kiểm soát transaction hoặc response chuyên biệt, hãy cân nhắc service và controller rõ ràng thay vì đưa mọi nghiệp vụ thành thao tác repository.
- **Hypermedia là một phần của response:** Spring Data REST dùng HAL để client điều hướng qua các liên kết. Client nên đọc liên kết từ response thay vì giả định mọi URL đều cố định.
- **Kiểm soát phạm vi export:** Có thể dùng `@RepositoryRestResource(exported = false)` để không xuất một repository. Có thể đặt `path` và `collectionResourceRel` để kiểm soát tên resource và relation.
- **Bảo mật trước khi triển khai:** Endpoint tạo, sửa và xóa có thể thay đổi dữ liệu thật. Cần thiết kế authentication, authorization, giới hạn method và kiểm soát dữ liệu được serialize trước khi đưa API ra môi trường dùng chung.
- **Không trộn phiên bản Spring thủ công:** Tránh tự đặt version cho riêng Spring Data REST hoặc Spring Framework khi Spring Boot BOM đã quản lý. Việc ghi đè có thể tạo ra tổ hợp thư viện không tương thích.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Maven báo thiếu version cho starter | Dự án không kế thừa Boot parent và chưa import Boot BOM | Kiểm tra `<parent>` hoặc `<dependencyManagement>` |
| Gradle không phân giải được dependency | Thiếu `mavenCentral()`, BOM hoặc cấu hình repository | Kiểm tra `repositories` và dependency constraints |
| Ứng dụng khởi động nhưng endpoint trả 404 | Repository nằm ngoài package scan, base path sai hoặc repository không được export | Kiểm tra package của `@SpringBootApplication`, `spring.data.rest.base-path` và annotation export |
| Ứng dụng lỗi khi khởi động datasource | Thiếu store starter, JDBC driver hoặc cấu hình kết nối | Kiểm tra JPA/store dependency, URL, username, password và trạng thái database |
| POST trả 401 hoặc 403 | Security policy hoặc CSRF policy chặn request | Kiểm tra cấu hình Spring Security và quyền của endpoint |
| Client không đọc được response | Client không xử lý media type/representation HAL | Gửi `Accept: application/hal+json` và đọc các liên kết trong response |

## 8. Checklist hoàn thành

- [ ] Đã thêm `spring-boot-starter-data-rest` vào đúng file build.
- [ ] Phiên bản starter được quản lý bởi cùng Spring Boot parent/BOM với các dependency còn lại.
- [ ] Đã thêm Spring Data store và database driver phù hợp với ứng dụng.
- [ ] Repository được đặt trong package mà Spring Boot scan.
- [ ] Ứng dụng khởi động thành công.
- [ ] Đã kiểm tra GET collection và POST một resource.
- [ ] Đã xem lại repository nào được export và chính sách bảo mật trước khi triển khai.

## Tài liệu chính thức

- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/intro.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/how-to/data-access.html)
