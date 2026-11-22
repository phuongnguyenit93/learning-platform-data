# Phân biệt không có phần tử với phản hồi HTTP 404 hoặc 204 trong Spring WebFlux

## 1. Ba khái niệm thuộc ba lớp khác nhau

Trong Spring WebFlux, cần tách ba khái niệm:

1. **Không có phần tử trong Reactor** là trạng thái của publisher: `Mono.empty()` hoặc `Flux.empty()` hoàn tất mà không phát `onNext`.
2. **HTTP 404 Not Found** là quyết định của API rằng không tìm thấy representation hiện tại cho tài nguyên được yêu cầu, hoặc server không muốn tiết lộ tài nguyên đó tồn tại.
3. **HTTP 204 No Content** là phản hồi thành công: server đã thực hiện yêu cầu và chủ ý không gửi nội dung response.

Ba khái niệm này không tự động chuyển đổi cho nhau. `Mono.empty()` **không tự có nghĩa là 404**, cũng **không tự có nghĩa là 204**. Publisher chỉ báo tín hiệu reactive; controller hoặc handler mới quyết định HTTP status theo hợp đồng endpoint.

Cùng một trạng thái reactive rỗng có thể được dùng theo những ý nghĩa nghiệp vụ khác nhau:

- Tìm user theo ID nhưng không có user: thường trả **404**.
- Tìm danh sách user nhưng hiện không có phần tử: thường trả **200 OK** với JSON array rỗng `[]`.
- Xóa một resource thành công và không cần trả representation: thường trả **204**.
- Một thao tác lưu hoàn tất bằng `Mono<Void>`: publisher không phát giá trị, nhưng thao tác có thể đã thành công.

**Nguyên tắc:** Reactor mô tả *có phát dữ liệu hay không*; HTTP status mô tả *kết quả của yêu cầu đối với client*. Hãy ánh xạ hai lớp này một cách chủ động.

## 2. Mono.empty(), Flux.empty() và Mono<Void>

### Mono.empty()

`Mono.empty()` phát `onComplete` mà không phát `onNext`:

~~~text
onSubscribe
    |
    v
onComplete
~~~

Nó biểu diễn một kết quả đơn có thể vắng mặt. Ví dụ:

~~~java
Mono<User> findUser(String id) {
    return repository.findById(id);
}
~~~

Nếu ID không tồn tại, repository có thể trả `Mono.empty()`. Đây là cách tự nhiên để biểu diễn “không có User” trong reactive layer. Ở tầng HTTP, endpoint quyết định trường hợp này là 404, fallback hay kết quả khác.

### Flux.empty()

`Flux.empty()` cũng hoàn tất mà không có phần tử, nhưng hợp đồng của nó cho phép 0 đến nhiều phần tử:

~~~java
Flux<User> findUsersByRole(String role) {
    return repository.findAllByRole(role);
}
~~~

Nếu không có user phù hợp, `Flux` có thể hoàn tất rỗng. Với endpoint liệt kê collection, không có item thường là **một kết quả danh sách hợp lệ**, không phải tài nguyên collection không tồn tại. Client thường nhận 200 và danh sách `[]` nếu API trả JSON array.

### Mono<Void>

`Mono<Void>` biểu diễn **hoàn tất hoặc lỗi của một thao tác không trả dữ liệu**. Khi thao tác thành công, nó hoàn tất mà không phát `onNext`:

~~~java
Mono<Void> saveAudit(AuditEvent event) {
    return auditRepository.save(event).then();
}
~~~

Một `Mono<Void>` thành công cũng không có phần tử dữ liệu. Không thể suy ra thao tác thất bại hoặc không tìm thấy dữ liệu chỉ từ việc không có `onNext`.

| Publisher | Có thể phát onNext? | Thành công rỗng có nghĩa gì? |
| --- | --- | --- |
| `Mono<User>` | Tối đa một User | Không có kết quả User, ví dụ không tìm thấy |
| `Flux<User>` | 0 đến nhiều User | Collection/stream hiện không có phần tử |
| `Mono<Void>` | Không có giá trị dữ liệu | Thao tác completion-only đã hoàn tất thành công |
| `Mono<Boolean>` | Một Boolean | Có thể biểu diễn rõ true/false |
| `Mono<Long>` | Một số | Có thể biểu diễn số dòng bị ảnh hưởng |

