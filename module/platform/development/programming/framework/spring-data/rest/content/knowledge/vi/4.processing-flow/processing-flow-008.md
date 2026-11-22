# Quan hệ giữa cấu hình Spring MVC thông thường và hạ tầng riêng của Spring Data REST

## Mục tiêu

Spring Data REST xuất bản các Spring Data Repository thành tài nguyên REST. Nó chạy trên nền Spring MVC và dùng cùng vòng đời xử lý HTTP của ứng dụng, nhưng tự đăng ký thêm các thành phần chuyên biệt để nhận diện repository, định tuyến request, gọi repository, tạo representation có liên kết và xử lý các quy tắc REST riêng.

Khi cấu hình ứng dụng, cần phân biệt hai phạm vi:

- **Spring MVC thông thường** điều khiển các controller do ứng dụng viết, chẳng hạn `@Controller`, `@RestController`, các route `@RequestMapping`, interceptor, resource handler và cấu hình web chung.
- **Spring Data REST** điều khiển cách repository được xuất bản thành REST resource, base path, tên resource, phân trang, sorting, media type, liên kết, validation và các hook trong vòng đời ghi dữ liệu.

Hai phạm vi phối hợp trong cùng web application. Cấu hình MVC thông thường vẫn quan trọng, nhưng không nên giả định mọi thiết lập dành cho controller MVC đều tự động thay thế cấu hình chuyên biệt của Spring Data REST.

## 1. Mô hình kiến trúc: cùng Spring MVC, thêm một nhánh xử lý repository

Spring Data REST không khởi tạo một HTTP server hoặc một DispatcherServlet độc lập. Request vẫn đi qua servlet container và DispatcherServlet của Spring MVC. Điểm khác biệt nằm ở các HandlerMapping, handler, adapter, argument resolver, message converter và thành phần xuất bản repository mà Spring Data REST đăng ký vào ApplicationContext.

Có thể hình dung luồng tổng quát như sau:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Servlet container]
    B --> C[DispatcherServlet]
    C --> D{Các HandlerMapping}
    D -->|Route @RequestMapping thông thường| E[Controller / RestController]
    D -->|Đường dẫn repository đã export| F[Spring Data REST HandlerMapping]
    F --> G[Repository REST controller và HandlerAdapter]
    G --> H[RepositoryInvoker]
    H --> I[Spring Data Repository]
    I --> J[Store module: JPA, MongoDB, JDBC, ...]
    E --> K[Spring MVC response handling]
    J --> L[REST representation và links]
    K --> M[HTTP response]
    L --> M
~~~

Các thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `DispatcherServlet` | Nhận request và điều phối tới handler phù hợp. Đây là điểm vào chung của Spring MVC. |
| `HandlerMapping` | Tìm handler cho URL và HTTP request. Spring MVC có mapping cho controller annotation; Spring Data REST bổ sung mapping dành cho repository resource. |
| `HandlerAdapter` | Gọi handler đã được chọn. Spring Data REST cấu hình adapter có thể xử lý các controller và argument resolver chuyên biệt của exporter. |
| `RepositoryResourceMappings` | Xác định repository nào được export và resource path tương ứng. |
| `RepositoryInvoker` | Gọi các thao tác trên repository theo metadata của resource. |
| `RepositoryRestConfiguration` | Lưu cấu hình riêng của REST exporter, như base path, chiến lược phát hiện repository và các tùy chọn biểu diễn. |
| `HttpMessageConverter` | Đọc request body và ghi response body. Spring Data REST cấu hình converter phù hợp với JSON, HAL và các dạng biểu diễn mà exporter hỗ trợ. |
| `RepositoryRestConfigurer` | Điểm mở rộng để ứng dụng tùy chỉnh cấu hình của Spring Data REST. |

Tên một số implementation nội bộ có thể khác giữa các phiên bản. Tài liệu tích hợp mô tả mapping chuyên biệt là `RepositoryRestHandlerMapping`; API của các phiên bản mới có thể bọc việc định tuyến qua `DelegatingHandlerMapping`. Điều cần nắm là exporter có một nhánh HandlerMapping riêng để nhận diện các đường dẫn repository.

