# flatMap cho công việc trả về Publisher

Trong **Spring Framework Reactive** và **Project Reactor**, `flatMap` là operator dùng khi một giá trị đầu vào phải trải qua **một công việc trả về `Publisher`** (thường là `Mono` hoặc `Flux`), rồi các phần tử từ publisher đó được đưa tiếp xuống pipeline. Điểm cốt lõi là `flatMap` vừa **biến đổi** giá trị vừa **làm phẳng** publisher lồng nhau; với `Flux.flatMap`, các công việc có thể đang diễn ra đồng thời và kết quả có thể xen kẽ theo thời điểm sẵn sàng.

Ví dụ thực tế: từ một `userId`, gọi API bất đồng bộ trả về `Mono<User>`; từ nhiều `orderId`, thực hiện nhiều lần truy vấn reactive và tạo một `Flux<Order>` chung; hoặc từ mỗi sự kiện tạo một `Flux` các sự kiện con.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn đúng `map`, `flatMap`, `flatMapMany` và `flatMapIterable` theo kiểu kết quả của hàm biến đổi.
- Giải thích quan hệ giữa `Publisher` ngoài (*outer*) và các `Publisher` bên trong (*inner*), cũng như thời điểm công việc được subscribe.
- Phân biệt `Flux.flatMap`, `concatMap` và `flatMapSequential` về subscription, thứ tự kết quả và mức độ chồng lấp.
- Giới hạn số inner publisher đang hoạt động bằng tham số `concurrency`; hiểu `prefetch`, backpressure và bộ đệm.
- Viết pipeline WebFlux không gọi `block()` hoặc `subscribe()` thủ công trong controller/service; xử lý nguồn rỗng, lỗi và cancellation.
- Kiểm thử các giá trị của `flatMap` theo cách không phụ thuộc thứ tự khi thứ tự không được bảo đảm.

## 2. Vấn đề mà `flatMap` giải quyết

Giả sử ta có hàm truy vấn hồ sơ:

~~~java
Mono<User> findUser(String userId);
~~~

Khi đầu vào là `Mono<String>`, hai cách viết sau tạo ra **hai kiểu dữ liệu khác nhau**:

~~~java
Mono<String> userId = Mono.just("u42");

Mono<Mono<User>> nested = userId.map(id -> findUser(id));

Mono<User> flattened = userId.flatMap(id -> findUser(id));
~~~

Đây là **đoạn minh họa kiểu**, chưa phải chương trình độc lập vì `User` và `findUser` do ứng dụng định nghĩa.

- `map` nhận hàm `T -> R`. Nếu `R` tình cờ là `Mono<User>`, kết quả trở thành `Mono<Mono<User>>`: mỗi tín hiệu của outer chứa **một publisher như một giá trị**. Việc subscribe outer không đồng nghĩa inner đã được subscribe.
- `flatMap` nhận hàm `T -> Mono<R>` đối với `Mono<T>`. Nó subscribe inner publisher và chuyển giá trị/kết thúc/lỗi phù hợp ra thành một `Mono<R>` duy nhất.
- `Flux.flatMap` nhận hàm `T -> Publisher<R>`. Mỗi đầu vào có thể tạo một publisher mang 0, 1 hoặc nhiều phần tử, rồi kết quả được **merge** thành một `Flux<R>`.

Hình dung:

~~~text
map:
outer:   "u42"
           |
           v
        findUser
           |
           v
      Mono<User>           -> Mono<Mono<User>>

flatMap:
outer:   "u42"
           |
           v
        findUser
           |
           v
inner:    User              -> Mono<User>
~~~

`flatMap` không có nghĩa là “chạy song song”. Với `Mono` chỉ có tối đa một giá trị outer, vấn đề chính là **ghép publisher kế tiếp**. Với `Flux` có nhiều giá trị, `flatMap` có thể subscribe nhiều inner publisher một cách háo hức (*eagerly*) và **merge** các phần tử đến từ chúng. Mức chồng lấp thực tế phụ thuộc nguồn và scheduler; bản thân operator không bắt buộc tạo thread mới.

## 3. Ký hiệu kiểu và quy tắc chọn operator

