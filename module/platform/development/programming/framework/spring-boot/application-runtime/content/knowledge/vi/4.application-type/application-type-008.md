# Ranh giới giữa vòng đời ứng dụng và xử lý yêu cầu Servlet hoặc Reactive

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **vòng đời ứng dụng Spring Boot** với **vòng đời một HTTP request**.
2. Giải thích vai trò của `SpringApplication`, `ApplicationContext`, embedded web server, controller và pipeline Servlet/Reactive.
3. Hiểu vì sao `ApplicationRunner`, `ApplicationReadyEvent`, `@PostConstruct` và `@PreDestroy` không phải các callback “mỗi request”.
4. Đọc và chạy ví dụ Spring MVC (Servlet) và Spring WebFlux (Reactive), đối chiếu điểm giống và khác.
5. Xử lý đúng trường hợp request lỗi, request bị hủy, ứng dụng chưa ready hoặc đang graceful shutdown.

**Bối cảnh:** Bài học thuộc phần **Spring Boot Application Runtime → Kiểu ứng dụng**. Trọng tâm là *ranh giới vòng đời*, không phải học toàn bộ Servlet API, Reactor hoặc thiết kế REST API.

## 1. Có ít nhất hai vòng đời khác nhau

### Vòng đời ứng dụng

Vòng đời ứng dụng bắt đầu khi tiến trình gọi `main` và `SpringApplication.run(...)`, bao gồm tạo/nạp `ApplicationContext`, chuẩn bị `Environment`, cấu hình bean, khởi tạo web server khi cần, gọi runner và phát thông báo ứng dụng sẵn sàng. Nó tiếp tục tồn tại cho đến lúc context được đóng và tài nguyên được giải phóng.

Thông thường một ứng dụng Spring Boot có **một context chính** phục vụ nhiều yêu cầu. Một vài kiến trúc đặc biệt có thể dùng nhiều context, nhưng đó không phải mặc định.

~~~text
main()
  └─ SpringApplication.run(args)
       ├─ Chuẩn bị Environment / cấu hình
       ├─ Tạo ApplicationContext phù hợp
       ├─ Đăng ký cấu hình và bean definitions
       ├─ refresh(): tạo bean, khởi động hạ tầng
       ├─ ApplicationStartedEvent
       ├─ ApplicationRunner / CommandLineRunner
       ├─ ApplicationReadyEvent
       └─ Trả về ConfigurableApplicationContext

Ứng dụng tiếp tục hoạt động
  ├─ Request A đến và hoàn tất
  ├─ Request B đến và hoàn tất
  ├─ Request C bị hủy hoặc gặp lỗi
  └─ ... nhiều request khác ...

Đóng context / tắt ứng dụng
  ├─ Dừng nhận và/hoặc xử lý nốt request theo cơ chế shutdown
  ├─ Dừng các thành phần được quản lý
  └─ Hủy bean, giải phóng tài nguyên
~~~

Đây là sơ đồ **khái niệm**. Thứ tự chi tiết còn các sự kiện lifecycle, post-processor và callback khác. Chẳng hạn `ApplicationStartedEvent` xuất hiện **sau khi context đã refresh nhưng trước runners**, còn `ApplicationReadyEvent` được phát sau khi runners chạy thành công.

### Vòng đời request

Mỗi HTTP request có hành trình riêng: kết nối/request đến server, framework phân giải route, gọi handler/controller, tạo response (hoặc dòng response), xử lý lỗi và hoàn tất hoặc bị hủy. Hành trình này nằm **bên trong khoảng thời gian ứng dụng đang chạy**, nhưng không lặp lại toàn bộ `SpringApplication.run`.

~~~text
                  Context và server đang hoạt động
                         │
Client ── HTTP request ──┤
                         ├─ Servlet: filter → DispatcherServlet → handler
                         │              → xử lý → HTTP response
                         │
                         └─ Reactive: WebFilter → DispatcherHandler → handler
                                        → Publisher → HTTP response
                                                  hoặc error/cancel
~~~

Một request kết thúc **không** có nghĩa là ứng dụng tắt. Một handler ném exception **không mặc nhiên** làm cả `ApplicationContext` thất bại. Ngược lại, khi ứng dụng bắt đầu shutdown, những request mới/đang chạy có thể bị ảnh hưởng tùy server và chính sách graceful shutdown.

