# Điều kiện `params`, `headers`, `consumes` và `produces` trong Spring WebFlux

## 1. Mục tiêu

Trong Spring WebFlux, `@RequestMapping` chọn controller handler dựa trên nhiều điều kiện của HTTP request, không chỉ URL và HTTP method. Bốn thuộc tính thường dùng để thu hẹp mapping là:

- **`params`**: query parameter phải có, phải vắng mặt hoặc phải mang giá trị phù hợp.
- **`headers`**: request header phải có, phải vắng mặt hoặc phải mang giá trị phù hợp.
- **`consumes`**: media type của body request mà handler chấp nhận, thường lấy từ `Content-Type`.
- **`produces`**: media type response mà handler có thể tạo, được đối chiếu với `Accept` qua content negotiation.

Đây là **điều kiện chọn handler**. Chúng được đánh giá trước khi controller method chạy. Chúng khác với việc bind argument (`@RequestParam`, `@RequestHeader`, `@RequestBody`), decode body, kiểm tra dữ liệu hoặc serialize response.

Sau bài này, bạn có thể đọc và viết các biểu thức điều kiện, hiểu cách class-level và method-level mapping kết hợp, dự đoán lỗi HTTP thường gặp và kiểm thử bằng `WebTestClient`.

## 2. Một request được chọn handler như thế nào?

```text
HTTP request
    |
    v
Path / URI pattern
    |
    v
HTTP method
    |
    v
params condition
    |
    v
headers condition
    |
    v
consumes condition (Content-Type)
    |
    v
produces condition (Accept)
    |
    v
Chọn handler phù hợp
    |
    v
Controller -> service -> response body
```

Ví dụ:

```java
@PostMapping(
        path = "/orders",
        params = "source=partner",
        headers = "X-Partner-Version=2",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> create(
        @RequestBody Mono<CreateOrder> body) {
    return body.flatMap(orderService::create);
}
```

Method chỉ được chọn khi path, HTTP method, query parameter, header và hai điều kiện media type đều phù hợp. Khi handler đã được chọn, message reader mới decode body thành `CreateOrder`; controller/service mới xử lý nghiệp vụ. Mapping thành công không bảo đảm JSON hợp lệ hoặc dữ liệu hợp lệ.

| Thuộc tính | Câu hỏi | Nguồn dữ liệu |
|---|---|---|
| `params` | Query parameter có thỏa điều kiện không? | URL query string |
| `headers` | Header có thỏa điều kiện không? | HTTP request headers |
| `consumes` | Server có nhận body theo media type này không? | `Content-Type` |
| `produces` | Server có thể trả định dạng client chấp nhận không? | `Accept` |

## 3. `params`: điều kiện theo query parameter

`params` nhận một hoặc nhiều biểu thức. Tất cả biểu thức trong một mapping phải cùng thỏa mãn.

| Biểu thức | Ý nghĩa |
|---|---|
| `"mode"` | Query parameter `mode` phải hiện diện |
| `"!mode"` | Query parameter `mode` phải vắng mặt |
| `"mode=compact"` | `mode` phải có giá trị `compact` |
| `"mode!=compact"` | `mode` không được có giá trị `compact` |

Ví dụ hai handler cùng path nhưng xử lý hai dạng response:

```java
@GetMapping(path = "/reports", params = "format=compact")
public Mono<Report> compact() {
    return reportService.compact();
}

@GetMapping(path = "/reports", params = "format=full")
public Mono<Report> full() {
    return reportService.full();
}
```

```text
GET /reports?format=compact  -> compact()
GET /reports?format=full     -> full()
```

Kết hợp nhiều điều kiện:

```java
@GetMapping(
        path = "/reports",
        params = {"format=compact", "tenant", "!debug"}
)
public Mono<Report> compactForTenant() {
    return reportService.compact();
}
```

Request cần `format=compact`, có parameter `tenant` và không có parameter `debug`. Các điều kiện trong mảng được kết hợp theo AND.

