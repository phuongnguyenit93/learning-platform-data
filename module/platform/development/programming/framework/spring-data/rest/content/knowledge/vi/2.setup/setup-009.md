# Cấu hình spring.data.rest.* và RepositoryRestConfigurer

Spring Data REST tự động export các Spring Data repository thành REST resource. Khi ứng dụng cần đổi đường dẫn gốc, giới hạn kích thước trang, tên query parameter, kiểu media mặc định hoặc chính sách export repository, ta có hai điểm cấu hình chính:

- Các thuộc tính **spring.data.rest.*** trong **application.properties** hoặc **application.yml** phù hợp với thiết lập tĩnh, khai báo được theo môi trường.
- **RepositoryRestConfigurer** phù hợp khi cần cấu hình bằng Java, áp dụng quy tắc có điều kiện, kiểm soát HTTP method, CORS, converter hoặc validator.

Spring Boot tự cấu hình Spring Data REST khi ứng dụng có **spring-boot-starter-data-rest** và dùng **@SpringBootApplication** hoặc **@EnableAutoConfiguration**. Không cần tự import **RepositoryRestMvcConfiguration** trong ứng dụng Spring Boot thông thường. Để tùy chỉnh, đăng ký một bean triển khai **RepositoryRestConfigurer**.

## 1. Các thuộc tính spring.data.rest.*

Spring Boot bind các thuộc tính có tiền tố **spring.data.rest** vào cấu hình Spring Data REST. Dùng dạng kebab-case trong file cấu hình.

Ví dụ **src/main/resources/application.properties**:

```properties
spring.data.rest.base-path=/api
spring.data.rest.default-page-size=25
spring.data.rest.max-page-size=100
spring.data.rest.page-param-name=p
spring.data.rest.limit-param-name=limit
spring.data.rest.sort-param-name=sort
spring.data.rest.default-media-type=application/hal+json
spring.data.rest.return-body-on-create=true
spring.data.rest.return-body-on-update=true
spring.data.rest.detection-strategy=annotated
spring.data.rest.enable-enum-translation=false
```

Với cấu hình trên, các repository resource được đặt dưới tiền tố **/api**. Ví dụ collection **/books** trở thành **/api/books**. Các tham số phân trang được đổi thành **p** (số trang), **limit** (số phần tử tối đa) và **sort** (sắp xếp).

### Ý nghĩa từng thuộc tính

| Thuộc tính | Tác dụng |
|---|---|
| **base-path** | Tiền tố URL cho các repository resource, ví dụ **/api** |
| **default-page-size** | Số phần tử mặc định khi client không chỉ định kích thước trang |
| **max-page-size** | Giới hạn trên của số phần tử trong một trang; request vượt mức bị giới hạn |
| **page-param-name** | Tên query parameter dùng để chọn số trang |
| **limit-param-name** | Tên query parameter dùng để chỉ định số phần tử muốn nhận |
| **sort-param-name** | Tên query parameter dùng để sắp xếp |
| **default-media-type** | Media type mặc định khi request không chỉ rõ kiểu response |
| **return-body-on-create** | Có trả representation trong response sau khi tạo entity hay không |
| **return-body-on-update** | Có trả representation trong response sau khi cập nhật entity hay không |
| **detection-strategy** | Quy tắc quyết định repository nào được export |
| **enable-enum-translation** | Bật hoặc tắt dịch giá trị enum bằng resource bundle mặc định của Spring Data REST |

**default-media-type** chỉ là lựa chọn mặc định. Client vẫn có thể yêu cầu kiểu representation bằng header **Accept**, chẳng hạn **Accept: application/hal+json**. HAL là định dạng phù hợp để client đọc các liên kết hypermedia.

Nếu **return-body-on-create** hoặc **return-body-on-update** được đặt rõ thành **true**, response sau thao tác tương ứng sẽ có body. Nếu đặt **false**, body bị tắt. Khi không cấu hình rõ, quyết định có thể dựa trên header **Accept** của request. Header này không thay đổi việc thao tác có thành công hay không; client vẫn nên đọc status và **Location** khi tạo resource.

