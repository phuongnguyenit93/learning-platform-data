# Trì hoãn tính toán bằng defer, fromSupplier và fromCallable

## 1. Vì sao cần trì hoãn tính toán khi tạo nguồn reactive?

Trong Project Reactor, một biểu thức tạo Mono hoặc Flux thường chỉ **mô tả pipeline**. Việc tạo object Publisher, việc đăng ký (subscribe) và việc thực thi một công việc là các thời điểm khác nhau. Nếu gọi một phương thức tốn thời gian **trước khi** đưa kết quả vào Publisher, công việc đã xảy ra ngay khi dựng pipeline; bọc kết quả bằng Mono không thể làm ngược điều đó.

Ví dụ:

~~~java
String value = loadData();       // loadData() chạy ngay tại đây.
Mono<String> mono = Mono.just(value); // Mono giữ giá trị đã có.
~~~

Viết ngắn lại thành Mono.just(loadData()) vẫn khiến loadData() chạy **ngay lúc biểu thức Java được đánh giá**, trước khi subscriber xuất hiện.

Ba factory quan trọng giúp tạo nguồn *lazy*:

- **Mono.defer(...)**: mỗi subscription yêu cầu factory **tạo và trả về một Mono khác**; Reactor đăng ký vào Mono vừa tạo.
- **Mono.fromSupplier(...)**: mỗi subscription thực thi Supplier.get() để tạo **một giá trị T**, hoặc hoàn tất rỗng nếu giá trị là null.
- **Mono.fromCallable(...)**: mỗi subscription thực thi Callable.call() để tạo **một giá trị T**, hoặc hoàn tất rỗng nếu là null; Callable còn cho phép ném **checked exception**.

Cả ba tạo ra Publisher thường được sử dụng theo cách **cold**, nghĩa là mỗi subscription độc lập kích hoạt lại công việc cung cấp dữ liệu. **Lazy không đồng nghĩa tự động bất đồng bộ, đa luồng hay non-blocking.** Đây là ranh giới quan trọng khi dùng với Spring WebFlux.

## 2. Ba thời điểm cần phân biệt

~~~text
T0: Assembly
    Tạo Mono, lắp ráp map/filter/flatMap...; có thể chưa có Subscriber.
                  |
                  v
T1: Subscription
    Có subscriber; cold source chuẩn bị công việc cho lần đăng ký đó.
                  |
                  v
T2: Signal
    Phát onNext(value), onComplete() hoặc onError(error).
~~~

Trong ví dụ nhỏ có dữ liệu đồng bộ, T1 và T2 có thể rất gần nhau và xảy ra **trên thread gọi subscribe()/block()**. Với nguồn có scheduler, network I/O, nguồn hot hoặc demand/cancellation, thứ tự thời gian và thread thực tế có thể khác. Nói “factory chạy khi subscription” là cách mô tả semantics, không phải cam kết rằng callback luôn chạy tại đúng dòng source code gọi subscribe() hay rằng mọi hành vi đều chạy đồng bộ.

Bảng so sánh:

| Cách tạo | Đối số factory | Khi lấy giá trị / chọn nguồn? | Dùng khi nào? |
| --- | --- | --- | --- |
| **Mono.just(value)** | Giá trị T đã tồn tại, không chấp nhận null | Giá trị được đánh giá trước/khi assembly | Đã có sẵn giá trị ổn định, muốn phát lại giá trị đó |
| **Mono.justOrEmpty(value)** | Giá trị T/Optional đã được đánh giá | Tương tự just, nhưng cho phép null/empty | Đã có giá trị tùy chọn; không cần trì hoãn tính toán |
| **Mono.fromSupplier(supplier)** | Supplier<T> trả T | Khi nguồn được subscribe và có demand phù hợp | Tính toán đồng bộ không cần khai báo checked exception |
| **Mono.fromCallable(callable)** | Callable<T> trả T, có thể throw Exception | Khi nguồn được subscribe và có demand phù hợp | Gọi hàm có checked exception; bọc API I/O đồng bộ |
| **Mono.defer(factory)** | Supplier<? extends Mono<? extends T>> trả Mono | Khi subscribe, chọn/tạo **Publisher** để subscribe tiếp | Chọn nhánh pipeline theo trạng thái ở thời điểm đăng ký, tạo nguồn mới từng subscription |