| Nguồn | Hàm biến đổi | Operator | Kết quả |
| --- | --- | --- | --- |
| `Mono<T>` | `T -> R` (giá trị thường) | `map` | `Mono<R>` |
| `Mono<T>` | `T -> Mono<R>` | `flatMap` | `Mono<R>` |
| `Mono<T>` | `T -> Publisher<R>` có thể phát nhiều phần tử | `flatMapMany` | `Flux<R>` |
| `Flux<T>` | `T -> R` | `map` | `Flux<R>` |
| `Flux<T>` | `T -> Publisher<R>` | `flatMap` | `Flux<R>` |
| `Flux<T>` | `T -> Publisher<R>`, cần giữ thứ tự outer | `concatMap` / `flatMapSequential` | `Flux<R>` |
| `Flux<T>` | `T -> Iterable<R>` | `flatMapIterable` | `Flux<R>` |

**Cách nhận diện nhanh:** xem **kiểu trả về của lambda**. Nếu hàm biến đổi đã trả `Mono`, `Flux` hoặc `Publisher` khác thì thường cần phiên bản *flat*. Nếu chỉ biến đổi đối tượng đồng bộ như `user.getName()` hoặc `price.multiply(rate)` thì dùng `map` đơn giản hơn.

Ví dụ:

~~~java
Mono<String> name = userMono.map(User::name); // User -> String
Mono<Address> address = userMono.flatMap(User::loadAddress); // User -> Mono<Address>
Flux<Permission> rights = userMono.flatMapMany(User::streamPermissions);
// User, Address, Permission là các kiểu minh họa trong ứng dụng.
~~~

Lưu ý: `Flux.flatMap(mapper)` xử lý từng phần tử source, tạo inner publisher rồi merge. **Số phần tử đầu ra không nhất thiết bằng số đầu vào**: inner có thể trả `Mono.empty()` (0 phần tử), `Mono.just(...)` (1 phần tử), `Flux.just(a,b)` (2 phần tử) hoặc nhiều hơn.

## 4. Cơ chế subscription, demand và tín hiệu

Một lần subscribe pipeline `Flux.flatMap` có thể diễn ra như sau:

1. Subscriber cuối subscribe vào `Flux` kết quả.
2. `flatMap` subscribe vào outer publisher.
3. Khi outer phát giá trị `x`, mapper tạo inner publisher `P(x)`.
4. `flatMap` subscribe inner đó (theo giới hạn concurrency) và chuyển các giá trị inner phát ra xuống downstream.
5. Khi một inner hoàn tất, vị trí của nó có thể được dùng để subscribe inner khác. Toàn bộ pipeline chỉ hoàn tất khi outer đã hoàn tất **và** tất cả inner liên quan đã hoàn tất thành công.
6. Nếu một nguồn lỗi, chế độ mặc định truyền lỗi xuống downstream và hủy phần công việc còn lại khi thích hợp. Nếu subscriber hủy, việc hủy được lan truyền lên outer và các inner hiện có theo khả năng hỗ trợ của nguồn.

Ví dụ về kết quả xen kẽ:

~~~text
Outer: A -------- B -------- C
        |          |          |
        v          v          v
Inner A: --- A1 -------- A2 --|
Inner B: - B1 -- B2 ---------|
Inner C: -- C1 -------------|
Merged: A1 ... B1 ... B2 ... C1 ... A2 ...  (thứ tự phụ thuộc thời gian)
~~~

Sơ đồ trên chỉ minh họa các inner có thể chồng lấp, không phải lịch thực thi chính xác. **`Flux.flatMap` không bảo đảm giữ thứ tự của outer hoặc giữ các phần tử từ một inner liền nhau với các inner khác.** Trong khi đó, thứ tự của các phần tử do **một** publisher hợp lệ phát ra vẫn tuân theo thứ tự tín hiệu của publisher ấy.

### Backpressure khi làm phẳng

Reactive Streams dùng `request(n)` để thể hiện nhu cầu từ downstream. `flatMap` điều phối nhu cầu cho outer và các inner; nhưng không nhất thiết chuyển nguyên một `request(n)` xuống từng nguồn. Tham số `concurrency` và `prefetch` ảnh hưởng số subscription đang hoạt động, lượng dữ liệu được yêu cầu trước và bộ đệm nội bộ. Nếu inner thực sự là nguồn bất đồng bộ có queue/buffer riêng, cần tính cả bộ nhớ của nguồn đó.

`flatMap` **không tự làm dịch vụ bên ngoài chậm lại** nếu HTTP service, SDK, callback hoặc message broker không hợp tác theo demand. Khi giới hạn tải, phối hợp giới hạn concurrency, chính sách timeout, kết nối, hàng đợi, retry và khả năng hủy của từng nguồn.

## 5. Ví dụ Java 17 chạy được: ghép Mono và merge Flux