### Repository detection strategy

**spring.data.rest.detection-strategy** quyết định repository nào được Spring Data REST phát hiện và export.

| Giá trị | Hành vi |
|---|---|
| **default** | Export các repository interface public và vẫn xét cờ **exported** của **@RepositoryRestResource** |
| **all** | Export tất cả repository, không phụ thuộc visibility hoặc annotation |
| **annotated** | Chỉ export repository có **@RepositoryRestResource**, trừ repository được đánh dấu **exported = false** |
| **visibility** | Chỉ export repository public có **@RepositoryRestResource** |

Ví dụ đặt **annotated**:

```properties
spring.data.rest.detection-strategy=annotated
```

Khi dùng chiến lược này, repository cần được đánh dấu rõ ràng:

```java
@RepositoryRestResource(path = "books", collectionResourceRel = "books")
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

Chiến lược **annotated** hữu ích khi ứng dụng có nhiều repository nội bộ nhưng chỉ một tập hợp nhỏ được phép trở thành HTTP API. Đây là quy tắc phát hiện repository; nó không thay thế xác thực và phân quyền cho từng người dùng.

## 2. Cấu hình bằng application.yml

Có thể biểu diễn cùng cấu hình bằng YAML:

```yaml
spring:
  data:
    rest:
      base-path: /api
      default-page-size: 25
      max-page-size: 100
      page-param-name: p
      limit-param-name: limit
      sort-param-name: sort
      default-media-type: application/hal+json
      return-body-on-create: true
      return-body-on-update: true
      detection-strategy: annotated
      enable-enum-translation: false
```

Chọn **application.properties** hoặc **application.yml** theo quy ước của dự án. Không cần khai báo cả hai bản cho cùng một thiết lập. Có thể đặt cấu hình khác nhau trong **application-dev.yml**, **application-prod.yml** và kích hoạt Spring profile tương ứng.

Spring Boot cũng hỗ trợ override qua biến môi trường hoặc command line. Ví dụ biến môi trường **SPRING_DATA_REST_BASE_PATH** tương ứng với **spring.data.rest.base-path**. Điều này cho phép giữ cùng một artifact ứng dụng nhưng triển khai với base path khác nhau theo môi trường.

## 3. RepositoryRestConfigurer là gì?

**RepositoryRestConfigurer** là interface mở rộng điểm cấu hình của Spring Data REST. Spring Boot tự động tìm bean này và gọi các hook tương ứng trong quá trình khởi tạo.

Hook thường dùng nhất là:

```java
void configureRepositoryRestConfiguration(
    RepositoryRestConfiguration config,
    CorsRegistry cors
)
```

- **RepositoryRestConfiguration** cung cấp API Java cho base path, phân trang, media type, repository detection, projection và HTTP method exposure.
- **CorsRegistry** cho phép khai báo chính sách Cross-Origin Resource Sharing (CORS) cho endpoint Spring Data REST.

Trong Spring Data REST từ phiên bản 3.4 trở lên, hãy override method có cả hai tham số như trên. Chữ ký một tham số cũ đã được thay thế trong các phiên bản mới.

## 4. Ví dụ cấu hình bằng Java

Giả sử dự án đã có entity **Book** và **BookRepository**. Tạo class **RestApiConfiguration.java**:

```java
package com.example.books.config;