Đây là các phương thức trên **Mono**. Flux cũng có **Flux.defer** để trì hoãn việc chọn/tạo một Publisher nhiều phần tử. Không suy ra rằng Flux có cùng các phương thức fromSupplier/fromCallable với chữ ký của Mono.

## 3. Mono.fromSupplier: trì hoãn một phép tính trả về T

Chữ ký ý nghĩa:

~~~java
static <T> Mono<T> fromSupplier(Supplier<? extends T> supplier)
~~~

**java.util.function.Supplier<T>** cung cấp T qua get() và không khai báo checked exception. Khi subscription cần giá trị, Reactor gọi Supplier và phát kết quả.

~~~java
AtomicInteger version = new AtomicInteger();

Mono<String> currentValue =
        Mono.fromSupplier(() -> "version-" + version.incrementAndGet());

// Lúc này chưa tăng version.
String a = currentValue.block(); // version-1
String b = currentValue.block(); // version-2
~~~

Ở đây hai lần **block() là hai subscription riêng biệt**. Ta nhận hai giá trị khác nhau vì Supplier được gọi lại; đây không phải tính chất bắt buộc của mọi dữ liệu: nếu Supplier chỉ trả hằng số, hai subscriber vẫn có thể nhận cùng giá trị.

**Supplier trả null**: Mono.fromSupplier hoàn tất **rỗng (onComplete, không onNext)**. Nó không phát null qua onNext vì Reactor không cho phép phát phần tử null. Có thể xử lý bằng defaultIfEmpty hoặc switchIfEmpty khi cần.

~~~java
Mono<String> missing = Mono.fromSupplier(() -> null);
Mono<String> result = missing.defaultIfEmpty("unknown");
// result phát "unknown".
~~~

**Supplier ném RuntimeException**: Reactor chuyển lỗi thành onError của subscription, để các toán tử xử lý lỗi như onErrorResume nhìn thấy. Supplier<T> không khai báo throw IOException; nếu API bên dưới ném checked exception, dùng fromCallable để rõ ràng hơn.

**Tránh làm việc ngoài lambda**:

~~~java
// Sai mục tiêu lazy: hàm tốn thời gian đã chạy trước khi tạo Mono.
String cached = expensiveLookup();
Mono<String> eager = Mono.fromSupplier(() -> cached);

// Lazy đúng: lời gọi nằm trong lambda, chạy khi subscription.
Mono<String> lazy = Mono.fromSupplier(() -> expensiveLookup());
~~~

Hai đoạn này là **ví dụ minh họa**, giả sử có phương thức expensiveLookup() trả String; không phải class Java độc lập.

## 4. Mono.fromCallable: trì hoãn tính toán có thể ném checked exception

Chữ ký ý nghĩa:

~~~java
static <T> Mono<T> fromCallable(Callable<? extends T> callable)
~~~

**java.util.concurrent.Callable<T>** có phương thức call() khai báo throws Exception. Nhờ đó, các API Java như đọc file, truy vấn đồng bộ hoặc gọi thư viện cũ có checked exception có thể được đưa vào pipeline mà không cần bọc thành RuntimeException ngay trong lambda.

~~~java
import java.io.IOException;
import reactor.core.publisher.Mono;

Mono<String> value = Mono.fromCallable(() -> {
    if (externalServiceUnavailable()) {
        throw new IOException("Service unavailable");
    }
    return "ok";
});

Mono<String> recovered =
        value.onErrorResume(IOException.class, error -> Mono.just("fallback"));
~~~

Đây là đoạn minh họa: externalServiceUnavailable() chưa được định nghĩa. Lưu ý **IOException xảy ra trong subscription** và trở thành tín hiệu onError; việc gọi Mono.fromCallable(...) để lắp ráp pipeline không chạy đoạn lambda đó.

Các trường hợp kết quả:

| Callable.call() | Tín hiệu của Mono |
| --- | --- |
| Trả T khác null | onNext(T) rồi onComplete() |
| Trả null | onComplete() không phát giá trị |
| Ném Exception | onError(exception) |
| Chưa subscribe | Chưa gọi Callable vì chỉ mới tạo nguồn |

