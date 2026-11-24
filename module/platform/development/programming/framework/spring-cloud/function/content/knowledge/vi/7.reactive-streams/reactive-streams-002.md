# Phân biệt gọi hàm theo từng phần tử với gọi một lần cho cả luồng

## 1. Bài toán: cùng xử lý đơn hàng, hai cách gọi khác nhau

Trong Spring Cloud Function, logic nghiệp vụ có thể được đóng gói bằng `Supplier`, `Function` hoặc `Consumer` và tra cứu qua `FunctionCatalog`. Cùng một logic có thể được adapter đưa ra qua HTTP, sự kiện hoặc môi trường serverless. Khi sử dụng Project Reactor, một chi tiết dễ gây nhầm lẫn là:

> **Hàm được gọi bao nhiêu lần** khác với **bao nhiêu phần tử được xử lý trong publisher mà hàm trả về**.

Giả sử nguồn phát ba sự kiện đơn hàng `A`, `B` và `C`. Ta cần kiểm tra mỗi đơn và trả kết quả tương ứng.

- Với `Function<Order, Decision>`, phía gọi cung cấp **một `Order` cho mỗi lần gọi `apply(order)`**. Nếu adapter theo mô hình từng message, ba đơn tương ứng ba lần áp dụng hàm.
- Với `Function<Flux<Order>, Flux<Decision>>`, phía gọi có thể cung cấp **một `Flux<Order>` chứa cả ba đơn** trong một lần `apply(flux)`. Lambda bên ngoài chạy một lần để xây pipeline; toán tử `map` bên trong mới xử lý lần lượt `A`, `B`, `C` khi luồng được subscribe.

Hai thiết kế đều có thể cho ra ba kết quả, nhưng điểm bắt đầu, vòng đời, cách xử lý trạng thái, lỗi và khả năng tổng hợp toàn luồng khác nhau.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **lần gọi `Function.apply`**, **lần đăng ký `subscribe`** và **lần phát phần tử `onNext`**.
2. Nhận diện khi nào logic chạy theo từng phần tử, khi nào logic được gắn vào cả luồng.
3. Chọn chữ ký `Function<T,R>`, `Function<Mono<T>, Mono<R>>` hoặc `Function<Flux<T>, Flux<R>>` phù hợp.
4. Giải thích ảnh hưởng của lựa chọn này tới trạng thái, xử lý lỗi, message metadata, composition và adapter.
5. Dùng `StepVerifier` để kiểm chứng số lần gọi và số phần tử thực sự được xử lý.

## 2. Ba mốc thời điểm không được đánh đồng

Ở một hàm reactive, nên đặt ba câu hỏi khác nhau:

| Mốc | Điều gì xảy ra? | Khi nào thường xảy ra? |
| --- | --- | --- |
| **Gọi hàm** | Caller thực thi `function.apply(input)`; mã nằm trực tiếp trong thân lambda được chạy để tạo kết quả | Khi adapter hoặc mã ứng dụng gọi hàm |
| **Đăng ký luồng** | Subscriber đăng ký với publisher được trả về; pipeline được kích hoạt theo ngữ nghĩa Reactor | Khi framework/adapter hoặc test tiêu thụ kết quả |
| **Nhận phần tử** | Pipeline nhận tín hiệu `onNext(item)` và chạy các toán tử như `map`, `filter` hoặc `flatMap` | Mỗi khi có phần tử phù hợp từ nguồn |

Trong phần lớn pipeline Reactor *cold*, việc tạo publisher **chưa** thực thi các phép biến đổi từng phần tử. Tuy nhiên, Java code được viết **ở bên ngoài** các toán tử vẫn chạy ngay khi `apply` được gọi.

~~~java
Function<Flux<String>, Flux<String>> normalize = source -> {
    System.out.println("apply: xây pipeline");

    return source.map(value -> {
        System.out.println("map: xử lý " + value);
        return value.trim().toUpperCase();
    });
};

Flux<String> output = normalize.apply(Flux.just(" a ", " b "));
// Ở đây mới in: apply: xây pipeline

// Khi có subscriber:
// map: xử lý  a
// map: xử lý  b
~~~

Nếu publisher cold được subscribe lại, các thao tác trong `map` có thể chạy lại, **không nhất thiết** làm `apply` chạy lại. Ngược lại, nếu caller gọi `apply` nhiều lần, thân hàm có thể chạy nhiều lần ngay cả khi chưa ai subscribe kết quả.

Sơ đồ dưới đây tách hai cách áp dụng hàm:

~~~mermaid
flowchart TB
    subgraph I["Theo từng phần tử: Function<Order, Decision>"]
        IA["A"] --> IFA["apply(A)"]
        IB["B"] --> IFB["apply(B)"]
        IC["C"] --> IFC["apply(C)"]
        IFA --> IDA["Decision A"]
        IFB --> IDB["Decision B"]
        IFC --> IDC["Decision C"]
    end

    subgraph R["Theo cả luồng: Function<Flux<Order>, Flux<Decision>>"]
        RS["Flux gồm A, B, C"] --> RF["apply(flux) một lần"]
        RF --> RP["Pipeline: map(decide)"]
        RP --> RX["Subscription và các onNext"]
        RX --> RD["Decision A, B, C"]
    end
