# Chọn bộ phiên bản JDK, Spring Boot và Spring Security tương thích

Trong quá trình **khởi tạo và cấu hình Spring Security OAuth 2.0/OIDC Resource Server**, việc chọn đúng bộ **JDK + Spring Boot + Spring Security** quyết định ứng dụng có thể build, khởi động, xác minh Bearer token và được bảo trì an toàn hay không. Chọn từng phiên bản độc lập rất dễ gây xung đột nhị phân, lỗi cấu hình bảo mật hoặc lỗi chỉ xuất hiện trên môi trường production.

**Nguyên tắc quan trọng nhất:** chọn một phiên bản **Spring Boot được hỗ trợ**, chọn **JDK nằm trong dải Java mà phiên bản Boot đó hỗ trợ**, rồi để **Spring Boot dependency management/BOM** lựa chọn Spring Framework và Spring Security tương ứng. Không tự ghép Security 7.x với một dự án Boot 3.x, hoặc chọn phiên bản Gradle không chạy được trên JDK thực tế.

Bài học đi từ cách đọc ma trận tương thích, lựa chọn release line, cấu hình dự án Maven/Gradle đến kiểm tra classpath và xử lý các lỗi thường gặp trong OAuth2 Resource Server.

## 1. Vì sao không thể chỉ chọn ba con số phiên bản?

Giả sử nhóm phát triển muốn dùng:

~~~text
JDK:             21
Spring Boot:     4.1.2
Spring Security: 6.5.11
~~~

JDK 21 có thể đáp ứng Java baseline của Boot 4.1.2, nhưng **Security 6.5.11** thuộc thế hệ mà Boot 3.5.x quản lý, còn Boot 4.1.2 quản lý **Security 7.1.2**. Bắt ép một số module quay về 6.5.x có thể khiến Spring Framework, Security Filter Chain và các module OAuth2 không tương thích.

Ngay cả tổ hợp JDK và Spring đúng, build vẫn có thể thất bại nếu dùng **Gradle Wrapper** quá cũ hoặc Spring Cloud release train không phù hợp.

Vì vậy, cần xác minh nhiều lớp:

| Lớp | Cần kiểm | Sai lệch thường gặp |
|---|---|---|
| **JDK** | Java tối thiểu, dải Java được Boot công bố, compiler/toolchain, JVM production | Build được với Java 21 nhưng runtime chỉ có Java 17 |
| **Spring Boot** | Release line, bản vá, lifecycle, BOM và auto-configuration | Dùng bản Boot cũ đã hết chính sách vá lỗi mong muốn |
| **Spring Framework** | Major/minor do Boot quản lý | Ép Spring Framework 6.x vào Boot 4.x |
| **Spring Security** | Major/minor do Boot quản lý; các module cùng thế hệ | Core/Web 7.x nhưng OAuth2 Resource Server 6.x |
| **Build tool** | Maven/Gradle, wrapper, plugin Boot và hỗ trợ Java | Gradle 7.6 với Spring Boot 4.1 |
| **HTTP runtime** | Servlet/MVC hoặc WebFlux, container và Jakarta API | Thư viện dùng javax.servlet trong runtime Jakarta |
| **OAuth/OIDC** | JWT/opaque token, JOSE, issuer, audience, scope, Security DSL | Thiếu JwtDecoder hoặc module JOSE |
| **Hệ sinh thái** | Spring Cloud, Data, Gateway, test libraries, monitoring agents | Starter bên ngoài kéo dependency trái thế hệ |

**Biên dịch thành công** chưa đủ để kết luận **chạy đúng và an toàn**. Sau khi chọn bộ phiên bản, Resource Server vẫn phải xác minh access token, từ chối token không hợp lệ và kiểm quyền truy cập endpoint/tài nguyên.

## 2. Quan hệ giữa JDK, Spring Boot, Spring Framework và Spring Security

- **JDK** cung cấp công cụ biên dịch, Java API và JVM để chạy ứng dụng. Phiên bản compiler và runtime cần phù hợp với bytecode/artifact được tạo ra.
- **Spring Framework** cung cấp DI container, HTTP stack, dữ liệu nền và các API được các module Spring sử dụng.
- **Spring Security** cung cấp xác thực, phân quyền, filter chain, OAuth2 Resource Server, JWT verification, opaque-token introspection và các tính năng bảo mật khác.
- **Spring Boot** chọn các phiên bản dependency nhất quán, cung cấp starters, build plugin và auto-configuration.

~~~mermaid
flowchart TD
    A[Yêu cầu kỹ thuật và vận hành] --> B[Chọn Spring Boot release line]
    B --> C[Chọn JDK hợp lệ]
    B --> D[Spring Boot BOM / Dependency Management]
    D --> E[Spring Framework]
    D --> F[Spring Security]
    D --> G[JOSE, JSON và thư viện liên quan]
    C --> H[Maven/Gradle Wrapper và CI]
    E --> I[OAuth2 Resource Server]
    F --> I
    G --> I
