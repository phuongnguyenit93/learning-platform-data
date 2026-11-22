# Cô lập lệnh chặn bằng `Mono.fromCallable` kết hợp `Schedulers.boundedElastic()`

## 1. Vì sao cần cô lập thao tác blocking trong Spring WebFlux?

Spring WebFlux và Project Reactor hỗ trợ xử lý chuỗi dữ liệu bằng `Mono` và `Flux`. Với server dùng mô hình event loop như Reactor Netty, một số ít thread phải phục vụ rất nhiều kết nối. Nếu một thread event loop bị giữ lại trong lúc **chờ thao tác blocking** (JDBC đồng bộ, thư viện HTTP đồng bộ, `Thread.sleep`, truy cập tệp chặn, SDK chỉ có API sync), các công việc khác dùng thread đó cũng bị trì hoãn.

Một ví dụ dễ gặp:

```java
// PHẢN VÍ DỤ: đồng bộ/blocking ngay khi controller được gọi.
@GetMapping("/customers/{id}")
public Mono<CustomerDto> customer(@PathVariable long id) {
    Customer customer = blockingRepository.findById(id); // chặn thread hiện tại
    return Mono.just(toDto(customer));
}
```

Đây là **mã minh họa bên trong ứng dụng WebFlux có sẵn**, không phải chương trình chạy độc lập. Dù kiểu trả về là `Mono`, thao tác `findById` đã **thực thi ngay** trước khi `Mono.just(...)` được tạo. Nếu method chạy trên event loop, chính event loop phải chờ I/O.

Khi buộc phải tích hợp một API sync, mẫu thiết kế Reactor thông dụng là:

```java
Mono<CustomerDto> result =
        Mono.fromCallable(() -> blockingRepository.findById(id))
            .subscribeOn(Schedulers.boundedElastic())
            .map(this::toDto);
```

Hai phần của mẫu giải quyết **hai việc khác nhau**:

1. **`Mono.fromCallable(...)`** đóng gói lời gọi đồng bộ trong một nguồn `Mono` **lazy**: `Callable.call()` chỉ được thực thi khi có subscription và nguồn được yêu cầu xử lý, thay vì chạy ngay lúc tạo pipeline.
2. **`.subscribeOn(Schedulers.boundedElastic())`** chuyển hoạt động subscribe/request ở phía upstream và việc thực thi `Callable` của nguồn sang một scheduler dành cho tác vụ có thể chặn, giúp tránh giữ thread đang subscribe (ví dụ event loop) trong khi chờ I/O.

Chỉ `fromCallable` **không tự chuyển thread**. Chỉ `boundedElastic` **không biến I/O blocking thành non-blocking**. Kết hợp đúng cả hai mới tạo được ranh giới xử lý phù hợp trong trường hợp này.

## 2. `fromCallable`: trì hoãn việc gọi hàm

Phác thảo kiểu API:

```java
static <T> Mono<T> Mono.fromCallable(
        java.util.concurrent.Callable<? extends T> supplier);
```

Đây là chữ ký **diễn giải generic**, không phải một phương thức Java có thể khai báo y nguyên trong class người dùng. Ý nghĩa của `Callable<T>` là nhận **không đối số**, trả kết quả `T`, và có thể ném `Exception`.

So sánh:

```java
// Gọi blocking trước, rồi mới tạo Mono: KHÔNG cô lập.
Mono<User> wrong = Mono.just(blockingUserDao.load(id));

// Tạo nguồn lazy: chưa gọi load(id) trong giai đoạn assembly.
Mono<User> lazy = Mono.fromCallable(() -> blockingUserDao.load(id));

// Lazy + cô lập lịch thực thi:
Mono<User> isolated = Mono.fromCallable(() -> blockingUserDao.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Các biến `blockingUserDao`, `User` và `id` là thành phần giả định của ứng dụng. Lựa chọn thứ hai tránh gọi ngay, nhưng nếu được subscribe trên event loop mà **không có `subscribeOn` phù hợp**, lệnh blocking vẫn có thể chạy trên event loop.

Những tính chất cần nhớ của `Mono.fromCallable`:

- **Mỗi subscription** vào một nguồn cold được tạo bằng `fromCallable` có thể khiến `Callable` được gọi lại. Không xem nó như cache kết quả hoặc cơ chế đảm bảo *exactly once*.
- Nếu `Callable` trả về đối tượng `T` khác `null`, nguồn phát tối đa một `onNext(T)` rồi `onComplete`.
- Nếu `Callable` trả về `null`, `Mono.fromCallable` được hoàn tất **rỗng**; không phát `onNext(null)`. Đây là cách biểu diễn không có giá trị trong Reactor, nhưng phải kiểm tra nghiệp vụ có cho phép “không tìm thấy” hay không.
- Nếu `Callable` ném exception, nguồn phát **`onError`**, không phát một giá trị lỗi `T`.
- `fromCallable` không thể biến một thao tác vốn blocking thành bất đồng bộ về bản chất; nó chỉ cho phép Reactor **đặt** việc thực thi thao tác đó vào ngữ cảnh thích hợp.

Ví dụ một repository trả `null` khi không tìm thấy:

```java
Mono<User> user = Mono.fromCallable(() -> blockingDao.find(id))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException("User not found")
        ));
```

`switchIfEmpty` giải quyết **trường hợp không có giá trị**; nó không xử lý exception do DAO ném ra. Với controller WebFlux, có thể ánh xạ “không tìm thấy” thành HTTP 404 thông qua `ResponseStatusException` theo quy ước dự án.

## 3. `boundedElastic`: đưa thao tác blocking sang tài nguyên có giới hạn

`Schedulers.boundedElastic()` là scheduler dùng chung trong Project Reactor phù hợp với **tác vụ blocking không tránh khỏi hoặc thao tác I/O đồng bộ**. Tên “bounded” nhắc rằng số worker/thread và lượng công việc chờ được **giới hạn và cấu hình được**; khác với giả định cứ có nhiều request thì tạo vô hạn thread.

Sơ đồ:

```text
HTTP event-loop thread
     |
     | subscribe(result)
     v
Mono.fromCallable(blockingCall)
     |
     | subscribeOn(boundedElastic)
     v
boundedElastic worker ── gọi blockingCall ── chờ I/O ── nhận T
     |
     | onNext(T) hoặc onError
     v
Các operator downstream (trừ khi có ranh giới scheduler khác)
     |
     v
Subscriber / cơ chế trả response của WebFlux
```

Đây là **sơ đồ logic**, không khẳng định mọi callback downstream đều chạy trên cùng một thread trong mọi pipeline. `publishOn`, các Publisher bất đồng bộ khác, và runtime có thể thay đổi thread thực tế.

Các giới hạn thực tiễn:

- Scheduler **không thể làm một lời gọi blocking nhanh hơn**. Nó ngăn thời gian chờ ấy giữ event-loop thread và cho phép các request khác tiếp tục được phục vụ.
- `boundedElastic()` **không cung cấp vô hạn năng lực**. Khi số tác vụ chặn và hàng đợi tăng cao, latency vẫn tăng, công việc có thể chờ worker và cuối cùng bị từ chối khi vượt giới hạn cấu hình.
- `boundedElastic` không tạo connection pool, timeout mạng hoặc giới hạn đồng thời cho API đích. Nếu database chỉ có 10 connection, mở hàng nghìn tác vụ chặn vẫn có thể khiến nhiều tác vụ phải chờ connection.
- Dùng **scheduler dùng chung** `Schedulers.boundedElastic()` trong tình huống thông thường; không tạo scheduler mới riêng cho từng HTTP request.
- Nếu tạo một scheduler riêng có quản lý vòng đời, ví dụ `Schedulers.newBoundedElastic(...)`, ứng dụng phải có kế hoạch **dispose** khi kết thúc vòng đời để tránh rò rỉ tài nguyên. Không tự dispose scheduler toàn cục dùng chung sau mỗi request.

Trong hệ thống có API I/O không chặn thực sự (ví dụ reactive database driver hoặc reactive HTTP client), thường nên giữ API reactive đó; việc bọc một tác vụ non-blocking trong `fromCallable` có thể làm sai kiểu hoặc tạo `Mono<Mono<T>>` không cần thiết.

## 4. `subscribeOn` và `publishOn` khác nhau ở ranh giới blocking

Đây là phần dễ triển khai sai nhất.

**Đúng:**

```java
Mono<Result> result = Mono.fromCallable(() -> blockingService.fetch())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::convert);
```

`subscribeOn` tác động lên quá trình đăng ký của phần upstream, giúp `Callable` nguồn chạy trên `boundedElastic`. Nếu chưa có `publishOn` hoặc boundary bất đồng bộ khác, các toán tử `map` sau đó trong nguồn đơn giản này thường cũng chạy trên worker đó.

**Sai mục đích nếu dùng riêng `publishOn` sau nguồn:**

```java
Mono<Result> result = Mono.fromCallable(() -> blockingService.fetch())
        .publishOn(Schedulers.boundedElastic())
        .map(this::convert);