Ví dụ sau cho thấy (a) `Mono.flatMap` xử lý công việc trả `Mono`, (b) pipeline có tính *lazy* khi xây dựng, (c) `Flux.flatMap` có thể merge nhiều inner publisher. Ta dùng phép cộng để đầu ra **không phụ thuộc thứ tự merge**.

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'FlatMapDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo `src/main/java/FlatMapDemo.java`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class FlatMapDemo {

    private static Mono<String> lookupUser(String id) {
        return Mono.defer(() -> {
            System.out.println("lookup " + id);
            return Mono.just("user-" + id);
        });
    }

    public static void main(String[] args) {
        Mono<String> profile = Mono.just("42")
            .flatMap(FlatMapDemo::lookupUser);

        System.out.println("pipeline created");
        System.out.println("result = " + profile.block());

        Integer sum = Flux.range(1, 3)
            .flatMap(n -> Mono.just(n * 10))
            .reduce(0, Integer::sum)
            .block();

        System.out.println("sum = " + sum);
    }
}
~~~

Chạy `gradle run` hoặc `./gradlew run` nếu có Gradle Wrapper (trên Windows: `gradlew.bat run`). **Stdout của chương trình**, không tính thông báo của Gradle:

~~~text
pipeline created
lookup 42
result = user-42
sum = 60
~~~

Giải thích:

- `lookupUser` trả về một `Mono<String>` được tạo với `Mono.defer`. Mã trong supplier chạy khi publisher được subscribe, do đó “lookup 42” xuất hiện **sau** “pipeline created”.
- `Mono.flatMap` subscribe inner `lookupUser("42")`, nhận `user-42` và chuyển giá trị đó ra ngoài.
- `Flux.range(1, 3)` phát ba số; mỗi số trở thành `Mono.just(n * 10)`. `flatMap` đưa các kết quả vào một Flux; `reduce(0, Integer::sum)` tính tổng 10 + 20 + 30, độc lập thứ tự.
- `block()` trong ví dụ **chỉ dùng ở hàm `main` của chương trình dòng lệnh** để lấy kết quả và kết thúc tiến trình. Trong handler/service WebFlux, thông thường **trả về `Mono` hoặc `Flux`**, không gọi `block()` trên event-loop.

Các phiên bản Reactor/JUnit ở đây được ghim để tái hiện dự án nhỏ. Trong ứng dụng Spring Boot, nên để **Spring Boot BOM** quản lý phiên bản Reactor và dependencies tương thích.

## 6. Thứ tự kết quả: flatMap, concatMap và flatMapSequential

Đây là quyết định thiết kế quan trọng khi outer có nhiều giá trị:

| Operator | Thời điểm subscribe inner | Thứ tự đầu ra theo outer | Đặc tính |
| --- | --- | --- | --- |
| `flatMap` | Có thể subscribe nhiều inner sớm | **Không bảo đảm** | Merge khi có kết quả; các inner có thể xen kẽ. |
| `concatMap` | Đợi inner hiện tại hoàn tất rồi mới subscribe inner kế tiếp | **Bảo đảm** | Tuần tự, tránh xen kẽ; có thể chậm vì phải chờ inner đầu. |
| `flatMapSequential` | Có thể subscribe nhiều inner sớm | **Bảo đảm** | Thực thi chồng lấp nhưng **đệm** kết quả của inner đến sau để phát theo thứ tự outer. |

Giả sử hai yêu cầu gọi dịch vụ:

~~~text
ID 1 -> dịch vụ chậm (500 ms)
ID 2 -> dịch vụ nhanh (50 ms)
~~~

- Với `flatMap`, kết quả ID 2 **có thể xuất hiện trước** ID 1.
- Với `concatMap`, yêu cầu ID 2 chỉ được subscribe sau khi publisher của ID 1 hoàn tất.
- Với `flatMapSequential`, hai yêu cầu có thể cùng được subscribe, nhưng kết quả ID 2 **được giữ lại** cho đến khi kết quả liên quan ID 1 có thể phát đúng thứ tự.

Ví dụ tích hợp, giả định `fetchAsync(id)` trả `Mono<Reply>` thật sự bất đồng bộ:

~~~java
Flux<Integer> ids = Flux.just(1, 2, 3);

Flux<Reply> fastestFirst = ids.flatMap(id -> fetchAsync(id));
Flux<Reply> strictOrder = ids.concatMap(id -> fetchAsync(id));
Flux<Reply> orderedMerge = ids.flatMapSequential(id -> fetchAsync(id));
~~~

