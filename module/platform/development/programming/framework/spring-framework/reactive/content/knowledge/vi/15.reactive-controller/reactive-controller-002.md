# @RequestMapping cùng các annotation theo HTTP method

Trong **Spring WebFlux**, controller dùng annotation để khai báo URL nào được xử lý bởi phương thức Java nào. `@RequestMapping` là annotation tổng quát: nó có thể khớp theo **path, HTTP method, query parameter, request header và media type**. Các annotation chuyên biệt như `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping` và `@DeleteMapping` là những dạng viết tắt giúp khai báo endpoint theo đúng HTTP method.

Một controller thường đặt `@RequestMapping` ở cấp lớp để định nghĩa phần URL chung, rồi dùng annotation theo HTTP method ở từng phương thức. Cách này làm hợp đồng API rõ ràng, tránh một handler vô tình nhận những HTTP method mà nó không hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `@RequestMapping` ở cấp lớp và cấp phương thức.
2. Chọn đúng `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping` hoặc `@DeleteMapping`.
3. Kết hợp path, `@PathVariable`, `@RequestParam`, điều kiện `params` và `headers`.
4. Dùng `consumes` để giới hạn kiểu nội dung request và `produces` để khai báo kiểu response.
5. Hiểu cách Spring WebFlux chọn handler khi có nhiều mapping và nhận diện xung đột mapping.
6. Viết controller reactive trả `Mono`/`Flux` và nhận body bằng `Mono<T>`.
7. Kiểm thử mapping bằng `WebTestClient` và xác minh method, path, status, headers, media type.
8. Phân biệt hành vi HTTP như GET, POST, PUT, PATCH, DELETE, HEAD và OPTIONS trong thiết kế endpoint.

## 2. `@RequestMapping` là gì?

`@RequestMapping` đánh dấu một controller hoặc phương thức controller để Spring có thể ánh xạ HTTP request vào handler tương ứng.

Nó hỗ trợ các thuộc tính thường dùng:

| Thuộc tính | Mục đích |
| --- | --- |
| `path` / `value` | Một hoặc nhiều URI path pattern. Hai thuộc tính này là alias của nhau. |
| `method` | Giới hạn theo HTTP method, dùng enum `RequestMethod`. |
| `params` | Điều kiện dựa trên query parameter: có, không có hoặc bằng/khác một giá trị. |
| `headers` | Điều kiện dựa trên request header. |
| `consumes` | Giới hạn media type của request body, thường đối chiếu `Content-Type`. |
| `produces` | Khai báo media type mà handler có thể trả, thường đối chiếu `Accept`. |
| `name` | Tên định danh cho mapping, hữu ích trong một số tình huống quản lý mapping. |

Ví dụ tổng quát:

~~~java
@RequestMapping(
    path = "/api/products",
    method = RequestMethod.GET,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<Product> listProducts() {
    // ...
}
~~~

Ở đây handler chỉ nhận GET cho path đã khai báo và biểu diễn response dưới dạng JSON. Vì đa số endpoint chỉ phục vụ một HTTP method cụ thể, Spring cung cấp các annotation viết tắt chuyên biệt để code dễ đọc hơn.

**Lưu ý quan trọng:** `@RequestMapping` không khai báo `method` thì mặc định có thể khớp với tất cả HTTP methods. Với API thông thường, nên dùng `@GetMapping`, `@PostMapping`... để tránh vô tình mở endpoint cho các method không mong muốn.

## 3. Mapping ở cấp lớp và cấp phương thức

Cách tổ chức phổ biến:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    public Flux<Product> list() {
        // GET /api/products
    }

    @GetMapping("/{id}")
    public Mono<Product> find(@PathVariable("id") String id) {
        // GET /api/products/{id}
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
        // POST /api/products
    }
}
~~~

Đây là **đoạn minh họa controller**, cần khai báo các kiểu `Product`, `CreateProduct` và phần xử lý tương ứng trong ứng dụng. Quy tắc ghép path:

- Mapping ở cấp lớp `/api/products` là phần chung.
- `@GetMapping("/{id}")` thêm phần `/{id}`.
- Endpoint cuối cùng là `GET /api/products/{id}`.
- `@PostMapping` không có path bổ sung nên dùng đúng path cấp lớp: `POST /api/products`.

Bạn cũng có thể đặt URI variable ở cấp lớp:

~~~java
@RestController
@RequestMapping("/tenants/{tenantId}/products")
class TenantProductController {

    @GetMapping("/{productId}")
    Mono<Product> get(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("productId") String productId) {
        // ...
    }
}
~~~

Cả `tenantId` và `productId` đều được lấy từ URI. Spring thực hiện chuyển kiểu cho các kiểu đơn giản như `long`, `int`, `UUID` hoặc kiểu có converter phù hợp; nếu chuyển kiểu thất bại, request không thể được bind như mong muốn và sẽ đi qua cơ chế xử lý lỗi tương ứng.

**Nên đặt path chung ở lớp, còn method/path cụ thể ở method.** Tránh lặp lại prefix ở mọi phương thức, đồng thời không tạo mapping quá rộng như `/**` nếu controller chỉ quản lý một nhóm tài nguyên.

## 4. Các annotation theo HTTP method

Các annotation chuyên biệt là composed annotation được xây dựng trên `@RequestMapping`:

| Annotation | HTTP method | Công dụng điển hình |
| --- | --- | --- |
| `@GetMapping` | GET | Đọc tài nguyên hoặc truy vấn dữ liệu. |
| `@PostMapping` | POST | Tạo tài nguyên hoặc thực hiện một hành động không được mô hình hóa bằng method khác. |
| `@PutMapping` | PUT | Thay thế toàn bộ biểu diễn tài nguyên tại URI đã biết. |
| `@PatchMapping` | PATCH | Cập nhật một phần tài nguyên. |
| `@DeleteMapping` | DELETE | Yêu cầu xóa tài nguyên tại URI. |

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    Flux<OrderView> list() {
        // GET /api/orders
    }

    @GetMapping("/{id}")
    Mono<OrderView> get(@PathVariable("id") String id) {
        // GET /api/orders/{id}
    }

    @PostMapping
    Mono<OrderView> create(@RequestBody Mono<CreateOrder> body) {
        // POST /api/orders
    }

    @PutMapping("/{id}")
    Mono<OrderView> replace(
            @PathVariable("id") String id,
            @RequestBody Mono<ReplaceOrder> body) {
        // PUT /api/orders/{id}
    }

    @PatchMapping("/{id}")
    Mono<OrderView> patch(
            @PathVariable("id") String id,
            @RequestBody Mono<PatchOrder> body) {
        // PATCH /api/orders/{id}
    }

    @DeleteMapping("/{id}")
    Mono<Void> delete(@PathVariable("id") String id) {
        // DELETE /api/orders/{id}
    }
}
~~~

Đây là **skeleton minh họa**, không phải chương trình Java chạy độc lập. Các kiểu request/response và logic nghiệp vụ cần được triển khai.

### 4.1. Ý nghĩa HTTP cần phản ánh trong API

- **GET**: đọc tài nguyên, không nên tạo side effect nghiệp vụ. GET được định nghĩa là *safe* và *idempotent* theo ngữ nghĩa HTTP.
- **POST**: thường tạo tài nguyên con hoặc thực hiện hành động; không mặc định idempotent. Nếu client retry sau timeout, server có thể đã tạo bản ghi trước khi kết nối bị ngắt.
- **PUT**: thay thế biểu diễn tại URI đích. PUT được định nghĩa idempotent về hiệu ứng mong muốn; gửi cùng request nhiều lần không nên tạo thêm các bản ghi khác nhau.
- **PATCH**: áp dụng một phần thay đổi; tính idempotent phụ thuộc nội dung patch và hợp đồng API.
- **DELETE**: yêu cầu xóa tài nguyên. DELETE được định nghĩa idempotent về hiệu ứng, dù response của lần đầu và lần sau có thể khác (ví dụ 204 rồi 404).

