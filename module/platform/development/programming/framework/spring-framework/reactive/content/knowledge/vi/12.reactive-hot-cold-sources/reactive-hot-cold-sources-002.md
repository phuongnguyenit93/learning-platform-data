# Dữ liệu tạo lúc lắp ghép và lúc đăng ký

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Nguồn nóng và lạnh

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt hai thời điểm quan trọng của Reactor: **lắp ghép pipeline (assembly time)** và **đăng ký tiêu thụ (subscription time)**.
2. Giải thích tại sao `Mono.just(expensiveCall())` gọi hàm ngay khi tạo publisher, còn `Mono.defer`, `Mono.fromSupplier` và `Mono.fromCallable` trì hoãn việc tạo giá trị đến mỗi lần subscribe.
3. Hiểu đúng `Flux`/`Mono` cold và hot, trong đó `Mono.just` giữ giá trị đã capture tại assembly và phát lại giá trị đó cho các subscriber.
4. Nhận diện state được chia sẻ qua closure với state tạo riêng cho từng subscription.
5. Phân biệt `defer`, `cache` và `share`; hiểu cách chúng tác động đến việc thực thi nguồn, số lần gọi side effect, replay và vòng đời kết nối.
6. Áp dụng trong Spring WebFlux, tránh vô tình giữ dữ liệu cũ, gọi I/O blocking lúc lắp pipeline hoặc lặp side effect khi có nhiều subscription/retry.

## 1. Hai mốc thời gian trong một chuỗi reactive

Khi viết code Reactor, ta thường tạo một biến `Mono<T>` hoặc `Flux<T>` bằng cách ghép các toán tử. Hành động này gọi là **assembly**: ứng dụng xây dựng mô tả về nguồn và chuỗi xử lý. Một pipeline chỉ bắt đầu được tiêu thụ khi có một subscriber đăng ký, trực tiếp hoặc thông qua một framework như Spring WebFlux.

Cần tách ba giai đoạn:

1. **Assembly time – thời điểm lắp ghép:** Java thực thi các biểu thức bình thường, tạo object publisher và kết nối các operator thành một pipeline.
2. **Subscription time – thời điểm đăng ký:** một subscriber đăng ký; nguồn và các operator khởi tạo state cần thiết cho subscription và bắt đầu phối hợp demand.
3. **Signal time – thời điểm phát tín hiệu:** dữ liệu `onNext`, lỗi `onError` hoặc hoàn tất `onComplete` đi qua pipeline.

```text
Java gọi method / tạo publisher
            |
            v
     ASSEMBLY TIME
  - tính đối số của just(...)
  - tạo object / nối operator
  - có thể chạy side effect Java ngay
            |
            |  publisher được giữ lại
            |  (chưa chắc đã có subscriber)
            v
   subscribe(subscriber)
            |
            v
   SUBSCRIPTION TIME
  - defer/supplier được gọi
  - tạo state theo subscription
  - nguồn bắt đầu được tiêu thụ
            |
            v
       SIGNAL TIME
  onNext(value) / onError(error) / onComplete()
```

**Lazy** nghĩa là một công việc được trì hoãn tới lúc cần, thường là khi có subscription. Reactor không thể tự động làm mọi biểu thức Java trở nên lazy: nếu bạn gọi một hàm trước khi truyền kết quả cho `Mono.just`, hàm ấy đã chạy.

### 1.1. Bẫy phổ biến: Mono.just gọi hàm trước

```java
Mono<User> user = Mono.just(userRepository.findByIdBlocking(id));
```

Đây là **đoạn minh họa có chủ đích**, giả sử `findByIdBlocking` trả `User`. Java đánh giá đối số của `Mono.just(...)` trước khi gọi `just`, nên lời gọi repository đã xảy ra ngay lúc method tạo pipeline chạy. Publisher chỉ capture kết quả đã có. Nếu repository trả `null`, `Mono.just(null)` không hợp lệ và có thể ném `NullPointerException` ngay ở assembly.

Nếu method controller chạy một lần cho mỗi request, lời gọi blocking có thể xảy ra trong lúc xử lý request, nhưng nó vẫn xảy ra **trước subscription vào publisher trả về**. Nếu bạn tạo publisher này trong constructor hoặc field của singleton bean, việc gọi có thể xảy ra một lần lúc khởi tạo bean, khiến mọi request sau dùng cùng một giá trị cũ.

### 1.2. Trì hoãn tạo giá trị bằng defer

```java
Mono<User> user = Mono.defer(() ->
        Mono.just(userRepository.findByIdBlocking(id)));
```

