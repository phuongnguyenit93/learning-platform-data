# Tạo các ứng dụng Spring Boot có quy trình xây dựng độc lập

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích ý nghĩa của việc mỗi ứng dụng Spring Boot có thể được build, test, đóng gói và phát hành theo quy trình riêng.
2. Phân biệt build độc lập, deploy độc lập, scale độc lập và quyền sở hữu độc lập của một microservice.
3. Tổ chức repository theo mô hình một repository cho mỗi service hoặc monorepo có ranh giới build rõ ràng.
4. Thiết kế cấu trúc Gradle/Maven để build một ứng dụng mà không cần build lại toàn bộ hệ thống.
5. Quản lý dependency, Spring Boot plugin, Java toolchain, BOM và shared library mà không tạo coupling giữa các ứng dụng.
6. Xây dựng pipeline CI riêng theo service, có test, artifact versioning, cache, kiểm tra bảo mật và khả năng tái lập.
7. Đóng gói ứng dụng thành executable JAR hoặc container image và triển khai theo cấu hình môi trường.
8. Giữ API/event contract tương thích khi các ứng dụng được build và phát hành ở thời điểm khác nhau.
9. Thiết kế kiểm thử unit, integration, contract và smoke test phù hợp với từng ứng dụng.
10. Đánh giá các trade-off về tốc độ build, chi phí bảo trì, consistency và quyền tự chủ khi chọn monorepo hay multi-repo.

Trong kiến trúc microservices, mỗi ứng dụng Spring Boot cần có một quy trình xây dựng mà nhóm sở hữu có thể chạy và kiểm chứng độc lập. Khi Team Catalog sửa code, họ nên có khả năng compile, test và tạo artifact Catalog mà không phải chờ Order, Billing hay Notification build thành công trong cùng một lần chạy.

**Build độc lập là một phần của ranh giới sở hữu service.** Nó giúp phát hiện lỗi sớm, rút ngắn feedback và hỗ trợ phát hành riêng; tuy nhiên, vẫn cần quản lý version của thư viện dùng chung, contract API/event và các dependency runtime.

## 1. Build độc lập nghĩa là gì?

Giả sử hệ thống có các ứng dụng:

~~~text
commerce-platform/
  catalog-service/
  order-service/
  payment-service/
  inventory-service/
  notification-service/
~~~

Mỗi ứng dụng có thể sở hữu:
- Source code và package namespace riêng.
- Build configuration và dependency graph rõ ràng.
- Spring Boot application entry point riêng.
- Unit/integration/contract tests riêng.
- Cấu hình và resource đóng gói riêng.
- Executable JAR hoặc container image riêng.
- Version artifact và pipeline CI riêng.
- Quy trình release, rollback và vận hành riêng.

Khi build Catalog, hệ thống chỉ cần source và dependency của Catalog cùng những artifact contract/library đã được công bố. Build không cần biên dịch source của Order hoặc Payment.

### Phân biệt bốn khái niệm

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Independent build | Có thể compile/test/package riêng không? | Chạy task build của Catalog |
| Independent deployment | Có thể triển khai phiên bản mới mà không release service khác không? | Deploy Catalog v1.8 trong khi Order giữ v2.1 |
| Independent scaling | Có thể tăng tài nguyên riêng không? | Catalog tăng từ 3 lên 10 replica |
| Independent ownership | Có owner chịu trách nhiệm code và production không? | Team Catalog quản lý SLO và on-call |

Một ứng dụng có thể build riêng nhưng vẫn phải deploy cùng ứng dụng khác vì contract thay đổi không tương thích. Ngược lại, nhiều module có thể deploy chung dù build task của từng module được chọn riêng.

Build độc lập là điều kiện hỗ trợ autonomy, nhưng chưa tự chứng minh toàn bộ hệ thống đã đạt independent deployability.

## 2. Chọn cách tổ chức source code

Có hai mô hình phổ biến.

### 2.1 Multi-repository: một repository cho mỗi service

~~~text
git/
  catalog-service/
    build.gradle
    settings.gradle
    src/
    Dockerfile
  order-service/
    pom.xml
    src/
    Dockerfile
  payment-service/
    pom.xml
    src/
    Dockerfile
~~~

Mỗi repository có lịch sử, quyền truy cập, pipeline, release tag và quy trình review riêng.

**Ưu điểm:**
- Build context nhỏ và rõ.
- Quyền sở hữu theo nhóm dễ phân định.
- Pipeline chỉ chạy cho một service.
- Có thể chọn nhịp nâng cấp Java, Spring Boot và dependency theo service.
- Release/tag/version của từng ứng dụng không phụ thuộc một repository chung.

**Chi phí:**
- Khó thực hiện một thay đổi xuyên nhiều service trong một pull request.
- Cần quản lý nhiều repository, quyền, branch protection và template.
- Dễ lệch phiên bản plugin/dependency nếu thiếu cơ chế quản lý chung.
- Thay đổi shared library phải phát hành artifact và cập nhật consumer.
- Tạo nhiều bản cấu hình CI giống nhau nếu không có template.

Multi-repo phù hợp khi nhóm có ownership rõ, pipeline/platform đủ tốt và các service cần vòng đời tương đối độc lập.

### 2.2 Monorepo: nhiều service trong một repository

~~~text
commerce-platform/
  settings.gradle
  build.gradle
  catalog-service/
    build.gradle
    src/
  order-service/
    build.gradle
    src/
  payment-service/
    build.gradle
    src/
  inventory-service/
    build.gradle
    src/
  contracts/
    build.gradle
    src/
~~~

Monorepo chứa nhiều ứng dụng nhưng vẫn có thể build một service theo task/path riêng. Một thay đổi trong Catalog có thể được review cùng contract và consumer test nếu cần.

**Ưu điểm:**
- Dễ thực hiện thay đổi đồng bộ trong một PR khi thật sự cần.
- Dùng chung convention, plugin, wrapper và tooling.
- Tái sử dụng code hoặc contract trong cùng repository thuận tiện.
- Dễ tìm dependency giữa các module khi cấu trúc được quản lý tốt.

**Chi phí:**
- Root build có thể cấu hình quá nhiều project nếu thiết kế không tốt.
- Pipeline phải xác định module bị ảnh hưởng.
- Một thay đổi root plugin/convention có thể tác động nhiều service.
- Repository lớn có thể tăng thời gian checkout, indexing và CI.
- Quyền truy cập và ownership cần được quy định theo thư mục/module.

**Monorepo không có nghĩa build chung.** Mục tiêu là giữ ranh giới task/dependency để một ứng dụng có thể được kiểm tra độc lập, dù source nằm cùng repository.

