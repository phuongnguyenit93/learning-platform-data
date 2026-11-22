# Tích hợp Redis phản ứng với API WebFlux

**Spring WebFlux** cung cấp mô hình xây dựng API HTTP dựa trên Reactive Streams, trong đó các thao tác bất đồng bộ được biểu diễn bằng `Mono<T>` và `Flux<T>`. **Spring Data Redis Reactive** cho phép ứng dụng thực hiện lệnh Redis theo mô hình tương tự, thông qua `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate` và kết nối Lettuce reactive.

Bài thực hành này xây dựng một ứng dụng Spring Boot có API quản lý **ghi chú tạm thời (temporary notes)**. Mỗi ghi chú được lưu trong Redis với **TTL 30 phút**. Ứng dụng hỗ trợ:

- `POST /api/notes`: tạo ghi chú, trả HTTP `201 Created`.
- `GET /api/notes/{id}`: đọc ghi chú; trả `404` khi khóa thật sự không tồn tại.
- `DELETE /api/notes/{id}`: xóa ghi chú; trả `204` khi đã xóa, `404` khi không có.
- Kiểm thử bằng `curl` và `WebTestClient` kết nối Redis thật trong Testcontainers.

Ngoài ứng dụng mẫu, bài viết phân tích cách dùng `Mono`/`Flux`, serialization, lỗi truy cập Redis, cache-aside, concurrency, Redis Cluster, Pub/Sub, Streams, testing và vận hành. Mục tiêu không chỉ là viết được một endpoint, mà còn hiểu **ranh giới của tính phản ứng**: không chặn event loop, không tự subscribe trong controller, không nhầm cache miss với lỗi, và không coi một reactive chain là transaction toàn cục.

## 1. Kiến trúc: WebFlux gọi Redis theo một reactive chain

Một request đi qua các lớp:

```text
                    HTTP client
                        |
                 Reactor Netty
                        |
                        v
                 WebFlux Router
                        |
                        v
               NoteController
                 Mono<...>
                        |
                        v
                  NoteService
                        |
                        v
          ReactiveStringRedisTemplate
                        |
                        v
           Lettuce reactive connection
                        |
                  TCP / TLS
                        |
                        v
                    Redis server
                        |
                        v
            Mono success / empty / error
                        |
                        v
              WebFlux HTTP response
```

Đặc điểm quan trọng:

1. Controller **trả publisher** cho WebFlux thay vì tự gọi `subscribe()` hoặc `block()`.
2. Redis client hỗ trợ I/O bất đồng bộ; thread xử lý request không cần chờ đồng bộ cho đến khi Redis phản hồi.
3. `Mono` biểu diễn tối đa một kết quả; `Flux` biểu diễn nhiều kết quả.
4. Một publisher không có giá trị và một publisher lỗi là hai trạng thái khác nhau.
5. Không có bảo đảm rằng mọi đoạn code bên trong reactive chain đều non-blocking: JDBC đồng bộ, `Thread.sleep` hoặc file I/O blocking vẫn có thể làm nghẽn thread nếu được gọi trực tiếp.
6. Một request được cancel không nhất thiết hủy được một Redis command đã được gửi đến server.

Đây là một mô hình I/O, **không phải cam kết rằng Redis nhanh hơn ở mọi lệnh**. Với tải nhỏ, chi phí tạo reactive chain có thể không mang lại lợi ích rõ rệt; lợi ích thường thấy khi hệ thống phải xử lý nhiều request đồng thời đang chờ I/O.

## 2. ReactiveRedisTemplate và ReactiveStringRedisTemplate

Hai API phổ biến:

| API | Khi nào dùng | Đặc điểm |
|---|---|---|
| `ReactiveRedisTemplate<K,V>` | Cần key/value dạng đối tượng theo serializer cấu hình | Generic, linh hoạt với nhiều cấu trúc Redis |
| `ReactiveStringRedisTemplate` | Key và value chuỗi UTF-8 | Phù hợp String, JSON chuỗi, counter và ví dụ nhỏ |
| `ReactiveValueOperations<K,V>` | SET, GET, INCR trên Redis String | Lấy qua `opsForValue()` |
| `ReactiveHashOperations` | Hash fields | Lấy qua `opsForHash()` |
| `ReactiveSetOperations` | Redis Set | Lấy qua `opsForSet()` |
| `ReactiveZSetOperations` | Sorted Set | Lấy qua `opsForZSet()` |
| `ReactiveStreamOperations` | Redis Streams | Thao tác stream theo reactive API |
| `ReactiveRedisConnectionFactory` | Tạo reactive Redis connections | Spring Data Redis infrastructure |

Trong bài thực hành, dùng `ReactiveStringRedisTemplate` để key và value đều là String. Đối tượng `Note` được đổi thành JSON bằng Jackson tại tầng service.

Lý do chọn cách này:

- Dễ kiểm tra dữ liệu trực tiếp bằng `redis-cli GET`.
- Tránh nhầm lẫn giữa key serializer và value serializer.
- Minh họa rõ ranh giới Redis bytes ↔ JSON ↔ đối tượng Java.
- Dùng được các command cơ bản mà không phải cấu hình serializer generic ngay từ đầu.

Trong ứng dụng lớn, một `ReactiveRedisTemplate<String, Note>` với JSON serializer được cấu hình tường minh cũng là lựa chọn hợp lý. Dù chọn cách nào, **mọi ứng dụng cùng đọc một key phải thống nhất serializer, namespace và schema**.

## 3. Chuẩn bị môi trường

Các thành phần thực hành:

- JDK tương thích với phiên bản Spring Boot đang dùng.
- Spring Boot với WebFlux, Spring Data Redis Reactive.
- Redis hỗ trợ lệnh String và TTL thông thường.
- Docker để chạy Redis cục bộ hoặc Testcontainers khi kiểm thử.
- Công cụ gọi HTTP như `curl`.

Ví dụ tổ chức dự án:

```text
redis-webflux-demo/
├── build.gradle
├── src/main/java/com/example/rediswebflux/
│   ├── RedisWebfluxDemoApplication.java
│   ├── note/
│   │   ├── Note.java
│   │   ├── CreateNoteRequest.java
│   │   ├── NoteService.java
│   │   └── NoteController.java
│   └── web/
│       └── RedisErrorAdvice.java
├── src/main/resources/
│   └── application.yml
└── src/test/java/com/example/rediswebflux/
    └── NoteApiIntegrationTest.java
```

Các class Java phải nằm trong package được Spring component scan. Ví dụ chính dùng package gốc `com.example.rediswebflux` và các package con.

### 3.1. Dependencies

Với Gradle và Spring Boot dependency management phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
}
```

Dự án dùng Spring Boot plugin/BOM để quản lý phiên bản tương thích của Reactor, Spring Data Redis, Lettuce và Testcontainers. Trong một số dòng Spring Boot, tên dependency/chi tiết auto-configuration có thể thay đổi; hãy dùng starter reactive được cung cấp cho **đúng phiên bản** đang triển khai.

**Không cần thêm `spring-boot-starter-web` (Spring MVC) để viết các API trong ví dụ.** Nếu đồng thời có MVC và WebFlux trên classpath, Spring Boot có thể chọn loại web application khác với mong muốn tùy cấu hình. Hãy chủ động xác định stack đang chạy.

### 3.2. Redis cục bộ

Nếu có Docker, có thể chạy Redis test chỉ publish vào loopback của máy phát triển:

```bash
docker run --rm -d \
  --name redis-webflux-demo \
  -p 127.0.0.1:6379:6379 \
  redis:7.4-alpine
```

Kiểm tra:

```bash
docker exec redis-webflux-demo redis-cli PING
```

Kỳ vọng `PONG`.

Cấu hình này dành riêng cho **máy phát triển có kiểm soát**; Redis production cần endpoint private, firewall, TLS, ACL, quản lý secret và HA tùy yêu cầu. Không publish Redis `6379` ra Internet.

Khi kết thúc thực hành:

```bash
docker stop redis-webflux-demo
```

Không chạy `FLUSHALL` trên Redis dùng chung chỉ để dọn dữ liệu bài học.

## 4. Cấu hình Spring Boot kết nối Redis

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      connect-timeout: 2s
      timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Khi chạy local, Redis ở `localhost:6379`. Khi chạy qua container hoặc môi trường cloud, dùng `REDIS_HOST` và `REDIS_PORT` tương ứng với **private Redis endpoint**.

Đối với Redis có xác thực và TLS, cấu hình phù hợp theo phiên bản Spring Boot có thể bổ sung:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
```

