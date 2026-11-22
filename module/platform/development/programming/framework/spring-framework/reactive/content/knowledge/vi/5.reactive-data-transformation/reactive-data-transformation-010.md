# transform và transformDeferred để tái sử dụng chuỗi xử lý trong Project Reactor

## 1. Bối cảnh và mục tiêu

Trong Spring WebFlux, nhiều `Flux` hoặc `Mono` cần chung một chuỗi xử lý: chuẩn hóa dữ liệu, lọc, ánh xạ, kiểm tra hợp lệ, thêm thông tin và ghi log. Viết lại cùng các lệnh `map`/`filter`/`flatMap` ở mọi nơi khiến bảo trì và kiểm thử khó hơn.

Project Reactor có hai toán tử **nhận một hàm biến đổi cả pipeline**:

- `transform(transformer)`: áp dụng hàm một lần tại **thời điểm lắp ghép (assembly)** chuỗi xử lý.
- `transformDeferred(transformer)`: áp dụng hàm **mỗi khi có một subscription** vào publisher kết quả.

Bài này giải thích chính xác hai vòng đời, cách tách chuỗi dùng chung, quản lý state theo Subscriber, những nhầm lẫn thường gặp, ví dụ Java 17+ chạy được và cách áp dụng cho mã Spring WebFlux.

## 2. Phân biệt assembly, subscription và dữ liệu

Một pipeline mẫu:

~~~java
Flux<Integer> pipeline = Flux.range(1, 4)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

pipeline.subscribe(System.out::println);
~~~

Stdout từ `Flux.range` đồng bộ:

~~~text
20
40
~~~

**Assembly** là lúc chương trình chạy chuỗi các lời gọi `Flux.range`, `filter`, `map` và tạo đối tượng Publisher kết quả. Phần lớn nguồn cold chưa phát dữ liệu ở giai đoạn này. **Subscription** bắt đầu khi có Subscriber kết nối, thiết lập `onSubscribe` và kích hoạt dữ liệu hoặc nguồn bất đồng bộ. **Xử lý phần tử** là lúc phần tử thực sự đi qua lambda của `filter` và `map`, thường sau khi subscribe.

Không được đánh đồng **hàm lắp ghép chuỗi** truyền cho `transform` với lambda **xử lý từng giá trị** truyền cho `map`. Hàm đầu nhận một Flux và trả một Publisher; lambda sau nhận từng `T` và trả `R`. Khái niệm cold/hot, request/backpressure và thứ tự tín hiệu vẫn tuân theo Publisher nguồn và các toán tử được ghép vào.

## 3. transform: đóng gói biến đổi tại assembly

Chữ ký ý tưởng với Flux:

~~~java
<V> Flux<V> transform(
        Function<? super Flux<T>, ? extends Publisher<V>> transformer)
~~~

`transformer` là `Function` nhận cả Flux hiện tại và trả một Publisher (thường thêm chuỗi các toán tử). Hàm này được Reactor **gọi ngay tại vị trí `transform` đang được lắp ghép**, tạo Flux kết quả. Nếu cùng Flux kết quả sau đó được subscribe nhiều lần, transformer **không được gọi thêm** chỉ vì có Subscriber khác.

Ví dụ biến đổi các tag văn bản:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<String>> cleanTags = input ->
        input.map(String::trim)
             .filter(s -> !s.isBlank())
             .map(String::toUpperCase);

Flux<String> tags = Flux.just(" java ", " ", "reactor ")
        .transform(cleanTags);

tags.subscribe(System.out::println);
~~~

Đầu ra:

~~~text
JAVA
REACTOR
~~~

Muốn tái sử dụng:

~~~java
// requestTags và cachedTags là hai Flux<String> sẵn có trong ứng dụng.
Flux<String> a = requestTags.transform(cleanTags);
Flux<String> b = cachedTags.transform(cleanTags);
~~~

Đây là **đoạn minh họa phụ thuộc vào dữ liệu ứng dụng**, không phải chương trình độc lập. `cleanTags` được áp dụng một lần khi xây dựng `a` và một lần khi xây dựng `b`. Mỗi lần `a` hoặc `b` được subscribe, các toán tử `map`/`filter` bên trong vẫn xử lý phần tử thực tế của từng subscription.

