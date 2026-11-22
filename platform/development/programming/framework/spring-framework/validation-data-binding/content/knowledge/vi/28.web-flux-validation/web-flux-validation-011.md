# Tránh truy vấn hoặc tác vụ chặn trong converter và validator của Spring WebFlux

## 1. Vì sao đây là một vấn đề quan trọng trong WebFlux?

**Spring WebFlux** được thiết kế để xử lý I/O bất đồng bộ với mô hình reactive (`Mono`/`Flux`), thường chạy trên một số lượng hữu hạn event-loop threads khi dùng Reactor Netty. Một event-loop thread có thể phục vụ nhiều kết nối/request. Nếu nó phải **chờ** một truy vấn JDBC, một HTTP call đồng bộ, `Thread.sleep(...)` hoặc `Mono#block()`, nhiều request khác trên cùng thread có thể bị chậm theo.

Một vị trí rất dễ bị bỏ sót là **type converter** hoặc **validator** do framework gọi tự động khi xử lý HTTP input:

- Converter đổi `String` từ query/path/header/form thành enum, ID, kiểu thời gian hoặc value object.
- Validator kiểm tra `@Valid`/`@Validated`, `@NotBlank`, `@Size`, quy tắc custom constraint hoặc form object.
- Các API converter/validator thông dụng có **hợp đồng đồng bộ**. Chúng không có chỗ để trả `Mono` và chờ database/network theo cách reactive.
- Trong WebFlux, những callback này có thể chạy trên thread phục vụ reactive request pipeline, bao gồm event loop. Không được giả định framework luôn tự chuyển chúng sang một worker thread an toàn cho blocking I/O.

**Quy tắc cốt lõi:** **converter và validator chỉ nên thực hiện việc kiểm tra/chuyển đổi cục bộ, ngắn và không blocking**. Nếu quy tắc đòi hỏi truy vấn database, kiểm tra dữ liệu từ API khác hoặc I/O đáng kể, hãy thực hiện ở **service layer bằng reactive composition** sau khi input đã được parse và kiểm tra cấu trúc.

Bài học này giải thích ranh giới giữa chuyển kiểu, Bean Validation và kiểm tra nghiệp vụ bất đồng bộ, cách xử lý legacy blocking API và cách kiểm thử trên Java 17+ / Spring Boot WebFlux.

## 2. Ba hợp đồng dễ nhầm với thao tác bất đồng bộ

| Thành phần | Phương thức/hợp đồng | Kết quả | Công việc phù hợp | Không nên làm |
| --- | --- | --- | --- | --- |
| Spring `Converter<S,T>` | `T convert(S source)` | Một `T` trực tiếp | Parse chuỗi, ánh xạ enum/ID, normalize/canonicalize đầu vào. | JDBC/JPA lookup, gọi REST API, đọc file/network, chờ khóa. |
| Spring `Validator` | `void validate(Object target, Errors errors)` | Ghi errors đồng bộ vào `Errors` | Kiểm tra field/cross-field thuần CPU và nhanh. | I/O để tra cứu xem giá trị có tồn tại, `Future#get`, `sleep`. |
| Jakarta `ConstraintValidator<A,T>` | `boolean isValid(T value, ConstraintValidatorContext context)` | `true/false` đồng bộ | Quy tắc constraint thuần dữ liệu: độ dài, pattern, so sánh ngày. | `reactiveRepository.exists(...).block()`, `WebClient...block()`. |
| Reactive service/repository | `Mono<T>`, `Flux<T>`, `flatMap` | Publisher được subscribe về sau | Tra cứu R2DBC, WebClient, kiểm tra tính khả dụng, nghiệp vụ I/O. | Gọi `.block()` để ép thành giá trị đồng bộ. |
| Legacy blocking adapter | `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Publisher chạy source trên worker dành cho blocking | Cầu nối tạm cho API không có phiên bản non-blocking. | Đặt blocking call trực tiếp trong converter/validator. |

Những chữ ký trên quyết định kiến trúc:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}

// Jakarta Validation:
public interface ConstraintValidator<A extends Annotation, T> {
    boolean isValid(T value, ConstraintValidatorContext context);
}
~~~

Đây là **mã giản lược để giải thích hợp đồng**, không phải bản sao đầy đủ các interface gốc: chúng có thêm metadata/default methods hoặc ràng buộc khác. Điểm quan trọng là các phương thức chuyển đổi/kiểm tra nêu trên **không trả `Mono` hay `Flux`**.

### Type conversion khác domain validation

Ví dụ endpoint nhận `@RequestParam("plan") Plan plan`:

- **Type conversion**: `"pro"` → `Plan.PRO`; `"unknown"` → lỗi chuyển kiểu.
- **Bean Validation**: `@NotBlank`/`@Min` hoặc custom constraint kiểm tra giá trị đầu vào đã có.
- **Domain rule cần I/O**: “người dùng hiện tại có quyền dùng `Plan.PRO` không?” hoặc “tên đăng ký này đã tồn tại trong database chưa?” → thường cần reactive service sau binding.

Đừng đưa truy vấn quyền hoặc DB vào converter chỉ vì Spring đang convert `String` thành `Plan`/`UserId`. **Chuyển `id` thành value object không đồng nghĩa phải tải entity từ database**.

## 3. Điều gì xảy ra khi block event loop?

Sơ đồ request xử lý đúng:

~~~text
HTTP request
   |
   v
WebFlux argument resolution / bind / validate   [nhanh, đồng bộ, không I/O]
   |
   v
Controller nhận typed DTO/argument
   |
   v
Reactive service: repository.exists(...) / WebClient...   [không block]
   |
   v
flatMap / map / switchIfEmpty / onErrorResume
   |
   v
HTTP response
~~~

Luồng xấu:

~~~text
HTTP request
   |
   v
Converter hoặc ConstraintValidator
   |
   +-- JDBC query / RestTemplate / Thread.sleep / future.get()
   |      |
   |      +-- Thread xử lý bị giữ để CHỜ
   |
   v
Controller (chỉ chạy sau khi hết chờ)
~~~

Việc chặn event loop có thể dẫn tới:

1. **Tăng tail latency**: một request chờ I/O làm chậm các kết nối khác dùng cùng thread.
2. **Giảm throughput** khi các event-loop threads bận đợi thay vì xử lý sự kiện mạng.
3. **Queue/backpressure không diễn ra đúng vị trí**: thay vì phối hợp bằng reactive publishers, code đồng bộ giữ thread.
4. **Timeout dây chuyền**, chiếm connection và làm số lượng pending requests tăng lên khi upstream có vấn đề.
5. **Khó giám sát** vì stack trace chỉ lộ vị trí converter/validator trong khi nguyên nhân là I/O không phù hợp.

Reactor nhận diện một số thread là **non-blocking**. Gọi các API kiểu `Mono#block()` hoặc `Flux#blockFirst()` trên thread được đánh dấu `NonBlocking` thường gây `IllegalStateException` kiểu “blocking is not supported”. Nhưng **không phải mọi lệnh blocking đều tự ném exception**: `Thread.sleep`, JDBC hay lock có thể im lặng chiếm thread. Vì thế **“không có exception” không chứng minh code an toàn**.

