# @ResponseStatus, phản hồi không có nội dung và trường hợp body null trong Spring MVC

## 1. Mục tiêu

Trong REST API, **HTTP status** và **HTTP response body** là hai yếu tố riêng. Một handler có thể thành công với body JSON, thành công nhưng không có body, hoặc không tìm thấy tài nguyên. Trong Spring MVC, việc trả `null` từ controller **không tự động** có nghĩa là HTTP 204 hay 404. Bài học giải thích cụ thể hành vi này, cách sử dụng `@ResponseStatus` và `ResponseEntity`, cách phân biệt *body vắng mặt* với *giá trị JSON `null`*, cũng như cách kiểm thử kết quả trên dây HTTP.

Sau bài này, bạn có thể:

- Gắn status cố định cho handler bằng `@ResponseStatus` và hiểu giới hạn của `reason`.
- Chọn rõ HTTP 200, 201, 202, 204 và 404 theo tình huống REST.
- Dùng `void`, `ResponseEntity<Void>`, `ResponseEntity.noContent().build()` và `ResponseEntity.notFound().build()` hợp lý.
- Phân biệt `return null`, `ResponseEntity.ok().body(null)`, JSON literal `null`, và property có giá trị null trong JSON object.
- Tránh gửi nội dung cho response 204; viết MockMvc tests xác nhận status và body thực tế.

Ví dụ được thiết kế cho **Spring MVC Servlet stack, Java 17+, Spring Boot 3.x**. Các nguyên tắc HTTP không phụ thuộc riêng Spring. Nếu dự án dùng Spring WebFlux, các API reactive như `Mono` và `ServerResponse` có quy tắc vận hành riêng; không áp dụng máy móc các ví dụ Servlet MVC.

## 2. HTTP status khác với việc body có hay không

Xem các response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"name":"Spring"}
~~~

~~~http
HTTP/1.1 200 OK

~~~

~~~http
HTTP/1.1 204 No Content

~~~

Response thứ hai có **200 OK, body rỗng**. Response thứ ba có **204 No Content**, tức một thông điệp ngữ nghĩa mạnh hơn: yêu cầu đã được xử lý thành công và không có nội dung response. Hai kết quả không tương đương chỉ vì đều không hiển thị dữ liệu sau header.

| Status | Ý nghĩa thường dùng | Response body |
| --- | --- | --- |
| `200 OK` | Request thành công; có thể trả representation hoặc response rỗng theo contract cụ thể | Có thể có hoặc không |
| `201 Created` | Tài nguyên đã được tạo | Có thể chứa representation; thường thêm `Location` |
| `202 Accepted` | Đã chấp nhận xử lý, chưa nhất thiết xử lý xong | Có thể có thông tin tiến độ hoặc rỗng |
| `204 No Content` | Thành công, không gửi message content | **Không được chứa body** |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc không tiết lộ sự tồn tại | Có thể có body lỗi, tùy thiết kế |
| `304 Not Modified` | Phản hồi điều kiện/cache, không trả representation | Không có message content; không phải thành công upload |
| `205 Reset Content` | Thành công và yêu cầu user agent reset view | Không được tạo content |
  
Theo RFC 9110, response **1xx, 204 và 304 không có message content**; request `HEAD` cũng không có response content dù có thể trả metadata. Đặc biệt **204 không được chứa `Content-Length`**. Không tạo JSON `{}`, `[]` hay `null` rồi tự đặt status 204, vì như vậy gửi cả body vào một trạng thái cấm body.

`200` với body rỗng đôi khi hợp lệ, nhưng nếu endpoint đang hứa trả một object JSON thì nó dễ khiến client nhầm. Khi tài nguyên không tồn tại, API thường nên trả `404` rõ ràng thay vì `200` rỗng; khi delete đã hoàn tất và không trả tài nguyên, `204` thường diễn đạt ý định tốt hơn.

## 3. `@ResponseStatus` đặt status tĩnh cho handler

Annotation `org.springframework.web.bind.annotation.ResponseStatus` có thể được đặt lên một handler method hoặc class exception. Trên handler method, nó khai báo status thường dùng cho mọi kết quả thành công đi theo nhánh method đó.

~~~java
@PostMapping("/orders")
@ResponseStatus(HttpStatus.CREATED)
public OrderView create(@RequestBody CreateOrderRequest request) {
    return new OrderView(42L, request.product());
}
~~~