Có thể viết dạng phương thức tái sử dụng để tránh tạo đối tượng `Function` ở mỗi nơi:

~~~java
static Flux<String> normalize(Flux<String> input) {
    return input.map(String::trim)
                .filter(s -> !s.isBlank())
                .map(String::toLowerCase);
}

// Dùng trong lớp chứa phương thức normalize:
Flux<String> normalized = inputFlux.transform(MyTransforms::normalize);
~~~

Tên `MyTransforms` ở đây tượng trưng cho lớp utility chứa phương thức; đây chỉ là ví dụ ở mức API. Trong mã sản phẩm, đặt tên utility chính xác theo nghiệp vụ, và ưu tiên hàm thuần không giữ trạng thái mutable nếu không cần.

### transform không chạy map trước khi subscribe

~~~java
AtomicInteger assemblies = new AtomicInteger();
Flux<Integer> processed = Flux.just(1, 2)
        .transform(source -> {
            assemblies.incrementAndGet();
            return source.map(n -> n * 2);
        });

System.out.println(assemblies.get()); // 1
~~~

Hàm transformer tăng counter khi `processed` được tạo. Tuy nhiên phép nhân `n * 2` trong `map` chưa chạy. Khi có Subscriber, phần tử mới đi qua `map`. Đây là hai tầng thực thi khác nhau.

## 4. transformDeferred: áp dụng biến đổi theo từng subscription

Chữ ký ý tưởng:

~~~java
<V> Flux<V> transformDeferred(
        Function<? super Flux<T>, ? extends Publisher<V>> transformer)
~~~

`transformDeferred` vẫn nhận một hàm chuyển cả Flux, nhưng **trì hoãn việc áp dụng transformer đến khi đăng ký**. Nếu một Flux kết quả có hai Subscriber, transformer được gọi hai lần, cho phép mỗi Subscriber nhận chuỗi biến đổi được xây lại theo bối cảnh của lượt đó.

~~~text
transform:
assembly           source ── transformer() ──► pipeline đã lắp
subscribe #1                               └─► data cho S1
subscribe #2                               └─► data cho S2

transformDeferred:
assembly           source ── hoãn transformer
subscribe #1               ── transformer() ──► pipeline #1 ──► S1
subscribe #2               ── transformer() ──► pipeline #2 ──► S2
~~~

Điểm quan trọng: “mỗi subscription” nghĩa là mỗi lần kết nối đến **đúng Publisher đầu ra** ở vị trí đó. Các toán tử `retry`, `repeat` hoặc những lần kết nối lại upstream có thể ảnh hưởng số lần đăng ký tại từng đoạn; không suy luận máy móc một request HTTP = một subscription trong mọi sơ đồ.

### Trường hợp cần tạo state riêng cho mỗi Subscriber

Giả sử cần đánh số các phần tử trong **mỗi lượt đăng ký**:

~~~java
Function<Flux<String>, Flux<String>> withIndex = input -> {
    AtomicInteger sequence = new AtomicInteger();
    return input.map(value ->
            sequence.incrementAndGet() + ": " + value);
};

Flux<String> numbered = Flux.just("A", "B")
        .transformDeferred(withIndex);
~~~

Khi `numbered` được subscribe hai lần, mỗi lượt xây một `AtomicInteger` mới, nên cả hai đều nhận `1: A`, `2: B`. Nếu dùng `transform(withIndex)`, đối tượng `sequence` được tạo một lần tại assembly rồi bị closure của `map` giữ lại; lượt subscribe sau có thể tiếp tục `3: A`, `4: B`.

**Không nhầm với state của toán tử chuẩn.** Ví dụ `distinct()` của Reactor quản lý tập dữ liệu đã thấy theo mỗi subscription; đặt `distinct()` bên trong `transform` không tự khiến các Subscriber dùng chung tập dữ liệu đã thấy. Vấn đề thường đến từ state mutable mà chính người viết ứng dụng capture trong lambda.

### transformDeferred không tự cô lập biến bên ngoài

~~~java
AtomicInteger shared = new AtomicInteger();