`Mono.defer` nhận một supplier tạo publisher. Supplier chỉ được gọi khi mỗi subscriber đăng ký. Vì vậy, `findByIdBlocking(id)` được thực hiện tại subscription time, một lần cho mỗi subscription vào `user`. Tuy nhiên, lời gọi này vẫn **blocking**. `defer` chỉ thay đổi thời điểm chạy; nó không chuyển lời gọi sang thread khác và không biến JDBC đồng bộ thành I/O nonblocking.

Nếu có API reactive, ưu tiên trả publisher từ repository thay vì bọc lời gọi blocking. Nếu buộc phải dùng API blocking, phải chuyển công việc sang scheduler phù hợp và quản lý giới hạn tài nguyên.

## 2. Mono.just, fromSupplier, fromCallable và defer

Các factory method có vẻ gần giống nhau nhưng khác về thời điểm tính giá trị và cách biểu diễn null/lỗi.

| Cách tạo | Khi nào expression/supplier chạy? | Null và exception |
| --- | --- | --- |
| `Mono.just(value)` | `value` đã được tính trước khi gọi `just` (assembly) | `null` bị từ chối; exception của biểu thức xảy ra trước khi publisher được tạo. |
| `Mono.fromSupplier(supplier)` | Supplier chạy khi mỗi subscription yêu cầu giá trị | Supplier trả `null` thì Mono hoàn tất rỗng; exception trở thành `onError`. |
| `Mono.fromCallable(callable)` | Callable chạy khi mỗi subscription yêu cầu giá trị | Callable trả `null` thì Mono hoàn tất rỗng; exception được chuyển thành `onError`. |
| `Mono.defer(factory)` | Factory tạo một `Mono` mới cho mỗi subscription | Factory ném exception thì subscription nhận `onError`; factory trả publisher rỗng thì kết quả rỗng. |
| `Flux.defer(factory)` | Factory tạo `Publisher`/`Flux` cho mỗi subscription | Lỗi factory trở thành `onError`; factory có thể trả nguồn cold, hot hoặc nguồn đã chia sẻ. |

### 2.1. Mono.fromSupplier: trì hoãn một giá trị

```java
Mono<String> name = Mono.fromSupplier(() -> loadName());
```

Supplier được gọi khi subscriber cần giá trị. Mỗi subscription độc lập có thể gọi supplier một lần và nhận giá trị mới. Nếu supplier trả `null`, Reactor biểu diễn kết quả là `Mono.empty()`, không phát `onNext(null)`.

### 2.2. Mono.fromCallable: khi hàm có thể ném checked exception

```java
Mono<String> contents = Mono.fromCallable(() -> Files.readString(path));
```

`Callable` có thể ném checked exception nên thuận tiện khi bọc API Java như đọc file. Exception được đưa thành tín hiệu lỗi reactive thay vì phải bắt và ném lại trong assembly. Tuy nhiên, `Files.readString` vẫn là thao tác blocking; để dùng trong ứng dụng WebFlux, cần chuyển nó khỏi event-loop, ví dụ `subscribeOn(Schedulers.boundedElastic())`, hoặc dùng API file/I/O bất đồng bộ thích hợp.

### 2.3. Mono.defer: trì hoãn việc tạo cả publisher

```java
Mono<Account> account = Mono.defer(() -> {
    String requestId = createRequestId();
    return accountService.find(requestId);
});
```

`defer` hữu ích khi chính **publisher cần trả về** phụ thuộc vào thời điểm đăng ký: tạo request ID, chọn nhánh, lấy giá trị cấu hình hiện tại hoặc tạo nguồn mới. Với mỗi subscription, factory được gọi lại.

Nếu chỉ cần một giá trị đơn giản, `fromSupplier`/`fromCallable` thường ngắn và rõ hơn. Nếu cần tạo một publisher khác nhau hoặc ghép logic tạo nguồn, dùng `defer`.

### 2.4. Factory được gọi mỗi subscription không có nghĩa mọi thứ bên trong đều mới

```java
Mono<String> shared = Mono.just(loadOnce());
Mono<String> deferredButShared = Mono.defer(() -> shared);
```

Hai publisher trên đều phát giá trị đã được tính trước. `deferredButShared` gọi factory ở mỗi subscription, nhưng factory trả lại **cùng một publisher `shared`**. Nó không gọi lại `loadOnce()`. Đây là điểm quan trọng: `defer` trì hoãn factory, nhưng chỉ tạo state/source mới nếu code bên trong factory thực sự tạo chúng.

## 3. Ví dụ Java 17+ chạy được: quan sát thời điểm thực thi

Ví dụ CLI dưới đây dùng **Java 17+**, **Maven** và **Project Reactor Core 3.8.8**. Nó so sánh giá trị tính lúc assembly, supplier chạy mỗi subscription và publisher cache kết quả.

Cấu trúc:

```text
assembly-subscription-demo/
├── pom.xml
└── src/main/java/demo/
    └── AssemblySubscriptionDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>assembly-subscription-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/AssemblySubscriptionDemo.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public final class AssemblySubscriptionDemo {
    private static final AtomicInteger sequence = new AtomicInteger();

    private static String load(String label) {
        int id = sequence.incrementAndGet();
        System.out.println("load " + label + " #" + id);
        return label + "-" + id;
    }

    public static void main(String[] args) {
        System.out.println("== just ==");
        Mono<String> just = Mono.just(load("just"));
        System.out.println("after assembly");
        System.out.println("A=" + just.block());
        System.out.println("B=" + just.block());

        System.out.println("== defer ==");
        Mono<String> deferred = Mono.defer(
                () -> Mono.just(load("defer")));
        System.out.println("after assembly");
        System.out.println("A=" + deferred.block());
        System.out.println("B=" + deferred.block());

        System.out.println("== fromSupplier ==");
        Mono<String> supplier = Mono.fromSupplier(
                () -> load("supplier"));
        System.out.println("after assembly");
        System.out.println("A=" + supplier.block());
        System.out.println("B=" + supplier.block());

        System.out.println("== cache ==");
        Mono<String> cached = Mono.fromSupplier(
                () -> load("cached")).cache();
        System.out.println("after assembly");
        System.out.println("A=" + cached.block());
        System.out.println("B=" + cached.block());

        Mono<String> empty = Mono.fromSupplier(() -> null);
        System.out.println("supplier null empty=" +
                empty.blockOptional().isEmpty());
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.AssemblySubscriptionDemo
```

**Stdout của chương trình** (không tính log của Maven):

```text
== just ==
load just #1
after assembly
A=just-1
B=just-1
== defer ==
after assembly
load defer #2
A=defer-2
load defer #3
B=defer-3
== fromSupplier ==
after assembly
load supplier #4
A=supplier-4
load supplier #5
B=supplier-5
== cache ==
after assembly
load cached #6
A=cached-6
B=cached-6
supplier null empty=true
```

### Giải thích từng trường hợp

- **just:** `load("just")` được Java gọi trước khi `Mono.just` được tạo, nên log xuất hiện ngay trong phần assembly. Publisher capture chuỗi `"just-1"`; cả A và B đều nhận cùng giá trị đã capture, không gọi lại hàm.
- **defer:** việc lắp pipeline chưa gọi `load("defer")`. Mỗi lần `block()` tạo một subscription, factory chạy và tính giá trị mới: `defer-2` rồi `defer-3`.
- **fromSupplier:** supplier chưa chạy lúc tạo Mono. Mỗi lần subscribe, nó chạy một lần và trả kết quả mới.
- **cache:** subscriber đầu tiên kích hoạt supplier và cache giá trị terminal; subscriber tiếp theo nhận lại kết quả đã cache, không gọi supplier thêm.
- **null:** `fromSupplier` trả null nên Mono rỗng; `blockOptional()` cho biết không có giá trị. Không có `onNext(null)`.

`block()` trong ví dụ chỉ để minh họa tại ranh giới CLI đồng bộ. Mỗi lời gọi `block()` tạo một subscription riêng. Không sao chép cách chờ này vào controller WebFlux.

## 4. Flux cũng có assembly time và subscription time

Các quy tắc tương tự áp dụng cho `Flux`. Ví dụ:

```java
Flux<Integer> eager = Flux.just(loadFirst(), loadSecond());
Flux<Integer> lazy = Flux.defer(() ->
        Flux.just(loadFirst(), loadSecond()));
```

Đây là **đoạn minh họa**: hai hàm `loadFirst` và `loadSecond` được gọi ngay khi Java đánh giá đối số cho `Flux.just`. Với `Flux.defer`, cả hai hàm được gọi khi factory chạy cho từng subscription.

Các nguồn khác nhau có hành vi riêng:

| Factory | Thời điểm tạo dữ liệu | Lưu ý |
| --- | --- | --- |
| `Flux.just(a, b, c)` | Các biểu thức `a`, `b`, `c` được tính lúc assembly | Capture các giá trị có sẵn và phát lại chúng cho từng subscriber. |
| `Flux.range(start, count)` | Tính dãy theo subscription | Mỗi subscription có tiến độ phát riêng. |
| `Flux.fromIterable(iterable)` | Lấy iterator khi subscribe | Thường tạo iterator mới mỗi lượt; iterable phải hỗ trợ nhiều lần duyệt nếu muốn subscribe lặp lại an toàn. |
| `Flux.defer(factory)` | Gọi factory mỗi subscription | Factory có thể tạo nguồn mới hoặc trả lại một nguồn dùng chung. |
| `Flux.generate(stateSupplier, generator)` | State supplier tạo state cho từng subscription | Hữu ích khi cần state machine độc lập theo subscriber. |
| `Flux.create(callback)` | Callback nguồn được thực thi theo subscription | Phải quản lý đăng ký/hủy listener và backpressure strategy cẩn thận. |