### 2.3 Chọn theo cấu trúc tổ chức

| Điều kiện | Hướng có thể phù hợp |
| --- | --- |
| Nhóm nhỏ, nhiều thay đổi cùng nhau | Monorepo với module boundary rõ |
| Nhóm domain lớn, ownership tách biệt | Multi-repo |
| Shared contract thay đổi thường xuyên | Monorepo có thể giúp review phối hợp |
| Service có nhịp runtime/dependency khác nhau | Multi-repo hoặc monorepo với build convention độc lập |
| Platform team cung cấp golden path tốt | Cả hai mô hình đều có thể vận hành |
| Nhiều service nhưng một nhóm sở hữu tất cả | Chọn theo dependency và release cadence, không theo số repo |

Không có mô hình duy nhất đúng cho mọi tổ chức. Cần ưu tiên khả năng truy vết, build reproducibility, ownership và chi phí bảo trì.

## 3. Cấu trúc chuẩn của một ứng dụng Spring Boot

Một ứng dụng Catalog có thể có cấu trúc:

~~~text
catalog-service/
  .gitignore
  .dockerignore
  README.md
  Dockerfile
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/
    wrapper/
      gradle-wrapper.jar
      gradle-wrapper.properties
  src/
    main/
      java/
        com/example/catalog/
          CatalogApplication.java
          api/
          application/
          domain/
          infrastructure/
      resources/
        application.yml
        db/migration/
    test/
      java/
        com/example/catalog/
          api/
          application/
          domain/
          infrastructure/
    integrationTest/
      java/
~~~

Ý nghĩa:
- File build mô tả Java toolchain, dependency và task của chính Catalog.
- Wrapper cố định phiên bản Gradle để developer/CI dùng cùng build tool.
- Main source chứa code được đóng gói.
- Test source chứa kiểm thử của ứng dụng.
- Resource chứa cấu hình mặc định, migration và tài nguyên cần đóng gói.
- Dockerfile tạo runtime image cho đúng artifact.

Với Maven, cấu trúc tương đương dùng pom.xml và Maven Wrapper:

~~~text
catalog-service/
  pom.xml
  mvnw
  mvnw.cmd
  .mvn/
    wrapper/
  src/
    main/java/
    main/resources/
    test/java/
~~~

### Một application entry point

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Mỗi executable Spring Boot application có entry point riêng. Khi chạy Catalog, Spring context chỉ nên nạp component thuộc Catalog và những thư viện thực sự cần thiết.

Không nên tạo một application class lớn quét package của mọi service trong cùng hệ thống. Việc component scan quá rộng có thể kéo dependency và bean không liên quan vào runtime.

## 4. Gradle: build độc lập cho một service trong monorepo

Một monorepo Gradle có thể khai báo project trong settings.gradle:

~~~groovy
rootProject.name = 'commerce-platform'

include 'catalog-service'
include 'order-service'
include 'payment-service'
include 'inventory-service'
~~~

Root build.gradle chứa convention chung ở mức vừa đủ:

~~~groovy
allprojects {
    group = 'com.example.commerce'
    version = '1.0.0'
}

subprojects {
    repositories {
        mavenCentral()
    }
}
~~~

File catalog-service/build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
    id 'io.spring.dependency-management' version '1.x.y'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các phiên bản plugin 3.x.y và 1.x.y là placeholder. Hãy thay bằng phiên bản tương thích với Java, Gradle và Spring Boot được tổ chức hỗ trợ; không dùng literal placeholder trong build thực tế.

Chạy từ root:

~~~bash
./gradlew :catalog-service:clean
./gradlew :catalog-service:test
./gradlew :catalog-service:bootJar
~~~

Trên Windows:

~~~powershell
.gradlew.bat :catalog-service:clean
.gradlew.bat :catalog-service:test
.gradlew.bat :catalog-service:bootJar
~~~

Gradle chỉ thực thi các task được yêu cầu và dependency graph cần thiết cho các task đó. Tuy nhiên, root build vẫn có thể cấu hình nhiều project. Muốn giảm chi phí configuration, cần dùng plugin/convention phù hợp, tránh logic root nặng và cân nhắc các khả năng như configuration cache hoặc isolated projects theo phiên bản Gradle thực tế.

### Kiểm tra artifact

Thông thường Spring Boot Gradle plugin tạo executable JAR trong build/libs của project:

~~~text
catalog-service/build/libs/catalog-service-1.0.0.jar
~~~

Tên chính xác phụ thuộc archiveBaseName, version và cấu hình build. Chạy:

~~~bash
java -jar catalog-service/build/libs/catalog-service-1.0.0.jar
~~~

Nếu chỉ build Catalog, CI không cần tạo JAR của Order hoặc Payment trừ khi Catalog có khai báo dependency tới artifact được build từ source của chúng.

## 5. Gradle multi-repo: mỗi service là một build độc lập

Với multi-repo, catalog-service có settings.gradle riêng:

~~~groovy
rootProject.name = 'catalog-service'
~~~

build.gradle riêng quản lý plugin và dependency:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
    id 'io.spring.dependency-management' version '1.x.y'
}

group = 'com.example.commerce'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong CI, checkout repository Catalog, dùng Gradle Wrapper và build artifact của repository này. Không cần clone source Order hay Payment để compile.

Nếu Catalog cần một thư viện dùng chung, dependency nên được tiêu thụ như một artifact đã publish, ví dụ:

~~~groovy
dependencies {
    implementation 'com.example.platform:observability-starter:2.3.1'
}
~~~

Nhờ đó build Catalog có thể lấy dependency từ artifact repository mà không cần biên dịch source của repository observability trong cùng một lần chạy.

### Gradle composite build

Composite build cho phép một build tham chiếu build khác trong quá trình phát triển cục bộ, ví dụ:

~~~groovy
includeBuild('../platform-libraries/observability-starter')
~~~

Đây là công cụ hữu ích khi sửa đồng thời library và consumer. Nhưng nếu CI production luôn phải include source build của library, service vẫn có dependency build-time vào repository đó. Muốn artifact service thực sự tái lập và độc lập, cần publish/version library và xác định rõ khi nào dùng composite build để phát triển.

## 6. Maven: build một ứng dụng độc lập

Một repository Maven riêng có pom.xml như sau:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.commerce</groupId>
    <artifactId>catalog-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>3.x.y</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phiên bản 3.x.y là placeholder cần thay bằng phiên bản thực tế tương thích. Maven Wrapper nên được commit cùng repository để developer và CI sử dụng cùng Maven distribution.

Các lệnh thường dùng:

~~~bash
./mvnw clean
./mvnw test
./mvnw package
./mvnw spring-boot:repackage
~~~

Trên Windows:

~~~powershell
.mvnw.cmd clean
.mvnw.cmd test
.mvnw.cmd package
~~~

Khi cấu hình plugin execution phù hợp, package sẽ tạo executable Spring Boot JAR. Kiểm tra target/ và chạy bằng java -jar.

### Maven multi-module trong monorepo

Root pom.xml có thể khai báo modules:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>catalog-service</module>
    <module>order-service</module>
    <module>payment-service</module>
</modules>
~~~

Build riêng một module:

~~~bash
./mvnw -pl catalog-service test
./mvnw -pl catalog-service package
~~~

Thêm -am (also make) nếu module cần những module khác trong cùng reactor:

~~~bash
./mvnw -pl catalog-service -am package
~~~

Cần hiểu rõ khác biệt: -pl chỉ chọn project, còn -am yêu cầu Maven build thêm các module phụ thuộc trong reactor. Nếu Catalog phụ thuộc source của một module shared trong reactor, build không còn chỉ gồm Catalog. Điều này có thể là chủ đích trong monorepo, nhưng phải được phản ánh trong dependency graph và thời gian CI.

## 7. Quản lý phiên bản Spring Boot, Java và dependency

Các service có thể cần cùng một baseline Java/Spring Boot để giảm chi phí hỗ trợ, nhưng không nhất thiết phải dùng chung mọi dependency và nhịp nâng cấp.

### Dùng BOM để quản lý dependency

Spring Boot dependency management cung cấp bộ phiên bản tương thích cho nhiều thư viện. Với Maven có thể import spring-boot-dependencies; với Gradle có thể dùng plugin dependency management hoặc native platform/BOM.

Mục tiêu:
- Không khai báo phiên bản rời rạc cho mọi Spring module nếu BOM đã quản lý.
- Tránh hai service vô tình dùng hai phiên bản thư viện có behavior khác nhau khi contract cần thống nhất.
- Cập nhật dependency có chủ đích và qua CI/security checks.
- Ghi lại version runtime và build tool trong artifact metadata.

### Java toolchain

Gradle Java toolchain giúp chỉ định JDK dùng để compile/test thay vì phụ thuộc JDK mặc định của máy developer:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Maven có thể dùng maven.compiler.release hoặc cấu hình toolchain plugin theo chính sách của tổ chức. CI cũng phải cung cấp JDK tương ứng.

Không chỉ kiểm tra compile. Runtime container phải dùng JRE/JDK tương thích với bytecode và thư viện được đóng gói. Một ứng dụng compile bằng JDK mới nhưng chạy trên runtime cũ có thể thất bại ngay khi startup.

### Version catalog và convention plugin

Trong monorepo Gradle, version catalog có thể tập trung alias và version dependency; convention plugin có thể áp dụng cấu hình Java, test, Spring Boot và quality checks nhất quán.

Tuy nhiên, nếu root build/convention plugin thay đổi, mọi service có thể bị ảnh hưởng. Cần test convention plugin, version hóa nếu được publish và có migration plan khi thay đổi quy tắc chung.

## 8. Shared library: dùng lại vừa đủ

Những thư viện có thể dùng chung:
- Logging/trace context integration.
- Authentication client hoặc chuẩn security nội bộ.
- Error response model nếu contract được quản lý.
- API client generated từ OpenAPI/gRPC.
- Observability starter.
- Domain-independent utility thực sự ổn định.

Cẩn trọng khi tạo một shared library chứa:
- Entity JPA của nhiều service.
- Repository truy cập database của service khác.
- Business service xuyên nhiều bounded context.
- DTO dùng chung cho mọi endpoint dù semantics khác nhau.
- Một bộ model domain khổng lồ khiến release nào cũng buộc các service cập nhật.

**Shared library có thể tạo coupling ở thời điểm build.** Nếu mọi service phụ thuộc version mới nhất của một thư viện lớn, thay đổi nhỏ trong library có thể buộc tất cả build/test lại. Ưu tiên thư viện nhỏ, versioned, có compatibility policy và không mang ownership dữ liệu của service khác.

### Phân biệt contract artifact và implementation library

Contract artifact mô tả cách hai service giao tiếp; implementation library chứa code thực thi. Ví dụ OpenAPI spec có thể sinh client cho Catalog consumer, nhưng không nên đưa toàn bộ implementation của Catalog vào classpath Order.

Nếu consumer cần dùng một DTO, có thể publish schema/contract hoặc generated model có version. Consumer vẫn phải hiểu semantics và không được dùng shared DTO như quyền truy cập database.

## 9. Cấu trúc package trong Spring Boot

Một cách tổ chức theo feature/domain:

~~~text
com.example.catalog
  CatalogApplication.java
  product/
    api/
      ProductController.java
      ProductRequest.java
      ProductResponse.java
    application/
      GetProductUseCase.java
      UpdateProductUseCase.java
    domain/
      Product.java
      ProductRepository.java
    infrastructure/
      JpaProductRepository.java
      ProductEntity.java
  category/
    api/
    application/
    domain/
    infrastructure/
  config/
  health/
~~~

Cấu trúc này giữ API, application logic, domain và persistence của Catalog trong một application boundary. Không nhất thiết phải tạo một Gradle subproject cho từng package; package/module boundary ở code và build boundary của ứng dụng là hai cấp độ khác nhau.

Tránh để một service import trực tiếp package private của service khác. Nếu hai service cần giao tiếp, dùng HTTP/gRPC client hoặc event consumer theo contract đã công bố.

### Component scan

Application class nên nằm ở package root của chính service để component scan tự nhiên bao phủ package con cần thiết. Nếu shared library có configuration, có thể dùng auto-configuration hoặc import rõ ràng theo cách thư viện hỗ trợ.

Không mở component scan tới package root của toàn monorepo; điều này có thể kéo controller, repository, entity và bean của ứng dụng khác vào context.

## 10. Cấu hình ứng dụng độc lập

Mỗi service có application.yml và cấu hình riêng:

~~~yaml
spring:
  application:
    name: catalog-service
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/catalog}
    username: ${DB_USERNAME:catalog}
    password: ${DB_PASSWORD:}
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
server:
  port: 8080
~~~

Các placeholder trong YAML minh họa cách lấy cấu hình từ environment. Không commit mật khẩu production hoặc token vào repository. Cần dùng secret manager hoặc cơ chế quản lý secret của nền tảng.

### Profiles và environment

Có thể có:
- application.yml: default an toàn, không chứa secret.
- application-local.yml: cấu hình máy cá nhân.
- application-test.yml: cấu hình kiểm thử.
- Environment variables: cấu hình deploy.
- Secret store: mật khẩu, private key, credential.