Đây là cấu hình **môi trường TLS riêng**, không áp nguyên vào Redis local plain TCP ở mục trước nếu Redis chưa được bật TLS. Password phải lấy từ secret manager hoặc cơ chế secret injection; không hardcode credential production.

### 4.1. Vì sao không tự tạo connection ở mỗi request?

Spring Boot thường tạo bean `ReactiveStringRedisTemplate` từ connection factory khi reactive Redis auto-configuration thỏa điều kiện. Controller/service chỉ cần inject bean:

```java
@Service
public class ExampleService {

    private final ReactiveStringRedisTemplate redis;

    public ExampleService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

Không khởi tạo một Lettuce native client mới cho mỗi HTTP request. Connection factory là tài nguyên dùng chung do Spring quản lý, kèm vòng đời reconnect, topology và giải phóng connection.

Tuy nhiên, **bean tạo thành công không chứng minh Redis đã sẵn sàng**. Lỗi mạng, ACL, TLS hoặc timeout có thể chỉ xuất hiện khi subscribe vào publisher chứa command.

## 5. Khởi tạo Spring Boot application

Entry point:

```java
package com.example.rediswebflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedisWebfluxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RedisWebfluxDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` giúp component scan các class trong package gốc và package con.

Ứng dụng mẫu không dùng R2DBC/JPA. Redis là kho chứa những ghi chú **tạm thời**. Trong dự án sản xuất, nếu thông tin phải bền vững, Redis có TTL không được xem là nguồn dữ liệu có độ bền tương đương database giao dịch.

## 6. Thiết kế tài nguyên: Note và CreateNoteRequest

Model bất biến bằng Java record:

```java
package com.example.rediswebflux.note;

import java.time.Instant;

public record Note(
        String id,
        String text,
        Instant createdAt) {
}
```

Input của API:

```java
package com.example.rediswebflux.note;

public record CreateNoteRequest(String text) {
}
```

Ví dụ request:

```json
{
  "text": "Ghi chú thử nghiệm WebFlux và Redis"
}
```

Ví dụ response:

```json
{
  "id": "e27a9f8a-d755-42ac-b11d-9e7c87501866",
  "text": "Ghi chú thử nghiệm WebFlux và Redis",
  "createdAt": "2026-11-13T08:10:00Z"
}
```

Các giá trị chỉ minh họa. ID được tạo bằng UUID cho mỗi ghi chú, tránh để người dùng tự chọn một Redis key tùy ý.

Hợp đồng nghiệp vụ của bài tập:

- Ghi chú chỉ là dữ liệu tạm thời, **không yêu cầu bền sau mọi sự cố Redis**.
- Mỗi ghi chú có TTL 30 phút tính từ lần tạo.
- `GET` **không tự gia hạn TTL**.
- Ghi chú hết TTL sẽ có hành vi tương tự một ID không tồn tại.
- Nếu Redis lỗi kết nối, API **không** trả `404` như thể key chắc chắn không có.

## 7. NoteService: Redis GET, SET có TTL và DEL

Đây là phần tích hợp chính của bài thực hành.

```java
package com.example.rediswebflux.note;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
public class NoteService {

    private static final String PREFIX = "demo:webflux:notes:v1:";
    private static final Duration TTL = Duration.ofMinutes(30);

    private final ReactiveStringRedisTemplate redis;
    private final ObjectMapper mapper;

    public NoteService(
            ReactiveStringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public Mono<Note> create(String text) {
        return Mono.defer(() -> {
            if (text == null
                    || text.isBlank()
                    || text.length() > 1000) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "text must contain 1..1000 characters"));
            }

            Note note = new Note(
                    UUID.randomUUID().toString(),
                    text.trim(),
                    Instant.now());

            return Mono.fromCallable(
                            () -> mapper.writeValueAsString(note))
                    .flatMap(json ->
                            redis.opsForValue()
                                    .set(key(note.id()), json, TTL)
                                    .flatMap(saved -> Boolean.TRUE.equals(saved)
                                            ? Mono.just(note)
                                            : Mono.error(
                                                    new IllegalStateException(
                                                            "Redis SET not confirmed"))));
        });
    }

    public Mono<Note> findById(String id) {
        String redisKey = key(id);

        return redis.opsForValue()
                .get(redisKey)
                .flatMap(json -> Mono.fromCallable(
                        () -> deserializeNote(json)));
    }

    public Mono<Boolean> deleteById(String id) {
        return redis.delete(key(id))
                .map(count -> count > 0);
    }

    private Note deserializeNote(String json)
            throws JsonProcessingException {

        Note note = mapper.readValue(json, Note.class);

        if (note == null) {
            throw new IllegalStateException(
                    "Redis returned invalid note payload");
        }

        return note;
    }

    private String key(String id) {
        try {
            return PREFIX + UUID.fromString(id);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid note id", error);
        }
    }
}
```

### 7.1. Vì sao dùng Mono.defer khi tạo ghi chú?

`Mono.defer(...)` trì hoãn việc tạo `UUID` và `Instant.now()` đến lúc có subscription.

Trong WebFlux, framework subscribe vào publisher để thực thi request. Cách viết này giúp mỗi lần subscribe tạo một lượt thao tác rõ ràng; không tạo ID sớm ngay khi phương thức Java được gọi nhưng publisher chưa được thực thi.

**Không đồng nghĩa mỗi HTTP retry sẽ giữ nguyên ID.** Nếu client gửi lại `POST`, đó là một request mới và có thể tạo một ghi chú mới. Nếu nghiệp vụ yêu cầu chống tạo trùng khi retry, cần cơ chế idempotency riêng.

### 7.2. SET có TTL là một thao tác thích hợp

Đoạn:

```java
redis.opsForValue().set(redisKey, json, Duration.ofMinutes(30))
```

tương ứng ý tưởng gửi một `SET` với điều kiện expire trong cùng thao tác Redis.

Nên ưu tiên **SET kèm TTL** thay vì:

```text
SET key value
EXPIRE key 1800
```

trong hai lệnh tách biệt nếu yêu cầu là “value luôn có TTL”. Nếu connection lỗi giữa hai lệnh, key có thể được tạo nhưng chưa nhận expiry.

Redis dùng TTL theo chính sách server. Khi TTL hết hoặc key bị evict/xóa, `GET` có thể không còn thấy value. TTL **không đảm bảo tài nguyên sẽ tồn tại đủ 30 phút** nếu Redis mất dữ liệu hoặc cấu hình eviction cho phép loại bỏ sớm.

### 7.3. GET trả Mono.empty() cho key không có

`redis.opsForValue().get(redisKey)` trả `Mono<String>`:

- Redis có value: phát JSON String.
- Redis trả nil vì key không có: thường hoàn thành rỗng, tức `Mono.empty()`.
- Redis lỗi: phát `Mono.error(error)`.

`flatMap(json -> Mono.fromCallable(...))` chỉ giải mã khi có JSON. Khi Redis báo miss, nhánh giải mã không chạy.

`deserializeNote` chủ động từ chối JSON literal `null` để không biến payload không hợp lệ thành một `Mono.empty()` giả. Nếu JSON bị lỗi schema, exception được truyền trong reactive chain; đây là **invalid payload**, không phải key không tồn tại.

### 7.4. DELETE trả số key được xóa

`redis.delete(redisKey)` trả `Mono<Long>` trong API reactive tương ứng:

- `1`: một key đã được xóa.
- `0`: không có key để xóa tại thời điểm lệnh được thực thi.
- `onError`: command không hoàn tất bình thường.

`DELETE` có thể được gọi lặp khi client retry, nhưng kết quả lần hai sẽ khác: khi key đã mất, count là 0. Với timeout sau lệnh xóa, có thể không biết lệnh đã thành công hay chưa; tuy vậy hiệu quả xóa theo key thường idempotent, khác với `INCR`.

## 8. NoteController: ánh xạ Mono sang HTTP response

Controller trả publisher, không tự thực thi publisher:

```java
package com.example.rediswebflux.note;

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
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/notes")
public class NoteController {

    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Note>> create(
            @RequestBody Mono<CreateNoteRequest> request) {

        return request
                .flatMap(body -> service.create(body.text()))
                .map(note -> ResponseEntity
                        .created(URI.create("/api/notes/" + note.id()))
                        .body(note));
    }

