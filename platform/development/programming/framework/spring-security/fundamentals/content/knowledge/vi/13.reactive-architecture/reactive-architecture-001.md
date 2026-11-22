# WebFlux, Mono, Flux và mô hình thực thi không chặn luồng

> **Bối cảnh:** Spring Security – fundamentals → Kiến trúc reactive. Bài này giải thích nền tảng Reactor/Spring WebFlux và liên hệ trực tiếp với cách Spring Security xử lý xác thực, phân quyền trên reactive stack. Ví dụ sử dụng Java 17+ và Spring Boot có Spring WebFlux, Spring Security.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt Spring MVC (Servlet) với Spring WebFlux về mô hình xử lý I/O và luồng.
2. Giải thích `Publisher`, `Subscriber`, `Subscription`, tín hiệu hoàn thành/lỗi và backpressure.
3. Chọn đúng `Mono<T>` (0 hoặc 1 giá trị) và `Flux<T>` (0 đến nhiều giá trị); ghép các bước xử lý bằng Reactor operators.
4. Nhận diện thao tác blocking trên event loop, cách tích hợp API bất đồng bộ và cách cô lập một API blocking bất khả kháng.
5. Hiểu `WebFilter`, `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveSecurityContextHolder` trong Spring Security.
6. Tạo và chạy ứng dụng WebFlux nhỏ, kiểm chứng endpoint công khai, endpoint cần đăng nhập và stream dữ liệu.

## 2. WebFlux là gì? Vì sao có mô hình reactive?

**Spring WebFlux** là web framework thuộc reactive stack của Spring Framework. Nó nhận/trả dữ liệu theo contract Reactive Streams và được thiết kế cho I/O bất đồng bộ, không chặn luồng. WebFlux hỗ trợ controller dựa trên annotation và functional endpoint; Spring Boot thường chạy WebFlux trên Reactor Netty, đồng thời WebFlux cũng có thể chạy trên những server được hỗ trợ khác.

So sánh ở mức tư duy:

| Góc nhìn | Spring MVC / Servlet thông dụng | Spring WebFlux / reactive |
| --- | --- | --- |
| Xử lý request | Thường có worker thread phục vụ từng request đang thực thi | Event-loop worker xử lý các sự kiện I/O của nhiều kết nối |
| Khi chờ kết quả I/O | Có thể giữ thread chờ trong lời gọi đồng bộ | Đăng ký bước tiếp theo và giải phóng thread để xử lý công việc khác |
| Kiểu trả về thường gặp | Đối tượng, `ResponseEntity<T>` (cũng hỗ trợ bất đồng bộ) | `Mono<T>`, `Flux<T>`, `Mono<Void>`, `ResponseEntity<Mono<T>>`... |
| Điều tiết nguồn dữ liệu | Thường dựa vào luồng gọi đồng bộ/bộ đệm | Reactive Streams có cơ chế `request(n)` để biểu đạt nhu cầu |
| API tích hợp phù hợp | JDBC, client đồng bộ nếu tải vừa phải | WebClient, R2DBC, driver reactive và API trả `Publisher` |
| Spring Security | Servlet `Filter`, `SecurityFilterChain`, `HttpSecurity` | `WebFilter`, `SecurityWebFilterChain`, `ServerHttpSecurity` |

Đừng đồng nhất **reactive** với "nhanh hơn trong mọi trường hợp". Lợi ích thường rõ khi ứng dụng phải chờ nhiều kết nối I/O, cần xử lý nhiều request đồng thời với lượng thread hạn chế hoặc stream dữ liệu. Với công việc CPU nặng, cơ sở dữ liệu chỉ có JDBC, hoặc ứng dụng CRUD đơn giản, WebFlux không mặc nhiên cải thiện độ trễ. Kiến trúc chỉ thực sự tránh chặn luồng khi các thao tác I/O chủ chốt trong pipeline cũng là non-blocking.

**Ghi nhớ:** `Mono`/`Flux` là mô hình biểu diễn dữ liệu và tín hiệu; chỉ trả về `Mono` không tự biến một lời gọi JDBC hay `Thread.sleep` thành non-blocking.

## 3. Cơ chế Reactive Streams: dữ liệu và tín hiệu

Reactive Streams mô tả cách một bên phát dữ liệu và một bên nhận dữ liệu trao đổi với nhau:

- `Publisher<T>`: nguồn có thể phát dữ liệu kiểu `T`. `Mono` và `Flux` là các implementation quan trọng của Reactor.
- `Subscriber<T>`: bên đăng ký nhận dữ liệu và tín hiệu.
- `Subscription`: quan hệ giữa subscriber và publisher; subscriber có thể gọi `request(n)` để yêu cầu thêm tối đa `n` phần tử và `cancel()` để hủy.
- `onSubscribe`: tín hiệu cấp `Subscription`; `onNext`: phát một phần tử; `onComplete`: kết thúc bình thường; `onError`: kết thúc do lỗi.