## 2. Ba lớp trách nhiệm và phạm vi tồn tại

| Thành phần | Phạm vi tồn tại điển hình | Trách nhiệm | Không nên hiểu là |
| --- | --- | --- | --- |
| Tiến trình JVM | Từ lúc khởi chạy đến khi kết thúc | Chạy code, quản lý thread, heap và resource của process | Một request HTTP |
| `SpringApplication` | Đối tượng bootstrap, chủ yếu dùng lúc `run` | Điều phối khởi động context theo cấu hình | Request handler; nơi giữ mọi trạng thái nghiệp vụ |
| `ApplicationContext` | Từ khi tạo đến khi đóng | Quản lý bean, dependency injection, lifecycle, sự kiện | Được tạo lại cho mỗi HTTP request |
| Embedded web server | Phần của runtime web, sống cùng context tương ứng | Lắng nghe cổng, nhận kết nối, đưa request vào framework | Đồng nghĩa với controller |
| Controller/handler | Thường là bean singleton trong context | Ánh xạ route và xử lý yêu cầu | Tự tạo mới mỗi lần gọi route |
| Đối tượng request/response | Theo từng exchange hoặc tác vụ liên quan | Mang HTTP metadata, body, status, headers | Nơi giữ cấu hình chung suốt đời ứng dụng |

**Hệ quả quan trọng:** `@RestController` thường là một bean **singleton**, được tạo khi khởi động và có thể xử lý nhiều request song song. Không đặt state riêng của request, ví dụ `currentUser` hoặc `lastRequestBody`, vào một field mutable của singleton controller mà không có thiết kế cách ly thích hợp.

`@PostConstruct` chạy khi bean được khởi tạo, còn `@PreDestroy` chạy khi bean bị hủy dưới sự quản lý của container. Chúng không chạy trước/sau từng HTTP request.

## 3. Kiểu ứng dụng quyết định hạ tầng request

Spring Boot thường suy luận `WebApplicationType` từ những thư viện có mặt trên classpath:

- **`SERVLET`:** Ứng dụng web theo Servlet stack, thường dùng `spring-boot-starter-web`, Spring MVC, `DispatcherServlet` và embedded Tomcat theo cấu hình mặc định.
- **`REACTIVE`:** Ứng dụng web phản ứng, thường dùng `spring-boot-starter-webflux`, Spring WebFlux, `DispatcherHandler` và Reactor Netty theo mặc định thông dụng.
- **`NONE`:** Ứng dụng không thiết lập web server nhúng theo cơ chế tự cấu hình web của Spring Boot; phù hợp cho CLI, worker hoặc tác vụ chạy nền.

Có thể đặt loại ứng dụng một cách tường minh **trước `run`**:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

Đoạn code trên chỉ minh họa điểm thiết lập, chưa phải chương trình độc lập.

