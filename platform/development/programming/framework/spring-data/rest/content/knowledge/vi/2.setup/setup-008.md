# Tích hợp spring-data-rest-webmvc vào ứng dụng Spring MVC hiện có

Spring Data REST có thể chạy cùng một ứng dụng Spring MVC đã tồn tại. Với ứng dụng Spring MVC cấu hình thủ công, phần tích hợp chính gồm hai việc: thêm module `spring-data-rest-webmvc` vào dependency và import cấu hình `RepositoryRestMvcConfiguration` vào Spring configuration đang phục vụ MVC. Cấu hình này đăng ký các thành phần cần thiết để Spring Data REST nhận request và xuất những Spring Data Repository được phép export thành REST resource.

Sau khi tích hợp, các controller MVC hiện có và các repository resource có thể cùng phục vụ request qua ứng dụng. Điểm cần chú ý nhất là đường dẫn repository được export có thể được Spring Data REST xử lý trước controller của ứng dụng nếu hai bên dùng trùng URL.

Bài này tập trung vào ứng dụng Spring MVC không dùng Spring Boot auto-configuration. Nếu ứng dụng dùng Spring Boot, cách cấu hình khác và được trình bày ở phần riêng bên dưới.

## 1. Spring Data REST hoạt động trong ứng dụng MVC như thế nào?

Spring Data REST được xây dựng trên Spring MVC. Nó bổ sung handler và cơ chế biểu diễn REST resource dựa trên Spring Data Repository. Khi tích hợp vào ứng dụng đã có MVC, Spring Data REST không cần một ứng dụng web riêng hoặc một DispatcherServlet thứ hai.

Luồng tổng quát:

~~~mermaid
flowchart TD
    C["HTTP client"] --> DS["DispatcherServlet hiện có"]
    DS --> RHM["RepositoryRestHandlerMapping"]
    RHM -->|URL thuộc repository đã export| SDR["RepositoryRestController"]
    RHM -->|Không khớp repository| HM["Các HandlerMapping khác"]
    HM --> MVC["Controller MVC hiện có"]
    SDR --> REPO["Spring Data Repository"]
    REPO --> STORE["Store module: JPA, MongoDB, ..."]
    SDR --> RESP["HAL / REST response"]
    MVC --> RESP2["Response của ứng dụng"]
~~~

Spring Data REST đăng ký một `RepositoryRestHandlerMapping` để nhận diện những URL thuộc repository đã export. Nếu đường dẫn tương ứng với một repository resource, request được chuyển đến Spring Data REST. Nếu không có repository phù hợp, handler mapping trả về `null`, để các `HandlerMapping` khác tiếp tục xử lý request.

Vì vậy, hai loại endpoint có thể cùng tồn tại:

- Endpoint do ứng dụng viết bằng `@Controller` hoặc `@RestController`.
- Endpoint collection, item, search và association do Spring Data REST tạo từ repository.

## 2. Kiểm tra ứng dụng Spring MVC hiện có

Trước khi thêm dependency, xác định cấu trúc ứng dụng và nơi khai báo MVC configuration.

Một ứng dụng Spring MVC truyền thống thường đã có:

- Spring Framework và Servlet container như Tomcat hoặc Jetty.
- Một `DispatcherServlet` được đăng ký trong web application.
- MVC configuration bằng Java Config hoặc XML.
- Một hoặc nhiều controller xử lý request.
- Spring Data Repository và module lưu trữ tương ứng, hoặc cấu hình persistence sẽ được bổ sung riêng.

Cần xác định Spring configuration nào đang được nạp trong web application. Spring Data REST configuration phải nằm trong ApplicationContext mà các repository có thể được nhìn thấy.

Trong ứng dụng có root context và DispatcherServlet child context, child context nhìn thấy bean ở parent context. Một cách bố trí thường gặp là repository và service được khai báo trong root context, còn MVC configuration được khai báo trong child context. Khi import `RepositoryRestMvcConfiguration` vào child context, cấu hình đó có thể sử dụng repository ở parent context. Nếu repository nằm trong một context không thể nhìn thấy từ context chứa cấu hình Spring Data REST, endpoint sẽ không được tạo như mong đợi.

Không tạo thêm DispatcherServlet chỉ để phục vụ Spring Data REST. Tích hợp đúng là đưa cấu hình của Spring Data REST vào MVC application context hiện có.

## 3. Thêm dependency spring-data-rest-webmvc