**Không có phần tử không phải exception.** `switchIfEmpty` xử lý trường hợp hoàn tất không có giá trị; `onErrorResume` xử lý trường hợp publisher phát `onError`. Không dùng hai toán tử thay thế nhau.

## 3. HTTP 404 Not Found

Theo HTTP Semantics (RFC 9110), 404 cho biết server không tìm thấy representation hiện tại cho target resource, hoặc không muốn tiết lộ rằng representation đó tồn tại. Status này không khẳng định resource đã bị xóa vĩnh viễn; nếu server biết tình trạng đã vĩnh viễn, 410 Gone có thể phù hợp hơn.

Ví dụ endpoint:

~~~http
GET /api/users/42
~~~

Nếu user ID 42 không tồn tại, client đang yêu cầu một resource đơn lẻ không có representation hiện tại. API thường trả:

~~~http
HTTP/1.1 404 Not Found
~~~

Body lỗi có thể chứa thông tin theo Problem Details nếu API thiết kế như vậy. 404 cũng có thể không có body; điều quan trọng là status truyền đạt ý nghĩa resource không tìm thấy.

404 phù hợp với các trường hợp:

- `GET /users/{id}`: ID không có user.
- `GET /orders/{id}`: đơn hàng không tồn tại hoặc không được phép tiết lộ.
- `GET /documents/{id}/content`: document không có representation được yêu cầu.
- Một endpoint tra cứu singular resource không tìm thấy đối tượng.

**Không tự động trả 404 chỉ vì một publisher bất kỳ hoàn tất rỗng.** Phải biết endpoint đang yêu cầu resource đơn lẻ, collection, kết quả tùy chọn hay chỉ đợi một thao tác hoàn tất.

## 4. HTTP 204 No Content

204 thuộc nhóm 2xx: server **đã thực hiện thành công yêu cầu**, và không có nội dung bổ sung để gửi trong response. Theo RFC 9110, response 204 không được chứa content hoặc trailers.

Các tình huống thường gặp:

- Client gửi `DELETE /users/42`, server xóa thành công và không cần trả body.
- Client gửi `PUT /preferences`, server cập nhật thành công và client không cần representation mới trong response.
- Một endpoint thực hiện lệnh như invalidate cache hoặc acknowledge, với hợp đồng rõ ràng là không trả body.

Ví dụ:

~~~http
DELETE /api/users/42
HTTP/1.1 204 No Content
~~~

Response 204 không có JSON `null`, không có `{}` và không có mảng rỗng. Status code đã nói rằng thao tác thành công và không có nội dung response.

### 204 khác 200 với collection rỗng

`200 OK` nói rằng request thành công. Nếu API trả collection JSON rỗng, response thường là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

`204 No Content` nói rằng request thành công và **không có representation response**. Client có thể xử lý hai tình huống khác nhau:

- `200 []`: collection tồn tại, hiện không có phần tử.
- `204`: thao tác đã thành công, API không gửi nội dung response.

Không trả 204 chỉ vì repository không tìm thấy phần tử. 204 là kết quả thành công của hành động theo hợp đồng API, không phải một cách viết khác của “không có dữ liệu”.

## 5. Bảng quyết định: empty nên ánh xạ sang status nào?

| Tình huống nghiệp vụ | Reactive result | HTTP response thường phù hợp | Lý do |
| --- | --- | --- | --- |
| GET một user theo ID, không tồn tại | `Mono<User>` empty | **404 Not Found** | Resource đơn lẻ không có representation |
| GET danh sách user, danh sách không có item | `Flux<User>` empty | **200 OK**, JSON `[]` | Collection query thành công, kết quả rỗng |
| GET search, không có kết quả | `Flux<Result>` empty | **200 OK**, JSON `[]` | Tìm kiếm thành công nhưng không có match |
| DELETE thành công, không trả body | `Mono<Void>` complete | **204 No Content** | Hành động thành công, không có representation |
| PUT cập nhật thành công, không trả body | `Mono<Void>` complete | **204 No Content** | Cập nhật đã hoàn tất |
| POST tạo resource và trả representation | `Mono<Resource>` có giá trị | **201 Created** hoặc 200 theo hợp đồng | Tạo mới; có thể kèm Location |
| POST nhận việc xử lý nền chưa hoàn thành | Publisher báo đã nhận việc | **202 Accepted** | Đã chấp nhận xử lý, chưa khẳng định hoàn tất |
| Repository/database phát lỗi | `onError` | **5xx** hoặc lỗi domain phù hợp | Đây là thất bại, không phải empty |
| Client không được phép truy cập | Lỗi authorization | **403** hoặc 404 theo chính sách | Không được đánh đồng với absence |

