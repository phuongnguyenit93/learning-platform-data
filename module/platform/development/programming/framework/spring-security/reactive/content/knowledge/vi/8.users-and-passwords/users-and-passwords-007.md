# Lập lịch kiểm tra mật khẩu tốn CPU và đánh giá ảnh hưởng đến luồng sự kiện

## Mục tiêu và phạm vi

Trong **Spring Security - reactive**, HTTP request thường được xử lý bằng Spring WebFlux trên các thread event loop. Tuy nhiên, việc đối chiếu mật khẩu bằng BCrypt, PBKDF2, scrypt hoặc Argon2 là một phép tính **cố tình tốn CPU (và có thể tốn bộ nhớ)**. Nếu đặt phép tính này trên event loop, các request khác có thể phải chờ, dù ứng dụng sử dụng `Mono` và `Flux`.

Sau bài học thuộc nhóm **Người dùng và mật khẩu**, bạn có thể:

1. Giải thích vì sao `PasswordEncoder.matches(...)` là thao tác đồng bộ tốn tài nguyên và phân biệt nó với I/O blocking.
2. Dự đoán hậu quả khi hash/verify chạy trên thread Netty event loop.
3. Dùng `Mono.fromCallable(...)`, `subscribeOn(...)` và scheduler phù hợp khi tự viết pipeline.
4. Hiểu cách `UserDetailsRepositoryReactiveAuthenticationManager` của Spring Security **đã lập lịch riêng cho việc kiểm tra mật khẩu**; biết khi nào nên dùng `setScheduler(...)`.
5. Cấu hình một scheduler dành riêng cho CPU hashing, định cỡ theo CPU và kiểm soát tải chờ.
6. Dựng ví dụ Java 17+, kiểm chứng thread chạy BCrypt, kết quả xác thực và độ trễ của endpoint không cần đăng nhập.
7. Đo **throughput, p95/p99, event-loop delay, CPU saturation, queueing** dưới tải và đề xuất biện pháp giảm ảnh hưởng mà không hạ thấp độ an toàn mật khẩu.

**Ý chính:** Reactive giúp giải phóng thread khi *đợi I/O*; nó không làm BCrypt tính nhanh hơn. Đổi scheduler chỉ chuyển nơi tiêu thụ CPU. Nếu tổng nhu cầu tính toán vượt năng lực máy, hàng đợi và độ trễ vẫn tăng.

## 1. Tại sao xác thực mật khẩu chủ đích phải chậm?

`PasswordEncoder` của Spring Security có API đồng bộ:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

`encode` tạo hash một chiều để lưu; `matches` kiểm tra mật khẩu được cung cấp với hash đã lưu. Mật khẩu gốc không nên xuất hiện trong database hoặc log.

Các thuật toán hash mật khẩu hiện đại sử dụng **work factor** và salt nhằm tăng chi phí brute force nếu hash bị lộ:

| Cơ chế | Tài nguyên chính | Điều cần đo |
| --- | --- | --- |
| BCrypt | CPU; cost theo lũy thừa | Thời gian mỗi lần `matches` khi tăng strength/cost |
| PBKDF2 | CPU theo số vòng lặp | Thời gian và khả năng tương thích chính sách mật mã |
| scrypt | CPU và bộ nhớ | Thời gian, RAM khi nhiều verify đồng thời |
| Argon2 | Bộ nhớ và CPU | Time cost, memory cost, parallelism, RAM/GC của container |

Trong hướng dẫn lưu mật khẩu, Spring Security khuyến nghị điều chỉnh work factor để một phép kiểm tra khoảng **một giây trên phần cứng triển khai** như một điểm tham khảo, rồi đo và cân đối latency/tài nguyên theo hệ thống thực. **Không coi 1 giây là SLA cố định** hoặc mức tối ưu cho mọi sản phẩm. Máy, CPU quota, thuật toán, bộ nhớ và nhu cầu đăng nhập đều ảnh hưởng đến quyết định. Mặc định `BCryptPasswordEncoder()` dùng strength 10, không chứng minh hệ thống của bạn sẽ mất đúng một khoảng thời gian nào.

Hash chậm là đặc tính an ninh. Các cách “tối ưu” như lưu mật khẩu rõ, dùng `NoOpPasswordEncoder`, dùng SHA-256 đơn lẻ hoặc hạ work factor không kiểm chứng **không phải** giải pháp cho hiện tượng nghẽn event loop.

Một người dùng thường nên dùng mật khẩu cho **bước đăng nhập**, sau đó tiếp tục bằng session hoặc credential ngắn hạn thích hợp; không nên chạy BCrypt cho **mọi request** chỉ vì muốn giữ ứng dụng stateless. Nếu API dùng HTTP Basic trên mỗi request, hãy tính số lần verify phát sinh tương ứng với lưu lượng request, không chỉ số phiên đăng nhập.

## 2. Event loop của WebFlux làm gì?

Với Spring Boot WebFlux chạy trên Reactor Netty, các luồng `reactor-http-nio-*` thường thực hiện nhiệm vụ nhận HTTP, chuyển dữ liệu, xử lý pipeline không blocking và ghi phản hồi. Chúng phải quay lại phục vụ nhiều connection.