Đây là **đoạn minh họa bên trong controller**, chưa phải chương trình chạy độc lập. Nếu handler xử lý thành công, response thường có **201 Created** và JSON của `OrderView`. `@ResponseStatus(HttpStatus.CREATED)` tương đương `@ResponseStatus(code = HttpStatus.CREATED)`; thuộc tính `value` là alias của `code`.

Khai báo status cho endpoint không tạo tài nguyên hoặc representation:

~~~java
@DeleteMapping("/orders/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    // Service xóa (hoặc bảo đảm tài nguyên không còn tồn tại).
}
~~~

**Kết quả hợp lý:** 204 với body rỗng, nếu xóa thành công. `void` chỉ là kiểu trả về Java; **204 được chỉ định bởi `@ResponseStatus`**.

Một ví dụ khác:

~~~java
@PostMapping("/jobs")
@ResponseStatus(HttpStatus.ACCEPTED)
public void submitJob(@RequestBody JobRequest job) {
    // Chấp nhận và đẩy job vào hàng đợi để xử lý sau.
}
~~~

Status `202 Accepted` chỉ nên dùng khi hệ thống **thực sự** có cơ chế tiếp nhận công việc bất đồng bộ; status này không bảo đảm đã xử lý xong. Đây cũng là đoạn minh họa, cần DTO, hàng đợi và xử lý lỗi thích hợp.

### Các đặc điểm quan trọng

- `@ResponseStatus` khai báo status **tĩnh**. Nếu cùng một endpoint đôi khi trả 200, đôi khi trả 404 hoặc 201, nên dùng `ResponseEntity`, `ResponseStatusException` hoặc exception handler thích hợp.
- Có thể đặt annotation ở mức controller class, từ đó áp dụng cho những handler phù hợp của class. Tuy nhiên cách đó dễ gán status không hợp lý cho nhiều endpoint; thường ưu tiên gắn trực tiếp từng method.
- Nếu handler ném exception, annotation status thành công trên method không có nghĩa exception vẫn trả status đó. Spring xử lý exception qua các exception resolver.
- Không dùng `@ResponseStatus` như thay thế cho kiểm tra quyền truy cập, validation hoặc transaction; nó chủ yếu là metadata của response.

### Tránh `reason` đối với REST JSON

Ví dụ sau **chỉ để nhận diện rủi ro, không nên áp dụng cho REST endpoint trả JSON**:

~~~java
@ResponseStatus(
        code = HttpStatus.BAD_REQUEST,
        reason = "Invalid request")
~~~

Khi `reason` khác chuỗi rỗng, Spring MVC dùng `HttpServletResponse.sendError(...)`. Nó có thể kích hoạt cơ chế error page của Servlet container hoặc Spring Boot và không cho handler viết response body theo cách thông thường; body cuối có thể là HTML, JSON lỗi hoặc cấu trúc khác tùy error handling. **Không hứa hẹn một JSON body cố định** từ `reason`.

Với API cần body lỗi có cấu trúc rõ, hãy dùng `ResponseEntity`, `ProblemDetail` và/hoặc `@RestControllerAdvice`. Điều này còn giúp client xử lý `status`, `type`, `detail` theo contract đã thống nhất.

### Không trộn tùy tiện `@ResponseStatus` với `ResponseEntity`

`ResponseEntity` cho phép chủ động cung cấp status, headers và body, trong khi `@ResponseStatus` cung cấp status tĩnh. Trong Spring Framework 6.x, status khai báo trên `ResponseEntity` có thể được ghi sau và có hiệu lực so với status annotation. **Không dựa vào thứ tự áp dụng để tạo logic phức tạp.** Với method trả `ResponseEntity`, hãy đặt status ngay trong object đó và bỏ annotation để người đọc hiểu chính xác.

## 4. `void` và response không có nội dung

Xét ba mẫu:

~~~java
// Mẫu A: không đặt status tường minh.
@GetMapping("/ping")
public void ping() {
}

// Mẫu B: đặt 204 bằng @ResponseStatus.
@DeleteMapping("/tasks/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
}

// Mẫu C: ResponseEntity thể hiện status và body rỗng.
@GetMapping("/health-ack")
public ResponseEntity<Void> acknowledge() {
    return ResponseEntity.ok().build();
}
~~~

Đây là **các handler minh họa đặt trong `@RestController`**; thiếu import, class và xử lý nghiệp vụ. Trong Spring MVC REST thông thường:

- A: status **200** mặc định, không có body; không tự động là 204.
- B: status **204**, không có body; status 204 đến từ annotation.
- C: status **200**, không có body, do `ResponseEntity.ok().build()` khai báo.

Với yêu cầu xóa thành công không cần response representation, có thể chọn:

~~~java
public ResponseEntity<Void> delete() {
    return ResponseEntity.noContent().build();
}
~~~

Dạng này hữu ích khi cùng handler có các nhánh kết quả khác nhau, nhưng ví dụ chỉ là **phần thân minh họa**; trong controller phải có mapping và xử lý xóa trước khi trả. `ResponseEntity<Void>` cho biết kiểu payload không dự kiến tồn tại. Nếu cần custom headers dù không có body, `ResponseEntity` cũng thuận tiện.

**Không tự suy ra status từ việc không viết body.** Framework nhìn vào annotation, `ResponseEntity`, exception và trạng thái HTTP response. Hãy chủ động khai báo status để giữ REST contract ổn định.

## 5. Body null: bốn trường hợp rất dễ nhầm

### 5.1. `return null` từ handler `@RestController`

~~~java
@GetMapping("/users/{id}/naive")
public UserDto findUser(@PathVariable long id) {
    return null;
}
~~~

Trong Spring MVC với `@RestController`/`@ResponseBody` thông thường, một giá trị trả về `null` **không tạo JSON text `null`**. Nếu không có nơi khác đặt status, response thường vẫn **200 OK** với body rỗng. Đây là một lỗi thiết kế phổ biến khi repository/service báo không tìm thấy bằng `null` mà controller truyền nguyên kết quả về client.

Với `@Controller` kiểu HTML view (không có `@ResponseBody`), `null`/`void` có thể còn tham gia cơ chế chọn view mặc định. Vì vậy luôn xét loại controller và cách Spring xử lý return value trước khi kết luận.

### 5.2. `ResponseEntity.ok().body(null)`

~~~java
@GetMapping("/users/empty")
public ResponseEntity<UserDto> emptyOk() {
    return ResponseEntity.ok().body(null);
}
~~~

Đoạn này cũng thường tạo **200 OK với body vắng mặt**, vì payload trong `ResponseEntity` là `null`. Header có thể khác tùy config; điều quan trọng là không có bốn byte `null` được ghi ra.

`ResponseEntity.ok().build()` diễn đạt “OK không có body” rõ hơn, còn `ResponseEntity.noContent().build()` diễn đạt “No Content” khi contract đòi 204.

**Đừng trả chính object `ResponseEntity` bằng `null`** rồi kỳ vọng client nhận 404. Việc không có `ResponseEntity` đồng nghĩa bạn cũng không khai báo status/headers một cách rõ ràng.

### 5.3. JSON literal `null`

JSON literal `null` là một payload hợp lệ gồm **4 byte UTF-8** (`n`, `u`, `l`, `l`). Đó là **body có nội dung**, khác body có độ dài bằng 0.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

null
~~~

Nếu contract cố ý yêu cầu một JSON null literal, có thể tạo body `"null"` với media type JSON một cách tường minh:

~~~java
@GetMapping("/literal-null")
public ResponseEntity<String> literalNull() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body("null");
}
~~~

Đây là ví dụ đơn giản về bytes của payload; dùng trong ứng dụng thật **chỉ khi API contract thực sự định nghĩa JSON literal `null`**. Đừng dùng cách này để che việc resource không tồn tại. Với các object JSON thông thường, để Jackson serialize một DTO thật và kiểm thử representation là đủ.

### 5.4. Property null bên trong một JSON object

~~~json
{"id":1,"name":null}
~~~

Ở đây response body **không rỗng**: JSON object tồn tại, chỉ property `name` có giá trị null. Ví dụ với Jackson mặc định của Spring Boot 3.x, DTO có `name == null` thường được ghi thành thuộc tính JSON null. Nếu cấu hình `@JsonInclude(Include.NON_NULL)` hoặc `spring.jackson.default-property-inclusion=non_null`, thuộc tính đó có thể bị lược bỏ:

~~~json
{"id":1}
~~~

Ba dạng `{"name":null}`, `{}` và **không có body** là những contract khác nhau. Client cần kiểm tra status trước, sau đó chỉ parse JSON khi response thực sự có representation hợp lệ.

### Bảng so sánh

| Controller trả về | Status điển hình | Nội dung body |
| --- | --- | --- |
| `return new UserDto(...)` trong `@RestController` | 200 | JSON object |
| `return null` trong `@RestController` | 200 nếu không có status khác | Không có body |
| `ResponseEntity.ok().body(null)` | 200 | Không có body |
| `ResponseEntity.ok().build()` | 200 | Không có body |
| `ResponseEntity.noContent().build()` | 204 | Không có body |
| `ResponseEntity.notFound().build()` | 404 | Không có body |
| `ResponseEntity.ok().contentType(APPLICATION_JSON).body("null")` | 200 | JSON literal `null` |
| DTO có property null | 200 | JSON object có `null` hoặc lược bỏ property tùy Jackson |