Đây là quy ước API phổ biến, không phải quy tắc máy móc cho mọi endpoint. Hợp đồng có thể chọn 404 hay 204 cho DELETE theo chính sách idempotency, nhưng phải nhất quán và được tài liệu hóa.

## 6. Ánh xạ Mono.empty() thành 404 trong annotated controller

Với `@RestController`, nếu service tìm kiếm trả `Mono<User>`, dùng `map` để tạo response khi có giá trị và `defaultIfEmpty` hoặc `switchIfEmpty` để chọn response khi không có.

~~~java
@GetMapping("/users/{id}")
public Mono<ResponseEntity<UserDto>> getUser(@PathVariable String id) {
    return userService.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(
            ResponseEntity.<UserDto>notFound().build()
        );
}
~~~

Kết quả:

- Có user: `Mono` phát `ResponseEntity<UserDto>` với status 200 và body.
- Không có user: `Mono.empty()` kích hoạt `defaultIfEmpty`, phát một `ResponseEntity` 404.
- Service báo lỗi database: lỗi vẫn lan downstream; không bị đổi thành 404.

Có thể dùng `switchIfEmpty` nếu muốn thay publisher:

~~~java
@GetMapping("/users/{id}/detail")
public Mono<ResponseEntity<UserDto>> getUserDetail(@PathVariable String id) {
    return userService.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .switchIfEmpty(Mono.just(
            ResponseEntity.<UserDto>notFound().build()
        ));
}
~~~

Hai cách đều phù hợp. `defaultIfEmpty(value)` thay empty bằng một giá trị; `switchIfEmpty(publisher)` chuyển sang một publisher khác khi nguồn hoàn tất rỗng.

### Không map mọi empty sang 404

Ví dụ sau chỉ đúng nếu `findById` thực sự có nghĩa “tìm một resource đơn lẻ”:

~~~java
return userService.findById(id)
    .switchIfEmpty(Mono.error(new ResponseStatusException(
        HttpStatus.NOT_FOUND, "User not found"
    )));
~~~

Nếu `userService.search(...)` trả collection rỗng, dùng cùng cách trên sẽ làm hợp đồng search sai. Search không có kết quả thường là 200 với danh sách rỗng.

## 7. Ánh xạ thành 204 khi thao tác hoàn tất thành công

Nếu thao tác trả `Mono<Void>`, có thể dùng `thenReturn` để tạo một giá trị response sau khi publisher hoàn tất:

~~~java
@DeleteMapping("/users/{id}/cache")
public Mono<ResponseEntity<Void>> clearCache(@PathVariable String id) {
    return cacheService.clear(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

`cacheService.clear(id)` là một `Mono<Void>`. Khi nó hoàn tất thành công, `thenReturn` phát ra `ResponseEntity` 204. Nếu nó phát lỗi, `thenReturn` không chạy và lỗi được truyền downstream.

Có thể dùng `@ResponseStatus` cho endpoint luôn trả 204 khi hoàn tất:

~~~java
@DeleteMapping("/sessions/current")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> closeCurrentSession() {
    return sessionService.closeCurrent();
}
~~~

Trong trường hợp này, annotation quy định HTTP status; `Mono<Void>` biểu diễn thời điểm thao tác kết thúc. Nếu service lỗi, WebFlux vẫn xử lý error signal theo cơ chế exception handling, không trả 204 thành công.

### Functional endpoint

WebFlux.fn cũng cho phép tạo response 204 sau khi publisher hoàn tất:

~~~java
public Mono<ServerResponse> deleteUser(ServerRequest request) {
    String id = request.pathVariable("id");

    return repository.deleteById(id)
        .then(ServerResponse.noContent().build());
}
~~~

Đây là mã phù hợp khi hợp đồng của `deleteById` chỉ biểu diễn hoàn tất/lỗi và API chấp nhận 204 cho thao tác đó. Nếu cần trả 404 khi không có row để xóa, repository phải cung cấp thông tin đó qua `Mono<Boolean>`, `Mono<Long>` hoặc một kết quả domain khác.

## 8. Bẫy quan trọng: switchIfEmpty trên Mono<Void>

Một thao tác thành công kiểu `Mono<Void>` **không phát giá trị**. Vì vậy, đoạn sau sai nếu mục tiêu là “nếu không xóa được thì trả 404”:

~~~java
// Sai nếu deleteById trả Mono<Void> và complete empty khi thành công.
return repository.deleteById(id)
    .then()
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)
    ));