Function<Flux<String>, Flux<String>> lambda =
        flux -> flux.map(value ->
                shared.incrementAndGet() + ": " + value);

Flux<String> stream = Flux.just("A", "B")
        .transformDeferred(lambda);
~~~

`shared` nằm **ngoài** transformer, vì vậy vẫn là một đối tượng dùng chung cho mọi lần gọi. `transformDeferred` không clone closure, field của service, static biến hay resource bên ngoài. Nếu cần state riêng, hãy cấp phát state bên trong thân transformer; nếu chia sẻ là chủ đích, thiết kế tính an toàn khi truy cập đồng thời.

## 5. Ví dụ Java 17+ hoàn chỉnh: khác biệt có thể quan sát

Ví dụ dùng `Flux.just` đồng bộ để đầu ra xác định, không phụ thuộc thời gian hoặc thread. Mỗi lần gọi transformer tạo một `generation` và một `position`. Với `transform`, state tạo ở assembly được giữ chung qua nhiều lượt subscribe. Với `transformDeferred`, state được tạo lại.

Cấu trúc thư mục:

~~~text
reactor-transform-demo/
├── build.gradle
└── src/main/java/TransformDemo.java
~~~

Nội dung `build.gradle` cho Gradle có Java toolchain (Reactor Core 3.8.8):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'TransformDemo'
}
~~~