```text
                         Spring WebFlux / Reactor Netty
Request A -----\
Request B ------> event-loop thread -- parse, route, schedule, write response
Request C -----/                |
                                +--> nếu chạy BCrypt trực tiếp ở đây:
                                     CPU chạy hàng trăm ms hoặc hơn
                                     thread chưa thể phục vụ B/C trong lúc đó
```

Để giữ responsiveness, những công việc chạy lâu phải rời event loop hoặc được thiết kế bất đồng bộ phù hợp. **Không đồng nhất CPU-bound và blocking I/O:**

- **CPU-bound:** `BCryptPasswordEncoder.matches` chiếm CPU để tính toán; method đồng bộ chỉ trả về sau khi tính xong. Nó không chờ network nhưng **giữ thread** suốt thời gian chạy.
- **Blocking I/O:** JDBC đồng bộ, đọc file đồng bộ hoặc gọi HTTP client blocking thường khiến thread **đợi** tài nguyên bên ngoài.
- **Nonblocking I/O:** reactive driver trả publisher khi đang đợi DB/network; event loop có thể phục vụ việc khác.
- **Memory-hard hash:** scrypt/Argon2 còn tiêu tốn RAM, gây pressure khi số job chạy cùng lúc lớn.

Reactor `Mono` chỉ định nghĩa cách phát tín hiệu; viết `Mono.just(encoder.matches(raw, hash))` **không** biến phép tính thành bất đồng bộ: Java đánh giá đối số trước khi tạo `Mono.just`.

### Hai luồng thời gian minh họa

```text
Sai: verify đồng bộ trong event loop

event-loop: [read A][BCrypt A .....................][respond A][read B]...
password CPU:    cùng thread event-loop bị chiếm

Đúng hướng: chuyển verify sang worker CPU có giới hạn

event-loop: [read A][schedule BCrypt A][read B][route B][respond B]...
pwd-worker:             [BCrypt A .............]
event-loop:                                            [respond A]

Tải cao: nhiều BCrypt hơn số worker/CPU -> job vẫn phải chờ trong queue.
```

Các dấu chấm chỉ minh họa thời lượng, không đại diện số mili giây đo thực tế.

## 3. Chọn scheduler: parallel, boundedElastic và immediate

Reactor cung cấp nhiều `Scheduler`:

| Scheduler | Mục đích thông thường | Có nên dùng cho password verify? |
| --- | --- | --- |
| `Schedulers.parallel()` | Công việc CPU ngắn hoặc có giới hạn; pool mặc định liên quan số CPU | Về loại workload là phù hợp, nhưng dùng **pool chia sẻ** có thể cạnh tranh với timer/operator khác |
| `Schedulers.newParallel("password-work", n)` | Pool CPU riêng, có thể định số worker và tên thread | Lựa chọn hữu ích để **cách ly việc hashing** khỏi scheduler `parallel` chia sẻ |
| `Schedulers.boundedElastic()` | Bọc nguồn **blocking I/O**; có giới hạn thread và queue | Không phải mặc định tối ưu cho việc chỉ tiêu thụ CPU; nhiều worker cùng chạy có thể làm quá tải CPU |
| `Schedulers.single()` | Một worker tuần tự | Dễ thành nút cổ chai cho nhiều lần hash |
| `Schedulers.immediate()` | Chạy ngay trên thread hiện tại | Rủi ro nếu thread là Netty event loop |
| Tự tạo `newBoundedElastic(...)` | Đồng bộ/blocking có cấu hình giới hạn thread/queue | Phù hợp khi tác vụ phải **đợi I/O**; không tự làm việc tính mật khẩu nhanh hơn |

Một chi tiết dễ bỏ sót: **`parallel` của Reactor là scheduler dùng chung trong nhiều operator**. Nếu toàn bộ hashing được chạy trên pool này và chiếm CPU liên tục, những tác vụ khác dùng `Schedulers.parallel()` có thể trễ. Một `newParallel` có tên riêng giúp cô lập **hàng đợi và thread**, nhưng **không cô lập CPU vật lý**: các pool vẫn tranh cùng CPU quota. Vì vậy cần đo CPU và số job active, không kết luận “có pool riêng là hết nghẽn”.

**Virtual threads** cũng không rút ngắn phép tính CPU thuần. Chúng hữu ích cho mô hình chờ blocking trong những điều kiện nhất định, không nhân năng lực CPU của container.

### Về mặc định của Spring Security

`UserDetailsRepositoryReactiveAuthenticationManager` kế thừa `AbstractUserDetailsReactiveAuthenticationManager`; API Spring Security mô tả `setScheduler(Scheduler)` và mặc định dùng một scheduler kiểu `Schedulers.newParallel(String)` cho kiểm tra mật khẩu, vì hash mật khẩu là CPU intensive. Vì thế:

- Nếu bạn đang dùng **manager chuẩn** để xác thực username/password, hãy **kiểm tra nó trước**: phần verify đã có lập lịch phù hợp, không cần bọc toàn bộ authenticate bằng một `subscribeOn` khác chỉ vì thấy nó trả `Mono`.
- Nếu muốn **cách ly**, đặt số thread, tên thread và lifecycle của pool theo ứng dụng, dùng `setScheduler(...)` trên manager **đúng instance thực sự được HTTP Basic/form login sử dụng**.
- Nếu bạn tự gọi `PasswordEncoder.matches` bên ngoài manager, chính bạn phải quyết định nơi thực hiện phép tính, ví dụ `Mono.fromCallable(...).subscribeOn(dedicatedScheduler)`.
- Không dùng `Schedulers.immediate()` cho BCrypt chỉ để né bước lập lịch; có thể đẩy phép tính trở lại event loop.