    @GetMapping("/{id}")
    public Mono<Note> get(@PathVariable String id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Note not found")));
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(
            @PathVariable String id) {

        return service.deleteById(id)
                .map(deleted -> {
                    if (deleted) {
                        return ResponseEntity.noContent()
                                .<Void>build();
                    }

                    return ResponseEntity.status(
                                    HttpStatus.NOT_FOUND)
                            .<Void>build();
                });
    }
}
```

Đây là một ứng dụng reactive ở cả HTTP và Redis I/O. Không có:

```java
redis.opsForValue().get(key).block();
```

trong controller, và cũng không có:

```java
redis.opsForValue().set(key, value).subscribe();
return Mono.just(ResponseEntity.ok().build());
```

Cách thứ hai là **fire-and-forget**: HTTP response có thể được gửi trước khi Redis ghi xong, lỗi ghi không đi vào response, và subscription tự tạo khó quản lý khi request bị hủy hoặc ứng dụng shutdown.

### 8.1. switchIfEmpty chỉ áp dụng cho miss

Trong endpoint `GET`:

```java
return service.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Note not found")));
```

Operator `switchIfEmpty` hoạt động khi upstream **hoàn tất mà không phát Note**. Nếu Redis timeout và upstream phát `onError`, `switchIfEmpty` **không** tự chuyển lỗi đó thành `404`.

Đây là hành vi mong muốn:

```text
GET /api/notes/{id}
        |
        +-- Redis trả JSON hợp lệ -> 200
        |
        +-- Redis trả nil         -> 404
        |
        +-- Redis connection fail -> lỗi truy cập, không 404
        |
        +-- JSON decode fail      -> lỗi dữ liệu, không 404
```

### 8.2. Mono<ResponseEntity<T>> và Mono<T>

Cả hai đều hợp lệ trong WebFlux:

- `Mono<Note>` để framework tự serialize body với status mặc định cho success.
- `Mono<ResponseEntity<Note>>` khi cần tự chọn status/header, ví dụ `201 Created`.
- `Mono<ResponseEntity<Void>>` để chọn `204 No Content` hoặc `404 Not Found`.

Dùng `ResponseEntity` không làm code tự động blocking. Điều quan trọng là việc xây dựng giá trị HTTP **nằm trong reactive chain** và không gọi blocking API trên event-loop.

## 9. Phân loại lỗi Redis và phản hồi API

Trong một ứng dụng API, lỗi Redis có thể gồm:

- Không kết nối được hoặc connect timeout.
- Command timeout.
- Sai mật khẩu/ACL `NOAUTH` hoặc `NOPERM`.
- Redis trả `WRONGTYPE` vì key bị ghi sai cấu trúc.
- TLS handshake hoặc certificate validation thất bại.
- Redis Cluster redirect/slot unavailable.
- Dữ liệu JSON không thể deserialize.
- Client bị shutdown trong khi command đang chạy.

Không nên xử lý tất cả bằng:

```java
.onErrorResume(error -> Mono.empty())
```

nếu sau đó controller dùng `switchIfEmpty` để trả `404`. Cách này biến sự cố hạ tầng hoặc lỗi dữ liệu thành “ghi chú không tồn tại”.

### 9.1. Advice cho lỗi kết nối Redis

Ví dụ ánh xạ riêng lỗi kết nối thường gặp sang HTTP `503 Service Unavailable`:

```java
package com.example.rediswebflux.web;

import java.util.Map;

import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RedisErrorAdvice {

    @ExceptionHandler(RedisConnectionFailureException.class)
    public ResponseEntity<Map<String, String>> unavailable(
            RedisConnectionFailureException error) {

        // Ghi log/metric nội bộ với thông tin đã loại bỏ secret.
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "error", "redis_unavailable",
                        "message", "Temporary storage is unavailable"));
    }
}
```

Ví dụ chỉ bắt **một loại exception cụ thể**. Trong production, cần phân loại thêm timeout, lỗi kết nối theo driver, lỗi serialization, sai cấu hình, `WRONGTYPE` và lỗi business. Không mặc định mọi subtype của `DataAccessException` đều là lỗi tạm thời có thể retry.

Không trả nguyên exception message chứa hostname, key hoặc thông tin cấu hình ra public API.

### 9.2. Bảng kết quả HTTP nên mong đợi

| Tình huống | Reactive signal | HTTP trong bài |
|---|---|---|
| Tạo ghi chú thành công | `Mono.just(note)` | `201 Created` |
| Đọc ID hợp lệ và có key | `Mono.just(note)` | `200 OK` |
| Đọc ID hợp lệ nhưng Redis nil | `Mono.empty()` | `404 Not Found` |
| Xóa key có tồn tại | `Mono.just(true)` | `204 No Content` |
| Xóa key không tồn tại | `Mono.just(false)` | `404 Not Found` |
| Body text rỗng/quá dài | `Mono.error(ResponseStatusException)` | `400 Bad Request` |
| UUID không hợp lệ | `Mono.error(ResponseStatusException)` | `400 Bad Request` |
| Redis connection failure | `Mono.error(RedisConnectionFailureException)` | `503` theo advice |
| Payload không giải mã được | `Mono.error(...)` | `5xx` và alert; không trả `404` |
| Redis ACL sai | Lỗi access/command | `5xx` kèm cảnh báo cấu hình; không coi là miss |

Nếu Redis chỉ là cache và database là nguồn sự thật, chính sách khi Redis lỗi có thể khác: ứng dụng được phép **fail-open có giới hạn** về database. Nhưng API ghi chú của bài đang lưu tài nguyên trực tiếp trong Redis, nên không có database để fallback. Phải tránh “trả ghi chú mặc định” như thể dữ liệu thật đã được tìm thấy.

## 10. Thực hành gọi API bằng curl

Sau khi Redis local và ứng dụng Spring Boot đã chạy, tạo một ghi chú:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello WebFlux Redis"}'
```

Kết quả dự kiến:

```http
HTTP/1.1 201 Created
Location: /api/notes/e27a9f8a-d755-42ac-b11d-9e7c87501866
Content-Type: application/json

{"id":"e27a9f8a-d755-42ac-b11d-9e7c87501866","text":"Hello WebFlux Redis","createdAt":"2026-11-13T08:10:00Z"}
```

ID và timestamp thực tế khác giá trị minh họa. Sao chép ID trả về vào lệnh sau:

```bash
curl -i \
  http://localhost:8080/api/notes/e27a9f8a-d755-42ac-b11d-9e7c87501866
```

Dự kiến `200 OK` với JSON Note.

Xem khóa vật lý trong Redis local:

```bash
docker exec redis-webflux-demo redis-cli \
  GET 'demo:webflux:notes:v1:e27a9f8a-d755-42ac-b11d-9e7c87501866'
```

Quan sát thời gian hết hạn:

```bash
docker exec redis-webflux-demo redis-cli \
  TTL 'demo:webflux:notes:v1:e27a9f8a-d755-42ac-b11d-9e7c87501866'
```

Giá trị TTL thường còn gần 1800 giây nếu mới tạo. Redis `TTL` trả `-2` khi key không còn, `-1` khi key tồn tại nhưng không có expiry; giá trị âm không tự đồng nghĩa lỗi mạng.

Xóa:

```bash
curl -i -X DELETE \
  http://localhost:8080/api/notes/e27a9f8a-d755-42ac-b11d-9e7c87501866
```

Dự kiến `204 No Content`. Gọi lại GET cho ID đã xóa sẽ nhận `404 Not Found`.

### 10.1. Thử key không tồn tại

Dùng một UUID hợp lệ nhưng chưa được tạo:

```bash
curl -i \
  http://localhost:8080/api/notes/00000000-0000-0000-0000-000000000001
```

Kỳ vọng `404` nếu Redis truy cập được. Đây là **khác biệt căn bản** với việc tắt Redis test rồi gọi cùng endpoint: khi Redis unavailable, ứng dụng không có bằng chứng key không tồn tại.

### 10.2. Thử input sai

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text":"   "}'
```

Kỳ vọng `400` do validation trong service. Với ID không có định dạng UUID, cũng trả `400`. Ở production, nên bổ sung Bean Validation và quy tắc request body size/JSON schema tại HTTP boundary, không chỉ kiểm tra một field.

## 11. Mono và Flux: hiểu đúng tín hiệu trước khi ghép operator

Reactor phân biệt:

```text
Mono có value:
    onNext(value) -> onComplete

Mono rỗng:
    onComplete

Mono lỗi:
    onError(error)