Với ứng dụng Spring MVC không dùng Spring Boot, thêm artifact `spring-data-rest-webmvc` vào compile-time dependency.

### 3.1. Gradle

Nếu dự án đã import Spring Data BOM hoặc có dependency management quản lý phiên bản Spring Data, khai báo các module không cần version riêng:

~~~groovy
dependencies {
    implementation("org.springframework.data:spring-data-rest-webmvc")
    implementation("org.springframework.data:spring-data-jpa")
}
~~~

Trong ví dụ, `spring-data-jpa` chỉ cần khi ứng dụng dùng JPA. Nếu ứng dụng dùng MongoDB, Redis hoặc store khác, thêm module Spring Data tương ứng và cấu hình repository cho store đó.

Nếu dự án chưa có dependency management, import Spring Data Release Train BOM bằng Gradle platform rồi khai báo các module:

~~~groovy
dependencies {
    implementation(platform("org.springframework.data:spring-data-bom:REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN_VERSION"))

    implementation("org.springframework.data:spring-data-rest-webmvc")
    implementation("org.springframework.data:spring-data-jpa")
}
~~~

Thay `REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN_VERSION` bằng release train do dự án lựa chọn. Chọn release train tương thích với phiên bản Spring Framework và các Spring Data module đang dùng. Không tự ghép các phiên bản Spring Data REST, Spring Data Commons, Spring Data JPA và Spring Framework từ những release train khác nhau.

### 3.2. Maven

