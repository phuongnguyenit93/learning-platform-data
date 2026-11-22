# Phân biệt lỗi ứng dụng với lỗi do block hoặc subscribe sai cách trong Spring WebFlux

## 1. Vì sao phải phân biệt ba nhóm lỗi?

Trong Spring WebFlux, một HTTP request có thể thất bại vì **quy tắc nghiệp vụ**, vì **hạ tầng** (database, API ngoài, timeout) hoặc vì **cách lập trình Reactive Streams không đúng**. Biểu hiện bên ngoài đôi khi đều là HTTP 500, response trống, timeout hoặc test không ổn định, nhưng cách khắc phục hoàn toàn khác nhau.

Ví dụ với `GET /api/orders/42`:

- Đơn hàng không tồn tại: ứng dụng **chủ động phát lỗi nghiệp vụ** `OrderNotFoundException`. Nếu hợp đồng API quy định 404, controller advice phải chuyển đúng thành `404 Not Found`.
- Gateway gặp sự cố: `Mono.error(new IllegalStateException("gateway unavailable"))` là **lỗi hệ thống/downstream**. Không nên biến nó thành 404 chỉ để làm test xanh.
- Controller gọi `.block()` trên một **Reactor non-blocking thread**: có thể ném `IllegalStateException` do thao tác blocking bị cấm ở thread đó. Đây là **lỗi thiết kế reactive**, không chứng minh đơn hàng có vấn đề.
- Controller gọi `.subscribe()` thủ công rồi trả một publisher khác: lỗi từ publisher được subscribe có thể đi qua **một subscription độc lập**, không còn thuộc HTTP response mà WebFlux đang quản lý. Client có thể nhận response thành công/rỗng dù công việc nền thất bại.
- Publisher không được subscribe: các thao tác lazy chưa chạy; test chỉ nhìn thấy object `Mono` và kết luận có side effect là **false positive**.

**Mục tiêu:** phân loại nguyên nhân qua vị trí phát sinh, tín hiệu `onNext/onError/onComplete`, đường subscription và ranh giới HTTP; sau đó dùng `StepVerifier`, `WebTestClient` và quan sát scheduler/thread để kiểm tra đúng hành vi.

## 2. Mô hình nền tảng: Mono/Flux là một bản mô tả công việc

Trong Reactor, `Mono<T>` biểu diễn một publisher có **tối đa một phần tử** (hoặc empty/error), còn `Flux<T>` có thể phát nhiều phần tử. Phần lớn publisher tạo từ `Mono.defer`, `Mono.fromCallable`, `Flux.defer` hoặc các thao tác reactive từ repository là **lazy/cold**: công việc có thể chỉ bắt đầu khi có subscriber.

```text
Assembly (lắp pipeline)
  Mono.defer(...)
      .map(...)
      .flatMap(...)
      .onErrorResume(...)
          |
          |  Chưa nhất thiết gọi DB/API
          v
Subscription
          |
          +---- request/demand ----> upstream
          |
          +---- onNext(value)  (0 hoặc 1 với Mono)
          |
          +---- onComplete()   (kết thúc bình thường)
          |
          +---- onError(error) (kết thúc bằng lỗi)
```

Đối với một subscription, `onError` và `onComplete` là **terminal signals loại trừ nhau**. `Mono.empty()` có thể hoàn tất mà không phát dữ liệu, và **không tự có nghĩa** HTTP 404. `Mono.error(ex)` mô tả lỗi sẽ được phát cho subscriber; nó khác với việc ném một exception đồng bộ trước khi trả publisher, dù WebFlux có thể xử lý cả hai qua các cơ chế thích hợp.

**WebFlux là bên subscribe cho publisher được controller trả về.** Vì vậy controller thông thường nên **return pipeline** thay vì tự `.subscribe()` hoặc `.block()`. Trong unit test Reactor, `StepVerifier` là subscriber có assertion. Trong web slice/integration test, `WebTestClient.exchange()` kích hoạt đường request rồi kiểm tra HTTP response.

### 2.1. Nhận diện từ một ví dụ ngắn

```java
Mono<String> pending = Mono.defer(() -> {
    System.out.println("executed");
    return Mono.just("OK");
});

// Lúc này mới tạo publisher; "executed" chưa được in.
StepVerifier.create(pending)
        .expectNext("OK")
        .verifyComplete();
```

Đây là **đoạn minh họa trong một test đã import `Mono` và `StepVerifier`**, không phải tệp Java độc lập. Khi `StepVerifier` subscribe, `Mono.defer` chạy và có thể in một dòng `executed`. Không nên kết luận mọi `Mono.just(...)` cũng trì hoãn biểu thức tạo đối số: **biểu thức dùng làm argument cho `just` được đánh giá ngay khi lắp pipeline**.

## 3. Ma trận chẩn đoán: lỗi ứng dụng hay lỗi do sử dụng reactive sai?

| Biểu hiện | Nhóm khả dĩ | Bằng chứng nên tìm | Hướng xử lý |
|---|---|---|---|
| `Mono.error(OrderNotFoundException)` | Nghiệp vụ: không tìm thấy | Exception type, mã đơn, HTTP mapping | `switchIfEmpty`/advice chuyển thành 404 theo hợp đồng |
| `IllegalArgumentException` do input sai | Validation/nghiệp vụ đầu vào | Constraint và request thực tế | Trả 400 khi lỗi thuộc client; kiểm tra trước khi gọi gateway |
| `R2dbcException`, connection refused, timeout gọi API | Hạ tầng | Root cause, log client, retry/timeout config | Trả lỗi hệ thống phù hợp; không mạo danh 404 |
| `IllegalStateException` báo `block()` không được phép trên thread non-blocking | Misuse Reactor scheduler/thread | Stack trace tại `.block()`, tên thread | Return publisher; bỏ block hoặc cô lập công việc blocking đúng cách |
| HTTP trả 200 rỗng dù async operation bị lỗi | Có thể `.subscribe()` thủ công và bỏ subscription khỏi response | Tìm `.subscribe()`, `doOnError`, terminal response | Return publisher để WebFlux quản lý lỗi/hoàn tất |
| Side effect không chạy dù đã tạo `Mono` | Chưa có subscription, publisher lazy | Thử `StepVerifier`, kiểm tra `doOnSubscribe` | Subscribe ở ranh giới đúng; không tự subscribe ở service/controller |
| Side effect chạy hai lần | Nhiều subscriptions lên cold source | Đếm subscription, network requests, gọi repository | Tránh duplicate subscription; chia sẻ/cache có chủ đích khi thật cần |
| Request treo, timeout, CPU không cao | Publisher không complete, blocking call, deadlock hoặc thiếu demand | Reactor signals, thread dump, timeout config | Tìm điểm chặn và ranh giới subscription/cancellation |
| `ErrorCallbackNotImplemented` hoặc error dropped | Subscriber không xử lý error hoặc signal không còn consumer | Stack trace, subscribe call, log Reactor | Return chain, có error handler phù hợp; kiểm tra terminal signals |
| `NullPointerException` do mock trả `null` thay vì `Mono` | Mock/stubbing không đúng reactive contract | Mockito stubs, method return type | Trả `Mono.just`, `Mono.empty`, `Mono.error` theo ca |