Trình tự khái quát:

~~~text
Subscriber                 Publisher
    | ------ subscribe() ----> |
    | <---- onSubscribe(s) --- |
    | ------ request(2) -----> |
    | <------ onNext(A) ------ |
    | <------ onNext(B) ------ |
    | ------ request(1) -----> |
    | <------ onNext(C) ------ |
    | <----- onComplete() ---- |
~~~

Trong một subscription hợp lệ, `onComplete` và `onError` là hai trạng thái kết thúc loại trừ nhau; sau tín hiệu kết thúc không có `onNext` mới. Subscriber có thể hủy trước khi hoàn thành. Publisher tuân thủ backpressure sẽ không phát `onNext` vượt quá nhu cầu đã được yêu cầu.

**Backpressure** là cách consumer báo tốc độ tiếp nhận cho producer để tránh bị ngập dữ liệu. Nếu nguồn bên ngoài không thể giảm tốc (ví dụ nguồn hot phát không kiểm soát), hệ thống vẫn cần chính sách buffer/drop/error phù hợp; Reactive Streams không tự tạo dung lượng bộ nhớ vô hạn và không bảo đảm mọi giao thức mạng đều truyền `request(n)` một-một đến tận nguồn.

Trong WebFlux, Spring thường là bên đăng ký subscription cho pipeline mà controller trả về; nó dùng các tín hiệu để ghi HTTP response. Vì vậy **không tự gọi `subscribe()` trong controller** chỉ để kích hoạt pipeline: việc làm đó tạo subscription khác, tách luồng dữ liệu/lỗi khỏi vòng đời HTTP, và có thể làm mất ngữ cảnh bảo mật.

## 4. Mono và Flux: chọn kiểu nào?

| Kiểu | Số phần tử mỗi subscription | Ví dụ |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Lấy một người dùng, gọi API trả một JSON, kiểm tra token |
| `Mono<Void>` | Không có giá trị `T`; chỉ báo hoàn thành/lỗi | Xóa tài nguyên, ghi log bất đồng bộ, hoàn tất response |
| `Flux<T>` | 0 đến nhiều | Danh sách sản phẩm, thông báo sự kiện, SSE, dòng bản ghi |

Ví dụ các nguồn Reactor:

~~~java
Mono<String> one = Mono.just("Java");
Mono<String> absent = Mono.empty();
Mono<String> maybe = Mono.justOrEmpty((String) null);
Mono<String> failed = Mono.error(new IllegalStateException("unavailable"));

Flux<Integer> many = Flux.just(1, 2, 3);
Flux<Integer> sequence = Flux.range(1, 5); // 1,2,3,4,5
Flux<Integer> none = Flux.empty();
~~~

Các dòng trên là **đoạn minh họa** dùng `reactor.core.publisher.Mono` và `Flux`, không phải chương trình Java độc lập. Chúng cho thấy `Mono.empty()` là luồng hoàn thành không có phần tử, khác với `Mono.just(null)`: Reactor không cho phép phần tử `null`, nên `Mono.just(null)` gây lỗi.

`Mono<List<T>>` và `Flux<T>` cũng không giống nhau: kiểu đầu phát **một** danh sách như một phần tử, kiểu sau phát **từng** phần tử. `collectList()` có thể đổi `Flux<T>` hữu hạn thành `Mono<List<T>>`, nhưng phải gom toàn bộ dữ liệu trong bộ nhớ. Với luồng rất lớn hoặc vô hạn, đừng gom thành danh sách.

### Lazy, cold, hot và thời điểm chạy

Phần lớn `Mono`/`Flux` từ các factory thông thường là **cold**: mỗi subscription khởi tạo quá trình phát riêng. Ví dụ `Mono.fromSupplier(...)` hoặc `Mono.defer(...)` chỉ thực hiện logic nguồn khi được subscribe. `Mono.just(value)` đã có `value` tại lúc dựng publisher, dù tín hiệu phát cho subscriber vẫn tới sau khi subscribe. Một publisher **hot** (như nguồn được chia sẻ qua `Sinks.Many`) có thể phát dữ liệu độc lập với một subscriber cụ thể; người đăng ký muộn có thể bỏ lỡ sự kiện nếu không có cơ chế replay.

~~~java
AtomicInteger counter = new AtomicInteger();
Mono<Integer> cold = Mono.fromSupplier(counter::incrementAndGet);

