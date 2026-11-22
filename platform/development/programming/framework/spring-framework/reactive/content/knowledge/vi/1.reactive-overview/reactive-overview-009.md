# Lộ trình từ chuỗi Reactor đến ứng dụng reactive hoàn chỉnh

> **Phạm vi:** Spring Framework – Reactive | **Chủ đề:** Tổng quan. Bài học dẫn từ tư duy xử lý luồng Reactor đến một API Spring WebFlux chạy được, rồi mở rộng thành dịch vụ có dữ liệu, kiểm thử, bảo mật và vận hành. Ví dụ chính dùng Java 17+ và Spring Boot 4.0.9. Phiên bản được ghim để có thể tái lập bài thực hành; với hệ thống thật, kiểm tra phiên bản Spring Boot còn được hỗ trợ trước khi triển khai.

## 1. Học xong cần làm được gì?

Một lập trình viên hoàn thành lộ trình phải:
1. Đọc được chuỗi **Mono** và **Flux**, xác định lúc tạo pipeline, lúc subscribe, nơi phát giá trị, lỗi và hoàn thành.
2. Chọn đúng **map**, **flatMap**, **concatMap**, **zip**, **switchIfEmpty**, **onErrorResume**, **timeout**, **retryWhen**; hiểu thứ tự, đồng thời, cold/hot và backpressure.
3. Viết HTTP endpoint **Spring WebFlux** trả về Mono/Flux mà không chặn event-loop; kết nối WebClient và kho dữ liệu reactive bằng cùng một chuỗi bất đồng bộ.
4. Phân biệt minh họa chạy được với lựa chọn vận hành thật: lưu trữ bền vững, transaction, giới hạn tài nguyên, bảo mật, metric, log, trace.
5. Kiểm thử bằng **StepVerifier** và **WebTestClient**, mô phỏng lỗi, hủy subscription, timeout và độ trễ.

**Đích đến:** một đường xử lý xuyên suốt từ HTTP request → controller → service → repository/WebClient → tín hiệu onNext/onError/onComplete → HTTP response, với quản lý tài nguyên và khả năng quan sát được.

## 2. Mô hình tư duy: từ lệnh tuần tự sang chuỗi tín hiệu

Trong xử lý đồng bộ, mỗi lời gọi thường chờ kết quả trước khi đi tiếp. Reactor biểu diễn công việc bằng **Publisher**; khi có **Subscriber** đăng ký, Publisher có thể gửi các tín hiệu:
- **onSubscribe**: cung cấp Subscription; phía tiêu thụ có thể request(n) để thông báo nhu cầu.
- **onNext(value)**: một phần tử dữ liệu; một publisher tuân thủ Reactive Streams không được gửi null.
- **onComplete**: hoàn thành bình thường, không còn dữ liệu.
- **onError(error)**: kết thúc bằng lỗi; sau onError/onComplete không có onNext hợp lệ nữa.
- **cancel**: subscriber hủy luồng, cho phép upstream giải phóng tài nguyên nếu hỗ trợ.

**Mono<T>** biểu diễn 0 hoặc 1 giá trị rồi kết thúc; **Flux<T>** biểu diễn 0 đến nhiều giá trị. Mono.empty() nghĩa là hoàn thành không có dữ liệu, khác với Mono.error(...) và khác với một giá trị null. Mono<Void> dùng cho thao tác chỉ cần biết hoàn tất.

Một pipeline thường **lazy**: gọi map/flatMap chỉ tạo mô tả; việc thực thi bắt đầu khi có subscription. Trong WebFlux, framework subscribe vào Publisher trả từ controller. Trong code nghiệp vụ, thường trả nguyên Mono/Flux và để lớp biên điều khiển subscription, không gọi subscribe() rải rác. Mỗi lần subscribe vào **cold publisher** có thể chạy lại nguồn (ví dụ gọi API/lưu bản ghi); phải lưu ý tác dụng phụ. **Hot publisher** có thể phát độc lập với subscriber, người đến sau có thể bỏ lỡ sự kiện; dùng share/replay/Sinks có chủ đích và thiết kế chính sách lưu đệm.

**Backpressure** là cơ chế subscriber báo số lượng phần tử mong nhận. Nó giúp điều phối luồng có hỗ trợ demand, nhưng không tự giới hạn mọi nguồn nóng, hàng đợi, kết nối hay hệ thống ngoài. Cần kết hợp giới hạn concurrency, pool, timeout, rate limit và chính sách tràn bộ đệm.

