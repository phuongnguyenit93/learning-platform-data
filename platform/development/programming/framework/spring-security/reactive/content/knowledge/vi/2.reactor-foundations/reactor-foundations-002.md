# Thời điểm tạo Publisher, đăng ký thực thi và đánh giá quyền truy cập

**Bối cảnh:** Spring Security Reactive (WebFlux) trên nền Project Reactor. Bài này giải thích chính xác điều gì diễn ra khi tạo `Mono`/`Flux`, khi có `Subscriber`, và khi Spring Security quyết định cho phép hoặc từ chối truy cập. Đây là ba việc liên quan nhưng không đồng nghĩa.

## 1. Ba mốc cần phân biệt

| Mốc | Ý nghĩa | Điều cần ghi nhớ |
| --- | --- | --- |
| **Assembly (tạo/ghép Publisher)** | Mã Java gọi các phương thức như `Mono.just(...)`, `Mono.defer(...)`, `map`, `flatMap` để tạo mô tả luồng xử lý. | Bản thân việc có một đối tượng `Mono` **không chứng minh** truy vấn dữ liệu đã chạy hoặc quyền đã được kiểm tra. Tuy nhiên, biểu thức Java truyền vào operator vẫn có thể chạy ngay. |
| **Subscription (đăng ký)** | `Subscriber` đăng ký nhận tín hiệu; với nguồn *cold*, đăng ký kích hoạt quá trình tạo dữ liệu và lan truyền `request` ngược lên nguồn. | Mỗi lượt đăng ký mới thường kích hoạt lại nguồn cold; `retry`/`repeat` có thể tạo lượt đăng ký bổ sung. |
| **Authorization (đánh giá quyền)** | Thành phần bảo mật dùng `Authentication`, quy tắc truy cập và đối tượng được bảo vệ để quyết định cho phép/từ chối. | Thời điểm kiểm tra phụ thuộc **vị trí áp dụng quy tắc**: WebFilter cho HTTP, interceptor cho phương thức, hoặc phép kiểm tra do ứng dụng tự ghép vào Publisher. |

**Quy tắc nền tảng:** “Không có subscription thì pipeline cold chưa phát dữ liệu” chỉ nói về việc thực thi *pipeline cold*. Nó **không** phủ nhận mã Java chạy ngay lúc gọi phương thức, lúc tính đối số, lúc tạo `Mono.just`, khi mở kết nối bên ngoài pipeline, hoặc hoạt động của nguồn *hot*.

## 2. Assembly không đồng nghĩa thực thi

Xét ba cách dựng `Mono`:

- `Mono.just(load())`: Java phải gọi `load()` để tính đối số **trước khi** `Mono.just` được gọi. Kết quả được chụp lại tại thời điểm assembly; subscription sau đó phát giá trị đã có.
- `Mono.fromSupplier(this::load)` (tương tự `fromCallable`): mỗi lần subscribe vào Publisher cold, Reactor mới gọi hàm sinh giá trị. Nếu không subscribe, hàm này không chạy.
- `Mono.defer(() -> repository.findById(id))`: hàm tạo **Publisher bên trong** chỉ được gọi khi subscribe. Phù hợp khi cần tạo truy vấn/nguồn dữ liệu dựa trên trạng thái tại lúc đăng ký, hoặc muốn tránh gọi API tạo Publisher quá sớm.

`map(value -> ...)` và `flatMap(value -> ...)` tạo toán tử khi assembly; callback của chúng được thực thi khi luồng phát tín hiệu tương ứng, thường sau subscription. Riêng đoạn mã **bên ngoài** callback vẫn chạy ngay:

```java
System.out.println("assembly: ngay bây giờ");
Mono<String> result = Mono.just("hello")
    .map(value -> {
        System.out.println("map: khi nhận onNext");
        return value.toUpperCase();
    });
```