Tài liệu API theo phiên bản có thể khác tên class/javadoc; luôn kiểm tra version Spring Security được Spring Boot BOM chọn.

## 4. Bọc một lời gọi PasswordEncoder đúng cách

Giả sử `encoder` là `BCryptPasswordEncoder` và `storedHash` đã được nạp từ kho người dùng.

### 4.1. Sai: tính trước khi tạo Mono

```java
// Sai nếu đang chạy trên event loop:
Mono<Boolean> verified =
        Mono.just(encoder.matches(rawPassword, storedHash));
```

`matches` được gọi **ngay tại thời điểm dựng biểu thức**, trên thread gọi đoạn code; không có phép lập lịch nào xảy ra trước khi CPU bị chiếm. Cũng không giúp được nếu viết:

```java
Mono<Boolean> verified =
        Mono.just(encoder.matches(rawPassword, storedHash))
                .subscribeOn(passwordScheduler);
```

`subscribeOn` chỉ tác động tới quá trình subscribe **sau khi** `Mono.just` đã được tạo. Phép tính đã chạy xong trên thread ban đầu.

### 4.2. Đúng: lười đánh giá và lập lịch ngay tại nguồn

```java
// Mảnh code dùng trong một authentication service tùy biến:
Mono<Boolean> verified =
        Mono.fromCallable(
                () -> encoder.matches(rawPassword, storedHash))
            .subscribeOn(passwordScheduler);
```

`Mono.fromCallable` trì hoãn gọi `matches` tới khi có subscriber. `subscribeOn` yêu cầu nguồn chạy trên scheduler chỉ định. Với mỗi subscription, hash được kiểm tra và phát Boolean hoặc `onError` nếu có exception.

**Vẫn phải trả kết quả bằng pipeline, không `block()` hoặc `subscribe()` độc lập**:

```java
// Mảnh code minh họa, không phải controller hoàn chỉnh.
// Không bao giờ trả true trước khi verify xong.
return Mono.fromCallable(
            () -> encoder.matches(rawPassword, storedHash))
        .subscribeOn(passwordScheduler)
        .flatMap(matches ->
            matches ? Mono.just(authentication)
                    : Mono.error(new BadCredentialsException(
                            "Bad credentials")));
```

Ở đây `authentication` là kết quả xác thực do application xây dựng đúng hợp đồng; còn `BadCredentialsException` thuộc Spring Security. Đừng cho phép truy cập chỉ vì repository hoặc scheduler lỗi. Không lộ trong response thông tin “user không tồn tại” hay “mật khẩu sai” quá chi tiết.

### 4.3. publishOn khác subscribeOn

`publishOn(scheduler)` chuyển **các toán tử downstream** sang scheduler đó. Nếu bạn đã thực hiện hash ở phía **upstream** thì đặt `publishOn` sau lời gọi không thể “đưa CPU về quá khứ”.

```java
// Có tác dụng nếu pipeline upstream chưa gọi matches:
Mono<Boolean> example =
        Mono.just(storedHash)
            .publishOn(passwordScheduler)
            .map(hash -> encoder.matches(rawPassword, hash));
```

Dạng này có thể đúng trong tình huống đơn giản, nhưng khi **tự bọc một phương thức đồng bộ độc lập**, mẫu `fromCallable(...).subscribeOn(passwordScheduler)` thường dễ đọc và ít nhầm hơn. Hạn chế `publishOn` không cần thiết vì mỗi lần đổi scheduler có overhead và thay đổi vị trí chạy toán tử downstream.

### 4.4. Không tạo scheduler cho từng request

```java
// Sai: mỗi request tạo thread pool mới, khó quản lý tài nguyên.
Mono.fromCallable(() -> encoder.matches(raw, hash))
    .subscribeOn(Schedulers.newParallel("one-request", 4));
```

Hãy tạo **một scheduler dùng chung do ứng dụng quản lý**, và đóng/dispose khi ứng dụng dừng. Tên thread, số worker và giới hạn tải phải thống nhất với ngân sách CPU.

## 5. Ví dụ Spring Security reactive chạy được với Java 17+

Ứng dụng dùng Spring Boot **3.3.13**, WebFlux, HTTP Basic và BCrypt. Để người học nhìn thấy lập lịch thật, ví dụ tạo `UserDetailsRepositoryReactiveAuthenticationManager`, gắn scheduler `newParallel("pwd-verify", n)` và dùng một `PasswordEncoder` có ghi nhận **tên thread + thời gian verify**; nó không in raw password, hash hay Authorization header.

### 5.1. File và dependency

Cấu trúc:

```text
password-scheduling-demo/
  settings.gradle
  build.gradle
  src/main/java/example/PasswordSchedulingApplication.java
  src/test/java/example/PasswordSchedulingApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'password-scheduling-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` của Servlet vào dự án WebFlux mẫu. Plugin và dependency management chọn các bản Spring Security, Reactor tương thích. Trong ứng dụng production, cập nhật lên bản còn được hỗ trợ theo chính sách của tổ chức; bản cố định trên dùng để giữ ví dụ tái lập.