Nếu `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt, Spring Boot **thông thường chọn `SERVLET`**; điều này có thể phù hợp khi dùng `WebClient` trong ứng dụng MVC nhưng không làm controller tự chuyển thành mô hình WebFlux. Để học ranh giới rõ ràng, nên thử hai project chỉ sử dụng một trong hai starter. Không nên ép `REACTIVE` chỉ để “chạy nhanh hơn”: framework, dependencies, cách làm I/O và thiết kế vận hành phải phù hợp.

### Ranh giới Servlet và Reactive

| Khía cạnh | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Điểm điều phối request của Spring | `DispatcherServlet` | `DispatcherHandler` |
| Lớp xử lý xen vào request | Servlet `Filter`, MVC `HandlerInterceptor`... | `WebFilter` và các cơ chế reactive tương ứng |
| Kết quả handler phổ biến | `String`, DTO, `ResponseEntity<T>`, async types khi phù hợp | `Mono<T>`, `Flux<T>` hoặc giá trị được hỗ trợ |
| Mô hình I/O điển hình | Servlet thread pool; request thường được xử lý bằng thread của server | Non-blocking I/O, event loop và chuỗi Publisher |
| Yêu cầu với thao tác blocking | Servlet hỗ trợ mô hình blocking; vẫn phải giới hạn thread, timeout | Tránh blocking trên event-loop; cần scheduler phù hợp nếu bắt buộc dùng thư viện blocking |
| Khi request hoàn tất | Framework ghi response và kết thúc xử lý request | Chuỗi reactive hoàn tất (`onComplete`), lỗi (`onError`) hoặc bị hủy (`cancel`), gắn với xử lý HTTP |
| Context và bean chính | Dùng lại trong nhiều request | Dùng lại trong nhiều request |

Đây là **mô hình phổ biến**, không phải khẳng định “Servlet không thể bất đồng bộ” hay “Reactive chỉ chạy trên một thread”. Servlet có async processing; WebFlux có thể chuyển scheduler và sử dụng nhiều thread. Sự khác biệt quan trọng nằm ở **hợp đồng xử lý request và I/O**.

## 4. Ví dụ chạy được: cùng vòng đời ứng dụng, hai kiểu request

Dùng **Java 17+**, **Gradle** và **Spring Boot 3.3.13**. Ta tạo một ứng dụng web nhỏ, sau đó chuyển giữa Spring MVC và WebFlux để đối chiếu. Mỗi lần chỉ sử dụng **một** web starter.

### 4.1. Cấu trúc file

~~~text
runtime-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runtime/
    ├── RuntimeBoundaryApplication.java
    └── GreetingController.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'runtime-boundary-demo'
~~~

`build.gradle` cho **bản Servlet/MVC**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

springBoot {
    mainClass = 'com.example.runtime.RuntimeBoundaryApplication'
}
~~~

Tệp `src/main/java/com/example/runtime/RuntimeBoundaryApplication.java`:

~~~java
package com.example.runtime;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RuntimeBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeBoundaryApplication.class, args);
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args ->
                System.out.println("LIFECYCLE: runner executed");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LIFECYCLE: application ready");
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println("LIFECYCLE: context closing");
    }
}
~~~

Ở đây:

- `main` gọi `SpringApplication.run` **một lần**.
- `ApplicationRunner` thực hiện sau khi context được refresh và trước khi ứng dụng được báo ready.
- Listener `ApplicationReadyEvent` chạy khi giai đoạn startup thành công đến mốc ready; nó không chạy theo từng HTTP request.
- `@PreDestroy` gắn với việc hủy bean ứng dụng khi context đóng bình thường. Nó không chạy sau khi controller trả response.

Tệp `src/main/java/com/example/runtime/GreetingController.java` cho **bản Servlet/MVC**:

~~~java
package com.example.runtime;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping(
            value = "/api/greeting",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String greet(
            @RequestParam(name = "name", defaultValue = "bạn") String name) {
        System.out.println("REQUEST: MVC handler invoked");
        return "Xin chào, " + name;
    }
}
~~~

Với `@RestController`, giá trị `String` là **body của HTTP response**, không phải tên view. `produces = MediaType.TEXT_PLAIN_VALUE` giúp xác định kiểu nội dung. Không có thông tin người dùng nào được lưu ở field của controller.

### 4.2. Chạy phiên bản Servlet/MVC

Trong thư mục chứa `build.gradle`, với Gradle tương thích đã cài:

~~~bash
gradle bootRun
~~~

Nếu project có Gradle Wrapper, có thể dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows.

Sau khi thấy ứng dụng chạy, ở terminal thứ hai:

~~~bash
curl -s "http://localhost:8080/api/greeting?name=Lan"
~~~

**HTTP response body** (không gồm HTTP headers):

~~~text
Xin chào, Lan
~~~

Những dòng `System.out.println` tự viết trong code xuất hiện theo ý nghĩa:

~~~text
LIFECYCLE: runner executed
LIFECYCLE: application ready
REQUEST: MVC handler invoked
~~~

Hai dòng `LIFECYCLE` xuất hiện trong startup, còn dòng `REQUEST` xuất hiện khi gửi request. Log do framework sinh ra có thể xen giữa; không phụ thuộc vào thứ tự log framework. Khi gọi URL hai lần, dòng `REQUEST` xuất hiện thêm lần nữa, còn runner/ready **không chạy lại**.

Với cấu hình mặc định của `spring-boot-starter-web`, Tomcat nhận HTTP request rồi Spring MVC ánh xạ tới `GreetingController.greet`. Một request có thể sử dụng thread server riêng, nhưng đối tượng controller thường được dùng chung giữa các request.

### 4.3. Chuyển sang WebFlux/Reactive

**Giữ nguyên** `settings.gradle` và `RuntimeBoundaryApplication.java`. Trong `build.gradle`, thay đúng dependency web:

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Đây là **thay thế toàn bộ block `dependencies`** của phiên bản MVC, không thêm WebFlux bên cạnh `spring-boot-starter-web`. Sau đó thay nội dung `GreetingController.java` bằng:

~~~java
package com.example.runtime;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping(
            value = "/api/greeting",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> greet(
            @RequestParam(name = "name", defaultValue = "bạn") String name) {
        return Mono.fromSupplier(() -> {
            System.out.println("REQUEST: WebFlux publisher executed");
            return "Xin chào, " + name;
        });
    }
}
~~~

`Mono<String>` biểu diễn publisher có tối đa một giá trị. `Mono.fromSupplier(...)` trì hoãn việc gọi supplier đến khi publisher được **subscribe**. Trong xử lý HTTP WebFlux thông thường, framework đăng ký nhận publisher và ghi dữ liệu trả về vào response. Handler **không cần** tự gọi `subscribe()` hay `block()`.

Dừng bản MVC, rồi chạy lại với dependency WebFlux:

~~~bash
gradle bootRun
~~~

Gửi cùng request:

~~~bash
curl -s "http://localhost:8080/api/greeting?name=Lan"
~~~

Response body vẫn là:

~~~text
Xin chào, Lan
~~~

Mốc khởi động `LIFECYCLE: runner executed` và `LIFECYCLE: application ready` vẫn chỉ diễn ra một lần mỗi startup. Với request vừa gửi, sẽ có dòng:

~~~text
REQUEST: WebFlux publisher executed
~~~

Khác biệt nằm ở hạ tầng xử lý request và hợp đồng trả về `Mono`, **không phải** cứ mỗi publisher là một `ApplicationContext` mới. Một context và các singleton bean vẫn có thể phục vụ rất nhiều request.

**Lưu ý chạy ví dụ:** Phải dừng ứng dụng cũ trước khi chạy phiên bản mới để tránh chiếm cùng cổng 8080. Nếu có `server.port` trong cấu hình triển khai hoặc biến môi trường, dùng đúng cổng thực tế thay vì mặc định 8080.

## 5. So sánh vòng đời từng request

### Servlet/MVC: từ request đến response

Mô hình phổ biến:

~~~text
Client
  → Embedded Tomcat
  → Servlet Filter chain
  → DispatcherServlet
  → HandlerMapping / HandlerAdapter
  → @RestController
  → Return value / HttpMessageConverter
  → HTTP response
~~~

Request có thể bị từ chối, hết hạn, lỗi validation hoặc lỗi server. Framework có cách xử lý lỗi riêng; trong Spring MVC thường có `HandlerExceptionResolver` và `@ExceptionHandler`/`@RestControllerAdvice`. Lỗi của một handler thông thường chỉ ảnh hưởng request liên quan; không đồng nghĩa context bị đóng.

Servlet API có mô hình request/response riêng và có thể dùng `HttpServletRequest`, `HttpServletResponse` khi cần. Tuy nhiên không nên lưu một request object vào singleton để dùng về sau; request sẽ hết hiệu lực khi vòng xử lý tương ứng kết thúc.

### WebFlux/Reactive: publisher và tín hiệu kết thúc

Mô hình phổ biến:

~~~text
Client
  → HTTP server (thường Reactor Netty)
  → WebFilter chain
  → DispatcherHandler
  → Reactive handler/controller
  → Mono / Flux publisher
  → ServerHttpResponse / encoded body
      ├─ onNext + onComplete (thành công)
      ├─ onError (lỗi)
      └─ cancel (bị hủy hoặc không còn subscriber)
~~~

`Mono`/`Flux` không phải “request mới” hay “bean mới”. Chúng là hợp đồng mô tả công việc và tín hiệu dữ liệu; mã trong một publisher lazy thường chạy theo subscription. Pipeline có thể bị hủy khi client ngắt kết nối hoặc do logic như timeout, nhưng thời điểm và cách quan sát phụ thuộc server, operator và giai đoạn response. Không nên suy ra mỗi TCP disconnect luôn phát `cancel` tại đúng một vị trí code cố định.

Ví dụ minh họa trong một handler WebFlux:

~~~java
@GetMapping("/api/slow")
public Mono<String> slow() {
    return Mono.fromSupplier(() -> "done");
}
~~~

Đây là **đoạn minh họa**, không phải file Java độc lập; nếu thêm vào controller cần import `GetMapping` và `Mono` như ví dụ trước. `fromSupplier` ở đây không tạo ra xử lý chậm; nó chỉ minh họa công việc trả dữ liệu được trì hoãn. Nếu thật sự có lời gọi blocking như JDBC đồng bộ hoặc `Thread.sleep`, không được đặt trực tiếp lên event-loop chỉ vì handler trả `Mono`.

### Những điểm chung

- Framework tạo/giữ controller bean trong context; HTTP request thường chỉ **gọi bean đã có**.
- Bean singleton có thể được gọi đồng thời. State của request cần được giữ trong local variables, tham số hoặc context phù hợp.
- Không gọi `SpringApplication.run(...)` trong một HTTP handler để “mở phiên” cho người dùng.
- Response lỗi hoặc client hủy request bình thường không gây sự kiện `ApplicationReadyEvent`, không yêu cầu rebuild context và không phát `@PreDestroy` cho toàn bộ ứng dụng.
- Khi ứng dụng gặp lỗi nghiêm trọng ngoài luồng request hoặc shutdown có chủ đích, context mới có thể đóng; cần phân biệt đó với lỗi HTTP đơn lẻ.

## 6. Ranh giới đồng thời, ThreadLocal và blocking I/O

### Servlet không đồng nghĩa “mỗi request là một thread riêng vĩnh viễn”

Trong Spring MVC chạy đồng bộ, server thường cấp một thread xử lý request trong phần lớn thời gian handler chạy; nhiều request dùng chung một thread pool. Servlet 3+ cũng hỗ trợ request bất đồng bộ, nên một request không bắt buộc gắn suốt vòng đời với đúng một thread.

Bởi vậy:

- Không tạo `new Thread(...)` cho mỗi request nếu framework/executor đã có công cụ phù hợp.
- Giới hạn độ dài của thao tác blocking; cấu hình timeout và giới hạn tài nguyên.
- Nếu dùng `ThreadLocal` hoặc thông tin gắn theo request, hiểu cách framework thiết lập và dọn nó, đặc biệt khi có async dispatch.

### Reactive không đồng nghĩa “đổi kiểu trả về là non-blocking”

Ví dụ **không nên dùng** trong handler WebFlux:

~~~java
@GetMapping("/api/bad")
public Mono<String> bad() {
    return Mono.fromSupplier(() -> {
        try {
            Thread.sleep(1000); // Blocking: rủi ro chiếm event-loop.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
        return "done";
    });
}
~~~

Đây là đoạn minh họa, không phải một tệp độc lập. `Thread.sleep` vẫn là thao tác blocking dù được bọc trong `Mono`. Tránh gọi `block()` trên luồng non-blocking, đặc biệt event-loop, vì có thể gây lỗi runtime hoặc khiến hệ thống mất khả năng đáp ứng.

Nếu buộc dùng thư viện legacy blocking, cách thường thấy là **cô lập tác vụ** trên scheduler phù hợp, không để nó chạy trên event-loop:

~~~java
@GetMapping("/api/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> legacyBlockingCall())
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây cũng là **mã minh họa**, giả định `legacyBlockingCall()` đã được định nghĩa và đã import `Mono`, `Schedulers`. Cách này không biến thư viện blocking thành non-blocking và vẫn cần giới hạn concurrency, timeout, cancellation và nguồn tài nguyên. Tốt hơn là dùng client/I/O non-blocking nếu hệ thống hỗ trợ.

Trong pipeline Reactive, không giả định dữ liệu `ThreadLocal` tự đi theo mọi lần chuyển thread. Với dữ liệu mang theo chuỗi xử lý, dùng cơ chế phù hợp như **Reactor Context** hoặc các API do Spring WebFlux/Security/Observation cung cấp.

## 7. Startup, readiness và nhận request là ba tín hiệu khác nhau

### Khởi động xong context chưa đủ để bảo đảm phục vụ thành công

Trong một ứng dụng web, embedded server được khởi tạo trong quá trình refresh context. Socket HTTP có thể đã lắng nghe **trước** khi `ApplicationReadyEvent` được phát và trước khi readiness state chính thức chuyển sang **ACCEPTING_TRAFFIC**.

Điều đó giải thích tại sao:

- Việc **cổng đã mở** không đủ chứng minh toàn bộ runner, dữ liệu ban đầu hoặc kiểm tra nghiệp vụ đã hoàn tất.
- Việc **context đã refresh** không có nghĩa mọi yêu cầu HTTP đều sẽ thành công.
- Nếu hệ thống dùng load balancer/Kubernetes, cần **readiness probe** đúng nghĩa để quyết định khi nào định tuyến traffic.

`ApplicationRunner` và `CommandLineRunner` chạy sau refresh. Nếu runner xử lý tác vụ dài hoặc lỗi, thời gian đạt trạng thái ready có thể kéo dài hoặc startup thất bại. Đừng đưa công việc vô hạn, consumer chạy mãi hoặc vòng lặp không kết thúc trực tiếp vào runner khi muốn ứng dụng tiến tới ready.

### Theo dõi readiness với Actuator (tùy chọn)

Có thể thêm vào dependencies của **một** trong hai phiên bản ví dụ:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
~~~

Rồi tạo tệp `src/main/resources/application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Khi có Actuator, probe phù hợp và endpoint được bật, URL health thường dùng gồm:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Ở môi trường Kubernetes, Spring Boot hỗ trợ tự kích hoạt các health group tương ứng trong những điều kiện được tài liệu mô tả; property trên hữu ích để thử chúng ở môi trường khác. **Liveness** trả lời liệu tiến trình có nên được khởi động lại; **readiness** trả lời liệu có nên đưa traffic mới đến instance. Các probe này không mặc nhiên kiểm tra tất cả dependency bên ngoài; muốn phản ánh điều kiện nghiệp vụ cần thiết phải cấu hình health indicators phù hợp.

