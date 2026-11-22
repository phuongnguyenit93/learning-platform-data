# Phát đồng bộ từng phần tử bằng Flux.generate

**Ngữ cảnh:** Spring Framework Reactive → Tạo nguồn dữ liệu.

`Flux.generate(...)` trong Project Reactor dùng để **tự tạo một chuỗi phần tử theo từng lượt, một cách đồng bộ, từ một hàm sinh (generator)**. Mỗi lần downstream có nhu cầu nhận dữ liệu, Reactor có thể gọi generator để tạo tín hiệu tiếp theo. Generator sử dụng `SynchronousSink<T>` để phát **tối đa một phần tử `T` trong một lần gọi**; đồng thời có thể báo hoàn tất hoặc lỗi.

Điểm cốt lõi là **một lượt sinh → tối đa một `onNext`**. Khi cần tính phần tử kế tiếp dựa trên trạng thái trước đó, `generate` đặc biệt hữu ích; khi chỉ cần các số nguyên liên tiếp hoặc duyệt một collection, những factory đơn giản như `Flux.range` và `Flux.fromIterable` thường dễ đọc hơn.

## 1. “Phát đồng bộ từng phần tử” nghĩa là gì?

Trong `Flux.generate`, hàm generator được gọi **đồng bộ** trong chuỗi xử lý subscription/request (trừ khi có sự điều phối scheduler từ bên ngoài). Generator phải quyết định tín hiệu cho lượt hiện tại **trước khi trả về**; nó không đăng ký callback để phát qua `SynchronousSink` vào một thời điểm bất kỳ trong tương lai.

Đối chiếu hai loại khái niệm:

- **Đồng bộ (synchronous):** callback tạo tín hiệu ngay trong lượt gọi hiện tại. Nó có thể chạy trên thread đang thực hiện subscription/request.
- **Từng phần tử (one by one):** mỗi lượt chỉ có **0 hoặc 1 `next`**, trong đó 0 chỉ hợp lệ nếu lượt đó kết thúc bằng `complete` hoặc `error`.
- **Backpressure:** downstream yêu cầu số phần tử qua `request(n)`. Generator được điều khiển theo nhu cầu thay vì phải phát toàn bộ một danh sách lớn ngay từ đầu.
- **Không đồng nghĩa với non-blocking:** nếu code trong callback gọi I/O blocking, thread chạy callback **vẫn bị chặn**. Bản thân `generate` không biến truy vấn database đồng bộ hay `Thread.sleep` thành non-blocking.
- **Không đồng nghĩa với một thread mới:** `Flux.generate` không mặc định tạo thread riêng cho từng item hay tự thực thi song song.

Ví dụ mô hình:

```text
Assembly (tạo mô tả Flux)
        |
        v
Subscriber đăng ký, nhận Subscription
        |
        v
downstream request(1)
        |
        v
generator(state, sink)
        |           |
        |           +-- sink.next(item) -- tối đa một lần
        |           +-- tùy chọn sink.complete() / sink.error(...)
        v
trả state tiếp theo
        |
        v
chờ demand kế tiếp / kết thúc / bị hủy
```

Đây là mô hình khái niệm. Trong một luồng có `map`, `buffer`, `publishOn` hoặc các operator khác, request có thể bị gộp/biến đổi, nên không suy luận máy móc “mỗi phần tử cuối cùng ứng với đúng một lần request(1) ở đầu chuỗi”.

## 2. Hợp đồng tín hiệu của SynchronousSink

`Flux.generate` dùng `SynchronousSink<T>`. Trong **mỗi invocation** của generator:

| Tín hiệu | Số lần hợp lệ | Ý nghĩa |
|---|---:|---|
| `sink.next(value)` | **Tối đa 1** | Phát một phần tử `T` không null |
| `sink.complete()` | 0 hoặc 1, kết thúc luồng | Kết thúc thành công |
| `sink.error(throwable)` | 0 hoặc 1, kết thúc luồng | Kết thúc do lỗi |

Có ba mẫu thường gặp:

```java
// Hợp lệ: tạo một phần tử, tiếp tục ở lượt sau.
sink.next(item);

// Hợp lệ: không tạo phần tử, dừng thành công.
sink.complete();

// Hợp lệ: phát phần tử cuối và hoàn tất ngay trong cùng lượt.
sink.next(lastItem);
sink.complete();

// Hợp lệ: báo lỗi và dừng, không phát phần tử ở lượt đó.
sink.error(new IllegalArgumentException("bad input"));
```

Đây là những **đoạn minh họa** đặt bên trong callback với biến `sink` và `item` phù hợp; chúng không tự chạy độc lập.

**Không được** gọi `next` hai lần trong một lượt:

```java
// SAI: một lần gọi generator không được phát hai item.
sink.next("A");
sink.next("B");
```