**Không khẳng định mọi request WebFlux luôn chạy đúng một event-loop thread.** Scheduler, security, custom operators, adapter và server runtime có thể thay đổi execution context. Thiết kế vẫn phải an toàn ở trường hợp callback được gọi trên event loop.

## 4. Anti-pattern trong `Converter`: dùng parser như một repository

Ví dụ giả định có `BlockingUserRepository`:

~~~java
// SAI — snippet minh họa, không phải file hoàn chỉnh.
public final class BadUserConverter
        implements Converter<String, User> {

    private final BlockingUserRepository repository;

    public BadUserConverter(BlockingUserRepository repository) {
        this.repository = repository;
    }

    @Override
    public User convert(String idText) {
        long id = Long.parseLong(idText);
        return repository.findById(id).orElseThrow(); // CHẶN!
    }
}
~~~

**Vấn đề:** chỉ cần một `@PathVariable User user` hoặc `@RequestParam User user` có converter này, việc load entity có thể bị gọi **trong giai đoạn argument resolution**, trước khi controller điều phối xử lý bất đồng bộ. Không nên dùng type conversion để đọc dữ liệu trạng thái động, xác thực quyền hay kết nối database.

### Sửa: converter tạo value object, service mới tra cứu

~~~java
public record UserId(long value) {
    public UserId {
        if (value <= 0) {
            throw new IllegalArgumentException("ID must be positive");
        }
    }
}

public final class UserIdConverter
        implements Converter<String, UserId> {

    @Override
    public UserId convert(String text) {
        return new UserId(Long.parseLong(text));
    }
}
~~~

Đây là **đoạn Java độc lập về logic**, nhưng cần imports và đăng ký Spring converter để dùng với WebFlux. `UserIdConverter` không đụng I/O, chỉ parse và tạo value object. Repository reactive được gọi sau khi đã có `UserId`:

~~~java
@GetMapping("/users/{id}")
public Mono<UserView> findUser(@PathVariable("id") UserId id) {
    return userService.findById(id);
}
~~~

Snippet trên giả định `userService.findById(UserId)` trả `Mono<UserView>`. Service có thể dùng R2DBC hoặc WebClient để tra cứu mà không block:

~~~java
public Mono<UserView> findById(UserId id) {
    return reactiveRepository.findById(id.value())
            .map(entity -> new UserView(entity.id(), entity.name()));
}
~~~

`UserView`/`reactiveRepository` được giả định trong ví dụ kiến trúc; không phải chương trình đầy đủ. **Không đặt `Mono<User>` làm kết quả của `Converter<String,User>`** vì kiểu trả về sẽ không phù hợp hợp đồng Spring ConversionService.

### Những việc có thể làm ngay trong converter

- `String.trim()`, normalize alias nhỏ, kiểm tra format.
- `Long.parseLong`, `UUID.fromString`, `LocalDate.parse` với format/locale rõ ràng.
- Mapping enum qua `switch`, `Map` bất biến, không đọc I/O.
- Tạo value object với invariant cục bộ.

Một converter vẫn có thể gây chậm nếu thực hiện CPU nặng (regex backtracking trên input không giới hạn, mã hóa/giải mã cực lớn, vòng lặp lớn). **“Không I/O” chưa đủ nếu tính toán quá tốn CPU**; giới hạn kích thước input và giữ conversion nhanh, có độ phức tạp dự đoán được.

## 5. Anti-pattern trong `ConstraintValidator`: kiểm tra uniqueness qua DB

Giả sử DTO có custom annotation `@UsernameAvailable`. Cách thường thấy nhưng nguy hiểm:

~~~java
// SAI — snippet cố tình minh họa lỗi thiết kế, không chạy độc lập.
@Override
public boolean isValid(
        String username, ConstraintValidatorContext context) {

    if (username == null || username.isBlank()) {
        return true;
    }

    Boolean exists =
            reactiveUserRepository.existsByUsername(username).block();
    return !Boolean.TRUE.equals(exists);
}
~~~

**Tại sao sai?**

1. `ConstraintValidator#isValid(...)` trả `boolean` **ngay lập tức**, không phải `Mono<Boolean>`. `block()` ép event-driven lookup thành chờ đồng bộ.
2. Validator có thể được Spring/Jakarta validation engine gọi trong xử lý `@Valid @RequestBody`, `@ModelAttribute` hoặc method validation; đó không phải nơi thích hợp để chờ một truy vấn.
3. Gọi `.block()` trên Reactor non-blocking thread có thể ném `IllegalStateException`; trên worker khác có thể không ném nhưng vẫn làm mất lợi ích concurrency và tạo nguy cơ exhaustion.
4. Một phép “username chưa tồn tại” **không thể bảo đảm tính duy nhất tại thời điểm ghi**: hai requests đồng thời đều thấy chưa có rồi cùng insert. Database vẫn phải có **unique constraint/index**.
5. Nếu DB chậm/hỏng, validator có thể thất bại thành lỗi hạ tầng thay vì “username sai”. Không được xem lỗi DB như một constraint violation bình thường bằng cách `catch (Exception) { return true; }`.

Đổi `.block()` thành một hàm phản ứng khác bên trong `isValid` cũng không giải quyết vấn đề nếu cuối cùng vẫn phải trả boolean trước khi truy vấn hoàn thành. `@Async` trên method `isValid` không làm hợp đồng boolean trở thành async; `subscribe()` thủ công rồi trả `true` là **race condition**, vì request được cho qua trước khi kết quả kiểm tra đến.

### Đúng: tách kiểm tra cú pháp và tra cứu bất đồng bộ

Trong DTO, dùng Bean Validation cho những quy tắc **đọc được từ chính input**:

~~~java
public record RegistrationInput(
        @NotBlank
        @Size(max = 40)
        @Pattern(regexp = "[a-zA-Z0-9_]+")
        String username,

        @Min(18)
        int age) {
}
~~~

Đây là DTO minh họa với imports Jakarta Validation phù hợp. Sau khi DTO đã được bind/validate, service mới kiểm tra username bằng reactive lookup:

~~~java
public Mono<RegistrationOutcome> register(RegistrationInput input) {
    return userRepository.existsByUsername(input.username())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.just(
                            RegistrationOutcome.USERNAME_TAKEN);
                }
                return userRepository.insertNew(input)
                        .thenReturn(RegistrationOutcome.CREATED);
            });
}
~~~

Snippet này giả định repository reactive và enum `RegistrationOutcome` đã được khai báo. Điểm quan trọng: lookup và insert đều nằm trong **reactive chain** được subscribe bởi WebFlux; không gọi `block()`. **Kiểm tra uniqueness chính thức vẫn phải được DB bảo đảm**: nếu insert vi phạm unique index do race, cần bắt lỗi duplicate key ở tầng persistence và ánh xạ sang phản hồi nghiệp vụ phù hợp (thường 409 Conflict). Pre-check chỉ là trải nghiệm sớm hơn, không thay ràng buộc DB.

Nếu người dùng muốn “username không tồn tại” là một quy tắc xác thực nghiệp vụ, hãy đặt tên rõ (ví dụ `UsernameAvailabilityService`) và định nghĩa response phù hợp; không cố nhét một truy vấn bất đồng bộ vào custom `ConstraintValidator` chỉ để có một field error mặc định.

## 6. Spring `Validator` cũng đồng bộ

Spring có giao diện:

~~~java
public final class RegistrationValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationInput.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationInput input = (RegistrationInput) target;

        if (input.username() != null
                && input.username().length() > 40) {
            errors.rejectValue("username", "tooLong");
        }
    }
}
~~~

Đây là **snippet** cần các imports và `RegistrationInput` phù hợp. Code xử lý cục bộ, không I/O. Hợp đồng `validate(..., Errors)` trả `void`, vì vậy không thể `return Mono<Void>` hoặc chờ API ngoài mà không chặn thread.

Nếu cần kiểm tra nhiều trường trong DTO, ví dụ `startDate <= endDate`, Spring `Validator` hoặc custom Bean Validation class-level constraint phù hợp **khi toàn bộ dữ liệu đã có trong object**. Nếu cần DB/network thì đưa sang reactive service.

**Lưu ý về null:** custom validator cục bộ nên có chính sách null rõ ràng, tránh ném `NullPointerException` làm request fail ở tầng hạ tầng. Trong Bean Validation, thường để `@NotNull`/`@NotBlank` xử lý thiếu giá trị rồi các constraint khác tránh báo lỗi trùng; đó là lựa chọn thiết kế, không bắt buộc cho mọi constraint.

## 7. Pipeline an toàn: `map` cho việc thuần dữ liệu, `flatMap` cho I/O

Một pipeline WebFlux điển hình:

~~~java
@PostMapping("/signup")
public Mono<ResponseEntity<SignupResult>> signup(
        @Valid @RequestBody Mono<SignupRequest> request) {

    return request
            .map(this::normalizeFast)        // CPU nhẹ, không block
            .flatMap(signupService::create) // async DB/WebClient...
            .map(result -> ResponseEntity
                    .status(HttpStatus.CREATED).body(result));
}
~~~

Đây là snippet với các class/service giả định. `normalizeFast` chỉ đổi text cục bộ; `signupService.create` phải thực sự bất đồng bộ, ví dụ Spring Data R2DBC/WebClient, không được gọi JDBC rồi bọc bằng `Mono.just(...)`.

**Phân biệt operators:**

- `map(fn)`: `fn` nhận một giá trị và trả ngay một giá trị. Nên dùng cho pure/nhẹ. Việc viết `.map(value -> legacyDao.load(value))` vẫn là blocking nếu `legacyDao.load` chờ I/O.
- `flatMap(fn)`: `fn` trả `Mono<R>` và reactive chain phối hợp kết quả bất đồng bộ mà không cần gọi `block()`.
- `Mono.defer(...)`/`Mono.fromSupplier(...)`: trì hoãn thời điểm thực thi code đến lúc subscribe, **không tự chuyển code sang thread khác** và **không biến blocking operation thành non-blocking**.
- `subscribeOn(scheduler)`: quyết định scheduler cho source subscription/upstream; dùng đúng khi cần cầu nối blocking legacy.
- `publishOn(scheduler)`: chuyển execution context cho **downstream** từ vị trí đặt nó; không sửa được việc blocking đã xảy ra upstream.
- `onErrorResume`: xử lý lỗi trong pipeline khi có chính sách rõ ràng; không được nuốt lỗi hạ tầng bằng `onErrorReturn(true)` trong kiểm tra quyền/uniqueness.
- `timeout(...)`: giới hạn thời gian chờ reactive publisher; không mặc định giết được I/O blocking ở tầng driver khi nó đã chạy.

Không gọi `subscribe()` thủ công trong controller để “chạy ngầm” một kiểm tra rồi trả response ngay; framework sẽ subscribe vào publisher được **trả về** từ handler. Manual subscription dễ làm mất quản lý lỗi, cancellation và vòng đời request.

## 8. Cầu nối bắt buộc cho API legacy blocking: `boundedElastic`

Không phải dự án nào cũng có repository/driver reactive. Nếu bắt buộc phải dùng JDBC, JPA, SDK đồng bộ hoặc file I/O blocking trong một luồng WebFlux, hãy **cô lập blocking work khỏi event-loop**, không giấu nó trong converter/validator.

### Pattern Reactor được khuyến nghị

~~~java
public Mono<Boolean> usernameExists(String username) {
    return Mono.fromCallable(
            () -> blockingUserDao.existsByUsername(username))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là snippet cho adapter có `blockingUserDao` đã được inject. `Mono.fromCallable` trì hoãn việc gọi DAO cho đến khi subscribe, còn `subscribeOn(Schedulers.boundedElastic())` đưa **source** sang scheduler dành cho blocking. `boundedElastic` có giới hạn về threads/queue để tránh tạo vô hạn luồng.

**Bản sai dễ gây nhầm:**

~~~java
public Mono<Boolean> wrongEager(String username) {
    // DAO đã block TRƯỚC KHI tạo Mono!
    return Mono.just(blockingUserDao.existsByUsername(username));
}

public Mono<Boolean> wrongDeferred(String username) {
    // Trì hoãn thời điểm nhưng vẫn chạy trên subscriber thread.
    return Mono.fromCallable(
            () -> blockingUserDao.existsByUsername(username));
}
~~~

Cả hai đều là **snippet minh họa anti-pattern** khi caller có thể chạy trên event loop; trường hợp thứ hai chỉ an toàn nếu source được subscribe trên scheduler cho blocking trước khi thực thi. Đừng cho rằng chỉ thấy kiểu trả về `Mono` nghĩa là non-blocking.

**Chi phí của cầu nối:** API legacy vẫn chiếm một thread khi chờ I/O. `boundedElastic` là **biện pháp cô lập tạm thời**, không tạo phép màu reactive cho JDBC. Khi tải tăng, thread/queue/connection pool có giới hạn và cần monitoring; cân nhắc chuyển sang R2DBC/SDK reactive khi kiến trúc và yêu cầu phù hợp.

### Đặt scheduler ở đúng ranh giới

~~~java
Mono.fromCallable(() -> blockingUserDao.existsByUsername(username))
        .subscribeOn(Schedulers.boundedElastic())
        .map(exists -> exists ? "taken" : "free");
~~~

Lưu ý: đặt `publishOn(boundedElastic())` **sau** `.map(x -> blockingCall())` không cứu được thao tác blocking đã chạy. Nếu controller gọi method converter trước khi trả Mono, cũng không thể chuyển tác vụ đó sang boundedElastic bằng cách đặt `subscribeOn` ở **phía sau controller body**.

Không tạo `Schedulers.newBoundedElastic(...)` cho từng request; dùng shared scheduler hoặc scheduler có lifecycle được quản lý để tránh rò threads/queues. Nếu có thể chọn reactive driver natively, ưu tiên phương án đó hơn cầu nối.

## 9. Ví dụ chạy được: Spring Boot 3.x + Java 17+ WebFlux

Ví dụ dưới đây minh họa **converter hoàn toàn đồng bộ và thuần cục bộ**, **Bean Validation chỉ kiểm tra DTO**, rồi một **reactive service boundary** cho kiểm tra username “đã dùng” bên ngoài validator.

Để bài có thể chạy **mà không cần database**, `DemoUsernameLookup` trả một `Mono<Boolean>` dựa trên **tập dữ liệu in-memory bất biến**, cố ý không làm I/O. Trong production, chỉ thay implementation đó bằng R2DBC/WebClient thật; **không được đổi thành JDBC trong `Mono.fromSupplier` rồi gọi đó là non-blocking**.

### 9.1. Maven dependencies

Tạo dự án **Spring Boot 3.x**, **Java 17+**, Maven (parent hoặc BOM quản lý phiên bản). Chỉ dùng WebFlux starter, không thêm MVC starter để tránh đổi web application type:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Thêm các file sau trong `src/main/java/com/example/nonblocking/` và test trong `src/test/java/com/example/nonblocking/`. Mỗi public top-level type khớp tên file và đều dùng namespace Jakarta.

### 9.2. `NonBlockingApplication.java`

~~~java
package com.example.nonblocking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NonBlockingApplication {

    public static void main(String[] args) {
        SpringApplication.run(NonBlockingApplication.class, args);
    }
}
~~~

### 9.3. `AccountTier.java`

~~~java
package com.example.nonblocking;

public enum AccountTier {
    BASIC,
    PREMIUM
}
~~~

### 9.4. `ConversionConfig.java`: converter không có I/O

~~~java
package com.example.nonblocking;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import java.util.Locale;

@Configuration
public class ConversionConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, AccountTier.class,
                raw -> switch (raw.trim().toLowerCase(Locale.ROOT)) {
                    case "basic", "b" -> AccountTier.BASIC;
                    case "premium", "p" -> AccountTier.PREMIUM;
                    default -> throw new IllegalArgumentException(
                            "Unknown tier");
                });
    }
}
~~~

