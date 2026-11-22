# Những sai lầm với `block()`, `subscribe()` thủ công và tác vụ ngoài chuỗi reactive

## 1. Mục tiêu học tập và phạm vi

Trong Spring WebFlux, các API trả về `Mono<T>` hoặc `Flux<T>` cho phép ghép những công việc bất đồng bộ thành một chuỗi Reactor. Tuy nhiên, một đoạn code có thể sử dụng đúng kiểu `Mono`/`Flux` mà vẫn làm hỏng mô hình reactive nếu tác giả tự chặn thread, tự kích hoạt subscription hoặc đưa tác vụ ra khỏi pipeline. Các sai lầm này đặc biệt nguy hiểm trong ứng dụng dùng **Spring Security Reactive**, vì danh tính và quyền của người dùng được gắn với **Reactor Context** của subscription.

Sau bài học, bạn sẽ:
- Biết khi nào `block()` là sai trong một luồng request WebFlux và khi nào chờ đồng bộ chỉ nên xuất hiện tại ranh giới ngoài cùng.
- Hiểu tại sao controller/service WebFlux thường phải **trả về Publisher** để framework sở hữu subscription, thay vì tự gọi `subscribe()`.
- Nhận diện lỗi “tạo `Mono` nhưng không ai subscribe”, lỗi “fire-and-forget” và công việc chạy bằng `Thread`, `CompletableFuture` hoặc `@Async` tách khỏi request.
- Giữ đúng propagation của dữ liệu, lỗi, cancellation và `ReactiveSecurityContextHolder` khi dùng `flatMap`, `then`, `contextWrite` và scheduler.
- Biết cách cô lập API blocking bất khả kháng và cách thiết kế tác vụ thực sự phải tiếp tục sau khi HTTP response kết thúc.

**Phạm vi:** đây là bài nền tảng Reactor trong module Spring Security Reactive. Ví dụ dùng Java 17+, Reactor Core và một số đoạn tích hợp WebFlux/Spring Security minh họa. Nội dung tập trung vào cơ chế pipeline, subscription và context; không xây dựng lại toàn bộ hệ thống đăng nhập.

## 2. Mô hình cần hiểu trước: Publisher là mô tả công việc

Khi viết:

~~~java
Mono<String> work = Mono.fromSupplier(() -> readValue());
~~~

ta đang **tạo mô tả cho việc đọc dữ liệu**, chưa nhất thiết thực hiện `readValue()`. Với loại nguồn `fromSupplier` này, mã trong supplier chạy khi có subscription. Những toán tử như `map`, `flatMap`, `filter`, `onErrorResume` thường ghép thêm các bước mà chưa kích hoạt chúng.

Một cách hình dung:

~~~text
Controller trả về Mono/Flux
          |
          v
Framework subscribe vào publisher được trả về
          |
          v
Nguồn dữ liệu -> map/flatMap -> security context -> response
          |             |                   |
          +----- lỗi / hủy / tín hiệu hoàn thành -----+
~~~

`subscribe()` là một **ranh giới thực thi**: khi có subscriber, Publisher bắt đầu phát tín hiệu `onNext`, `onError`, `onComplete` theo hợp đồng Reactive Streams. Trong WebFlux, framework điều phối subscription cho publisher mà handler trả về, qua đó quản lý response và liên hệ với vòng đời request.

Không phải mọi Publisher đều “cold”: có nguồn hot, multicast hoặc đã được `cache`/ `share`. Nhưng các nguồn thường dùng như `Mono.fromCallable`, `Mono.defer` và nhiều chuỗi truy vấn dữ liệu được xây dựng theo lối **lazy**, nên việc không subscribe dẫn đến “không chạy”. `Mono.just(expensiveCall())` là ngoại lệ cần nhớ: lời gọi `expensiveCall()` đã xảy ra **ngay khi tạo** `Mono.just`, trước subscription. Nếu muốn trì hoãn một lời gọi đồng bộ để mô tả bằng Publisher, dùng `fromSupplier` hoặc `fromCallable` thích hợp.

Một pipeline đúng tạo ra **một chuỗi có liên kết** mà downstream có thể nhận được giá trị, lỗi, completion và tín hiệu hủy. Ba lỗi trong bài đều phá vỡ một hoặc nhiều liên kết đó.

## 3. Sai lầm thứ nhất: gọi `block()` bên trong WebFlux

### 3.1. `block()` thực sự làm gì?