**Đừng chẩn đoán chỉ từ HTTP status.** Một lỗi business có thể bị global error handler biến thành 500 khi thiếu mapping; một lỗi từ gateway có thể bị `onErrorResume` vô tình che thành 200 hoặc 404; một lỗi `.block()` cũng có thể được chuyển thành 500. Cần đọc **stack trace, signal path, operator và logic handler**.

## 4. `.block()` sai ở đâu?

`block()` subscribe vào `Mono` rồi **chờ đồng bộ** để nhận dữ liệu/kết thúc. Nó có thể phù hợp ở **biên đồng bộ có chủ đích** (ví dụ chương trình CLI, một số đoạn integration test chạy trên test thread), nhưng là anti-pattern trong reactive controller và trong một pipeline chạy trên Reactor event loop.

### 4.1. Sai: block bên trong controller WebFlux

```java
// Đoạn minh họa CỐ Ý SAI, đặt trong controller WebFlux.
@GetMapping("/{id}")
public Mono<OrderView> find(@PathVariable String id) {
    OrderView order = reader.find(id).block();
    return Mono.just(order);
}
```

Nếu method này được gọi trên một Reactor thread được đánh dấu non-blocking (thường gặp trong Reactor Netty), việc `.block()` có thể ném `IllegalStateException` với thông báo kiểu “block()/blockFirst()/blockLast() are blocking, which is not supported in thread ...”. Chi tiết stack trace/tên thread phụ thuộc phiên bản Reactor, runtime và đường thực thi. Nếu thread **không** được đánh dấu non-blocking, `.block()` có thể vẫn chạy nhưng **chiếm thread và gây giảm throughput/latency**, thay vì ném đúng thông báo đó.

Còn một lỗi khác: nếu `reader.find(id)` trả `Mono.empty()`, `.block()` có thể trả `null`; `Mono.just(null)` sẽ lỗi tiếp. Do đó không được dùng `.block()` chỉ để chuyển reactive result sang một giá trị Java rồi bọc trở lại `Mono`.

### 4.2. Đúng: trả lại publisher

```java
// Đoạn đúng bên trong controller có reader đã inject.
@GetMapping("/{id}")
public Mono<OrderView> find(@PathVariable String id) {
    return reader.find(id);
}
```

WebFlux sẽ subscribe cho publisher và xử lý `onNext`, completion hoặc error trong request lifecycle. Nhờ đó, `@ExceptionHandler`/global error handling có cơ hội nhìn thấy lỗi thuộc response.

### 4.3. `Thread.sleep` và JDBC blocking cũng nguy hiểm

Lỗi blocking không giới hạn ở `.block()`. Một `Thread.sleep`, JDBC call, `RestTemplate` đồng bộ, ghi file đồng bộ hoặc một SDK blocking chạy trên event loop có thể **không tự ném `IllegalStateException`**, nhưng vẫn chiếm non-blocking thread, làm các request khác bị chậm hoặc timeout. Đây thường là lỗi hiệu năng khó nhìn thấy trong test đơn giản.

Nếu tạm thời phải gọi API legacy blocking, có thể bọc nguồn gọi đồng bộ:

```java
// Ví dụ minh họa: legacyClient.load(id) là thao tác blocking
// của một dependency đã tồn tại trong ứng dụng.
Mono<OrderView> result =
        Mono.fromCallable(() -> legacyClient.load(id))
                .subscribeOn(Schedulers.boundedElastic());
```

Đây là **đoạn minh họa không độc lập**, yêu cầu imports `Mono`, `Schedulers` và kiểu `legacyClient` phù hợp. `boundedElastic` chuyển tác vụ blocking sang scheduler có giới hạn tài nguyên, **không làm I/O trở thành non-blocking**, không bảo đảm hủy một JDBC call đang chặn, và không thay thế reactive driver như R2DBC hoặc WebClient khi kiến trúc cho phép.

**Sai về thời điểm gọi:**

```java
Mono<OrderView> wrong =
        Mono.just(legacyClient.load(id))
            .subscribeOn(Schedulers.boundedElastic());
```

Lời gọi `legacyClient.load(id)` được đánh giá **trước khi Mono được tạo**, nên `subscribeOn` đến quá muộn để chuyển thao tác blocking đó khỏi thread hiện tại. Dùng `Mono.fromCallable` hoặc `Mono.defer` để trì hoãn đúng phần công việc cần xử lý.

## 5. `.subscribe()` thủ công có thể làm hỏng HTTP contract

Trong các handler và service được WebFlux quản lý, một lỗi phổ biến là **tự subscribe** vào publisher phụ rồi trả một response khác:

```java
// Đoạn minh họa CỐ Ý SAI: fire-and-forget không có hợp đồng rõ.
@PostMapping("/orders/{id}/confirm")
public Mono<Void> confirm(@PathVariable String id) {
    confirmationService.confirm(id).subscribe();
    return Mono.empty();
}
```

Ở đây subscription do `.subscribe()` tạo có lifecycle/error/cancellation **riêng**, không còn là publisher trả về cho WebFlux. Client có thể được báo hoàn tất trong khi confirm vẫn chạy hoặc đã lỗi. Nếu lỗi không có error consumer phù hợp, Reactor có thể log lỗi không được xử lý hoặc `ErrorCallbackNotImplemented`/dropped-error message tùy tình huống.

Cách **đúng khi HTTP contract yêu cầu đợi xác nhận hoàn tất**:

```java
@PostMapping("/orders/{id}/confirm")
public Mono<Void> confirm(@PathVariable String id) {
    return confirmationService.confirm(id);
}
```