```

Không có `onNext(null)` trong Reactive Streams. Khi Redis trả nil, phương thức `GET` reactive thông thường biểu diễn bằng completion rỗng, không phát Java `null`.

### 11.1. Những operator thường gặp

| Operator | Mục đích | Điều cần nhớ |
|---|---|---|
| `map` | Đổi value đồng bộ | Hàm mapping không được trả null tùy tiện |
| `flatMap` | Ghép thao tác bất đồng bộ trả publisher | Dùng khi gọi tiếp Redis/API/DB reactive |
| `switchIfEmpty` | Chuyển sang publisher khác nếu rỗng | Không bắt `onError` |
| `defaultIfEmpty` | Đưa default value khi rỗng | Không xử lý exception |
| `onErrorResume` | Phục hồi theo loại lỗi | Đặt sát nguồn lỗi cần bắt để không nuốt lỗi tầng khác |
| `onErrorMap` | Chuyển loại exception | Giữ cause hữu ích |
| `timeout` | Giới hạn thời gian chờ trong chuỗi | Timeout không đảm bảo Redis command chưa thực thi |
| `retryWhen` | Retry có điều kiện và giới hạn | Không retry side effect vô điều kiện |
| `doOnNext` | Quan sát/log/metric | Tránh side effect nghiệp vụ không quản lý được |
| `doFinally` | Cleanup/metric khi complete/error/cancel | Không coi cancel là rollback |
| `concatMap` | Xử lý tuần tự nhiều value | Thường hữu ích khi cần giữ thứ tự |
| `flatMap` với concurrency | Xử lý song song có giới hạn | Không đảm bảo thứ tự side effect |

### 11.2. Vì sao không gọi subscribe() trong controller?

Sai:

```java
@PostMapping("/bad")
public Mono<String> wrong() {
    redis.opsForValue()
            .set("demo:key", "value")
            .subscribe();

    return Mono.just("ok");
}
```

Response có thể đến trước khi `SET` hoàn tất; nếu `SET` lỗi, response vẫn có thể là `200`. Subscription tự tạo còn không gắn đúng lifecycle/cancellation của HTTP request.

Đúng hơn:

```java
@PostMapping("/good")
public Mono<String> correct() {
    return redis.opsForValue()
            .set("demo:key", "value")
            .flatMap(ok -> Boolean.TRUE.equals(ok)
                    ? Mono.just("ok")
                    : Mono.error(new IllegalStateException(
                            "SET was not confirmed")));
}
```

WebFlux subscribe và quản lý publisher; lỗi đi về hệ thống xử lý error của HTTP.

### 11.3. Vì sao không block() trong request handler?

Sai:

```java
@GetMapping("/bad/{key}")
public String wrong(@PathVariable String key) {
    return redis.opsForValue().get(key).block();
}
```

`block()` đợi đồng bộ, làm mất lợi ích non-blocking và có thể bị Reactor từ chối trên thread được đánh dấu non-blocking. Với workload nhiều request, chờ I/O kiểu này dễ làm giảm throughput.

Nếu phải gọi thư viện blocking như JDBC/JPA, nên cân nhắc dùng stack phù hợp hoặc cách ly thao tác đó trên scheduler cho blocking I/O như `Schedulers.boundedElastic()`:

```java
Mono<Product> result =
        Mono.fromCallable(() -> blockingRepository.find(id))
                .subscribeOn(Schedulers.boundedElastic());
```

Đây là phương án **cô lập blocking**, không biến JDBC thành non-blocking thật và vẫn phải giới hạn connection pool, concurrency và latency. Trong WebFlux reactive end-to-end, R2DBC hoặc một API reactive phù hợp thường dễ kiểm soát hơn.

## 12. Cấu hình serializer: vì sao chọn String + JSON?

Trong ví dụ:

```text
Note object
    |
    v
ObjectMapper.writeValueAsString
    |
    v
JSON String
    |
    v
ReactiveStringRedisTemplate
    |
    v
UTF-8 bytes trong Redis
```

Khi đọc, quá trình đi ngược lại:

```text
Redis UTF-8 String
    |
    v
ReactiveStringRedisTemplate GET
    |
    v
ObjectMapper.readValue(..., Note.class)
    |
    v
Note object
```

Những ranh giới cần giữ:

1. **Redis nil:** không có key theo `GET` → `Mono.empty()`.
2. **JSON literal null:** key có value `"null"` nhưng decoder trả Java null → dữ liệu không hợp lệ theo hợp đồng Note.
3. **JSON schema sai:** Redis có bytes nhưng ứng dụng deserialize lỗi → `Mono.error()`.
4. **Sai key serializer/prefix:** ứng dụng có thể truy vấn một key vật lý khác → miss hợp lệ ở Redis nhưng lỗi cấu hình ở kiến trúc.
5. **Data version:** khi đổi Java record/schema, cần kế hoạch tương thích với dữ liệu đã lưu trong TTL.

### 12.1. ReactiveRedisTemplate với serializer đối tượng

Trong dự án lớn, có thể cấu hình `ReactiveRedisTemplate<String, Note>` với `RedisSerializationContext` để tự xử lý value serialization. Cần thiết lập tường minh:

- Key serializer.
- Value serializer.
- Hash key/value serializer nếu dùng Hash.
- JSON type mapping hoặc schema version.
- Quy tắc xử lý value không đọc được.
- Tương thích giữa các phiên bản ứng dụng lúc rolling deploy.

Không để hai ứng dụng cùng thao tác một namespace nhưng một bên dùng JSON String còn bên kia dùng Java native serialization rồi kết luận “Redis làm mất key”.

### 12.2. JSON mapping không nhất thiết phải chuyển thread

`ObjectMapper` thực hiện xử lý CPU đồng bộ trên dữ liệu đã ở bộ nhớ. Với payload nhỏ như Note, có thể dùng trong `Mono.fromCallable` trên reactive chain. Nhưng với payload cực lớn, mã hóa/giải mã tốn CPU có thể làm chậm event loop. Khi đó cần đo và cân nhắc thay format, giảm payload hoặc cách ly tính toán nặng trên scheduler phù hợp.

**Không gọi `boundedElastic()` cho mọi bước nhỏ chỉ vì thấy một hàm Java đồng bộ.** Chuyển scheduler cũng có overhead; tối ưu dựa trên profiling và đặc tính workload.

## 13. TTL, trượt thời hạn và giới hạn của lưu trữ tạm thời

Ở bài thực hành, mỗi Note có `TTL = 30 phút` khi `SET`:

```text
T0: POST tạo note, TTL 30 phút
T1: GET note, TTL còn 20 phút
T2: GET note, TTL còn 5 phút
T3: Redis hết hạn key
T4: GET note -> Mono.empty -> HTTP 404
```

`GET` không tự gia hạn TTL. Đây là **fixed expiration** kể từ lần ghi.

Nếu muốn **sliding expiration** cho dữ liệu phù hợp, cần cập nhật TTL khi truy cập. Tuy nhiên, ghép `GET` và `EXPIRE` thành hai command riêng không nguyên tử; trong một số trường hợp có race với xóa/ghi lại. Với yêu cầu chặt, có thể dùng lệnh hoặc Lua script phù hợp để đọc và gia hạn trên cùng server/slot.

Đừng áp sliding TTL cho mọi dữ liệu mà không xét:

- Khả năng key sống mãi vì được đọc liên tục.
- Nhu cầu absolute lifetime.
- Rủi ro thao tác GET gia hạn session/lock không đúng chính sách.
- Chi phí thêm write command mỗi lần đọc.
- Redis Cluster slot và script semantics.

Trong production, lưu tài nguyên quan trọng chỉ ở Redis có eviction/TTL cần được đánh giá về durability. `201 Created` ở ví dụ xác nhận `SET` trả thành công, **không phải cam kết dữ liệu chắc chắn tồn tại sau mọi failover hoặc mất máy chủ**.

## 14. Khác biệt giữa Redis miss và Redis error trong API reactive

Giả sử viết:

```java
Mono<Note> noteMono = redis.opsForValue()
        .get(key)
        .flatMap(this::decode);
```

Ba đường đi:

```text
Redis GET thành công, có JSON:
    onNext(json) -> decode -> onNext(Note)

Redis GET thành công, key không tồn tại:
    onComplete -> Mono.empty

Redis timeout / connection failure:
    onError(error) -> Mono.error(error)
```

Sai lầm:

```java
return redis.opsForValue()
        .get(key)
        .onErrorResume(error -> Mono.empty())
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

Đoạn này trả `404` cả khi Redis timeout, phá ý nghĩa HTTP response và che sự cố.

### 14.1. Cache-aside có database nguồn thì khác

Giả sử Redis chỉ là cache còn sản phẩm nằm trong database. Một flow có thể là:

```text
GET cache
    |
    +--> HIT -> trả ngay
    |
    +--> MISS -> gọi Reactive ProductSource
    |              |
    |              +--> Có sản phẩm -> ghi cache TTL, trả sản phẩm
    |              +--> Không có    -> business not found
    |
    +--> Redis ERROR -> policy riêng:
                       fallback có giới hạn hoặc trả 503
```

Ở trường hợp này, lỗi Redis có thể được phép fallback sang database nhưng phải **được đo là ERROR**, không tính là MISS. Nếu database nguồn cũng lỗi, không được chuyển lỗi nguồn thành not-found.