~~~

**“Gọi một lần cho cả luồng” chỉ đúng trong phạm vi một lần caller truyền một publisher vào hàm.** Đây không phải lời hứa rằng lambda được gọi duy nhất một lần trong suốt vòng đời ứng dụng. HTTP có thể gọi theo từng request, binder sự kiện có thể thiết lập pipeline dài hạn, và mỗi instance/restart có thể tạo thêm lời gọi.

## 3. Cách 1: Function nhận một phần tử mỗi lần

Một hàm imperative thường có dạng:

~~~java
import java.util.function.Function;

Function<String, String> cleanOne =
    value -> value.trim().toUpperCase();
~~~

Nếu caller gọi:

~~~java
String a = cleanOne.apply(" a ");
String b = cleanOne.apply(" b ");
String c = cleanOne.apply(" c ");
~~~

thì phần thân lambda chạy ba lần. Mỗi lần nhận một giá trị độc lập và trả một giá trị trực tiếp.

Trong ứng dụng tích hợp sự kiện, adapter hỗ trợ mô hình message-by-message có thể dùng hàm dạng `Function<OrderEvent, Decision>` để xử lý từng thông điệp. Framework thực hiện việc nhận message, chuyển đổi payload và gọi hàm với giá trị cụ thể; bản thân hàm không cần biết broker hay giao thức.

### 3.1. “Gọi theo từng phần tử” vẫn có thể nằm trong pipeline Reactor

Bạn cũng có thể dùng cùng một hàm imperative bên trong `Flux.map`:

~~~java
Function<String, String> cleanOne =
    value -> value.trim().toUpperCase();

Flux<String> cleaned = Flux.just(" a ", " b ", " c ")
    .map(cleanOne::apply);
~~~

Ở ví dụ này, chỉ có một lần tạo `cleaned`, nhưng `cleanOne.apply(...)` được gọi **mỗi khi `map` nhận một phần tử** trong từng subscription. Điều quan trọng là vị trí của lời gọi: nó nằm **bên trong** callback của toán tử `map`.

Vì vậy, không nên đánh giá “gọi từng phần tử” dựa vào việc đoạn chương trình có dùng `Flux` hay không. Hãy xác định chính xác **đối tượng được truyền cho `apply`** và **nơi `apply` được thực thi**.

### 3.2. Đặc điểm của hàm imperative

- Dễ viết, dễ kiểm thử cho logic thuần một vào/một ra.
- Mỗi lần `apply` có đối số và kết quả riêng.
- Hợp với thao tác xử lý từng message không cần trạng thái của các message khác.
- Nếu đặt I/O chặn luồng trong lambda, việc dùng hàm này bên trong một pipeline reactive **không** tự biến I/O thành bất đồng bộ.
- Khả năng retry, transaction và acknowledgment theo từng message do caller/adapter thiết kế; chỉ riêng kiểu `Function<T,R>` không cung cấp những bảo đảm đó.

## 4. Cách 2: Function nhận một publisher đại diện cho cả luồng

Một hàm reactive thường có dạng:

~~~java
Function<Flux<String>, Flux<String>> cleanStream =
    input -> input.map(value -> value.trim().toUpperCase());
~~~

Caller có thể áp dụng hàm với một `Flux`:

~~~java
Flux<String> source = Flux.just(" a ", " b ", " c ");
Flux<String> result = cleanStream.apply(source);
~~~

Ở đây:

1. `cleanStream.apply(source)` chạy một lần và trả về `Flux<String>` mới.
2. `result` biểu diễn pipeline; với nguồn cold trên, `map` chưa chạy.
3. Khi `result` có subscriber, `map` chạy cho mỗi phần tử được phát.
4. Khi nguồn phát `onComplete`, đầu ra cũng hoàn tất nếu không có lỗi và các toán tử không thay đổi hành vi kết thúc.

**Một lần gọi hàm không có nghĩa chỉ xử lý một phần tử.** Pipeline có thể xử lý 0, 1, hàng triệu phần tử hoặc tiếp tục cho đến khi nguồn bị hủy.

### 4.1. Mono cũng có ranh giới tương tự

~~~java
Function<Mono<String>, Mono<String>> cleanMono =
    input -> input.map(String::trim);
~~~

`cleanMono.apply(mono)` tạo publisher kết quả; callback `map` chỉ chạy nếu input thật sự phát một giá trị trong subscription. Với `Mono.empty()`, không có phần tử nào đi qua `map`. Một `Mono` cold có thể được subscribe nhiều lần, nên “tối đa một giá trị” là cho **một lần subscription**, không phải bảo đảm tác vụ chỉ chạy một lần mãi mãi.

### 4.2. Hạn chế về ý nghĩa của một lần gọi

Hàm kiểu `Function<Flux<T>, Flux<R>>` có thể nhận toàn luồng ở cấp API, nhưng **không đồng nghĩa nó tải tất cả phần tử vào bộ nhớ cùng lúc**. Thông thường toán tử xử lý dần theo tín hiệu và nhu cầu của downstream (backpressure). Chỉ các toán tử tích lũy như `collectList()`, `reduce()` hoặc một số dạng buffer mới cần chờ một phần hay toàn bộ dữ liệu theo hợp đồng của chúng.