import com.example.books.Book;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setBasePath("/api");
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
        config.setPageParamName("p");
        config.setLimitParamName("limit");
        config.setSortParamName("sort");
        config.setDefaultMediaType(MediaTypes.HAL_JSON);
        config.setReturnBodyOnCreate(true);
        config.setReturnBodyOnUpdate(true);

        config.getExposureConfiguration()
            .forDomainType(Book.class)
            .withItemExposure((metadata, methods) ->
                methods.disable(HttpMethod.DELETE)
            );

        cors.addMapping("/**")
            .allowedOrigins("https://client.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Content-Type", "Authorization");
    }
}
```

**Giải thích:**

1. **@Configuration** đăng ký class này như một Spring bean. Spring Boot phát hiện bean triển khai **RepositoryRestConfigurer** mà không cần gọi thủ công.
2. **setBasePath("/api")** đặt tiền tố cho repository resources. Client truy cập root resource tại **/api/** và collection sách tại **/api/books**.
3. **setDefaultPageSize(25)** chọn số phần tử mặc định; **setMaxPageSize(100)** giới hạn kích thước trang tối đa.
4. **setPageParamName**, **setLimitParamName** và **setSortParamName** thay tên các query parameter.
5. **setDefaultMediaType(MediaTypes.HAL_JSON)** chọn HAL JSON khi request không chỉ định media type.
6. **setReturnBodyOnCreate** và **setReturnBodyOnUpdate** điều khiển việc trả representation sau khi tạo hoặc cập nhật.
7. **getExposureConfiguration()** cho phép tùy chỉnh HTTP method theo loại domain và loại resource. Trong ví dụ, **DELETE** bị tắt trên item resource của **Book**.
8. **CorsRegistry** chỉ cho phép origin frontend được nêu trong ví dụ gọi API từ trình duyệt bằng các method và header đã liệt kê.

Đoạn cấu hình Java thể hiện các thiết lập tương đương với ví dụ properties và bổ sung quy tắc CORS cùng HTTP method exposure. Trong một dự án thực tế, chọn một nơi làm nguồn cấu hình cho từng thuộc tính. Tránh đặt cùng một giá trị ở cả file cấu hình và configurer vì khó xác định thay đổi nào đang có hiệu lực khi nhiều configurer cùng chạy.

### Cấu hình đơn giản bằng withConfig

Nếu chỉ cần thay một vài giá trị trong **RepositoryRestConfiguration**, có thể dùng factory method thay vì tạo class riêng:

```java
package com.example.books.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class SimpleRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.setBasePath("/api");
            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        });
    }
}
```

**withConfig** tạo một implementation của **RepositoryRestConfigurer** từ lambda. Dùng dạng này cho các thiết lập ngắn gọn chỉ cần truy cập **RepositoryRestConfiguration**. Nếu cần cấu hình CORS hoặc override nhiều hook, triển khai interface thành class sẽ dễ đọc hơn.

## 5. Tùy chỉnh HTTP method exposure

Repository method được export có thể làm xuất hiện các HTTP method tương ứng. Ví dụ **save** có thể phục vụ **POST** trên collection và **PUT/PATCH** trên item. Vì vậy, chỉ ẩn method bằng annotation đôi khi chưa đủ nếu muốn giới hạn riêng từng method cho từng loại resource.

### Tắt method ở cấp repository hoặc method

Có thể đánh dấu repository không được export:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
```

Hoặc ẩn một method khỏi REST API:

```java
@RepositoryRestResource(path = "books")
public interface BookRepository extends JpaRepository<Book, Long> {

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);
}
```

Method vẫn tồn tại trong repository để code nội bộ gọi, nhưng không được export thành endpoint tương ứng. Chữ ký override phải khớp với interface cha và phiên bản Spring Data đang sử dụng.

### Tắt method theo loại resource

Dùng **ExposureConfiguration** khi cần phân biệt collection và item resource:

```java
config.getExposureConfiguration()
    .forDomainType(Book.class)
    .withCollectionExposure((metadata, methods) ->
        methods.disable(HttpMethod.POST)
    )
    .withItemExposure((metadata, methods) ->
        methods.disable(HttpMethod.DELETE)
    );
```

Với cấu hình này, **POST** bị tắt trên collection resource của **Book**, còn **DELETE** bị tắt trên item resource của **Book**. Các quy tắc được giới hạn cho domain type đã chỉ định. Có thể cấu hình association exposure riêng khi cần kiểm soát thao tác trên liên kết.

Không nhầm **detection-strategy** với **ExposureConfiguration**: detection strategy quyết định repository nào được export; exposure configuration quyết định HTTP method nào được phép trên resource đã export.

