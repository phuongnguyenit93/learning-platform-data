# @BasePathAwareController và phân biệt với @RestController thông thường

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của **@BasePathAwareController** trong Spring Data REST.
- Hiểu cách base path của repository exporter được ghép vào custom request mapping.
- Phân biệt **@BasePathAwareController**, **@RestController** và **@RepositoryRestController**.
- Chọn annotation phù hợp cho custom endpoint, view hoặc thao tác gắn với repository resource.
- Trả JSON, ResponseEntity và Spring HATEOAS representation từ custom controller.
- Tránh xung đột URL, cấu hình base path trùng lặp và nhầm lẫn về CORS hoặc bảo mật.
- Kiểm tra endpoint bằng curl và browser DevTools.

## 1. Vì sao cần controller nhận biết base path?

Spring Data REST có thể tự xuất bản repository thành REST API. Ví dụ ứng dụng cấu hình base path là **/api**, repository Person có thể được truy cập tại:

~~~text
/api/people
/api/people/42
~~~

Trong thực tế, ứng dụng thường cần thêm endpoint riêng như trạng thái hệ thống, báo cáo, thao tác nghiệp vụ hoặc trang quản trị. Nếu tạo một controller Spring MVC thông thường, mapping của controller đó không tự động được thêm base path Spring Data REST.

Điều này dễ tạo ra hai nhóm URL khác nhau:

~~~text
Spring Data REST:  /api/people
Custom MVC:        /reports/summary
~~~

Nếu muốn custom endpoint nằm dưới cùng base path với repository API, Spring Data REST cung cấp **@BasePathAwareController**. Annotation này đánh dấu controller có request mapping cần được bổ sung base URI được cấu hình trong Spring Data REST.

Ví dụ:

~~~text
Spring Data REST base path: /api
Custom mapping:             /system/status
Final URL:                  /api/system/status
~~~

Nhờ vậy, nếu base path đổi từ **/api** sang **/rest**, custom endpoint cũng được điều chỉnh theo cấu hình chung mà không phải sửa từng mapping.

## 2. Cấu hình base path

Có thể cấu hình base path bằng Spring Boot property:

~~~properties
spring.data.rest.base-path=/api
~~~

Hoặc dùng RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

Trong ví dụ tiếp theo, giả sử base path đang là **/api**. Base path này thuộc Spring Data REST. Nó khác với servlet context path có thể được cấu hình ở cấp ứng dụng web.

Nếu ứng dụng đồng thời dùng servlet context path, URL bên ngoài còn có thể bao gồm context path đó. Hãy xác định rõ hai cấu hình khi kiểm tra URL thực tế.

## 3. @BasePathAwareController là gì?

**@BasePathAwareController** nằm trong package:

~~~java
org.springframework.data.rest.webmvc.BasePathAwareController
~~~

Đây là annotation của Spring Data REST dùng để đánh dấu controller có các request mapping được bổ sung base URI trong RepositoryRestConfiguration.

Ví dụ đơn giản:

~~~java
import java.util.Map;

import org.springframework.data.rest.webmvc.BasePathAwareController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@BasePathAwareController
public class SystemStatusController {

    @GetMapping("/system/status")
    @ResponseBody
    public Map<String, String> status() {
        return Map.of("status", "UP");
    }
}
~~~

Với base path **/api**, endpoint được phục vụ tại:

~~~http
GET /api/system/status
~~~

Điểm quan trọng:

- **@BasePathAwareController** cho Spring Data REST biết controller này phải nhận base path đã cấu hình.
- **@GetMapping** vẫn xác định phần path của handler method.
- **@ResponseBody** yêu cầu Spring ghi giá trị trả về vào response body, ví dụ serialize Map thành JSON.
- Controller vẫn là custom endpoint do ứng dụng định nghĩa; annotation không tự tạo repository hay entity resource.