Reactor sẽ báo lỗi vì vi phạm quy tắc một `next`/lượt (ví dụ `IllegalStateException` về nhiều lần `onNext`). Không dùng vòng lặp để gọi `sink.next(...)` nhiều lần trong **cùng callback**.

**Không được** trả về mà chưa phát bất kỳ tín hiệu nào:

```java
// SAI: lượt generator này không có next, complete hoặc error.
Flux.generate(sink -> {
    // chưa làm gì
});
```

Nếu callback trả về mà không phát giá trị **và** không kết thúc, Reactor báo lỗi, thường là `IllegalStateException` với nội dung “The generator didn't call any of the SynchronousSink method”. Muốn không có phần tử ở lượt cuối, hãy gọi `sink.complete()` hoặc `sink.error(...)` rõ ràng.

`null` không phải một giá trị hợp lệ cho `sink.next(null)`; nó gây lỗi. Nếu nguồn không tìm được item tiếp theo, phát `complete` hoặc xử lý tình huống theo hợp đồng nghiệp vụ, thay vì gửi null.

### Phân biệt “không có item” với “có item rồi hoàn tất”

`sink.complete()` có thể được gọi:

1. **Không có `next`:** phiên sinh kết thúc mà không tạo thêm item.
2. **Sau một `next` trong cùng callback:** item cuối cùng được phát rồi luồng kết thúc.

Sau tín hiệu kết thúc, không gọi thêm `next`/`complete`/`error`. Một Flux có thể phát nhiều item **qua nhiều lượt**, dù mỗi callback bị giới hạn tối đa một item.

## 3. Ba overload của Flux.generate

Các chữ ký khái niệm trong Reactor:

```java
// 1. Không quản lý state tường minh:
Flux.generate(Consumer<SynchronousSink<T>> generator);

// 2. Một state riêng cho mỗi subscription:
Flux.generate(
        Callable<S> stateSupplier,
        BiFunction<S, SynchronousSink<T>, S> generator);

// 3. Có thêm dọn state/resource khi kết thúc hoặc hủy:
Flux.generate(
        Callable<S> stateSupplier,
        BiFunction<S, SynchronousSink<T>, S> generator,
        Consumer<? super S> stateConsumer);
```

Đây là **chữ ký minh họa** dùng để đọc API, không phải lệnh Java cần copy nguyên văn; `T` và `S` là generic type parameters.

- `T`: kiểu dữ liệu mà Flux phát ra.
- `S`: kiểu **state nội bộ** của generator; có thể khác `T`.
- `stateSupplier`: chạy cho **mỗi subscriber**, tạo trạng thái ban đầu độc lập.
- `generator`: nhận `state` và `sink`, phát tín hiệu cho lượt hiện tại, rồi **trả về state dùng ở lượt tiếp theo**.
- `stateConsumer`: nhận state cuối cùng để dọn tài nguyên khi chuỗi kết thúc hoặc bị hủy.

Đừng đặt state biến đổi dùng chung ở ngoài `stateSupplier` nếu bạn muốn mỗi subscription được chạy độc lập. Mỗi subscriber phải có một phiên state riêng để tránh rò rỉ dữ liệu, tranh chấp và kết quả khó dự đoán khi nhiều HTTP request cùng đăng ký.

## 4. Ví dụ đầu tiên: một phần tử mỗi lượt

Giả sử muốn phát ba số nguyên 1, 2, 3:

```java
Flux<Integer> numbers = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state);
            if (state == 3) {
                sink.complete();
            }
            return state + 1;
        });
```

Đây là **snippet** trong code đã import `reactor.core.publisher.Flux`.

Khi có đủ demand, dòng tín hiệu là:

```text
Lượt 1: state=1 → next(1)            → state mới=2
Lượt 2: state=2 → next(2)            → state mới=3
Lượt 3: state=3 → next(3), complete() → dừng
Downstream nhận: 1, 2, 3, onComplete
```

Một số điểm cần đọc kỹ:

- `() -> 1` là supplier khởi tạo state `Integer`; được gọi khi subscribe.
- Callback `(state, sink) -> {...}` là một hàm áp dụng lần lượt khi có nhu cầu.
- `sink.next(state)` phát **chính xác một số** mỗi lượt.
- Khi `state == 3`, có thể phát item cuối và `complete()` cùng callback.
- `return state + 1` cung cấp state tiếp theo. Sau khi đã complete, state mới không dẫn đến lần sinh thứ tư.

Trong bài toán “phát các số từ 1 đến 3” đơn giản, `Flux.range(1, 3)` ngắn và rõ hơn. `generate` trở nên hữu ích khi việc tạo item kế tiếp phụ thuộc logic trạng thái, điều kiện chuyển trạng thái hoặc tài nguyên cần quản lý.

### Biến thể: chỉ hoàn tất ở lượt kế tiếp

```java
Flux<Integer> numbers = Flux.generate(
        () -> 1,
        (state, sink) -> {
            if (state > 3) {
                sink.complete();
            } else {
                sink.next(state);
            }
            return state + 1;
        });
```