## 6. Cấu hình CORS

CORS cho phép trình duyệt gửi request từ một origin khác tới API khi server trả về các header CORS phù hợp. Ví dụ:

```java
cors.addMapping("/**")
    .allowedOrigins("https://client.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
    .allowedHeaders("Content-Type", "Authorization");
```

- **allowedOrigins** chỉ định origin được phép, bao gồm scheme, host và port nếu có.
- **allowedMethods** chỉ định HTTP method được phép.
- **allowedHeaders** chỉ định request header mà browser client có thể gửi.

Không dùng CORS như cơ chế xác thực hoặc phân quyền. CORS chủ yếu là chính sách mà trình duyệt áp dụng; client như curl vẫn có thể gọi endpoint. API vẫn cần Spring Security, xác thực và authorization theo nghiệp vụ. Nếu dùng cookie hoặc credential từ browser, cần cấu hình credentials cùng origin cụ thể; không kết hợp credential với wildcard origin.

## 7. Các hook khác của RepositoryRestConfigurer

Ngoài **configureRepositoryRestConfiguration**, interface còn có các hook cho các nhu cầu chuyên biệt:

| Hook | Trường hợp sử dụng |
|---|---|
| **configureValidatingRepositoryEventListener** | Đăng ký Validator chạy trước hoặc sau các repository event như create, save |
| **configureConversionService** | Đăng ký converter cho kiểu dữ liệu domain hoặc kiểu request/response |
| **configureHttpMessageConverters** | Bổ sung hoặc tùy chỉnh HttpMessageConverter |
| **configureJacksonObjectMapper** | Tùy chỉnh cách Jackson tạo JSON |
| **configureExceptionHandlerExceptionResolver** | Bổ sung cách xử lý exception và argument resolver |

Không cần override mọi hook. Chỉ thêm cấu hình khi ứng dụng có yêu cầu cụ thể. Với validation đơn giản, Spring Data REST cũng hỗ trợ đăng ký Validator theo quy ước tên bean gắn với event, chẳng hạn **beforeCreateBookValidator** hoặc **beforeSaveBookValidator**. Cách đăng ký thủ công qua **configureValidatingRepositoryEventListener** phù hợp khi muốn kiểm soát trực tiếp validator và event.

Khi tùy chỉnh Jackson hoặc message converter, cần kiểm tra cả representation HAL và các endpoint MVC khác của ứng dụng. Cấu hình serialization quá rộng có thể làm thay đổi response mà client hiện tại đang phụ thuộc.

## 8. Kiểm tra cấu hình sau khi khởi động