Nếu muốn trả một view Spring MVC thay vì JSON, controller có thể dùng cơ chế view resolution tương ứng. Đây là một lý do annotation phù hợp với các custom operation hoặc resource nằm dưới base path nhưng không nhất thiết là thao tác trên một entity.

## 4. Thuộc tính path và value

**@BasePathAwareController** hỗ trợ thuộc tính **path** và **value** như alias của nhau. Chúng xác định root path bổ sung vào các request mapping của handler method.

Ví dụ:

~~~java
@BasePathAwareController(path = "/ops")
public class OperationsController {

    @GetMapping("/health")
    @ResponseBody
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }
}
~~~

Với base path **/api**, URL kết hợp là:

~~~text
/api/ops/health
~~~

Có thể dùng **value** thay cho **path**:

~~~java
@BasePathAwareController("/ops")
public class OperationsController {
    // Các handler mapping bắt đầu từ /ops.
}
~~~

Chỉ dùng một trong hai thuộc tính để tránh cấu hình trùng lặp. Thuộc tính này là root path bổ sung cho các mapping của controller; nó không thay thế base path được cấu hình ở cấp Spring Data REST.

## 5. Phân biệt với @RestController thông thường

**@RestController** là annotation của Spring MVC. Nó kết hợp vai trò controller với **@ResponseBody**, nên giá trị trả về của handler method được ghi vào HTTP response body và thường được serialize qua HttpMessageConverter.

Ví dụ:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/reports/summary")
    public Map<String, Object> summary() {
        return Map.of(
            "activeMembers", 120,
            "pendingOrders", 8
        );
    }
}
~~~

Mapping trên thuộc Spring MVC thông thường. Nếu Spring Data REST có base path **/api**, annotation **@RestController** không tự biến URL thành **/api/reports/summary**. URL còn phụ thuộc servlet context path và mapping của ứng dụng, nhưng không được tự động ghép Spring Data REST base path.

So sánh:

| Tiêu chí | @BasePathAwareController | @RestController |
|---|---|---|
| Cơ chế | Controller được Spring Data REST nhận biết để bổ sung base URI | Controller chuẩn của Spring MVC |
| Base path Spring Data REST | Tự động được ghép vào request mapping | Không tự động được ghép |
| Response body | Dùng @ResponseBody hoặc kiểu trả về như ResponseEntity khi cần body | Có sẵn @ResponseBody ở cấp class |
| Mục đích | Custom operations/resources nằm dưới base path Spring Data REST | REST endpoint thông thường của ứng dụng |
| Phạm vi xử lý | Được nhận biết bởi hạ tầng base-path-aware của Spring Data REST | Nằm ngoài phạm vi xử lý riêng của Spring Data REST |
| Ví dụ URL với base path /api | /api/system/status | /reports/summary |

Nếu dùng **@RestController** và tự ghi cứng **/api** vào @RequestMapping, endpoint có thể chạy đúng ở thời điểm hiện tại. Tuy nhiên, khi base path thay đổi, mapping đó không tự đổi theo. Điều này tạo ra cấu hình lặp và có thể khiến custom endpoint lệch khỏi repository API.

Đừng nhầm **server.servlet.context-path** với **spring.data.rest.base-path**. Context path thuộc ứng dụng web; base path thuộc REST exporter. Một controller MVC thông thường có thể nằm dưới context path, nhưng không vì vậy mà nó trở thành base-path-aware của Spring Data REST.

## 6. @BasePathAwareController không đồng nghĩa @RestController

Một điểm cần chú ý: **@BasePathAwareController** chịu trách nhiệm đánh dấu controller nhận base path. Nó không nên được xem như alias hoàn toàn của **@RestController**.

Nếu handler trả Map, DTO hoặc object cần serialize thành JSON, hãy khai báo rõ **@ResponseBody** trên method:

~~~java
@BasePathAwareController
public class VersionController {