Các kết quả trên giả sử **không có filter, advice, interceptor hay servlet response logic tùy chỉnh** thay đổi status/body.

## 6. Khi không tìm thấy tài nguyên: dùng 404, không dựa vào null

Với API lấy resource `GET /users/42`, có thể lấy kết quả kiểu `Optional<UserDto>` từ service và biểu diễn “không tìm thấy” thành 404:

~~~java
@GetMapping("/users/{id}")
public ResponseEntity<UserDto> find(@PathVariable long id) {
    Optional<UserDto> found = service.findById(id);
    return ResponseEntity.of(found);
}
~~~

Đây là code minh họa trong controller có `service` được inject và import `Optional`; không phải file độc lập.

`ResponseEntity.of(Optional<T>)` (trong các phiên bản Spring Framework 6.x) trả 200 cùng body khi `Optional` chứa giá trị, hoặc 404 không có body khi `Optional.empty()`. Cũng có thể viết rõ:

~~~java
UserDto user = service.findByIdOrNull(id);
if (user == null) {
    return ResponseEntity.notFound().build();
}
return ResponseEntity.ok(user);
~~~

Đoạn này cũng chỉ là minh họa, với kiểu trả về `ResponseEntity<UserDto>` và `service` có method thích hợp.

Nếu “không tìm thấy” là ngoại lệ nghiệp vụ, có thể ném:

~~~java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "User does not exist");
~~~

Spring MVC sẽ xử lý thành **404** nếu không có handler khác override; body lỗi phụ thuộc cấu hình Spring Boot, Problem Details và các exception handlers. Đừng giả định luôn có hoặc luôn không có JSON body.

## 7. Ví dụ Spring Boot 3.x chạy được

Tạo project bằng Spring Initializr: **Java 17+**, **Maven**, **Spring Boot 3.x**, dependencies `spring-boot-starter-web` và `spring-boot-starter-test`. Các class dưới đây ở package `com.example.demo`. Ứng dụng minh họa dữ liệu cố định để status có thể kiểm thử xác định; nó **không lưu/xóa dữ liệu thật** và không có Spring Security.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/StatusController.java
src/test/java/com/example/demo/StatusControllerTest.java
~~~

### 7.1. `DemoApplication.java`

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

### 7.2. `StatusController.java`

~~~java
package com.example.demo;

import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/items")
public class StatusController {

    // Nguồn dữ liệu giả lập: chỉ id=1 tồn tại.
    private Item find(long id) {
        return id == 1L ? new Item(1L, "Spring") : null;
    }

    // Tình huống cố ý chưa tốt: không tìm thấy -> 200 với body rỗng.
    @GetMapping("/{id}")
    public Item naiveFind(@PathVariable long id) {
        return find(id);
    }

    // Contract rõ: có tài nguyên -> 200; không có -> 404.
    @GetMapping("/{id}/checked")
    public ResponseEntity<Item> checkedFind(@PathVariable long id) {
        Item item = find(id);
        if (item == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(item);
    }

    // Annotation đặt status cố định: tạo thành công -> 201 và body.
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Item create(@RequestBody ItemRequest request) {
        return new Item(2L, request.name());
    }

    // Tương đương hướng tạo có Location, linh hoạt bằng ResponseEntity.
    @PostMapping("/with-location")
    public ResponseEntity<Item> createWithLocation(
            @RequestBody ItemRequest request) {
        Item created = new Item(2L, request.name());
        return ResponseEntity
                .created(URI.create("/api/items/2"))
                .body(created);
    }

    // Xóa giả lập thành công -> 204, body rỗng.
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable long id) {
        // Demo không có repository; production phải xử lý nghiệp vụ.
    }

    // Không có body vẫn có thể là 200.
    @GetMapping("/empty-ok")
    public ResponseEntity<Void> emptyOk() {
        return ResponseEntity.ok().build();
    }

    // null payload trong ResponseEntity -> 200 với body rỗng.
    @GetMapping("/null-body")
    public ResponseEntity<Item> nullBody() {
        return ResponseEntity.ok().body(null);
    }