`Mono.block()` subscribe vào `Mono`, sau đó **chặn thread hiện tại** cho tới khi có giá trị, hoàn thành rỗng hoặc phát sinh lỗi. `Flux.blockFirst()` và `Flux.blockLast()` có vấn đề tương tự.

Ví dụ sai trong controller WebFlux:

~~~java
// Ví dụ SAI; các service và controller chỉ minh họa, không chạy độc lập.
@GetMapping("/users/{id}")
public Mono<UserDto> user(@PathVariable String id) {
    UserDto user = userService.findById(id).block();
    return Mono.just(user);
}
~~~

Vấn đề:
1. Handler có thể đang chạy trên **event-loop** của Reactor Netty. Chặn event-loop sẽ ngăn nó xử lý các request khác; các blocking API của Reactor trên thread đánh dấu non-blocking thường ném `IllegalStateException` với thông báo blocking không được hỗ trợ.
2. `block()` tạo subscription riêng và kết thúc phần reactive sớm. Logic retry, timeout, cancellation hoặc context do request bao quanh có thể không còn kết nối như mong đợi.
3. Nếu nguồn phát `Mono.empty()`, `block()` có thể trả `null`, và `Mono.just(null)` lại không hợp lệ.
4. Với số lượng request lớn, giữ nhiều thread trong trạng thái chờ gây giảm thông lượng và tăng độ trễ.

Cách đúng: trả luôn publisher, hoặc tiếp tục biến đổi nó bằng các toán tử:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> user(@PathVariable String id) {
    return userService.findById(id);
}
~~~

Nếu cần kiểm tra dữ liệu và gọi một service reactive khác:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> user(@PathVariable String id) {
    return userService.findById(id)
            .flatMap(user -> permissionService.verifyCanRead(user)
                    .thenReturn(user));
}
~~~

`verifyCanRead` trong ví dụ trả về `Mono<Void>`: hoàn thành thành công nghĩa là được phép; lỗi được phát ra qua pipeline để tầng xử lý lỗi/authorization thích hợp quyết định response. Đoạn này là ví dụ tích hợp, cần định nghĩa các service tương ứng để chạy.

### 3.2. Nguy cơ đặc biệt khi `block()` để lấy SecurityContext

Ví dụ sai:

~~~java
String username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block(); // SAI trong WebFlux handler/service
~~~

`ReactiveSecurityContextHolder` đọc thông tin người gọi từ **Reactor Context của subscription**, không từ một biến global. `block()` tự tạo subscription khác; ngoài nguy cơ chặn thread, subscription mới không được bảo đảm có Reactor Context đã gắn với request gốc. Kết quả có thể vắng context hoặc phát sinh lỗi.

Cách đúng:

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
~~~

Sau đó dùng `flatMap` để tiếp tục tác vụ cần danh tính:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .flatMap(username -> orderService.findOrdersForUser(username));
~~~

Đừng biến `Mono<SecurityContext>` thành `SecurityContext` đồng bộ chỉ để sử dụng được cú pháp quen thuộc của Spring MVC.

### 3.3. Có khi nào `block()` được phép?

Có, ở **ranh giới ngoài Reactor** do bạn kiểm soát, chẳng hạn:
- Hàm `main` của một chương trình console muốn chờ chương trình hoàn thành.
- Một thử nghiệm đồng bộ hoặc mã tích hợp với API đồng bộ, khi thread hiện tại không phải thread non-blocking và tác động chặn đã được đánh giá.
- Đoạn chuyển đổi ở lớp biên mà ứng dụng không còn vận hành như một WebFlux request.

Dùng `block()` ở `main` **không** biến nó thành công cụ hợp lệ trong controller, WebFilter hoặc service thuộc pipeline WebFlux. Đừng dùng `block()` như cách “chữa” code thiếu `flatMap`.

## 4. Sai lầm thứ hai: gọi `subscribe()` thủ công trong controller hoặc service

### 4.1. Sai kiểu “tôi đã gọi service rồi”

Giả sử `auditService.save` trả về `Mono<Void>`:

~~~java
// SAI: tạo Mono nhưng không đưa vào pipeline; có thể hoàn toàn không ghi audit.
return orderService.findById(orderId)
        .doOnNext(order -> auditService.save(order));
~~~

`doOnNext` nhận callback dùng cho quan sát hoặc tác dụng phụ **đồng bộ, nhanh**. Callback này chỉ tạo ra một `Mono` mới mà không ghép nó vào chuỗi; đối với một service lazy, việc lưu audit chưa được thực hiện.

Một bản “sửa nhanh” vẫn sai:

~~~java
// SAI: fire-and-forget; subscription thứ hai tách khỏi response.
return orderService.findById(orderId)
        .doOnNext(order -> auditService.save(order).subscribe());
~~~

Tự gọi `subscribe()` làm xuất hiện **hai subscription độc lập**: một của request/response, một của việc ghi audit. Hệ quả có thể xảy ra:

- Response hoàn thành trước khi audit kết thúc; nếu audit lỗi, request ban đầu không nhận được lỗi đó.
- Request bị hủy (ví dụ client ngắt kết nối) không đương nhiên hủy tác vụ đã subscribe riêng.
- Không có sự bảo đảm context của request, đặc biệt là `ReactiveSecurityContextHolder`, được truyền sang subscriber mới.
- Việc retry hoặc timeout ở pipeline chính không kiểm soát được tác vụ phụ.
- Các overload `subscribe` dùng callback đơn giản thường yêu cầu dữ liệu không giới hạn ngay từ đầu; với `Flux` lớn có thể làm khó quản lý backpressure.
- Subscription không được quản lý có thể tiếp tục tiêu thụ tài nguyên sau khi request không còn cần kết quả.

**Cách đúng là ghép tác vụ phụ vào pipeline bằng `flatMap` rồi `thenReturn`:**

~~~java
return orderService.findById(orderId)
        .flatMap(order -> auditService.save(order)
                .thenReturn(order));
~~~

Cả hai bước cùng thuộc một subscription. Nếu `auditService.save` thất bại, lỗi đi vào cùng chuỗi; nếu bị hủy, tín hiệu hủy được truyền cho các publisher liên kết khi có thể. `thenReturn(order)` chờ publisher audit hoàn thành thành công rồi trả lại `order`. Điều này phù hợp khi nghiệp vụ **cần biết audit đã hoàn tất trước khi trả response**.

Nếu audit chỉ là phụ trợ và thất bại không được làm hỏng response, chính sách đó cũng phải được biểu diễn minh bạch trong pipeline, ví dụ `onErrorResume` kèm logging/metric phù hợp. Không ngầm nuốt lỗi của một bước quan trọng về bảo mật hoặc toàn vẹn dữ liệu.

### 4.2. Sai kiểu tự subscribe rồi trả response ngay

~~~java
// SAI: chưa chờ kết quả xác minh quyền.
public Mono<String> handle(String orderId) {
    permissionService.checkAccess(orderId).subscribe();
    return Mono.just("OK");
}
~~~

Hành vi thực tế nguy hiểm: response có thể trả `OK` dù kiểm tra quyền chưa xong hoặc đã thất bại. Chuyện kiểm tra authorization không được phép trở thành “tác vụ nền” tách khỏi quyết định cho truy cập.

Sửa:

~~~java
public Mono<String> handle(String orderId) {
    return permissionService.checkAccess(orderId)
            .thenReturn("OK");
}
~~~

Nếu `checkAccess` cần trả `Mono<Boolean>`, phải kiểm tra giá trị boolean bằng `flatMap`, **không** dùng `thenReturn("OK")` để vô tình bỏ qua `false`. Ví dụ:

~~~java
return permissionService.canAccess(orderId)
        .flatMap(allowed -> allowed
                ? Mono.just("OK")
                : Mono.error(new AccessDeniedException("Not allowed")));
~~~

`AccessDeniedException` ở đây là kiểu ngoại lệ của Spring Security; đoạn mã cần các import/service phù hợp. Khi triển khai, ưu tiên sử dụng các cơ chế authorization của Spring Security tại filter hoặc method và kiểm tra quyền theo đối tượng nghiệp vụ nơi cần thiết.

### 4.3. Khi nào tự `subscribe()` là đúng?

Tại **ranh giới cuối cùng** nơi một thành phần thực sự chịu trách nhiệm tiêu thụ Publisher, ví dụ một ứng dụng console, một service chủ động tích hợp sự kiện hoặc hạ tầng sở hữu vòng đời subscription. Khi đó thành phần phải tự quản lý:
- `Disposable` và cơ chế đóng/hủy.
- `onError`, completion và giới hạn tài nguyên.
- Backpressure hoặc chiến lược tải, khi xử lý `Flux`.
- Danh tính/context cần truyền và yêu cầu tồn tại sau khi caller rời đi.

Trong HTTP handler WebFlux thông thường, bạn **trả về `Mono`/`Flux`** và để WebFlux làm subscriber. Không tự subscribe trong cùng handler để “kích hoạt” thao tác.

## 5. Sai lầm thứ ba: đẩy tác vụ ra ngoài chuỗi reactive