Hai đoạn chỉ minh họa method controller, giả định `confirmationService.confirm` trả `Mono<Void>`; không phải chương trình độc lập. Nếu sản phẩm thật sự yêu cầu **202 Accepted và xử lý nền**, cần thiết kế queue/job/outbox/lifecycle lỗi rõ ràng; đừng coi `subscribe()` thủ công trong request handler là cơ chế job management bền vững.

### 5.1. Vì sao subscribe lần hai có thể phát side effect hai lần?

Phần lớn reactive sources là **cold**: mỗi lần subscribe có thể kích hoạt lại đọc DB/gọi HTTP/gửi event. Ví dụ:

```java
Mono<OrderView> order = reader.find("42");

// Một subscriber phụ, ví dụ để log:
order.subscribe(value -> audit(value));

// WebFlux cũng subscribe vào publisher được return:
return order;
```

Đây là **đoạn minh họa anti-pattern** bên trong một handler có `reader`/`audit`. Hai subscription có thể dẫn đến **hai lần gọi upstream** và hai trạng thái khác nhau nếu dữ liệu đã thay đổi. Trường hợp muốn log nhưng vẫn giữ một pipeline, thường dùng:

```java
return reader.find("42")
        .doOnNext(value -> audit(value));
```

`doOnNext` là side effect khi có signal, **không tự subscribe**. Nếu `audit` là thao tác I/O blocking, không được thực hiện trực tiếp trên event loop; cần lựa chọn kiến trúc phù hợp. `doOnNext` cũng không biến một audit bất đồng bộ thành việc được chờ hoàn tất — nếu audit trả publisher, cần phối hợp bằng `flatMap` hoặc operator tương ứng.

### 5.2. Cẩn thận khi dùng cache/share

`Mono.cache()` có thể tránh chạy lại upstream giữa nhiều subscription của **cùng một Mono đã cache**. Tuy nhiên, cache cũng có thể giữ **kết quả rỗng hoặc lỗi**, tăng nguy cơ dữ liệu cũ, chứa kết quả theo user/tenant sai, và thay đổi semantics cancellation. Không chữa duplicate subscription bằng `cache()` một cách vô điều kiện. Biên đúng là tổ chức luồng dữ liệu để có **một subscription chủ đạo** trong request; dùng cache chỉ khi hợp đồng cho phép chia sẻ dữ liệu và lifetime được thiết kế rõ.

## 6. Những operator có thể che mất lỗi ứng dụng

### 6.1. `doOnError` chỉ quan sát, không xử lý

```java
return gateway.findById(id)
        .doOnError(error -> logger.warn(
                "order lookup failed", error));
```

Đây là đoạn minh họa trong component có `gateway` và `logger`. `doOnError` cho phép logging/metrics khi `onError` đi qua; nó **không** chuyển lỗi thành thành công và không ngăn subscriber nhận `onError`.

### 6.2. `onErrorResume` thay publisher và có thể đổi ý nghĩa lỗi

```java
return gateway.findById(id)
        .onErrorResume(OrderNotFoundException.class,
                error -> Mono.empty());
```

Dòng này biến **lỗi không tìm thấy** thành **hoàn tất rỗng**. Điều đó chỉ đúng nếu hợp đồng tầng gọi muốn kết quả vắng mặt dưới dạng empty; trong controller mà hợp đồng cần HTTP 404, phải tiếp tục chuyển empty thành 404 hoặc dùng `ResponseEntity.notFound()`. Nếu dùng `onErrorResume(error -> Mono.empty())` cho **mọi exception**, lỗi kết nối DB/API có thể bị che thành 200 body rỗng — nguy hiểm cho vận hành.

### 6.3. `onErrorMap` chuyển loại lỗi, không nuốt lỗi

```java
return gateway.findById(id)
        .onErrorMap(GatewayTimeoutException.class,
                error -> new ServiceUnavailableException(
                        "read service unavailable", error));
```

Đây là minh họa với exception classes giả định của ứng dụng. Cần phân loại thật sự những lỗi có thể được chuyển đổi; không tự chuyển mọi `IllegalStateException` hoặc lỗi `.block()` thành “đơn hàng không tồn tại”.

### 6.4. `onErrorComplete` có thể khiến test xanh sai

`onErrorComplete()` chuyển error terminal thành complete terminal. Nếu dùng để “sửa” một test đang gặp `IllegalStateException` do blocking, bạn đã **giấu nguyên nhân** chứ chưa sửa thiết kế. Chỉ dùng khi hợp đồng **chủ động chấp nhận bỏ qua lỗi** trong một nhánh có giới hạn và đã được ghi nhận/giám sát.

### 6.5. `map` khác `flatMap` khi callback trả Mono

Sai về cấu trúc:

```java
Mono<Mono<OrderView>> nested =
        Mono.just("42").map(id -> reader.find(id));
```

`nested` chỉ phát ra **một Mono bên trong**, không tự subscribe để lấy `OrderView`. Đúng khi cần ghép async operation:

```java
Mono<OrderView> flattened =
        Mono.just("42").flatMap(id -> reader.find(id));
```

Đây là các đoạn minh họa trong scope có `reader`. Nếu test chỉ `expectNextMatches(value -> value != null)` trên `Mono<Mono<...>>`, nó có thể xanh nhưng chưa kiểm chứng việc tra cứu đơn hàng **thực sự thực thi**. Cần assert đúng kiểu và giá trị cuối cùng.

## 7. Ví dụ Java 17+ chạy được: phân biệt lỗi nghiệp vụ và lỗi gateway qua StepVerifier

### 7.1. Cấu trúc và điều kiện

Ví dụ sau minh họa service đọc đơn hàng theo ID, trả `Mono<OrderView>` và phân biệt:

- `id` rỗng → `InvalidOrderIdException`.
- Không có đơn hàng → `OrderNotFoundException`.
- Gateway phát lỗi hạ tầng → **giữ lỗi hệ thống**, không giả làm “not found”.
- Thành công → đúng `OrderView`.
- Việc gọi gateway được trì hoãn đến **subscription**; test chứng minh bằng Mockito.
- Hai subscriptions lên cold source có thể kích hoạt gateway hai lần.

Dùng Java 17+, Spring Boot 3.4/3.5, `spring-boot-starter-webflux`, `spring-boot-starter-test` và `reactor-test`. Các tệp nằm trong package `com.example.reactiveerrors`. Unit test `OrderReaderTest` **không khởi động Spring context**, chỉ sử dụng Reactor + JUnit Jupiter + Mockito.