Không kết luận mọi `Flux` đều cold chỉ vì kiểu của nó là `Flux`. Semantics phụ thuộc publisher gốc, operator biến đổi và cách quản lý kết nối.

### 4.1. State riêng mỗi subscription với defer

```java
Flux<Integer> isolated = Flux.defer(() -> {
    AtomicInteger counter = new AtomicInteger();
    return Flux.range(1, 3)
            .map(ignored -> counter.incrementAndGet());
});
```

Đây là **đoạn minh họa**; cần import `AtomicInteger`. Mỗi lần subscribe, factory tạo một counter mới, vì vậy mỗi subscriber có thể nhận `1, 2, 3`. Ngược lại:

```java
AtomicInteger sharedCounter = new AtomicInteger();
Flux<Integer> sharedState = Flux.range(1, 3)
        .map(ignored -> sharedCounter.incrementAndGet());
```

Counter nằm ngoài factory nên được capture và chia sẻ bởi mọi subscription. Lần đầu có thể nhận `1, 2, 3`; lần sau `4, 5, 6`. `AtomicInteger` chỉ làm thao tác tăng an toàn trong cạnh tranh; nó **không** biến state dùng chung thành state riêng. Nếu dữ liệu phải được cô lập theo request/subscriber, hãy tạo state bên trong `defer` hoặc state supplier tương ứng.

## 5. Cold và hot publisher: mối liên hệ với thời điểm tạo dữ liệu

### 5.1. Cold publisher: công việc được thực hiện theo từng subscriber

Cold publisher thường bắt đầu tạo hoặc đọc dữ liệu khi subscriber đăng ký. Mỗi subscription độc lập thường có thể nhận lại toàn bộ chuỗi logic từ đầu:

```java
Flux<Integer> cold = Flux.defer(() -> {
    System.out.println("create source for subscriber");
    return Flux.range(1, 3);
});
```

Đây là **đoạn minh họa**. Mỗi lần subscribe, factory in log và tạo nguồn range mới. Subscriber A nhận `1, 2, 3`; B đăng ký sau cũng bắt đầu từ `1`. Các thao tác truy vấn database, gọi HTTP hoặc tính toán trong nguồn cold có thể lặp lại theo mỗi subscription.

**Cold không có nghĩa là tự động chạy trên thread riêng.** Một cold publisher đồng bộ có thể thực hiện công việc ngay trên thread gọi subscribe/request. Muốn asynchronous/nonblocking cần nguồn và operator phù hợp.

### 5.2. Hot publisher: nguồn có thể hoạt động độc lập với subscriber

Hot publisher có thể phát dữ liệu độc lập với thời điểm một subscriber đăng ký. Subscriber đến muộn có thể bỏ lỡ các sự kiện đã phát, trừ khi nguồn có buffer/replay/cache. Ví dụ điển hình là stream sự kiện từ sensor, message bus hoặc `Sinks.Many` multicast.

Trong Reactor, `Mono.just(value)` là trường hợp cần hiểu tinh tế: nó **capture giá trị tại assembly time**, rồi phát giá trị đó cho subscriber. Tài liệu Reactor xếp `just` vào ví dụ hot theo nghĩa giá trị được chốt từ assembly, dù tín hiệu `onNext` chỉ được gửi khi có subscription. Nó không giống một nguồn sự kiện live multicast đang tự phát liên tục.

### 5.3. So sánh nhanh

| Thuộc tính | Cold | Hot |
| --- | --- | --- |
| Khi nào nguồn tạo/phát dữ liệu | Thường khi có subscription | Có thể trước hoặc không phụ thuộc subscription |
| Subscriber đến sau | Thường nhận lại từ đầu | Có thể chỉ nhận sự kiện từ thời điểm tham gia |
| Tác dụng phụ | Có thể lặp theo từng subscription | Có thể chia sẻ một upstream/tác dụng phụ |
| Tiến độ | Thường riêng từng subscription | Có thể là tiến độ chung của nguồn |
| Replay | Thường phát lại do tái thực thi | Chỉ khi nguồn/operator có chính sách replay/cache |
| Ví dụ | `Flux.range`, `Mono.defer` trả nguồn cold | `Sinks.Many` multicast, `share` trong lúc kết nối, `cache` replay |

Không có quy luật đơn giản “một đối tượng Flux luôn là cold” hay “mọi Mono.just đều phát ngay”. Hãy hỏi: **giá trị được tính khi nào, nguồn thực sự bắt đầu khi nào, và subscriber muộn nhận được phần nào?**

