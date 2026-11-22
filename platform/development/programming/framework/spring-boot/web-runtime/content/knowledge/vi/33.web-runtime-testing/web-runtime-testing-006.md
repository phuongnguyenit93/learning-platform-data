# Kiểm thử mapping, status, header, JSON và content negotiation

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Kiểm thử web runtime

## 1. Bài toán: API chạy được chưa đủ, hợp đồng HTTP phải đúng

Một Spring Boot REST controller có thể trả dữ liệu đúng khi lập trình viên mở trình duyệt, nhưng vẫn sai hợp đồng HTTP theo nhiều cách: URL mapping sai một đoạn, method POST bị nhận nhầm thành GET, response trả 200 khi cần 404, thiếu header Location của 201, dữ liệu boolean thành chuỗi, hoặc nhận application/xml dù API chỉ hỗ trợ JSON.

Một HTTP API không chỉ có body. Hợp đồng observable gồm:

1. **Request mapping:** HTTP method, đường dẫn, path variables, query parameters, headers, consumes và produces.
2. **Status:** 200, 201, 204, 400, 401, 403, 404, 405, 406, 409, 415, 422, 500..., với semantics đúng.
3. **Response headers:** Content-Type, Location, Cache-Control, Vary, ETag, Allow, security headers hoặc custom headers cần thiết.
4. **JSON representation:** tên field, kiểu dữ liệu, nested objects, arrays, null, missing fields, serialization và encoding.
5. **Content negotiation:** sự khác nhau giữa request **Accept** và **Content-Type**, chọn representation đúng, từ chối khi không hỗ trợ.
6. **Tính đúng trên wire:** một số thứ chỉ có thể kiểm khi HTTP server thực chạy, không chỉ MockMvc.

Ví dụ một API tài nguyên thiết bị có thể có hợp đồng:

~~~text
GET    /api/widgets/1         Accept: application/json
  -> 200 application/json, JSON object, Vary: Accept

GET    /api/widgets/1         Accept: text/plain
  -> 200 text/plain, plain text representation

GET    /api/widgets/1         Accept: application/xml
  -> 406 Not Acceptable

POST   /api/widgets           Content-Type: application/json
                               Accept: application/json
  -> 201 Created, Location: /api/widgets/{new-id}, JSON object

POST   /api/widgets           Content-Type: text/plain
  -> 415 Unsupported Media Type

POST   /api/widgets           Content-Type: application/json
                               malformed JSON
  -> 400 Bad Request

GET    /api/widgets/999       Accept: application/json
  -> 404 Not Found
~~~

**Mục tiêu bài học:** tạo và kiểm toàn bộ hợp đồng này bằng **Spring Boot 3.3 / Java 17+**, sử dụng **MockMvc**, **@WebMvcTest**, **@SpringBootTest**, **@AutoConfigureMockMvc**, **RANDOM_PORT**, JUnit 5 và Java HttpClient. Đặc biệt phải phân biệt những gì một test slice có thể chứng minh với những gì cần chạy embedded Tomcat thật.

**Ghi chú về phiên bản:** bài demo dùng **Spring Boot 3.3.13** để các ví dụ cùng API thuộc nhánh 3.3. Đây không phải lời khuyên dùng nhánh 3.3 cho dự án production mới; nhánh 3.3 đã hết hỗ trợ mã nguồn mở. Production nên dùng phiên bản Spring Boot hiện còn được duy trì, nâng cấp các bản vá và điều chỉnh imports/API testing nếu chuyển lên nhánh lớn mới.

## 2. Hiểu đúng tầng nào đang được kiểm thử

Các lớp kiểm thử khác nhau không có cùng khả năng:

| Hình thức | Khởi động những gì? | Kiểm được | Không tự chứng minh |
| --- | --- | --- | --- |
| Unit test gọi method controller | Java class + dependencies giả | Logic thuần trong method | Spring MVC handler mappings, converters, HTTP status thật. |
| **MockMvc standaloneSetup** | Spring MVC test infrastructure quanh controller chỉ định | Mapping/converters đã cấu hình cho standalone | Toàn bộ Boot auto-config, container và filters thực tế nếu chưa thêm. |
| **@WebMvcTest + MockMvc** | MVC slice gồm controller, MVC mappings, converters, selected advice/filters | Method/path, status, headers, JSON, media negotiation ở MVC layer | Embedded server socket/TLS/compression/HTTP2; toàn bộ business beans. |
| **@SpringBootTest + @AutoConfigureMockMvc** | Full ApplicationContext, mocked servlet request/response | Web MVC + app auto-config + filters/beans trong context | Network/server connector behavior. |
| **@SpringBootTest(RANDOM_PORT)** | Full context + embedded HTTP server thật | Status/headers/body qua network, serialization, server behavior | Hành vi của public ingress/CDN nếu test bypass proxy. |
| End-to-end qua ingress | Gateway, TLS, proxy, service deployment | Public URL, forwarding, auth/routing/caching | Không cô lập dễ lỗi ở từng layer. |

**MockMvc không dùng socket TCP thật.** Nó gửi một **MockHttpServletRequest** qua Spring MVC và nhận **MockHttpServletResponse**. Vì vậy rất hiệu quả để kiểm hợp đồng controller, nhưng không thay thế việc đo compression threshold, connector timeout, HTTP/2 framing, TLS, reverse proxy hoặc shutdown behavior.

**@WebMvcTest** scan một phần bean của web layer, không tự nạp mọi **@Service**, **@Repository** hay configuration của app. Nếu controller phụ thuộc service, test slice cần fake/mocks như **@MockBean** trong Spring Boot 3.3; đừng cố autowire cả database thật chỉ để kiểm một status 404. Với Boot mới hơn, API mock bean có thể đổi; cần đối chiếu tài liệu theo version.

**@SpringBootTest** mặc định webEnvironment=MOCK, không tự mở HTTP listener. Muốn kiểm qua socket, chọn **RANDOM_PORT**. Muốn MockMvc trong full context, thêm **@AutoConfigureMockMvc**.

## 3. Mapping: điều kiện chọn handler của Spring MVC

Một handler trong Spring MVC có thể dùng:

~~~java
@GetMapping(
    path = "/api/widgets/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
public WidgetDto find(@PathVariable long id) {
    // Domain lookup and return.
    return someWidget;
}
~~~

Đoạn trên là **snippet minh họa, không phải chương trình độc lập**. Phần ví dụ runnable sẽ có controller đầy đủ.

Spring MVC xem xét một tập điều kiện để chọn handler:

- **HTTP method:** GET/POST/PUT/PATCH/DELETE; method sai thường dẫn tới **405 Method Not Allowed** khi URL khớp mapping.
- **Path:** class-level + method-level @RequestMapping; path variables; nested routes; servlet context path.
- **params:** ví dụ @GetMapping(params="active=true") chỉ match request có điều kiện query phù hợp.
- **headers:** có thể ràng buộc một request header phải hiện diện/đúng giá trị.
- **consumes:** giới hạn media types được đọc từ **request Content-Type**, quan trọng với POST/PUT/PATCH có body.
- **produces:** giới hạn media types response mà handler có thể tạo, được chọn dựa trên **request Accept**.
- **Argument conversion:** string path/query sang long/enum/date có thể thất bại và dẫn tới 400.
- **Message conversion:** Jackson đọc/ghi JSON; converter không phù hợp có thể phát lỗi 400/415/406 hoặc lỗi server tùy nguyên nhân.

**Test mapping không phải chỉ kiểm URI có tồn tại.** Cần kiểm method đúng, path đúng, Accept phù hợp, consumes phù hợp và các kết quả từ chối. Ví dụ GET và POST cùng URL có hợp đồng hoàn toàn khác nhau.

### 3.1. Content-Type và Accept không đồng nghĩa

| Header | Hướng | Ý nghĩa |
| --- | --- | --- |
| **Content-Type** | Request gửi tới server | Media type của **request body** hiện tại; ví dụ application/json. |
| **Accept** | Request gửi tới server | Những **response media types** mà client chấp nhận; ví dụ application/json hoặc text/plain. |
| **Content-Type** của response | Server trả về | Media type thực của response body đã chọn. |
| **Vary: Accept** | Response/caching | Cache cần xét Accept khi representations khác nhau theo header này. |

Một request có thể có:

~~~http
POST /api/widgets HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"name":"Spring Tests"}
~~~