    // Cố ý gửi JSON literal null, khác body rỗng.
    @GetMapping("/literal-null")
    public ResponseEntity<String> literalNull() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body("null");
    }

    // JSON object có property null.
    @GetMapping("/null-property")
    public ItemWithNullableProperty nullProperty() {
        return new ItemWithNullableProperty(1L, null);
    }

    // Một nhánh 404 qua exception thay cho ResponseEntity.
    @GetMapping("/{id}/required")
    public Item required(@PathVariable long id) {
        Item item = find(id);
        if (item == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Item does not exist");
        }
        return item;
    }

    public record Item(long id, String name) {}
    public record ItemRequest(String name) {}
    public record ItemWithNullableProperty(long id, String name) {}
}
~~~

**Điểm cần hiểu:**

- `find(1)` tạo DTO; `find(99)` trả `null`. Đây là dữ liệu giả để minh họa, không phải repository thật.
- `GET /api/items/99` cố tình trả `null` từ `@RestController`, minh họa **200 rỗng dù tài nguyên không tồn tại**. Không sử dụng mẫu naive này làm API production.
- `GET /api/items/99/checked` chủ động trả **404**. Với id 1, method trả DTO **200 JSON**.
- `POST /api/items` dùng `@ResponseStatus(CREATED)` để đặt **201** cố định. `POST /api/items/with-location` dùng `ResponseEntity.created(...)` để đặt **201** và header `Location: /api/items/2`.
- `DELETE /api/items/1` là demo no-op: response **204** do annotation. Trong dự án thật, chỉ trả thành công sau khi service xử lý đúng; trường hợp xóa id không tồn tại có thể quyết định 204 hoặc 404 theo hợp đồng API.
- `GET /api/items/empty-ok` và `GET /api/items/null-body` đều có **200, không có body**. `GET /api/items/literal-null` có **200 với body bốn byte `null`**.
- `GET /api/items/null-property` trả object; với Jackson mặc định Boot 3.x, JSON có property `name` mang null.
- `GET /api/items/99/required` dùng `ResponseStatusException` để phản hồi **404**; nội dung lỗi tùy thuộc cấu hình.

**Đây là bài dạy về response contract.** Ví dụ tạo/xóa chỉ minh họa status, không giả lập tính đúng đắn của database, giao dịch hay quyền truy cập.

## 8. Gọi API với curl và đọc response thực tế

Chạy trong thư mục có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper, chạy `mvn spring-boot:run` sau khi cài Maven.

### 8.1. Xem status 200 có body và 200 không body

~~~bash
curl -i http://localhost:8080/api/items/1
curl -i http://localhost:8080/api/items/99
curl -i http://localhost:8080/api/items/empty-ok
curl -i http://localhost:8080/api/items/null-body
~~~

Phản hồi đầu là **200** với JSON:

~~~json
{"id":1,"name":"Spring"}
~~~

Ba phản hồi tiếp theo đều là **200** với body rỗng trong cấu hình mẫu. Đây là bằng chứng quan trọng rằng status 200 **không nói lên** body có JSON hay không.

### 8.2. Xem 404 và 204 rõ ràng

~~~bash
curl -i http://localhost:8080/api/items/99/checked
curl -i -X DELETE http://localhost:8080/api/items/1
~~~

Dòng đầu trả **404 Not Found** với body rỗng do `ResponseEntity.notFound().build()`. Dòng thứ hai trả **204 No Content** mà không gửi body. Đừng thử `response.json()` trên fetch response 204 vì không có JSON để parse.

### 8.3. Status 201 khi tạo resource

~~~bash
curl -i -X POST "http://localhost:8080/api/items"   -H "Content-Type: application/json"   --data-binary '{"name":"MVC"}'
~~~

Status **201 Created**, body:

~~~json
{"id":2,"name":"MVC"}
~~~

Nếu dùng `/api/items/with-location`, status cũng **201**, cộng header `Location: /api/items/2`. URI trong ví dụ là relative URI hợp lệ trong header Location; service thực tế cần trỏ tới resource có thể truy cập, không trả một link giả.

### 8.4. So sánh JSON `null` và body rỗng

~~~bash
curl -i http://localhost:8080/api/items/literal-null
curl -i http://localhost:8080/api/items/null-property
~~~

Kết quả có nội dung lần lượt là:

~~~json
null
~~~

~~~json
{"id":1,"name":null}
~~~

Khác với `/api/items/null-body`, cả hai response trên có **JSON payload thực sự**. Có thể xem bằng `curl -i` hoặc tab Network trong trình duyệt, nhưng không kết luận chỉ qua việc terminal hiển thị trắng vì có thể còn các byte newline/whitespace. Khi cần kiểm chứng chặt, test `MockMvc` với `content().string("")` và `content().string("null")`.