Spring WebFlux nhận converter qua `WebFluxConfigurer#addFormatters`. `convert` ở đây chỉ trim, lowercase và map enum. Nó có thể được gọi đồng thời bởi nhiều requests mà không giữ mutable state. Nếu input không thuộc alias hợp lệ, conversion exception dẫn tới lỗi argument binding, thường HTTP 400. Chú ý `String.trim()` có tính toán cục bộ rất nhỏ; không phụ thuộc DB hay network.

### 9.5. `DemoUsernameLookup.java`: mock reactive repository

~~~java
package com.example.nonblocking;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

import java.util.Locale;
import java.util.Set;

@Component
public class DemoUsernameLookup {

    private static final Set<String> TAKEN =
            Set.of("taken", "reserved");

    public Mono<Boolean> exists(String username) {
        return Mono.fromSupplier(() ->
                TAKEN.contains(
                        username.toLowerCase(Locale.ROOT)));
    }
}
~~~

`Set` bất biến chỉ là dữ liệu demo; phép tra cứu nội bộ rất nhanh nên an toàn cho request thread. `Mono.fromSupplier` **không tự làm code bên trong asynchronous**; ở đây không cần vì không có I/O. Khi thay bằng DB, dùng reactive repository:

~~~java
// Snippet kiến trúc, chưa phải file Java độc lập.
public Mono<Boolean> exists(String username) {
    return reactiveUserRepository
            .existsByUsername(username);
}
~~~

Với Spring Data R2DBC, repository và driver phải thực sự reactive. Đừng dùng JPA blocking repository bên trong `Mono.fromSupplier` mà không cô lập theo phần 8.

### 9.6. `SignupController.java`: bind/validate rồi tra cứu trong Mono