Cấu hình Gradle Groovy DSL minh họa trong dự án đã có Boot plugin, Java 17+ và repository Maven Central:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là một fragment `build.gradle`, không phải build script độc lập. Trong Maven, dùng BOM/parent Spring Boot để đồng bộ dependency versions và phiên bản Surefire chạy JUnit Jupiter.

### 7.2. Các kiểu dữ liệu và exception

Tệp `src/main/java/com/example/reactiveerrors/OrderView.java`:

```java
package com.example.reactiveerrors;

public record OrderView(String id, String state) {}
```

Tệp `src/main/java/com/example/reactiveerrors/OrderNotFoundException.java`:

```java
package com.example.reactiveerrors;

public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(String id) {
        super("Order " + id + " not found");
    }
}
```

Tệp `src/main/java/com/example/reactiveerrors/InvalidOrderIdException.java`:

```java
package com.example.reactiveerrors;

public final class InvalidOrderIdException extends RuntimeException {
    public InvalidOrderIdException() {
        super("Order id must not be blank");
    }
}
```

Dùng exception type riêng cho lỗi nghiệp vụ giúp tầng API map chúng sang 404 hoặc 400 có chủ đích. Không phân biệt lỗi chỉ bằng cách so sánh fragment string của `getMessage()`, vì thông báo có thể thay đổi theo locale hoặc refactor.

### 7.3. Gateway contract và service thật

Tệp `src/main/java/com/example/reactiveerrors/OrderGateway.java`:

```java
package com.example.reactiveerrors;

import reactor.core.publisher.Mono;

public interface OrderGateway {
    Mono<OrderView> findById(String id);
}
```

Tệp `src/main/java/com/example/reactiveerrors/OrderReader.java`:

```java
package com.example.reactiveerrors;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderReader {

    private final OrderGateway gateway;

    public OrderReader(OrderGateway gateway) {
        this.gateway = gateway;
    }

    public Mono<OrderView> find(String rawId) {
        if (rawId == null || rawId.isBlank()) {
            return Mono.error(new InvalidOrderIdException());
        }

        String normalizedId = rawId.trim();

        return Mono.defer(() -> gateway.findById(normalizedId))
                .switchIfEmpty(Mono.error(
                        () -> new OrderNotFoundException(normalizedId)));
    }
}
```

**Vì sao code này có ích khi chẩn đoán?**

- Đầu vào không hợp lệ được biểu diễn bằng **error signal**. Tầng gọi có thể assert `onError` mà không cần catch exception đồng bộ tại thời điểm gọi `find`.
- `Mono.defer(...)` trì hoãn lời gọi `gateway.findById` cho tới khi publisher được subscribe. Nếu gateway method ném exception đồng bộ bên trong `defer`, Reactor thường biến exception đó thành error signal cho subscriber.
- `switchIfEmpty` chỉ xử lý **publisher kết thúc mà không có item**, không tự đổi mọi lỗi `onError` thành “not found”.
- Lỗi từ gateway như `IllegalStateException("gateway unavailable")` **được truyền tiếp**; đây là lỗi hạ tầng, cần xử lý ở mức thích hợp thay vì chuyển nó thành 404.
- `OrderReader` là service thật. Trong unit test, chỉ `OrderGateway` được mock.

Một điểm tinh tế: `Mono.defer` thường tạo cold publisher, do đó **mỗi subscription** có thể gọi lại gateway. Đó là hành vi có chủ đích ở đây để dạy lifecycle subscription; đừng mặc định một publisher luôn chạy đúng một lần cho mọi subscriber.

### 7.4. Gateway in-memory để ứng dụng mẫu có thể khởi động

Tệp `src/main/java/com/example/reactiveerrors/InMemoryOrderGateway.java`:

```java
package com.example.reactiveerrors;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class InMemoryOrderGateway implements OrderGateway {

    @Override
    public Mono<OrderView> findById(String id) {
        return Mono.defer(() -> {
            if ("42".equals(id)) {
                return Mono.just(new OrderView("42", "PAID"));
            }
            return Mono.empty();
        });
    }
}
```

Đây là fake repository **cục bộ, không cần database**. Không đánh đồng một fake trả `Mono` với một driver R2DBC thật. Khi ứng dụng chạy, ID `42` trả thành công; các ID khác trả empty để `OrderReader` biến thành lỗi nghiệp vụ.

Tệp `src/main/java/com/example/reactiveerrors/ReactiveErrorsApplication.java`:

```java
package com.example.reactiveerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorsApplication.class, args);
    }
}
```

Ứng dụng dùng package cha trùng với các class của ví dụ, để Spring tìm controller, service, advice và gateway. Đó là một ứng dụng WebFlux tối giản có thể chạy khi dependencies/runtime hợp lệ, không tích hợp cơ sở dữ liệu thật.

### 7.5. Unit test: StepVerifier assert terminal signals

Tệp `src/test/java/com/example/reactiveerrors/OrderReaderTest.java`:

```java
package com.example.reactiveerrors;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderReaderTest {

    @Mock
    OrderGateway gateway;

    @Test
    void gatewayIsNotCalledUntilSubscription() {
        OrderView expected = new OrderView("42", "PAID");
        when(gateway.findById("42"))
                .thenReturn(Mono.just(expected));

        OrderReader reader = new OrderReader(gateway);
        Mono<OrderView> result = reader.find(" 42 ");

        // Chỉ assemble; chưa có subscription của result.
        verifyNoInteractions(gateway);

        StepVerifier.create(result)
                .expectNext(expected)
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        verify(gateway).findById("42");
    }

    @Test
    void emptyGatewayResultBecomesNotFoundError() {
        when(gateway.findById("404"))
                .thenReturn(Mono.empty());

        OrderReader reader = new OrderReader(gateway);

        StepVerifier.create(reader.find("404"))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                            OrderNotFoundException.class, error);
                    assertEquals(
                            "Order 404 not found",
                            error.getMessage());
                })
                .verify(Duration.ofSeconds(3));

        verify(gateway).findById("404");
    }

    @Test
    void invalidIdReturnsInputErrorWithoutGatewayCall() {
        OrderReader reader = new OrderReader(gateway);

        StepVerifier.create(reader.find(" "))
                .expectError(InvalidOrderIdException.class)
                .verify(Duration.ofSeconds(3));

        verifyNoInteractions(gateway);
    }

    @Test
    void gatewayFailureIsNotMisreportedAsNotFound() {
        when(gateway.findById("42")).thenReturn(
                Mono.error(new IllegalStateException(
                        "gateway unavailable")));

        OrderReader reader = new OrderReader(gateway);

        StepVerifier.create(reader.find("42"))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "gateway unavailable".equals(
                                error.getMessage()))
                .verify(Duration.ofSeconds(3));

        verify(gateway).findById("42");
    }

    @Test
    void twoSubscriptionsCanRepeatColdSourceWork() {
        AtomicInteger sourceSubscriptions = new AtomicInteger();
        when(gateway.findById("42")).thenAnswer(call ->
                Mono.defer(() -> {
                    sourceSubscriptions.incrementAndGet();
                    return Mono.just(new OrderView("42", "PAID"));
                }));

        OrderReader reader = new OrderReader(gateway);
        Mono<OrderView> pending = reader.find("42");

        StepVerifier.create(pending)
                .expectNext(new OrderView("42", "PAID"))
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        StepVerifier.create(pending)
                .expectNext(new OrderView("42", "PAID"))
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertEquals(2, sourceSubscriptions.get());
        verify(gateway, times(2)).findById("42");
    }
}
```