Biến thể này phát 1, 2, 3 rồi, **khi được gọi thêm một lượt**, gửi `complete()`. Sự khác biệt quan trọng với biến thể phía trên: nếu downstream chỉ request đúng ba item, chưa chắc có lượt thứ tư để phát tín hiệu hoàn tất. Khi biết **item cuối** ngay trong callback đang phát item đó, gọi `sink.complete()` cùng lượt thường giúp hoàn tất đúng lúc.

Không dùng thêm một lượt chỉ để “thử xem đã hết chưa” nếu hợp đồng yêu cầu kết thúc ngay sau item cuối và bạn có thể biết điều đó.

## 5. Chương trình Java 17+ chạy độc lập: quan sát demand và cleanup

Ví dụ sau cho thấy **tạo Flux**, **đăng ký nhưng chưa request**, **request theo đợt**, **phát một item/lượt** và **dọn state**. Đây là chương trình Java đầy đủ dùng Reactor Core, **không cần Spring Boot**, có thể chạy bằng Maven.

Cấu trúc thư mục:

```text
generate-demo/
├── pom.xml
└── src/main/java/demo/GenerateDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>generate-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/GenerateDemo.java`:

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class GenerateDemo {

    private static Flux<String> generateValues() {
        return Flux.generate(
                () -> 1,
                (state, sink) -> {
                    sink.next("value-" + state);

                    if (state == 3) {
                        sink.complete();
                    }
                    return state + 1;
                },
                lastState -> System.out.println("cleanup=" + lastState)
        );
    }

    public static void main(String[] args) {
        BaseSubscriber<String> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("subscribed");
                // Chưa request nên generator chưa sinh phần tử.
            }

            @Override
            protected void hookOnNext(String item) {
                System.out.println("next=" + item);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("complete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("error=" + error.getClass().getSimpleName());
            }
        };

        generateValues().subscribe(subscriber);
        System.out.println("request(1)");
        subscriber.request(1);
        System.out.println("request(2)");
        subscriber.request(2);
    }
}
```

Chạy từ thư mục chứa `pom.xml`, với JDK 17+ và Maven có thể tải dependency Reactor:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.GenerateDemo
```

**Standard output dự kiến của chương trình** (không tính thông báo riêng của Maven):

```text
subscribed
request(1)
next=value-1
request(2)
next=value-2
next=value-3
complete
cleanup=4
```

Vì sao thứ tự này xác định?

1. `BaseSubscriber` được override `hookOnSubscribe` mà **không** request ngay; do đó lần subscribe chỉ in `subscribed`.
2. `subscriber.request(1)` cấp nhu cầu cho một item. Source đồng bộ chạy generator một lần, phát `value-1`.
3. `subscriber.request(2)` cấp thêm hai item. Generator phát `value-2` rồi `value-3` ở **hai lần gọi khác nhau**.
4. Khi sinh `value-3`, callback gọi `sink.complete()`, vì vậy subscriber nhận `onComplete` ngay trong lượt cuối.
5. Callback trả state `4`; `stateConsumer` nhận state cuối để cleanup. Đoạn demo in `cleanup=4`. Trong ứng dụng thật, callback này đóng tài nguyên hoặc ghi nhận việc dọn dẹp thay vì chỉ in console.

**Về `BaseSubscriber`:** mặc định nếu không override `hookOnSubscribe`, nó request `Long.MAX_VALUE` (unbounded). Ví dụ đã override để tự cấp demand theo từng đợt. Lời gọi request trong ví dụ được thực hiện trên main thread, source là synchronous và không thêm `publishOn` nên không có thao tác I/O hoặc luồng phụ ảnh hưởng thứ tự output.

`BaseSubscriber` giúp thấy backpressure; trong **controller Spring WebFlux**, thường trả `Flux` và để framework/subscriber downstream quản lý subscription và demand. Không tự gọi `subscribe` chỉ để “bật Flux” rồi bỏ qua response HTTP.

## 6. State nội bộ: cách biến một lời gọi thành nhiều item liên tiếp

`Flux.generate` thường dùng khi tạo item kế tiếp phụ thuộc vào kết quả lần trước.

### 6.1. State bất biến (immutable)

Với `Integer` như ví dụ, mỗi lượt trả về state mới:

```java
Flux<Integer> squares = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state * state);
            if (state == 4) {
                sink.complete();
            }
            return state + 1;
        });
```

Kết quả khi có subscription và đủ request: **1, 4, 9, 16**, rồi `onComplete`. `Integer` ở đây là kiểu state; `sink` phát một `Integer` là bình phương của state. Có thể chọn state khác kiểu dữ liệu phát ra, chẳng hạn `S = Position`, `T = OrderEvent`.

### 6.2. State có thể thay đổi (mutable)

Bạn cũng có thể lưu state trong một object thay đổi được:

```java
Flux<String> labels = Flux.generate(
        () -> new java.util.concurrent.atomic.AtomicInteger(1),
        (counter, sink) -> {
            int value = counter.getAndIncrement();
            sink.next("item-" + value);
            if (value == 3) {
                sink.complete();
            }
            return counter;
        });
```

Đây là snippet. Mỗi subscription nhận **một `AtomicInteger` mới** từ supplier. Không cần dùng `AtomicInteger` chỉ để bảo vệ concurrent mutation trong trường hợp generator chạy tuần tự; một class state đơn giản hoặc số nguyên bất biến cũng được. Điều cần giữ là **không chia sẻ một mutable state trên nhiều subscriber**.

**Sai ví dụ: state dùng chung ngoài callback:**

```java
// KHÔNG nên nếu mỗi subscription phải bắt đầu độc lập từ 1.
AtomicInteger shared = new AtomicInteger(1);
Flux<Integer> wrong = Flux.generate(
        sink -> sink.next(shared.getAndIncrement()));
```

Đoạn này có thể chạy mãi nếu nhận demand không giới hạn, và các subscriber cùng dùng `shared` khiến mỗi subscription quan sát vị trí khác nhau. Không có nhánh `complete`/`error`; việc sinh vô hạn chỉ phù hợp khi chủ đích và được kiểm soát demand/cancellation.

### 6.3. Ví dụ hữu ích: Iterator có trạng thái riêng theo subscriber

```java
Flux<String> colors = Flux.generate(
        () -> java.util.List.of("red", "green", "blue").iterator(),
        (iterator, sink) -> {
            if (iterator.hasNext()) {
                sink.next(iterator.next());
            } else {
                sink.complete();
            }
            return iterator;
        });
```

Source này phát đúng ba chuỗi khi được request đủ lần; mỗi subscriber nhận một iterator riêng. Tuy vậy, với `List` đã có, **`Flux.fromIterable(List.of(...))` rõ ràng hơn**. Dùng `generate` khi phần tử kế tiếp cần một state machine hoặc thuật toán custom.

Nhánh không còn phần tử chỉ gọi `sink.complete()`. Không gọi `sink.next(null)`, không quay vòng liên tục cho tới khi iterator có item mới, và không gọi `iterator.next()` sau khi đã hết.

## 7. Kết thúc và lỗi theo state

Chọn đúng thời điểm kết thúc để luồng không bị treo hoặc phát dư.

### 7.1. Hoàn tất khi đạt điều kiện

```java
Flux<String> countdown = Flux.generate(
        () -> 3,
        (remaining, sink) -> {
            sink.next("T-" + remaining);
            if (remaining == 1) {
                sink.complete();
            }
            return remaining - 1;
        });
```

Kết quả: `T-3`, `T-2`, `T-1`, rồi completion. Nếu không gọi `complete` ở `remaining == 1`, generator có thể tiếp tục sang số 0, -1... khi có thêm demand.

### 7.2. Báo lỗi thay vì phát dữ liệu không hợp lệ

```java
Flux<Integer> checked = Flux.generate(
        () -> 0,
        (state, sink) -> {
            if (state == 2) {
                sink.error(new IllegalStateException("state 2 is invalid"));
            } else {
                sink.next(state);
            }
            return state + 1;
        });
```

Kết quả khi được subscribe với demand: phát `0`, `1`, sau đó `onError(IllegalStateException)`. Không có `onComplete` sau `onError`. Khi generator ném exception, Reactor cũng chuyển nó thành lỗi của luồng (trừ trường hợp ngoại lệ thuộc nhóm fatal theo hợp đồng thư viện), nhưng `sink.error(...)` giúp biểu đạt nhánh lỗi nghiệp vụ rõ ràng.

### 7.3. Empty sequence

```java
Flux<String> noItems = Flux.generate(sink -> sink.complete());
```

Đây là một Flux hoàn tất mà không phát item. Với nguồn rỗng cố định, `Flux.empty()` đơn giản hơn. `generate` có ích khi việc quyết định rỗng hay có dữ liệu **phụ thuộc state được kiểm tra tại subscription**.

## 8. Backpressure: downstream quyết định nhịp sinh

Ở mức Reactive Streams, `request(n)` thể hiện nhu cầu nhận thêm `n` phần tử, còn `cancel()` dừng subscription. `Flux.generate` phù hợp với backpressure vì một invocation chỉ tạo tối đa một item; nó có thể tạm dừng giữa các lượt khi không còn demand.

Ví dụ từ bài chạy độc lập:

```text
subscribe
  └── chưa request        → 0 lần sinh
request(1)
  └── generator lần 1     → next(value-1)
request(2)
  ├── generator lần 2     → next(value-2)
  └── generator lần 3     → next(value-3), complete
```

Lưu ý:

- **`request(2)` không có nghĩa callback được gọi một lần và được phép `next` hai lần.** Reactor gọi generator cho các lượt khác nhau, mỗi lượt tối đa một `next`.
- Nếu code dùng `subscribe(System.out::println)` hoặc `blockLast()`, downstream thông thường yêu cầu không giới hạn. Với một generator **vô hạn và tính toán quá nhanh**, luồng có thể chạy liên tục, đốt CPU và chiếm thread.
- Operator như `limitRate`, `buffer`, `publishOn` có thể thay đổi cách demand được truyền lên upstream (gộp/phân lô/prefetch). Phân tích demand tại vị trí thực của `Flux.generate`, không suy ra trực tiếp từ số item mà HTTP client nhận.
- **Backpressure không tự giúp I/O blocking trở thành non-blocking**. Nếu một lần generator chờ database trong 3 giây, thread chạy callback vẫn bị giữ 3 giây.

### Cancellation khi chưa hoàn tất

Ví dụ chỉ lấy hai item:

```java
Flux<Integer> upstream = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state);
            return state + 1;
        });

Flux<Integer> firstTwo = upstream.take(2);
```

Khi downstream tiêu thụ đủ hai item, `take(2)` kết thúc kết quả và hủy subscription upstream; generator không cần phát tiếp số 3. Trường hợp có tài nguyên hoặc mutable state, sử dụng overload với `stateConsumer` để dọn dẹp khi cancel.

**Không phụ thuộc vào `sink.complete()` để dọn tài nguyên** nếu subscriber có thể cancel sớm. Tài nguyên phải được giải phóng cả khi complete, error và cancel.

## 9. stateConsumer: dọn state khi complete, error hoặc cancel

Overload ba tham số:

```java
Flux<Integer> stream = Flux.generate(
        () -> new CounterState(0),      // state riêng mỗi subscriber
        (state, sink) -> {              // phát tối đa một item
            if (state.current >= 10) {
                sink.complete();
            } else {
                sink.next(state.current++);
            }
            return state;
        },
        state -> state.close());        // cleanup
```

Đây là **snippet**; `CounterState` là class giả định có `int current` và method `close()`. Dùng để thể hiện API cleanup, không phải chương trình Java có thể chạy một mình.

`stateConsumer` được Reactor dùng khi generator hoàn tất, lỗi hoặc downstream hủy. Tham số chính là state cuối cùng do generator trả về (hoặc state hiện có ở thời điểm hủy). Đây là nơi thích hợp để đóng iterator/resource có thể đóng, giải phóng bộ đệm đặc biệt hoặc ghi nhận cleanup.

Ví dụ state quản lý resource theo chuẩn Java:

```java
final class ResourceState implements AutoCloseable {
    private int next = 1;
    private boolean closed;

    int nextValue() {
        return next++;
    }

    @Override
    public void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}
```

Khi muốn dùng class này trong cùng project:

```java
Flux<Integer> generated = Flux.generate(
        ResourceState::new,
        (state, sink) -> {
            int current = state.nextValue();
            sink.next(current);
            if (current == 3) {
                sink.complete();
            }
            return state;
        },
        ResourceState::close
);
```

Hai snippet trên cần nằm trong project có Reactor và `Flux` đã import; `ResourceState` là class độc lập hợp lệ. Sau khi source hoàn tất hoặc bị cancel, Reactor gọi cleanup trên state tương ứng.

**Quan trọng:** `generate` cho phép state là `null` ở API, nhưng nếu sử dụng cleanup method reference như `ResourceState::close` thì phải bảo đảm supplier trả resource hợp lệ, hoặc kiểm tra null ở cleanup. Với resource ngoài hệ thống, cũng cần lưu ý cleanup có thể được kích hoạt từ luồng thực thi subscription/cancellation; không mặc định cho rằng nó luôn chạy trên cùng một thread cố định.

Nếu bài toán của bạn là **quản lý tài nguyên cho một stream** và logic chủ yếu là acquire/use/cleanup, `Flux.using` hoặc `Flux.usingWhen` có thể phù hợp hơn, đặc biệt với cleanup bất đồng bộ. `stateConsumer` phù hợp khi state/resource là một phần trực tiếp của thuật toán generator đồng bộ.

## 10. Khi nào nên dùng generate thay vì factory khác?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Một danh sách có sẵn | `Flux.fromIterable(items)` | Không tự viết state machine chỉ để duyệt |
| Dãy nguyên liên tiếp có giới hạn | `Flux.range(start, count)` | Ngắn, dễ hiểu |
| Một vài giá trị cố định | `Flux.just(a, b, c)` | Không cần generator |
| Một thuật toán sinh phần tử kế tiếp theo state, đồng bộ | **`Flux.generate`** | Một callback/một item, có state theo subscriber |
| Tích hợp API callback phát nhiều event, có thể đa thread | `Flux.create` hoặc `Sinks.Many` tùy thiết kế | Cơ chế phát tín hiệu phù hợp nguồn bất đồng bộ |
| Callback phát sự kiện từ một thread producer chuyên biệt | `Flux.push` có thể phù hợp | API push một producer; cần quản lý sự kiện và vòng đời |
| Tick theo đồng hồ | `Flux.interval` | Scheduler phát sự kiện theo thời gian |
| Một kết quả hoặc completion | `Mono`, `Mono.fromCallable`, `Mono.defer` tùy trường hợp | Hợp đồng 0..1 thay vì nhiều item |

