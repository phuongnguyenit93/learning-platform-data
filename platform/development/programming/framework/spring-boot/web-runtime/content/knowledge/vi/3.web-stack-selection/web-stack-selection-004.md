# spring-boot-starter-webflux và mô hình reactive với Reactor

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `spring-boot-starter-webflux`, Spring WebFlux và Project Reactor trong một ứng dụng Spring Boot.
- Mô tả vòng đời Publisher, Subscriber, Subscription và cơ chế backpressure của Reactive Streams.
- Phân biệt `Mono<T>` và `Flux<T>`, biết cách kết hợp chúng bằng các operator thông dụng.
- Xử lý dữ liệu, lỗi, timeout và cancellation trong một pipeline reactive.
- Hiểu event loop, Scheduler và cách cô lập lời gọi blocking.
- Xây dựng REST endpoint reactive, gọi dịch vụ HTTP bằng WebClient và kiểm thử bằng StepVerifier/WebTestClient.
- Nhận diện trường hợp nên dùng WebFlux và những lỗi khiến ứng dụng reactive mất lợi ích non-blocking.

## 1. Ba thành phần cần phân biệt

Các tên gọi thường xuất hiện cùng nhau nhưng thuộc những lớp khác nhau:

| Thành phần | Vai trò |
|---|---|
| Spring Boot | Tự cấu hình ứng dụng dựa trên dependency và cấu hình; quản lý phiên bản thư viện qua dependency management. |
| Spring WebFlux | Web framework reactive của Spring: routing, controller/handler, request/response, codec và tích hợp server. |
| Project Reactor | Thư viện reactive triển khai Reactive Streams; cung cấp Publisher, Mono, Flux, operator và Scheduler. |
| Reactor Netty | Máy chủ HTTP non-blocking thường được Spring Boot chọn mặc định khi chạy WebFlux. |

`spring-boot-starter-webflux` là starter dependency để đưa stack WebFlux vào dự án Spring Boot. Starter này kéo các thư viện cần thiết cho Spring WebFlux và runtime reactive mặc định, bao gồm Reactor và Reactor Netty theo phiên bản Spring Boot đang quản lý.

Có thể hình dung các lớp như sau:

~~~text
Spring Boot application
        |
        +-- spring-boot-starter-webflux
                 |
                 +-- Spring WebFlux
                 |      +-- annotated controllers
                 |      +-- functional endpoints
                 |      +-- codecs / HTTP integration
                 |
                 +-- Project Reactor
                 |      +-- Mono<T>
                 |      +-- Flux<T>
                 |      +-- operators / Scheduler
                 |
                 +-- Reactor Netty (default server)
                        +-- non-blocking HTTP I/O
~~~

Spring WebFlux dùng Reactor làm API reactive chủ đạo. Reactor có thể được dùng độc lập ngoài tầng web, ví dụ trong service hoặc xử lý stream. Ngược lại, một ứng dụng WebFlux không chỉ là một tập hợp Mono/Flux: framework còn quản lý vòng đời request, subscription, ghi response và tích hợp server.

## 2. Thêm spring-boot-starter-webflux vào dự án

### Maven

Nếu dự án dùng Spring Boot parent hoặc BOM để quản lý phiên bản, không cần khai báo version riêng cho starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

### Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Không nên tự ghép các phiên bản Spring Framework, Reactor và Reactor Netty tùy ý. Hãy để Spring Boot dependency management chọn các phiên bản tương thích. Khi nâng cấp Spring Boot, kiểm tra release notes và dependency tree để phát hiện thay đổi tương thích.

### Cấu hình ứng dụng tối thiểu

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

Với WebFlux là web stack duy nhất, Spring Boot thường cấu hình ứng dụng theo reactive web application type và khởi động Reactor Netty. Cổng mặc định thường là 8080; có thể đổi trong `application.properties`:

~~~properties
server.port=8081
~~~

### Nếu dự án có cả starter MVC và WebFlux

Khi classpath có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot mặc định ưu tiên Spring MVC. Một lý do phổ biến là ứng dụng MVC có thể muốn dùng WebClient mà không muốn chuyển server sang WebFlux.

Nếu thật sự muốn chạy reactive web application trong tình huống này, có thể đặt rõ:

~~~properties
spring.main.web-application-type=reactive
~~~

Tuy nhiên, hãy kiểm tra dependency tree và loại bỏ starter MVC nếu ứng dụng không cần nó. Việc ép application type không làm cho thư viện blocking trở thành non-blocking. Chỉ thêm WebFlux để sử dụng WebClient cũng không bắt buộc chuyển toàn bộ server sang reactive.

Kiểm tra dependency bằng:

~~~bash
mvn dependency:tree
~~~

Hoặc với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

## 3. Reactive Streams: giao thức nền tảng

Reactive Streams định nghĩa giao thức truyền dữ liệu bất đồng bộ có cơ chế điều tiết lượng dữ liệu. Bốn thành phần cơ bản là:

- `Publisher<T>`: nguồn phát dữ liệu.
- `Subscriber<T>`: bên nhận dữ liệu.
- `Subscription`: liên kết giữa Publisher và Subscriber; cho phép yêu cầu số phần tử và hủy đăng ký.
- `Processor<T, R>`: vừa là Subscriber của kiểu T, vừa là Publisher của kiểu R.

Một luồng tín hiệu tiêu chuẩn diễn ra như sau:

~~~text
Subscriber                    Publisher
    |                             |
    |-------- subscribe() ------->|
    |<------ onSubscribe(s) ------|
    |                             |
    |-------- request(n) ------->|  Subscriber yêu cầu n phần tử
    |<--------- onNext(x) --------|  Có thể phát tối đa theo demand
    |<--------- onNext(y) --------|
    |                             |
    |<------- onComplete ---------|  Hoàn tất bình thường
    |              hoặc           |
    |<--------- onError ----------|  Kết thúc bằng lỗi
    |                             |
    |-------- cancel() --------->|  Hủy subscription khi cần
~~~

Các quy tắc cần nhớ:

1. Subscriber nhận `onSubscribe` trước các tín hiệu dữ liệu.
2. Subscriber gọi `request(n)` để báo lượng phần tử nó sẵn sàng nhận; n phải lớn hơn 0.
3. Publisher không được phát nhiều `onNext` hơn lượng demand đã được yêu cầu.
4. Một subscription kết thúc bằng `onComplete` hoặc `onError`; sau tín hiệu kết thúc không còn dữ liệu tiếp theo.
5. Subscriber có thể gọi `cancel()` để yêu cầu dừng luồng.

### Backpressure là gì?

Backpressure là cơ chế để bên tiêu thụ điều tiết tốc độ nhận dữ liệu. Ví dụ một nguồn có thể phát hàng triệu bản ghi, trong khi bước ghi xuống đích chỉ xử lý được một lượng nhỏ tại mỗi thời điểm. Demand cho phép subscriber yêu cầu lượng dữ liệu phù hợp với khả năng tiêu thụ.

Backpressure hữu ích với stream lớn, streaming HTTP và pipeline có tốc độ giữa các bước khác nhau. Tuy vậy:

- Backpressure không làm cho một API blocking trở thành non-blocking.
- Không phải mọi nguồn bên ngoài đều có thể điều tiết theo demand; adapter có thể phải buffer hoặc áp dụng chính sách riêng.
- Các operator có thể prefetch hoặc giữ buffer. Cần hiểu giới hạn bộ nhớ và hành vi của operator.
- `onBackpressureBuffer` có thể làm bộ nhớ tăng nếu producer liên tục nhanh hơn consumer; phải đặt giới hạn và chính sách xử lý tràn phù hợp.

## 4. Mono và Flux

Project Reactor cung cấp hai kiểu Publisher phổ biến nhất:

| Kiểu | Số phần tử | Ví dụ sử dụng |
|---|---:|---|
| `Mono<T>` | 0 hoặc 1 | Tìm một người dùng, lấy một đơn hàng, lưu một bản ghi hoàn tất. |
| `Flux<T>` | 0 đến N | Danh sách sản phẩm, sự kiện, dữ liệu streaming. |

Một số trường hợp quan trọng:

- `Mono.just(value)`: phát một giá trị đã có.
- `Mono.empty()`: hoàn tất mà không phát giá trị.
- `Mono.error(exception)`: kết thúc bằng lỗi.
- `Mono.justOrEmpty(nullableValue)`: phát giá trị nếu khác null, nếu null thì empty.
- `Flux.just(a, b, c)`: phát các giá trị đã cho.
- `Flux.fromIterable(items)`: phát các phần tử từ Iterable.
- `Flux.range(start, count)`: phát một dãy số hữu hạn.
- `Flux.empty()` và `Flux.error(exception)`: tương ứng với luồng rỗng và luồng lỗi.

Ví dụ:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<String> oneName = Mono.just("An");

Flux<Integer> numbers = Flux.range(1, 5);

Mono<String> noName = Mono.empty();

Flux<String> names = Flux.just("An", "Binh", "Chi");
~~~

`Mono<T>` không đồng nghĩa với một Future đã chạy xong. Nó là Publisher mô tả kết quả có thể được phát trong tương lai. Tương tự, `Flux<T>` không nhất thiết giữ sẵn toàn bộ danh sách trong bộ nhớ; nó có thể phát dữ liệu theo thời gian.

### Assembly và subscription

Khi gọi các operator, bạn thường đang xây dựng pipeline (assembly). Công việc thực sự thường bắt đầu khi có subscription.

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> {
    System.out.println("Tạo giá trị");
    return 10;
}).map(value -> value * 2);

// Chưa có subscriber thì supplier chưa được gọi.
pipeline.subscribe(value -> System.out.println("Kết quả: " + value));
~~~

Output:

~~~text
Tạo giá trị
Kết quả: 20
~~~

Trong ứng dụng WebFlux, framework sẽ subscribe vào Publisher controller trả về để xử lý request và response. Vì vậy, controller thường chỉ cần trả về Mono hoặc Flux; không tự gọi `subscribe()` để tạo một luồng độc lập.

Một lưu ý về thời điểm tạo dữ liệu:

- `Mono.just(value)` nắm giữ giá trị tại thời điểm assembly và phát lại giá trị đó cho subscriber.
- `Mono.fromSupplier(...)` gọi supplier khi có subscription.
- `Mono.defer(...)` tạo một Publisher mới cho từng subscription, hữu ích khi cần tính toán hoặc đọc trạng thái tại thời điểm subscribe.

## 5. Các operator thường dùng

Operator biến đổi Publisher thành Publisher khác. Hãy đọc kiểu đầu vào, kiểu đầu ra và cách operator xử lý empty/error trước khi ghép pipeline.

### map: biến đổi đồng bộ từng phần tử

~~~java
Mono<Integer> doubled = Mono.just(5)
    .map(number -> number * 2);
~~~

Kết quả là `Mono<Integer>` phát ra 10. Dùng `map` khi phép biến đổi trả về một giá trị thông thường, không phải Publisher.

### flatMap: nối một thao tác reactive khác

~~~java
Mono<Order> order = orderRepository.findById(orderId);

Mono<Customer> customer = order
    .flatMap(foundOrder -> customerRepository.findById(foundOrder.customerId()));
~~~

`flatMap` nhận một giá trị rồi gọi hàm trả về Publisher, sau đó nối kết quả vào pipeline. Đây là operator quan trọng khi bước tiếp theo cũng là thao tác bất đồng bộ.

### filter: giữ lại phần tử thỏa điều kiện

~~~java
Flux<Integer> evenNumbers = Flux.range(1, 6)
    .filter(number -> number % 2 == 0);
~~~

Kết quả phát ra 2, 4, 6.

### concatMap, flatMap và flatMapSequential

Khi mỗi phần tử cần gọi một Publisher khác:

- `flatMap` cho phép các inner Publisher chạy đồng thời; thứ tự phát kết quả không được đảm bảo.
- `concatMap` xử lý inner Publisher tuần tự và giữ thứ tự nguồn.
- `flatMapSequential` có thể subscribe đồng thời nhưng giữ thứ tự phát kết quả theo thứ tự nguồn; có thể phải buffer kết quả đến sớm.

Chọn theo yêu cầu thứ tự và mức song song, không thay thế chúng cho nhau một cách máy móc.

### zip: kết hợp nhiều kết quả

~~~java
Mono<Product> product = productRepository.findById(id);
Mono<Stock> stock = stockRepository.findStock(id);