~~~java
package com.example.nonblocking;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SignupController {

    private final DemoUsernameLookup lookup;

    public SignupController(DemoUsernameLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/tier")
    public String tier(@RequestParam("value") AccountTier value) {
        return "TIER:" + value;
    }

    @PostMapping(
            path = "/signups",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<SignupReply>> signup(
            @Valid @RequestBody Mono<SignupRequest> body) {

        return body.flatMap(request ->
                lookup.exists(request.username())
                        .map(taken -> taken
                                ? ResponseEntity.status(
                                        HttpStatus.CONFLICT)
                                        .body(new SignupReply(
                                                "username_taken"))
                                : ResponseEntity.status(
                                        HttpStatus.CREATED)
                                        .body(new SignupReply(
                                                "created"))));
    }

    public record SignupRequest(
            @NotBlank String username,
            @Min(18) int age) {
    }

    public record SignupReply(String status) {
    }
}
~~~

**Giải thích theo đúng luồng:**

1. `GET /api/tier?value=p`: WebFlux gọi converter `String → AccountTier` đồng bộ, nhận `PREMIUM`; controller trả `TIER:PREMIUM`. Không có truy vấn.
2. `POST /api/signups`: WebFlux đọc JSON body bằng codecs, kiểm tra `@Valid` trên `Mono<SignupRequest>` khi object được materialize. Đây là pattern `@RequestBody` reactive được Spring WebFlux hỗ trợ.
3. `@NotBlank`/`@Min(18)` là **validation thuần dữ liệu**; nếu fail, WebFlux thường ném `WebExchangeBindException` và trả HTTP 400 khi không có custom handler.
4. Chỉ khi body hợp lệ, controller mới gọi `lookup.exists(...)` trong `flatMap`; “username taken” là **quy tắc nghiệp vụ bất đồng bộ**, được chuyển thành 409 Conflict, không nhét vào `ConstraintValidator`.
5. Kết quả từ `lookup` đi qua `map` (chuyển Boolean đã nhận thành response), không chặn request thread.
6. `SignupReply` là DTO response, `ResponseEntity` quyết định status theo kết quả nghiệp vụ.

**Giới hạn demo:** fake lookup chỉ kiểm tra tồn tại và **không tạo user thật**, nên status `"created"` minh họa một quyết định xử lý. Trong hệ thống thật phải thêm bước lưu dữ liệu reactive rồi mới trả 201 Created, bảo đảm unique index ở database, xử lý duplicate insert và chỉ trả 201 sau khi ghi thành công. Không dùng kết quả pre-check làm bằng chứng đã lưu dữ liệu.

Nếu ứng dụng muốn bắt một trường hợp thiếu age thay vì mặc định primitive `int` bằng 0, dùng `Integer age` kèm `@NotNull` và `@Min(18)`; demo dùng `int` để tập trung vào phân biệt converter/validator với async lookup, vẫn nhận lỗi `@Min` khi age không đủ.

## 10. Kiểm thử WebTestClient cho conversion, validation và async domain rule

Tạo file `src/test/java/com/example/nonblocking/NonBlockingApplicationTest.java`:

~~~java
package com.example.nonblocking;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NonBlockingApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void convertsAliasWithoutLookup() {
        client.get()
                .uri("/api/tier?value=p")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("TIER:PREMIUM");
    }

    @Test
    void convertsSecondAlias() {
        client.get()
                .uri("/api/tier?value=basic")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("TIER:BASIC");
    }

    @Test
    void invalidAliasIsBadRequest() {
        client.get()
                .uri("/api/tier?value=unknown")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void missingQueryIsBadRequest() {
        client.get()
                .uri("/api/tier")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void registrationPassesPureValidationThenLookup() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"fresh","age":22}
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("created");
    }

    @Test
    void takenUsernameIsBusinessConflict() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"taken","age":22}
                        """)
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.status").isEqualTo(
                        "username_taken");
    }

    @Test
    void blankUsernameIsBeanValidationError() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"","age":22}
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void underageIsBeanValidationError() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"fresh","age":16}
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void malformedJsonFailsBeforeBeanValidation() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"username\":")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void missingRequiredBodyFailsBeforeController() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Chạy từ thư mục gốc dự án đã cấu hình Maven:

~~~bash
./mvnw test -Dtest=NonBlockingApplicationTest
~~~

Trên Windows dùng `mvnw.cmd test -Dtest=NonBlockingApplicationTest`; nếu Maven đã được cài có thể dùng `mvn test -Dtest=NonBlockingApplicationTest`.

Với Spring Boot 3.x + WebFlux + Validation + Test theo cấu hình này, **10 test được thiết kế để pass**:

| Tình huống | HTTP status kỳ vọng | Điểm chứng minh |
| --- | --- | --- |
| `?value=p` | 200, `TIER:PREMIUM` | Converter parse alias local. |
| `?value=basic` | 200, `TIER:BASIC` | Chuyển kiểu đơn giản không I/O. |
| `?value=unknown` | 400 | Conversion failure, không phải DB lookup failure. |
| Không gửi `value` | 400 | Required query parameter. |
| `username=fresh, age=22` | 201, `created` | Đầu vào hợp lệ → domain lookup in-memory qua Mono. |
| `username=taken, age=22` | 409, `username_taken` | Domain conflict tách khỏi Bean Validation. |
| `username=""` | 400 | `@NotBlank` fail trên reactive body. |
| `age=16` | 400 | `@Min(18)` fail. |
| Body JSON sai cú pháp | 400 | JSON decoding fail trước validator. |
| Thiếu required body | 400 | Lỗi đọc body, không phải “username chưa tồn tại”. |

Các test chủ yếu xác nhận **hợp đồng HTTP và tách trách nhiệm**, không tự đo hiệu năng hoặc chứng minh toàn bộ hệ thống production không còn blocking. Để phát hiện blocking thật cần thêm profiler, metrics và công cụ kiểm tra trên môi trường phù hợp.

### Thử bằng curl

Khởi chạy bằng `./mvnw spring-boot:run`, sau đó:

~~~bash
curl -i "http://localhost:8080/api/tier?value=p"

curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  -d '{"username":"fresh","age":22}'

curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  -d '{"username":"taken","age":22}'

curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  -d '{"username":"","age":22}'
~~~

Lệnh shell Unix; trên PowerShell cần dùng `curl.exe` hoặc điều chỉnh quoting/line continuation. Dự kiến HTTP lần lượt là **200**, **201**, **409**, **400** với cấu hình mặc định của demo. Body lỗi 400 do WebFlux trả mặc định có thể khác theo version/configuration; do đó test chỉ assert status ở những case đó.

## 11. Làm việc với R2DBC và WebClient thay vì block

Trong production, reactive repository có dạng:

~~~java
public interface UserRepository
        extends ReactiveCrudRepository<UserEntity, Long> {

    Mono<Boolean> existsByUsername(String username);
}
~~~

Đây là **snippet kiến trúc**, cần entity, R2DBC driver, dependencies, import `ReactiveCrudRepository` và schema DB phù hợp. `ReactiveCrudRepository` thuộc Spring Data Reactive; xác minh module/repository implementation hỗ trợ reactive I/O thực sự. Không đủ điều kiện nếu dưới lớp này vẫn gọi JDBC/JPA rồi chờ.

Một dịch vụ xác minh từ API khác có thể dùng `WebClient`:

~~~java
public Mono<Boolean> isAllowed(String username) {
    return webClient.get()
            .uri("/permissions/{username}", username)
            .retrieve()
            .bodyToMono(Boolean.class);
}
~~~

Đây là snippet với `WebClient` đã cấu hình và API response kiểu Boolean. `bodyToMono(Boolean.class)` **không block**. Trong production cần timeout, authentication, giới hạn concurrency, backoff, rate limiting, circuit-breaker khi phù hợp, và phân biệt HTTP 4xx/5xx từ upstream. Không gọi `.block()` trên kết quả để ép thành một boolean cho `isValid`.

### Phân biệt lỗi người dùng với lỗi hệ thống

- `username=""` hoặc `age=16`: **dữ liệu sai** → 400 với thông tin validation phù hợp.
- `username=taken`: **xung đột nghiệp vụ** → thường 409; có thể thiết kế error code riêng và hỗ trợ user đổi tên.
- **DB/permission API không phản hồi, connection pool cạn, timeout**: lỗi hạ tầng → thường 5xx/503 theo error policy, **không giả vờ username hợp lệ** hoặc biến thành “tên đã tồn tại”.
- **Duplicate key khi insert**: xử lý một cách chắc chắn ở database, có thể ánh xạ thành 409. Không tin rằng pre-check đã chặn mọi race.

Nếu policy yêu cầu availability check trong bước đăng ký, nên cấu trúc domain service rõ ràng thay vì dùng custom constraint tạo message như thể uniqueness là một property cục bộ bất biến.

## 12. Phát hiện blocking bằng test, profiler và observability

### 12.1. Quan sát event-loop và boundedElastic

Khi debug local, logging có thể ghi thread name, request ID và span cho các bước conversion/service, nhưng **không dựa vào thread name cố định như `reactor-http-nio-3`** để quyết định code đúng/sai. Tên thread phụ thuộc runtime và scheduler.

Gợi ý kiểm tra:

- Reactor Netty **event loop busy/stalled** và request latency percentiles (p95/p99).
- Connection pool wait time, DB query times và số pending tasks trên boundedElastic.
- Thread dumps/JFR/flame graphs khi request bị treo để phát hiện stack của `Thread.sleep`, `java.sql`, `RestTemplate`, `Future#get` hoặc `Mono#block()` trong converter/validator.
- Metrics trước/sau khi tách I/O khỏi binding để đánh giá tail latency dưới tải đồng thời.
- Logging có kiểm soát và distributed tracing để phân biệt 400 do validation với 409 do nghiệp vụ và 5xx do upstream.

### 12.2. BlockHound: hữu ích nhưng không thay code review

**BlockHound** là công cụ tùy chọn có thể phát hiện một số lời gọi blocking khi chúng chạy trên các non-blocking threads đã được instrument. Công cụ này yêu cầu setup/instrumentation tương thích JVM và các thư viện; với một số Java version phải cấu hình thêm agent/flags. Nó không tự chứng minh mọi driver/custom method đều non-blocking và có thể gặp false positives/false negatives.

Vì vậy, khi tích hợp BlockHound vào test hoặc môi trường dev:

1. Kiểm tra version/điều kiện cài đặt phù hợp.
2. Kiểm thử cả đường conversion/validation dưới concurrent load.
3. Kết hợp profiling và kiểm tra call graph: `@Converter` → DB/HTTP hoặc `@Valid` → `block()` cần được phát hiện ngay từ review.
4. Không disable mọi cảnh báo chỉ để test pass; hiểu nguồn blocking và sửa ở đúng lớp.

### 12.3. Test hành vi bất đồng bộ quan trọng hơn việc chỉ thấy `Mono`

Test `WebTestClient` ở phần 10 kiểm tra response behavior. Để xác nhận triển khai truy vấn thực sự bất đồng bộ, cần integration test với **reactive driver thật**, concurrency test có tải đại diện và quan sát thread/pool. `Mono.fromSupplier(() -> jdbcCall())` và `Mono.just(jdbcCall())` vẫn có thể trả kiểu `Mono` nhưng **block như thường**.

Với blocking adapter `fromCallable + boundedElastic`, test trên environment có đủ resources; nếu có giới hạn worker/queue, under-load latency có thể tăng. Đừng gọi `.block()` trong handler chỉ để dùng kết quả hoặc “cho test đơn giản” khi code test không kiểm soát scheduler.

### 12.4. Tránh kiểm tra I/O theo từng item trong `Flux` không giới hạn

Một request có nhiều records, nếu viết:

~~~java
return Flux.fromIterable(inputs)
        .flatMap(input -> reactiveService.check(input));
~~~

Đây là snippet minh họa; khi input lớn, nên **giới hạn concurrency** và batching tùy downstream capacity, ví dụ:

~~~java
return Flux.fromIterable(inputs)
        .flatMap(input -> reactiveService.check(input), 8);
~~~

`flatMap(..., 8)` giới hạn số inner publishers được xử lý đồng thời; nó không thay thế giới hạn tổng input, timeout hay connection pool sizing. Các quy tắc kiểm tra cục bộ nhanh có thể chạy bằng `map` trước khi dùng `flatMap` để gọi I/O. Không cố tạo một `ConstraintValidator` gọi API N lần cho N field rồi chờ.

## 13. Những lỗi phổ biến và cách sửa

| Anti-pattern | Vì sao sai | Cách thay thế |
| --- | --- | --- |
| `Converter#convert` gọi JPA/JDBC | Chặn giai đoạn binding, có thể block event loop. | Parse sang ID/value object; lookup reactive trong service. |
| `ConstraintValidator#isValid` gọi `reactiveRepo.exists(...).block()` | Ép reactive về boolean bằng chờ đồng bộ. | Bean Validation chỉ kiểm tra dữ liệu; async uniqueness trong `flatMap`. |
| `Spring Validator#validate` gọi `RestTemplate` | Contract đồng bộ, giữ thread để đợi mạng. | Dùng `WebClient` trong service. |
| `Mono.just(blockingDao.load())` | Blocking chạy **eagerly**, trước khi Publisher được tạo. | Tạm dùng `Mono.fromCallable(...).subscribeOn(boundedElastic())`. |
| `Mono.fromSupplier(() -> jdbcCall())` không scheduler | Lazy ≠ asynchronous/non-blocking. | Offload legacy đúng boundary, hoặc reactive driver. |
| `publishOn(boundedElastic())` đặt sau blocking `map` | Source đã block upstream trước khi chuyển scheduler. | Đưa `subscribeOn` lên nguồn blocking. |
| `isValid` tự `subscribe()` rồi trả `true` | Kiểm tra hoàn thành sau khi request được coi hợp lệ. | Compose publisher và đợi qua `flatMap`. |
| Chuyển toàn bộ request sang `boundedElastic` | Che architectural problem, lãng phí threads và tăng contention. | Giữ conversion/validation nhẹ; chỉ offload nguồn blocking bắt buộc. |
| Catch mọi DB error rồi `return false` trong validator | Lỗi hạ tầng bị gắn nhầm thành lỗi người dùng. | Propagate/map lỗi 5xx hợp lý ở service/advice. |
| Kiểm tra uniqueness rồi không có DB unique index | Hai requests cùng pass pre-check vẫn có thể ghi trùng. | Unique constraint + xử lý duplicate key. |
| Regex/normalization CPU nặng trong converter | Không I/O nhưng vẫn chiếm event loop. | Giới hạn input, dùng algorithm hữu hạn; xử lý nặng ở tầng được quản lý. |
| Dùng `@Async` để bọc `isValid` | Không đổi chữ ký `boolean` thành reactive contract. | Chuyển async business check ra pipeline sau binding. |

## 14. Checklist thiết kế WebFlux không chặn

- [ ] `Converter#convert` chỉ làm parse/normalize/lookup map bất biến, không JDBC/JPA, HTTP sync, file I/O, `sleep` hoặc `Future#get`.
- [ ] Spring `Validator#validate` và Jakarta `ConstraintValidator#isValid` chỉ kiểm tra dữ liệu đã có, không gọi `block()`.
- [ ] Giá trị `@PathVariable`/`@RequestParam` được chuyển sang value object; entity được lấy từ reactive service sau khi binding.
- [ ] DTO dùng `@NotBlank`, `@Size`, `@Min`/`@Pattern` cho ràng buộc cục bộ.
- [ ] Quy tắc cần DB/remote API được triển khai bằng `Mono`/`Flux` và `flatMap`, không `subscribe()` thủ công.
- [ ] Nếu còn legacy blocking API, dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` ở **boundary** và theo dõi thread/queue/connection-pool.
- [ ] Không hiểu nhầm `Mono.just`/`Mono.defer`/`Mono.fromSupplier` tự động biến thao tác blocking thành non-blocking.
- [ ] Có policy phân biệt 400 dữ liệu sai, 409 xung đột nghiệp vụ, 5xx lỗi hạ tầng.
- [ ] Database bảo đảm unique index/constraint, không chỉ phụ thuộc availability pre-check.
- [ ] Kiểm thử input hợp lệ, conversion lỗi, Bean Validation lỗi, domain conflict và malformed body.
- [ ] Code review/observability kiểm tra event-loop stalls, p95/p99, thread dumps, boundedElastic queue và downstream latency.
- [ ] Tính toán CPU trong converter/validator ngắn, giới hạn input; state dùng chung thread-safe và không lưu request-specific data trong validator singleton.

**Kết luận:** **Converter/validator có hợp đồng đồng bộ; reactive lookup có hợp đồng bất đồng bộ.** Trong WebFlux, hãy giữ chuyển kiểu và validation thuần dữ liệu nhanh, còn database/network checks phải được compose trong service với `Mono`/`Flux`. `boundedElastic` chỉ dành cho cầu nối blocking legacy khi không thể tránh, chứ không phải lý do để gọi I/O trong `isValid` hay `convert`.

## Tài liệu tham khảo

- Spring Framework Reference — WebFlux Type Conversion (`ConversionService`/formatters): https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html
- Spring Framework Reference — WebFlux `@RequestBody`, reactive argument và `@Valid`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework Reference — WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework Reference — Spring `Validator`: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Reference — Jakarta Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Project Reactor Reference — **How Do I Wrap a Synchronous, Blocking Call?** (`fromCallable` + `boundedElastic`): https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/
- Project Reactor Reference — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Spring Data R2DBC Reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