cold.subscribe(System.out::println); // 1
cold.subscribe(System.out::println); // 2
~~~

Đây là đoạn minh họa (cần import `java.util.concurrent.atomic.AtomicInteger` và `reactor.core.publisher.Mono`). Hai subscription chạy tuần tự nên thứ tự stdout như chú thích; `subscribe()` trên nguồn đồng bộ này thực thi ngay. Không suy ra mọi subscription đều chạy bất đồng bộ.

## 5. Operators: xây pipeline mà không tự quản thread

Reactor operators tạo publisher **mới**; chúng không thay đổi đối tượng publisher ban đầu theo kiểu mutable. Các toán tử thường dùng:

- `map(f)`: biến đổi đồng bộ `T → R`. Dùng khi `f` trả giá trị thông thường và thực thi nhanh.
- `flatMap(f)`: biến đổi `T → Publisher<R>`, ghép tác vụ bất đồng bộ. Với `Flux`, các phần tử có thể xen kẽ, thứ tự hoàn thành không được bảo đảm.
- `concatMap(f)`: ghép publisher lần lượt, giữ thứ tự nguồn; phù hợp khi thứ tự là bắt buộc, chấp nhận giảm mức đồng thời.
- `filter(predicate)`: chỉ giữ phần tử thỏa điều kiện.
- `switchIfEmpty(other)`: dùng publisher thay thế khi nguồn không có phần tử.
- `zip(a,b)`: kết hợp kết quả các nguồn khi tất cả nguồn cần thiết có dữ liệu; lưu ý nguồn empty có thể khiến kết quả zip cũng empty.
- `onErrorResume(f)`: chuyển sang nhánh phục hồi khi có lỗi; `onErrorMap(f)`: đổi kiểu lỗi; `timeout(duration)`: đặt hạn chờ cho pipeline.
- `doOnNext`, `doOnError`, `doFinally`: quan sát tín hiệu (logging, metrics, cleanup); không biến đổi giá trị như `map`.

~~~java
Flux<String> names = Flux.just(" an ", " binh ", " chi ");

Flux<String> normalized = names
    .map(String::trim)
    .filter(name -> name.length() >= 3)
    .map(String::toUpperCase);

normalized.subscribe(System.out::println);
~~~

Khi chạy trong ứng dụng có Reactor trên classpath, đoạn minh họa đồng bộ này in chính xác:

~~~text
BINH
CHI
~~~

`flatMap` đặc biệt quan trọng với I/O. Ví dụ **mã minh họa phụ thuộc một reactive repository có thật**:

~~~java
Mono<User> user = repository.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));

Flux<Order> orders = Flux.fromIterable(userIds)
    .flatMap(userId -> reactiveOrderRepository.findByUserId(userId));
~~~

Các tên `User`, `Order`, repository và exception cần được định nghĩa trong ứng dụng thật; đây không phải tệp tự chạy. Không thay `flatMap` bằng `map` khi callback trả `Mono`: nếu dùng `map` trong trường hợp đó, kết quả là `Mono<Mono<User>>` thay vì `Mono<User>`.

Tránh `onErrorResume(error -> Mono.empty())` cho mọi lỗi: nó âm thầm biến sự cố thành dữ liệu trống. Với lỗi xác thực, phân quyền hoặc lỗi hệ thống nghiêm trọng, cần giữ đúng ngữ nghĩa và trả phản hồi HTTP phù hợp.

## 6. Mô hình thực thi không chặn luồng: hiểu đúng event loop

Khi một client gửi HTTP request tới WebFlux chạy trên Reactor Netty, mô hình khái quát là:

~~~text
HTTP client
    |
    v
Reactor Netty event loop (đọc/ghi socket, I/O readiness)
    |
    v
WebFlux WebFilter chain (Spring Security có mặt tại đây)
    |
    v
DispatcherHandler -> Controller/Handler
    |
    v
Mono/Flux pipeline -> dữ liệu hoặc tín hiệu hoàn thành/lỗi
    |
    v
HTTP codec -> ghi response theo sự sẵn sàng của I/O
~~~

Các callback có thể chạy trên thread khác do nguồn I/O hoặc `Scheduler`; sơ đồ không có nghĩa mọi bước nằm trên cùng một thread. Với non-blocking I/O, trong lúc đợi network/database trả lời, event loop có thể phục vụ các kết nối khác thay vì đứng chờ kết quả. Đó là lý do một số lượng event-loop thread tương đối nhỏ có thể quản lý nhiều kết nối.

Phân biệt bốn khái niệm:

1. **Blocking:** thread phải chờ trước khi thực hiện tiếp, ví dụ `Thread.sleep`, JDBC đồng bộ, `Future.get()`, `Mono.block()`.
2. **Non-blocking:** lời gọi không giữ thread đứng chờ I/O; công việc tiếp tục khi có sự kiện/kết quả.
3. **Asynchronous:** kết quả đến ở thời điểm sau; không có nghĩa code tự động không blocking.
4. **Parallelism:** nhiều công việc thực sự chạy đồng thời trên nhiều lõi/thread; không đồng nghĩa với non-blocking.

Ví dụ `Mono.delay(Duration.ofMillis(200))` tạo tín hiệu sau khoảng 200 ms bằng cơ chế scheduler/timer, không gọi `Thread.sleep(200)` trên event-loop thread đang xử lý request. Trong khi đó, `Mono.just(slowJdbcCall())` gọi `slowJdbcCall()` **ngay khi biểu thức được đánh giá**, trước khi pipeline được subscribe, nên vẫn có thể chặn thread.

### `subscribeOn` và `publishOn`

Reactor không mặc định mở một thread mới cho mỗi `map`. Mọi callback thường chạy trên thread đang phát tín hiệu, trừ khi nguồn hoặc scheduler làm thay đổi ngữ cảnh.

- `subscribeOn(scheduler)` ảnh hưởng đến ngữ cảnh subscribe và upstream/source; đặt gần nguồn giúp người đọc thấy mục đích.
- `publishOn(scheduler)` chuyển xử lý các tín hiệu downstream sau nó sang một worker của scheduler đã chọn, cho đến lần chuyển tiếp theo.
- `Schedulers.parallel()` thích hợp cho công việc CPU có giới hạn; `Schedulers.boundedElastic()` dùng để cô lập lời gọi blocking không thể thay thế, với giới hạn lượng thread/queue.
- Không lạm dụng đổi scheduler ở mọi operator; chuyển thread có chi phí và không sửa được bottleneck của nguồn dữ liệu.

**Quan trọng:** "đẩy blocking sang boundedElastic" giúp tránh khóa event loop nhưng bản thân lời gọi vẫn blocking và vẫn tiêu tốn một thread; lựa chọn tốt hơn cho I/O tải lớn là dùng driver/reactive API thực sự.

## 7. Ứng dụng WebFlux + Spring Security hoàn chỉnh (Java 17+)

Tạo dự án từ Spring Initializr, chọn **Java 17 hoặc mới hơn**, Maven, và đúng hai dependency: **Spring Reactive Web** (`spring-boot-starter-webflux`) và **Spring Security** (`spring-boot-starter-security`). Dùng phiên bản Spring Boot ổn định tương thích với JDK tại thời điểm tạo dự án. Không thêm Spring Web MVC starter trong demo: khi cả Web MVC và WebFlux starter cùng hiện diện, Spring Boot mặc định chọn mô hình MVC trừ khi cấu hình kiểu ứng dụng rõ ràng.

Đặt các tệp trong `src/main/java/com/example/reactive/`. Không cần cơ sở dữ liệu hoặc dịch vụ bên ngoài.

**Tệp `ReactiveDemoApplication.java`**

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemoApplication.class, args);
    }
}
~~~

**Tệp `ApiController.java`**

~~~java
package com.example.reactive;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class ApiController {

    record Message(String message) {}

    @GetMapping("/public")
    Mono<Message> publicEndpoint() {
        return Mono.just(new Message("public"));
    }

    @GetMapping("/squares")
    Flux<Integer> squares() {
        return Flux.range(1, 3).map(n -> n * n);
    }

    @GetMapping(value = "/ticks",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<Long> ticks() {
        return Flux.interval(Duration.ofMillis(200)).take(3);
    }

    @GetMapping("/me")
    Mono<Message> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> new Message("hello " + name));
    }
}
~~~

**Tệp `SecurityConfig.java`**

~~~java
package com.example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public", "/api/ticks").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

Giải thích cấu hình: `SecurityWebFilterChain` kiểm tra route trước khi controller xử lý; `/api/public` và `/api/ticks` công khai, các endpoint còn lại yêu cầu `Authentication`. `httpBasic` cho phép gửi Basic Authorization để thử nghiệm. `MapReactiveUserDetailsService` là kho người dùng trong bộ nhớ phù hợp demo; mật khẩu được băm bằng BCrypt. Tài khoản và mật khẩu mẫu chỉ dành cho môi trường học tập, không đưa cố định vào production. Đối với ứng dụng production cần chọn cơ chế xác thực, HTTPS, lưu trữ bí mật và chính sách CSRF phù hợp với loại client.

Chạy tại thư mục dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell có thể dùng `.\mvnw.cmd spring-boot:run`. Khi server đã khởi động trên cổng mặc định 8080, mở terminal khác:

~~~bash
curl -s http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -s -u learner:demo123 http://localhost:8080/api/me
curl -s -u learner:demo123 http://localhost:8080/api/squares
curl -N http://localhost:8080/api/ticks
~~~

Kết quả nội dung phản hồi được kỳ vọng:

- `GET /api/public` → HTTP 200, JSON `{"message":"public"}`.
- `GET /api/me` không có credentials → HTTP 401 Unauthorized (các header có thể khác tùy phiên bản).
- `GET /api/me` có HTTP Basic đúng → HTTP 200, JSON `{"message":"hello learner"}`.
- `GET /api/squares` có credentials → HTTP 200, JSON `[1,4,9]`.
- `GET /api/ticks` → HTTP 200, stream SSE phát lần lượt giá trị `0`, `1`, `2`, cách nhau xấp xỉ 200 ms. `curl -N` tránh buffering ở phía curl; thời điểm thực tế phụ thuộc scheduling.

Lưu ý: các kết quả trên là kết quả **kỳ vọng theo mã mẫu**, không phải log chạy thực tế của một môi trường đã được khởi động. Mã ví dụ đồng bộ các tên class, package, import và endpoint; cấu hình môi trường ngoài dự án có thể làm thay đổi cổng hoặc cơ chế bảo mật.

### Tại sao ví dụ là reactive?

- `/api/public` dùng `Mono<Message>` cho một giá trị.
- `/api/squares` dùng `Flux<Integer>` cho ba giá trị; `map` là biến đổi đồng bộ nhanh.
- `/api/ticks` dùng publisher phát theo timer và SSE; không giữ một request thread ngủ 200 ms giữa các giá trị.
- `/api/me` lấy tên người dùng qua `ReactiveSecurityContextHolder` bên trong pipeline.
- Controller chỉ **trả publisher**. Spring WebFlux/Spring Security chịu trách nhiệm subscribe, gửi response và xử lý lỗi/hủy.

Không suy ra rằng tất cả `Mono` luôn chạy trên thread riêng: `Mono.just` có thể phát đồng bộ; `Flux.interval` dùng scheduler. "Reactive" nằm ở contract và cách kết hợp các nguồn, không phải lời hứa mỗi operator đều tạo thread.

## 8. Spring Security trên reactive stack

Spring Security cho WebFlux được tích hợp qua **`WebFilter`** và được cấu hình bằng **`SecurityWebFilterChain`**/`ServerHttpSecurity`. Nó khác với `SecurityFilterChain`/`HttpSecurity` của Servlet stack. Những khái niệm xác thực và phân quyền vẫn quen thuộc, nhưng API xử lý là reactive:

| Việc cần làm | Kiểu/khái niệm reactive |
| --- | --- |
| Kiểm tra request và áp dụng policy | `SecurityWebFilterChain` và `authorizeExchange` |
| Xác thực bất đồng bộ | `ReactiveAuthenticationManager` trả publisher chứa kết quả authentication |
| Tra cứu thông tin tài khoản | `ReactiveUserDetailsService`, thường trả `Mono<UserDetails>` |
| Đọc security context của request | `ReactiveSecurityContextHolder.getContext()` |
| Ghi/đọc security context ở web layer | Các cơ chế reactive của Spring Security, ví dụ `ServerSecurityContextRepository` theo cấu hình |
| Phân quyền ở service method (khi có) | `@EnableReactiveMethodSecurity` và các annotation method security tương ứng |

### Vì sao không đọc SecurityContextHolder kiểu Servlet?

Trong Servlet stack, `SecurityContextHolder` thường gắn dữ liệu vào `ThreadLocal` của thread đang phục vụ request. Trong reactive pipeline, execution có thể đi qua nhiều thread do I/O và scheduler, đồng thời một thread có thể phục vụ các subscription khác nhau. Vì thế không nên dựa vào một `ThreadLocal` thông thường để mang identity xuyên suốt reactive chain.

Spring Security truyền security context phù hợp thông qua **Reactor Context**, gắn theo subscription, và hỗ trợ truy xuất bằng `ReactiveSecurityContextHolder`. Ví dụ `/api/me` đọc context trong pipeline thay vì lấy một giá trị toàn cục tại lúc dựng controller. Context không phải dữ liệu được gửi tự động sang mọi HTTP service khác: khi gọi downstream phải thiết kế cách chuyển token/credentials phù hợp.

Cũng vì context phụ thuộc subscription, tự gọi `subscribe()` tách rời trong service/controller có thể phá vỡ vòng đời request, xử lý lỗi hoặc ngữ cảnh xác thực. Hãy trả về `Mono`/`Flux` cho framework hoặc compose nó vào pipeline của caller.