Không nên tạo một profile tên production rồi nhúng endpoint/secret cố định. Cấu hình runtime cần được cấp theo môi trường và có thể kiểm tra riêng khỏi artifact.

### Mỗi service có cổng và identity riêng

Khi chạy local đồng thời:
- Catalog: 8081.
- Order: 8082.
- Payment: 8083.

Cổng là ví dụ; container production thường có thể dùng cùng internal port 8080 vì mỗi container/network namespace riêng. Tên service, metrics, health endpoint và resource identity cần nhất quán để quan sát.

## 11. Quản lý database migration riêng

Một ứng dụng Spring Boot có thể dùng Flyway hoặc Liquibase để quản lý schema thuộc service đó. Ví dụ:

~~~text
catalog-service/
  src/main/resources/
    db/migration/
      V1__create_product.sql
      V2__add_product_status.sql
~~~

Catalog chịu trách nhiệm schema Catalog. Order không nên phụ thuộc vào migration nội bộ của Catalog hoặc chạy script trực tiếp vào Catalog DB.

Build độc lập không có nghĩa migration luôn chạy an toàn khi ứng dụng khởi động. Với production:
- Migration có thể được chạy bằng một job riêng hoặc giai đoạn release có kiểm soát.
- Dùng expand-and-contract cho schema thay đổi phá vỡ.
- Kiểm tra tương thích giữa phiên bản app cũ và schema mới trong rolling deploy.
- Backup/restore và rollback migration phải có kế hoạch.
- Tránh migration dài giữ lock trong giờ cao điểm.
- Theo dõi migration version và kết quả trên từng môi trường.

Ví dụ đổi cột cần triển khai theo pha: thêm cột mới, backfill, dual-read/dual-write nếu cần, chuyển code, sau đó mới xóa cột cũ khi không còn consumer. Không dùng một release duy nhất để drop cột mà app cũ vẫn đang chạy.

## 12. API/event contract không được phụ thuộc vào build cùng lúc

Giả sử Order cần dùng Catalog API. Trong build Order, nó chỉ cần client contract hoặc generated client version đã publish. Không cần build source Catalog cùng thời điểm.

~~~text
Catalog Service
    |
    +--> OpenAPI contract v2
             |
             v
      Artifact/Contract Registry
             |
             v
      Order generated client v2
             |
             v
       Order Service build
~~~

Các nguyên tắc:
- Contract có version và owner.
- Producer thêm field theo hướng tương thích khi có thể.
- Consumer có tests cho schema và semantics mà nó dùng.
- Breaking change dùng migration plan và support window.
- Event consumer hỗ trợ dữ liệu lịch sử theo replay/retention policy.
- Không giả định build pass đồng nghĩa runtime contract tương thích.

Nếu Order gọi Catalog API trong runtime, việc compile không chứng minh Catalog đang deploy đúng version. Cần integration/contract tests và rollout compatibility.

## 13. Tạo REST client theo contract

Spring Boot có thể dùng HTTP interface, RestClient hoặc WebClient tùy phiên bản và nhu cầu. Ví dụ interface đơn giản:

~~~java
public interface CatalogClient {
    ProductResponse getProduct(String productId);
}
~~~

Implementation cần định nghĩa base URL, timeout, auth, serialization và error mapping theo cấu hình của Order. Không hard-code địa chỉ Catalog production vào code.

Một client production cần:
- Timeout connect/read phù hợp ngân sách latency.
- Retry có giới hạn và chỉ với thao tác phù hợp.
- Idempotency khi request có side effect.
- Circuit breaker/bulkhead nếu cần.
- Trace propagation và metrics.
- Mapping lỗi rõ ràng.
- Version compatibility.

Nếu dùng generated client, version client artifact phải được pin và cập nhật theo contract. Không tự động lấy latest trong mỗi build vì artifact có thể đổi behavior mà không có PR review.

## 14. Build và test không cần service khác chạy

Một mục tiêu của build độc lập là unit test Catalog không phải khởi động Order, Payment hoặc broker thật.

Phân lớp kiểm thử:
1. **Unit test:** domain/application logic với dependency giả hoặc mock có chủ đích.
2. **Spring slice test:** ví dụ WebMvcTest hoặc DataJpaTest để kiểm tra phần Spring cần thiết.
3. **Component/integration test:** chạy với database/broker thực tế qua Testcontainers hoặc môi trường test tương đương.
4. **Contract test:** kiểm tra provider/consumer theo spec.
5. **End-to-end test:** kiểm tra hành trình nhiều service, chạy ít hơn và dành cho luồng quan trọng.
6. **Smoke test:** xác minh artifact vừa deploy khởi động và đáp ứng endpoint cần thiết.

Ví dụ test Spring Boot:

~~~java
@SpringBootTest
class CatalogApplicationTest {
    @Test
    void applicationContextLoads() {
    }
}
~~~

Test này xác nhận context khởi động trong cấu hình test, nhưng không chứng minh toàn bộ API/DB/event hoạt động. Cần test bổ sung theo rủi ro và dependency của ứng dụng.

### Test với Testcontainers

Một integration test có thể khởi chạy PostgreSQL riêng trong container để kiểm tra repository/migration. Khi test, mỗi service chỉ khởi tạo dependency mà chính service đó cần.

Lợi ích:
- Build không cần database dùng chung của môi trường staging.
- Test có thể lặp lại và cô lập.
- Version DB có thể pin.
- CI có thể chạy trong worker/container phù hợp.

Chi phí:
- Cần Docker/container runtime hoặc môi trường hỗ trợ.
- Khởi tạo container tốn thời gian.
- Test phải quản lý dữ liệu và cleanup.
- Không thay thế kiểm thử network/security thật ở môi trường tích hợp.

## 15. Gradle task và Maven lifecycle theo service

Một pipeline build service nên có các bước rõ:
- Kiểm tra wrapper/toolchain.
- Compile.
- Unit tests.
- Integration/contract tests theo scope.
- Static analysis/lint.
- Dependency vulnerability checks.
- Package executable JAR.
- Tạo SBOM/metadata nếu tổ chức yêu cầu.
- Build container image.
- Scan image.
- Publish artifact/image theo version bất biến.

Ví dụ Gradle:

~~~bash
./gradlew :catalog-service:check
./gradlew :catalog-service:bootJar
~~~

Ví dụ Maven:

~~~bash
./mvnw -pl catalog-service verify
~~~

Maven verify thường chạy các phase trước đó trong lifecycle và các plugin đã được gắn vào lifecycle. Nếu integration test plugin chưa cấu hình, lệnh verify không tự động tạo ra mọi kiểm thử mà nhóm mong muốn.