Ba dòng trên là ba **pipeline độc lập**. Mỗi lần subscribe mới có thể gọi lại nguồn/công việc; không nên tự động subscribe cả ba trong ứng dụng production. `Reply` và `fetchAsync` là các kiểu/phương thức minh họa, chưa định nghĩa trong chương trình dòng lệnh mục 5.

**Quy tắc chọn:**

- Nếu mục tiêu là throughput của các I/O độc lập và thứ tự không quan trọng, `flatMap` thường phù hợp.
- Nếu mỗi công việc phải chờ công việc trước hoàn tất để bảo đảm thứ tự thao tác hoặc phụ thuộc nghiệp vụ, dùng `concatMap`; đừng dựa vào thời điểm kết quả để tự tái sắp xếp.
- Nếu công việc độc lập có thể chạy chồng lấp nhưng kết quả **phải phát theo thứ tự input**, cân nhắc `flatMapSequential` và đánh giá chi phí buffer/head-of-line blocking.

### Ví dụ bất đồng bộ chỉ để quan sát thứ tự

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> calls = Flux.just(1, 2, 3)
    .flatMap(id -> Mono.delay(Duration.ofMillis((4 - id) * 80L))
        .map(tick -> "done-" + id));

calls.doOnNext(System.out::println).blockLast();
~~~

Đây là đoạn Java tích hợp trong một phương thức (`Flux` và `Mono` đã import), có thể đặt trong `main`. Thời gian delay của ID 3 ngắn hơn ID 1, nên các lần chạy **thường** thấy ID 3 đến sớm hơn; **không được khẳng định stdout luôn có một thứ tự cố định** vì scheduler và thời điểm subscribe có thể khác nhau. Thay `flatMap` bằng `concatMap` sẽ giữ thứ tự `done-1`, `done-2`, `done-3`, nhưng cũng thay đổi cách các delay được kích hoạt.

## 7. Điều khiển concurrency và prefetch

`Flux.flatMap` có các overload hữu ích:

~~~java
Flux<Reply> merged = ids.flatMap(id -> fetchAsync(id), 8);

Flux<Reply> tuned = ids.flatMap(id -> fetchUpdates(id), 8, 16);
~~~

Đây là đoạn minh họa với `ids` là `Flux<Integer>`, `fetchAsync` trả `Mono<Reply>`, còn `fetchUpdates` trả `Flux<Reply>`. Ý nghĩa:

- `concurrency = 8`: giới hạn số **inner publisher đang được subscribe/chờ hoàn tất** đồng thời theo sự điều phối của `flatMap`. Đây không phải lời hứa dùng đúng tám thread hay chỉ có tám kết nối vật lý trong mọi hệ thống.
- `prefetch = 16`: cấu hình số lượng phần tử mà `flatMap` chuẩn bị yêu cầu trước từ **mỗi inner publisher**. Mức hiệu quả thực tế phụ thuộc inner và demand downstream; với inner `Mono` chỉ phát một giá trị thì tham số này thường ít tác dụng hơn so với inner `Flux` phát nhiều phần tử.

Ví dụ khác có inner thực sự phát hai phần tử:

~~~java
Flux<Integer> grouped = Flux.range(1, 10)
    .flatMap(id -> Flux.just(id * 10, id * 10 + 1), 4, 2);
~~~

Có tối đa bốn inner hoạt động trong quá trình merge và tham số prefetch bằng hai. Hai phần tử từ mỗi inner có thể xen kẽ với phần tử của inner khác, do đó **không viết test dựa trên thứ tự ngoài** nếu không sử dụng operator bảo đảm thứ tự.

Không đặt concurrency thật lớn chỉ vì muốn “nhanh hơn”: với 2.000 ID cùng gọi dịch vụ, concurrency lớn có thể gây kiệt connection pool, quá tải API, tăng queue hoặc timeout. Đặt giới hạn dựa trên hạn mức downstream, độ trễ, tài nguyên, số kết nối, kích thước payload và kết quả kiểm thử tải. Điều chỉnh prefetch sau khi đã đo queue/bộ nhớ, không dựa trên một con số “tối ưu” chung cho mọi pipeline.

## 8. Mono.flatMap, Mono.flatMapMany và nguồn rỗng

### Khi đầu vào là Mono và inner chỉ có tối đa một phần tử

~~~java
Mono<Order> order = orderRepository.findById("o1");
Mono<Customer> customer = order.flatMap(
    value -> customerRepository.findById(value.customerId())
);
~~~