### 7.6. Những gì bài test thật sự chứng minh

| Ca test | Kết luận có cơ sở |
|---|---|
| `gatewayIsNotCalledUntilSubscription` | Service lắp publisher lazy; gateway chỉ được gọi khi StepVerifier subscribe |
| `emptyGatewayResultBecomesNotFoundError` | Empty được chuyển thành `OrderNotFoundException`, không phải HTTP 404 trực tiếp |
| `invalidIdReturnsInputErrorWithoutGatewayCall` | Input sai phát đúng error signal; gateway không bị gọi |
| `gatewayFailureIsNotMisreportedAsNotFound` | Lỗi hạ tầng được giữ khác loại lỗi nghiệp vụ |
| `twoSubscriptionsCanRepeatColdSourceWork` | Hai subscriber có thể tái kích hoạt upstream và source side effects |

**Không có `System.out.println` trong các test**, nên không đưa một stdout cố định. Với dependencies phù hợp và mã ví dụ ở trên, năm test được thiết kế để đạt; phải chạy đúng test trong dự án trước khi báo cáo chúng thực sự đã pass.

`StepVerifier.verify(Duration.ofSeconds(3))` cung cấp giới hạn thời gian cho bước kiểm chứng, giúp báo lỗi khi pipeline không hoàn tất. Nó **không** làm một thao tác blocking trở nên non-blocking hoặc tự phát hiện mọi deadlock. Khi kiểm thử time operators phức tạp, có thể dùng `StepVerifier.withVirtualTime` theo hướng dẫn Reactor, với yêu cầu publisher được tạo theo cách tương thích với virtual scheduler.

## 8. Test HTTP contract: chuyển lỗi nghiệp vụ thành 404 qua WebFlux

Một service test chứng minh `OrderNotFoundException` được phát dưới dạng `onError`; nó chưa chứng minh client sẽ nhận HTTP 404. Đó là trách nhiệm của controller/advice và được kiểm tra bằng `WebTestClient`.

### 8.1. Controller trả publisher, không block/subscribe

Tệp `src/main/java/com/example/reactiveerrors/OrderController.java`:

```java
package com.example.reactiveerrors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderReader reader;

    public OrderController(OrderReader reader) {
        this.reader = reader;
    }

    @GetMapping("/{id}")
    public Mono<OrderView> find(@PathVariable("id") String id) {
        return reader.find(id);
    }
}
```

Controller không tự `.block()`, `.subscribe()` hay `.toFuture().get()`: publisher được WebFlux xử lý trong request lifecycle.

### 8.2. Advice tách 404 nghiệp vụ khỏi 400 đầu vào

Tệp `src/main/java/com/example/reactiveerrors/OrderErrorAdvice.java`:

```java
package com.example.reactiveerrors;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            OrderNotFoundException error) {
        return ResponseEntity.status(404)
                .body(Map.of("code", "ORDER_NOT_FOUND"));
    }

    @ExceptionHandler(InvalidOrderIdException.class)
    public ResponseEntity<Map<String, String>> invalidId(
            InvalidOrderIdException error) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_ORDER_ID"));
    }
}
```

Chỉ hai exception nghiệp vụ được map ở đây. Một lỗi `IllegalStateException("gateway unavailable")` từ gateway không bị advice trên biến thành 404/400; ứng dụng sẽ xử lý theo global error handling đối với lỗi chưa được map, thường là server error. Mã HTTP cuối cùng phụ thuộc cấu hình exception handlers và error attributes, nên đừng khẳng định một JSON 500 cụ thể khi chưa kiểm chứng.

### 8.3. Web slice test với WebTestClient

Tệp `src/test/java/com/example/reactiveerrors/OrderControllerWebFluxTest.java`:

```java
package com.example.reactiveerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = OrderController.class)
class OrderControllerWebFluxTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    OrderReader reader;

    @Test
    void successfulPublisherBecomesHttp200WithJson() {
        when(reader.find("42"))
                .thenReturn(Mono.just(
                        new OrderView("42", "PAID")));

        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.state").isEqualTo("PAID");

        verify(reader).find("42");
    }

    @Test
    void businessErrorBecomesHttp404WithStableCode() {
        when(reader.find("404")).thenReturn(
                Mono.error(new OrderNotFoundException("404")));

        client.get()
                .uri("/api/orders/404")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("ORDER_NOT_FOUND");

        verify(reader).find("404");
    }
}
```

Với Spring Boot 3.4/3.5 và Spring Framework 6.2+, `@MockitoBean` thuộc package `org.springframework.test.context.bean.override.mockito`. Trên Boot cũ hơn, annotation này có thể chưa tồn tại; phải dùng cơ chế mock bean tương ứng với phiên bản. `@WebFluxTest` nạp controller/advice trong phạm vi web slice và thường auto-configure `WebTestClient` bind-to-context, **không mở HTTP port thật**.

Hai test web được thiết kế để đạt khi cấu hình WebFlux/Jackson và advice đã nạp đúng. Chúng chứng minh HTTP status/JSON contract của MVC-reactive handler đang chạy với reader **mock**, không chứng minh `OrderReader` thật đã được gọi. Vì vậy, phải giữ **cả StepVerifier service test ở mục 7 lẫn WebTestClient test ở mục 8** nếu muốn kiểm tra đủ hai ranh giới.

## 9. Kiểm tra thực sự có blocking: không đánh đồng với lỗi nghiệp vụ