Ví dụ concept (các hàm do ứng dụng cung cấp):

```java
Mono<ProductView> cacheRead =
        productCache.read(productId)
                .onErrorResume(
                        RedisConnectionFailureException.class,
                        error -> {
                            metrics.redisError();
                            return Mono.empty();
                        });

Mono<ProductView> response =
        cacheRead.switchIfEmpty(
                Mono.defer(() -> productSource.findById(productId)));
```

Đây là chính sách cache-only **cố ý fail-open**. Chỉ đặt `onErrorResume` tại phạm vi `productCache.read` để không vô tình bắt lỗi của `productSource`. Trong code production, cần phân biệt metric “source load do miss” và “source load do Redis outage”, hoặc trả một kiểu kết quả có trạng thái tường minh.

Không dùng cách này cho session, distributed lock, nonce hoặc quyết định quyền truy cập nếu không có thiết kế bảo mật phù hợp.

## 15. Reactive cache-aside hoàn chỉnh cần xử lý cả cache write

Một pattern cache-aside khác:

```java
public Mono<ProductView> loadAndCache(String id) {
    return productSource.findById(id)
            .flatMap(product ->
                    productCache.put(product)
                            .onErrorResume(
                                    RedisConnectionFailureException.class,
                                    error -> {
                                        metrics.redisWriteError();
                                        return Mono.empty();
                                    })
                            .thenReturn(product));
}
```

Trong ví dụ, `productSource.findById` là reactive database/source API, còn `productCache.put` trả `Mono<?>` báo kết quả ghi.

Ý nghĩa:

- Database/source là nguồn sự thật.
- Nếu chỉ là cache tối ưu, lỗi ghi cache có thể không làm hỏng response đã lấy từ source.
- Không được nuốt lỗi database trong cùng nhánh catch của Redis.
- Nếu `put` có tác dụng phụ và timeout, có thể không biết cache đã được ghi hay chưa; nhưng caller vẫn có giá trị authoritative từ source.
- Khi một sản phẩm được cập nhật, phải thiết kế invalidation/TTL/version; không chỉ dựa vào cache fill.

Nếu yêu cầu dữ liệu không bao giờ stale, cache-aside đơn giản thường không đủ; cần đọc nguồn authoritative hoặc thiết kế consistency có version/invalidation phù hợp.

## 16. Atomic operations: counter và race condition

Redis có những lệnh nguyên tử trên **một key** như `INCR`. Trong Spring Data Redis reactive:

```java
public Mono<Long> incrementViews(
        ReactiveStringRedisTemplate redis,
        String productId) {

    String key = "demo:webflux:views:v1:" + productId;
    return redis.opsForValue().increment(key);
}
```

`increment` trả `Mono<Long>` chứa giá trị mới khi lệnh hoàn tất.

Không thay bằng read-modify-write:

```java
// Không an toàn khi có nhiều request đồng thời:
return redis.opsForValue().get(key)
        .map(Long::parseLong)
        .flatMap(old -> redis.opsForValue()
                .set(key, Long.toString(old + 1)));
```

Hai request có thể cùng đọc giá trị cũ và ghi đè nhau.

### 16.1. Timeout của INCR là trường hợp cần chú ý

```text
Client gửi INCR
        |
        v
Redis tăng bộ đếm thành công
        |
        v
Kết nối mất trước khi client nhận kết quả
        |
        v
Mono.error(timeout)
```

Nếu retry cả `INCR` vô điều kiện, bộ đếm có thể tăng hai lần. Một reactive chain không tự mang lại exactly-once behavior. Với business counter nhạy cảm, cần operation ID, idempotency hoặc nguồn giao dịch phù hợp.

### 16.2. Reactive @Transactional không bao toàn Redis + DB

`@Transactional` trong ứng dụng R2DBC có thể điều khiển transaction của database reactive tương ứng, nhưng **không tự tạo transaction phân tán giữa database và Redis**.

Nếu vừa update DB vừa `SET` Redis, một bên có thể thành công và bên kia lỗi. Với nghiệp vụ quan trọng, dùng database transaction làm nguồn sự thật, rồi đồng bộ cache qua outbox hoặc cơ chế reconciliation phù hợp.

Redis Lua script giúp kiểm tra–ghi nguyên tử **trong phạm vi một node/slot tương thích**, nhưng không tự đảm bảo rollback các write trước đó nếu script lỗi runtime và không làm xuất hiện transaction xuyên nhiều primary Redis Cluster.

## 17. Đưa Flux vào WebFlux: khi nào phù hợp?

`Mono` phù hợp cho một GET/SET. `Flux` phù hợp khi server có **nhiều phần tử**: quét key, streaming event, đọc records hoặc tổng hợp nhiều Redis operations.

Ví dụ đọc nhiều ID từ client theo reactive chain:

```java
public Flux<Note> findMany(
        NoteService service,
        Flux<String> ids) {

    return ids.flatMap(
            service::findById,
            8); // Tối đa 8 tác vụ inner được đăng ký đồng thời.
}
```

Đây là ví dụ service helper, không phải endpoint đầy đủ. Cần giới hạn số ID từ request, validate input và không cho client tự yêu cầu quét hàng triệu key.

Nếu cần giữ thứ tự kết quả theo input, có thể dùng `concatMap`:

```java
return ids.concatMap(service::findById);
```

Đánh đổi:

| Operator | Đặc điểm | Lưu ý |
|---|---|---|
| `concatMap` | Xử lý lần lượt | Dễ giữ thứ tự, throughput có thể thấp hơn |
| `flatMap(fn, n)` | Cho tối đa n inner subscriptions đồng thời | Có thể hoàn thành lệch thứ tự |
| `flatMapSequential(fn, n)` | Thực thi cạnh tranh nhưng phát kết quả theo thứ tự nguồn | Có thể cần buffer khi phần tử đầu chậm |

Nếu một `findById` trả `Mono.empty()` vì key không có, `flatMap` thường không phát phần tử cho ID đó. API batch có thể cần trả kết quả theo ID với trạng thái HIT/MISS/ERROR riêng để caller không bị nhầm số kết quả trả về với số ID đầu vào.

### 17.1. Backpressure không phải phép màu

Reactive Streams cho phép downstream biểu diễn mức demand. Nhưng Redis server không nhất thiết dừng tạo dữ liệu vì browser tạm đọc chậm, nhất là khi dùng Pub/Sub.

Cần đặt giới hạn:

- Số request đồng thời tới Redis.
- Batch size.
- Kích thước dữ liệu trả về.
- Bộ nhớ buffer.
- Timeout và cancellation policy.
- Những publisher có nguồn vô hạn.

Không dùng `collectList()` cho một `Flux` vô hạn hoặc danh sách key khổng lồ rồi kỳ vọng WebFlux tự bảo vệ memory.

## 18. SSE và Redis Pub/Sub: một hướng mở rộng

Một WebFlux API có thể phát Server-Sent Events (SSE) từ Redis Pub/Sub:

```text
Publisher
   |
   v
Redis PUBLISH updates
   |
   v
Reactive Pub/Sub subscription
   |
   v
Flux<event>
   |
   v
GET /api/events (text/event-stream)
   |
   v
Browser EventSource
```

Spring Data Redis có reactive listener container cho Pub/Sub và khả năng nhận các message thành `Flux` theo API/phiên bản phù hợp.

Một handler SSE có thể trả:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return eventSource.receiveUpdates()
            .map(text -> ServerSentEvent.<String>builder()
                    .data(text)
                    .build());
}
```

`eventSource.receiveUpdates()` đại diện cho một bean do ứng dụng triển khai bằng reactive Redis Pub/Sub subscription, không phải API Spring Data Redis có tên như vậy.

### 18.1. Giới hạn của Redis Pub/Sub

- Message phát khi subscriber mất kết nối có thể bị mất.
- Không có consumer group PEL/ACK/replay cho Pub/Sub thông thường.
- Client HTTP chậm không biến Redis Pub/Sub thành hàng đợi bền có backpressure.
- Cancel HTTP subscription cần được xử lý để tránh rò rỉ subscription/resource.
- Nhiều HTTP client cùng nghe có thể làm tăng tải; cần chiến lược share subscription phù hợp.
- Không dùng Pub/Sub làm nguồn duy nhất cho audit, giao dịch hoặc sự kiện bắt buộc xử lý.

Nếu API cần replay khi client reconnect, hãy cân nhắc Redis Streams hoặc event store/broker có bảo đảm phù hợp, rồi ánh xạ sang `Flux` một cách có kiểm soát.

## 19. Redis Streams reactive với WebFlux

Redis Streams phù hợp hơn Pub/Sub khi cần lưu sự kiện, phân chia công việc theo consumer group và ACK.

Spring Data Redis cung cấp các API reactive liên quan stream, bao gồm `ReactiveStreamOperations` và những thành phần receiver theo khả năng của phiên bản đang dùng.

Luồng ứng dụng:

```text
Producer
    |
    v