Đừng chỉ đổi annotation mà không xét semantics. Ví dụ, cập nhật một trường trạng thái có thể là PATCH; thay toàn bộ representation thường phù hợp với PUT. Nếu POST tạo tài nguyên, response thường trả 201 Created và có thể có header `Location` trỏ đến tài nguyên mới.

### 4.2. HEAD và OPTIONS

Spring WebFlux hỗ trợ HEAD qua mapping GET cho mục đích request mapping; ứng dụng không nhất thiết phải tạo handler HEAD riêng cho trường hợp thông thường. Server adapter xử lý response HEAD sao cho không gửi response body như GET.

OPTIONS mặc định có thể được Spring xử lý bằng header `Allow` liệt kê các HTTP methods được hỗ trợ cho path tương ứng. Chỉ khai báo handler OPTIONS riêng khi ứng dụng cần hành vi tùy chỉnh. CORS preflight cũng dùng OPTIONS nhưng cần cấu hình CORS phù hợp; không nhầm việc có handler OPTIONS với việc đã cấu hình CORS.

## 5. Path pattern, PathVariable và RequestParam

### 5.1. URI path pattern

Spring WebFlux dùng `PathPattern` để khớp URI. Các dạng thường dùng:

| Pattern | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `/products` | Path cố định | `/products` |
| `/products/{id}` | Một segment được đặt tên | `/products/p-10` |
| `/files/*` | Wildcard trong một segment | `/files/a.txt` |
| `/files/**` | Nhiều segment ở cuối pattern | `/files/images/a.png` |
| `/{id:\d+}` | Segment có ràng buộc regex | `/123` |

Ví dụ bắt path variable:

~~~java
@GetMapping("/orders/{orderId}/items/{itemId}")
Mono<ItemView> getItem(
        @PathVariable("orderId") String orderId,
        @PathVariable("itemId") String itemId) {
    // ...
}
~~~

Đặt tên rõ trong annotation giúp code không phụ thuộc việc compiler giữ tên tham số bằng `-parameters`. Nếu tên tham số và tên biến URI trùng nhau, có thể rút gọn `@PathVariable`, nhưng khai báo tường minh thường dễ đọc khi dự án có nhiều module.

### 5.2. Query parameter

`@RequestParam` lấy giá trị từ query string hoặc form parameter được hỗ trợ:

~~~java
@GetMapping("/search")
Flux<Product> search(
        @RequestParam(name = "q") String keyword,
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    // ...
}
~~~

Ví dụ URL: `GET /api/products/search?q=keyboard&page=0&size=20`.

- `required` mặc định là true.
- `defaultValue` làm tham số không còn bắt buộc theo nghĩa phải có mặt; nếu vắng mặt hoặc rỗng, giá trị mặc định được sử dụng.
- Kiểu dữ liệu được chuyển từ chuỗi; đầu vào không chuyển được sang `int` có thể dẫn tới lỗi bind.
- `@RequestParam` là **bind giá trị vào tham số Java**. Thuộc tính `params` của `@RequestMapping` là **điều kiện chọn handler**; hai việc này liên quan nhưng không giống nhau.

### 5.3. Điều kiện params

Bạn có thể định nghĩa nhiều handler cùng path nhưng khác query condition:

~~~java
@GetMapping(path = "/reports", params = "format=full")
Mono<Report> fullReport() {
    // GET /reports?format=full
}

@GetMapping(path = "/reports", params = "!format")
Mono<Report> defaultReport() {
    // GET /reports khi không có query parameter format
}
~~~

Các biểu thức phổ biến:

- `"mode"`: parameter phải tồn tại.
- `"!mode"`: parameter phải không tồn tại.
- `"mode=full"`: parameter phải bằng giá trị chỉ định.
- `"mode!=full"`: parameter phải khác giá trị chỉ định.

Nếu nhiều mapping cùng khớp, Spring so sánh mức độ cụ thể để chọn mapping phù hợp nhất. Không tạo hai handler có cùng điều kiện hoặc điều kiện chồng lấn khó phân biệt; mapping không rõ ràng có thể gây lỗi đăng ký hoặc lỗi ambiguous khi xử lý request.

## 6. Điều kiện headers, consumes và produces

### 6.1. Điều kiện request header