Mono<ProductView> view = Mono.zip(product, stock)
    .map(tuple -> new ProductView(tuple.getT1(), tuple.getT2()));
~~~

`zip` đợi mỗi nguồn phát giá trị để tạo tuple. Nếu một nguồn hoàn tất rỗng, kết quả kết hợp có thể hoàn tất rỗng. Nếu một nguồn lỗi, lỗi được truyền xuống theo quy tắc của operator.

### defaultIfEmpty và switchIfEmpty

`Mono.empty()` không phải lỗi. Dùng `defaultIfEmpty` để thay bằng giá trị mặc định hoặc `switchIfEmpty` để chuyển sang Publisher khác:

~~~java
Mono<Product> product = productRepository.findById(id)
    .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
~~~

### take, collectList và limitRate

- `take(n)`: chỉ nhận tối đa n phần tử rồi hoàn tất.
- `collectList()`: gom các phần tử thành một List trong Mono; phù hợp với tập dữ liệu có giới hạn.
- `limitRate(n)`: điều chỉnh cách yêu cầu demand upstream theo nhóm; không phải giới hạn tổng số phần tử như `take(n)`.

Không dùng `collectList()` cho stream không giới hạn hoặc tập dữ liệu rất lớn nếu không có lý do rõ ràng, vì toàn bộ kết quả sẽ được giữ trong bộ nhớ.

## 6. Xử lý lỗi trong Reactor

Trong Reactive Streams, lỗi là một tín hiệu kết thúc của Publisher. Khi một operator phát sinh exception, pipeline chuyển sang nhánh lỗi và các bước xử lý dữ liệu thông thường phía sau sẽ không tiếp tục như khi thành công.

Các operator thường gặp:

| Operator | Công dụng |
|---|---|
| `onErrorReturn(value)` | Thay lỗi bằng một giá trị dự phòng cố định. |
| `onErrorResume(error -> publisher)` | Chuyển sang Publisher dự phòng, có thể dựa vào loại lỗi. |
| `onErrorMap(error -> newError)` | Biến đổi exception sang loại lỗi khác. |
| `doOnError(...)` | Thực hiện side effect như ghi log; không xử lý hay khôi phục lỗi. |
| `retry(n)` / `retryWhen(...)` | Đăng ký lại nguồn khi gặp lỗi theo chính sách retry. |

Ví dụ fallback có điều kiện:

~~~java
Mono<Product> result = productService.findById(id)
    .onErrorResume(TimeoutException.class,
        error -> cacheService.findById(id));
~~~

Ví dụ chuyển loại lỗi:

~~~java
Mono<Product> result = productService.findById(id)
    .onErrorMap(error ->
        new ProductLookupException("Không thể tra cứu sản phẩm", error));
~~~

Ví dụ retry có backoff:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<Response> response = remoteClient.call()
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200)));
~~~

Retry có thể lặp lại side effect. Chỉ retry thao tác có thể lặp an toàn hoặc đã có idempotency key/cơ chế chống tạo giao dịch trùng. Không nên retry mọi exception; lỗi validation hoặc dữ liệu không tồn tại thường không tự hết khi thử lại.

Trong WebFlux, có thể xử lý lỗi HTTP tập trung bằng `@ExceptionHandler`, `@ControllerAdvice` hoặc cơ chế error handling của ứng dụng. Đừng biến mọi lỗi thành HTTP 200 với một body báo lỗi; hãy giữ status code phản ánh đúng kết quả.

## 7. Cancellation và vòng đời của request

Cancellation xảy ra khi subscriber không còn cần dữ liệu. Ví dụ client đóng kết nối trước khi server phát hết stream. Framework có thể hủy subscription để các bước phía sau dừng công việc nếu nguồn và operator hỗ trợ cancellation.

Điều cần lưu ý:

- Cancellation không đảm bảo có thể thu hồi một thao tác I/O bên ngoài đã gửi đi.
- Một side effect đã được thực hiện không tự động được rollback khi client ngắt kết nối.
- Khi xử lý stream dài, nên để cancellation lan truyền tự nhiên qua pipeline.
- Tránh tự tạo subscription nền trong controller vì nó tách công việc khỏi vòng đời request và làm khó quản lý lỗi/cancellation.