### So sánh generate và create

`Flux.generate` nhận **`SynchronousSink`**; bạn chỉ dùng sink trong phạm vi **callback hiện tại**. Không lưu sink vào field rồi gọi `next` sau khi callback trả về.

`Flux.create` nhận **`FluxSink`**, được thiết kế để kết nối các API phát event bất đồng bộ như listener/callback và có thể phát nhiều tín hiệu. Khi dùng nguồn push ngoài, cần quản lý backpressure/overflow, cleanup callback và concurrency đúng cách.

```java
// Dùng generate khi item được tính ngay từ state:
Flux<Integer> calculated = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state * 10);
            if (state == 3) {
                sink.complete();
            }
            return state + 1;
        });

// Ví dụ ý tưởng create khi có một API listener bất đồng bộ:
// Flux.create(sink -> {
//     EventListener listener = event -> sink.next(event);
//     source.register(listener);
//     sink.onDispose(() -> source.unregister(listener));
// });
```

Đoạn `Flux.create` phía dưới là **pseudocode chú thích**; `EventListener` và `source` chỉ minh họa mô hình callback và phải được khai báo bằng API thực tế. Việc dùng `create` không tự tạo luồng mới hoặc tự bảo đảm non-blocking.

## 11. Liên hệ với Spring WebFlux

Khi xây dựng endpoint WebFlux, service/controller có thể trả một `Flux<T>` sinh bằng `generate`. WebFlux quản lý subscription và chuyển phần tử thành HTTP response theo HTTP codec và media type.

Ví dụ **một controller Java 17 dùng trong project Spring Boot có `spring-boot-starter-webflux`**:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class SequenceController {

    @GetMapping("/squares")
    public Flux<Integer> squares() {
        return Flux.generate(
                () -> 1,
                (state, sink) -> {
                    sink.next(state * state);
                    if (state == 5) {
                        sink.complete();
                    }
                    return state + 1;
                });
    }
}
```

Khi ứng dụng chạy bình thường, `GET /squares` trả dữ liệu tương ứng các phần tử **1, 4, 9, 16, 25**, theo cách Spring mã hóa response (thường là mảng JSON nếu client yêu cầu JSON). Đoạn class này **không phải ứng dụng Spring Boot độc lập**: cần main application, dependency, server và cấu hình phù hợp.

Luồng xử lý:

1. WebFlux gọi `squares()` và nhận một đối tượng `Flux<Integer>`.
2. Framework subscribe khi xử lý response; generator bắt đầu sinh khi downstream có demand.
3. Mỗi invocation phát tối đa một số; khi state bằng 5, `sink.complete()` báo hết dữ liệu.
4. JSON encoder/HTTP response hoàn tất sau khi Flux gửi terminal signal thành công.

### Tính đồng bộ của generate có phải vấn đề với event loop?

Không phải mọi xử lý đồng bộ đều xấu. Phép nhân nhỏ hoặc chuyển trạng thái rất nhanh thường phù hợp. Tuy nhiên, code generator **có thể chạy trên thread nhạy cảm với độ trễ của WebFlux**; tránh làm các việc sau trong callback:

- `Thread.sleep(...)`, chờ network/file I/O đồng bộ, hoặc gọi JDBC blocking.
- Vòng lặp chờ bận (busy wait) hoặc tính toán CPU nặng kéo dài.
- Chạy vòng lặp vô hạn để cố phát hàng nghìn item trong **một callback**.
- Gọi `subscribe()` trên publisher khác và giữ `SynchronousSink` để phát trong callback bất đồng bộ về sau.

Nếu thực sự cần kết nối nguồn I/O blocking, cân nhắc driver non-blocking thay thế. Khi buộc phải dùng thư viện blocking, cô lập có chủ đích trên `Schedulers.boundedElastic()` và kiểm soát pool, timeout, hủy; việc đổi scheduler không biến I/O đó thành non-blocking. Với nguồn callback bất đồng bộ, chuyển sang mô hình `Flux.create`/`Sinks` thích hợp.

### SSE có tự “phát chậm” vì generate không?

Không. `Flux.generate` có thể phát tất cả các item trong một khoảng rất ngắn khi có demand. Gắn `produces = MediaType.TEXT_EVENT_STREAM_VALUE` giúp lựa chọn định dạng/streaming, **không tự thêm delay** giữa các item. Nếu yêu cầu phát định kỳ, dùng `Flux.interval` hoặc operator thời gian được thiết kế cho mục đích đó, kèm chiến lược hủy và backpressure.

## 12. Những lỗi dễ mắc

### Lỗi 1 — gọi next nhiều lần trong cùng callback

```java
// Sai: callback này gọi next hai lần.
Flux.<Integer>generate(sink -> {
    sink.next(1);
    sink.next(2);
});
```

**Sửa:** lưu vị trí vào state; để Reactor gọi callback lần sau khi có demand, hoặc dùng `Flux.fromIterable`/`Flux.range` cho dữ liệu có sẵn.

### Lỗi 2 — không phát bất kỳ signal nào

```java
// Sai: không có tín hiệu next/complete/error.
Flux.generate(sink -> {
    if (false) {
        sink.next("never");
    }
});
```

**Sửa:** mỗi callback cần phát một item hoặc terminal signal. Nếu rỗng, `sink.complete()`.

### Lỗi 3 — dùng null làm tín hiệu hết dữ liệu

```java
// Sai: Reactor không cho phép phát null.
Flux.<String>generate(sink -> sink.next(null));
```

**Sửa:** gọi `sink.complete()` khi hết dữ liệu. Ở những API cũ trả nullable, kiểm tra null trước khi emit.

### Lỗi 4 — bỏ điều kiện kết thúc

```java
// Có thể vô hạn: mọi demand mới lại tạo thêm một item.
Flux<Integer> endless = Flux.generate(
        () -> 0,
        (state, sink) -> {
            sink.next(state);
            return state + 1;
        });