**fromCallable không tự chuyển hàm blocking thành non-blocking.** Nếu call() chờ filesystem, JDBC hoặc HTTP client đồng bộ, thread thực thi call() vẫn bị chiếm trong lúc chờ. Scheduler cần được chọn riêng khi dùng trong runtime event-loop như WebFlux.

## 5. Mono.defer: trì hoãn việc **tạo/chọn Publisher**

Chữ ký ý nghĩa:

~~~java
static <T> Mono<T> defer(Supplier<? extends Mono<? extends T>> factory)
~~~

Khác với fromSupplier/fromCallable, đối số của defer **phải trả về một Mono**, không chỉ trả T.

~~~java
AtomicBoolean usePrimary = new AtomicBoolean(true);

Mono<String> selected = Mono.defer(() ->
        usePrimary.get()
                ? Mono.just("primary")
                : Mono.just("secondary")
);

String first = selected.block(); // primary
usePrimary.set(false);
String second = selected.block(); // secondary
~~~

Cùng một object selected nhưng **mỗi subscription đánh giá lại lựa chọn**. Nếu viết:

~~~java
Mono<String> selectedEager =
        usePrimary.get() ? Mono.just("primary") : Mono.just("secondary");
~~~

thì nhánh được chọn **ngay khi lắp ráp**, vì toán tử điều kiện Java chạy trước khi Mono được đăng ký. Thay đổi usePrimary sau đó không thay nội dung Mono đã tạo.

Trường hợp phù hợp với defer:

- Chọn một trong các Publisher dựa trên cấu hình hoặc trạng thái hiện tại khi subscriber đến.
- Tạo Publisher có tham số, tài nguyên hoặc side effect của **việc khởi tạo Publisher** cần lùi đến subscription.
- Bọc nhánh fallback trong switchIfEmpty để tránh gọi hàm **xây dựng fallback** quá sớm.
- Chọn giữa Mono.empty(), Mono.error(...) hoặc Mono dữ liệu theo logic mỗi lần đăng ký.
- Dùng **Mono.deferContextual** khi cần Reactor Context riêng của từng subscriber, thay vì chỉ đọc trạng thái toàn cục.

Không cần lạm dụng defer nếu chỉ muốn gọi một hàm trả T ở thời điểm subscribe. Mono.fromSupplier(() -> getValue()) hoặc Mono.fromCallable(() -> getValue()) thường đơn giản hơn Mono.defer(() -> Mono.just(getValue())).

**Trả null thay cho Mono** là không hợp lệ: factory của defer cần trả Publisher/Mono hợp lệ; nếu trả null, subscription sẽ kết thúc bằng lỗi NullPointerException. Điều này **khác với** Supplier/Callable trả null trong fromSupplier/fromCallable, vốn được biểu diễn thành Mono rỗng.

## 6. So sánh trực quan với Mono.just

~~~text
Mono.just(load())                Mono.fromSupplier(() -> load())
     |                                         |
     | -- load() ngay lúc assembly              | -- assembly chỉ giữ Supplier
     v                                         v
  giá trị T                                   subscribe
     |                                         |
   subscribe                                   load()
     |                                         |
     v                                         v
   phát T                                    phát T

Mono.defer(() -> createMono())
     |
     | -- assembly chỉ giữ factory trả Mono
     v
   subscribe
     |
   createMono() -> Mono cụ thể
     |
  subscribe Mono cụ thể -> phát tín hiệu
~~~

Một lưu ý hữu ích: **defer trì hoãn việc tạo Mono con**, nhưng các nguồn bên trong Mono con vẫn tuân theo semantics riêng. Ví dụ Mono.defer(() -> Mono.just(expensive())) làm expensive() chạy khi factory được gọi; Mono.defer(() -> Mono.fromCallable(this::readFile)) sẽ tạo một Mono con cũng lazy và chỉ đọc file khi nó được subscribe. Việc lồng nhiều tầng lazy có thể là cần thiết để chọn pipeline, nhưng không tự mang thêm lợi ích chỉ vì có nhiều lambda.