Có thể quan sát lifecycle bằng các hook như `doOnSubscribe`, `doOnNext`, `doOnError`, `doOnCancel` và `doFinally`. Chỉ dùng các hook này cho side effect quan sát như metric/log; không đặt nghiệp vụ chính vào đó nếu nghiệp vụ cần tạo ra giá trị trả về.

## 8. Thread, event loop và Scheduler

### Event loop trong WebFlux

Khi dùng Reactor Netty, WebFlux thường xử lý I/O trên nhóm event-loop thread. Một event-loop thread có thể phục vụ nhiều kết nối vì nó không cần chờ đồng bộ cho từng thao tác I/O. Khi socket có dữ liệu hoặc thao tác non-blocking hoàn tất, callback tương ứng được đưa vào xử lý.

Mô hình này hiệu quả khi code nhanh chóng trả quyền điều khiển cho event loop và các dependency cũng hỗ trợ non-blocking. Nếu event loop bị giữ bởi một lời gọi blocking, các kết nối khác có thể bị ảnh hưởng.

### Scheduler trong Reactor

Scheduler quyết định nơi một phần pipeline thực thi. Những scheduler thường gặp:

- `Schedulers.parallel()`: nhóm thread dành cho tác vụ CPU-bound, phù hợp với công việc tính toán ngắn và không blocking.
- `Schedulers.boundedElastic()`: nhóm thread có giới hạn dành cho công việc blocking hoặc tác vụ có thể chờ lâu.
- `Schedulers.single()`: một thread tuần tự dùng chung cho các tác vụ cần chạy trên một thread.
- `Schedulers.immediate()`: thực thi ngay trên thread hiện tại.

Không nên chuyển mọi operator sang scheduler khác mà không có lý do. Việc đổi scheduler có chi phí chuyển thread và có thể làm mất lợi ích của event loop.

### subscribeOn và publishOn

- `subscribeOn(scheduler)` ảnh hưởng đến quá trình subscribe và nguồn upstream; thường dùng để đưa một nguồn blocking sang scheduler phù hợp.
- `publishOn(scheduler)` chuyển việc thực thi các operator downstream kể từ vị trí đó sang scheduler đã chọn.

Ví dụ cô lập API blocking:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<User> user = Mono.fromCallable(() -> legacyJdbcDao.findUser(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đoạn code tránh chạy JDBC trực tiếp trên event loop. Tuy nhiên, JDBC vẫn blocking và vẫn chiếm một thread trong lúc chờ. Nếu có driver reactive tương ứng, nên cân nhắc dùng driver đó để có non-blocking I/O thực sự.

### Những điều cần tránh

- Gọi `Thread.sleep()`, JDBC/JPA blocking hoặc HTTP client blocking trực tiếp trên event loop.
- Gọi `block()` trong controller hoặc trong pipeline đang chạy trên non-blocking thread.
- Gọi `subscribe()` thủ công trong controller chỉ để lấy kết quả.
- Dùng `boundedElastic` như nơi chứa mọi công việc mà không đo tải và không giới hạn nguồn blocking.
- Giả định các operator luôn chạy trên cùng một thread hoặc luôn chạy trên một thread cụ thể.

## 9. Xây dựng REST API với WebFlux

Ví dụ sau minh họa một REST API nhỏ dùng Java 17+, Spring Boot và dữ liệu trong bộ nhớ. Đây là các file mã nguồn của một ứng dụng Spring Boot; dependency `spring-boot-starter-webflux` được khai báo như phần trên.

### DTO

~~~java
package com.example.reactive;

public record Product(long id, String name) {
}
~~~

### Service trả về Publisher

~~~java
package com.example.reactive;

import java.util.Map;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final Map<Long, Product> products = Map.of(
        1L, new Product(1L, "Keyboard"),
        2L, new Product(2L, "Mouse"),
        3L, new Product(3L, "Monitor")
    );

    public Mono<Product> findById(long id) {
        return Mono.justOrEmpty(products.get(id));
    }

    public Flux<Product> findAll() {
        return Flux.fromIterable(products.values());
    }
}
~~~

### Controller

~~~java
package com.example.reactive;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> findById(@PathVariable long id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping
    public Flux<Product> findAll() {
        return service.findAll();
    }
}
~~~

Khi chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gọi API:

~~~bash
curl http://localhost:8080/api/products/1
curl http://localhost:8080/api/products/99
curl http://localhost:8080/api/products
~~~

Kết quả JSON cho sản phẩm có id 1:

~~~json
{"id":1,"name":"Keyboard"}
~~~

Với id 99, endpoint trả HTTP 404 vì `Mono.empty()` được chuyển thành `ResponseEntity.notFound()`. Endpoint danh sách trả về một Flux; WebFlux ghi các phần tử thành response theo cơ chế HTTP message writer phù hợp.

Ví dụ này dùng Map trong bộ nhớ nên thao tác tra cứu rất nhanh và không minh họa I/O bất đồng bộ thật. Trong ứng dụng thực tế, hãy dùng repository/driver phù hợp với mô hình dữ liệu và tải của hệ thống.

## 10. Gọi dịch vụ HTTP bằng WebClient

WebClient là HTTP client reactive của Spring. Nó có thể dùng trong ứng dụng WebFlux và cũng có thể dùng trong ứng dụng Spring MVC. WebClient hỗ trợ non-blocking I/O, streaming và trả về Mono/Flux.

Ví dụ một client gọi dịch vụ catalog:

~~~java
package com.example.reactive;

import java.time.Duration;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://catalog.example")
            .build();
    }

    public Mono<CatalogItem> findById(String id) {
        return webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(CatalogItem.class)
            .timeout(Duration.ofSeconds(3));
    }
}
~~~