Nếu client gửi **Accept: text/plain** nhưng endpoint POST chỉ có JSON response, server có thể trả **406**. Nếu client gửi **Content-Type: text/plain** nhưng endpoint chỉ nhận JSON, nó có thể trả **415**.

**Không yêu cầu Content-Type trên GET khi không gửi body**, và đừng viết test kiểm rằng GET có Content-Type: application/json ở phía request mới được trả JSON. Trên GET thông thường, **Accept** mới là điều kiện quan trọng cho response format.

### 3.2. 406 và 415 khác nhau

**406 Not Acceptable:** server không có representation phù hợp với Accept mà client yêu cầu, dựa trên cấu hình content negotiation/produces.  
**415 Unsupported Media Type:** server không nhận request entity media type được khai báo trong Content-Type theo consumes hoặc converter support.

**400 Bad Request** có thể xảy ra khi Content-Type đúng là application/json nhưng body không phải JSON hợp lệ, field conversion sai hoặc validation bị từ chối.

**405 Method Not Allowed** xảy ra khi URL có mapping, nhưng HTTP method không được hỗ trợ. **404** là không có resource/route theo semantics của endpoint; một GET tới URL hợp lệ nhưng id không tồn tại có thể được controller trả 404 chủ động.

Các status code có thể được xử lý qua **@ControllerAdvice**, custom exception handlers hoặc proxy; bài demo sử dụng Spring MVC mặc định và ResponseEntity để ví dụ rõ.

## 4. Khi nào kỳ vọng JSON chính xác?

Đừng đồng nhất "response có chuỗi trông giống JSON" với "HTTP response JSON hợp lệ". Cần kiểm cả:

1. **Content-Type**: ứng dụng thực sự trả **application/json**, không phải text/plain chứa dấu ngoặc JSON.
2. **JSON parse được** bằng Jackson/JSON parser.
3. **Tên property** đúng: id/name/active khác ID/Name/activeFlag.
4. **Kiểu** đúng: id number, active boolean, name string; không chấp nhận "1" thay cho 1 nếu contract yêu cầu number.
5. **Giá trị** đúng, bao gồm Unicode và whitespace khi được yêu cầu.
6. **Field presence/absence**: field thiếu khác field có null hoặc chuỗi rỗng.
7. **Array/nested structures**: số phần tử, thứ tự nếu có ý nghĩa, quan hệ.
8. **Không lộ field nội bộ**: passwordHash, internalMemo, credentials; test negative assertions.
9. **Error representation**: 400/404/500 có thể có JSON lỗi khác nhau; không mặc định mọi lỗi giống success DTO.

JSON object member order thường không mang ý nghĩa hợp đồng. Không so sánh raw JSON string theo thứ tự field hoặc whitespace; dùng **jsonPath**, parse JSON hoặc **content().json(...)** với mức strict phù hợp.

**Jackson với Java record:** Spring Boot 3.3 sử dụng Jackson phù hợp với Java 17, có thể serialize **record WidgetDto(long id, String name, boolean active)** thành các fields id/name/active. Nếu dự án có naming strategy (snake_case), JsonViews, custom modules hoặc @JsonProperty, phải test dữ liệu thực chứ không chỉ nhìn tên Java field.

## 5. Dự án Spring Boot 3.3 / Java 17+ chạy được

Chúng ta xây API **Widget** với hai representations trên cùng URL:

- **GET /api/widgets/{id}** có **produces="application/json"** trả WidgetDto.
- **GET /api/widgets/{id}** có **produces="text/plain"** trả chuỗi đọc được.
- **POST /api/widgets** với **consumes="application/json", produces="application/json"** tạo widget, trả **201 Created** và Location.
- Request không có item id tồn tại trả **404**.
- Invalid JSON hoặc name rỗng trả **400**.
- Unsupported Accept trả **406**; unsupported request Content-Type trả **415**.

Các GET có cùng path nhưng khác **produces** cho thấy Spring MVC chọn representation theo Accept; test luôn gửi **Accept rõ ràng** để tránh sự mơ hồ của client chỉ gửi */*.

Cấu trúc:

~~~text
web-contract-demo/
  pom.xml
  src/main/java/com/example/webcontract/
    WebContractDemoApplication.java
    WidgetDto.java
    CreateWidgetRequest.java
    WidgetController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/webcontract/
    WidgetControllerMvcTests.java
    WidgetFullContextMvcTests.java
    WidgetLiveHttpTests.java
    WidgetJsonTests.java
~~~

### 5.1. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-contract-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**Không cần spring-boot-starter-webflux** chỉ để dùng MockMvc. Starter-web dùng Spring MVC/Servlet và mặc định embedded Tomcat; starter-test mang JUnit Jupiter, Spring Test, AssertJ, Hamcrest, Mockito và JSON testing tools tương ứng với BOM.

**Boot 3.3.13 là phiên bản phục vụ ví dụ**, không nên giữ lâu dài trong hệ thống mới vì nhánh này đã hết OSS support. Nếu chuyển Spring Boot 4.x, package/artifact testing và API có thể khác, cần cập nhật theo docs version đang dùng.

### 5.2. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
spring.application.name=web-contract-demo
server.port=8080

# Khong bat path extension negotiation tu dong.
# Client nen dung Accept de chon representation.
~~~

Không tự đặt default Content-Type cho tất cả endpoints. Spring MVC chọn **HttpMessageConverter** và type dựa trên return value/Accept/produces. Khi có reverse proxy, URL/Location có thể phải xử lý forwarded headers riêng.

### 5.3. Main class

Tạo **src/main/java/com/example/webcontract/WebContractDemoApplication.java**:

~~~java
package com.example.webcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebContractDemoApplication.class, args);
    }
}
~~~

Mỗi public class/record nằm trong file đúng tên. Package root **com.example.webcontract** bao trùm các controllers/DTO. Không cần web.xml hoặc @EnableWebMvc; @EnableWebMvc có thể làm thay đổi Boot MVC auto-configuration khi dùng không phù hợp.

### 5.4. DTO: JSON number, string và boolean

Tạo **src/main/java/com/example/webcontract/WidgetDto.java**:

~~~java
package com.example.webcontract;

public record WidgetDto(long id, String name, boolean active) {
}
~~~

Tạo **src/main/java/com/example/webcontract/CreateWidgetRequest.java**:

~~~java
package com.example.webcontract;

public record CreateWidgetRequest(String name) {
}
~~~

Hai Java records là **DTO** để nhận/trả HTTP JSON. Không có entity JPA/database trong demo; state nằm trong một ConcurrentHashMap và sẽ mất khi app restart. Trong dự án thật, tách persistence/service/security, test ở mức phù hợp với dependencies.

### 5.5. WidgetController đầy đủ

Tạo **src/main/java/com/example/webcontract/WidgetController.java**:

~~~java
package com.example.webcontract;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/widgets")
public class WidgetController {

    private final Map<Long, WidgetDto> widgets =
            new ConcurrentHashMap<>(Map.of(
                    1L, new WidgetDto(1L, "Spring MVC", true),
                    2L, new WidgetDto(2L, "Spring Testing", false)
            ));

    private final AtomicLong nextId = new AtomicLong(100L);

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<WidgetDto> json(
            @PathVariable("id") long id) {

        WidgetDto widget = widgets.get(id);

        if (widget == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .varyBy(HttpHeaders.ACCEPT)
                .cacheControl(CacheControl.noStore())
                .header("X-Widget-Format", "json")
                .body(widget);
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> text(
            @PathVariable("id") long id) {

        WidgetDto widget = widgets.get(id);

        if (widget == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .varyBy(HttpHeaders.ACCEPT)
                .header("X-Widget-Format", "text")
                .contentType(MediaType.TEXT_PLAIN)
                .body("widget:" + widget.id() + ":" + widget.name());
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<WidgetDto> create(
            @RequestBody CreateWidgetRequest input) {

        if (input == null ||
                input.name() == null ||
                input.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.getAndIncrement();
        WidgetDto created =
                new WidgetDto(id, input.name().trim(), true);

        widgets.put(id, created);

        URI location = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .path("/{id}")
                .buildAndExpand(id)
                .toUri();

        return ResponseEntity.created(location)
                .body(created);
    }
}
~~~

**Giải thích theo hợp đồng HTTP:**

1. **@RequestMapping("/api/widgets")** là prefix chung.
2. Hai **@GetMapping("/{id}")** được phân biệt bằng **produces**: JSON và text. Request Accept rõ ràng giúp Spring chọn handler.
3. **@PathVariable("id") long id** chuyển path segment sang long; input không phải số có thể bị từ chối 400.
4. **ResponseEntity.notFound().build()** tạo **404** không có body trong demo, không lộ persistence exception.
5. **ResponseEntity.ok()** tạo 200; **header("X-Widget-Format", ...)** là header quan sát được để test.
6. **varyBy(HttpHeaders.ACCEPT)** chủ động đặt **Vary: Accept** để cache biết hai representations phụ thuộc Accept. Không phải mọi Spring MVC response tự thêm Vary: Accept.
7. **CacheControl.noStore()** đặt **Cache-Control: no-store** cho JSON response, giúp test header nhưng không thay security/caching toàn hệ thống.
8. **@PostMapping(consumes=JSON, produces=JSON)** giới hạn định dạng request/response.
9. **@RequestBody** dùng Jackson deserialize JSON thành record CreateWidgetRequest; JSON sai cú pháp thường bị MVC từ chối 400 trước khi vào method.
10. **Validation name rỗng** diễn ra trong controller để demo không cần Bean Validation dependency; production nên dùng Jakarta Validation + @Valid khi phù hợp.
11. **ConcurrentHashMap** giữ dữ liệu demo trên một instance; **AtomicLong** phát ID khi có POST đồng thời trong process.
12. **ResponseEntity.created(location)** đặt **201 Created** và **Location** từ actual request URI (thông qua ServletUriComponentsBuilder), không nối cứng localhost.
13. **POST thành công trả WidgetDto JSON**, và tài nguyên mới thật sự được lưu vào map để GET bằng Location có thể thành công.
14. **No security** trong demo, vì vậy không dùng đoạn code này cho API chứa dữ liệu nhạy cảm mà không thêm authentication/authorization.

### 5.6. Một số điểm cần suy nghĩ

**Hai GET cùng path, khác produces có hợp lệ không?** Có: produces là một phần điều kiện request mapping. Tuy nhiên khi client gửi **Accept: */*** hoặc không gửi Accept, hai variants có thể cạnh tranh và selection phụ thuộc cách mapping/converters được cấu hình. API public nên quy định default representation rõ ràng hoặc thiết kế route/negotiation không mơ hồ; các tests của bài chủ động gửi Accept tương ứng. Không đánh đồng Accept text/html của browser với Accept application/json của REST client.

