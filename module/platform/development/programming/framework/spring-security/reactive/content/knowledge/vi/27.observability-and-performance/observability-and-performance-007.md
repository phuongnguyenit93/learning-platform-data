# Phát hiện chặn luồng bằng BlockHound trong Spring Security Reactive

## Mục tiêu học tập

Trong ứng dụng **Spring Security – reactive**, một thao tác đồng bộ kéo dài trong luồng xử lý authentication/authorization có thể giữ chặt **event-loop thread** của Reactor Netty, khiến nhiều request khác trên cùng luồng bị chậm. Bài này hướng dẫn dùng **BlockHound** phát hiện những lời gọi blocking trên các luồng được chỉ định là non-blocking, viết test có thể lặp lại bằng Reactor `StepVerifier`, phân tích lỗi và sửa đúng ranh giới giữa tác vụ blocking và reactive.

Sau bài học, bạn sẽ có thể:

1. Giải thích vì sao blocking trong `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, custom `WebFilter` hoặc publisher phía controller làm giảm khả năng đáp ứng của WebFlux.
2. Phân biệt thao tác **blocking** (đợi I/O hoặc ngủ luồng), tác vụ CPU nặng, sự kiện **backpressure** và việc dùng `block()` không phù hợp; hiểu giới hạn phát hiện của BlockHound.
3. Cài BlockHound trong JVM test, viết test **đỏ về mặt hành vi ứng dụng nhưng xanh về mặt phát hiện**: chủ động thực thi `Thread.sleep` trên `Schedulers.parallel()` và mong đợi `BlockingOperationError`.
4. Chuyển một API đồng bộ bắt buộc phải giữ lại sang `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; kiểm tra phản ứng của pipeline sau sửa.
5. Biết khi nào một test có thể âm tính giả, vì sao không nên “sửa” bằng cách whitelist mọi lời gọi, và cách quan sát tác động thực tế bằng latency/throughput khi chạy tải.

**Phạm vi:** kiểm tra blocking ở runtime trên Reactor/WebFlux, có ví dụ đặc trưng của **Spring Security Reactive**. BlockHound là công cụ chẩn đoán hiệu năng/độ đúng của cách dùng luồng; nó không thay thế test xác thực, phân quyền hay kiểm thử HTTP 401/403.

## 1. Vấn đề: blocking trên event loop nguy hiểm ở đâu?

Trong mô hình WebFlux sử dụng Reactor Netty, một số ít event-loop threads đảm nhiệm xử lý I/O và các đoạn callback không blocking của rất nhiều kết nối. Khác với cách nghĩ “mỗi request có một thread riêng”, đoạn code của một request có thể tạm thời chạy trên luồng cùng phục vụ những request khác.

Sơ đồ khái niệm:

~~~text
Client request
     |
     v
Reactor Netty event loop (non-blocking)
     |
     v
SecurityWebFilterChain
     |
     +--> AuthenticationWebFilter / ReactiveAuthenticationManager
     |             |
     |             +--> ReactiveUserDetailsService / token verifier
     |
     +--> authorization checks / custom WebFilter
     |
     v
Handler -> Mono/Flux -> HTTP response
~~~

Giả sử bộ xác thực gọi một JDBC repository đồng bộ và đợi 300 ms trên event loop. Trong thời gian chờ, **cả event-loop thread** chưa thể tiếp tục các callback khác đang chờ trên chính thread đó. Số request chịu tác động có thể lớn hơn rất nhiều so với số request đang truy vấn database. Lỗi này thường tạo ra tail latency tăng (p95/p99), các kết nối xếp hàng và throughput giảm dưới tải, dù đơn lẻ một request vẫn trả kết quả đúng.

Những điểm dễ có blocking trong chuỗi security:

- `ReactiveUserDetailsService.findByUsername` gọi JDBC/JPA repository đồng bộ, truy vấn LDAP đồng bộ, API đồng bộ hoặc đọc file tại chỗ.
- `ReactiveAuthenticationManager.authenticate` dùng client HTTP đồng bộ, `Thread.sleep` để retry, chờ `Future.get` hoặc tạo một publisher rồi gọi `block()` bên trong.
- `WebFilter` ghi audit/log vào sink đồng bộ, gọi driver đồng bộ hoặc thực hiện khóa chờ có thể kéo dài.
- Một nhánh trong method security `@PreAuthorize` hoặc bean kiểm quyền tùy biến gọi nguồn dữ liệu đồng bộ trước khi publisher được thực thi.
- Một dịch vụ phía controller gọi cùng dependency blocking sau khi security đã cho qua; tác động là tương tự vì vẫn chạy trên event loop.

**Điểm then chốt:** tên kiểu trả về `Mono<T>` / `Flux<T>` không bảo đảm phần logic bên trong không blocking. Bao một truy vấn blocking trong `Mono.just(repository.find(...))` chỉ thay đổi kiểu kết quả; lời gọi đồng bộ vẫn chạy ngay trong lúc dựng publisher.

## 2. BlockHound làm gì và không làm gì?

**BlockHound** là một **Java instrumentation agent**: khi được cài vào JVM, nó can thiệp vào các phương thức blocking mà nó biết, rồi ném `reactor.blockhound.BlockingOperationError` nếu chúng được gọi từ luồng được đánh dấu **non-blocking**. Các thread do `Schedulers.parallel()` hoặc `Schedulers.single()` tạo ra thuộc nhóm non-blocking mặc định của Reactor; event-loop threads của Reactor Netty cũng phải được giữ không blocking. Ngược lại, `Schedulers.boundedElastic()` được thiết kế để chứa những tác vụ đồng bộ buộc phải chờ, nên BlockHound thông thường **không báo lỗi chỉ vì có blocking trên boundedElastic**.

Bảng phân biệt:

| Tình huống | Có thể được BlockHound bắt? | Diễn giải |
| --- | --- | --- |
| `Thread.sleep(20)` trên `Schedulers.parallel()` | **Có**, là phép thử chuẩn | Lỗi `BlockingOperationError` khi subscribe |
| Đọc file/socket bằng API đồng bộ đã được instrument trên event loop | **Có thể**, tùy phương thức/JDK/phiên bản | Phải kiểm thử đường chạy thực tế |
| JDBC/JPA đồng bộ trên event loop | **Có thể** nếu đi qua phương thức blocking được theo dõi | Không mặc định bao phủ mọi lời gọi của mọi driver |
| `Mono.block()` trên một luồng Reactor non-blocking | **Bị Reactor cấm**; lỗi có thể là `IllegalStateException` | Không nhất thiết xuất hiện dưới tên `BlockingOperationError` |
| `Thread.sleep(20)` trong `boundedElastic` | **Thông thường không** | Blocking đã được chuyển sang pool chuyên dụng; vẫn tiêu tốn thread và thời gian |
| Mã CPU nặng (bcrypt, vòng lặp lớn, JSON quá lớn) | **Không bảo đảm** | Không nhất thiết gọi primitive blocking đã được instrument |
| Lời gọi API đồng bộ trên thread JUnit thông thường | **Thường không** | Thread test không mặc nhiên thuộc nhóm non-blocking |
| Cờ chậm do GC, nghẽn mạng, queue, lock không được instrument | **Không đầy đủ** | Cần metrics, profiling và load test bổ sung |

BlockHound **không phát hiện mọi nguyên nhân làm hệ thống chậm**. Nó không tính thời gian thực thi, không đo p99 và không kết luận rằng chuyển một việc sang boundedElastic là đủ để scale. Ngược lại, một số phần mềm nội bộ hay thư viện dùng phương thức blocking chưa có trong danh sách của agent cũng có thể lọt qua. Bởi vậy test bắt buộc phải có một **smoke test** chủ động gây ra blocking đã biết để chứng minh agent thật sự đang hoạt động.