`CatalogItem` là DTO của dịch vụ catalog. `retrieve()` chuyển response thành body; status 4xx/5xx mặc định được biểu diễn bằng lỗi WebClient response. Có thể dùng `onStatus(...)` để ánh xạ status hoặc body lỗi sang exception nghiệp vụ riêng.

Ví dụ tích hợp client vào controller/service:

~~~java
public Mono<CatalogItem> loadCatalogItem(String id) {
    return catalogClient.findById(id)
        .onErrorResume(error -> fallbackCatalog.findById(id));
}
~~~

Trong code thực tế, fallback nên chọn theo loại lỗi. Không nên fallback cho mọi lỗi nếu điều đó che giấu lỗi xác thực, lỗi lập trình hoặc dữ liệu không hợp lệ.

Không gọi `block()` chỉ để lấy kết quả WebClient trong request path. Hãy trả Mono/Flux để pipeline tiếp tục bất đồng bộ. Nếu một ứng dụng MVC cần gọi WebClient, controller MVC vẫn có thể dùng kiểu trả về phù hợp của MVC; điều đó không tự chuyển máy chủ sang WebFlux.

## 11. Streaming và functional endpoints

WebFlux hỗ trợ streaming vì controller có thể trả Flux và framework ghi dữ liệu theo từng phần tử khi phù hợp với media type/protocol.

Một số trường hợp sử dụng:

- Server-Sent Events (SSE) để gửi sự kiện từ server đến trình duyệt.
- Streaming dữ liệu lớn thay vì gom toàn bộ vào một List.
- Proxy dữ liệu giữa các dịch vụ.
- Luồng sự kiện hoặc cập nhật trạng thái theo thời gian.

Ví dụ endpoint SSE:

~~~java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventController {

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> "event-" + sequence);
    }
}
~~~

Trong ví dụ, mỗi giây phát một chuỗi sự kiện. Với kết nối thực tế, cần xem xét giới hạn số kết nối, timeout, heartbeat, xác thực, cancellation và khả năng scale của nguồn sự kiện. Không dùng stream vô hạn nếu client hoặc hạ tầng không có chính sách kết thúc và quản lý tài nguyên phù hợp.

Ngoài annotation controller, WebFlux còn hỗ trợ functional endpoints với `RouterFunction` và `HandlerFunction`. Cách này hữu ích khi muốn định nghĩa route và handler bằng Java DSL; cả hai phong cách đều dùng reactive type và chung nền tảng runtime WebFlux.

## 12. Kiểm thử pipeline và HTTP endpoint

### StepVerifier