## 5. Ví dụ Spring Cloud Function: hai bean cho cùng một nghiệp vụ

Chúng ta cài đặt hai cách kiểm tra đơn hàng. Quy tắc nghiệp vụ là đơn có `amountCents > 0` được chấp nhận. Ví dụ sử dụng Java 17+ (vì có `record`), Spring Framework/Spring Cloud Function và Project Reactor.

~~~java
package demo;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class OrderFunctionConfig {

    public record OrderEvent(String id, long amountCents) { }
    public record Decision(String id, boolean accepted) { }

    private static Decision decide(OrderEvent order) {
        return new Decision(order.id(), order.amountCents() > 0);
    }

    // Gọi apply(...) với một đơn tại một thời điểm.
    @Bean
    public Function<OrderEvent, Decision> decideOne() {
        return OrderFunctionConfig::decide;
    }

    // Gọi apply(...) với một Flux; map xử lý mỗi đơn khi có onNext.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideStream() {
        return source -> source.map(OrderFunctionConfig::decide);
    }
}
~~~

Cả hai đều dựa vào **một** hàm thuần `decide`, nên quy tắc nghiệp vụ không bị nhân bản. Tuy nhiên, chúng có hợp đồng gọi khác nhau:

| Khía cạnh | `decideOne` | `decideStream` |
| --- | --- | --- |
| Kiểu đầu vào | `OrderEvent` | `Flux<OrderEvent>` |
| Kiểu đầu ra | `Decision` | `Flux<Decision>` |
| Caller gọi `apply` | Mỗi lần có một order cần xử lý | Mỗi lần cung cấp một nguồn `Flux` |
| Xử lý từng order | Trong chính thân hàm `decide` | Trong callback `map` khi luồng phát dữ liệu |
| Kết quả nếu nguồn có ba order | Ba lời gọi trả ba `Decision` | Một lời gọi trả một `Flux` phát ba `Decision` |
| Có thể tổng hợp nhiều order trong cùng một lời gọi | Cần gom dữ liệu từ bên ngoài | Có thể dùng toán tử `window`, `buffer`, `reduce` tùy yêu cầu |
| Vòng đời tín hiệu | Kết quả trực tiếp hoặc ngoại lệ Java | `onNext`, `onComplete` hoặc `onError` do publisher phát |

Trong ứng dụng có nhiều function bean, một adapter thường cần biết function nào sẽ được expose/bind. Ví dụ chọn một trong hai:

~~~properties
spring.cloud.function.definition=decideStream
~~~

`FunctionCatalog` giúp tra cứu và composition các function bean theo tên, đồng thời tích hợp cơ chế chuyển đổi kiểu với adapter. Nó **không** xóa bỏ sự khác biệt giữa áp dụng một `OrderEvent` và áp dụng một `Flux<OrderEvent>`.

### 5.1. Minh họa lời gọi thuần Java

~~~java
OrderFunctionConfig configuration = new OrderFunctionConfig();

var one = configuration.decideOne();
var many = configuration.decideStream();

OrderFunctionConfig.OrderEvent a =
    new OrderFunctionConfig.OrderEvent("A", 100);
OrderFunctionConfig.OrderEvent b =
    new OrderFunctionConfig.OrderEvent("B", 0);

// Hai lần gọi hàm imperative:
OrderFunctionConfig.Decision resultA = one.apply(a);
OrderFunctionConfig.Decision resultB = one.apply(b);

// Một lần gọi hàm reactive để tạo pipeline cho hai order:
Flux<OrderFunctionConfig.Decision> results =
    many.apply(Flux.just(a, b));
~~~

`resultA` và `resultB` là giá trị hoàn tất ngay khi `apply` trả về. Ngược lại, `results` là một publisher; để phần tử chảy qua `map`, phải có subscription. Khi chạy trong Spring Cloud Function, việc subscribe thường thuộc trách nhiệm của caller/adapter.

## 6. Thí nghiệm đếm chính xác apply, subscribe và onNext

Đây là cách kiểm tra sự khác nhau mà không cần phụ thuộc HTTP hay message broker. Ba bộ đếm đặt ở ba vị trí khác nhau:

~~~java
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger applyCalls = new AtomicInteger();
AtomicInteger subscriptions = new AtomicInteger();
AtomicInteger processedItems = new AtomicInteger();

Function<Flux<String>, Flux<String>> uppercaseStream = input -> {
    applyCalls.incrementAndGet();

    return input
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .map(item -> {
            processedItems.incrementAndGet();
            return item.toUpperCase(Locale.ROOT);
        });
};

Flux<String> output = uppercaseStream.apply(
    Flux.just("a", "b", "c")
);

// Ngay sau apply:  applyCalls=1; subscriptions=0; processedItems=0

StepVerifier.create(output)
    .expectNext("A", "B", "C")
    .verifyComplete();