Đoạn này mới **tạo** `result`, nên chỉ dòng `assembly: ngay bây giờ` được in. Khi `result` được subscribe và yêu cầu dữ liệu, callback `map` mới chạy. Đây là đoạn minh họa, không phải chương trình Java độc lập.

### Ví dụ Java 17 chạy được: chứng minh các thời điểm

Tạo dự án Maven với hai tệp sau. Ví dụ dùng Reactor Core 3.7.0 để các kết quả có thể tái hiện ổn định; không cần khởi chạy WebFlux.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-timing</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/ReactorTimingDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class ReactorTimingDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        Mono<Integer> just =
            Mono.just(compute("just", counter));
        Mono<Integer> supplier =
            Mono.fromSupplier(() -> compute("supplier", counter));
        Mono<Integer> defer =
            Mono.defer(() -> Mono.just(compute("defer", counter)));

        System.out.println("đã tạo Publisher");
        just.subscribe(value -> System.out.println("just nhận " + value));
        supplier.subscribe(value -> System.out.println("supplier nhận " + value));
        supplier.subscribe(value -> System.out.println("supplier nhận " + value));
        defer.subscribe(value -> System.out.println("defer nhận " + value));
    }

    private static int compute(String source, AtomicInteger counter) {
        int number = counter.incrementAndGet();
        System.out.println(source + " tính #" + number);
        return number;
    }
}
```

Chạy từ thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ReactorTimingDemo
```

**Dòng stdout của chương trình** (không tính thông báo riêng của Maven nếu có):

```text
just tính #1
đã tạo Publisher
just nhận 1
supplier tính #2
supplier nhận 2
supplier tính #3
supplier nhận 3
defer tính #4
defer nhận 4
```

Giải thích: `compute("just", ...)` chạy ngay khi tạo Publisher; `supplier` chạy **hai lần** vì có hai subscription; `defer` chỉ tạo inner `Mono.just` khi được subscribe. Ví dụ cố ý không dùng scheduler nên thứ tự stdout là xác định. Gọi `subscribe()` trực tiếp ở đây chỉ để minh họa trong chương trình CLI; **không dùng cách này bên trong handler WebFlux**.

## 3. Ai subscribe trong WebFlux, và quyền được kiểm tra lúc nào?

Trong request HTTP bình thường, framework WebFlux/Reactor Netty điều phối đăng ký luồng phục vụ response; mã controller chỉ nên **trả về** `Mono`/`Flux`. Bạn không cần gọi `subscribe()` trong controller. Có hai tầng bảo mật quan trọng:

1. **Bảo mật HTTP** — quy tắc `ServerHttpSecurity.authorizeExchange(...)` được cấu hình khi ứng dụng khởi động; khi xử lý từng request, filter bảo mật (bao gồm `AuthorizationWebFilter` khi áp dụng) kiểm tra request và `Authentication` trong chuỗi xử lý. Việc **khai báo** `pathMatchers(...).hasRole(...)` lúc startup không phải là một lần cấp quyền vĩnh viễn. Quyết định được thực hiện cho request khi security chain được chạy, trước khi cho phép đi tiếp đến tài nguyên tương ứng.
2. **Bảo mật phương thức** — `@EnableReactiveMethodSecurity` kích hoạt kiểm soát dựa trên Spring AOP và Reactor Context. Khi gọi bean qua proxy, `@PreAuthorize` yêu cầu kiểm tra quyền trước khi cho phép lời gọi phương thức đích; cơ chế reactive gắn quyết định vào quá trình xử lý Publisher và có thể bất đồng bộ. `@PostAuthorize` kiểm tra sau lời gọi/phần kết quả được bảo vệ, vì vậy không thay thế được chốt kiểm tra ban đầu cho tác vụ có side effect.

Đường đi khái niệm đối với một request đã cấu hình cả hai tầng:

```text
HTTP request
    |
    v
Spring Security WebFilter chain
    |-- xác thực / lấy SecurityContext cho request
    |-- authorizeExchange: kiểm tra quyền ở tầng HTTP
    |-- DENY --> dừng đường đi được bảo vệ và xử lý lỗi
    |
   ALLOW
    v
WebFlux handler/controller
    |
    v
Gọi service bean qua Spring AOP proxy
    |-- @PreAuthorize: quyết định quyền cho phương thức
    |-- DENY --> không thực thi phương thức đích
    |
   ALLOW
    v
Thực thi các publisher nguồn (DB / HTTP / tính toán) khi có subscription
    |
    v
Phát dữ liệu hoặc lỗi -> WebFlux ghi response
```

Sơ đồ mô tả **thứ tự trách nhiệm**, không cam kết mọi bước có một thời điểm duy nhất hay một thread cố định. Một số Publisher được lắp ghép trong lúc request đang được xử lý; khởi tạo cấu hình security lúc startup, gọi controller, tạo Publisher và subscribe là các sự kiện khác nhau. Đặc biệt, mã Java chạy ở phần *assembly* có thể có side effect trước khi các operator kiểm tra quyền tự viết được subscribe.

Với HTTP Basic, request **chưa xác thực** thường được thách thức bằng `401 Unauthorized`; người đã xác thực nhưng thiếu quyền thường nhận `403 Forbidden`. Kết quả cụ thể còn phụ thuộc authentication entry point, access-denied handler và việc response đã được commit hay chưa. Đừng mặc định mọi lỗi bảo mật ở một stream đã phát dữ liệu đều có thể chuyển thành HTTP 403.

## 4. Ví dụ ghép vào ứng dụng Spring WebFlux + Spring Security