StepVerifier thuộc Reactor Test, giúp kiểm tra tín hiệu của Publisher theo thứ tự mà không cần tự subscribe và chờ bằng tay.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class NumberServiceTest {

    @Test
    void emitsEvenNumbers() {
        Flux<Integer> numbers = Flux.range(1, 6)
            .filter(number -> number % 2 == 0);

        StepVerifier.create(numbers)
            .expectNext(2, 4, 6)
            .verifyComplete();
    }
}
~~~

StepVerifier có thể kiểm tra empty, error, demand, cancellation và các luồng phụ thuộc thời gian. Với test dùng timer/delay, có thể dùng virtual time để kiểm tra nhanh mà không phải đợi thời gian thực.

### WebTestClient

WebTestClient kiểm thử endpoint WebFlux qua HTTP mà không cần khởi chạy server thật, hoặc có thể bind tới server đang chạy trong integration test. Ví dụ kiểm tra endpoint:

~~~java
webTestClient.get()
    .uri("/api/products/1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.name").isEqualTo("Keyboard");
~~~

Trong test tích hợp, có thể dùng `@SpringBootTest` kết hợp cấu hình WebTestClient phù hợp với cách khởi chạy ứng dụng. Kiểm thử cả status, header, body, lỗi, timeout và trường hợp client ngắt kết nối khi endpoint streaming.

## 13. Lỗi thường gặp khi mới dùng Reactor

### Dùng map cho hàm trả về Mono/Flux

Nếu hàm bên trong trả Publisher, dùng `flatMap` hoặc `concatMap` tùy yêu cầu thứ tự. Dùng `map` sẽ tạo Publisher lồng nhau như `Mono<Mono<T>>`.

### Gọi block() để lấy giá trị

`block()` biến thao tác reactive thành chờ đồng bộ. Trong request path của WebFlux, điều này có thể chặn event loop và làm giảm khả năng phục vụ đồng thời. Hãy nối Publisher bằng operator và trả nó về framework.

### Gọi subscribe() trong controller

Tự subscribe tạo một luồng tách khỏi vòng đời request. Framework không còn quản lý kết quả đó như response của request; lỗi, cancellation và thời điểm hoàn tất trở nên khó kiểm soát. Hãy trả Publisher từ controller.

### Đặt JDBC/JPA trên event loop

Mono/Flux không làm thư viện blocking trở thành non-blocking. Dùng driver reactive nếu phù hợp hoặc cô lập đoạn blocking trên boundedElastic trong thời gian chuyển đổi.

### Nhầm empty với error

`Mono.empty()` là hoàn tất bình thường nhưng không có phần tử. Nếu cần báo không tìm thấy, dùng `switchIfEmpty` để phát lỗi hoặc trả response 404 theo ý nghĩa API.

### Dùng flatMap khi cần thứ tự

`flatMap` có thể phát kết quả không theo thứ tự nguồn. Dùng `concatMap` khi cần tuần tự; dùng `flatMapSequential` khi cần chạy song song nhưng giữ thứ tự phát kết quả.

### Gom stream không giới hạn vào List

`collectList()` giữ mọi phần tử trong bộ nhớ. Với dữ liệu lớn hoặc vô hạn, hãy xử lý theo từng phần tử, phân trang hoặc dùng streaming/backpressure.

### Retry không kiểm soát

Retry có thể lặp side effect, tăng tải lên dịch vụ đang lỗi và tạo hiệu ứng dây chuyền. Đặt số lần thử, backoff, timeout, phân loại lỗi và bảo đảm idempotency.

### Dùng ThreadLocal như trong mô hình thread-per-request

Reactive pipeline có thể chuyển thread qua Scheduler. Không giả định ThreadLocal luôn đi theo request. Với dữ liệu theo subscription, cân nhắc Reactor Context và các tích hợp context propagation phù hợp.

## 14. Khi nào nên chọn WebFlux?

WebFlux phù hợp khi hệ thống có nhiều I/O đồng thời, cần streaming, cần phối hợp nhiều dịch vụ và các thư viện quan trọng đều hỗ trợ non-blocking. Mô hình event loop có thể phục vụ nhiều kết nối mà không giữ một worker thread riêng trong suốt thời gian chờ I/O.

Spring MVC thường là lựa chọn đơn giản và hiệu quả khi ứng dụng dựa nhiều vào JDBC/JPA hoặc thư viện blocking, luồng nghiệp vụ chủ yếu đồng bộ và đội ngũ đã quen với Servlet stack. MVC cũng hỗ trợ async request và có thể sử dụng WebClient.