~~~

**BOM (Bill of Materials)** là tập thông tin dùng để quản lý phiên bản của các dependency. Khi sử dụng **spring-boot-starter-parent** hoặc import **spring-boot-dependencies** đúng cách, Maven có thể tự xác định version cho các dependency mà Boot quản lý. Gradle có cơ chế tương đương thông qua **platform()** hoặc plugin dependency management.

Ví dụ khi đã dùng Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
</dependency>
~~~

Không khai báo version ở dependency trên là **chủ đích**, vì bản Boot 4.x tương ứng quản lý version cho starter và các dependency transitive.

## 3. Ma trận phiên bản tham khảo

Theo trang **System Requirements** và **Managed Dependency Coordinates** chính thức, đối với những bản phát hành được kiểm tra ngày **15/11/2026**:

| Spring Boot | Spring Framework do Boot quản lý | Spring Security do Boot quản lý | Dải Java công bố | Định hướng |
|---|---|---|---|---|
| **4.1.2** | **7.0.10** | **7.1.2** | **Java 17–27** | Thế hệ Boot 4, dùng starter mới |
| **3.5.16** | **6.2.19** | **6.5.11** | **Java 17–25** | Thế hệ Boot 3, dùng starter tương ứng |

Đây là **ảnh chụp phiên bản theo các patch cụ thể**. Bản vá khác trong cùng nhánh có thể quản lý những patch mới hơn của Framework/Security. Cũng không nên coi mốc trên là bản mới nhất vĩnh viễn: trước khi lập dự án hoặc triển khai, hãy đọc lại tài liệu của release được chốt.

Nguồn kiểm tra:

- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html)
- [Spring Boot 4.1 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)

### 3.1. Hai bộ lựa chọn dễ kiểm soát

**Phương án A — Dự án mới:**

~~~text
JDK                  21 LTS
Spring Boot          4.1.2
Spring Framework     7.0.10, do Boot quản lý
Spring Security      7.1.2, do Boot quản lý
HTTP stack           Spring MVC / Servlet
Resource Server      Spring Boot 4 security-oauth2-resource-server starter
~~~

Đây là bộ minh họa hợp lý khi thư viện và hạ tầng đã sẵn sàng với Spring Boot 4. Việc chọn Java 21 thay vì JDK cao nhất được hỗ trợ thường giúp sử dụng một mốc LTS quen thuộc; vẫn cần xem tổ chức đang chuẩn hóa JDK nào.

**Phương án B — Giữ hệ sinh thái Boot 3.5:**

~~~text
JDK                  21 LTS
Spring Boot          3.5.16
Spring Framework     6.2.19, do Boot quản lý
Spring Security      6.5.11, do Boot quản lý
HTTP stack           Spring MVC / Servlet
Resource Server      Spring Boot 3 oauth2-resource-server starter
~~~

Phương án này phù hợp để hiểu một dự án đang chạy trên Boot 3.5. Trong production, cần kiểm tra **vòng đời hỗ trợ bản 3.5.x** và yêu cầu vá lỗi trước khi quyết định ở lại nhánh này.

### 3.2. Đừng nhầm mức Java tối thiểu với dải tương thích

Spring Boot **4.1.2** và **3.5.16** đều yêu cầu **tối thiểu Java 17**, nhưng dải Java phía trên không giống nhau trong tài liệu của các bản tương ứng. Điều đó có nghĩa:

- **JDK 11** không đáp ứng baseline của cả hai phiên bản.
- **JDK 17 hoặc 21** nằm trong dải Java công bố của cả hai phiên bản nêu ở bảng.
- **JDK 25** nằm trong dải được công bố của Boot 3.5.16 và 4.1.2, nhưng phải kiểm tiếp support của công cụ build và plugin.
- **JDK 27** nằm trong dải Boot 4.1.2 công bố; không thể suy ra Boot 3.5.16 đã hỗ trợ JDK 27.

Dải Java của Boot **không tự bảo đảm** Gradle, Maven plugin, bytecode enhancer, annotation processor, IDE hay CI image đã hỗ trợ JDK đó. Cũng không nên chạy production ở một Java version không được hệ thống vận hành/chính sách hỗ trợ chỉ vì ứng dụng khởi động được.

## 4. Maven và Gradle có ma trận riêng

Tài liệu yêu cầu build tool cho các patch được nêu:

| Build tool | **Boot 4.1.2** | **Boot 3.5.16** |
|---|---|---|
| **Maven** | **3.6.3 trở lên** | **3.6.3 trở lên** |
| **Gradle** | **8.x từ 8.14** hoặc **9.x** | **7.x từ 7.6.4** hoặc **8.x từ 8.4** |

Ví dụ:

- **Boot 4.1.2 + Gradle 7.6**: không nằm trong phạm vi build tool được Spring Boot 4.1 công bố.
- **Boot 3.5.16 + Gradle 8.4**: đáp ứng giới hạn Gradle của Boot 3.5; vẫn kiểm JVM dùng chạy Gradle.
- **Boot 4.1.2 + JDK 25 + Gradle 8.14**: chưa thể kết luận hỗ trợ hoàn chỉnh chỉ từ bảng Boot; phải đối chiếu Java compatibility của chính Gradle/Gradle daemon.
- **Boot 4.1.2 + Maven 3.9.x + JDK 21**: là hướng Maven phổ biến, với điều kiện các plugin dự án cũng tương thích.

Nên commit **Maven Wrapper** hoặc **Gradle Wrapper** vào repository để máy phát triển, CI và production build dùng cùng công cụ. Tránh phụ thuộc phiên bản Maven/Gradle được cài tùy ý trên mỗi máy.

Nếu dùng Gradle, cần phân biệt:

1. **JDK chạy Gradle daemon**.
2. **Java toolchain để biên dịch**.
3. **JVM chạy ứng dụng đã đóng gói**.

Chúng có thể không phải một JDK và có yêu cầu tương thích khác nhau.

Tài liệu hữu ích: [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html).

## 5. Tại sao nên để Boot quản lý Spring Security?

Spring Security không chỉ là một dependency đơn lẻ. Một Resource Server JWT có thể dùng đồng thời:

~~~text
spring-security-core
spring-security-config
spring-security-web
spring-security-oauth2-core
spring-security-oauth2-resource-server
spring-security-oauth2-jose
~~~

Spring Boot cung cấp dependency management để các module này và Spring Framework khớp nhau. Tránh tự ghi những version không đồng bộ như:

~~~text
spring-boot-starter-webmvc             4.1.2
spring-security-core                   7.1.2
spring-security-web                    6.5.11  <-- lệch thế hệ
spring-security-oauth2-resource-server 7.1.2
~~~

Hậu quả có thể là **NoSuchMethodError**, **NoClassDefFoundError**, lỗi tạo SecurityFilterChain hoặc lỗi chỉ xuất hiện khi xử lý Bearer token. Maven/Gradle có quy tắc resolution riêng; build thông qua không phải bằng chứng các module đã đúng thế hệ.

Chỉ nên override một dependency Security ngoài BOM trong trường hợp có lý do rõ ràng, đã xác nhận tính tương thích và có kiểm thử, chẳng hạn cần bản vá đặc biệt trước khi Boot release thích hợp. Với hoạt động thường ngày, **nâng patch Spring Boot** thường là hướng dễ duy trì hơn.

### 5.1. Spring Security 6 và 7 khác nhau ở đâu?