**Không gọi readiness mỗi lần request để quyết định bean có tồn tại hay không.** Readiness là tín hiệu quản lý tiến trình và traffic; controller vẫn có cơ chế xử lý lỗi, validation và timeout cho từng request.

## 8. Shutdown: ảnh hưởng tới request đang xử lý

Khi JVM nhận tín hiệu dừng phù hợp hoặc context được đóng theo cách được hỗ trợ, Spring quản lý việc tắt server và bean. Đây là **vòng đời ứng dụng**, nhưng request đang xử lý có thể chưa hoàn tất, nên cần một chiến lược shutdown.

Cấu hình mẫu trong `application.properties`:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Ý nghĩa:

- `server.shutdown=graceful` yêu cầu server hỗ trợ dừng theo cơ chế graceful: hạn chế tiếp nhận traffic mới và cho request đang chạy có cơ hội hoàn tất, với hành vi cụ thể tùy server.
- `spring.lifecycle.timeout-per-shutdown-phase=30s` đặt **thời hạn chờ tối đa cho mỗi pha shutdown** của `SmartLifecycle`; không phải lời hứa mọi request sẽ hoàn tất trong đúng 30 giây.
- Khi quá thời hạn, có lỗi hoặc tiến trình bị **kill cưỡng bức**, một request có thể bị cắt giữa chừng. Shutdown graceful không thay thế timeout, idempotency hoặc logic retry phía client.