// Sau subscription thứ nhất:
// applyCalls=1; subscriptions=1; processedItems=3

StepVerifier.create(output)
    .expectNext("A", "B", "C")
    .verifyComplete();

// Sau subscription thứ hai trên cùng publisher cold:
// applyCalls=1; subscriptions=2; processedItems=6
~~~

| Thời điểm | `applyCalls` | `subscriptions` | `processedItems` |
| --- | ---: | ---: | ---: |
| Trước `apply` | 0 | 0 | 0 |
| Sau `apply`, trước `StepVerifier` | 1 | 0 | 0 |
| Sau lần `verifyComplete()` đầu | 1 | 1 | 3 |
| Sau lần `verifyComplete()` thứ hai | 1 | 2 | 6 |

Kết quả này đúng với pipeline và nguồn `Flux.just(...)` *cold* trong ví dụ. Một nguồn hot, nguồn có chia sẻ subscription hoặc nguồn ngoài hệ thống sẽ có cách phát lại khác. Đo số lần subscription tại một điểm trong pipeline cũng không nhất thiết bằng tổng số kết nối mạng hoặc số lần nhận message từ broker.

### 6.1. Điều gì xảy ra nếu gọi apply hai lần?

~~~java
Flux<String> first = uppercaseStream.apply(Flux.just("a"));
Flux<String> second = uppercaseStream.apply(Flux.just("b"));
// applyCalls đã tăng thêm 2, dù chưa subscribe first/second.
~~~

Hàm tạo pipeline được gọi theo số lần caller áp dụng nó. Không nên đặt giả định “Spring chỉ gọi một lần” trong logic nghiệp vụ dùng chung, đặc biệt khi cùng function được sử dụng qua nhiều adapter.

### 6.2. Điều gì xảy ra nếu xử lý phần tử bằng một hàm riêng?

~~~java
AtomicInteger oneCalls = new AtomicInteger();

Function<String, String> uppercaseOne = text -> {
    oneCalls.incrementAndGet();
    return text.toUpperCase(Locale.ROOT);
};

Flux<String> output = Flux.just("a", "b", "c")
    .map(uppercaseOne::apply);
~~~

Mỗi subscription vào `output` sẽ gọi `uppercaseOne.apply` ba lần với nguồn cold này. Dù toàn bộ đoạn mã dùng Reactor, **lời gọi `uppercaseOne.apply` vẫn diễn ra theo từng phần tử**. Đây là sự phân biệt quan trọng giữa *hàm nhận Flux* và *hàm nhận T được gọi từ Flux*.

## 7. Tại sao Spring Cloud Function và adapter làm khác nhau?

Spring Cloud Function tách logic `Supplier`, `Function`, `Consumer` khỏi cơ chế kích hoạt. Vì vậy, cùng một bean có thể được gọi theo những nhịp khác nhau tùy adapter và môi trường.

### 7.1. Gọi trực tiếp qua FunctionCatalog

Một caller có thể tra cứu function theo tên và chủ động đưa vào giá trị:

~~~java
// Minh họa hợp đồng gọi, bỏ qua phần lấy bean/catalog:
Decision decision = decideOne.apply(order);
Flux<Decision> stream = decideStream.apply(orderFlux);
~~~

Caller quyết định có bao nhiêu lần gọi `apply`, bao nhiêu phần tử trong `orderFlux` và ai subscribe `stream`. `FunctionCatalog` làm việc với kiểu và wrapper của function, nhưng không bảo đảm rằng mọi function đều được gọi theo cùng một nhịp.

### 7.2. Qua HTTP

Một HTTP adapter thường tổ chức việc gọi theo từng HTTP request. Một request mới có thể dẫn đến một lần áp dụng hàm mới. Nếu đầu vào được ánh xạ thành `Flux<T>`, thì hàm reactive nhận một publisher cho phạm vi invocation đó; định dạng request, buffering/streaming và loại response cụ thể tùy adapter, phiên bản, cấu hình và content negotiation.

Không được suy ra rằng:

- Mọi `Flux` luôn tương đương “toàn bộ traffic HTTP từ khi server chạy”.
- Mọi HTTP request với mảng JSON đều tự động thành `Flux` có cùng cách xử lý.
- Trả `Flux` luôn đồng nghĩa client lập tức nhận mỗi phần tử qua một kết nối streaming.

Để xác nhận hành vi cần integration test qua HTTP với media type và runtime thực tế.

### 7.3. Qua sự kiện hoặc Spring Cloud Stream

Trong mô hình xử lý message riêng lẻ, một function imperative `Function<Event, Result>` thường được gọi cho **mỗi message**. Binder nhận từng message, có thể chuyển đổi payload, gọi hàm, rồi chuyển kết quả ra kênh/broker tiếp theo.

Với reactive function `Function<Flux<Event>, Flux<Result>>`, binder hỗ trợ luồng có thể thiết lập **một pipeline** và cung cấp dữ liệu cho nó theo thời gian. Function lambda bên ngoài thường được áp dụng khi kết nối pipeline; các phần tử tiếp tục chảy qua toán tử bên trong. Một số binder hoặc cấu hình có thể tái tạo pipeline khi khởi động lại, lập binding mới hoặc subscribe lại.