Khi nghi ngờ một request treo do blocking, thứ tự điều tra có ích:

1. Xác định **đường đi**: controller WebFlux → service → gateway/client → operator nào.
2. Tìm `.block()`, `.blockFirst()`, `.blockLast()`, `Thread.sleep`, `Future.get()`, JDBC sync, SDK sync hoặc `RestTemplate` bên trong handler/reactive callback.
3. Đọc exception root cause. Thông báo từ Reactor về “blocking is not supported in thread ...” chỉ ra việc gọi blocking Reactor API trên thread non-blocking; một `ReadTimeoutException` có thể là lỗi network, không chứng minh `.block()` xảy ra.
4. Quan sát thread name và thread dump nếu có latency/timeout nhưng **không có exception**. Netty event-loop thread bị giữ bởi blocking I/O có thể làm nhiều request chậm, dù không hề ném đúng `IllegalStateException`.
5. Xác định operator nào được subscribe và nơi bắt đầu work. `publishOn`/ `subscribeOn` ảnh hưởng scheduling theo cách khác nhau; đặt scheduler sau một lời gọi eager không khắc phục blocking đã xảy ra.
6. Kiểm chứng lại bằng test đo behavior, giới hạn timeout và telemetry; đừng chỉ thêm `onErrorResume` để nuốt lỗi.

### 9.1. subscribeOn và publishOn khác nhau

- `subscribeOn(scheduler)` ảnh hưởng ngữ cảnh thực thi **subscription/request tới upstream** và thường được dùng sát nguồn blocking được bọc trong `fromCallable`. Nó không biến I/O thành nonblocking.
- `publishOn(scheduler)` chuyển **các signals downstream** sang scheduler chỉ định từ vị trí operator đó. Nó không “quay ngược thời gian” để chuyển một thao tác blocking đã thực thi khi assembly.
- Scheduler được cấu hình sai có thể tạo tắc nghẽn hoặc tăng độ trễ. Dùng `boundedElastic` có chủ đích cho phần blocking khó thay thế, ưu tiên WebClient/R2DBC cho đường nonblocking khi phù hợp.

### 9.2. BlockHound là công cụ bổ trợ, không phải bằng chứng tự động

Trong một số dự án Reactor, **BlockHound** có thể phát hiện những API blocking được biết khi chúng chạy trên thread được xác định là non-blocking. Tuy nhiên nó là công cụ bên ngoài, cần instrumentation và có điều kiện tương thích với JDK/agent/runtime. Không nên viết “có Reactor thì mọi JDBC hoặc `sleep` sẽ tự ném lỗi” — điều đó sai. Test nên dựa trên thread observation, profiling, latency và đường gọi, kết hợp BlockHound khi phiên bản/hạ tầng cho phép.

## 10. Chẩn đoán subscription và thời điểm phát lỗi

Một pipeline có thể được lắp ở thời điểm A và chỉ chạy tại thời điểm B. Đây là lý do stack trace đôi khi có hai vùng thông tin: **assembly site** và **subscription/execution site**.

Các công cụ Reactor hữu ích:

| Công cụ | Cho biết điều gì? | Lưu ý |
|---|---|---|
| `doOnSubscribe` | Publisher bắt đầu có subscriber | Dùng để quan sát, không tự tạo subscription |
| `doOnNext` | Giá trị `onNext` đi qua | Không thấy tín hiệu empty hoặc error nếu không có value |
| `doOnError` | Lỗi đi qua vị trí operator | Không xử lý lỗi; error vẫn tiếp tục |
| `doFinally` | Kết thúc bằng complete, error hoặc cancel | Hữu ích cho cleanup/metrics terminal |
| `checkpoint("read-order")` | Thêm assembly marker để tìm pipeline gây lỗi | Có chi phí; chọn vị trí có ý nghĩa |
| `log()` | Quan sát subscribe/request/onNext/onError/cancel | Cẩn thận độ ồn và dữ liệu nhạy cảm |
| `Hooks.onOperatorDebug()` | Ghi thêm assembly stack information ở phạm vi rộng | Có overhead lớn; không bật vô hạn trong production |
| `StepVerifier` | Subscriber kiểm chứng signals | Không thay cho WebFlux HTTP test |
| `WebTestClient` | Status/header/body theo request | Không tự phát hiện lỗi trong subscription phụ fire-and-forget |

Ví dụ minh họa trong service đã có gateway:

```java
return gateway.findById(id)
        .checkpoint("lookup-order-" + id)
        .doOnSubscribe(subscription ->
                logger.debug("subscribed order lookup"))
        .doOnError(error ->
                logger.warn("lookup failed", error));
```

`logger` là logging dependency của ứng dụng (đoạn không độc lập). Trong production, tránh đưa ID bí mật, token, payload hay thông tin nhạy cảm vào checkpoint/log nếu không cần. Đừng bật debug hooks toàn JVM như một cách sửa nghiệp vụ.

Một exception có dạng `ErrorCallbackNotImplemented` thường gợi ý subscriber không có error consumer phù hợp. Dấu hiệu `onErrorDropped` có thể liên quan một tín hiệu không còn downstream tiêu thụ được, ví dụ sau cancellation hoặc do lỗi xảy ra ngoài publisher mà HTTP đang quản lý. **Không suy ra chắc chắn một nguyên nhân duy nhất từ thông báo log**; tìm `.subscribe(...)`, operator, cancellation và tình huống xảy ra lỗi.

## 11. Test reactive đúng cách: StepVerifier, WebTestClient và timeout

### 11.1. StepVerifier kiểm tra publisher ở mức signal

Một test chỉ viết:

```java
reader.find("404");
```

thường chỉ **lắp publisher**, chưa có subscriber; nếu `find` trả `Mono.defer` thì gateway còn chưa chạy. Test đó không thể chứng minh lỗi `OrderNotFoundException` được phát.

Một test chỉ viết:

```java
reader.find("404").subscribe();
```

có thể tạo subscription nhưng **không có assertion**, không chờ completion và không có error consumer. Nó có thể kết thúc test trước khi lỗi xảy ra, hoặc log lỗi từ thread khác.

Dùng:

```java
StepVerifier.create(reader.find("404"))
        .expectError(OrderNotFoundException.class)
        .verify(Duration.ofSeconds(3));
```

Đây là đoạn minh họa từ test với `reader` được cấu hình hợp lệ và imports Reactor Test. `StepVerifier` subscribe, nhận terminal signal và verify điều kiện trong giới hạn thời gian. Nếu muốn kiểm tra message/cause, dùng `expectErrorSatisfies` như mã đầy đủ ở mục 7.