## 2. Request được phân luồng như thế nào?

Giả sử ứng dụng có:

- Một controller thông thường xử lý `GET /health`.
- Một repository được export với resource path là `people`.
- Spring Data REST có base path là `/api`.

Các request được xử lý theo mục đích:

| Request | Handler dự kiến | Lý do |
|---|---|---|
| `GET /health` | Controller MVC thông thường | Đây là route do ứng dụng khai báo bằng `@GetMapping` hoặc `@RequestMapping`. |
| `GET /api/people` | Spring Data REST | Đây là collection resource của repository đã export. |
| `GET /api/people/42` | Spring Data REST | Đây là item resource của repository đó. |
| `GET /reports/daily` | Controller MVC thông thường | Đường dẫn không thuộc resource path của repository được export. |

DispatcherServlet hỏi các HandlerMapping để tìm handler. Mapping của Spring Data REST kiểm tra URL có tương ứng với repository resource được export hay không. Nếu không khớp, mapping đó để các HandlerMapping khác tiếp tục xử lý. Nếu khớp, request được chuyển tới controller của Spring Data REST.

Vì vậy, **đường dẫn của repository có thể chiếm một vùng URL mà controller MVC thông thường đang muốn sử dụng**. Nếu repository export thành `people`, một controller khác cũng khai báo route trùng vùng `/api/people/**` có thể không nhận được request như dự kiến. Cách giải quyết tốt nhất là thiết kế URL không trùng nhau và xác định rõ route nào thuộc repository exporter, route nào thuộc controller nghiệp vụ.

Không nên chỉnh thứ tự HandlerMapping theo phỏng đoán để xử lý xung đột. Trước tiên hãy kiểm tra resource path thực tế, base path, repository detection strategy và mapping mà phiên bản đang dùng đăng ký.

## 3. Hai hệ cấu hình có trách nhiệm khác nhau

### Cấu hình Spring MVC thông thường

Các thiết lập này phục vụ web layer của ứng dụng, đặc biệt là controller do nhóm phát triển tự viết. Điểm mở rộng quen thuộc là `WebMvcConfigurer`.

Ví dụ các trách nhiệm thường thuộc MVC:

- Đăng ký interceptor cho controller MVC.
- Cấu hình resource handler để phục vụ static resource.
- Đăng ký formatter và converter cho dữ liệu đầu vào của controller.
- Cấu hình CORS cho các route MVC thông thường.
- Điều chỉnh content negotiation hoặc các thành phần MVC dùng chung.
- Đăng ký controller bằng `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`.

Ví dụ:

~~~java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RequestLoggingInterceptor())
                .addPathPatterns("/health", "/reports/**");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/reports/**")
                .allowedMethods("GET");
    }
}
~~~

Đây là ví dụ minh họa phạm vi cấu hình MVC của ứng dụng. Nếu muốn một quy tắc áp dụng cho endpoint Spring Data REST, hãy kiểm tra extension point của exporter tương ứng thay vì suy ra rằng mọi callback của MVC đều được áp dụng giống nhau.

### Cấu hình Spring Data REST

Spring Data REST có cấu hình riêng thông qua:

- `RepositoryRestConfiguration`: các tùy chọn của exporter.
- `RepositoryRestConfigurer`: callback để thay đổi cấu hình exporter và một số thành phần hỗ trợ.
- Các thuộc tính Spring Boot trong namespace `spring.data.rest.*`.

Những cấu hình thường gặp:

- Base path, ví dụ `/api`.
- Repository detection strategy: repository nào được phép xuất bản thành REST resource.
- Tên và đường dẫn collection resource.
- Kích thước trang mặc định, giới hạn trang, tên query parameter cho page và sort.
- Media type mặc định và hành vi trả response body khi create/update.
- CORS cho REST resource.
- ConversionService, HttpMessageConverter và Jackson mapper của exporter.
- Validation listener và exception resolver liên quan đến Spring Data REST.

Ví dụ, thay đổi base path trong Spring Boot:

~~~properties
spring.data.rest.base-path=/api
spring.data.rest.default-page-size=20
spring.data.rest.max-page-size=100
~~~

Các thuộc tính trên thuộc namespace của Spring Data REST. Chúng khác với cấu hình Spring Data Web thông thường như `spring.data.web.*`.

## 4. Spring Boot và ứng dụng Spring MVC không dùng Boot

### Khi dùng Spring Boot

Cách thông thường là thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
~~~

Hoặc với Gradle:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-data-rest")
~~~

Khi ứng dụng được bật bằng `@SpringBootApplication` hoặc `@EnableAutoConfiguration`, Spring Boot tự động cấu hình Spring Data REST. Không cần import thủ công `RepositoryRestMvcConfiguration` thêm lần nữa.

Để tùy chỉnh exporter, đăng ký một bean `RepositoryRestConfigurer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
class DataRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config ->
                config.setBasePath("/api"));
    }
}
~~~

Ví dụ trên dùng API tiện ích `RepositoryRestConfigurer.withConfig`. Nếu phiên bản Spring Data REST của dự án không cung cấp API tiện ích này, triển khai interface và override phương thức cấu hình tương ứng của phiên bản đang dùng.

### Khi tích hợp vào ứng dụng Spring MVC không dùng Boot

Ứng dụng cần dependency `spring-data-rest-webmvc` tương thích với phiên bản Spring Data đang dùng. Sau đó import cấu hình MVC của Spring Data REST vào cấu hình ứng dụng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.rest.webmvc.config.RepositoryRestMvcConfiguration;

@Configuration
@Import(RepositoryRestMvcConfiguration.class)
class WebConfiguration {
}
~~~

`RepositoryRestMvcConfiguration` bootstrap các thành phần MVC cần thiết để export repository trong ApplicationContext. Ứng dụng cũng phải cấu hình Spring Data repository và module lưu trữ tương ứng, ví dụ Spring Data JPA hoặc Spring Data MongoDB.

Không nên vừa dựa vào auto-configuration của Spring Boot vừa import lại cấu hình exporter theo cách thủ công nếu không có lý do rõ ràng. Cấu hình trùng có thể khiến việc khởi tạo bean và hành vi MVC khó dự đoán.

## 5. Ví dụ: repository resource chạy cạnh controller MVC

Repository có thể được export như sau:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Với base path `/api`, Spring Data REST tạo các endpoint resource theo metadata repository, chẳng hạn:

- `GET /api/people`: lấy collection.
- `GET /api/people/42`: lấy một item.
- `POST /api/people`: tạo item nếu thao tác được export và được phép.
- `PUT` hoặc `PATCH /api/people/42`: cập nhật item nếu được export và được phép.
- `DELETE /api/people/42`: xóa item nếu được export và được phép.

Các thao tác thực tế còn phụ thuộc repository, cấu hình export, phương thức bị ẩn và quyền truy cập. Không nên xem danh sách trên là cam kết rằng mọi endpoint ghi đều luôn mở.

Một controller MVC thông thường vẫn có thể tồn tại cạnh repository:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class HealthController {

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "UP");
    }
}
~~~

Ở đây:

- `/health` do Spring MVC thông thường xử lý.
- `/api/people` do Spring Data REST xử lý.
- Cả hai cùng chạy trong một web application và đi qua DispatcherServlet.

Spring Data REST gọi repository trực tiếp thông qua abstraction của Spring Data. Nó không tự động gọi service nghiệp vụ của ứng dụng chỉ vì ứng dụng có service bean. Nếu một thao tác cần quy trình nghiệp vụ nhiều bước, kiểm tra quyền theo nghiệp vụ, điều phối nhiều aggregate hoặc side effect đặc thù, hãy cân nhắc tạo endpoint bằng controller và gọi service tương ứng thay vì export trực tiếp thao tác repository.

## 6. Chọn annotation cho controller tùy biến

Có ba trường hợp thường bị nhầm:

| Annotation | Khi nào dùng | Hành vi chính |
|---|---|---|
| `@RestController` / `@Controller` | Endpoint thuộc web layer thông thường của ứng dụng. | Được xử lý theo cấu hình Spring MVC thông thường; không tự động nằm trong phạm vi cấu hình và xử lý riêng của Spring Data REST. |
| `@RepositoryRestController` | Endpoint tùy biến gắn với vùng URI và tài nguyên của repository exporter. | Được phục vụ dưới base path của Spring Data REST và có thể dùng cấu hình, message converter, exception handling cùng một số hành vi đặc thù của exporter. |
| `@BasePathAwareController` | Endpoint tùy biến cần nằm dưới base path của Spring Data REST nhưng không phải thao tác cụ thể trên một entity resource. | Phù hợp cho các thao tác hoặc tài nguyên tùy biến bên trong vùng API của Spring Data REST. |

Ví dụ một custom endpoint nằm trong vùng repository REST:

~~~java
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.http.ResponseEntity;

@RepositoryRestController
class ScannerController {

    @GetMapping("/scanners/search/producers")
    ResponseEntity<?> getProducers() {
        // Gọi service hoặc repository và tạo representation phù hợp.
        return ResponseEntity.ok().build();
    }
}
~~~

Với base path là `/api`, đường dẫn đầy đủ của ví dụ là `/api/scanners/search/producers`.

Dùng `@RepositoryRestController` khi cần endpoint tùy biến hòa vào cơ chế REST của repository. Tài liệu Spring Data REST mô tả thêm các hành vi như áp dụng CORS theo repository tương ứng và interceptor hỗ trợ truy cập thuộc tính lazy khi dùng JPA.

Nếu chỉ cần một endpoint ứng dụng độc lập, `@RestController` thường là lựa chọn phù hợp hơn. Việc dùng annotation đặc thù nên xuất phát từ nhu cầu tích hợp với exporter, không phải chỉ vì endpoint trả JSON.

## 7. Các concern dùng chung và các concern cần cấu hình riêng

| Concern | Spring MVC thông thường | Spring Data REST |
|---|---|---|
| Điểm vào HTTP | Dùng DispatcherServlet của ứng dụng. | Cũng dùng DispatcherServlet đó. |
| Định tuyến | Mapping cho controller annotation và các handler MVC khác. | Bổ sung mapping nhận diện repository resource đã export. |
| Controller | `@Controller`, `@RestController`. | Controller exporter có sẵn và controller tùy biến mang annotation phù hợp. |
| JSON và response body | Cấu hình message converter của MVC. | Có converter và representation dành cho JSON, HAL, URI list; tùy chỉnh qua `RepositoryRestConfigurer` khi cần. |
| Base path | Thường đến từ context path, servlet path hoặc mapping của ứng dụng. | Dùng `RepositoryRestConfiguration` hoặc `spring.data.rest.base-path`. |
| CORS | Cấu hình MVC như `WebMvcConfigurer#addCorsMappings`. | Cấu hình CORS trong phạm vi REST exporter, ví dụ callback `RepositoryRestConfigurer`. |
| Validation | Validation của request/controller và Bean Validation theo cấu hình MVC. | Có repository event validation listener và các hook trước/sau thao tác repository. |
| Exception | Các resolver và advice của MVC. | Có exception handling của exporter; `RepositoryRestConfigurer` cung cấp callback để tùy chỉnh resolver liên quan. |
| Security | Servlet filter chain, chẳng hạn Spring Security. | Cùng filter chain đó bảo vệ endpoint repository; vẫn phải cấu hình quyền cho các route và thao tác ghi. |
| Phân trang và sorting | Có thể dùng hỗ trợ Spring Data Web như `Pageable` và `Sort` trong controller. | Có quy ước query parameter và page size riêng của REST exporter, có thể cấu hình qua `spring.data.rest.*`. |

Một số hạ tầng nằm ngoài DispatcherServlet, đặc biệt servlet filter và Spring Security filter chain, áp dụng trước khi request được chuyển vào MVC nên có thể bảo vệ cả hai nhóm endpoint. Ngược lại, interceptor gắn vào một HandlerMapping, converter hoặc exception resolver thuộc một cấu hình cụ thể không nên mặc định là áp dụng đồng nhất cho tất cả handler.

## 8. Phân biệt Spring Data Web với Spring Data REST

Hai khái niệm có liên quan nhưng không thay thế nhau:

- **Spring Data Web support** giúp controller MVC nhận các kiểu như `Pageable`, `Sort` hoặc chuyển đổi identifier thành domain object thông qua các thành phần hỗ trợ web.
- **Spring Data REST** export repository thành REST resource và cung cấp một REST API có resource mapping, representation, links, metadata và các hành vi repository.

Vì thế, bật `@EnableSpringDataWebSupport` không đồng nghĩa với việc repository đã được export thành REST endpoint. Tương tự, chỉnh `spring.data.web.*` không thay cho việc cấu hình `spring.data.rest.*`.

## 9. CORS, exception, converter và security

### CORS

Nếu endpoint MVC hoạt động nhưng endpoint repository bị lỗi preflight hoặc bị trình duyệt chặn, hãy kiểm tra cấu hình CORS của Spring Data REST. Có thể cấu hình qua `RepositoryRestConfigurer` và tham số `CorsRegistry` của callback cấu hình exporter. Nếu cần CORS cho controller thông thường, cấu hình MVC tương ứng vẫn có vai trò riêng.

### Message converter và representation

Spring Data REST hỗ trợ các representation như HAL và JSON, đồng thời tạo liên kết giữa collection, item và association. Khi client gửi `Accept` hoặc `Content-Type`, media type và converter tham gia quyết định cách đọc request cũng như ghi response.

Nếu cần thêm converter hoặc tùy chỉnh Jackson cho repository REST, dùng các callback của `RepositoryRestConfigurer`, chẳng hạn:

- `configureHttpMessageConverters(...)`
- `configureJacksonObjectMapper(...)`
- `configureConversionService(...)`

Khi thêm converter, cần giữ lại các converter mặc định mà exporter cần. Thay thế toàn bộ danh sách mà không kiểm tra có thể làm hỏng khả năng đọc/ghi HAL hoặc các media type đặc thù.

### Exception handling

Lỗi từ repository exporter có thể đi qua exception resolver được cấu hình cho Spring Data REST. Nếu một exception được xử lý khác nhau giữa controller MVC và repository endpoint, hãy kiểm tra handler, resolver và annotation controller đang dùng. `RepositoryRestConfigurer` có callback `configureExceptionHandlerExceptionResolver(...)` để mở rộng resolver của exporter.

### Security

Export repository có thể làm lộ các thao tác đọc và ghi mà repository hỗ trợ. Spring Data REST không thay thế authorization của ứng dụng. Cần:

- Dùng Spring Security để bảo vệ URL và HTTP method phù hợp.
- Chỉ export repository thực sự cần công khai.
- Dùng repository detection strategy và thuộc tính `exported` để kiểm soát resource hoặc method nào được xuất bản.
- Kiểm tra quyền trên từng thao tác, đặc biệt create, update và delete.
- Không dựa vào việc ẩn một link trong HAL như cơ chế bảo mật.

Nếu nghiệp vụ cần quyết định quyền dựa trên trạng thái aggregate hoặc quan hệ giữa nhiều đối tượng, hãy đặt kiểm tra ở service/security layer phù hợp và kiểm thử bằng request thật tới endpoint.

## 10. Những nhầm lẫn thường gặp

1. **Đổi `spring.mvc.*` nhưng base path repository không đổi.** Base path của exporter thuộc `spring.data.rest.base-path` hoặc `RepositoryRestConfiguration.setBasePath(...)`.
2. **Bật `@EnableSpringDataWebSupport` nhưng không thấy endpoint repository.** Annotation đó cung cấp web support cho Spring Data, không tự export repository.
3. **Controller tùy biến không nhận request.** Kiểm tra xem đường dẫn có trùng resource path của repository đã export hay không.
4. **Dùng `@RestController` nhưng mong có base path, HAL converter hoặc exception handling của exporter.** Dùng `@RepositoryRestController` hoặc `@BasePathAwareController` nếu endpoint thực sự cần tích hợp với Spring Data REST.
5. **Thêm converter rồi làm mất HAL.** Kiểm tra cách thêm converter và giữ lại các converter mặc định cần thiết.
6. **Endpoint repository hoạt động nhưng ghi dữ liệu không được bảo vệ.** Export resource không tự đảm bảo authorization; cần cấu hình Spring Security và kiểm soát export.
7. **Import cấu hình exporter thủ công trong Spring Boot mà không cần thiết.** Starter và auto-configuration đã đảm nhiệm việc đăng ký; chỉ thêm cấu hình thủ công khi kiến trúc ứng dụng thực sự yêu cầu.
8. **Cho rằng service layer sẽ tự chạy khi repository được export.** Spring Data REST làm việc với repository abstraction; business workflow của service không tự động được gọi.

## 11. Checklist chẩn đoán khi endpoint không hoạt động

Khi `GET /api/people` trả về 404 hoặc đi nhầm controller, kiểm tra theo thứ tự:

1. Dependency `spring-boot-starter-data-rest` hoặc `spring-data-rest-webmvc` đã có và tương thích với Spring Boot/Spring Data release train chưa?
2. Ứng dụng có auto-configuration của Spring Boot không? Nếu không dùng Boot, `RepositoryRestMvcConfiguration` đã được import vào đúng ApplicationContext chưa?
3. Repository có được scan và tạo bean trong ApplicationContext không?
4. Repository có được export theo detection strategy hiện tại không? Có annotation hoặc thuộc tính `exported=false` nào đang ẩn nó không?
5. Base path thực tế là gì? Resource path được tạo từ repository là gì?
6. Có controller MVC nào khai báo URL trùng vùng resource của repository không?
7. Request có đi qua Spring Security không? Có bị từ chối trước khi tới DispatcherServlet không?
8. Client gửi `Accept` và `Content-Type` nào? Converter của exporter có hỗ trợ media type đó không?
9. Nếu chỉ lỗi preflight, đã cấu hình CORS cho đúng phạm vi endpoint chưa?

Khi debug, nên quan sát mapping được đăng ký lúc ứng dụng khởi động và kiểm tra URL thực tế. Không nên thay đổi thứ tự HandlerMapping hoặc thêm cấu hình MVC diện rộng trước khi xác định request đang được mapping nào nhận.

## 12. Nguyên tắc chọn cách triển khai

- Dùng Spring Data REST khi resource có thể biểu diễn tự nhiên từ repository và các thao tác CRUD tiêu chuẩn đáp ứng nhu cầu.
- Dùng controller MVC thông thường gọi service khi endpoint đại diện cho một use case hoặc workflow nghiệp vụ.
- Dùng `@RepositoryRestController` khi endpoint tùy biến cần hòa vào base path, representation, CORS hoặc exception handling của Spring Data REST.
- Giữ URL của repository resource và URL của controller nghiệp vụ tách biệt.
- Đặt cấu hình đúng phạm vi: `WebMvcConfigurer` cho MVC của ứng dụng, `RepositoryRestConfigurer` cho exporter.
- Quản lý phiên bản Spring Boot, Spring Data Commons và Spring Data REST theo release train tương thích; không tự nâng riêng một module Spring Data nếu chưa kiểm tra ma trận tương thích.

## Tóm tắt

Spring Data REST là một phần mở rộng của Spring MVC. DispatcherServlet và web application vẫn là nền tảng chung; Spring Data REST bổ sung một nhánh định tuyến và xử lý chuyên biệt để biến repository thành REST resource. Vì vậy, cấu hình MVC thông thường và cấu hình Spring Data REST có thể cùng tồn tại nhưng có phạm vi trách nhiệm riêng.

Khi một thiết lập không ảnh hưởng đến repository endpoint như mong đợi, hãy xác định request thuộc HandlerMapping nào và điều chỉnh đúng extension point: `WebMvcConfigurer` cho controller MVC, `RepositoryRestConfigurer` và `RepositoryRestConfiguration` cho repository exporter.

## Tài liệu tham khảo

- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Adding Spring Data REST to an Existing Spring MVC Application](https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html)
- [Overriding Spring Data REST Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Framework — Special Bean Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html)