### Không dùng task build chung một cách mặc định

Chạy ./gradlew build hoặc mvn verify ở root có thể build nhiều service. Điều này phù hợp cho nightly/full regression hoặc thay đổi root convention, nhưng CI theo service nên xác định đúng project bị ảnh hưởng.

Nếu thay đổi ở một thư viện dùng chung, pipeline cần chạy consumer impact tests cho những service sử dụng artifact đó. Tách build không có nghĩa bỏ qua dependency thật.

## 16. CI pipeline độc lập cho từng ứng dụng

Một workflow CI cho Catalog có thể mô tả:

~~~text
Push / Pull Request affecting catalog-service
                  |
                  v
          Checkout repository
                  |
                  v
          Set up JDK / Gradle
                  |
                  v
            Compile + Unit Test
                  |
                  v
        Integration / Contract Test
                  |
                  v
       Static analysis / dependency scan
                  |
                  v
            Build bootJar
                  |
                  v
          Build container image
                  |
                  v
         Scan + publish immutable artifact
                  |
                  v
         Deployment workflow / approval
~~~

CI của Catalog không cần chạy pipeline Order khi source Order không thay đổi. Tuy nhiên:
- Thay đổi shared build convention có thể ảnh hưởng tất cả service.
- Thay đổi contract Catalog cần kiểm tra consumer đã đăng ký.
- Thay đổi thư viện chung cần chạy compatibility tests.
- Thay đổi base image hoặc JDK có thể cần rebuild nhiều service.
- Một PR thay đổi nhiều thư mục cần xác định tất cả module bị ảnh hưởng.

### Path filters trong monorepo

