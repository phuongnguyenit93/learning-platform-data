# Thứ tự phần tử khi dùng map, flatMap và concatMap

## 1. Vấn đề: nhận A → B → C nhưng kết quả lại B → C → A

Giả sử một hệ thống nhận ba sự kiện đơn hàng theo thứ tự **A, B, C**. Mỗi sự kiện cần đi qua dịch vụ kiểm tra rủi ro:

- A cần 300 ms.
- B cần 100 ms.
- C cần 200 ms.

Nếu xử lý **tuần tự**, kết quả theo thứ tự A, B, C. Nếu gửi ba yêu cầu bất đồng bộ cùng lúc, B có thể hoàn tất trước, tiếp theo là C rồi mới tới A.

Trong **Spring Cloud Function**, logic nghiệp vụ có thể đóng gói bằng `Supplier`, `Function` hoặc `Consumer`, được tra cứu qua `FunctionCatalog`, ghép bằng composition và chạy sau adapter HTTP, sự kiện hoặc serverless. Với các hàm nhận `Flux<T>`, lựa chọn toán tử Reactor quyết định một phần quan trọng của hợp đồng: **thứ tự các kết quả phát ra và thứ tự bắt đầu tác dụng phụ**.

Ba toán tử phổ biến cần phân biệt:

| Toán tử | Biến đổi | Số tác vụ con được xử lý | Thứ tự kết quả theo nguồn |
| --- | --- | --- | --- |
| `map` | `T -> R` đồng bộ | Không tự sinh publisher con | **Giữ thứ tự** tín hiệu đầu vào |
| `flatMap` | `T -> Publisher<R>`, rồi trộn các publisher con | Có thể đồng thời | **Không bảo đảm** thứ tự |
| `concatMap` | `T -> Publisher<R>`, rồi nối các publisher con lần lượt | Tối đa một publisher con đang được subscribe để xử lý | **Giữ thứ tự** theo nguồn và thứ tự bên trong từng publisher con |
| `flatMapSequential` | `T -> Publisher<R>`, đăng ký nhiều publisher con nhưng phát theo thứ tự nguồn | Có thể đồng thời | **Giữ thứ tự phát kết quả**, không nhất thiết giữ thứ tự tác dụng phụ |

**Điểm cốt lõi:** “Kết quả có đúng thứ tự không?” và “Các thao tác nghiệp vụ có được thực hiện tuần tự không?” là **hai câu hỏi khác nhau**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ngữ nghĩa thứ tự của `map`, `flatMap`, `concatMap` và `flatMapSequential`.
2. Biết vì sao `map` không phù hợp để xử lý một API trả `Mono<R>` nếu mục tiêu là `Flux<R>`.
3. Chọn toán tử khi có yêu cầu về thứ tự kết quả, thứ tự ghi dữ liệu, throughput hoặc latency.
4. Nhận diện ảnh hưởng của nguồn dữ liệu, lỗi, retry, subscription và adapter bên ngoài.
5. Viết function reactive có thể tái sử dụng qua `FunctionCatalog`, composition, HTTP, sự kiện và serverless.
6. Kiểm thử thứ tự bằng `StepVerifier` và thời gian ảo để tránh các bài test thiếu ổn định.

## 2. “Giữ thứ tự” là giữ thứ tự nào?

Với một `Flux<T>`, *thứ tự nguồn* là thứ tự các tín hiệu `onNext` mà subscription nhìn thấy. Ví dụ:

~~~java
Flux<String> ids = Flux.just("A", "B", "C");
~~~

Publisher trên phát A rồi B rồi C trong mỗi lần subscription thông thường.

Tuy nhiên, nếu dữ liệu đã đi qua một hàng đợi nhiều partition, một `flatMap` ở upstream hoặc một nguồn hot với nhiều producer, thứ tự `onNext` **có thể đã khác thứ tự tạo sự kiện ngoài đời thực**. Một `map` hoặc `concatMap` ở downstream chỉ giữ được thứ tự **mà nó thực sự nhận**, không thể tự suy ra và khôi phục “thứ tự gốc” ở hệ thống bên ngoài.

Cần phân biệt bốn loại thứ tự:

| Loại thứ tự | Câu hỏi cần trả lời |
| --- | --- |
| Thứ tự **nguồn** | Những `T` nào đi vào toán tử trước/sau? |
| Thứ tự **bắt đầu** | Yêu cầu I/O cho A có bắt đầu trước B không? |
| Thứ tự **hoàn thành tác dụng phụ** | Giao dịch ghi A có hoàn thành trước giao dịch ghi B không? |
| Thứ tự **phát kết quả** | Subscriber ở đầu ra nhận `R(A)` trước `R(B)` không? |

`flatMapSequential` có thể giữ **thứ tự phát kết quả**, dù B đã hoàn thành I/O trước A. Nếu thao tác gửi email, chuyển tiền hoặc cập nhật trạng thái xảy ra bên trong publisher con, thứ tự phát kết quả **không tự bảo đảm thứ tự tác dụng phụ**.

~~~mermaid
flowchart TB
    IN["Nguồn phát A → B → C"] --> Q{"Chọn toán tử"}
    Q --> MAP["map: biến đổi đồng bộ"]
    Q --> FLAT["flatMap: chạy publisher con đồng thời"]
    Q --> CONCAT["concatMap: nối publisher con tuần tự"]
    Q --> SEQ["flatMapSequential: đồng thời, phát có thứ tự"]
    MAP --> O1["A' → B' → C'"]
    FLAT --> O2["Có thể B' → C' → A'"]
    CONCAT --> O3["A' → B' → C'"]
    SEQ --> O4["A' → B' → C'"]
~~~

## 3. map: biến đổi từng phần tử và giữ thứ tự nguồn

`map` nhận một hàm biến đổi đồng bộ `Function<T,R>`:

~~~java
Flux<String> result = Flux.just(" A ", " B ", " C ")
    .map(String::trim)
    .map(String::toLowerCase);
~~~

Subscriber nhận `"a"`, `"b"`, `"c"` theo thứ tự. Các callback `map` chạy khi có phần tử `onNext`; chúng không tự tạo thêm scheduler hay xử lý I/O bất đồng bộ.

Một ví dụ với kiểu nghiệp vụ:

~~~java
record OrderEvent(String id, long amountCents) {}
record Decision(String id, boolean accepted) {}