### Bản đồ xử lý

~~~text
HTTP request
    ↓
WebFlux controller trả Mono/Flux
    ↓
Service: kiểm tra đầu vào + ghép các Publisher
    ↓
Repository reactive / WebClient / luồng sự kiện
    ↓
onNext, onComplete hoặc onError
    ↓
Codec HTTP ghi JSON/SSE và xử lý hủy khi client ngắt
~~~

Lợi ích lớn của non-blocking I/O là một lượng nhỏ thread có thể phục vụ nhiều yêu cầu đang chờ I/O. Điều đó không đồng nghĩa mọi tác vụ trở nên nhanh hơn: tác vụ CPU nặng, JDBC/JPA đồng bộ, đọc file chặn hay một SDK blocking vẫn có thể làm nghẽn event-loop nếu đặt sai chỗ. Ứng dụng truy cập DB nhẹ và đồng bộ hoàn toàn có thể phù hợp với Spring MVC hơn. Chọn WebFlux khi luồng I/O bất đồng bộ, streaming và quản lý tải là nhu cầu có thật.

## 3. Nắm vững chuỗi Reactor trước khi viết HTTP

### 3.1. Mỗi toán tử làm gì?

| Toán tử | Khi dùng | Điểm cần nhớ |
| --- | --- | --- |
| map | Biến đổi đồng bộ từng giá trị | Hàm chuyển đổi không nên trả Publisher và không được trả null. |
| flatMap | Gọi hàm trả Mono/Flux bất đồng bộ, cho phép công việc đan xen | Kết quả có thể thay đổi thứ tự; giới hạn concurrency nếu upstream nhiều phần tử. |
| concatMap | Ghép Publisher tuần tự, giữ thứ tự | Dễ dự đoán nhưng có thể giảm thông lượng. |
| flatMapSequential | Chạy nhiều công việc cùng lúc nhưng xuất ra theo thứ tự nguồn | Có thể tốn bộ đệm khi phần tử trước đến chậm. |
| filter / distinct | Chọn dữ liệu và loại trùng | Với dữ liệu lớn, distinct có trạng thái lưu dấu, cần giới hạn đầu vào. |
| collectList | Gom Flux thành Mono<List<T>> | Chờ hoàn thành và giữ tất cả trong RAM; tránh dùng với stream vô hạn. |
| zip / zipWith | Ghép các nguồn có phần tử | Nguồn rỗng có thể khiến kết quả rỗng và hủy nguồn khác. |
| switchIfEmpty | Xử lý nhánh Mono/Flux không có giá trị | Dùng Mono.defer(...) nếu fallback có công việc/tác dụng phụ cần trì hoãn. |
| onErrorResume | Phục hồi bằng Publisher thay thế | Không được biến mọi lỗi thành thành công giả hoặc giấu lỗi nghiêm trọng. |
| timeout | Chặn thời gian chờ vượt ngân sách | Nên xác định thời hạn cho mỗi hop và toàn request. |
| retryWhen | Thử lại có điều kiện | Chỉ retry lỗi tạm thời; cân nhắc idempotency, backoff và jitter. |
| doOnNext/doOnError/doFinally | Quan sát tín hiệu, cleanup/metric | Không dùng chúng như bước biến đổi dữ liệu nghiệp vụ. |

**Ví dụ chuỗi:** đầu vào là những tên được làm sạch, bỏ trùng và chuẩn hóa; mã này là một fragment Java đặt trong một phương thức có import Reactor và java.util.Locale.

~~~java
Flux<String> names = Flux.just("  an ", "binh", "an", "  ");
Mono<List<String>> normalized = names
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .distinct()
    .map(s -> s.toUpperCase(Locale.ROOT))
    .collectList();

// Chỉ ở chương trình dòng lệnh hoặc test mới chủ động chờ:
System.out.println(normalized.block());
~~~

**Stdout:** [AN, BINH]. **Không đặt block() trong controller WebFlux.** Nguồn Flux ở đây hữu hạn, nên collectList phù hợp; với một luồng sự kiện vô hạn cần giới hạn hoặc trả trực tiếp Flux.

### 3.2. Phân biệt map và flatMap