Có thể chọn handler theo một header:

~~~java
@GetMapping(path = "/reports", headers = "X-Client=admin")
Mono<Report> adminReport() {
    // Chỉ khớp khi X-Client có giá trị admin.
}
~~~

Điều kiện header cũng hỗ trợ kiểm tra tồn tại, vắng mặt hoặc giá trị. Tuy nhiên, với content negotiation, nên dùng `consumes` và `produces` thay vì viết điều kiện trực tiếp cho `Content-Type` hoặc `Accept`.

### 6.2. `consumes`: kiểu nội dung request

`consumes` giới hạn request body theo media type của request, thường dựa trên header `Content-Type`:

~~~java
@PostMapping(
    path = "/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
    // ...
}
~~~

Client phải gửi body JSON với Content-Type phù hợp. Nếu gửi media type không được handler hỗ trợ, Spring thường trả 415 Unsupported Media Type.

Có thể nhận nhiều media type:

~~~java
@PostMapping(
    path = "/imports",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        "text/csv"
    }
)
Mono<ImportResult> importData(@RequestBody Mono<String> body) {
    // ...
}
~~~

Đây chỉ là minh họa mapping; để parse CSV và JSON đúng kiểu, ứng dụng cần logic/codec tương ứng. Khai báo `consumes` không tự biến body thành định dạng mong muốn.

### 6.3. `produces`: kiểu response

`produces` giới hạn media type response theo khả năng client yêu cầu qua `Accept`:

~~~java
@GetMapping(
    path = "/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Product> get(@PathVariable("id") String id) {
    // ...
}
~~~

Nếu client yêu cầu một kiểu response không tương thích, Spring có thể trả 406 Not Acceptable.

Với WebFlux, một `Flux<T>` trả về cùng `application/json` thường được encode thành một JSON array. Nếu muốn stream sự kiện theo Server-Sent Events, có thể dùng `text/event-stream` và kiểu `Flux<ServerSentEvent<T>>` hoặc publisher phù hợp. Không mặc định rằng mọi `Flux` response đều là SSE.

### 6.4. Cấp lớp và cấp phương thức

Có thể đặt `consumes`/`produces` chung trên lớp và ghi đè ở method. Với các thuộc tính này, khai báo tại method **ghi đè** điều kiện cùng loại ở cấp lớp, thay vì luôn cộng thêm điều kiện. Điều này quan trọng nếu controller mặc định JSON nhưng có một endpoint trả SSE hoặc nhận CSV.

## 7. Ví dụ mapping đầy đủ trong Spring WebFlux

Dự án nhỏ dưới đây triển khai API đơn giản cho đơn hàng. Nó minh họa mapping theo HTTP method, path variable, query condition, request body và response reactive.

### 7.1. Tạo dự án Gradle

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo file `src/main/java/demo/RequestMappingDemoApplication.java`:

~~~java
package demo;

import java.net.URI;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class RequestMappingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestMappingDemoApplication.class, args);
    }
}

record CreateOrderRequest(String customer, int quantity) {}
record StatusPatch(String status) {}
record OrderView(
    String id, String customer, int quantity, String status
) {}

@RestController
@RequestMapping(
    path = "/api/orders",
    produces = MediaType.APPLICATION_JSON_VALUE
)
class OrderController {

    private final ConcurrentMap<String, OrderView> orders =
        new ConcurrentHashMap<>();

    OrderController() {
        orders.put("o-1",
            new OrderView("o-1", "An", 2, "NEW"));
        orders.put("o-2",
            new OrderView("o-2", "Binh", 1, "PAID"));
    }

    @GetMapping
    Flux<OrderView> list(
            @RequestParam(name = "status", required = false)
            String status) {
        return Flux.fromIterable(orders.values())
            .filter(order -> status == null
                || order.status().equalsIgnoreCase(status));
    }