Nội dung `src/main/java/TransformDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import reactor.core.publisher.Flux;

public class TransformDemo {
    public static void main(String[] args) {
        AtomicInteger applied = new AtomicInteger();

        Function<Flux<Integer>, Flux<String>> annotate = flux -> {
            int generation = applied.incrementAndGet();
            AtomicInteger position = new AtomicInteger();

            return flux.map(value -> generation + "/"
                    + position.incrementAndGet() + "=" + value);
        };

        Flux<String> immediate = Flux.just(3, 4).transform(annotate);
        Flux<String> deferred = Flux.just(3, 4).transformDeferred(annotate);

        System.out.println("after assembly: " + applied.get());

        immediate.collectList().subscribe(values ->
                System.out.println("transform S1: " + values));
        immediate.collectList().subscribe(values ->
                System.out.println("transform S2: " + values));

        deferred.collectList().subscribe(values ->
                System.out.println("deferred S1: " + values));
        deferred.collectList().subscribe(values ->
                System.out.println("deferred S2: " + values));

        System.out.println("after subscriptions: " + applied.get());
    }
}
~~~

Từ thư mục `reactor-transform-demo`, chạy:

~~~bash
gradle -q run
~~~

Nếu có Gradle wrapper sẵn, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows. Stdout **do chương trình** phát ra:

~~~text
after assembly: 1
transform S1: [1/1=3, 1/2=4]
transform S2: [1/3=3, 1/4=4]
deferred S1: [2/1=3, 2/2=4]
deferred S2: [3/1=3, 3/2=4]
after subscriptions: 3
~~~

Phân tích:

1. Khi khai báo `immediate`, Reactor gọi `annotate` một lần, tăng `applied` thành 1 và tạo `position` dùng với Flux ấy. Khai báo `deferred` chưa gọi transformer.
2. `transform S1` nhận `generation = 1` và chỉ số 1, 2. `transform S2` dùng lại closure của pipeline đã lắp, nên chỉ số tăng tiếp thành 3, 4.
3. `deferred S1` mới áp dụng transformer: `generation = 2`, một `position` khác đếm 1, 2.
4. `deferred S2` lại áp dụng transformer: `generation = 3` và đếm riêng 1, 2.
5. Tổng số lần gọi `annotate` là 3: một lần ở assembly, hai lần ở subscription.

`collectList()` giúp in một danh sách cho mỗi lượt trong ví dụ. Nếu thay `Flux.just` bằng nguồn bất đồng bộ, không bảo đảm thứ tự log giữa các subscriptions độc lập; phần cần kiểm chứng là số lần áp dụng transformer và ngữ nghĩa state.

## 6. Bảng so sánh lựa chọn

| Tiêu chí | `transform` | `transformDeferred` |
| --- | --- | --- |
| Thời điểm transformer được áp dụng | Assembly | Mỗi subscription |
| Pipeline được subscribe N lần | Transformer tại vị trí đó đã chạy một lần | Transformer chạy N lần |
| Transformer có thể chọn cấu trúc mới cho mỗi Subscriber | Không tự chạy lại | Có thể chọn mới theo mỗi lần gọi |
| State mutable tạo **bên trong** transformer | Có nguy cơ bị chia sẻ qua nhiều subscription | Có thể cấp phát riêng từng subscription |
| State bên ngoài bị closure capture | Có thể chia sẻ | Vẫn có thể chia sẻ |
| Chuỗi thuần như `filter` + `map` | Thường là lựa chọn đơn giản | Cũng đúng, thường không cần |
| Có tự đổi scheduler/thread? | Không | Không |
| Có tự chuyển hot publisher thành cold? | Không | Không |

Hãy chọn `transform` khi muốn **tái sử dụng một quy tắc cố định** và không cần dựng thêm pipeline theo Subscriber. Hãy chọn `transformDeferred` khi transformer thực sự cần **tạo state mới hoặc quyết định khác nhau theo lượt đăng ký**. Đừng chọn deferred chỉ vì “Reactor là lazy”: các lambda xử lý phần tử của toán tử chuẩn đã chạy khi dữ liệu đi qua.

## 7. Áp dụng trong Spring WebFlux

### Tái sử dụng quy tắc cho dịch vụ

Đoạn sau là một lớp trong ứng dụng WebFlux, không phải chương trình độc lập:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

public final class TagService {
    private static final Function<Flux<String>, Flux<String>> CLEAN_TAGS =
            input -> input.map(String::trim)
                          .filter(s -> !s.isBlank())
                          .map(String::toLowerCase)
                          .distinct();

    public Flux<String> clean(Flux<String> values) {
        return values.transform(CLEAN_TAGS);
    }
}
~~~

Có thể chuyển `Flux<String>` từ HTTP body, messaging hoặc repository qua service này. Phần xử lý được giữ cùng một chỗ. `distinct` trong ví dụ quản lý việc loại trùng cho **mỗi subscription**, nên không lấy các tag ở Subscriber này làm điều kiện loại tag ở Subscriber khác.

### Đánh số theo subscription

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;

// Đặt trong một service của WebFlux.
public Flux<String> numbered(Flux<String> input) {
    return input.transformDeferred(source -> {
        AtomicInteger index = new AtomicInteger();
        return source.map(value -> index.incrementAndGet() + ": " + value);
    });
}
~~~

Không đặt `AtomicInteger` ở field của Spring singleton service nếu mong mỗi lần xử lý có chỉ số riêng. `transformDeferred` cho phép state riêng theo **subscription**, và đó mới là phạm vi được bảo đảm.

Trong controller WebFlux, trả về `Flux`/`Mono` thay vì tự gọi `subscribe()` hoặc `block()` để Spring điều phối subscription, cancellation, backpressure và lỗi. Nếu transformer có truy vấn blocking, chuyển sang API nonblocking phù hợp hoặc dùng kỹ thuật bọc nguồn blocking trên scheduler thích hợp; `transformDeferred` không tự tránh blocking.

## 8. Dùng với Mono và Context

### Mono cũng hỗ trợ hai toán tử

~~~java
import reactor.core.publisher.Mono;

Mono<String> a = Mono.just("  Spring ")
        .transform(m -> m.map(String::trim).map(String::toUpperCase));

Mono<String> b = Mono.just("  Spring ")
        .transformDeferred(m -> m.map(String::trim).map(String::toUpperCase));
~~~

Khi subscribe, cả hai phát `"SPRING"` rồi complete. Với lambda thuần như trên, `transform` đã đáp ứng nhu cầu tái sử dụng; `transformDeferred` có ý nghĩa nếu hàm cần cấp phát state hoặc chọn đoạn xử lý theo subscriber. `Mono.empty()` vẫn complete mà không kích hoạt `map` nếu transformer không thêm fallback.

### Context theo Subscriber: transformDeferredContextual

Nếu muốn xây dựng phần xử lý dựa trên Reactor `ContextView` của Subscriber, dùng biến thể chuyên dụng `transformDeferredContextual`:

~~~java
import reactor.core.publisher.Flux;
import reactor.util.context.Context;

Flux<String> tagged = Flux.just("a", "b")
        .transformDeferredContextual((source, ctx) -> {
            String tenant = ctx.getOrDefault("tenant", "public");
            return source.map(v -> tenant + ":" + v);
        });

tagged.contextWrite(Context.of("tenant", "teamA"))
      .subscribe(System.out::println);
~~~

Với nguồn đồng bộ, stdout:

~~~text
teamA:a
teamA:b
~~~

`Context` là metadata gắn với subscription theo mô hình Reactor, giúp truyền request/correlation id mà không phụ thuộc thread-local. Không giả định `transformDeferred` thường tự cung cấp `ContextView`; cần phương thức `transformDeferredContextual` hoặc một toán tử chuyên đọc Context.

## 9. Phân biệt với các API gần nhau

- `map(fn)`: nhận **một phần tử** để biến thành phần tử khác; gọi khi có `onNext`.
- `flatMap(fn)`: nhận **một phần tử** và tạo nguồn bất đồng bộ liên quan; với `Flux.flatMap` có thể đan xen các inner publisher.
- `transform(fn)`: nhận **cả Flux/Mono** và ghép đoạn toán tử một lần tại assembly.
- `transformDeferred(fn)`: nhận **cả Flux/Mono**, ghép đoạn đó khi mỗi Subscriber đăng ký.
- `Flux.defer(supplier)` / `Mono.defer(supplier)`: trì hoãn **tạo Publisher nguồn** đến mỗi lần subscribe; không có tham số là Flux đã tồn tại để ghép thêm đoạn transformer.
- `as(fn)`: cho phép chuyển toàn bộ Flux/Mono thành một **kiểu kết quả khác** (không nhất thiết là Publisher), nên không thay thế trực tiếp hai toán tử trên.
- `transformDeferredContextual`: biến thể cho transformer đọc `ContextView`.

Một hàm tái sử dụng dạng `f -> f.filter(...).map(...)` không phải `flatMap` vì nó vận hành trên Publisher, không phải cho mỗi phần tử. `transformDeferred` cũng không tự đổi nguồn cold sang hot, và không tự thực hiện trên thread riêng.

## 10. Kiểm thử với StepVerifier

Với dự án có `reactor-test` và JUnit 5 ở test scope, có thể kiểm chứng thời điểm áp dụng transformer. Ví dụ nếu dùng Gradle đơn giản, khai báo thêm:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/test/java/TransformTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class TransformTest {
    @Test
    void immediateAppliedAtAssembly() {
        AtomicInteger calls = new AtomicInteger();
        Function<Flux<Integer>, Flux<Integer>> f = source -> {
            int increment = calls.incrementAndGet();
            return source.map(n -> n + increment);
        };

        Flux<Integer> data = Flux.just(10).transform(f);
        assertEquals(1, calls.get());

        StepVerifier.create(data).expectNext(11).verifyComplete();
        StepVerifier.create(data).expectNext(11).verifyComplete();
        assertEquals(1, calls.get());
    }

    @Test
    void deferredAppliedForEachSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Function<Flux<Integer>, Flux<Integer>> f = source -> {
            int increment = calls.incrementAndGet();
            return source.map(n -> n + increment);
        };

        Flux<Integer> data = Flux.just(10).transformDeferred(f);
        assertEquals(0, calls.get());

        StepVerifier.create(data).expectNext(11).verifyComplete();
        StepVerifier.create(data).expectNext(12).verifyComplete();
        assertEquals(2, calls.get());
    }
}
~~~

Hai tests độc lập minh họa: `transform` gọi transformer một lần trước subscribe và giá trị từ closure là cố định; `transformDeferred` chưa gọi transformer ở assembly, tăng counter lần lượt khi hai Subscriber đăng ký. Đó là kiểm thử đúng hợp đồng. Các dự án nhiều luồng cần thêm tình huống concurrency và cancellation, tránh dựa vào log đan xen giữa subscribers.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Cho rằng `transform` chạy một lần cho mỗi `onNext` | Sai vòng đời hàm. | Transformer chạy ở assembly; `map` bên trong chạy theo phần tử. |
| Tạo counter trong transformer dùng `transform` rồi kỳ vọng reset theo Subscriber | Closure capture state đã tạo một lần. | Dùng `transformDeferred` nếu cần counter riêng. |
| Dùng `transformDeferred` nhưng giữ state ở biến ngoài/field singleton | State vẫn dùng chung. | Cấp phát trong transformer, hoặc chủ động quản lý shared state. |
| Cho rằng mọi toán tử stateful bên trong `transform` bị chia sẻ state | Hiểu sai operator state của Reactor. | Phân biệt state Reactor quản lý theo subscription với closure mutable của ứng dụng. |
| Dùng `transformDeferred` cho chuỗi thuần không cần thêm điều kiện | Không mang lại lợi ích rõ ràng; tốn công gọi transformer lặp lại. | Ưu tiên `transform` cho chuỗi cố định. |
| Gọi I/O blocking trực tiếp trong transformer | Có thể chặn thread tại assembly hoặc lúc subscribe. | Thiết kế nguồn không chặn hoặc bọc tác vụ blocking có scheduler phù hợp. |
| Nhầm `transformDeferred` tự tạo scheduler | Vẫn chạy theo thread do nguồn/toán tử quyết định. | Dùng `subscribeOn` / `publishOn` theo nhu cầu thực tế. |
| Dùng `transformDeferred` rồi nghĩ nguồn hot biến thành cold | Bản chất upstream không tự đổi. | Xem kỹ nguồn, cache/share/publish và subscription lifecycle. |
| Dùng `flatMap` để ghép đoạn biến đổi dùng chung | `flatMap` áp dụng trên từng phần tử. | Dùng `transform` / `transformDeferred` để ghép toàn pipeline. |
| Gọi `block()` trong WebFlux handler để quan sát pipeline | Chặn event loop và mất lợi ích reactive. | Trả về Publisher, dùng StepVerifier trong test và hook quan sát khi cần. |

Khi chẩn đoán, dùng `.log("before")`/`.log("after")` hoặc `doOnSubscribe` để quan sát tín hiệu runtime. Muốn biết transformer được áp dụng bao nhiêu lần, đặt counter/log ngay **trong hàm transformer**, vì log `onNext` chỉ cho biết số phần tử đi qua, không cho biết assembly diễn ra lúc nào.

## 12. Câu hỏi tự kiểm tra

1. Một Flux dùng `transform(f)` và được subscribe ba lần, `f` được áp dụng mấy lần ở vị trí đó? **Một lần tại assembly.**
2. Với `transformDeferred(f)`, ba subscriptions thì `f` được gọi bao nhiêu lần? **Ba lần.**
3. `transformDeferred` có tự chạy trên thread khác hay tạo hot publisher không? **Không.**
4. Đặt `AtomicInteger` ở **ngoài** transformer có tự thành state riêng khi dùng `transformDeferred` không? **Không; closure vẫn chia sẻ tham chiếu.**
5. Tại sao `distinct()` trong `transform` thường không trộn dữ liệu seen giữa hai Subscriber? **Vì state chuẩn của toán tử này thuộc từng subscription.**
6. Muốn đọc request metadata từ Reactor Context khi dựng chuỗi per-subscription dùng gì? **`transformDeferredContextual`.**
7. Logic thuần chuẩn hóa tên không cần state theo Subscriber nên chọn gì? **Thường chọn `transform`.**

**Điểm cần nhớ:** `transform` áp dụng **hàm ghép chuỗi** tại assembly để tái sử dụng logic cố định. `transformDeferred` áp dụng hàm ấy **cho từng subscription** để có thể tạo chuỗi và state riêng. Luôn phân biệt state do Reactor quản lý với mutable state trong closure và hiểu rõ phạm vi của các lần subscribe.

## Tài liệu tham khảo

- [Project Reactor — Mutualizing Operator Usage: transform và transformDeferred](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-mutualizing-operator-usage.html).
- [Project Reactor — Flux Javadoc (transform, transformDeferred, transformDeferredContextual)](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor — Testing với StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