Các lệnh multiline dùng ký tự `\` của Linux/macOS/Git Bash. Trong PowerShell, dùng `curl.exe` và viết tham số trên một dòng hoặc thay bằng cú pháp nối dòng đúng của PowerShell; cách quote chuỗi JSON cần điều chỉnh theo shell.

## 9. Kiểm thử MockMvc: so đồng thời status, body và Location

Bổ sung `spring-boot-starter-test`. Tạo **`src/test/java/com/example/demo/StatusControllerTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StatusController.class)
class StatusControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void successReturns200WithJson() throws Exception {
        mockMvc.perform(get("/api/items/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Spring"));
    }

    @Test
    void naiveMissingResourceIs200WithEmptyBody() throws Exception {
        mockMvc.perform(get("/api/items/99"))
                .andExpect(status().isOk())
                .andExpect(content().string(""));
    }

    @Test
    void missingResourceHandledExplicitlyIs404() throws Exception {
        mockMvc.perform(get("/api/items/99/checked"))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));
    }

    @Test
    void deleteReturns204WithoutBody() throws Exception {
        mockMvc.perform(delete("/api/items/1"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));
    }

    @Test
    void createReturns201AndJson() throws Exception {
        mockMvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"MVC\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(2))
                .andExpect(jsonPath("$.name").value("MVC"));
    }

    @Test
    void createWithLocationReturns201AndLocation() throws Exception {
        mockMvc.perform(post("/api/items/with-location")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"MVC\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/items/2"))
                .andExpect(jsonPath("$.name").value("MVC"));
    }

    @Test
    void emptyOkAndNullBodyRemain200WithNoBody() throws Exception {
        mockMvc.perform(get("/api/items/empty-ok"))
                .andExpect(status().isOk())
                .andExpect(content().string(""));

        mockMvc.perform(get("/api/items/null-body"))
                .andExpect(status().isOk())
                .andExpect(content().string(""));
    }

    @Test
    void literalNullIsFourCharactersNotEmptyBody() throws Exception {
        mockMvc.perform(get("/api/items/literal-null"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(content().string("null"));
    }

    @Test
    void nullPropertyIsStillAJsonObject() throws Exception {
        mockMvc.perform(get("/api/items/null-property"))
                .andExpect(status().isOk())
                .andExpect(content().json(
                        "{\"id\":1,\"name\":null}"));
    }

    @Test
    void responseStatusExceptionMapsTo404() throws Exception {
        mockMvc.perform(get("/api/items/99/required"))
                .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Các test kiểm tra cả **status** và **body**; nếu chỉ assert status 200, rất dễ bỏ sót endpoint cần trả JSON nhưng lại trả rỗng. Test `literalNullIsFourCharactersNotEmptyBody` trực tiếp phân biệt payload `null` (4 ký tự ASCII) với chuỗi rỗng. Test có `@WebMvcTest` chỉ dựng MVC test slice với controller này, không mở server thật.

Test `responseStatusExceptionMapsTo404` chỉ xác nhận mã 404 vì body lỗi của Spring Boot phụ thuộc auto-configuration và tính năng Problem Details; test không giả định thông điệp lỗi sẽ xuất hiện trong JSON cụ thể.

## 10. `@ResponseStatus` đặt trên lớp exception và xử lý lỗi REST

Bạn có thể định nghĩa exception mang status cố định:

~~~java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ResourceNotFoundException extends RuntimeException {
    public ResourceNotFoundException(String message) {
        super(message);
    }
}
~~~

Đoạn này là **class Java minh họa**, cần import `ResponseStatus`, `HttpStatus`; và file `ResourceNotFoundException.java` riêng. Khi handler ném exception, `ResponseStatusExceptionResolver` có thể xử lý thành 404. Nhưng `@ResponseStatus` **trên exception class** sử dụng cơ chế `sendError`; server hoặc error controller có thể tạo body lỗi. Vì vậy không nên suy ra “404 luôn trống” hay “404 luôn có cùng JSON”.

Nếu muốn JSON có cấu trúc nhất quán, chọn xử lý rõ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            ResourceNotFoundException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.NOT_FOUND, "Resource not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Đây là **class minh họa riêng**, cần import `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, `HttpStatus` và exception tương ứng. Spring Framework 6.x hỗ trợ `ProblemDetail` biểu diễn thông tin lỗi theo RFC 9457. Không gửi stack trace, dữ liệu nội bộ hoặc message nhạy cảm vào response chỉ vì exception có thông tin đó.

Khi xử lý status động, lựa chọn giữa `ResponseEntity`, `ResponseStatusException` và `@ExceptionHandler` phụ thuộc thiết kế API:
- Nếu muốn nhánh local rõ ngay trong handler, `ResponseEntity` thường đơn giản.
- Nếu thiếu resource là ngoại lệ ứng dụng, có thể ném exception và xử lý tập trung.
- Nếu chỉ cần status tĩnh của một hành động thành công, `@ResponseStatus` trên method ngắn gọn.

## 11. Response 204 trong HTTP client và frontend

Ví dụ một frontend gọi DELETE:

~~~javascript
async function deleteItem(id) {
  const response = await fetch("/api/items/" + id, {
    method: "DELETE"
  });

  if (response.status === 204) {
    return; // Không gọi response.json(): không có body.
  }
  if (response.status === 404) {
    throw new Error("Item does not exist");
  }
  if (!response.ok) {
    throw new Error("Delete failed: " + response.status);
  }
}
~~~

Không phải mọi response có status 2xx đều chứa JSON; `response.ok` trong Fetch chỉ kiểm tra phạm vi status 200–299. `response.json()` trên body rỗng có thể ném `SyntaxError`, kể cả request thành công. Client có thể thiết kế logic theo API contract: 204 thì không parse; 200 có body JSON thì parse; 404 xử lý không tồn tại.

Nếu API contract cho phép `200` với body rỗng, frontend phải kiểm tra nội dung trước khi parse (hoặc tốt hơn là thống nhất contract để loại bỏ mơ hồ). Không dựa hoàn toàn vào header `Content-Length`, bởi HTTP có nhiều cách framing response và header đó có thể vắng mặt dù body tồn tại.

Một số client API dùng kiểu `Optional<T>` hoặc `T | null` để biểu diễn “không tồn tại” ở tầng application. **Không mặc nhiên** map các kiểu đó sang 200 empty response; phía HTTP nên quyết định semantics 404/204/200 rõ ràng.

## 12. Lựa chọn status khi update, delete, create

| Tình huống REST | Status được dùng phổ biến | Cách Spring MVC |
| --- | --- | --- |
| GET có tài nguyên | 200 kèm JSON | Trả DTO hoặc `ResponseEntity.ok(dto)` |
| GET không tìm thấy | 404 | `ResponseEntity.notFound().build()` |
| POST tạo tài nguyên ngay | 201 | `@ResponseStatus(CREATED)` hoặc `ResponseEntity.created(uri).body(dto)` |
| POST nhận job chờ xử lý | 202 | `ResponseEntity.accepted().build()` hoặc trả thông tin job |
| PUT/PATCH cập nhật và trả object | 200 kèm JSON | `ResponseEntity.ok(dto)` |
| PUT/PATCH cập nhật, không trả object | 204 | `ResponseEntity.noContent().build()` |
| DELETE thành công, không trả object | 204 | `@ResponseStatus(NO_CONTENT) void` hoặc `noContent().build()` |
| DELETE tài nguyên vắng mặt | Theo contract: 404 hoặc 204 idempotent | Viết nhánh có chủ đích, kiểm thử |

**Idempotency** của DELETE nghĩa là lặp lại cùng thao tác có hiệu ứng trạng thái mong muốn như lần đầu, **không** bắt buộc mọi lần gọi phải trả cùng status. Một API có thể trả 204 khi xóa lần đầu và 404 khi xóa lại; miễn hợp đồng thể hiện rõ và ổn định. HTTP 204 có thể kèm metadata hợp lệ như ETag trong một số ngữ cảnh nhưng không được kèm body.

201 thường nên kèm `Location` tới resource mới, nhất là khi server cấp ID. Trong ví dụ demo, dữ liệu không được lưu thật; dự án thực tế phải tạo resource rồi cung cấp URI hoạt động.

## 13. Những lỗi thường gặp

### Lỗi A: Trả `null` và tưởng Spring tự chọn 404

~~~java
@GetMapping("/{id}")
public UserDto get(@PathVariable long id) {
    return service.findByIdOrNull(id);
}
~~~

Nếu service trả `null`, `@RestController` có thể tạo **200 rỗng**. **Cách sửa:** chuyển sang `ResponseEntity.notFound().build()` hoặc exception 404 có chủ đích.

### Lỗi B: Thêm `@ResponseStatus(NO_CONTENT)` nhưng vẫn trả dữ liệu

~~~java
@ResponseStatus(HttpStatus.NO_CONTENT)
@GetMapping("/value")
public UserDto value() {
    return new UserDto(1L, "Lan");
}
~~~

Đây là đoạn minh họa lỗi, không phải code để chạy: HTTP 204 **không được chứa message content**. Việc response có cố ghi/loại bỏ body ra sao tùy lớp server nhưng thiết kế này là sai contract. **Cách sửa:** trả `void`/không body với 204 hoặc dùng 200 và dữ liệu thực.

### Lỗi C: Dùng `@ResponseStatus(reason="...")` làm JSON error

`reason` đi qua `sendError`, có thể dẫn tới trang lỗi hoặc response khác dự kiến. **Cách sửa:** dùng `ResponseEntity<ProblemDetail>`, `@RestControllerAdvice` và kiểm thử response JSON lỗi.

### Lỗi D: Nhầm `200 + body rỗng` với JSON `null`

HTTP 200 với body rỗng có **0 byte**. JSON literal `null` có **4 byte**; body `{"data":null}` còn dài hơn. **Cách sửa:** test `content().string("")` hoặc `content().string("null")`, không chỉ nhìn status.

### Lỗi E: Gọi `response.json()` sau DELETE 204

Frontend ném lỗi parse JSON dù HTTP request thành công. **Cách sửa:** kiểm tra status 204 và tránh parse payload.

### Lỗi F: Trả `ResponseEntity.ok().body(null)` khi không tìm thấy

API báo thành công 200, không cho client phân biệt thiếu resource. **Cách sửa:** trả 404 nếu API xác định GET không có tài nguyên.

### Lỗi G: Trộn status tĩnh và status động

Method vừa có `@ResponseStatus` vừa trả `ResponseEntity` với status khác làm code khó hiểu và phụ thuộc cơ chế xử lý return value. **Cách sửa:** dùng một cơ chế làm nguồn chân lý cho status của endpoint.

### Lỗi H: Test chỉ kiểm tra status

Test chỉ `isOk()` vẫn PASS dù JSON body bị mất. **Cách sửa:** kiểm tra JSON schema, property chính, `Content-Type`, body rỗng hay `Location` tương ứng.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Controller trả `null` cho `@GetMapping` trong `@RestController`; API có tự trả 204 không?

**Trả lời:** Không. Trong cấu hình MVC thông thường, nếu không đặt status khác, response thường là **200 với body rỗng**.

**Câu 2.** Có thể dùng `@ResponseStatus(HttpStatus.NO_CONTENT)` cho method trả một JSON object không?

**Trả lời:** Không nên: 204 cấm message content. Muốn trả JSON object hãy dùng 200 hoặc 201 phù hợp. Muốn 204, bỏ body.

**Câu 3.** `ResponseEntity.ok().body(null)` khác `ResponseEntity.ok().contentType(APPLICATION_JSON).body("null")` như thế nào?

**Trả lời:** Cái đầu có 200 với body vắng mặt. Cái sau có 200 với payload JSON literal `null` dài bốn byte, nếu dùng String converter tiêu chuẩn.

**Câu 4.** Đâu là khác biệt giữa `@ResponseStatus(CREATED)` và `ResponseEntity.created(location)`?

**Trả lời:** Annotation đặt status 201 cố định cho handler; `ResponseEntity.created(...)` đồng thời biểu diễn status 201 và header `Location`, có thể kèm body.

**Câu 5.** Tại sao test 204 cần kiểm tra body?

**Trả lời:** Vì status và payload là hai khía cạnh riêng; cần chắc chắn API không cố trả dữ liệu trong trạng thái cấm body và client không parse JSON sau 204.

## 15. Checklist triển khai

1. Định nghĩa trước contract của mỗi endpoint: status thành công, status không tìm thấy, có body hay không, và shape JSON nếu có.
2. Dùng `@ResponseStatus` trên handler khi status thành công là cố định; dùng `ResponseEntity` khi phải quyết định status/headers/body theo kết quả.
3. Với không có nội dung: đặt `204` tường minh và không tạo payload. Với `200` rỗng: chỉ dùng nếu contract thật sự cần.
4. Với dữ liệu không tồn tại: không để `null` trôi ra ngoài `@RestController` rồi biến thành 200 không rõ nghĩa.
5. Phân biệt body không tồn tại, JSON literal `null` và property null trong JSON; đối chiếu cấu hình Jackson.
6. Dùng `@RestControllerAdvice`/`ProblemDetail` khi cần chuẩn hóa lỗi; tránh `reason` của `@ResponseStatus` cho REST JSON.
7. Kiểm thử **status + body + headers** và các nhánh bất thường (404, 204, parse JSON rỗng ở frontend).

## Tham khảo chính thức

- [Spring Framework 6.2 — Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — @ResponseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html)
- [Spring Framework — REST Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