### Pipeline bảo mật cần giữ tính non-blocking

Một pipeline dễ hiểu là:

~~~text
request
  -> WebFilter/Authentication
  -> Authorization
  -> Controller
  -> Reactive service
  -> Reactive repository hoặc WebClient
  -> HTTP response
~~~

Nếu ở bất kỳ bước nào bạn gọi API blocking trên event loop (ví dụ lookup user bằng JDBC đồng bộ trong authentication), bạn có thể làm nghẽn cả các request khác. Đổi signature thành `Mono<Authentication>` nhưng thực hiện I/O đồng bộ trực tiếp trong `map` không giải quyết vấn đề.

Trong method security, việc trả publisher và kiểm soát context cần được thiết kế cùng nhau. Không nên vô tình "phân quyền sau khi dữ liệu nhạy cảm đã được phát"; áp dụng quy tắc sớm, có điều kiện kiểm tra rõ ràng, và tránh fallback cho phép truy cập khi một bước xác thực gặp lỗi.

## 9. Viết non-blocking từ đầu đến cuối

Một ứng dụng thường phải gọi service khác hoặc truy vấn cơ sở dữ liệu. Các lựa chọn nên ưu tiên:

- HTTP outbound: `WebClient` với non-blocking connector thay cho client đồng bộ khi dùng WebFlux.
- Truy vấn quan hệ: R2DBC/reactive repository khi hệ quản trị và driver hỗ trợ; JDBC thông thường vẫn blocking.
- Luồng sự kiện: reactive adapter tương thích, quản lý backpressure và vòng đời subscription.
- Tác vụ CPU lớn: cân nhắc scheduler, số lượng công việc đồng thời và kiến trúc xử lý nền, không ép tính toán nặng lên event loop.

Ví dụ **đoạn minh họa trong service có `WebClient` đã được cấu hình và `UserDto` đã được khai báo**:

~~~java
Mono<UserDto> result = webClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .bodyToMono(UserDto.class)
    .timeout(Duration.ofSeconds(2));
~~~

Ở đây `bodyToMono` biểu diễn một kết quả tương lai. `timeout` giới hạn thời gian đợi; lỗi timeout cần được phân loại và ánh xạ sang phản hồi/cơ chế retry phù hợp. Không được gọi `result.block()` trong request handler chỉ để "lấy giá trị ra" vì như vậy phá vỡ mục tiêu non-blocking.

### Khi bắt buộc dùng API blocking cũ

Dùng `Mono.fromCallable` để **trì hoãn** lời gọi tới lúc subscribe, rồi chuyển nó sang `boundedElastic`. Ví dụ sau chỉ là pattern minh họa vì `legacyClient` phải được cung cấp ở ứng dụng thật:

~~~java
Mono<String> adapted = Mono
    .fromCallable(() -> legacyClient.lookup("customer-42"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Lý do dùng hai bước: `fromCallable` tránh gọi `lookup` ngay lúc dựng pipeline; `subscribeOn` chạy nguồn blocking trên scheduler phù hợp, tránh chặn event-loop thread. Cách này không khiến client trở thành non-blocking và vẫn phải giới hạn concurrency/queue, connection pool, timeout. Không dùng `Schedulers.parallel()` để chờ I/O blocking kéo dài.

**Sai thường gặp:**

~~~java
Mono<String> wrong = Mono.just(legacyClient.lookup("customer-42"));
// lookup() chạy ngay, có thể chặn event loop.

Mono<String> stillWrong = Mono.fromSupplier(
    () -> legacyClient.lookup("customer-42"));
// Lazy, nhưng nếu subscribe trên event loop thì vẫn blocking ở event loop.
~~~

Cả hai đoạn đều là mã minh họa không tự chạy. `fromSupplier` giải quyết tính lazy, không tự quyết định một scheduler có thể chịu blocking.

## 10. Backpressure, độ trễ và tiêu thụ bộ nhớ

Với `Flux`, downstream có thể yêu cầu một lượng phần tử phù hợp thông qua `request(n)`. Tuy nhiên nhiều operator có chính sách prefetch/buffering riêng, các boundary như HTTP, database driver và hot source có hành vi khác nhau. Cần kiểm soát đồng thời **số request đang chạy**, **số phần tử xử lý song song** và **bộ đệm**.

Ví dụ minh họa về giới hạn concurrency:

~~~java
Flux<Result> results = Flux.fromIterable(ids)
    .flatMap(id -> reactiveService.fetch(id), 8);
~~~

Đoạn này cần `ids`, `Result` và `reactiveService` từ ứng dụng thật. Tham số `8` giới hạn số inner publishers được `flatMap` subscribe đồng thời, hữu ích khi không muốn mở quá nhiều lời gọi upstream. Nó không phải giới hạn số kết nối toàn hệ thống: connection pool, rate limit và cấu hình server vẫn cần được thiết lập.

Một số operator liên quan:

- `limitRate(n)` điều chỉnh cách request demand lên upstream; không có nghĩa toàn bộ pipeline luôn giữ tối đa `n` phần tử trong bộ nhớ.
- `onBackpressureBuffer(...)` lưu phần tử khi downstream chậm; cần giới hạn rõ và phương án overflow.
- `onBackpressureDrop()`/`onBackpressureLatest()` phù hợp một số stream telemetry có thể bỏ mẫu, không phù hợp dữ liệu tài chính hoặc sự kiện bắt buộc xử lý đủ.
- `take(n)` kết thúc sau `n` phần tử và thường cancel upstream. Hủy subscription giúp giải phóng tài nguyên nhưng không thể đảm bảo một tác vụ bên ngoài đã bắt đầu sẽ luôn được hoàn tác.

Với SSE/stream dài, xử lý disconnect, timeout, cleanup và tốc độ client là yếu tố quan trọng. Với JSON array thông thường, việc encode/ghi response có thể phụ thuộc cách codec buffer/flush, không nên mặc định mỗi phần tử `Flux` sẽ lập tức hiện trên màn hình client.

## 11. Xử lý lỗi, empty và cancellation

Reactive error là **tín hiệu kết thúc** của một subscription. Một số pattern:

~~~java
Mono<String> fallback = remoteCall()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(TimeoutException.class, error -> Mono.just("cached"));
~~~

Đây là đoạn minh họa: cần có `remoteCall()`, import `Duration` và `TimeoutException` tương ứng. Fallback cache chỉ hợp lý nếu nghiệp vụ chấp nhận dữ liệu cũ; không được mặc định dùng chuỗi `"cached"` thay cho kết quả quyết định quyền truy cập.

- `onErrorResume` chọn nhánh phục hồi, khác `doOnError` chỉ ghi log/quan sát.
- `switchIfEmpty` xử lý **không có phần tử**, khác hoàn toàn **đã có lỗi**.
- `retry` có thể gọi lại upstream, nên phải cân nhắc idempotency (đặc biệt với POST, thanh toán, gửi thông báo), số lần thử và backoff.
- `timeout` đặt thời hạn; cần phân biệt timeout do mình chủ động áp và timeout của client/driver.
- `doFinally`/`usingWhen` hữu ích khi giải phóng tài nguyên theo complete/error/cancel.
- Khi HTTP response đã bắt đầu stream, một lỗi muộn có thể không còn chuyển được thành JSON lỗi hay status code mới; cần cơ chế báo lỗi thích hợp với stream.

Không nuốt lỗi authentication/authorization bằng `onErrorResume(e -> Mono.just(true))` hoặc trả dữ liệu mặc định giống thành công. Về bảo mật, thất bại xác thực/phân quyền phải dẫn tới quyết định từ chối hoặc xử lý lỗi có kiểm soát.

## 12. Lỗi phổ biến và cách sửa

| Vấn đề | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `Mono.just(blockingCall())` | Lời gọi diễn ra trước subscription | Dùng reactive driver; hoặc `fromCallable(...).subscribeOn(boundedElastic())` khi bắt buộc |
| `Thread.sleep`, `block()`, `Future.get()` trong controller | Chặn thread xử lý request | Compose pipeline bằng `flatMap`/`zip`, dùng timer/async API |
| Gọi `subscribe()` trong controller/service rồi trả `Mono.empty()` | Tạo công việc tách khỏi response, mất ngữ nghĩa lỗi/context | Trả publisher hoặc nối publisher vào pipeline được framework quản lý |
| Dùng `map` cho hàm trả `Mono` | Sinh publisher lồng nhau | Dùng `flatMap` |
| Nghĩ `Flux` luôn giữ thứ tự sau `flatMap` | Inner publisher có thể hoàn tất khác thứ tự | Dùng `concatMap` khi cần thứ tự |
| Dùng `collectList()` trên stream lớn/vô hạn | Gom dữ liệu vào RAM, chờ hoàn thành | Stream từng phần tử, phân trang, giới hạn kích thước |
| Dùng `ThreadLocal` cho user/security context | Reactive chain có thể chuyển thread | Dùng `ReactiveSecurityContextHolder`/Reactor Context |
| Cấu hình `HttpSecurity` thay `ServerHttpSecurity` trong WebFlux | Trộn servlet và reactive security stack | Dùng `SecurityWebFilterChain` + `ServerHttpSecurity` |
| Retry mọi lỗi hoặc nuốt mọi `onError` | Che giấu sự cố, có thể lặp side effect | Phân loại lỗi, giới hạn retry, giữ semantics bảo mật |
| Cho rằng mỗi `Mono` tự chạy bất đồng bộ | Publisher có thể đồng bộ/lazy | Xác định nguồn phát tín hiệu, scheduler và I/O thực tế |

Một lỗi khác là thêm đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux` rồi mặc định nghĩ ứng dụng chạy WebFlux. Spring Boot thường ưu tiên MVC khi có cả hai; cần kiểm tra dependency và application type. Một ứng dụng MVC vẫn có thể dùng `WebClient` mà không biến toàn bộ server thành WebFlux.

## 13. Kiểm tra và chẩn đoán

1. **Hành vi HTTP:** thử endpoint anonymous và authenticated; đối chiếu 200/401/403 theo rule; kiểm tra phản hồi JSON và SSE.
2. **Thread và blocking:** xem thread name trong log ở môi trường thử nghiệm để hiểu điểm chuyển scheduler; không dùng log thread name làm cơ chế xác định danh tính. BlockHound trong môi trường test có thể giúp phát hiện các lời gọi blocking trên thread được đánh dấu non-blocking.
3. **Hiệu năng:** quan sát CPU, event-loop latency, connection pool, timeout, số subscription đang hoạt động, buffer/queue và p95/p99 latency trong tải thực tế.
4. **Backpressure:** thử consumer chậm, cancellation/disconnect, upstream nhanh và timeout. Xác minh chính sách buffer/drop được chọn phù hợp dữ liệu.
5. **Security:** kiểm tra context được truyền qua các bước bất đồng bộ; không rò rỉ identity giữa requests; không vô tình mở endpoint do rule `permitAll` quá rộng.
6. **Testing Reactor:** `StepVerifier` từ `reactor-test` giúp kiểm tra thứ tự `onNext`, `onComplete`, `onError`; dùng `WebTestClient` để kiểm tra endpoint WebFlux, với Spring Security test support khi cần giả lập authenticated principal.

Không đánh giá kiến trúc chỉ bằng số thread: non-blocking có thể tăng khả năng chịu tải I/O nhưng vẫn cần xác minh độ trễ, throughput, GC, DB bottleneck và lỗi khi client ngắt kết nối.

## 14. Bài tập tự luyện

**Bài 1 – Phân loại publisher.** Chọn `Mono` hay `Flux` cho: lấy profile theo id, đếm số bản ghi, stream thông báo, lệnh xóa trả 204. Giải thích vì sao `Mono<Void>` phù hợp với trường hợp chỉ cần biết thành công/thất bại.

**Bài 2 – Đọc code và sửa lỗi.** Trong controller WebFlux, đoạn `Mono.just(jdbcRepository.findById(id))` có hai vấn đề gì? Hãy nêu phương án tốt nhất và phương án tạm thời khi chưa thay được JDBC.

**Bài 3 – Bảo mật reactive.** Với ứng dụng demo, tại sao `/api/me` đọc được `learner` dù controller không giữ một biến toàn cục `currentUser`? Giải thích vai trò `SecurityWebFilterChain`, authentication, Reactor Context.

**Bài 4 – Stream.** Đổi `take(3)` trong `/api/ticks` thành `take(5)`, thử ngắt client sớm và mô tả cancellation. Xác định vì sao dữ liệu SSE đến từng đợt trong khi JSON array thông thường có thể được xử lý khác.

**Gợi ý đáp án ngắn:** Profile và count thường là `Mono<T>`; notifications là `Flux<T>`; delete không body là `Mono<Void>`. JDBC vẫn blocking; ưu tiên driver reactive, nếu chưa thể dùng `fromCallable` và `boundedElastic` với giới hạn tài nguyên. Authentication trong demo đi qua WebFlux security filters, context của subscription được truy xuất bằng `ReactiveSecurityContextHolder`, không dựa vào `ThreadLocal` của Servlet.

## 15. Tổng kết và tài liệu chính thức

Nắm đúng ba tầng: **WebFlux** cung cấp HTTP reactive stack; **Reactor** cung cấp `Mono`/`Flux` và operators để mô tả tín hiệu, backpressure và execution; **Spring Security reactive** áp chính sách bảo mật bằng `WebFilter` và context gắn với reactive subscription. Non-blocking không tự đến từ kiểu trả về: cần xây pipeline không chặn I/O từ đầu đến cuối, quản lý concurrency và xử lý lỗi/cancellation rõ ràng.

Tài liệu tra cứu:

- [Spring Framework – Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Framework – WebFlux Overview và mô hình concurrency](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