### `params` khác `@RequestParam`

```java
@GetMapping(path = "/search", params = "scope=public")
public Flux<Result> search(
        @RequestParam("q") String query,
        @RequestParam(defaultValue = "20") int limit) {
    return searchService.searchPublic(query, limit);
}
```

- `params="scope=public"` quyết định method có được chọn không.
- `@RequestParam("q")` bind giá trị `q` vào argument.
- `defaultValue="20"` là quy tắc binding cho `limit`, không phải mapping condition.

Trong WebFlux, `@RequestParam` bind query parameters. Form data và multipart được truy cập bằng cơ chế riêng của WebFlux; không nên giả định khái niệm Servlet request parameter áp dụng nguyên vẹn.

## 4. `headers`: điều kiện theo request header

Cú pháp `headers` tương tự `params`, nhưng áp dụng lên HTTP header:

| Biểu thức | Ý nghĩa |
|---|---|
| `"X-Client"` | Header phải hiện diện |
| `"!X-Client"` | Header phải vắng mặt |
| `"X-Client=mobile"` | Header phải có giá trị `mobile` |
| `"X-Client!=mobile"` | Header không được có giá trị `mobile` |

Ví dụ:

```java
@GetMapping(path = "/dashboard", headers = "X-Client=mobile")
public Mono<Dashboard> mobile() {
    return dashboardService.mobile();
}

@GetMapping(path = "/dashboard", headers = "X-Client=web")
public Mono<Dashboard> web() {
    return dashboardService.web();
}
```

Request có `X-Client: mobile` phù hợp với method `mobile()`.

Nhiều điều kiện có thể kết hợp:

```java
@GetMapping(
        path = "/offers",
        params = "region=apac",
        headers = {"X-Channel=partner", "X-Partner-Id"}
)
public Flux<Offer> partnerOffers() {
    return offerService.partnerOffers();
}
```

Request cần `region=apac`, `X-Channel` có giá trị `partner` và header `X-Partner-Id` hiện diện.

Header name không phân biệt chữ hoa/chữ thường theo quy tắc HTTP. Không nên tự giả định mọi header value cũng không phân biệt chữ hoa/chữ thường; hãy theo contract của header cụ thể.

### Không dùng `headers` thay `consumes` hoặc `produces`

Có thể kiểm tra `Content-Type` hoặc `Accept` bằng header expression, nhưng Spring có thuộc tính chuyên biệt cho media type:

- `consumes` biểu đạt định dạng body request.
- `produces` biểu đạt định dạng response có thể được thương lượng.

Dùng hai thuộc tính này giúp mapping thể hiện đúng ý định và được framework xử lý theo semantics của media type.

## 5. `consumes`: media type của request body

`consumes` giới hạn media type mà endpoint chấp nhận, thường được đối chiếu với request header `Content-Type`.

```java
@PostMapping(
        path = "/products",
        consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
    return body.flatMap(productService::create);
}
```

Request phù hợp:

```http
POST /products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Keyboard"}
```

Nếu client gửi `Content-Type: text/plain`, mapping JSON không phù hợp và WebFlux thường trả **415 Unsupported Media Type**.

Có thể khai báo nhiều media type:

```java
@PostMapping(
        path = "/imports",
        consumes = {
                MediaType.APPLICATION_JSON_VALUE,
                "text/csv"
        }
)
public Mono<ImportResult> importData(@RequestBody Mono<String> body) {
    return body.flatMap(importService::process);
}
```

Một trong các media type được khai báo có thể phù hợp. Tuy nhiên, khai báo `text/csv` không tự cung cấp CSV parser; ứng dụng vẫn phải có logic đọc định dạng đó và message reader tương thích.

### Wildcard và phủ định

```java
@PostMapping(path = "/text", consumes = "text/*")
public Mono<String> acceptText(@RequestBody Mono<String> body) {
    return body;
}
```