Những mẫu có rủi ro thường gặp:

~~~java
new Thread(() -> sendNotification(orderId)).start();

CompletableFuture.runAsync(() -> auditRepository.write(orderId));

// Hoặc gọi một @Async method nhưng không gắn completion/error với Mono trả về.
~~~

Đây là mã minh họa cho anti-pattern, không phải một chương trình Java độc lập. Các tác vụ có thể chạy trên thread khác, thoát khỏi phạm vi lifecycle của request. Nếu dùng `SecurityContextHolder` kiểu `ThreadLocal` quen thuộc từ Servlet, chúng còn không có gì bảo đảm giữ được danh tính WebFlux gốc.

Phân biệt hai tình huống:

**A. Tác vụ phải hoàn tất để request được coi là thành công.** Giữ nó trong pipeline:

~~~java
return orderService.save(input)
        .flatMap(saved -> notificationService.sendReactive(saved)
                .thenReturn(saved));
~~~

Nếu cần hai nguồn dữ liệu độc lập, có thể dùng `Mono.zip`; nếu cần làm lần lượt, dùng `flatMap`, `then`, `concatMap`... tùy điều kiện thứ tự. Điều cốt lõi là publisher được **compose** vào kết quả trả về.

**B. Tác vụ có thể tiếp tục đáng tin cậy sau khi trả HTTP response.** Khi đó nó **thực sự có vòng đời riêng** và không nên bí mật dựa vào subscription của request. Dùng cơ chế có owner rõ ràng, ví dụ job scheduler, message broker, durable queue hoặc transactional outbox, cùng retry và giám sát. Truyền các dữ kiện cần thiết (user ID, correlation ID, order ID, phạm vi quyền phù hợp) thành **payload rõ ràng**; không kỳ vọng Reactor Context của HTTP request sống mãi trong background worker.

Chỉ gọi `subscribe()` để giả lập một hàng đợi nền là chưa đủ: tiến trình tắt, lỗi bất đồng bộ, thất bại mạng hoặc việc mở rộng nhiều instance có thể khiến công việc bị mất. Với tác vụ quan trọng, cần chiến lược bảo đảm và theo dõi riêng.

## 6. Reactor Context và Spring Security: lỗi chỉ xuất hiện khi chạy thật

### 6.1. Reactor Context là gì?

Reactor Context là cấu trúc dữ liệu đi theo **subscription**, dùng để lưu thông tin như correlation ID hoặc security context mà không phụ thuộc vào thread cố định. Mỗi lần subscribe tạo ra luồng ngữ cảnh liên quan đến subscriber đó; toán tử có thể đọc thông qua `Mono.deferContextual` hoặc cơ chế `ReactiveSecurityContextHolder` trong Spring Security.

Ví dụ Reactor cơ bản:

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("username")))
    .contextWrite(reactor.util.context.Context.of("username", "alice"));
~~~

`contextWrite` cung cấp context cho các toán tử **ở phía upstream** trong cùng subscription. Reactor Context có tính bất biến theo cấu trúc; các lần `put`/`contextWrite` tạo view/context mới thích hợp, không sửa một object global có thể dùng chung giữa request.

**Điểm quan trọng:** `publishOn` hoặc `subscribeOn` đổi scheduler **không mặc nhiên đánh mất Reactor Context** khi tất cả thao tác còn nằm trong cùng chuỗi Reactor. Mất context thường gắn với việc tự tạo subscription khác, đưa công việc ra API không tham gia Reactor hoặc sử dụng `ThreadLocal` mà không có cơ chế propagation phù hợp.

### 6.2. Cách sai khi đọc user trong tác vụ tách riêng

~~~java
// SAI: tự tạo subscription tách khỏi request.
orderService.findById(id).subscribe(order -> {
    ReactiveSecurityContextHolder.getContext()
            .subscribe(ctx -> externalAudit(
                    ctx.getAuthentication().getName(), order));
});
~~~

Đoạn code này có nested subscriptions; security context của HTTP request không được bảo đảm xuất hiện ở subscription mới. Nó còn làm mất cách điều phối error và completion của cả truy vấn lẫn audit.

Cách đúng khi audit phải hoàn thành cùng request:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .flatMap(username -> orderService.findById(id)
                .flatMap(order -> auditService.write(username, order)
                        .thenReturn(order)));
~~~

Việc lấy `username` trong pipeline rồi truyền rõ ràng vào API downstream còn giảm sự phụ thuộc của service vào ngữ cảnh ẩn. Dữ liệu xác thực được Spring Security xác minh mới nên được sử dụng để quyết định quyền truy cập.