~~~java
Mono<String> userId = Mono.just("u-7");

// Hàm xử lý trực tiếp tạo chuỗi.
Mono<String> label = userId.map(id -> "User " + id);

// Hàm xử lý trả một Publisher bất đồng bộ.
Mono<String> profile = userId.flatMap(id -> fetchProfile(id));
~~~

Trong ví dụ, fetchProfile(String) **đại diện cho một phương thức có thật trả Mono<String> trong ứng dụng**, không phải hàm có sẵn của Reactor; fragment này minh họa kiểu dữ liệu, không phải chương trình độc lập. Dùng map với fetchProfile sẽ tạo Mono<Mono<String>>, thường là sai ý định.

### 3.3. Kiểm soát thứ tự và đồng thời

~~~java
Flux<String> ids = Flux.just("u1", "u2", "u3");
Flux<String> sequential = ids.concatMap(this::loadUser);
Flux<String> concurrent = ids.flatMap(this::loadUser, 4);
~~~

Giả sử loadUser(String) trả Mono<String>. concatMap giữ thứ tự và chỉ xử lý từng nguồn phụ một; flatMap cho phép nhiều thao tác cùng lúc, giới hạn ở 4 trong ví dụ, nhưng không bảo đảm thứ tự đầu ra. Không nên chọn một số concurrency cực lớn chỉ vì throughput tăng trên máy phát triển.

### 3.4. Thread và Scheduler

Reactor không tự tạo thread cho từng operator. **subscribeOn(scheduler)** tác động đến đường subscribe và nguồn phía upstream; thường đặt gần nguồn có blocking I/O. **publishOn(scheduler)** đổi ngữ cảnh xử lý cho các toán tử phía downstream. Không nên đổi scheduler thường xuyên nếu không có lý do đo được.

~~~java
Mono<String> fromLegacyLibrary = Mono
    .fromCallable(() -> legacyBlockingRead())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Trong ví dụ, legacyBlockingRead() là một lời gọi blocking đã tồn tại trong hệ thống. Đây là **cầu nối tạm thời**, không biến thư viện blocking thành non-blocking. Schedulers.boundedElastic() có giới hạn số worker và hàng chờ; phải giám sát khi tải tăng. Không dùng Schedulers.parallel() cho blocking I/O. Tránh block(), blockFirst(), Thread.sleep() và JDBC chặn trực tiếp trên Netty event-loop.

### 3.5. Lỗi là tín hiệu kết thúc

~~~java
Mono<String> result = remoteCall()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(TimeoutException.class, ex -> Mono.just("cached"));
~~~

Đây là fragment cần có remoteCall() trả Mono<String> và import tương ứng. Bản fallback chỉ đúng nếu dữ liệu cache có thể chấp nhận theo yêu cầu nghiệp vụ. Lỗi timeout của WebClient, lỗi HTTP và lỗi domain cần phân loại riêng; onErrorResume không khôi phục chính publisher đã lỗi để phát tiếp, mà chuyển sang Publisher thay thế. Retry có thể **tái đăng ký** vào nguồn, nghĩa là phát lại side effect nếu không idempotent.

## 4. Lộ trình học và mốc hoàn thành

| Chặng | Năng lực chính | Bài thực hành | Tiêu chí hoàn thành |
| --- | --- | --- | --- |
| 1. Reactor cơ bản | Signal, Mono, Flux, lazy, cold/hot | Chuyển danh sách bằng map/filter/collectList | Giải thích được tín hiệu và thời điểm thực thi. |
| 2. Kết hợp pipeline | flatMap/concatMap/zip, empty/error | Ghép 2 tác vụ I/O giả lập, chọn fallback | Có test cho thành công, rỗng và lỗi; biết khi nào thứ tự thay đổi. |
| 3. Tài nguyên | Scheduler, backpressure, cancel, timeout | Bọc một lời gọi blocking bằng boundedElastic; giới hạn concurrency | Không khóa event-loop; cancel/timeout có hành vi dự kiến. |
| 4. HTTP WebFlux | Annotated controller hoặc functional routes, codec JSON, HTTP status | Tạo API GET/POST/PATCH dùng Mono/Flux | Có thể chạy curl, test được 201/400/404. |
| 5. Tích hợp reactive | WebClient, reactive repository, transaction | Kết nối service ngoài và DB bằng R2DBC | Không tự subscribe, không gọi JDBC trên event-loop, xử lý retry hợp lý. |
| 6. Vận hành | Test, security, metrics, tracing, capacity | Đo latency, tải và kiểm tra lỗi | Có dashboard, alert, budget timeout, bảo mật và quy trình rollout. |