```

`publishOn` chuyển **tín hiệu downstream sau vị trí của nó** sang scheduler, nhưng **không chuyển lệnh chạy nguồn `fromCallable` nằm phía trước** sang đó. Nếu subscription đi vào từ event loop, `blockingService.fetch()` vẫn có thể chặn event loop trước khi `publishOn` nhận được dữ liệu.

**Một quy tắc áp dụng:** với **nguồn blocking** được gói trong `Mono.fromCallable`, đặt `.subscribeOn(Schedulers.boundedElastic())` ngay gần nguồn để code rõ ý định. Trong một chain đơn giản, `subscribeOn` vẫn tác động đến nguồn dù nằm phía sau `map`, nhưng đặt gần nguồn giúp tránh che khuất ranh giới blocking và dễ review.

Bảng phân biệt:

| Thành phần | Tác động chính | Không tự bảo đảm |
|---|---|---|
| `Mono.fromCallable` | Trì hoãn lời gọi đồng bộ đến khi subscribe | Không tự chọn thread khác |
| `subscribeOn(scheduler)` | Chọn scheduler cho quá trình subscription và upstream | Không biến thao tác blocking thành non-blocking |
| `publishOn(scheduler)` | Chuyển xử lý tín hiệu ở downstream từ vị trí đó | Không đưa nguồn blocking nằm phía trước sang scheduler |
| `Schedulers.boundedElastic()` | Cung cấp worker có giới hạn phù hợp blocking | Không tạo năng lực vô hạn, không tự đặt timeout cho API ngoài |

Nếu trong pipeline có nhiều lần `subscribeOn`, các thao tác đăng ký có thể được lập lịch qua nhiều lớp, nhưng `subscribeOn` đầu tiên có hiệu lực gần nguồn thường là yếu tố quyết định ngữ cảnh thực thi của nguồn. Không dùng nhiều `subscribeOn` tùy tiện vì làm khó phân tích luồng thực thi.

## 5. Ví dụ Java 17+ chạy độc lập

Để quan sát rõ, ví dụ này có một lời gọi `Thread.sleep(...)` làm **giả lập blocking I/O**. Sử dụng `block(Duration)` **chỉ tại `main()` của chương trình console** để chờ kết quả và có stdout ổn định; trong handler/controller WebFlux tuyệt đối không dùng cách chờ này để ghép dữ liệu.

Cấu trúc dự án:

```text
reactor-blocking-isolation/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-blocking-isolation</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class Main {
    public static void main(String[] args) {
        Thread caller = Thread.currentThread();

        // Tạo nguồn lazy. Ở thời điểm này Callable chưa chạy.
        Mono<String> isolated = Mono.fromCallable(() -> {
                    System.out.println(
                            "callable-on-main: "
                                    + (Thread.currentThread() == caller)
                    );
                    Thread.sleep(40); // mô phỏng I/O blocking
                    return "  hello reactor  ";
                })
                .subscribeOn(Schedulers.boundedElastic())
                .map(String::trim)
                .map(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("assembled");

        // block chỉ trong chương trình console để demo, không dùng trong WebFlux.
        String value = isolated.block(Duration.ofSeconds(5));
        System.out.println("result: " + value);

        Mono<String> recovered =
                Mono.<String>fromCallable(() -> {
                            throw new IOException("backend offline");
                        })
                        .subscribeOn(Schedulers.boundedElastic())
                        .onErrorResume(
                                IOException.class,
                                error -> Mono.just("fallback")
                        );

        System.out.println(
                "error result: "
                        + recovered.block(Duration.ofSeconds(5))
        );
    }
}
```

Từ thư mục `reactor-blocking-isolation/`, cần Maven và JDK 17+:

```bash
mvn -q compile exec:java
```

Stdout của chương trình khi chạy bình thường:

```text
assembled
callable-on-main: false
result: HELLO REACTOR
error result: fallback
```

Giải thích từng dòng:

1. `assembled` xuất hiện đầu tiên vì `Mono.fromCallable` **chưa chạy `Callable`** lúc xây dựng pipeline.
2. `callable-on-main: false` cho biết hàm blocking được thực hiện trên worker của `boundedElastic`, khác thread của `main`.
3. `result: HELLO REACTOR` chứng minh `map` nhận dữ liệu sau khi `Callable` trả kết quả và biến đổi nó. Toán tử downstream không cần gọi blocking lần nữa.
4. `IOException` được biến thành `onError`; `onErrorResume(IOException.class, ...)` chuyển tín hiệu lỗi đó sang giá trị dự phòng `fallback`.

Ví dụ dùng `Thread.sleep` **chỉ để học**. Trong dự án thực, nên đặt lời gọi đồng bộ có giới hạn thời gian thực tế trong Callable, như thư viện JDBC hoặc SDK sync.

**Điều kiện của output:** máy không bị quá tải đến mức vượt timeout năm giây và scheduler hoạt động bình thường. Trong môi trường tải nặng, `.block(Duration)` của demo có thể ném lỗi timeout; đấy là hành vi cần thiết để tránh chờ vô thời hạn, không phải một thứ tự stdout thay thế được bảo đảm.

## 6. Đọc đúng sự kiện ở từng giai đoạn

Giả sử endpoint nhận một request:

```text
T0: event loop gọi controller, controller trả Mono đã mô tả công việc
T1: server subscribe vào Mono khi chuẩn bị phản hồi
T2: subscribeOn chuyển subscription của nguồn qua boundedElastic
T3: boundedElastic chạy Callable, chờ I/O blocking
T4: kết quả được phát qua onNext(T), map(T->R)
T5: server tiêu thụ R và hoàn tất response, hoặc xử lý onError
```

**Lợi ích:** từ T3 tới T4, event loop không phải đứng chờ chính lời gọi blocking này. Nó tiếp tục phục vụ công việc khác. Nhưng nếu quá nhiều Callable cùng chờ, boundedElastic và API đích vẫn có thể bị nghẽn; mô hình không xóa bỏ giới hạn tài nguyên.

**Vòng đời subscription:** nếu cùng một nguồn cold `Mono.fromCallable(...)` được subscribe hai lần, Callable có thể chạy **hai lần**. Nếu thêm `.retry(2)`, một lỗi có thể dẫn đến nhiều lần thực hiện lại thao tác đồng bộ; hãy xem xét tính idempotent khi thao tác có side effect, đặc biệt ghi dữ liệu hoặc thanh toán. Nếu cần chia sẻ kết quả, đó là quyết định khác và phải cân nhắc vòng đời cache, lỗi và dữ liệu người dùng.

## 7. Mẫu sử dụng trong service Spring WebFlux

Giả sử có một `LegacyCustomerClient` chỉ có method đồng bộ:

```java
Customer findCustomer(long id); // có thể chờ I/O và ném exception
```

Một service WebFlux có thể **trả Publisher** thay vì block tại controller:

```java
// Mã minh họa phụ thuộc Customer, CustomerDto, LegacyCustomerClient của dự án.
@Service
class CustomerService {
    private final LegacyCustomerClient legacyClient;

    CustomerService(LegacyCustomerClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    Mono<CustomerDto> find(long id) {
        return Mono.fromCallable(() -> legacyClient.findCustomer(id))
                .subscribeOn(Schedulers.boundedElastic())
                .map(customer -> new CustomerDto(
                        customer.getId(),
                        customer.getName()
                ));
    }
}
```

Controller chỉ cần trả về `Mono<CustomerDto>`:

```java
// Mã minh họa trong ứng dụng Spring WebFlux, cần các import thích hợp.
@RestController
class CustomerController {
    private final CustomerService service;

    CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/customers/{id}")
    public Mono<CustomerDto> get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Hai đoạn là **mã tích hợp phụ thuộc ứng dụng**, không phải file chạy độc lập; cần import các annotation của Spring Web, `Mono` và `Schedulers`. Ở đây controller không gọi `.subscribe()` hoặc `.block()`: Spring WebFlux quản lý đăng ký Publisher và kết quả HTTP. Nếu DAO trả `null` cho ID không tồn tại, `Mono.fromCallable` hoàn tất rỗng; cần có **chính sách 404** rõ ràng nếu đó là yêu cầu nghiệp vụ, chẳng hạn `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))`.

Một điểm dễ bỏ qua: nếu `legacyClient.findCustomer(id)` tự tạo thread, thực hiện callback bất đồng bộ hoặc trả một `CompletableFuture`, cách tích hợp có thể khác. `fromCallable` phù hợp nhất khi **hàm sync trả trực tiếp kết quả T**. Không bọc `Mono` đã reactive vào `fromCallable` để tạo một `Mono<Mono<T>>` không cần thiết.

## 8. Đồng thời: vì sao cần giới hạn số lời gọi blocking?

Giả sử cần tải 100 item bằng thư viện sync. Dùng `flatMap` với giới hạn concurrency rõ ràng:

```java
// Mã minh họa: legacyClient.load(id) là lệnh blocking, trả Item.
Flux<Item> items = Flux.range(1, 100)
        .flatMap(
                id -> Mono.fromCallable(() -> legacyClient.load(id))
                        .subscribeOn(Schedulers.boundedElastic()),
                4
        );
```

Trong cấu hình này, `flatMap` cố gắng giữ số **inner Publisher đang hoạt động** tối đa là 4 ở một thời điểm, từ đó giới hạn số lời gọi blocking đang được xử lý trong chuỗi này. Giá trị `4` là ví dụ, không phải cấu hình tối ưu cho mọi hệ thống.

Điều cần cân nhắc:

- **Concurrency** phải phù hợp với kích thước pool JDBC/HTTP sync, lưu lượng, thời gian I/O, năng lực CPU và giới hạn dịch vụ đích.
- Nếu cần kết quả theo đúng thứ tự ID, `flatMap` có thể phát theo thứ tự hoàn tất, nên dùng `concatMap` (tuần tự) hoặc cân nhắc `flatMapSequential` với mức concurrency được kiểm soát.
- `flatMap` và `boundedElastic` có thể cùng xếp lịch nhiều tác vụ; không tự suy ra có đúng bốn thread hoặc đúng bốn connection ở mọi thời điểm.
- Dù một request chỉ dùng concurrency 4, tổng số request HTTP đồng thời có thể khiến **toàn ứng dụng** có nhiều lời gọi sync. Cần kiểm soát tải ở cấp dịch vụ và API đích, không chỉ ở một pipeline cục bộ.

Ví dụ quan sát qua log:

```java
Mono<Item> source = Mono.fromCallable(() -> {
            System.out.println("thread: " + Thread.currentThread().getName());
            return legacyClient.load(id);
        })
        .subscribeOn(Schedulers.boundedElastic());
```

Tên worker thực tế không cố định; không viết test so sánh với đúng một chuỗi như `boundedElastic-1`. Đây là mã quan sát, không phải API đảm bảo quy tắc đặt tên thread.

## 9. Xử lý lỗi, timeout và cancellation

### 9.1. Error là tín hiệu reactive

Exception bên trong Callable tự chuyển thành `onError`. Ví dụ:

```java
Mono<Response> result = Mono.fromCallable(() -> syncClient.get())
        .subscribeOn(Schedulers.boundedElastic())
        .onErrorResume(ExternalUnavailableException.class,
                error -> Mono.just(Response.cached()));
```

Đây là mã minh họa với các kiểu thuộc ứng dụng. Chỉ fallback khi đó là quyết định có ý nghĩa nghiệp vụ; không tự nuốt mọi exception thành “không có dữ liệu”. Nếu downstream cần thông tin lỗi, để `onError` đi qua và dùng hệ thống xử lý lỗi Spring tương ứng.

### 9.2. Timeout của Reactor không thay thế timeout của thư viện sync

```java
Mono<Response> result = Mono.fromCallable(() -> syncClient.get())
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(2));
```

Khi quá thời gian chờ tín hiệu, `timeout` có thể hủy subscription upstream và phát lỗi timeout xuống downstream. Nhưng **hủy một subscription không bảo đảm** có thể cắt ngay mọi lời gọi native, socket hay thư viện sync đang blocking. Một số tác vụ hỗ trợ interruption, một số không.

Cần đặt timeout ở **chính thư viện sync** (connection timeout, socket/read timeout, statement timeout, v.v.) phù hợp với deadline HTTP, đồng thời cân nhắc timeout phía Reactor để kiểm soát trải nghiệm client.

### 9.3. `cancel()` không phải `Thread.stop()`

Khi client HTTP ngắt kết nối, downstream có thể cancel. Reactor sẽ cố hủy công việc liên quan theo hợp đồng, nhưng không có bảo đảm mọi lệnh blocking không hỗ trợ interruption dừng ngay tức khắc. Vì vậy:

- Không giả định `cancel()` hoàn tác một transaction đã bắt đầu hoặc thu hồi side effect đã hoàn thành.
- Thiết kế hoạt động ghi idempotent khi có retry hoặc client kết nối lại.
- Đảm bảo các tài nguyên DB/HTTP được đóng đúng cách bằng thư viện và pattern an toàn, kể cả khi timeout hoặc lỗi.
- Tránh giữ worker blocking vô hạn bằng cách có timeout bên trong client/DAO thực sự.

### 9.4. Có thể dùng `onErrorMap`, `retryWhen`, `doFinally` không?

Có, với điều kiện phù hợp:

- `onErrorMap` chuyển lỗi kỹ thuật thành lỗi nghiệp vụ rõ nghĩa.
- `retryWhen` có thể **subscribe lại và chạy lại Callable**, nên phải giới hạn retry, có backoff phù hợp và xem xét idempotency.
- `doFinally` hữu ích để quan sát kết thúc do complete/error/cancel. Nó không thay thế thao tác giải phóng tài nguyên nếu nguồn blocking không tự quản lý tài nguyên đúng cách.

## 10. Phân biệt với những lựa chọn tương tự

| Nhu cầu | Cách tiếp cận | Vì sao |
|---|---|---|
| Hàm đồng bộ trả `T`, có thể block | `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Lazy + chạy lời gọi trên scheduler thích hợp |
| Chạy tác vụ đồng bộ không có kết quả | `Mono.fromRunnable(...).subscribeOn(boundedElastic())` | Biểu diễn hoàn tất/lỗi, không phát giá trị `T` |
| Có API trả sẵn `Mono<T>` non-blocking | Giữ `Mono<T>` và phối hợp bằng toán tử | Tránh bọc Publisher bên trong Publisher |
| Có API trả `CompletionStage<T>`/`CompletableFuture<T>` | Xem `Mono.fromFuture(...)` và lifecycle của future | Cầu nối kiểu dữ liệu bất đồng bộ; việc hoàn thành chạy theo cơ chế của future |
| Cần tạo Publisher mới theo ngữ cảnh subscription | `Mono.defer(() -> publisherFactory())` | Trì hoãn **việc tạo Publisher**, khác `fromCallable` trả giá trị `T` |
| Chuyển xử lý tín hiệu downstream sang scheduler | `publishOn(scheduler)` | Chuyển ngữ cảnh sau vị trí đặt, không tự sửa blocking source phía trước |
| I/O database có driver reactive | API reactive thực sự, ví dụ R2DBC | Tránh chiếm worker chỉ để chờ I/O nếu stack hỗ trợ non-blocking |

**Phân biệt đặc biệt với `Mono.just`:**

```java
Mono<String> eager = Mono.just(syncClient.read()); // syncClient.read() chạy ngay

Mono<String> deferred = Mono.fromCallable(syncClient::read)
        .subscribeOn(Schedulers.boundedElastic()); // chạy khi subscribe
```

`Mono.just(value)` rất hợp khi `value` đã có sẵn trong bộ nhớ; nó không sai tự thân. Vấn đề nằm ở **biểu thức blocking được tính trước khi tạo Mono**.

## 11. Lỗi triển khai và cách tự QA

### Lỗi 1: `fromCallable` mà quên `subscribeOn`

```java
Mono<Data> mono = Mono.fromCallable(() -> syncDao.read());
```

Việc đọc đã lazy, nhưng nếu subscribe trực tiếp trên event loop thì Callable có thể chạy và chặn **event loop**. Gắn `.subscribeOn(Schedulers.boundedElastic())` cho nguồn blocking.

### Lỗi 2: Dùng `publishOn` sau Callable rồi cho rằng đã cô lập

```java
Mono<Data> mono = Mono.fromCallable(() -> syncDao.read())
        .publishOn(Schedulers.boundedElastic());
```

Nguồn vẫn chạy trên ngữ cảnh subscription upstream; chỉ các tín hiệu sau `publishOn` được điều phối. Với nguồn blocking, dùng `subscribeOn`.

### Lỗi 3: Chuyển sang boundedElastic rồi gọi `.block()` trong controller

```java
@GetMapping("/data")
public Data get() {
    return service.readOnBoundedElastic().block(); // PHẢN VÍ DỤ
}
```

Dù lệnh sync chạy trên worker, `block()` vẫn giữ thread controller chờ kết quả; trên event-loop thread, Reactor còn có thể ném lỗi do gọi API blocking bị cấm. Trả `Mono<Data>` trực tiếp để framework xử lý subscription và response.

### Lỗi 4: Dùng scheduler vô giới hạn hoặc tạo scheduler per request

Một request tạo một thread/pool riêng có thể làm hệ thống cạn tài nguyên khi lưu lượng tăng. Nên dùng `Schedulers.boundedElastic()` dùng chung và đặt giới hạn ở các tầng thích hợp. Khi có scheduler riêng theo yêu cầu thật sự, cần quản lý vòng đời/giới hạn của nó.

### Lỗi 5: Nghĩ có `boundedElastic` thì không cần timeout và giới hạn concurrency

Một lời gọi JDBC có thể treo quá lâu; nhiều lời gọi như vậy chiếm hết worker và/hoặc pool kết nối. Cần timeout bên trong thư viện và chính sách admission/concurrency; Reactor scheduler không thể bảo đảm API ngoài dừng đúng hạn.

### Lỗi 6: Side effect lặp sau retry hoặc subscription mới

```java
Mono<Receipt> write = Mono.fromCallable(() -> blockingPayment.charge())
        .subscribeOn(Schedulers.boundedElastic())
        .retry(1);
```

Đây là **phản ví dụ rủi ro nghiệp vụ**: nếu lỗi xảy ra sau khi đã ghi nhận charge ở hệ thống ngoài, retry có thể làm side effect lặp. Phải có idempotency key và chính sách retry phù hợp trước khi áp dụng trên thao tác ghi.

### Lỗi 7: Gọi blocking lồng trong `map`/`doOnNext` bên ngoài ranh giới scheduler

```java
Mono<Item> item = reactiveSource
        .map(id -> syncDao.load(id)); // Có thể block thread phát onNext.
```

Nếu `reactiveSource` chạy trên event loop, đoạn này có nguy cơ chặn thread đó. Dùng `flatMap(id -> Mono.fromCallable(() -> syncDao.load(id)).subscribeOn(Schedulers.boundedElastic()))`, rồi quản lý concurrency nếu đầu vào là `Flux`.

### Lỗi 8: Tin rằng dùng boundedElastic khiến mọi phần trong pipeline chạy trên cùng scheduler

`subscribeOn` xác định đường thực thi upstream liên quan; `publishOn`, `flatMap` với nguồn bên trong có scheduler riêng, timer và network I/O có thể làm tín hiệu tiếp tục ở thread khác. Luôn xem ranh giới scheduler của **mỗi nguồn** và dùng log/metric/trace để xác minh phần blocking không thực thi trên event loop.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Mono.just(blockingDao.load(id))` không cô lập thao tác chặn?

**Trả lời:** Java đánh giá đối số `blockingDao.load(id)` trước khi gọi `Mono.just(...)`; thao tác blocking xảy ra ngay trên thread hiện tại.

**Câu 2.** `Mono.fromCallable(() -> blockingDao.load(id))` đã đủ an toàn cho event loop chưa?

**Trả lời:** Chưa. Nó chỉ làm lời gọi lazy; cần chọn execution context cho nguồn blocking, thường `.subscribeOn(Schedulers.boundedElastic())`.

**Câu 3.** Vì sao `publishOn(boundedElastic)` đặt sau `fromCallable` không giải quyết blocking source?

**Trả lời:** `publishOn` chuyển xử lý tín hiệu downstream, còn Callable upstream chạy theo ngữ cảnh subscription. `subscribeOn` mới là toán tử thường dùng để đưa việc thực thi nguồn sang scheduler phù hợp.

**Câu 4.** `Mono.fromCallable` được subscribe hai lần thì có thể gọi DAO bao nhiêu lần?

**Trả lời:** Hai lần, một lần cho mỗi subscription của nguồn cold, nếu không có cơ chế chia sẻ/cache riêng.

**Câu 5.** Một `timeout(Duration)` của Reactor có bảo đảm dừng ngay một thư viện JDBC bị kẹt không?

**Trả lời:** Không. Nó có thể phát lỗi và hủy subscription, nhưng hiệu lực dừng I/O phụ thuộc thư viện, interruption và timeout phía driver/DB.

**Câu 6.** Khi load 200 item qua API sync, vì sao nên giới hạn concurrency của `flatMap` ngoài việc dùng boundedElastic?

**Trả lời:** Vì có giới hạn pool connection, worker, hàng đợi, memory và sức chịu tải API ngoài. Bounded scheduler không tự đảm bảo mọi luồng request dùng tài nguyên đúng ngân sách.

**Câu 7.** Trong WebFlux, sau khi dùng `fromCallable(...).subscribeOn(boundedElastic())`, controller nên trả gì?

**Trả lời:** Trả `Mono<T>` (hoặc `Flux<T>`) để Spring WebFlux subscribe và gửi response; tránh `.block()`/`.subscribe()` thủ công trong controller cho luồng trả kết quả.

## 13. Checklist đưa vào dự án thật

1. Xác định chính xác **lệnh nào** là blocking, latency và thread hiện tại của nó.
2. Đưa chính lời gọi blocking vào `Mono.fromCallable` (hoặc `Mono.fromRunnable` nếu không trả giá trị).
3. Gắn `subscribeOn(Schedulers.boundedElastic())` gần nguồn cần cô lập.
4. Trả Publisher tới framework; tránh block event loop trong controller/handler.
5. Thiết lập timeout của thư viện sync, giới hạn concurrency và resource pool; đo hàng đợi, số worker, tỷ lệ lỗi.
6. Xử lý `null` → empty, exception → error và HTTP status theo nghiệp vụ; xác định retry có an toàn hay không.
7. Quan sát bằng thread log, metrics/trace và test dưới tải; đừng suy luận việc chuyển thread chỉ vì phương thức trả `Mono`.
8. Ưu tiên thay bằng API non-blocking khi phù hợp về lâu dài, vì cô lập blocking vẫn tiêu thụ worker trong thời gian chờ.

**Ghi nhớ:** **`fromCallable` làm lời gọi blocking trở nên lazy; `subscribeOn(boundedElastic)` đưa lời gọi ấy sang tài nguyên thực thi phù hợp**. Mẫu này là cầu nối có kiểm soát giữa code Java đồng bộ và Spring WebFlux; nó giúp bảo vệ event loop nhưng vẫn cần timeout, giới hạn concurrency, xử lý lỗi và quản lý vòng đời tài nguyên.