## 7. Ví dụ Java 17+ có thể chạy: quan sát chính xác số lần gọi

Ví dụ này cô lập ba factory và so sánh với Mono.just. Sử dụng **Java 17+, Maven 3.9+**, Project Reactor Core. Tạo:

~~~text
lazy-factory-demo/
├── pom.xml
└── src/main/java/example/LazyFactoriesDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>lazy-factory-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/LazyFactoriesDemo.java**:

~~~java
package example;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class LazyFactoriesDemo {
    private static String compute(String kind, AtomicInteger counter) {
        String value = kind + "#" + counter.incrementAndGet();
        System.out.println("compute " + value);
        return value;
    }

    public static void main(String[] args) {
        AtomicInteger justCalls = new AtomicInteger();
        AtomicInteger supplierCalls = new AtomicInteger();
        AtomicInteger callableCalls = new AtomicInteger();
        AtomicInteger deferCalls = new AtomicInteger();

        Mono<String> just = Mono.just(compute("just", justCalls));

        Mono<String> supplier =
                Mono.fromSupplier(() -> compute("supplier", supplierCalls));

        Mono<String> callable =
                Mono.fromCallable(() -> compute("callable", callableCalls));

        Mono<String> deferred = Mono.defer(() -> {
            System.out.println("build deferred Mono");
            return Mono.just(compute("defer", deferCalls));
        });

        System.out.println("assembled");

        System.out.println("just A=" + just.block());
        System.out.println("just B=" + just.block());
        System.out.println("supplier A=" + supplier.block());
        System.out.println("supplier B=" + supplier.block());
        System.out.println("callable A=" + callable.block());
        System.out.println("callable B=" + callable.block());
        System.out.println("defer A=" + deferred.block());
        System.out.println("defer B=" + deferred.block());

        Mono<String> recovered = Mono.<String>fromCallable(() -> {
            throw new IOException("disk unavailable");
        }).onErrorResume(IOException.class, error -> Mono.just("fallback"));

        Mono<String> missing = Mono.fromSupplier(() -> (String) null);

        System.out.println("recovered=" + recovered.block());
        System.out.println("has value=" + missing.hasElement().block());
    }
}
~~~

Từ thư mục dự án chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.LazyFactoriesDemo
~~~

**Các dòng do chương trình in** (không tính log Maven nếu môi trường có log riêng):

~~~text
compute just#1
assembled
just A=just#1
just B=just#1
compute supplier#1
supplier A=supplier#1
compute supplier#2
supplier B=supplier#2
compute callable#1
callable A=callable#1
compute callable#2
callable B=callable#2
build deferred Mono
compute defer#1
defer A=defer#1
build deferred Mono
compute defer#2
defer B=defer#2
recovered=fallback
has value=false
~~~

Giải thích kết quả:

1. **compute just#1** xuất hiện trước **assembled** vì Mono.just(compute(...)) gọi compute ngay khi gán biến just.
2. Hai lần block() của Mono.just phát cùng giá trị đã giữ, không chạy compute lần nữa.
3. supplier.block() và callable.block() chạy lambda riêng **mỗi lần subscription**, nên mỗi counter tăng từ 1 lên 2.
4. defer.block() trước tiên in **build deferred Mono**, sau đó mới tạo Mono.just(compute(...)); cả việc chọn nguồn và tính giá trị đều xảy ra mỗi subscription.
5. Checked IOException từ Callable được biến thành onError rồi onErrorResume trả **fallback**; không cần try/catch ngoài block().
6. Supplier trả null làm Mono hoàn tất rỗng; hasElement() trả false.

**Chú ý về block():** block() chỉ được dùng ở ranh giới chương trình console để dễ quan sát kết quả. Mỗi lần block() là một subscription; không đặt block()/blockLast() trong handler WebFlux hoặc thread event-loop.

## 8. Mono.defer trong trường hợp fallback: tránh công việc khởi tạo quá sớm

Một bẫy phổ biến là tưởng switchIfEmpty sẽ trì hoãn cả việc **tạo đối số alternate**. Trong Java, đối số được đánh giá trước khi gọi phương thức:

~~~java
// Hàm expensiveFallback() đã chạy lúc lắp ráp alternate Mono:
Mono<String> alternateEager = Mono.just(expensiveFallback());
Mono<String> result = primary.switchIfEmpty(alternateEager);
~~~

Ngay cả khi primary có dữ liệu, expensiveFallback() đã chạy khi khởi tạo alternateEager.

Một phương án:

~~~java
Mono<String> result = primary.switchIfEmpty(
        Mono.defer(() -> Mono.just(expensiveFallback()))
);
~~~

Hoặc ngắn hơn nếu chỉ tạo một giá trị:

~~~java
Mono<String> result = primary.switchIfEmpty(
        Mono.fromSupplier(() -> expensiveFallback())
);
~~~

Hai đoạn là **minh họa**, giả sử primary là Mono<String> đã tồn tại và expensiveFallback() trả String khác null. Trong các đoạn lazy, expensiveFallback() chỉ chạy **nếu fallback thực sự được subscribe**. Với một primary có giá trị, switchIfEmpty không cần subscribe alternate.

Khi fallback được tạo bằng hàm trả Mono, defer đặc biệt hữu ích:

~~~java
// Chỉ khi primary rỗng mới gọi hàm tạo Publisher fallback.
Mono<String> result =
        primary.switchIfEmpty(Mono.defer(() -> buildFallbackMono()));
~~~

buildFallbackMono() trả Mono<String> và có thể chọn nhánh, ghi log hoặc cấu hình Publisher khi cần. Nếu buildFallbackMono() vốn chỉ trả một Mono.fromCallable có sẵn và không thực hiện công việc lúc lắp ráp, dùng defer thêm có thể không mang lợi ích.

## 9. Đọc Reactor Context theo subscriber: Mono.deferContextual

Đôi khi dữ liệu thay đổi theo **ngữ cảnh của từng subscription** (ví dụ tenant ID, correlation ID) chứ không theo biến global. Reactor Context là dữ liệu gắn với subscription; không nên nhầm nó với ThreadLocal.

Mono.deferContextual nhận ContextView để tạo Publisher:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> tenant = Mono.deferContextual(ctx ->
        Mono.just("tenant=" + ctx.getOrDefault("tenantId", "guest")));

System.out.println(tenant.contextWrite(
        Context.of("tenantId", "north")).block());

System.out.println(tenant.contextWrite(
        Context.of("tenantId", "south")).block());
~~~

Đây là **đoạn minh họa đặt trong phương thức Java**, không phải class độc lập. Đầu ra lần lượt là:

~~~text
tenant=north
tenant=south
~~~

Cùng một Mono ban đầu có thể tạo kết quả khác nhau theo Context của mỗi subscriber. Với dữ liệu request trong ứng dụng reactive, deferContextual thường phù hợp hơn việc đọc thông tin request từ biến tĩnh hoặc ThreadLocal không được quản lý.

## 10. Trì hoãn không tự giải quyết blocking: dùng Scheduler đúng chỗ

Phép tính Supplier/Callable thường chạy trên **thread thực hiện subscription** nếu không có operator đổi scheduler. Trong WebFlux, nếu đoạn đó chiếm thread event-loop lâu, các request khác cũng có thể bị ảnh hưởng.

Pattern khi bắt buộc tích hợp API blocking đồng bộ:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> legacyValue = Mono.fromCallable(
        () -> legacyBlockingClient.fetch()
).subscribeOn(Schedulers.boundedElastic());
~~~

Đây là ví dụ **minh họa**, giả định legacyBlockingClient.fetch() trả String và có thể blocking. Scheduler boundedElastic chuyển phần công việc đăng ký/chạy Callable sang worker phù hợp để chờ thao tác blocking; nó có **giới hạn tài nguyên**, không bảo đảm tải vô hạn. Đây là biện pháp tương thích khi chưa thể chuyển API; ưu tiên API/driver non-blocking nếu đường đi được thiết kế hoàn toàn reactive.

Các phân biệt quan trọng:

- **Mono.fromCallable** giải quyết *khi nào* code synchronous được gọi.
- **subscribeOn(Schedulers.boundedElastic())** ảnh hưởng *nơi* thực hiện phần source có tính blocking.
- Không có subscribeOn thì Callable **không tự** chạy trên thread pool khác.
- Đặt subscribeOn gần nguồn blocking để mã dễ hiểu; việc một operator map phía sau chạy trên thread nào còn phụ thuộc các operator khác như publishOn.
- Không dùng scheduler **parallel** để chờ I/O blocking lâu; các thread đó dành cho tác vụ phù hợp với mô hình non-blocking/CPU.
- boundedElastic cô lập blocking khỏi event loop nhưng không biến JDBC hoặc HTTP client đồng bộ thành I/O non-blocking; vẫn dùng một tài nguyên thực thi trong lúc chờ.
- Nếu thực hiện nhiều thao tác blocking, cân nhắc connection pool, timeout, giới hạn đồng thời và chính sách phục hồi; chỉ bọc Callable chưa đủ.

Ví dụ có cùng vấn đề dù dùng Supplier:

~~~java
// Vẫn blocking nếu subscribe trên event loop:
Mono<String> source = Mono.fromSupplier(() -> legacyBlockingClient.fetch());
~~~

Lựa chọn **fromSupplier hay fromCallable** không quyết định tính async; loại lời gọi thực tế và scheduler mới quyết định tác động lên thread.

## 11. Tác động của nhiều subscription, retry, cache và trạng thái chia sẻ

Các factory lazy thường hoạt động **theo subscription**. Đó vừa là sức mạnh, vừa là nguồn gốc của lỗi nếu lambda có side effect.

### Nhiều subscriber

~~~java
AtomicInteger count = new AtomicInteger();
Mono<Integer> source = Mono.fromSupplier(count::incrementAndGet);

Integer first = source.block();  // 1
Integer second = source.block(); // 2
~~~

Nếu hệ thống có nhiều subscriber đồng thời, side effect có thể chạy song song trên các thread tùy scheduler; dùng cấu trúc thread-safe nếu ghi state chung. Không nên giả định các subscription được serialize với nhau chỉ vì chúng dùng một object Mono.

### Retry có thể gọi lại nguồn

~~~java
AtomicInteger tries = new AtomicInteger();

Mono<String> operation = Mono.fromCallable(() -> {
    if (tries.incrementAndGet() == 1) {
        throw new java.io.IOException("temporary");
    }
    return "ok";
}).retry(1);
~~~

Đây là **đoạn code đặt trong phương thức**, không phải class độc lập. Khi được subscribe với demand phù hợp, lần đầu lỗi, retry(1) sẽ **resubscribe** vào nguồn và Callable được gọi lại. Ví dụ này thành công với "ok" khi gọi operation.block(). Đối với thao tác có side effect bên ngoài như thanh toán, ghi file, ghi database, retry có thể lặp hành động; cần thiết kế tính idempotent và chính sách retry rõ ràng.

### Cache làm thay đổi hành vi tái thực thi

~~~java
AtomicInteger count = new AtomicInteger();
Mono<Integer> cached =
        Mono.fromSupplier(count::incrementAndGet).cache();

Integer a = cached.block(); // 1
Integer b = cached.block(); // 1 (lấy tín hiệu đã cache)
~~~

**cache()** lưu kết quả/tín hiệu kết thúc cho những subscriber sau theo semantics của operator. Sau khi nguồn đã được cache, không còn đúng rằng **mỗi subscriber đều gọi lại Supplier**. Việc nguồn là cold trước khi áp dụng cache không đồng nghĩa toàn pipeline luôn thực thi lại.

**Cẩn trọng với dữ liệu cá nhân theo request:** không cache một pipeline mang thông tin tenant/user vào phạm vi toàn ứng dụng nếu chưa có chính sách khóa cache và cô lập dữ liệu phù hợp.

## 12. Dùng đúng trong Spring WebFlux

Controller WebFlux thường nên **trả Mono/Flux**, để framework điều phối subscription cùng vòng đời HTTP. Nếu service cần xây nguồn khi request thực sự được subscribe, trả Publisher lazy:

~~~java
@RestController
class ReportController {
    private final LegacyReportService reportService;