Trước khi chọn WebFlux, hãy đánh giá:

1. Workload chủ yếu chờ I/O hay tiêu tốn CPU?
2. Database driver và HTTP client có hỗ trợ non-blocking không?
3. Có thư viện blocking nào chạy trong request path không?
4. Hệ thống có nhu cầu streaming hoặc số lượng kết nối đồng thời lớn không?
5. Đội ngũ có thể vận hành, debug và kiểm thử Reactor pipeline không?
6. Benchmark có phản ánh latency, throughput, memory và tải downstream thực tế không?

Reactive không tự động nhanh hơn imperative. Hiệu quả phụ thuộc vào workload, dependency, cách thiết kế pipeline, giới hạn tài nguyên và khả năng vận hành. Một ứng dụng WebFlux chứa nhiều blocking call có thể khó hiểu hơn MVC mà không nhận được lợi ích tương ứng.

## 15. Câu hỏi tự kiểm tra

1. `spring-boot-starter-webflux`, Spring WebFlux và Project Reactor khác nhau ở vai trò nào?
2. Publisher, Subscriber và Subscription phối hợp ra sao để truyền dữ liệu?
3. `Mono<T>` khác `Flux<T>` như thế nào? `Mono.empty()` có phải lỗi không?
4. Vì sao controller WebFlux nên trả Publisher thay vì tự gọi `subscribe()`?
5. Khi nào dùng `map`, `flatMap`, `concatMap` và `flatMapSequential`?
6. Backpressure điều tiết điều gì? Nó có tự biến JDBC thành non-blocking không?
7. Khác biệt chính giữa `subscribeOn` và `publishOn` là gì?
8. Vì sao không nên gọi `block()` trên event-loop?
9. Nếu ứng dụng chỉ cần WebClient nhưng có cả starter MVC và WebFlux, Spring Boot thường chọn web stack nào?
10. Khi nào nên chọn WebFlux thay cho Spring MVC?

### Đáp án gợi ý

1. Starter là dependency bundle; WebFlux là web framework; Reactor là thư viện reactive cung cấp Mono, Flux, operator và Scheduler.
2. Subscriber đăng ký với Publisher, nhận Subscription rồi gọi request(n); Publisher phát onNext theo demand và kết thúc bằng onComplete hoặc onError. Subscriber có thể cancel.
3. Mono phát 0 hoặc 1 phần tử; Flux phát 0 đến nhiều phần tử. Mono.empty hoàn tất bình thường mà không phát giá trị.
4. Framework cần quản lý subscription và gắn kết quả với vòng đời HTTP request, bao gồm lỗi và cancellation.
5. map cho phép biến đổi đồng bộ; flatMap nối Publisher; concatMap xử lý tuần tự và giữ thứ tự; flatMapSequential cho phép chạy inner Publisher đồng thời nhưng giữ thứ tự phát kết quả.
6. Backpressure điều tiết lượng dữ liệu subscriber yêu cầu. JDBC vẫn blocking dù được bọc trong Mono.
7. subscribeOn ảnh hưởng việc subscribe/nguồn upstream; publishOn chuyển thực thi downstream kể từ vị trí đặt operator.
8. block giữ thread chờ kết quả, có thể làm event loop không xử lý được các kết nối khác.
9. Spring Boot mặc định ưu tiên MVC khi cả hai starter cùng có mặt; WebClient vẫn có thể dùng trong MVC.
10. Khi workload có nhiều I/O đồng thời hoặc streaming và phần lớn dependency hỗ trợ non-blocking, đồng thời đội ngũ có khả năng vận hành reactive stack.

## 16. Tài liệu tham khảo chính thức

- [Spring Boot: Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html) — starter, auto-configuration và reactive web runtime.
- [Spring Framework: Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) — kiến trúc WebFlux, controller, functional endpoints và runtime.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/index.html) — Mono, Flux, operator, Scheduler, error handling và testing.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — giao thức Publisher/Subscriber và backpressure.
- [Spring WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html) — HTTP client reactive của Spring.
- [Spring WebFlux Testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — kiểm thử HTTP với WebTestClient.