```

Với subscription unbounded, callback có thể chạy lâu và tiêu tốn CPU. **Sửa:** xác định điều kiện complete, giới hạn bằng `take(n)` khi phù hợp, và giám sát overflow/giới hạn kiểu số. Không dùng tăng `int` vô hạn nếu số tràn có ý nghĩa nghiệp vụ.

### Lỗi 5 — khởi tạo mutable state dùng chung

```java
// Sai khi kỳ vọng mỗi subscription chạy từ một state riêng:
java.util.concurrent.atomic.AtomicInteger global =
        new java.util.concurrent.atomic.AtomicInteger(0);
Flux<Integer> sharedState = Flux.generate(
        sink -> sink.next(global.incrementAndGet()));
```

**Sửa:** sử dụng overload có `stateSupplier` tạo state mới cho từng subscription.

### Lỗi 6 — tưởng generate tự là async hoặc non-blocking

```java
// Snippet SAI cho event loop: gọi I/O blocking trong generator.
Flux<String> blockingSource = Flux.generate(sink -> {
    String value = legacyJdbcQuery();
    sink.next(value);
});
```

`legacyJdbcQuery()` giả định là API blocking; snippet chưa khai báo hàm và cũng chưa có kết thúc. Dời task sang scheduler khi cần chỉ giải quyết vị trí thread bị chặn. Nếu code cần thực sự phát nhiều event từ nguồn bất đồng bộ, `generate` không phải bridge callback phù hợp.

### Lỗi 7 — gọi SynchronousSink sau khi callback đã trả về

```java
// Sai về hợp đồng: callback bất đồng bộ giữ sink để emit sau.
Flux<String> wrong = Flux.generate(sink -> {
    someAsyncApi(value -> sink.next(value));
});
```

`someAsyncApi` là pseudocode, không phải hàm có sẵn. Callback của `generate` trở về khi chưa phát tín hiệu và code đã giữ sink quá phạm vi hợp lệ. **Sửa:** kết nối nguồn listener/callback qua `Flux.create` hoặc `Sinks`, quản lý unsubscribe và backpressure.

### Lỗi 8 — chỉ complete khi được request thêm một lượt

Nếu generator biết vừa phát phần tử cuối cùng nhưng chưa `sink.complete()`, downstream có thể chờ terminal signal đến lượt tiếp theo. Khi biết điểm kết thúc ngay trong callback hiện tại, hãy kết thúc cùng lượt nếu hợp đồng cho phép.

### Lỗi 9 — không dọn state khi cancel sớm

Source có thể bị `take`, timeout, kết nối HTTP đóng hoặc subscriber gọi `cancel()`. Không đặt cleanup chỉ sau dòng `sink.complete()` trong body generator. Sử dụng `stateConsumer` hoặc operator quản lý resource thích hợp.

### Lỗi 10 — nhận định “một callback = một thread”

Reactor có thể chạy nhiều lượt callback trên cùng thread. Scheduler và cách downstream subscribe quyết định bối cảnh thực thi. `generate` không tự phân chia song song các lượt và không nên chia sẻ một `SynchronousSink` giữa nhiều thread.

## 13. Checklist thiết kế generator

Khi review một lời gọi `Flux.generate(...)`, hãy kiểm tra:

1. **Vì sao cần tự generate?** Có factory đơn giản hơn như `range`, `fromIterable`, `just`, `empty` hay không?
2. **Mỗi callback có đúng tối đa một `next`?** Không gọi trong vòng lặp nhiều lần.
3. **Mỗi callback có phát ít nhất một tín hiệu?** Nếu không có `next` phải có `complete` hoặc `error`.
4. **Điều kiện hoàn tất có chính xác không?** Có bỏ sót item cuối, sinh dư item hoặc cần request thêm chỉ để complete?
5. **State có riêng theo subscriber?** StateSupplier có được gọi mỗi subscription và không dùng mutable global?
6. **Không có blocking I/O hoặc CPU loop nặng trên event loop?** Nếu có, chọn nguồn/scheduler phù hợp.
7. **Có xử lý cancel/error/cleanup?** Đặc biệt khi state sở hữu tài nguyên.
8. **Có giới hạn sinh vô hạn?** Tính đến demand unbounded, cancellation, giới hạn kiểu số và tốc độ sinh.
9. **Có test với request theo đợt?** Quan sát cả item, terminal và việc giải phóng tài nguyên.
10. **Có trả publisher cho WebFlux?** Không dùng `subscribe()` trong controller để tách xử lý khỏi HTTP lifecycle.

## 14. Tự kiểm tra và tình huống áp dụng

| Tình huống | Kết luận |
|---|---|
| Callback gọi `sink.next(a)` rồi trả state | Hợp lệ; lượt sau có thể phát item kế tiếp |
| Callback gọi `sink.next(a); sink.complete();` | Hợp lệ; phát item cuối rồi hoàn tất |
| Callback gọi `sink.complete()` không có `next` | Hợp lệ; hoàn tất không thêm item |
| Callback không gọi `next`/`complete`/`error` | Không hợp lệ; Reactor báo lỗi |
| Callback gọi `sink.next(a); sink.next(b);` | Không hợp lệ; vi phạm one-next-per-call |
| Có `request(5)` | Reactor có thể gọi generator nhiều lượt; **không** cho phép 5 lần `next` trong cùng callback |
| Source giữ `AtomicInteger` ở static field | State có thể bị chia sẻ giữa subscribers; nên tạo state trong `stateSupplier` |
| `take(2)` trên generator vô hạn | Downstream chỉ nhận hai item và có thể cancel upstream |
| Generator chờ JDBC 2 giây | Thread thực hiện callback vẫn blocking; `generate` không tự non-blocking |
| Có nguồn WebSocket callback ngoài | Xem `Flux.create`/`Sinks`; không giữ `SynchronousSink` qua callback async |
| `stateConsumer` được cung cấp | Cho phép dọn state khi complete, error hoặc cancel |

**Bài tập nhỏ:** Hãy viết generator phát dãy Fibonacci `1, 1, 2, 3, 5, 8` với một object state chứa `previous`, `current` và `emittedCount`, hoàn tất **cùng lượt** khi phát phần tử thứ sáu. Mỗi callback chỉ được gọi `sink.next(...)` một lần; tạo object state mới qua supplier để mỗi subscription bắt đầu từ đầu. Sau đó thử `take(3)` và xác nhận consumer chỉ nhận ba item đầu.

Một hướng giải quyết bằng Java (snippet nằm trong class đã import `Flux`):

```java
record FibState(int previous, int current, int emittedCount) { }