## 6. cache, share và defer làm thay đổi semantics ra sao?

### 6.1. cache: thực thi nguồn rồi replay tín hiệu đã cache

`cache()` chuyển một nguồn thành publisher lưu tín hiệu để subscriber sau nhận lại. Với `Mono.cache()`, kết quả terminal (giá trị, empty hoặc error) được cache theo semantics của API; subscriber sau không mặc nhiên gọi lại upstream. Có overload TTL để giới hạn thời gian giữ kết quả. Với `Flux.cache()`, cần xem chính sách history/TTL và giới hạn bộ nhớ: cache toàn bộ history của stream vô hạn có thể làm bộ nhớ tăng không giới hạn.

```java
Mono<Config> config = configClient.fetch()
        .cache(Duration.ofMinutes(1));
```

Đây là **đoạn minh họa**, cần import `java.time.Duration`. Subscriber đầu kích hoạt nguồn; trong thời hạn cache, subscriber sau nhận lại kết quả cache. Cache là lựa chọn về tính mới dữ liệu và chia sẻ, không chỉ là tối ưu tốc độ. Đối với dữ liệu phân quyền hoặc theo từng người dùng, phải đảm bảo cache key/scope đúng; một cache không phân biệt user có thể làm rò dữ liệu.

### 6.2. share: nhiều subscriber cùng dùng một upstream đang kết nối

`share()` cho phép nhiều subscriber chia sẻ một nguồn trong khoảng thời gian kết nối chung. Nó thường được hiểu qua mô hình `publish().refCount(1)`: upstream kết nối khi có subscriber cần và có thể bị disconnect khi không còn subscriber. Subscriber tham gia sau có thể bỏ lỡ các phần tử đã phát trước đó; `share()` không mặc nhiên replay lịch sử.

```java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
        .share();
```

Đây là **đoạn minh họa**, cần import `Duration` và `Flux`. Hai subscriber cùng hoạt động có thể quan sát cùng nhịp tick kể từ lúc tham gia, thay vì mỗi người có timer độc lập. Subscriber đến muộn không được đảm bảo nhận lại tick cũ. Vòng đời reconnect sau khi không còn subscriber phụ thuộc semantics cụ thể của operator/version và trạng thái nguồn.

### 6.3. defer không đồng nghĩa cold

```java
Flux<Event> deferred = Flux.defer(() -> sharedEventBus);
```

Đây là **đoạn minh họa**, `sharedEventBus` là nguồn hot được chia sẻ. `defer` gọi factory theo từng subscription nhưng factory trả cùng nguồn hot. Vì thế, subscription vẫn tham gia một nguồn sự kiện dùng chung; nó không tạo bus mới.

Muốn tạo nguồn độc lập, factory phải tạo nguồn độc lập:

```java
Flux<Integer> perSubscriber = Flux.defer(() ->
        Flux.range(1, 3));
```

Đoạn trên tạo một `Flux.range` mới theo mỗi subscription. Điều quyết định là **đối tượng và semantics mà factory trả về**, không phải chỉ có từ khóa `defer`.

### 6.4. Sinks: nguồn hot do ứng dụng phát tín hiệu

Reactor `Sinks.Many<T>` cho phép ứng dụng chủ động phát sự kiện. Các biến thể như `multicast()`, `unicast()` và `replay()` có chính sách subscriber/buffer khác nhau. Chọn sink theo yêu cầu: một consumer, nhiều consumer đang hoạt động hay cần replay lịch sử. Cần xử lý kết quả phát tín hiệu như `OK`, `FAIL_OVERFLOW`, `FAIL_NON_SERIALIZED`; không bỏ qua overflow hoặc phát đồng thời không đúng quy tắc.

Sinks không tự biến mọi luồng thành bền vững. Nếu cần không mất message khi tiến trình chết, cần broker/durable queue hoặc persistence; một sink trong bộ nhớ không thay thế cơ chế đó.

## 7. Nhiều subscription và tác dụng phụ

Một cold publisher có thể chạy lại logic upstream mỗi lần subscribe. Điều này thường mong muốn khi cần dữ liệu mới, nhưng nguy hiểm nếu side effect là ghi đơn hàng, gửi email hoặc trừ tiền.

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> request = Mono.fromSupplier(() -> {
    calls.incrementAndGet();
    return "result";
});

request.subscribe();
request.subscribe();
```

Đây là **đoạn minh họa**, cần xử lý subscriber/error phù hợp. Supplier được gọi hai lần vì có hai subscription. Với side effect, mỗi subscription có thể thực hiện hành động một lần; đừng mặc định publisher chỉ chạy một lần vì nó được gán vào một biến.

### 7.1. Retry cũng tạo subscription mới

```java
Mono<Result> result = remoteCall()
        .retry(2);