Với Spring MVC/Servlet và Spring WebFlux/Reactive, các server có thể xử lý việc từ chối request/connection mới khác nhau trong giai đoạn tắt. Không khẳng định một mã HTTP duy nhất được trả trong mọi trường hợp.

Callback `@PreDestroy` của một bean được quản lý được gọi khi bean bị hủy theo chu trình đóng bình thường; điều này khác xa “kết thúc mỗi request” và cũng không bảo đảm xảy ra khi JVM bị buộc dừng đột ngột.

Nếu ứng dụng đang chạy job dài, consumer hoặc xử lý nền, hãy thiết kế để nhận yêu cầu dừng, không nhận thêm việc mới, chờ/chuyển giao việc đang chạy khi có thể, và đóng tài nguyên. Đó là vấn đề **lifecycle của cả process**, không phải một Filter/WebFilter đơn lẻ.

## 9. Vòng đời exception và phạm vi lỗi

Cùng một exception có hậu quả khác nhau tùy nơi xảy ra:

| Lỗi xảy ra ở đâu? | Hậu quả thường thấy | Cách xử lý phù hợp |
| --- | --- | --- |
| Constructor hoặc bean initialization trong startup | Context có thể refresh thất bại, `run` ném exception, ứng dụng không ready | Sửa cấu hình, bean dependency, điều kiện khởi động; đọc startup logs |
| `ApplicationRunner` trong startup | Có thể làm quá trình startup thất bại trước ready | Không nuốt lỗi quan trọng; kiểm tra dữ liệu/tác vụ startup |
| MVC controller xử lý một request | Request nhận mã lỗi, context thường tiếp tục phục vụ request khác | Exception handler, validation, observability, timeout |
| WebFlux publisher phát `onError` | Pipeline request phát lỗi; WebFlux xử lý nếu response còn khả năng trả lỗi | Reactive error handling; tránh gọi `subscribe` tự quản lý |
| Client ngắt kết nối/cancel | Request pipeline tương ứng có thể bị hủy; không đồng nghĩa đóng app | Thiết kế hủy tác vụ, cleanup và retry hợp lý |
| Resource hỏng nặng, OOM hoặc process bị kill | Có thể ảnh hưởng toàn process, cả request đang chạy | Giám sát, giới hạn tài nguyên, restart/recovery và dữ liệu bền vững |