### 5.2. Ứng dụng hoàn chỉnh

Tạo `src/main/java/example/PasswordSchedulingApplication.java`:

```java
package example;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class PasswordSchedulingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordSchedulingApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/private")
    public String privateData() {
        return "PRIVATE_OK";
    }

    @Bean(destroyMethod = "dispose")
    Scheduler passwordScheduler() {
        int cpus = Runtime.getRuntime().availableProcessors();
        int threads = Math.max(1, Math.min(cpus, 4));
        return Schedulers.newParallel("pwd-verify", threads);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

        return new PasswordEncoder() {
            @Override
            public String encode(CharSequence rawPassword) {
                return bcrypt.encode(rawPassword);
            }

            @Override
            public boolean matches(CharSequence raw, String encoded) {
                long started = System.nanoTime();
                try {
                    return bcrypt.matches(raw, encoded);
                }
                finally {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);
                    System.out.println("password-verify thread="
                            + Thread.currentThread().getName()
                            + " elapsedMs=" + elapsedMs);
                }
            }

            @Override
            public boolean upgradeEncoding(String encodedPassword) {
                return bcrypt.upgradeEncoding(encodedPassword);
            }
        };
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("alice")
                .password(encoder.encode("learn"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder,
            Scheduler passwordScheduler) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setScheduler(passwordScheduler);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
                .authenticationManager(manager)
                .authorizeExchange(ex -> ex
                        .pathMatchers("/ping").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Các điểm cần đọc đúng trong ví dụ:**

1. `PasswordEncoder.matches` vẫn là BCrypt **đồng bộ**. Bao ngoài bằng encoder instrumentation để biết nó chạy trên thread nào và mất bao nhiêu thời gian. `encode("learn")` diễn ra **một lần lúc tạo user demo**, không phải kết quả benchmark.
2. `UserDetailsRepositoryReactiveAuthenticationManager` thực hiện username/password authentication. Nó đã có scheduler kiểu parallel mặc định, nhưng ở đây `setScheduler(passwordScheduler)` **chủ động thay pool** bằng pool riêng để quan sát/giới hạn.
3. `Schedulers.newParallel("pwd-verify", threads)` tạo pool riêng với số worker không quá 4 trong demo và không quá số logical CPU nhìn thấy. Con số 4 chỉ là lựa chọn minh họa, **không phải cấu hình khuyên dùng cho mọi môi trường**; phải đo theo CPU quota và số instance.
4. `@Bean(destroyMethod = "dispose")` đảm bảo scheduler do ứng dụng sở hữu được dispose khi ApplicationContext đóng.
5. `.authenticationManager(manager)` gắn đúng manager vào `ServerHttpSecurity`, thay vì tạo bean rồi để pipeline Basic thực dùng manager khác.
6. `/ping` là endpoint công khai, **không cần BCrypt**. `/private` yêu cầu HTTP Basic, nên mỗi yêu cầu kèm username/password có thể kích hoạt verify.
7. Không in mật khẩu, hash hoặc header Basic. `System.out.println` chỉ để quan sát thread tại máy học; production nên dùng metric/timer tối thiểu và không đặt logging blocking trên đường nóng.
8. `BCryptPasswordEncoder(10)` chỉ là cấu hình mẫu. Hãy đánh giá cost theo hệ thống thật và chính sách mật khẩu trước khi triển khai.

### 5.3. Chạy và kiểm tra

Yêu cầu JDK 17+ và Gradle 7.5+/8.x tương thích Spring Boot 3.3.13. Từ thư mục dự án:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Mở terminal khác:

```bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/private
curl -i -u alice:learn http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
```

Kết quả nghiệp vụ mong đợi:

| Request | Kết quả HTTP | Body/ý nghĩa |
| --- | --- | --- |
| `GET /ping` không credentials | `200` | `PONG` |
| `GET /private` không credentials | `401` | Basic challenge, handler bảo vệ chưa được gọi |
| `GET /private` Basic `alice:learn` | `200` | `PRIVATE_OK` |
| `GET /private` Basic `alice:wrong` | `401` | Mật khẩu sai, không được cấp quyền |

Mỗi yêu cầu có password và user hợp lệ có thể tạo log có dạng:

```text
password-verify thread=pwd-verify-1 elapsedMs=...
```

Ký tự `...` thể hiện con số thực tế thay đổi theo phần cứng và tải. Tên cuối thread có thể là `pwd-verify-2`, v.v. **Đừng viết kiểm thử dựa vào số mili giây chính xác**. Điều đáng xác minh là prefix `pwd-verify-`: phép tính được thực hiện trên scheduler riêng, **không trên `reactor-http-nio-*`**.

Tại thời điểm chạy `GET /ping`, không có lời gọi `matches` từ endpoint này. Điều đó giúp dùng `/ping` làm probe đo responsiveness khi các request `/private` chạy đồng thời.

## 6. Unit test kiểm tra scheduler và HTTP behavior

Tạo `src/test/java/example/PasswordSchedulingApplicationTests.java`:

```java
package example;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class PasswordSchedulingApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequirePassword() {
        client.get().uri("/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void privateEndpointRequiresAuthentication() {
        client.get().uri("/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctPasswordSucceeds() {
        client.get().uri("/private")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PRIVATE_OK");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/private")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void callableRunsOnDedicatedScheduler() {
        Scheduler scheduler = Schedulers.newParallel("pwd-test", 1);
        try {
            BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(10);
            String hash = encoder.encode("learn");
            AtomicReference<String> thread = new AtomicReference<>();

            Mono<Boolean> verify = Mono.fromCallable(() -> {
                thread.set(Thread.currentThread().getName());
                return encoder.matches("learn", hash);
            }).subscribeOn(scheduler);

            StepVerifier.create(verify)
                    .expectNext(true)
                    .verifyComplete();

            assertTrue(thread.get().startsWith("pwd-test-"));
        }
        finally {
            scheduler.dispose();
        }
    }
}
```

Chạy:

```bash
gradle test
```

Test HTTP kiểm tra chức năng security chain; test `StepVerifier` kiểm tra việc `fromCallable.subscribeOn` dùng đúng worker của pool được đặt tên. **Không dùng test thread name làm bằng chứng hiệu năng đạt SLA.** Hiệu năng phải được đo dưới tải ổn định và hạ tầng thật, còn test scheduler bảo đảm cơ chế lập lịch hoạt động.

Nếu thay custom scheduler bằng mặc định của manager, bạn vẫn cần kiểm tra nó sử dụng scheduler nào trong **phiên bản Spring Security cụ thể**. Không tự bọc manager bằng thêm một scheduler rồi kết luận BCrypt đã được chuyển đúng nếu chưa quan sát nguồn thực thi.

## 7. Tính toán năng lực và hàng đợi: vì sao chỉ thêm thread không đủ?

Giả sử trung bình mỗi phép BCrypt mất `S` giây CPU/worker và một máy có khả năng thực thi hiệu quả `C` phép đồng thời. Năng lực lý tưởng xấp xỉ:

```text
throughput_lý_tưởng ≈ C / S   (lần verify/giây)
mức_tải_xấp_xỉ    ≈ λ × S / C
```

Trong đó `λ` là số **yêu cầu verify thực sự tới mỗi giây trên cùng instance**. Đây là ước lượng sơ bộ cho workload CPU-heavy; không phải công thức dự báo chính xác khi có I/O, GC, contention, cgroup throttling, startup cost hoặc điều chỉnh work factor.

Ví dụ giả định **không phải số đo của ứng dụng**:

- CPU có hiệu năng tương đương khoảng 4 worker hash hoạt động.
- Mỗi verify cần trung bình 250 ms = 0,25 giây.
- Năng lực tối đa lý tưởng: `4 / 0,25 = 16 verify/giây`.
- Nếu tải trung bình `20 verify/giây`, số việc đến **nhiều hơn** năng lực xử lý; queue có xu hướng tăng ngay cả khi event loop được giải phóng.
- Tăng worker lên 16 trên máy chỉ có 4 CPU **không tạo ra** năng lực CPU tương đương 16 core; overhead/context switching còn có thể làm tệ hơn.

| Tình trạng | Thấy gì trong chỉ số | Hành động phân tích |
| --- | --- | --- |
| CPU còn dư, ít queue | Thời gian hash gần baseline | Chưa cần tăng thread |
| Worker password luôn bận, queue tăng | Login p95/p99 tăng | Giới hạn concurrency, rate limit hoặc bổ sung năng lực |
| CPU 100% / cgroup throttling | Cả `/ping` cũng chậm | Xem CPU quota, số pod, worker, phân phối tải |
| RAM/GC tăng khi dùng Argon2 | Pause hoặc OOM risk | Giảm job đồng thời, đo memory cost |
| Event loop trì trệ dù password worker chưa bận | Có thể có blocking/CPU khác trên event loop | Profiling thread/stack, BlockHound trong test phù hợp |
| Throughput thấp nhưng CPU thấp | Có thể do DB/users lookup, lock, queue hoặc mạng | Phân tách thời gian lookup, scheduler wait, hash |

Tách **thời gian chờ trong queue** khỏi **thời gian thực thi `matches`**. Timer chỉ đặt trong `PasswordEncoder.matches` sẽ đo được thời gian hash trên worker nhưng **không bao gồm thời gian yêu cầu đợi đến lượt worker**. Để giải thích p99 login, cần đo tổng request và khoảng chờ admission/scheduler nếu có.

### Điều gì xảy ra khi queue tăng?

Một `newParallel` có số worker hữu hạn, nhưng **không đồng nghĩa số tác vụ chờ được giới hạn ở mức an toàn cho API**. Nếu client liên tục gửi request và mỗi lần tạo thêm một công việc chờ, bộ nhớ và latency có thể tăng. Hãy dùng:

- Giới hạn số login attempts đồng thời trên toàn instance theo ngân sách CPU/memory.
- Rate limiting theo IP/tài khoản và bảo vệ trước credential stuffing; tránh cho attacker dùng hashing làm CPU DoS.
- Queue hữu hạn và chính sách quá tải minh bạch, phản hồi 429/503 phù hợp sau khi xem xét security semantics.
- Timeout có ý nghĩa cho request nhưng **không giả định `timeout` ngừng ngay phép hash đồng bộ đã bắt đầu**; cancellation có thể không hủy CPU work ngay lập tức.
- Autoscaling dựa trên CPU, latency và queue kết hợp, có tính đến warmup và giới hạn số pod.

Không dùng `onErrorReturn(true)`, `onErrorComplete()` rồi tiếp tục quyền truy cập, hoặc trả authentication thành công nếu scheduler bị từ chối thực thi do overload. Lỗi hạ tầng phải giữ tính “không thể xác thực” cho tới khi policy xử lý an toàn.

## 8. Kiểm soát đồng thời trong reactive code

Đối với **một batch hữu hạn** các việc kiểm tra offline (không phải endpoint login cho client bên ngoài), có thể giới hạn fan-out bằng tham số `concurrency` của `flatMap`:

```java
// Mảnh code minh họa, requests là một Flux<VerifyRequest> nội bộ,
// passwordScheduler là scheduler dùng chung, verifyRequest trả Mono<Boolean>.
int concurrency = 4;

Flux<Boolean> checked = requests.flatMap(
        request -> verifyRequest(request, passwordScheduler),
        concurrency);
```

`flatMap(..., concurrency)` giới hạn số publisher inner được subscribe đồng thời **trong pipeline batch này**. Tuy nhiên, mỗi HTTP request login thường có **pipeline riêng**; gắn `flatMap(..., 4)` vào từng request **không tạo giới hạn 4 login cho toàn service**. Muốn giới hạn toàn instance, cần một bulkhead/semaphore/admission controller **dùng chung** với cơ chế chờ/từ chối không blocking và release permit an toàn trên cả success/error/cancellation.

Không dùng `Semaphore.acquire()` đồng bộ trên event loop để “giới hạn” vì thao tác có thể tự chặn event loop. Khi cần queue, nên có scheduler/admission giải quyết bất đồng bộ hoặc trả trạng thái quá tải khi hết permit. Mọi đường kết thúc cần trả permit bằng `doFinally` hoặc tài nguyên quản lý tương đương.

### Kiểm tra thứ tự thao tác

Nếu phải vừa truy vấn database user vừa hash:

```text
HTTP request
    |
    +-- lookup ReactiveUserDetailsService (I/O nonblocking)
    |
    +-- sau khi có stored hash:
    |      -> schedule CPU-only matches trên dedicated scheduler
    |
    +-- nhận Boolean -> kết quả authentication
    |
    +-- authorization -> handler / security response
```

Không dùng `subscribeOn(passwordScheduler)` ở **đầu toàn bộ luồng** nếu có thể chuyển riêng đúng phép tính CPU; làm vậy khiến việc khác chạy trên worker đắt giá, tăng contention. Với manager chuẩn, thường chính framework đã tách bước verify và không cần tự bọc nữa.

## 9. Thiết kế thí nghiệm đo ảnh hưởng đến event loop

Mục tiêu không phải chứng minh “đã có thread tên `pwd-verify` là đủ” mà phải đánh giá **tính phản hồi khi có nhiều lần kiểm tra mật khẩu đồng thời**.

### 9.1. Thiết lập thí nghiệm

Chạy các tình huống trong **môi trường test cô lập**, giữ cố định:

- JDK, phiên bản Spring Boot/Security/Reactor, thuật toán và BCrypt cost.
- CPU/memory limit của container, số instance, cgroup throttling, cấu hình Netty và worker.
- Cơ sở dữ liệu user/password hash; không đo cả thời gian tạo hash mỗi request.
- Số kết nối, arrival rate (RPS), độ đồng thời, thời lượng warmup và thời lượng đo.
- Kịch bản đúng/sai mật khẩu, số account và số hash được thực sự so sánh.
- Client load generator chạy đủ năng lực, tốt nhất tách máy khỏi server để không cạnh tranh CPU.

Không chạy stress test trên production hoặc sử dụng mật khẩu thật. Không ghi raw Authorization header vào logs của load test.

### 9.2. Bốn kịch bản so sánh

| Kịch bản | Kiểm tra điều gì? | Dấu hiệu cần chú ý |
| --- | --- | --- |
| A — không có tải login | Baseline `GET /ping` | P50/p95/p99 latency và throughput của endpoint nhẹ |
| B — login ở tải thấp, scheduler đúng | Overhead hợp lý của BCrypt | `/ping` vẫn phản hồi gần baseline, login mất thời gian hash |
| C — tăng login tới sát giới hạn CPU | Tác động CPU contention và queue | Login p95/p99 tăng trước; `/ping` có thể chậm khi host hết CPU |
| D — cấu hình sai, chạy `matches` trên event loop (chỉ trên test) | Xác nhận vì sao offload cần thiết | Thread event loop bận lâu, `/ping` trễ rõ dưới tải tương đương |

Kịch bản D có thể tạo một endpoint thử nghiệm **chỉ ở môi trường benchmark**, không đưa vào ứng dụng public. Không viết đường kiểm tra password kém an toàn để người dùng thật truy cập; mục đích chỉ là so sánh thời gian event loop bị chiếm.

### 9.3. Các chỉ số cần ghi

**Login:** request rate, success/failure rate, `latency_p50`, `latency_p95`, `latency_p99`, throughput hoàn thành, số timeout và rejection.

**Password check:** thời gian `matches` riêng, số phép đang chạy, ước lượng queue wait, số job chờ, mức sử dụng worker password.

**WebFlux/Netty:** latency `/ping`, event-loop task delay (qua instrumentation hoặc sampling phù hợp), thread state, thời gian phản hồi các endpoint không dùng password, socket backlog.

**Máy/container:** CPU total/CPU quota throttling, per-core saturation, thread count, heap/RSS, GC pause, memory allocation, số instance.

**Bảo mật:** số login thất bại theo account/IP (ẩn danh hóa phù hợp), rate-limit rejects, credential-stuffing patterns, không ghi password/token. Một tốc độ fail tăng đột ngột có thể là tấn công làm cạn CPU.

### 9.4. Ví dụ bảng ghi kết quả (không phải benchmark thực)

| Kịch bản | Login RPS | Login p95 (ms) | Ping p95 (ms) | CPU % | In-flight verify | Kết luận |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A — baseline | Đo | Đo | Đo | Đo | Đo | Tốc độ nền |
| B — load nhỏ | Đo | Đo | Đo | Đo | Đo | So với A |
| C — gần bão hòa | Đo | Đo | Đo | Đo | Đo | Queue và contention |
| D — lỗi event loop | Đo | Đo | Đo | Đo | Đo | Mức ảnh hưởng của mis-scheduling |

Các ô “Đo” cần điền bằng kết quả thực; **không được tự bịa số throughput/latency**. Nếu p95 `/ping` tăng mạnh trong khi BCrypt vẫn ở dedicated worker, xem CPU saturation/GC và các tác vụ khác; offload không đảm bảo loại bỏ mọi độ trễ hệ thống.

Đo từng mức tải nhiều lần sau warmup; báo phân vị thay vì chỉ trung bình; loại bỏ ảnh hưởng của load generator bị bão hòa. Giữ cùng cost/password hash và số kết nối khi so sánh hai cấu hình.

## 10. Phân tích các tình huống thường gặp

### Tình huống A: handler tự gọi BCrypt trên event loop

```java
// Ví dụ SAI trong WebFlux controller nếu thread hiện tại là event loop:
boolean allowed = encoder.matches(passwordFromRequest, storedHash);
return Mono.just(allowed);
```

Gọi `matches` trực tiếp trước khi trả Mono làm event loop bị giữ. **Sửa:** dùng manager chuẩn đã có scheduler, hoặc bọc riêng `fromCallable(...).subscribeOn(...)` nếu là phép kiểm tra tùy biến.

### Tình huống B: vừa có password manager chuẩn vừa offload toàn bộ authenticate

```java
// Không mặc định cần thiết nếu manager đã có scheduler riêng:
return manager.authenticate(authentication)
        .subscribeOn(Schedulers.boundedElastic());
```

Đường này có thể thêm overhead và khiến toàn bộ bước nguồn của authentication chạy trên boundedElastic nhưng **không thay thế scheduler nội tại** của manager. Hãy kiểm tra chính instance manager và dùng `setScheduler(...)` cho mục đích quản trị password worker.

### Tình huống C: mỗi request dùng HTTP Basic rồi verify lại

Nếu hệ thống gửi username/password trên **mọi API request**, chi phí BCrypt tỉ lệ với request rate; dù bảo vệ đúng và scheduler hoạt động, số verify có thể cao. Giải pháp kiến trúc là dùng session hoặc short-lived token sau bước xác thực thích hợp, có TTL, revocation/rotation, transport protection và CSRF policy theo mô hình credentials. Không cache Boolean `matches` vô thời hạn theo raw password như một cách tối ưu vội vàng.

### Tình huống D: tăng số thread “để nhanh hơn”

Khi CPU đã hết, tăng thread có thể tăng context switching và memory pressure, đặc biệt với Argon2. Số thread dành cho hash nên được xác định sau khi đo CPU quota, concurrency, latency mục tiêu và memory budget. `newParallel` riêng chỉ cách ly scheduling, không bảo đảm tổng tài nguyên được cấp thêm.

### Tình huống E: quá tải và timeout

`timeout(Duration.ofSeconds(...))` trên `Mono<Boolean>` có thể hủy subscription phía Reactor, nhưng một phép hashing đồng bộ đã chạy không được bảo đảm bị ngắt dứt khoát ở mọi implementation. Nếu request timeout mà CPU tiếp tục làm việc, load vẫn có thể tăng. Vì vậy **admission control/rate limiting** quan trọng hơn chỉ thêm timeout.

### Tình huống F: user không tồn tại

Một đường trả lỗi ngay khi không tìm thấy username và đường thực hiện BCrypt khi username có thật có thể để lộ khác biệt thời gian; thiết kế authentication cần phản hồi lỗi đồng nhất, cân nhắc timing và workload theo framework/chính sách. Không trả “username tồn tại” trong API login, không tối ưu bỏ hash cho unknown user mà bỏ qua rủi ro enumeration, và không tự thêm hash giả mà chưa đo tác động.

### Tình huống G: memory-hard hash

Với Argon2/scrypt, giới hạn concurrency còn cần theo RAM: nếu mỗi verify sử dụng nhiều memory, số job đồng thời quá lớn có thể gây OOM trước khi CPU đạt 100%. Đo heap và native memory/RSS, memory limit container; không chỉ theo `Runtime.availableProcessors()`.

## 11. Checklist triển khai

1. **Cơ chế xác thực:** HTTP Basic/form login đang dùng `ReactiveAuthenticationManager` nào? Có xác nhận instance ở security chain không?
2. **Chỗ hash chạy:** `matches` thực sự ở thread nào? Có còn trên `reactor-http-nio-*` không?
3. **Scheduler:** manager chuẩn đã offload chưa? Nếu custom, scheduler có số worker, tên và dispose đúng không?
4. **Tài nguyên:** CPU quota, memory, BCrypt cost/Argon2 memory cost đã được benchmark chưa?
5. **Concurrency:** có giới hạn login attempts đang xử lý cùng lúc trên instance và queue hữu hạn không?
6. **Overload:** phản hồi quá tải có giữ policy từ chối, không chuyển thành authentication thành công không?
7. **Đo đạc:** có tách hash execution time, queue wait, end-to-end login p95/p99 và `/ping` p95 không?
8. **Security:** có rate limiting, chống enumeration, bảo vệ log và không hạ work factor tùy tiện không?
9. **Kiểm thử:** password đúng, sai, user không tồn tại, scheduler đúng, timeout, lỗi repository, burst load được kiểm tra chưa?
10. **Vòng đời:** pool custom được dispose; có tránh tạo thread pool mỗi request và tránh `block()` trong WebFlux không?

## 12. Câu hỏi tự kiểm tra

**1. `Mono.just(encoder.matches(...)).subscribeOn(scheduler)` có chuyển BCrypt khỏi event loop không?**  
Không. `matches` được Java gọi ngay trước khi tạo `Mono.just`. `subscribeOn` tác động quá muộn.

**2. Vì sao `Mono.fromCallable(...).subscribeOn(passwordScheduler)` có ý nghĩa?**  
Nó hoãn phép tính đến lúc subscribe rồi chọn worker chạy nguồn. Cần ghép publisher vào pipeline thật và xử lý kết quả/error.

**3. Spring Security reactive đã có mặc định gì đối với username/password?**  
`UserDetailsRepositoryReactiveAuthenticationManager` sử dụng scheduler parallel riêng cho công việc password verification theo Javadoc. `setScheduler(...)` cho phép thay scheduler ở manager thực sự được dùng.

**4. `boundedElastic` có luôn là lựa chọn tốt nhất cho BCrypt không?**  
Không. `boundedElastic` chủ yếu dành cho blocking I/O. BCrypt là CPU bound; quá nhiều worker không tạo thêm CPU. Pool `newParallel` chuyên dụng và giới hạn số verify đồng thời thường dễ điều khiển.

**5. Nếu đã chuyển hash sang worker, vì sao `/ping` vẫn có thể chậm khi nhiều login?**  
Vì worker và event loop vẫn dùng cùng CPU vật lý, bộ nhớ, GC và CPU quota. Khi toàn host bão hòa, scheduler không tăng năng lực xử lý.

**6. Có thể dùng `flatMap(..., 4)` trong mỗi request để giới hạn toàn server chỉ 4 lần hash không?**  
Không. Mỗi request có pipeline riêng. Cần admission control/bulkhead dùng chung cho instance hoặc giới hạn ở gateway.

**7. Vì sao chỉ đo thời gian bên trong `matches` chưa đủ?**  
Nó không gồm thời gian request đợi worker, lookup user, authorization hoặc network. Cần đo end-to-end login latency và scheduler queue wait.

**8. Nếu request timeout, BCrypt chắc chắn dừng ngay không?**  
Không có bảo đảm chung. Cancellation của pipeline không nhất thiết ngắt tức thì phép toán đồng bộ đã bắt đầu.

**9. Có nên hạ BCrypt strength xuống rất thấp để p95 tốt hơn?**  
Không tự quyết định như vậy. Work factor là một yêu cầu an ninh, cần lựa chọn theo benchmark, threat model và chính sách. Tối ưu admission, architecture và tài nguyên trước.

**10. Cách nhanh nhất để biết mã đang kiểm tra mật khẩu trên đúng thread?**  
Instrument tạm `PasswordEncoder.matches` để ghi tên worker và thời lượng (không log password/hash), rồi gọi endpoint có credentials hợp lệ. Kiểm tra prefix của scheduler chuyên dụng cùng chỉ số CPU/event loop.

**Ghi nhớ:** Xác thực mật khẩu sử dụng thuật toán cố tình tốn CPU. Trong WebFlux, hãy **giữ phép tính đó khỏi event loop**, dùng manager có scheduler phù hợp hoặc `fromCallable(...).subscribeOn(...)` cho custom code, giới hạn lượng công việc đồng thời và đo latency thực. “Không blocking I/O” **không đồng nghĩa** “không tốn thread/CPU”.

## Tài liệu tham khảo

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): adaptive one-way functions, work factor, BCrypt/PBKDF2/scrypt/Argon2 và lý do không verify mật khẩu mỗi request.
- [Spring Security — AbstractUserDetailsReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html): `setScheduler(Scheduler)` và scheduler mặc định dành cho password hashing.
- [Spring Security — UserDetailsRepositoryReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): manager dùng `ReactiveUserDetailsService` và `PasswordEncoder`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): phân biệt `parallel`, `boundedElastic`, `single` và chuyển thread.
- [Project Reactor — FAQ: Wrap a Synchronous Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html): `Mono.fromCallable`, `subscribeOn` và nguyên tắc lazy execution.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` và thiết lập authentication/authorization trong WebFlux.