## 3. Cài BlockHound trong dự án Spring Boot/WebFlux

Ví dụ dưới đây giả định dự án **Spring Boot 3.x / Spring Security 6.x** dùng Java 17+ và Gradle Groovy DSL, đã quản lý phiên bản các Spring dependency bằng Spring Boot plugin/BOM. Thêm vào `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'io.projectreactor.tools:blockhound:1.0.18.RELEASE'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    // Cần cho cơ chế instrument/redefine native methods của BlockHound
    // trên các JDK 13+ phù hợp, ví dụ JDK 17/21.
    jvmArgs '-XX:+AllowRedefinitionToAddDeleteMethods'
}
~~~

`1.0.18.RELEASE` là một bản stable được phát hành trong tháng 10/2026; khi áp dụng thực tế cần đối chiếu tương thích với phiên bản JDK và Reactor đang khóa trong dự án. Nhóm `io.projectreactor.tools:blockhound` không đồng nghĩa với `io.projectreactor:reactor-test`: cần cả hai nếu muốn dùng `StepVerifier` để khẳng định lỗi từ agent.

**Về cấu hình JVM:** BlockHound thực hiện instrumentation/retransformation ở runtime. Với các JDK từ 13 trở lên, dự án BlockHound hướng dẫn thêm `-XX:+AllowRedefinitionToAddDeleteMethods`. Một số JDK phát cảnh báo liên quan dynamic agent loading hoặc policy cấm attach; phải xem **lỗi thật từ test JVM** và kiểm tra bản agent/JDK, không bỏ qua lỗi cài đặt. Tùy môi trường có thể cấu hình nạp agent qua JVM `-javaagent:...` từ đầu process, nhưng đừng cấu hình cả hai kiểu bừa bãi hoặc giả định một đường dẫn JAR dùng chung cho mọi môi trường.

**Cài agent sớm và một lần:** gọi `BlockHound.install()` trước khi các phép thử chạy code reactive cần đo, tốt nhất trong bootstrap test/JVM hoặc `@BeforeAll` của test chuyên dụng. BlockHound có hiệu lực trên toàn JVM; các lần gọi `install()` sau không tự thiết lập lại cấu hình khác. Với test suite lớn, sử dụng một chiến lược cài agent chung, thống nhất và có test xác thực instrumentation hoạt động. Không lén vô hiệu hóa BlockHound khi gặp test đỏ.

## 4. Test Java hoàn chỉnh: bắt blocking và xác nhận cách cách ly

Đặt file `src/test/java/demo/security/reactive/BlockHoundDetectionTest.java`. Ví dụ này chạy trong **một dự án Gradle đã cấu hình dependencies như phần 3**; không cần khởi động web server hoặc có database. Mã test dùng Java 17+, JUnit Jupiter và Reactor:

~~~java
package demo.security.reactive;

import java.time.Duration;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockHoundDetectionTest {

    @BeforeAll
    static void installAgent() {
        BlockHound.install();
    }

    // API đồng bộ cố ý chặn thread: chỉ dùng làm fixture.
    private static Mono<String> legacyBlockingCall() {
        return Mono.fromCallable(() -> {
            Thread.sleep(20);
            return "ok";
        });
    }

    @Test
    void detectsBlockingOnNonBlockingScheduler() {
        StepVerifier.create(
                legacyBlockingCall()
                    .subscribeOn(Schedulers.parallel()))
            .expectError(BlockingOperationError.class)
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void canRunLegacyBlockingCallOnBoundedElastic() {
        StepVerifier.create(
                legacyBlockingCall()
                    .subscribeOn(Schedulers.boundedElastic()))
            .expectNext("ok")
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void pureNonBlockingPipelineCompletesNormally() {
        StepVerifier.create(
                Mono.just("ok")
                    .map(String::toUpperCase)
                    .subscribeOn(Schedulers.parallel()))
            .expectNext("OK")
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }
}
~~~

Chạy test từ thư mục gốc Gradle của module/dự án có class đó:

~~~bash
./gradlew test --tests demo.security.reactive.BlockHoundDetectionTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests demo.security.reactive.BlockHoundDetectionTest
~~~

Không có stdout cố định nào phải so sánh: Gradle in báo cáo tùy cấu hình. **Kỳ vọng** khi môi trường instrument đúng là cả ba test PASS.

### Test thứ nhất: test phải thấy lỗi, vì sao vẫn PASS?

Phương thức `legacyBlockingCall()` dùng `Mono.fromCallable` nên `Thread.sleep(20)` chỉ thực thi khi subscriber thực sự subscribe. `subscribeOn(Schedulers.parallel())` chuyển việc subscribe và chạy callable sang một thread Reactor đánh dấu non-blocking. Khi `Thread.sleep` được gọi, BlockHound ném `BlockingOperationError`. `StepVerifier.expectError(BlockingOperationError.class)` khớp với tín hiệu `onError`; đó là **kết quả mong muốn** của test phát hiện.

Stack trace minh họa (dòng và chi tiết JDK có thể khác):

~~~text
reactor.blockhound.BlockingOperationError:
  Blocking call! java.lang.Thread.sleep
  at ...Thread.sleep(...)
  at ...BlockHoundDetectionTest.lambda$legacyBlockingCall$0(...)
~~~

Nếu xóa `BlockHound.install()` và không có nơi nào khác cài agent, `Thread.sleep` thông thường hoàn thành, publisher phát `"ok"` và test thứ nhất **FAIL** vì không nhận được `BlockingOperationError`. Điều này làm cho test trở thành **canary/smoke test** chống tình trạng pipeline CI “xanh” nhưng BlockHound không chạy.

### Test thứ hai: vì sao không còn `BlockingOperationError`?

`Schedulers.boundedElastic()` dành cho các tác vụ **synchronous blocking phải giữ lại tạm thời**. `Mono.fromCallable` trì hoãn lời gọi tới lúc subscribe; `subscribeOn(boundedElastic)` chạy callable trên worker thích hợp. Kết quả `"ok"` cùng `onComplete` chứng minh tác vụ hoàn thành trên luồng dành cho blocking. Đây là kỹ thuật **cách ly blocking**, không phải biến API JDBC/HTTP đồng bộ thành non-blocking hay đảm bảo vô hạn khả năng chịu tải.

`boundedElastic` có giới hạn số worker và hàng đợi: blocking nhiều, thời gian chờ lớn hoặc pool bên ngoài không phù hợp vẫn có thể gây bão hòa. Khi có client non-blocking thực sự (R2DBC, reactive driver, WebClient) thì ưu tiên dùng client đó trong luồng WebFlux. Bounded elastic phù hợp làm cầu nối khi chưa thể thay adapter đồng bộ.

### Test thứ ba: test đối chứng

`Mono.just("ok").map(String::toUpperCase)` không dùng primitive blocking đã biết. Test kiểm tra nó phát `"OK"` và hoàn thành trên scheduler non-blocking. Có cả **test dương tính phát hiện lỗi** và **test âm tính hợp lệ** giúp phân biệt “agent bắt sai” với một pipeline non-blocking bình thường.

**Vì sao có `verify(Duration...)`?** Các test bất đồng bộ nên có thời hạn để tránh treo lâu khi scheduler hoặc setup gặp lỗi. `StepVerifier` cần subscribe; gọi `legacyBlockingCall()` rồi chỉ `assertNotNull(...)` không kích hoạt mã bên trong publisher.

## 5. Áp dụng trực tiếp vào Spring Security Reactive

### 5.1. Antipattern: dùng blocking store trong `ReactiveUserDetailsService`

Ví dụ dưới mô tả **đoạn mã không nên dùng**:

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    UserDetails user = legacyStore.findByUsername(username);
    return Mono.justOrEmpty(user);
}
~~~

Giả sử `legacyStore.findByUsername` là truy vấn JDBC đồng bộ, đoạn đó chạy **ngay khi method được gọi**, trước cả khi `Mono` được trả về. Nếu method được gọi bởi `ReactiveAuthenticationManager` trong request trên event loop, luồng có thể bị chặn. Đổi thành `Mono.just(legacyStore.findByUsername(username))` cũng không giúp ích vì đối số được tính trước khi `Mono.just` chạy.

Thậm chí:

~~~java
return Mono.fromCallable(() -> legacyStore.findByUsername(username));
~~~

mặc dù đã **lazy**, nhưng nếu subscribe xảy ra trên event loop, callable vẫn có thể chạy blocking ở đó. Phải điều chỉnh cả **thời điểm thực thi** và **scheduler thực thi**.

### 5.2. Adapter đúng khi bắt buộc phải dùng legacy store

Mã minh họa sau là một adapter Java độc lập về mặt class, biên dịch được trong module có Spring Security và Reactor. `LegacyStore` là interface do bạn hiện thực bằng datasource hiện có, nên đoạn này **không tự kết nối database**:

~~~java
package demo.security.reactive;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LegacyUserDetailsAdapter
        implements ReactiveUserDetailsService {

    public interface LegacyStore {
        // Truy vấn đồng bộ, có thể chờ I/O.
        UserDetails findByUsername(String username);
    }

    private final LegacyStore store;

    public LegacyUserDetailsAdapter(LegacyStore store) {
        this.store = store;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return Mono.fromCallable(
                    () -> store.findByUsername(username))
                .subscribeOn(Schedulers.boundedElastic())
                .switchIfEmpty(Mono.error(
                    new UsernameNotFoundException(username)));
    }
}
~~~

Cơ chế theo thứ tự:

1. Gọi `findByUsername` tạo `Mono` lạnh mà **chưa truy vấn** store.
2. Khi authentication pipeline subscribe, `subscribeOn` yêu cầu worker boundedElastic thực hiện nguồn `fromCallable`.
3. Kết quả `UserDetails` được phát xuống chuỗi reactive; `null` từ callable trở thành publisher empty và nhánh `switchIfEmpty` chuyển thành `UsernameNotFoundException`.
4. Reactor Context được truyền theo cơ chế operator khi đổi scheduler; không nên tự khởi tạo thread rồi dựa vào `SecurityContextHolder` ThreadLocal của servlet để đoán danh tính.

Trong production, adapter nên có thêm **timeout thích hợp tại client/driver**, giới hạn số kết nối, giới hạn concurrency, và giám sát queue/latency. `Mono.timeout` giới hạn thời gian chờ theo góc nhìn subscriber nhưng **không mặc nhiên hủy** một thao tác JDBC đồng bộ đang kẹt trong driver; timeout của driver/network vẫn quan trọng. Không chủ động tạo một thread mới cho từng request.

### 5.3. Liên hệ `SecurityWebFilterChain` và method security

Một ứng dụng có thể có cả authorization ở `SecurityWebFilterChain` lẫn `@EnableReactiveMethodSecurity`. BlockHound không biết “request nào là login” hoặc “annotation nào là `@PreAuthorize`”; nó quan sát **lời gọi blocking trên thread không được phép blocking**. Nếu expression, custom authorization service hoặc logic được gọi sau `@PreAuthorize` chạy một API đồng bộ trên event loop, BlockHound có thể nêu vị trí gần phương thức blocking, không tự kết luận rule bảo mật đúng/sai.

Ví dụ đường chạy cần chủ động kiểm tra:

~~~text
POST /login hoặc GET /private
   -> reactive authentication (lookup user / validate token)
   -> authorization
   -> secured service
   -> data source
~~~

Một test kiểu `StepVerifier` trực tiếp trên service có thể cố định `Schedulers.parallel()` để **chứng minh adapter cũ gây lỗi**. Sau khi sửa, test trên service phải hoàn thành như mong đợi. Với đường HTTP đầy đủ, dùng Spring Boot/WebFlux test hoặc `WebTestClient` cấu hình security chain thực và chạy request qua server; không thay service thật bằng Mockito mock nếu mục đích là tìm blocking bên trong chính service đó. Thao tác `WebTestClient.bindToController` đơn thuần hoặc test khởi tạo publisher trên thread JUnit **không đương nhiên tạo ra event-loop scenario** như production.

Để đảm bảo phép thử integration có ý nghĩa, cần kiểm:

- Request thật sự đi qua authentication/authorization path liên quan.
- BlockHound đã cài trong **cùng JVM** xử lý đoạn cần quan sát.
- Có ít nhất một test canary xác nhận agent được instrument; thiếu lỗi BlockHound trong một test HTTP **không tự chứng minh** mọi nhánh đều non-blocking.
- Trường hợp deny hoặc unauthenticated có thể kết thúc sớm: muốn kiểm lookup bên trong thì phải có fixture/request khiến lookup thực sự được gọi.

## 6. Vị trí đặt `subscribeOn`, `publishOn` và lỗi nhầm thường gặp

### Trường hợp SAI: blocking xảy ra trước khi tạo `Mono`

~~~java
String value = legacyClient.fetchSync();  // blocking xảy ra NGAY
return Mono.just(value)
           .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` tác động đến quá trình **subscribe publisher**, không thể quay ngược thời gian để dịch một `fetchSync()` đã chạy xong. Hơn nữa, đặt `publishOn(boundedElastic)` ở sau lời gọi đồng bộ này cũng không giúp vì nguồn đã thực thi.