```

`retry(2)` có thể đăng ký lại upstream tối đa hai lần sau lỗi, ngoài lượt đầu. Nếu `remoteCall` cold, lời gọi upstream có thể được thực hiện tối đa ba lượt. Hãy cân nhắc timeout, backoff, idempotency và loại lỗi được retry. Với lệnh ghi không idempotent, retry mù có thể tạo side effect trùng.

### 7.2. Chỉ tạo một subscription cho một kết quả dùng chung

Nếu một luồng cần được tiêu thụ ở nhiều nơi, quyết định rõ liệu chúng cần cùng một lần thực thi hay mỗi nơi một lần thực thi:

- **Mỗi subscriber tự thực thi:** giữ nguồn cold và chấp nhận tác dụng phụ/chi phí lặp.
- **Chia sẻ khi đang chạy:** dùng `share`/`publish().refCount(...)` với chính sách vòng đời phù hợp.
- **Replay kết quả đã hoàn tất:** dùng `cache` với TTL/history có giới hạn thích hợp.
- **Một công việc nền sở hữu độc lập:** khởi chạy ở component có lifecycle rõ ràng, quản lý `Disposable`/shutdown và lỗi; đừng tạo subscription nền ngẫu nhiên trong controller.

Không dùng `cache()` chỉ để “chữa” việc gọi subscribe nhiều lần nếu chưa hiểu dữ liệu có thể stale bao lâu và cache có an toàn giữa người dùng hay không.

## 8. Assembly time trong Spring WebFlux

### 8.1. Tạo publisher trong controller

Một handler có thể tạo publisher khi được gọi cho request:

```java
@GetMapping("/profile")
public Mono<ProfileDto> profile(@RequestParam String id) {
    return profileService.findById(id);
}
```

Đây là **đoạn minh họa controller**, cần import Spring và định nghĩa `ProfileDto`/`profileService`. Controller tạo và trả publisher; WebFlux sau đó tiêu thụ publisher để ghi response. Nếu `profileService.findById(id)` trả cold publisher, subscription cho request đó kích hoạt thao tác đọc.

### 8.2. Dùng defer cho giá trị phải đọc tại subscription time

```java
@GetMapping("/request-time")
public Mono<String> requestTime() {
    return Mono.defer(() ->
            Mono.just(Instant.now().toString()));
}
```

Đây là **đoạn minh họa controller**, cần import `Instant`. Thời gian được đọc khi subscriber đăng ký. Nếu viết `Mono.just(Instant.now().toString())`, thời gian được chốt khi method tạo publisher chạy. Sự khác biệt có ý nghĩa khi publisher được tạo sớm rồi giữ lại trước khi subscribe, hoặc được chia sẻ giữa nhiều consumer.

### 8.3. Tránh giữ request-specific state trong publisher field của singleton

Ví dụ nguy hiểm:

```java
@Component
class BadService {
    private final Mono<String> startupValue =
            Mono.just(loadConfigurationNow());
}
```

Nếu bean singleton được tạo lúc khởi động, `loadConfigurationNow()` chạy một lần khi khởi tạo bean; mọi subscriber sau nhận cùng giá trị đã capture. Đây có thể là ý định nếu đó là cấu hình bất biến lúc startup, nhưng sai nếu giá trị phải mới theo từng request hoặc cần refresh.

Nếu cần truy xuất cấu hình hiện tại:

```java
@Component
class ConfigService {
    Mono<String> currentValue() {
        return Mono.defer(() -> Mono.just(loadCurrentConfiguration()));
    }
}
```

Đây là **đoạn minh họa**. Nếu `loadCurrentConfiguration` blocking, hãy xử lý scheduler/I/O đúng cách. Nếu dữ liệu nên cache trong một khoảng thời gian, dùng cache có TTL và chính sách refresh thay vì gọi lại không giới hạn.

### 8.4. Request Context và dữ liệu theo request

Dữ liệu correlation/request ID nên gắn với request lifecycle, thường qua Reactor `Context` hoặc cơ chế tracing tích hợp. Không capture mutable field của singleton để chứa ID của request hiện tại: nhiều request đồng thời có thể ghi đè lẫn nhau. `deferContextual` cho phép đọc context theo subscription:

```java
Mono<String> requestId = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "unknown")));
```

Đây là **đoạn minh họa**, context được cung cấp upstream bằng `contextWrite`. `Context` được gắn theo subscription, không phải ThreadLocal dùng chung giữa các request.

## 9. Lazy không có nghĩa nonblocking

Ba khái niệm phải tách biệt:

- **Lazy:** công việc chỉ bắt đầu khi subscription hoặc khi supplier được gọi.
- **Asynchronous:** caller không cần chờ công việc hoàn thành trong cùng call stack; kết quả đến sau qua callback/signal.
- **Nonblocking:** thread không bị giữ chờ I/O; runtime có thể dùng thread đó cho công việc khác trong lúc chờ.

`Mono.fromCallable(() -> jdbcTemplate.queryForObject(...))` có thể lazy, nhưng JDBC vẫn blocking khi callable chạy. `Mono.defer(() -> Mono.just(blockingCall()))` cũng trì hoãn lời gọi nhưng không làm nó nonblocking. Với API blocking bắt buộc phải dùng, có thể cô lập:

```java
Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **đoạn minh họa**, cần import Reactor và định nghĩa `legacyClient`. `boundedElastic` dành cho công việc blocking có giới hạn, không phải lý do để bọc toàn bộ ứng dụng bằng blocking call. Ưu tiên WebClient, R2DBC hoặc API reactive khi có thể.