    @GetMapping("/system/version")
    @ResponseBody
    public Map<String, String> version() {
        return Map.of("version", "1.0.0");
    }
}
~~~

Hoặc trả về ResponseEntity:

~~~java
@BasePathAwareController
public class VersionController {

    @GetMapping("/system/version")
    public ResponseEntity<Map<String, String>> version() {
        return ResponseEntity.ok(
            Map.of("version", "1.0.0")
        );
    }
}
~~~

ResponseEntity là kiểu trả về có body và status/header rõ ràng. Với handler trả về một object trực tiếp, @ResponseBody giúp xác định rằng object là response body thay vì tên view.

Không thêm **@RestController** chỉ để có JSON rồi cho rằng base path sẽ tự được áp dụng. Hãy chọn annotation theo handler mapping cần dùng.

## 7. Phân biệt thêm với @RepositoryRestController

Spring Data REST còn cung cấp **@RepositoryRestController**. Annotation này cũng nhận base path, nhưng phục vụ một mục đích cụ thể hơn: custom handler gắn vào URI space do repository resource quản lý.

Ví dụ:

~~~java
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseBody;

@RepositoryRestController
public class PersonCustomController {

    private final PersonRepository repository;

    public PersonCustomController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/{id}/summary")
    @ResponseBody
    public PersonSummary summary(@PathVariable Long id) {
        Person person = repository.findById(id).orElseThrow();
        return PersonSummary.from(person);
    }
}
~~~

Với base path **/api**, URL minh họa là:

~~~text
/api/people/42/summary
~~~

Khác biệt quan trọng:

- **@BasePathAwareController** dành cho custom operation dưới base path, chẳng hạn resource hoặc view không gắn trực tiếp với thao tác của một repository entity.
- **@RepositoryRestController** dành cho handler có mapping nằm trong URI space của repository resource. Hạ tầng đặc biệt của nó có thể áp dụng CORS theo repository tương ứng và OpenEntityManagerInViewInterceptor cho JPA để hỗ trợ truy cập thuộc tính lazy.
- **@RestController** là Spring MVC controller thông thường, nằm ngoài phạm vi xử lý riêng của Spring Data REST.

Nếu handler làm việc với một repository item và cần tích hợp các thiết lập repository-specific, hãy cân nhắc **@RepositoryRestController**. Nếu chỉ cần một custom resource dưới base path, **@BasePathAwareController** thường phù hợp hơn.

Không dùng @RepositoryRestController cho mọi endpoint chỉ vì nó có tên giống Spring Data REST. Mapping của nó cần phù hợp với URI space mà repository quản lý.

## 8. Chọn annotation theo tình huống

| Tình huống | Annotation nên cân nhắc |
|---|---|
| Endpoint health/status dưới /api | **@BasePathAwareController** |
| Resource hoặc view custom nằm dưới base path | **@BasePathAwareController** |
| Handler bổ sung cho một repository resource, cần CORS/OEIV theo repository | **@RepositoryRestController** |
| API độc lập của ứng dụng, không cần Spring Data REST base path | **@RestController** |
| MVC controller trả HTML view thông thường | **@Controller** |
| CRUD collection/item đã được repository xuất bản | Repository do Spring Data REST quản lý; thường không cần custom controller |

Quyết định theo hai câu hỏi:

1. Endpoint có cần tự động nằm dưới base path Spring Data REST không?
2. Endpoint có cần được xử lý như một custom handler trong URI space của repository hay chỉ là custom resource độc lập?

Câu trả lời giúp chọn đúng annotation và tránh việc controller vô tình tranh chấp URL với repository exporter.

## 9. Kết hợp với Spring HATEOAS

Một custom endpoint có thể trả về dữ liệu kèm link để client khám phá API. Spring HATEOAS cung cấp **EntityModel**, **CollectionModel** và các kiểu RepresentationModel để biểu diễn resource cùng liên kết.

Ví dụ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;