Ví dụ một endpoint trả lỗi không nhất thiết phát `ContextClosedEvent`. Tương tự, `@RestControllerAdvice`/`@ExceptionHandler` xử lý lỗi HTTP trong phạm vi MVC/WebFlux; chúng không phải giải pháp thay thế xử lý lỗi tại `SpringApplication.run`.

## 10. Các nhầm lẫn phổ biến và cách sửa

**Nhầm lẫn 1: “Mỗi request đi qua `SpringApplication.run`.”**

Sai. `run` khởi động context và server; sau đó request được server/framework đưa đến handler trên context đã có. Gọi `run` trong controller có thể tạo thêm context, gây trùng cổng hoặc rò rỉ tài nguyên.

**Nhầm lẫn 2: “Controller được tạo mới ở mọi lần gọi.”**

Mặc định `@RestController` là singleton. Vì vậy các field mutable chung dễ gây race condition hoặc lộ dữ liệu giữa request. Chuyển dữ liệu riêng của request sang tham số/local variables và thiết kế lifecycle state hợp lý.

**Nhầm lẫn 3: “WebFlux là Servlet xử lý song song hơn.”**

Spring WebFlux có mô hình handler và reactive pipeline riêng. `WebFilter` không đồng nghĩa Servlet `Filter`; `DispatcherHandler` khác `DispatcherServlet`. Không dùng trực tiếp assumption về Servlet request thread cho tất cả pipeline Reactive.