Sau khi khởi động ứng dụng, kiểm tra root resource:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/
```

Root resource cần cung cấp các liên kết của repository đã export. Nếu **BookRepository** được export, client sẽ tìm thấy relation tương ứng trong **_links**.

Đọc collection với các query parameter đã đổi tên:

```bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/api/books?p=0&limit=10&sort=title,asc"
```

Request trên yêu cầu trang đầu, tối đa 10 kết quả, sắp xếp theo **title** tăng dần. Tên parameter phải khớp với cấu hình đang có hiệu lực.

Thử method đã bị tắt:

```bash
curl -i -X DELETE -H "Accept: application/hal+json" http://localhost:8080/api/books/1
```

Với cấu hình exposure trong ví dụ, item resource của **Book** không hỗ trợ **DELETE** và server trả lỗi method không được phép, thường là **405 Method Not Allowed**.

Có thể kiểm tra CORS preflight bằng request **OPTIONS** với header **Origin** và **Access-Control-Request-Method**:

```bash
curl -i -X OPTIONS http://localhost:8080/api/books -H "Origin: https://client.example.com" -H "Access-Control-Request-Method: GET"
```

Response cần có header **Access-Control-Allow-Origin** tương ứng origin đã cho phép. Kiểm tra thêm origin khác để xác nhận chính sách từ chối origin không nằm trong danh sách.

## 9. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Endpoint vẫn ở **/books**, không ở **/api/books** | Sai key, sai profile hoặc configurer không được Spring phát hiện | Kiểm tra **spring.data.rest.base-path**, profile đang active và bean configurer |
| Repository biến mất sau khi đặt **annotated** | Repository chưa có **@RepositoryRestResource** | Gắn annotation cho repository cần export |
| Repository nội bộ xuất hiện ngoài ý muốn | Detection strategy quá rộng | Chọn **annotated**, đánh dấu **exported = false** và kiểm tra từng repository |
| Query parameter cũ không còn hoạt động | Đã đổi tên **page**, **limit** hoặc **sort** | Cập nhật client theo tên parameter mới |
| Client yêu cầu nhiều dữ liệu hơn dự kiến | Chưa giới hạn **max-page-size** hoặc hiểu nhầm tên parameter | Đặt mức trần hợp lý và kiểm tra request thực tế |
| Response không có body sau POST/PUT | Cấu hình return body hoặc header **Accept** | Kiểm tra **return-body-on-create/update** và gửi Accept phù hợp |
| Trình duyệt báo lỗi CORS | Origin, method hoặc header chưa được cho phép | Kiểm tra preflight và **CorsRegistry** |
| DELETE vẫn được export | Quy tắc exposure chưa áp dụng cho đúng domain/resource | Kiểm tra **forDomainType**, item/collection exposure và annotation trên method |

Khi nhiều cấu hình cùng tác động, kiểm tra lần lượt: profile đang active, giá trị property đã bind, bean **RepositoryRestConfigurer** có được component scan phát hiện, và request đang gọi đúng base path cùng query parameter. Sau đó kiểm tra response HAL và HTTP status để xác nhận chính sách đã được áp dụng.

## 10. Chọn đúng cơ chế cấu hình

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Đổi base path giữa dev và prod | **spring.data.rest.base-path** trong profile |
| Đặt kích thước trang mặc định và tối đa | **default-page-size**, **max-page-size** |
| Đổi tên query parameter | **page-param-name**, **limit-param-name**, **sort-param-name** |
| Chỉ export repository được đánh dấu | **detection-strategy=annotated** |
| Chặn riêng DELETE cho item resource của một domain type | **RepositoryRestConfigurer** và **ExposureConfiguration** |
| Cho phép một frontend origin gọi API | **RepositoryRestConfigurer** và **CorsRegistry** |
| Thêm converter hoặc validator | Hook tương ứng của **RepositoryRestConfigurer** |
| Ẩn hẳn một repository hoặc method | **@RepositoryRestResource(exported = false)** hoặc **@RestResource(exported = false)** |

Ưu tiên property cho thiết lập đơn giản, dễ quản lý theo môi trường. Dùng **RepositoryRestConfigurer** khi cần API Java hoặc logic tùy biến. Kết hợp annotation ở repository để diễn đạt rõ resource nào được công khai. Sau cùng, dùng Spring Security để bảo vệ endpoint theo danh tính và quyền của client.

## 11. Bài tập thực hành

1. Đổi base path từ **/api** thành **/v1** và xác nhận root resource chuyển theo.
2. Đặt **default-page-size=10**, **max-page-size=30**. Gọi collection không có tham số và gọi với **limit=100**; quan sát số phần tử thực tế.
3. Đổi **page-param-name** thành **p** và **sort-param-name** thành **order**, sau đó cập nhật request client.
4. Đặt **detection-strategy=annotated**. Thêm một repository không có annotation và một repository có **@RepositoryRestResource**; so sánh endpoint được export.
5. Tắt **DELETE** cho item resource của **Book** bằng **ExposureConfiguration** và kiểm tra status khi gọi DELETE.
6. Cấu hình CORS cho một origin frontend, gửi preflight OPTIONS với origin được phép và origin khác.
7. Thử cấu hình **return-body-on-create** là **true** và **false**, sau đó so sánh response của POST với cùng header Accept.

## Tài liệu tham khảo

- [Spring Data REST — Getting Started và Basic Settings](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