`Mono.flatMap` trả `Mono<Customer>`. Đây là đoạn tích hợp; repository và kiểu domain phải tồn tại trong ứng dụng.

### Khi đầu vào là Mono nhưng inner có thể phát nhiều phần tử

~~~java
Mono<Customer> customer = customerRepository.findById("c1");
Flux<Order> orders = customer.flatMapMany(
    value -> orderRepository.findAllByCustomerId(value.id())
);
~~~

Dùng `flatMapMany` để có `Flux<Order>` thay vì cố nhét nhiều phần tử vào một `Mono`.

### Khi đầu vào rỗng

~~~java
Mono<String> noId = Mono.empty();
Mono<String> result = noId.flatMap(
    id -> Mono.just("user-" + id)
);
~~~

`result` cũng hoàn tất rỗng; mapper **không được gọi** khi outer không có `onNext`. Trong thao tác tra cứu, có thể chọn rõ cách xử lý “không tìm thấy”:

~~~java
Mono<User> requiredUser = userRepository.findById(id)
    .switchIfEmpty(Mono.error(new IllegalArgumentException("User not found")));
~~~

Lưu ý: `switchIfEmpty` dùng để xử lý **không có phần tử**; nó không phải bắt lỗi của API. Nếu inner thất bại, lỗi đi theo `onError` và có thể dùng `onErrorResume`/`retryWhen` khi nghiệp vụ cho phép.

### Khi đầu vào là một collection đồng bộ

~~~java
Flux<Integer> values = Flux.just(1, 2)
    .flatMapIterable(n -> java.util.List.of(n, n * 10));
~~~

Ở đây mapper trả `Iterable`, không phải `Publisher`. `flatMapIterable` thích hợp hơn việc ép mỗi collection thành `Flux.fromIterable(...)` nếu chỉ cần trải phẳng collection có sẵn. Tuy vậy, không nên tạo một collection khổng lồ chỉ để trải phẳng: collection vẫn được cấp phát trước.

## 9. Xử lý lỗi ở cấp inner và cấp toàn pipeline

Theo mặc định, một inner báo lỗi có thể làm `flatMap` phát `onError` và hủy những nguồn còn đang chạy. Với luồng cần xử lý độc lập từng ID, hãy xác định liệu **một ID lỗi có được phép bỏ qua** hay không.

**Bắt lỗi bên trong mapper — cô lập theo từng phần tử:**

~~~java
Flux<Result> results = ids.flatMap(id ->
    callRemote(id)
        .onErrorResume(error -> {
            logFailure(id, error);
            return Mono.empty(); // Cố ý bỏ kết quả ID này.
        }),
    8
);
~~~

Đây là đoạn tích hợp; `Result`, `callRemote` và `logFailure` do ứng dụng cung cấp. Mỗi inner lỗi được chuyển thành hoàn tất rỗng và các ID khác có cơ hội tiếp tục. **Cách này làm mất kết quả của ID lỗi theo chủ ý**; không phù hợp nếu mọi bản ghi bắt buộc thành công.

**Bắt lỗi ở bên ngoài — phạm vi toàn pipeline:**

~~~java
Flux<Result> results = ids
    .flatMap(id -> callRemote(id), 8)
    .onErrorResume(error -> {
        logFailure("pipeline", error);
        return Flux.empty();
    });
~~~

Khi có lỗi, đường xử lý chuyển sang fallback của **toàn bộ** Flux. Các inner chưa hoàn tất có thể bị hủy; không nên diễn giải đây là “bỏ qua đúng một ID rồi tiếp tục toàn bộ danh sách”.

Nếu cần gom lỗi sau khi xử lý phần còn lại, Reactor có `flatMapDelayError(mapper, concurrency, prefetch)`, nhưng phải thiết kế rõ chính sách lỗi, tài nguyên và cách báo partial success. `flatMapDelayError` **không** tự làm các thao tác thất bại thành thành công hoặc tự retry.

Với API bất đồng bộ dễ timeout:

~~~java
Flux<Result> results = ids.flatMap(
    id -> callRemote(id)
        .timeout(java.time.Duration.ofSeconds(3)),
    8
);
~~~

Timeout của từng inner được truyền như lỗi. Có thể đặt `onErrorResume` **bên trong** để xử lý riêng lỗi đó. Khi timeout hoặc cancel, publisher có thể cố hủy I/O, nhưng không cam kết thao tác bên thứ ba đã được rollback. Hãy kiểm tra tính idempotent và side effect nếu có retry.