Đoạn sau là **mã tích hợp** trong một Spring Boot WebFlux project đã có dependencies `spring-boot-starter-webflux` và `spring-boot-starter-security`, cùng cấu hình xác thực phù hợp. Nó không phải ứng dụng Spring Boot độc lập vì chưa bao gồm class `@SpringBootApplication` và nguồn người dùng. Đặt các lớp vào package được component scan.

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/reports/**").hasRole("READER")
                .anyExchange().authenticated())
            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
            .build();
    }
}

@Service
class ReportService {
    @PreAuthorize("hasRole('READER')")
    public Mono<String> read(String id) {
        // Chỉ tính dữ liệu khi có subscription và đã qua lớp kiểm tra.
        return Mono.fromSupplier(() -> "report-" + id);
    }
}

@RestController
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/api/reports/{id}")
    public Mono<String> read(@PathVariable String id) {
        return service.read(id); // Trả Publisher; không tự subscribe.
    }
}
```

Trong ví dụ, tài khoản có authority `ROLE_READER` có thể qua cả kiểm tra HTTP và `@PreAuthorize`. Tài khoản thiếu role bị từ chối ở tầng HTTP (nên thường chưa gọi controller); nếu service được gọi qua proxy từ lối khác, `@PreAuthorize` vẫn bảo vệ phương thức. `hasRole("READER")` và `hasRole('READER')` xét authority `ROLE_READER` theo prefix mặc định của Spring Security. Hàm `Mono.fromSupplier` mô tả công việc được chạy muộn; trong ứng dụng thực, truy cập cơ sở dữ liệu reactive nên dùng repository/R2DBC trả về Publisher thay vì đặt lời gọi JDBC blocking vào supplier.

**Giới hạn cần phân biệt:** `@PreAuthorize` bảo vệ **method invocation đi qua Spring AOP proxy**, không bảo vệ một đoạn mã tùy ý đã chạy trước khi gọi proxy. Gọi nội bộ `this.read(...)` trong cùng bean, method không được proxy, hoặc tạo side effect trong argument expression có thể bỏ qua chốt bảo vệ dự kiến. Đặt kiểm tra tại boundary thực sự và bảo vệ thao tác nhạy cảm trong phần được kiểm soát.

## 5. Reactive SecurityContext gắn với subscription

Spring Security Reactive dùng `ReactiveSecurityContextHolder` để lấy `SecurityContext` từ **Reactor Context**, gắn với luồng subscriber. Đây không phải giả định “luôn có principal trong ThreadLocal hiện tại”. Khi pipeline được thực thi trên scheduler/thread khác, Reactor Context vẫn có thể đi theo chuỗi reactive đúng cách; tách luồng bằng một lần `subscribe()` tự tạo hoặc dựa vào `ThreadLocal` có thể làm mất ngữ cảnh bảo mật cần thiết.

Ví dụ truy cập tên người dùng đã xác thực trong pipeline:

```java
Mono<String> currentUser =
    org.springframework.security.core.context.ReactiveSecurityContextHolder
        .getContext()
        .map(org.springframework.security.core.context.SecurityContext::getAuthentication)
        .map(org.springframework.security.core.Authentication::getName);
```

Đoạn này là **fragment** trong chương trình đã cấu hình Spring Security. Nó chưa đọc tên người dùng khi được khai báo; lúc subscribe, operator đọc context của subscriber tương ứng. Trong WebFlux, filter bảo mật thường thiết lập context theo request. Trong test hoặc luồng chạy ngoài request, có thể tự cung cấp context:

```java
Authentication alice =
    new TestingAuthenticationToken("alice", "unused", "ROLE_READER");

Mono<String> readAsAlice = currentUser
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));
```

Ở fragment thứ hai, `Authentication`, `TestingAuthenticationToken` và `ReactiveSecurityContextHolder` là các kiểu Spring Security cần import; `readAsAlice` chỉ phát `"alice"` khi được subscribe. `contextWrite` tác động lên *upstream* của subscription. Nó không phải cách “đăng nhập” HTTP cho toàn hệ thống; đây là kỹ thuật cấp context trong phạm vi pipeline/test.

Khi chính sách truy cập thay đổi theo người dùng, **đọc context và ra quyết định trong đường đi thực thi của mỗi subscription**. Đừng lấy `Authentication` của một request cũ ở thời điểm khởi tạo bean, lưu trong trường static, hay chia sẻ Publisher đã gắn kết quả nhạy cảm cho nhiều người dùng.

## 6. Đặt authorization trước side effect: lỗi và cách sửa

Nếu tự cài điều kiện truy cập bằng `Mono<Boolean>`, hãy ghép **toàn bộ thao tác nhạy cảm** sau nhánh cho phép. Sai sót phổ biến là nghĩ rằng cứ đặt một giá trị vào `Mono.just` thì thao tác tạo giá trị tự động được trì hoãn.

**Sai — tải dữ liệu ngay ở assembly, trước khi kết quả quyền xuất hiện:**

```java
Mono<Report> result = Mono.just(loadSensitiveReport(id)); // Hàm chạy ngay!
return accessPolicy.canRead(id)
    .flatMap(allowed -> allowed
        ? result
        : Mono.error(new AccessDeniedException("Forbidden")));
```

**Đúng về thứ tự — chỉ tạo Publisher tải dữ liệu sau kết quả cho phép:**

```java
return accessPolicy.canRead(id)
    .flatMap(allowed -> allowed
        ? Mono.defer(() -> reactiveReportRepository.findById(id))
        : Mono.error(new AccessDeniedException("Forbidden")));
```

Hai đoạn là **fragment minh họa** (các lớp `Report`, `accessPolicy`, `reactiveReportRepository`, `loadSensitiveReport` được định nghĩa trong ứng dụng). `accessPolicy.canRead(id)` trả về `Mono<Boolean>` và phải là kiểm tra quyền đáng tin cậy cho principal hiện tại. Nếu nguồn dữ liệu trả về Publisher cold đúng nghĩa, việc tạo nó sớm thường chưa thực hiện I/O; `defer` giúp thể hiện rõ ranh giới và ngăn logic tạo nguồn chạy quá sớm. Khi cần chống thay đổi quyền giữa bước kiểm tra và bước thao tác, hãy dùng quy tắc/chặn kiểm tra sát dữ liệu hoặc giao dịch phù hợp; riêng “lazy” không giải quyết được bài toán TOCTOU.

Phải bảo vệ cả các **side effect** như ghi dữ liệu, gửi sự kiện, thanh toán, gọi dịch vụ ngoài hoặc ghi log chứa bí mật. Một Publisher bị từ chối khi subscribe không thể “hoàn tác” side effect đã xảy ra từ trước trong mã Java.

## 7. Nhiều subscriptions, retry và cache ảnh hưởng thế nào?

| Trường hợp | Tác động |
| --- | --- |
| Subscribe hai lần vào `Mono.fromSupplier(...)` cold | Supplier thường chạy hai lần, và kiểm tra bảo mật nằm trong mỗi lượt subscription cũng có thể chạy hai lần. |
| `retry(n)` khi lỗi | Có thể **resubscribe** nguồn và lặp lại kiểm tra quyền, truy vấn hoặc side effect. Thiết kế idempotency cho thao tác ghi. |
| `repeat(n)` | Đăng ký lại sau khi hoàn tất, có thể tái chạy công việc. |
| `cache()`, `share()`, hot source | Có thể dùng lại hoặc chia sẻ kết quả giữa các subscriber, không còn suy luận “mỗi subscribe = luôn gọi nguồn mới”. |
| `subscribeOn`/`publishOn` | Thay đổi nơi chạy một phần pipeline; bản thân chúng không cấp quyền, không tự subscribe, và không thay thế Reactor Context. |

Ví dụ nguy hiểm: cache toàn bộ `Mono` trả về thông tin của người A rồi chia sẻ instance ấy cho request của người B. Nếu giá trị nhạy cảm đã cache, lần sau có thể nhận giá trị của A mà không tái chạy phần bên trong. Dù đặt `@PreAuthorize` ở một số điểm, vẫn phải kiểm tra đúng **mỗi đường truy cập** và thiết kế cache theo principal/quyền, hoặc chỉ cache dữ liệu thật sự công khai. Không dùng một `Mono.cache()` global làm kho lưu kết quả có phụ thuộc danh tính.

## 8. Quan sát thời điểm thật bằng logging và test

Trong Reactor, có thể đặt các hook sau vào pipeline khi cần điều tra:

```java
Mono<String> traced = Mono.defer(() -> {
        System.out.println("defer: tạo nguồn khi subscribe");
        return Mono.just("ok");
    })
    .doOnSubscribe(s -> System.out.println("đã subscribe"))
    .doOnNext(v -> System.out.println("onNext: " + v))
    .doOnError(e -> System.out.println("onError: " + e.getClass().getSimpleName()));
```

Đây là fragment; thời điểm của từng log phụ thuộc vị trí operator. `doOnSubscribe` chứng minh một subscription tại vị trí đó, **không** chứng minh một quyền đã được cấp. Theo dõi cả sự kiện *permit/deny* tại security boundary hoặc kiểm thử với danh tính/authority khác nhau. Để test thời gian chạy nguồn, dùng `StepVerifier` (dependency `reactor-test` trong scope test); để test chính sách WebFlux, dùng `WebTestClient` và test security support. Các ca tối thiểu nên chứng minh: không subscribe thì supplier không chạy; subscribe hai lần thì nguồn cold chạy hai lần; thiếu authority thì luồng dữ liệu nhạy cảm không bị kích hoạt; context của hai principal không bị trộn; retry/cancel không để lại tác dụng ngoài ý muốn.

## 9. Những nhầm lẫn cần loại bỏ

1. **“Tạo Mono là đã chạy DB hoặc đã authorize.”** Sai với đa số cold publishers; nhưng đối số/logic khởi tạo eager vẫn chạy, vì thế cần xem **toàn bộ biểu thức Java**.
2. **“Không thấy subscribe() trong code nghĩa là endpoint không chạy.”** WebFlux framework chủ động subscribe; controller nên trả Publisher để framework kiểm soát lifecycle, lỗi và cancellation.
3. **“@PreAuthorize có thể bảo vệ code chạy trước khi chạm proxy.”** Không. Chỉ đường gọi qua proxy được bảo vệ; bảo đảm không có side effect ngoài boundary.
4. **“Có @PostAuthorize là mọi side effect đều an toàn.”** Không. Kiểm tra sau không thay thế bảo vệ trước thao tác nhạy cảm.
5. **“ThreadLocal luôn chứa Authentication của request.”** Không nên dựa vào điều đó trong reactive; dùng `ReactiveSecurityContextHolder`/Reactor Context trên cùng luồng Publisher.
6. **“Mọi subscribe đều tạo truy vấn mới.”** Không đúng với hot/cached/shared Publisher; phân biệt nguồn cold với kết quả được giữ lại.
7. **“Đưa subscribe() vào service để chạy cho chắc.”** Việc này tách công việc khỏi luồng HTTP, làm khó quản lý lỗi, hủy tác vụ và security context; trả về/chaining Publisher mới là cách thông thường.
8. **“Xử lý onErrorResume bằng dữ liệu mặc định luôn vô hại.”** Nếu bắt luôn `AccessDeniedException` và trả dữ liệu nhạy cảm hoặc HTTP thành công, có thể phá chính sách bảo mật. Phân loại lỗi rõ ràng.

## 10. Tự kiểm tra hiểu bài

**Tình huống A:** `Mono<String> p = Mono.just(load());` được tạo nhưng không ai subscribe. `load()` có chạy không? **Có** — Java đánh giá `load()` ngay; chưa có emission từ Publisher không có nghĩa chưa có side effect.

**Tình huống B:** `Mono<String> p = Mono.defer(() -> repository.findById(id));` được tạo và subscribe hai lần. Có chắc hai lần truy cập DB? **Nếu** repository trả Publisher cold và hai subscription được thực thi đầy đủ, thường có hai lượt I/O. `cache`/hot publisher/cancellation có thể thay đổi kết quả, nên không tuyệt đối hóa.

**Tình huống C:** Config `authorizeExchange` đã khởi tạo tại startup. Quyền của request X đã được quyết định chưa? **Chưa**; quy tắc được khai báo trước, quyết định cần ngữ cảnh request/Authentication tại lúc xử lý.

**Tình huống D:** User không có `ROLE_READER` gọi `/api/reports/1` ở ví dụ phần 4. Supplier tạo báo cáo có chạy không? **Không theo đường xử lý bình thường**, vì HTTP authorization từ chối trước; nếu đường khác gọi service qua proxy thì method authorization cũng từ chối. Điều này giả định không có side effect nằm ngoài các chốt bảo vệ.

**Tình huống E:** Hai người subscribe cùng một cached Publisher đã chứa dữ liệu riêng. Có an toàn không? **Không mặc nhiên**; cache chung có thể trả kết quả của người trước. Thiết kế isolation theo người dùng và chính sách trước khi chia sẻ.

### Nguồn tham khảo chính thức

- Project Reactor, *Introduction to Reactive Programming* (assembly, subscription, cold/hot): https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security, *EnableReactiveMethodSecurity*: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html

**Ghi nhớ để áp dụng:** Luôn hỏi ba câu riêng biệt: **(1) Biểu thức nào chạy ngay khi tạo Publisher? (2) Ai subscribe, subscribe bao nhiêu lần và context của ai? (3) Quyết định quyền được thực hiện tại ranh giới nào, trước hay sau thao tác nhạy cảm?** Trả lời được cả ba mới có thể đánh giá chính xác thời điểm thực thi và an toàn truy cập trong Spring Security Reactive.