XADD stream:orders:v1
    |
    v
Redis Stream
    |
    v
Consumer group read
    |
    v
Flux<Record>
    |
    v
Handler nghiệp vụ (reactive)
    |
    v
Commit hoàn tất
    |
    v
XACK
```

Mẫu composition ở mức ý tưởng:

```java
receiver.receive(
        Consumer.from(group, consumerName),
        StreamOffset.create(
                stream, ReadOffset.lastConsumed()))
    .concatMap(record ->
        processBusiness(record)
                .then(acknowledge(record)));
```

Ở đây `receiver`, `processBusiness` và `acknowledge` là những thành phần cần triển khai theo API thực tế; không phải chương trình hoàn chỉnh. Dùng `concatMap` để đảm bảo chuỗi xử lý và ACK theo thứ tự nếu nghiệp vụ cần.

Đặc điểm cần giữ:

- **Đọc không đồng nghĩa ACK**.
- Một message đã được giao nhưng chưa ACK nằm trong PEL.
- Worker crash trước ACK cần pending recovery.
- Crash sau database commit nhưng trước ACK có thể dẫn tới xử lý lặp, nên handler cần idempotency.
- `ReadOffset.lastConsumed()` để đọc message mới không tự claim pending thuộc consumer đã chết.
- Reactive cancellation không tự xóa PEL hoặc rollback business side effect.
- TTL/retention/trim của Stream không được xóa payload trước thời gian recovery nếu dữ liệu cần bền.

Với API note đơn giản của bài, không cần Streams. Chỉ chọn Streams khi nghiệp vụ thật sự yêu cầu asynchronous work và replay.

## 20. Redis Cluster và reactive connection

Khi Redis được mở rộng thành Cluster, mỗi key thuộc một trong 16.384 hash slot. Lettuce reactive cluster-aware có thể định tuyến các lệnh single-key thông thường:

```text
ReactiveStringRedisTemplate
           |
           v
Lettuce Cluster client
           |
       Tính slot từ key
           |
    +------+------+------+
    |             |      |
    v             v      v
Primary A    Primary B  Primary C
```

Ứng dụng sử dụng `Mono`/`Flux` không làm mất những giới hạn của Redis Cluster:

- Multi-key command có thể yêu cầu cùng hash slot hoặc được driver chia xử lý theo khả năng cụ thể.
- Lua script nhiều key phải tuân thủ slot; không có transaction nguyên tử xuyên nhiều primary.
- `MOVED`/`ASK` có thể xuất hiện khi reshard.
- Một node không sẵn sàng có thể ảnh hưởng những key thuộc slot do node đó quản lý.
- Đọc replica có thể stale vì replication bất đồng bộ.
- Driver topology refresh và retry cần được cấu hình và kiểm thử.
- Một lần ping seed node không đảm bảo mọi slot đều khỏe.

Ví dụ cấu hình seed nodes theo Spring Boot có hỗ trợ properties tương ứng:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:6379
          - redis-b.internal:6379
          - redis-c.internal:6379
        max-redirects: 5
      timeout: 2s
```

Các địa chỉ chỉ minh họa. Khi chạy ở Cluster, cần đảm bảo toàn bộ node được Redis quảng bá có private address có thể truy cập và TLS/ACL đúng.

Ghi chú của bài lưu mỗi object vào **một key**, nên không cần multi-key transaction. Nếu mở rộng thành nhiều key cho một aggregate, có thể dùng hash tag để gom key cùng slot nhưng phải cân nhắc load skew.

## 21. Timeout, retry và cancellation trong reactive I/O

Một endpoint chờ Redis không thể chờ vô hạn. Ứng dụng nên có deadline phù hợp HTTP và command timeout.

Ví dụ giới hạn thời gian trong reactive chain:

```java
return service.findById(id)
        .timeout(Duration.ofSeconds(2))
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND)));
```

Cần phân biệt:

- `Mono.empty()` khi Redis xác nhận key không tồn tại → có thể trả `404`.
- `TimeoutException` từ Reactor `timeout` → error, không phải miss.
- Timeout của Lettuce/connection cũng là error, với loại exception khác.
- Timeout không chứng minh command ghi chưa được áp dụng.

### 21.1. Retry chỉ cho lỗi phù hợp

Với `GET` idempotent, có thể retry ngắn nếu gặp lỗi transient. Nhưng không dùng:

```java
.retry()
```

không giới hạn trên một API phục vụ traffic lớn. Nó có thể tạo vòng retry vô hạn và gây quá tải Redis lúc sự cố.

Một pattern có giới hạn cần lọc exception và có backoff, ví dụ:

```java
return redis.opsForValue()
        .get(key)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isTransientRedisFailure));
```

`isTransientRedisFailure` là policy phân loại lỗi do ứng dụng định nghĩa; không mặc định lỗi JSON schema, ACL `NOPERM` hoặc `WRONGTYPE` là transient.

Đối với `SET` trong bài, gửi lại cùng key và cùng value có thể tương đối an toàn về hiệu quả trong những tình huống nhất định, nhưng sẽ ảnh hưởng TTL và có thể ghi đè một update cạnh tranh. Đối với `INCR`, Lua có side effect hoặc `XADD`, retry sau timeout có nguy cơ tạo tác dụng lặp. **Không áp retry giống nhau cho mọi command**.

### 21.2. Cancellation khi client ngắt kết nối

HTTP client có thể ngắt request khi Redis đang thực hiện command. Reactor có thể hủy subscription phía ứng dụng, nhưng nếu lệnh đã được gửi tới Redis thì server vẫn có thể hoàn tất.

```text
POST /api/notes
    |
    v
Client gửi SET tới Redis
    |
    v
Browser ngắt kết nối
    |
    v
Publisher bị cancel
    |
    v
Redis vẫn có thể đã lưu Note
```

Đừng suy luận client không nhận `201` thì Redis chắc chắn chưa tạo note. Nếu yêu cầu chống tạo trùng giữa retry, dùng idempotency key ổn định từ request và một cơ chế atomic trên Redis hoặc database phù hợp.

## 22. WebFlux không thay thế xác thực và bảo mật

Một API chạy reactive vẫn cần cùng các lớp bảo vệ cơ bản:

- Spring Security WebFlux filter chain nếu endpoint có user authentication.
- Authorization theo resource và tenant.
- Validation độ dài request/payload.
- Rate limiting phù hợp.
- Redis private network, TLS, Redis ACL.
- Không log session ID, JWT, password hoặc dữ liệu nhạy cảm.
- Không đưa một generic Redis command execution endpoint ra Internet.

API note trong bài là ví dụ **không có authentication** để tập trung vào Reactive Redis. Trong production, không sử dụng nguyên mẫu này như kho ghi chú riêng tư của nhiều người dùng.

Nếu dữ liệu phân theo tenant/user, key nên bao gồm scope đã được xác thực theo quy tắc phù hợp, ví dụ:

```text
tenant:team-7:notes:v1:<note-uuid>
```

Nhưng **không tin tenant ID do client tự nhập** nếu request chưa được authorize. Cần lấy tenant/principal từ security context đã xác thực, chống truy cập chéo tenant khi GET/DELETE theo ID.

### 22.1. Reactive SecurityContext khác ThreadLocal thông thường

Trong WebFlux, Reactor context tham gia truyền thông tin bảo mật qua reactive chain. Không giả định `SecurityContextHolder` dùng ThreadLocal trong một reactive handler luôn có cùng hành vi như Servlet request thread.

Khi cần principal, dùng WebFlux/Spring Security reactive API thích hợp, chẳng hạn controller nhận `Principal`/`Mono<Principal>` theo hợp đồng framework hoặc `ReactiveSecurityContextHolder` trong chain.

Không dùng session user ID từ query parameter làm bằng chứng authorization chỉ vì nó được chuyển qua một `Mono`.

## 23. Quan sát API và Redis theo từng lớp

Một hệ thống reactive cần các metric riêng cho HTTP, Redis và tầng nghiệp vụ.