`text/*` chấp nhận các media type thuộc nhóm text nếu codec có thể đọc kiểu body được yêu cầu.

Có thể dùng biểu thức phủ định:

```java
@PostMapping(path = "/payload", consumes = "!text/plain")
public Mono<Void> acceptNonPlainText(@RequestBody Mono<byte[]> body) {
    return body.then();
}
```

Biểu thức phủ định có thể mở rộng phạm vi chấp nhận ngoài những định dạng ứng dụng đã thực sự hỗ trợ. Một danh sách cho phép rõ ràng thường dễ bảo trì hơn.

### Media type parameters và decode body

Media type có thể có parameter, ví dụ `application/json;charset=UTF-8`. Spring có quy tắc so khớp parameter: nếu điều kiện và request cùng có parameter tương ứng thì giá trị cần tương thích; nếu request không gửi parameter đó, việc so khớp có thể bỏ qua parameter theo semantics của Spring.

`consumes` chỉ kiểm tra media type. Nếu Content-Type đúng nhưng JSON sai cú pháp hoặc không thể chuyển thành DTO, lỗi xảy ra ở bước đọc/decode body, thường được ánh xạ thành 400. Validation field và business validation là các bước riêng nữa.

## 6. `produces`: media type của response

`produces` mô tả định dạng response handler có thể tạo. Spring đối chiếu điều kiện này với các media type client chấp nhận, thường được gửi qua `Accept`.

```java
@GetMapping(
        path = "/products/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> find(@PathVariable String id) {
    return productService.find(id);
}
```

Client gửi `Accept: application/json` thì mapping phù hợp. Nếu client chỉ chấp nhận `text/plain` trong khi handler chỉ tạo JSON, WebFlux thường trả **406 Not Acceptable**.

Có thể khai báo nhiều representation:

```java
@GetMapping(
        path = "/catalog",
        produces = {
                MediaType.APPLICATION_JSON_VALUE,
                MediaType.APPLICATION_XML_VALUE
        }
)
public Mono<Catalog> catalog() {
    return catalogService.load();
}
```

Ứng dụng cần có encoder/codec phù hợp với representation được chọn. Khai báo `produces=application/xml` không tự cài Jackson XML hoặc codec XML.

### Accept, wildcard và q-value

Các ví dụ:

| `Accept` | Ý nghĩa |
|---|---|
| `application/json` | Client chấp nhận JSON |
| `application/*` | Client chấp nhận các media type thuộc application |
| Wildcard mọi loại | Client không giới hạn theo media type |
| `application/json, text/plain` | Client chấp nhận nhiều loại |
| `application/json;q=0.9, text/plain;q=0.5` | JSON được ưu tiên hơn text |

Nếu request không có `Accept`, thông thường client không đặt giới hạn cụ thể và mọi media type đều có thể được xem là chấp nhận. Khi có nhiều lựa chọn, content negotiation và các message writer khả dụng quyết định representation phù hợp.

Có thể dùng phủ định như `produces="!text/plain"`, nhưng điều đó không bảo đảm mọi media type còn lại đều có encoder. Chỉ dùng khi thực sự cần semantics phủ định.

### `Content-Type` và `Accept` là hai chiều khác nhau

Một request có thể gửi:

```http
Content-Type: application/json
Accept: text/plain
```

Nghĩa là client gửi body JSON nhưng muốn nhận response dạng text. `consumes` kiểm tra phần gửi lên; `produces` kiểm tra phần trả về. Hai điều kiện độc lập.

## 7. Kết hợp class-level và method-level

Có thể khai báo điều kiện dùng chung ở class-level:

```java
@RestController
@RequestMapping(
        path = "/api/v1",
        headers = "X-Api-Version=2",
        produces = MediaType.APPLICATION_JSON_VALUE
)
public class CatalogController {

    @GetMapping(path = "/items", params = "view=compact")
    public Mono<Item> compact() {
        return Mono.just(new Item("compact"));
    }

    @PostMapping(
            path = "/items",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Item> create(@RequestBody Mono<Item> body) {
        return body;
    }

    @GetMapping(
            path = "/plain",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> plain() {
        return Mono.just("ready");
    }
}
```