CI có thể chỉ chạy Catalog khi thay đổi nằm trong:
- catalog-service/**
- build convention được Catalog sử dụng.
- contract mà Catalog sở hữu.
- shared library mà Catalog phụ thuộc.

Nhưng path filter cần hiểu dependency graph. Nếu một file root build.gradle thay đổi, tất cả service có thể bị ảnh hưởng dù path filter đơn giản chỉ nhìn thư mục service.

### Tránh build không tái lập

- Commit Gradle/Maven Wrapper.
- Pin plugin và dependency version.
- Dùng lockfile/dependency locking khi phù hợp.
- Kiểm soát JDK, locale và build environment.
- Không tải dependency từ URL không ổn định.
- Dùng artifact repository có retention và access policy.
- Không dùng latest hoặc dynamic version trong release build nếu không kiểm soát.
- Lưu build metadata/commit SHA trong artifact.

Build tái lập giúp xác định artifact production được tạo từ source và dependency nào, hỗ trợ rollback và audit.

## 17. Versioning artifact và container image

Mỗi service nên có version độc lập, ví dụ:
- catalog-service: 1.8.0
- order-service: 2.4.1
- payment-service: 1.3.2

Không nhất thiết các service cùng tăng version theo một số chung. Version nên phản ánh release của từng artifact và quy ước SemVer nếu tổ chức chọn SemVer.

Container image nên được publish bằng tag không mơ hồ, ví dụ:

~~~text
registry.example.com/catalog-service:1.8.0
registry.example.com/catalog-service:git-a1b2c3d
~~~

Production deployment nên có cách xác định image digest bất biến, vì tag có thể bị ghi đè nếu registry policy cho phép. Build pipeline nên ghi commit SHA, build time và dependency metadata theo yêu cầu audit.

Nếu một shared library phát hành version 2.3.1, Catalog có thể nâng cấp riêng và chạy tests mà không buộc Order nâng cấp cùng lúc. Cần giữ compatibility của library theo support policy.

## 18. Dockerfile cho Spring Boot application

Một Dockerfile đơn giản dùng executable JAR:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

RUN useradd --system --uid 10001 appuser

COPY build/libs/catalog-service-1.0.0.jar app.jar

USER 10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Tên artifact phải khớp output thực tế của build. Base image và version cần pin theo policy; trong production nên ưu tiên image được scan, có digest/version kiểm soát và được cập nhật bảo mật.

### Build container từ artifact đã kiểm thử

Có hai cách thường gặp:
- CI build JAR rồi đóng gói image từ đúng JAR đã được test.
- Multi-stage Docker build thực hiện compile/package trong builder stage rồi tạo runtime image.

Cách đầu giúp đảm bảo image chứa artifact đã qua test nếu pipeline không build lại khác nội dung. Multi-stage build tiện cho môi trường developer, nhưng cần kiểm soát cache, dependency và provenance.

### Runtime container

- Chạy non-root user.
- Không đóng gói secret vào image.
- Externalize config.
- Giới hạn CPU/memory phù hợp.
- Có health endpoints.
- Log ra stdout/stderr theo chuẩn nền tảng.
- Graceful shutdown và termination grace period.
- Image nhỏ, ít package thừa.
- Scan vulnerability và có quy trình rebuild khi base image có bản vá.

## 19. Spring Boot health và readiness

Một service build độc lập vẫn phải cung cấp tín hiệu để platform biết nó có thể phục vụ hay chưa.

Spring Boot Actuator có thể cung cấp health endpoints. Cấu hình ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Kubernetes Deployment có thể dùng readiness và liveness:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

Readiness trả lời pod đã sẵn sàng nhận traffic chưa. Liveness giúp phát hiện tiến trình không thể tự phục hồi. Không đưa mọi dependency ngoài vào liveness probe theo cách khiến toàn bộ pod restart khi một hệ thống bên ngoài tạm lỗi.

Cấu hình endpoint phải phù hợp Spring Boot version và health group thực tế của ứng dụng. Không copy probe path vào Kubernetes nếu Actuator chưa được thêm hoặc endpoint chưa được bật.

## 20. Cấu hình runtime không được buộc build lại artifact

Một nguyên tắc hữu ích là **build once, deploy many**: cùng một artifact được triển khai qua dev, test, staging và production với cấu hình ngoài khác nhau.

Ví dụ:
- Dev dùng database local.
- Test dùng database container.
- Staging dùng database staging.
- Production dùng endpoint và secret do môi trường cấp.

Không build JAR riêng cho production chỉ để thay URL hoặc password. Cấu hình runtime phải được externalize và được validate khi ứng dụng khởi động.

Có thể dùng:
- Environment variables.
- Kubernetes ConfigMap/Secret.
- Secret manager.
- Spring profiles cho cấu hình không nhạy cảm.
- Config server nếu tổ chức thực sự cần và có vận hành phù hợp.

Một config server chung cũng là dependency runtime; phải tính availability, cache, bootstrap và cách service khởi động khi config server lỗi.

## 21. Shared build convention và golden path

Khi có nhiều ứng dụng, copy build.gradle hoặc pom.xml từ service này sang service khác dễ gây lệch. Platform team có thể cung cấp:
- Convention plugin cho Gradle.
- Parent POM/BOM cho Maven.
- Template repository.
- Base Dockerfile/runtime image.
- CI reusable workflow.
- Dependency/security policy.
- Logging/metrics/trace starter.
- Build cache và artifact repository.

Một convention plugin Gradle có thể áp dụng Java toolchain, test task, lint và plugin version thống nhất. Một parent POM có thể quản lý dependencyManagement và pluginManagement.

Nhưng convention chung không nên chứa logic nghiệp vụ hoặc ép mọi service có cùng database/runtime nếu workload khác nhau. Khi đổi convention, phải có version, changelog và migration guide; một thay đổi root có thể ảnh hưởng toàn bộ build.

## 22. Tích hợp local: chạy nhiều service mà vẫn giữ build riêng

Developer có thể chạy riêng từng ứng dụng:

~~~bash
./gradlew :catalog-service:bootRun
./gradlew :order-service:bootRun
~~~

Hoặc với multi-repo:

~~~bash
cd catalog-service
./gradlew bootRun
~~~

Để kiểm thử một luồng gồm Order gọi Catalog, có thể chạy Catalog và Order như hai process riêng, mỗi process dùng config local. Docker Compose có thể khởi chạy các dependency như PostgreSQL, Redis hoặc broker.

Điều này giúp:
- Catalog unit test không cần Order.
- Order component test có thể mock Catalog API.
- Integration test của hai service chạy cùng lúc khi cần.
- Mỗi service vẫn build artifact riêng.

Không nên biến lệnh chạy local của một service thành script tự clone/build/deploy toàn bộ hệ thống mà không có lý do. Tách rõ quick feedback của service và môi trường tích hợp đầy đủ.

## 23. Cô lập dependency test

Một ứng dụng build độc lập cần biết dependency nào bắt buộc để compile, test và runtime.

| Loại dependency | Ví dụ | Cách quản lý |
| --- | --- | --- |
| Compile/runtime | Spring Web, JDBC driver | Khai báo trong application build |
| Test only | JUnit, Mockito, Testcontainers | Test scope/configuration |
| Contract | Generated API client/schema | Artifact có version |
| Runtime external | PostgreSQL, Redis, broker | Config + integration environment |
| Build tool | Gradle/Maven, JDK | Wrapper/toolchain |
| Platform | logging/trace starter | Versioned shared artifact hoặc convention |
| Deployment | base image, Helm chart | Pin version/digest và pipeline |

Nếu test cần truy cập staging chung để chạy, build sẽ dễ thất bại khi staging không sẵn sàng. Nên tách unit/component tests tự chủ và chỉ dùng shared environment cho kiểm thử tích hợp cần thiết.

## 24. Quản lý dependency giữa các service

Một build dependency hợp lý có thể là:

~~~text
Order Service build
    |
    +--> Spring Boot dependencies
    |
    +--> order-domain code
    |
    +--> catalog-api-client:2.1.0
    |
    +--> platform-observability:1.7.2
    |
    +--> test libraries
~~~

Order không cần source Catalog để compile. Runtime mới gọi Catalog qua HTTP hoặc nhận event theo contract.

Nếu Order khai báo Gradle project dependency trực tiếp vào catalog-service, hoặc Maven module dependency vào source module chứa toàn bộ Catalog, hai ứng dụng đã bị ghép ở build time. Có thể đây là một bước tạm trong monorepo, nhưng cần đánh giá liệu đó có phải shared contract/library nhỏ hay đã kéo implementation của service khác vào.

### Dependency direction

- API client phụ thuộc vào contract được publish.
- Service implementation phụ thuộc vào library nền tảng có version.
- Không để domain model của Service A trở thành model persistence chung cho Service B.
- Không dùng shared database entity làm contract.
- Không để build task của A cần chạy application B.
- Không dùng source path tuyệt đối từ máy developer.

## 25. Thay đổi shared library mà không phá quy trình độc lập

Giả sử observability-starter có version 1.7.2, Team Platform phát hành 1.8.0:
1. Library có pipeline riêng, test và publish artifact.
2. Changelog mô tả thay đổi và compatibility.
3. Catalog nâng version trong pull request của Catalog.
4. CI Catalog chạy compile/test/contract checks.
5. Catalog phát hành riêng sau khi pass.
6. Order vẫn dùng 1.7.2 cho tới khi nhóm Order sẵn sàng nâng cấp.

Đây là lợi ích của dependency versioning. Nếu mọi service dùng latest snapshot hoặc lấy source branch main, build không còn tái lập và việc thay đổi library có thể gây lỗi bất ngờ.

Một shared library breaking change cần migration plan, support window và kiểm tra các consumer đã đăng ký. Không được coi library nội bộ là “không có contract” chỉ vì nó được publish trong artifact repository riêng.

## 26. Build cache và tối ưu tốc độ

Build độc lập không chỉ là chọn đúng project; nó còn là làm cho feedback nhanh và ổn định.

Gradle có thể sử dụng:
- Local build cache.
- Remote build cache có quyền và isolation phù hợp.
- Configuration cache nếu plugin/build logic hỗ trợ.
- Parallel execution khi task an toàn.
- Incremental compilation và dependency caching.

Maven có thể sử dụng:
- Local repository cache.
- Remote artifact repository.
- Plugin cấu hình incremental khi phù hợp.
- Build agents có cache được quản lý.

Cần theo dõi:
- Configuration time.
- Compile time.
- Unit/integration test time.
- Dependency download time.
- Cache hit/miss.
- Container image build time.
- Thời gian từ push đến feedback.

Không chia nhỏ task để tăng tốc nếu làm mất tính đúng đắn hoặc cache không an toàn giữa các branch/tenant. Remote build cache cần kiểm soát nội dung artifact, quyền ghi và tính nhất quán.

## 27. Reproducible build và nguồn gốc artifact

Một artifact có thể được truy vết về:
- Commit SHA.
- Service version.
- Java/Gradle/Maven version.
- Spring Boot/plugin version.
- Dependency lock/BOM.
- Build environment/base image.
- Test result và scan result.
- Build timestamp/provenance theo quy định.

Mục tiêu là khi production chạy catalog-service:1.8.0, nhóm có thể xác định chính xác source và dependency tạo ra nó.

Không build lại artifact sau khi đã kiểm thử rồi deploy một file khác có cùng tag. Pipeline nên promote cùng artifact qua các môi trường, sử dụng digest bất biến và lưu metadata phù hợp.

## 28. Ví dụ CI cho một service trong GitHub Actions

Ví dụ workflow rút gọn cho repository Catalog:

~~~yaml
name: catalog-service-ci

on:
  pull_request:
    paths:
      - 'catalog-service/**'
      - '.github/workflows/catalog-service-ci.yml'
  push:
    branches: [main]
    paths:
      - 'catalog-service/**'
      - '.github/workflows/catalog-service-ci.yml'

jobs:
  verify:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: catalog-service
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Verify
        run: ./gradlew clean check bootJar
~~~

Đây là ví dụ cấu trúc workflow, cần điều chỉnh runner, action version, wrapper và path theo repository thật. Nếu build.gradle nằm ngay root của repository riêng, không cần working-directory catalog-service.

Với monorepo, path filters phải bao gồm file build convention, shared library và contract mà Catalog sử dụng. Nếu không, một thay đổi dependency chung có thể không kích hoạt pipeline Catalog.

### Pull request và main branch

- PR: compile, unit, contract, static analysis và kiểm tra thay đổi.
- Main: build artifact version bất biến, scan và publish theo policy.
- Release: promote artifact đã publish sang môi trường đích.
- Deploy: rollout/canary, smoke test và theo dõi SLO.

Không nhất thiết deploy production ngay mỗi lần main thay đổi. Release policy có thể cần approval hoặc cửa sổ triển khai; nhưng build/test của service vẫn có thể độc lập.

## 29. Kiểm soát chất lượng và bảo mật dependency

Mỗi build pipeline nên cân nhắc:
- Static analysis và formatting.
- Unit/integration test.
- Dependency vulnerability scan.
- License policy.
- Secret scanning.
- Container image scan.
- SBOM generation.
- Artifact signing/provenance nếu yêu cầu.
- Kiểm tra base image và JDK support.
- Kiểm tra dependency bị bỏ maintenance.

Không để một shared vulnerability scan thất bại ở service không liên quan chặn mọi build nếu policy không yêu cầu; nhưng khi root/base image/shared library bị ảnh hưởng, cần fan-out kiểm tra tới các consumer thật.

Dependency updates cần được phân loại:
- Security critical: xử lý theo SLA bảo mật.
- Patch/minor compatible: có thể tự động tạo PR và chạy tests.
- Major/breaking: cần migration review.
- Runtime/JDK upgrade: kiểm tra behavior, memory, GC và performance.

## 30. Build độc lập và deploy độc lập trong Kubernetes

Sau khi tạo image riêng, mỗi service có Deployment/Service riêng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: catalog
          image: registry.example.com/catalog-service:1.8.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
~~~

Ví dụ chỉ minh họa cấu trúc Deployment. Production cần bổ sung resources, probes, service account, security context, secret/config management, rollout strategy, image digest và policy phù hợp.

Mỗi service có pipeline deploy riêng, có thể triển khai Catalog mà không cần rollout Order. Tuy nhiên, nếu Catalog thay đổi contract breaking, vẫn phải phối hợp thứ tự producer/consumer để runtime tương thích.

### Build independent nhưng runtime dependency vẫn có

Catalog có thể build mà không cần Order, nhưng runtime vẫn gọi Pricing hoặc Search. Khi dependency down, Catalog có thể giảm chức năng hoặc trả lỗi theo contract. Build độc lập không có nghĩa service không phụ thuộc runtime.

## 31. Release và migration database an toàn

Một build độc lập có thể tạo artifact mới trong khi database schema vẫn đang được dùng bởi version cũ. Vì vậy, migration cần tương thích qua giai đoạn rollout.

Ví dụ đổi product_name thành display_name:
1. Thêm cột display_name.
2. Migration/backfill dữ liệu.
3. App version mới ghi cả hai hoặc đọc fallback theo quy tắc.
4. Rollout tất cả pod mới.
5. Xác minh dữ liệu và consumer.
6. Ngừng đọc cột cũ.
7. Xóa cột cũ trong một release sau.

Nếu xóa cột ngay trong cùng deploy đầu tiên, pod cũ có thể lỗi trong rolling update hoặc rollback. Một service có build pipeline riêng vẫn cần kế hoạch tương thích schema qua nhiều phiên bản runtime.

## 32. Kiểm tra build độc lập bằng dependency graph

Một số dấu hiệu build chưa độc lập:
- Build Catalog tự động gọi task compile Order.
- Catalog compile bằng source path trỏ sang repository khác.
- CI phải checkout tất cả repo chỉ để tạo JAR Catalog.
- Test Catalog yêu cầu toàn bộ hệ thống staging hoạt động.
- Một module shared chứa implementation business của nhiều service.
- Version dependency dùng latest hoặc snapshot không kiểm soát.
- Thay đổi plugin root buộc rebuild tất cả dù không có impact analysis.
- Artifact Catalog không thể tạo lại từ commit và dependency đã lưu.

Có thể kiểm tra task graph Gradle bằng task dry-run phù hợp, hoặc Maven reactor build plan. Mục tiêu là biết **những project/task nào thật sự cần thiết**, không cần build toàn bộ để xác nhận một service.

Không đánh đồng task không chạy với dependency không tồn tại: root build có thể vẫn cấu hình project, plugin hoặc convention dù task execution chỉ gồm một service. Nếu thời gian configuration là bottleneck, cần tối ưu build logic riêng.

## 33. Tổ chức test để vừa độc lập vừa bảo vệ tích hợp

| Loại test | Chạy khi nào | Phụ thuộc |
| --- | --- | --- |
| Unit test | Mỗi PR | Không cần service khác |
| Spring slice/component test | Mỗi PR hoặc theo module | Chỉ context cần thiết |
| DB integration test | PR/release | DB container hoặc môi trường test |
| Contract test | PR và provider release | Contract artifact/registry |
| Consumer verification | Provider CI | Consumer contracts đang được hỗ trợ |
| End-to-end | Nightly/release gate theo rủi ro | Một nhóm service tích hợp |
| Smoke test | Sau deploy | Artifact/runtime thật |
| Performance test | Trước release quan trọng hoặc định kỳ | Workload và dependency đại diện |

Một bộ E2E rất lớn có thể khiến pipeline mỗi service phải chờ cả hệ thống. Tách test theo scope giúp feedback nhanh, nhưng không bỏ qua test contract và các hành trình business quan trọng.

## 34. Quản lý test data và local dependencies

Một service build/test riêng cần có test data độc lập:
- Fixture/factory tạo dữ liệu có nghĩa.
- Test database được reset hoặc transaction rollback phù hợp.
- Không phụ thuộc record thủ công trong staging.
- Không dùng credential production.
- Không chia sẻ mutable test account giữa các pipeline song song.
- Container/port được cấp động khi test concurrency.
- Test cleanup và timeout rõ.

Nếu một test Catalog thất bại vì dữ liệu Order trong staging bị thay đổi bởi team khác, pipeline chưa thật sự cô lập. Tạo test environment hoặc Testcontainers cho dependency mà Catalog sở hữu giúp kết quả ổn định hơn.

## 35. Các anti-pattern cần tránh

**Một build.gradle root khổng lồ chứa logic mọi service.** Thay đổi nhỏ có thể làm mọi build chậm và khó hiểu. Dùng convention plugin và cấu hình theo module.

**Service phụ thuộc source của service khác.** Build autonomy giảm và implementation boundary bị rò rỉ. Dùng contract/client artifact đã version hóa.

**Shared library chứa domain model của toàn hệ thống.** Mọi team phải cập nhật cùng lúc. Giữ thư viện nhỏ và ổn định.

**Dùng latest/snapshot trong release build.** Cùng một commit có thể tạo artifact khác nhau ở hai thời điểm. Pin dependency.

**CI chạy toàn bộ monorepo cho mọi PR.** Feedback chậm và chi phí tăng. Dùng path/dependency impact analysis, vẫn fan-out khi shared root thay đổi.

**CI chỉ build JAR mà không chạy tests.** Artifact compile được nhưng có thể sai behavior hoặc contract. Dùng test gates theo risk.

**Build độc lập nhưng deploy luôn cùng nhau.** Pipeline tách nhưng release coupling vẫn còn. Theo dõi dependency và compatibility.

**Build lại image ở mỗi môi trường.** Artifact dev/test không còn là artifact production. Promote cùng artifact/digest, externalize config.

**Đưa secret vào application.yml hoặc image.** Tăng rủi ro rò rỉ và buộc rebuild khi rotate. Dùng secret management.

**Chạy migration database không kiểm soát lúc startup.** Nhiều replica có thể cùng tranh lock hoặc migration dài gây downtime. Có migration job/lock và release plan.

**Test mọi dependency qua shared staging.** Pipeline phụ thuộc tình trạng hệ thống ngoài. Dùng unit/component/integration cô lập, E2E có chọn lọc.

**Tách repository nhưng dùng chung database/schema tùy tiện.** Build độc lập nhưng data ownership vẫn coupling. Có contract và quyền sở hữu dữ liệu rõ.

**Không pin JDK/Gradle/Maven.** Developer và CI có kết quả khác nhau. Dùng wrapper và toolchain.

**Dùng root task thành công làm bằng chứng từng service độc lập.** Cần chạy task target cụ thể và xem dependency graph.

## 36. Checklist tạo một Spring Boot application có build độc lập

- [ ] Service có repository hoặc module boundary rõ và owner cụ thể.
- [ ] Có application entry point riêng.
- [ ] Có Gradle/Maven build file và wrapper được commit.
- [ ] Java toolchain/runtime version được xác định.
- [ ] Dependency được pin hoặc quản lý qua BOM/version catalog.
- [ ] Build chỉ cần source và artifact dependency thực sự của service.
- [ ] Shared library nhỏ, versioned và có compatibility policy.
- [ ] Không import implementation hoặc database entity của service khác.
- [ ] Cấu hình runtime được externalize; không đóng gói secret.
- [ ] Database migration thuộc owner service và có chiến lược rolling compatibility.
- [ ] API/event contract có version và tests.
- [ ] Unit, integration và contract tests chạy được theo scope service.
- [ ] CI chạy build/test/package độc lập theo path/dependency graph.
- [ ] Artifact JAR/image có version và provenance rõ.
- [ ] Image chạy non-root, có health probes và resource limits phù hợp.
- [ ] Cùng một artifact được promote giữa môi trường.
- [ ] Có smoke test, monitoring và rollback riêng.
- [ ] Build có thể tái lập từ commit và dependency đã pin.
- [ ] Có runbook và người chịu trách nhiệm production.
- [ ] Đã xác nhận build độc lập không đồng nghĩa bỏ qua runtime contract.

## 37. Bài tập thực hành

Một nền tảng thương mại điện tử có ba ứng dụng Spring Boot: Catalog, Order và Payment. Hiện tại chúng nằm trong một monorepo Gradle; root build có shared module common chứa DTO, JPA entity và utility. CI chạy toàn bộ build khi bất kỳ file nào thay đổi. Catalog cần phát hành thường xuyên; Order và Payment có nhịp release chậm hơn. Cả ba cùng dùng một database schema.

Hãy thiết kế:
1. Cấu trúc monorepo mới để mỗi service có build task riêng.
2. Những phần nào của common nên trở thành contract artifact hoặc library nhỏ, phần nào phải thuộc owner service.
3. Gradle task để build/test/bootJar riêng Catalog.
4. Cách quản lý Java toolchain, Spring Boot BOM và plugin version.
5. CI path/dependency filters khi Catalog hoặc shared convention thay đổi.
6. Cách tạo artifact/image bất biến và promote qua môi trường.
7. Lộ trình tách database ownership mà không làm Order/Payment ngừng hoạt động.
8. Contract tests để Catalog deploy mới vẫn tương thích với consumer cũ.
9. Chiến lược Testcontainers và E2E để build nhanh nhưng vẫn kiểm tra tích hợp.
10. Các metric chứng minh build autonomy: CI duration, task graph, dependency wait, build failure và release frequency.

Hãy phân biệt rõ việc build Catalog riêng với việc Catalog có thể deploy riêng. Nếu ba service vẫn dùng chung database schema và cùng migration, cần nêu bước tiếp theo để giảm coupling runtime/data.

## Kết luận

Tạo các ứng dụng Spring Boot có quy trình xây dựng độc lập giúp mỗi nhóm nhận feedback nhanh, kiểm soát dependency và tạo artifact riêng. Có thể đạt điều đó bằng multi-repo hoặc monorepo; điểm quyết định là build graph, contract và ownership có ranh giới rõ. Gradle/Maven wrapper, Java toolchain, BOM, shared library có version, test phân lớp và CI theo service tạo nền tảng cho build reproducible.

Để lợi ích đi tới production, cần tiếp tục quản lý API/event compatibility, database migration, cấu hình runtime, image provenance, observability và rollback. Một ứng dụng build riêng là bước quan trọng; independent deployment chỉ thực sự đạt được khi các service có thể cùng tồn tại qua nhiều phiên bản mà không phải phát hành đồng bộ.