Lộ trình không bắt buộc chuyển một ứng dụng Spring MVC đang ổn định sang WebFlux. Mỗi chặng nên có một bài đo thực tế về tải/latency và một bài kiểm thử trước khi mở rộng.

## 5. Dự án mẫu chạy được: Reactive Tasks API

Dự án này tạo task trong bộ nhớ để người học chạy ngay mà không cần database. Đây là **ứng dụng WebFlux hoàn chỉnh cho mục tiêu học HTTP → service → Reactor → JSON → test**, nhưng dữ liệu mất khi restart và chưa đáp ứng yêu cầu lưu trữ bền vững của sản phẩm thật. Bước kế tiếp sẽ thay tầng service/repository bằng R2DBC mà giữ hợp đồng HTTP.

**Yêu cầu:** JDK 17+, Maven 3.6.3+ và cổng 8080 còn trống. Dùng Spring Boot 4.0.9 (Spring Framework 7); Boot quản lý phiên bản Reactor tương thích, không tự ghim phiên bản reactor-core khác BOM.

Cấu trúc:

~~~text
reactive-tasks/
├── pom.xml
├── src/main/java/com/example/reactivetasks/
│   ├── ReactiveTasksApplication.java
│   ├── Task.java
│   ├── CreateTaskRequest.java
│   ├── TaskService.java
│   └── TaskController.java
└── src/test/java/com/example/reactivetasks/
    └── TaskControllerTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-tasks</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

Spring Boot starter WebFlux đưa WebFlux, Reactor Netty, JSON codec và Reactor vào classpath. Starter WebFlux Test cung cấp hạ tầng kiểm thử WebFlux cùng Reactor Test trong cấu hình mẫu này.

### 5.2. Điểm khởi động

**src/main/java/com/example/reactivetasks/ReactiveTasksApplication.java**

~~~java
package com.example.reactivetasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTasksApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTasksApplication.class, args);
    }
}
~~~

### 5.3. Kiểu dữ liệu

**src/main/java/com/example/reactivetasks/Task.java**

~~~java
package com.example.reactivetasks;

public record Task(long id, String title, boolean done) {}
~~~

**src/main/java/com/example/reactivetasks/CreateTaskRequest.java**

~~~java
package com.example.reactivetasks;

public record CreateTaskRequest(String title) {}
~~~

Java record là kiểu bất biến gọn cho dữ liệu trao đổi JSON. Với hợp đồng public thật, tách DTO khỏi entity persistence và bổ sung validation có cấu trúc.

### 5.4. Service: tạo Publisher lười và cập nhật an toàn theo khóa

**src/main/java/com/example/reactivetasks/TaskService.java**

~~~java
package com.example.reactivetasks;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class TaskService {
    private final ConcurrentMap<Long, Task> tasks = new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong();

    public Mono<Task> create(CreateTaskRequest request) {
        return Mono.defer(() -> {
            if (request == null || request.title() == null ||
                    request.title().isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "title must not be blank"));
            }
            Task task = new Task(
                ids.incrementAndGet(), request.title().trim(), false);
            tasks.put(task.id(), task);
            return Mono.just(task);
        });
    }

    public Mono<Task> findById(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(tasks.get(id)));
    }

    public Flux<Task> findAll() {
        return Flux.defer(() ->
            Flux.fromIterable(new ArrayList<>(tasks.values()))
                .sort(Comparator.comparingLong(Task::id)));
    }

    public Mono<Task> complete(long id) {
        return Mono.defer(() ->
            Mono.justOrEmpty(tasks.computeIfPresent(id, (key, old) ->
                new Task(old.id(), old.title(), true))));
    }
}
~~~