Với Maven, có thể import Spring Data BOM trong `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo các module cần thiết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-rest-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Thay giá trị placeholder bằng một release train phù hợp với nền tảng hiện tại. Nếu dự án đã có BOM quản lý Spring Data, không cần import thêm BOM thứ hai.

### 3.3. Chọn phiên bản tương thích

Spring Data REST, Spring Data Commons và các module store không nhất thiết có cùng số phiên bản. Spring Data Release Train BOM được cung cấp để quản lý những phiên bản tương thích với nhau.

Khi thêm Spring Data REST vào một ứng dụng Spring MVC cũ, cần kiểm tra cả phiên bản Spring Framework. Không phải cứ chọn Spring Data REST mới nhất là có thể dùng với mọi ứng dụng MVC hiện tại. Nếu dự án đang ở một thế hệ Spring Framework cũ, hãy chọn Spring Data release train hỗ trợ thế hệ đó hoặc nâng cấp nền tảng theo kế hoạch đã kiểm thử.

Không thêm đồng thời `spring-boot-starter-data-rest` và cấu hình thủ công chỉ vì ứng dụng đã có Spring MVC. Starter là lựa chọn cho ứng dụng Spring Boot; ứng dụng MVC thuần có thể dùng trực tiếp `spring-data-rest-webmvc`.

## 4. Import RepositoryRestMvcConfiguration

Đây là bước cấu hình cốt lõi của ứng dụng Spring MVC truyền thống.

Tạo một configuration class hoặc bổ sung `@Import` vào configuration hiện có:

~~~java
package example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.rest.webmvc.RepositoryRestMvcConfiguration;

@Configuration
@Import(RepositoryRestMvcConfiguration.class)
public class SpringDataRestIntegrationConfiguration {
}
~~~

Khi Spring tạo ApplicationContext, `RepositoryRestMvcConfiguration` đăng ký các MVC resource cần thiết để cấu hình `RepositoryRestController` và export các repository mà context đó cùng các parent context nhìn thấy.

Có thể đặt `@Import` trực tiếp trên MVC configuration hiện có:

~~~java
package example.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.rest.webmvc.RepositoryRestMvcConfiguration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@Import(RepositoryRestMvcConfiguration.class)
@ComponentScan(basePackages = "example.web")
public class WebMvcConfiguration implements WebMvcConfigurer {
    // Các cấu hình MVC hiện có của ứng dụng.
}
~~~

Ví dụ thứ hai minh họa một ứng dụng đang dùng Java Config với `@EnableWebMvc`. Nếu ứng dụng đã có MVC configuration, chỉ cần import Spring Data REST vào cấu hình đó hoặc vào một configuration class được nạp cùng context. Không tạo thêm một cấu hình MVC độc lập chỉ để khai báo lại những thành phần đã tồn tại.

### 4.1. Không bật MVC hai lần

`@EnableWebMvc` bật cấu hình Spring MVC. Nếu ứng dụng đã có annotation này hoặc đã cấu hình MVC bằng XML, không cần thêm một lần nữa chỉ vì tích hợp Spring Data REST.

`@Import(RepositoryRestMvcConfiguration.class)` là bước bổ sung cấu hình Spring Data REST. Nó không có nghĩa phải đăng ký thêm DispatcherServlet hoặc thay thế toàn bộ cấu hình controller, view resolver, resource handler và interceptor hiện có.

### 4.2. Trường hợp XML configuration

Ứng dụng cũ có thể khai báo Spring bean bằng XML. Khi đó, cần đăng ký cấu hình Java của Spring Data REST trong ApplicationContext phù hợp, hoặc import configuration theo cơ chế Java Config mà ứng dụng đang sử dụng. Tên class/package cho XML phải khớp với artifact Spring Data REST cụ thể của dự án; không sao chép một FQN từ tài liệu của phiên bản cũ mà chưa kiểm tra dependency đang dùng.

## 5. Đảm bảo Spring Data Repository đã được cấu hình

Import `RepositoryRestMvcConfiguration` không tự tạo repository và không thay thế cấu hình store. Spring Data REST chỉ có thể export các repository đã được Spring Data đăng ký.

Ví dụ với Spring Data JPA:

~~~java
package example.people;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Ứng dụng cần có cấu hình JPA và repository scanning phù hợp. Nếu dự án chưa bật repository scanning, có thể khai báo trong data configuration:

~~~java
package example.config;

import example.people.PersonRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(basePackageClasses = PersonRepository.class)
public class JpaRepositoryConfiguration {
    // EntityManagerFactory và transaction manager của ứng dụng.
}
~~~

Đoạn trên chỉ minh họa việc bật scanning; một ứng dụng JPA thực tế vẫn phải có DataSource, EntityManagerFactory, transaction manager và entity mapping phù hợp. Nếu các thành phần này đã được cấu hình, không khai báo trùng.

Với store khác, dùng annotation scanning và module Spring Data tương ứng. Ví dụ repository MongoDB cần Spring Data MongoDB và cấu hình MongoDB; Spring Data REST không tự tạo kết nối database.

### 5.1. Kiểm soát repository nào được export

Spring Data REST có repository detection strategy để xác định repository nào trở thành REST resource. Strategy mặc định xét các public repository interface và cờ `exported` của annotation. Có thể dùng `@RepositoryRestResource` để khai báo rõ repository cần export:

~~~java
@RepositoryRestResource(path = "people", exported = true)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Để không export một repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalPersonRepository extends JpaRepository<Person, Long> {
}
~~~

Có repository trong Spring context không đồng nghĩa repository đó phải được công khai qua HTTP. Hãy quyết định rõ repository nào thuộc API.

## 6. Tích hợp endpoint Spring MVC và repository resource

Giả sử ứng dụng đã có controller:

~~~java
package example.web;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {

    @GetMapping
    public List<String> getReports() {
        return List.of("daily", "monthly");
    }
}
~~~

Đồng thời, ứng dụng có `PersonRepository` được export với path `people`.

Hai endpoint có thể cùng tồn tại:

| Request | Thành phần xử lý |
|---|---|
| `GET /reports` | `ReportController` của ứng dụng |
| `GET /people` | Spring Data REST |
| `GET /people/{id}` | Spring Data REST |
| `GET /people/search` | Spring Data REST nếu repository có search method được export |

Spring Data REST không biến mọi controller hiện có thành repository endpoint. Controller vẫn chạy theo mapping của Spring MVC; repository resource được xử lý bởi cơ chế handler riêng của Spring Data REST.

### 6.1. RepositoryRestHandlerMapping và xung đột URL

Đây là chi tiết quan trọng nhất khi tích hợp vào ứng dụng đang có nhiều controller.

Spring Data REST đăng ký `RepositoryRestHandlerMapping`. Handler mapping này kiểm tra URL có tương ứng với repository đã export hay không:

- Nếu repository được export dưới path `people`, request bắt đầu bằng `/people` được chuyển cho Spring Data REST.
- Nếu không có repository được export dưới path tương ứng, handler mapping trả về `null`, để handler mapping khác của ứng dụng thử xử lý.
- Nếu controller hiện có cũng khai báo `/people`, route đó có thể bị Spring Data REST nhận trước. Controller của ứng dụng sẽ không xử lý request vốn thuộc repository resource.

Ví dụ, nếu có:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

thì không nên đồng thời khai báo controller nghiệp vụ dùng chung path `/people` với ý định ghi đè endpoint collection/item do repository cung cấp.

Cách xử lý:

1. Đặt repository resource và controller nghiệp vụ ở các path khác nhau, ví dụ `/people` và `/people-management`.
2. Đổi path export bằng `@RepositoryRestResource(path = "...")` nếu cần.
3. Đặt `exported = false` cho repository hoặc method nếu không muốn công khai endpoint đó.
4. Nếu cần custom handler nằm trong API namespace và dùng cấu hình response của Spring Data REST, cân nhắc `@RepositoryRestController`. Nếu cần một controller riêng dưới base path nhưng không gắn với repository resource cụ thể, cân nhắc `@BasePathAwareController`.

Controller gắn `@RepositoryRestController` hoặc `@BasePathAwareController` có thể sử dụng các quy tắc phù hợp của Spring Data REST như base path và cơ chế xử lý response. Một `@RestController` thông thường vẫn thuộc luồng Spring MVC của ứng dụng.

Không tự đăng ký thêm `RepositoryRestHandlerMapping` nếu đã import `RepositoryRestMvcConfiguration`. Cấu hình được import đã tạo handler mapping cần thiết.

## 7. Tùy chỉnh base path và cấu hình REST

Mặc định, Spring Data REST phục vụ resource từ root path. Có thể đổi base path để tách API repository khỏi các endpoint MVC hiện có.

Với ứng dụng không dùng Spring Boot, đăng ký `RepositoryRestConfigurer`:

~~~java
package example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestSettings {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return new RepositoryRestConfigurer() {
            @Override
            public void configureRepositoryRestConfiguration(
                    RepositoryRestConfiguration config,
                    CorsRegistry cors) {
                config.setBasePath("/api/data");
            }
        };
    }
}
~~~

Với cấu hình trên, repository `people` được truy cập qua `/api/data/people`. Base path được áp dụng cho các REST resource do Spring Data REST quản lý.

`RepositoryRestConfigurer` còn cung cấp các điểm tùy chỉnh khác như repository detection, page size, media type và CORS. Chỉ override các phương thức phù hợp với yêu cầu của ứng dụng.

Nếu ứng dụng dùng Spring Boot, base path có thể cấu hình bằng property `spring.data.rest.basePath`. Với MVC thuần, dùng `RepositoryRestConfigurer` bean như ví dụ.

## 8. Kiểm tra sau khi tích hợp

Sau khi thêm dependency, import configuration và xác nhận repository đã được scan, khởi động lại ứng dụng trên Servlet container như bình thường.

Giả sử:

- `PersonRepository` export với path `people`.
- Spring Data REST base path là `/api/data`.
- Ứng dụng đang chạy tại `http://localhost:8080`.