~~~

Vì `Mono<Void>` không có `onNext` ngay cả khi thành công, `switchIfEmpty` sẽ thấy empty sau completion và chạy fallback. Nó không thể phân biệt:

- Xóa thành công, nhưng API không phát dữ liệu.
- Không có bản ghi để xóa.
- Một thao tác completion-only khác đã hoàn tất.

Nếu muốn quyết định 204 hay 404, thay đổi hợp đồng repository/service để phát một giá trị:

~~~java
Mono<Boolean> deleteById(String id) {
    return Mono.fromSupplier(() ->
        repository.deleteAndReturnCount(id) > 0
    );
}
~~~

Đây là đoạn minh họa; `deleteAndReturnCount` là method giả định của tầng persistence. Controller có thể ánh xạ:

~~~java
@DeleteMapping("/users/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
    return userService.deleteById(id)
        .map(deleted -> deleted
            ? ResponseEntity.<Void>noContent().build()
            : ResponseEntity.<Void>notFound().build()
        );
}
~~~

Ở đây `Mono<Boolean>` phát `true` hoặc `false`, vì vậy `map` có thể chọn status một cách rõ ràng. Nếu service có thể không phát kết quả vì lý do khác, hãy xác định thêm chính sách empty tương ứng.

Một lựa chọn khác là trả số dòng bị ảnh hưởng:

~~~java
Mono<Long> deleteRows(String id);
~~~

- Số dòng lớn hơn 0: đã xóa, trả 204.
- Số dòng bằng 0: không có resource phù hợp, trả 404 nếu hợp đồng yêu cầu.
- Publisher phát error: xử lý lỗi database, không đổi thành 404.

**Đừng dùng `thenReturn(true)` để giả lập kết quả có xóa hay không.** Nó chỉ xác nhận publisher trước đó hoàn tất thành công; không cung cấp thông tin về số dòng bị ảnh hưởng.

## 9. Flux rỗng trong endpoint collection

Với endpoint trả danh sách, empty thường có nghĩa “không có item phù hợp” chứ không phải “collection không tồn tại”.