Function<Flux<OrderEvent>, Flux<Decision>> validate = events ->
    events.map(order ->
        new Decision(order.id(), order.amountCents() > 0)
    );
~~~

Với đầu vào `[A, B, C]`, đầu ra sẽ là `[Decision(A), Decision(B), Decision(C)]` theo thứ tự đầu vào, nếu các phép biến đổi thành công và không có toán tử khác thay đổi thứ tự ở upstream/downstream.

### 3.1. map không có nghĩa tự chạy song song

~~~java
Flux<Integer> values = Flux.range(1, 5)
    .map(value -> expensiveCalculation(value));
~~~

Ngay cả khi `expensiveCalculation` tốn CPU, `map` không tự động phân tán năm phép tính lên năm thread. Trên một nguồn tuần tự, nó xử lý theo các tín hiệu nhận được. Phép tính tốn thời gian sẽ làm chậm quá trình phát phần tử tiếp theo.

**Không nên gọi một API blocking trong `map`** trên luồng xử lý nhạy cảm với blocking:

~~~java
// Không phù hợp cho I/O blocking trên event loop:
events.map(event -> blockingHttpClient.call(event));
~~~

Hãy ưu tiên client reactive trả `Mono<R>` và kết hợp bằng một toán tử flatten thích hợp. Nếu bắt buộc dùng thư viện blocking, cô lập công việc bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` với giới hạn đồng thời và timeout.

### 3.2. map cũng không tự “sửa” thứ tự đầu vào đã sai

~~~java
Flux<String> alreadyReordered = Flux.just("B", "A", "C");
Flux<String> mapped = alreadyReordered.map(String::toLowerCase);
~~~

`mapped` vẫn phát `b, a, c`. Nếu nghiệp vụ đòi sắp xếp theo sequence number, cần giữ khóa thứ tự trong payload và có cơ chế phục hồi thứ tự được thiết kế riêng.

## 4. flatMap: nhiều publisher con có thể xen kẽ kết quả

`flatMap` rất hữu ích khi mỗi phần tử dẫn tới một tác vụ bất đồng bộ:

~~~java
Function<String, Mono<String>> lookup = id ->
    remoteClient.lookup(id); // Mono<String>

Flux<String> found = Flux.just("A", "B", "C")
    .flatMap(lookup);
~~~

Với các tác vụ bất đồng bộ, `flatMap` có thể subscribe nhiều publisher con trước khi các publisher trước hoàn tất. Khi kết quả đến, nó **trộn tín hiệu** từ các publisher con vào luồng đầu ra theo khả năng sẵn có.

Vì vậy:

- A có thể được gửi đi trước B nhưng hoàn tất sau B.
- Subscriber có thể nhận kết quả B trước A.
- Khi mỗi inner publisher là `Flux<R>` nhiều phần tử, các phần tử từ nhiều publisher con còn có thể **xen kẽ** nhau.
- `flatMap` không có cam kết giữ thứ tự `T` ban đầu.

### 4.1. Thử nghiệm có độ trễ cố định

Ví dụ dưới đây mô phỏng thời gian xử lý, không cần HTTP server:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<String> a = Mono.just("A")
    .delayElement(Duration.ofMillis(300));
Mono<String> b = Mono.just("B")
    .delayElement(Duration.ofMillis(100));
Mono<String> c = Mono.just("C")
    .delayElement(Duration.ofMillis(200));

Flux<String> merged = Flux.just(a, b, c)
    .flatMap(inner -> inner);
~~~

Nếu ba publisher con được subscribe gần như cùng thời điểm, kết quả có thể đến theo thứ tự **B, C, A**. Ví dụ này sử dụng độ trễ khác nhau để cho thấy sự khác biệt, **không có nghĩa `flatMap` luôn đảo thứ tự**. Nếu các tác vụ hoàn tất đúng thứ tự hoặc toán tử chỉ có một inner publisher đang hoạt động, đầu ra vẫn có thể trùng thứ tự nguồn.

~~~mermaid
sequenceDiagram
    participant F as flatMap
    participant A as Mono(A) 300 ms
    participant B as Mono(B) 100 ms
    participant C as Mono(C) 200 ms
    participant D as Subscriber

    F->>A: subscribe A
    F->>B: subscribe B
    F->>C: subscribe C
    B-->>F: B hoàn tất
    F-->>D: onNext(B)
    C-->>F: C hoàn tất
    F-->>D: onNext(C)
    A-->>F: A hoàn tất
    F-->>D: onNext(A)
~~~

### 4.2. flatMap không tự tạo bất đồng bộ

Nếu mapper trả một `Mono.just(...)` hoàn tất ngay, output thường có thể theo thứ tự nguồn:

~~~java
Flux<String> result = Flux.just("A", "B", "C")
    .flatMap(id -> Mono.just(id.toLowerCase()));
~~~

Đây **không phải** bảo đảm thứ tự của `flatMap`; nó chỉ là hành vi dễ thấy khi tất cả thao tác nội bộ hoàn tất ngay trong ví dụ cụ thể.

Khi thư viện client hoặc scheduler thay đổi, thứ tự hoàn tất có thể đổi. Vì vậy, không dùng một lần test “đầu ra đúng thứ tự” để kết luận `flatMap` có ngữ nghĩa giữ thứ tự.

### 4.3. Giới hạn concurrency

~~~java
Flux<Decision> decisions = orders.flatMap(
    riskClient::check,
    8
);
~~~

Tham số `8` giới hạn số **inner publishers đang hoạt động đồng thời tại toán tử này trong một subscription**. Nó giúp kiểm soát tải, nhưng không chuyển `flatMap` thành toán tử bảo đảm thứ tự. Với `concurrency = 1`, các inner publishers thường được xử lý nối tiếp, nhưng nếu mục tiêu là thứ tự tuần tự rõ ràng, `concatMap` diễn đạt ý định tốt hơn.

Con số này cũng không phải tổng giới hạn trên nhiều pipeline, nhiều instance hoặc toàn bộ cluster.

## 5. concatMap: lần lượt hoàn tất publisher trước rồi mới tới publisher sau

`concatMap` có hình thức gần giống `flatMap`:

~~~java
Flux<String> ordered = Flux.just("A", "B", "C")
    .concatMap(id -> remoteClient.lookup(id));
~~~

Nhưng ở mức publisher con, `concatMap` xử lý chúng theo thứ tự nguồn: **publisher con của A được subscribe và xử lý đến khi hoàn tất trước khi chuyển sang publisher con của B**, rồi mới tới C.

Nếu tất cả inner publishers thành công và mỗi publisher phát một kết quả, output theo thứ tự A, B, C bất kể B là một tác vụ có thể hoàn thành nhanh hơn khi chạy riêng.

### 5.1. Mô phỏng cùng ba thời gian xử lý

~~~java
Flux<String> ordered = Flux.just("A", "B", "C")
    .concatMap(id -> switch (id) {
        case "A" -> Mono.just("A")
            .delayElement(Duration.ofMillis(300));
        case "B" -> Mono.just("B")
            .delayElement(Duration.ofMillis(100));
        default -> Mono.just("C")
            .delayElement(Duration.ofMillis(200));
    });
~~~

Đầu ra theo thứ tự **A, B, C**. Do các tác vụ chạy nối tiếp trong ví dụ, thời gian xử lý toàn bộ xấp xỉ `300 + 100 + 200 = 600 ms`, chưa kể chi phí lập lịch.

Mô hình dòng thời gian:

~~~text
0 ms         300 ms     400 ms             600 ms
A: [---------- hoàn tất]
B:             [--- xong]
C:                         [------ xong]
Output:       A          B                  C
~~~

Khác với `flatMap`, B không được xử lý sớm chỉ vì nó có độ trễ thấp hơn. Đây là đánh đổi: thứ tự và quyền kiểm soát side effect thường tốt hơn, nhưng thông lượng thấp hơn với I/O độc lập.

### 5.2. concatMap giữ thứ tự cả khi mỗi publisher con phát nhiều kết quả

~~~java
Flux<String> result = Flux.just("A", "B")
    .concatMap(id -> Flux.just(id + "-1", id + "-2"));
~~~

Đầu ra là:

~~~text
A-1, A-2, B-1, B-2
~~~

Hai phần tử của publisher A được phát trước khi bắt đầu publisher B. Nếu thay `concatMap` bằng `flatMap` và các publisher con là nguồn bất đồng bộ, kết quả của A và B có thể xen kẽ.

### 5.3. Giữ thứ tự phát không phải lời hứa giao dịch

`concatMap` chỉ đảm bảo lần lượt đăng ký/xử lý các publisher con. Nếu `repository.save(order)` trả một `Mono<Void>` chỉ hoàn tất **sau khi ghi thật sự thành công**, `concatMap` có thể giúp đảm bảo B không bắt đầu ghi trước khi A hoàn tất.

Tuy nhiên, nếu API trả một publisher hoàn tất ngay sau khi **đưa lệnh vào hàng đợi** mà giao dịch thật tiếp tục ở hệ thống ngoài, thì thứ tự completion của publisher không đủ để bảo đảm thứ tự commit thực. Hợp đồng của client/repository và transaction vẫn là yếu tố quyết định.

## 6. flatMapSequential: làm đồng thời nhưng phát theo thứ tự

Khi vừa muốn throughput cao, vừa yêu cầu subscriber nhận kết quả theo thứ tự nguồn, Reactor có `flatMapSequential`:

~~~java
Flux<String> output = Flux.just("A", "B", "C")
    .flatMapSequential(id -> remoteClient.lookup(id), 8);
~~~

Toán tử này có thể subscribe nhiều publisher con **đồng thời**, nhưng giữ kết quả của những publisher đến sau trong buffer nếu publisher trước chưa phát/hoàn tất đủ để bảo đảm thứ tự.

Với A chậm hơn B và C, B/C có thể hoàn tất sớm rồi **chờ A**. Khi có thể phát A theo đúng thứ tự, toán tử tiếp tục giải phóng các kết quả được giữ lại.

| Khía cạnh | `flatMap` | `flatMapSequential` | `concatMap` |
| --- | --- | --- | --- |
| Subscribe inner publishers song song | Có | Có | Không, xử lý tuần tự |
| Kết quả có thể vượt A để phát B trước | Có | Không | Không |
| Side effect B có thể chạy trước khi A hoàn tất | Có | **Có** | Không, nếu publisher A phản ánh completion thật |
| Có thể giữ kết quả chờ publisher đầu | Có thể có queue/prefetch | **Có, vì phải giữ thứ tự** | Không cần buffer kết quả của các inner chạy trước |
| Rủi ro A chậm làm B/C đợi ở đầu ra | Ít hơn | **Có, head-of-line blocking** | Có, vì B/C chưa được chạy |
| Đánh đổi chính | Thứ tự đầu ra | Bộ nhớ/latency do chờ | Giảm đồng thời/throughput |

### 6.1. Vì sao flatMapSequential không bảo vệ thứ tự ghi database?

~~~java
Flux<String> written = Flux.just("A", "B", "C")
    .flatMapSequential(id ->
        repository.write(id)
            .thenReturn(id),
        8
    );
~~~

`written` có thể phát A, B, C. Nhưng các `repository.write(...)` đã được subscribe đồng thời. B có thể **ghi xong trước A**, chỉ là tín hiệu đầu ra B được giữ lại cho đến khi A hoàn tất. Vì vậy, với cập nhật một aggregate theo sequence nghiêm ngặt, `concatMap` là lựa chọn dễ lập luận hơn.

### 6.2. Head-of-line blocking và bộ nhớ

Nếu A kéo dài 30 giây trong khi B đến Z hoàn tất sau 100 ms, `flatMapSequential` phải giữ nhiều kết quả để bảo đảm A xuất trước. Điều này có thể tăng bộ nhớ và độ trễ. Cần giới hạn concurrency/prefetch và đặt timeout hợp lý với nguồn có kích thước lớn.

Khi cần thứ tự **chỉ ở output** nhưng side effect được phép chạy đồng thời, `flatMapSequential` thường hữu ích. Khi cần **tuần tự hóa side effect**, dùng `concatMap`.

## 7. map với hàm bất đồng bộ: lỗi Flux<Mono<R>> rất thường gặp

Giả sử:

~~~java
interface RiskClient {
    Mono<Decision> check(OrderEvent order);
}
~~~

Dòng này **không tạo `Flux<Decision>`**:

~~~java
Flux<Mono<Decision>> nested =
    orders.map(riskClient::check);
~~~

`map` đã biến mỗi `OrderEvent` thành **một đối tượng `Mono<Decision>`**. Mỗi `Mono` con vẫn cần subscriber; nếu không được flatten, công việc kiểm tra có thể chưa chạy. Muốn kết quả thật sự là `Flux<Decision>`:

~~~java
// Ưu tiên throughput, cho phép kết quả đổi thứ tự:
Flux<Decision> fast = orders.flatMap(riskClient::check, 8);

// Xử lý tuần tự, giữ thứ tự và không chồng các tác vụ con:
Flux<Decision> sequential = orders.concatMap(riskClient::check);

// Gọi đồng thời, nhưng phát kết quả theo thứ tự input:
Flux<Decision> orderedOutput =
    orders.flatMapSequential(riskClient::check, 8);
~~~

Không dùng `doOnNext(order -> riskClient.check(order))` để thay cho những toán tử trên: `doOnNext` chỉ thực hiện side effect đồng bộ trong callback; publisher con trả về không tự được subscribe hay chờ.

## 8. Ví dụ Spring Cloud Function đầy đủ: ba cách kiểm tra đơn hàng

Bên dưới là một cấu hình Java 17+ dùng `record`. `DecisionClient` là API nghiệp vụ trả `Mono<Decision>`, được triển khai bởi HTTP client hoặc reactive repository của ứng dụng.

~~~java
package demo.ordering;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderingFunctions {

    public record OrderEvent(
        String orderId,
        long sequence,
        long amountCents
    ) {}

    public record Decision(
        String orderId,
        long sequence,
        boolean accepted
    ) {}

    public interface DecisionClient {
        Mono<Decision> decide(OrderEvent event);
    }

    // Biến đổi tại chỗ, đồng bộ và giữ thứ tự nguồn.
    @Bean
    public Function<Flux<OrderEvent>, Flux<OrderEvent>> positiveOrders() {
        return input -> input.filter(event ->
            event.amountCents() > 0
        );
    }

    // Cho phép nhiều thao tác I/O đồng thời, không bảo đảm thứ tự output.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideFast(
            DecisionClient client) {
        return input -> input.flatMap(client::decide, 8);
    }

    // Mỗi thao tác hoàn tất rồi mới bắt đầu thao tác kế tiếp.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideInOrder(
            DecisionClient client) {
        return input -> input.concatMap(client::decide);
    }

    // Thao tác đồng thời, subscriber nhận output theo thứ tự nguồn.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideOutputInOrder(
            DecisionClient client) {
        return input -> input.flatMapSequential(client::decide, 8);
    }
}
~~~

### 8.1. Diễn giải ba lựa chọn

Một nguồn phát:

~~~java
Flux<OrderingFunctions.OrderEvent> events = Flux.just(
    new OrderingFunctions.OrderEvent("A", 1, 100),
    new OrderingFunctions.OrderEvent("B", 2, 200),
    new OrderingFunctions.OrderEvent("C", 3, 300)
);
~~~

Nếu dịch vụ giả định trả quyết định B nhanh hơn A:

- `decideFast` có thể phát `Decision(B)` trước `Decision(A)`.
- `decideInOrder` phát quyết định A rồi B rồi C; yêu cầu B chỉ được xử lý tiếp sau khi publisher của A hoàn tất.
- `decideOutputInOrder` có thể hoàn tất xử lý B trước A, nhưng giữ kết quả B để phát ra sau kết quả A.

Với các quyết định có khóa `orderId` khác nhau và không phụ thuộc nhau, việc đổi thứ tự kết quả có thể chấp nhận được, giúp tăng throughput. Với một chuỗi cập nhật cùng aggregate theo `sequence`, cần thiết kế tính tuần tự hoặc cơ chế kiểm tra phiên bản một cách rõ ràng.

### 8.2. Đưa hàm qua FunctionCatalog và composition

Spring Cloud Function dùng `FunctionCatalog` để tra cứu, chuyển đổi kiểu và composition các function bean. Ví dụ lọc trước khi kiểm tra tuần tự:

~~~properties
spring.cloud.function.definition=positiveOrders|decideInOrder
~~~

Ở mức logic, một `Flux<OrderEvent>` đi qua `positiveOrders`, rồi các phần tử còn lại lần lượt vào `decideInOrder`. Toán tử `filter` giữ thứ tự **các phần tử không bị loại**; `concatMap` giữ thứ tự đó trong kết quả.

Nếu yêu cầu throughput cao hơn và không cần giữ thứ tự output, adapter có thể chọn:

~~~properties
spring.cloud.function.definition=positiveOrders|decideFast
~~~

Hai đoạn cấu hình trên là **hai lựa chọn độc lập**; khi triển khai chỉ dùng definition phù hợp. Đầu ra của composition không tự tạo HTTP endpoint hoặc kết nối broker: cần adapter, binding và cấu hình môi trường tương ứng.

## 9. Khi nào giữ thứ tự là yêu cầu nghiệp vụ?

### 9.1. Trường hợp có thể đổi thứ tự

Giả sử ba đơn A, B, C thuộc ba khách hàng khác nhau. Dịch vụ kiểm tra rủi ro không chia sẻ trạng thái giữa các đơn và mỗi kết quả có `orderId`. Nếu downstream tra cứu kết quả bằng ID, `flatMap` có thể phù hợp.

~~~java
Flux<Decision> decisions = orders.flatMap(
    client::decide, 8
);
~~~

Kết quả có thể đến theo thứ tự bất kỳ. **Đừng ghép kết quả vào đơn hàng bằng vị trí trong danh sách**; phải dùng khóa `orderId` hoặc correlation ID đi cùng kết quả.

### 9.2. Trường hợp phải giữ thứ tự tác động

Ví dụ sự kiện của **cùng một ví điện tử**:

~~~text
A: cộng 100
B: trừ 50 nếu số dư đủ
C: khóa ví
~~~

Nếu chạy B/C đồng thời với A, nghiệp vụ có thể ra kết quả khác nhau do phụ thuộc trạng thái. Chọn `concatMap` trong một pipeline cho cùng khóa, hoặc thiết kế partition theo khóa với thứ tự/transaction phù hợp.

Chỉ dùng `concatMap` **trên một publisher** vẫn chưa bảo đảm thứ tự toàn hệ thống nếu cùng ví được xử lý đồng thời từ **nhiều partition, nhiều subscription hoặc nhiều instance**. Cần cơ chế phân vùng theo key, kiểm soát cạnh tranh và transaction ở nơi lưu.

### 9.3. Chỉ cần giữ thứ tự phản hồi

Một báo cáo gọi nhiều API độc lập có thể muốn giữ thứ tự các dòng như danh sách yêu cầu ban đầu:

~~~java
Flux<ReportLine> lines = requests
    .flatMapSequential(reportService::fetch, 10);
~~~

Các request có thể chạy đồng thời, nhưng các dòng báo cáo được phát theo thứ tự requests. Chấp nhận được nếu tác dụng phụ của `fetch` độc lập và bộ nhớ có thể chịu kết quả chờ đầu dòng.

## 10. Lỗi, timeout và retry ảnh hưởng gì tới thứ tự?

Tất cả các toán tử có thể phát `onError` khi một inner publisher lỗi. Trong Reactive Streams, `onError` là tín hiệu terminal: publisher đang lỗi không thể tiếp tục phát thêm phần tử trong cùng subscription nếu không có một cấu trúc phục hồi ở phạm vi thích hợp.

### 10.1. Lỗi một phần tử có thể dừng toàn pipeline

~~~java
Flux<Decision> decisions = orders.concatMap(
    client::decide
);
~~~

Nếu B phát lỗi chưa xử lý, luồng kết quả có thể kết thúc ở B; C có thể không được xử lý. `concatMap` bảo đảm thứ tự trong trường hợp thành công **không có nghĩa tự động bỏ qua phần tử lỗi để tiếp tục**.

Với `flatMap`, các inner publishers đã chạy đồng thời cũng có thể bị hủy khi một lỗi được phát xuống downstream. Một số tác vụ bên ngoài có thể đã bắt đầu hoặc hoàn tất trước khi bị hủy.

### 10.2. Xử lý lỗi ở phạm vi từng phần tử

Nếu nghiệp vụ cho phép ghi nhận trạng thái “chưa thể quyết định”, hãy xử lý ngay bên trong publisher của từng đơn:

~~~java
enum Status { APPROVED, REJECTED, UNAVAILABLE }

record Result(String orderId, Status status) {}

Function<Flux<OrderEvent>, Flux<Result>> resilient = events ->
    events.concatMap(event ->
        riskService.evaluate(event)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(
                    new Result(event.orderId(), Status.UNAVAILABLE)
                )
            )
    );
~~~

`OrderEvent` và `riskService.evaluate` là các kiểu/API giả định của ứng dụng, với `evaluate` trả `Mono<Result>`. `UNAVAILABLE` thể hiện lỗi tạm thời, khác với `REJECTED` vì nghiệp vụ kết luận từ chối. Sau khi trả một fallback cho B, `concatMap` có thể tiếp tục C theo thứ tự.

Không chuyển lỗi thành “đã duyệt” hoặc im lặng bỏ event nếu nghiệp vụ yêu cầu ghi đầy đủ. Khi cần báo lỗi để retry/đưa vào dead-letter, hãy để lỗi truyền ra cơ chế xử lý thích hợp.

### 10.3. flatMapDelayError và concatMapDelayError

Reactor có các biến thể trì hoãn lỗi trong một số tình huống như `flatMapDelayError` và `concatMapDelayError`. Ý nghĩa chung là cho phép một số publisher con tiếp tục xử lý trước khi báo lỗi kết thúc. Tuy nhiên:

- Trì hoãn lỗi **không có nghĩa mất lỗi**; cuối luồng vẫn cần xử lý tín hiệu error.
- `flatMapDelayError` **không khôi phục thứ tự kết quả** của `flatMap`.
- `concatMapDelayError` vẫn cần đánh giá hành vi với nguồn, prefetch và điểm phát lỗi.
- Các biến thể delay-error không thay thế dead-letter, idempotency hoặc transaction.

Nếu cần kết quả cho từng đơn ngay cả khi một số đơn thất bại, một kiểu kết quả nghiệp vụ như `Result(orderId, status, errorCode)` thường rõ hơn việc chỉ nhìn tín hiệu error terminal.

### 10.4. Retry làm thay đổi số lần thực thi

~~~java
Flux<Decision> retried = orders
    .concatMap(event -> client.decide(event).retry(2));
~~~

Retry ở **bên trong** mỗi inner publisher có thể gọi lại tác vụ cho **cùng** event trước khi chuyển sang event kế tiếp. Với `concatMap`, đây vẫn là chuỗi tuần tự theo các publisher con.

Nếu đặt `retry(2)` **ở ngoài cùng**:

~~~java
Flux<Decision> retriedAll = orders
    .concatMap(client::decide)
    .retry(2);
~~~

lỗi sẽ khiến hệ thống thử subscribe lại upstream. Với nguồn cold, A có thể được xử lý lần nữa. Thứ tự trong mỗi lần xử lý có thể đúng, nhưng **side effect bị lặp** vẫn là rủi ro. Cần idempotency hoặc checkpoint nếu gọi lại có thể gây tác động không mong muốn.

## 11. Backpressure, prefetch và đánh đổi hiệu năng

### 11.1. flatMap nhanh hơn trong trường hợp nào?

Khi các publisher con thực sự bất đồng bộ và độc lập, `flatMap` có thể tận dụng thời gian chờ I/O: trong lúc đợi A, B và C có thể chạy. Nếu các tác vụ hoàn toàn đồng bộ hoặc CPU chạy trên cùng thread, `flatMap` không tự tạo thêm năng lực xử lý song song.

Cũng không nên dùng số concurrency quá lớn. Nó có thể gây quá nhiều socket, request, connection hoặc bộ nhớ tạm. Giới hạn phù hợp phụ thuộc tải thực tế, pool và hạn mức dịch vụ đích.

### 11.2. concatMap giảm overlap nhưng có thể tăng latency

`concatMap` giúp thứ tự và điều kiện “xong A mới xử lý B” dễ hiểu, nhưng một A rất chậm có thể làm các phần tử phía sau phải đợi. Với hệ thống nhận sự kiện liên tục, nếu nguồn nhanh hơn khả năng xử lý tuần tự, cần thêm backpressure hoặc hàng đợi bền vững ở biên nguồn.

### 11.3. flatMapSequential có chi phí buffer

Để phát kết quả theo thứ tự, `flatMapSequential` có thể phải giữ các kết quả hoàn tất sớm trong khi chờ publisher đầu. Với publisher con phát nhiều phần tử hoặc một A có thời gian chờ lớn, lượng dữ liệu đệm có thể đáng kể.

| Mục tiêu | Lựa chọn thường hợp lý | Đánh đổi chính |
| --- | --- | --- |
| Biến đổi giá trị tại chỗ | `map` | Không dùng cho tác vụ trả publisher |
| I/O độc lập, ưu tiên throughput | `flatMap(..., concurrency)` | Kết quả có thể đổi thứ tự |
| Cần tuần tự hóa side effect | `concatMap` | Ít tác vụ chạy đồng thời hơn |
| I/O độc lập, output theo thứ tự | `flatMapSequential(..., concurrency)` | Buffer và head-of-line blocking |
| CPU chạy song song | Thiết kế scheduler/partition phù hợp | Cần quản lý tài nguyên; `flatMap` đơn thuần không đủ |
| Đơn hàng theo key, nhiều key song song | Phân vùng theo key và xử lý tuần tự từng key | Cần tránh bùng nổ số nhóm và trạng thái |

Backpressure điều tiết **nhu cầu nhận**, còn concurrency giới hạn **số tác vụ con**. Dù đặt concurrency bằng 8, broker bên ngoài không nhất thiết tự giảm tốc theo đúng nhu cầu nếu adapter không truyền được tín hiệu Reactive Streams đến nguồn.

## 12. Giữ thứ tự theo khóa thay vì toàn bộ luồng

Một hệ thống có hàng nghìn khách hàng có thể cần:

- **Trong cùng một `customerId`:** xử lý A rồi B rồi C.
- **Giữa các khách hàng khác nhau:** cho phép xử lý song song để tăng throughput.

Đây là yêu cầu thứ tự **theo khóa**, không nhất thiết cần tuần tự hóa toàn bộ dòng sự kiện. Reactor có toán tử `groupBy` để chia luồng thành các nhóm theo key, và ta có thể áp dụng `concatMap` trong từng nhóm:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> byCustomer =
    input -> input
        .groupBy(OrderEvent::customerId)
        .flatMap(group ->
            group.concatMap(client::decide),
            8
        );
~~~

Đây là **phác thảo thiết kế**: `OrderEvent` cần có `customerId()` và `client.decide` trả `Mono<Decision>`. Ví dụ cho thấy các phần tử của **một nhóm đã được subscribe** được xử lý tuần tự; kết quả của các nhóm khác nhau có thể đan xen.

**Cần rất thận trọng với `groupBy` trong production:** số lượng khóa lớn hoặc nhiều group chưa được tiêu thụ có thể khiến queue lớn hoặc pipeline bị nghẽn, đặc biệt nếu `flatMap` giới hạn số group đang được subscribe. Với không gian khóa rộng, cơ chế phân vùng có số partition cố định ở broker/consumer hoặc worker queue theo key thường dễ kiểm soát hơn.

Một `groupBy` trong từng process **không đảm bảo cùng key không bị xử lý đồng thời ở instance khác**. Nếu yêu cầu thứ tự chặt chẽ toàn hệ thống, phải đảm bảo định tuyến và ownership của key qua các node.

## 13. Message<T>, correlation ID và rủi ro ghép sai kết quả

Khi output có thể thay đổi thứ tự, nên mang **khóa tương quan** đi cùng mỗi phần tử. Ví dụ:

~~~java
Function<
    Flux<org.springframework.messaging.Message<OrderEvent>>,
    Flux<org.springframework.messaging.Message<Decision>>
> decisionsWithHeaders = messages ->
    messages.flatMap(message ->
        client.decide(message.getPayload())
            .map(decision ->
                org.springframework.messaging.support.MessageBuilder
                    .withPayload(decision)
                    .copyHeaders(message.getHeaders())
                    .build()
            ),
        8
    );
~~~

Mỗi publisher con giữ tham chiếu tới **message đầu vào tương ứng** qua closure, do đó khi kết quả về muộn vẫn có thể gắn metadata đúng event. Một số header hệ thống như ID/timestamp có thể được tạo lại; binder có thể chuyển đổi hoặc lọc header theo transport. Cần xác định rõ các header nghiệp vụ bắt buộc như `eventId` hoặc `correlationId`.

### 13.1. Không ghép theo chỉ số vị trí

Sai lầm nguy hiểm:

~~~java
List<OrderEvent> inputs = ...;
List<Decision> outputs = ...; // Thu từ flatMap không giữ thứ tự

// Sai nếu giả định outputs[i] luôn ứng với inputs[i].
~~~

Với `flatMap`, vị trí kết quả không phải khóa tương quan ổn định. Hãy sử dụng `orderId`, `eventId` hoặc correlation ID. Nếu bắt buộc cần giữ thứ tự đầu vào ở output, cân nhắc `flatMapSequential` trong phạm vi publisher và đánh giá chi phí buffer.

### 13.2. Thứ tự output của Reactor chưa phải thứ tự đến ở broker

Ngay cả khi function dùng `concatMap`, adapter gửi message ra broker có thể có nhiều kết nối, partition, retry hoặc worker. Thứ tự mà **một subscriber Reactor nhận** và thứ tự mà **một consumer ở hệ thống khác nhận** chưa chắc trùng nhau.

Để có bảo đảm từ đầu đến cuối, cần kiểm tra routing key, partition, cơ chế producer/consumer, retry và cấu hình ordering của binder cụ thể. Không dùng thứ tự của các toán tử Reactor làm thay thế cho hợp đồng delivery của transport.

## 14. Luồng hữu hạn, liên tục và tác động lên ordering

### 14.1. Nguồn hữu hạn

Một `Flux.just(...)` thường phát theo thứ tự xác định và hoàn tất. Với nguồn hữu hạn, có thể dùng `StepVerifier` để kiểm tra toàn bộ output. Nếu thực sự cần **sắp xếp lại theo sequence number** sau khi xử lý không thứ tự, có thể dùng `sort`:

~~~java
Flux<OrderEvent> sorted = events
    .sort(java.util.Comparator.comparingLong(OrderEvent::sequence));
~~~

`sort` cần **đợi toàn bộ upstream hoàn tất** và giữ dữ liệu để sắp xếp. Đây là lựa chọn phù hợp cho lô hữu hạn kích thước kiểm soát được, **không phù hợp để sort toàn bộ một luồng vô hạn**.

### 14.2. Nguồn dài hạn

Với luồng sự kiện chạy liên tục, bạn hiếm khi có “toàn bộ” danh sách để sort. Nếu cần xử lý theo sequence, có thể dùng các cơ chế như:

- Phân vùng theo khóa và bảo đảm thứ tự ở từng partition.
- Kiểm tra `sequence`/version tại database để từ chối cập nhật cũ.
- Cửa sổ hữu hạn có buffer và quy tắc hết hạn khi thiếu sự kiện.
- Hàng đợi bền vững giúp khôi phục event đến chậm hoặc out-of-order.

Lựa chọn phụ thuộc vào mục tiêu: thứ tự kết quả ở một subscription, thứ tự tác dụng phụ của một aggregate, hay thứ tự bền vững xuyên nhiều hệ thống.

### 14.3. Chữ ký Flux không tự thay đổi số lần gọi Function

Trong Spring Cloud Function, `Function<Flux<T>, Flux<R>>` có thể được `apply(flux)` một lần để tạo pipeline dài hạn. Khi có subscription, các callback `map`/`flatMap`/`concatMap` chạy theo từng phần tử. Đừng hiểu mỗi `onNext` là một lần framework gọi lại lambda function bên ngoài.

Ngược lại, trong mô hình imperative `Function<T,R>` xử lý theo message, adapter có thể gọi `apply(t)` một lần cho mỗi message. Hai mô hình có ranh giới invocation khác nhau; ordering tại application cần gắn với ranh giới thực tế của adapter.

## 15. Kiểm thử thứ tự bằng StepVerifier và thời gian ảo

Một bài kiểm thử chỉ chạy `flatMap` với các `Mono.just` hoàn tất ngay rồi thấy kết quả đúng thứ tự **không chứng minh được** toán tử có bảo đảm ordering. Nên chủ động tạo các độ trễ khác nhau.

Ví dụ test hoàn chỉnh dưới đây dùng JUnit 5, `reactor-test` và Java 17+:

~~~java
package demo.ordering;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OperatorOrderingTest {

    private static Mono<String> delayed(String id) {
        Duration delay = switch (id) {
            case "A" -> Duration.ofMillis(300);
            case "B" -> Duration.ofMillis(100);
            default -> Duration.ofMillis(200);
        };
        return Mono.just(id).delayElement(delay);
    }

    @Test
    void mapKeepsInputOrder() {
        StepVerifier.create(
                Flux.just("A", "B", "C")
                    .map(String::toLowerCase)
            )
            .expectNext("a", "b", "c")
            .verifyComplete();
    }

    @Test
    void flatMapMayEmitByCompletionTime() {
        StepVerifier.withVirtualTime(
                () -> Flux.just("A", "B", "C")
                    .flatMap(OperatorOrderingTest::delayed)
            )
            .thenAwait(Duration.ofMillis(650))
            .expectNext("B", "C", "A")
            .verifyComplete();
    }

    @Test
    void concatMapEmitsInSourceOrder() {
        StepVerifier.withVirtualTime(
                () -> Flux.just("A", "B", "C")
                    .concatMap(OperatorOrderingTest::delayed)
            )
            .thenAwait(Duration.ofMillis(650))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }

    @Test
    void flatMapSequentialEmitsInSourceOrder() {
        StepVerifier.withVirtualTime(
                () -> Flux.just("A", "B", "C")
                    .flatMapSequential(
                        OperatorOrderingTest::delayed,
                        3
                    )
            )
            .thenAwait(Duration.ofMillis(650))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }
}
~~~

Ở đây `StepVerifier.withVirtualTime` thay lịch thời gian của Reactor bằng đồng hồ ảo khi publisher được tạo **bên trong factory**. Nhờ vậy test không phải chờ 650 ms thật.

Các kỳ vọng phản ánh mô hình thời gian:

- `flatMap` subscribe ba inner publishers gần như cùng lúc; B phát sau 100 ms, C sau 200 ms, A sau 300 ms.
- `concatMap` đợi A 300 ms, rồi B 100 ms, rồi C 200 ms; sau khoảng 600 ms phát đủ A, B, C.
- `flatMapSequential` cho phép B/C hoàn thành sớm nhưng phát theo thứ tự A, B, C khi có thể giải phóng buffer.

**Lưu ý:** Đây là test cho publisher xác định, dùng scheduler thời gian ảo. Nó chưa kiểm tra lỗi mạng, thread của I/O client thật hoặc thứ tự message trên broker.

### 15.1. Kiểm thử thứ tự side effect bằng bộ đếm

Nếu yêu cầu quan trọng là không chồng tác vụ ghi, hãy kiểm tra **số inner publishers đang chạy**, không chỉ danh sách kết quả.

~~~java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxActive = new AtomicInteger();

Flux<String> pipeline = Flux.just("A", "B", "C")
    .concatMap(id ->
        Mono.defer(() -> {
            int current = active.incrementAndGet();
            maxActive.accumulateAndGet(current, Math::max);

            return Mono.just(id)
                .delayElement(Duration.ofMillis(10))
                .doOnTerminate(() -> active.decrementAndGet());
        })
    );
~~~

Khi subscribe và đợi publisher hoàn tất, `maxActive` dự kiến không vượt quá 1. Trong ví dụ, bộ đếm giảm ở tín hiệu terminal của inner publisher, phù hợp với điểm chuyển sang inner tiếp theo của `concatMap`. Tuy vậy, kiểm tra concurrency của publishers **không tự kiểm chứng transaction commit ở dịch vụ ngoài**.

### 15.2. Tránh test phụ thuộc Thread.sleep

~~~java
// Không nên dùng trong unit test ordering:
Thread.sleep(200);
assertEquals(...);
~~~

Các test dựa trên timing thật dễ thất bại khi CI tải cao. Với nguồn thời gian Reactor, `withVirtualTime` phù hợp. Khi phải kiểm tra I/O/broker thật, dùng integration test có timeout hữu hạn, dữ liệu định danh rõ và điều kiện chờ kết quả thay vì giả định một thứ tự/tốc độ do thread scheduling tạo ra.

## 16. Các lỗi thiết kế và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Input A, B, C nhưng nhận B, C, A | `flatMap` trộn các kết quả bất đồng bộ | Dùng `concatMap` hoặc `flatMapSequential` theo yêu cầu |
| Dùng `flatMapSequential` nhưng DB vẫn ghi B trước A | Các thao tác con chạy đồng thời | Dùng `concatMap` khi cần thứ tự side effect |
| Output là `Flux<Mono<R>>` | Dùng `map` với API trả `Mono<R>` | Flatten bằng toán tử phù hợp |
| `concatMap` quá chậm | Các thao tác I/O độc lập bị xử lý tuần tự | Cân nhắc `flatMap` giới hạn concurrency nếu cho phép đổi thứ tự |
| `flatMapSequential` tăng bộ nhớ | Kết quả B/C chờ A chậm | Giới hạn đồng thời, timeout và quan sát buffer |
| Đã dùng `map` nhưng kết quả “sai thứ tự gốc” | Upstream đã phát sai thứ tự nghiệp vụ | Giữ sequence/correlation ID; sửa nguồn hoặc khôi phục thứ tự có kiểm soát |
| Ghi trùng khi retry | Subscription hoặc thao tác side effect bị thực hiện lại | Idempotency, transaction, checkpoint |
| Thứ tự đúng trong test nhưng sai qua broker | Adapter/partition/retry thay đổi đường đi | Integration test ở ranh giới transport |
| Lỗi B khiến C không được xử lý | Lỗi inner publisher kết thúc subscription | Xác định fail-fast hay xử lý lỗi riêng từng phần tử |
| Map làm nghẽn event loop | Callback chứa thao tác blocking | Dùng client reactive hoặc cô lập blocking trên scheduler thích hợp |
| Chỉ cần thứ tự theo khách nhưng xử lý toàn bộ tuần tự | Dùng `concatMap` cho tất cả keys | Thiết kế phân vùng theo key và giới hạn tài nguyên |
| Bị treo khi dùng `groupBy` nhiều keys | Quá nhiều group chưa được subscribe/tiêu thụ | Dùng số partition hữu hạn hoặc thiết kế quản lý groups phù hợp |

## 17. Quy tắc chọn toán tử trong thực tế

~~~mermaid
flowchart TD
    START["Mỗi phần tử cần được xử lý"] --> ASYNC{"Mapper trả Publisher<R>?"}
    ASYNC -->|Không, trả R đồng bộ| MAP["map"]
    ASYNC -->|Có| ORDER{"Cần giữ thứ tự tác dụng phụ?"}
    ORDER -->|Có| CONCAT["concatMap"]
    ORDER -->|Không| OUT{"Cần đầu ra theo thứ tự nguồn?"}
    OUT -->|Có| SEQ["flatMapSequential\n+ giới hạn concurrency"]
    OUT -->|Không| FLAT["flatMap\n+ giới hạn concurrency"]
    MAP --> TEST["Kiểm tra nguồn,\nlỗi và adapter"]
    CONCAT --> TEST
    SEQ --> TEST
    FLAT --> TEST
~~~

Trước khi chọn, hãy đặt các câu hỏi cụ thể:

1. Đầu vào có thực sự có thứ tự và có sequence/key để đối chiếu không?
2. Phép biến đổi là đồng bộ hay trả `Mono`/`Flux`?
3. Thứ tự **phát kết quả** quan trọng, hay thứ tự **tác động lên hệ thống ngoài** quan trọng?
4. Có thể xử lý các khóa độc lập song song không?
5. Một publisher con có phát nhiều kết quả, gặp lỗi hoặc không bao giờ hoàn tất không?
6. Có bao nhiêu tác vụ được phép chạy đồng thời và có nguy cơ head-of-line blocking không?
7. Retry/resubscription có làm lặp tác vụ không?
8. Khi đi qua HTTP, binder hoặc serverless, adapter có giữ hợp đồng thứ tự cần thiết không?

## 18. Câu hỏi tự đánh giá

1. Vì sao `Flux.just("A","B","C").map(...)` giữ thứ tự phát của nguồn?
2. Nếu ba API request mất lần lượt 300, 100, 200 ms, `flatMap` có thể phát theo thứ tự nào?
3. `flatMap` có luôn thay đổi thứ tự kết quả không? Vì sao không được dựa vào việc tình cờ giữ thứ tự?
4. `concatMap` khác `flatMapSequential` ở **thời điểm bắt đầu thao tác con** như thế nào?
5. Vì sao `flatMapSequential` có thể giữ output A, B, C nhưng lệnh ghi B vẫn commit trước A?
6. Đoạn `orders.map(client::check)` có kiểu kết quả gì nếu `check` trả `Mono<Decision>`?
7. Khi nào nên chọn `flatMap(..., 8)`, và `8` có giới hạn tổng số request trên toàn cluster không?
8. Vì sao một `concatMap` downstream không khôi phục được thứ tự sự kiện nếu nguồn đã phát B trước A?
9. Nếu một inner publisher báo lỗi, `onErrorResume` đặt trong inner publisher và đặt ngoài toàn luồng khác nhau thế nào?
10. Vì sao dùng `retry` có thể làm lặp side effect dù thứ tự kết quả vẫn đúng?
11. Khi có nhiều khách hàng nhưng chỉ cần thứ tự theo từng khách, nên tổ chức concurrency ra sao?
12. `StepVerifier.withVirtualTime` giúp kiểm chứng sự khác biệt giữa ba toán tử như thế nào?
13. Có thể dựa vào thứ tự của Reactor để khẳng định Kafka/Rabbit sẽ giao message đúng thứ tự cuối cùng không?
14. Nếu một publisher con không bao giờ hoàn tất, `concatMap` và `flatMapSequential` chịu ảnh hưởng gì?

## 19. Tài liệu tham khảo

- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `map`, `flatMap`, `concatMap`, `flatMapSequential`, subscription và backpressure.
- [Project Reactor Test Reference](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier`, `withVirtualTime` và xác minh thứ tự các tín hiệu.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — hàm imperative/reactive và hợp đồng `Function<Flux<T>, Flux<R>>`.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — function qua binder và ranh giới xử lý message.

Các ví dụ Java sử dụng Java 17+ cùng Reactor và Spring Cloud Function. Hành vi subscription, retry và ordering tại transport cần được kiểm chứng theo phiên bản framework/binder đang triển khai.

**Ghi nhớ:** `map` giữ thứ tự các tín hiệu nguồn khi biến đổi giá trị đồng bộ; `flatMap` trộn các publisher con và có thể phát theo thứ tự hoàn tất; `concatMap` subscribe/xử lý các publisher con lần lượt để giữ thứ tự và tránh chồng tác vụ; `flatMapSequential` chạy đồng thời nhưng giữ thứ tự **phát kết quả**, không đảm bảo thứ tự **side effect**. Khi triển khai Spring Cloud Function qua HTTP, sự kiện hoặc serverless, hãy xác định rõ thứ tự cần bảo vệ ở đâu, chọn toán tử phù hợp và xác minh cả publisher lẫn adapter.