### 6.3. Những điều không được suy luận từ một lần chuyển thread

- Chuyển thread trong cùng chain **không tự động** làm mất Reactor Context.
- Tự mở `Thread`/`CompletableFuture` **không tự động** kế thừa Reactor Context hay `ReactiveSecurityContextHolder`.
- `block()` mở thêm subscription mới; không thể giả định có security context giống subscription gốc.
- Không nên sao chép toàn bộ credentials/token từ request vào hàng đợi nền; chỉ truyền các dữ kiện tối thiểu cần thiết, theo chính sách bảo mật.

Để gắn tracing/logging vào môi trường phức tạp, cần hiểu cơ chế context propagation mà framework/thư viện thực sự hỗ trợ. Đừng dùng `ThreadLocal` như nguồn duy nhất cho danh tính của một WebFlux request.

## 7. API đồng bộ bắt buộc: `boundedElastic` giải quyết phần nào?

Đôi khi hệ thống phải gọi thư viện legacy có I/O đồng bộ, ví dụ JDBC driver cũ, SDK chỉ có API blocking hoặc thư viện đọc file. Đưa trực tiếp lời gọi đó vào `map`, `doOnNext` hay `Mono.just(blockingCall())` sẽ **vẫn chặn thread đang chạy callback**.

Sai:

~~~java
return Mono.just(legacyClient.fetch(id)); // fetch() chạy ngay khi tạo Mono
~~~

Đúng hơn khi chưa thể thay thư viện:

~~~java
return Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` trì hoãn việc gọi API; `subscribeOn(Schedulers.boundedElastic())` chuyển phần subscription/nguồn blocking lên scheduler dành cho công việc có thể chặn. `Schedulers.boundedElastic()` có giới hạn tài nguyên, vì vậy đây là **biện pháp tương thích tạm thời**, không biến API đồng bộ thành non-blocking thực thụ. Cần đặt timeout, quan sát queue/thread exhaustion và xem liệu cancellation có thực sự dừng được I/O đồng bộ hay không.

Nếu thư viện có API reactive chuẩn (R2DBC, reactive HTTP client, v.v.), thường ưu tiên API đó để giảm số thread phải giữ trong khi chờ I/O.

`publishOn` đổi nơi chạy **các toán tử downstream**; `subscribeOn` tác động vào quá trình subscribe và nguồn upstream. Không thêm scheduler ngẫu nhiên với hy vọng mọi lỗi blocking sẽ biến mất. Quan trọng là đặt phép gọi blocking bên trong `fromCallable`/`defer` và lập lịch ở đúng ranh giới.

**Không sửa bằng cách gọi `block()` trong `boundedElastic` rồi coi như đã có reactive pipeline.** Nếu API đích đã trả `Mono`, compose nó; chỉ phải cô lập lời gọi vốn thật sự đồng bộ khi không có lựa chọn tốt hơn.

## 8. Ví dụ Java 17+ chạy độc lập: ghép đọc dữ liệu, audit và context

Ví dụ dưới đây chỉ cần **Reactor Core**, không yêu cầu Spring Boot hay server. Mục tiêu là thấy rõ ba sự kiện: tạo pipeline chưa chạy công việc, audit là một phần của subscription, và context được đọc trong pipeline.

Cấu trúc:

~~~text
reactor-pipeline-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ReactorPipelineDemo.java
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactor-pipeline-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.6'
}

application {
    mainClass = 'demo.ReactorPipelineDemo'
}
~~~

**`src/main/java/demo/ReactorPipelineDemo.java`**

~~~java
package demo;

import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ReactorPipelineDemo {

    private ReactorPipelineDemo() {
    }

    private static Mono<String> loadResource(String id) {
        return Mono.fromSupplier(() -> {
            System.out.println("load:" + id);
            return "resource-" + id;
        });
    }

    private static Mono<Void> saveAudit(String principal, String resource) {
        return Mono.fromRunnable(() ->
                System.out.println("audit:" + principal + ":" + resource)
        ).then();
    }

    private static Mono<String> handle(String id) {
        return Mono.deferContextual(contextView -> {
            String principal = contextView.get("principal");
            return loadResource(id)
                    .flatMap(resource -> saveAudit(principal, resource)
                            .thenReturn("ok:" + resource));
        });
    }

    public static void main(String[] args) {
        Mono<String> pending = handle("42")
                .contextWrite(Context.of("principal", "alice"));

        System.out.println("assembled");
        String result = pending.block(); // Chỉ ở biên console main().
        System.out.println("result:" + result);
    }
}
~~~

Lệnh chạy (cần Gradle tương thích Java 17 trên máy; nếu có Gradle Wrapper, có thể thay bằng `./gradlew run`):

~~~bash
gradle run --quiet
~~~

**Đầu ra của chương trình:**

~~~text
assembled
load:42
audit:alice:resource-42
result:ok:resource-42
~~~

Giải thích chính xác:
1. `handle("42")` xây dựng Publisher; việc in `load:42` chưa xảy ra, vì `loadResource` dùng `fromSupplier`.
2. Dòng `assembled` xuất hiện trước mọi thao tác của pipeline.
3. `pending.block()` nằm ở `main` của chương trình console, đóng vai trò subscriber ngoài cùng và chờ kết quả; **không** sao chép cách này vào WebFlux controller.
4. `contextWrite` đưa `principal=alice` vào context cho cùng subscription.
5. `flatMap` đợi `saveAudit` hoàn tất trước khi `thenReturn` trả về kết quả. Vì vậy dòng audit xuất hiện trước `result:...`.

Trong ví dụ nhỏ, `saveAudit` chỉ in ra console khi được subscribe. Nó **không mô phỏng một database hoặc network client thật**; nếu audit thật dùng I/O bất đồng bộ, hãy trả về Publisher của client đó, hoặc cô lập API blocking như phần 7.

### 8.1. Thử thay đổi để nhìn thấy lỗi “publisher bị bỏ quên”

Nếu sửa `handle` thành:

~~~java
private static Mono<String> handle(String id) {
    return loadResource(id)
            .doOnNext(resource -> saveAudit("alice", resource))
            .map(resource -> "ok:" + resource);
}
~~~

dòng `audit:...` **không được in**, bởi `saveAudit` trả về một `Mono` lazy nhưng callback không compose/subscribe publisher ấy. Đoạn sửa này là phần thay thế trong cùng class ở trên, không phải một chương trình độc lập.

Nếu tiếp tục thay `saveAudit(...)` bằng `saveAudit(...).subscribe()`, có thể thấy audit in ra trong demo đồng bộ này, nhưng đó chỉ là tình cờ vì `fromRunnable` kết thúc ngay. Với I/O bất đồng bộ, tác vụ phụ có thể hoàn thành sau response, thất bại riêng hoặc thiếu request context. Đừng dùng một lần in console thành công làm bằng chứng rằng detached subscription an toàn.

## 9. Tích hợp đúng trong Spring WebFlux + Spring Security Reactive

Trong ứng dụng WebFlux có security filter chain và route yêu cầu xác thực, code minh họa có thể giữ toàn bộ quyết định nghiệp vụ bên trong một `Mono`:

~~~java
// Đoạn tích hợp: cần các bean/orderService/auditService và import phù hợp.
@GetMapping("/orders/{id}")
public Mono<OrderDto> getOrder(@PathVariable String id) {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .flatMap(authentication ->
                    orderService.findById(id)
                            .flatMap(order ->
                                    permissionService.requireOwner(
                                                    order, authentication.getName())
                                            .then(auditService.saveViewed(
                                                    order, authentication.getName()))
                                            .thenReturn(order)));
}
~~~

Ở đây:
- `ReactiveSecurityContextHolder` lấy `Authentication` từ pipeline của request đã được security filter chain thiết lập.
- `requireOwner` phải hoàn thành thành công **trước khi** truy cập được chấp nhận; nếu phát lỗi, pipeline ngừng và không trả `order`.
- `saveViewed` là Publisher được nối vào chain, không dùng `subscribe()` thủ công.
- `thenReturn(order)` chỉ chạy khi các bước trước đã hoàn thành thành công.
- Spring WebFlux subscribe vào Publisher mà controller trả về.

Với ứng dụng cần không lưu audit khi bước yêu cầu quyền bị từ chối, cấu trúc trên thực thi đúng thứ tự đó. Cách phát `AccessDeniedException`/status phù hợp phải tuân theo security và exception handling thực tế. Kiểm soát quyền truy cập theo đối tượng như đơn hàng vẫn cần trong service; việc có `authenticated()` ở route chưa tự động bảo đảm đơn hàng thuộc người gọi.

**Lưu ý:** đoạn trên minh họa cách compose, không phải một chương trình chạy riêng. `OrderDto`, `orderService`, `permissionService` và `auditService` là thành phần của ứng dụng cần được định nghĩa.

Nếu muốn trả về danh tính cho một endpoint được bảo vệ, mẫu tối giản là:

~~~java
@GetMapping("/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
~~~

Không `block()`, không `subscribe()`, không tự truyền `ThreadLocal` qua thread.

## 10. Lỗi, hủy và timeout: kiểm chứng một chain có còn nguyên vẹn không

Một phần quan trọng của lập trình reactive là **tín hiệu**, không chỉ giá trị trả về.

| Tình huống | Khi mọi bước cùng một chain | Khi tự `subscribe()` / tạo tác vụ ngoài |
| --- | --- | --- |
| Truy vấn thất bại | `onError` truyền xuống pipeline, có thể xử lý tập trung | Lỗi có thể nằm ở subscription phụ, không ảnh hưởng response |
| Client hủy request | Cancellation được chuyển tới upstream liên kết khi có thể | Tác vụ tách riêng có thể tiếp tục chạy |
| Timeout request | `timeout` thuộc pipeline kiểm soát publisher của request | Không tự kiểm soát job đã tách ra |
| Cần bảo đảm bước B xong mới trả A | `flatMap(...).thenReturn(...)` biểu diễn thứ tự | Response có thể hoàn thành trước B |
| Đọc reactive security context | Dựa vào context của subscription hiện hành | Không bảo đảm context sẵn có ở subscription mới |

Ví dụ xử lý lỗi đúng chủ đích:

~~~java
return orderService.findById(orderId)
        .flatMap(order -> auditService.save(order).thenReturn(order))
        .timeout(Duration.ofSeconds(3))
        .doOnError(error -> log.error("Order flow failed", error));
~~~

`timeout` tạo tín hiệu lỗi nếu chuỗi không kịp hoàn thành; `doOnError` chỉ quan sát lỗi, **không nuốt lỗi**. Nếu muốn đổi lỗi thành giá trị dự phòng, dùng `onErrorResume` nhưng chỉ khi nghiệp vụ cho phép. Cần import `java.time.Duration` và logger phù hợp; đoạn này không chạy độc lập. Đặc biệt, **không** dùng fallback cho phép truy cập khi một bước authorization thất bại.

Cancellation trong Reactor là tín hiệu hợp tác: nó không bảo đảm dừng tức thì mọi thao tác I/O blocking, mọi cuộc gọi bên ngoài hoặc công việc đã được giao cho hệ thống khác. Vì thế cần phân biệt “cancellation được truyền” với “tác vụ chắc chắn đã dừng”.

Có thể chẩn đoán vòng đời publisher qua `doOnSubscribe`, `doOnError`, `doFinally` và các bài kiểm thử `StepVerifier`. Khi log, tránh in credential, JWT, password, thông tin cá nhân hoặc toàn bộ security context.

## 11. Khi nào dùng toán tử nào?

| Nhu cầu | Mẫu thường phù hợp | Tránh |
| --- | --- | --- |
| Biến đổi giá trị đồng bộ, nhanh | `map(value -> transform(value))` | `map(value -> blockingI/O(value))` trên event-loop |
| Gọi service trả `Mono<R>` và cần kết quả | `flatMap(value -> service.call(value))` | `service.call(value).subscribe()` trong callback |
| Chờ tác vụ `Mono<Void>` hoàn thành rồi giữ dữ liệu ban đầu | `flatMap(x -> save(x).thenReturn(x))` | `doOnNext(x -> save(x))` |
| Chạy tác vụ tiếp theo sau completion, bỏ kết quả trước | `first.then(second)` | Tự gọi `subscribe()` ở bước đầu |
| Lấy dữ liệu gắn với subscription | `Mono.deferContextual(...)` / `ReactiveSecurityContextHolder` | Tin vào `ThreadLocal` hoặc subscription tách rời |
| Bọc API blocking không thể thay | `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` | Chặn event-loop, hoặc `Mono.just(blockingCall())` |
| Chạy tác vụ sau response cần độ tin cậy | Hàng đợi/job/outbox có lifecycle, retry, giám sát | Fire-and-forget vô chủ trong HTTP handler |

Bảng này không thay thế việc xem giao diện trả về: `flatMap` cho `Mono`, `flatMap`/`concatMap` cho `Flux` có khác biệt về concurrency và thứ tự; chọn theo yêu cầu nghiệp vụ. `doOnNext` phù hợp cho logging/metric đồng bộ nhẹ, không phù hợp để điều phối một Publisher bất đồng bộ cần hoàn tất.

## 12. Tình huống thực tế và cách phân tích

### Tình huống A — API đôi khi mất audit log

Controller trả response thành công, nhưng audit thỉnh thoảng không xuất hiện. Tìm các mẫu `auditService.save(...).subscribe()` và `doOnNext(x -> auditService.save(x))`. Nếu audit là điều kiện thành công, compose nó bằng `flatMap(...).thenReturn(...)`. Nếu audit phải tồn tại lâu hơn request, chuyển sang cơ chế durable phù hợp với yêu cầu hệ thống.

### Tình huống B — Trên máy nhỏ chạy được, tải lớn thì chậm

Service gọi `blockingClient.fetch()` trong `map`, hoặc `block()` trong controller, khiến event-loop đợi I/O. Kiểm tra thread/stack trace, loại bỏ block từ reactive chain hoặc cô lập API blocking bằng `fromCallable` + `boundedElastic`. Đo và theo dõi giới hạn scheduler; không tăng số thread vô hạn.

### Tình huống C — `ReactiveSecurityContextHolder.getContext()` rỗng ở task bất đồng bộ

Kiểm tra task có bị tách khỏi subscription bằng `subscribe()`, `new Thread` hay `CompletableFuture.runAsync` không. Nếu công việc cần kết quả trước response, compose vào chain hiện tại. Nếu là job nền, truyền principal/actor ID đã xác thực như dữ liệu rõ ràng, cùng chính sách quyền hợp lệ tại nơi job chạy.

### Tình huống D — Người dùng chưa đủ quyền vẫn nhận 200

Tìm mã tự gọi `checkAccess().subscribe()` rồi trả `Mono.just(success)`. Đảm bảo kết quả authorization được **chờ và kiểm tra** trong publisher trả về. Viết kiểm thử với người chưa xác thực, người đã xác thực nhưng không có quyền và người có quyền, đồng thời kiểm tra quyền sở hữu dữ liệu ở tầng service.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `Mono.just(repository.find())` có thể gọi repository trước lúc subscribe, trong khi `Mono.fromCallable(repository::find)` chưa gọi ngay?
2. Khi WebFlux controller đã trả `Mono<Order>`, vì sao controller không nên tự gọi `subscribe()` để “làm cho code chạy”?
3. `audit.save(x)` trả `Mono<Void>`. Vì sao `doOnNext(x -> audit.save(x))` có thể không ghi gì? Viết lại bằng `flatMap` và `thenReturn`.
4. Một service gọi `ReactiveSecurityContextHolder.getContext().block()` từ WebFlux request. Có **hai** loại lỗi nào cần nghĩ tới?
5. `publishOn(Schedulers.parallel())` trong cùng chain có chắc làm mất Reactor Context không? Điều gì khác khi dùng `CompletableFuture.runAsync`?
6. Nếu công việc bắt buộc phải tiếp tục sau HTTP response và không được mất khi instance chết, vì sao `subscribe()` thủ công chưa đủ?
7. Khi đưa một JDBC client đồng bộ lên `boundedElastic`, client đó đã trở thành non-blocking chưa?

**Gợi ý đáp án:** (1) đối số của `just` được tính ngay, `fromCallable` hoãn tới subscribe; (2) WebFlux là owner của subscription response; (3) `doOnNext` không tự subscribe Publisher mới, nên ghép `flatMap(x -> audit.save(x).thenReturn(x))`; (4) nguy cơ blocking trên non-blocking thread và tạo subscription mới thiếu request context; (5) không mất chỉ vì chuyển scheduler trong cùng chain, nhưng future tự chạy không tự kế thừa Reactor Context; (6) cần lifecycle/durability/retry/giám sát; (7) không, đó là API blocking được cô lập trên scheduler phù hợp.

## 14. Ghi nhớ

**Quy tắc cốt lõi của Reactor trong WebFlux: giữ công việc cần thiết trong một pipeline được trả về; framework subscribe ở biên HTTP; đừng chặn event-loop, đừng tạo subscription phụ tùy tiện và đừng coi SecurityContext như một biến thread-local có mặt ở mọi nơi.**

Khi cần dữ liệu từ một Publisher khác, **compose bằng toán tử**. Khi phải dùng thư viện blocking, **cô lập rõ ràng và có giới hạn**. Khi cần job thực sự độc lập với request, **giao cho thành phần có vòng đời và cơ chế tin cậy riêng**. Các lựa chọn này quyết định độ đúng đắn của authorization, khả năng quan sát lỗi và tính ổn định của ứng dụng WebFlux.

Tài liệu tham khảo:
- Project Reactor — Blocking Can Be Wasteful: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Simple Ways to Create a Flux or Mono and Subscribe to It: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html