~~~java
@GetMapping(value = "/users", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<UserDto> listUsers() {
    return userService.findAll();
}
~~~

Nếu không có user, `findAll()` có thể trả `Flux.empty()`. Với Jackson codec mặc định của Spring WebFlux và media type `application/json`, multi-value publisher được gom thành collection trước khi serialize; collection rỗng được biểu diễn bằng JSON array `[]`.

Response theo hợp đồng thường là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

Điều này giúp client luôn xử lý cùng một schema: response là một mảng, bất kể có 0, 1 hay nhiều item.

Với streaming media type như `application/x-ndjson`, encoder ghi từng phần tử theo dạng line-delimited. Nếu Flux rỗng thì không có dòng dữ liệu nào; **status HTTP vẫn do handler quyết định**, không tự chuyển thành 404.

### Khi nào 404 cho endpoint collection?

Chỉ trả 404 nếu chính resource collection/đường dẫn đó không tồn tại hoặc API định nghĩa route/resource như vậy. Ví dụ tenant không tồn tại có thể làm `GET /tenants/{tenantId}/users` trả 404; nhưng tenant tồn tại và chưa có user thì thường trả 200 với `[]`.

Không nên dùng số lượng phần tử làm tiêu chí duy nhất để quyết định 404 cho mọi collection.

## 10. ResponseEntity: đặt status đồng bộ với kết quả bất đồng bộ

Spring WebFlux hỗ trợ nhiều dạng `ResponseEntity` với reactive types:

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| `ResponseEntity<T>` | Status, headers và body được xác định ngay |
| `Mono<ResponseEntity<T>>` | Status, headers và body được xác định sau khi publisher hoàn tất |
| `ResponseEntity<Mono<T>>` | Status/headers biết trước, body được cung cấp bất đồng bộ |
| `ResponseEntity<Flux<T>>` | Status/headers biết trước, body là stream nhiều phần tử |
| `Mono<ResponseEntity<Mono<T>>>` | Status/headers được xác định bất đồng bộ trước; body tiếp tục bất đồng bộ sau |

Khi status phụ thuộc vào việc có tìm thấy resource hay không, thường dùng `Mono<ResponseEntity<T>>`:

~~~java
public Mono<ResponseEntity<UserDto>> get(String id) {
    return service.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(
            ResponseEntity.<UserDto>notFound().build()
        );
}
~~~

Khi status luôn 200 nhưng body có thể đến bất đồng bộ, có thể dùng `ResponseEntity<Mono<T>>`. Không nên chọn wrapper chỉ theo sở thích; hãy xem status có phụ thuộc vào kết quả async hay không.

## 11. Functional endpoint: 404 và 204 theo nghiệp vụ

Trong WebFlux.fn, `ServerResponse` cho phép chỉ định status tường minh:

~~~java
public Mono<ServerResponse> getUser(ServerRequest request) {
    String id = request.pathVariable("id");

    return repository.findById(id)
        .flatMap(user -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(user))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Ở đây, repository trả `Mono<User>`; empty được hiểu là không có user và được ánh xạ thành 404.

Với thao tác completion-only:

~~~java
public Mono<ServerResponse> saveUser(ServerRequest request) {
    Mono<User> user = request.bodyToMono(User.class);

    return repository.save(user)
        .then(ServerResponse.noContent().build());
}
~~~

`repository.save(user)` được giả định trả `Mono<Void>`; response 204 chỉ được tạo sau khi publisher save hoàn tất thành công. Nếu save lỗi, handler phát lỗi thay vì 204.

Spring có ví dụ chính thức tương tự: khi lưu đối tượng, repository trả `Mono<Void>` và handler dùng `build(Publisher<Void>)` để chỉ gửi response sau khi thao tác lưu hoàn tất. Với lookup singular resource, ví dụ dùng `switchIfEmpty(ServerResponse.notFound().build())`.

## 12. Empty, error và cancellation không phải một thứ

| Reactive signal | Ý nghĩa | HTTP mapping thường gặp |
| --- | --- | --- |
| `onComplete` không có `onNext` | Hoàn tất rỗng, không lỗi | Tùy hợp đồng: 200, 204 hoặc 404 |
| `onError(ex)` | Publisher thất bại | 4xx nếu lỗi request/domain; 5xx nếu lỗi server/hạ tầng |
| `cancel()` | Downstream không cần dữ liệu nữa | Không tự tạo status mới; thường liên quan client disconnect |

Ví dụ:

- Repository không tìm thấy user: `Mono.empty()`.
- Database mất kết nối: `Mono.error(DataAccessException)`.
- Client đóng kết nối khi đang nhận stream: upstream có thể bị cancel.

Không viết:

~~~java
return service.findById(id)
    .onErrorResume(error -> Mono.empty())
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)
    ));
~~~

Đoạn trên biến mọi lỗi (kể cả database outage) thành empty rồi đổi thành 404, khiến lỗi hạ tầng bị che giấu. Chỉ ánh xạ empty của **lookup không tìm thấy** thành 404; lỗi khác được chuyển tới error handler phù hợp.

## 13. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây minh họa ba hợp đồng:

- `GET /api/users`: danh sách rỗng vẫn trả 200 với `[]`.
- `GET /api/users/{id}`: user không tồn tại trả 404.
- `DELETE /api/users/{id}`: xóa thành công trả 204; không có user để xóa trả 404.

Tạo cấu trúc:

~~~text
http-empty-status-demo/
├── pom.xml
└── src/main/java/com/example/httpstatus/
    ├── HttpStatusApplication.java
    ├── User.java
    ├── UserStore.java
    └── UserController.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>http-empty-status-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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

File `src/main/java/com/example/httpstatus/HttpStatusApplication.java`:

~~~java
package com.example.httpstatus;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpStatusApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpStatusApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/httpstatus/User.java`:

~~~java
package com.example.httpstatus;

public record User(String id, String name) {
}
~~~

File `src/main/java/com/example/httpstatus/UserStore.java`:

~~~java
package com.example.httpstatus;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class UserStore {
    private final ConcurrentMap<String, User> users =
        new ConcurrentHashMap<>();

    public UserStore() {
        users.put("42", new User("42", "An"));
    }

    public Flux<User> findAll() {
        return Flux.defer(() -> Flux.fromIterable(users.values()));
    }

    public Mono<User> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(users.get(id)));
    }

    public Mono<User> deleteById(String id) {
        return Mono.fromSupplier(() -> users.remove(id));
    }
}
~~~

File `src/main/java/com/example/httpstatus/UserController.java`:

~~~java
package com.example.httpstatus;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserStore store;

    public UserController(UserStore store) {
        this.store = store;
    }

    // Collection rỗng là kết quả hợp lệ: trả JSON array.
    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<User> list() {
        return store.findAll();
    }

    // Lookup một resource: empty được ánh xạ thành 404.
    @GetMapping("/{id}")
    public Mono<ResponseEntity<User>> get(@PathVariable String id) {
        return store.findById(id)
            .map(user -> ResponseEntity.ok(user))
            .defaultIfEmpty(
                ResponseEntity.<User>notFound().build()
            );
    }

    // deleteById phát User khi xóa được, empty khi không có ID.
    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
        return store.deleteById(id)
            .map(removed -> ResponseEntity.<Void>noContent().build())
            .defaultIfEmpty(
                ResponseEntity.<Void>notFound().build()
            );
    }
}
~~~

Chạy trong thư mục `http-empty-status-demo` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### GET resource có tồn tại

~~~bash
curl -i http://localhost:8080/api/users/42
~~~

Kết quả chính:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"42","name":"An"}
~~~

### GET resource không tồn tại

~~~bash
curl -i http://localhost:8080/api/users/99
~~~

Kết quả chính:

~~~http
HTTP/1.1 404 Not Found
~~~

Repository trả `Mono.empty()`; controller đổi empty thành `ResponseEntity` 404.

### GET collection trước khi xóa

~~~bash
curl -i http://localhost:8080/api/users
~~~

Body JSON dự kiến:

~~~json
[{"id":"42","name":"An"}]
~~~

### DELETE resource có tồn tại

~~~bash
curl -i -X DELETE http://localhost:8080/api/users/42
~~~

Kết quả chính:

~~~http
HTTP/1.1 204 No Content
~~~

Không có response body.

### GET collection sau khi xóa

~~~bash
curl -i http://localhost:8080/api/users
~~~

Body JSON dự kiến:

~~~json
[]
~~~

Danh sách không còn user, nhưng endpoint collection vẫn trả 200 với array rỗng.

### DELETE lại ID đã xóa

~~~bash
curl -i -X DELETE http://localhost:8080/api/users/42
~~~

Theo hợp đồng của demo này, không còn user để xóa nên trả:

~~~http
HTTP/1.1 404 Not Found
~~~

Demo dùng `ConcurrentHashMap` trong bộ nhớ; dữ liệu trở về trạng thái ban đầu khi ứng dụng khởi động lại. Trong production, repository database cần trả affected-row count hoặc domain result phù hợp nếu endpoint phải phân biệt xóa thành công và không có bản ghi.

## 14. DELETE 204 hay 404 khi resource đã không tồn tại?

Đây là quyết định hợp đồng API, không phải Reactor tự chọn.

### Chính sách A: trả 204 khi trạng thái mong muốn đã đạt được

Một DELETE có thể được thiết kế idempotent: sau request, resource không còn tồn tại. Nếu resource đã không tồn tại trước đó, trạng thái cuối vẫn giống nhau; API có thể trả 204 trong cả hai trường hợp.

Với chính sách này, service có thể trả `Mono<Void>` và controller trả 204 khi hoàn tất. Nó không cần tiết lộ có row thực sự bị xóa hay không.

### Chính sách B: trả 404 nếu không có resource để xóa

Một API khác có thể quy định client chỉ nhận 204 khi xóa được resource hiện hữu. Nếu không tìm thấy ID, trả 404. Khi đó service phải phát kết quả như `Boolean`, số row hoặc `DeleteResult`; `Mono<Void>` không đủ thông tin.

Hãy xác định:

- DELETE có idempotent theo hợp đồng client mong đợi không?
- Client có cần biết resource đã tồn tại trước khi xóa không?
- API có cần ẩn sự tồn tại của resource vì lý do bảo mật không?
- Có cần phân biệt “đã xóa”, “đã không tồn tại” và “không có quyền” không?

Không có một lựa chọn phù hợp cho mọi API. Điều quan trọng là không dùng `Mono.empty()` một cách mơ hồ rồi để tầng HTTP suy đoán.

## 15. Kiểm thử status và body bằng WebTestClient

WebTestClient giúp kiểm tra status, headers và body mà không cần browser. Có thể dùng trong test với `@SpringBootTest`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void existingUserReturns200AndBody() {
        client.get()
            .uri("/api/users/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42");
    }

    @Test
    void missingUserReturns404() {
        client.get()
            .uri("/api/users/99")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody().isEmpty();
    }

    @Test
    void deletingExistingUserReturns204WithoutBody() {
        client.delete()
            .uri("/api/users/42")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }
}
~~~

Đây là đoạn test minh họa; thêm import JUnit, Spring Boot test, `@Autowired`, `WebTestClient` và dependency `spring-boot-starter-test`. Các test thay đổi dữ liệu trong store; nếu chạy độc lập, reset dữ liệu trước mỗi test hoặc dùng store test riêng để tránh phụ thuộc thứ tự.

Nên kiểm thử thêm:

- `GET /api/users` khi rỗng: 200 và body `[]`.
- `DELETE` ID không tồn tại theo chính sách đã chọn: 404 hoặc 204.
- Repository error: lỗi được ánh xạ đúng, không bị đổi thành 404.
- `Mono<Void>` hoàn tất: response 204 chỉ được gửi sau khi thao tác hoàn tất.
- POST/PUT trả 201, 200 hoặc 204 đúng hợp đồng.
- Response 204 không có body.
- JSON body của 200 collection luôn có schema mà client mong đợi.

## 16. Những lỗi thường gặp

1. **Cho rằng `Mono.empty()` tự tạo HTTP 404:** sai; controller/handler phải ánh xạ rõ ràng.
2. **Cho rằng empty luôn có nghĩa 204:** sai; 204 biểu thị hành động thành công và không gửi representation.
3. **Trả 404 cho danh sách không có item:** thường sai hợp đồng collection; trả 200 với `[]` nếu collection tồn tại.
4. **Dùng `switchIfEmpty` trên `Mono<Void>` để phát hiện không có row:** sai; thao tác thành công cũng không phát phần tử.
5. **Dùng `thenReturn(true)` để chứng minh đã xóa:** sai; nó chỉ nói publisher trước đó complete, không nói số row bị tác động.
6. **Map mọi `onError` thành 404:** che giấu lỗi database, timeout hoặc lỗi server; chỉ map empty của lookup phù hợp.
7. **Trả 204 kèm JSON `null` hoặc `{}`:** không đúng semantics 204; status này không được chứa response content.
8. **Dùng `Mono.empty()` để biểu diễn validation failure:** validation failure nên là lỗi 4xx hoặc kết quả domain rõ ràng.
9. **Dùng `Flux.empty()` để biểu diễn lỗi truy vấn:** lỗi truy vấn phải phát error signal; empty chỉ có nghĩa không có phần tử.
10. **Cho rằng 404 có nghĩa resource đã bị xóa vĩnh viễn:** 404 không nói điều đó; 410 có thể phù hợp khi biết tình trạng là vĩnh viễn.
11. **Không quyết định chính sách DELETE:** client không biết xóa ID vắng mặt là thành công idempotent hay lỗi 404.
12. **Không phân biệt status với body:** 200 body rỗng, 200 `[]`, 204 và 404 có ý nghĩa khác nhau dù một số trường hợp đều không có JSON object.
13. **Dùng `ResponseEntity<Mono<T>>` khi status phụ thuộc vào kết quả lookup:** status đã bị quyết định quá sớm; dùng `Mono<ResponseEntity<T>>`.
14. **Để lỗi repository biến thành empty:** có thể khiến lỗi hệ thống bị báo như “không tìm thấy”; giữ error signal và xử lý riêng.
15. **Kiểm tra empty bằng `null` trong reactive chain:** Reactor không cho phép phát `null` bằng `onNext`; dùng `Mono.empty()`, `Optional` hoặc kiểu kết quả tường minh.

## 17. Checklist thiết kế HTTP contract

Trước khi chọn status cho endpoint, hãy trả lời:

- Endpoint đang truy cập một **resource đơn lẻ**, một **collection**, hay thực hiện một **command**?
- Empty của service có nghĩa “resource không tồn tại”, “không có item”, hay “thao tác đã hoàn tất”?
- Nếu trả 404, resource có thực sự không có representation hiện tại không?
- Nếu trả 204, hành động đã thành công chưa và response có chủ ý không có content không?
- Nếu trả 200 cho collection, body rỗng có được biểu diễn nhất quán là `[]` không?
- Service có dùng `Mono<Void>` không? Nếu cần biết số row thay đổi, hãy trả kết quả có dữ liệu.
- Có phân biệt `onError` với `onComplete` không?
- Có quy định DELETE idempotent và hành vi khi ID không tồn tại không?
- Status có phụ thuộc kết quả async không? Nếu có, cân nhắc `Mono<ResponseEntity<T>>`.
- Đã kiểm thử status, body, headers và lỗi repository chưa?

## 18. Câu hỏi tự kiểm tra

**1.** `Mono.empty()` có phải HTTP 404 không? Không. Nó chỉ là publisher hoàn tất mà không phát giá trị; endpoint mới quyết định status.

**2.** Khi nào lookup `Mono<User>` empty thường được ánh xạ thành 404? Khi API yêu cầu một user/resource đơn lẻ và không có representation hiện tại.

**3.** `Flux.empty()` trên endpoint danh sách thường trả gì? 200 với JSON array rỗng `[]` khi dùng JSON collection contract.

**4.** 204 biểu thị điều gì? Request đã được thực hiện thành công và không có response content bổ sung.

**5.** Có thể gửi body JSON trong 204 không? Không. 204 không được chứa response content.

**6.** Vì sao `switchIfEmpty` trên `Mono<Void>` không thể xác định thao tác có tìm thấy row? Vì Mono<Void> thành công cũng không phát `onNext`; nó luôn complete rỗng.

**7.** Muốn phân biệt delete thành công và không có row thì service nên trả gì? Ví dụ `Mono<Boolean>`, `Mono<Long>` affected-row count hoặc một domain result.

**8.** `onErrorResume` khác `switchIfEmpty` thế nào? Một toán tử xử lý error signal, toán tử kia xử lý completion không có giá trị.

**9.** Nếu GET collection không có kết quả, có nên trả 404 không? Thông thường không; nếu collection tồn tại, trả 200 với danh sách rỗng.

**10.** Nếu DELETE không tìm thấy ID, bắt buộc trả 404 không? Không; phụ thuộc hợp đồng API. Một DELETE idempotent có thể trả 204 nếu trạng thái cuối đã đạt được.

**11.** Vì sao dùng `Mono<ResponseEntity<T>>` cho lookup? Vì status và body có thể được quyết định sau khi biết lookup có giá trị hay không.

**12.** Nếu repository lỗi kết nối, có nên đổi thành 404? Không. Đó là lỗi hạ tầng và phải được xử lý theo error mapping phù hợp.

**Ghi nhớ:** `Mono.empty()`/`Flux.empty()` mô tả **không có phần tử**, không quyết định HTTP status. 404 dành cho resource không có representation hiện tại; 204 dành cho request thành công mà response không có content; collection rỗng thường là 200 với `[]`. Đặc biệt, `Mono<Void>` thành công luôn không phát giá trị, nên không dùng `switchIfEmpty` để phát hiện không có bản ghi. Hãy để service trả kết quả tường minh nếu HTTP contract cần phân biệt các trường hợp đó.

**Tài liệu tham khảo chính thức:**
- [Spring Framework 6.2 — Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 — Return Values in WebFlux Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — ResponseEntity in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Framework 6.2 — Reactive Core and Jackson Encoder](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [RFC 9110 — HTTP Semantics, 204 and 404](https://www.rfc-editor.org/rfc/rfc9110.html).