~~~mermaid
flowchart LR
    E1["Event A"] --> BUS["Event binder"]
    E2["Event B"] --> BUS
    E3["Event C"] --> BUS
    BUS --> FX["Flux<Event>"]
    FX --> FN["Function.apply(flux)"]
    FN --> PIPE["map / flatMap / filter"]
    PIPE --> OUT["Flux<Result>"]
    OUT --> OB["Output binding"]
~~~

Số lần callback nhận message **không bằng** số lần lambda function ngoài cùng được gọi. Ngoài ra, tín hiệu backpressure của Reactor không tự bảo đảm broker sẽ tạm dừng hoặc acknowledgment sẽ được thực hiện theo từng phần tử. Những điều đó phụ thuộc binder, connector, offset/ack mode và cấu hình.

### 7.4. Qua serverless

Runtime serverless thường có ranh giới một invocation, timeout và giới hạn tài nguyên. Một reactive function có thể tạo publisher cho mỗi invocation; framework phải đợi hoặc chuyển kết quả về theo giao thức được hỗ trợ. Luồng vô hạn không mặc nhiên phù hợp với mô hình invocation ngắn. Nếu cần xử lý sự kiện liên tục, hãy kiểm tra cách adapter duy trì nguồn, thời điểm kết thúc và chính sách retry/ack.

## 8. Những tình huống cần xử lý “cả luồng”

Chữ ký `Function<Flux<T>, Flux<R>>` không chỉ là biến thể cú pháp của `Function<T,R>`. Nó cho phép một lần áp dụng hàm tạo pipeline có các phép xử lý cần biết **mối quan hệ giữa nhiều phần tử**.

### 8.1. Lọc, biến đổi và gom theo cửa sổ

~~~java
Function<Flux<Long>, Flux<Long>> rollingTotals = amounts ->
    amounts
        .filter(amount -> amount > 0)
        .buffer(3)
        .map(batch -> batch.stream()
            .mapToLong(Long::longValue)
            .sum());
~~~

Với nguồn hữu hạn phát `10, -1, 20, 30, 40`, sau lọc ta được `10, 20, 30, 40`; `buffer(3)` tạo hai nhóm, nên publisher kết quả phát `60` và `40`. Một nhóm chưa đủ ba phần tử cũng được phát khi nguồn hoàn tất bình thường.

Logic này khó thể hiện bằng `Function<Long, Long>` thuần một vào/một ra vì kết quả phụ thuộc nhiều phần tử. Khi nguồn chạy vô hạn, một nhóm cuối chưa đủ ba phần tử có thể phải chờ các phần tử tương lai hoặc kết thúc.

### 8.2. Tổng hợp cuối luồng: Flux vào, Mono ra

~~~java
Function<Flux<Long>, Mono<Long>> totalAfterComplete =
    values -> values.reduce(0L, Long::sum);
~~~

Caller chỉ áp dụng function **một lần** cho một `Flux<Long>`; `reduce` xử lý lần lượt các phần tử nhưng đợi `onComplete` mới phát tổng. Nếu luồng sự kiện chạy mãi và không hoàn tất, không có “tổng cuối” để trả.

Khi cần cập nhật tổng định kỳ của một luồng không kết thúc, hãy dùng cửa sổ theo thời gian/số lượng, hoặc một trạng thái tích lũy phát nhiều kết quả (ví dụ `scan`) theo hợp đồng nghiệp vụ.

### 8.3. Gọi I/O bất đồng bộ cho từng phần tử

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> checkAsync =
    orders -> orders.flatMap(
        order -> fraudService.check(order), // Mono<Decision>
        8 // tối đa 8 tác vụ con đồng thời
    );
~~~

`checkAsync.apply(orders)` vẫn chỉ xây pipeline một lần cho publisher được truyền vào. Tuy nhiên, `fraudService.check(order)` có thể được gọi **mỗi khi xuất hiện phần tử**, với tối đa 8 inner publishers đang hoạt động đồng thời trong ví dụ. `flatMap` có thể làm kết quả ra khác thứ tự vào; dùng `concatMap` hoặc `flatMapSequential` khi yêu cầu thứ tự cao hơn hiệu năng đồng thời.

*Đoạn `checkAsync` chỉ minh họa cấu trúc: `OrderEvent`, `Decision` và `fraudService.check` là các kiểu/dịch vụ giả định trong ứng dụng.*

## 9. Tác động lên trạng thái và tài nguyên

### 9.1. Biến nằm bên ngoài toán tử chỉ được khởi tạo khi apply

~~~java
Function<Flux<Integer>, Flux<Integer>> numberItems = source -> {
    AtomicInteger counter = new AtomicInteger();

    return source.map(value -> counter.incrementAndGet());
};
~~~

Trong một lần `apply`, `counter` được tạo một lần và chia sẻ giữa các phần tử đi qua pipeline đó. Nếu subscribe lại **cùng** publisher kết quả, counter vẫn là đối tượng cũ nên giá trị có thể tiếp tục tăng. Nếu caller gọi lại `apply` để tạo publisher mới, counter mới được tạo. Điều này thường là nguồn lỗi khi lập trình viên tưởng biến trong function là “biến của mỗi message”.