Gọi collection endpoint:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/data/people
~~~

Nếu repository đã được nhận diện, response thường là HAL JSON. Khi chưa có dữ liệu, collection vẫn có thể trả về response hợp lệ với danh sách rỗng và các link resource.

Kiểm tra endpoint MVC hiện có:

~~~bash
curl -i http://localhost:8080/reports
~~~

Hai request trên giúp xác nhận Spring Data REST đã được thêm vào và controller cũ vẫn được xử lý qua MVC.

Có thể kiểm tra search resource nếu repository khai báo query method được export. Ví dụ:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {
    List<Person> findByNameContainingIgnoreCase(String name);
}
~~~

Khi method search được export, Spring Data REST cung cấp link search trong resource metadata. Client nên khám phá link đó hoặc dùng đúng path/parameter được cấu hình cho repository.

## 9. CORS, security và dữ liệu được export

Spring Data REST tạo HTTP endpoint từ repository, vì vậy việc thêm module này có thể làm xuất hiện các thao tác đọc và ghi mới. Hãy xem xét những điểm sau trước khi triển khai:

- Kiểm tra repository nào được export và những CRUD/search method nào có thể gọi.
- Cấu hình Spring Security để bảo vệ các URL repository, bao gồm collection, item, search và association.
- Không giả định CORS configuration đang áp dụng cho controller MVC sẽ tự động đáp ứng chính sách của Spring Data REST. Cấu hình CORS của repository REST thông qua `RepositoryRestConfigurer` và kiểm tra bằng request thực tế.
- Không export entity chứa trường nội bộ hoặc dữ liệu nhạy cảm nếu representation chưa được kiểm soát. Dùng projection/DTO phù hợp và authorization cho thao tác tương ứng.
- Kiểm tra đường dẫn API sau khi đặt base path để bảo đảm các rule bảo mật và reverse proxy vẫn khớp.