- **Mono.defer** trì hoãn việc tạo/sửa dữ liệu đến lúc subscribe. Nếu subscribe lại Mono từ create(), thao tác tạo có thể diễn ra lại; không dùng retry mù cho POST.
- **ConcurrentHashMap.computeIfPresent** cập nhật cùng khóa theo cơ chế atomic của map, tránh đọc rồi ghi tách rời trong demo. **AtomicLong** cấp mã tăng dần trong một tiến trình.
- **findAll()** chụp snapshot và sort toàn bộ tập dữ liệu trong RAM; chỉ dùng với dữ liệu nhỏ. Trong hệ thống thật, phân trang/sắp xếp phải chuyển xuống database.
- Trả Mono.empty() khi không có id để tầng HTTP quyết định 404, thay vì gắn HTTP status vào repository. Ở mẫu này service dùng ResponseStatusException cho lỗi input để giảm số file; hệ thống lớn nên tách domain exception và error mapping.

### 5.5. Controller: framework quản lý subscription

**src/main/java/com/example/reactivetasks/TaskController.java**

~~~java
package com.example.reactivetasks;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<Task>> create(
            @RequestBody Mono<CreateTaskRequest> body) {
        return body.flatMap(service::create)
            .map(task -> ResponseEntity
                .created(URI.create("/api/tasks/" + task.id()))
                .body(task));
    }

    @GetMapping
    public Flux<Task> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Mono<Task> get(@PathVariable long id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "task not found")));
    }

    @PatchMapping("/{id}/complete")
    public Mono<Task> complete(@PathVariable long id) {
        return service.complete(id)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "task not found")));
    }
}
~~~

Controller không gọi subscribe(), block() hay CompletableFuture.join(). WebFlux subscribe vào Publisher khi xử lý request, truyền kết quả qua JSON encoder và xử lý HTTP 201/400/404. @RequestBody Mono<CreateTaskRequest> cho phép đọc body theo mô hình reactive; với request thiếu/malformed JSON, WebFlux thực hiện xử lý lỗi nhập liệu. Đối với API thật, nên thống nhất cấu trúc lỗi theo Problem Details, field validation và correlation ID.

### 5.6. Chạy và kiểm tra HTTP

Tại thư mục có pom.xml:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Trong terminal khác (ví dụ dùng curl trên Linux/macOS, hoặc curl.exe trên Windows):

~~~bash
curl -i -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Học Reactor"}'
curl http://localhost:8080/api/tasks/1
curl -X PATCH http://localhost:8080/api/tasks/1/complete
curl http://localhost:8080/api/tasks
curl -i http://localhost:8080/api/tasks/999
~~~

Khi bắt đầu với bộ nhớ rỗng, POST trả **201 Created**, Location: /api/tasks/1 và body:

~~~json
{"id":1,"title":"Học Reactor","done":false}
~~~

GET /api/tasks/1 trả bản ghi đó; PATCH /api/tasks/1/complete trả cùng id/title với done=true; GET danh sách trả một mảng JSON gồm task hiện có. GET /api/tasks/999 trả **404 Not Found**; lỗi title rỗng hoặc chỉ có khoảng trắng trả **400 Bad Request**. Header, thông báo lỗi và các trường lỗi bổ sung có thể khác theo cấu hình Spring; không nên khẳng định một JSON lỗi cố định.

## 6. Kiểm thử: từ tín hiệu đến HTTP

**src/test/java/com/example/reactivetasks/TaskControllerTest.java**