Cách đọc:

- Class-level `path` tạo prefix `/api/v1`.
- Class-level `headers` yêu cầu mọi method có `X-Api-Version=2`.
- `params` ở method `compact` bổ sung điều kiện riêng.
- `consumes` ở method `create` giới hạn media type body.
- `produces` ở method `plain` ghi đè class-level JSON, nên endpoint đó trả text.

| Điều kiện | Khi khai báo ở class và method |
|---|---|
| Path | Kết hợp thành đường dẫn cụ thể |
| HTTP method | Các điều kiện được kết hợp |
| `params` | Method-level bổ sung điều kiện class-level |
| `headers` | Method-level bổ sung điều kiện class-level |
| `consumes` | Method-level ghi đè class-level nếu khai báo |
| `produces` | Method-level ghi đè class-level nếu khai báo |

Không giả định mọi thuộc tính đều được kết hợp giống nhau. Đặc biệt, `consumes` và `produces` có quy tắc ghi đè ở method-level.

### Không chồng nhiều mapping annotation trên cùng method

Không viết đồng thời `@GetMapping` và `@RequestMapping` trên cùng method. Đây đều là request-mapping annotations; Spring cảnh báo và chỉ dùng mapping đầu tiên.

Gộp điều kiện vào một annotation:

```java
@GetMapping(path = "/items", params = "mode=full")
public Mono<Item> items() {
    return Mono.just(new Item("example"));
}
```

## 8. Phân biệt mapping conditions với binding và codec

| Công cụ | Vai trò | Ví dụ |
|---|---|---|
| `params` | Chọn handler theo query | `params="mode=full"` |
| `@RequestParam` | Bind query vào argument | `@RequestParam String mode` |
| `headers` | Chọn handler theo header | `headers="X-Client=web"` |
| `@RequestHeader` | Bind header vào argument | `@RequestHeader("X-Client") String client` |
| `consumes` | Chọn handler theo Content-Type | `consumes="application/json"` |
| `@RequestBody` | Đọc và decode body | `@RequestBody Mono<CreateOrder>` |
| `produces` | Chọn representation theo Accept | `produces="application/json"` |
| `@ResponseBody` / `@RestController` | Ghi response qua message writer | `Mono<OrderResponse>` |

Ví dụ kết hợp:

```java
@PostMapping(
        path = "/orders",
        params = "source=partner",
        headers = "X-Partner-Id",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> create(
        @RequestParam("source") String source,
        @RequestHeader("X-Partner-Id") String partnerId,
        @RequestBody Mono<CreateOrder> body) {

    return body.flatMap(order ->
            orderService.create(source, partnerId, order));
}
```

Mapping condition giúp chọn method; argument resolver cung cấp dữ liệu cho method sau khi đã chọn.

## 9. HTTP status thường gặp khi mapping không khớp

| Tình huống | Status thường gặp | Giải thích |
|---|---|---|
| Không có path phù hợp | 404 Not Found | Không tìm thấy handler |
| Path phù hợp nhưng HTTP method không hỗ trợ | 405 Method Not Allowed | Method không được hỗ trợ |
| `params` không thỏa điều kiện | Thường 400 Bad Request trong WebFlux | Có thể là `UnsatisfiedRequestParameterException` |
| `headers` không thỏa điều kiện | Có thể không còn handler và trả 404 | Không có mapping thỏa header condition |
| `consumes` không khớp Content-Type | 415 Unsupported Media Type | Server không chấp nhận request media type |
| `produces` không tương thích Accept | 406 Not Acceptable | Không có representation phù hợp |

Status cụ thể còn phụ thuộc tập handler candidates và exception handling được cấu hình. Không nên kết luận mọi mapping mismatch đều là 404.

Phân biệt hai lỗi:

1. Gửi `Content-Type: text/plain` vào handler chỉ nhận JSON: mapping không phù hợp, thường 415.
2. Gửi `Content-Type: application/json` nhưng body sai cú pháp JSON: mapping có thể đã chọn handler; message reader thất bại khi decode, thường là 400.

## 10. Thử request bằng curl

Giả sử controller có base path `/api/v1`, yêu cầu `X-Api-Version: 2`, endpoint compact cần `view=compact`, `X-Client=web` và response JSON:

```bash
curl -i \
  -H "X-Api-Version: 2" \
  -H "X-Client: web" \
  -H "Accept: application/json" \
  "http://localhost:8080/api/v1/items?view=compact"
```

Response thành công ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"name":"compact"}
```

Gửi JSON vào POST:

```bash
curl -i -X POST \
  -H "X-Api-Version: 2" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"new-item"}' \
  "http://localhost:8080/api/v1/items"
```

Nếu gửi `Content-Type: text/plain`, mapping `consumes=application/json` không phù hợp và thường trả 415.

Thử `produces` bằng cách gọi `/api/v1/plain` với `Accept: text/plain`. Nếu chỉ gửi `Accept: application/json` trong khi endpoint chỉ tạo text, thường nhận 406.

## 11. Dự án Java 17+ chạy được: Spring Boot WebFlux và WebTestClient

Dự án Maven này kiểm thử bốn loại điều kiện bằng test HTTP. Dùng Java 17+, Maven và Spring Boot 3.3.5.

Cấu trúc:

```text
request-mapping-conditions/
├── pom.xml
└── src/
    ├── main/java/edu/demo/
    │   ├── RequestMappingConditionsApplication.java
    │   ├── CatalogController.java
    │   └── Item.java
    └── test/java/edu/demo/
        └── RequestMappingConditionsTest.java
```

### 11.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>request-mapping-conditions</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

### 11.2. `RequestMappingConditionsApplication.java`

```java
package edu.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestMappingConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RequestMappingConditionsApplication.class, args);
    }
}
```

### 11.3. `Item.java`

```java
package edu.demo;

public record Item(String name) {
}
```

### 11.4. `CatalogController.java`

```java
package edu.demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping(
        path = "/api/v1",
        headers = "X-Api-Version=2",
        produces = MediaType.APPLICATION_JSON_VALUE
)
public class CatalogController {

    @GetMapping(
            path = "/items",
            params = {"view=compact", "!debug"},
            headers = "X-Client=web"
    )
    public Mono<Item> compact() {
        return Mono.just(new Item("compact"));
    }

    @GetMapping(
            path = "/items",
            params = "view=full",
            headers = "X-Client=web"
    )
    public Mono<Item> full() {
        return Mono.just(new Item("full"));
    }