Flux<Integer> fibonacci = Flux.generate(
        () -> new FibState(0, 1, 0),
        (state, sink) -> {
            sink.next(state.current());
            if (state.emittedCount() == 5) {
                sink.complete();
            }
            return new FibState(
                    state.current(),
                    state.previous() + state.current(),
                    state.emittedCount() + 1);
        });
```

Khi có đủ request, kết quả lần lượt là **1, 1, 2, 3, 5, 8** rồi hoàn tất. Vì `record` chỉ giữ số nguyên không thay đổi được, mỗi lần callback trả về một `FibState` mới. Khi mở rộng dãy vô hạn, cần tránh tràn `int` (cân nhắc `long`/`BigInteger`, ngưỡng kết thúc và hiệu năng).

**Ghi nhớ:** `Flux.generate` là công cụ **sinh dữ liệu đồng bộ, theo state, mỗi callback tối đa một `onNext`**. Nó lắng nghe demand qua subscription, hỗ trợ terminal signal và cleanup state. Chọn nó khi thuật toán tự tính phần tử kế tiếp; dùng nguồn callback bất đồng bộ hoặc factory dựng sẵn khi kiểu bài toán tương ứng.

## Tài liệu tham khảo

- Project Reactor — [Programmatically creating a sequence: Synchronous generate](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html).
- Project Reactor — [Flux API: các overload của generate](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [SynchronousSink API và giới hạn tín hiệu](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/SynchronousSink.html).
- Project Reactor — [Backpressure and ways to reshape requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [BaseSubscriber API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html).
- Spring Framework — [WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