    @GetMapping(path = "/search", params = "status")
    Flux<OrderView> searchByStatus(
            @RequestParam("status") String status) {
        return Flux.fromIterable(orders.values())
            .filter(order ->
                order.status().equalsIgnoreCase(status));
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable("id") String id) {
        return Mono.justOrEmpty(orders.get(id))
            .map(order -> ResponseEntity.ok().body(order))
            .defaultIfEmpty(
                ResponseEntity.<OrderView>notFound().build()
            );
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<OrderView>> create(
            @RequestBody Mono<CreateOrderRequest> body) {
        return body.map(request -> {
            String id = UUID.randomUUID().toString();
            OrderView created = new OrderView(
                id, request.customer(), request.quantity(), "NEW"
            );
            orders.put(id, created);
            return ResponseEntity
                .created(URI.create("/api/orders/" + id))
                .body(created);
        });
    }

    @PutMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<OrderView>> replace(
            @PathVariable("id") String id,
            @RequestBody Mono<CreateOrderRequest> body) {
        return body.map(request -> {
            AtomicReference<OrderView> replaced =
                new AtomicReference<>();

            orders.computeIfPresent(id, (key, current) -> {
                OrderView next = new OrderView(
                    id, request.customer(), request.quantity(), "NEW"
                );
                replaced.set(next);
                return next;
            });

            OrderView result = replaced.get();
            return result == null
                ? ResponseEntity.<OrderView>notFound().build()
                : ResponseEntity.ok(result);
        });
    }

    @PatchMapping(
        path = "/{id}/status",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<OrderView>> changeStatus(
            @PathVariable("id") String id,
            @RequestBody Mono<StatusPatch> body) {
        return body.map(patch -> {
            AtomicReference<OrderView> updated =
                new AtomicReference<>();

            orders.computeIfPresent(id, (key, current) -> {
                OrderView next = new OrderView(
                    current.id(), current.customer(),
                    current.quantity(), patch.status()
                );
                updated.set(next);
                return next;
            });

            OrderView result = updated.get();
            return result == null
                ? ResponseEntity.<OrderView>notFound().build()
                : ResponseEntity.ok(result);
        });
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(
            @PathVariable("id") String id) {
        OrderView removed = orders.remove(id);
        return removed == null
            ? ResponseEntity.<Void>notFound().build()
            : ResponseEntity.noContent().build();
    }
}
~~~

Đây là chương trình Spring Boot hoàn chỉnh ở mức demo; không dùng database và dữ liệu nằm trong bộ nhớ của process. `ConcurrentHashMap` bảo vệ thao tác map cơ bản trước truy cập đồng thời, nhưng ví dụ không thay thế transaction hoặc persistence cho ứng dụng thật. `AtomicReference` trong PUT/PATCH giúp lấy kết quả của phép cập nhật nguyên tử `computeIfPresent` để phân biệt ID tồn tại với không tồn tại.

Chạy ứng dụng:

~~~bash
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun`; trên Windows dùng `gradlew.bat bootRun`. Mặc định Spring Boot khởi động server tại cổng 8080 nếu không cấu hình khác.

### 7.2. Gọi các endpoint

Liệt kê tất cả:

~~~bash
curl -i http://localhost:8080/api/orders
~~~

Lọc bằng query parameter:

~~~bash
curl -i "http://localhost:8080/api/orders?status=PAID"
~~~

Tìm theo path variable:

~~~bash
curl -i http://localhost:8080/api/orders/o-1
~~~

Tìm qua handler có điều kiện `params`:

~~~bash
curl -i "http://localhost:8080/api/orders/search?status=NEW"
~~~

Tạo đơn hàng:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":3}'
~~~

Thay thế đơn hàng:

~~~bash
curl -i -X PUT http://localhost:8080/api/orders/o-1 \
  -H "Content-Type: application/json" \
  -d '{"customer":"An Nguyen","quantity":4}'
~~~

Cập nhật trạng thái:

~~~bash
curl -i -X PATCH http://localhost:8080/api/orders/o-1/status \
  -H "Content-Type: application/json" \
  -d '{"status":"PAID"}'
~~~

Xóa:

~~~bash
curl -i -X DELETE http://localhost:8080/api/orders/o-1
~~~

Các lệnh trên minh họa cách gọi endpoint; body phản hồi thực tế của POST/PUT/PATCH chứa UUID và dữ liệu tương ứng. Không có một stdout cố định cho toàn bộ các lệnh vì UUID được tạo ngẫu nhiên và trạng thái map thay đổi theo thứ tự gọi.

## 8. Mapping condition và lỗi thường gặp

### 8.1. Cùng path, khác HTTP method

Hai handler sau là hợp lệ vì method khác nhau:

~~~java
@GetMapping("/{id}")
Mono<Product> get(@PathVariable("id") String id) {
    // ...
}

@DeleteMapping("/{id}")
Mono<Void> delete(@PathVariable("id") String id) {
    // ...
}
~~~

Nếu client gọi POST tới path này nhưng không có POST mapping phù hợp, Spring có thể trả 405 Method Not Allowed khi path tồn tại nhưng HTTP method không được hỗ trợ.

### 8.2. Cùng path, khác params hoặc headers

~~~java
@GetMapping(path = "/reports", params = "format=csv")
Mono<byte[]> csv() {
    // ...
}

@GetMapping(path = "/reports", params = "format=json")
Mono<Report> json() {
    // ...
}
~~~

Mỗi handler có điều kiện query riêng. Nếu thêm handler mặc định không có điều kiện, cần cân nhắc mức độ cụ thể và đảm bảo mapping cụ thể hơn được chọn như mong muốn. Tránh các điều kiện trùng hoặc chồng lấn khó phân giải.

### 8.3. Sai Content-Type hoặc Accept

- Gửi body XML tới handler chỉ `consumes="application/json"` có thể dẫn tới 415.
- Gửi `Accept: application/xml` tới handler chỉ `produces="application/json"` có thể dẫn tới 406.
- Thiếu body hoặc JSON không hợp lệ có thể gây lỗi đọc/giải mã request body; đây không phải lỗi mapping giống 415.

Hãy phân biệt **không có handler phù hợp** với **handler có nhưng body không bind được**. Log/trace mapping và codec error riêng sẽ giúp tìm nguyên nhân.

### 8.4. Dùng nhiều mapping annotation trên cùng method

Không viết:

~~~java
@GetMapping("/items")
@PostMapping("/items")
public Mono<Void> handle() {
    // ...
}
~~~

Các annotation chuyên biệt đều là composed annotation của `@RequestMapping`. Spring không ghép hai annotation trên cùng method thành một mapping có cả GET và POST; khi phát hiện nhiều mapping annotation trên cùng element, Spring ghi warning và chỉ dùng mapping đầu tiên. Nếu thực sự cần nhiều HTTP methods cho một handler, khai báo một `@RequestMapping(path=..., method={...})` duy nhất và hiểu rõ hợp đồng của endpoint. Thông thường nên tách method để mỗi HTTP method có semantics và body/response riêng.

### 8.5. Nhầm mapping condition với argument binding

~~~java
@GetMapping(path = "/search", params = "status")
Flux<Order> search(@RequestParam("status") String status) {
    // ...
}
~~~

`params="status"` chỉ cho phép mapping khi query parameter tồn tại; `@RequestParam` mới đưa giá trị đó vào tham số Java. Có thể dùng `@RequestParam` mà không khai báo `params` nếu không cần chọn handler theo sự hiện diện của parameter.

### 8.6. Nhầm consumes và produces

- `consumes`: client **gửi** nội dung loại gì?
- `produces`: server **trả** nội dung loại gì theo thương lượng Accept?

Đổi nhầm hai thuộc tính thường khiến endpoint không khớp request hoặc phản hồi 406/415 ngoài dự kiến.

## 9. Cách Spring chọn handler khi nhiều mapping cùng khớp

Spring so sánh các điều kiện mapping, không chỉ nhìn path. Những yếu tố quan trọng gồm:

1. Path pattern nào cụ thể hơn.
2. HTTP method có khớp không.
3. Query parameter và header conditions.
4. Request Content-Type có khớp `consumes` không.
5. Accept có tương thích `produces` không.

Ví dụ `/orders/search` cụ thể hơn `/orders/{id}` khi cả hai có thể khớp chuỗi path. Spring WebFlux dùng `PathPattern` và bộ so sánh specificity để chọn pattern phù hợp hơn. Tuy nhiên, nếu hai mapping có cùng độ cụ thể và cùng điều kiện, ứng dụng có thể gặp ambiguous mapping; không dựa vào thứ tự khai báo method để giải quyết xung đột.

Khi ứng dụng khởi động, mapping trùng hoàn toàn thường được phát hiện lúc đăng ký handler. Các mapping khác nhau nhưng vẫn có thể cùng khớp một request cần được thiết kế rõ để tránh lỗi runtime.

**Một nguyên tắc hữu ích:** mỗi endpoint nên có một hợp đồng path + HTTP method + điều kiện request đủ rõ. Dùng query/header condition khi nó thực sự phân biệt biến thể endpoint; nếu chỉ là bộ lọc dữ liệu, thường nên bind bằng `@RequestParam` rồi xử lý trong logic.

## 10. Reactive request body và response

Trong Spring WebFlux, handler có thể nhận và trả publisher:

~~~java
@PostMapping
Mono<ResponseEntity<ProductView>> create(
        @RequestBody Mono<CreateProduct> body) {
    return body.flatMap(service::create)
        .map(saved -> ResponseEntity
            .created(URI.create("/api/products/" + saved.id()))
            .body(saved));
}
~~~

Đây là snippet tích hợp với `service.create` trả `Mono<ProductView>`. Spring WebFlux đọc body bất đồng bộ, đưa đối tượng vào publisher, rồi handler ghép công việc service mà không cần chặn thread.

Một số kiểu chữ ký phổ biến:

| Tham số/giá trị trả về | Ý nghĩa |
| --- | --- |
| `@RequestBody Mono<T>` | Nhận body đơn, giải mã thành một đối tượng bất đồng bộ. |
| `@RequestBody Flux<T>` | Nhận body dạng stream các phần tử khi codec và media type hỗ trợ. |
| `Mono<T>` | Không hoặc một giá trị response. |
| `Flux<T>` | Nhiều giá trị response; cách encode phụ thuộc media type. |
| `Mono<ResponseEntity<T>>` | Response status, headers và body được quyết định bất đồng bộ. |
| `Mono<Void>` | Chỉ báo completion/error, không có body giá trị. |

**Không gọi `block()` hoặc `subscribe()` bên trong controller** để lấy body hay khởi chạy service. Hãy trả publisher đã ghép; WebFlux quản lý subscription, cancellation và ghi response.

## 11. Kiểm thử mapping với WebTestClient

WebTestClient có thể kiểm thử controller WebFlux mà không cần khởi động server thật. Trong dự án ở mục 7, tạo file `src/test/java/demo/OrderControllerTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrderControllerTest {

    private final WebTestClient client =
        WebTestClient.bindToController(new OrderController()).build();

    @Test
    void getMappingUsesPathVariable() {
        client.get()
            .uri("/api/orders/o-1")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("o-1");
    }

    @Test
    void queryParameterSelectsSearchMapping() {
        client.get()
            .uri("/api/orders/search?status=PAID")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].status").isEqualTo("PAID");
    }

    @Test
    void postMappingCreatesResource() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("Lan", 3))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.customer").isEqualTo("Lan")
            .jsonPath("$.quantity").isEqualTo(3);
    }