### 11.2. Mono<Void> và Flux cần kiểu assertion thích hợp

- `Mono<Void>` thành công thường **không có `onNext`**: dùng `StepVerifier.create(publisher).verifyComplete()` hoặc `expectComplete().verify(timeout)` theo nhu cầu.
- `Mono.empty()` hoàn tất rỗng, khác `Mono.error`. Đừng coi completion rỗng là bằng chứng không tìm thấy nếu hợp đồng chưa định nghĩa.
- `Flux<T>` có nhiều `onNext`; `expectNext`, `expectNextCount`, `recordWith`, `consumeRecordedWith` có thể giúp xác minh phần tử và thứ tự. Nếu thứ tự không được bảo đảm bởi hợp đồng hoặc scheduler, chọn assertion không quá chặt nhưng vẫn giữ số lần xuất hiện khi cần.
- Publisher `never()` không hoàn tất: test cần cancel/timeout có chủ đích; chờ vô hạn không có giá trị.
- Với luồng streaming dài hạn/SSE, client và test phải xử lý cancellation, backpressure và timeout chứ không đợi `verifyComplete()` mãi.

### 11.3. WebTestClient xác minh API, không thay service test

`WebTestClient` giúp kiểm tra HTTP status, headers và JSON. Với `@WebFluxTest` + service mock, nó có thể chứng minh 404 mapping của `OrderNotFoundException` nhưng **không chứng minh** gateway thật không block hoặc không double subscribe. Ngược lại, `StepVerifier` kiểm tra `OrderReader` thật, nhưng **không tự kiểm tra** HTTP error schema.

Muốn kiểm chứng đường HTTP thực qua network, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` với WebTestClient gắn tới server phù hợp, khác với client bind-to-context của slice. Nếu lỗi chỉ xuất hiện dưới tải/concurrency và do Netty event-loop bị chiếm, cần thêm integration/performance test đo latency/throughput thật với môi trường có kiểm soát.

### 11.4. Đừng để timeout trở thành cách che lỗi

`timeout(Duration)` trong reactive pipeline có thể phát `TimeoutException` khi quá lâu. Nhưng nó không giải quyết thao tác I/O blocking hoặc task đã tách subscription có lifecycle riêng. Trong test, dùng `verify(Duration)`/response timeout để tránh treo; trong production, chọn timeout/retry/bulkhead và error mapping theo hợp đồng.

**Retry phải có điều kiện:** `retryWhen` với lỗi network tạm thời có thể hợp lý, nhưng retry lỗi validation/nghiệp vụ thường vô ích. Với POST tạo đơn hàng, retry không có idempotency key có thể làm lặp side effect. Đừng dùng retry vô hạn chỉ để che race hoặc lỗi subscribe sai.

## 12. Chạy bộ test và kiểm tra tín hiệu thay vì chỉ nhìn build xanh

Với Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.reactiveerrors.OrderReaderTest"
./gradlew test --tests "com.example.reactiveerrors.OrderControllerWebFluxTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.reactiveerrors.OrderReaderTest"
.\gradlew.bat test --tests "com.example.reactiveerrors.OrderControllerWebFluxTest"
```

Với Maven wrapper trên Linux/macOS:

```bash
./mvnw -Dtest=OrderReaderTest test
./mvnw -Dtest=OrderControllerWebFluxTest test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=OrderReaderTest test
.\mvnw.cmd -Dtest=OrderControllerWebFluxTest test
```

Các lệnh giả định dự án có wrapper, Java 17+, Spring Boot 3.4/3.5, Maven/Gradle/JUnit Platform tương thích. Gradle task `test` thường có HTML report ở `build/reports/tests/test/index.html`; Maven Surefire có reports trong `target/surefire-reports/`. Trong multi-module project, cần chạy đúng task/module tương ứng.

Khi xem report hãy xác nhận:
1. Đúng **tên lớp và số test** được khám phá (năm test service, hai test web slice trong ví dụ).
2. `StepVerifier` đã subscribe và kiểm tra **onError/onComplete** chứ không chỉ tạo publisher.
3. WebTestClient assert status/JSON theo hợp đồng (200 và 404 của ví dụ).
4. Không có `timeout`, dropped-error hay Reactor scheduler exception bị bỏ qua trong logs.
5. Không có test bị **SKIPPED**, `NO-SOURCE` hoặc chỉ dựa vào build cache mà không kiểm tra lần thực thi thực tế.

Không có stdout nghiệp vụ cố định trong các test này. **Không tuyên bố code đã được chạy** chỉ vì nó được biên soạn; phải thực thi và đọc report thật mới có bằng chứng PASS.

## 13. Tình huống thực tế: lỗi nằm ở domain, gateway hay subscription?

### Tình huống A: không tìm thấy đơn hàng

**Tín hiệu:** gateway `Mono.empty()`, service `switchIfEmpty(Mono.error(OrderNotFoundException))`, advice map 404.

**Bài test:** StepVerifier assert `OrderNotFoundException`; WebTestClient assert HTTP 404 và `code=ORDER_NOT_FOUND`.

**Không sửa bằng:** trả `Mono.just(new OrderView(...))` giả hoặc nuốt lỗi 404 thành 200 rỗng nếu API hợp đồng yêu cầu 404.

### Tình huống B: gateway tạm thời mất kết nối

**Tín hiệu:** gateway `Mono.error(ConnectionException/TimeoutException)`; service không đổi thành not-found.

**Bài test:** StepVerifier assert đúng loại/cause, kiểm tra retry chính sách nếu có; integration test phù hợp có thể kiểm tra error mapping 503/500.

**Không sửa bằng:** `onErrorResume(e -> Mono.empty())` cho tất cả exception, vì nó che incident.

### Tình huống C: controller gọi block() trên event loop

**Dấu hiệu:** exception kiểu Reactor blocking-call restriction hoặc latency/tắc event-loop nếu loại blocking API không bị bắt.

**Bài test:** soát controller path, stack trace, thread name; test WebFlux với publisher đúng và chạy concurrency/performance test khi cần. Không mong chỉ riêng test đơn lẻ tự phát hiện mọi blocking source.

**Sửa:** return publisher và giữ các call nonblocking, hoặc bọc legacy blocking source bằng `fromCallable(...).subscribeOn(boundedElastic())` trong lúc chuyển đổi kiến trúc.