| Metric | Ý nghĩa |
|---|---|
| HTTP requests/s và error rate | Khả năng phục vụ tổng thể |
| HTTP p50/p95/p99 | Latency người dùng nhìn thấy |
| Redis GET/SET/DEL latency | Độ trễ lệnh Redis |
| Redis connection failures | Lỗi mạng, TLS, auth và reconnect |
| Redis timeout count | Lệnh vượt deadline |
| Redis cache hit/miss | Tình trạng dữ liệu khi Redis là cache |
| Redis invalid payload count | JSON/schema bị lỗi |
| Redis command failures theo loại | Phân biệt lỗi mạng và sai loại dữ liệu |
| Event-loop delay | Dấu hiệu có thao tác blocking hoặc CPU quá nặng |
| Active requests/subscriptions | Áp lực concurrency |
| Reactor operator errors/cancellations | Reactive chains lỗi hoặc bị hủy |
| Redis Cluster redirects/slot errors | Vấn đề topology |
| Redis memory/evictions | Khả năng data mất trước TTL |
| HTTP 404 và 503 tách biệt | Không nhầm resource missing với hạ tầng lỗi |

Với Spring Boot Actuator, có thể dùng health endpoint cho Redis nếu auto-configuration hỗ trợ; nhưng readiness/liveness cần tách mục đích:

- Liveness: process còn hoạt động hay bị kẹt.
- Readiness: instance có thể tiếp nhận công việc mới hay không.
- Redis health: một dependency có sẵn sàng hay không; nó không chứng minh toàn bộ business workflow đúng.

Nếu Redis là kho dữ liệu bắt buộc của API note, readiness có thể phụ thuộc Redis. Nếu Redis chỉ là cache tùy chọn có fallback an toàn, không nhất thiết cần chuyển toàn bộ ứng dụng sang unready khi Redis outage.

### 23.1. Không để health check tạo tải lớn

Không nên để mỗi `GET /actuator/health/readiness`:

- `SCAN` toàn bộ Redis keyspace.
- Tạo/xóa nhiều key.
- Gửi Pub/Sub event rồi đợi subscriber.
- Kiểm tra tất cả Redis Cluster nodes bằng hàng trăm lệnh.
- Mở một connection factory mới.
- Chạy database query nặng để xác nhận cache consistency.

Health check thường được gọi liên tục; nó phải nhẹ và có timeout.

## 24. Kiểm thử API bằng WebTestClient và Redis thật

Mock service có thể kiểm tra controller, nhưng không chứng minh `SET` với TTL, Redis nil, `DEL` và serialization hoạt động đúng. Với bài tích hợp, dùng **Testcontainers** để chạy Redis thật.

Ví dụ:

```java
package com.example.rediswebflux;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.example.rediswebflux.note.Note;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.data.redis.host",
                REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    WebTestClient client;

    @Test
    void canCreateReadAndDeleteNote() {
        EntityExchangeResult<Note> created =
                client.post()
                        .uri("/api/notes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of("text", "Hello Redis"))
                        .exchange()
                        .expectStatus().isCreated()
                        .expectBody(Note.class)
                        .returnResult();

        Note note = created.getResponseBody();
        assertNotNull(note);

        client.get()
                .uri("/api/notes/{id}", note.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.text")
                .isEqualTo("Hello Redis");

        client.delete()
                .uri("/api/notes/{id}", note.id())
                .exchange()
                .expectStatus().isNoContent();

        client.get()
                .uri("/api/notes/{id}", note.id())
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void missingValidUuidReturnsNotFound() {
        client.get()
                .uri("/api/notes/{id}",
                        "00000000-0000-0000-0000-000000000001")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void invalidBodyReturnsBadRequest() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("text", " "))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Với phiên bản Spring Boot/đường package testing khác nhau, điều chỉnh imports hoặc auto-configuration tương ứng. Test cần chạy trong một Spring Boot application context có `NoteService` và `NoteController`. Docker/Testcontainers phải có quyền tạo container.

### 24.1. Vì sao dùng Redis thật?

Một mock `ReactiveStringRedisTemplate` có thể giả lập:

```java
Mono.just("json")
Mono.empty()
Mono.error(new RuntimeException("Redis failed"))
```

nhưng **không kiểm tra**:

- Key serializer thực.
- TTL được Redis áp dụng.
- Redis String value trả về đúng.
- Xóa và đọc lại key.
- ACL/connection/TLS.
- Lệnh được thực thi như mong đợi.
- Redis data isolation giữa các test.

Testcontainers giúp thu hẹp khoảng cách đó trong integration test. Không cần chạy Redis thật cho mọi unit test đơn giản; dùng kết hợp cả hai cấp.

## 25. Test Reactor với StepVerifier

Đối với service tạo `Mono`/`Flux`, `StepVerifier` giúp kiểm tra trực tiếp các loại tín hiệu:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.just("READY"))
        .expectNext("READY")
        .verifyComplete();

StepVerifier.create(Mono.<String>empty())
        .verifyComplete();

StepVerifier.create(
                Mono.<String>error(
                        new IllegalStateException("Redis unavailable")))
        .expectError(IllegalStateException.class)
        .verify();
```

Đây là ví dụ kiểm tra **ngữ nghĩa tín hiệu Reactor**. Để kiểm tra service thật, có thể mock Redis operations hoặc dùng Redis Testcontainers.

### 25.1. Các tình huống đáng kiểm tra

| Kịch bản | Kỳ vọng |
|---|---|
| GET key tồn tại | `Mono<Note>` phát Note và HTTP 200 |
| GET key thiếu | `Mono.empty()` ở service, HTTP 404 |
| Redis connection refused | `onError`, HTTP 503/5xx theo policy |
| Redis key chứa JSON không hợp lệ | Decode lỗi, không trả 404 |
| SET với TTL | Redis có key và TTL dương |
| Đợi TTL hết | GET trở thành empty/404 |
| DELETE cùng ID hai lần | Lần đầu true/204, lần sau false/404 |
| Input text rỗng | HTTP 400, không ghi Redis |
| UUID path sai | HTTP 400 |
| Nhiều POST đồng thời | Tạo ID riêng và không block event loop |
| Cancel khi SET đang chạy | Không suy luận command chưa áp dụng |
| Retry INCR sau timeout | Chính sách idempotency được kiểm tra |
| Redis Cluster failover | Error/reconnect không bị giả thành miss |
| Server shutdown | Không tạo subscription/connection rò rỉ |

Với test TTL, không nên dựa vào `Thread.sleep(100)` và một khoảng thời gian quá ngắn khiến bài kiểm thử flaky. Chọn TTL test phù hợp và dùng bounded polling/deadline để xác định khi nào key thực sự hết hạn.

### 25.2. Kiểm tra TTL trực tiếp trong integration test

Một cách bổ sung là inject `ReactiveStringRedisTemplate` vào test, tạo một ghi chú rồi kiểm tra:

```java
StepVerifier.create(
        redis.getExpire(
                "demo:webflux:notes:v1:" + createdNote.id()))
        .assertNext(ttl -> {
            // TTL vừa tạo thường lớn hơn 0 và không vượt 30 phút.
            org.junit.jupiter.api.Assertions.assertTrue(
                    ttl.compareTo(Duration.ZERO) > 0);
            org.junit.jupiter.api.Assertions.assertTrue(
                    ttl.compareTo(Duration.ofMinutes(30)) <= 0);
        })
        .verifyComplete();
```

Ví dụ là một assertion bổ sung trong test có các biến `redis` và `createdNote` đã được chuẩn bị. Nó không thay cho test HTTP và không khẳng định key sẽ sống đủ 30 phút nếu Redis bị evict hoặc dữ liệu mất khi sự cố.

## 26. Test lỗi mạng, deserialize và backpressure

Một API có thể hoạt động đúng khi Redis khỏe nhưng sai khi Redis mất kết nối.

Kịch bản test:

1. Tạo một ghi chú khi Redis còn hoạt động.
2. Ngắt Redis test hoặc chặn connection tới container theo cơ chế thử nghiệm.
3. Gửi GET lại ID đó.
4. Đảm bảo response không bị chuyển thành `404` chỉ vì Redis unavailable.
5. Kiểm tra timeout được giới hạn, không treo request vô hạn.
6. Khôi phục Redis và quan sát kết nối lại.
7. Nếu container đã bị xóa và tạo lại, hiểu rằng dữ liệu Redis có thể đã mất: khi đó GET trả `404` là do key thực sự không còn trong store mới, khác với connection failure.

Để thử JSON lỗi, ghi một value không hợp lệ vào đúng test key, rồi gọi GET và xác nhận handler không trả 404:

```bash
redis-cli SET \
  demo:webflux:notes:v1:00000000-0000-0000-0000-000000000001 \
  'not-valid-json' EX 120
```

Dùng Redis test riêng. Không chỉnh key của ứng dụng production để tạo lỗi deserialize.

### Test concurrency

Chạy nhiều request `POST` đồng thời với WebTestClient hoặc công cụ load-test, đo:

- HTTP throughput và p95/p99 latency.
- Redis connections/command latency.
- Tỷ lệ thành công và số key đã tạo.
- JVM heap và event-loop delay.
- Error rate khi Redis đạt giới hạn.
- Sự khác biệt khi vô tình thêm một bước blocking.

Không đánh giá “reactive hiệu năng tốt hơn” chỉ vì code không có `block()`. Cần so sánh cùng workload, payload, network topology và memory budget.

## 27. Vận hành trong Kubernetes và graceful shutdown

Khi triển khai WebFlux + Redis, ứng dụng cần dừng có kiểm soát:

```text
Pod startup
    |
    v
Spring context tạo ReactiveRedisTemplate/Lettuce
    |
    v
Readiness được công bố theo dependency policy
    |
    v
Nhận HTTP requests
    |
    v
Pod nhận SIGTERM
    |
    v
Ngừng nhận request mới
    |
    v
Cho in-flight requests hoàn tất theo deadline
    |
    v
Hủy/đóng background subscriptions nếu có
    |
    v
Spring giải phóng connection factory
    |
    v
Process kết thúc
```

Ví dụ cấu hình:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoint:
    health:
      probes:
        enabled: true
```

Nếu Redis là thành phần bắt buộc của mọi endpoint, readiness có thể cần contributor Redis được đưa vào health group theo cấu hình Actuator của phiên bản Boot. Nếu chỉ là cache có fallback, cần chính sách khác để tránh mọi pod đồng thời not ready khi Redis outage.

**Spring Boot graceful shutdown chỉ là một phần**. Những subscription nền như Pub/Sub/SSE hoặc Redis Stream consumer do ứng dụng tự mở phải được quản lý và đóng đúng lifecycle; không tạo `subscribe()` vô chủ rồi hy vọng JVM dừng sẽ dọn sạch ngay.

### 27.1. Tránh đóng LettuceConnectionFactory trong handler

Không gọi `destroy()` hoặc `close()` trên shared connection factory sau mỗi HTTP request. Đây là infrastructure bean thuộc Spring context; đóng sớm có thể phá các request khác.

Với native client/low-level connection tự tạo, thành phần tạo phải giải phóng nó đúng ownership và đúng thứ tự.

## 28. Các lỗi phổ biến khi tích hợp WebFlux với Redis reactive

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Gọi `.block()` trong WebFlux controller | Giữ thread chờ Redis, có thể làm nghẽn event loop | Trả `Mono`/`Flux` cho WebFlux |
| Gọi `.subscribe()` rồi trả success | Trả HTTP trước khi Redis ghi xong, lỗi bị tách | Compose publisher và trả chain |
| Dùng `StringRedisTemplate` blocking trong reactive flow | Mất non-blocking I/O | Dùng `ReactiveStringRedisTemplate` |
| `Mono.empty()` bị coi là Redis outage | Trả lỗi khi key thiếu bình thường | Phân biệt miss và error |
| `onErrorResume(e -> Mono.empty())` cho mọi lỗi | Redis timeout thành 404 | Chỉ fallback theo lỗi/policy cụ thể |
| JSON `null` biến thành key miss | Sai contract dữ liệu | Từ chối payload null/invalid |
| Không đặt TTL cho dữ liệu tạm | Key tích lũy, tăng memory | SET kèm Duration |
| Tách SET và EXPIRE không kiểm soát | Key có thể tồn tại không TTL | SET với expiration trong một command |
| Retry `INCR`/`XADD` vô điều kiện | Tăng bộ đếm hoặc tạo event trùng | Idempotency và retry policy |
| Dùng `@Transactional` rồi nghĩ Redis + R2DBC atomic | Hai nguồn có thể commit lệch | Nguồn authoritative/outbox |
| `flatMap` concurrency vô hạn | Nhiều lệnh/connection/buffer cùng lúc | Giới hạn concurrency, backpressure |
| Dùng `collectList()` cho Flux vô hạn | Tăng memory vô hạn | Streaming/bounded batches |
| Cho phép client chọn Redis key tự do | Truy cập sai namespace, dữ liệu nhạy cảm | Key từ ID đã validate và scope |
| Public Redis port | Lộ dữ liệu và bề mặt tấn công | Private network/TLS/ACL |
| Serializer giữa các ứng dụng không khớp | Miss giả hoặc decode lỗi | Serializer/schema có version |
| Dùng Pub/Sub làm event log bền | Mất message khi subscriber offline | Streams/broker bền |
| Đọc Redis replica cho session/lock quan trọng | Có thể đọc stale | Chọn consistency policy phù hợp |
| Chỉ test controller bằng mock | Không kiểm tra Redis TTL/serialization thật | WebTestClient + Testcontainers |
| Chỉ ping một node Redis Cluster | Không phát hiện lỗi slot khác | Cluster metrics và kiểm thử topology |
| Không đo event-loop blocking | p99 tăng khó giải thích | Observability và profiling |

## 29. Checklist hoàn thành bài thực hành

**Ứng dụng và API**

- Spring Boot chạy WebFlux và dependency Redis reactive.
- Inject được `ReactiveStringRedisTemplate`.
- `POST` ghi JSON với TTL và chỉ trả `201` khi SET thành công.
- `GET` trả Note hoặc HTTP `404` đúng cho Redis nil.
- `DELETE` xác nhận số key đã xóa.
- Input và ID được validate.
- Không có `block()`/`subscribe()` tự phát trong controller.

**Reactive semantics**

- Phân biệt `Mono.just`, `Mono.empty` và `Mono.error`.
- Dùng `flatMap` để ghép lệnh Redis bất đồng bộ.
- `switchIfEmpty` chỉ dùng cho nhánh thực sự rỗng.
- Error handler không nuốt bừa Redis failures.
- Timeout/retry chỉ dùng theo chính sách, không tạo side effect trùng.
- Có giới hạn concurrency cho batch/Flux.

**Redis data**

- Namespace key có version và scope phù hợp.
- Serializer/thời gian sống được xác định.
- TTL không bị gia hạn ngoài ý muốn.
- Invalid JSON được coi là lỗi dữ liệu, không phải miss.
- Redis Cluster/Sentinel/TLS/ACL phù hợp khi chuyển sang production.
- Không dùng Redis TTL data làm nguồn giao dịch bền nếu nghiệp vụ cần durability mạnh.

**Kiểm thử và vận hành**

- `curl` tạo/đọc/xóa thành công.
- WebTestClient + Testcontainers kiểm tra Redis thật.
- Có test key thiếu, input sai, Redis lỗi, JSON lỗi và TTL.
- Readiness/liveness phản ánh vai trò Redis.
- Có metric HTTP/Redis latency và lỗi.
- WebFlux event loop không bị thao tác blocking kéo dài.
- Connection factory/subscription được giải phóng đúng lifecycle.

## 30. Tổng kết

Tích hợp Redis phản ứng vào API WebFlux không chỉ là đổi `RedisTemplate` thành `ReactiveRedisTemplate`. Phần quan trọng là **xây dựng một chuỗi xử lý bất đồng bộ có thể quan sát và quản lý lỗi đúng**:

1. **Controller trả Mono/Flux**, để WebFlux subscribe và quản lý lifecycle.
2. **Lettuce reactive thực hiện Redis I/O** mà không cần block thread chờ response.
3. **Redis nil khác Redis failure.** `Mono.empty()` có thể biểu diễn key không tồn tại, còn `onError` phải được xử lý như lỗi.
4. **Serialization và TTL là một phần của contract dữ liệu.** Key tồn tại với payload lỗi không phải miss; note tạm cần SET kèm expiry.
5. **Lệnh Redis không tự là transaction xuyên toàn hệ thống.** Retry, cancellation và DB/Redis dual-write cần idempotency/consistency policy.
6. **Flux không loại bỏ mọi giới hạn tài nguyên.** Dùng concurrency control, backpressure và giới hạn payload.
7. **Kiểm thử bằng Redis thật.** WebTestClient + Testcontainers xác nhận behavior của GET/SET/DELETE/TTL và error path.
8. **Triển khai vẫn phải an toàn.** Private Redis, TLS/ACL, readiness, graceful shutdown và observability quan trọng không kém code reactive.

Với ứng dụng bài tập, `ReactiveStringRedisTemplate`, JSON String và `Mono<Note>` là cách dễ quan sát từ HTTP đến Redis. Khi phát triển thành hệ thống production, hãy tiếp tục phân biệt **Redis là cache hay nguồn dữ liệu chính**, lựa chọn serialization và độ bền phù hợp, và dùng reactive composition như một phương tiện để kiểm soát công việc bất đồng bộ — không phải thay thế cho thiết kế nghiệp vụ đúng.