**Nhầm lẫn 4: “Trả về Mono thì thao tác blocking tự thành non-blocking.”**

Một `Mono` có thể chứa code blocking. Kiểm tra thực sự việc I/O nào blocking, scheduler nào thực thi, lượng concurrency và timeout.

**Nhầm lẫn 5: “Controller lỗi thì Spring Boot tự khởi động lại.”**

Thông thường lỗi request được chuyển thành error response hoặc tín hiệu lỗi cho request; application context vẫn chạy. Chỉ các điều kiện như lỗi startup/lifecycle hoặc sự cố nghiêm trọng mới có thể đe dọa cả tiến trình.

**Nhầm lẫn 6: “`@PostConstruct` và `@PreDestroy` là callback per-request.”**

Chúng thuộc vòng đời bean. Servlet filter hoặc WebFlux filter mới xử lý đường đi request; mã cleanup per-request phải gắn với cơ chế phù hợp, không đặt vào `@PreDestroy` của singleton controller.

**Nhầm lẫn 7: “Cổng 8080 mở là đã ready.”**

Lắng nghe cổng có thể xảy ra trước khi runners xong. Dùng readiness probe và cơ chế triển khai để tránh gửi traffic quá sớm.

**Nhầm lẫn 8: “Graceful shutdown luôn trả response hoàn chỉnh cho mọi request.”**