Trong môi trường có nhiều subscription hoặc xử lý song song, trạng thái chia sẻ còn cần chú ý concurrency. Dùng một biến đổi thuần hoặc các toán tử trạng thái như `scan`/`window` sẽ dễ suy luận hơn.

### 9.2. Muốn có trạng thái riêng cho mỗi subscription?

Có thể trì hoãn tạo trạng thái đến lúc subscribe bằng `Flux.defer`:

~~~java
Function<Flux<String>, Flux<String>> numberPerSubscription =
    source -> Flux.defer(() -> {
        AtomicInteger sequence = new AtomicInteger();

        return source.map(value ->
            sequence.incrementAndGet() + ":" + value
        );
    });
~~~

Với nguồn cold hữu hạn, mỗi lần subscribe vào kết quả tạo một `sequence` mới bắt đầu từ 0. `defer` **không** thay đổi số lần `apply`; nó thay đổi thời điểm tạo publisher và trạng thái nằm bên trong callback của `defer`. Khi dùng luồng hot hoặc source có thể chia sẻ subscription, vẫn cần xét vòng đời nguồn cụ thể.

### 9.3. Side effect, retry và gửi trùng

Nếu lambda chạy trong `map` ghi database hoặc gọi API ngoài, nó có thể chạy lại khi publisher cold được subscribe thêm lần nữa hoặc khi cơ chế retry thực hiện đăng ký lại. Do đó:

- Không giả định `apply` gọi một lần sẽ kéo theo thao tác side effect đúng một lần.
- Với sự kiện có thể được phát lại, thiết kế idempotency theo ID sự kiện/đơn hàng.
- Không tự gọi `subscribe()` trong bean `Function<Flux<T>, Flux<R>>` nếu adapter là bên quản lý publisher; điều này dễ tách lỗi và cancellation khỏi caller.
- Khi thao tác trả `Mono<?>`, kết hợp bằng `flatMap`/`concatMap` thay vì `map` tạo `Flux<Mono<?>>` mà không có nơi subscribe các tác vụ con.

## 10. Tác động lên lỗi, thứ tự và ranh giới message

| Tình huống | Hàm nhận từng `T` | Hàm nhận `Flux<T>` |
| --- | --- | --- |
| Một phần tử gặp lỗi | Lần gọi hiện tại có thể ném exception | Lỗi không được xử lý tạo `onError` và thường kết thúc subscription đang chạy |
| Cần bỏ riêng phần tử lỗi | Caller/adapter quyết định tiếp tục các message khác | Xử lý trong inner publisher của từng phần tử, tùy nghiệp vụ |
| Giữ thứ tự | Có thể phụ thuộc thứ tự caller gọi và xử lý | `map` giữ thứ tự; `flatMap` có thể thay đổi; `concatMap` xử lý nối tiếp |
| Cần header/message key | Caller có thể đưa `Message<T>` vào hàm | Có thể dùng `Flux<Message<T>>` để giữ envelope cho từng phần tử |
| Transaction/ack | Không tự được bảo đảm bởi chữ ký | Không tự được bảo đảm bởi subscription hoặc `onComplete` |

Ví dụ một lỗi của dịch vụ có thể được xử lý theo phạm vi từng đơn:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> safeCheck =
    orders -> orders.flatMap(
        order -> fraudService.check(order)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(new Decision(order.id(), false))
            ),
        8
    );
~~~

Đây là chính sách *fail closed* minh họa. Chỉ biến lỗi thành kết quả `false` khi nghiệp vụ thực sự chấp nhận coi thất bại kiểm tra là từ chối đơn; nếu cần phân biệt trạng thái lỗi, hãy dùng một kiểu kết quả có trạng thái riêng.

Ngược lại, một `onErrorResume` đặt **sau** toàn bộ `flatMap` chỉ thay thế luồng đã lỗi và **không** khởi động lại subscription cũ từ phần tử kế tiếp. Trong luồng message dài hạn, chọn vị trí xử lý lỗi ảnh hưởng trực tiếp tới việc các thông điệp tiếp theo có còn được xử lý không.

### 10.1. Header của từng message không tự biến thành header chung của Flux

Nếu cần correlation ID hoặc routing key của mỗi sự kiện, chữ ký có thể là:

~~~java
Function<Flux<Message<OrderEvent>>, Flux<Message<Decision>>> route =
    messages -> messages.map(message ->
        MessageBuilder
            .withPayload(decide(message.getPayload()))
            .copyHeaders(message.getHeaders())
            .build()
    );
~~~

Cần import `org.springframework.messaging.Message` và `MessageBuilder`. Ví dụ copy header giúp thể hiện ý định, nhưng một số header do framework quản lý có thể được tạo lại hoặc bị binder xử lý đặc biệt. Với thao tác ghép N message thành một kết quả, hãy xác định rõ metadata nào được giữ, tổng hợp hoặc bỏ đi; không thể tùy tiện lấy header của phần tử đầu làm header cho toàn luồng.