    @Test
    void optionsReportsAllowedMethods() {
        client.options()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Allow");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc `./gradlew test` / `gradlew.bat test`. Các test xác minh:

- GET mapping nhận path variable và trả JSON.
- Query parameter được dùng để chọn handler có điều kiện.
- POST mapping nhận JSON và trả 201 cùng header Location.
- OPTIONS được Spring hỗ trợ và cung cấp Allow cho path.

Trong controller demo, dữ liệu khởi tạo có `o-2` với status `PAID`, vì vậy test search có kết quả. Nếu đổi fixture, hãy cập nhật kỳ vọng. Với các test chạy song song hoặc test POST/PUT/PATCH/DELETE, tạo controller riêng cho mỗi test hoặc reset fixture để tránh phụ thuộc trạng thái dùng chung.

## 12. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `@RequestMapping` không khai báo method cho endpoint chỉ cần GET | Endpoint có thể khớp nhiều HTTP methods hơn dự kiến | Dùng `@GetMapping` hoặc khai báo `method` rõ ràng |
| Lặp lại prefix path ở mọi method | URL khó bảo trì, dễ lệch route | Đặt prefix chung ở cấp lớp |
| Dùng `@GetMapping` và `@PostMapping` trên cùng method | Spring không hợp nhất thành một mapping; chỉ một mapping được dùng | Tách handler hoặc dùng một `@RequestMapping(method={...})` có chủ đích |
| Nghĩ `params` tự bind query vào biến Java | Handler được chọn nhưng biến chưa được bind nếu thiếu `@RequestParam` | Dùng `@RequestParam` cho argument |
| Dùng `produces` để kiểm tra Content-Type request | Sai chiều content negotiation | Dùng `consumes` cho request, `produces` cho response |
| Không khai báo `consumes` cho body nhiều định dạng | Handler có thể nhận request không phù hợp codec/logic | Khai báo media type và triển khai parser tương ứng |
| Tạo hai mapping cùng path/method/condition | Lỗi ambiguous hoặc đăng ký mapping trùng | Làm rõ path, params, headers hoặc tách controller |
| Dùng `@PathVariable` nhưng path không có biến tương ứng | Binding thất bại | Kiểm tra tên placeholder và annotation |
| Cho rằng `@PatchMapping` tự merge JSON object | Annotation chỉ chọn HTTP method/path; logic patch do ứng dụng quyết định | Thiết kế DTO/JSON Patch/Merge Patch và semantics rõ |
| Trả `Flux` và nghĩ mặc định là SSE | Codec có thể encode thành JSON array hoặc dạng khác theo media type | Khai báo `produces` phù hợp như `text/event-stream` khi cần SSE |
| Gọi `block()` trong controller reactive | Chặn event-loop hoặc bị Reactor từ chối | Trả `Mono`/`Flux` và ghép bằng operator |
| Chỉ test status 200 | Có thể bỏ sót sai path, header, content type hoặc body | Dùng WebTestClient kiểm tra toàn hợp đồng HTTP |

## 13. Checklist thiết kế controller mapping

Trước khi thêm endpoint, hãy kiểm tra:

1. **Tài nguyên và path:** URL thể hiện tài nguyên nào? Path cấp lớp có dùng chung hợp lý không?
2. **HTTP method:** GET/POST/PUT/PATCH/DELETE có đúng semantics và khả năng retry/idempotency không?
3. **Path variable và query:** dữ liệu định danh nằm trong path; bộ lọc/phân trang thường ở query. Có cần điều kiện `params` để chọn handler hay chỉ cần `@RequestParam`?
4. **Media type:** request body chấp nhận loại nào (`consumes`)? response có loại nào (`produces`)?
5. **Headers:** header nào thực sự tham gia chọn mapping? Có thể dùng cơ chế authentication/CORS riêng thay vì biến header thành điều kiện route không?
6. **Mapping specificity:** có route trùng hoặc chồng lấn? Literal path và variable path có được phân biệt rõ?
7. **Reactive lifecycle:** handler có trả publisher thay vì tự subscribe/block? Body/response có thể rỗng, lỗi hoặc bị hủy như thế nào?
8. **Status và headers:** POST tạo mới có 201/Location? GET không tìm thấy có 404? DELETE thành công có 204? API có tài liệu hóa các trường hợp đó không?
9. **Test:** WebTestClient đã kiểm tra method, URL, params, header, media type, status và body chưa?

**Ghi nhớ:** `@RequestMapping` mô tả các điều kiện để một request được chọn vào handler; `@GetMapping`/`@PostMapping`/`@PutMapping`/`@PatchMapping`/`@DeleteMapping` giúp khai báo HTTP method cụ thể. Hãy kết hợp path ở cấp lớp, điều kiện request ở cấp method, media type đúng chiều và chữ ký reactive phù hợp. Mapping rõ ràng làm API dễ hiểu, dễ kiểm thử và tránh nhận nhầm request.

## Tài liệu tham khảo

- Spring Framework — WebFlux: Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