### Tình huống D: subscribe() thủ công để gửi email/audit

**Dấu hiệu:** response thành công trước khi task hoàn tất; lỗi xuất hiện dưới dạng log không gắn với response; retry/cancel ngữ nghĩa không rõ.

**Bài test:** xác minh publisher được nối vào response `Mono<Void>` nếu contract cần đợi; với async job thật, kiểm tra publish/queue theo hợp đồng và trạng thái job độc lập.

**Sửa:** `return emailService.send(...)` hoặc dùng queue/outbox đã thiết kế; không tự fire-and-forget trong handler theo thói quen.

### Tình huống E: test không subscribe nên giả tưởng mọi việc đã chạy

**Dấu hiệu:** test xanh dù gateway không được gọi, logger trong `Mono.defer` không chạy.

**Sửa:** dùng `StepVerifier` có expectation và timeout; `verify` interaction sau subscription nếu cần chứng minh side effect.

### Tình huống F: hai subscriptions sinh hai lần tính phí

**Dấu hiệu:** cùng business operation bị gọi hai lần từ cold publisher; log/metrics có hai subscriptions.

**Sửa:** đừng tạo subscriber phụ chỉ để log; dùng `doOnNext`, `doOnError` hoặc cấu trúc pipeline một nguồn, một consumer; nếu chia sẻ phải có chính sách idempotency và lifecycle rõ. Với thao tác ghi, đảm bảo idempotency ở tầng nghiệp vụ chứ không dựa vào `Mono.cache()` cục bộ.

## 14. Lỗi chẩn đoán thường gặp

| Sai lầm | Vì sao dẫn tới kết luận sai | Cách sửa |
|---|---|---|
| Thấy 500 và coi đó là lỗi business | 500 cũng có thể do `.block()`, codec, gateway hoặc cấu hình | Đọc root cause, thread, signal và mapping |
| `Mono.error` được tạo nhưng test không subscribe | Error signal có thể chưa được phát | Dùng StepVerifier và assert terminal signal |
| `subscribe()` trong controller rồi `return Mono.empty()` | Lỗi của công việc phụ không thuộc response | Return đúng publisher hoặc thiết kế async job rõ ràng |
| `subscribe()` để “bắt đầu” một cold publisher rồi lại return nó | Có thể chạy upstream hai lần | Giữ một subscription do WebFlux quản lý |
| `Mono.just(blockingCall())` rồi `subscribeOn(boundedElastic)` | Blocking đã xảy ra tại assembly | Dùng `Mono.fromCallable` cho nguồn blocking |
| Tin `block()` sẽ luôn ném IllegalStateException | Trên thread không bị đánh dấu non-blocking, nó có thể chỉ làm chậm | Không dùng block trong handler; đo thread/latency |
| Dùng `map` để trả `Mono<Mono<T>>` | Publisher bên trong chưa được flatten | Dùng `flatMap` khi callback trả publisher |
| Dùng `onErrorComplete()` để test xanh | Nuốt lỗi có thể che incident | Phân loại và xử lý lỗi theo hợp đồng |
| `doOnError` được coi là exception handler | Nó chỉ quan sát lỗi | Giữ downstream error hoặc `onErrorResume` có điều kiện |
| Mặc định `Mono.empty()` là HTTP 404 | Empty không mang status code | Map bằng `switchIfEmpty`/ResponseEntity theo API |
| Mockito mock reactive method trả null | Handler gặp NPE không liên quan domain | Stub bằng publisher không null |
| Chỉ test WebTestClient với service mock | Không kiểm tra service reactive thật có block/double subscribe | Bổ sung StepVerifier service/integration test |
| `verifyComplete()` trên infinite Flux | Test có thể không kết thúc | Hủy subscription hoặc giới hạn stream/timeout |
| Dựa vào stdout/log như assertion duy nhất | Log có thể thiếu hoặc bị lọc | Assert values, error types, status và interactions |
| `retryWhen` cho mọi exception | Có thể retry validation hoặc tạo side effect trùng | Chỉ retry transient errors, dùng idempotency |
| Dùng một JVM để kết luận cùng ThreadLocal context | Reactive execution có scheduler/context riêng | Quan sát execution path và dùng Reactor Context đúng thiết kế |

## 15. Checklist trước khi kết luận một WebFlux test đã bảo vệ đúng lỗi

- [ ] Đã phân loại rõ **business validation/not-found**, **downstream infrastructure error** và **reactive programming misuse**.
- [ ] Controller/service trả `Mono`/`Flux` cho framework, không `.block()` hoặc `.subscribe()` vô cớ trong request path.
- [ ] Khi buộc dùng blocking API legacy, đã đặt việc gọi trong publisher lazy và scheduler thích hợp, không đánh giá eager trong `Mono.just`.
- [ ] Test service dùng StepVerifier **thật sự subscribe**, assert `onNext/onError/onComplete` và có timeout phù hợp.
- [ ] Test HTTP dùng WebTestClient assert status, header và error JSON; không gộp kết luận service thật vào slice có mock.
- [ ] `Mono.empty()` được map theo hợp đồng; không tự xem đó là 404.
- [ ] Không nuốt lỗi gateway bằng `onErrorResume`/`onErrorComplete` quá rộng.
- [ ] Có kiểm tra trường hợp subscription lặp gây side effect lặp nếu nghiệp vụ nhạy cảm.
- [ ] Không coi `doOnError` hoặc `log` là giải pháp xử lý/kiểm thử lỗi.
- [ ] Đã kiểm tra scheduler/thread khi nghi blocking, thay vì đoán từ status code.
- [ ] Với streaming, đã xử lý cancellation/backpressure và không đợi vô hạn.
- [ ] Đã chạy đúng test task/lớp và kiểm tra report, không tuyên bố PASS chỉ từ đoạn code minh họa.

**Kết luận:** Trong Spring WebFlux, cần phân biệt **lỗi mà ứng dụng chủ động phát ra** với **lỗi do quản lý subscription/thread không đúng**. `Mono.error` của domain, gateway failure và `IllegalStateException` do `.block()` trên event loop có ý nghĩa rất khác nhau. Để chẩn đoán đáng tin cậy, giữ **một reactive pipeline được WebFlux subscribe**, không fire-and-forget bằng `.subscribe()` trong handler, không blocking trên event loop, dùng `StepVerifier` kiểm tra signals và `WebTestClient` kiểm tra HTTP contract, rồi đối chiếu thread, stack trace và dữ liệu đã thực sự được phát.