~~~java
package com.example.reactivetasks;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class TaskControllerTest {

    @Test
    void serviceEmitsOneCreatedTask() {
        TaskService service = new TaskService();

        StepVerifier.create(service.create(
                new CreateTaskRequest("Học Reactor")))
            .assertNext(task -> {
                assertEquals(1L, task.id());
                assertEquals("Học Reactor", task.title());
                assertFalse(task.done());
            })
            .verifyComplete();
    }

    @Test
    void httpCreatesAndReadsTask() {
        WebTestClient client = WebTestClient
            .bindToController(new TaskController(new TaskService()))
            .build();

        client.post().uri("/api/tasks")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateTaskRequest("Học Reactor"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .valueMatches("Location", "/api/tasks/[0-9]+")
            .expectBody()
            .jsonPath("$.title").isEqualTo("Học Reactor");

        client.get().uri("/api/tasks/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.done").isEqualTo(false);

        client.get().uri("/api/tasks/999")
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

**StepVerifier** kiểm tra onNext và onComplete cùng thứ tự; nếu chuỗi lỗi có thể dùng expectErrorMatches(...), nếu chỉ hoàn thành rỗng dùng verifyComplete() mà không expectNext. **WebTestClient.bindToController(...)** kiểm thử HTTP layer trong bộ nhớ, không cần mở cổng 8080. Khi tích hợp repository, nên thêm @SpringBootTest với database thật hoặc Testcontainers để kiểm tra transaction, migration và query; dùng mock ở cấp đơn vị khi thích hợp.

Các kịch bản quan trọng cần có trong test suite sản phẩm: 400 với input sai, 404 với bản ghi thiếu, 401/403 với quyền truy cập, lỗi dịch vụ phụ 5xx, timeout, hủy client, race condition cập nhật đồng thời, nhu cầu backpressure, giới hạn concurrency và giao dịch rollback. Dùng StepVerifier.withVirtualTime cho các luồng dùng timer/delay để không phải chờ thời gian thực; tạo Publisher bên trong supplier của withVirtualTime để VirtualTimeScheduler áp dụng đúng.

## 7. Tích hợp WebClient mà vẫn giữ luồng non-blocking

**WebClient** thay việc chặn bằng RestTemplate hoặc gọi .block() trong controller khi cần HTTP client bất đồng bộ. Fragment sau có thể đặt trong một bean đã inject WebClient.Builder; giả sử API task ở localhost:8080 đang chạy:

~~~java
WebClient client = builder.baseUrl("http://localhost:8080").build();

Mono<Task> task = client.get()
    .uri("/api/tasks/{id}", 1)
    .retrieve()
    .bodyToMono(Task.class)
    .timeout(Duration.ofSeconds(2));
~~~

Các biến builder và Task ở fragment này lấy từ ứng dụng hiện có; code có tính minh họa trong một phương thức, không phải một tệp Java độc lập. Mặc định retrieve() chuyển HTTP 4xx/5xx thành lỗi; nếu cần ánh xạ chi tiết, thêm onStatus(...) hoặc dùng exchangeToMono(...) và phải tiêu thụ/giải phóng body đúng cách. Cấu hình base URL, connection pool, timeout kết nối/đọc, TLS, chứng thực, proxy và giới hạn response theo môi trường. **Không gọi block() để lấy kết quả**, thay vào đó flatMap kết quả vào các Mono/Flux của service.

Khi kết hợp nhiều nguồn:
- Nguồn độc lập và đều phải có giá trị: dùng Mono.zip(a, b) nếu hai nguồn có thể chạy song song. Cần xử lý trường hợp một Mono rỗng trước khi zip.
- Cần gọi API B dựa trên output A: dùng a.flatMap(this::callB).
- Nhiều id: dùng Flux.fromIterable(ids).flatMap(this::callRemote, 8) để giới hạn đồng thời; nếu cần giữ thứ tự dùng concatMap hoặc flatMapSequential.
- Nếu retry, chỉ retry lỗi được xác định là transient, có giới hạn số lần, exponential backoff và ngân sách thời gian chung; POST/PATCH cần idempotency key hoặc thiết kế chống ghi trùng.
- Nếu service ngoài chậm, dùng bulkhead/rate limit/circuit breaker phù hợp và bảo vệ request budget; tự động retry vô hạn sẽ khuếch đại sự cố.

## 8. Tiến từ bộ nhớ sang persistence reactive

Mẫu InMemory TaskService là điểm xuất phát; để biến thành dịch vụ thực tế, tách cổng **TaskRepository** và thay map bằng database có driver reactive. Với PostgreSQL có thể chọn **Spring Data R2DBC** cùng driver R2DBC PostgreSQL:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-r2dbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Đây là **phần mở rộng** của pom.xml ở trên; riêng hai dependency này không tạo database hay migration. Cần cấp ConnectionFactory/R2DBC URL từ cấu hình an toàn, tạo schema qua migration, và đổi Task dạng HTTP DTO sang entity có @Table/@Id. Ví dụ interface:

~~~java
interface TaskRepository
        extends ReactiveCrudRepository<TaskEntity, Long> {
    Flux<TaskEntity> findByDone(boolean done);
}
~~~

Trong fragment này TaskEntity là entity persistence của ứng dụng thực tế; phải định nghĩa nó và import org.springframework.data.repository.reactive.ReactiveCrudRepository, reactor.core.publisher.Flux. Service sẽ gọi repository.save(...), findById(...), findAll() trả Mono/Flux trực tiếp, map entity → DTO và xử lý tính nhất quán nghiệp vụ. Đừng đưa nguyên Task record của ví dụ thành entity chỉ vì trùng tên; identity, migration, unique constraint, kiểu thời gian và audit field cần thiết kế rõ.

**Transaction reactive:** dùng @Transactional trên phương thức trả Publisher với ReactiveTransactionManager thích hợp, hoặc TransactionalOperator để bao nhiều bước ghi liên quan; transaction chạy trong **Reactor Context**, không dựa vào ThreadLocal như giao dịch đồng bộ. Không trộn JDBC/JPA đồng bộ với R2DBC trong cùng một reactive transaction rồi giả định rollback xuyên cả hai. Với tác vụ liên dịch vụ, dùng outbox/idempotency/compensation thay vì tưởng có giao dịch phân tán tự động.

**Phân trang và streaming:** không trả toàn bộ bảng vô hạn hoặc dùng collectList() trên tập dữ liệu lớn. Quy định page size, sort key ổn định, cursor/keyset pagination khi phù hợp; cân nhắc giới hạn kích thước JSON, buffer, cancel/timeout khi client ngắt. Cần đo áp lực connection pool và số query đang chạy, vì non-blocking không làm DB có thêm kết nối vô hạn.

## 9. Lỗi, validation, bảo mật và vận hành

### 9.1. Xác định hợp đồng lỗi

Thống nhất mã HTTP theo nhóm: **400** input không hợp lệ, **401** chưa xác thực, **403** thiếu quyền, **404** không tìm thấy, **409** xung đột version/unique key, **429** quá giới hạn, **5xx** lỗi hệ thống/phụ thuộc. Lỗi domain nên được ánh xạ tập trung bằng @RestControllerAdvice hoặc WebExceptionHandler; không trả stack trace, token, query bí mật ra response. Dùng optimistic locking/version hoặc unique constraint cho tranh chấp cập nhật, nhất là khi chuyển map sang DB.

Kiểm tra trường bắt buộc, độ dài, định dạng và giá trị hợp lệ ngay tại biên API; với Bean Validation, bổ sung starter validation tương ứng và các annotation jakarta.validation. Việc dùng Mono<T> không tự bật validation; phải chọn vị trí và cách kích hoạt phù hợp với model controller.

### 9.2. Bảo mật reactive

Dùng Spring Security hỗ trợ WebFlux, cấu hình **SecurityWebFilterChain**, xác thực OAuth2/JWT/session theo kiến trúc, phân quyền endpoint và resource, bảo vệ CSRF khi dùng cookie/session với browser. Truyền thông tin bảo mật và trace qua Reactor Context theo cơ chế framework, tránh trông cậy ThreadLocal/Servlet Filter. Thiết lập TLS và quản lý secrets ngoài source code. Với SSE/WebSocket, kiểm tra cả việc xác thực kết nối ban đầu lẫn giới hạn phiên và sự kiện gửi đi.

### 9.3. Quan sát và quản lý tài nguyên

Bật Actuator health/readiness/liveness, metrics cho tỉ lệ lỗi, p50/p95/p99 latency, inflight requests, event-loop blocking, connection pool, queue và timeout. Kết nối Micrometer tracing/OpenTelemetry khi cần quan sát xuyên dịch vụ; log có correlation ID và tránh ghi dữ liệu nhạy cảm. Đặt timeout ở HTTP client, DB, end-to-end và LB phù hợp nhau. Đo hiệu ứng của flatMap concurrency, buffer, payload size và giới hạn upstream dưới tải đồng thời; phải kiểm tra cả throughput, memory, CPU, GC và số kết nối.

Một pipeline non-blocking vẫn có thể quá tải khi:
- Nguồn nóng phát nhanh hơn downstream, tạo buffer lớn hoặc mất sự kiện.
- flatMap quá nhiều yêu cầu I/O cùng lúc khiến pool/DB cạn.
- collectList/sort/groupBy giữ trạng thái lớn hoặc không bao giờ hoàn thành.
- Chuyển sang boundedElastic rồi dồn toàn bộ công việc blocking vào hàng chờ.
- Bỏ qua cancellation, timeout và cleanup tài nguyên.
- Retry không giới hạn làm sự cố lan rộng.

Với dữ liệu luồng thực sự như sự kiện, đánh giá **Server-Sent Events (SSE)** hoặc WebSocket; quy định lifecycle, khả năng reconnect, event id, replay, chấp nhận mất dữ liệu và backpressure giữa từng hop. Không mặc định Flux bất kỳ tự trở thành stream hiệu quả nếu HTTP consumer hoặc proxy đang buffer.

## 10. Những lỗi phổ biến cần tự nhận diện

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Controller trả Mono nhưng request vẫn chậm nghẽn | Có JDBC/SDK blocking hoặc CPU nặng trên event-loop | Dùng driver reactive hoặc cô lập blocking tạm thời trên boundedElastic; đo profiler. |
| Ghi dữ liệu hai lần | Subscribe/retry lại cold publisher có side effect | Giữ một luồng subscription có chủ ý, thiết kế idempotency cho ghi. |
| Danh sách ra sai thứ tự | flatMap phát theo thời điểm hoàn thành | Dùng concatMap/flatMapSequential khi thứ tự là hợp đồng. |
| Không trả 404 khi thiếu id | Mono.empty() đi qua biên HTTP mà không ánh xạ | switchIfEmpty thành lỗi domain/ResponseStatusException thích hợp. |
| Mất dữ liệu hay tăng RAM khi stream | Nguồn nóng, buffer không giới hạn, collectList | Cấu hình backpressure, giới hạn buffer, phân trang hoặc streaming trực tiếp. |
| Test đợi mãi | Publisher vô hạn hoặc thiếu terminal signal | Kiểm tra take/timeout/cancel, dùng StepVerifier với kỳ vọng rõ ràng. |
| Mất context bảo mật/trace | Dựa vào ThreadLocal khi chuyển scheduler | Dùng Reactor Context và tích hợp context propagation chính thức. |
| Retry làm DB/remote quá tải | Retry bất kỳ lỗi nào, không backoff/budget | Chọn transient errors, giới hạn, backoff+jitter, circuit breaker. |
| Lỗi production khó truy dấu | Thiếu metric/trace và request budget | Thêm instrumentation, correlation ID, SLO và alert có ngưỡng. |

## 11. Checklist hoàn thiện một dịch vụ reactive

**Năng lực code:** Tất cả API business trả Mono/Flux; không có subscribe()/block()/Thread.sleep() trong request path; phân biệt error/empty; flatMap có giới hạn; cancellation và timeout rõ ràng. Test từng nhánh tín hiệu bằng StepVerifier.

**HTTP:** Hợp đồng REST rõ, status và JSON nhất quán; có WebTestClient kiểm tra success/4xx/5xx; xác thực và phân quyền; validation; error response không lộ bí mật; CORS/CSRF theo kiến trúc.

**Tích hợp:** WebClient tái sử dụng, connection pool và timeout có số đo; DB dùng R2DBC/reactive driver hoặc cô lập rõ chỗ còn blocking; migration và transaction được test; idempotency cho ghi và retry có kiểm soát.

**Sẵn sàng triển khai:** health/readiness, metric/tracing/log, shutdown graceful, cấu hình/secrets ngoài source, load test, giới hạn payload/stream/concurrency, dashboard và alert, rollback plan. Đo trước–sau với cùng workload; mục tiêu là khả năng phục vụ tải và độ ổn định, không phải dùng Mono/Flux ở mọi nơi.

## 12. Tài liệu tiếp tục học

1. Spring WebFlux reference: https://docs.spring.io/spring-framework/reference/web/webflux.html — cơ chế xử lý HTTP, annotated và functional endpoints.
2. Reactor reference: https://projectreactor.io/docs/core/release/reference/ — operators, backpressure, scheduler, errors và testing.
3. Spring Boot reactive web: https://docs.spring.io/spring-boot/reference/web/reactive.html — auto-configuration và triển khai.
4. Spring Boot 4.0.9 system requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html — Java và build tools.
5. Spring Data R2DBC repositories: https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html — kho dữ liệu reactive.

**Đường đi thực hành:** chạy được mẫu Tasks API → thêm validation và error format → thay in-memory service bằng R2DBC + migration → tích hợp một WebClient → bổ sung timeout/retry idempotent → viết StepVerifier/WebTestClient/Testcontainers → đo tải, bật security/observability và kiểm tra readiness trước rollout. Mỗi bước phải giữ nguyên các test đã có và bổ sung test cho hành vi mới.