Shutdown có deadline và phụ thuộc server, client, load balancer cùng thời gian tác vụ. Cần xử lý timeout, reconnect/retry có kiểm soát, idempotency cho những thao tác có tác dụng phụ.

**Nhầm lẫn 9: “Có cả spring-webmvc và spring-webflux thì handler tự chọn Reactive.”**

Spring Boot thường suy luận loại Servlet nếu cả hai stack cùng có mặt; kiểu ứng dụng phải được xác nhận từ dependencies và cấu hình. `WebClient` có thể được dùng như một HTTP client trong ứng dụng MVC mà không làm request server đổi sang WebFlux.

**Nhầm lẫn 10: “Kết thúc request cũng đóng transaction, subscription và resource theo cùng quy tắc trong mọi trường hợp.”**

Transaction, subscription và resource phải được quản lý theo cơ chế framework/I/O tương ứng. Ví dụ Servlet async, publisher streaming và request cancellation tạo ra thời điểm cleanup khác nhau; cần hiểu contract thực tế của handler và server.

## 11. Bài thực hành và câu hỏi tự kiểm tra

1. Chạy bản Servlet/MVC. Gửi ba request liên tiếp và đếm số lần các dòng `LIFECYCLE`/`REQUEST` xuất hiện. Vì sao số lần khác nhau?
2. Chuyển dependency sang WebFlux và thay controller trả `Mono<String>` như hướng dẫn. Gọi lại cùng URL. Điều gì thay đổi trong cách server/framework xử lý request, điều gì không thay đổi trong lifecycle context?
3. Thêm log tên thread vào cả startup runner và controller. Thử gọi nhiều request đồng thời. Có nên viết kiểm thử kỳ vọng tên thread **luôn cố định** cho mọi lần chạy không? Vì sao?
4. Dự đoán điều gì xảy ra nếu thêm `spring.main.web-application-type=none` vào ứng dụng có controller: bean có thể tồn tại, nhưng vì sao URL HTTP không còn sẵn sàng theo cấu hình web thông thường?
5. Giải thích lý do một lời gọi I/O blocking trực tiếp trong WebFlux event-loop nguy hiểm, kể cả khi phương thức trả `Mono`.
6. Cài Actuator readiness probe. Đọc khác biệt giữa `ApplicationStartedEvent`, runner, `ApplicationReadyEvent` và readiness accepting traffic. Tại sao nên cấu hình health phù hợp với môi trường vận hành?
7. Bật graceful shutdown, tạo một request xử lý có thời gian dài rồi gửi tín hiệu dừng bình thường. Quan sát sự khác nhau giữa tác vụ kết thúc trước deadline và tác vụ quá deadline.
8. Nếu một request phát sinh exception, xác định phạm vi cần xử lý: `@RestControllerAdvice` cho request hay xử lý startup ở `main`? Dựa vào vị trí exception để giải thích.

## Tổng kết kiến thức

- **Application lifecycle**: tạo context, khởi động server/bean, runners, ready, vận hành, shutdown.
- **Request lifecycle**: server tiếp nhận, framework phân giải route, handler tạo kết quả, ghi response hoặc xử lý error/cancel.
- **Servlet/MVC** và **Reactive/WebFlux** có request pipeline khác nhau nhưng cùng nguyên tắc context có thể phục vụ nhiều request.
- **ApplicationReadyEvent** là mốc khởi động; **HTTP response**, **onComplete**, **onError** hay **cancel** thuộc từng request.
- **Graceful shutdown** nối hai phạm vi: ứng dụng dừng thì các request đang chạy chịu tác động, nhưng không có bảo đảm tuyệt đối mọi request hoàn thành.
- **Không xây lifecycle ứng dụng bên trong handler** và không giả định một request tạo lại toàn bộ bean/context.

### Tài liệu tham khảo

- Spring Boot 3.3 — SpringApplication & Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