## 10. Ví dụ ứng dụng Spring WebFlux: làm giàu dữ liệu bất đồng bộ

Giả sử API muốn trả danh sách đơn hàng kèm tên khách hàng. Repository reactive phát `Flux<Order>`; WebClient trả `Mono<CustomerDto>`. `flatMap` thích hợp để ghép các request phụ thuộc vào mỗi order:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

@RestController
public class OrderController {
    private final OrderRepository orderRepository;
    private final WebClient customerClient;

    public OrderController(
            OrderRepository orderRepository,
            WebClient customerClient
    ) {
        this.orderRepository = orderRepository;
        this.customerClient = customerClient;
    }

    @GetMapping("/orders/enriched")
    public Flux<OrderView> enrichedOrders() {
        return orderRepository.findAll()
            .flatMap(order -> customerClient.get()
                .uri("/customers/{id}", order.customerId())
                .retrieve()
                .bodyToMono(CustomerDto.class)
                .map(customer -> new OrderView(
                    order.id(), customer.name()
                )), 8);
    }
}
~~~

**Đây là đoạn code tích hợp**, không phải chương trình độc lập. Cần ứng dụng Spring Boot có `spring-boot-starter-webflux`, một `WebClient` được cấu hình base URL, và các kiểu `OrderRepository`, `Order`, `CustomerDto`, `OrderView`. Ví dụ tối thiểu về kiểu dữ liệu (có thể thay bằng class/record thực tế):

~~~java
record Order(String id, String customerId) {}
record CustomerDto(String name) {}
record OrderView(String orderId, String customerName) {}
~~~

Hợp đồng `OrderRepository` cần có phương thức tương đương `Flux<Order> findAll()`; trong dự án dùng Spring Data, hãy khai báo repository/adapter cho domain thực. Không tự tạo repository trống rồi giả định endpoint hoạt động.

Luồng hoạt động:

1. WebFlux subscribe vào `Flux<OrderView>` khi xử lý HTTP response.
2. `findAll()` phát từng `Order`. Mapper tạo một request WebClient trả `Mono<CustomerDto>`.
3. `flatMap(..., 8)` cho phép tối đa tám request inner đang hoạt động theo điều phối của operator.
4. Mỗi phản hồi thành công được `map` thành `OrderView`, rồi được phát xuống HTTP response khi sẵn sàng.
5. Thứ tự các `OrderView` **có thể khác thứ tự `findAll()`**; nếu hợp đồng API yêu cầu thứ tự input, cân nhắc `flatMapSequential(..., 8)`, hoặc áp dụng sắp xếp theo khóa nghiệp vụ với giới hạn dữ liệu hợp lý.

**Không viết như sau:**

~~~java
// Sai cách triển khai trên event-loop WebFlux:
return orderRepository.findAll()
    .map(order -> customerClient.get()
        .uri("/customers/{id}", order.customerId())
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .block());
~~~

`block()` chặn thread trong quá trình xử lý và có thể bị Reactor từ chối trên non-blocking thread. Nếu bỏ `block()` mà vẫn dùng `map`, pipeline sẽ trả `Flux<Mono<CustomerDto>>`, không phải các đối tượng khách hàng đã được lấy. Trong handler WebFlux, hãy để framework subscribe publisher trả về; **không tự gọi `subscribe()` trong controller để khởi động các request rồi trả response sớm**.

Nếu mỗi order cần customer và payment cùng lúc, có thể dùng `Mono.zip(customerMono, paymentMono)` **bên trong mỗi mapper** khi cả hai nguồn thực sự phát một giá trị cần kết hợp. Khi hai nguồn chỉ báo completion bằng `Mono<Void>`, dùng `Mono.when(...)` hoặc `then(...)` thay vì `zip` vì `zip` cần giá trị từ các nguồn để kết hợp.

## 11. Nguồn blocking, hot publisher và các giới hạn thực tế

`flatMap` không tự động chuyển công việc blocking sang luồng riêng:

~~~java
// Sai: legacyBlockingCall(id) đã chạy đồng bộ trong mapper.
Flux<Result> wrong = ids.flatMap(id ->
    Mono.just(legacyBlockingCall(id))
);
~~~

Khi buộc phải tích hợp API blocking, có thể cô lập bằng `fromCallable` và `Schedulers.boundedElastic()`:

~~~java
import reactor.core.scheduler.Schedulers;

Flux<Result> isolated = ids.flatMap(
    id -> Mono.fromCallable(() -> legacyBlockingCall(id))
        .subscribeOn(Schedulers.boundedElastic()),
    8
);
~~~