Ẩn một repository hoặc method khỏi REST API là một phần của thiết kế API; nó không thay thế authorization. Client vẫn phải được xác thực và phân quyền ở server.

## 10. Lỗi thường gặp khi tích hợp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Repository endpoint trả 404 | Repository chưa được scan, không được export hoặc không nhìn thấy từ ApplicationContext chứa cấu hình Spring Data REST | Kiểm tra store configuration, detection strategy và context hierarchy |
| Controller cũ không nhận request | Path của controller trùng path repository đã export | Kiểm tra `@RepositoryRestResource(path = "...")` và mapping controller |
| Ứng dụng không khởi động do lỗi class/method | Phiên bản Spring Data REST, Spring Data Commons hoặc Spring Framework không tương thích | Kiểm tra dependency tree và Spring Data BOM |
| Không có repository resource dù đã import configuration | Repository nằm trong context không được cấu hình Spring Data REST nhìn thấy | Đặt repository trong cùng context hoặc parent context phù hợp |
| API trả 406 hoặc 415 | Accept/Content-Type không phù hợp hoặc message converter cấu hình chưa đúng | Gửi `Accept: application/hal+json` và `Content-Type: application/json` khi gửi JSON |
| Request bị từ chối bởi security | Security matcher chưa bao phủ path mới của repository REST | Kiểm tra rule cho base path, collection, item và search |
| Browser báo lỗi CORS | Chính sách CORS cho Spring Data REST chưa được cấu hình tương ứng | Kiểm tra `RepositoryRestConfigurer` và response preflight |

Khi debug, hãy kiểm tra theo thứ tự: dependency và version alignment, ApplicationContext, repository scanning/export, URL mapping, rồi mới đến media type, CORS và security. Cách này giúp xác định lỗi nằm ở bước tích hợp nào.

## 11. Trường hợp Spring Boot

Nếu ứng dụng thực tế sử dụng Spring Boot, thông thường không cần import `RepositoryRestMvcConfiguration` thủ công. Thêm starter:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
}
~~~

Spring Boot auto-configuration sẽ cấu hình Spring Data REST khi ứng dụng bật auto-configuration. Tiếp tục khai báo repository và module store cần dùng; cấu hình tùy chỉnh có thể được cung cấp bằng bean `RepositoryRestConfigurer`.

Không áp dụng đồng thời hai cách bootstrap nếu không có lý do cụ thể. Khi đã dùng Boot starter và auto-configuration, hãy để Boot quản lý việc tích hợp MVC.

## 12. Quy trình tích hợp thực tế

Có thể thực hiện theo trình tự sau:

1. Xác định phiên bản Spring Framework và Spring Data hiện tại.
2. Chọn Spring Data Release Train BOM tương thích; thêm `spring-data-rest-webmvc` và module store tương ứng.
3. Xác nhận Spring Data Repository đã được scan và store configuration hoạt động.
4. Import `RepositoryRestMvcConfiguration` vào MVC ApplicationContext đang phục vụ ứng dụng.
5. Chọn repository được export bằng annotation hoặc detection strategy.
6. Kiểm tra path repository có xung đột với controller hiện có hay không.
7. Cấu hình base path, CORS và các tùy chỉnh cần thiết qua `RepositoryRestConfigurer`.
8. Kiểm thử repository endpoint và controller endpoint hiện tại.
9. Rà soát security và dữ liệu được phép công khai trước khi triển khai.

## 13. Ghi nhớ

- `spring-data-rest-webmvc` là module triển khai Spring Data REST trên Spring MVC.
- `RepositoryRestMvcConfiguration` là cấu hình Java cần import khi tích hợp thủ công vào MVC application.
- Không cần thêm DispatcherServlet thứ hai.
- Repository phải được Spring Data đăng ký và phải nằm trong ApplicationContext mà Spring Data REST nhìn thấy.
- `RepositoryRestHandlerMapping` định tuyến request đến repository đã export; path trùng với repository có thể khiến controller hiện có không nhận request.
- Dùng `RepositoryRestConfigurer` để cấu hình base path và các tùy chỉnh REST.
- Với Spring Boot, starter và auto-configuration thường đã thực hiện các bước bootstrap này.

## 14. Tài liệu chính thức

- Spring Data REST — Getting Started: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
- Spring Data REST — Adding Spring Data REST to an Existing Spring MVC Application: https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html
- Spring Data REST — Dependencies và Release Train BOM: https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html
- Spring Data REST — Project overview: https://spring.io/projects/spring-data-rest/