@BasePathAwareController
public class SystemInfoController {

    @GetMapping("/system/info")
    @ResponseBody
    public EntityModel<SystemInfo> info() {
        SystemInfo info = new SystemInfo("Spring Data REST");

        return EntityModel.of(
            info,
            linkTo(methodOn(SystemInfoController.class).info()).withSelfRel()
        );
    }
}
~~~

Ví dụ minh họa cho custom resource có self link. Trong dự án thật, kiểm tra link builder và servlet/base path configuration của phiên bản Spring HATEOAS đang dùng để bảo đảm URI được tạo đúng theo deployment.

Việc đặt controller dưới base path không tự động thêm link của endpoint đó vào mọi HAL response của repository. Nếu client cần khám phá custom operation từ một entity hoặc API root, hãy bổ sung link bằng cơ chế phù hợp như RepresentationModelProcessor hoặc ResourceProcessor.

## 10. Tránh xung đột mapping

Spring Data REST đã dùng một URI space cho collection, item, association và search resource. Khi thêm custom controller, tránh định nghĩa path trùng với endpoint repository đã công bố.

Ví dụ không nên tùy tiện dùng:

~~~text
/api/people
/api/people/{id}
~~~

cho một custom controller khác nếu các path đó đã thuộc PersonRepository.

Thay vào đó, chọn một namespace rõ ràng:

~~~text
/api/system/status
/api/reports/summary
/api/operations/reindex
~~~

Nếu cần thao tác gắn với một item cụ thể, dùng một subpath không xung đột và cân nhắc **@RepositoryRestController**:

~~~text
/api/people/42/summary
~~~

Khi mapping không được gọi như mong đợi, kiểm tra startup log để tìm ambiguous mapping, xem request URL thực tế và xác định HandlerMapping nào đang xử lý endpoint.

## 11. Cấu hình CORS và bảo mật

**@BasePathAwareController** chỉ giải quyết việc nhận base path. Nó không tự cấp quyền truy cập cho frontend và không thay thế cấu hình CORS.

Nếu custom endpoint cần cross-origin access, cấu hình CORS theo cơ chế Spring MVC/Spring Security phù hợp với endpoint đó. Đừng mặc định cấu hình CORS dành cho repository resource cũng tự áp dụng giống hệt cho mọi custom controller.

Tương tự, việc URL nằm dưới **/api** không làm endpoint tự động có authentication hoặc authorization giống như bạn mong đợi. Hãy kiểm tra SecurityFilterChain và áp dụng rule rõ ràng cho custom path.

Một số nguyên tắc:

- Chỉ cho phép origin frontend tin cậy.
- Giới hạn HTTP method và request header theo nhu cầu.
- Kiểm tra quyền người dùng ở server cho từng thao tác.
- Nếu dùng cookie session, đánh giá CSRF protection.
- Không coi việc ẩn link hoặc đổi base path là biện pháp bảo mật.

Với **@RepositoryRestController**, Spring Data REST có thể áp dụng CORS configuration theo repository được ánh xạ với path của handler. Đây là một trong những khác biệt thực tế so với custom endpoint chỉ dùng @BasePathAwareController.

## 12. Kiểm tra endpoint bằng curl

Giả sử:

- Base path: **/api**
- Controller: **@BasePathAwareController**
- Handler: **@GetMapping("/system/status")**

Gọi endpoint:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/system/status
~~~

Kết quả mong đợi là status thành công cùng JSON body, ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

Kiểm tra endpoint MVC thông thường:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/reports/summary
~~~

Nếu mapping chuẩn Spring MVC được khai báo như ví dụ trước, URL không tự thêm **/api**. Nếu ứng dụng có servlet context path, hãy thêm context path đó theo cấu hình web thực tế.

Nếu thay base path từ **/api** sang **/rest**, gọi lại:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/rest/system/status
~~~