Đây là đoạn tích hợp. Giới hạn concurrency không được bỏ qua: luồng boundedElastic là tài nguyên có hạn, và kết nối JDBC/file I/O cũng có giới hạn riêng. Khi có driver reactive đúng nghĩa, ưu tiên không-blocking end-to-end.

**Nguồn hot** có thể phát dữ liệu trước khi subscriber đăng ký hoặc khi downstream chậm. Nếu mapper tạo inner từ một hot source, việc subscribe muộn có thể bỏ lỡ tín hiệu; không suy đoán rằng `flatMap` sẽ replay sự kiện. Cần xác định hợp đồng hot/cold, replay, backpressure và cancellation của nguồn.

**Luồng vô hạn:** `flatMap` có thể tiếp tục phát mãi khi outer hoặc inner không kết thúc. Vì vậy `collectList()`, `reduce(...)` hoặc `blockLast()` chỉ hoàn tất khi nguồn đã kết thúc. Với luồng vô hạn, cân nhắc `take(n)`, timeout, window, cancellation và giới hạn bộ nhớ phù hợp; không gom vô hạn vào một `List`.

**Phụ thuộc thứ tự nghiệp vụ:** nếu ID 2 phải cập nhật sau ID 1, `flatMap` có thể vi phạm thứ tự side effect, ngay cả khi sau đó dùng `sort()` để sắp lại kết quả. `sort()` chỉ sắp **các giá trị đầu ra sau khi đã phát sinh**; nó không hoàn tác thứ tự tác vụ I/O. Dùng `concatMap` cho ràng buộc tuần tự hoặc cơ chế transaction/serialization thích hợp.

## 12. Kiểm thử bằng StepVerifier

Bổ sung file `src/test/java/FlatMapTest.java` vào dự án mục 5 (dependency `reactor-test` và JUnit đã khai báo):