    @PostMapping(
            path = "/items",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Item> create(@RequestBody Mono<Item> body) {
        return body;
    }

    @GetMapping(
            path = "/plain",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> plain() {
        return Mono.just("ready");
    }
}
```

### 11.5. `RequestMappingConditionsTest.java`

```java
package edu.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class RequestMappingConditionsTest {

    @Autowired
    private WebTestClient client;

    @Test
    void paramsAndHeadersSelectCompactHandler() {
        client.get()
                .uri("/api/v1/items?view=compact")
                .header("X-Api-Version", "2")
                .header("X-Client", "web")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.name").isEqualTo("compact");
    }

    @Test
    void paramsSelectFullHandler() {
        client.get()
                .uri("/api/v1/items?view=full")
                .header("X-Api-Version", "2")
                .header("X-Client", "web")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                    .jsonPath("$.name").isEqualTo("full");
    }

    @Test
    void absentDebugParameterIsRequired() {
        client.get()
                .uri("/api/v1/items?view=compact&debug=true")
                .header("X-Api-Version", "2")
                .header("X-Client", "web")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().is4xxClientError();
    }

    @Test
    void headerConditionMustMatch() {
        client.get()
                .uri("/api/v1/items?view=compact")
                .header("X-Api-Version", "2")
                .header("X-Client", "mobile")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().is4xxClientError();
    }

    @Test
    void jsonRequestMatchesConsumesCondition() {
        client.post()
                .uri("/api/v1/items")
                .header("X-Api-Version", "2")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new Item("created"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                    .jsonPath("$.name").isEqualTo("created");
    }

    @Test
    void unsupportedContentTypeReturns415() {
        client.post()
                .uri("/api/v1/items")
                .header("X-Api-Version", "2")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("not-json")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void methodLevelProducesOverridesClassLevel() {
        client.get()
                .uri("/api/v1/plain")
                .header("X-Api-Version", "2")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
                .expectBody(String.class)
                    .isEqualTo("ready");
    }

    @Test
    void unacceptableResponseTypeReturns406() {
        client.get()
                .uri("/api/v1/plain")
                .header("X-Api-Version", "2")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(406);
    }
}
```

### 11.6. Chạy test

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Khi dependency tải thành công và assertion đúng, Maven Surefire sẽ báo tám test chạy, không có failure hoặc error. Các test xác nhận:

1. `view=compact` và `X-Client=web` chọn handler compact.
2. `view=full` chọn handler full.
3. Có `debug` làm điều kiện `!debug` thất bại.
4. Header `X-Client` không đúng làm mapping không phù hợp.
5. JSON request thỏa `consumes`.
6. `text/plain` không thỏa `consumes=application/json` và nhận 415.
7. Method-level `produces=text/plain` ghi đè class-level JSON.
8. Client chỉ chấp nhận JSON trong khi endpoint chỉ tạo text nhận 406.

Test dùng `is4xxClientError()` cho mismatch `params` và `headers` vì kết quả cụ thể phụ thuộc loại condition và tập handler candidates. Hai test media type kiểm tra trực tiếp status chuyên biệt 415 và 406.

## 12. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng `params` nhưng không gửi query tương ứng | Mapping không được chọn | Gửi đúng query hoặc bỏ condition |
| Nhầm `params` với `@RequestParam` | Một cái chọn handler, một cái bind argument | Dùng đúng mục đích từng loại |
| Dùng `headers=Content-Type` thay `consumes` | Bỏ qua semantics media type | Dùng `consumes` |
| Dùng `headers=Accept` thay `produces` | Không biểu đạt rõ content negotiation | Dùng `produces` |
| Nhầm `consumes` với response format | `consumes` là body gửi lên | Dùng `produces` cho response |
| Gửi Content-Type không được hỗ trợ | Mapping không phù hợp, thường 415 | Sửa request hoặc media type được hỗ trợ |
| Accept không tương thích | Không có representation phù hợp, thường 406 | Sửa Accept hoặc hỗ trợ representation phù hợp |
| Dùng `!debug` nhưng client vẫn gửi debug | Điều kiện yêu cầu parameter vắng mặt | Bỏ parameter hoặc đổi mapping |
| Nghĩ `produces` method-level được cộng vào class-level | Method-level ghi đè class-level | Khai báo điều kiện đầy đủ tại method |
| Chồng `@GetMapping` và `@RequestMapping` | Spring chỉ dùng mapping đầu tiên | Gộp vào một annotation |
| Dùng header mapping để xác thực API key | Mapping không kiểm tra identity/quyền | Dùng Spring Security |
| Nghĩ consumes xác nhận JSON hợp lệ | Chỉ kiểm tra media type | Dùng codec, validation và business rules |

## 13. Checklist thiết kế mapping

- Path và HTTP method đã cụ thể chưa? Ưu tiên các shortcut như `@GetMapping` và `@PostMapping`.
- `params` có thực sự cần chọn handler khác nhau hay chỉ cần bind một argument?
- Header nào là điều kiện định tuyến, header nào thuộc authentication/security?
- `consumes` có giới hạn đúng định dạng body mà codec hỗ trợ không?
- `produces` có phù hợp với representation mà message writer thực sự tạo được không?
- Class-level conditions và method-level overrides có đúng ý định không?
- Có hai mapping trùng điều kiện hoặc gây ambiguity không?
- Đã test thiếu parameter/header, sai Content-Type, sai Accept và body sai định dạng chưa?
- Error response có rõ ràng nhưng không tiết lộ nội bộ không?
- API key/token có được xác thực bằng security mechanism phù hợp không?

## 14. Bài tập tự kiểm tra

**Bài 1.** Mapping sau cần request nào?

```java
@GetMapping(path = "/items", params = {"type=book", "!archived"})
public Flux<Item> books() {
    return itemService.books();
}
```

**Đáp án:** Request phải có `type=book` và không có query parameter `archived`, ví dụ `/items?type=book`.

**Bài 2.** `headers="X-Mode"` khác `headers="X-Mode=fast"` thế nào?

**Đáp án:** Biểu thức đầu yêu cầu header hiện diện với giá trị bất kỳ; biểu thức sau yêu cầu giá trị phù hợp là `fast`.

**Bài 3.** Client gửi `Content-Type: application/json` và `Accept: text/plain`. Điều kiện nào kiểm tra từng header?

**Đáp án:** `consumes` kiểm tra Content-Type; `produces` kiểm tra response có tương thích với Accept hay không.

**Bài 4.** Endpoint chỉ nhận `consumes=application/json`, client gửi text/plain. Status thường gặp?

**Đáp án:** 415 Unsupported Media Type.

**Bài 5.** Endpoint chỉ tạo `produces=application/json`, client chỉ chấp nhận text/plain. Status thường gặp?

**Đáp án:** 406 Not Acceptable.

**Bài 6.** Class-level `produces=application/json`, method-level `produces=text/plain`. Method đó nhận cả hai loại?

**Đáp án:** Không. Method-level `produces` ghi đè class-level cho method đó.

**Bài 7.** Vì sao không nên đặt cả `@GetMapping` và `@RequestMapping` trên cùng method?

**Đáp án:** Spring cảnh báo và chỉ dùng mapping đầu tiên; gộp điều kiện vào một annotation.

**Bài 8.** `consumes=application/json` có bảo đảm body có field `name` hợp lệ?

**Đáp án:** Không. Nó chỉ giới hạn media type. Decode, Bean Validation và business validation là các bước riêng.

## 15. Ghi nhớ

- `params` và `headers` là điều kiện chọn handler, hỗ trợ kiểm tra có mặt, vắng mặt và giá trị.
- `consumes` kiểm tra request body qua Content-Type; mismatch thường là 415.
- `produces` tham gia content negotiation với Accept; mismatch thường là 406.
- Nhiều điều kiện trong cùng mapping phải cùng thỏa mãn.
- Class-level cung cấp điều kiện chung; method-level bổ sung điều kiện, với quy tắc ghi đè riêng cho `consumes` và `produces`.
- `@RequestParam`, `@RequestHeader`, `@RequestBody` và codecs thực hiện binding/serialization sau khi handler được chọn.
- Dùng `WebTestClient` để kiểm thử cả request hợp lệ và không hợp lệ.
- Mapping condition không thay thế authentication, authorization hoặc validation nghiệp vụ.

Khi debug một controller không được gọi, hãy kiểm tra lần lượt **path → HTTP method → params → headers → Content-Type/consumes → Accept/produces**.

## Tài liệu chính thức

- Spring Framework, **Spring WebFlux – Mapping Requests**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework, **Spring WebFlux – Annotated Controllers**: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework, **Spring WebFlux – `@RequestParam`**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework, **Spring WebFlux – `@RequestBody`**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework, **`RequestMapping` API 6.2**: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html
- Spring Framework, **`UnsatisfiedRequestParameterException`**: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/server/UnsatisfiedRequestParameterException.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html