Endpoint base-path-aware theo cấu hình mới sẽ đi theo prefix mới. Một @RestController có mapping cố định sẽ không tự đổi theo base path Spring Data REST.

## 13. Kiểm tra bằng browser DevTools

Trong Network panel:

1. Gọi endpoint từ frontend.
2. Xác nhận Request URL có đúng base path không.
3. Kiểm tra method và status code.
4. Xem Content-Type và response body.
5. Nếu browser báo CORS, kiểm tra OPTIONS preflight và response header.
6. Nếu nhận 404, kiểm tra base path, servlet context path và mapping của controller.
7. Nếu nhận 406/415, kiểm tra Accept và Content-Type.
8. Nếu nhận 401/403, kiểm tra security rule của custom path.

Dùng Actuator mappings hoặc startup log nếu dự án có bật endpoint chẩn đoán phù hợp để xem mapping đã được đăng ký. Không bật thông tin mapping nhạy cảm ra môi trường public nếu chính sách vận hành không cho phép.

## 14. Lỗi thường gặp

### @RestController không nằm dưới /api

@RestController dùng mapping Spring MVC thông thường. Nó không tự động nhận Spring Data REST base path. Dùng @BasePathAwareController hoặc tự cấu hình path theo kiến trúc ứng dụng.

### Thêm /api thủ công vào từng mapping

Khi base path đổi, các mapping cố định không đổi theo. Để Spring Data REST ghép prefix bằng @BasePathAwareController.

### Dùng @BasePathAwareController nhưng object không được serialize thành JSON

Annotation này đánh dấu base-path-aware controller, không nên coi nó là alias đầy đủ của @RestController. Dùng @ResponseBody trên handler hoặc trả ResponseEntity.

### Dùng @RepositoryRestController cho endpoint độc lập

RepositoryRestController phù hợp với URI space của repository và có thêm tích hợp repository-specific. Với health, report hoặc resource độc lập dưới base path, cân nhắc @BasePathAwareController.

### Mapping custom trùng với repository

Collection, item, association hoặc search path có thể đã được exporter sử dụng. Chọn namespace riêng và kiểm tra ambiguous mapping.

### CORS của repository không áp dụng như mong đợi

CORS phụ thuộc handler mapping và cấu hình security. @BasePathAwareController không tự động có cùng repository-specific CORS behavior như @RepositoryRestController.

### Cho rằng base path cung cấp bảo mật

Base path chỉ là prefix URL. Authentication, authorization, CSRF và validation vẫn phải được cấu hình riêng.

### Custom endpoint không xuất hiện trong HAL

Controller mapping không tự động thêm link vào representation repository. Nếu client cần khám phá endpoint, bổ sung hypermedia link rõ ràng.

## 15. Ghi nhớ

- **@BasePathAwareController** đánh dấu custom controller có request mapping được bổ sung Spring Data REST base URI.
- Base path có thể cấu hình bằng **spring.data.rest.base-path** hoặc **RepositoryRestConfiguration.setBasePath(...)**.
- Thuộc tính **path/value** của annotation có thể thêm root path cho các handler mapping.
- **@RestController** là Spring MVC controller thông thường và không tự nhận Spring Data REST base path.
- Dùng **@ResponseBody** hoặc **ResponseEntity** khi handler base-path-aware cần trả response body.
- **@RepositoryRestController** dành cho custom handler trong URI space của repository và có thêm tích hợp như CORS theo repository, OpenEntityManagerInView cho JPA.
- Chọn namespace custom tránh trùng collection, item, association và search resource.
- Base path không tự thêm hypermedia link, không cấp authentication và không thay thế authorization.
- Kiểm tra URL, HandlerMapping, CORS, security và response bằng curl/DevTools.

## Tài liệu tham khảo

- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — BasePathAwareController API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/BasePathAwareController.html)
- [Spring Data REST — RepositoryRestController API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositoryRestController.html)
- [Spring Data REST — Getting Started and Base URI](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