~~~java
import java.util.Set;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class FlatMapTest {

    @Test
    void mergedValuesAreCorrectWithoutAssumingOrder() {
        Mono<Set<Integer>> values = Flux.just(1, 2, 3)
            .flatMap(n -> Mono.just(n * 10))
            .collectList()
            .map(Set::copyOf);

        StepVerifier.create(values)
            .expectNext(Set.of(10, 20, 30))
            .verifyComplete();
    }

    @Test
    void concatMapPreservesOuterAndInnerOrder() {
        Flux<String> result = Flux.just(1, 2, 3)
            .concatMap(n -> Flux.just(n + "a", n + "b"));

        StepVerifier.create(result)
            .expectNext("1a", "1b", "2a", "2b", "3a", "3b")
            .verifyComplete();
    }

    @Test
    void recoverOneInnerErrorWithoutStoppingTheOthers() {
        Mono<Set<Integer>> values = Flux.range(1, 3)
            .flatMap(n -> n == 2
                ? Mono.<Integer>error(
                    new IllegalStateException("bad"))
                    .onErrorReturn(-2)
                : Mono.just(n))
            .collectList()
            .map(Set::copyOf);

        StepVerifier.create(values)
            .expectNext(Set.of(1, -2, 3))
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` hoặc Gradle Wrapper tương ứng. Ba test được kỳ vọng **PASS**:

- Test đầu kiểm tra **tập giá trị** của `flatMap`, tránh phụ thuộc thứ tự merge chưa được bảo đảm.
- Test thứ hai kiểm tra hợp đồng thứ tự của `concatMap` qua hai phần tử từ mỗi inner.
- Test thứ ba đặt `onErrorReturn` **bên trong mapper**, do đó lỗi ở input 2 được thay bằng -2, không chấm dứt các input khác.

Test chỉ so sánh `Set` khi giá trị **không trùng** và thứ tự thật sự không quan trọng; cách này sẽ làm mất thông tin về số lần xuất hiện của phần tử trùng nhau. Nếu nghiệp vụ yêu cầu giữ multiplicity, kiểm tra histogram/count hoặc so sánh danh sách đã sắp theo khóa thay vì chuyển thẳng sang `Set`.

Với inner dùng `Mono.delay` và scheduler, hãy dùng `StepVerifier.withVirtualTime(...)` hoặc một scheduler có thể kiểm soát để test hành vi thời gian; không dùng `Thread.sleep` và khẳng định một thứ tự kết quả không được operator cam kết.

## 13. Lỗi phổ biến và cách sửa

| Cách viết/vấn đề | Vì sao sai hoặc rủi ro | Hướng xử lý |
| --- | --- | --- |
| `map(id -> repo.findById(id))` khi cần kết quả truy vấn | Tạo `Flux<Mono<User>>`; inner không tự được làm phẳng. | Dùng `flatMap(id -> repo.findById(id))`. |
| `flatMap(id -> Mono.just(transform(id)))` với phép biến đổi thuần đồng bộ | Thừa publisher, khó đọc; khi transform blocking vẫn bị block. | Dùng `map` cho hàm thuần; tích hợp blocking bằng adapter phù hợp. |
| Giả định `Flux.flatMap` giữ thứ tự ID | Inner nhanh có thể phát trước inner chậm. | Dùng `concatMap` hoặc `flatMapSequential` tùy yêu cầu. |
| Đặt concurrency rất cao | Có thể quá tải dịch vụ/DB, connection pool, queue, bộ nhớ. | Bắt đầu với giới hạn đo được và kiểm thử tải. |
| Dùng `sort()` để “sửa” thứ tự side effect | Chỉ sắp kết quả, không sửa thứ tự hành động bên ngoài. | Tuần tự hóa tác vụ với `concatMap` nếu thứ tự thao tác là bắt buộc. |
| Bắt lỗi sau `flatMap` rồi tưởng chỉ bỏ một input | Recovery áp dụng cấp pipeline, có thể hủy các inner khác. | Xử lý lỗi trong từng inner nếu muốn cô lập từng ID. |
| Giả định mọi input luôn cho một output | Inner có thể rỗng hoặc phát nhiều giá trị. | Xác định hợp đồng 0..N và cách xử lý thiếu/nhân bản kết quả. |
| `subscribe()` bên trong service rồi trả publisher khác | Mất chuỗi điều khiển completion/error/cancel của caller. | Trả về publisher đã ghép để caller/framework subscribe. |
| `block()` trong mapper chạy trên event-loop | Chặn xử lý reactive, gây nghẽn hoặc lỗi runtime. | Dùng non-blocking API; cô lập adapter blocking có giới hạn khi bắt buộc. |
| Gom `Flux` vô hạn bằng `collectList()` | Publisher không hoàn tất; bộ nhớ tăng khi giá trị tiếp tục tới. | Đặt ranh giới, giới hạn, window/take hoặc tiêu thụ dạng stream. |

## 14. Checklist khi áp dụng vào một pipeline thật

1. **Xem kiểu của mapper:** trả giá trị thường hay trả `Mono`/`Flux`? Chọn `map` hay `flatMap` từ hợp đồng kiểu, đừng dựa trên tên hàm.
2. **Xác định tính độc lập:** input sau có được chạy trước khi input trước hoàn tất không? Nếu không, chọn `concatMap` hoặc cơ chế tuần tự phù hợp.
3. **Định nghĩa yêu cầu thứ tự:** có cần giữ thứ tự outer trong response không? Nếu có nhưng cho phép chồng lấp I/O, cân nhắc `flatMapSequential` và lượng buffer.
4. **Đặt giới hạn tải:** đo số request đồng thời, độ trễ, connection pool, prefetch, dung lượng queue và khả năng chịu tải của dependency.
5. **Quyết định chính sách lỗi/rỗng:** một ID không tìm thấy, timeout hay lỗi thì bỏ qua, thay bằng giá trị mặc định, retry hay thất bại cả pipeline? Viết xử lý đúng cấp inner hoặc cấp toàn pipeline.
6. **Giữ chuỗi cancellation:** trả publisher từ WebFlux handler, thêm timeout/cleanup khi cần; không tự tách luồng bằng `subscribe()` hoặc chặn bằng `block()`.
7. **Viết test đúng hợp đồng:** test giá trị và số lượng, thứ tự chỉ khi operator cam kết, và thử cả lỗi/hủy/nguồn chậm khi quan trọng.

**Ghi nhớ:** `map` biến đổi `T -> R`; `flatMap` dùng khi bước tiếp theo trả về `Publisher<R>` và cần đưa tín hiệu của inner ra pipeline. Đối với nhiều giá trị outer, `flatMap` ưu tiên merge khi có kết quả và **không bảo đảm thứ tự**; hãy chọn `concatMap` hoặc `flatMapSequential` khi thứ tự là một phần hợp đồng.

## Tài liệu tham khảo

- Reactor Core Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Reactor Flux API — `flatMap`, `concatMap` và `flatMapSequential`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Mono API — `flatMap` và `flatMapMany`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Streams specification: https://www.reactive-streams.org/