- **Spring Security 6.x** là thế hệ thường đi cùng Spring Framework 6 và Spring Boot 3.x.
- **Spring Security 7.x** là thế hệ đi cùng Spring Framework 7 và Spring Boot 4.x.
- Việc nâng **6 → 7** là **major migration**, cần đọc [Spring Security Migration Guide](https://docs.spring.io/spring-security/reference/migration/) để chuẩn bị API/configuration, framework và tích hợp Jackson.
- Nếu còn code dùng API cũ như **WebSecurityConfigurerAdapter** hoặc phụ thuộc module OAuth2 legacy, cần xem hướng chuyển đổi sang **SecurityFilterChain** và mô hình Resource Server hiện đại.

Đừng chỉ sửa version của một artifact trong project để “thử Security 7” trong khi vẫn giữ Boot 3.

## 6. Spring Boot 4 đổi tên một số starter

Đây là khác biệt thực tế ngay khi khởi tạo dự án:

| Tính năng | **Spring Boot 3.5.x** | **Spring Boot 4.x** |
|---|---|---|
| Servlet / Spring MVC | **spring-boot-starter-web** | **spring-boot-starter-webmvc** |
| OAuth2 Resource Server | **spring-boot-starter-oauth2-resource-server** | **spring-boot-starter-security-oauth2-resource-server** |
| OAuth2/OIDC Client | **spring-boot-starter-oauth2-client** | **spring-boot-starter-security-oauth2-client** |
| OAuth2 Authorization Server | **spring-boot-starter-oauth2-authorization-server** | **spring-boot-starter-security-oauth2-authorization-server** |

Tài liệu Boot 4 ghi nhận những tên starter cũ vẫn xuất hiện trong danh mục nhưng **deprecated** để chuyển sang tên mới. Với dự án Boot 4 mới, nên dùng starter mới ngay từ đầu. Với Boot 3.5, dùng các tên starter của chính nhánh 3.5; không áp tên mới của Boot 4 vào Boot 3.

Lưu ý phân biệt ba vai trò:

- **Resource Server**: API nhận và xác minh Bearer access token, kiểm quyền.
- **OAuth2/OIDC Client**: ứng dụng thực hiện đăng nhập hoặc xin token để gọi API.
- **Authorization Server/OpenID Provider**: phát hành token, cung cấp issuer metadata, JWKS, introspection và các endpoint liên quan.

Một API chỉ cần xác minh JWT thường **không cần** OAuth2 Client starter hay Authorization Server starter.

Nguồn: [Spring Boot Build Systems — danh mục starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html).

## 7. Dự án mẫu Spring Boot 4.1.2 + JDK 21 + Maven

Giả sử tạo **Orders API** dùng Spring MVC và JWT access token do Authorization Server bên ngoài phát hành.

### 7.1. Chọn thông số ban đầu

Trên [Spring Initializr](https://start.spring.io/) hoặc cấu hình thủ công:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Project | Maven |
| Language | Java |
| Spring Boot | **4.1.2** |
| Java | **21** |
| Packaging | Jar |
| Web | Spring MVC |
| Authentication | OAuth2 Resource Server |
| Token | JWT được ký bởi issuer tin cậy |

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-resource-server</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>orders-resource-server</name>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
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

Những điểm then chốt:

1. **Parent Boot 4.1.2** định nghĩa dependency management cho Spring Framework, Security và các thư viện liên quan.
2. **java.version 21** thể hiện mức Java của dự án. Vẫn phải chuẩn bị JDK 21 ở build và JVM phù hợp khi chạy.
3. **webmvc** phù hợp ứng dụng Servlet. Nếu chọn WebFlux, phải dùng starter WebFlux và cấu hình reactive security.
4. Starter **security-oauth2-resource-server** cung cấp dependency cần thiết theo nhánh Boot 4; không tự ghim version Spring Security.
5. Dự án **không tự phát hành access token**. Issuer và audience là cấu hình từ hệ thống danh tính đáng tin cậy.

### 7.3. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Giá trị issuer/audience ở đây chỉ minh họa. Trong môi trường thật, **issuer-uri** phải khớp claim **iss** của access token, còn **audiences** phải khớp đối tượng nhận token được phát hành cho API. Resource Server xác minh JWT dựa trên issuer/JWKS hoặc khóa tin cậy; chỉ dùng token để cấp quyền sau khi token đã được xác minh.

### 7.4. SecurityFilterChain cho Servlet

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Đoạn này minh họa Security DSL cho Spring Security 7.x. **SCOPE_orders.read** yêu cầu access token có scope **orders.read** theo cơ chế ánh xạ scope thành GrantedAuthority. Cần kiểm thêm quyền chủ sở hữu/tenant trên từng đơn hàng; scope không tự chứng minh người dùng được đọc mọi đơn.

Các vấn đề như CSRF, session management, lỗi 401/403, phía client dùng cookie hay bearer header và CORS phải được thiết kế theo kiến trúc cụ thể. Một project khởi động được chưa có nghĩa chính sách bảo mật đã đầy đủ.

## 8. Dự án Spring Boot 3.5.16 tương ứng

Với ứng dụng chưa nâng sang Boot 4, hãy dùng **JDK 21 + Boot 3.5.16** và tên starter của Boot 3.

Phần quan trọng của **pom.xml**:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Đây là phần trích, không phải toàn bộ file Maven POM. Parent Boot 3.5.16 quản lý Security **6.5.11** theo dependency coordinates tại thời điểm nêu trên.

Spring Security 6.x cũng có thể dùng **SecurityFilterChain** và API OAuth2 Resource Server hiện đại. Điều không nên làm là thêm Spring Security 7.1.x chỉ vào một module để giữ một feature mới trong khi cả project vẫn đang ở Boot 3.5.x.

### Khi nào chọn Boot 3.5 thay vì Boot 4?

Một dự án đang dùng Boot 3.5 có thể cần giữ lại trong khi:

- Các thư viện Spring Cloud, Gateway, JPA hoặc adapter đặc thù chưa được nâng.
- Nhóm chưa hoàn thành kiểm thử thay đổi major hoặc migration Jackson/Jakarta.
- Hệ thống đang vận hành theo SLA nghiêm ngặt và cần kế hoạch triển khai nhiều giai đoạn.

Tuy nhiên, **không được dùng lý do “đang chạy ổn” để bỏ qua bảo trì**. Luôn kiểm lịch hỗ trợ của release line và bản vá bảo mật. Với dự án mới, ưu tiên chọn nền tảng stable và được hỗ trợ đáp ứng các ràng buộc của tổ chức.

## 9. Dùng Gradle: Java toolchain và BOM

Ví dụ **build.gradle** Groovy cho **Boot 4.1.2**, sử dụng Gradle Wrapper đáp ứng yêu cầu Boot 4.1:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong ví dụ này:

- **org.springframework.boot plugin** và **spring-boot-dependencies BOM** đều dùng 4.1.2; phải nâng chúng đồng bộ.
- **platform()** là cách Gradle gắn dependency constraints vào các configuration liên quan.
- **toolchain Java 21** giúp chọn JDK compile, nếu JDK đó sẵn có hoặc được toolchain resolver cung cấp.
- Không cần chỉ định version riêng cho module Security.
- Cần kiểm Gradle wrapper và version Java chạy Gradle daemon, bởi **toolchain** không tự thay JDK chạy Gradle.

Trong một dự án thực tế có nhiều module, có thể dùng version catalog hoặc convention plugin để tránh lặp version giữa plugin và BOM.

Khi dùng plugin **io.spring.dependency-management**, có thể để plugin Spring Boot phối hợp quản lý BOM thay vì gọi **platform()**; hãy chọn một cách được tài liệu hướng dẫn và tránh đưa thêm constraint trái chiều.

## 10. Kiểm JDK build và JDK runtime

### 10.1. Java 21 compile không có nghĩa Java 17 chạy được

Một ứng dụng biên dịch ra Java 21 bytecode thường cần runtime Java 21 trở lên tương thích. Nếu chuyển nó vào image chỉ có Java 17, có thể gặp lỗi:

~~~text
java.lang.UnsupportedClassVersionError:
class file version 65.0; runtime only recognizes up to 61.0
~~~

Version class file **65** tương ứng Java 21; **61** tương ứng Java 17.

Ví dụ mô hình container:

~~~dockerfile
# Minh họa các stage, không phải Dockerfile hoàn chỉnh.
FROM eclipse-temurin:21-jdk AS builder
# Copy source, chạy Maven/Gradle Wrapper và tạo JAR.

FROM eclipse-temurin:21-jre
# Copy JAR từ stage builder và khởi chạy.
~~~

Hãy kiểm image thực tế tại CI và production. Pin image tag/digest phù hợp chính sách, quản lý bản vá JDK thường xuyên. Việc JDK ở máy developer khác JDK trong container dễ gây sai lệch khi build.

### 10.2. Kiểm trực tiếp phiên bản

Các lệnh thông dụng:

~~~bash
java -version
javac -version
mvn -version

# Với Maven Wrapper trên macOS/Linux:
./mvnw -version

# Với Gradle Wrapper trên macOS/Linux:
./gradlew -version
~~~

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
.\mvnw.cmd -version
.\gradlew.bat -version
~~~

Lệnh Maven/Gradle wrapper cho biết **Java đang chạy build tool**. Đối với Gradle toolchain, xem thêm cấu hình Java compiler và JDK được chọn. Với Maven, nếu cần nhiều JDK trên cùng máy, xem Maven Toolchains và kiểm cấu hình compiler release.

Lưu ý **JAVA_HOME**, cấu hình PATH, IDE project SDK, CI runner và Docker image có thể trỏ tới những JDK khác nhau. Khi phân tích lỗi, cần xác nhận từng môi trường thực tế.

## 11. Kiểm dependency tree để phát hiện xung đột

Dù code không chỉ định version Security, một thư viện bên thứ ba có thể đưa transitive dependency hoặc constraints gây ra việc chọn version khác dự kiến.

### 11.1. Maven

Trên Linux/macOS:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security:*
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.security:*"
~~~

Có thể xem effective POM và dependencyManagement:

~~~bash
./mvnw help:effective-pom
~~~

Trong output, tập trung các dependency Spring Security thực tế được resolve. Với Boot 4.1.2, thông thường các module Security nằm ở nhánh **7.1.2**; với Boot 3.5.16 là **6.5.11**. Đọc phần **resolved version**, không chỉ bản được một dependency transitive yêu cầu.

### 11.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-security-oauth2-resource-server
~~~

Tương đương Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency spring-security-oauth2-resource-server
~~~

**runtimeClasspath** cho biết bộ dependency mà ứng dụng sẽ nạp khi chạy. **dependencyInsight** giúp biết phiên bản cuối cùng được chọn do BOM, conflict resolution hoặc constraints nào. Nếu cần, kiểm các module Spring Security liên quan để tìm bản bị ép sai.

### 11.3. Những dấu hiệu nên điều tra

- **spring-security-core** và **spring-security-web** được resolve thành hai major khác nhau.
- **spring-framework** hoặc Servlet API được ghi đè ngoài bộ Boot.
- Spring Cloud starter thuộc release train không hỗ trợ Boot đang dùng.
- **spring-security-oauth2-resource-server** có mặt nhưng **spring-security-oauth2-jose** thiếu trong một thiết lập JWT tự quản lý.
- Spring Security 7.x xuất hiện trong dự án Boot 3.x mà chưa có migration/bộ phụ thuộc tương ứng.
- Một module third-party pin quá chặt Nimbus JOSE/Jackson gây xung đột.

Không giải quyết xung đột bằng cách tăng version tất cả dependency lên bản mới nhất riêng lẻ. Hãy tìm nguồn version, so ma trận tương thích và thay đổi có kiểm soát.

## 12. JWT hay opaque token ảnh hưởng cấu hình nhưng không quyết định JDK

Sau khi chọn bộ phiên bản, Resource Server còn phải biết **access token dạng nào**:

| Tiêu chí | JWT access token | Opaque access token |
|---|---|---|
| Cách kiểm token | JWT signature/JWKS và validators | Token introspection tới Authorization Server |
| Thành phần Spring Security | **JwtDecoder** | **OpaqueTokenIntrospector** |
| Cấu hình chính | **resourceserver.jwt** | **resourceserver.opaquetoken** |
| Đọc quyền từ | Claims của JWT đã được xác minh | Introspection response đáng tin cậy |
| Phụ thuộc vào issuer | Có thể lấy public keys qua HTTPS/JWKS | Thường cần introspection endpoint và client credentials |

Ví dụ JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Ví dụ opaque-token config ở mức khái niệm:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: read-from-secret-manager
          client-secret: read-from-secret-manager
~~~

Đây chỉ là minh họa cấu trúc property, không nên hardcode client secret thật vào source control. Sử dụng environment variables hoặc secret manager có kiểm soát.

Nếu **không dùng Spring Boot starter**, cấu hình JWT cần các module phù hợp như **spring-security-oauth2-resource-server** và **spring-security-oauth2-jose**. Dù chọn JWT hay opaque, Resource Server vẫn phải kiểm **issuer/audience khi phù hợp, hiệu lực token và quyền nghiệp vụ**; OIDC ID Token dùng cho client đăng nhập không tự trở thành access token của API.

## 13. Servlet và WebFlux dùng cấu hình Security khác nhau

Có hai nhánh HTTP stack phổ biến:

| Đặc điểm | Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|---|
| Cơ chế web | Servlet filter chain | Reactive WebFilter chain |
| Security bean | **SecurityFilterChain** | **SecurityWebFilterChain** |
| Builder | **HttpSecurity** | **ServerHttpSecurity** |
| JWT decoder | **JwtDecoder** | **ReactiveJwtDecoder** |
| Boot starter | **webmvc** (Boot 4) / **web** (Boot 3) | **webflux** |

Ví dụ **Servlet**:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ví dụ **Reactive**:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Đây là hai hướng khác nhau. Không ghép hai cấu hình vào cùng một ứng dụng chỉ để thử code từ hướng dẫn trên Internet. Khi chọn version và starter, phải xác định HTTP stack theo kiến trúc ứng dụng.

## 14. Migration: Java 8/11, Boot 2.x, Security 5.x lên Boot 3/4

Một ứng dụng legacy có thể đang dùng:

~~~text
Java 8 hoặc 11
Spring Boot 2.x
Spring Framework 5.x
Spring Security 5.x
javax.servlet.*
WebSecurityConfigurerAdapter
~~~

Việc nâng lên Boot 3.x/4.x thường phải xử lý nhiều thay đổi đồng thời.

### 14.1. Nâng nền tảng Java

Boot 3 và Boot 4 yêu cầu Java 17 trở lên. Cần nâng JDK development, CI, build tool, container runtime và agent/plugins. Nếu định dùng JDK 21, hãy đảm bảo compiler release và runtime tương ứng.

### 14.2. Chuyển từ javax sang jakarta

Ví dụ:

~~~java
// Ứng dụng thế hệ cũ:
import javax.servlet.http.HttpServletRequest;

// Ứng dụng dùng Jakarta Servlet:
import jakarta.servlet.http.HttpServletRequest;
~~~

Đây là thay đổi hệ sinh thái API: Servlet container, validation, JPA và third-party integrations cũng có thể phải nâng. Spring Boot 4.x có yêu cầu servlet/container cao hơn nhánh 3.x; cần đọc System Requirements của phiên bản đang đích.

### 14.3. Chuyển kiểu cấu hình Security

Hướng cấu hình hiện đại dùng bean **SecurityFilterChain** và lambda DSL. Các tutorial cũ dựa trên **WebSecurityConfigurerAdapter**, một số API cũ hoặc các module OAuth2 legacy không phù hợp để copy nguyên sang Security 6/7.

### 14.4. Khi nâng Boot 3 → 4

Ngoài Spring Security 7, cần xem:

- Starter được thay tên/tách module theo Boot 4.
- Spring Framework 7 và các API thay đổi.
- Migration Jackson 2 → Jackson 3 ở các thành phần liên quan.
- Servlet container Jakarta tương ứng.
- Spring Cloud release train, Spring Data, database drivers, test libraries.
- Thay đổi mặc định trong security, error responses, serialization và observability.

**Lộ trình hợp lý** là giải quyết dependency và deprecated APIs ở phiên bản hiện tại, xem migration guides, nâng major có kiểm soát, rồi kiểm thử từng đường xử lý. Tránh chỉ sửa version trong pom.xml rồi giả định toàn bộ ứng dụng đã tương thích.

## 15. Các lỗi thường gặp khi chọn sai bộ phiên bản

### 15.1. Java runtime thấp hơn bytecode

~~~text
UnsupportedClassVersionError: ... class file version 65.0 ...
~~~

Ứng dụng được build cho Java 21 nhưng JVM chỉ hỗ trợ Java 17. Kiểm **java -version** của runtime, Maven/Gradle toolchain và Docker image. Không sửa bằng cách đổi Spring Security một cách ngẫu nhiên.

### 15.2. Gradle Plugin yêu cầu version mới hơn

~~~text
Spring Boot plugin requires Gradle ... or later
~~~

Gradle wrapper quá cũ so với Boot plugin. Nâng wrapper lên bản trong dải được tài liệu Boot công bố, đồng thời kiểm Gradle hỗ trợ JDK đang dùng.

### 15.3. NoSuchMethodError hoặc NoClassDefFoundError

Có thể xuất hiện khi Spring Framework/Security bị trộn major, một thư viện bên ngoài đưa API cũ, hoặc một module được chọn khác BOM. Hãy phân tích dependency tree/insight để tìm **resolved version**; không coi đây là lỗi JWT trước khi xác định classpath.

### 15.4. Không có JwtDecoder

~~~text
No qualifying bean of type JwtDecoder ...
~~~

Có thể thiếu dependency JOSE, cấu hình issuer/JWKS chưa đủ hoặc custom bean khiến auto-configuration không hoạt động. Xác nhận dự án dùng JWT Resource Server, starter đúng nhánh và properties phù hợp.

### 15.5. Token bị 401 dù ứng dụng khởi động

Một JWT bị 401 có thể do **iss** sai, **aud** không dành cho API, **exp** hết hạn, JWKS không truy cập được, chữ ký không hợp lệ hoặc thuật toán không được chấp nhận. Đây thường là vấn đề **cấu hình trust/token**, không tự động có nghĩa bộ JDK/Boot/Security sai.

### 15.6. Token hợp lệ nhưng trả 403

Người dùng đã được xác thực nhưng thiếu scope/quyền như **SCOPE_orders.read**, hoặc vi phạm tenant/ownership policy. Không giải quyết bằng cách tắt phân quyền. Chọn đúng phiên bản giúp Security chạy được, nhưng **chính sách quyền** vẫn do ứng dụng định nghĩa.

### 15.7. Dependency tên mới không tồn tại trong Boot cũ

**spring-boot-starter-security-oauth2-resource-server** là tên starter hướng tới Boot 4. Dùng tên này với Boot 3.5 không đồng nghĩa Maven sẽ tìm được starter tương ứng. Khi chọn Boot 3, dùng **spring-boot-starter-oauth2-resource-server**.

### 15.8. Mọi thứ build được nhưng production lại lỗi

CI có thể chạy JDK khác container. Đồng thời còn có proxy, TLS, trust store, DNS, issuer metadata và certificates. Ghi rõ các version/build artifacts và kiểm môi trường thực tế thay vì chỉ xác nhận trên laptop.

## 16. Quy trình ra quyết định cho một dự án mới

~~~mermaid
flowchart TD
    A[Định nghĩa vai trò API và ràng buộc hạ tầng] --> B[Chọn nhánh Spring Boot còn hỗ trợ]
    B --> C{JDK dự kiến có trong dải hỗ trợ?}
    C -->|Không| D[Đổi JDK hoặc nhánh Boot]
    C -->|Có| E[Chọn Maven/Gradle Wrapper phù hợp]
    E --> F[Khởi tạo dự án với starter đúng nhánh]
    F --> G[Để BOM quản lý Security/Framework]
    G --> H[Kiểm dependency graph và Java runtime]
    H --> I[Cấu hình issuer, audience, JWT/opaque]
    I --> J[Kiểm đường xác thực và phân quyền]
~~~

Quy trình theo từng bước:

1. **Ghi rõ vai trò**: Resource Server xác minh JWT/opaque hay còn làm OIDC Client, Authorization Server?
2. **Chốt HTTP stack**: Spring MVC/Servlet hay WebFlux/reactive?
3. **Liệt kê ràng buộc JDK**: Java runtime production, base image, CI, IDE, build tools và team policy.
4. **Chọn release Boot**: ưu tiên bản stable được hỗ trợ đáp ứng môi trường, xem lifecycle và các thư viện tích hợp.
5. **Dùng Boot BOM**: tránh trộn Spring Security major hoặc thêm các dependency riêng version.
6. **Chọn starter đúng release**: Boot 3 dùng tên starter cũ, Boot 4 dùng nhóm mới.
7. **Khóa build tool**: commit Wrapper và đặt Java toolchain/compilation target.
8. **Đối chiếu dependency graph**: Security, Framework, JOSE/Jackson, Spring Cloud.
9. **Cấu hình Resource Server**: issuer/JWKS hoặc introspection; kiểm audience và authorization.
10. **Chạy kiểm thử tích hợp cần thiết** trước khi triển khai và khi cập nhật patch/major.

Một bảng quyết định ngắn:

| Trường hợp | Cách chọn |
|---|---|
| Dự án mới, Java 21, các thư viện đã sẵn sàng Boot 4 | Cân nhắc Boot 4.1.x + Security 7.1.x do BOM quản lý |
| Dự án đã dùng Boot 3.5 và cần cập nhật bảo mật trong cùng release line | Dùng patch 3.5 phù hợp, giữ Security 6.5.x do BOM quản lý |
| Dự án dùng Java 11 | Phải nâng JDK nếu muốn Boot 3/4; không giữ Java 11 rồi ép Boot mới |
| Dự án dùng Gradle 7.x | Cần nâng wrapper nếu chọn Boot 4.1; kiểm Java support của Gradle |
| Dự án dùng Spring Cloud | Tra release train tương thích với Boot đang chọn |
| Dự án có dependency Spring Security bị pin riêng | Kiểm lý do pin và dependency tree; ưu tiên đồng bộ theo BOM |

## 17. Những kiểm tra tối thiểu sau khi tạo project

Sau khi một dự án thật được tạo và build, nên xác nhận:

| Tình huống thử | Kết quả mong đợi |
|---|---|
| Build project bằng JDK/toolchain mục tiêu | Build thành công; không có xung đột classpath |
| Khởi động trong runtime/container thật | Không lỗi bytecode, dependency hoặc startup security |
| Gọi API riêng tư không có token | Thường **401 Unauthorized** |
| JWT chữ ký sai, issuer/audience sai hoặc hết hạn | Bị từ chối, thường **401** |
| JWT hợp lệ nhưng thiếu quyền | Bị chặn, thường **403** |
| JWT có quyền loại thao tác nhưng không sở hữu bản ghi | Bị chặn theo owner/tenant policy |
| Đổi patch Boot trong release line đã chọn | Dependency được resolve lại; các kiểm thử liên quan vẫn đạt |
| Nâng major Boot/Security | Migration guide được áp dụng và kiểm thử lại toàn bộ các đường bảo mật |

Những bước này không thay thế secure coding và quản lý secrets, nhưng phát hiện các vấn đề phổ biến do tổ hợp phiên bản hoặc cấu hình Resource Server sai.

## Kết luận

**Spring Boot là điểm neo của bộ phiên bản.** Chọn release Boot phù hợp, sử dụng **JDK** nằm trong dải hỗ trợ của Boot và công cụ build, rồi để BOM quản lý **Spring Framework/Spring Security**. Đối với ví dụ được kiểm chứng ngày 15/11/2026, **Boot 4.1.2** quản lý **Security 7.1.2**; **Boot 3.5.16** quản lý **Security 6.5.11**. Cả hai đều yêu cầu từ **Java 17**, nhưng dải Java/Gradle hỗ trợ và tên starter khác nhau.

Sau khi tạo dự án, kiểm wrapper, JDK runtime, resolved dependencies, issuer/audience và các chính sách quyền của API. Chọn đúng bộ JDK–Boot–Security là **điều kiện nền tảng** để Resource Server xác minh token chính xác; phần bảo vệ dữ liệu vẫn cần các chính sách authorization được thiết kế và kiểm thử riêng.

### Tài liệu tham khảo

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.1 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Migration Guide](https://docs.spring.io/spring-security/reference/migration/)
- [Gradle — Java Compatibility](https://docs.gradle.org/current/userguide/compatibility.html)
- [Spring — Support Policy](https://spring.io/support)