## 11. Composition: chức năng nào xử lý phần tử, chức năng nào xử lý luồng?

Spring Cloud Function hỗ trợ tìm hàm và composition qua `FunctionCatalog`. Ví dụ:

~~~java
@Bean
Function<String, String> normalizeOne() {
    return String::trim;
}

@Bean
Function<String, String> labelOne() {
    return value -> "checked:" + value;
}
~~~

Một adapter có thể chọn:

~~~properties
spring.cloud.function.definition=normalizeOne|labelOne
~~~

Ở mức nghiệp vụ imperative, mỗi lần gọi composition áp dụng cả hai bước cho **một** giá trị. Nếu adapter gọi composition cho từng message, pipeline composition cũng chạy theo từng message.

Với dạng reactive:

~~~java
@Bean
Function<Flux<String>, Flux<String>> normalizeStream() {
    return source -> source.map(String::trim);
}

@Bean
Function<Flux<String>, Flux<String>> labelStream() {
    return source -> source.map(value -> "checked:" + value);
}
~~~

và:

~~~properties
spring.cloud.function.definition=normalizeStream|labelStream
~~~

Composition xây pipeline gồm hai phép biến đổi, còn mỗi phần tử lần lượt đi qua hai toán tử `map`. **Không suy ra số lần áp dụng composition chỉ bằng cách đếm phần tử.**

Việc ghép lẫn hàm imperative, reactive, `Mono`, `Flux` và `Message` phụ thuộc khả năng thích ứng kiểu của phiên bản Spring Cloud Function và adapter cụ thể. Khi yêu cầu có aggregation, split một vào nhiều, hoặc message header, hãy kiểm chứng composition bằng integration test chứ không mặc định dữ liệu luôn có ánh xạ một-một.

## 12. Supplier và Consumer cũng có hai cấp vòng đời

Dù chủ đề tập trung vào `Function`, phân biệt **lần gọi API chức năng** và **lần xử lý phần tử** còn áp dụng cho hai kiểu còn lại.

| Vai trò | Kiểu theo giá trị đơn | Kiểu theo publisher | Câu hỏi vòng đời |
| --- | --- | --- | --- |
| Supplier | `Supplier<T>` | `Supplier<Flux<T>>` | Adapter gọi `get()` bao nhiêu lần? Ai subscribe publisher nhận được? |
| Function | `Function<T,R>` | `Function<Flux<T>, Flux<R>>` | Caller gọi `apply()` bao nhiêu lần? Bao nhiêu `onNext` chạy qua các toán tử? |
| Consumer | `Consumer<T>` | `Consumer<Flux<T>>` | Ai nhận và xử lý nguồn? Ai quản lý subscription, lỗi và cancellation? |

Ví dụ:

~~~java
@Bean
Supplier<Flux<Long>> heartbeat() {
    return () -> Flux.interval(Duration.ofSeconds(1));
}
~~~

Khi `get()` trả một `Flux.interval`, phần tử được phát theo thời gian sau khi có subscriber. Không thể đếm số phần tử phát ra bằng số lần supplier `get()` được gọi. Việc adapter có tự kích hoạt supplier, gọi lại `get()` hay giữ một subscription dài hạn phải được kiểm tra ở môi trường đang dùng.

Đặc biệt với `Consumer<Flux<T>>` trả về `void`, không nên giả định caller đã có tín hiệu hoàn tất và lỗi của tác vụ bất đồng bộ. Cần hiểu quy ước của adapter và quản lý subscription thích hợp; nơi cần caller quan sát việc hoàn thành có thể cân nhắc function trả publisher như `Function<Flux<T>, Mono<Void>>` nếu adapter hỗ trợ hợp đồng đó.

## 13. Kiểm thử để không nhầm lẫn hai cách gọi

Thử nghiệm sau xác nhận bằng `StepVerifier` rằng thân hàm chạy một lần nhưng toán tử xử lý ba phần tử. Nó dùng Reactor Test và JUnit 5.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class InvocationBoundaryTest {

    @Test
    void oneApplyCanProcessThreeItems() {
        AtomicInteger applications = new AtomicInteger();
        AtomicInteger items = new AtomicInteger();

        Function<Flux<Integer>, Flux<Integer>> doubleAll = source -> {
            applications.incrementAndGet();

            return source.map(value -> {
                items.incrementAndGet();
                return value * 2;
            });
        };

        Flux<Integer> result = doubleAll.apply(Flux.just(1, 2, 3));

        assertEquals(1, applications.get());
        assertEquals(0, items.get());

        StepVerifier.create(result)
            .expectNext(2, 4, 6)
            .verifyComplete();

        assertEquals(1, applications.get());
        assertEquals(3, items.get());
    }

    @Test
    void perItemFunctionIsAppliedThreeTimes() {
        AtomicInteger applications = new AtomicInteger();

        Function<Integer, Integer> doubleOne = value -> {
            applications.incrementAndGet();
            return value * 2;
        };

        Flux<Integer> result =
            Flux.just(1, 2, 3).map(doubleOne::apply);

        assertEquals(0, applications.get());

        StepVerifier.create(result)
            .expectNext(2, 4, 6)
            .verifyComplete();

        assertEquals(3, applications.get());
    }
}
~~~