### Trường hợp ĐÚNG: đưa lời gọi blocking vào nguồn lazy

~~~java
return Mono.fromCallable(() -> legacyClient.fetchSync())
           .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` bảo đảm lời gọi được trì hoãn tới subscription; `subscribeOn` chỉ định scheduler cho subscription/source. Một `publishOn` phù hợp có thể chuyển các operator **phía sau nó**, nhưng không thay thế cách cô lập nguồn synchronous blocking khi nguồn chạy trước điểm chuyển. Khi ghép nhiều publisher, xem luồng thực thi của từng nguồn/`flatMap`, đừng chỉ nhìn scheduler trên publisher ngoài cùng.

### Trường hợp nguy hiểm: gọi `block()` ở trong pipeline

~~~java
return reactiveHttpClient.get()
    .retrieve()
    .bodyToMono(String.class)
    .map(body -> anotherMono().block()); // Không dùng trên event loop.
~~~

Reactor chủ động từ chối nhiều lời gọi `block()` khi chúng chạy trên thread được đánh dấu non-blocking. Lỗi thường có dạng `IllegalStateException` nói rằng `block()/blockFirst()/blockLast()` không được hỗ trợ trên thread đó. Điều này khác với primitive như `Thread.sleep` do BlockHound báo thành `BlockingOperationError`. Sửa bằng cách **ghép publisher** qua `flatMap`/`zipWhen` thay vì chờ đồng bộ:

~~~java
return reactiveHttpClient.get()
    .retrieve()
    .bodyToMono(String.class)
    .flatMap(body -> anotherMono()
        .map(other -> body + ":" + other));
~~~

Hai snippet sử dụng `reactiveHttpClient` và `anotherMono()` làm dependency giả định để minh họa **cấu trúc operator**, không phải chương trình Java độc lập. Trong code thật, khai báo/import chúng theo client/service của dự án.

## 7. Đưa BlockHound vào quy trình kiểm thử có kiểm soát

**Ở mức unit/reactor test:** test tác vụ blocking bằng nguồn lazy, chạy trên `Schedulers.parallel()` và đợi `BlockingOperationError`. Đặt thêm test phiên bản đã sửa chạy trên boundedElastic; kết quả phải đúng và toàn pipeline phải complete. Đây là mức thử nhanh, ổn định, không cần cổng HTTP.

**Ở mức Spring integration test:** chạy bean/security chain thật; với các service đụng data source, dùng fake/stub được kiểm soát tại **dependency** của service để mô phỏng lời gọi blocking đã biết, nhưng không mock bỏ đoạn code cần kiểm. Khi test request thực tế, xác nhận đường đi qua login/token lookup hoặc protected handler trước khi kết luận. Đặt BlockHound ở bootstrap của JVM, không mỗi test tự cấu hình các whitelist khác nhau.

**Ở mức CI:** chạy tập test canary luôn; nếu instrumentation thất bại do JDK/agent thì fail build và điều tra nguyên nhân. Nên có job tích hợp dành cho cấu hình JDK/Spring Boot đang hỗ trợ. Thêm benchmark/load test đo p50/p95/p99, throughput, hàng đợi/kết nối và tài nguyên thread để đánh giá sửa chữa có hiệu quả dưới tải thật.

**Tách lỗi ứng dụng khỏi lỗi instrumentation:**

| Triệu chứng | Khả năng | Hành động |
| --- | --- | --- |
| `BlockHound.install()` lỗi trước khi test chạy | JVM không cho attach/redefinition hoặc agent không tương thích | Đọc stack trace setup, xác minh JDK, dependency, JVM flags; không coi kết quả là “không có blocking” |
| Canary `Thread.sleep` trên `parallel()` **không** phát `BlockingOperationError` | Agent không hoạt động hoặc call không chạy trên non-blocking thread | Kiểm installer chạy chưa, scheduler là `parallel` chưa, có subscribe thật chưa |
| Stack trace nêu `Blocking call! ...Thread.sleep` | Có lời gọi blocking được theo dõi trên non-blocking thread | Tìm dòng ứng dụng gần nhất trong trace; thay API hoặc cách ly nguồn lazy trên boundedElastic |
| Có `IllegalStateException` về `block()` | Vi phạm rule Reactor khi block ở non-blocking thread | Xóa lời gọi `block()`, ghép chuỗi bằng reactive operator |
| Test trực tiếp từ thread JUnit “không báo” nhưng request chậm | Không mô phỏng thread non-blocking hoặc chưa chạm nhánh có lỗi | Ép đúng scheduler ở unit test; dùng server integration và đo tải |
| Canary PASS nhưng p99 vẫn cao | CPU-heavy, I/O ngoài phạm vi instrument, contention, quá tải boundedElastic hoặc nhiều nguyên nhân khác | Profiler/JFR, Reactor/Netty metrics, driver metrics và load test |

## 8. Tùy biến BlockHound: phải thu hẹp và có giải trình

BlockHound cho phép tùy biến một số hành vi bằng `BlockHoundIntegration`/`BlockHound.Builder`. Một ví dụ API là:

~~~java
BlockHound.install(builder ->
    builder.allowBlockingCallsInside(
        "com.example.legacy.LibraryInternals",
        "initializeCache"));
~~~

Đây là **ví dụ cấu hình**, chỉ dùng nếu đã kiểm chứng vùng gọi blocking đó thật sự chấp nhận được ở đúng hoàn cảnh của nó. Nó **không phải** giải pháp chung để bỏ qua lỗi. Tên class/method trên là giả định, không tồn tại sẵn trong framework. Và vì `install` thực hiện một lần cho cả JVM, phải đặt tùy biến ngay khi cài agent; một `install` muộn có thể không áp dụng như bạn tưởng.

Khi nào có thể cân nhắc allowlist? Ví dụ một thư viện có bước khởi tạo đồng bộ ngắn được chứng minh chỉ chạy trước khi server nhận request, nhưng instrumentation cảnh báo ở một test setup đặc biệt. Trước khi cho phép, cần có bằng chứng về thời điểm gọi, phạm vi ảnh hưởng, chi phí, và test riêng bảo đảm đường request thật không phụ thuộc vào ngoại lệ đó. Không whitelist mọi lời gọi trong `ReactiveAuthenticationManager`, event loop, controller hay scheduler chỉ để CI xanh.

Nếu có custom native/blocking method mà BlockHound không nhận diện, Builder còn có khả năng `markAsBlocking` với tên class/method và JVM method descriptor chính xác. Cách này nên đi kèm test canary riêng vì sai descriptor hoặc JDK thay đổi có thể làm test “lọt” lỗi.

Một số hạn chế cần luôn ghi nhớ:

- BlockHound chỉ phát hiện các primitive/phương thức đã được instrument trên những thread nằm trong non-blocking predicate. `boundedElastic` không bị mặc định đánh dấu non-blocking; một test “không lỗi” ở pool này không chứng minh code không blocking.
- Cài instrumentation có thể phụ thuộc phiên bản JDK, quyền agent attach và thứ tự khởi tạo thư viện. Test không được im lặng bỏ qua lỗi cài.
- BlockHound không thể thay thế bảo vệ resource exhaustion. Dùng boundedElastic có giới hạn; yêu cầu concurrency cao cần driver non-blocking hoặc thiết kế kiểm soát tải.
- ThreadLocal và Reactor Context không giống nhau; tự chuyển sang `Thread`/`CompletableFuture` không tự bảo toàn authentication context. Giữ pipeline bằng Reactor operator và kiểm tra việc truyền context khi tích hợp Spring Security.
- Việc xử lý lỗi `BlockingOperationError` ở middleware không nên biến lỗi hiệu năng nghiêm trọng thành response “thành công”; nên để kiểm thử phát hiện và sửa nguyên nhân ở nguồn.

## 9. Checklist đánh giá bài thực hành

Có thể coi bài lab hoàn thành khi:

1. Test `detectsBlockingOnNonBlockingScheduler` PASS **vì đã nhận được** `BlockingOperationError` từ một lời gọi `Thread.sleep` đã biết trên `Schedulers.parallel()`.
2. Nếu tạm tắt cài BlockHound (trong môi trường thử biệt lập), canary chuyển sang FAIL; điều này chứng minh test thực sự phụ thuộc agent.
3. Test tác vụ blocking được chuyển sang `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` trả giá trị chính xác và hoàn thành trong timeout.
4. Giải thích được vì sao `Mono.just(legacyStore.find(...))` và `Mono.fromCallable(... )` không có scheduler vẫn có thể blocking trên event loop.
5. Chỉ ra được vị trí trong luồng Spring Security Reactive có khả năng blocking (user lookup, token/introspection, audit, authorization service), phân biệt kiểm tra ở service và kiểm tra request qua security filter chain.
6. Khi test đỏ, xác định nguyên nhân từ **lỗi cài agent**, **lỗi non-blocking thread**, **lỗi code thực thi** hoặc **giới hạn của công cụ** thay vì tăng timeout hoặc whitelist tràn lan.
7. Đánh giá performance bằng metrics/profiling/load test riêng, không kết luận “không có blocking” chỉ từ một suite có BlockHound chạy xanh.

## Tài liệu tham khảo

- BlockHound README (cơ chế instrumentation, cách cài, yêu cầu JVM): https://github.com/reactor/BlockHound
- BlockHound Quick start (test canary và cài agent): https://github.com/reactor/BlockHound/blob/master/docs/quick_start.md
- BlockHound Customization (allow/disallow và khả năng tùy biến): https://github.com/reactor/BlockHound/blob/master/docs/customization.md
- BlockHound releases (đối chiếu bản stable/JDK): https://github.com/reactor/BlockHound/releases
- Reactor Core Reference, FAQ “How Do I Wrap a Synchronous, Blocking Call?”: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Security Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