**Tại sao no-store chỉ ở JSON?** Đó là lựa chọn minh họa để kiểm header. Một ứng dụng production cần cache policy nhất quán cho tất cả representations có cùng sensitivity; phần text trong demo được tạo chỉ để học content negotiation, không phải quy tắc cache chuẩn.

**Location sau proxy:** đường dẫn được dựng từ request hiện tại. Nếu app đứng sau ingress HTTPS nhưng backend chỉ thấy http://service:8080, Location có thể trỏ sai scheme/host. Có thể dùng **server.forward-headers-strategy** khi proxy đáng tin cậy, và kiểm qua public gateway. Không chấp nhận forwarded headers không được sanitize vì nguy cơ host-header poisoning.

## 6. Chạy API trước khi tự động kiểm thử

Ở thư mục project:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Giữ server chạy trong terminal thứ nhất, thử ở terminal thứ hai. Lưu ý **mvn clean test** chạy các test trong phần sau khi bạn đã tạo files; nếu mới chỉ thêm app main/DTO/controller mà chưa có tests thì nó chỉ compile/test những gì có.

### 6.1. JSON response

~~~bash
curl -si \
  -H 'Accept: application/json' \
  http://localhost:8080/api/widgets/1
~~~

Kỳ vọng status **200**, Content-Type tương thích **application/json**, Vary chứa Accept, Cache-Control no-store và X-Widget-Format=json.

Body JSON về mặt dữ liệu:

~~~json
{
  "id": 1,
  "name": "Spring MVC",
  "active": true
}
~~~

Không đòi JSON phải có đúng thứ tự các keys hay whitespace như ví dụ.

### 6.2. Text representation

~~~bash
curl -si \
  -H 'Accept: text/plain' \
  http://localhost:8080/api/widgets/1
~~~

Kỳ vọng **200**, Content-Type tương thích **text/plain**, X-Widget-Format=text, Vary có Accept. Body exact:

~~~text
widget:1:Spring MVC
~~~

Body text này không phải JSON, nên không dùng jsonPath để kiểm.

### 6.3. Chấp nhận response type không hỗ trợ

~~~bash
curl -si \
  -H 'Accept: application/xml' \
  http://localhost:8080/api/widgets/1
~~~

Hai handler GET chỉ produces JSON/text nên khi request đòi XML, Spring MVC sẽ từ chối content negotiation với **406 Not Acceptable**. Không dự đoán exact error body vì MVC/Boot error handling có thể thay đổi.

### 6.4. Tạo tài nguyên với JSON

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"name":"Test Widget"}' \
  http://localhost:8080/api/widgets
~~~

Kỳ vọng **201 Created**, Location có dạng **http://localhost:8080/api/widgets/100** trên một instance mới khởi động, body có:

~~~json
{
  "id": 100,
  "name": "Test Widget",
  "active": true
}
~~~

**ID 100 chỉ chắc chắn khi đây là request create đầu tiên trong một process mới.** Nếu test hoặc request khác đã tạo data, ID có thể tăng. Test tự động phải lấy ID thực từ response rồi đối chiếu Location, không cố định 100.

### 6.5. Request body media type sai

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data-binary 'name=BadRequestType' \
  http://localhost:8080/api/widgets
~~~

Kỳ vọng **415 Unsupported Media Type** vì @PostMapping chỉ consumes application/json.

### 6.6. Malformed JSON

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"name":' \
  http://localhost:8080/api/widgets
~~~

Kỳ vọng **400 Bad Request** từ Jackson/Spring MVC message conversion. Đây là lỗi cú pháp JSON khác với lỗi business validation.

### 6.7. Tài nguyên không tồn tại

~~~bash
curl -si \
  -H 'Accept: application/json' \
  http://localhost:8080/api/widgets/999
~~~

Kỳ vọng **404 Not Found**. Trong demo controller trả ResponseEntity.notFound().build(), nên không nên hardcode một JSON error body.

### 6.8. HTTP method không được khai báo

~~~bash
curl -si \
  -X DELETE \
  -H 'Accept: application/json' \
  http://localhost:8080/api/widgets/1
~~~

Kỳ vọng **405 Method Not Allowed**, vì path có GET nhưng không có DELETE handler. HTTP response có thể có **Allow** do MVC xử lý, nhưng thứ tự hoặc tập methods (bao gồm HEAD/OPTIONS) có thể khác; không nên assert một chuỗi Allow nguyên văn nếu không là hợp đồng explicit.

## 7. Kiểm mapping, status, headers, JSON bằng @WebMvcTest + MockMvc

**@WebMvcTest(WidgetController.class)** nạp web slice và tự cấu hình MockMvc. Controller demo không phụ thuộc service ngoài nên test slice độc lập; trong app thật, dùng @MockBean cho service dependencies theo API Spring Boot 3.3.

Tạo **src/test/java/com/example/webcontract/WidgetControllerMvcTests.java**:

~~~java
package com.example.webcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(WidgetController.class)
class WidgetControllerMvcTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void getJsonMatchesMappingStatusHeadersAndFields()
            throws Exception {
        mvc.perform(get("/api/widgets/{id}", 1)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        HttpHeaders.VARY, "Accept"))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().string(
                        "X-Widget-Format", "json"))
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Spring MVC"))
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.passwordHash").doesNotExist());
    }

    @Test
    void getTextUsesDifferentRepresentation()
            throws Exception {
        mvc.perform(get("/api/widgets/1")
                        .accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        HttpHeaders.VARY, "Accept"))
                .andExpect(header().string(
                        "X-Widget-Format", "text"))
                .andExpect(content().string("widget:1:Spring MVC"));
    }

    @Test
    void unsupportedAcceptReturns406() throws Exception {
        mvc.perform(get("/api/widgets/1")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void unknownWidgetReturns404() throws Exception {
        mvc.perform(get("/api/widgets/999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(delete("/api/widgets/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void postConsumesJsonAndReturns201Location()
            throws Exception {
        String body = mapper.writeValueAsString(
                new CreateWidgetRequest("Sách Java"));

        MvcResult result = mvc.perform(
                    post("/api/widgets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(jsonPath("$.name").value("Sách Java"))
                .andExpect(jsonPath("$.active").value(true))
                .andReturn();

        JsonNode created = mapper.readTree(
                result.getResponse().getContentAsString());
        long id = created.path("id").asLong();

        assertTrue(id >= 100L);

        String location =
                result.getResponse().getHeader(HttpHeaders.LOCATION);
        assertTrue(location.endsWith("/api/widgets/" + id));

        mvc.perform(get("/api/widgets/{id}", id)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value((int) id))
                .andExpect(jsonPath("$.name").value("Sách Java"));
    }

    @Test
    void postTextBodyReturns415() throws Exception {
        mvc.perform(post("/api/widgets")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("name=wrong"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void postMalformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/widgets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void postBlankNameReturns400() throws Exception {
        mvc.perform(post("/api/widgets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"  \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void noInternalFieldInJson() throws Exception {
        MvcResult response = mvc.perform(
                    get("/api/widgets/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode node = mapper.readTree(
                response.getResponse().getContentAsString());

        assertEquals(1L, node.get("id").longValue());
        assertTrue(node.get("active").isBoolean());
        assertFalse(node.has("passwordHash"));
    }
}
~~~

**Lưu ý imports:** Các static imports cho MockMvcRequestBuilders và MockMvcResultMatchers là bắt buộc. Java code sử dụng **MvcResult** để đọc giá trị ID được tạo runtime và so sánh Location. Không cần tự tạo URL cố định với ID 100 khi test.

### Phân tích từng nhóm assertions

| Yêu cầu | Assertion MockMvc | Giá trị |
| --- | --- | --- |
| GET thành công | **status().isOk()** | Đúng HTTP 200. |
| JSON media type | **content().contentTypeCompatibleWith(APPLICATION_JSON)** | Không nhầm text/plain chứa JSON. |
| Custom header | **header().string("X-Widget-Format", "json")** | Mapping chọn JSON variant. |
| Cache header | **header().string(CACHE_CONTROL, "no-store")** | Response policy được áp. |
| Vary header | **header().string(VARY, "Accept")** | Cache phân biệt hai representations. |
| JSON number | **jsonPath("$.id").value(1)** | id có numeric value đúng. |
| JSON string | **jsonPath("$.name").value("Spring MVC")** | Chuỗi domain đúng. |
| JSON boolean | **jsonPath("$.active").value(true)** | boolean đúng, không phải "true". |
| Không lộ field | **jsonPath("$.passwordHash").doesNotExist()** | Negative JSON contract. |
| Text variant | **content().string(...)** | Body plain text chính xác. |
| Wrong Accept | **status().isNotAcceptable()** | 406, không silently trả XML. |
| Wrong Content-Type | **status().isUnsupportedMediaType()** | 415. |
| Missing item | **status().isNotFound()** | 404. |
| Wrong method | **status().isMethodNotAllowed()** | 405. |
| POST created | **status().isCreated()**, Location exists | 201 + resource link. |
| Malformed body | **status().isBadRequest()** | 400. |

**Không nên assert raw JSON string theo thứ tự field.** Jackson có thể thay thứ tự properties mà contract vẫn đúng. JSONPath và JsonNode kiểm giá trị trực tiếp. Với JSON arrays, test count/membership/order nếu order thật sự được API cam kết.

**Không phải lỗi nào cũng có JSON error document.** Các tests ở trên chỉ kiểm 400/404/405/406/415 status vì default framework error body có thể thay đổi theo MVC/Boot server layer. Nếu app có @ControllerAdvice trả **ProblemDetail** theo schema được công bố, hãy thêm assertions cho application/problem+json và các fields được contract hóa.

## 8. @WebMvcTest không nạp business service bình thường

Ví dụ ở một dự án thật:

~~~java
@RestController
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/api/orders/{id}")
    OrderDto get(@PathVariable long id) {
        return service.get(id);
    }
}
~~~

Đây là **snippet minh họa phụ thuộc OrderService/OrderDto không có trong demo**, không phải chương trình độc lập.

Nếu dùng **@WebMvcTest(OrderController.class)**, Spring không tự scan regular @Service/@Repository. Vì vậy test phải cung cấp collaborator. Trong Spring Boot 3.3, ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerSliceTests {

    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService service;

    // Mockito.when(service.get(42L)).thenReturn(...);
    // Then mvc.perform(get("/api/orders/42")) andExpect(...).
}
~~~

Imports cần có **org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest**, **org.springframework.boot.test.mock.mockito.MockBean**, **org.springframework.beans.factory.annotation.Autowired**, **org.springframework.test.web.servlet.MockMvc**. Đây là snippet định hướng, chưa định nghĩa OrderService/OrderDto hay test method.

Nếu test báo **NoSuchBeanDefinitionException / failed to load ApplicationContext**, kiểm whether collaborator phải được mocked/imported. Đừng đổi sang @SpringBootTest chỉ để giấu mọi configuration problem mà chưa cân nhắc test scope.

### Security FilterChain trong test slice

**@WebMvcTest** có thể kéo các Security configurations/filters tương ứng khi Spring Security có trên classpath. Một POST test có thể trả **403 CSRF** dù controller đúng. Khi đó:

- Dùng **spring-security-test**, **@WithMockUser**, **SecurityMockMvcRequestPostProcessors.csrf()**, hoặc mock authentication đúng hợp đồng.
- Test cả **401/403** và role-based authorization như production.
- Không tắt filter chain toàn bộ chỉ để làm test xanh nếu security là một phần hợp đồng.
- Nếu bạn cố ý test controller độc lập security, ghi rõ phạm vi và có security integration tests khác.

Demo chính không thêm Spring Security để tập trung mapping/status/headers/JSON/media type, nên những status security cần được test khi ứng dụng thật có dependency ấy.

## 9. @SpringBootTest + @AutoConfigureMockMvc: full context nhưng vẫn mock HTTP

Đây là lựa chọn khi cần MVC mapping cùng với thực tế application configuration, filters, custom converters, ControllerAdvice, interceptors hoặc wiring services.

Tạo **src/test/java/com/example/webcontract/WidgetFullContextMvcTests.java**:

~~~java
package com.example.webcontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WidgetFullContextMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void fullContextUsesSameJsonContract()
            throws Exception {

        mvc.perform(get("/api/widgets/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        HttpHeaders.VARY, "Accept"))
                .andExpect(jsonPath("$.name").value("Spring MVC"));
    }
}
~~~

**Điểm chính:** @SpringBootTest (mặc định MOCK) nạp **toàn ApplicationContext**, còn @AutoConfigureMockMvc tạo mock web testing infrastructure. Nó vẫn **không mở một HTTP socket**. Đừng hiểu @AutoConfigureMockMvc là tương đương RANDOM_PORT.

Tốc độ thường chậm hơn @WebMvcTest vì khởi tạo thêm beans; dùng khi cần kiểm integration của filters/advice/security/serialization config thật.

## 10. @SpringBootTest(RANDOM_PORT): test qua HTTP connector thật

Một test MockMvc không bắt được lỗi thấp hơn servlet stack hoặc infrastructure. Để test HTTP thật, khởi động embedded Tomcat trên random port rồi dùng **Java 17 HttpClient**.

Tạo **src/test/java/com/example/webcontract/WidgetLiveHttpTests.java**:

~~~java
package com.example.webcontract;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class WidgetLiveHttpTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path, String accept)
            throws Exception {

        HttpRequest req = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .header("Accept", accept)
                .GET()
                .build();

        return client.send(req,
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void jsonAndTextAreNegotiatedOverRealHttp()
            throws Exception {

        HttpResponse<String> json =
                get("/api/widgets/1", "application/json");

        assertEquals(200, json.statusCode());
        assertTrue(json.headers()
                .firstValue("content-type")
                .orElse("")
                .startsWith("application/json"));

        JsonNode data = mapper.readTree(json.body());

        assertEquals(1L, data.path("id").asLong());
        assertEquals("Spring MVC", data.path("name").asText());
        assertTrue(data.path("active").isBoolean());
        assertTrue(data.path("active").asBoolean());
        assertFalse(data.has("passwordHash"));

        HttpResponse<String> text =
                get("/api/widgets/1", "text/plain");

        assertEquals(200, text.statusCode());
        assertTrue(text.headers()
                .firstValue("content-type")
                .orElse("")
                .startsWith("text/plain"));
        assertEquals("widget:1:Spring MVC", text.body());

        assertEquals(406,
                get("/api/widgets/1", "application/xml")
                        .statusCode());
    }

    @Test
    void invalidRequestMediaTypeIs415()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + port + "/api/widgets"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "text/plain")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("wrong"))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(415, response.statusCode());
    }

    @Test
    void absentWidgetReturns404() throws Exception {
        assertEquals(404,
                get("/api/widgets/999", "application/json")
                        .statusCode());
    }
}
~~~

**Vì sao random port?** Khi CI hoặc developer đang chạy nhiều services, cố định 8080 có thể xung đột. @LocalServerPort nhận port thực của embedded server. Test không cần giả định application chính đang chạy ở terminal.

**Tại sao dùng Java HttpClient thay WebTestClient?** JDK 17 có sẵn java.net.http.HttpClient, nên dự án Servlet MVC không phải thêm reactive web dependencies chỉ để thử HTTP. Spring Boot 3.3 cũng có **TestRestTemplate** và có thể tích hợp **WebTestClient** nếu dependency thích hợp; API chọn theo nhu cầu. Tránh dùng API chỉ tồn tại ở Boot 4.x rồi dán vào code Boot 3.3.

**Đây vẫn chưa phải end-to-end public topology test.** Test qua 127.0.0.1 không kiểm TLS termination, Nginx rewrites, CDN caching hay Load Balancer. Các ranh giới đó cần một test khác trong environment tương ứng.

## 11. @JsonTest: kiểm serializer độc lập với HTTP

Nếu dự án có custom Jackson naming strategy, serializations hoặc JsonViews, lỗi có thể xuất hiện trước khi handler mapping liên quan. **@JsonTest** kiểm slice JSON mapping và ObjectMapper mà không mở web context.

Tạo **src/test/java/com/example/webcontract/WidgetJsonTests.java**:

~~~java
package com.example.webcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class WidgetJsonTests {

    @Autowired
    ObjectMapper mapper;

    @Test
    void recordFieldsHaveStableNamesAndTypes()
            throws Exception {

        WidgetDto widget =
                new WidgetDto(7L, "Kiểm thử JSON", true);

        String json = mapper.writeValueAsString(widget);
        JsonNode node = mapper.readTree(json);

        assertEquals(7L, node.path("id").asLong());
        assertEquals("Kiểm thử JSON",
                node.path("name").asText());
        assertTrue(node.path("active").isBoolean());
        assertTrue(node.path("active").asBoolean());
        assertFalse(node.has("internalMemo"));
    }

    @Test
    void inputRecordDeserializesCorrectly()
            throws Exception {

        CreateWidgetRequest request =
                mapper.readValue(
                        "{\"name\":\"Sách Java\"}",
                        CreateWidgetRequest.class);

        assertEquals("Sách Java", request.name());
    }
}
~~~

**@JsonTest** là một slice khác, không kết hợp đồng thời **@JsonTest** và **@WebMvcTest** trên cùng test class. Nên để chúng trong những class riêng theo mục đích. @JsonTest kiểm ObjectMapper/record type, **không** kiểm HTTP Content-Type, Accept, routing, status hoặc response headers.

### Tránh test implementation details không cần thiết

Không cần kiểm class name của internal Jackson converter hay số lượng beans nếu điều bạn thực sự muốn biết là **API trả JSON hợp đồng đúng**. Unit JSON tests hữu ích khi schema có custom serializers, nhưng integration test MVC vẫn phải xác minh representation qua HTTP.

## 12. Quy trình chạy và điều gì được chứng minh

Chạy toàn bộ test suite:

~~~bash
mvn clean test
~~~

Lệnh này build ứng dụng và chạy các lớp JUnit có tên kết thúc bằng Tests trong cấu trúc đã khai báo. Khi Maven Surefire/JUnit Jupiter được Spring Boot parent quản lý đúng, test phải chạy mà không cần server thủ công ở port 8080.

**Đầu ra Maven có thể khác nhau** theo môi trường, số CPU, dependency cache và logging, nên không ghi số giây/số dòng console cố định. Điều cần kiểm là Maven kết thúc **exit code 0**, các tests được thực thi và không có failures/errors/skips ngoài dự kiến.

Một ma trận kết quả:

| Test class | Web stack thật? | Điều kiểm |
| --- | --- | --- |
| WidgetJsonTests | Không | Jackson record serialization/deserialization, field names/types. |
| WidgetControllerMvcTests | Mock MVC slice | Mapping GET/POST, status 200/201/400/404/405/406/415, headers, JSON. |
| WidgetFullContextMvcTests | Full context nhưng mock requests | MVC + Boot app beans/filter/config wiring. |
| WidgetLiveHttpTests | Embedded server thật trên random port | JSON/text negotiation trên HTTP connector, Content-Type, 404, 406, 415. |

**Không báo “tests passed” nếu chưa chạy Maven thật.** Đoạn mã trong bài là tài liệu mẫu có thể dựng project để chạy; kết quả yêu cầu kiểm bằng lệnh sau khi tạo project. Bài Knowledge không đồng nghĩa đã thực thi build trong workspace của người đọc.

### Vì sao những negative tests có giá trị cao?

Happy path GET 200 thường dễ đúng. Các lỗi production hay nằm ở ranh giới:

- Một endpoint vô tình chấp nhận text/plain thành JSON dẫn tới inconsistent behavior.
- Một request Accept application/xml bị converter fallback thành content type không mong muốn.
- Lỗi malformed JSON trả 500 thay vì 400.
- Resource không tồn tại nhưng service trả null + 200.
- POST tạo thành công nhưng quên **Location**.
- API có dữ liệu đúng nhưng header **Content-Type** sai.
- Custom media type version chưa được hỗ trợ nhưng API silently trả default.
- Header cache Vary thiếu làm CDN cache nhầm JSON/text variants.
- JSON internal field xuất hiện do serialize entity thay vì DTO.

Thêm test cho **các ranh giới thất bại** thường phòng ngừa regression hiệu quả hơn việc lặp nhiều happy-path tests gần giống nhau.

## 13. Viết test theo HTTP contract thay vì implementation

Một test tốt có dạng **Given – When – Then**:

- **Given:** có widget ID 1, client chấp nhận application/json.
- **When:** GET /api/widgets/1.
- **Then:** HTTP 200, Content-Type application/json, Vary Accept, id là number 1, name đúng, active là boolean true và không có internal fields.

Nếu đổi thuật toán lookup từ Map sang JDBC nhưng hợp đồng HTTP không đổi, test controller contract lý tưởng vẫn xanh. Nếu đổi URL hoặc schema field public, test đỏ vì đó có thể là breaking change.

### Đừng assert quá ít

Không tốt:

~~~java
mvc.perform(get("/api/widgets/1"))
        .andExpect(status().isOk());
~~~

Test này không phát hiện endpoint trả text thay JSON, body thiếu, header sai hay giá trị sai. Đặc biệt trong demo có nhiều representations cùng URL, phải gửi Accept.

### Đừng assert quá nhiều detail ngoài contract

Cũng không tốt nếu assert:

- JSON field order phải cố định dù client không quan tâm.
- Exact auto-generated error body mặc định chưa được công bố.
- Exception stacktrace/message trong 4xx.
- Nội dung full Date/Server headers của embedded Tomcat hoặc thứ tự Allow.
- Thời gian response phải luôn dưới 1ms trong CI không kiểm soát.
- Location luôn có port 8080 khi server chạy RANDOM_PORT.

Nên test những gì client thực sự cần và application cam kết.

### Khi nào dùng content().json?

MockMvc có thể so sánh JSON theo cấu trúc:

~~~java
mvc.perform(get("/api/widgets/1")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().json(
        "{\"id\":1,\"name\":\"Spring MVC\",\"active\":true}"
    ));
~~~

Đây là snippet nằm trong một JUnit test đã có mvc/imports, không phải class độc lập. Với nhiều schema phức tạp, sử dụng **jsonPath** hoặc Jackson **JsonNode** giúp phân biệt numeric/string/boolean và điều kiện field missing rõ hơn. So sánh cấu trúc còn tránh phụ thuộc whitespace và field ordering.

## 14. Test headers đúng cách

**Header có thể lặp hoặc có danh sách giá trị**, nên chọn matcher phù hợp. Các headers hay kiểm trong Spring MVC:

| Header | Mục đích | Cách test |
| --- | --- | --- |
| **Content-Type** | Media type của response | contentTypeCompatibleWith(...), hoặc contentType(...) nếu contract exact. |
| **Location** | URI resource mới sau 201 | header exists + kiểm URI path/host theo deployment. |
| **Cache-Control** | Cacheability của representation | header string, hoặc parse/cache policy theo requirement. |
| **Vary** | Cache key thay đổi theo request header | Kiểm chứa Accept (không hardcode thứ tự nếu nhiều values). |
| **ETag** | Representation validator | Test header/conditional GET If-None-Match và 304 nếu app implement. |
| **Last-Modified** | Validator theo thời gian | Test conditional GET khi có. |
| **Allow** | Supported methods ở 405/OPTIONS | Kiểm có methods cần thiết, không cần ép exact order. |
| **Content-Disposition** | File download filename/attachment | Header assertion + encoding/filename semantics. |
| **Set-Cookie** | Session/cookie flags | Với security test, kiểm Secure, HttpOnly, SameSite theo context. |
| **X-Widget-Format** | Custom representation signal của demo | Header exact json/text. |

**Không tự giả định mỗi response có ETag hoặc Cache-Control.** Chúng phải được controller, middleware hoặc container tạo. Trong demo, Cache-Control no-store chỉ được thêm cho JSON GET, còn Vary do code gọi **varyBy(HttpHeaders.ACCEPT)**; không khẳng định Spring luôn tự phát Vary: Accept.

### Vary và caching khi content negotiation

Hai representations của cùng resource có thể có chung URL nhưng khác Accept. Nếu CDN/shared cache bỏ qua Accept và response không có Vary phù hợp, client cần text có thể nhận JSON hoặc ngược lại. Vì vậy test **Vary: Accept** có giá trị thực khi API hỗ trợ nhiều variants cùng URI.

Ngoài Accept, response có thể vary theo **Accept-Encoding**, **Accept-Language**, **Origin** hoặc những headers khác tùy behavior. Không nhầm Vary với header tự cho phép CORS, cũng không dùng **Vary: \*** thay cho thiết kế cache policy.

### ETag và 304: một bài test mở rộng

Nếu API triển khai ETag, test nên có hai request:

~~~text
1. GET /resource -> 200, ETag: "v1"
2. GET /resource, If-None-Match: "v1" -> 304 Not Modified
~~~

Đây là một **kịch bản mở rộng**, không phải output của demo WidgetController vì demo không thêm ETag. Với 304, body thường không có representation; kiểm status, header và conditional request semantics, không ép JSON body như response 200.

## 15. Content negotiation chi tiết: Accept, q-values và wildcards

Một client có thể gửi:

~~~http
Accept: application/json, text/plain;q=0.2
~~~

**q** là quality preference; client ưu tiên JSON hơn text trong ví dụ. Spring MVC xem xét compatibility và preference khi chọn handler/converter. Với **Accept: application/json** và **Accept: text/plain** đơn giản, demo chọn rõ variant.

Một số tình huống cần test riêng trong API thật:

- **Accept: */*** hoặc không có Accept: có thể cho phép nhiều variants. Nếu API đăng ký nhiều @GetMapping cùng path chỉ khác produces, cần định nghĩa/default rõ ràng và test tránh ambiguity.
- **Accept: application/*:** có thể compatible với application/json, tùy available variants.
- **Accept: application/xml:** demo không hỗ trợ XML, kỳ vọng 406.
- **Accept: application/json;q=0.2,text/plain;q=0.9:** test ưu tiên text nếu contract và negotiation cho phép.
- **Accept: application/vnd.acme.widget+json:** vendor media type có thể cần produces/converter riêng; không giả định mapping application/json bao phủ mọi structured syntax suffix.
- **Accept-Language:** có thể quyết định locale of representation, nhưng không tự đổi JSON thành text/plain.
- **Accept-Encoding:** là nội dung nén (gzip/br), **không phải** chọn JSON vs text representation của controller. Thường do connector/proxy compression xử lý.
- **URL .json/.xml suffix:** Spring MVC hiện đại không nên dựa vào suffix/path extension negotiation mặc định; ưu tiên Accept hoặc cấu hình rõ khi thật sự cần.

**HTTP 406 là kết quả hợp lệ khi server không thể tạo representation mà client yêu cầu.** Một số server/API có thể fallback sang default representation, nên test status theo **cấu hình hợp đồng thực**, không áp đặt 406 lên mọi endpoint thế giới.

### consumes trước hay produces trước?

Spring MVC xem nhiều điều kiện mapping. Với một request đồng thời sai **Content-Type** và **Accept**, status lỗi có thể phụ thuộc handler matching/resolvers. **Đừng viết một test kỳ vọng vừa 406 vừa 415** trên cùng request sai cả hai. Kiểm từng lỗi độc lập: wrong consumes + Accept hợp lệ → 415; correct consumes + wrong Accept → 406.

### Content-Type có charset parameter

Một response có thể ghi:

~~~http
Content-Type: text/plain;charset=UTF-8
~~~

Trong các trường hợp charset được thêm, **contentTypeCompatibleWith(MediaType.TEXT_PLAIN)** thích hợp hơn assert exact **"text/plain"** khi contract chỉ yêu cầu media type. Nếu contract yêu cầu charset cụ thể, kiểm riêng **Content-Type** parameters và byte decoding.

## 16. Serialization errors và exception handling

Một POST body không hợp lệ có nhiều loại lỗi:

| Input | Vùng lỗi | Status thường dùng |
| --- | --- | --- |
| JSON syntax sai | HttpMessageNotReadableException/converter | **400** |
| JSON hợp lệ nhưng name rỗng | Business validation trong demo | **400** |
| Path id="abc" nhưng controller yêu cầu long | Argument type conversion | **400** |
| Content-Type=text/plain nhưng consumes=application/json | Mapping/media restriction | **415** |
| Accept=application/xml nhưng chỉ produces JSON/text | Negotiation | **406** |
| Không có widget trong in-memory map | Domain lookup | **404** |
| DELETE vào URI chỉ hỗ trợ GET | Method restriction | **405** |
| Có authenticated user nhưng không đủ quyền | Security authorization trong app có security | **403** |
| Không authenticated trên resource yêu cầu đăng nhập | Security challenge/entry point | **401** |
| Service bug/unhandled exception | Server error | **500** |

**Nội dung lỗi có thể khác khi dùng @ControllerAdvice/ProblemDetail**. Spring Framework có **ProblemDetail**/ErrorResponse APIs, và Spring Boot có tùy chọn bật xử lý Problem Details trong một số cấu hình. Muốn test **application/problem+json**, hãy implement và công bố error contract rõ, rồi assert **type/title/status/detail** đúng, không dựa vào default body tình cờ.

**Đừng trả raw exception.getMessage() cho client** khi nó có thể chứa SQL/URI/PII. Test thông tin lỗi được phép expose và rằng stacktrace không nằm trong production error responses. Ngay cả khi status đúng, dữ liệu nhạy cảm ở body vẫn là regression.

## 17. JSON shape, Unicode và null vs missing

Một JSON contract không chỉ là "body có id". Cần quan sát:

~~~json
{
  "id": 7,
  "name": "Sách Java",
  "active": true,
  "tags": ["spring", "web"],
  "description": null
}
~~~

Các phân biệt:

- **id=7** là number; **"7"** là string.
- **active=true** là boolean; **"true"** là string.
- **tags=[]** là array rỗng; **tags=null** là null; **tags** vắng mặt là missing.
- **description=null** khác **description=""** và khác không có field.
- **name="Sách Java"** phải round-trip Unicode; đừng giả định mọi client dùng default platform encoding giống nhau.
- JSON **object field order** không quan trọng, nhưng array element order có thể quan trọng nếu API công bố sorting.
- Float có rounding/tolerance: currency thường cần BigDecimal và representation contract được xác định, không test binary float equality một cách bất cẩn.

Spring Boot/Jackson có thể thay behavior với **@JsonInclude**, **@JsonIgnore**, **@JsonProperty**, custom serializers/deserializers hoặc **spring.jackson.\*** properties. Hãy viết test cấp JsonTest và MVC để khóa đúng representation mà client thấy.

Khi muốn không expose sensitive fields, dùng explicit DTO; không đưa thẳng JPA entity với toàn bộ fields ra response.

## 18. Vì sao tests có thể flaky và cách làm ổn định

Một test HTTP đáng tin phải độc lập, determinism cao và không cần mạng ngoài.

**Những nguồn flakiness thường gặp:**

- Cố định **server.port=8080** trong integration tests thay vì RANDOM_PORT.
- Dùng dữ liệu global/static qua nhiều test methods và assert ID luôn là 100.
- Phụ thuộc JUnit test method execution order.
- Test với real DB/shared staging có state từ lần chạy trước.
- Assert timestamp, random UUID, content length theo số byte không ổn định.
- Client timeout quá ngắn trong CI.
- Kiểm json string raw order thay vì parse tree.
- Dùng sleep để đợi server trong khi @SpringBootTest đã cung cấp lifecycle.
- Dùng wildcard Accept khiến có hai mapping cùng path cạnh tranh.
- Chạy tests bằng một profile khác mà không cố định những production config ảnh hưởng converters/security.
- Dùng @Transactional trên RANDOM_PORT rồi kỳ vọng server transaction bị rollback bởi client test thread.

**Mấu chốt về @Transactional + RANDOM_PORT:** client và server xử lý ở các threads/process-boundary riêng. Một transaction được tạo trong test method không bao trùm transaction do server request mở. Vì vậy rollback mặc định của test không nhất thiết rollback DB work từ HTTP request; cần cleanup strategy phù hợp cho integration tests dùng real DB.

**Cách ổn định:**

- Sử dụng in-memory/fake service cho MVC slice, mock dependency khi cần.
- Dùng RANDOM_PORT cho real HTTP tests.
- Dùng unique test data hoặc cleanup transaction/environment, không phụ thuộc thứ tự.
- Tách tests có external database/broker vào integration test suite riêng.
- Kiểm headers/JSON semantics, không kiểm những giá trị framework-generated không quan trọng.
- Có test profile cho auth/locale/timezone/serialization policies cần thiết.
- Khi lỗi, dùng **andDo(print())** của MockMvc để xem request/response mock có kiểm soát, nhưng **không bật raw body/header prints trên CI production data** vì logs có thể chứa secret.
- Nếu có time-sensitive tests, dùng injected Clock/fake clock thay Thread.sleep khi có thể.

## 19. Security, filters, cookies và content negotiation

**Không tắt Spring Security chỉ để tests POST 201.** Nếu API production yêu cầu login hoặc CSRF, 401/403 là một phần hợp đồng. Sử dụng Spring Security test support và appropriate test principals/tokens. Kiểm đúng:

- Unauthenticated → challenge/401 hoặc redirect login theo config.
- Authenticated but forbidden → 403.
- Cookie/session flags và token transport.
- CSRF rejection với unsafe methods trong mô hình cookie/session.
- CORS preflight OPTIONS và Vary: Origin khi có cross-origin browser clients.
- Content negotiation của error messages: 401/403 có JSON/ProblemDetail đúng.
- Không lộ token/password trong response body, Location hoặc custom headers.

**@WebMvcTest** có thể load các filters có trong web slice, và **@AutoConfigureMockMvc(addFilters=false)** có thể bỏ filters khi test tập trung thuần controller. Dùng tùy chọn đó chỉ có chủ đích, và phải có các integration tests khác cho security filters. Nếu tests chạy xanh vì bỏ filters, không được báo API production đã được bảo vệ đúng.

**CORS khác content negotiation.** CORS dùng Origin/Access-Control-Allow-* và browser policy; Accept chọn representation media type. Cùng một response có thể cần cả Vary: Accept và Vary: Origin nếu response thay đổi theo Origin và cache semantics yêu cầu.

## 20. Reverse proxy, host, Location và TLS

Trong production:

~~~text
Client HTTPS https://api.example.test/catalog/api/widgets
    |
    v
Nginx / ingress [TLS termination, path rewrite]
    |
    v
Spring Boot http://widgets-service:8080/api/widgets
~~~

Nếu controller xây Location từ request nội bộ mà không xử lý trusted forwarded headers, HTTP 201 có thể trả **Location: http://widgets-service:8080/api/widgets/100**, sai đối với client ngoài.

Spring Boot có cấu hình:

~~~properties
# Chi bat khi proxy bien xoa/gia tri hoa Forwarded headers
server.forward-headers-strategy=framework
~~~

Hoặc native strategy khi thích hợp. Nhưng **Forwarded/X-Forwarded-Host/X-Forwarded-Proto/X-Forwarded-Prefix phải đến từ proxy đáng tin cậy**, không thể tin headers client internet gửi tùy ý. Nếu không, attacker có thể thay host của Location hoặc link bằng hostname độc hại.

Một test tại localhost không thể chứng minh public HTTPS Location chính xác. Cần một integration/e2e test qua ingress hoặc môi trường test mô phỏng forwarded headers được sanitize:

1. POST qua public URL.
2. Kiểm status 201.
3. Kiểm **Location** trỏ đúng https/public host/prefix.
4. GET chính Location trả 200.
5. Kiểm Host/Forwarded spoofing không thay Location khi request qua edge.

## 21. Các lỗi phổ biến khi viết MockMvc tests

| Triệu chứng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| @WebMvcTest không load ApplicationContext | Controller thiếu @Service collaborator | @MockBean hoặc @Import scoped dependency. |
| MockMvc = null | Không @WebMvcTest/@AutoConfigureMockMvc hoặc thiếu @Autowired | Dùng đúng annotations/imports. |
| 200 nhưng JSON body sai | Test chỉ assert status | jsonPath + Content-Type + schema/field types. |
| 404 khi gọi controller | Sai @RequestMapping prefix/context path | Kiểm mappings và path variables. |
| 405 thay vì 404 | URL có handler nhưng HTTP method không hỗ trợ | Kiểm method và Allow/handler config. |
| 406 khi GET | Accept không compatible với produces | Gửi đúng Accept; test negative contract. |
| 415 khi POST | Content-Type không compatible với consumes | Content-Type JSON và body JSON hợp lệ. |
| 400 khi gửi JSON | Malformed body hoặc argument conversion/validation | Kiểm request body, converter và error contract. |
| 403 khi POST tests | CSRF/security filter | Dùng security-test, csrf(), principal hợp lệ; không tắt security vô thức. |
| Test content type exact bị fail | Charset/media parameters thêm vào | Dùng contentTypeCompatibleWith khi contract cho phép. |
| Test Location fail trong RANDOM_PORT | Hardcode 8080 hoặc host | Lấy Location thực, parse/so path theo contract. |
| Vary header không có | Code không thêm varyBy, cache proxy không cấu hình | Thêm Vary khi response thật sự thay đổi theo Accept. |
| JSON id đôi khi là 100, đôi khi 101 | Shared mutable state, test order | Đọc ID được tạo, không dự đoán sequence cố định. |
| @SpringBootTest không mở socket | Dùng default MOCK environment | Chọn RANDOM_PORT. |
| @WebMvcTest pass nhưng deployment lỗi | MockMvc không test TLS/connector/proxy | Thêm real HTTP + e2e tests. |
| MockMvc error body khác curl | Container error handling không chạy đầy đủ | Test server thật nếu error page format là contract. |
| jsonPath miss field vì snake_case | Custom Jackson naming strategy | Test schema theo API, không theo Java property. |
| Response JSON thứ tự khác | So sánh raw strings | Parse JSON/JsonNode. |
| .accept(MediaType.APPLICATION_JSON) trên POST nhưng 415 | Request Content-Type vẫn sai | Phân biệt Accept với Content-Type. |
| WebFlux handler test bị import sai | Dùng MockMvc thay WebTestClient/@WebFluxTest | Kiểm runtime Servlet vs Reactive. |

## 22. Checklist kiểm thử API trước release

- [ ] GET/POST/PATCH/DELETE mapping theo HTTP method và URL đúng.
- [ ] Path variable/query param conversion và validation có test.
- [ ] Mỗi happy path có status phù hợp (200/201/204) và response body đúng.
- [ ] Error paths có 400/401/403/404/405/406/409/415 theo hợp đồng thật, không ép status không áp dụng.
- [ ] Response Content-Type phù hợp body; request Content-Type/Accept được test riêng.
- [ ] JSON property names, numeric/boolean/string types, nested/array, null/missing và Unicode đúng.
- [ ] Không lộ các fields nội bộ/secret trong JSON.
- [ ] 201 Created có Location trỏ tài nguyên đã tạo và client theo được URL.
- [ ] Cache-Control, Vary, ETag, Last-Modified và security headers được kiểm khi API có contract tương ứng.
- [ ] Multi-representation endpoint có các tests Accept khác nhau và negative 406.
- [ ] Unsupported request media type có negative 415; malformed JSON 400.
- [ ] Không assert field order hoặc internal server error body nếu không được contract hóa.
- [ ] Test @WebMvcTest với fake service/mocks thích hợp; không khởi động DB vô ích.
- [ ] Test full context bằng @SpringBootTest + @AutoConfigureMockMvc khi có filters/advice/converters.
- [ ] Test connector thật bằng @SpringBootTest(RANDOM_PORT) cho HTTP behavior.
- [ ] Nếu app có security, test 401/403/CSRF/CORS cùng filters thật.
- [ ] Nếu có API gateway, test public HTTPS URL, Location và forwarded-header trust.
- [ ] Không cố định ID, random port, timestamps hoặc thứ tự chạy tests.
- [ ] Chạy mvn clean test trên CI, đo tests failures và xác nhận test classes thực sự được chạy.
- [ ] Đồng bộ docs/OpenAPI với media types, status, headers và error schema đã test.
- [ ] Khi upgrade Spring Boot/Jackson/Spring Security, chạy lại contract tests và cập nhật behavior theo version.

## 23. Câu hỏi tự kiểm tra

**1. Vì sao test chỉ assert status().isOk() chưa đủ?**  
Vì không phát hiện sai Content-Type, headers, JSON shape, giá trị hoặc media negotiation.

**2. @WebMvcTest có mở Tomcat thật không?**  
Không. Nó cấu hình MVC slice/MockMvc và mock servlet environment.

**3. @SpringBootTest không có webEnvironment được cấu hình có mở socket HTTP thật không?**  
Không. Mặc định MOCK.

**4. @SpringBootTest(RANDOM_PORT) để làm gì?**  
Khởi động embedded HTTP server thật ở cổng ngẫu nhiên, kiểm qua network.

**5. @AutoConfigureMockMvc có biến @SpringBootTest thành real HTTP integration test không?**  
Không. Nó cung cấp MockMvc trong full context.

**6. Accept và Content-Type khác nhau ở đâu?**  
Accept thể hiện response media types client muốn; request Content-Type thể hiện media type của body gửi lên.

**7. Khi nào mong đợi 406?**  
Khi server không thể/không muốn trả representation phù hợp Accept theo cấu hình.

**8. Khi nào mong đợi 415?**  
Khi request entity media type không được endpoint hoặc converter hỗ trợ.

**9. JSON syntax sai nhưng Content-Type đúng thường trả gì?**  
400 Bad Request nếu converter không đọc được body.

**10. GET /api/widgets/999 trong demo trả gì?**  
404, do controller không tìm được item.

**11. DELETE trên URL chỉ có GET thường trả gì?**  
405 Method Not Allowed.

**12. Vì sao dùng Vary: Accept?**  
Vì cùng URL có representations JSON/text khác nhau theo Accept, cache cần phân biệt.

**13. 201 Created nên kiểm header nào?**  
Location, đồng thời có thể theo location để kiểm resource mới tồn tại.

**14. Vì sao không cố định ID 100 trong POST test?**  
Vì state có thể thay đổi; nên đọc ID thực từ response và kiểm Location khớp.

**15. JsonPath kiểm được type không?**  
Có thể kết hợp JSONPath, JsonNode và type-specific assertions để phân biệt boolean/string/number.

**16. Nếu dùng Spring Security trong app thật, vì sao MockMvc POST có thể trả 403?**  
Do CSRF hoặc authorization; cần security-test và principal/CSRF hợp lệ.

**17. Có nên tin absolute Location do Forwarded headers từ client bất kỳ không?**  
Không. Chỉ dùng forwarded metadata từ proxy đã được cấu hình tin cậy.

**18. @JsonTest có kiểm HTTP status/Content-Type không?**  
Không. Nó kiểm serialization/deserialization ngoài web HTTP mapping.

**19. Vì sao MockMvc success không bảo đảm ingress production hoạt động?**  
Vì nó không kiểm TCP/TLS, reverse proxy, edge rewrites, socket timeout và caching.

**20. Content negotiation với Accept */* có luôn chọn JSON variant trong demo không?**  
Không nên giả định. Client/tests cần Accept rõ ràng hoặc server có default variant policy không mơ hồ.

## 24. Tham khảo chính thức

- **Spring Boot 3.3 – Testing Spring Boot Applications:** https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html — @WebMvcTest, MockMvc, @AutoConfigureMockMvc, @SpringBootTest(MOCK/RANDOM_PORT), TestRestTemplate, JSON tests.
- **Spring Framework – MockMvc:** https://docs.spring.io/spring-framework/reference/testing/mockmvc.html — Spring MVC server-side test framework.
- **Spring Framework – MockMvc Assertions:** https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html — request/response verification through MockMvc.
- **Spring Framework – Request Mapping:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html — HTTP method/path/params/headers/consumes/produces matching.
- **Spring Framework – Content Types/Negotiation:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html — Accept-based response selection, media type strategies.
- **Spring Framework 6.1 – ResponseEntity HeadersBuilder:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ResponseEntity.HeadersBuilder.html — cacheControl, location, varyBy, build.
- **Spring Framework – Message Converters:** https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html — Jackson JSON, StringHttpMessageConverter và converter behavior.
- **Spring Framework – Error Responses:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html — ProblemDetail và exception handling.
- **Spring Security – MockMvc Testing:** https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html — CSRF, mock authentication, protected endpoints.
- **HTTP Semantics RFC 9110:** https://www.rfc-editor.org/rfc/rfc9110.html — 200/201/400/404/405/406/415, Accept, Content-Type và Vary semantics.
- **Spring Boot 3.3.13 Release Announcement:** https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/ — phiên bản mẫu và thông báo kết thúc OSS support nhánh 3.3.