Hai test cùng kỳ vọng `2, 4, 6`, nhưng vị trí `apply` thay đổi đáng kể: một test gọi một lần với cả `Flux`, test còn lại gọi ba lần với ba số.

Với mã thực dùng adapter, nên bổ sung integration test xác nhận:

- Có bao nhiêu invocation được tạo cho một HTTP request hoặc cho N message.
- Header nghiệp vụ được giữ đúng khi function nhận `Message<T>` hay `Flux<Message<T>>`.
- Error, retry và acknowledgment của binder hoạt động theo ranh giới mong muốn.
- Luồng có được tiêu thụ và hủy khi ngừng ứng dụng, client ngắt kết nối hoặc serverless timeout.

## 14. Các nhầm lẫn phổ biến

| Nhầm lẫn | Diễn giải đúng |
| --- | --- |
| “Nhận `Flux<T>` tức là lambda chạy N lần với N phần tử.” | `apply(flux)` có thể chạy một lần; callback bên trong toán tử mới chạy theo phần tử. |
| “Function chỉ được gọi một lần khi khởi động ứng dụng.” | Điều đó có thể đúng với cách một binder dựng pipeline dài hạn, nhưng HTTP request, restart, nhiều instance hoặc caller khác có thể tạo lời gọi mới. |
| “`apply` đã trả `Flux` nghĩa là dữ liệu đã được xử lý.” | Publisher thường lazy; cần subscription để pipeline hoạt động. |
| “Một lần `apply` nghĩa là side effect chạy đúng một lần.” | Resubscription/retry với publisher cold có thể chạy lại tác vụ bên trong. |
| “Đặt `Function<T,R>` vào `map` sẽ gọi nó một lần cho cả `Flux`.” | Callback `map` gọi function với từng `T` trong mỗi subscription. |
| “`Flux` luôn có đủ dữ liệu để tính tổng cuối.” | Nguồn có thể vô hạn; `reduce` cuối luồng phải đợi `onComplete`. |
| “Lỗi một message chỉ hủy message đó.” | `onError` không được xử lý là tín hiệu kết thúc subscription; cần chọn phạm vi xử lý lỗi. |
| “Reactive đồng nghĩa với không blocking.” | Gọi JDBC, `Thread.sleep` hoặc `block()` trong toán tử vẫn có thể chặn thread. |
| “Luồng duy nhất tương đương transaction hoặc acknowledgment duy nhất.” | Giao dịch và xác nhận message tuân theo hệ thống I/O và adapter, không được xác định chỉ bằng chữ ký `Flux`. |

## 15. Quy tắc chọn chữ ký và câu hỏi tự đánh giá

Chọn `Function<T,R>` khi nghiệp vụ tự nhiên là xử lý độc lập từng đầu vào, adapter xử lý message-by-message và không cần truy cập dòng dữ liệu ở cấp luồng. Chọn `Function<Flux<T>, Flux<R>>` khi caller có thể cung cấp một publisher, hoặc khi cần phép biến đổi, kiểm soát đồng thời, cửa sổ, trạng thái hay tổng hợp gắn với luồng. Chọn `Function<Mono<T>, Mono<R>>` khi hợp đồng đầu vào/đầu ra của một invocation là tối đa một giá trị bất đồng bộ. Mọi lựa chọn cần được kiểm tra với adapter cụ thể về vòng đời, lỗi, backpressure và metadata.

Tự đánh giá bằng các tình huống sau:

1. `Function<Flux<Order>, Flux<Decision>>` được `apply` một lần với 100 order. Nếu dùng `map` thuần và subscribe một lần, có bao nhiêu lần chạy mã trong callback `map`?
2. Khi cùng publisher cold được subscribe hai lần nhưng `apply` không được gọi lại, các bộ đếm ở ngoài và bên trong `map` có thay đổi giống nhau không?
3. Trong ứng dụng nhận message liên tục, vì sao `Function<Flux<Order>, Mono<Total>>` có thể không phát giá trị nào?
4. Đưa một `Function<Order, Decision>` vào `Flux.map(function::apply)` có nghĩa function được gọi cho cả luồng hay cho từng phần tử?
5. Với ba sự kiện, tại sao số lần gọi lambda ngoài cùng không đủ để suy ra số lần gọi API chống gian lận bên trong `flatMap`?
6. Trước khi đưa một reactive function qua HTTP và qua event binder, bạn cần xác nhận điều gì về invocation, subscription, buffering, lỗi và xác nhận message?

**Ghi nhớ:** `apply` là lời gọi Java áp dụng hàm với **một đối số** — đối số đó có thể là một `T` hoặc một `Flux<T>`. `subscribe` kích hoạt việc tiêu thụ publisher. `onNext` khiến các phép biến đổi từng phần tử chạy. Khi viết Spring Cloud Function, hãy xác định rõ **ai gọi hàm, ai subscribe và dữ liệu chảy theo nhịp nào** trước khi quyết định vị trí đặt logic, trạng thái và xử lý lỗi.