### 9.1. Supplier chỉ chạy khi có demand thích hợp

Với `Mono.fromSupplier`, supplier không nhất thiết được gọi chỉ vì bạn tạo một biến Mono. Nó chạy khi subscription bắt đầu tiêu thụ giá trị theo demand. Nếu subscriber cancel trước khi supplier được thực thi, supplier có thể không chạy. Với nguồn đồng bộ đơn giản, supplier thường chạy ngay trong quá trình subscribe/request; với operator bất đồng bộ, thời điểm thực thi phụ thuộc pipeline.

## 10. Chọn factory theo mục tiêu

| Nhu cầu | Nên cân nhắc | Lý do |
| --- | --- | --- |
| Đã có giá trị bất biến, muốn phát lại giá trị ấy | `Mono.just(value)` / `Flux.just(values)` | Giá trị được capture lúc assembly. |
| Muốn gọi supplier mỗi subscription | `Mono.fromSupplier` | Factory đơn giản tạo một giá trị. |
| Hàm có thể ném checked exception hoặc trả null | `Mono.fromCallable` | Chuyển exception thành onError, null thành empty. |
| Muốn tạo/chọn publisher mới mỗi subscription | `Mono.defer` / `Flux.defer` | Trì hoãn việc tạo nguồn/pipeline. |
| Muốn state machine riêng mỗi subscription | `Flux.generate(stateSupplier, generator)` | State supplier được gọi cho từng subscription. |
| Muốn nhiều subscriber chia sẻ nguồn đang chạy | `share` / `publish().refCount(...)` | Chia sẻ upstream trong lifecycle kết nối. |
| Muốn replay kết quả/tín hiệu đã phát | `cache` / replay sink | Subscriber sau nhận dữ liệu đã giữ; phải quản lý TTL/history. |
| Muốn phát sự kiện hot do ứng dụng kiểm soát | `Sinks.Many` | Ứng dụng chủ động phát, với chính sách multicast/unicast/replay. |

## 11. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `Mono.just(methodCall())` lazy | Java gọi method trước khi gọi `just` | Dùng `fromSupplier`, `fromCallable` hoặc `defer`. |
| Dùng `Mono.just(null)` | Reactor không cho null làm onNext | Dùng `justOrEmpty`/`fromSupplier` null semantics và xử lý empty. |
| Nghĩ `defer` luôn tạo nguồn cold mới | Factory có thể trả lại cùng hot/cached publisher | Kiểm tra publisher thực sự được tạo/trả trong supplier. |
| Đặt mutable counter ngoài defer và kỳ vọng mỗi subscriber có state riêng | Mọi subscriber capture cùng object | Tạo counter bên trong factory/state supplier. |
| Dùng `fromCallable` rồi kết luận I/O đã nonblocking | Callable có thể gọi JDBC/file/network blocking | Dùng API reactive hoặc cô lập trên scheduler phù hợp. |
| Tạo publisher ở field singleton bằng giá trị cần refresh | Giá trị được capture từ startup/assembly và stale | Tạo publisher theo request hoặc cache có TTL/refresh rõ ràng. |
| Subscribe hai lần và nghĩ nguồn chỉ chạy một lần | Cold publisher có thể thực thi upstream hai lần | Kiểm soát boundary subscription; share/cache chỉ khi semantics cho phép. |
| Dùng `cache()` cho dữ liệu theo user mà không có key/scope | Có thể trả nhầm dữ liệu hoặc dữ liệu cũ | Cache theo key, quyền, TTL và phạm vi an toàn. |
| Dùng `share()` rồi kỳ vọng subscriber muộn nhận lịch sử | Share không mặc nhiên replay history | Chọn cache/replay nếu cần, với giới hạn bộ nhớ. |
| Tưởng `Mono.just` là live event bus | Nó capture giá trị assembly, không phải nguồn multicast event liên tục | Dùng sink/broker/Flux hot phù hợp. |
| Tưởng retry chỉ gọi lại operator mà không chạy lại nguồn | Retry resubscribe upstream | Kiểm tra idempotency và side effect. |
| Dùng field mutable trong singleton để lưu request hiện tại | Request đồng thời có thể ghi đè dữ liệu nhau | Dùng tham số method và Reactor Context. |
| Gọi `block()` trong WebFlux controller | Chặn thread xử lý HTTP | Trả publisher để WebFlux tiêu thụ. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào `load()` chạy trong `Mono.just(load())`?  
**Đáp án:** Ngay lúc Java lắp ghép biểu thức, trước khi `Mono.just` được gọi. Giá trị đã tính được capture vào publisher.