    ReportController(LegacyReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports/{id}")
    Mono<Report> getReport(@PathVariable long id) {
        return Mono.fromCallable(() -> reportService.loadById(id))
                   .subscribeOn(Schedulers.boundedElastic())
                   .switchIfEmpty(Mono.error(
                           new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}
~~~

Đoạn **minh họa cấu trúc**, giả định có lớp Report, LegacyReportService với loadById(id) có thể blocking và trả null nếu thiếu. Cần import các annotation Spring Web, Mono, Schedulers, HttpStatus và ResponseStatusException; chưa phải class độc lập. Trong mã trên:

1. Phương thức controller được gọi để **trả một Mono**; phần loadById chưa chạy khi Mono.fromCallable được tạo.
2. Khi framework subscribe, Callable được thực thi dưới boundedElastic.
3. Nếu loadById trả Report, Mono phát giá trị và WebFlux xử lý phản hồi.
4. Nếu loadById trả null, Mono hoàn tất rỗng và switchIfEmpty tạo lỗi 404.
5. Nếu loadById ném lỗi khác, pipeline nhận onError và xử lý theo error handler hiện hành.

Nếu đã có driver R2DBC hoặc HTTP client reactive thật sự, **không bọc lời gọi reactive có sẵn vào fromCallable chỉ vì muốn lazy**. Hãy trả publisher gốc hoặc dùng defer khi cần chọn hoặc tạo publisher theo subscription.

## 13. Các lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng Mono.just(expensive()) và nghĩ expensive() chạy sau | Java tính đối số trước khi gọi just | Đưa lời gọi vào fromSupplier/fromCallable hoặc defer đúng kiểu |
| Dùng Mono.defer(() -> value) với value là String | defer đòi Publisher/Mono, không phải T | Dùng Mono.fromSupplier(() -> value) hoặc Mono.defer(() -> Mono.just(value)) |
| Dùng Mono.fromSupplier cho hàm khai báo throws IOException mà không xử lý | Supplier.get() không khai báo checked exception | Dùng Mono.fromCallable |
| Chỉ dùng fromCallable cho JDBC và nghĩ đã non-blocking | Callable vẫn chiếm thread khi chờ | Dùng subscribeOn(boundedElastic) khi cần, ưu tiên API non-blocking |
| Factory defer trả null | Không có Publisher hợp lệ để subscribe | Trả Mono.empty(), Mono.justOrEmpty(value) hoặc Mono.error(...) |
| Mono.just(null) | just không nhận null | Dùng Mono.justOrEmpty(null) cho giá trị đã có, hoặc fromSupplier/fromCallable trả null để Mono rỗng |
| Gọi subscribe() trong controller rồi trả Mono.empty() | Tách tác vụ khỏi HTTP response và cancellation | Trả Mono để WebFlux sở hữu subscription |
| Dùng lambda có side effect nhưng bật retry không kiểm soát | Retry có thể thực thi side effect thêm lần nữa | Thiết kế idempotent, giới hạn và phân loại lỗi retry |
| Nghĩ Mono.fromSupplier luôn tính lại dù đã gọi cache() | cache lưu tín hiệu sau lần subscribe đầu | Chọn cache theo yêu cầu và hiểu phạm vi dùng chung |
| Đọc biến ThreadLocal trong pipeline chuyển scheduler | Thread có thể thay đổi giữa các operator | Truyền dữ liệu rõ ràng hoặc dùng Reactor Context/deferContextual |

Một lưu ý về error handling: khi factory ném lỗi ở subscription, các toán tử **onErrorResume, onErrorMap, retry** ở downstream có thể xử lý lỗi. Nhưng nếu **tính toán đã ném lỗi trước khi tạo Mono**, không có Publisher nào được tạo để downstream xử lý. Đây là một lý do thực tiễn để đặt công việc có thể lỗi vào lazy factory.

## 14. Chọn factory bằng câu hỏi ngắn

~~~text
Tôi đã có giá trị T và không cần tính lại?
    -> Mono.just(T) hoặc Mono.justOrEmpty(T).

Tôi muốn mỗi subscription tự TÍNH một giá trị T?
    -> Tính toán không cần khai báo checked exception?
           -> Mono.fromSupplier(...)
       Có thể ném checked exception?
           -> Mono.fromCallable(...)

Tôi muốn mỗi subscription tự CHỌN/TẠO một Mono/Flux?
    -> Mono.defer(...) / Flux.defer(...)

Tôi cần Context của subscriber?
    -> Mono.deferContextual(...)

Tôi gọi API blocking?
    -> Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())
       và kiểm soát tài nguyên/timeout; cân nhắc API non-blocking.
~~~

Không cần lồng defer và fromCallable cho mọi phép tính. Chọn **đơn vị cần trì hoãn**: một **giá trị** hay **việc tạo/chọn cả nguồn Publisher**. Đây là sự khác biệt thiết kế quan trọng nhất giữa ba phương thức.

## 15. Tự kiểm tra

**Câu 1.** Vì sao Mono.just(System.currentTimeMillis()) có thể phát cùng timestamp cho nhiều subscription?

Vì System.currentTimeMillis() được gọi lúc biểu thức Mono.just được đánh giá; Mono giữ giá trị đó. Mono.fromSupplier(System::currentTimeMillis) lấy thời gian ở mỗi subscription (các thời điểm gần nhau vẫn có thể có cùng millisecond).

**Câu 2.** Muốn một API đọc file ném IOException chỉ chạy khi subscribe, dùng gì?

Mono.fromCallable(() -> Files.readString(path)). Nếu gọi trong WebFlux và đó là I/O blocking, cân nhắc subscribeOn(Schedulers.boundedElastic()) và chính sách timeout/tài nguyên.

**Câu 3.** Nếu factory của Mono.defer trả null thì có phát ra null không?

Không. Nó không tạo Mono hợp lệ, dẫn đến lỗi. Để biểu diễn không có phần tử, trả Mono.empty() hoặc Mono.justOrEmpty(value).

**Câu 4.** Có thể thay fromSupplier bằng defer(() -> Mono.just(...)) không?

Có thể trong trường hợp giá trị khác null, nhưng fromSupplier thường đơn giản hơn khi chỉ tạo T. Khi giá trị có thể null, dùng Mono.justOrEmpty trong defer hoặc để Supplier/Callable trả null và Mono hoàn tất rỗng.

**Câu 5.** Dùng fromCallable rồi đặt subscribeOn(boundedElastic) có tự làm database synchronous trở thành non-blocking không?

Không. Nó điều phối công việc blocking sang worker thích hợp; bản thân lời gọi vẫn blocking tại thread đó.

**Câu 6.** Vì sao một nguồn từ fromSupplier có thể chỉ gọi Supplier một lần cho ba subscriber?

Có thể pipeline đã được áp dụng cache() hoặc operator chia sẻ khác, khiến những subscriber sau nhận lại kết quả mà không tạo subscription mới vào nguồn gốc.

**Câu 7.** Khi nào Mono.deferContextual tốt hơn Mono.defer?

Khi quyết định tạo nguồn hoặc dữ liệu phải phụ thuộc **Reactor Context của từng subscription**, chẳng hạn tenant ID, correlation ID, thay vì đọc một trạng thái global.

## 16. Tài liệu tham khảo

- [Project Reactor: Mono API — defer, deferContextual, fromSupplier, fromCallable, just](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html).
- [Project Reactor: Reactor Core Reference Guide](https://projectreactor.io/docs/core/3.6.17/reference/), phần tạo sequence và các best practices.
- [Project Reactor FAQ: wrapping a synchronous, blocking call](https://projectreactor.io/docs/core/3.6.17/reference/#faq.wrap-blocking).
- [Java 17: Supplier<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html) và [Callable<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html).

**Ghi nhớ:** **fromSupplier** và **fromCallable** trì hoãn việc tạo **giá trị** cho mỗi subscription; **defer** trì hoãn việc tạo hoặc chọn **Publisher** cho mỗi subscription. **Mono.just** nhận giá trị đã được đánh giá. Cả ba factory lazy có thể chạy code blocking nếu code bên trong blocking; muốn sử dụng an toàn trong WebFlux phải hiểu thread, demand, cancellation, lỗi và các operator như retry/cache.