**Câu 2.** Cùng `Mono.defer(() -> Mono.just(load()))` được subscribe hai lần, `load()` chạy mấy lần?  
**Đáp án:** Hai lần, một lần cho mỗi subscription được thực thi, trừ khi có operator/cache bên ngoài thay đổi semantics hoặc subscription bị hủy trước khi supplier chạy.

**Câu 3.** `Mono.fromSupplier(() -> null)` phát gì?  
**Đáp án:** Không phát `onNext`; nó hoàn tất rỗng (`Mono.empty()`).

**Câu 4.** `Mono.defer(() -> sharedHotPublisher)` có tự biến publisher thành cold không?  
**Đáp án:** Không. Factory chạy theo subscription nhưng publisher trả về vẫn là nguồn hot được chia sẻ.

**Câu 5.** Hai subscriber cùng dùng `Mono.just(value)` có nhận hai object được tính lại không?  
**Đáp án:** Không. Biểu thức tạo `value` chạy lúc assembly; cả hai nhận giá trị đã capture. Nếu value mutable, họ có thể cùng tham chiếu tới một object.

**Câu 6.** `cache()` khác `share()` như thế nào ở mục tiêu chính?  
**Đáp án:** Cache giữ và replay tín hiệu theo chính sách cache; share phối hợp subscriber với upstream đang kết nối, không mặc nhiên replay history cho người đến muộn.

**Câu 7.** `fromCallable(() -> jdbcCall())` có nonblocking không?  
**Đáp án:** Không. Nó chỉ trì hoãn lời gọi và chuyển exception thành signal. JDBC vẫn blocking; cần API reactive hoặc scheduler phù hợp.

**Câu 8.** Một publisher được tạo trong constructor singleton bằng `Mono.just(Instant.now())` sẽ phát thời gian nào?  
**Đáp án:** Thời điểm constructor/assembly chạy, thường là lúc bean được khởi tạo, không phải thời điểm mỗi request subscribe.

**Câu 9.** Tại sao `retry(2)` có thể làm một lời gọi HTTP được thực hiện nhiều lần?  
**Đáp án:** Retry đăng ký lại upstream. Nếu nguồn cold, supplier hoặc request được tạo theo subscription sẽ chạy lại. Cần idempotency và chính sách retry rõ ràng.

## Ghi nhớ

- **Assembly time:** Java tính các đối số và tạo publisher. `Mono.just(methodCall())` gọi method ngay; giá trị đã được capture.
- **Subscription time:** `defer`, `fromSupplier` và `fromCallable` thực thi phần được trì hoãn khi publisher được tiêu thụ. Mỗi subscription có thể tạo giá trị/state mới.
- **Cold/hot là semantics của nguồn và cách kết nối:** `just` capture tại assembly; `defer` không tự làm một hot publisher thành cold; `share` chia sẻ nguồn đang kết nối; `cache` replay tín hiệu đã lưu.
- **State trong closure có thể được chia sẻ:** muốn riêng theo subscriber, tạo state trong factory/state supplier. Nhiều subscription hoặc retry có thể lặp side effect.
- **Lazy không đồng nghĩa nonblocking:** defer chỉ thay đổi thời điểm chạy; I/O blocking vẫn blocking.
- Trong Spring WebFlux, trả publisher và để framework quản lý HTTP subscription. Chọn cache/share/defer theo tính mới dữ liệu, request scope, quyền truy cập và vòng đời nguồn.

### Tài liệu tham khảo

1. [Project Reactor – Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html): phân biệt hot/cold, `just` và `defer`.
2. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `just`, `defer`, `fromSupplier`, `fromCallable`, `cache`.
3. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): nguồn Flux, `defer`, `generate`, `share` và `cache`.
4. [Project Reactor – Creating and Subscribing to a Flux or Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): assembly, subscription và các cách subscribe.
5. [Project Reactor – Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): nguồn hot và chính sách sink.
6. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): xử lý HTTP reactive và tích hợp publisher.
